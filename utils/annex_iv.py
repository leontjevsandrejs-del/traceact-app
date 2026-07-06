"""
Annex IV technical-documentation reconciliation scanner.

Deterministically checks uploaded corporate documentation for the presence
and depth of every mandatory Annex IV component of Regulation (EU) 2024/1689.
The scan is evidence-based (keyword-cluster detection over the actual
uploaded text), so downstream agents receive hard PRESENT / SHALLOW / MISSING
verdicts instead of being free to assume or hallucinate coverage.

Also builds the "Clarification Request Matrix" for ambiguous intakes: when
client data cannot support a definitive finding, the pipeline asks targeted
questions instead of guessing.
"""

import re
from dataclasses import dataclass

# Minimum matched-keyword hits for a section to count as more than a mention.
_DEPTH_THRESHOLD = 3

# Each Annex IV component: (id, title, citation, keyword clusters, mitigation)
ANNEX_IV_COMPONENTS = [
    {
        "id": "general_description",
        "title": "General system description & intended purpose",
        "citation": "Annex IV, point 1",
        "keywords": [
            "intended purpose", "intended use", "system description",
            "product description", "version", "release", "deployer",
            "hardware", "instructions for use", "market",
        ],
        "mitigation": (
            "Draft a system datasheet covering intended purpose, provider "
            "identity, version lineage, hardware requirements, and "
            "instructions for use (Annex IV pt. 1(a)–(h))."
        ),
    },
    {
        "id": "architecture",
        "title": "System architecture & development process",
        "citation": "Annex IV, point 2(a)-(c)",
        "keywords": [
            "architecture", "component", "pipeline", "integration",
            "development process", "design specification", "computational",
            "third-party", "pre-trained", "api", "model card", "diagram",
            "microservice", "infrastructure",
        ],
        "mitigation": (
            "Produce an architecture dossier: component diagrams, third-party "
            "tool inventory, design specifications, and the development "
            "methods used (Annex IV pt. 2(a)–(c))."
        ),
    },
    {
        "id": "algorithmic_logic",
        "title": "Algorithmic logic, model parameters & key design choices",
        "citation": "Annex IV, point 2(b)",
        "keywords": [
            "algorithm", "model", "logic", "parameter", "weight",
            "classification", "optimisation", "optimization", "loss",
            "trade-off", "assumption", "feature", "inference", "threshold",
        ],
        "mitigation": (
            "Document the general logic of the system: main classification/"
            "decision choices, key design assumptions, optimisation targets, "
            "and parameter rationale (Annex IV pt. 2(b))."
        ),
    },
    {
        "id": "data_governance",
        "title": "Data governance — training, validation & testing datasets",
        "citation": "Annex IV, point 2(d) / Article 10",
        "keywords": [
            "training data", "dataset", "validation", "testing", "test set",
            "provenance", "labelling", "labeling", "annotation", "cleaning",
            "bias", "representativeness", "data governance", "datasheet",
        ],
        "mitigation": (
            "Create datasheets for every training/validation/testing dataset: "
            "origin, scope, collection methodology, labelling procedures, and "
            "bias examination records (Annex IV pt. 2(d), Article 10)."
        ),
    },
    {
        "id": "human_oversight",
        "title": "Human oversight design & measures",
        "citation": "Annex IV, point 2(e) / Article 14",
        "keywords": [
            "human oversight", "human review", "override", "human-in-the-loop",
            "intervention", "operator", "stop button", "kill switch",
            "escalation", "supervisor", "manual approval", "reviewer",
        ],
        "mitigation": (
            "Specify the Article 14 oversight design: who can intervene, the "
            "override/interrupt mechanism, operator competence requirements, "
            "and the technical measures facilitating output interpretation "
            "(Annex IV pt. 2(e))."
        ),
    },
    {
        "id": "accuracy_robustness",
        "title": "Performance metrics — accuracy, robustness, foreseeable misuse",
        "citation": "Annex IV, points 2(g) & 3 / Article 15",
        "keywords": [
            "accuracy", "precision", "recall", "f1", "benchmark", "metric",
            "performance", "robustness", "error rate", "failure mode",
            "misuse", "limitation", "validation result", "evaluation",
        ],
        "mitigation": (
            "Publish declared accuracy metrics with their measurement "
            "methodology, robustness test results, known limitations, and "
            "foreseeable-misuse analysis (Annex IV pts. 2(g), 3; Article 15)."
        ),
    },
    {
        "id": "cybersecurity",
        "title": "Cybersecurity measures & resilience metrics",
        "citation": "Annex IV, point 2(h) / Article 15(5)",
        "keywords": [
            "cybersecurity", "security", "encryption", "access control",
            "penetration test", "adversarial", "poisoning", "vulnerability",
            "incident response", "authentication", "hardening", "threat model",
        ],
        "mitigation": (
            "Document the cybersecurity posture: threat model, adversarial-"
            "robustness measures (data poisoning, model evasion, extraction), "
            "access controls, and incident-response metrics (Article 15(5))."
        ),
    },
    {
        "id": "risk_management",
        "title": "Risk management system documentation",
        "citation": "Annex IV, point 5 / Article 9",
        "keywords": [
            "risk management", "risk assessment", "risk register", "hazard",
            "mitigation", "residual risk", "iterative", "risk analysis",
            "impact assessment", "fria",
        ],
        "mitigation": (
            "Stand up the Article 9 continuous risk-management system with a "
            "living risk register, mitigation tracking, and residual-risk "
            "acceptance records (Annex IV pt. 5)."
        ),
    },
    {
        "id": "lifecycle_monitoring",
        "title": "Lifecycle change management & post-market monitoring plan",
        "citation": "Annex IV, points 6-9 / Article 72",
        "keywords": [
            "post-market", "monitoring", "lifecycle", "drift", "logging",
            "audit trail", "change management", "versioning", "declaration of "
            "conformity", "standards", "en iso", "retraining",
        ],
        "mitigation": (
            "Define the post-market monitoring plan (Article 72), automatic "
            "event-logging retention (Article 12), applied harmonised "
            "standards list, and the EU declaration of conformity workflow "
            "(Annex IV pts. 6–9)."
        ),
    },
]


