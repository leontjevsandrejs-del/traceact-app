"""
Per-user session isolation for Streamlit state.

Guest auditors share a default footprint until Stripe post-payment activation
binds a verified billing email and encrypted workspace identity.
"""

from __future__ import annotations

import streamlit as st

GUEST_USER_ID = "guest_auditor"
GUEST_USER_EMAIL = "guest_auditor@traceact.eu"

_SESSION_ROOT = "_traceact_user_sessions"
_TRACEACT_USERNAME_KEY = "auth_username"
_TRACEACT_EMAIL_KEY = "traceact_user_email"
_SESSION_ID_KEY = "traceact_session_id"
_PENDING_ACTIVATION_KEY = "_traceact_pending_activation"


def ensure_guest_session() -> str:
    """Pin the active workspace to the shared guest auditor identity."""
    st.session_state[_TRACEACT_USERNAME_KEY] = GUEST_USER_ID
    st.session_state[_TRACEACT_EMAIL_KEY] = GUEST_USER_EMAIL
    st.session_state.setdefault(_SESSION_ID_KEY, GUEST_USER_ID)
    return GUEST_USER_ID


def activate_workspace_user(user_id: str, email: str) -> None:
    st.session_state[_TRACEACT_USERNAME_KEY] = user_id
    st.session_state[_TRACEACT_EMAIL_KEY] = email
    st.session_state[_SESSION_ID_KEY] = user_id


def current_user_id() -> str:
    return st.session_state.get(_TRACEACT_USERNAME_KEY) or ensure_guest_session()


def current_user_email() -> str:
    return st.session_state.get(_TRACEACT_EMAIL_KEY) or GUEST_USER_EMAIL


def guest_user_email() -> str:
    return current_user_email()


def is_activated_user() -> bool:
    return current_user_id() != GUEST_USER_ID


def current_session_id() -> str:
    ensure_guest_session()
    return st.session_state.get(_SESSION_ID_KEY, GUEST_USER_ID)


def set_pending_activation(email: str, draft_id: str) -> None:
    st.session_state[_PENDING_ACTIVATION_KEY] = {
        "email": email,
        "draft_id": draft_id,
    }


def pending_activation() -> dict:
    return st.session_state.get(_PENDING_ACTIVATION_KEY) or {}


def clear_pending_activation() -> None:
    st.session_state.pop(_PENDING_ACTIVATION_KEY, None)


def is_pending_activation() -> bool:
    pending = pending_activation()
    return bool(pending.get("email") and pending.get("draft_id"))


def hydrate_workspace_from_snapshot(snapshot: dict) -> None:
    """Restore a paid draft into the active user bucket."""
    mapping = {
        "intake": snapshot.get("intake", {}),
        "step": snapshot.get("step", 4),
        "report_markdown": snapshot.get("report_markdown", ""),
        "pdf_data_bytes": snapshot.get("pdf_data_bytes"),
        "audit_complete": snapshot.get("audit_complete", False),
        "risk_tier": snapshot.get("risk_tier"),
        "risk_citation": snapshot.get("risk_citation"),
        "audit_date": snapshot.get("audit_date"),
    }
    for key, value in mapping.items():
        if value is not None:
            us_set(key, value)


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
