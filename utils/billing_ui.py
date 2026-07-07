"""
Paywall UI helpers — Stripe checkout surfacing and credit gating.
"""

from __future__ import annotations

import os

import streamlit as st

from utils.tenant_db import get_audit_credits, get_company_profile
from utils.user_session import current_user_id


def has_audit_credits() -> bool:
    uid = current_user_id()
    return bool(uid) and get_audit_credits(uid) > 0


def render_credit_banner() -> int:
    """Sidebar/header credit meter. Returns remaining credits."""
    uid = current_user_id()
    if not uid:
        return 0
    profile = get_company_profile(uid)
    credits = get_audit_credits(uid)
    company = profile.company_name if profile else uid
    st.sidebar.markdown("### Enterprise Account")
    st.sidebar.markdown(f"**Organisation:** {company}")
    st.sidebar.metric("Audit Credits Remaining", credits)
    return credits


def render_stripe_paywall(context: str = "audit") -> None:
    """Clean purchase CTA when credits are exhausted."""
    checkout_url = os.getenv(
        "STRIPE_CHECKOUT_URL",
        "https://buy.stripe.com/test_traceact_audit_credits",
    )
    st.markdown(
        """
        <div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:12px;
             padding:1.25rem 1.5rem;margin:0.75rem 0;
             box-shadow:0 1px 4px rgba(0,0,0,0.05);">
          <div style="font-size:0.72rem;font-weight:700;letter-spacing:0.1em;
               text-transform:uppercase;color:#2563EB;margin-bottom:0.35rem;">
            Audit Credits Required
          </div>
          <div style="font-size:1rem;font-weight:600;color:#0F172A;margin-bottom:0.35rem;">
            Unlock EU AI Act Conformity Audits
          </div>
          <div style="font-size:0.85rem;color:#64748B;line-height:1.6;">
            Your organisation has no remaining audit credits. Purchase a credit pack
            to run the multi-agent evaluation pipeline and generate your official
            PDF conformity report.
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
    st.caption(
        f"Context: {context} · Credits are consumed only after a successful PDF report is generated."
    )


def render_locked_description_notice() -> None:
    st.info(
        "System description and evidence uploads are locked until your organisation "
        "has at least one audit credit. Purchase credits above to unlock the intake "
        "fields and run a conformity assessment."
    )
