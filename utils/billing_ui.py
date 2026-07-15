"""
Paywall UI helpers — static Stripe Payment Link gate for Conformity Assessment.
"""

from __future__ import annotations

import streamlit as st

from utils.draft_store import ensure_session_draft_id, persist_session_draft
from utils.stripe_config import (
    get_stripe_payment_link,
    get_stripe_growth_payment_link,
    get_stripe_one_time_payment_link,
)
from utils.user_session import us_get, us_set, current_user_email, current_user_id

DESCRIPTION_WIDGET_KEY = "system_description_input"
_PAID_FLAG = "assessment_paid"
_AUTO_RUN_FLAG = "auto_run_assessment"
WORKSPACE_TAB_KEY = "workspace_active_tab"


def focus_conformity_assessment_tab(tab_label: str = "Conformity Assessment") -> None:
    """Select the Conformity Assessment workspace after Stripe payment return."""
    st.session_state[WORKSPACE_TAB_KEY] = tab_label


def is_assessment_paid() -> bool:
    return bool(
        st.session_state.get(_PAID_FLAG)
        or us_get(_PAID_FLAG, False)
    )


def mark_assessment_paid(*, auto_run: bool = True) -> None:
    st.session_state[_PAID_FLAG] = True
    st.session_state["payment_cleared"] = True
    st.session_state["b2b_tier"] = "Growth"
    us_set(_PAID_FLAG, True)
    if auto_run:
        st.session_state[_AUTO_RUN_FLAG] = True
        us_set(_AUTO_RUN_FLAG, True)
    _sync_stripe_entitlement_to_tenant()


def _sync_stripe_entitlement_to_tenant() -> None:
    """Mirror a successful Stripe payment into the tenant credit ledger."""
    try:
        from utils.tenant_db import add_audit_credits, ensure_company_profile

        uid = current_user_id()
        ensure_company_profile(uid, current_user_email())
        add_audit_credits(uid, 1)
    except Exception:
        pass


def consume_audit_entitlement(user_id: str) -> bool:
    """
    Record use of a certified assessment after PDF generation.

    Stripe-paid sessions are always entitled; legacy tenant credits are
    deducted only when the Stripe flag is not set.
    """
    if is_assessment_paid():
        return True
    if not user_id:
        return True
    from utils.tenant_db import deduct_audit_credit

    return deduct_audit_credit(user_id, 1)


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


def is_pdf_export_unlocked() -> bool:
    return bool(st.session_state.get("payment_cleared") or is_assessment_paid())


def build_stripe_checkout_url() -> str | None:
    """Payment Link URL with draft id for post-checkout session restore."""
    ensure_session_draft_id()
    persist_session_draft()
    base_link = get_stripe_payment_link()
    if not base_link or not base_link.startswith("https://buy.stripe.com/"):
        return None
    draft_id = st.session_state.get("draft_id", "")
    separator = "&" if "?" in base_link else "?"
    return f"{base_link}{separator}client_reference_id={draft_id}"


def build_stripe_growth_checkout_url() -> str | None:
    """Growth-tier Payment Link with draft id for workspace continuity."""
    ensure_session_draft_id()
    persist_session_draft()
    base_link = get_stripe_growth_payment_link() or get_stripe_payment_link()
    if not base_link or not base_link.startswith("https://buy.stripe.com/"):
        return None
    draft_id = st.session_state.get("draft_id", "")
    separator = "&" if "?" in base_link else "?"
    return f"{base_link}{separator}client_reference_id={draft_id}"


def build_stripe_one_time_checkout_url() -> str | None:
    """Single-report Payment Link with draft id for post-checkout session restore."""
    ensure_session_draft_id()
    persist_session_draft()
    base_link = get_stripe_one_time_payment_link()
    if not base_link or not base_link.startswith("https://buy.stripe.com/"):
        return None
    draft_id = st.session_state.get("draft_id", "")
    separator = "&" if "?" in base_link else "?"
    return f"{base_link}{separator}client_reference_id={draft_id}"


