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
