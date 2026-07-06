"""
Four-tier EU AI Act conformity report PDF builder.

Tier 1 — Executive Risk Level Status (deterministic banner)
Tier 2 — The Legal "Why" (the exact statutory decision pathway from the
          deterministic risk engine, plus the grounded agent narrative)
Tier 3 — Gap Analysis Spreadsheet (Annex IV component table, deterministic)
Tier 4 — Engineering Action Plan (grounded agent remediation output)

Zero-mistake design: Tiers 1, 3, the statutory pathway of Tier 2, and the
Clarification Request Matrix are rendered directly from deterministic Python
structures — the LLM cannot alter them. Only the narrative sections flow
from the (citation-constrained) agent pipeline.
"""

import os
import re
from datetime import date

from fpdf import FPDF

_C_SLATE   = (26,  46,  64)   # Deep Slate Blue  — primary headers
_C_CHAR    = (60,  60,  60)   # Soft Charcoal    — body text
_C_GRAY_BG = (245, 246, 248)  # Muted Light Gray — fills
_C_ACCENT  = (92, 130, 165)   # Steel accent     — rule lines
_C_WHITE   = (255, 255, 255)

# Tier banner palettes keyed by tier_code
_TIER_COLORS = {
    "prohibited": ((127, 29, 29),  _C_WHITE),   # dark red
    "high":       ((154, 52, 18),  _C_WHITE),   # burnt orange
    "limited":    ((30, 64, 175),  _C_WHITE),   # blue
    "minimal":    ((6, 78, 59),    _C_WHITE),   # green
}

_STATUS_COLORS = {
    "PRESENT": (6, 95, 70),
    "SHALLOW": (146, 64, 14),
    "MISSING": (153, 27, 27),
    "EXEMPT": _C_SLATE,   # charcoal — not a deficiency alert
}

_MINIMAL_RISK_EXEMPT_MITIGATION = (
    "No mandatory technical dossier required under Article 11 for Minimal Risk "
    "systems. Voluntary alignment with Article 95 (Codes of Conduct) is "
    "recommended for institutional-grade AI governance."
)


def _is_minimal_risk(classification) -> bool:
    if classification is None:
        return False
    return (
        getattr(classification, "tier_code", None) == "minimal"
        or getattr(classification, "tier", "") == "MINIMAL RISK"
    )


def annex_iv_row_display(finding, classification=None, had_documentation: bool = False):
    """
    Resolve the Tier 3 table status and mitigation text for one Annex IV row.

    Minimal-risk systems are not subject to Article 11 / Annex IV dossier
    duties, so every component is marked EXEMPT regardless of upload state.
    """
    if _is_minimal_risk(classification):
        return "EXEMPT", _MINIMAL_RISK_EXEMPT_MITIGATION
    status = "MISSING" if not had_documentation else finding.status
    return status, finding.mitigation


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
    text = str(text)
    text = text.replace("\u26a0\ufe0f ", "").replace("\u26a0\ufe0f", "")
    text = text.replace("\u26a0", "").replace("\ufe0f", "")
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2014", "--").replace("\u2013", "-")
    text = text.replace("\u2192", "->").replace("\u00a7", "s.")
    return text.encode("latin-1", errors="ignore").decode("latin-1")


def _usable_width(pdf) -> float:
    pdf.set_x(pdf.l_margin)
    return pdf.w - pdf.l_margin - pdf.r_margin


def _tier_heading(pdf, label: str) -> None:
    page_h = pdf.h - pdf.b_margin
    if pdf.get_y() > page_h - 24:
        pdf.add_page()
    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 13.5)
    pdf.set_text_color(*_C_SLATE)
    pdf.set_draw_color(*_C_ACCENT)
    pdf.set_line_width(0.45)
    pdf.multi_cell(_usable_width(pdf), 7, _sanitise(label))
    pdf.set_x(pdf.l_margin)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(3)


