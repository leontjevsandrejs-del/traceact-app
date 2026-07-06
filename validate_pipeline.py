"""
Offline validation harness for the refactored conformity-audit pipeline.

Runs entirely without network access or a Gemini key:
    1. Deterministic risk-engine classification matrix (statutory cases)
    2. Annex IV documentation scan statuses
    3. Clarification Request Matrix triggers
    4. Four-tier PDF generation (structural integrity, no key errors)
    5. content.json parse + ui_layouts import smoke test

Usage:  python validate_pipeline.py
Exit code 0 = all checks passed.
"""

import json
import sys
import traceback

# Windows consoles default to cp1252 — force UTF-8 so citation glyphs print.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PASSED = 0
FAILED = 0


def check(name: str, condition: bool, detail: str = ""):
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  [PASS] {name}")
    else:
        FAILED += 1
        print(f"  [FAIL] {name}  {detail}")


def base_intake(**overrides) -> dict:
    intake = {
        "industry": "Other / General Business Operations",
        "company": "Validation Corp",
        "role": "Deployer (we use the system)",
        "biometric": "No — the system never touches biometric or emotional data",
        "policing": "No — no predictive policing or profiling datasets are used",
        "social_scoring": "No — the system never scores or ranks people's general behaviour",
        "data_source": "Private enterprise databases (our own or licensed first-party data)",
        "audience": "Internal employees only",
        "oversight": "Human-in-the-loop — a human can override any decision instantly",
        "annex1": "No — standalone software with no product-safety function",
        "function": "Primary decision-making — the system materially drives or "
                    "replaces decisions about natural persons",
    }
    intake.update(overrides)
    return intake


