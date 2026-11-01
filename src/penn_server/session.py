"""Serialized session recovery; push reservation is durable before any push."""

import asyncio
import time
import uuid


class SessionUnavailable(RuntimeError):
    pass


class SessionManager:
    def __init__(self, browser, vault, notifier):
        self.browser, self.vault, self.notifier = browser, vault, notifier
        self.lock = asyncio.Lock()
        self.last_probe = 0.0
        self.last_checkpoint = 0.0

    def status(self):
        state = self.vault.read("session", {})
        return {
            k: state.get(k) for k in ("phase", "incident", "push_reserved", "last_ok")
        }

    async def _healthy(self):
        status = await self.browser.probe()
        if status == 200:
            state = self.vault.read("session", {})
            if state.get("incident"):
                self.notifier.queue(
                    state["incident"] + "-recovered",
                    "Penn Canvas recovered",
                    "Automatic session recovery completed.",
                )
            self.vault.write(
                "session",
                dict(phase="healthy", last_ok=time.time(), push_reserved=False),
            )
            now = time.monotonic()
            if state.get("incident") or now - self.last_checkpoint >= 60:
                await self.browser.checkpoint()
                self.last_checkpoint = now
            self.last_probe = now
            return True
        if status == 401:
            return False
        raise SessionUnavailable(
            "Canvas is temporarily unavailable; login was not retried"
        )

    async def ensure(self, force=False):
        async with self.lock:
            if (
                not force
                and self.last_probe
                and time.monotonic() - self.last_probe < 30
            ):
                return
            if await self._healthy():
                return
            # Retry a failed authentication probe exactly once before recovery.
            if await self._healthy():
                return
            state = self.vault.read("session", {})
            if not state.get("incident"):
                state = dict(
                    phase="recovering", incident=uuid.uuid4().hex, push_reserved=False
                )
                self.vault.write("session", state)
                self.notifier.queue(
                    state["incident"],
                    "Penn Canvas session expired",
                    "Automatic recovery is in progress. No action is needed unless a follow-up email requests it.",
                )
            # A paused incident may still recover after a late approval; probe above
            # observes it without generating another password attempt or push.
            if state.get("phase") in ("manual_required", "mfa_wait"):
                raise SessionUnavailable(
                    "Recovery is waiting; check the incident email"
                )
            if state.get("push_reserved"):
                raise SessionUnavailable(
                    "This incident already attempted login; check email"
                )
            state.update(push_reserved=True, phase="recovering")
            self.vault.write("session", state)
            result = await self.browser.relogin(allow_password=True, allow_push=True)
            if result == "healthy" and await self._healthy():
                return
            if result == "mfa_required":
                state["phase"] = "mfa_wait"
                self.notifier.queue(
                    state["incident"] + "-mfa",
                    "Penn Canvas needs Duo approval",
                    "Penn requires Duo authentication. Approve the pending request on your enrolled device. No additional push will be initiated for this incident.",
                )
            else:
                state["phase"] = "manual_required"
                self.notifier.queue(
                    state["incident"] + "-manual",
                    "Penn Canvas needs login recovery",
                    "Automatic recovery could not complete. Open "
                    + self.browser.settings.public_url
                    + self.browser.settings.prefix
                    + "/login . Never send credentials through chat.",
                )
            self.vault.write("session", state)
            raise SessionUnavailable(
                "Session recovery pending; check the incident email"
            )

    async def heartbeat(self):
        try:
            await self.ensure(force=True)
        except SessionUnavailable:
            pass
