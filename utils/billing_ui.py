"""
Paywall UI helpers — Stripe checkout surfacing, credit gating, and sandbox demo.
"""

from __future__ import annotations

import os

import streamlit as st

from utils.tenant_db import get_audit_credits, get_company_profile
from utils.user_session import current_user_id

SANDBOX_WATERMARK = "SANDBOX PREVIEW - NOT LEGAL COMPLIANCE EVIDENCE"


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


def render_intake_access_status() -> None:
    """Dynamic access banner for Step 4 intake workspace."""
    if is_sandbox_demo():
        st.markdown(
            """
            <div class="intake-status-card intake-status-success">
              <div class="intake-status-body">
                <strong>Sandbox Mode Active:</strong> You can now enter sample specifications
                to test our evaluation speed and report structure for free.
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.success(
            "💡 Sandbox Mode Active: You can now enter sample specifications to test "
            "our evaluation speed and report structure for free."
        )
        return

    if st.session_state.get("credit_count", 0) > 0:
        return

    st.markdown(
        """
        <div class="intake-status-card intake-status-warning">
          <div class="intake-status-title">Intake Workspace Locked</div>
          <div class="intake-status-body">
            <strong>An audit credit or Sandbox Demo activation is required</strong>
            to unlock file uploads, system descriptions, and the conformity pipeline.
            Toggle <strong>Activate Sandbox Demo Mode</strong> above for a free preview,
            or purchase credits using the secure checkout option <strong>below</strong>.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_workspace_tile_open(title: str, subtitle: str = "") -> None:
    sub_html = (
        f'<div class="intake-tile-sub">{subtitle}</div>' if subtitle else ""
    )
    st.markdown(
        f"""
        <div class="intake-workspace-tile">
          <div class="intake-tile-label">{title}</div>
          {sub_html}
        """,
        unsafe_allow_html=True,
    )


def render_workspace_tile_close() -> None:
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
                    <strong>1×</strong> watermarked-official PDF report<br/>
                    <strong>Full</strong> obligations register export</td>
                <td class="stripe-action-cell">Use the checkout button below</td>
              </tr>
            </tbody>
          </table>
          <div class="stripe-card-foot">
            Credits are consumed only after a successful PDF report is generated.
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