def render_pdf_export_action(
    *,
    pdf_bytes: bytes | None = None,
    audit_complete: bool = False,
    download_label: str = "Download Certified PDF Report",
    upgrade_label: str = "Upgrade to Export Full Certified PDF Report",
) -> None:
    """B2B finish-line: Sandbox diagnostic hand-off or premium export controls."""
    st.markdown("---")
    st.subheader("🛡️ Compliance Diagnostic Output & Validation Pipeline")

    if st.session_state.get("b2b_tier") == "Sandbox":
        st.info(
            "💡 **Diagnostic Mode Active:** You are viewing the automated readiness "
            "evaluation framework. Select a clearance tier below to unlock your "
            "corporate conformity package."
        )

        col1, col2 = st.columns(2)

        growth_url = (
            build_stripe_growth_checkout_url()
            or "https://buy.stripe.com/dRmbJ2ddmgvb61qeVm87K00"
        )
        one_time_url = (
            build_stripe_one_time_checkout_url()
            or "https://buy.stripe.com/fZu3cw4GQceVahGaF687K01"
        )

        with col1:
            st.markdown("""
        <div style="background-color:#f8fafc; border: 1px solid #e2e8f0; padding: 20px; border-radius: 12px; min-height: 250px; display: flex; flex-direction: column; justify-content: space-between;">
            <div>
                <h3 style="margin-top:0; color:#0f172a; font-size:20px;">🚀 Growth Monitor</h3>
                <p style="color:#475569; font-size:18px; font-weight:700; margin-top:5px; margin-bottom:15px;">€249 / month <span style="font-size:12px; font-weight:400; color:#94a3b8;">(Billed Annually)</span></p>
                <ul style="color:#334155; padding-left:18px; line-height:1.5; font-size:14px;">
                    <li><strong>Active Repository Drift Mapping:</strong> Continuous tracking against live code updates.</li>
                    <li><strong>Unlimited Vault Parsing:</strong> Run heavy technical compliance blueprints transiently.</li>
                    <li><strong>Monthly Delta Metrics:</strong> Regular alignment health monitoring alerts.</li>
                </ul>
            </div>
        </div>
        """, unsafe_allow_html=True)
            st.link_button(
                "Subscribe to Growth",
                growth_url,
                type="primary",
                use_container_width=True,
            )

        with col2:
            st.markdown("""
        <div style="background-color:#f8fafc; border: 1px solid #e2e8f0; padding: 20px; border-radius: 12px; min-height: 250px; display: flex; flex-direction: column; justify-content: space-between;">
            <div>
                <h3 style="margin-top:0; color:#0f172a; font-size:20px;">📄 Single Compliance Report</h3>
                <p style="color:#475569; font-size:18px; font-weight:700; margin-top:5px; margin-bottom:15px;">€149 <span style="font-size:12px; font-weight:400; color:#94a3b8;">(One-Time Purchase)</span></p>
                <ul style="color:#334155; padding-left:18px; line-height:1.5; font-size:14px;">
                    <li><strong>Instant PDF Blueprint:</strong> Full download access to this complete evaluation package.</li>
                    <li><strong>Conformity Documentation:</strong> Pre-compiled draft framework mapped to the EU AI Act.</li>
                    <li><strong>B2B Invoice Generation:</strong> Automatic corporate receipt parsing for accounting.</li>
                </ul>
            </div>
        </div>
        """, unsafe_allow_html=True)
            st.link_button(
                "Buy Single Report",
                one_time_url,
                type="primary",
                use_container_width=True,
            )

    elif st.session_state.get("b2b_tier") in ["Growth", "Enterprise"]:
        st.success(
            f"💳 Premium {st.session_state['b2b_tier']} Suite Active — "
            "Continuous Monitoring Engaged."
        )
        if pdf_bytes:
            st.download_button(
                label=download_label,
                data=pdf_bytes,
                file_name="EU_AI_Act_Audit_Report.pdf",
                mime="application/pdf",
                type="primary",
                key="download_audit_report",
                use_container_width=True,
            )
        elif audit_complete:
            st.info("Your certified PDF is being prepared. Refresh if this persists.")
        elif is_pdf_export_unlocked():
            checkout_url = build_stripe_checkout_url()
            if checkout_url:
                st.link_button(
                    upgrade_label,
                    checkout_url,
                    type="primary",
                    use_container_width=True,
                )
        else:
            st.caption(
                "Run the compliance audit above to generate your certified PDF report."
            )
