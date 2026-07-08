"""
Paywall UI helpers — static Stripe Payment Link gate for Conformity Assessment.
"""

from __future__ import annotations

import streamlit as st

from utils.draft_store import ensure_session_draft_id, persist_session_draft
from utils.stripe_config import get_stripe_payment_link
from utils.user_session import us_get, us_set

DESCRIPTION_WIDGET_KEY = "system_description_input"
_PAID_FLAG = "assessment_paid"
_AUTO_RUN_FLAG = "auto_run_assessment"


def is_assessment_paid() -> bool:
    return bool(
        st.session_state.get(_PAID_FLAG)
        or us_get(_PAID_FLAG, False)
    )


def mark_assessment_paid(*, auto_run: bool = True) -> None:
    st.session_state[_PAID_FLAG] = True
    us_set(_PAID_FLAG, True)
    if auto_run:
        st.session_state[_AUTO_RUN_FLAG] = True
        us_set(_AUTO_RUN_FLAG, True)


def consume_auto_run_assessment() -> bool:
    if st.session_state.get(_AUTO_RUN_FLAG) or us_get(_AUTO_RUN_FLAG, False):
        st.session_state[_AUTO_RUN_FLAG] = False
        us_set(_AUTO_RUN_FLAG, False)
        return True
    return False


def ensure_description_widget_state(fallback: str = "") -> None:
    """Initialise the Step 4 description widget once (prevents focus-loss on typing)."""
    if DESCRIPTION_WIDGET_KEY not in st.session_state:
        legacy = st.session_state.get("wizard_description_area")
        st.session_state[DESCRIPTION_WIDGET_KEY] = (
            legacy if legacy is not None else fallback
        )


def sync_description_to_intake(intake: dict) -> None:
    intake["description"] = st.session_state.get(DESCRIPTION_WIDGET_KEY, "")
    us_set("intake", intake)
    persist_session_draft()


def render_certified_assessment_paywall() -> None:
    """Block agent loops until Stripe payment completes."""
    st.markdown(
        """
        <div class="certified-report-lock">
          🔒 <strong>Certified Assessment Locked.</strong>
          Complete your intake above, then unlock the multi-agent conformity
          pipeline with a one-time certified assessment payment (0.50 €).
        </div>
        """,
        unsafe_allow_html=True,
    )

    draft_id = ensure_session_draft_id()
    persist_session_draft()

    base_link = get_stripe_payment_link()
    if not base_link:
        checkout_url = "#"
        st.error(
            "Payment link is not configured. Set **STRIPE_PAYMENT_LINK** in "
            "`.env` (local) or Streamlit Cloud secrets."
        )
    elif not base_link.startswith("https://buy.stripe.com/"):
        checkout_url = "#"
        st.error(
            "STRIPE_PAYMENT_LINK must be a full Stripe Payment Link URL "
            "(https://buy.stripe.com/...). Copy it from the Stripe Dashboard."
        )
    else:
        checkout_url = (
            f"{base_link}?client_reference_id={st.session_state.get('draft_id', '')}"
        )
        slug = base_link.rsplit("/", 1)[-1][:12]
        st.caption(f"Checkout destination: …/{slug}…")

    with st.container(border=True):
        st.link_button(
            "💳 Run Certified Assessment — 0.50 €",
            checkout_url,
            use_container_width=True,
        )


def render_certified_report_paywall() -> None:
    render_certified_assessment_paywall()


def sync_credit_count() -> int:
    """Legacy hook — assessment unlock is now driven by Stripe payment state."""
    paid = 1 if is_assessment_paid() else 0
    st.session_state["credit_count"] = paid
    return paid


def has_audit_credits() -> bool:
    return is_assessment_paid()
