"""
Enterprise sidebar workspace — corporate profile, auth, and report library.
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from utils.audit_archive import get_purchased_audits
from utils.auth_session import (
    get_auth_email,
    get_company_name,
    is_logged_in,
    login_user,
    logout_user,
    register_user,
)
from utils.user_session import current_user_id, current_user_email, is_activated_user


def _format_generation_date(iso_date: str) -> str:
    try:
        return datetime.fromisoformat(iso_date).strftime("%d %b %Y")
    except ValueError:
        return iso_date


def _render_user_account_section() -> None:
    """Login / Register gate — Supabase Auth."""
    st.markdown("#### 👤 User Account")

    if is_logged_in():
        email = get_auth_email() or current_user_email()
        company = get_company_name()
        st.success("Signed in")
        st.caption(email)
        if company:
            st.caption(f"Company: {company}")
        if st.button("Log out", key="auth_logout_btn", use_container_width=True):
            logout_user()
            st.rerun()
        return

    login_tab, register_tab = st.tabs(["Login", "Register"])

    with login_tab:
        with st.form("traceact_login_form", clear_on_submit=False):
            login_email = st.text_input("Email", key="login_email_input")
            login_password = st.text_input(
                "Password", type="password", key="login_password_input"
            )
            submitted = st.form_submit_button("Log in", use_container_width=True)
            if submitted:
                ok, message = login_user(login_email, login_password)
                if ok:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)

    with register_tab:
        with st.form("traceact_register_form", clear_on_submit=False):
            reg_email = st.text_input("Email", key="register_email_input")
            reg_password = st.text_input(
                "Password", type="password", key="register_password_input"
            )
            reg_company = st.text_input(
                "Company Name", key="register_company_input"
            )
            submitted = st.form_submit_button(
                "Create account", use_container_width=True
            )
            if submitted:
                ok, message = register_user(reg_email, reg_password, reg_company)
                if ok:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)


def render_enterprise_sidebar() -> None:
    """Permanent corporate workspace card and certified report library."""
    uid = current_user_id()
    email = current_user_email()

    if is_logged_in():
        title = "🏢 Traceact Corporate Workspace"
        subtitle = f"👤 {get_auth_email() or email}"
    elif is_activated_user():
        title = "🏢 Traceact Corporate Workspace"
        subtitle = f"👤 {email}"
    else:
        title = "🏢 Traceact Corporate Workspace"
        subtitle = "👤 Guest Auditor (Zero-Retention)"

    with st.sidebar:
        st.markdown(f"### {title}")
        st.caption(subtitle)
        st.divider()

        _render_user_account_section()
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

        # Dev-only: verify Supabase SSL + table wiring (collapsed / non-prominent)
        with st.expander("🛠 Developer", expanded=False):
            if st.button(
                "Test Database Connection",
                key="supabase_db_connection_test",
                use_container_width=True,
            ):
                from utils.supabase_db import (
                    get_supabase_client,
                    insert_connection_test_row,
                )

                client = get_supabase_client()
                if client is None:
                    st.error(
                        "Supabase client unavailable. Set SUPABASE_URL and "
                        "SUPABASE_KEY in Streamlit secrets."
                    )
                else:
                    row = insert_connection_test_row()
                    if row:
                        st.success(
                            "Database connection OK — mock row written to "
                            f"`audit_reports` (id={row.get('id', 'n/a')})."
                        )
                    else:
                        st.error(
                            "Connection reached Supabase but the insert failed. "
                            "Confirm the SQL schema is applied and the key has "
                            "insert rights on `audit_reports`."
                        )
