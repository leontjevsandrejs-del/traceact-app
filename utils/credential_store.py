"""
Supplementary credential store for streamlit-authenticator.

Merges users from auth_config.yaml, Streamlit secrets, and a local JSON
registry so self-service registrations survive process restarts where the
filesystem allows writes (and secrets cover Streamlit Cloud redeploys).
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import streamlit as st
import streamlit_authenticator as stauth
import yaml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_AUTH_CONFIG_PATH = _PROJECT_ROOT / "config" / "auth_config.yaml"
_RUNTIME_USERS_PATH = _PROJECT_ROOT / "data" / "auth_users.json"


def _load_yaml_credentials() -> dict:
    if not _AUTH_CONFIG_PATH.is_file():
        return {"usernames": {}}
    with open(_AUTH_CONFIG_PATH, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    creds = cfg.get("credentials", {})
    creds.setdefault("usernames", {})
    return creds


def _load_secrets_credentials() -> dict:
    try:
        auth = st.secrets.get("auth", {})
    except Exception:
        return {"usernames": {}}
    creds = auth.get("credentials", {})
    if isinstance(creds, dict):
        creds.setdefault("usernames", {})
        return creds
    return {"usernames": {}}


def _load_runtime_users() -> dict:
    if not _RUNTIME_USERS_PATH.is_file():
        return {}
    try:
        with open(_RUNTIME_USERS_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_runtime_users(users: dict) -> bool:
    try:
        _RUNTIME_USERS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_RUNTIME_USERS_PATH, "w", encoding="utf-8") as fh:
            json.dump(users, fh, indent=2)
        return True
    except OSError:
        return False


def load_merged_credentials() -> dict:
    """Combine yaml, secrets, and runtime JSON user registries."""
    merged = copy.deepcopy(_load_yaml_credentials())
    merged.setdefault("usernames", {})

    for extra in (_load_secrets_credentials(), {"usernames": _load_runtime_users()}):
        for username, row in extra.get("usernames", {}).items():
            merged["usernames"][username.lower()] = row

    return merged


def register_runtime_user(
    username: str,
    email: str,
    display_name: str,
    plain_password: str,
    password_hint: str = "",
) -> str:
    """
    Persist a newly registered user to the runtime JSON store.

    Returns the normalised (lowercase) username key.
    """
    key = username.lower().strip()
    users = _load_runtime_users()
    user_row = {
        "email": email,
        "failed_login_attempts": 0,
        "logged_in": False,
        "name": display_name,
        "password": stauth.Hasher.hash(plain_password),
    }
    if password_hint:
        user_row["password_hint"] = password_hint
    users[key] = user_row
    _save_runtime_users(users)
    return key


def sync_yaml_credentials_snapshot(credentials: dict) -> None:
    """Best-effort write-back to auth_config.yaml (local dev)."""
    if not _AUTH_CONFIG_PATH.is_file():
        return
    try:
        with open(_AUTH_CONFIG_PATH, encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}
        cfg["credentials"] = credentials
        with open(_AUTH_CONFIG_PATH, "w", encoding="utf-8") as fh:
            yaml.safe_dump(cfg, fh, default_flow_style=False, allow_unicode=True)
    except OSError:
        pass
