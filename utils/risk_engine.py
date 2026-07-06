"""
Deterministic EU AI Act risk-classification engine.

Pure-Python module (no Streamlit / no LLM). Implements the statutory
classification cascade of Regulation (EU) 2024/1689 in strict order:

    1. Article 5        — Prohibited practices (boolean hooks, hard stops)
    2. Article 6(1)     — Annex I filter (safety components / harmonised
                          products requiring third-party conformity)
    3. Article 6(2)     — Annex III eight-domain cross-reference matrix
    4. Article 6(3)     — Narrow-task exemption filter (with the profiling
                          override of Article 6(3) third subparagraph)
    5. Chapter V        — GPAI obligations
    6. Article 50       — Transparency / limited-risk obligations
    7. Minimal risk     — default tier

Every branch taken is appended to ``ClassificationResult.decision_path`` so
the final report can print the exact statutory pathway (legal defensibility
requirement: the engine must *prove* the tier, not merely assert it).
"""

from dataclasses import dataclass, field


# ══════════════════════════════════════════════════════════════════════════════
# Intake option catalogues (shared by the wizard UI and this engine —
# keep the strings identical in both places)
# ══════════════════════════════════════════════════════════════════════════════

INDUSTRY_OPTIONS = [
    "Employment & HR (hiring, evaluation)",
    "Banking & Credit Scoring",
    "Critical Infrastructure (water, gas, electricity, digital networks)",
    "Education & Vocational Training",
    "Healthcare & Medical Devices",
    "Insurance (life & health risk assessment / pricing)",
    "Law Enforcement",
    "Migration, Asylum & Border Control",
    "Administration of Justice & Democratic Processes",
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

SOCIAL_SCORING_OPTIONS = [
    "No — the system never scores or ranks people's general behaviour",
    "Yes — it scores individuals on social behaviour or personal traits, and "
    "scores are reused in unrelated contexts or cause disproportionate treatment",
    "Unsure — it produces person-level scores but reuse context is unclear",
]

DATA_SOURCE_OPTIONS = [
    "Private enterprise databases (our own or licensed first-party data)",
    "Public scraping (data harvested from the open internet)",
    "Untargeted scraping of facial images (internet or CCTV footage)",
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

# Annex I filter (Article 6(1))
ANNEX_I_OPTIONS = [
    "No — standalone software with no product-safety function",
    "Yes — the AI is a safety component of a product covered by EU harmonised "
    "legislation (machinery, medical devices, vehicles, toys, lifts, radio equipment...)",
    "Yes — the AI system itself is such a product and requires third-party "
    "conformity assessment before market placement",
]

# Article 6(3) functional-role filter
FUNCTION_OPTIONS = [
    "Primary decision-making — the system materially drives or replaces "
    "decisions about natural persons",
    "Narrow procedural task only (document formatting, data structuring, "
    "translation, deduplication)",
    "Improves the result of a previously completed human activity "
    "(polish, refine, summarise human work)",
    "Detects decision-making patterns or deviations from prior patterns — "
    "flags for human review, never replaces the human assessment",
    "Preparatory task for a human assessment (file assembly, information "
    "retrieval ahead of a human decision)",
]


# ══════════════════════════════════════════════════════════════════════════════
# Annex III — the eight statutory high-risk domains
# ══════════════════════════════════════════════════════════════════════════════

# Maps intake industry strings to (domain name, Annex III point).
ANNEX_III_DOMAIN_MAP = {
    "Employment & HR (hiring, evaluation)":
        ("Employment, workers management and access to self-employment",
         "Annex III, point 4"),
    "Banking & Credit Scoring":
        ("Access to essential private services — creditworthiness",
         "Annex III, point 5(b)"),
    "Critical Infrastructure (water, gas, electricity, digital networks)":
        ("Critical infrastructure (safety components in management/operation)",
         "Annex III, point 2"),
    "Education & Vocational Training":
        ("Education and vocational training",
         "Annex III, point 3"),
    "Healthcare & Medical Devices":
        ("Access to essential services — healthcare",
         "Annex III, point 5(a)"),
    "Insurance (life & health risk assessment / pricing)":
        ("Access to essential private services — life/health insurance",
         "Annex III, point 5(c)"),
    "Law Enforcement":
        ("Law enforcement",
         "Annex III, point 6"),
    "Migration, Asylum & Border Control":
        ("Migration, asylum and border control management",
         "Annex III, point 7"),
    "Administration of Justice & Democratic Processes":
        ("Administration of justice and democratic processes",
         "Annex III, point 8"),
}

ANNEX_III_ALL_DOMAINS = [
    ("1", "Biometrics (remote biometric ID, categorisation, emotion recognition)"),
    ("2", "Critical infrastructure"),
    ("3", "Education and vocational training"),
    ("4", "Employment, workers management, access to self-employment"),
    ("5", "Access to essential private and public services"),
    ("6", "Law enforcement"),
    ("7", "Migration, asylum and border control management"),
    ("8", "Administration of justice and democratic processes"),
]


# ══════════════════════════════════════════════════════════════════════════════
# Result container
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ClassificationResult:
    tier: str
    tier_code: str            # prohibited | high | limited | minimal
    citation: str
    decision_path: list = field(default_factory=list)
    article5_triggers: list = field(default_factory=list)   # (citation, finding)
    annex1_finding: str | None = None
    annex3_matches: list = field(default_factory=list)      # (domain, citation)
    exemption: dict = field(default_factory=dict)

    # Backward-compatible tuple unpacking: tier, citation = classify_risk(...)
    def __iter__(self):
        return iter((self.tier, self.citation))


# ══════════════════════════════════════════════════════════════════════════════
# Intake normalisation helpers
# ══════════════════════════════════════════════════════════════════════════════

def _flags(intake: dict) -> dict:
    """Normalise raw wizard strings into explicit boolean hooks."""
    biometric = intake.get("biometric", "")
    policing = intake.get("policing", "")
    social = intake.get("social_scoring", "")
    data_source = intake.get("data_source", "")
    audience = intake.get("audience", "")
    oversight = intake.get("oversight", "")
    industry = intake.get("industry", "")
    annex1 = intake.get("annex1", "")
    function = intake.get("function", "")

    bio_yes = biometric.lower().startswith("yes")
    pol_yes = policing.lower().startswith("yes")
    return {
        "industry": industry,
        "bio_id": bio_yes and ("identification" in biometric.lower()
                               or "both" in biometric.lower()),
        "emotion": bio_yes and ("emotion" in biometric.lower()
                                or "both" in biometric.lower()),
        "profiling": pol_yes and "profiling" in policing.lower(),
        "pred_pol": pol_yes and "predictive policing" in policing.lower(),
        "social_scoring": social.lower().startswith("yes"),
        "social_unsure": social.lower().startswith("unsure"),
        "untargeted_face_scrape": "Untargeted scraping of facial images" in data_source,
        "public_scrape": "Public scraping" in data_source or "Mixed" in data_source,
        "vendor_unknown": "provenance unknown" in data_source,
        "public_infra": "Public infrastructure" in audience,
        "consumer_facing": "External consumers" in audience,
        "autonomous": "Fully autonomous" in oversight,
        "annex1_safety_component": annex1.lower().startswith("yes") and
                                   "safety component" in annex1,
        "annex1_is_product": annex1.lower().startswith("yes") and
                             "itself" in annex1,
        "narrow_task": any(
            marker in function
            for marker in ("Narrow procedural task",
                           "Improves the result",
                           "Detects decision-making patterns",
                           "Preparatory task")
        ),
        "function_label": function,
        "gpai": industry == "General Purpose AI / LLM Development",
    }


# ══════════════════════════════════════════════════════════════════════════════
# Stage 1 — Article 5 prohibited-practice boolean hooks
# ══════════════════════════════════════════════════════════════════════════════

def check_article5(intake: dict) -> list:
    """
    Return every triggered Article 5 prohibition as (citation, finding) tuples.
    Each hook is an explicit boolean condition — no fuzzy matching.
    """
    f = _flags(intake)
    triggers = []

    if f["social_scoring"]:
        triggers.append((
            "Article 5(1)(c)",
            "Social scoring: evaluation/classification of natural persons based "
            "on social behaviour or personal characteristics, with detrimental "
            "treatment in unrelated contexts or disproportionate to the behaviour."
        ))
    if f["pred_pol"]:
        triggers.append((
            "Article 5(1)(d)",
            "Predictive policing: risk assessment of natural persons to predict "
            "criminal offences based solely on profiling or personality traits."
        ))
    if f["untargeted_face_scrape"]:
        triggers.append((
            "Article 5(1)(e)",
            "Untargeted scraping of facial images from the internet or CCTV "
            "footage to create or expand facial recognition databases."
        ))
    if f["emotion"] and f["industry"] in (
        "Employment & HR (hiring, evaluation)",
        "Education & Vocational Training",
    ):
        triggers.append((
            "Article 5(1)(f)",
            "Emotion recognition in the areas of workplace or education "
            "institutions (medical/safety exceptions not indicated by intake)."
        ))
    if f["bio_id"] and f["public_infra"] and f["industry"] == "Law Enforcement":
        triggers.append((
            "Article 5(1)(h)",
            "Real-time remote biometric identification in publicly accessible "
            "spaces for law-enforcement purposes (outside the exhaustive "
            "Article 5(2) exceptions, none of which are indicated by intake)."
        ))
    return triggers


# ══════════════════════════════════════════════════════════════════════════════
# Stage 2 — Annex I filter (Article 6(1))
# ══════════════════════════════════════════════════════════════════════════════

def check_annex1(intake: dict) -> str | None:
    """Return an Annex I finding string when Article 6(1) applies, else None."""
    f = _flags(intake)
    if f["annex1_is_product"]:
        return ("The AI system is itself a product covered by Union harmonised "
                "legislation listed in Annex I and is required to undergo "
                "third-party conformity assessment — high-risk under Article 6(1).")
    if f["annex1_safety_component"]:
        return ("The AI system is used as a safety component of a product covered "
                "by Union harmonised legislation listed in Annex I and subject to "
                "third-party conformity assessment — high-risk under Article 6(1).")
    return None


# ══════════════════════════════════════════════════════════════════════════════
# Stage 3 — Annex III eight-domain matrix (Article 6(2))
# ══════════════════════════════════════════════════════════════════════════════

def check_annex3(intake: dict) -> list:
    """Cross-reference intake against all eight Annex III domains."""
    f = _flags(intake)
    matches = []

    # Point 1 — Biometrics (non-prohibited biometric use cases)
    if f["bio_id"]:
        matches.append((
            "Biometrics — remote biometric identification systems",
            "Annex III, point 1(a)"))
    if f["emotion"] and f["industry"] not in (
        "Employment & HR (hiring, evaluation)",
        "Education & Vocational Training",
    ):
        matches.append((
            "Biometrics — emotion recognition systems",
            "Annex III, point 1(c)"))

    # Points 2–8 — sector mapping
    if f["industry"] in ANNEX_III_DOMAIN_MAP:
        matches.append(ANNEX_III_DOMAIN_MAP[f["industry"]])

    # Public-infrastructure deployments outside a matched sector still touch
    # point 2 when the system operates autonomously on civic infrastructure.
    if f["public_infra"] and f["autonomous"] and not any(
        "point 2" in m[1] for m in matches
    ):
        matches.append((
            "Critical infrastructure — autonomous operation on public "
            "infrastructure", "Annex III, point 2"))

    return matches


# ══════════════════════════════════════════════════════════════════════════════
# Stage 4 — Article 6(3) exemption filter
# ══════════════════════════════════════════════════════════════════════════════

def check_article_6_3(intake: dict, annex3_matches: list) -> dict:
    """
    Evaluate the narrow-task derogation. Returns a dict that documents the
    analysis (the engine must PROVE the exemption, not assume it):
        {applicable, claimed, granted, reason}
    """
    f = _flags(intake)
    result = {
        "applicable": bool(annex3_matches),
        "claimed": f["narrow_task"],
        "granted": False,
        "reason": "",
    }
    if not annex3_matches:
        result["reason"] = ("No Annex III domain matched — the Article 6(3) "
                            "derogation analysis is not applicable.")
        return result
    if not f["narrow_task"]:
        result["reason"] = (
            "The declared system function is primary decision-making over "
            "natural persons. None of the four Article 6(3) derogation limbs "
            "(narrow procedural task; improving a completed human activity; "
            "pattern-deviation detection without replacing human assessment; "
            "preparatory task) is satisfied. Default: HIGH-RISK stands.")
        return result
    if f["profiling"] or f["pred_pol"]:
        result["reason"] = (
            "A derogation limb was claimed, but the system performs profiling "
            "of natural persons. Under Article 6(3), third subparagraph, an "
            "Annex III system that performs profiling is ALWAYS considered "
            "high-risk — the exemption is statutorily unavailable. "
            "Default: HIGH-RISK stands.")
        return result
    if any("point 1" in m[1] for m in annex3_matches):
        result["reason"] = (
            "A derogation limb was claimed, but biometric use cases under "
            "Annex III point 1 are not suitable candidates for the narrow-task "
            "derogation given their direct impact on fundamental rights. "
            "Conservative default: HIGH-RISK stands; seek a documented "
            "assessment under Article 6(4) before relying on any exemption.")
        return result

    result["granted"] = True
    result["reason"] = (
        f"Derogation limb satisfied: '{f['function_label']}'. The system does "
        "not perform profiling and does not materially influence "
        "decision-making outcomes. Per Article 6(3) the system is NOT "
        "considered high-risk. MANDATORY CONDITION (Article 6(4)): the "
        "provider must document this assessment BEFORE market placement and "
        "register the system under Article 49(2); the exemption is defeasible "
        "on review by market surveillance authorities.")
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Master cascade
# ══════════════════════════════════════════════════════════════════════════════

def classify_risk(intake: dict) -> ClassificationResult:
    """
    Execute the full statutory classification cascade and return a
    ClassificationResult whose decision_path documents every step taken.
    """
    f = _flags(intake)
    path = []

    # ── Stage 1: Article 5 ────────────────────────────────────────────────────
    a5 = check_article5(intake)
    if a5:
        cites = "; ".join(c for c, _ in a5)
        path.append(f"STAGE 1 — Article 5 screen: TRIGGERED ({cites}). "
                    "Classification cascade halts: prohibited practices cannot "
                    "be remediated into compliance and must be decommissioned.")
        return ClassificationResult(
            tier="UNACCEPTABLE RISK — PROHIBITED PRACTICE (Article 5)",
            tier_code="prohibited",
            citation=a5[0][0],
            decision_path=path,
            article5_triggers=a5,
        )
    path.append("STAGE 1 — Article 5 screen: no prohibited-practice hook "
                "triggered (social scoring, predictive policing, untargeted "
                "facial scraping, workplace/education emotion recognition, "
                "real-time remote biometric ID all negative).")
    if f["social_unsure"]:
        path.append("NOTE — social-scoring answer was 'Unsure': flagged for the "
                    "Clarification Request Matrix; Article 5(1)(c) exposure "
                    "cannot be excluded without further evidence.")

    # ── Stage 2: Annex I / Article 6(1) ───────────────────────────────────────
    annex1 = check_annex1(intake)
    if annex1:
        path.append(f"STAGE 2 — Annex I filter: TRIGGERED. {annex1}")
        return ClassificationResult(
            tier="HIGH-RISK SYSTEM (Article 6(1) / Annex I)",
            tier_code="high",
            citation="Article 6(1) in conjunction with Annex I",
            decision_path=path,
            annex1_finding=annex1,
        )
    path.append("STAGE 2 — Annex I filter: negative (not a safety component of, "
                "nor itself, a product under Union harmonised legislation "
                "requiring third-party conformity assessment).")

    # ── Stage 3: Annex III eight-domain matrix ────────────────────────────────
    annex3 = check_annex3(intake)
    if annex3:
        listed = "; ".join(f"{d} [{c}]" for d, c in annex3)
        path.append(f"STAGE 3 — Annex III matrix: MATCHED {len(annex3)} "
                    f"domain(s): {listed}.")
    else:
        path.append("STAGE 3 — Annex III matrix: no match across the eight "
                    "statutory domains (biometrics, critical infrastructure, "
                    "education, employment, essential services, law "
                    "enforcement, migration/border, justice/democracy).")

    # ── Stage 4: Article 6(3) derogation ──────────────────────────────────────
    exemption = check_article_6_3(intake, annex3)
    if annex3:
        path.append(f"STAGE 4 — Article 6(3) derogation analysis: "
                    f"{exemption['reason']}")
        if not exemption["granted"]:
            return ClassificationResult(
                tier="HIGH-RISK SYSTEM (Article 6(2) / Annex III)",
                tier_code="high",
                citation=annex3[0][1],
                decision_path=path,
                annex3_matches=annex3,
                exemption=exemption,
            )
        # exemption granted → fall through to transparency / minimal tiers

    # ── Stage 5: GPAI (Chapter V) ─────────────────────────────────────────────
    if f["gpai"]:
        path.append("STAGE 5 — GPAI screen: the system is a general-purpose AI "
                    "model. Chapter V obligations apply (Articles 51–55): "
                    "technical documentation, training-data summary, copyright "
                    "policy; systemic-risk duties above the Article 51 "
                    "compute threshold.")
        return ClassificationResult(
            tier="SPECIFIC TRANSPARENCY RISK (Chapter V — GPAI)",
            tier_code="limited",
            citation="Articles 51-55",
            decision_path=path,
            annex3_matches=annex3,
            exemption=exemption,
        )

    # ── Stage 6: Article 50 transparency ──────────────────────────────────────
    if f["consumer_facing"]:
        path.append("STAGE 6 — Article 50 screen: consumer-facing deployment. "
                    "Transparency obligations apply: disclosure of AI "
                    "interaction (Article 50(1)) and synthetic-content "
                    "labelling duties where applicable (Article 50(2)/(4)).")
        return ClassificationResult(
            tier="TRANSPARENCY / LIMITED RISK (Article 50)",
            tier_code="limited",
            citation="Article 50(1)",
            decision_path=path,
            annex3_matches=annex3,
            exemption=exemption,
        )

    # ── Stage 7: Minimal risk ─────────────────────────────────────────────────
    path.append("STAGE 7 — Default tier: MINIMAL RISK. No prohibited hook, no "
                "Annex I/III trigger surviving the Article 6(3) analysis, no "
                "GPAI or consumer-transparency exposure. Voluntary codes of "
                "conduct (Article 95) recommended.")
    return ClassificationResult(
        tier="MINIMAL RISK",
        tier_code="minimal",
        citation="Article 95 (voluntary codes of conduct)",
        decision_path=path,
        annex3_matches=annex3,
        exemption=exemption,
    )
