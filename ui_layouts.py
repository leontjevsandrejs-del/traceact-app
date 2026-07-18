"""
TraceAct layout module — core functional web views.

All user-facing labels and body markdown are pulled dynamically from
``st.session_state.content`` (loaded from content.json by the app.py router).
No marketing or legal copy is hardcoded in this file.

Exports:
    render_workspace_engine()  — intake wizard, multi-agent audit pipeline,
                                 compliance tracking sheets, PDF pack hooks.
    render_legal_hub()         — EU AI Act risk tier reference.
"""

import pandas as pd
import streamlit as st
from datetime import date, timedelta
import pypdf

from utils.gemini_client import (
    call_gemini_with_retry,
    get_gemini_client,
)
from utils.thinking_ui import thinking_mode

from utils.risk_engine import (
    classify_risk,
    INDUSTRY_OPTIONS,
    BIOMETRIC_OPTIONS,
    POLICING_OPTIONS,
    SOCIAL_SCORING_OPTIONS,
    DATA_SOURCE_OPTIONS,
    AUDIENCE_OPTIONS,
    OVERSIGHT_OPTIONS,
    ROLE_OPTIONS,
    ANNEX_I_OPTIONS,
    FUNCTION_OPTIONS,
)
from utils.annex_iv import (
    scan_documentation,
    findings_summary_block,
    build_clarification_matrix,
    clarification_block,
)
from utils.knowledge import load_legal_knowledge_base, knowledge_base_inventory
from utils.report_gen import generate_pdf_report
from utils.user_session import us_get, us_set, us_pop, us_contains, current_user_id, current_user_email
from utils.tenant_db import archive_purchased_audit
from utils.auth_session import get_auth_user_id, is_logged_in
from utils.supabase_db import persist_member_audit
from utils.billing_ui import (
    WORKSPACE_TAB_KEY,
    consume_auto_run_assessment,
    ensure_description_widget_state,
    is_pdf_export_unlocked,
    render_pdf_export_action,
    sync_credit_count,
    sync_description_to_intake,
    DESCRIPTION_WIDGET_KEY,
)
from utils.draft_store import persist_session_draft
from utils.fria_triage import (
    FRIA_DATA_DEFAULTS,
    apply_high_risk_triage,
    evidence_step_number,
    fria_step_active,
    fria_step_number,
)

INTAKE_CONTENT_KEY = "intake_content"
UPLOADED_FILE_TEXT_KEY = "uploaded_file_text"


def _extract_uploaded_file_text(uploaded_file) -> str:
    """Extract plain text from a Step 4 TXT or PDF upload."""
    if uploaded_file is None:
        return ""
    try:
        uploaded_file.seek(0)
        if uploaded_file.name.lower().endswith(".pdf"):
            reader = pypdf.PdfReader(uploaded_file)
            return "\n".join(
                (page.extract_text() or "") for page in reader.pages
            ).strip()
        uploaded_file.seek(0)
        return uploaded_file.read().decode("utf-8", errors="replace").strip()
    except Exception:
        return ""


def compile_intake_content(pasted_notes: str, file_text: str) -> str:
    """Merge pasted notes and uploaded file text into one evidence payload."""
    pasted_notes = (pasted_notes or "").strip()
    file_text = (file_text or "").strip()
    sections: list[str] = []
    if pasted_notes:
        sections.append(f"=== Pasted Notes ===\n{pasted_notes}")
    if file_text:
        sections.append(f"=== Uploaded File Content ===\n{file_text}")
    return "\n\n".join(sections).strip()


def refresh_intake_content(intake: dict, uploaded_file=None) -> str:
    """Compile Step 4 inputs into ``st.session_state['intake_content']``."""
    pasted = (
        st.session_state.get(DESCRIPTION_WIDGET_KEY, "")
        or intake.get("description", "")
        or st.session_state.get("pasted_notes", "")
    ).strip()
    file_text = ""

    if uploaded_file is not None:
        extracted = _extract_uploaded_file_text(uploaded_file)
        if extracted:
            file_text = extracted
            st.session_state[UPLOADED_FILE_TEXT_KEY] = file_text
    else:
        file_text = (
            st.session_state.get(UPLOADED_FILE_TEXT_KEY, "")
            or intake.get("evidence_text", "")
        ).strip()

    content = compile_intake_content(pasted, file_text)
    st.session_state[INTAKE_CONTENT_KEY] = content
    st.session_state["pasted_notes"] = pasted
    intake["intake_content"] = content
    intake["description"] = pasted
    intake["evidence_text"] = file_text
    us_set("intake", intake)
    persist_session_draft()
    return content


def restore_pasted_notes_widget(intake: dict) -> None:
    """Restore the Step 4 text area from persisted intake when remounting."""
    saved = (intake.get("description") or st.session_state.get("pasted_notes", "")).strip()
    current = st.session_state.get(DESCRIPTION_WIDGET_KEY, "")
    if saved and not (current or "").strip():
        st.session_state[DESCRIPTION_WIDGET_KEY] = saved
    elif DESCRIPTION_WIDGET_KEY not in st.session_state:
        st.session_state[DESCRIPTION_WIDGET_KEY] = saved


def _on_pasted_notes_changed() -> None:
    """Persist text-area edits immediately (survives workspace tab switches)."""
    intake = us_get("intake", {})
    st.session_state["pasted_notes"] = st.session_state.get(DESCRIPTION_WIDGET_KEY, "")
    refresh_intake_content(intake)


def get_active_intake_content(intake: dict) -> str:
    """Return compiled intake evidence, rebuilding from all persisted sources."""
    content = refresh_intake_content(intake).strip()
    if content:
        return content
    content = (intake.get("intake_content") or st.session_state.get(INTAKE_CONTENT_KEY, "")).strip()
    if content:
        return content
    pasted = (intake.get("description") or st.session_state.get("pasted_notes", "")).strip()
    file_text = (
        intake.get("evidence_text", "")
        or st.session_state.get(UPLOADED_FILE_TEXT_KEY, "")
    ).strip()
    return compile_intake_content(pasted, file_text)

ARTICLE_50_GUARDRAIL = """---
ARTICLE 50 TEXT-GENERATION ANALYSIS RULE:
When evaluating an AI system that generates text content under Article 50:
1. Distinguish between 'Providers' (who build the model and carry the machine-readable marking duty of Article 50(2)) and 'Deployers' (who use the model to generate text, governed by Article 50(4)).
2. Under Article 50(4), second subparagraph, a Deployer's duty to disclose that text is AI-generated applies to text published to inform the public on matters of public interest, and that duty does not apply where the AI-generated content has undergone human review or editorial control with a natural or legal person holding editorial responsibility.
3. Apply the exemption ONLY when the intake explicitly evidences the human editorial-control workflow; state the evidence you relied on and cite Article 50(4) in your finding. If the evidence is absent or ambiguous, do not assume the exemption — route the question to the Clarification Request Matrix instead.
---"""

CITATION_PROTOCOL = """---
ZERO-MISTAKE CITATION PROTOCOL (binding on every statement you output):
1. Every compliance classification, legal assertion, or breach finding MUST carry an explicit statutory anchor: Article, paragraph, Recital, or Annex point of Regulation (EU) 2024/1689 — e.g. [Article 10(3)], [Annex III, point 4], [Recital 61].
2. Where an Annex document has been supplied in the OFFICIAL REGULATORY REFERENCE DOCUMENTS block, cite the source document name as well: [source: Annex IV - Technical Documentation].
3. If you cannot anchor a statement to a specific provision, you MUST NOT make the statement. Write instead: "INSUFFICIENT EVIDENCE — routed to Clarification Request Matrix."
4. Never invent Article numbers, paragraph numbers, or Annex points. Never paraphrase a provision as a quotation. Never assert that documentation contains something the ANNEX IV DOCUMENTATION SCAN marks as MISSING or SHALLOW.
5. The deterministic classification tier and decision pathway supplied to you are authoritative. You must not contradict, upgrade, or downgrade the tier. Your role is analysis within the tier, not re-classification.
---"""


