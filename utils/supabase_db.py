"""
Supabase storage layer — connection bootstrap and audit persistence hooks.

Credentials are read exclusively from Streamlit secrets
(``SUPABASE_URL``, ``SUPABASE_KEY``). Does not touch the 3-agent pipeline.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import streamlit as st

logger = logging.getLogger(__name__)

AUDIT_REPORTS_TABLE = "audit_reports"
COMPLIANCE_TASKS_TABLE = "compliance_tasks"


def create_supabase_client():
    """
    Build a fresh Supabase client from Streamlit secrets.

    Prefer this for Auth API calls so a cached client never holds a user session.
    """
    try:
        url = str(st.secrets["SUPABASE_URL"]).strip().strip("\"'")
        key = str(st.secrets["SUPABASE_KEY"]).strip().strip("\"'")
    except Exception as exc:
        logger.warning("Supabase secrets unavailable: %s", exc)
        return None

    if not url or not key:
        logger.warning("Supabase URL or KEY is empty.")
        return None

    try:
        from supabase import create_client

        return create_client(url, key)
    except Exception as exc:
        logger.exception("Failed to create Supabase client: %s", exc)
        return None


@st.cache_resource
def get_supabase_client():
    """
    Initialise and cache a single anonymous Supabase client for DB I/O.

    Expects Streamlit secrets:
      - SUPABASE_URL
      - SUPABASE_KEY  (anon or service-role key)

    Do not call ``.auth.sign_in_*`` on this instance — use
    ``create_supabase_client()`` for authentication.
    """
    return create_supabase_client()


def _as_json_object(value: Any, field_name: str) -> dict[str, Any]:
    """Coerce text / dict payloads into a JSON object for JSONB columns."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {"raw_text": text}
        if isinstance(parsed, dict):
            return parsed
        return {field_name: parsed}
    if isinstance(value, (list, int, float, bool)):
        return {field_name: value}
    return {"raw_text": str(value)}


def save_audit_to_db(
    user_id: str,
    system_profile: Any,
    audit_results: Any,
) -> dict[str, Any] | None:
    """
    Insert one audit report row into ``audit_reports``.

    Safely parses ``system_profile`` / ``audit_results`` (dict or JSON/text)
    and swallows client/API errors so the UI pipeline is never interrupted.
    Returns the inserted row dict on success, otherwise ``None``.
    """
    uid = (user_id or "").strip()
    if not uid:
        logger.warning("save_audit_to_db called without user_id")
        return None

    profile = _as_json_object(system_profile, "system_profile")
    results = _as_json_object(audit_results, "audit_results")

    system_name = (
        str(
            profile.get("system_name")
            or profile.get("company_name")
            or profile.get("company")
            or ""
        ).strip()
        or "Untitled System"
    )
    risk_tier = str(
        results.get("risk_tier")
        or results.get("tier")
        or profile.get("risk_tier")
        or ""
    ).strip() or None

    payload = {
        "user_id": uid,
        "system_profile": profile,
        "audit_results": results,
        "system_name": system_name,
        "risk_tier": risk_tier,
    }

    try:
        client = get_supabase_client()
        if client is None:
            logger.warning("save_audit_to_db: Supabase client not configured")
            return None

        response = (
            client.table(AUDIT_REPORTS_TABLE)
            .insert(payload)
            .execute()
        )
        rows = getattr(response, "data", None) or []
        return rows[0] if rows else payload
    except Exception as exc:
        logger.exception("save_audit_to_db failed: %s", exc)
        return None


def save_compliance_tasks(
    user_id: str,
    audit_id: str,
    tasks: list[dict[str, Any]],
) -> int:
    """
    Insert outstanding compliance task rows linked to an audit report.

    Each task dict may include: title, description, status, due_date, citation.
    Returns the number of rows inserted (0 on failure / empty input).
    """
    uid = (user_id or "").strip()
    aid = (audit_id or "").strip()
    if not uid or not aid or not tasks:
        return 0

    rows: list[dict[str, Any]] = []
    for raw in tasks:
        title = str(raw.get("title") or "").strip()
        if not title:
            continue
        status = str(raw.get("status") or "open").strip().lower()
        if status not in {"open", "in_progress", "done", "blocked"}:
            status = "open"
        row: dict[str, Any] = {
            "user_id": uid,
            "audit_id": aid,
            "title": title[:500],
            "description": str(raw.get("description") or "")[:4000] or None,
            "status": status,
            "citation": str(raw.get("citation") or "")[:500] or None,
            "framework_mapping": str(
                raw.get("framework_mapping") or "EU AI Act"
            )[:100],
        }
        due = raw.get("due_date")
        if due:
            row["due_date"] = str(due)
        rows.append(row)

    if not rows:
        return 0

    try:
        client = get_supabase_client()
        if client is None:
            return 0
        response = (
            client.table(COMPLIANCE_TASKS_TABLE)
            .insert(rows)
            .execute()
        )
        inserted = getattr(response, "data", None) or []
        return len(inserted) if inserted else len(rows)
    except Exception as exc:
        logger.exception("save_compliance_tasks failed: %s", exc)
        return 0


