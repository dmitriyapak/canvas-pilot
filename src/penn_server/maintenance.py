"""In-process supervision; Docker restart=always recovers persistent failures."""

import logging
import os
import signal
import time

log = logging.getLogger("penn.maintenance")


def restart_process():
    # SIGTERM lets the ASGI lifespan checkpoint state before Docker restarts it.
    os.kill(os.getpid(), signal.SIGTERM)


class Maintenance:
    def __init__(
        self,
        tools,
        session,
        schedule,
        interval,
        *,
        restart=restart_process,
        clock=time.monotonic,
    ):
        self.tools, self.session, self.schedule = tools, session, schedule
        self.interval, self.restart, self.clock = interval, restart, clock
        self.next_at = 0.0
        self.failures = 0

    async def tick(self):
        if self.clock() < self.next_at:
            return
        try:
            async with self.tools.lock:
                healthy = await self.session.heartbeat()
            if healthy and self.session.status().get("phase") == "healthy":
                await self.schedule.tick()
        except Exception as error:
            self.failures += 1
            # Only the exception type is safe to persist: messages may contain secrets.
            log.error(
                "maintenance_failed error_type=%s failures=%d",
                type(error).__name__,
                self.failures,
            )
            self.next_at = self.clock() + min(60, 5 * 2**self.failures)
            if self.failures >= 3:
                log.error("maintenance_restart_requested")
                self.restart()
            return
        self.failures = 0
        self.next_at = self.clock() + self.interval
