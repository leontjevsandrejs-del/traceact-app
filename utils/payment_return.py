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
SESSION_ID_PARAM = "session_id"
CHECKOUT_SESSION_PARAM = "checkout_session_id"


def _user_session():
    from utils import user_session
    return user_session


def _checkout_session_id_from_query() -> str:
    return (
        st.query_params.get(SESSION_ID_PARAM)
        or st.query_params.get(CHECKOUT_SESSION_PARAM)
        or ""
    ).strip()


def _recover_draft_id_from_stripe(checkout_session_id: str) -> str | None:
    """Fetch Checkout Session and read ``client_reference_id`` as draft id."""
    if not configure_stripe_api_key():
        st.error(
            "Stripe payment could not be verified. "
            "Add STRIPE_SECRET_KEY to Streamlit secrets or the root .env file."
        )
        return None

    try:
        import stripe  # type: ignore[import-untyped]
    except ImportError:
        st.error("Stripe Python package is not installed.")
        return None

    try:
        session = stripe.checkout.Session.retrieve(checkout_session_id)
    except stripe.error.StripeError as err:
        st.error(f"Stripe Error: {err.user_message or err}")
        return None

    if session.payment_status != "paid":
        st.error("Stripe reports that this checkout session is not paid yet.")
        return None

    recovered = (session.client_reference_id or "").strip()
    if not recovered:
        meta = session.metadata or {}
        recovered = (meta.get("draft_id") or "").strip()
    return recovered or None


def restore_paid_draft(draft_id: str) -> bool:
    """Load a paid draft snapshot into the active workspace and queue auto-run."""
    draft = get_draft(draft_id)
    if not draft:
        return False
    snapshot = draft.get("snapshot") or {}
    _user_session().hydrate_workspace_from_snapshot(snapshot)

    from utils.billing_ui import DESCRIPTION_WIDGET_KEY, ensure_description_widget_state

    intake = snapshot.get("intake") or {}
    ensure_description_widget_state(intake.get("description", ""))
    st.session_state[DESCRIPTION_WIDGET_KEY] = intake.get("description", "")

    st.session_state["draft_id"] = draft_id
    mark_draft_paid(draft_id)
    mark_assessment_paid(auto_run=True)
    return True


def process_stripe_return() -> None:
    """
    Inbound Stripe recovery — call at the top of ``app.py``.

    When ``payment=success`` is present, retrieves the Checkout Session via
    ``STRIPE_SECRET_KEY``, unpacks ``client_reference_id``, re-hydrates intake
    text from ``data/drafts.json``, unlocks Conformity Assessment, and queues
    the multi-agent ReportLab PDF pipeline.
    """
    if st.query_params.get(PAYMENT_PARAM) != "success":
        return

    checkout_session_id = _checkout_session_id_from_query()
    recovered_draft_id = None

    if checkout_session_id:
        recovered_draft_id = _recover_draft_id_from_stripe(checkout_session_id)
    else:
        recovered_draft_id = (st.query_params.get(DRAFT_ID_PARAM) or "").strip() or None

    if not recovered_draft_id:
        st.error(
            "Payment succeeded but no checkout session or draft id was found. "
            "Confirm your Payment Link success URL includes the session id."
        )
        return

    if not restore_paid_draft(recovered_draft_id):
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
