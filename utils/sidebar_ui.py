"""
Enterprise sidebar workspace — corporate profile and report library.
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from utils.audit_archive import get_purchased_audits
from utils.user_session import current_user_id, current_user_email, is_activated_user


def _format_generation_date(iso_date: str) -> str:
    try:
        return datetime.fromisoformat(iso_date).strftime("%d %b %Y")
    except ValueError:
        return iso_date


def render_enterprise_sidebar() -> None:
    """Permanent corporate workspace card and certified report library."""
    uid = current_user_id()
    email = current_user_email()

    if is_activated_user():
        title = "🏢 Traceact Corporate Workspace"
        subtitle = f"👤 {email}"
    else:
        title = "🏢 Traceact Corporate Workspace"
        subtitle = "👤 Auditor Session"

    with st.sidebar:
        st.markdown(f"### {title}")
        st.caption(subtitle)
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
