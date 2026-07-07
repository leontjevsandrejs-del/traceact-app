"""
Pre-payment audit draft registry.

Persists wizard intake and report artefacts keyed by ``draft_id`` until a
verified Stripe billing email completes account activation.
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DRAFTS_PATH = _PROJECT_ROOT / "data" / "draft_registry.json"


def _load_registry() -> dict[str, dict]:
    if not _DRAFTS_PATH.is_file():
        return {}
    try:
        with open(_DRAFTS_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_registry(registry: dict[str, dict]) -> None:
    _DRAFTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_DRAFTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(registry, fh, indent=2)


def _encode_bytes(value: bytes | None) -> str | None:
    if value is None:
        return None
    return base64.b64encode(value).decode("ascii")


def _decode_bytes(value: str | None) -> bytes | None:
    if not value:
        return None
    return base64.b64decode(value.encode("ascii"))


def create_draft(snapshot: dict[str, Any]) -> str:
    draft_id = str(uuid.uuid4())
    registry = _load_registry()
    registry[draft_id] = {
        "draft_id": draft_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "bound_user_id": None,
        "bound_email": None,
        "snapshot": {
            **snapshot,
            "pdf_data_bytes_b64": _encode_bytes(snapshot.get("pdf_data_bytes")),
        },
    }
    if "pdf_data_bytes" in registry[draft_id]["snapshot"]:
        del registry[draft_id]["snapshot"]["pdf_data_bytes"]
    _save_registry(registry)
    return draft_id


def get_draft(draft_id: str) -> dict | None:
    row = _load_registry().get(draft_id)
    if not row:
        return None
    snap = dict(row.get("snapshot") or {})
    snap["pdf_data_bytes"] = _decode_bytes(snap.pop("pdf_data_bytes_b64", None))
    return {
        "draft_id": row["draft_id"],
        "bound_user_id": row.get("bound_user_id"),
        "bound_email": row.get("bound_email"),
        "snapshot": snap,
    }


def bind_draft_to_user(draft_id: str, user_id: str, email: str) -> bool:
    registry = _load_registry()
    row = registry.get(draft_id)
    if not row:
        return False
    row["bound_user_id"] = user_id
    row["bound_email"] = email.strip().lower()
    row["bound_at"] = datetime.now(timezone.utc).isoformat()
    _save_registry(registry)
    return True


def draft_snapshot_for_session() -> dict[str, Any]:
    """Collect the active guest workspace for Stripe checkout handoff."""
    from utils.user_session import us_get

    pdf_bytes = us_get("pdf_data_bytes")
    return {
        "intake": us_get("intake", {}),
        "step": us_get("step", 1),
        "report_markdown": us_get("report_markdown", ""),
        "pdf_data_bytes": pdf_bytes,
        "audit_complete": us_get("audit_complete", False),
        "risk_tier": us_get("risk_tier"),
        "risk_citation": us_get("risk_citation"),
        "audit_date": us_get("audit_date"),
    }
