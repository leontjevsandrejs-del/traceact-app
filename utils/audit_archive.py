"""
Certified report vault — lightweight archive with no tenant/billing imports.

Swap ``_AUDIT_VAULT`` for Supabase or object storage without pulling in the
full tenant database module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import uuid


@dataclass(frozen=True)
class PurchasedAudit:
    audit_id: str
    system_name: str
    generated_at: str
    pdf_bytes: bytes
    contact_email: str = ""
    user_id: str = ""


# In-memory mock vault (replace with Supabase / object storage)
_AUDIT_VAULT: dict[str, list[dict]] = {
    "demo_user": [
        {
            "audit_id": "demo-audit-001",
            "system_name": "HR Screening Assistant",
            "generated_at": "2026-07-01",
            "contact_email": "demo@traceact.eu",
            "user_id": "demo_user",
            "pdf_bytes": b"%PDF-1.4 demo placeholder",
        },
    ],
}


def get_purchased_audits(user_email: str, user_id: str = "") -> list[PurchasedAudit]:
    seen: set[str] = set()
    results: list[PurchasedAudit] = []

    def _collect(rows: list[dict]) -> None:
        for row in rows:
            aid = row["audit_id"]
            if aid in seen:
                continue
            seen.add(aid)
            results.append(PurchasedAudit(
                audit_id=aid,
                system_name=row["system_name"],
                generated_at=row["generated_at"],
                pdf_bytes=row["pdf_bytes"],
                contact_email=row.get("contact_email", ""),
                user_id=row.get("user_id", ""),
            ))

    if user_id:
        _collect(_AUDIT_VAULT.get(user_id, []))
    email_key = (user_email or "").strip().lower()
    if email_key:
        for rows in _AUDIT_VAULT.values():
            _collect([r for r in rows if r.get("contact_email", "").lower() == email_key])

    results.sort(key=lambda r: r.generated_at, reverse=True)
    return results


def archive_purchased_audit(
    user_id: str,
    contact_email: str,
    system_name: str,
    pdf_bytes: bytes,
    generated_at: str | None = None,
) -> PurchasedAudit:
    audit_id = str(uuid.uuid4())
    stamp = generated_at or date.today().isoformat()
    row = {
        "audit_id": audit_id,
        "system_name": system_name or "Unnamed AI System",
        "generated_at": stamp,
        "contact_email": contact_email,
        "user_id": user_id,
        "pdf_bytes": pdf_bytes,
    }
    _AUDIT_VAULT.setdefault(user_id, []).insert(0, row)
    return PurchasedAudit(
        audit_id=audit_id,
        system_name=row["system_name"],
        generated_at=stamp,
        pdf_bytes=pdf_bytes,
        contact_email=contact_email,
        user_id=user_id,
    )