def test_risk_engine():
    print("\n[1] Deterministic risk-engine classification matrix")
    from utils.risk_engine import classify_risk, ANNEX_III_DOMAIN_MAP

    # ── Article 5 boolean hooks ───────────────────────────────────────────────
    r = classify_risk(base_intake(
        policing="Yes — predictive policing (crime-risk forecasting on persons or areas)"))
    check("Art 5(1)(d) predictive policing → PROHIBITED",
          r.tier_code == "prohibited" and r.citation == "Article 5(1)(d)",
          f"got {r.tier_code}/{r.citation}")

    r = classify_risk(base_intake(
        social_scoring="Yes — it scores individuals on social behaviour or personal "
                       "traits, and scores are reused in unrelated contexts or cause "
                       "disproportionate treatment"))
    check("Art 5(1)(c) social scoring → PROHIBITED",
          r.tier_code == "prohibited" and r.citation == "Article 5(1)(c)",
          f"got {r.tier_code}/{r.citation}")

    r = classify_risk(base_intake(
        data_source="Untargeted scraping of facial images (internet or CCTV footage)"))
    check("Art 5(1)(e) untargeted facial scraping → PROHIBITED",
          r.tier_code == "prohibited" and r.citation == "Article 5(1)(e)",
          f"got {r.tier_code}/{r.citation}")

    r = classify_risk(base_intake(
        industry="Employment & HR (hiring, evaluation)",
        biometric="Yes — emotion recognition (mood, stress, engagement inference)"))
    check("Art 5(1)(f) workplace emotion recognition → PROHIBITED",
          r.tier_code == "prohibited" and r.citation == "Article 5(1)(f)",
          f"got {r.tier_code}/{r.citation}")

    r = classify_risk(base_intake(
        industry="Law Enforcement",
        biometric="Yes — biometric identification (face, fingerprint, voice matching)",
        audience="Public infrastructure (utilities, transport, civic services)"))
    check("Art 5(1)(h) real-time remote biometric ID → PROHIBITED",
          r.tier_code == "prohibited" and r.citation == "Article 5(1)(h)",
          f"got {r.tier_code}/{r.citation}")

    # ── Annex I filter (Article 6(1)) ─────────────────────────────────────────
    r = classify_risk(base_intake(
        annex1="Yes — the AI is a safety component of a product covered by EU "
               "harmonised legislation (machinery, medical devices, vehicles, toys, "
               "lifts, radio equipment...)"))
    check("Annex I safety component → HIGH (Art 6(1))",
          r.tier_code == "high" and "Annex I" in r.citation,
          f"got {r.tier_code}/{r.citation}")

    # ── Annex III sector map: all mapped domains classify HIGH ────────────────
    for industry, (domain, cite) in ANNEX_III_DOMAIN_MAP.items():
        r = classify_risk(base_intake(industry=industry))
        check(f"Annex III domain: {industry[:44]}... → HIGH ({cite})",
              r.tier_code == "high" and any(cite == c for _, c in r.annex3_matches),
              f"got {r.tier_code}, matches={r.annex3_matches}")

    # ── Article 6(3) exemption logic ──────────────────────────────────────────
    r = classify_risk(base_intake(
        industry="Employment & HR (hiring, evaluation)",
        function="Narrow procedural task only (document formatting, data structuring, "
                 "translation, deduplication)"))
    check("Art 6(3) narrow task, no profiling → exemption granted (not high)",
          r.tier_code != "high" and r.exemption.get("granted") is True,
          f"got {r.tier_code}, exemption={r.exemption}")

    r = classify_risk(base_intake(
        industry="Employment & HR (hiring, evaluation)",
        policing="Yes — profiling datasets (behavioural scoring of individuals)",
        function="Narrow procedural task only (document formatting, data structuring, "
                 "translation, deduplication)"))
    check("Art 6(3) claimed but profiling → override, stays HIGH",
          r.tier_code == "high" and r.exemption.get("granted") is False
          and "profiling" in r.exemption.get("reason", "").lower(),
          f"got {r.tier_code}, exemption={r.exemption}")

    r = classify_risk(base_intake(industry="Employment & HR (hiring, evaluation)"))
    check("Annex III + primary decision-making → HIGH (no exemption)",
          r.tier_code == "high" and r.exemption.get("granted") is False,
          f"got {r.tier_code}")

    # ── GPAI / Article 50 / minimal ───────────────────────────────────────────
    r = classify_risk(base_intake(industry="General Purpose AI / LLM Development"))
    check("GPAI → limited (Chapter V)",
          r.tier_code == "limited" and "51-55" in r.citation,
          f"got {r.tier_code}/{r.citation}")

    r = classify_risk(base_intake(audience="External consumers / customers"))
    check("Consumer-facing → limited (Article 50(1))",
          r.tier_code == "limited" and r.citation == "Article 50(1)",
          f"got {r.tier_code}/{r.citation}")

    r = classify_risk(base_intake())
    check("Neutral profile → MINIMAL",
          r.tier_code == "minimal", f"got {r.tier_code}")
    check("Decision path documents all cascade stages",
          len(r.decision_path) >= 4 and r.decision_path[0].startswith("STAGE 1"),
          f"path={r.decision_path}")

    # Backward-compatible tuple unpacking
    tier, citation = classify_risk(base_intake())
    check("ClassificationResult tuple-unpacks (tier, citation)",
          isinstance(tier, str) and isinstance(citation, str))