def _render_markdown_body(pdf, insights_text: str) -> None:
    """Parse agent markdown line-by-line and render with styling."""
    page_h = pdf.h - pdf.b_margin

    for raw_line in (insights_text or "").splitlines():
        line = raw_line.rstrip()

        if line.startswith("## ") or line.startswith("# "):
            label = line.lstrip("#").strip()
            if pdf.get_y() > page_h - 20:
                pdf.add_page()
            pdf.ln(4)
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_text_color(*_C_SLATE)
            pdf.multi_cell(_usable_width(pdf), 7, _sanitise(label))
            pdf.ln(2)

        elif line.startswith("### "):
            label = line[4:].strip()
            if pdf.get_y() > page_h - 14:
                pdf.add_page()
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 10.5)
            pdf.set_text_color(*_C_SLATE)
            pdf.multi_cell(_usable_width(pdf), 6, _sanitise(label))
            pdf.ln(1)

        elif re.match(r"^\s*\d+\.\d", line):
            if pdf.get_y() > page_h - 10:
                pdf.add_page()
            pdf.set_fill_color(*_C_GRAY_BG)
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(*_C_SLATE)
            pdf.multi_cell(_usable_width(pdf), 7,
                           _sanitise(line.strip()), fill=True)

        elif line.strip() == "":
            pdf.ln(2)

        else:
            pdf.set_text_color(*_C_CHAR)
            clean = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
            if re.match(r"^\*\*", line.strip()):
                pdf.set_font("Helvetica", "B", 10)
            else:
                pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(_usable_width(pdf), 6, _sanitise(clean))


def _render_tier1(pdf, classification, company, industry, disclaimer_meta):
    """Tier 1 — Executive Risk Level Status banner + metadata card."""
    bg, fg = _TIER_COLORS.get(classification.tier_code, (_C_SLATE, _C_WHITE))
    pdf.set_fill_color(*bg)
    pdf.set_text_color(*fg)
    pdf.set_font("Helvetica", "B", 14)
    pdf.multi_cell(_usable_width(pdf), 12,
                   _sanitise(f"TIER 1 - EXECUTIVE RISK STATUS: {classification.tier}"),
                   fill=True, align="C")
    pdf.ln(4)

    pdf.set_fill_color(*_C_GRAY_BG)

    def _meta_row(label, value):
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*_C_SLATE)
        pdf.cell(48, 8, label, fill=True)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*_C_CHAR)
        pdf.cell(0, 8, _sanitise(value), ln=True, fill=True)

    _meta_row("Generation Date:", date.today().strftime("%B %d, %Y"))
    if company:
        _meta_row("Organisation:", company)
    if industry:
        _meta_row("Industry Sector:", industry)
    _meta_row("EU AI Act Risk Tier:", classification.tier)
    _meta_row("Primary Citation:", classification.citation)
    _meta_row("Report Type:", "Automated Readiness Indicator")
    _meta_row("Legal Status:", disclaimer_meta or "Not Licensed Legal Counsel")
    pdf.ln(4)


def _render_tier2_pathway(pdf, classification):
    """Tier 2 — deterministic statutory decision pathway."""
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_text_color(*_C_CHAR)
    pdf.multi_cell(_usable_width(pdf), 5.5, _sanitise(
        "The classification above was produced by a deterministic statutory "
        "cascade, executed in the mandatory order of Regulation (EU) "
        "2024/1689. Each stage below documents the exact legal test applied "
        "and its outcome:"))
    pdf.ln(2)

    page_h = pdf.h - pdf.b_margin
    for step in classification.decision_path:
        if pdf.get_y() > page_h - 16:
            pdf.add_page()
        pdf.set_fill_color(*_C_GRAY_BG)
        pdf.set_font("Helvetica", "", 8.8)
        pdf.set_text_color(*_C_SLATE)
        pdf.multi_cell(_usable_width(pdf), 5.2, _sanitise(step), fill=True)
        pdf.ln(1.5)

    if classification.article5_triggers:
        pdf.ln(1)
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(153, 27, 27)
        pdf.multi_cell(_usable_width(pdf), 6,
                       "Triggered Article 5 prohibitions:")
        pdf.set_font("Helvetica", "", 9)
        for cite, finding in classification.article5_triggers:
            pdf.set_text_color(*_C_CHAR)
            pdf.multi_cell(_usable_width(pdf), 5.5,
                           _sanitise(f"- {cite}: {finding}"))
    if classification.exemption and classification.exemption.get("applicable"):
        pdf.ln(1)
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(*_C_SLATE)
        pdf.multi_cell(_usable_width(pdf), 6,
                       "Article 6(3) derogation record:")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*_C_CHAR)
        pdf.multi_cell(_usable_width(pdf), 5.5,
                       _sanitise(classification.exemption.get("reason", "")))


