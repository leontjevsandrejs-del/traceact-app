"""
Enterprise sidebar workspace — corporate profile, report library, logout.
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from utils.auth_gate import get_sidebar_authenticator
from utils.tenant_db import get_company_profile, get_purchased_audits
from utils.user_session import current_user_id


def _format_generation_date(iso_date: str) -> str:
    try:
        return datetime.fromisoformat(iso_date).strftime("%d %b %Y")
    except ValueError:
        return iso_date


def render_enterprise_sidebar() -> None:
    """Corporate account card, certified report library, and logout."""
    uid = current_user_id()
    if not uid:
        return

    profile = get_company_profile(uid)
    company = profile.company_name if profile else uid.replace("_", " ").title()
    email = (
        st.session_state.get("email")
        or (profile.contact_email if profile else "")
        or uid
    )

    with st.sidebar:
        st.markdown(
            f"""
            <div class="sidebar-account-card">
              <div class="sidebar-account-icon">🏢</div>
              <div class="sidebar-account-company">{company}</div>
              <div class="sidebar-account-email">👤 {email}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="sidebar-library-heading">📂 Certified Report Library</div>',
            unsafe_allow_html=True,
        )

        audits = get_purchased_audits(user_email=email, user_id=uid)
        if not audits:
            st.markdown(
                """
                <div class="sidebar-library-empty">
                  No certified reports generated yet. Completed production audits
                  will appear here securely.
                </div>
                """,
                unsafe_allow_html=True,
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
                        file_name=f"TraceAct_{audit.system_name.replace(' ', '_')}_{audit.generated_at}.pdf",
                        mime="application/pdf",
                        key=f"sidebar_audit_download_{audit.audit_id}",
                        use_container_width=True,
                    )

        st.markdown('<div class="sidebar-logout-spacer"></div>', unsafe_allow_html=True)

        authenticator = get_sidebar_authenticator()
        authenticator.logout(
            button_name="Sign Out",
            location="sidebar",
            key="TraceActLogout",
        )