def test_annex_iv():
    print("\n[2] Annex IV documentation scan")
    from utils.annex_iv import (scan_documentation, findings_summary_block,
                                build_clarification_matrix)

    rich_doc = (
        "System architecture: microservice pipeline with three components and "
        "API integration diagram. Algorithmic logic: a gradient-boosted model "
        "whose classification threshold and parameter choices reflect "
        "documented design assumptions and optimisation trade-offs. "
        "Training data provenance: labelled datasets "
        "with validation and testing splits; bias examination performed. "
        "Human oversight: human-in-the-loop reviewer with an override kill "
        "switch and escalation protocol. Accuracy: precision 0.94, recall "
        "0.91, F1 0.92 benchmark on the evaluation set. Cybersecurity: "
        "encryption at rest, access control, adversarial penetration test and "
        "incident response runbook. Risk management: living risk register "
        "with residual risk sign-off and iterative risk assessment. "
        "Post-market monitoring plan with drift detection, audit trail "
        "logging, and change management versioning. Intended purpose and "
        "instructions for use documented per release version for deployers "
        "on standard hardware."
    )
    findings = scan_documentation(rich_doc)
    check("Rich documentation → all 9 components detected",
          len(findings) == 9, f"got {len(findings)}")
    check("Rich documentation → every component PRESENT",
          all(f.status == "PRESENT" for f in findings),
          str([(f.component_id, f.status, f.hits) for f in findings
               if f.status != "PRESENT"]))

    shallow_doc = "We have an algorithm. Security matters to us. We assessed risk."
    findings = scan_documentation(shallow_doc)
    check("Vague documentation → SHALLOW/MISSING only, never PRESENT",
          all(f.status in ("SHALLOW", "MISSING") for f in findings),
          str([(f.component_id, f.status) for f in findings]))

    findings = scan_documentation("")
    check("Empty documentation → all MISSING",
          all(f.status == "MISSING" for f in findings))

    block = findings_summary_block(findings, had_documentation=False)
    check("No-docs scan block declares Critical Regulatory Deficiency",
          "CRITICAL REGULATORY DEFICIENCY" in block.upper())

    matrix = build_clarification_matrix(
        base_intake(
            social_scoring="Unsure — it produces person-level scores but reuse "
                           "context is unclear",
            data_source="Third-party vendor — training data provenance unknown to us",
            oversight="Human-on-the-loop — humans monitor but intervention is delayed",
        ),
        findings, had_documentation=False)
    topics = [m["topic"] for m in matrix]
    check("Clarification matrix: social-scoring ambiguity",
          any("Social scoring" in t for t in topics), str(topics))
    check("Clarification matrix: unknown provenance",
          any("provenance" in t for t in topics), str(topics))
    check("Clarification matrix: missing documentation",
          any("documentation" in t.lower() for t in topics), str(topics))
    check("Clarification matrix: oversight latency",
          any("latency" in t.lower() for t in topics), str(topics))
    check("Every matrix row carries a citation",
          all(m.get("citation") for m in matrix))


def test_minimal_risk_gap_rows():
    print("\n[2b] Minimal-risk Annex IV gap table rows")
    from utils.risk_engine import classify_risk
    from utils.annex_iv import scan_documentation
    from utils.report_gen import annex_iv_row_display, _MINIMAL_RISK_EXEMPT_MITIGATION

    classification = classify_risk(base_intake())
    check("Fixture intake is MINIMAL RISK",
          classification.tier_code == "minimal",
          f"got {classification.tier_code}")

    findings = scan_documentation("")  # all MISSING without minimal override
    statuses = {
        annex_iv_row_display(f, classification, had_documentation=False)[0]
        for f in findings
    }
    mitigations = {
        annex_iv_row_display(f, classification, had_documentation=False)[1]
        for f in findings
    }
    check("Minimal risk: all 9 rows EXEMPT (no false MISSING)",
          statuses == {"EXEMPT"} and len(findings) == 9,
          str(statuses))
    check("Minimal risk: exempt mitigation text applied",
          mitigations == {_MINIMAL_RISK_EXEMPT_MITIGATION})

    # High-risk path unchanged
    hr = classify_risk(base_intake(industry="Employment & HR (hiring, evaluation)"))
    st, mt = annex_iv_row_display(findings[0], hr, had_documentation=False)
    check("High-risk without docs still MISSING",
          st == "MISSING" and mt == findings[0].mitigation,
          f"got {st}")


