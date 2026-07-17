"""
HMAC-signed workspace session tokens (browser cookie + Streamlit state).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

_SESSION_STATE_KEY = "traceact_secure_session"
_COOKIE_NAME = "traceact_workspace"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SESSIONS_PATH = _PROJECT_ROOT / "data" / "active_sessions.json"
_SESSION_TTL_SECONDS = 60 * 60 * 24 * 30


def _session_secret() -> bytes:
    return os.getenv(
        "TRACEACT_SESSION_SECRET",
        os.getenv("AUTH_COOKIE_KEY", "traceact_dev_session_signing_key_change_me"),
    ).encode("utf-8")


def _load_sessions() -> dict[str, dict]:
    if not _SESSIONS_PATH.is_file():
        return {}
    try:
        with open(_SESSIONS_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_sessions(sessions: dict[str, dict]) -> None:
    _SESSIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_SESSIONS_PATH, "w", encoding="utf-8") as fh:
        json.dump(sessions, fh, indent=2)


def _sign_payload(payload: str) -> str:
    return hmac.new(_session_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def issue_session_token(user_id: str, email: str) -> str:
    token = secrets.token_urlsafe(32)
    sessions = _load_sessions()
    sessions[token] = {
        "user_id": user_id,
        "email": email,
        "issued_at": int(time.time()),
    }
    _save_sessions(sessions)
    st.session_state[_SESSION_STATE_KEY] = token
    return token


def validate_session_token(token: str | None) -> dict | None:
    if not token:
        return None
    row = _load_sessions().get(token)
    if not row:
        return None
    issued = int(row.get("issued_at", 0))
    if time.time() - issued > _SESSION_TTL_SECONDS:
        return None
    return row


def current_secure_session() -> dict | None:
    token = st.session_state.get(_SESSION_STATE_KEY)
    return validate_session_token(token)


def restore_session_from_cookie() -> dict | None:
    """Read signed browser cookie set after account activation."""
    return current_secure_session()


def establish_secure_cookie_session(user_id: str, email: str) -> None:
    token = issue_session_token(user_id, email)
    max_age = _SESSION_TTL_SECONDS
    components.html(
        f"""
        <script>
        document.cookie = "{_COOKIE_NAME}={token}; path=/; max-age={max_age}; SameSite=Lax; Secure";
        </script>
        """,
        height=0,
    )


def restore_workspace_identity() -> bool:
    """Apply a validated secure session token to the Streamlit workspace identity."""
    # Supabase Auth member sessions take precedence over Stripe cookie identity.
    try:
        from utils.auth_session import is_logged_in, get_auth_user_id, get_auth_email

        if is_logged_in() and get_auth_user_id():
            from utils.user_session import activate_workspace_user

            activate_workspace_user(
                get_auth_user_id(),
                get_auth_email() or "",
            )
            return True
    except Exception:
        pass

    session = current_secure_session()
    if not session:
        return False
    user_id = session["user_id"]
    email = session["email"]
    st.session_state["auth_username"] = user_id
    st.session_state["traceact_user_email"] = email
    st.session_state["traceact_session_id"] = user_id
    return True


def clear_secure_session() -> None:
    st.session_state.pop(_SESSION_STATE_KEY, None)
    components.html(
        f"""
        <script>
        document.cookie = "{_COOKIE_NAME}=; path=/; max-age=0; SameSite=Lax; Secure";
        </script>
        """,
        height=0,
    )