@dataclass
class ComponentFinding:
    component_id: str
    title: str
    citation: str
    status: str          # PRESENT | SHALLOW | MISSING
    hits: int
    matched_terms: list
    mitigation: str


def scan_documentation(evidence_text: str) -> list[ComponentFinding]:
    """
    Scan uploaded documentation text against every Annex IV component.
    Returns one finding per component with a deterministic status:
        PRESENT — multiple distinct keyword clusters matched (real depth)
        SHALLOW — mentioned but lacks technical specificity
        MISSING — no evidence found → Critical Regulatory Deficiency
    """
    text = (evidence_text or "").lower()
    findings = []
    for comp in ANNEX_IV_COMPONENTS:
        matched = sorted({
            kw for kw in comp["keywords"]
            if re.search(r"(?<![a-z])" + re.escape(kw.lower()), text)
        })
        hits = len(matched)
        if hits >= _DEPTH_THRESHOLD:
            status = "PRESENT"
        elif hits >= 1:
            status = "SHALLOW"
        else:
            status = "MISSING"
        findings.append(ComponentFinding(
            component_id=comp["id"],
            title=comp["title"],
            citation=comp["citation"],
            status=status,
            hits=hits,
            matched_terms=matched,
            mitigation=comp["mitigation"],
        ))
    return findings


def findings_summary_block(findings: list[ComponentFinding],
                           had_documentation: bool) -> str:
    """Render the deterministic scan as a text block for agent prompts."""
    if not had_documentation:
        return (
            "=== ANNEX IV DOCUMENTATION SCAN ===\n"
            "NO TECHNICAL DOCUMENTATION WAS UPLOADED. Every Annex IV component "
            "must be treated as a CRITICAL REGULATORY DEFICIENCY — do not "
            "assume any documentation exists.\n"
            "=== END OF SCAN ===\n"
        )
    lines = ["=== ANNEX IV DOCUMENTATION SCAN (deterministic, evidence-based) ==="]
    for f in findings:
        terms = ", ".join(f.matched_terms[:6]) if f.matched_terms else "none"
        lines.append(
            f"[{f.status}] {f.title} ({f.citation}) — "
            f"evidence terms found: {terms}"
        )
    lines.append(
        "RULES: components marked MISSING are Critical Regulatory "
        "Deficiencies. Components marked SHALLOW lack technical depth and "
        "must be flagged as deficiencies requiring detail. NEVER upgrade a "
        "status; never invent documentation content that is not evidenced."
    )
    lines.append("=== END OF SCAN ===")
    return "\n".join(lines) + "\n"