def test_pdf_generation():
    print("\n[3] Four-tier PDF generation")
    from utils.risk_engine import classify_risk
    from utils.annex_iv import scan_documentation, build_clarification_matrix
    from utils.report_gen import generate_pdf_report

    narrative = (
        "## Executive Summary\n"
        "The system is classified HIGH-RISK [Annex III, point 4]. 3 CRITICAL findings.\n\n"
        "## Section 1: Compliance Breach Inventory\n"
        "1.1 Critical Regulatory Deficiency -- Data governance\n"
        "  1.1.1 Systemic Vulnerability: no dataset datasheets exist\n"
        "  1.1.2 Legal Violation: [Article 10(2)] and [Annex IV, point 2(d)]\n"
        "  1.1.3 Severity: CRITICAL\n\n"
        "## Section 2: Regulatory Metric Map\n"
        "2.1 Article 5 Compliance Status: PASS  Rationale: no prohibited hook [Article 5].\n"
        "2.2 Article 10 Compliance Status: FAIL  Rationale: missing datasheets [Article 10].\n"
    )
    action_plan = (
        "3.1 Phase I: Immediate Technical Remediation (0-30 days)\n"
        "  Step 3.1.1: Build dataset datasheets [Article 10]\n"
        "3.2 Phase II: Documentation Build-Out (30-90 days)\n"
        "  Step 3.2.1: Draft the Annex IV dossier [Article 11]\n"
    )

    scenarios = {
        "high-risk with docs": base_intake(
            industry="Employment & HR (hiring, evaluation)"),
        "prohibited": base_intake(
            policing="Yes — predictive policing (crime-risk forecasting on "
                     "persons or areas)"),
        "minimal": base_intake(),
        "exempt 6(3)": base_intake(
            industry="Banking & Credit Scoring",
            function="Preparatory task for a human assessment (file assembly, "
                     "information retrieval ahead of a human decision)"),
    }
    doc_text = "architecture pipeline component training data validation bias"

    for name, intake in scenarios.items():
        classification = classify_risk(intake)
        had_docs = name == "high-risk with docs"
        findings = scan_documentation(doc_text if had_docs else "")
        matrix = build_clarification_matrix(intake, findings, had_docs)
        try:
            pdf_bytes = generate_pdf_report(
                narrative,
                classification=classification,
                annex_iv_findings=findings,
                had_documentation=had_docs,
                clarification_matrix=matrix,
                company="Validation Corp",
                industry=intake["industry"],
                disclaimer_line="Automated readiness indicator only.",
                legal_narrative=narrative,
                action_plan=action_plan,
            )
            check(f"PDF scenario '{name}': bytes generated",
                  isinstance(pdf_bytes, bytes) and len(pdf_bytes) > 3000,
                  f"got {type(pdf_bytes)} len={len(pdf_bytes) if isinstance(pdf_bytes, bytes) else 'n/a'}")
            check(f"PDF scenario '{name}': valid PDF header",
                  pdf_bytes[:5] == b"%PDF-")
        except Exception as err:
            check(f"PDF scenario '{name}'", False,
                  f"raised {err.__class__.__name__}: {err}")
            traceback.print_exc()

    # Legacy single-blob call signature still works
    try:
        legacy = generate_pdf_report("## Legacy report body\nplain text only")
        check("Legacy generate_pdf_report(text) signature",
              isinstance(legacy, bytes) and legacy[:5] == b"%PDF-")
    except Exception as err:
        check("Legacy generate_pdf_report(text) signature", False, str(err))


def test_content_and_imports():
    print("\n[4] content.json + module import smoke test")
    with open("content.json", "r", encoding="utf-8") as f:
        content = json.load(f)
    wiz = content["workspace"]["wizard"]
    check("content.json parses", True)
    check("step2 social-scoring copy present",
          "q_social" in wiz["step2"] and "hint_social" in wiz["step2"])
    check("step3 Annex I + Art 6(3) copy present",
          "q_annex1" in wiz["step3"] and "q_function" in wiz["step3"])
    check("spinner_d present",
          "spinner_d" in content["workspace"]["assessment"])

    try:
        import ui_layouts  # noqa: F401  (pulls streamlit, utils.*)
        check("ui_layouts imports cleanly (full dependency graph)", True)
    except Exception as err:
        check("ui_layouts imports cleanly", False,
              f"{err.__class__.__name__}: {err}")
        traceback.print_exc()

    from utils.knowledge import load_legal_knowledge_base, knowledge_base_inventory
    inv = knowledge_base_inventory()
    corpus = load_legal_knowledge_base()
    check(f"Knowledge base inventory lists Annex sources ({len(inv)} files)",
          len(inv) >= 10, str(inv))
    check("Knowledge base corpus ingests Annex PDFs (non-empty, tagged)",
          len(corpus) > 5000 and "<<< SOURCE DOCUMENT:" in corpus,
          f"corpus length={len(corpus)}")


if __name__ == "__main__":
    print("=== TraceAct pipeline validation harness ===")
    test_risk_engine()
    test_annex_iv()
    test_minimal_risk_gap_rows()
    test_pdf_generation()
    test_content_and_imports()
    print(f"\n=== RESULT: {PASSED} passed, {FAILED} failed ===")
    sys.exit(1 if FAILED else 0)
