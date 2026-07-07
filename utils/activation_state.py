"""
Post-payment activation state — no imports from other TraceAct utils.

Keeps the Stripe return handler decoupled so Cloud deploys cannot fail on
partial ``user_session`` rollouts.
"""

from __future__ import annotations

import streamlit as st

_PENDING_ACTIVATION_KEY = "_traceact_pending_activation"


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
