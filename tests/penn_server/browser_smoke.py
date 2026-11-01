"""Feed to `docker run --network none ... python -`; never contacts Penn."""

import asyncio
from pathlib import Path
from cryptography.fernet import Fernet
from src.penn_server.config import Settings
from src.penn_server.vault import Vault
from src.penn_server.browser import Browser


async def main():
    key = Path("/tmp/smoke-key")
    key.write_bytes(Fernet.generate_key())
    key.chmod(0o600)
    owner = Path("/tmp/smoke-owner")
    owner.write_text("simulated-owner-password-not-a-real-secret")
    settings = Settings(
        "https://penn.example.test",
        "/abcdefghijklmnopqrstuvwxyz",
        Path("/data"),
        Path("/run/penn-browser"),
        key,
        owner,
        (),
    )
    vault = Vault(settings.state_dir, key)
    browser = Browser(settings, vault)
    await browser.start()
    await browser.page.set_content("<h1>Offline browser smoke test</h1>")
    await browser.context.add_cookies(
        [
            dict(
                name="offline_test",
                value="simulated-cookie",
                domain="penn.instructure.com",
                path="/",
                secure=True,
                httpOnly=True,
            )
        ]
    )
    await browser.checkpoint()
    assert any(c["name"] == "offline_test" for c in await browser.context.cookies())
    assert b"simulated-cookie" not in (vault.root / "browser.enc").read_bytes()
    await browser.close()
    restored = Browser(settings, vault)
    await restored.start()
    assert any(c["name"] == "offline_test" for c in await restored.context.cookies())
    await restored.close()
    print("PASS: encrypted profile and session-cookie restore with network disabled")


if __name__ == "__main__":
    asyncio.run(main())
