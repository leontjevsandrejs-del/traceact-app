"""
Paywall UI helpers — Stripe checkout gate for the Conformity Assessment tab.
"""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from utils.draft_store import create_draft, draft_snapshot_for_session
from utils.stripe_checkout import create_checkout_session
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


def render_certified_assessment_paywall() -> None:
    """Block agent loops until Stripe payment completes."""
    st.markdown(
        """
        <div class="certified-report-lock">
          🔒 <strong>Certified Assessment Locked.</strong>
          Complete your intake above, then unlock the multi-agent conformity
          pipeline with a one-time certified assessment payment.
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button(
        "💳 Run Certified Assessment — 0.01 €",
        type="primary",
        use_container_width=True,
        key="run_certified_assessment_checkout",
    ):
        intake = us_get("intake", {})
        sync_description_to_intake(intake)
        us_set("intake", intake)

        draft_id = create_draft(draft_snapshot_for_session())
        checkout_url = create_checkout_session(draft_id)
        if not checkout_url:
            st.error(
                "Stripe checkout could not be started. "
                "Verify STRIPE_SECRET_KEY in the root .env file."
            )
            return

        components.html(
            f'<script>window.top.location.href = "{checkout_url}";</script>',
            height=0,
        )


# Back-compat alias used by older imports
def render_certified_report_paywall() -> None:
    render_certified_assessment_paywall()


def sync_credit_count() -> int:
    """Legacy hook — assessment unlock is now driven by Stripe payment state."""
    paid = 1 if is_assessment_paid() else 0
    st.session_state["credit_count"] = paid
    return paid


def has_audit_credits() -> bool:
    return is_assessment_paid()
