"""
Supabase Auth session helpers for TraceAct.

Tracks login state in ``st.session_state`` and syncs the workspace identity
used by ``utils.user_session``. Auth API calls use ephemeral Supabase clients
so a shared ``@st.cache_resource`` client is never polluted by user sessions.
"""

from __future__ import annotations

import logging
from typing import Any

import streamlit as st

from utils.user_session import activate_workspace_user, ensure_guest_session

logger = logging.getLogger(__name__)

LOGGED_IN_KEY = "logged_in"
AUTH_USER_ID_KEY = "user_id"
AUTH_EMAIL_KEY = "auth_email"
AUTH_COMPANY_KEY = "company_name"


def init_auth_state() -> None:
    """Ensure default guest auth keys exist (call once on app boot)."""
    st.session_state.setdefault(LOGGED_IN_KEY, False)
    st.session_state.setdefault(AUTH_USER_ID_KEY, None)
    st.session_state.setdefault(AUTH_EMAIL_KEY, None)
    st.session_state.setdefault(AUTH_COMPANY_KEY, None)


def is_logged_in() -> bool:
    init_auth_state()
    return bool(st.session_state.get(LOGGED_IN_KEY))


def get_auth_user_id() -> str | None:
    if not is_logged_in():
        return None
    uid = st.session_state.get(AUTH_USER_ID_KEY)
    return str(uid) if uid else None


def get_auth_email() -> str | None:
    if not is_logged_in():
        return None
    email = st.session_state.get(AUTH_EMAIL_KEY)
    return str(email) if email else None


def get_company_name() -> str | None:
    if not is_logged_in():
        return None
    name = st.session_state.get(AUTH_COMPANY_KEY)
    return str(name) if name else None


def _apply_logged_in_user(
    user_id: str,
    email: str,
    company_name: str | None = None,
) -> None:
    st.session_state[LOGGED_IN_KEY] = True
    st.session_state[AUTH_USER_ID_KEY] = user_id
    st.session_state[AUTH_EMAIL_KEY] = email
    if company_name:
        st.session_state[AUTH_COMPANY_KEY] = company_name
    activate_workspace_user(user_id, email)


def clear_auth_session() -> None:
    """Return to anonymous guest mode."""
    st.session_state[LOGGED_IN_KEY] = False
    st.session_state[AUTH_USER_ID_KEY] = None
    st.session_state[AUTH_EMAIL_KEY] = None
    st.session_state[AUTH_COMPANY_KEY] = None
    ensure_guest_session()


def _ephemeral_client():
    """Fresh client for auth only — never reuse the cached DB client session."""
    from utils.supabase_db import create_supabase_client

    return create_supabase_client()


def _user_meta(user: Any) -> dict:
    try:
        meta = getattr(user, "user_metadata", None)
        if meta is None and isinstance(user, dict):
            meta = user.get("user_metadata") or user.get("userMetadata")
        return dict(meta or {})
    except Exception:
        return {}


def register_user(
    email: str,
    password: str,
    company_name: str,
) -> tuple[bool, str]:
    """
    Register via Supabase Auth ``sign_up``.
    Returns ``(ok, message)``.
    """
    email = (email or "").strip().lower()
    password = password or ""
    company_name = (company_name or "").strip()

    if not email or not password:
        return False, "Email and password are required."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    if not company_name:
        return False, "Company name is required."

    client = _ephemeral_client()
    if client is None:
        return False, "Database auth is unavailable. Check SUPABASE_URL / SUPABASE_KEY."

    try:
        response = client.auth.sign_up(
            {
                "email": email,
                "password": password,
                "options": {
                    "data": {
                        "company_name": company_name,
                    },
                },
            }
        )
        user = getattr(response, "user", None)
        if user is None:
            return False, "Registration failed — no user returned. Check Supabase Auth settings."

        user_id = str(getattr(user, "id", "") or "")
        if not user_id:
            return False, "Registration failed — missing user id."

        # Email confirmation may leave session empty; still mark workspace identity.
        _apply_logged_in_user(user_id, email, company_name)

        session = getattr(response, "session", None)
        if session is None:
            return (
                True,
                "Account created. If email confirmation is enabled in Supabase, "
                "confirm your inbox before the next login — you are signed in "
                "for this session.",
            )
        return True, "Account created. Welcome to TraceAct."
    except Exception as exc:
        logger.exception("register_user failed: %s", exc)
        msg = str(exc)
        if "already" in msg.lower() or "registered" in msg.lower():
            return False, "An account with this email already exists. Please log in."
        return False, f"Registration failed: {msg}"


def login_user(email: str, password: str) -> tuple[bool, str]:
    """Authenticate via Supabase Auth ``sign_in_with_password``."""
    email = (email or "").strip().lower()
    password = password or ""

    if not email or not password:
        return False, "Email and password are required."

    client = _ephemeral_client()
    if client is None:
        return False, "Database auth is unavailable. Check SUPABASE_URL / SUPABASE_KEY."

    try:
        response = client.auth.sign_in_with_password(
            {
                "email": email,
                "password": password,
            }
        )
        user = getattr(response, "user", None)
        if user is None:
            return False, "Login failed — invalid credentials."

        user_id = str(getattr(user, "id", "") or "")
        if not user_id:
            return False, "Login failed — missing user id."

        meta = _user_meta(user)
        company = str(meta.get("company_name") or "").strip() or None
        _apply_logged_in_user(user_id, email, company)
        return True, "Signed in successfully."
    except Exception as exc:
        logger.exception("login_user failed: %s", exc)
        msg = str(exc)
        if "invalid" in msg.lower() or "credentials" in msg.lower():
            return False, "Invalid email or password."
        return False, f"Login failed: {msg}"


def logout_user() -> None:
    clear_auth_session()
