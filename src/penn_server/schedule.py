"""In-process read-only scan/reminder schedule; no agent process or submissions."""

from datetime import datetime
from zoneinfo import ZoneInfo


class ReadOnlySchedule:
    def __init__(self, tools, notifier, vault):
        self.tools, self.notifier, self.vault = tools, notifier, vault

    async def tick(self, now=None):
        now = now or datetime.now(ZoneInfo("America/New_York"))
        if now.hour < 9:
            return
        day = now.date().isoformat()
        previous = self.vault.read("schedule", {})
        if previous.get("last_scan_day") == day:
            return
        plan = await self.tools.scan()
        self.notifier.queue(
            "daily-scan-" + day,
            "Penn Canvas daily scan",
            "Your read-only Canvas scan is ready through the connector. "
            + str(len(plan["courses"]))
            + " courses inspected. No coursework was submitted or changed.",
        )

        self.vault.write("schedule", {"last_scan_day": day})
