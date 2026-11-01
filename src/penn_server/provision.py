"""Run on the VPS console/SSH terminal; input is hidden and never echoed."""

import argparse
import getpass
from pathlib import Path

from cryptography.fernet import Fernet

from .vault import Vault


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["init", "pennkey"])
    p.add_argument("--key-file", type=Path, required=True)
    p.add_argument("--owner-file", type=Path)
    p.add_argument("--state-dir", type=Path, default=Path("/data"))
    args = p.parse_args()
    if args.action == "init":
        if not args.owner_file:
            p.error("--owner-file is required for init")
        for path in (args.key_file, args.owner_file):
            if path.exists():
                p.error("Refusing to overwrite an existing secret")
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        owner = getpass.getpass("New connector owner password (32+ characters): ")
        if len(owner) < 32 or owner != getpass.getpass("Confirm owner password: "):
            p.error("Owner password must match and contain at least 32 characters")
        for path, value in (
            (args.key_file, Fernet.generate_key()),
            (args.owner_file, owner.encode()),
        ):
            with path.open("xb") as f:
                path.chmod(0o600)
                f.write(value)
        return
    vault = Vault(args.state_dir, args.key_file)
    username = input("PennKey username: ").strip()
    password = getpass.getpass("PennKey password: ")
    if not username or not password:
        p.error("Empty credentials")
    vault.write("pennkey", {"username": username, "password": password})


if __name__ == "__main__":
    main()
