"""
Paywall UI helpers — credit sync and the single Conformity Assessment gate.
"""

from __future__ import annotations

import os

import streamlit as st
import streamlit.components.v1 as components

from utils.draft_store import create_draft, draft_snapshot_for_session
from utils.tenant_db import get_audit_credits
from utils.user_session import current_user_id

DESCRIPTION_WIDGET_KEY = "system_description_input"


def stripe_checkout_url(draft_id: str | None = None) -> str:
    base = os.getenv(
        "STRIPE_CHECKOUT_URL",
        "https://buy.stripe.com/test_traceact_audit_credits",
    )
    if not draft_id:
        return base
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}client_reference_id={draft_id}"


def stripe_success_url_template() -> str:
    """
    Configure this URL in the Stripe Checkout success redirect:

    ``?payment=success&draft_id={CLIENT_REFERENCE_ID}&email={CUSTOMER_EMAIL}``
    """
    return os.getenv(
        "STRIPE_SUCCESS_URL",
        "?payment=success&draft_id={CLIENT_REFERENCE_ID}&email={CUSTOMER_EMAIL}",
    )


def sync_credit_count() -> int:
    """Mirror tenant credits on ``st.session_state.credit_count`` (no sidebar UI)."""
    uid = current_user_id()
    credits = get_audit_credits(uid) if uid else 0
    st.session_state["credit_count"] = credits
    return credits


def has_audit_credits() -> bool:
    return sync_credit_count() > 0


def ensure_description_widget_state(fallback: str = "") -> None:
    """Initialise the Step 4 description widget once (prevents focus-loss on typing)."""
    if DESCRIPTION_WIDGET_KEY not in st.session_state:
        legacy = st.session_state.get("wizard_description_area")
        st.session_state[DESCRIPTION_WIDGET_KEY] = (
            legacy if legacy is not None else fallback
        )


def sync_description_to_intake(intake: dict) -> None:
    intake["description"] = st.session_state.get(DESCRIPTION_WIDGET_KEY, "")


def render_certified_report_paywall() -> None:
    """Single purchase gate for the Conformity Assessment tab (zero credits)."""
    st.markdown(
        """
        <div class="certified-report-lock">
          🔒 <strong>Certified Compliance Report Locked.</strong>
          Your account has no remaining audit credits.
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button(
        "💳 Buy Certified Audit Report — €79",
        type="primary",
        use_container_width=True,
        key="buy_certified_audit_report",
    ):
        draft_id = create_draft(draft_snapshot_for_session())
        checkout = stripe_checkout_url(draft_id)
        components.html(
            f'<script>window.top.location.href = "{checkout}";</script>',
            height=0,
        )
