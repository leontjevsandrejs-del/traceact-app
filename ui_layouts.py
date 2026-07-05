"""
TraceAct layout module — core functional web views.

All user-facing labels and body markdown are pulled dynamically from
``st.session_state.content`` (loaded from content.json by the app.py router).
No marketing or legal copy is hardcoded in this file.

Exports:
    render_workspace_engine()  — intake wizard, multi-agent audit pipeline,
                                 compliance tracking sheets, PDF pack hooks.
    render_legal_hub()         — GDPR Article 28 agreements + corporate imprint.
"""

import os
import re
import time
import random

import pandas as pd
import streamlit as st
from datetime import date, timedelta
from google import genai
from google.genai.errors import APIError, ClientError
from fpdf import FPDF
import pypdf

PRIMARY_MODEL = "gemini-2.5-flash"
FALLBACK_MODEL = "gemini-2.0-flash"

ARTICLE_50_GUARDRAIL = """---
⚠️ CRITICAL REGULATORY GUARDRAIL – ARTICLE 50 TEXT GENERATION EXEMPTION:
When evaluating an AI system that generates text content (such as marketing copy, social media posts, or articles) under Article 50:
1. You must explicitly distinguish between 'Providers' (who build the model and must watermark synthetic outputs under Article 50(2)) and 'Deployers' (who use the model to generate public-facing text under Article 50(4)).
2. Under Article 50(4), a Deployer is ONLY required to label text as AI-generated if it is published to inform the public on matters of public interest (e.g., news, political announcements) AND it has not undergone human review or editorial control.
3. EXEMPTION CRITERIA: If the user profile explicitly states that a human reviews, edits, or approves the text outputs before public release, or if the content is standard commercial retail marketing, the system qualifies for the statutory exemption. In this scenario, you MUST mark the Article 50 compliance status as a 'PASS' and state that human editorial control satisfies the regulatory threshold. Never issue a 'FAIL' or a high-severity breach if a human-in-the-loop workflow is active.
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
# Gemini client & resilient retry lane
# ══════════════════════════════════════════════════════════════════════════════

def get_gemini_api_key() -> str | None:
    key = os.getenv("GEMINI_API_KEY", "").strip().strip("\"'")
    if not key or key == "YOUR_ACTUAL_API_KEY_HERE":
        return None
    return key


def get_gemini_client() -> genai.Client | None:
    api_key = get_gemini_api_key()
    if not api_key:
        return None
    return genai.Client(api_key=api_key)


def _is_rate_limit_error(err: Exception) -> bool:
    """Return True if the exception signals a 429 / quota-exhausted condition."""
    if isinstance(err, (ClientError, APIError)):
        status = getattr(err, "status_code", None) or getattr(err, "code", None)
        if status == 429:
            return True
    err_str = str(err)
    return any(token in err_str for token in ("429", "RESOURCE_EXHAUSTED", "quota"))


def _is_transient_error(err: Exception) -> bool:
    """Return True for retryable conditions: 429 rate limits and 503 overload."""
    if _is_rate_limit_error(err):
        return True
    if isinstance(err, (ClientError, APIError)):
        status = getattr(err, "status_code", None) or getattr(err, "code", None)
        if status in (500, 503, 504):
            return True
    err_str = str(err)
    return any(
        token in err_str
        for token in ("503", "UNAVAILABLE", "overloaded", "high demand", "Deadline")
    )


def call_gemini_with_retry(client, prompt, model_name=None):
    """
    Call the Gemini API with up to 4 attempts and exponential backoff.
    Displays a live animated countdown in the Streamlit UI during each wait.
    """
    model = model_name or PRIMARY_MODEL
    max_attempts = 4
    last_err = None

    for attempt in range(max_attempts):
        try:
            result = client.models.generate_content(
                model=model, contents=prompt
            )
            return result.text

        except (ClientError, APIError, Exception) as err:
            last_err = err

            if not _is_transient_error(err):
                # Non-recoverable error — surface immediately
                raise

            is_overload = not _is_rate_limit_error(err)

            # A 503 means this specific model is overloaded — switch to the
            # fallback model right away instead of waiting out a long backoff.
            if is_overload and model == PRIMARY_MODEL:
                model = FALLBACK_MODEL
                st.info(
                    f"⚡ {PRIMARY_MODEL} is overloaded (503). "
                    f"Switching to fallback lane ({FALLBACK_MODEL}) immediately."
                )
                time.sleep(2)
                continue

            if is_overload:
                delay = int((2 ** attempt) * 5 + random.uniform(1, 3))
                reason = "Model overloaded (503 UNAVAILABLE)"
            else:
                delay = int((2 ** attempt) * 8 + random.uniform(1, 3))
                reason = "Rate limit threshold reached"

            countdown_box = st.empty()

            for remaining in range(delay, 0, -1):
                countdown_box.warning(
                    f"⏳ {reason} on **{model}** "
                    f"(attempt {attempt + 1}/{max_attempts}). "
                    f"Cooldown backoff active... retrying in **{remaining}s**."
                )
                time.sleep(1)

            countdown_box.empty()

            # On the final attempt, try FALLBACK_MODEL before giving up
            if attempt == max_attempts - 2 and model == PRIMARY_MODEL:
                model = FALLBACK_MODEL
                st.info(
                    f"Switching to fallback lane ({FALLBACK_MODEL}) "
                    f"for remaining attempts."
                )

    st.error(
        f"**All {max_attempts} retry attempts exhausted.**\n\n"
        f"The Gemini API is currently rate-limited or overloaded. "
        f"Please try the following:\n"
        f"- Wait 60–90 seconds and click **Run Compliance Audit** again.\n"
        f"- Check your quota at [Google AI Studio](https://aistudio.google.com/app/u/0/plan_information).\n"
        f"- Verify your API key is for a paid-tier project if usage is high.\n\n"
        f"Last error: `{last_err}`"
    )
    return None


def load_legal_knowledge_base():
    kb_path = os.path.join(os.path.dirname(__file__), "knowledge_base")
    if not os.path.isdir(kb_path):
        return ""
    combined_text = []
    for filename in os.listdir(kb_path):
        if filename.endswith(".txt"):
            filepath = os.path.join(kb_path, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                combined_text.append(f.read())
    return "\n\n".join(combined_text)


# ══════════════════════════════════════════════════════════════════════════════
# PDF document builder (branded audit pack)
# ══════════════════════════════════════════════════════════════════════════════

_C_SLATE   = (26,  46,  64)   # Deep Slate Blue  — primary headers
_C_CHAR    = (60,  60,  60)   # Soft Charcoal    — body text
_C_GRAY_BG = (245, 246, 248)  # Muted Light Gray — metric summary fills
_C_ACCENT  = (92, 130, 165)   # Steel accent     — rule lines
_C_WHITE   = (255, 255, 255)


class _AuditPDF(FPDF):
    """FPDF subclass that stamps a branded header and page-number footer."""

    def header(self):
        self.set_draw_color(*_C_ACCENT)
        self.set_line_width(0.4)
        self.line(20, 14, 190, 14)
        self.set_font("Helvetica", "I", 7.5)
        self.set_text_color(*_C_ACCENT)
        self.set_y(9)
        self.cell(0, 5,
                  "EU AI Act Compliance Assessment Hub  |  Confidential Audit File",
                  align="C")
        self.ln(8)

    def footer(self):
        self.set_y(-13)
        self.set_draw_color(*_C_ACCENT)
        self.set_line_width(0.3)
        self.line(20, self.get_y(), 190, self.get_y())
        self.set_font("Helvetica", "I", 7.5)
        self.set_text_color(*_C_ACCENT)
        self.cell(0, 6, f"Page {self.page_no()}", align="C")


def _sanitise(text: str) -> str:
    """Strip non-latin-1 characters and common markdown clutter."""
    text = text.replace("\u26a0\ufe0f ", "").replace("\u26a0\ufe0f", "")  # ⚠️ prefix
    text = text.replace("\u26a0", "").replace("\ufe0f", "")               # stray parts
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2014", "--").replace("\u2013", "-")
    # Drop any remaining glyphs Helvetica/latin-1 cannot render
    # (errors="replace" would turn each of them into a "?").
    return text.encode("latin-1", errors="ignore").decode("latin-1")


def _render_body(pdf: _AuditPDF, insights_text: str) -> None:
    """Parse the agent output line-by-line and render with styling."""
    page_h = pdf.h - pdf.b_margin

    def _w():
        """Usable line width, always anchored to the left margin."""
        pdf.set_x(pdf.l_margin)
        return pdf.w - pdf.l_margin - pdf.r_margin

    for raw_line in insights_text.splitlines():
        line = raw_line.rstrip()

        # ── H1 / H2 section headers ──────────────────────────────────────────
        if line.startswith("## ") or line.startswith("# "):
            label = line.lstrip("#").strip()
            if pdf.get_y() > page_h - 20:
                pdf.add_page()
            pdf.ln(4)
            pdf.set_font("Helvetica", "B", 13)
            pdf.set_text_color(*_C_SLATE)
            pdf.set_draw_color(*_C_ACCENT)
            pdf.set_line_width(0.35)
            pdf.multi_cell(_w(), 7, _sanitise(label))
            pdf.set_x(pdf.l_margin)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(3)

        # ── H3 sub-headers ───────────────────────────────────────────────────
        elif line.startswith("### "):
            label = line[4:].strip()
            if pdf.get_y() > page_h - 14:
                pdf.add_page()
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(*_C_SLATE)
            pdf.multi_cell(_w(), 6, _sanitise(label))
            pdf.ln(1)

        # ── Metric / summary rows (lines starting with 2.X) ──────────────────
        elif re.match(r"^\s*2\.\d", line):
            if pdf.get_y() > page_h - 10:
                pdf.add_page()
            pdf.set_fill_color(*_C_GRAY_BG)
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(*_C_SLATE)
            pdf.multi_cell(_w(), 7, _sanitise(line.strip()), fill=True)

        # ── Empty lines ──────────────────────────────────────────────────────
        elif line.strip() == "":
            pdf.ln(2)

        # ── Regular body paragraphs (with inline **bold** handling) ──────────
        else:
            pdf.set_text_color(*_C_CHAR)
            clean = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
            if re.match(r"^\*\*", line.strip()):
                pdf.set_font("Helvetica", "B", 10)
            else:
                pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(_w(), 6, _sanitise(clean))


def generate_pdf_report(final_report_text, risk_tier=None, citation=None,
                        company=None, industry=None):
    pdf = _AuditPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_margins(left=20, top=20, right=20)
    pdf.add_page()

    # ── Cover title banner ────────────────────────────────────────────────────
    pdf.set_fill_color(*_C_SLATE)
    pdf.set_text_color(*_C_WHITE)
    pdf.set_font("Helvetica", "B", 17)
    pdf.cell(0, 16,
             "EU AI Act Official Compliance Assessment Report",
             ln=True, fill=True, align="C")
    pdf.ln(4)

    # ── Metadata summary card ─────────────────────────────────────────────────
    pdf.set_fill_color(*_C_GRAY_BG)
    pdf.set_draw_color(*_C_ACCENT)
    pdf.set_line_width(0.3)

    def _meta_row(label, value):
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*_C_SLATE)
        pdf.cell(48, 8, label, fill=True)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*_C_CHAR)
        pdf.cell(0, 8, _sanitise(value), ln=True, fill=True)

    _meta_row("Generation Date:",      date.today().strftime("%B %d, %Y"))
    if company:
        _meta_row("Organisation:",     company)
    if industry:
        _meta_row("Industry Sector:",  industry)
    if risk_tier:
        _meta_row("EU AI Act Risk Tier:", risk_tier)
    if citation:
        _meta_row("Primary Citation:", citation)
    _meta_row("Report Type:",          "Automated Readiness Indicator")
    _meta_row("Legal Status:",         "Not Licensed Legal Counsel")
    pdf.ln(5)

    # ── Accent rule before body ───────────────────────────────────────────────
    pdf.set_draw_color(*_C_SLATE)
    pdf.set_line_width(0.6)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(5)

    # ── Parsed body ──────────────────────────────────────────────────────────
    _render_body(pdf, final_report_text)

    # ── Legal disclaimer ─────────────────────────────────────────────────────
    if pdf.get_y() > pdf.h - pdf.b_margin - 18:
        pdf.add_page()
    pdf.ln(6)
    pdf.set_draw_color(*_C_ACCENT)
    pdf.set_line_width(0.25)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(3)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(100, 116, 139)
    pdf.multi_cell(
        pdf.w - pdf.l_margin - pdf.r_margin,
        5,
        _sanitise(_c("legal", "disclaimer", "pdf_line")),
    )

    return bytes(pdf.output())


def save_report_to_downloads(pdf_bytes: bytes) -> tuple[bool, str, str | None]:
    """
    Write the audit PDF to the user's Downloads folder.
    Returns (success, message, saved_path).
    If the default filename is locked (e.g. open in a PDF viewer), retries with a timestamped name.
    """
    downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
    os.makedirs(downloads_dir, exist_ok=True)

    candidates = [
        os.path.join(downloads_dir, "EU_AI_Act_Audit_Report.pdf"),
        os.path.join(
            downloads_dir,
            f"EU_AI_Act_Audit_Report_{date.today().strftime('%Y%m%d_%H%M%S')}.pdf",
        ),
    ]

    last_err: Exception | None = None
    for path in candidates:
        try:
            with open(path, "wb") as f:
                f.write(pdf_bytes)
            if path == candidates[0]:
                return (
                    True,
                    f"✅ Success! Report saved to your Downloads folder:\n`{path}`",
                    path,
                )
            return (
                True,
                "✅ Report saved with a new filename because the original PDF "
                "is open or locked. Close `EU_AI_Act_Audit_Report.pdf` in your "
                "PDF viewer if you want to overwrite it next time.\n\n"
                f"Saved as:\n`{path}`",
                path,
            )
        except PermissionError as err:
            last_err = err
        except OSError as err:
            last_err = err

    return (
        False,
        "Could not save the report to Downloads. This usually means "
        "`EU_AI_Act_Audit_Report.pdf` is still open in another program "
        "(Adobe, Edge, etc.). Close that file and try again.\n\n"
        f"Technical detail: `{last_err}`",
        None,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Intake option catalogues & deterministic risk classification
# ══════════════════════════════════════════════════════════════════════════════

INDUSTRY_OPTIONS = [
    "Employment & HR (hiring, evaluation)",
    "Banking & Credit Scoring",
    "Critical Infrastructure (water, gas, electricity)",
    "Education & Vocational Training",
    "Healthcare & Medical Devices",
    "Law Enforcement",
    "General Purpose AI / LLM Development",
    "Other / General Business Operations",
]

BIOMETRIC_OPTIONS = [
    "No — the system never touches biometric or emotional data",
    "Yes — biometric identification (face, fingerprint, voice matching)",
    "Yes — emotion recognition (mood, stress, engagement inference)",
    "Yes — both identification and emotion recognition",
]

POLICING_OPTIONS = [
    "No — no predictive policing or profiling datasets are used",
    "Yes — profiling datasets (behavioural scoring of individuals)",
    "Yes — predictive policing (crime-risk forecasting on persons or areas)",
]

DATA_SOURCE_OPTIONS = [
    "Private enterprise databases (our own or licensed first-party data)",
    "Public scraping (data harvested from the open internet)",
    "Mixed — both scraped public data and private databases",
    "Third-party vendor — training data provenance unknown to us",
]

AUDIENCE_OPTIONS = [
    "Internal employees only",
    "External consumers / customers",
    "Public infrastructure (utilities, transport, civic services)",
]

OVERSIGHT_OPTIONS = [
    "Human-in-the-loop — a human can override any decision instantly",
    "Human-on-the-loop — humans monitor but intervention is delayed",
    "Fully autonomous — decisions execute with no human intervention",
]

ROLE_OPTIONS = [
    "Deployer (we use the system)",
    "Provider (we build and place it on the market)",
    "Both provider and deployer",
]

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
    "Critical Infrastructure (water, gas, electricity)": (
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
    "Law Enforcement": (
        "Annex III §6 law-enforcement systems: most use cases require prior "
        "judicial authorisation, strict necessity tests, and Article 5 "
        "prohibitions on real-time remote biometric ID apply in public spaces."
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


def classify_risk(intake: dict):
    """Map deep wizard answers onto official EU AI Act risk tiers."""
    industry  = intake.get("industry", "")
    biometric = intake.get("biometric", "")
    policing  = intake.get("policing", "")
    audience  = intake.get("audience", "")
    oversight = intake.get("oversight", "")

    # Option strings start with "Yes —"/"No —", so gate on the Yes prefix
    # before keyword matching (the No options repeat the same keywords).
    bio_yes   = biometric.lower().startswith("yes")
    emotion   = bio_yes and ("emotion" in biometric.lower() or "both" in biometric.lower())
    bio_id    = bio_yes and ("identification" in biometric.lower() or "both" in biometric.lower())
    pol_yes   = policing.lower().startswith("yes")
    pred_pol  = pol_yes and "predictive policing" in policing.lower()
    profiling = pol_yes and "profiling" in policing.lower()
    public    = "Public infrastructure" in audience
    autonomous = "Fully autonomous" in oversight

    high_risk_sectors = {
        "Employment & HR (hiring, evaluation)": "Annex III, Section 4",
        "Banking & Credit Scoring": "Annex III, Section 5(b)",
        "Critical Infrastructure (water, gas, electricity)": "Annex III, Section 2",
        "Education & Vocational Training": "Annex III, Section 3",
        "Healthcare & Medical Devices": "Annex III, Section 5(a)",
        "Law Enforcement": "Annex III, Section 6",
    }

    # Tier 1 — Prohibited Practices (Article 5)
    if pred_pol:
        return ("PROHIBITED PRACTICES (Article 5)", "Article 5(1)(d)")
    if emotion and industry in (
        "Employment & HR (hiring, evaluation)",
        "Education & Vocational Training",
    ):
        return ("PROHIBITED PRACTICES (Article 5)", "Article 5(1)(f)")
    if bio_id and public and "Law Enforcement" in industry:
        return ("PROHIBITED PRACTICES (Article 5)", "Article 5(1)(h)")

    # Tier 2 — High-Risk Systems (Annex III)
    if industry in high_risk_sectors:
        return ("HIGH-RISK SYSTEM (Annex III)", high_risk_sectors[industry])
    if bio_id or (profiling and autonomous) or (public and autonomous):
        return ("HIGH-RISK SYSTEM (Annex III)", "Annex III, Section 1/7")

    # Tier 3 — Specific Transparency Risks (Article 50 / Chapter V)
    if industry == "General Purpose AI / LLM Development":
        return ("SPECIFIC TRANSPARENCY RISK (Chapter V — GPAI)", "Articles 50-55")
    if "External consumers" in audience:
        return ("SPECIFIC TRANSPARENCY RISK (Article 50)", "Article 50(1)")

    # Tier 4 — Minimal Risk
    return ("MINIMAL RISK", "General Provisions")


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


def _wizard_step_header(current: int) -> str:
    labels = _c("workspace", "wizard", "step_labels",
                default=["Step 1", "Step 2", "Step 3", "Step 4"])
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
    tab1, tab2, tab3 = st.tabs(_c("workspace", "tabs",
                                  default=["System Triage", "Evidence Vault",
                                           "Conformity Assessment"]))

    with tab1:
        _render_intake_wizard(ws.get("wizard", {}))

    with tab2:
        _render_evidence_vault(ws.get("evidence", {}))

    with tab3:
        _render_conformity_assessment(ws.get("assessment", {}),
                                      ws.get("command_center", {}))


def _render_intake_wizard(wz: dict):
    _section_header(wz.get("label", ""), wz.get("title", ""), wz.get("sub", ""))

    if "step" not in st.session_state:
        st.session_state.step = 1
    if "intake" not in st.session_state:
        st.session_state.intake = {}

    intake = st.session_state.intake
    step = st.session_state.step

    st.markdown(_wizard_step_header(step), unsafe_allow_html=True)

    def _saved_index(options, key, default=0):
        saved = intake.get(key)
        return options.index(saved) if saved in options else default

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
            )

        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
        if st.button(s1.get("next_button", "Continue →"), type="primary"):
            intake["industry"] = sel_industry
            intake["company"] = sel_company.strip()
            intake["role"] = sel_role
            st.session_state.step = 2
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
                st.session_state.step = 1
                st.rerun()
        with col_next:
            if st.button(s2.get("next_button", "Continue →"), type="primary"):
                intake["biometric"] = sel_biometric
                intake["policing"] = sel_policing
                intake["data_source"] = sel_data_source
                st.session_state.step = 3
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

        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
        col_back, col_next = st.columns([1, 5])
        with col_back:
            if st.button(wz.get("step4", {}).get("back_button", "← Back")):
                st.session_state.step = 2
                st.rerun()
        with col_next:
            if st.button(s3.get("next_button", "Continue →"), type="primary"):
                intake["audience"] = sel_audience
                intake["oversight"] = sel_oversight
                st.session_state.step = 4
                st.rerun()

    # ── STEP 4: Evidence Upload & Intake Review ──────────────────────────────
    else:
        s4 = wz.get("step4", {})
        st.markdown(f"""
        <div class="section-label" style="margin-bottom:0.6rem;">{s4.get("label", "")}</div>
        <div class="section-sub">{s4.get("sub", "")}</div>
        """, unsafe_allow_html=True)

        col_upload, col_paste = st.columns([1, 1], gap="large")
        with col_upload:
            wizard_file = st.file_uploader(
                s4.get("upload_label", "Drop a file (TXT or PDF)"),
                type=["txt", "pdf"],
                key="wizard_uploader",
                help=s4.get("upload_help", ""),
            )
            if wizard_file is not None:
                try:
                    wizard_file.seek(0)
                    if wizard_file.name.lower().endswith(".pdf"):
                        reader = pypdf.PdfReader(wizard_file)
                        intake["evidence_text"] = "\n".join(
                            (page.extract_text() or "") for page in reader.pages
                        )
                    else:
                        intake["evidence_text"] = wizard_file.read().decode(
                            "utf-8", errors="replace"
                        )
                    st.success(s4.get("upload_success", "Document cached."))
                except Exception:
                    intake["evidence_text"] = ""
                    st.error(s4.get("upload_error", "Could not extract text."))

        with col_paste:
            pasted_val = st.text_area(
                s4.get("paste_label", "Or paste a description here"),
                value=intake.get("description", ""),
                height=160,
                placeholder=s4.get("paste_placeholder", ""),
            )
            intake["description"] = pasted_val

        # ── Live classification preview ───────────────────────────────────────
        preview_tier, preview_citation = classify_risk(intake)
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

        st.metric(label=s4.get("preview_metric", "Preliminary Risk Tier"),
                  value=preview_tier)
        st.markdown(f"**Primary Citation:** {preview_citation}")

        col_back, col_done = st.columns([1, 5])
        with col_back:
            if st.button(s4.get("back_button", "← Back")):
                st.session_state.step = 3
                st.rerun()
        with col_done:
            if st.button(s4.get("confirm_button", "✓ Confirm Intake"), type="primary"):
                intake["confirmed"] = True
                st.success(s4.get("confirm_success", "Intake locked."))


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

    if 'audit_complete' not in st.session_state:
        st.session_state.audit_complete = False
    if 'report_markdown' not in st.session_state:
        st.session_state.report_markdown = ""
    if 'pdf_data_bytes' not in st.session_state:
        st.session_state.pdf_data_bytes = None

    if st.button(assess.get("run_button", "Run Compliance Audit"), type="primary"):
        st.session_state.audit_complete = False
        st.session_state.report_markdown = ""
        st.session_state.pdf_data_bytes = None

        client = get_gemini_client()
        intake = st.session_state.get("intake", {})
        if client is None:
            st.error(assess.get("missing_key_error", "Missing GEMINI_API_KEY."))
        elif not intake.get("industry"):
            st.error(assess.get("missing_intake_error", "Complete the wizard first."))
        else:
            _run_audit_pipeline(client, intake, assess)

    if st.session_state.audit_complete:
        _render_command_center(cc)


def _run_audit_pipeline(client, intake: dict, assess: dict):
    """Sequential three-agent evaluation loop (A → B → C) with PDF compilation."""
    # ── Risk classification (deep wizard inputs → official tiers) ─────────────
    system_risk_status, risk_citation = classify_risk(intake)
    sector_mitigation = SECTOR_MITIGATIONS.get(
        intake.get("industry", ""),
        SECTOR_MITIGATIONS["Other / General Business Operations"],
    )

    official_law_context = load_legal_knowledge_base()

    # ── Build standardised intake payload ─────────────────────────────────────
    # Wizard answers are prepended as structured metadata so Agent A
    # receives a pre-normalised profile regardless of upload quality.
    wizard_metadata = (
        "=== SMART COMPLIANCE WIZARD — DEEP INTAKE PROFILE ===\n"
        f"Company / Organisation:        {intake.get('company') or '[not provided]'}\n"
        f"Value-Chain Role:              {intake.get('role', '—')}\n"
        f"S1 — Industry Sector:          {intake.get('industry', '—')}\n"
        f"S2 — Biometric Footprint:      {intake.get('biometric', '—')}\n"
        f"S2 — Profiling / Policing:     {intake.get('policing', '—')}\n"
        f"S2 — Training Data Source:     {intake.get('data_source', '—')}\n"
        f"S3 — Operational Scope:        {intake.get('audience', '—')}\n"
        f"S3 — Human Oversight Model:    {intake.get('oversight', '—')}\n"
        "=== END OF WIZARD METADATA ===\n"
    )

    description = (intake.get("description") or "").strip()
    pasted_block = (
        f"\n--- USER-PROVIDED PRODUCT DESCRIPTION ---\n{description}\n"
        if description else ""
    )

    blueprint_text = intake.get("evidence_text", "")
    combined_blueprint = (
        wizard_metadata
        + pasted_block
        + (f"\n--- UPLOADED DOCUMENT TEXT ---\n{blueprint_text}" if blueprint_text else "")
    )

    checkbox_summary = (
        f"- Industry Sector: {intake.get('industry', '—')}\n"
        f"- Biometric / Emotion Processing: {intake.get('biometric', '—')}\n"
        f"- Predictive Policing / Profiling: {intake.get('policing', '—')}\n"
        f"- Training Data Provenance: {intake.get('data_source', '—')}\n"
        f"- Deployment Audience: {intake.get('audience', '—')}\n"
        f"- Human Oversight Guardrails: {intake.get('oversight', '—')}"
    )

    final_report_text = None

    try:
        # ── Agent A: Ingestion Analyst ────────────────────────────────────────
        with st.spinner(assess.get("spinner_a", "Agent A is analysing...")):
            prompt_a = (
                "You are Agent A — the Ingestion Analyst in a multi-agent EU AI Act compliance pipeline.\n\n"
                "Your sole task is to produce a structured TECHNICAL PROFILE of the target AI system "
                "based on the user inputs below. Cover exactly these four dimensions:\n"
                "1. Core Data Pipelines\n"
                "2. Training Data Recency & Origin\n"
                "3. Automation Thresholds\n"
                "4. Systemic Decision Footprint\n\n"
                f"SYSTEM RISK CLASSIFICATION: {system_risk_status} ({risk_citation})\n\n"
                f"DEEP INTAKE CONFIGURATION:\n{checkbox_summary}\n\n"
                f"SYSTEM INTAKE PAYLOAD:\n{combined_blueprint if combined_blueprint.strip() else '[No intake data provided]'}\n\n"
                "Output only the structured technical profile. Be precise and concise."
            )
            profile_a = call_gemini_with_retry(client, prompt_a)
            if not profile_a:
                raise RuntimeError("Agent A returned no output — pipeline halted.")

        # ── Agent B: Regulatory Cross-Examiner ────────────────────────────────
        with st.spinner(assess.get("spinner_b", "Agent B is auditing...")):
            law_block = (
                f"\n\nOFFICIAL REGULATORY REFERENCE DOCUMENTS:\n{official_law_context}\n"
                if official_law_context else ""
            )
            prompt_b = (
                "You are Agent B — the Regulatory Cross-Examiner in a multi-agent EU AI Act compliance pipeline.\n\n"
                "Agent A has produced the following technical profile of the target AI system:\n\n"
                f"{profile_a}\n\n"
                f"The deterministic intake classifier has assigned this system the tier: "
                f"{system_risk_status} (primary citation: {risk_citation}).\n\n"
                "Your task: cross-examine this technical profile against EU AI Act law and identify ALL "
                "legal non-compliance risks. You MUST explicitly check and cite findings under:\n"
                "- Article 5 (Prohibited AI Practices)\n"
                "- Article 10 (Data Governance & Training Data Requirements)\n"
                "- Article 14 (Human Oversight Obligations)\n"
                "- Article 50 (Transparency Obligations) where consumer-facing\n"
                "- Any applicable Annex III subsections for high-risk systems\n"
                "- Chapter V (GPAI obligations) where the system is a general-purpose model\n\n"
                f"{ARTICLE_50_GUARDRAIL}\n"
                f"{law_block}"
                "Output: raw legal findings, specific compliance breach maps, and definitive statutory citations. "
                "Be exhaustive and cite chapter/article/paragraph numbers precisely."
            )
            findings_b = call_gemini_with_retry(client, prompt_b)
            if not findings_b:
                raise RuntimeError("Agent B returned no output — pipeline halted.")

        # ── Agent C: Executive Auditor Draftsman ──────────────────────────────
        with st.spinner(assess.get("spinner_c", "Agent C is drafting...")):
            prompt_c = (
                "You are Agent C — the Executive Auditor Draftsman in a multi-agent EU AI Act compliance pipeline.\n\n"
                "Agent B has produced the following raw legal findings:\n\n"
                f"{findings_b}\n\n"
                "Your task: transform these findings into a pristine, authoritative "
                "**EU AI Act Formal Conformity Assessment Report** in clean markdown.\n\n"
                f"OFFICIAL RISK TIER (from the deterministic intake classifier): "
                f"{system_risk_status} — primary citation {risk_citation}. "
                "State this tier verbatim in the Executive Summary as one of the four "
                "official EU AI Act tiers: Prohibited Practices, High-Risk Systems, "
                "Specific Transparency Risks, or Minimal Risk.\n\n"
                f"SECTOR-SPECIFIC MITIGATION MANDATE for "
                f"{intake.get('industry', 'the selected industry')}: {sector_mitigation} "
                "Weave these sector-specific measures into Section 3 as concrete, "
                "named remediation steps.\n\n"
                "You MUST follow this exact multi-level decimal numbering scheme throughout "
                "the entire document. Do not use plain bullet points or unnumbered lists "
                "anywhere in Sections 1, 2, or 3.\n\n"
                "## Executive Summary\n"
                "Open with a short executive summary header stating the system classification, "
                "primary regulatory citation, and overall compliance verdict.\n\n"
                "## Section 1: Executive Compliance Breach Inventory\n"
                "List every identified regulatory breach using this strict structure:\n"
                "  1.1 [Breach Title]\n"
                "    1.1.1 Systemic Vulnerability: [describe the concrete technical flaw]\n"
                "    1.1.2 Legal Violation: [cite exact Article, paragraph, and Annex]\n"
                "    1.1.3 Severity: [CRITICAL / HIGH / MEDIUM]\n"
                "  1.2 [Next Breach Title]\n"
                "    1.2.1 Systemic Vulnerability: ...\n"
                "    1.2.2 Legal Violation: ...\n"
                "    1.2.3 Severity: ...\n"
                "Continue for every breach found. Prefix each top-level breach with ⚠️.\n\n"
                f"{ARTICLE_50_GUARDRAIL}\n\n"
                "## Section 2: Regulatory Metric Map\n"
                "Evaluate each article using this exact numbered block format — "
                "no tables, no plain bullets:\n"
                "  2.1 Article 5 Compliance Status: [PASS / FAIL / PARTIAL]\n"
                "       Rationale: [one-sentence justification]\n"
                "  2.2 Article 10 Compliance Status: [PASS / FAIL / PARTIAL]\n"
                "       Rationale: ...\n"
                "  2.3 Article 14 Compliance Status: [PASS / FAIL / PARTIAL]\n"
                "       Rationale: ...\n"
                "  2.4 Annex III Compliance Status: [PASS / FAIL / PARTIAL / N/A]\n"
                "       Rationale: ...\n\n"
                "## Section 3: Mandatory Remediation Roadmap\n"
                "Structure the remediation plan as sequentially indexed phases and steps:\n"
                "  3.1 Phase I: Immediate Technical Remediation\n"
                "    Step 3.1.1: [first concrete action — owner, tool, deadline]\n"
                "    Step 3.1.2: [second concrete action]\n"
                "  3.2 Phase II: Lifecycle Logging Architecture\n"
                "    Step 3.2.1: [first concrete action]\n"
                "    Step 3.2.2: [second concrete action]\n"
                "  3.3 Phase III: Governance & Human Oversight Controls\n"
                "    Step 3.3.1: [first concrete action]\n"
                "    Step 3.3.2: [second concrete action]\n"
                "Add further phases as required by the severity of findings.\n\n"
                "## Closing Certification Statement\n"
                "End with a formal certification paragraph stating the audit scope, "
                "methodology, and the conditions under which conformity may be declared.\n\n"
                "CRITICAL FORMATTING RULE: Every finding, metric row, and roadmap item "
                "MUST carry its decimal index (1.X / 1.X.X, 2.X, 3.X / Step 3.X.X) "
                "as a hard prefix in the output text so the structure is preserved "
                "identically when rendered in both the markdown dashboard and the PDF export."
            )
            final_report_text = call_gemini_with_retry(client, prompt_c)
            if not final_report_text:
                raise RuntimeError("Agent C returned no output — pipeline halted.")

    except Exception as pipeline_err:
        st.error(f"Multi-Agent Pipeline Failure. Details: {pipeline_err}")

    if final_report_text:
        st.session_state.report_markdown = final_report_text
        st.session_state.pdf_data_bytes = generate_pdf_report(
            final_report_text,
            risk_tier=system_risk_status,
            citation=risk_citation,
            company=intake.get("company") or None,
            industry=intake.get("industry") or None,
        )
        st.session_state.risk_tier = system_risk_status
        st.session_state.risk_citation = risk_citation
        st.session_state.audit_date = date.today().isoformat()
        # Reset the obligations sheet so a fresh audit repopulates it
        st.session_state.pop("obligations_df", None)
        st.session_state.audit_complete = True
        st.rerun()


def _render_command_center(cc: dict):
    """Post-assessment governance workspace: overview, obligations, calendar."""
    intake_done = st.session_state.get("intake", {})
    tier_done = st.session_state.get("risk_tier", "—")
    citation_done = st.session_state.get("risk_citation", "—")
    try:
        audit_dt = date.fromisoformat(st.session_state.get("audit_date", ""))
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

        st.markdown(st.session_state.report_markdown)

        if st.button(cc.get("save_button", "💾 Save Report")):
            ok, msg, _ = save_report_to_downloads(st.session_state.pdf_data_bytes)
            if ok:
                st.success(msg)
            else:
                st.error(msg)

    # ── COMMAND CENTER TAB 2: Obligations Sheet ───────────────────────────────
    with cc_obligations:
        st.markdown(f"""
        <div class="section-label" style="margin-bottom:0.4rem;">{cc.get("obligations_label", "")}</div>
        <div class="section-sub">{cc.get("obligations_sub", "")}</div>
        """, unsafe_allow_html=True)

        if "obligations_df" not in st.session_state:
            st.session_state.obligations_df = build_obligations_register(
                intake_done, tier_done
            )

        edited_df = st.data_editor(
            st.session_state.obligations_df,
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
        st.session_state.obligations_df = edited_df

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
    """GDPR Article 28 data agreements + mandatory corporate impressum blocks."""
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

    # ── GDPR Article 28 data agreements ───────────────────────────────────────
    gdpr = _c("legal", "gdpr", default={})
    st.markdown(f"### {gdpr.get('heading', '')}")
    st.markdown(gdpr.get("body", ""))

    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

    # ── Corporate imprint (Impressum) ─────────────────────────────────────────
    imprint = _c("legal", "imprint", default={})
    st.markdown(f"### {imprint.get('heading', '')}")
    st.markdown(imprint.get("body", ""))

    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

    # ── Liability disclaimer block ────────────────────────────────────────────
    disclaimer = _c("legal", "disclaimer", default={})
    st.markdown(f"### {disclaimer.get('heading', '')}")
    with st.container(border=True):
        st.markdown(disclaimer.get("body", ""))
