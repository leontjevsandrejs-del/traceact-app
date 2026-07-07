"""
Stripe success-return handler and post-payment account activation gate.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import streamlit as st

from utils.account_store import activate_account, normalize_email
from utils.audit_archive import archive_purchased_audit
from utils.draft_store import bind_draft_to_user, get_draft
from utils.secure_session import establish_secure_cookie_session
from utils.tenant_db import ensure_company_profile, add_audit_credits
from utils.user_session import (
    activate_workspace_user,
    hydrate_workspace_from_snapshot,
    is_pending_activation,
    pending_activation,
    set_pending_activation,
    clear_pending_activation,
)

PAYMENT_PARAM = "payment"
DRAFT_ID_PARAM = "draft_id"
EMAIL_PARAM = "email"
SESSION_ID_PARAM = "session_id"


@dataclass(frozen=True)
class StripeReturnPayload:
    draft_id: str
    email: str
    session_id: str | None = None


def _inject_activation_css() -> None:
    st.markdown(
        """
        <style>
        section[data-testid="stSidebar"] { display: none !important; }
        .main .block-container {
            max-width: 520px !important;
            padding-top: 2.5rem;
        }
        .traceact-activation-card {
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 16px;
            padding: 1.75rem 1.5rem;
            box-shadow: 0 20px 40px rgba(15, 23, 42, 0.08);
        }
        .traceact-activation-title {
            font-size: 1.15rem;
            font-weight: 700;
            color: #0F172A;
            margin-bottom: 0.75rem;
            line-height: 1.45;
        }
        .traceact-activation-copy {
            font-size: 0.88rem;
            color: #64748B;
            line-height: 1.6;
            margin-bottom: 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _parse_stripe_return() -> StripeReturnPayload | None:
    if st.query_params.get(PAYMENT_PARAM) != "success":
        return None
    draft_id = (st.query_params.get(DRAFT_ID_PARAM) or "").strip()
    email = normalize_email(st.query_params.get(EMAIL_PARAM) or "")
    if not draft_id or not email:
        return None
    return StripeReturnPayload(
        draft_id=draft_id,
        email=email,
        session_id=(st.query_params.get(SESSION_ID_PARAM) or "").strip() or None,
    )


def _verify_stripe_session(payload: StripeReturnPayload) -> bool:
    """
    Optional server-side Stripe Checkout Session verification.

    When ``STRIPE_SECRET_KEY`` and ``session_id`` are present, confirm that the
    session is paid and metadata matches the return URL parameters.
    """
    secret = os.getenv("STRIPE_SECRET_KEY", "").strip()
    if not secret or not payload.session_id:
        return True
    try:
        import stripe  # type: ignore[import-untyped]

        stripe.api_key = secret
        session = stripe.checkout.Session.retrieve(payload.session_id)
        if session.payment_status != "paid":
            return False
        meta = session.metadata or {}
        meta_draft = (meta.get("draft_id") or session.client_reference_id or "").strip()
        customer_email = normalize_email(
            session.customer_details.email if session.customer_details else ""
        )
        return meta_draft == payload.draft_id and customer_email == payload.email
    except Exception:
        return False


def _unlock_draft_assets(user_id: str, email: str, draft_id: str) -> bool:
    draft = get_draft(draft_id)
    if not draft:
        return False
    snapshot: dict[str, Any] = draft.get("snapshot") or {}
    hydrate_workspace_from_snapshot(snapshot)
    bind_draft_to_user(draft_id, user_id, email)
    ensure_company_profile(user_id, contact_email=email)
    add_audit_credits(user_id, 1)

    pdf_bytes = snapshot.get("pdf_data_bytes")
    if pdf_bytes:
        intake = snapshot.get("intake") or {}
        system_name = (
            intake.get("company")
            or intake.get("industry")
            or "AI System"
        )
        archive_purchased_audit(
            user_id,
            email,
            system_name,
            pdf_bytes,
        )
    return True


def render_account_activation_frame(email: str, draft_id: str) -> None:
    _inject_activation_css()
    st.markdown(
        f"""
        <div class="traceact-activation-card">
          <div class="traceact-activation-title">Secure Account Activation</div>
          <div class="traceact-activation-copy">
            Your corporate vault has been initialized for <strong>{email}</strong>.
            Please establish a secure password to encrypt your dataset inputs and
            lock down your certified compliance assets.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    password = st.text_input(
        "Workspace password",
        type="password",
        placeholder="Minimum 8 characters",
        key="traceact_activation_password",
    )
    if st.button(
        "Activate Compliance Workspace",
        type="primary",
        use_container_width=True,
        key="traceact_activation_submit",
    ):
        try:
            user_id = activate_account(email, password, draft_id)
            if not _unlock_draft_assets(user_id, email, draft_id):
                st.error("Payment draft could not be located. Contact support.")
                return
            activate_workspace_user(user_id, email)
            establish_secure_cookie_session(user_id, email)
            clear_pending_activation()
            st.query_params.clear()
            st.success("Compliance workspace activated. Loading your certified assets…")
            st.rerun()
        except ValueError as err:
            st.error(str(err))


def handle_stripe_return_or_continue() -> bool:
    """
    Process Stripe success returns.

    Returns True when the main workspace may render; False when the activation
    password gate is showing (caller should ``st.stop()``).
    """
    payload = _parse_stripe_return()
    if payload is None:
        if is_pending_activation():
            pending = pending_activation()
            render_account_activation_frame(pending["email"], pending["draft_id"])
            return False
        return True

    if not _verify_stripe_session(payload):
        st.error("Stripe payment could not be verified for this return URL.")
        return False

    draft = get_draft(payload.draft_id)
    if not draft:
        st.error(
            "Your payment succeeded but the audit draft was not found. "
            "Please contact support with your receipt."
        )
        return False

    set_pending_activation(payload.email, payload.draft_id)
    render_account_activation_frame(payload.email, payload.draft_id)
    return False