def _render_tier3_gap_table(pdf, annex_iv_findings, had_documentation,
                            classification=None):
    """Tier 3 — Annex IV gap-analysis table (deterministic scan results)."""
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_text_color(*_C_CHAR)
    if _is_minimal_risk(classification):
        intro = (
            "Annex IV technical-documentation obligations under Article 11 apply "
            "only to high-risk AI systems. This system is classified MINIMAL "
            "RISK; every component below is marked EXEMPT. Voluntary alignment "
            "with Article 95 (Codes of Conduct) remains recommended."
        )
    elif had_documentation:
        intro = (
            "Deterministic reconciliation of the uploaded technical documentation "
            "against every mandatory Annex IV component. MISSING items are "
            "Critical Regulatory Deficiencies; SHALLOW items were mentioned but "
            "lack audit-grade technical depth."
        )
    else:
        intro = (
            "No technical documentation was uploaded. Every Annex IV component "
            "defaults to MISSING (Critical Regulatory Deficiency) until evidence "
            "is provided."
        )
    pdf.multi_cell(_usable_width(pdf), 5.5, _sanitise(intro))
    pdf.ln(2)

    col_w = {"comp": 62, "cite": 38, "status": 20, "fix": 50}
    page_h = pdf.h - pdf.b_margin

    def _header_row():
        pdf.set_fill_color(*_C_SLATE)
        pdf.set_text_color(*_C_WHITE)
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(col_w["comp"],   7, "Annex IV Component", fill=True, border=1)
        pdf.cell(col_w["cite"],   7, "Legal Basis", fill=True, border=1)
        pdf.cell(col_w["status"], 7, "Status", fill=True, border=1)
        pdf.cell(col_w["fix"],    7, "Required Mitigation", fill=True,
                 border=1, ln=True)

    _header_row()
    for f in annex_iv_findings:
        status, mitigation = annex_iv_row_display(
            f, classification, had_documentation)
        # Measure row height across the wrapped columns
        pdf.set_font("Helvetica", "", 7.6)
        comp_lines = pdf.multi_cell(col_w["comp"], 4.4, _sanitise(f.title),
                                    split_only=True)
        fix_lines = pdf.multi_cell(col_w["fix"], 4.4, _sanitise(mitigation),
                                   split_only=True)
        row_h = max(len(comp_lines), len(fix_lines), 2) * 4.4

        if pdf.get_y() + row_h > page_h:
            pdf.add_page()
            _header_row()

        y0 = pdf.get_y()
        x0 = pdf.l_margin

        pdf.set_text_color(*_C_CHAR)
        pdf.set_xy(x0, y0)
        pdf.multi_cell(col_w["comp"], 4.4, _sanitise(f.title), border=1)

        pdf.set_xy(x0 + col_w["comp"], y0)
        pdf.multi_cell(col_w["cite"], row_h, _sanitise(f.citation), border=1)

        pdf.set_xy(x0 + col_w["comp"] + col_w["cite"], y0)
        pdf.set_font("Helvetica", "B", 7.6)
        pdf.set_text_color(*_STATUS_COLORS.get(status, _C_CHAR))
        pdf.multi_cell(col_w["status"], row_h, status, border=1, align="C")

        pdf.set_font("Helvetica", "", 7.6)
        pdf.set_text_color(*_C_CHAR)
        pdf.set_xy(x0 + col_w["comp"] + col_w["cite"] + col_w["status"], y0)
        pdf.multi_cell(col_w["fix"], 4.4, _sanitise(mitigation), border=1)

        pdf.set_y(y0 + row_h)
    pdf.ln(2)


def _render_clarification_matrix(pdf, matrix):
    """Clarification Request Matrix — rendered instead of guessed answers."""
    if not matrix:
        return
    _tier_heading(pdf, "Clarification Request Matrix - Outstanding Evidence")
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_text_color(*_C_CHAR)
    pdf.multi_cell(_usable_width(pdf), 5.5, _sanitise(
        "The intake contained ambiguities that cannot be resolved without "
        "further client input. In line with the zero-assumption audit "
        "protocol, the following targeted requests are issued instead of "
        "speculative findings:"))
    pdf.ln(2)
    page_h = pdf.h - pdf.b_margin
    for i, row in enumerate(matrix, 1):
        if pdf.get_y() > page_h - 22:
            pdf.add_page()
        pdf.set_fill_color(*_C_GRAY_BG)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*_C_SLATE)
        pdf.multi_cell(_usable_width(pdf), 6,
                       _sanitise(f"CR-{i}  [{row['citation']}]  {row['topic']}"),
                       fill=True)
        pdf.set_font("Helvetica", "", 8.8)
        pdf.set_text_color(*_C_CHAR)
        pdf.multi_cell(_usable_width(pdf), 5.2,
                       _sanitise(f"Request: {row['question']}"))
        pdf.set_font("Helvetica", "I", 8.4)
        pdf.multi_cell(_usable_width(pdf), 5,
                       _sanitise(f"Regulatory relevance: {row['why_it_matters']}"))
        pdf.ln(2)