def _c(*keys, default=""):
    """Safely traverse st.session_state.content with dotted key paths."""
    node = st.session_state.get("content", {})
    for key in keys:
        if isinstance(node, dict) and key in node:
            node = node[key]
        else:
            return default
    return node


# ══════════════════════════════════════════════════════════════════════════════
# Sector-specific mitigation mandates (kept in sync with utils.risk_engine)
# ══════════════════════════════════════════════════════════════════════════════

SECTOR_MITIGATIONS = {
    "Employment & HR (hiring, evaluation)": (
        "Annex III §4 employment systems: implement bias audits on protected "
        "characteristics, candidate notification duties, and human review of "
        "all adverse hiring or evaluation decisions."
    ),
    "Banking & Credit Scoring": (
        "Annex III §5(b) creditworthiness systems: establish explainability "
        "documentation for every score, adverse-action notices, and periodic "
        "fairness back-testing against protected groups."
    ),
    "Critical Infrastructure (water, gas, electricity, digital networks)": (
        "Annex III §2 safety components: enforce fail-safe manual fallback "
        "modes, redundancy testing, and incident reporting to national "
        "competent authorities within statutory windows."
    ),
    "Education & Vocational Training": (
        "Annex III §3 education systems: guarantee appeal channels for "
        "automated scoring, proctoring transparency notices, and strict "
        "limits on emotion-inference features (Article 5 exposure)."
    ),
    "Healthcare & Medical Devices": (
        "Coordinate EU AI Act conformity with MDR/IVDR device classification; "
        "clinical validation evidence, post-market surveillance, and human "
        "clinician sign-off on diagnostic or triage outputs are mandatory."
    ),
    "Insurance (life & health risk assessment / pricing)": (
        "Annex III §5(c) insurance systems: document actuarial fairness "
        "testing, explainability for adverse pricing decisions, and human "
        "review of declined-coverage outcomes."
    ),
    "Law Enforcement": (
        "Annex III §6 law-enforcement systems: most use cases require prior "
        "judicial authorisation, strict necessity tests, and Article 5 "
        "prohibitions on real-time remote biometric ID apply in public spaces."
    ),
    "Migration, Asylum & Border Control": (
        "Annex III §7 migration systems: strict necessity and proportionality "
        "documentation, individual assessment safeguards, and prohibition of "
        "risk-assessment tools based solely on profiling."
    ),
    "Administration of Justice & Democratic Processes": (
        "Annex III §8 justice systems: judicial-assistance tools must preserve "
        "the decision-making autonomy of the judiciary; document that outputs "
        "are advisory research aids, never determinative rulings."
    ),
    "General Purpose AI / LLM Development": (
        "Chapter V GPAI obligations: technical documentation, training-data "
        "summaries, copyright policy compliance, and — above systemic-risk "
        "compute thresholds — adversarial testing and incident reporting."
    ),
    "Other / General Business Operations": (
        "Maintain an AI inventory register, transparency notices where users "
        "interact with AI (Article 50), and voluntary codes of conduct."
    ),
}


def build_obligations_register(intake: dict, tier: str) -> "pd.DataFrame":
    """Pre-populate the interactive obligations sheet from the intake profile."""
    rows = [
        ("Human Oversight Controls", "Art. 26(2) / Art. 14",
         "Assign trained natural persons with authority and competence to "
         "oversee the system and override or interrupt any decision."),
        ("Data Quality & Input Logs", "Art. 26(4) / Art. 10",
         "Ensure input data is relevant and sufficiently representative; "
         "maintain data-quality logs for the system's intended purpose."),
        ("Automatic Event Logging", "Art. 26(6) / Art. 12",
         "Retain automatically generated system logs for at least six months, "
         "under access control and tamper protection."),
        ("Model Drift Monitoring", "Art. 26(5) / Art. 72",
         "Operate continuous post-market monitoring for accuracy degradation, "
         "drift, and emerging risks; act on anomalies without delay."),
        ("Worker / Affected-Person Notification", "Art. 26(7)",
         "Inform affected workers and their representatives before putting a "
         "workplace high-risk AI system into service."),
        ("Serious Incident Reporting", "Art. 26(5) / Art. 73",
         "Report serious incidents to the provider, importer/distributor, and "
         "market surveillance authority within statutory windows."),
        ("Instruction-for-Use Conformance", "Art. 26(1)",
         "Use the system strictly in accordance with the provider's "
         "instructions for use; document any deviation."),
        ("Registration Verification", "Art. 26(8) / Art. 49",
         "Verify the system is registered in the EU database before "
         "deployment (public-authority deployers must self-register)."),
    ]

    industry = intake.get("industry", "")
    if "PROHIBITED" in tier:
        rows.insert(0, ("Immediate Decommission Plan", "Art. 5",
                        "The classified practice is banned outright — draft a "
                        "wind-down and substitution plan with legal counsel."))
    if industry == "Employment & HR (hiring, evaluation)":
        rows.append(("Candidate Transparency Notices", "Art. 26(7) / Annex III §4",
                     "Notify candidates and employees that an AI system is used "
                     "in evaluation or hiring decisions."))
    if industry == "Banking & Credit Scoring":
        rows.append(("Creditworthiness FRIA", "Art. 27",
                     "Complete a Fundamental Rights Impact Assessment before "
                     "first use of the credit-scoring system."))
    if industry == "General Purpose AI / LLM Development":
        rows.append(("GPAI Technical Documentation", "Arts. 53-55",
                     "Maintain model documentation, training-data summaries, "
                     "and copyright-compliance policy; test for systemic risk."))
    if "biometric" in intake.get("biometric", "").lower() and \
            intake.get("biometric", "").lower().startswith("yes"):
        rows.append(("Biometric Data Safeguards", "Art. 10(5) / GDPR Art. 9",
                     "Apply special-category safeguards to all biometric "
                     "processing pipelines and document lawful basis."))

    return pd.DataFrame(
        [{"Obligation": r[0], "Legal Basis": r[1], "Description": r[2],
          "Status": "Action Required", "Notes": ""} for r in rows]
    )


def build_regulatory_calendar(audit_dt: date, intake: dict, tier: str):
    """Compute profile-driven regulatory deadlines. Returns sorted event tuples."""
    events = [
        (audit_dt + timedelta(days=365), "Annual FRIA Refresh",
         "Article 27",
         "Mandatory yearly re-validation of the Fundamental Rights Impact "
         "Assessment against the deployed system's current behaviour."),
        (audit_dt + timedelta(days=180), "Log Retention Sweep",
         "Article 12 / 26(6)",
         "Verify the six-month automatic log archive is complete, "
         "access-controlled, and export-ready for market surveillance."),
        (audit_dt + timedelta(days=90), "Incident Reporting Test Window",
         "Article 73",
         "Quarterly dry-run of the serious-incident escalation chain — "
         "confirm the 15-day authority notification path executes cleanly."),
        (audit_dt + timedelta(days=30), "Human Oversight Attestation",
         "Article 26(2)",
         "Thirty-day check-in: confirm assigned overseers completed training "
         "and exercised at least one supervised override drill."),
    ]

    industry = intake.get("industry", "")
    if "HIGH-RISK" in tier:
        events.append(
            (audit_dt + timedelta(days=270), "Conformity Re-Assessment Gate",
             "Article 43",
             "Review whether any substantial modification occurred that "
             "re-triggers the conformity assessment procedure."))
    if industry == "General Purpose AI / LLM Development":
        events.append(
            (audit_dt + timedelta(days=120), "GPAI Documentation Refresh",
             "Articles 53-55",
             "Update model cards, training-data summaries, and systemic-risk "
             "evaluations for the current model generation."))
    if "Fully autonomous" in intake.get("oversight", ""):
        events.append(
            (audit_dt + timedelta(days=45), "Autonomy Guardrail Review",
             "Article 14",
             "Priority review: the system currently runs fully autonomously — "
             "validate the interim human-override implementation plan."))

    return sorted(events, key=lambda e: e[0])


