"""
Standalone single-shot audit helper (legacy CLI/API lane).

The Streamlit app uses the full multi-agent pipeline in ui_layouts.py; this
module provides the same grounding guarantees for programmatic callers:
deterministic classification via utils.risk_engine, Annex IV reconciliation
via utils.annex_iv, and the cite-your-source constraint on the model call.
"""

from google import genai

from utils.gemini_client import GEMINI_MODEL, call_gemini_with_retry
from utils.knowledge import load_legal_knowledge_base
from utils.risk_engine import classify_risk
from utils.annex_iv import (
    scan_documentation,
    findings_summary_block,
    build_clarification_matrix,
    clarification_block,
)


def get_knowledge_base_text():
    """Full tagged legal corpus (.txt and Annex .pdf files, cached)."""
    return load_legal_knowledge_base()


def run_audit(
    client: genai.Client,
    manual_triage_data,
    evidence_text,
    intake: dict | None = None,
    model_name: str | None = None,
):
    """
    Run a grounded single-shot audit.

    ``intake`` (optional) is the structured wizard dict; when provided the
    deterministic risk engine pre-classifies the system and the model is
    barred from re-classifying.
    """
    if client is None:
        return "Error: Gemini API key is missing."

    kb_context = get_knowledge_base_text()
    intake = intake or {}

    classification_block = ""
    if intake:
        classification = classify_risk(intake)
        pathway = "\n".join(f"  {s}" for s in classification.decision_path)
        classification_block = (
            "=== DETERMINISTIC STATUTORY CLASSIFICATION (authoritative — do not alter) ===\n"
            f"TIER: {classification.tier}\n"
            f"PRIMARY CITATION: {classification.citation}\n"
            f"DECISION PATHWAY:\n{pathway}\n"
            "=== END OF CLASSIFICATION ===\n\n"
        )

    had_documentation = bool((evidence_text or "").strip())
    findings = scan_documentation(evidence_text or "")
    annex_iv_block = findings_summary_block(findings, had_documentation)
    matrix = build_clarification_matrix(intake, findings, had_documentation)
    matrix_block = clarification_block(matrix)

    prompt = f"""You are a precision EU AI Act conformity auditor. You operate under a strict
zero-mistake protocol:

CITATION PROTOCOL (binding):
1. Every classification or legal assertion must carry an explicit statutory
   anchor — Article, paragraph, Recital, or Annex point of Regulation (EU)
   2024/1689.
2. If you cannot anchor a statement to a specific provision, do not make it;
   write "INSUFFICIENT EVIDENCE — clarification required" instead.
3. Never invent Article numbers or describe documentation content that the
   ANNEX IV DOCUMENTATION SCAN marks as MISSING or SHALLOW.
4. Where a deterministic classification block is present, it is authoritative
   — analyse within the tier, never re-classify.

{classification_block}Reference knowledge base (EU AI Act source documents):
{kb_context}

{annex_iv_block}
{matrix_block}
Manual triage data provided by the user:
{manual_triage_data}

System architecture and data-governance evidence uploaded by the user:
{evidence_text}

Your tasks:
1. Confirm the risk tier (Prohibited / High-Risk / Transparency-Limited /
   Minimal) with the exact statutory pathway that produces it.
2. Cite the exact provision for every finding.
3. List missing Annex IV components as 'Critical Regulatory Deficiency'
   entries with actionable mitigation steps — never assume undocumented
   coverage exists.
4. Restate any open Clarification Request Matrix items instead of guessing.

Output format:
### Classification: [tier]

### Statutory Pathway
[numbered steps with citations]

### Critical Regulatory Deficiencies
*   [component — citation — mitigation]

### Action Required
*   [action — citation]

### Open Clarification Requests
*   [CR items, if any]
"""

    try:
        return call_gemini_with_retry(
            client,
            prompt,
            model_name=model_name or GEMINI_MODEL,
        )
    except Exception as err:
        return f"An error occurred during the audit: {err}"
