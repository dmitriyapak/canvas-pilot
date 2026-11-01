"""Remove only this server's retired alert records; preserve all auth state."""


def remove_retired_alert_state(vault):
    for name in ("gmail", "outbox"):
        vault.delete(name)
