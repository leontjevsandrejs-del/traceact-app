"""
Stripe success-return handler — restores paid drafts into the workspace.
"""

from __future__ import annotations

import streamlit as st

from utils.billing_ui import mark_assessment_paid
from utils.draft_store import get_draft, mark_draft_paid
from utils.stripe_config import configure_stripe_api_key

PAYMENT_PARAM = "payment"
DRAFT_ID_PARAM = "draft_id"


def _user_session():
    from utils import user_session
    return user_session


def _verify_checkout_paid(draft_id: str) -> bool:
    """Optional Stripe session verification when ``session_id`` is in the URL."""
    session_id = (st.query_params.get("session_id") or "").strip()
    secret = configure_stripe_api_key()
    if not session_id or not secret:
        return True
    try:
        import stripe  # type: ignore[import-untyped]

        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status != "paid":
            return False
        meta_draft = (session.metadata or {}).get("draft_id") or session.client_reference_id
        return (meta_draft or "").strip() == draft_id
    except Exception:
        return False


def restore_paid_draft(draft_id: str) -> bool:
    """Load a paid draft snapshot into the active workspace."""
    draft = get_draft(draft_id)
    if not draft:
        return False
    snapshot = draft.get("snapshot") or {}
    _user_session().hydrate_workspace_from_snapshot(snapshot)
    mark_draft_paid(draft_id)
    mark_assessment_paid(auto_run=True)
    return True


def process_stripe_return() -> None:
    """
    Inbound Stripe recovery — call at the top of ``app.py``.

    When ``payment=success`` and ``draft_id`` are present, hydrates the saved
    guest intake, unlocks the assessment pipeline, clears URL params, and reruns.
    """
    if st.query_params.get(PAYMENT_PARAM) != "success":
        return

    draft_id = (st.query_params.get(DRAFT_ID_PARAM) or "").strip()
    if not draft_id:
        st.error("Payment succeeded but no draft_id was supplied in the return URL.")
        return

    if not _verify_checkout_paid(draft_id):
        st.error("Stripe payment could not be verified for this session.")
        return

    if not restore_paid_draft(draft_id):
        st.error(
            "Your payment succeeded but the saved assessment draft was not found. "
            "Please contact support with your receipt."
        )
        return

    st.query_params.clear()
    st.rerun()


def handle_stripe_return_or_continue() -> bool:
    """Back-compat wrapper — always allows the workspace to continue loading."""
    process_stripe_return()
    return True
