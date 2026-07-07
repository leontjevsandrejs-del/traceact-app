"""
Activated corporate accounts — password hashes and draft bindings.

Replace the JSON file backend with Supabase / PostgreSQL in production.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ACCOUNTS_PATH = _PROJECT_ROOT / "data" / "accounts.json"

_PBKDF2_ITERATIONS = 260_000


def _load_accounts() -> dict[str, dict]:
    if not _ACCOUNTS_PATH.is_file():
        return {}
    try:
        with open(_ACCOUNTS_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_accounts(accounts: dict[str, dict]) -> None:
    _ACCOUNTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_ACCOUNTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(accounts, fh, indent=2)


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def email_to_user_id(email: str) -> str:
    local = normalize_email(email).split("@", 1)[0]
    slug = re.sub(r"[^a-z0-9]+", "_", local).strip("_") or "auditor"
    return f"corp_{slug}"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        _PBKDF2_ITERATIONS,
    ).hex()
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt, digest = stored.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        check = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        ).hex()
        return secrets.compare_digest(check, digest)
    except (ValueError, TypeError):
        return False


def get_account(email: str) -> dict | None:
    return _load_accounts().get(normalize_email(email))


def activate_account(email: str, password: str, draft_id: str) -> str:
    """Create or update the corporate account and return its user id."""
    email_key = normalize_email(email)
    if not email_key or not password.strip():
        raise ValueError("Email and password are required.")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")

    user_id = email_to_user_id(email_key)
    accounts = _load_accounts()
    accounts[email_key] = {
        "user_id": user_id,
        "email": email_key,
        "password_hash": hash_password(password),
        "draft_id": draft_id,
        "activated_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_accounts(accounts)
    return user_id


def account_exists(email: str) -> bool:
    return normalize_email(email) in _load_accounts()
