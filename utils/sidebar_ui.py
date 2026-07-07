"""
Enterprise sidebar workspace — corporate profile, report library, logout.
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from utils.audit_archive import get_purchased_audits
from utils.auth_session import (
    AUTHENTICATOR_STATE_KEY,
    AUTH_STATUS_KEY,
    AUTH_USERNAME_KEY,
)
from utils.user_session import current_user_id, sync_auth_session, us_get


def _format_generation_date(iso_date: str) -> str:
    try:
        return datetime.fromisoformat(iso_date).strftime("%d %b %Y")
    except ValueError:
        return iso_date


def _load_company_profile(uid: str):
    try:
        from utils.tenant_db import get_company_profile
        return get_company_profile(uid)
    except ImportError:
        return None


def _workspace_company_name(uid: str, profile) -> str:
    intake_company = (us_get("intake", {}) or {}).get("company", "").strip()
    if intake_company:
        return intake_company
    if profile and profile.company_name:
        return profile.company_name
    return "Active Workspace"


def render_enterprise_sidebar() -> None:
    """Corporate account card, certified report library, and logout."""
    if st.session_state.get(AUTH_STATUS_KEY) is not True:
        return

    uid = sync_auth_session() or st.session_state.get(AUTH_USERNAME_KEY, "")
    if not uid:
        return

    profile = _load_company_profile(uid)
    company = _workspace_company_name(uid, profile)
    username = st.session_state.get(AUTH_USERNAME_KEY, uid) or "Auditor User"
    email = (
        st.session_state.get("email")
        or (profile.contact_email if profile else "")
        or username
    )

    with st.sidebar:
        st.markdown(f"### 🏢 {company}")
        st.caption(f"👤 {username}")
        st.divider()

        st.markdown("#### 📂 Certified Report Library")

        audits = get_purchased_audits(user_email=email, user_id=uid)
        if not audits:
            st.info(
                "No certified reports generated yet. Your paid PDF compliance "
                "evidence packages will append here automatically."
            )
        else:
            for audit in audits:
                label = (
                    f"{audit.system_name}  ·  "
                    f"{_format_generation_date(audit.generated_at)}"
                )
                with st.expander(label, expanded=False):
                    st.markdown(
                        f"**System Name:** {audit.system_name}  \n"
                        f"**Generation Date:** {_format_generation_date(audit.generated_at)}"
                    )
                    st.download_button(
                        label="Download Certified PDF",
                        data=audit.pdf_bytes,
                        file_name=(
                            f"TraceAct_{audit.system_name.replace(' ', '_')}"
                            f"_{audit.generated_at}.pdf"
                        ),
                        mime="application/pdf",
                        key=f"sidebar_audit_download_{audit.audit_id}",
                        use_container_width=True,
                    )

        st.markdown('<div class="sidebar-logout-spacer"></div>', unsafe_allow_html=True)

        authenticator = st.session_state.get(AUTHENTICATOR_STATE_KEY)
        if authenticator is not None:
            authenticator.logout(
                button_name="Sign Out",
                location="sidebar",
                key="TraceActLogout",
            )
