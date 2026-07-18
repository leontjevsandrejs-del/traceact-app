"""
Integrated QMS (Quality Management System) tracking dashboard for members.

Fetches ``compliance_tasks`` from Supabase and renders an interactive
``st.data_editor`` workspace with live status syncing.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from utils.auth_session import get_auth_user_id, is_logged_in
from utils.supabase_db import (
    QMS_STATUS_UI_OPTIONS,
    fetch_compliance_tasks_for_user,
    update_compliance_task_statuses,
)

QMS_TAB_DEFAULT = "QMS Workspace"
QMS_EDITOR_KEY = "qms_tasks_editor"


def qms_tab_label(copy: dict | None = None) -> str:
    if copy:
        return str(copy.get("tab_label") or QMS_TAB_DEFAULT)
    return QMS_TAB_DEFAULT


def render_qms_dashboard(qms_copy: dict | None = None) -> None:
    """Premium member-only compliance task tracking board."""
    copy = qms_copy or {}

    if not is_logged_in():
        st.warning(
            copy.get(
                "login_required",
                "Sign in to access the Integrated QMS tracking workspace.",
            )
        )
        return

    user_id = get_auth_user_id()
    if not user_id:
        st.error(
            copy.get(
                "missing_user",
                "Unable to resolve your member account. Please log in again.",
            )
        )
        return

    st.markdown(f"""
    <div style="padding:1.25rem 0 0.25rem;">
      <div class="section-label">{copy.get("label", "Integrated Quality Management System")}</div>
      <div class="section-title">{copy.get("title", "Compliance Task Tracking Board")}</div>
      <div class="section-sub">{copy.get("sub", "Track statutory obligations across frameworks and sync progress to your enterprise vault.")}</div>
    </div>
    <hr class="section-divider">
    """, unsafe_allow_html=True)

    tasks = fetch_compliance_tasks_for_user(user_id)

    if not tasks:
        st.info(
            copy.get(
                "empty_state",
                "No compliance tasks yet. Run a Conformity Assessment while "
                "signed in to populate your QMS workspace automatically.",
            )
        )
        return

    df = pd.DataFrame(tasks, columns=["id", "title", "framework_mapping", "status"])

    in_progress = int((df["status"] == "In Progress").sum())
    compliant = int((df["status"] == "Compliant").sum())
    total = len(df)

    m1, m2, m3 = st.columns(3)
    m1.metric(
        copy.get("metric_total", "Total Tasks"),
        total,
    )
    m2.metric(
        copy.get("metric_in_progress", "In Progress"),
        in_progress,
    )
    m3.metric(
        copy.get("metric_compliant", "Fully Compliant"),
        compliant,
    )

    st.markdown('<div style="height:0.75rem;"></div>', unsafe_allow_html=True)

    edited_df = st.data_editor(
        df,
        key=QMS_EDITOR_KEY,
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        column_config={
            "id": st.column_config.TextColumn(
                "ID",
                disabled=True,
                width="small",
            ),
            "title": st.column_config.TextColumn(
                copy.get("col_title", "Obligation"),
                disabled=True,
                width="large",
            ),
            "framework_mapping": st.column_config.TextColumn(
                copy.get("col_framework", "Framework"),
                disabled=True,
                width="medium",
            ),
            "status": st.column_config.SelectboxColumn(
                copy.get("col_status", "Status"),
                options=list(QMS_STATUS_UI_OPTIONS),
                required=True,
                width="small",
            ),
        },
    )

    if st.button(
        copy.get("save_button", "Save Workspace Progress"),
        type="primary",
        key="qms_save_progress_btn",
        use_container_width=True,
    ):
        updates = [
            {"id": str(row["id"]), "status": str(row["status"])}
            for _, row in edited_df.iterrows()
            if row.get("id")
        ]
        saved = update_compliance_task_statuses(updates)
        if saved:
            success_msg = copy.get(
                "save_success",
                "Workspace progress synced to Supabase.",
            )
            st.success(success_msg)
            try:
                st.toast(success_msg, icon="✅")
            except Exception:
                pass
            st.rerun()
        else:
            st.error(
                copy.get(
                    "save_error",
                    "Could not sync task statuses. Check Supabase connectivity.",
                )
            )
