"""
Paywall UI helpers — Stripe checkout, credit gating, and Light Preview Mode.
"""

from __future__ import annotations

import os

import streamlit as st

from utils.tenant_db import get_audit_credits, get_company_profile
from utils.user_session import current_user_id

DESCRIPTION_WIDGET_KEY = "system_description_input"


def sync_credit_count() -> int:
    """Mirror tenant credits on ``st.session_state.credit_count`` for UI conditionals."""
    uid = current_user_id()
    credits = get_audit_credits(uid) if uid else 0
    st.session_state["credit_count"] = credits
    return credits


def has_audit_credits() -> bool:
    return sync_credit_count() > 0


def ensure_description_widget_state(fallback: str = "") -> None:
    """
    Initialise the Step 4 description widget once with a stable session key.

    Avoids passing ``value=`` on every rerun, which fights the widget ``key``
    and causes focus loss while typing.
    """
    if DESCRIPTION_WIDGET_KEY not in st.session_state:
        legacy = st.session_state.get("wizard_description_area")
        st.session_state[DESCRIPTION_WIDGET_KEY] = (
            legacy if legacy is not None else fallback
        )


def sync_description_to_intake(intake: dict) -> None:
    intake["description"] = st.session_state.get(DESCRIPTION_WIDGET_KEY, "")


def render_credit_banner() -> int:
    """Sidebar/header credit meter. Returns remaining credits."""
    credits = sync_credit_count()
    uid = current_user_id()
    if not uid:
        return credits
    profile = get_company_profile(uid)
    company = profile.company_name if profile else uid
    st.sidebar.markdown("### Enterprise Account")
    st.sidebar.markdown(f"**Organisation:** {company}")
    st.sidebar.metric("Audit Credits Remaining", credits)
    return credits


def render_intake_onboarding_tip() -> None:
    st.markdown(
        """
        <div class="intake-tip intake-tip-banner">
          <strong>Quick Tip:</strong> Clearly outline your human verification gates.
          Avoid <strong>fully autonomous decision making</strong> if a human supervisor
          signs off on final outputs — this helps our preliminary classifier surface
          accurate risk tiers.
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_column_tile_header(title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="intake-col-tile">
          <div class="intake-tile-label">{title}</div>
          <div class="intake-tile-sub">{subtitle}</div>
        """,
        unsafe_allow_html=True,
    )


def render_column_tile_footer() -> None:
    st.markdown("</div>", unsafe_allow_html=True)


def render_stripe_purchase_card(context: str = "audit") -> None:
    """Premium paywall product table + Stripe checkout CTA."""
    checkout_url = os.getenv(
        "STRIPE_CHECKOUT_URL",
        "https://buy.stripe.com/test_traceact_audit_credits",
    )
    st.markdown(
        """
        <div class="stripe-dashboard-card">
          <div class="stripe-section-label">Premium Compliance Package</div>
          <table class="stripe-dashboard-table">
            <thead>
              <tr>
                <th>Capability</th>
                <th>Light Preview (Free)</th>
                <th>Certified Audit (1 Credit)</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><strong>Preliminary risk tier scan</strong></td>
                <td>Included</td>
                <td>Included</td>
              </tr>
              <tr>
                <td><strong>Annex IV gap analysis matrix</strong></td>
                <td>Locked</td>
                <td>Included</td>
              </tr>
              <tr>
                <td><strong>Multi-agent compliance breach review</strong></td>
                <td>Locked</td>
                <td>Included</td>
              </tr>
              <tr>
                <td><strong>Download certified PDF report</strong></td>
                <td>Locked</td>
                <td>Included</td>
              </tr>
            </tbody>
          </table>
          <div class="stripe-card-foot">
            Purchase one audit credit below to unlock the full conformity pipeline and
            official PDF evidence pack.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.link_button(
        "Purchase Audit Credits via Stripe",
        checkout_url,
        type="primary",
        use_container_width=True,
        help="Secure checkout powered by Stripe. Credits are applied to your company profile after payment.",
    )
    st.caption(f"Context: {context}")


def render_full_audit_locked_notice() -> None:
    st.markdown(
        """
        <div class="intake-status-card intake-status-paywall">
          <div class="intake-status-title">Full Audit Locked</div>
          <div class="intake-status-body">
            <strong>Annex IV gap analysis</strong>, the <strong>multi-agent compliance
            breach matrices</strong>, and <strong>certified PDF download</strong> require
            an audit credit. Run the free preliminary scan above, then purchase a credit
            <strong>below</strong> to unlock production-grade evidence.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# Backward-compatible aliases.
def render_stripe_paywall(context: str = "audit") -> None:
    render_stripe_purchase_card(context)


def render_locked_description_notice() -> None:
    render_full_audit_locked_notice()