# ══════════════════════════════════════════════════════════════════════════════
# Shared layout fragments
# ══════════════════════════════════════════════════════════════════════════════

def _section_header(label: str, title: str, sub: str) -> None:
    st.markdown(f"""
    <div style="padding:1.25rem 0 0.25rem;">
      <div class="section-label">{label}</div>
      <div class="section-title">{title}</div>
      <div class="section-sub">{sub}</div>
    </div>
    <hr class="section-divider">
    """, unsafe_allow_html=True)


def _wizard_step_labels(high_risk: bool) -> list[str]:
    labels = list(_c(
        "workspace", "wizard", "step_labels",
        default=["Sector Profile", "Data Footprint", "Deployment & Oversight", "Evidence & Review"],
    ))
    if high_risk:
        if len(labels) >= 4:
            return labels[:3] + ["FRIA Assessment"] + [labels[3]]
        return labels[:3] + ["FRIA Assessment", "Evidence & Review"]
    return labels[:4]


def _wizard_step_header(current: int, high_risk: bool | None = None) -> str:
    if high_risk is None:
        high_risk = fria_step_active()
    labels = _wizard_step_labels(high_risk)
    cells = []
    for i, label in enumerate(labels, start=1):
        if i < current:
            dot = "background:#059669;color:#fff;"
        elif i == current:
            dot = "background:#2563EB;color:#fff;"
        else:
            dot = "background:#E2E8F0;color:#64748B;"
        cells.append(
            f'<div style="display:flex;align-items:center;gap:8px;">'
            f'<div style="width:26px;height:26px;border-radius:50%;{dot}'
            f'display:flex;align-items:center;justify-content:center;'
            f'font-size:0.75rem;font-weight:700;">{i}</div>'
            f'<span style="font-size:0.78rem;font-weight:{600 if i == current else 400};'
            f'color:{"#0F172A" if i == current else "#94A3B8"};">{label}</span></div>'
        )
    joined = '<div style="flex:1;height:1px;background:#E2E8F0;margin:0 10px;"></div>'.join(cells)
    return f'<div style="display:flex;align-items:center;margin:0.5rem 0 1.5rem;">{joined}</div>'