def persist_member_audit(
    user_id: str,
    system_profile: Any,
    audit_results: Any,
    compliance_tasks: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """
    Save the audit report, then attach automated compliance tasks when provided.
    """
    row = save_audit_to_db(user_id, system_profile, audit_results)
    if not row:
        return None
    audit_id = str(row.get("id") or "").strip()
    if audit_id and compliance_tasks:
        save_compliance_tasks(user_id, audit_id, compliance_tasks)
    return row


def insert_connection_test_row() -> dict[str, Any] | None:
    """Write a disposable mock audit row to verify SSL + table wiring."""
    return save_audit_to_db(
        user_id="dev_connection_test",
        system_profile={
            "system_name": "Supabase Connection Probe",
            "company_name": "TraceAct Dev",
            "source": "sidebar_test_button",
        },
        audit_results={
            "risk_tier": "Connection Test",
            "status": "ok",
            "message": "Mock entry confirming API communication and schema.",
        },
    )


# ── QMS dashboard: status vocabulary (DB ↔ UI) ───────────────────────────────

QMS_STATUS_UI_OPTIONS = ("Not Started", "In Progress", "Compliant")

_DB_TO_UI_STATUS = {
    "open": "Not Started",
    "in_progress": "In Progress",
    "done": "Compliant",
    "blocked": "Not Started",
}

_UI_TO_DB_STATUS = {
    "Not Started": "open",
    "In Progress": "in_progress",
    "Compliant": "done",
}


def db_status_to_ui(status: str | None) -> str:
    key = str(status or "open").strip().lower()
    return _DB_TO_UI_STATUS.get(key, "Not Started")


def ui_status_to_db(status: str | None) -> str:
    label = str(status or "Not Started").strip()
    return _UI_TO_DB_STATUS.get(label, "open")


def fetch_compliance_tasks_for_user(user_id: str) -> list[dict[str, Any]]:
    """
    Load QMS task rows for the interactive dashboard.

    Returns dicts with keys: id, title, framework_mapping, status (UI labels).
    """
    uid = (user_id or "").strip()
    if not uid:
        return []

    try:
        client = get_supabase_client()
        if client is None:
            return []

        response = (
            client.table(COMPLIANCE_TASKS_TABLE)
            .select("id, title, framework_mapping, status")
            .eq("user_id", uid)
            .order("created_at", desc=False)
            .execute()
        )
        rows = getattr(response, "data", None) or []
        results: list[dict[str, Any]] = []
        for row in rows:
            results.append({
                "id": str(row.get("id", "")),
                "title": str(row.get("title") or ""),
                "framework_mapping": str(
                    row.get("framework_mapping") or "EU AI Act"
                ),
                "status": db_status_to_ui(row.get("status")),
            })
        return results
    except Exception as exc:
        logger.exception("fetch_compliance_tasks_for_user failed: %s", exc)
        return []


def update_compliance_task_statuses(updates: list[dict[str, str]]) -> int:
    """
    Persist edited QMS task statuses.

    Each update dict must include ``id`` and ``status`` (UI label).
    Returns the count of successfully updated rows.
    """
    if not updates:
        return 0

    client = get_supabase_client()
    if client is None:
        return 0

    updated = 0
    for item in updates:
        task_id = str(item.get("id") or "").strip()
        if not task_id:
            continue
        db_status = ui_status_to_db(item.get("status"))
        try:
            (
                client.table(COMPLIANCE_TASKS_TABLE)
                .update({"status": db_status})
                .eq("id", task_id)
                .execute()
            )
            updated += 1
        except Exception as exc:
            logger.exception(
                "update_compliance_task_statuses failed for %s: %s",
                task_id,
                exc,
            )
    return updated

