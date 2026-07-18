"""
High-risk sector triage for dynamic FRIA (Fundamental Rights Impact Assessment) intake.

Evaluates Step 1 industry selection and drives ``st.session_state.is_high_risk``.
"""

from __future__ import annotations

import streamlit as st

# Statutory Annex III domain triggers for mandatory FRIA intake.
EMPLOYMENT_INDUSTRY = "Employment & HR (hiring, evaluation)"
ESSENTIAL_SERVICES_LABEL = "Essential Private and Public Services"

# Existing catalogue entries mapped to Annex III, point 5 (essential services).
ESSENTIAL_SERVICES_INDUSTRIES = frozenset({
    "Banking & Credit Scoring",
    "Healthcare & Medical Devices",
    "Insurance (life & health risk assessment / pricing)",
})

FRIA_DATA_DEFAULTS: dict[str, str] = {
    "intended_purpose": "",
    "affected_persons": "",
    "rights_risks": "",
    "human_oversight": "",
}


def evaluate_high_risk_triage(industry: str | None) -> bool:
    """
    Return True when the selected sector requires the FRIA wizard step.

    Matches:
      - Employment (Annex III, point 4)
      - Essential private & public services (Annex III, point 5)
    """
    sector = (industry or "").strip()
    if not sector:
        return False
    if sector.startswith("Employment") or sector == EMPLOYMENT_INDUSTRY:
        return True
    if sector == ESSENTIAL_SERVICES_LABEL:
        return True
    if sector in ESSENTIAL_SERVICES_INDUSTRIES:
        return True
    return False


def ensure_triage_state() -> None:
    """Initialise triage session keys (safe to call on every app boot)."""
    st.session_state.setdefault("is_high_risk", False)
    if "fria_data" not in st.session_state or not isinstance(
        st.session_state.get("fria_data"), dict
    ):
        st.session_state.fria_data = dict(FRIA_DATA_DEFAULTS)


def apply_high_risk_triage(industry: str | None) -> bool:
    """Evaluate sector and persist ``is_high_risk`` on session state."""
    ensure_triage_state()
    is_high = evaluate_high_risk_triage(industry)
    st.session_state.is_high_risk = is_high
    if not is_high:
        st.session_state.fria_data = dict(FRIA_DATA_DEFAULTS)
    return is_high


def fria_step_active() -> bool:
    ensure_triage_state()
    return bool(st.session_state.get("is_high_risk"))


def evidence_step_number() -> int:
    return 5 if fria_step_active() else 4


def fria_step_number() -> int:
    return 4
