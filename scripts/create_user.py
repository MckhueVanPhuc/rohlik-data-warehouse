"""Manage the configured Rohlik Decision Hub admin without exposing passwords.

Examples:
    python -m scripts.create_user change-password
    python -m scripts.create_user disable
    python -m scripts.create_user enable
    python -m scripts.create_user status
"""

from __future__ import annotations

import argparse
import getpass
from pathlib import Path
import sys

import yaml

from app.services.identity import (
    AccountConflictError,
    CredentialStore,
    CredentialStoreError,
    PasswordPolicy,
    PasswordPolicyError,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUTH_CONFIG_PATH = PROJECT_ROOT / "config" / "auth.yaml"


def configure_console_encoding() -> None:
    """Use UTF-8 for Vietnamese CLI output on Windows terminals."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def load_cli_dependencies() -> tuple[CredentialStore, PasswordPolicy, str]:
    try:
        config = yaml.safe_load(AUTH_CONFIG_PATH.read_text(encoding="utf-8"))
        password_config = config["password_policy"]
        admin_username = config["admin_username"]
        store_path = (PROJECT_ROOT / config["credential_store"]).resolve()
    except (OSError, yaml.YAMLError, KeyError, TypeError) as exc:
        raise CredentialStoreError("Authentication configuration is invalid.") from exc
    auth_root = (PROJECT_ROOT / "data" / "auth").resolve()
    if not isinstance(admin_username, str) or not admin_username.strip():
        raise CredentialStoreError("Configured admin username is invalid.")
    if store_path != auth_root and auth_root not in store_path.parents:
        raise CredentialStoreError("Credential store must remain under data/auth.")
    password_policy = PasswordPolicy(
        min_length=int(password_config["min_length"]),
        max_length=int(password_config["max_length"]),
    )
    return (
        CredentialStore(store_path, harden_windows_acl=True),
        password_policy,
        admin_username,
    )


def prompt_new_password() -> str:
    password = getpass.getpass("Mật khẩu mới: ")
    confirmation = getpass.getpass("Nhập lại mật khẩu: ")
    if password != confirmation:
        raise PasswordPolicyError("Password confirmation does not match.")
    return password


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Quản lý một tài khoản admin cục bộ Rohlik Decision Hub."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("change-password", help="Đổi mật khẩu")
    commands.add_parser("disable", help="Vô hiệu hóa admin")
    commands.add_parser("enable", help="Khôi phục quyền truy cập admin")
    commands.add_parser("status", help="Xem username và trạng thái admin")
    return parser


def run_command(args: argparse.Namespace) -> int:
    store, password_policy, admin_username = load_cli_dependencies()
    current = store.find_by_username(admin_username)
    if current is None:
        raise AccountConflictError(
            "Configured admin does not exist. Refusing to create or reset an account automatically."
        )
    if args.command == "change-password":
        password = prompt_new_password()
        user = store.change_password(
            admin_username,
            password,
            password_policy=password_policy,
        )
        print(f"Đã đổi mật khẩu: {user.username}")
        return 0
    if args.command == "disable":
        user = store.disable_user(admin_username)
        print(f"Đã vô hiệu hóa: {user.username}")
        return 0
    if args.command == "enable":
        user = store.enable_user(admin_username)
        print(f"Đã khôi phục: {user.username}")
        return 0
    if args.command == "status":
        print("USERNAME\tENABLED")
        print(f"{current.username}\t{str(current.enabled).lower()}")
        return 0
    raise ValueError(f"Unsupported command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    configure_console_encoding()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run_command(args)
    except (CredentialStoreError, AccountConflictError, PasswordPolicyError, ValueError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
