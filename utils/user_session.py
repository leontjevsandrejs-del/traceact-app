"""
Per-user session isolation for Streamlit state.

Audit artefacts are namespaced under a stable guest session identifier so
the wizard, vault, and billing helpers share one safe default footprint.
"""

from __future__ import annotations

import streamlit as st

GUEST_USER_ID = "guest_auditor"
GUEST_USER_EMAIL = "guest_auditor@traceact.eu"

_SESSION_ROOT = "_traceact_user_sessions"
_TRACEACT_USERNAME_KEY = "auth_username"
_SESSION_ID_KEY = "traceact_session_id"


def ensure_guest_session() -> str:
    """Pin the active workspace to the shared guest auditor identity."""
    st.session_state[_TRACEACT_USERNAME_KEY] = GUEST_USER_ID
    st.session_state.setdefault(_SESSION_ID_KEY, GUEST_USER_ID)
    return GUEST_USER_ID


def current_user_id() -> str:
    return st.session_state.get(_TRACEACT_USERNAME_KEY) or ensure_guest_session()


def guest_user_email() -> str:
    return GUEST_USER_EMAIL


def current_session_id() -> str:
    ensure_guest_session()
    return st.session_state.get(_SESSION_ID_KEY, GUEST_USER_ID)


def _bucket() -> dict:
    uid = current_user_id()
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
