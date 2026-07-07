"""
Paywall UI helpers — Stripe checkout surfacing, credit gating, and sandbox demo.
"""

from __future__ import annotations

import os

import streamlit as st

from utils.tenant_db import get_audit_credits, get_company_profile
from utils.user_session import current_user_id

SANDBOX_WATERMARK = "SANDBOX PREVIEW - NOT LEGAL COMPLIANCE EVIDENCE"
_INTAKE_MODE_OPTIONS = ("Production Audit Mode", "Free Sandbox Demo Mode")
_DESCRIPTION_WIDGET_KEY = "wizard_description_area"


def sync_credit_count() -> int:
    """Mirror tenant credits on ``st.session_state.credit_count`` for UI conditionals."""
    uid = current_user_id()
    credits = get_audit_credits(uid) if uid else 0
    st.session_state["credit_count"] = credits
    return credits


def is_sandbox_demo() -> bool:
    return bool(st.session_state.get("sandbox_demo", False))


def intake_inputs_unlocked() -> bool:
    sync_credit_count()
    return st.session_state.get("credit_count", 0) > 0 or is_sandbox_demo()


def has_audit_credits() -> bool:
    return sync_credit_count() > 0


def ensure_description_widget_state(fallback: str = "") -> None:
    """
    Initialise the Step 4 description widget once.

    Avoids passing ``value=`` on every rerun, which fights the widget ``key``
    and causes focus loss while typing.
    """
    if _DESCRIPTION_WIDGET_KEY not in st.session_state:
        st.session_state[_DESCRIPTION_WIDGET_KEY] = fallback


def sync_description_to_intake(intake: dict) -> None:
    intake["description"] = st.session_state.get(_DESCRIPTION_WIDGET_KEY, "")


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
    if is_sandbox_demo():
        st.sidebar.success("Sandbox Demo active")
    return credits


def render_intake_mode_selector() -> None:
    """Enterprise mode switch — Production vs Free Sandbox Demo."""
    if "intake_mode_choice" not in st.session_state:
        st.session_state["intake_mode_choice"] = (
            _INTAKE_MODE_OPTIONS[1]
            if st.session_state.get("sandbox_demo")
            else _INTAKE_MODE_OPTIONS[0]
        )

    st.markdown(
        """
        <div class="intake-mode-shell">
          <div class="intake-mode-heading">Assessment Mode</div>
          <div class="intake-mode-copy">
            Choose <strong>Production Audit Mode</strong> for credit-backed official reports,
            or <strong>Free Sandbox Demo Mode</strong> to test intake and preview structures.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    choice = st.radio(
        "Assessment Mode",
        options=_INTAKE_MODE_OPTIONS,
        horizontal=True,
        key="intake_mode_choice",
        label_visibility="collapsed",
    )
    st.session_state["sandbox_demo"] = choice == _INTAKE_MODE_OPTIONS[1]


def render_intake_access_status() -> None:
    """Dynamic enterprise banner — sandbox success or locked paywall guidance."""
    if is_sandbox_demo():
        st.markdown(
            """
            <div class="intake-status-card intake-status-success">
              <div class="intake-status-body">
                💡 <strong>Sandbox Mode Active:</strong> Enter your parameters below to test our
                multi-agent RAG verification speed and preview report structures for free.
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    if st.session_state.get("credit_count", 0) > 0:
        return

    st.markdown(
        """
        <div class="intake-status-card intake-status-paywall">
          <div class="intake-status-title">Unlock the Conformity Workspace</div>
          <div class="intake-status-body">
            <strong>Activate the free Sandbox Demo</strong> above to instantly test application
            structure, intake flow, and preview report formatting — or
            <strong>purchase an audit credit below</strong> to generate production-grade
            compliance evidence.
          </div>
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
    """Professional Stripe checkout panel for zero-credit tenants."""
    checkout_url = os.getenv(
        "STRIPE_CHECKOUT_URL",
        "https://buy.stripe.com/test_traceact_audit_credits",
    )
    st.markdown(
        """
        <div class="stripe-dashboard-card">
          <table class="stripe-dashboard-table">
            <thead>
              <tr>
                <th>Product</th>
                <th>Includes</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><strong>TraceAct Audit Credit Pack</strong><br/>
                    <span class="stripe-muted">Official EU AI Act conformity assessment</span></td>
                <td><strong>1×</strong> multi-agent evaluation run<br/>
                    <strong>1×</strong> official PDF conformity report<br/>
                    <strong>Full</strong> obligations register export</td>
                <td class="stripe-action-cell">Secure checkout below</td>
              </tr>
            </tbody>
          </table>
          <div class="stripe-card-foot">
            Credits are consumed only after a successful production PDF report is generated.
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


def render_sandbox_preview_banner() -> None:
    """On-screen watermark for sandbox audit results."""
    st.markdown(
        f"""
        <div class="sandbox-preview-banner">
          <strong>{SANDBOX_WATERMARK}</strong>
        </div>
        """,
        unsafe_allow_html=True,
    )


# Backward-compatible aliases used elsewhere in the codebase.
def render_stripe_paywall(context: str = "audit") -> None:
    render_stripe_purchase_card(context)


def render_locked_description_notice() -> None:
    render_intake_access_status()
