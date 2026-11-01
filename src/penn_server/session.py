"""Serialized, self-healing recovery with a durable one-push incident limit."""

import asyncio
import logging
import time
import uuid

log = logging.getLogger("penn.session")


class SessionUnavailable(RuntimeError):
    pass


class SessionManager:
    def __init__(self, browser, vault):
        self.browser, self.vault = browser, vault
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
            now = time.monotonic()
            if state.get("incident") or now - self.last_checkpoint >= 60:
                await self.browser.checkpoint()
                self.last_checkpoint = now
            self.vault.write(
                "session",
                dict(phase="healthy", last_ok=time.time(), push_reserved=False),
            )
            self.last_probe = now
            if state.get("incident"):
                log.info("session_recovered incident=%s", state["incident"])
            return True
        self.last_probe = 0.0
        if status == 401:
            return False
        log.warning("canvas_probe_unavailable status=%s", status)
        raise SessionUnavailable(
            "Canvas temporarily unavailable; recovery will retry automatically"
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
            if await self._healthy():
                return
            state = self.vault.read("session", {})
            if not state.get("incident"):
                state = dict(
                    phase="recovering", incident=uuid.uuid4().hex, push_reserved=False
                )
                self.vault.write("session", state)
                log.warning(
                    "session_expired incident=%s recovery=automatic", state["incident"]
                )
            # Every heartbeat still probes for a late approval/restored session.
            # A restart must never create a second automatic push in this incident.
            if state.get("phase") in ("manual_required", "mfa_wait") or state.get(
                "push_reserved"
            ):
                raise SessionUnavailable(
                    "Session recovery pending; status is recorded locally"
                )
            state.update(push_reserved=True, phase="recovering")
            self.vault.write("session", state)
            result = await self.browser.relogin(allow_password=True, allow_push=True)
            if result == "healthy" and await self._healthy():
                return
            state["phase"] = (
                "mfa_wait" if result == "mfa_required" else "manual_required"
            )
            self.vault.write("session", state)
            log.warning(
                "session_recovery_pending incident=%s phase=%s",
                state["incident"],
                state["phase"],
            )
            raise SessionUnavailable(
                "Session recovery pending; status is recorded locally"
            )

    async def heartbeat(self):
        try:
            await self.ensure(force=True)
            return True
        except SessionUnavailable:
            # Expected outage/authentication states do not crash-loop or resend Duo.
            return False
