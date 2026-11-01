"""Bounded local logs. Never log credentials, cookies, URLs or exception text."""

import logging
from logging.handlers import RotatingFileHandler


def configure(root):
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    target = root / "server.log"
    handler = RotatingFileHandler(
        target, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    target.chmod(0o600)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    logger = logging.getLogger("penn")
    for old in logger.handlers[:]:
        old.close()
        logger.removeHandler(old)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
