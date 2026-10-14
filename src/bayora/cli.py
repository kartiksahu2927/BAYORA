"""Command line entry point."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

from .auth import hash_password
from .config import Settings
from .db import Database
from .server import serve
from .service import BayoraService


SEEDED_USERNAMES = ("red-analyst", "blue-engineer", "security-admin", "audit-reviewer")


def _prompt_for_password(username: str) -> str | None:
    while True:
        try:
            password = getpass.getpass(f"Password for {username} (minimum 12 characters): ")
            if len(password) < 12:
                print("Password must be at least 12 characters.", file=sys.stderr)
                continue
            confirmation = getpass.getpass("Confirm password: ")
        except (EOFError, KeyboardInterrupt):
            print("\nPassword initialization cancelled.", file=sys.stderr)
            return None
        if password == confirmation:
            return password
        print("Passwords do not match; try again.", file=sys.stderr)


def _init_users(data_dir: str | None, username: str | None) -> int:
    # Only the data-directory setting is needed here. Avoid loading bootstrap
    # credentials or constructing the service/provider stack for this command.
    settings = Settings(data_dir=Path(data_dir or os.environ.get("BAYORA_DATA_DIR", ".bayora")))
    settings.prepare()
    database = Database(settings.database_path)
    usernames = (username,) if username else SEEDED_USERNAMES

    missing: list[str] = []
    for account in usernames:
        credentials = database.user_credentials(account)
        if credentials is None:
            print(f"{account}: unavailable")
        elif credentials.get("password_hash"):
            print(f"{account}: skipped (password already configured)")
        else:
            missing.append(account)

    if not missing:
        print("No missing passwords. Changes are immediate; a running Bayora server does not need a restart.")
        return 0

    if not sys.stdin.isatty():
        print(
            "Cannot initialize missing passwords without an interactive terminal; "
            "password input is refused.",
            file=sys.stderr,
        )
        return 1

    for account in missing:
        password = _prompt_for_password(account)
        if password is None:
            return 1
        password_hash = hash_password(password)
        del password
        if database.set_password_hash_if_missing(account, password_hash):
            print(f"{account}: initialized")
        else:
            print(f"{account}: skipped (password was configured concurrently)")
    print("Password changes are immediate; a running Bayora server does not need a restart.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="bayora",
        description="Bayora security evaluation platform",
        epilog=(
            "init-users initializes missing passwords in the configured database using local hidden prompts. "
            "Existing passwords are skipped, passwords are never accepted as arguments, and a running server "
            "uses successful changes without a restart."
        ),
    )
    parser.add_argument("command", choices=("serve", "validate", "init-users"))
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument(
        "--username",
        choices=SEEDED_USERNAMES,
        default=None,
        help="init-users only: initialize this seeded username instead of all missing-password accounts",
    )
    args = parser.parse_args()
    if args.command != "init-users" and args.username is not None:
        parser.error("--username is only valid with init-users")
    if args.command == "init-users":
        return _init_users(args.data_dir, args.username)

    try:
        settings = Settings.from_env(args.data_dir)
        if args.host:
            settings = replace(settings, host=args.host)
        if args.port is not None:
            settings = replace(settings, port=args.port)
        service = BayoraService(settings)
    except ValueError as exc:
        parser.error(str(exc))
    if args.command == "validate":
        actor = service.actor_for_user("security-admin")
        result = service.run_security_validation(actor)
        print(json.dumps(result, indent=2))
        return 0 if result.get("passed") else 1
    serve(service, settings.host, settings.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
