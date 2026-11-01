"""Authenticated encrypted records with atomic replacement and a separate key."""

import fcntl
import json
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path

from cryptography.fernet import Fernet


class Vault:
    def __init__(self, root: Path, key_file: Path):
        self.root = root
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(root, 0o700)
        if key_file.resolve().is_relative_to(root.resolve()):
            raise ValueError("Master key must be outside the encrypted state directory")
        if key_file.stat().st_mode & 0o077:
            raise ValueError("Master key must not be group/world accessible")
        self.cipher = Fernet(key_file.read_bytes().strip())

    def _path(self, name):
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", name):
            raise ValueError("Invalid vault record")
        return self.root / (name + ".enc")

    def read(self, name, default=None):
        p = self._path(name)
        if not p.exists():
            return default
        # Corruption/decryption failure is an error, never an empty vault.
        return json.loads(self.cipher.decrypt(p.read_bytes()))

    def write(self, name, value):
        payload = self.cipher.encrypt(json.dumps(value, separators=(",", ":")).encode())
        fd, tmp = tempfile.mkstemp(prefix=".checkpoint-", dir=self.root)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self._path(name))
            directory = os.open(self.root, os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            Path(tmp).unlink(missing_ok=True)

    def delete(self, name):
        path = self._path(name)
        path.unlink(missing_ok=True)
        descriptor = os.open(self.root, os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @contextmanager
    def transaction(self, name, default=None):
        with (self.root / (name + ".lock")).open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            value = self.read(name, default)
            yield value
            self.write(name, value)

    @contextmanager
    def exclusive_process(self):
        with (self.root / "server.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError(
                    "Only one Penn server may own this state directory"
                ) from None
            yield
