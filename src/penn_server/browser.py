"""One async Chromium profile, decrypted only on tmpfs. No traces or recordings."""

import asyncio
import base64
import io
import json
import shutil
import zipfile
from urllib.parse import urlsplit


class Browser:
    def __init__(self, settings, vault):
        self.settings, self.vault = settings, vault
        self.context = self.page = self.pw = None
        self.profile = settings.runtime_dir / "profile"
        self.last_status = None

    async def start(self):
        from playwright.async_api import async_playwright

        self.settings.runtime_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        saved = self.vault.read("browser", {})
        # Runtime state is disposable; the encrypted checkpoint is authoritative.
        shutil.rmtree(self.profile, ignore_errors=True)
        self.profile.mkdir(mode=0o700)
        if saved.get("profile"):
            with zipfile.ZipFile(
                io.BytesIO(base64.b64decode(saved["profile"]))
            ) as archive:
                total = 0
                for entry in archive.infolist():
                    target = (self.profile / entry.filename).resolve()
                    total += entry.file_size
                    if (
                        not target.is_relative_to(self.profile.resolve())
                        or total > 256 * 1024 * 1024
                    ):
                        raise ValueError("Invalid browser checkpoint")
                    if entry.is_dir():
                        target.mkdir(mode=0o700, parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                        target.write_bytes(archive.read(entry))
                        target.chmod(0o600)
        self.pw = await async_playwright().start()
        await self._open()
        if saved.get("storage"):
            await self.context.add_cookies(saved["storage"].get("cookies", []))

    async def _open(self):
        self.context = await self.pw.chromium.launch_persistent_context(
            str(self.profile),
            headless=True,
            viewport={"width": 1100, "height": 800},
            accept_downloads=False,
            service_workers="block",
            args=["--disable-breakpad", "--disable-crash-reporter"],
        )
        self.page = (
            self.context.pages[0]
            if self.context.pages
            else await self.context.new_page()
        )
        # Capture only the configured Penn credential origin, never arbitrary forms.
        await self.context.route("**/*", self._route)
        await self.context.expose_binding("__penn_credentials", self._capture)
        hosts = json.dumps(list(self.settings.login_hosts))
        await self.context.add_init_script(
            """(() => {
          const hosts = HOSTS;
          if (!hosts.includes(location.hostname)) return;
          document.addEventListener('submit', e => {
            const p = e.target.querySelector('input[type="password"]');
            const u = e.target.querySelector('input[autocomplete="username"],input[name="j_username"],input[name="username"]');
            if (u && p && u.value && p.value) window.__penn_credentials({username:u.value,password:p.value});
          }, true);
        })();""".replace("HOSTS", hosts)
        )

    async def _route(self, route):
        request = route.request
        parsed = urlsplit(request.url)
        host = parsed.hostname or ""
        # The login viewer cannot navigate arbitrary hosts or mutate coursework.
        if request.is_navigation_request() and request.frame == self.page.main_frame:
            allowed = (
                host == "penn.instructure.com"
                or host in self.settings.login_hosts
                or host.endswith(".duosecurity.com")
            )
            if parsed.scheme != "https" or not allowed:
                await route.abort()
                return
        if (
            self.settings.testing_read_only
            and host == "penn.instructure.com"
            and request.method not in ("GET", "HEAD", "OPTIONS")
        ):
            # SAML login is authentication, not a coursework mutation.
            if parsed.path not in ("/login/saml", "/login/saml/consume"):
                await route.abort()
                return
        await route.continue_()

    async def _capture(self, source, value):
        origin = urlsplit(source["frame"].url)
        if origin.scheme != "https" or origin.hostname not in self.settings.login_hosts:
            return
        if isinstance(value, dict) and value.get("username") and value.get("password"):
            self.vault.write("pennkey_pending", value)

    async def probe(self):
        # Recover a crashed Chromium from the encrypted checkpoint without
        # creating a new login incident or clearing its push reservation.
        if self.context and (
            (self.page and self.page.is_closed())
            or (self.context.browser and not self.context.browser.is_connected())
        ):
            await self.pw.stop()
            await self.start()
        try:
            response = await self.context.request.get(
                self.settings.canvas_origin + "/api/v1/users/self",
                max_redirects=0,
                timeout=10000,
            )
            if response.status == 200:
                if "json" not in response.headers.get("content-type", ""):
                    return 401
                user = await response.json()
                identity = self.vault.read("identity", {})
                expected = self.settings.expected_user_id or identity.get("id")
                if expected and str(user.get("id")) != str(expected):
                    raise RuntimeError("Canvas identity mismatch")
                if not user.get("id"):
                    return 401
                self.vault.write("identity", {"id": str(user["id"])})
                pending = self.vault.read("pennkey_pending")
                if pending and pending.get("password"):
                    self.vault.write("pennkey", pending)
                    self.vault.write("pennkey_pending", {})
                return 200
            return (
                401
                if response.status in (301, 302, 303, 307, 308, 401)
                else response.status
            )
        except RuntimeError:
            raise
        except Exception:
            return 503

    async def checkpoint(self):
        storage = await self.context.storage_state()
        # Close before archiving SQLite/profile data; do not copy live databases.
        await self.context.close()
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in self.profile.rglob("*"):
                if (
                    path.is_file()
                    and not path.is_symlink()
                    and not any(
                        p in ("Cache", "Code Cache", "GPUCache", "Crashpad")
                        for p in path.parts
                    )
                ):
                    archive.write(path, path.relative_to(self.profile))
                    if output.tell() > 128 * 1024 * 1024:
                        raise RuntimeError("Browser checkpoint exceeded size limit")
        self.vault.write(
            "browser",
            dict(storage=storage, profile=base64.b64encode(output.getvalue()).decode()),
        )
        await self._open()
        await self.context.add_cookies(storage["cookies"])

    async def relogin(self, allow_password=True, allow_push=False):
        # The session manager reserves an incident's one possible push BEFORE
        # navigating: Duo can send a push automatically on arrival.
        try:
            await self.page.goto(
                self.settings.canvas_origin + "/login/saml",
                wait_until="domcontentloaded",
                timeout=30000,
            )
        except Exception:
            return "manual_required"
        credentials = self.vault.read("pennkey", {}) if allow_password else {}
        submitted = False
        for _ in range(40):
            if await self.probe() == 200:
                return "healthy"
            for frame in self.page.frames:
                host = urlsplit(frame.url).hostname or ""
                if (
                    urlsplit(frame.url).scheme == "https"
                    and host in self.settings.login_hosts
                    and credentials
                    and not submitted
                ):
                    u = frame.locator(
                        'input[autocomplete="username"], input[name="j_username"], input[name="username"]'
                    ).first
                    p = frame.locator('input[type="password"]').first
                    if await u.count() and await p.count() and await p.is_visible():
                        await u.fill(credentials["username"])
                        await p.fill(credentials["password"])
                        submitted = (
                            True  # before submission, never repeat rejected passwords
                        )
                        await p.press("Enter")
                if host.endswith(".duosecurity.com"):
                    # Duo may already have initiated its automatic push. Never
                    # click push, retry or resend: this conservatively prevents
                    # a second push when the prompt state is ambiguous.
                    trust = frame.get_by_role(
                        "button", name="Yes, this is my device", exact=True
                    )
                    if await trust.count() and await trust.first.is_visible():
                        await trust.first.click()
            await asyncio.sleep(1)
        return (
            "mfa_required"
            if any(
                (urlsplit(f.url).hostname or "").endswith(".duosecurity.com")
                for f in self.page.frames
            )
            else "manual_required"
        )

    async def request(self, method, path, params=None, data=None):
        if self.settings.testing_read_only and method != "GET":
            raise PermissionError("Testing mode blocks all real Canvas writes")
        url = self.settings.canvas_origin + path
        headers = {"Accept": "application/json+canvas-string-ids"}
        if method != "GET":
            from urllib.parse import unquote

            for cookie in await self.context.cookies(self.settings.canvas_origin):
                if cookie["name"] == "_csrf_token":
                    headers["X-CSRF-Token"] = unquote(cookie["value"])
            if "X-CSRF-Token" not in headers:
                raise RuntimeError("Canvas CSRF token unavailable")
        response = await self.context.request.fetch(
            url,
            method=method,
            params=params,
            data=data,
            headers=headers,
            max_redirects=0,
            timeout=30000,
        )
        self.last_status = response.status
        if response.status >= 300:
            # Never include upstream response bodies, cookies, or signed URLs in errors.
            raise RuntimeError("Canvas request failed: HTTP " + str(response.status))
        if response.status == 204:
            return {}, response.headers
        return await response.json(), response.headers

    async def close(self):
        if self.context:
            await self.checkpoint()
            await self.context.close()
        if self.pw:
            await self.pw.stop()
        shutil.rmtree(self.profile, ignore_errors=True)
