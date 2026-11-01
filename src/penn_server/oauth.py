"""Single-owner OAuth 2.1 subset with exact redirects, S256 PKCE and rotation.

Opaque credentials are stored only as hashes. OAuth state is encrypted at rest.
The owner password is provisioned out of band; Canvas credentials never enter here.
"""

import base64
import hashlib
import hmac
import html
import json
import re
import secrets
import time
from urllib.parse import urlencode

from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def challenge(value):
    return (
        base64.urlsafe_b64encode(hashlib.sha256(value.encode()).digest())
        .rstrip(b"=")
        .decode()
    )


class OAuth:
    def __init__(self, settings, vault):
        self.settings, self.vault = settings, vault
        if settings.owner_file.stat().st_mode & 0o077:
            raise ValueError("Owner password must not be group/world accessible")
        self.owner_digest = digest(settings.owner_file.read_text().strip())
        if len(settings.owner_file.read_text().strip()) < 32:
            raise ValueError("Provision an owner password of at least 32 characters")
        self.failures = []

    def owner_ok(self, password):
        now = time.time()
        self.failures = [t for t in self.failures if t > now - 900]
        if len(self.failures) >= 10:
            return False
        ok = hmac.compare_digest(digest(password), self.owner_digest)
        if not ok:
            self.failures.append(now)
        return ok

    @property
    def resource(self):
        return self.settings.public_url + self.settings.prefix + "/mcp"

    async def metadata(self, request):
        base = self.settings.public_url
        return JSONResponse(
            dict(
                issuer=base,
                authorization_endpoint=base + "/authorize",
                token_endpoint=base + "/token",
                registration_endpoint=base + "/register",
                revocation_endpoint=base + "/revoke",
                response_types_supported=["code"],
                grant_types_supported=["authorization_code", "refresh_token"],
                code_challenge_methods_supported=["S256"],
                token_endpoint_auth_methods_supported=["none"],
                scopes_supported=["canvas:read", "canvas:write"],
            )
        )

    async def resource_metadata(self, request):
        return JSONResponse(
            dict(
                resource=self.resource,
                authorization_servers=[self.settings.public_url],
                scopes_supported=["canvas:read", "canvas:write"],
                bearer_methods_supported=["header"],
            )
        )

    async def register(self, request):
        try:
            body = await request.json()
            redirects = body["redirect_uris"]
            if not isinstance(redirects, list) or not redirects or len(redirects) > 10:
                raise ValueError()
            if any(r not in self.settings.redirects for r in redirects):
                raise ValueError()
            if body.get("token_endpoint_auth_method", "none") != "none":
                raise ValueError()
            identifier = secrets.token_urlsafe(24)
            with self.vault.transaction(
                "oauth", dict(clients={}, codes={}, tokens={}, refresh={})
            ) as db:
                if len(db["clients"]) >= 100:
                    raise ValueError()
                db["clients"][identifier] = dict(redirects=redirects)
            return JSONResponse(
                dict(
                    client_id=identifier,
                    redirect_uris=redirects,
                    token_endpoint_auth_method="none",
                    grant_types=["authorization_code", "refresh_token"],
                    response_types=["code"],
                ),
                status_code=201,
            )
        except (ValueError, KeyError, TypeError):
            return JSONResponse({"error": "invalid_client_metadata"}, status_code=400)

    def _authorization(self, params):
        db = self.vault.read("oauth", dict(clients={}))
        client = db["clients"].get(params.get("client_id"))
        if not client or params.get("redirect_uri") not in client["redirects"]:
            raise ValueError("Invalid client or redirect")
        if (
            params.get("response_type") != "code"
            or params.get("code_challenge_method") != "S256"
        ):
            raise ValueError("Authorization code with S256 PKCE is required")
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", params.get("code_challenge", "")):
            raise ValueError("Invalid PKCE challenge")
        if params.get("resource") not in (None, self.resource):
            raise ValueError("Invalid resource")
        scopes = set(params.get("scope", "canvas:read").split())
        if not scopes or not scopes <= {"canvas:read", "canvas:write"}:
            raise ValueError("Invalid scopes")
        return sorted(scopes)

    async def authorize(self, request):
        try:
            if request.method == "GET":
                params = dict(request.query_params)
                self._authorization(params)
                nonce = secrets.token_urlsafe(32)
                # Signed/encrypted form state binds the redirect and requested scopes.
                ticket = self.vault.cipher.encrypt(
                    json.dumps(dict(params=params, nonce=nonce)).encode()
                ).decode()
                content = (
                    "<h1>Penn Canvas connector sign-in</h1><p>Authorize this client: "
                    + html.escape(params["client_id"])
                    + "</p>"
                )
                content += (
                    "<p>Scopes: "
                    + html.escape(params.get("scope", "canvas:read"))
                    + "</p>"
                )
                content += (
                    '<form method="post"><input type="hidden" name="ticket" value="'
                    + html.escape(ticket, quote=True)
                    + '"><label>Owner password <input type="password" name="password" autocomplete="current-password" required></label><button>Authorize</button></form>'
                )
                response = HTMLResponse(content)
                response.set_cookie(
                    "penn_oauth_csrf",
                    nonce,
                    secure=True,
                    httponly=True,
                    samesite="lax",
                    max_age=600,
                )
                return response
            form = await request.form()
            saved = json.loads(
                self.vault.cipher.decrypt(str(form["ticket"]).encode(), ttl=600)
            )
            if not hmac.compare_digest(
                saved["nonce"], request.cookies.get("penn_oauth_csrf", "")
            ):
                raise ValueError("Invalid form session")
            params = saved["params"]
            scopes = self._authorization(params)
            if not self.owner_ok(str(form.get("password", ""))):
                return HTMLResponse("Sign-in failed or rate limited", status_code=403)
            code = secrets.token_urlsafe(32)
            with self.vault.transaction("oauth") as db:
                db["codes"] = {
                    k: v for k, v in db["codes"].items() if v["expires"] > time.time()
                }
                db["codes"][digest(code)] = dict(
                    client=params["client_id"],
                    redirect=params["redirect_uri"],
                    challenge=params["code_challenge"],
                    scopes=scopes,
                    expires=time.time() + 120,
                )
            query = dict(code=code)
            if "state" in params:
                query["state"] = params["state"]
            response = RedirectResponse(
                params["redirect_uri"]
                + ("&" if "?" in params["redirect_uri"] else "?")
                + urlencode(query),
                status_code=303,
            )
            response.delete_cookie(
                "penn_oauth_csrf", secure=True, httponly=True, samesite="lax"
            )
            return response
        except Exception:
            return JSONResponse({"error": "invalid_request"}, status_code=400)

    async def token(self, request):
        try:
            form = await request.form()
            client = str(form.get("client_id", ""))
            if form.get("resource") not in (None, self.resource):
                raise ValueError()
            with self.vault.transaction("oauth") as db:
                if form.get("grant_type") == "authorization_code":
                    key = digest(str(form.get("code", "")))
                    grant = db["codes"].get(key)
                    verifier = str(form.get("code_verifier", ""))
                    if (
                        not grant
                        or grant["expires"] < time.time()
                        or grant["client"] != client
                        or grant["redirect"] != form.get("redirect_uri")
                        or not re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", verifier)
                        or not hmac.compare_digest(
                            grant["challenge"], challenge(verifier)
                        )
                    ):
                        raise ValueError()
                    del db["codes"][key]
                    family = secrets.token_urlsafe(24)
                elif form.get("grant_type") == "refresh_token":
                    key = digest(str(form.get("refresh_token", "")))
                    spent = db.setdefault("spent_refresh", {})
                    old = spent.get(key)
                    if old and old["client"] == client:
                        for kind in ("tokens", "refresh"):
                            db[kind] = {
                                k: v
                                for k, v in db[kind].items()
                                if v["family"] != old["family"]
                            }
                        return JSONResponse({"error": "invalid_grant"}, status_code=400)
                    grant = db["refresh"].get(key)
                    if (
                        not grant
                        or grant["expires"] < time.time()
                        or grant["client"] != client
                    ):
                        raise ValueError()
                    spent[key] = dict(grant)
                    del db["refresh"][key]
                    family = grant["family"]
                else:
                    raise ValueError()
                db["spent_refresh"] = {
                    k: v
                    for k, v in db.get("spent_refresh", {}).items()
                    if v["expires"] > time.time()
                }
                access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                db["tokens"] = {
                    k: v for k, v in db["tokens"].items() if v["expires"] > time.time()
                }
                db["refresh"] = {
                    k: v for k, v in db["refresh"].items() if v["expires"] > time.time()
                }
                common = dict(
                    client=client,
                    scopes=grant["scopes"],
                    family=family,
                    resource=self.resource,
                )
                db["tokens"][digest(access)] = dict(
                    **common, expires=time.time() + 3600
                )
                db["refresh"][digest(refresh)] = dict(
                    **common, expires=time.time() + 60 * 86400
                )
            return JSONResponse(
                dict(
                    access_token=access,
                    token_type="Bearer",
                    expires_in=3600,
                    refresh_token=refresh,
                    scope=" ".join(grant["scopes"]),
                )
            )
        except Exception:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)

    def verify(self, token):
        db = self.vault.read("oauth", dict(tokens={}))
        grant = db["tokens"].get(digest(token))
        if (
            grant
            and grant["expires"] > time.time()
            and grant["resource"] == self.resource
        ):
            return grant
        return None

    async def revoke(self, request):
        form = await request.form()
        with self.vault.transaction(
            "oauth", dict(clients={}, codes={}, tokens={}, refresh={})
        ) as db:
            key = digest(str(form.get("token", "")))
            grant = db["tokens"].get(key) or db["refresh"].get(key)
            if grant:
                for kind in ("tokens", "refresh"):
                    db[kind] = {
                        k: v
                        for k, v in db[kind].items()
                        if v["family"] != grant["family"]
                    }
        return JSONResponse({})
