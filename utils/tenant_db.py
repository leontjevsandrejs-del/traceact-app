"""
Tenant / billing abstraction layer (mock implementation).

Swap the private ``_STORE`` backend for Supabase or PostgreSQL clients
without changing the UI contract. All lookups are keyed by the authenticated
username issued by streamlit-authenticator.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol
import uuid


@dataclass(frozen=True)
class CompanyProfile:
    user_id: str
    company_name: str
    audit_credits: int
    contact_email: str = ""


@dataclass(frozen=True)
class PurchasedAudit:
    audit_id: str
    system_name: str
    generated_at: str
    pdf_bytes: bytes
    contact_email: str = ""
    user_id: str = ""


class TenantDatabase(Protocol):
    def get_profile(self, user_id: str) -> CompanyProfile | None: ...
    def register_profile(
        self, user_id: str, company_name: str, contact_email: str = "",
        initial_credits: int = 0,
    ) -> CompanyProfile: ...
    def get_audit_credits(self, user_id: str) -> int: ...
    def deduct_audit_credit(self, user_id: str, amount: int = 1) -> bool: ...
    def add_audit_credits(self, user_id: str, amount: int) -> int: ...
    def get_purchased_audits(self, user_email: str, user_id: str = "") -> list[PurchasedAudit]: ...
    def archive_purchased_audit(
        self, user_id: str, contact_email: str, system_name: str,
        pdf_bytes: bytes, generated_at: str | None = None,
    ) -> PurchasedAudit: ...


# In-memory mock store (replace with Supabase / PostgreSQL)
_STORE: dict[str, dict] = {
    "demo_user": {
        "company_name": "Demo Compliance GmbH",
        "audit_credits": 3,
        "contact_email": "demo@traceact.eu",
    },
    "trial_zero": {
        "company_name": "Trial Organisation",
        "audit_credits": 0,
        "contact_email": "trial@traceact.eu",
    },
}

# Certified report vault (replace with Supabase / object storage)
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


class MockTenantDatabase:
    """Development backend — persists only for the server process lifetime."""

    def get_profile(self, user_id: str) -> CompanyProfile | None:
        row = _STORE.get(user_id)
        if not row:
            return None
        return CompanyProfile(
            user_id=user_id,
            company_name=row["company_name"],
            audit_credits=int(row["audit_credits"]),
            contact_email=row.get("contact_email", ""),
        )

    def register_profile(
        self,
        user_id: str,
        company_name: str,
        contact_email: str = "",
        initial_credits: int = 0,
    ) -> CompanyProfile:
        _STORE[user_id] = {
            "company_name": company_name or user_id,
            "audit_credits": max(0, initial_credits),
            "contact_email": contact_email,
        }
        return self.get_profile(user_id)  # type: ignore[return-value]

    def get_audit_credits(self, user_id: str) -> int:
        profile = self.get_profile(user_id)
        return profile.audit_credits if profile else 0

    def deduct_audit_credit(self, user_id: str, amount: int = 1) -> bool:
        row = _STORE.get(user_id)
        if not row or row["audit_credits"] < amount:
            return False
        row["audit_credits"] -= amount
        return True

    def add_audit_credits(self, user_id: str, amount: int) -> int:
        row = _STORE.setdefault(
            user_id,
            {"company_name": user_id, "audit_credits": 0, "contact_email": ""},
        )
        row["audit_credits"] = int(row.get("audit_credits", 0)) + max(0, amount)
        return row["audit_credits"]

    def get_purchased_audits(
        self, user_email: str, user_id: str = "",
    ) -> list[PurchasedAudit]:
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
        self,
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


_db: TenantDatabase = MockTenantDatabase()


def get_database() -> TenantDatabase:
    return _db


def get_company_profile(user_id: str) -> CompanyProfile | None:
    return get_database().get_profile(user_id)


def ensure_company_profile(user_id: str, contact_email: str = "") -> CompanyProfile:
    profile = get_company_profile(user_id)
    if profile:
        return profile
    return get_database().register_profile(
        user_id,
        company_name=user_id.replace("_", " ").title(),
        contact_email=contact_email,
        initial_credits=0,
    )


def get_audit_credits(user_id: str) -> int:
    return get_database().get_audit_credits(user_id)


def deduct_audit_credit(user_id: str, amount: int = 1) -> bool:
    return get_database().deduct_audit_credit(user_id, amount)


def add_audit_credits(user_id: str, amount: int) -> int:
    return get_database().add_audit_credits(user_id, amount)


def get_purchased_audits(user_email: str, user_id: str = "") -> list[PurchasedAudit]:
    return get_database().get_purchased_audits(user_email, user_id)


def archive_purchased_audit(
    user_id: str,
    contact_email: str,
    system_name: str,
    pdf_bytes: bytes,
    generated_at: str | None = None,
) -> PurchasedAudit:
    return get_database().archive_purchased_audit(
        user_id, contact_email, system_name, pdf_bytes, generated_at,
    )
