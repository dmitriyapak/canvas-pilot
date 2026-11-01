"""Fail-closed deployment configuration. Secrets are file paths, never env values."""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    public_url: str
    prefix: str
    state_dir: Path
    runtime_dir: Path
    key_file: Path
    owner_file: Path
    redirects: tuple[str, ...]
    canvas_origin: str = "https://penn.instructure.com"
    email: str = "owner@example.invalid"
    heartbeat_seconds: int = 720
    testing_read_only: bool = True
    expected_user_id: str = ""
    login_hosts: tuple[str, ...] = ()

    def __post_init__(self):
        u = urlsplit(self.public_url)
        if (
            u.scheme != "https"
            or not u.hostname
            or u.path
            or u.query
            or u.fragment
            or u.username
            or u.password
        ):
            raise ValueError(
                "PENN_PUBLIC_URL must be an HTTPS origin without a trailing slash"
            )
        if not re.fullmatch(r"/[A-Za-z0-9_-]{24,128}", self.prefix):
            raise ValueError(
                "PENN_PREFIX must be a random path of at least 24 characters"
            )
        if self.canvas_origin != "https://penn.instructure.com":
            raise ValueError("This deployment is restricted to Penn Canvas")
        if not 600 <= self.heartbeat_seconds <= 900:
            raise ValueError("Heartbeat must be between 600 and 900 seconds")
        if self.state_dir.resolve() == self.runtime_dir.resolve():
            raise ValueError(
                "Browser runtime must be separate from persistent encrypted state"
            )
        for r in self.redirects:
            p = urlsplit(r)
            if (
                p.scheme != "https"
                or not p.hostname
                or p.fragment
                or p.username
                or p.password
            ):
                raise ValueError("OAuth redirects must be exact HTTPS URLs")

    @classmethod
    def from_env(cls):
        return cls(
            public_url=os.environ["PENN_PUBLIC_URL"],
            prefix=os.environ["PENN_PREFIX"],
            state_dir=Path(os.getenv("PENN_STATE_DIR", "/data")),
            runtime_dir=Path(os.getenv("PENN_RUNTIME_DIR", "/run/penn-browser")),
            key_file=Path(os.getenv("PENN_KEY_FILE", "/run/secrets/master_key")),
            owner_file=Path(
                os.getenv("PENN_OWNER_FILE", "/run/secrets/owner_password")
            ),
            redirects=tuple(
                filter(None, os.getenv("PENN_OAUTH_REDIRECTS", "").split(","))
            ),
            email=os.environ["PENN_GMAIL_ADDRESS"],
            heartbeat_seconds=int(os.getenv("PENN_HEARTBEAT_SECONDS", "720")),
            testing_read_only=os.getenv("PENN_TESTING_READ_ONLY", "true").lower()
            != "false",
            expected_user_id=os.getenv("PENN_EXPECTED_USER_ID", ""),
            login_hosts=tuple(
                filter(None, os.getenv("PENN_LOGIN_HOSTS", "").split(","))
            ),
        )
