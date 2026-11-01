"""In-process read-only daily scan; results persist locally, without alerts."""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

log = logging.getLogger("penn.schedule")


class ReadOnlySchedule:
    def __init__(self, tools, vault):
        self.tools, self.vault = tools, vault

    async def tick(self, now=None):
        now = now or datetime.now(ZoneInfo("America/New_York"))
        if now.hour < 9:
            return
        day = now.date().isoformat()
        if self.vault.read("schedule", {}).get("last_scan_day") == day:
            return
        plan = await self.tools.scan()
        self.vault.write("schedule", {"last_scan_day": day})
        log.info("daily_scan_completed courses=%d", len(plan["courses"]))
