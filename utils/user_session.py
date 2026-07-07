"""
Per-user session isolation for Streamlit state.

All proprietary audit artefacts (intake payloads, uploaded text, PDF bytes,
report markdown) are stored under a namespace keyed by the authenticated
username so concurrent B2B tenants never share transient data.
"""

from __future__ import annotations

import streamlit as st

from utils.auth_session import (
    AUTH_DISPLAY_NAME_KEY,
    AUTH_STATUS_KEY,
    AUTH_USERNAME_KEY,
)

_SESSION_ROOT = "_traceact_user_sessions"
_TRACEACT_USERNAME_KEY = "auth_username"
_AUTH_NAME_KEY = "auth_name"
_AUTH_SESSION_ID_KEY = "auth_session_id"


def is_authenticated_session() -> bool:
    """True when streamlit-authenticator has an active login session."""
    return st.session_state.get(AUTH_STATUS_KEY) is True


def sync_auth_session() -> str:
    """
    Mirror streamlit-authenticator session keys into TraceAct's user scope.

    Returns the active username, or an empty string when unauthenticated.
    """
    if not is_authenticated_session():
        return ""
    username = (st.session_state.get(AUTH_USERNAME_KEY) or "").strip()
    if not username:
        return st.session_state.get(_TRACEACT_USERNAME_KEY, "") or ""
    display_name = st.session_state.get(AUTH_DISPLAY_NAME_KEY) or username
    set_authenticated_user(username, display_name)
    return username


def set_authenticated_user(username: str, display_name: str) -> None:
    st.session_state[_TRACEACT_USERNAME_KEY] = username
    st.session_state[_AUTH_NAME_KEY] = display_name
    # Stable per-browser session pin for metadata isolation audits.
    st.session_state.setdefault(
        _AUTH_SESSION_ID_KEY,
        f"{username}:{id(st.session_state)}",
    )


def current_user_id() -> str:
    if is_authenticated_session():
        synced = sync_auth_session()
        if synced:
            return synced
    return st.session_state.get(_TRACEACT_USERNAME_KEY, "") or ""


def current_session_id() -> str:
    return st.session_state.get(_AUTH_SESSION_ID_KEY, "") or current_user_id()


def is_authenticated() -> bool:
    return is_authenticated_session() and bool(current_user_id())


def _bucket() -> dict:
    uid = current_user_id()
    if not uid:
        return {}
    root = st.session_state.setdefault(_SESSION_ROOT, {})
    return root.setdefault(uid, {})


def us_get(key: str, default=None):
    return _bucket().get(key, default)


def us_set(key: str, value) -> None:
    _bucket()[key] = value


def us_pop(key: str, default=None):
    return _bucket().pop(key, default)


def us_contains(key: str) -> bool:
    return key in _bucket()