def _question(label: str, hint: str, spaced: bool = False) -> None:
    style = ' style="margin-top:1rem;display:block;"' if spaced else ""
    st.markdown(
        f'<span class="question-label"{style}>{label}</span>'
        f'<div class="question-hint">{hint}</div>',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# VIEW 1 — Compliance Workspace Engine
# ══════════════════════════════════════════════════════════════════════════════

def render_workspace_engine():
    """Multi-agent questionnaire wizard, compliance tracking, and PDF hooks."""
    ws = _c("workspace", default={})
    tab_labels = list(_c("workspace", "tabs", default=[
        "AI System Intake",
        "Evidence Upload",
        "Conformity Assessment",
    ]))
    conformity_tab = tab_labels[2] if len(tab_labels) > 2 else "Conformity Assessment"

    if WORKSPACE_TAB_KEY not in st.session_state:
        st.session_state[WORKSPACE_TAB_KEY] = tab_labels[0]

    st.markdown(
        '<div class="workspace-tab-bar-label">Workspace Navigation</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div id="traceact-workspace-nav" style="display:none;"></div>',
        unsafe_allow_html=True,
    )
    nav_cols = st.columns(len(tab_labels), gap="small")
    for label, col in zip(tab_labels, nav_cols):
        with col:
            is_active = st.session_state[WORKSPACE_TAB_KEY] == label
            if st.button(
                label,
                key=f"traceact_ws_tab_{label.replace(' ', '_')}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                st.session_state[WORKSPACE_TAB_KEY] = label
                st.rerun()

    st.markdown('<div class="workspace-tab-bar-rule"></div>', unsafe_allow_html=True)
    active_tab = st.session_state[WORKSPACE_TAB_KEY]

    if active_tab == tab_labels[0]:
        _render_intake_wizard(ws.get("wizard", {}))
    elif active_tab == tab_labels[1]:
        _render_evidence_vault(ws.get("evidence", {}))
    elif active_tab == conformity_tab:
        _render_conformity_assessment(ws.get("assessment", {}),
                                      ws.get("command_center", {}))


def _process_step4_upload(wizard_file, intake: dict, s4: dict) -> None:
    if wizard_file is None:
        return
    extracted = _extract_uploaded_file_text(wizard_file)
    if extracted:
        st.session_state[UPLOADED_FILE_TEXT_KEY] = extracted
        st.success(s4.get("upload_success", "Document cached."))
    else:
        st.session_state.pop(UPLOADED_FILE_TEXT_KEY, None)
        st.error(s4.get("upload_error", "Could not extract text."))
    refresh_intake_content(intake, wizard_file=None)


def _render_step4_intake_workspace(
    s4: dict, intake: dict, wz: dict, *, back_step: int = 3,
) -> None:
    st.markdown(f"""
    <div class="section-label" style="margin-bottom:0.6rem;">{s4.get("label", "")}</div>
    <div class="section-sub">{s4.get("sub", "")}</div>
    """, unsafe_allow_html=True)

    ensure_description_widget_state(intake.get("description", ""))
    restore_pasted_notes_widget(intake)

    st.info(
        "Quick Tip: To get an accurate compliance roadmap, clearly outline your human "
        "verification gates. Avoid phrases like 'fully autonomous decision making' if a "
        "human supervisor signs off on the final text outputs."
    )

    col_upload, col_paste = st.columns([1, 1], gap="large")

    with col_upload:
        wizard_file = st.file_uploader(
            s4.get("upload_label", "Drop a file (TXT or PDF)"),
            type=["txt", "pdf"],
            key="wizard_uploader",
            help=s4.get("upload_help", ""),
        )
        _process_step4_upload(wizard_file, intake, s4)

    with col_paste:
        st.text_area(
            s4.get("paste_label", "Or paste a product description / notes here"),
            height=200,
            placeholder=s4.get("paste_placeholder", ""),
            help=(
                "Define whether the tool is a human-verified suggestion or text "
                "optimization aid. Human-in-the-loop workflows default safely to "
                "Minimal Risk under the Act."
            ),
            key=DESCRIPTION_WIDGET_KEY,
            on_change=_on_pasted_notes_changed,
        )

    refresh_intake_content(intake)

    preview = classify_risk(intake)
    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
    st.markdown(
        f'<div class="section-label" style="margin-bottom:0.6rem;">{s4.get("summary_label", "")}</div>',
        unsafe_allow_html=True,
    )

    sum_col1, sum_col2 = st.columns([1, 1], gap="large")
    with sum_col1:
        st.markdown(
            f"**Industry Sector:** {intake.get('industry', '—')}  \n"
            f"**Value-Chain Role:** {intake.get('role', '—')}  \n"
            f"**Biometric Footprint:** {intake.get('biometric', '—')}  \n"
            f"**Profiling / Policing:** {intake.get('policing', '—')}"
        )
    with sum_col2:
        st.markdown(
            f"**Training Data Source:** {intake.get('data_source', '—')}  \n"
            f"**Operational Scope:** {intake.get('audience', '—')}  \n"
            f"**Human Oversight:** {intake.get('oversight', '—')}"
        )

    st.metric(label=s4.get("preview_metric", "Preliminary Risk Tier"), value=preview.tier)
    st.markdown(f"**Primary Citation:** {preview.citation}")

    with st.expander(s4.get("pathway_label", "View the statutory decision pathway")):
        for step_line in preview.decision_path:
            st.markdown(f"- {step_line}")

    col_back, col_done = st.columns([1, 5])
    with col_back:
        if st.button(s4.get("back_button", "← Back")):
            us_set("step", back_step)
            st.rerun()
    with col_done:
        if st.button(s4.get("confirm_button", "✓ Confirm Intake"), type="primary"):
            intake["confirmed"] = True
            refresh_intake_content(intake)
            st.success(s4.get("confirm_success", "Intake locked."))


def _render_fria_step(s3a: dict, intake: dict) -> None:
    """Step 3A — mandatory FRIA questionnaire for high-risk sector triage."""
    st.markdown(f"""
    <div class="section-label" style="margin-bottom:0.6rem;">{s3a.get("label", "Step 3A — Fundamental Rights Impact Assessment (FRIA)")}</div>
    <div class="section-sub">{s3a.get("sub", "")}</div>
    """, unsafe_allow_html=True)

    fria = dict(st.session_state.get("fria_data") or FRIA_DATA_DEFAULTS)
    field_keys = {
        "intended_purpose": "fria_intended_purpose",
        "affected_persons": "fria_affected_persons",
        "rights_risks": "fria_rights_risks",
        "human_oversight": "fria_human_oversight",
    }
    for field, widget_key in field_keys.items():
        if widget_key not in st.session_state:
            st.session_state[widget_key] = fria.get(field, "")

    _question(
        s3a.get("q_intended_purpose", "Intended purpose and deployment context"),
        s3a.get("hint_intended_purpose", ""),
    )
    st.text_area(
        "Intended purpose and deployment context",
        height=120,
        key="fria_intended_purpose",
        label_visibility="collapsed",
    )

    _question(
        s3a.get("q_affected_persons", "Specific categories of natural persons affected"),
        s3a.get("hint_affected_persons", ""),
        spaced=True,
    )
    st.text_area(
        "Affected persons",
        height=100,
        key="fria_affected_persons",
        label_visibility="collapsed",
    )

    _question(
        s3a.get("q_rights_risks", "Environmental or human rights risks identified"),
        s3a.get("hint_rights_risks", ""),
        spaced=True,
    )
    st.text_area(
        "Rights and environmental risks",
        height=100,
        key="fria_rights_risks",
        label_visibility="collapsed",
    )

    _question(
        s3a.get("q_human_oversight", "Human oversight protocols established"),
        s3a.get("hint_human_oversight", ""),
        spaced=True,
    )
    st.text_area(
        "Human oversight protocols",
        height=100,
        key="fria_human_oversight",
        label_visibility="collapsed",
    )

    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
    col_back, col_next = st.columns([1, 5])
    with col_back:
        if st.button(s3a.get("back_button", "← Back"), key="fria_back_btn"):
            us_set("step", 3)
            st.rerun()
    with col_next:
        if st.button(
            s3a.get("next_button", "Continue to Evidence & Review →"),
            type="primary",
            key="fria_continue_btn",
        ):
            payload = {
                "intended_purpose": str(st.session_state.get("fria_intended_purpose", "")).strip(),
                "affected_persons": str(st.session_state.get("fria_affected_persons", "")).strip(),
                "rights_risks": str(st.session_state.get("fria_rights_risks", "")).strip(),
                "human_oversight": str(st.session_state.get("fria_human_oversight", "")).strip(),
            }
            if not all(payload.values()):
                st.warning("Please complete every FRIA field before continuing.")
            else:
                st.session_state.fria_data = payload
                intake["fria_data"] = payload
                us_set("intake", intake)
                us_set("step", evidence_step_number())
                st.rerun()


def _render_intake_wizard(wz: dict):
    _section_header(wz.get("label", ""), wz.get("title", ""), wz.get("sub", ""))

    st.markdown('<span id="traceact-wizard-anchor" style="display:none;"></span>', unsafe_allow_html=True)

    if not us_contains("step"):
        us_set("step", 1)
    if not us_contains("intake"):
        us_set("intake", {})

    intake = us_get("intake", {})
    step = us_get("step", 1)

    if intake.get("industry"):
        apply_high_risk_triage(intake.get("industry"))

    high_risk = fria_step_active()
    display_step = step
    if high_risk and step >= evidence_step_number():
        display_step = step
    elif not high_risk and step > 4:
        us_set("step", 4)
        step = 4
        display_step = 4

    st.markdown(_wizard_step_header(display_step, high_risk), unsafe_allow_html=True)

    def _saved_index(options, key):
        saved = intake.get(key)
        if not saved or saved not in options:
            return None
        return options.index(saved)

    def _require_selections(**fields) -> bool:
        if any(value is None for value in fields.values()):
            st.warning("Please answer every question before continuing.")
            return False
        return True

    # ── STEP 1: Company & Industry Sector Profile ────────────────────────────
    if step == 1:
        s1 = wz.get("step1", {})
        st.markdown(
            f'<div class="section-label" style="margin-bottom:0.6rem;">{s1.get("label", "")}</div>',
            unsafe_allow_html=True,
        )
        _question(s1.get("question", ""), s1.get("hint", ""))

        sel_industry = st.selectbox(
            "Industry sector",
            options=INDUSTRY_OPTIONS,
            index=_saved_index(INDUSTRY_OPTIONS, "industry"),
            placeholder="Select industry sector…",
            label_visibility="collapsed",
        )

        col_org1, col_org2 = st.columns([1, 1], gap="large")
        with col_org1:
            sel_company = st.text_input(
                s1.get("company_label", "Company name"),
                value=intake.get("company", ""),
                placeholder=s1.get("company_placeholder", ""),
            )
        with col_org2:
            sel_role = st.selectbox(
                s1.get("role_label", "Value-chain role"),
                options=ROLE_OPTIONS,
                index=_saved_index(ROLE_OPTIONS, "role"),
                placeholder="Select value-chain role…",
            )

        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
        if st.button(s1.get("next_button", "Continue →"), type="primary"):
            if not _require_selections(industry=sel_industry, role=sel_role):
                pass
            else:
                intake["industry"] = sel_industry
                intake["company"] = sel_company.strip()
                intake["role"] = sel_role
                apply_high_risk_triage(sel_industry)
                us_set("intake", intake)
                us_set("step", 2)
                st.rerun()

    # ── STEP 2: Algorithmic Data & Biometric Footprint ───────────────────────
    elif step == 2:
        s2 = wz.get("step2", {})
        st.markdown(
            f'<div class="section-label" style="margin-bottom:0.6rem;">{s2.get("label", "")}</div>',
            unsafe_allow_html=True,
        )

        _question(s2.get("q_biometric", ""), s2.get("hint_biometric", ""))
        sel_biometric = st.radio(
            "Biometric processing", BIOMETRIC_OPTIONS,
            index=_saved_index(BIOMETRIC_OPTIONS, "biometric"),
            label_visibility="collapsed",
        )

        _question(s2.get("q_policing", ""), s2.get("hint_policing", ""), spaced=True)
        sel_policing = st.radio(
            "Profiling datasets", POLICING_OPTIONS,
            index=_saved_index(POLICING_OPTIONS, "policing"),
            label_visibility="collapsed",
        )

        _question(s2.get("q_social", "Does the system score or rank people's general behaviour?"),
                  s2.get("hint_social", "Social scoring with cross-context detriment is prohibited under Article 5(1)(c)."),
                  spaced=True)
        sel_social = st.radio(
            "Social scoring", SOCIAL_SCORING_OPTIONS,
            index=_saved_index(SOCIAL_SCORING_OPTIONS, "social_scoring"),
            label_visibility="collapsed",
        )

        _question(s2.get("q_data_source", ""), s2.get("hint_data_source", ""), spaced=True)
        sel_data_source = st.radio(
            "Training data source", DATA_SOURCE_OPTIONS,
            index=_saved_index(DATA_SOURCE_OPTIONS, "data_source"),
            label_visibility="collapsed",
        )

        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
        col_back, col_next = st.columns([1, 5])
        with col_back:
            if st.button(wz.get("step4", {}).get("back_button", "← Back")):
                us_set("step", 1)
                st.rerun()
        with col_next:
            if st.button(s2.get("next_button", "Continue →"), type="primary"):
                if not _require_selections(
                    biometric=sel_biometric,
                    policing=sel_policing,
                    social_scoring=sel_social,
                    data_source=sel_data_source,
                ):
                    pass
                else:
                    intake["biometric"] = sel_biometric
                    intake["policing"] = sel_policing
                    intake["social_scoring"] = sel_social
                    intake["data_source"] = sel_data_source
                    us_set("intake", intake)
                    us_set("step", 3)
                    st.rerun()

    # ── STEP 3: System Deployment & Human Oversight ──────────────────────────
    elif step == 3:
        s3 = wz.get("step3", {})
        st.markdown(
            f'<div class="section-label" style="margin-bottom:0.6rem;">{s3.get("label", "")}</div>',
            unsafe_allow_html=True,
        )

        _question(s3.get("q_audience", ""), s3.get("hint_audience", ""))
        sel_audience = st.radio(
            "Operational scope", AUDIENCE_OPTIONS,
            index=_saved_index(AUDIENCE_OPTIONS, "audience"),
            label_visibility="collapsed",
        )

        _question(s3.get("q_oversight", ""), s3.get("hint_oversight", ""), spaced=True)
        sel_oversight = st.radio(
            "Human oversight", OVERSIGHT_OPTIONS,
            index=_saved_index(OVERSIGHT_OPTIONS, "oversight"),
            label_visibility="collapsed",
        )

        _question(
            s3.get("q_annex1", "Is the AI a safety component of — or itself — a product under EU harmonised legislation?"),
            s3.get("hint_annex1", "Machinery, medical devices, vehicles, toys, lifts, radio equipment... A 'Yes' triggers high-risk status via Article 6(1) and Annex I."),
            spaced=True)
        sel_annex1 = st.radio(
            "Annex I product-safety link", ANNEX_I_OPTIONS,
            index=_saved_index(ANNEX_I_OPTIONS, "annex1"),
            label_visibility="collapsed",
        )

        _question(
            s3.get("q_function", "What functional role does the system play in decisions about people?"),
            s3.get("hint_function", "Article 6(3) exempts narrow procedural, preparatory, or pattern-flagging tasks from high-risk status — unless the system performs profiling, which defeats the exemption."),
            spaced=True)
        sel_function = st.radio(
            "Functional role", FUNCTION_OPTIONS,
            index=_saved_index(FUNCTION_OPTIONS, "function"),
            label_visibility="collapsed",
        )

        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
        col_back, col_next = st.columns([1, 5])
        with col_back:
            if st.button(wz.get("step4", {}).get("back_button", "← Back")):
                us_set("step", 2)
                st.rerun()
        with col_next:
            if st.button(
                s3.get(
                    "next_button_fria" if fria_step_active() else "next_button",
                    "Continue →",
                ),
                type="primary",
            ):
                if not _require_selections(
                    audience=sel_audience,
                    oversight=sel_oversight,
                    annex1=sel_annex1,
                    function=sel_function,
                ):
                    pass
                else:
                    intake["audience"] = sel_audience
                    intake["oversight"] = sel_oversight
                    intake["annex1"] = sel_annex1
                    intake["function"] = sel_function
                    us_set("intake", intake)
                    us_set("step", fria_step_number() if fria_step_active() else evidence_step_number())
                    st.rerun()

    # ── STEP 3A: FRIA (high-risk sectors only) ───────────────────────────────
    elif step == fria_step_number() and fria_step_active():
        _render_fria_step(wz.get("step3a", {}), intake)

    # ── STEP 4 / 5: Evidence Upload & Intake Review ──────────────────────────
    elif step == evidence_step_number():
        back_step = fria_step_number() if fria_step_active() else 3
        _render_step4_intake_workspace(
            wz.get("step4", {}), intake, wz, back_step=back_step,
        )

    elif step > evidence_step_number():
        us_set("step", evidence_step_number())
        st.rerun()

    else:
        us_set("step", 1)
        st.rerun()


def _render_evidence_vault(ev: dict):
    _section_header(ev.get("label", ""), ev.get("title", ""), ev.get("sub", ""))
    extra_file = st.file_uploader(
        ev.get("upload_label", "Upload additional documentation (TXT / PDF)"),
        type=["txt", "pdf"],
        key="tab2_uploader",
    )
    if extra_file:
        st.success(ev.get("upload_success", "Document cached."))


def _render_conformity_assessment(assess: dict, cc: dict):
    _section_header(assess.get("label", ""), assess.get("title", ""),
                    assess.get("sub", ""))

    if not us_contains("audit_complete"):
        us_set("audit_complete", False)
    if not us_contains("report_markdown"):
        us_set("report_markdown", "")
    if not us_contains("pdf_data_bytes"):
        us_set("pdf_data_bytes", None)

    sync_credit_count()
    audit_complete = us_get("audit_complete")

    intake = us_get("intake", {})
    save_label = cc.get("save_button", "Download Certified PDF Report")
    refresh_intake_content(intake)

    def _try_run_audit() -> None:
        intake_content = get_active_intake_content(intake).strip()
        st.session_state[INTAKE_CONTENT_KEY] = intake_content
        intake["intake_content"] = intake_content
        us_set("intake", intake)
        if not intake_content:
            st.warning(
                "⚠️ Please upload a file or paste a product description to run the audit."
            )
            return
        client = get_gemini_client()
        if client is None:
            st.error(assess.get("missing_key_error", "Missing GEMINI_API_KEY."))
            return
        if not intake.get("industry"):
            st.error(assess.get("missing_intake_error", "Complete the wizard first."))
            return
        us_set("audit_complete", False)
        us_set("report_markdown", "")
        us_set("pdf_data_bytes", None)
        _run_audit_pipeline(client, intake, assess)

    if consume_auto_run_assessment() and not audit_complete:
        _try_run_audit()
        st.rerun()

    if not audit_complete and st.button(
        assess.get("run_button", "Run Compliance Audit"), type="primary"
    ):
        _try_run_audit()

    if audit_complete:
        _render_command_center(cc)

    render_pdf_export_action(
        pdf_bytes=us_get("pdf_data_bytes") if audit_complete else None,
        audit_complete=audit_complete,
        download_label=save_label,
    )


def _run_audit_pipeline(client, intake: dict, assess: dict):
    """
    Deterministic-first audit pipeline:

        0. utils.risk_engine  — statutory classification cascade (no LLM)
        0. utils.annex_iv     — Annex IV documentation scan + clarification matrix
        A. Ingestion Analyst  — technical profile, evidence-bound
        B. Regulatory Cross-Examiner — cited legal findings, KB-grounded
        C. Executive Auditor Draftsman — 4-tier narrative (Tier 2 & Tier 4)

    The LLM agents operate INSIDE the deterministic classification: they may
    not re-classify, and every assertion must carry a statutory citation or
    be routed to the Clarification Request Matrix.
    """
    # ── Stage 0a: deterministic statutory classification ─────────────────────
    classification = classify_risk(intake)
    system_risk_status, risk_citation = classification.tier, classification.citation
    decision_path_block = "\n".join(f"  {s}" for s in classification.decision_path)

    sector_mitigation = SECTOR_MITIGATIONS.get(
        intake.get("industry", ""),
        SECTOR_MITIGATIONS["Other / General Business Operations"],
    )

    # ── Stage 0b: deterministic Annex IV documentation reconciliation ─────────
    intake_content = (intake.get("intake_content") or "").strip()
    if not intake_content:
        blueprint_text = intake.get("evidence_text", "") or ""
        description = (intake.get("description") or "").strip()
        intake_content = compile_intake_content(description, blueprint_text)

    documentation_corpus = intake_content
    had_documentation = bool(documentation_corpus.strip())

    annex_iv_findings = scan_documentation(documentation_corpus)
    annex_iv_block = findings_summary_block(annex_iv_findings, had_documentation)

    clarification_matrix = build_clarification_matrix(
        intake, annex_iv_findings, had_documentation)
    clarification_text = clarification_block(clarification_matrix)

    # ── Legal grounding corpus ────────────────────────────────────────────────
    official_law_context = load_legal_knowledge_base()
    kb_sources = knowledge_base_inventory()

    # ── Standardised intake payload ───────────────────────────────────────────
    wizard_metadata = (
        "=== SMART COMPLIANCE WIZARD — DEEP INTAKE PROFILE ===\n"
        f"Company / Organisation:        {intake.get('company') or '[not provided]'}\n"
        f"Value-Chain Role:              {intake.get('role', '—')}\n"
        f"S1 — Industry Sector:          {intake.get('industry', '—')}\n"
        f"S2 — Biometric Footprint:      {intake.get('biometric', '—')}\n"
        f"S2 — Profiling / Policing:     {intake.get('policing', '—')}\n"
        f"S2 — Social Scoring:           {intake.get('social_scoring', '—')}\n"
        f"S2 — Training Data Source:     {intake.get('data_source', '—')}\n"
        f"S3 — Operational Scope:        {intake.get('audience', '—')}\n"
        f"S3 — Human Oversight Model:    {intake.get('oversight', '—')}\n"
        f"S3 — Annex I Product Link:     {intake.get('annex1', '—')}\n"
        f"S3 — Functional Role (Art 6(3)): {intake.get('function', '—')}\n"
        "=== END OF WIZARD METADATA ===\n"
    )

    pasted_block = (
        f"\n--- COMPILED INTAKE CONTENT ---\n{intake_content}\n"
        if intake_content else ""
    )
    combined_blueprint = wizard_metadata + pasted_block

    classification_block = (
        "=== DETERMINISTIC STATUTORY CLASSIFICATION (authoritative — do not alter) ===\n"
        f"TIER: {system_risk_status}\n"
        f"PRIMARY CITATION: {risk_citation}\n"
        f"DECISION PATHWAY:\n{decision_path_block}\n"
        "=== END OF CLASSIFICATION ===\n"
    )

    final_report_text = None
    action_plan_text = None

    try:
        # ── Agent A: Ingestion Analyst (evidence-bound profile) ──────────────
        with thinking_mode(assess.get("spinner_a", "Agent A is analysing...")):
            prompt_a = (
                "You are Agent A — the Ingestion Analyst in a multi-agent EU AI Act "
                "conformity-assessment pipeline.\n\n"
                "Produce a structured TECHNICAL PROFILE of the target AI system covering "
                "exactly these five dimensions:\n"
                "1. Core Data Pipelines\n"
                "2. Training Data Recency & Origin\n"
                "3. Automation Thresholds & Human Oversight Wiring\n"
                "4. Systemic Decision Footprint (who is affected, at what scale)\n"
                "5. Documentation Coverage (mirror the Annex IV scan verdicts below "
                "verbatim — you may not upgrade any status)\n\n"
                "EVIDENCE RULE: every statement in your profile must be traceable to the "
                "intake payload below. Where the payload is silent, write exactly "
                "'[NOT EVIDENCED IN INTAKE]' — do not infer, embellish, or fill gaps.\n\n"
                f"{classification_block}\n"
                f"{annex_iv_block}\n"
                f"SYSTEM INTAKE PAYLOAD:\n{combined_blueprint if combined_blueprint.strip() else '[No intake data provided]'}\n\n"
                "Output only the structured technical profile. Be precise and concise."
            )
            profile_a = call_gemini_with_retry(client, prompt_a)

        # ── Agent B: Regulatory Cross-Examiner (grounded findings) ───────────
        with thinking_mode(assess.get("spinner_b", "Agent B is auditing...")):
            law_block = (
                f"\n\nOFFICIAL REGULATORY REFERENCE DOCUMENTS "
                f"({len(kb_sources)} source files: {', '.join(kb_sources[:6])}...):\n"
                f"{official_law_context}\n"
                if official_law_context else
                "\n\nNOTE: the knowledge base returned no reference text. Restrict "
                "citations to provisions you can identify with certainty; route "
                "anything uncertain to the Clarification Request Matrix.\n"
            )
            prompt_b = (
                "You are Agent B — the Regulatory Cross-Examiner in a multi-agent EU AI Act "
                "conformity-assessment pipeline.\n\n"
                f"{CITATION_PROTOCOL}\n\n"
                f"{classification_block}\n"
                "Agent A's evidence-bound technical profile:\n\n"
                f"{profile_a}\n\n"
                f"{annex_iv_block}\n"
                f"{clarification_text}"
                "Your task: cross-examine the profile against the EU AI Act and produce "
                "cited legal findings. Work through this exact checklist in order:\n"
                "B1. Article 5 exposure — confirm or refute each prohibited-practice hook "
                "relevant to the profile (social scoring 5(1)(c), predictive policing 5(1)(d), "
                "untargeted facial scraping 5(1)(e), workplace/education emotion recognition "
                "5(1)(f), real-time remote biometric ID 5(1)(h)).\n"
                "B2. Annex I pathway (Article 6(1)) — safety-component / harmonised-product analysis.\n"
                "B3. Annex III pathway (Article 6(2)) — walk ALL EIGHT domains explicitly: "
                "(1) Biometrics, (2) Critical infrastructure, (3) Education, (4) Employment, "
                "(5) Essential public/private services, (6) Law enforcement, (7) Migration/"
                "asylum/border control, (8) Administration of justice & democratic processes. "
                "State MATCH or NO MATCH per domain with the Annex III point.\n"
                "B4. Article 6(3) derogation — evaluate the deterministic exemption record in "
                "the decision pathway; verify the profiling override of Article 6(3) third "
                "subparagraph was applied correctly.\n"
                "B5. High-risk obligations — Articles 8-15 (risk management 9, data governance 10, "
                "technical documentation 11/Annex IV, logging 12, transparency to deployers 13, "
                "human oversight 14, accuracy/robustness/cybersecurity 15).\n"
                "B6. Annex IV reconciliation — for every component the scan marks MISSING, "
                "record a 'CRITICAL REGULATORY DEFICIENCY' finding citing Article 11 and the "
                "specific Annex IV point; for SHALLOW components, record a depth deficiency. "
                "NEVER describe documentation content that is not evidenced.\n"
                "B7. Article 50 transparency and Chapter V GPAI duties where applicable.\n\n"
                f"{ARTICLE_50_GUARDRAIL}\n"
                f"{law_block}"
                "Output: numbered legal findings (F-1, F-2, ...), each with its statutory "
                "citation, the evidence relied on, and a severity (CRITICAL/HIGH/MEDIUM). "
                "Close with a verbatim restatement of the Clarification Request Matrix items "
                "that remain open."
            )
            findings_b = call_gemini_with_retry(client, prompt_b)

        # ── Agent C: Executive Auditor Draftsman (Tier 2 narrative) ──────────
        with thinking_mode(assess.get("spinner_c", "Agent C is drafting...")):
            prompt_c = (
                "You are Agent C — the Executive Auditor Draftsman in a multi-agent EU AI Act "
                "conformity-assessment pipeline.\n\n"
                f"{CITATION_PROTOCOL}\n\n"
                f"{classification_block}\n"
                "Agent B's cited legal findings:\n\n"
                f"{findings_b}\n\n"
                "Draft the NARRATIVE LAYERS of a formal conformity report in clean markdown. "
                "The deterministic engine already renders the risk banner, the statutory "
                "decision pathway, and the Annex IV gap table — do NOT reproduce them. "
                "Produce exactly these sections:\n\n"
                "## Executive Summary\n"
                "Three to five sentences: state the deterministic tier verbatim, the primary "
                "citation, the count of CRITICAL findings, and the overall conformity verdict. "
                "Write for a non-lawyer executive; define any term of art in plain language.\n\n"
                "## Section 1: Compliance Breach Inventory\n"
                "One numbered entry per finding from Agent B:\n"
                "  1.1 [Breach Title]\n"
                "    1.1.1 Systemic Vulnerability: [concrete technical flaw, plain language]\n"
                "    1.1.2 Legal Violation: [exact Article/paragraph/Annex point citation]\n"
                "    1.1.3 Severity: [CRITICAL / HIGH / MEDIUM]\n"
                "Annex IV items marked MISSING must appear here titled "
                "'Critical Regulatory Deficiency — [component]'.\n\n"
                "## Section 2: Regulatory Metric Map\n"
                "  2.1 Article 5 Compliance Status: [PASS / FAIL / PARTIAL]  Rationale: ...\n"
                "  2.2 Article 10 Compliance Status: [...]  Rationale: ...\n"
                "  2.3 Article 11 / Annex IV Documentation Status: [...]  Rationale: ...\n"
                "  2.4 Article 14 Compliance Status: [...]  Rationale: ...\n"
                "  2.5 Article 15 Compliance Status: [...]  Rationale: ...\n"
                "  2.6 Annex III Classification Status: [CONFIRMED HIGH-RISK / EXEMPT UNDER "
                "6(3) / NOT APPLICABLE]  Rationale: ...\n"
                "Use INSUFFICIENT EVIDENCE instead of PASS wherever the intake cannot "
                "support a verdict, and reference the matching CR-number.\n\n"
                f"SECTOR-SPECIFIC MITIGATION MANDATE for "
                f"{intake.get('industry', 'the selected industry')}: {sector_mitigation}\n\n"
                f"{ARTICLE_50_GUARDRAIL}\n\n"
                "FORMATTING RULE: every finding and metric row carries its decimal index "
                "(1.X / 1.X.X, 2.X) as a hard prefix. No plain bullets in Sections 1-2."
            )
            final_report_text = call_gemini_with_retry(client, prompt_c)

        # ── Agent C (second pass): Tier 4 Engineering Action Plan ────────────
        with thinking_mode(assess.get("spinner_d",
                                       "Agent C is compiling the engineering action plan...")):
            prompt_d = (
                "You are Agent C — now drafting TIER 4: THE ENGINEERING ACTION PLAN of the "
                "conformity report.\n\n"
                f"{CITATION_PROTOCOL}\n\n"
                f"{classification_block}\n"
                "The cited findings and breach inventory:\n\n"
                f"{findings_b}\n\n"
                f"{annex_iv_block}\n"
                "Write a remediation roadmap FOR A SOFTWARE ENGINEERING TEAM, not lawyers. "
                "Plain language, concrete deliverables, no legalese beyond the citations. "
                "Structure:\n"
                "  3.1 Phase I: Immediate Technical Remediation (0-30 days)\n"
                "    Step 3.1.1: [action — deliverable, suggested owner role, statutory anchor]\n"
                "    Step 3.1.2: ...\n"
                "  3.2 Phase II: Documentation & Data Governance Build-Out (30-90 days)\n"
                "    Step 3.2.1: [one step per Annex IV component marked MISSING or SHALLOW, "
                "using the scan's mitigation text as the deliverable]\n"
                "  3.3 Phase III: Oversight, Logging & Monitoring Architecture (90-180 days)\n"
                "    Step 3.3.1: ...\n"
                "Add further phases only if the findings demand them. Every step ends with "
                "its statutory anchor in brackets. If the tier is PROHIBITED, Phase I must "
                "begin with the decommissioning plan [Article 5] and state plainly that no "
                "engineering fix can legalise the practice.\n\n"
                f"SECTOR MANDATE to weave into the phases: {sector_mitigation}"
            )
            action_plan_text = call_gemini_with_retry(client, prompt_d)

    except Exception:
        return

    if final_report_text and action_plan_text:
        pathway_md = "\n".join(f"1. {s}" for s in classification.decision_path)
        us_set("report_markdown", (
            f"### Statutory Decision Pathway (deterministic)\n{pathway_md}\n\n"
            f"{final_report_text}\n\n## Engineering Action Plan\n{action_plan_text}"
        ))
        pdf_bytes = generate_pdf_report(
            final_report_text,
            classification=classification,
            annex_iv_findings=annex_iv_findings,
            had_documentation=had_documentation,
            clarification_matrix=clarification_matrix,
            company=intake.get("company") or None,
            industry=intake.get("industry") or None,
            disclaimer_line=_c("legal", "disclaimer", "pdf_line"),
            legal_narrative=final_report_text,
            action_plan=action_plan_text,
        )
        us_set("pdf_data_bytes", pdf_bytes)
        us_set("risk_tier", system_risk_status)
        us_set("risk_citation", risk_citation)
        us_set("audit_date", date.today().isoformat())
        us_pop("obligations_df", None)
        us_set("audit_complete", True)

        # Member Mode only: persist profile + report + compliance tasks to Supabase.
        # Guests remain zero-retention (screen preview only).
        if is_logged_in():
            member_uid = get_auth_user_id() or current_user_id()
            obligations_df = build_obligations_register(intake, system_risk_status)
            compliance_tasks = []
            for _, row in obligations_df.iterrows():
                compliance_tasks.append({
                    "title": str(row.get("Obligation", "")),
                    "description": str(row.get("Description", "")),
                    "citation": str(row.get("Legal Basis", "")),
                    "status": "open",
                })
            for item in clarification_matrix or []:
                topic = str(item.get("topic") or "Clarification required")
                compliance_tasks.append({
                    "title": f"Clarify: {topic}",
                    "description": str(item.get("question") or item.get("why_it_matters") or ""),
                    "citation": str(item.get("citation") or ""),
                    "status": "open",
                })
            audit_results_payload = {
                "risk_tier": system_risk_status,
                "risk_citation": risk_citation,
                "audit_date": date.today().isoformat(),
                "report_markdown": us_get("report_markdown", ""),
                "decision_path": list(classification.decision_path),
                "annex_iv_summary": [
                    {
                        "component_id": f.component_id,
                        "title": f.title,
                        "status": f.status,
                        "citation": f.citation,
                    }
                    for f in (annex_iv_findings or [])
                ],
                "clarification_matrix": clarification_matrix or [],
            }
            system_profile_payload = {
                **dict(intake),
                "system_name": (
                    intake.get("company")
                    or intake.get("industry")
                    or "AI System"
                ),
                "company_name": intake.get("company") or "",
            }
            try:
                persist_member_audit(
                    member_uid,
                    system_profile_payload,
                    audit_results_payload,
                    compliance_tasks=compliance_tasks,
                )
            except Exception:
                pass

        if is_pdf_export_unlocked():
            system_name = (
                intake.get("company")
                or intake.get("industry")
                or "AI System"
            )
            contact_email = current_user_email()
            archive_purchased_audit(
                current_user_id(),
                contact_email,
                system_name,
                pdf_bytes,
                generated_at=date.today().isoformat(),
            )

        st.rerun()


def _render_command_center(cc: dict):
    """Post-assessment governance workspace: overview, obligations, calendar."""
    intake_done = us_get("intake", {})
    tier_done = us_get("risk_tier", "—")
    citation_done = us_get("risk_citation", "—")
    try:
        audit_dt = date.fromisoformat(us_get("audit_date", ""))
    except ValueError:
        audit_dt = date.today()

    _section_header(cc.get("label", ""), cc.get("title", ""), cc.get("sub", ""))

    cc_overview, cc_obligations, cc_calendar = st.tabs(
        cc.get("tabs", ["Overview", "Obligations Sheet", "Regulatory Calendar"])
    )

    # ── COMMAND CENTER TAB 1: Overview ────────────────────────────────────────
    with cc_overview:
        ov1, ov2, ov3 = st.columns(3)
        ov1.metric("EU AI Act Risk Tier", tier_done.split(" (")[0])
        ov2.metric("Primary Citation", citation_done)
        ov3.metric("Assessment Date", audit_dt.strftime("%d %b %Y"))

        st.markdown(us_get("report_markdown", ""))

    # ── COMMAND CENTER TAB 2: Obligations Sheet ───────────────────────────────
    with cc_obligations:
        st.markdown(f"""
        <div class="section-label" style="margin-bottom:0.4rem;">{cc.get("obligations_label", "")}</div>
        <div class="section-sub">{cc.get("obligations_sub", "")}</div>
        """, unsafe_allow_html=True)

        if not us_contains("obligations_df"):
            us_set("obligations_df", build_obligations_register(
                intake_done, tier_done
            ))

        edited_df = st.data_editor(
            us_get("obligations_df"),
            key="obligations_editor",
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            column_config={
                "Obligation": st.column_config.TextColumn(
                    "Obligation", disabled=True, width="medium"),
                "Legal Basis": st.column_config.TextColumn(
                    "Legal Basis", disabled=True, width="small"),
                "Description": st.column_config.TextColumn(
                    "Description", disabled=True, width="large"),
                "Status": st.column_config.SelectboxColumn(
                    "Status",
                    options=["Compliant", "In Progress", "Action Required"],
                    required=True,
                    width="small",
                ),
                "Notes": st.column_config.TextColumn(
                    "Notes", help="Free-text compliance log", width="medium"),
            },
        )
        us_set("obligations_df", edited_df)

        total = len(edited_df)
        compliant = int((edited_df["Status"] == "Compliant").sum())
        in_prog = int((edited_df["Status"] == "In Progress").sum())
        action = int((edited_df["Status"] == "Action Required").sum())

        ob1, ob2, ob3, ob4 = st.columns(4)
        ob1.metric("Total Obligations", total)
        ob2.metric("Compliant", compliant)
        ob3.metric("In Progress", in_prog)
        ob4.metric("Action Required", action)
        st.progress(compliant / total if total else 0.0,
                    text=f"Register closure: {compliant}/{total} obligations compliant")

    # ── COMMAND CENTER TAB 3: Regulatory Calendar ─────────────────────────────
    with cc_calendar:
        st.markdown(f"""
        <div class="section-label" style="margin-bottom:0.4rem;">{cc.get("calendar_label", "")}</div>
        <div class="section-sub">{cc.get("calendar_sub", "")}</div>
        """, unsafe_allow_html=True)

        events = build_regulatory_calendar(audit_dt, intake_done, tier_done)
        today = date.today()

        timeline_rows = []
        for ev_date, title, basis, detail in events:
            days_left = (ev_date - today).days
            if days_left < 0:
                badge_bg, badge_fg, badge_txt = "#7F1D1D", "#FECACA", "OVERDUE"
            elif days_left <= 30:
                badge_bg, badge_fg, badge_txt = "#78350F", "#FDE68A", f"{days_left} DAYS"
            else:
                badge_bg, badge_fg, badge_txt = "#064E3B", "#A7F3D0", f"{days_left} DAYS"
            timeline_rows.append(f"""
            <div style="display:flex;gap:16px;margin-bottom:0;">
              <div style="display:flex;flex-direction:column;align-items:center;">
                <div style="width:14px;height:14px;border-radius:50%;background:#2563EB;
                     border:3px solid #DBEAFE;flex-shrink:0;margin-top:4px;"></div>
                <div style="width:2px;flex:1;background:#E2E8F0;min-height:46px;"></div>
              </div>
              <div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:10px;
                   padding:0.85rem 1.1rem;margin-bottom:0.9rem;flex:1;
                   box-shadow:0 1px 4px rgba(0,0,0,0.05);">
                <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;">
                  <span style="font-size:0.9rem;font-weight:600;color:#0F172A;">{title}</span>
                  <span style="font-size:0.68rem;font-weight:700;letter-spacing:0.05em;
                        background:{badge_bg};color:{badge_fg};border-radius:20px;
                        padding:3px 10px;white-space:nowrap;">{badge_txt}</span>
                </div>
                <div style="font-size:0.78rem;color:#2563EB;font-weight:600;margin:2px 0 4px;">
                  {ev_date.strftime("%A, %d %B %Y")} · {basis}
                </div>
                <div style="font-size:0.8rem;color:#64748B;">{detail}</div>
              </div>
            </div>""")

        st.markdown(
            '<div style="margin-top:0.75rem;">' + "".join(timeline_rows) + "</div>",
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
# VIEW 2 — Legal & Imprint Hub
# ══════════════════════════════════════════════════════════════════════════════

def render_legal_hub():
    """EU AI Act risk tier reference framework."""
    hub = _c("legal", "hub", default={})
    _section_header(hub.get("label", ""), hub.get("title", ""), hub.get("sub", ""))

    tiers = _c("risk_tiers", default={})

    # ── Risk tier reference framework ─────────────────────────────────────────
    if tiers:
        st.markdown(
            '<div class="section-label" style="margin-bottom:0.6rem;">'
            'EU AI Act Risk Tier Framework</div>',
            unsafe_allow_html=True,
        )
        tier_cols = st.columns(3)
        for col, key in zip(tier_cols, ("minimal", "limited", "high")):
            tier = tiers.get(key, {})
            with col:
                st.markdown(f"""
                <div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:10px;
                     padding:1rem 1.1rem;height:100%;box-shadow:0 1px 4px rgba(0,0,0,0.05);">
                  <div style="font-size:0.95rem;font-weight:700;color:#0F172A;">{tier.get("name", "")}</div>
                  <div style="font-size:0.72rem;font-weight:600;color:#2563EB;margin:2px 0 8px;">{tier.get("citation", "")}</div>
                  <div style="font-size:0.8rem;color:#475569;line-height:1.55;">{tier.get("summary", "")}</div>
                  <div style="font-size:0.76rem;color:#64748B;line-height:1.5;margin-top:8px;">{tier.get("pass_rules", "")}</div>
                </div>
                """, unsafe_allow_html=True)
        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