# ══════════════════════════════════════════════════════════════════════════════
# Clarification Request Matrix — fallback for ambiguous client data
# ══════════════════════════════════════════════════════════════════════════════

def build_clarification_matrix(intake: dict,
                               findings: list[ComponentFinding],
                               had_documentation: bool) -> list[dict]:
    """
    Detect ambiguity in the intake and return targeted clarification
    requests. Each entry: {topic, question, why_it_matters, citation}.
    The pipeline includes this matrix in the report INSTEAD of guessing.
    """
    matrix = []

    if intake.get("social_scoring", "").lower().startswith("unsure"):
        matrix.append({
            "topic": "Social scoring exposure",
            "question": (
                "Are person-level scores produced by the system ever reused in "
                "a social context unrelated to the one in which the data was "
                "generated, or do they lead to treatment disproportionate to "
                "the scored behaviour?"),
            "why_it_matters": (
                "Determines whether the prohibition in Article 5(1)(c) "
                "applies. If yes, the practice is banned outright."),
            "citation": "Article 5(1)(c)",
        })

    if "provenance unknown" in intake.get("data_source", ""):
        matrix.append({
            "topic": "Training-data provenance",
            "question": (
                "Request the vendor's training-data summary: data origin, "
                "collection method, whether facial images were scraped, and "
                "whether special-category data is present."),
            "why_it_matters": (
                "Unknown provenance blocks the Article 10 data-governance "
                "assessment and may conceal an Article 5(1)(e) scraping "
                "violation."),
            "citation": "Article 10 / Article 25",
        })

    if not had_documentation:
        matrix.append({
            "topic": "Technical documentation package",
            "question": (
                "Provide the technical documentation for the system: "
                "architecture description, dataset datasheets, oversight "
                "design, accuracy metrics, and cybersecurity measures."),
            "why_it_matters": (
                "No Annex IV reconciliation is possible without the source "
                "documents; every component currently defaults to a Critical "
                "Regulatory Deficiency."),
            "citation": "Article 11 / Annex IV",
        })
    else:
        shallow = [f for f in findings if f.status == "SHALLOW"]
        for f in shallow[:4]:
            matrix.append({
                "topic": f"Annex IV depth — {f.title}",
                "question": (
                    f"The uploaded documentation mentions this area "
                    f"(terms: {', '.join(f.matched_terms[:4])}) but lacks "
                    f"verifiable technical detail. Provide the underlying "
                    f"specification or metrics."),
                "why_it_matters": (
                    "A conformity assessment cannot pass on assertions alone; "
                    "auditors require inspectable technical depth."),
                "citation": f.citation,
            })

    if "Human-on-the-loop" in intake.get("oversight", ""):
        matrix.append({
            "topic": "Oversight intervention latency",
            "question": (
                "Quantify the human intervention path: maximum delay between "
                "an anomalous output and effective human override, and "
                "whether the overseer can halt the system entirely."),
            "why_it_matters": (
                "Article 14(4) requires oversight measures to be 'effective' "
                "— delayed monitoring may not satisfy the standard for the "
                "system's risk profile."),
            "citation": "Article 14(4)",
        })

    return matrix


def clarification_block(matrix: list[dict]) -> str:
    """Render the matrix as a text block for agent prompts / reports."""
    if not matrix:
        return ""
    lines = ["=== CLARIFICATION REQUEST MATRIX (ambiguous intake — do not guess) ==="]
    for i, row in enumerate(matrix, 1):
        lines.append(f"CR-{i} [{row['citation']}] {row['topic']}: "
                     f"{row['question']} (Why: {row['why_it_matters']})")
    lines.append("=== END OF MATRIX ===")
    return "\n".join(lines) + "\n"
