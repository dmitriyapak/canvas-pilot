"""Durable, deduplicated Gmail SMTP outbox. No secrets in messages or logs."""

import asyncio
import smtplib
import ssl
import time
from email.message import EmailMessage


class Notifier:
    def __init__(self, vault, email):
        self.vault, self.email = vault, email

    def queue(self, key, subject, body):
        with self.vault.transaction("outbox", {}) as box:
            if key not in box:
                box[key] = dict(
                    subject=subject, body=body, sent=False, attempts=0, next_at=0
                )

    def _send(self, subject, body):
        credentials = self.vault.read("gmail")
        if not credentials or not credentials.get("app_password"):
            raise RuntimeError("Gmail is not provisioned")
        message = EmailMessage()
        message["From"] = message["To"] = self.email
        message["Subject"] = subject
        message.set_content(body)
        with smtplib.SMTP_SSL(
            "smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=20
        ) as smtp:
            smtp.login(self.email, credentials["app_password"])
            smtp.send_message(message)

    async def flush(self):
        # One server process and one delivery task; never overlap flushes.
        box = self.vault.read("outbox", {})
        for key, entry in box.items():
            if entry["sent"] or entry["next_at"] > time.time():
                continue
            try:
                await asyncio.to_thread(self._send, entry["subject"], entry["body"])
                entry["sent"] = True
            except Exception:
                entry["attempts"] += 1
                entry["next_at"] = time.time() + min(
                    3600, 30 * 2 ** min(entry["attempts"], 7)
                )
            with self.vault.transaction("outbox", {}) as current:
                current[key] = entry