def generate_pdf_report(final_report_text,
                        classification=None,
                        annex_iv_findings=None,
                        had_documentation=False,
                        clarification_matrix=None,
                        company=None,
                        industry=None,
                        disclaimer_line=None,
                        legal_narrative=None,
                        action_plan=None):
    """
    Build the 4-tier conformity report.

    ``final_report_text`` (full agent markdown) is used as the narrative when
    the split ``legal_narrative`` / ``action_plan`` sections are not provided,
    preserving backward compatibility with the legacy single-blob flow.
    """
    pdf = _AuditPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_margins(left=20, top=20, right=20)
    pdf.add_page()

    # ── Cover title ───────────────────────────────────────────────────────────
    pdf.set_fill_color(*_C_SLATE)
    pdf.set_text_color(*_C_WHITE)
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 14, "EU AI Act Formal Conformity Assessment Report",
             ln=True, fill=True, align="C")
    pdf.ln(4)

    # ── Tier 1 ────────────────────────────────────────────────────────────────
    if classification is not None:
        _render_tier1(pdf, classification, company, industry,
                      "Not Licensed Legal Counsel")

    # ── Tier 2 ────────────────────────────────────────────────────────────────
    if classification is not None:
        _tier_heading(pdf, 'Tier 2 - The Legal "Why": Statutory Classification Pathway')
        _render_tier2_pathway(pdf, classification)

    narrative = legal_narrative or final_report_text
    if narrative:
        pdf.ln(2)
        _render_markdown_body(pdf, narrative)

    # ── Tier 3 ────────────────────────────────────────────────────────────────
    if annex_iv_findings is not None:
        _tier_heading(pdf, "Tier 3 - Annex IV Gap Analysis")
        _render_tier3_gap_table(
            pdf, annex_iv_findings, had_documentation, classification)

    # ── Clarification Request Matrix ──────────────────────────────────────────
    _render_clarification_matrix(pdf, clarification_matrix or [])

    # ── Tier 4 ────────────────────────────────────────────────────────────────
    if action_plan:
        _tier_heading(pdf, "Tier 4 - Engineering Action Plan")
        _render_markdown_body(pdf, action_plan)

    # ── Legal disclaimer ──────────────────────────────────────────────────────
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
        _usable_width(pdf), 5,
        _sanitise(disclaimer_line or
                  "Legal disclaimer: This report is an automated readiness "
                  "indicator only and does not constitute official licensed "
                  "legal counsel."))

    return bytes(pdf.output())


def save_report_to_downloads(pdf_bytes: bytes) -> tuple[bool, str, str | None]:
    """
    Write the audit PDF to the user's Downloads folder.
    Returns (success, message, saved_path).
    """
    from datetime import datetime

    from utils.paths import get_downloads_directory

    downloads_dir = get_downloads_directory()
    try:
        downloads_dir.mkdir(parents=True, exist_ok=True)
    except OSError as err:
        return (
            False,
            f"Could not access your Downloads folder at `{downloads_dir}`.\n\n"
            f"Technical detail: `{err}`",
            None,
        )

    candidates = [
        downloads_dir / "EU_AI_Act_Audit_Report.pdf",
        downloads_dir / f"EU_AI_Act_Audit_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
    ]

    last_err: Exception | None = None
    for path in candidates:
        try:
            path.write_bytes(pdf_bytes)
            path_str = str(path)
            if path == candidates[0]:
                return (
                    True,
                    f"✅ Success! Report saved to your Downloads folder:\n`{path_str}`",
                    path_str,
                )
            return (
                True,
                "✅ Report saved with a new filename because the original PDF "
                "is open or locked. Close `EU_AI_Act_Audit_Report.pdf` in your "
                "PDF viewer if you want to overwrite it next time.\n\n"
                f"Saved as:\n`{path_str}`",
                path_str,
            )
        except (PermissionError, OSError) as err:
            last_err = err

    return (
        False,
        "Could not save the report to Downloads. This usually means "
        "`EU_AI_Act_Audit_Report.pdf` is still open in another program "
        "(Adobe, Edge, etc.). Close that file and try again.\n\n"
        f"Target folder: `{downloads_dir}`\n"
        f"Technical detail: `{last_err}`",
        None,
    )
