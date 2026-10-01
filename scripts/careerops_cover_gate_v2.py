from careerops_config import candidate_identity
from careerops_config import source_dir
#!/usr/bin/env python3

import argparse
import hashlib
import json
import re
from difflib import SequenceMatcher
from pathlib import Path

from careerops_runtime import runtime_dir

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = runtime_dir(ROOT)
SOURCE = source_dir(ROOT)

DEFAULT_COVER = RUNTIME / "generated_cover_letter_pair_candidate.json"
DEFAULT_RESUME = RUNTIME / "generated_resume_content_pair_candidate.json"
DEFAULT_PLAN = RUNTIME / "cover_plan.json"
DEFAULT_RULES = SOURCE / "cover_letter_rules.json"
DEFAULT_REPORT = RUNTIME / "cover_gate_v2_report.json"

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "by",
    "for", "from", "had", "has", "have", "i", "in", "into", "is", "it",
    "its", "my", "of", "on", "or", "our", "that", "the", "their", "this",
    "to", "was", "were", "will", "with", "would",
}

AI_PATTERN_FAMILIES = [
    "that combination",
    "directly aligns",
    "directly aligned",
    "directly matches",
    "directly matched",
    "this work taught me",
    "i would apply",
    "i bring",
    "my background",
    "resonates with me",
    "uniquely positioned",
    "meaningful contribution",
    "proven track record",
    "actionable insights",
    "leverage my skills",
    "robust solution",
    "results-driven",
    "passionate about",
    "excited to apply",
    "i would welcome the opportunity",
    "i look forward to discussing",
]

REASONING_MARKERS = (
    "because",
    "so that",
    "in order to",
    "rather than",
    "instead of",
    "which allowed",
    "which enabled",
    "to preserve",
    "to avoid",
    "given that",
    "therefore",
)

DECISION_VERBS = (
    "chose",
    "designed",
    "used",
    "built",
    "kept",
    "preserved",
    "separated",
    "modeled",
    "made",
    "structured",
    "implemented",
    "validated",
)

INTEREST_SIGNAL_GROUPS = {
    "state_reporting": (
        "state reporting",
        "state-reporting",
    ),
    "database_change_adaptation": (
        "database changes",
        "databases change",
        "database change",
        "changing databases",
        "reporting processes when databases change",
    ),
    "data_quality_submission": (
        "data-quality review",
        "data quality review",
        "review before formal submissions",
        "review before submissions",
        "submission accuracy",
    ),
    "stakeholder_query_requirements": (
        "stakeholder-defined data requests",
        "query requirements",
        "input and output requirements",
        "user needs",
    ),
    "governance": (
        "data-governance",
        "data governance",
        "governance controls",
    ),
    "privacy": (
        "privacy controls",
        "privacy regulations",
        "privacy-conscious",
        "privacy",
    ),
    "recurring_reporting": (
        "recurring reporting",
        "annual reporting",
        "annual reports",
    ),
}


def load(path):
    if not path.exists():
        raise SystemExit(f"Missing required file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def words(text):
    return re.findall(r"\b[\w'-]+\b", str(text))


def normalize(text):
    text = str(text or "").lower()
    text = text.replace("—", "-").replace("–", "-")
    text = re.sub(r"[^a-z0-9%+#./'-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def canonical_token(token):
    token = str(token or "").lower().strip("'")

    families = {
        "reconciliation": "reconcile",
        "reconciled": "reconcile",
        "reconciling": "reconcile",
        "reconcile": "reconcile",

        "validation": "validate",
        "validated": "validate",
        "validating": "validate",
        "validate": "validate",

        "measurements": "measure",
        "measurement": "measure",
        "measured": "measure",
        "measures": "measure",
        "measure": "measure",

        "mappings": "mapping",
        "mapped": "mapping",
        "mapping": "mapping",

        "hashes": "hash",
        "hashed": "hash",
        "hashing": "hash",
        "hash": "hash",

        "releases": "release",
        "released": "release",
        "release": "release",

        "counts": "count",
        "counted": "count",
        "count": "count",

        "schemas": "schema",
        "schema": "schema",

        "bridges": "bridge",
        "bridge": "bridge",

        "tables": "table",
        "table": "table",

        "files": "file",
        "file": "file",

        "records": "record",
        "record": "record",

        "reports": "report",
        "reporting": "report",
        "report": "report",

        "queries": "query",
        "querying": "query",
        "query": "query",

        "visualizations": "visualization",
        "visualization": "visualization",

        "outputs": "output",
        "output": "output",

        "preserving": "preserve",
        "preserved": "preserve",
        "preserve": "preserve",
    }

    if token in families:
        return families[token]

    # Conservative plural normalization only.
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"

    if (
        len(token) > 4
        and token.endswith("s")
        and not token.endswith("ss")
    ):
        return token[:-1]

    return token


def content_tokens(text):
    # Split hyphenated/slashed compounds into their meaningful parts.
    raw = re.findall(
        r"[a-z0-9]+",
        normalize(text),
    )

    tokens = set()

    for token in raw:
        canonical = canonical_token(token)

        if (
            len(canonical) >= 3
            and canonical not in STOPWORDS
        ):
            tokens.add(canonical)

    return tokens


def sentences(text):
    return [
        s.strip()
        for s in re.split(r"(?<=[.!?])\s+", str(text).strip())
        if s.strip()
    ]


def normalized_digits(text):
    return re.sub(r"\D", "", str(text or ""))


def phrase_hits(text, phrases):
    low = normalize(text)
    return [
        phrase
        for phrase in phrases
        if normalize(phrase) in low
    ]


def evidence_phrase_match(text, evidence_phrase):
    """
    Fuzzy concept coverage. We do not require the model to reproduce planner
    wording verbatim. A concept matches when enough distinctive evidence tokens
    are present in the target text.
    """
    target = content_tokens(text)
    source = content_tokens(evidence_phrase)

    if not source:
        return False, 0.0

    overlap = len(target & source) / len(source)

    # Long planner phrases contain connective/detail tokens that need not all
    # be repeated. 35% is enough to detect the underlying method concept.
    return overlap >= 0.35, round(overlap, 4)


def semantic_overlap(sentence, bullet):
    a = content_tokens(sentence)
    b = content_tokens(bullet)

    if not a or not b:
        return 0.0, 0.0

    containment = len(a & b) / min(len(a), len(b))
    sequence = SequenceMatcher(
        None,
        normalize(sentence),
        normalize(bullet),
    ).ratio()

    return round(containment, 4), round(sequence, 4)

def plan_authorized_validation_explanation(
    sentence,
    validation_methods,
    sequence_similarity,
):
    """
    Narrowly distinguish a plan-authorized validation explanation
    from a resume-bullet rewrite.

    Requirements:
      1. low sentence-shape similarity;
      2. explicit validation/reliability purpose;
      3. at least two methods already authorized by Cover Plan.

    No fact, metric, method, employer, history, or outcome is created.
    """

    if (
        sequence_similarity is None
        or float(sequence_similarity) > 0.20
    ):
        return False

    low = normalize(
        sentence
    )

    validation_purpose = bool(
        re.search(
            (
                r"\b(?:"
                r"check(?:ed|ing)?|"
                r"validat(?:e|ed|ing)|"
                r"verif(?:y|ied|ying)|"
                r"reconcil(?:e|ed|ing)|"
                r"audit(?:ed|ing)?|"
                r"reliab(?:le|ility)|"
                r"integrity"
                r")\b"
            ),
            low,
            flags=re.I,
        )
    )

    if not validation_purpose:
        return False

    matched_methods = 0

    for method in (
        validation_methods
        or []
    ):
        matched, _ = evidence_phrase_match(
            sentence,
            method,
        )

        if matched:
            matched_methods += 1

    return matched_methods >= 2


def interest_signals(text):
    low = normalize(text)
    hits = []

    for group, variants in INTEREST_SIGNAL_GROUPS.items():
        if any(normalize(v) in low for v in variants):
            hits.append(group)

    return hits

INTEREST_INTENT_PATTERNS = (
    "specifically interests me",
    "interests me",
    "interested in",
    "work i want to take on",
    "work i want to pursue",
    "work i want to do",
    "why i am pursuing",
    "why i'm pursuing",
    "draws me",
)

def has_interest_intent(text):
    """
    Detect explicit employer/role interest without requiring one
    pre-approved wording template.

    This is intentionally generic: it recognizes ordinary constructions
    such as "the reason I am pursuing this role" in addition to the
    historical phrase inventory.
    """
    low = normalize(text)

    if any(
        normalize(pattern) in low
        for pattern in INTEREST_INTENT_PATTERNS
    ):
        return True

    generic_patterns = (
        r"\bi (?:want|would like) to join\b[^.!?]{0,220}\bbecause\b",
        r"\b(?:the\s+)?(?:specific\s+)?reason\s+"
        r"(?:i\s+am|i'm)\s+"
        r"(?:pursuing|interested\s+in|drawn\s+to)\b",

        r"\b(?:the\s+)?reason\s+"
        r"(?:i\s+want\s+to|i\s+would\s+like\s+to)\s+"
        r"(?:pursue|join|do)\b",

        r"\b(?:what|the\s+work)\s+"
        r"(?:interests|draws|motivates)\s+me\b",
    )

    #
    # Recognize natural professional evaluation without forcing one
    # canned first-person sentence. Final specific_interest still
    # requires employer identity + target-work specificity, so this
    # does not turn generic company praise into acceptable interest.
    generic_patterns = (
        generic_patterns
        + (
            (
                r"\b(?:this|the)\s+"
                r"(?:role|position|opportunity|work)"
                r"(?:'s|’s)?\b"
                r"[^.!?]{0,160}\b(?:is|are)\s+"
                r"(?:particularly\s+|especially\s+)?"
                r"(?:compelling|appealing|meaningful|interesting)\b"
            ),
            (
                r"\b(?:this|the)\s+"
                r"(?:role|position|opportunity|work)\b"
                r"[^.!?]{0,160}\b"
                r"(?:stands?\s+out|appeals?\s+to\s+me)\b"
            ),
        )
    )

    return any(
        re.search(
            pattern,
            low,
            re.I,
        )
        for pattern in generic_patterns
    )

def has_causal_decision_reasoning(text):
    """
    Require a decision verb and an explicit causal/rationale construction
    in the same sentence.

    This catches natural analytical reasoning such as:
      "The sample was sparse, so I chose a transparent model."
    while avoiding a weak rule where an unrelated "so" elsewhere in the
    paragraph satisfies the reasoning requirement.
    """
    verbs = "|".join(
        re.escape(verb)
        for verb in DECISION_VERBS
    )

    for sentence in sentences(text):
        low = normalize(sentence)

        has_decision = bool(
            re.search(
                rf"\b(?:{verbs})\b",
                low,
                re.I,
            )
        )

        if not has_decision:
            continue

        if any(
            normalize(marker) in low
            for marker in REASONING_MARKERS
        ):
            return True

        if re.search(
            rf"\bso\s+(?:i|we)\s+(?:{verbs})\b",
            low,
            re.I,
        ):
            return True

        # Also recognize the equally natural inverse construction:
        #   "I chose X so Y..."
        #   "We used X because Y..."
        # The decision and rationale must remain in the same sentence.
        if re.search(
            rf"\b(?:i|we)\s+(?:{verbs})\b"
            rf".{{0,180}}?"
            rf"\b(?:so|because|since|"
            rf"in\s+order\s+to|to\s+ensure|"
            rf"to\s+avoid|to\s+keep|to\s+make)\b",
            low,
            re.I,
        ):
            return True

        if re.search(
            rf"\b(?:therefore|thus|consequently)\s+"
            rf"(?:i|we)\s+(?:{verbs})\b",
            low,
            re.I,
        ):
            return True

    # A stated design decision can explain purpose through its consequence,
    # e.g. separating bridge tables preserved the unit of analysis.
    for sentence in sentences(text):
        if re.search(r"\b(?:separating|partitioning|retaining|mapping|reconciling|standardizing|isolating)\b.{0,160}\b(?:preserved|prevented|kept|protected|enabled|ensured)\b.{3,160}",sentence,re.I):
            return True
        if re.search(r"\b(?:i|we) (?:chose|used|designed|implemented|required)\b.{0,180}\b(?:to support|to retain|to protect|to distinguish|to trace|to keep)\b",sentence,re.I):
            return True
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cover", default=str(DEFAULT_COVER))
    parser.add_argument("--resume", default=str(DEFAULT_RESUME))
    parser.add_argument("--plan", default=str(DEFAULT_PLAN))
    parser.add_argument("--rules", default=str(DEFAULT_RULES))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    args = parser.parse_args()

    cover_path = Path(args.cover)
    resume_path = Path(args.resume)
    plan_path = Path(args.plan)
    rules_path = Path(args.rules)
    report_path = Path(args.report)

    for name, path in (
        ("cover", cover_path),
        ("resume", resume_path),
        ("plan", plan_path),
        ("rules", rules_path),
        ("report", report_path),
    ):
        if not path.is_absolute():
            locals()[f"{name}_path"] = ROOT / path

    # Rebind because assigning through locals() is not portable.
    cover_path = cover_path if cover_path.is_absolute() else ROOT / cover_path
    resume_path = resume_path if resume_path.is_absolute() else ROOT / resume_path
    plan_path = plan_path if plan_path.is_absolute() else ROOT / plan_path
    rules_path = rules_path if rules_path.is_absolute() else ROOT / rules_path
    report_path = report_path if report_path.is_absolute() else ROOT / report_path

    cover = load(cover_path)
    resume = load(resume_path)
    plan = load(plan_path)
    rules = load(rules_path)

    paragraphs = cover.get("paragraphs", [])
    body = "\n\n".join(paragraphs)
    body_low = normalize(body)
    body_words = len(words(body))

    p1 = paragraphs[0] if len(paragraphs) >= 1 else ""
    p2 = paragraphs[1] if len(paragraphs) >= 2 else ""
    p3 = paragraphs[2] if len(paragraphs) >= 3 else ""

    checks = {}
    details = {}

    # ================================================================
    # A. STRUCTURE
    # ================================================================

    expected_paragraphs = int(
        plan.get("writer_contract", {}).get(
            "paragraph_count",
            rules.get("purpose", {}).get("paragraphs", 3),
        )
    )

    checks["paragraph_count"] = len(paragraphs) == expected_paragraphs

    min_words = int(
        rules.get("purpose", {}).get(
            "target_body_words_min",
            190,
        )
    )
    max_words = int(
        rules.get("purpose", {}).get(
            "target_body_words_max",
            240,
        )
    )

    checks["body_word_count"] = min_words <= body_words <= max_words

    checks["salutation"] = (
        cover.get("salutation")
        == rules.get("output", {}).get(
            "salutation",
            "Dear Hiring Manager,",
        )
    )

    checks["closing"] = (
        cover.get("closing")
        == rules.get("output", {}).get(
            "closing",
            "Sincerely,",
        )
    )

    checks["signature"] = (
        cover.get("signature")
        == rules.get("output", {}).get(
            "signature",
            candidate_identity(ROOT)["name"],
        )
    )

    checks["final_sentence"] = (
        bool(paragraphs)
        and p3.strip().endswith(
            "Thank you for your consideration."
        )
    )

    checks["paragraph_2_longest"] = (
        len(words(p2)) > len(words(p1))
        and len(words(p2)) > len(words(p3))
    )

    # ================================================================
    # B. IDENTITY + PLANNER AUTHORITY
    # ================================================================

    target = plan.get("target_job", {})

    # Preserve exact substantive identity while ignoring accidental
    # outer whitespace introduced by CLI copy/paste.
    planned_company = str(
        target.get("company")
        or ""
    ).strip()

    planned_position = str(
        target.get("position")
        or ""
    ).strip()

    cover_company = str(
        cover.get("company")
        or ""
    ).strip()

    cover_position = str(
        cover.get("position")
        or ""
    ).strip()

    checks["exact_company"] = (
        bool(planned_company)
        and cover_company == planned_company
    )

    checks["exact_position"] = (
        bool(planned_position)
        and cover_position == planned_position
    )

    checks["paragraph1_names_company"] = (
        bool(planned_company)
        and normalize(planned_company) in normalize(p1)
    )

    checks["paragraph1_names_position"] = (
        bool(planned_position)
        and normalize(planned_position) in normalize(p1)
    )

    checks["paragraph3_names_company"] = (
        bool(planned_company)
        and normalize(planned_company) in normalize(p3)
    )

    planned_primary = (
        plan.get("primary_evidence", {}).get("evidence_id")
    )
    cover_primary = cover.get("primary_evidence_ids", [])

    checks["primary_evidence_matches_plan"] = (
        bool(planned_primary)
        and cover_primary == [planned_primary]
    )

    planned_secondary = plan.get("secondary_evidence", {})
    cover_secondary = cover.get("secondary_evidence_ids", [])

    if planned_secondary.get("use_secondary_story"):
        allowed_secondary = planned_secondary.get("evidence_id")
        checks["secondary_evidence_authorized"] = (
            len(cover_secondary) <= 1
            and (
                not cover_secondary
                or cover_secondary == [allowed_secondary]
            )
        )
    else:
        checks["secondary_evidence_authorized"] = (
            cover_secondary == []
        )

    # ================================================================
    # C. NUMERICAL ANCHORS + CROSS-DOCUMENT CONSISTENCY
    # ================================================================

    cover_anchors = cover.get("numerical_anchors", [])
    plan_anchors = plan.get("numerical_anchors", [])

    min_anchors = int(
        rules.get("numerical_evidence", {}).get(
            "minimum_meaningful_candidate_anchors",
            2,
        )
    )

    checks["anchor_count"] = len(cover_anchors) >= min_anchors

    anchor_validation = []

    for planned in plan_anchors[:min_anchors]:
        value_digits = normalized_digits(planned.get("value"))
        source = planned.get("source_entity")

        body_has_value = bool(
            value_digits
            and value_digits in normalized_digits(body)
        )

        matching_declared = [
            a
            for a in cover_anchors
            if a.get("source_entity") == source
            and (
                value_digits
                and value_digits
                in normalized_digits(a.get("text"))
            )
        ]

        anchor_validation.append({
            "planned": planned,
            "value_present_in_body": body_has_value,
            "matching_declared_anchor":
                bool(matching_declared),
        })

    checks["planned_anchors_present"] = (
        len(anchor_validation) >= min_anchors
        and all(
            x["value_present_in_body"]
            and x["matching_declared_anchor"]
            for x in anchor_validation
        )
    )

    checks["anchor_sources_match_primary"] = all(
        a.get("source_entity") == planned_primary
        for a in cover_anchors
    )

    # ================================================================
    # D. TECHNICAL STORY DEPTH
    # ================================================================

    story = plan.get("story", {})

    mechanics = (
        story.get("exact_implementation", {})
        .get("supported_mechanics", [])
    )

    mechanic_matches = []
    for mechanic in mechanics:
        matched, score = evidence_phrase_match(
            p2,
            mechanic,
        )
        if matched:
            mechanic_matches.append({
                "mechanic": mechanic,
                "coverage": score,
            })

    checks["technical_mechanics_depth"] = (
        len(mechanic_matches) >= 2
    )

    validation_methods = (
        story.get("validation", {})
        .get("supported_validation_methods", [])
    )

    validation_matches = []
    for method in validation_methods:
        matched, score = evidence_phrase_match(
            p2,
            method,
        )
        if matched:
            validation_matches.append({
                "method": method,
                "coverage": score,
            })

    checks["validation_depth"] = (
        len(validation_matches) >= 2
    )

    reasoning_markers_found = phrase_hits(
        p2,
        REASONING_MARKERS,
    )

    decision_verbs_found = [
        verb
        for verb in DECISION_VERBS
        if re.search(
            rf"\b{re.escape(verb)}\b",
            normalize(p2),
        )
    ]

    causal_decision_reasoning = (
        has_causal_decision_reasoning(p2)
    )

    checks["judgment_and_why_visible"] = (
        (
            bool(reasoning_markers_found)
            and bool(decision_verbs_found)
        )
        or causal_decision_reasoning
    )

    supported_outputs = (
        story.get("output", {})
        .get("supported_outputs", [])
    )

    output_matches = []
    for item in supported_outputs:
        matched, score = evidence_phrase_match(
            p2,
            item,
        )
        if matched:
            output_matches.append({
                "output": item,
                "coverage": score,
            })

    checks["supported_output_visible"] = (
        len(output_matches) >= 1
    )

    # ================================================================
    # E. PARAGRAPH 1 HOOK SPECIFICITY
    # ================================================================

    hook_evidence = []

    for anchor in plan_anchors:
        digits = normalized_digits(anchor.get("value"))
        if digits and digits in normalized_digits(p1):
            hook_evidence.append(
                f"anchor:{anchor.get('label')}"
            )

    constraint_points = (
        story.get("constraint_complexity", {})
        .get("supported_evidence_points", [])
    )

    for point in constraint_points:
        matched, score = evidence_phrase_match(
            p1,
            point,
        )
        if matched:
            hook_evidence.append(
                f"constraint:{point}"
            )

    # Role-general objective specificity.
    # Do not hardcode terms from any historical fixture/job.
    objective_text = story.get(
        "real_problem",
        "",
    )

    objective_tokens = content_tokens(
        objective_text
    )

    paragraph1_tokens = content_tokens(
        p1
    )

    generic_objective_tokens = {
        "analysis",
        "analytical",
        "data",
        "dataset",
        "datasets",
        "build",
        "built",
        "work",
        "project",
        "platform",
        "system",
        "systems",
        "support",
        "reporting",
        "research",
        "result",
        "results",
        "output",
        "outputs",
    }

    objective_token_hits = sorted(
        (
            objective_tokens
            & paragraph1_tokens
        )
        - generic_objective_tokens
    )

    if len(objective_token_hits) >= 2:
        hook_evidence.extend(
            "objective_token:"
            + term
            for term
            in objective_token_hits
        )

    checks["paragraph1_specific_hook"] = bool(
        hook_evidence
    )

    # ================================================================
    # F. TARGET-ROLE APPLICATION + SPECIFIC INTEREST
    # ================================================================

    target_application = plan.get(
        "target_role_application",
        {},
    )

    target_requirement_text = " ".join(
        item.get("target_responsibility", "")
        for item in target_application.get(
            "target_requirements",
            [],
        )
    )

    # Preserve the original high-signal vocabulary, but do not
    # require every role family to use IRSC/research-oriented terms.
    # Also derive substantive overlap directly from the current
    # plan-authorized target responsibility.
    target_signal_phrases = [
        "data quality",
        "database",
        "query",
        "state reporting",
        "data requests",
        "subject matter experts",
        "institutional definitions",
        "reports",
        "visualizations",
        "governance",
    ]

    legacy_target_application_hits = [
        phrase
        for phrase in target_signal_phrases
        if (
            normalize(phrase)
            in normalize(target_requirement_text)
            and normalize(phrase)
            in normalize(p3)
        )
    ]

    generic_target_tokens = {
        "data",
        "analysis",
        "support",
        "related",
        "role",
        "work",
        "position",
        "responsibility",
        "responsibilities",
        "process",
    }

    target_token_hits = sorted(
        (
            content_tokens(target_requirement_text)
            & content_tokens(p3)
        )
        - generic_target_tokens
    )

    target_application_hits = sorted(
        set(
            legacy_target_application_hits
            + [
                f"token:{token}"
                for token in target_token_hits
            ]
        )
    )

    raw_target_role_application_specific = (
        len(set(legacy_target_application_hits)) >= 2
        or len(target_token_hits) >= 2
    )

    interest_reason_for_applicability = (
        plan.get("interest_reason", {}) or {}
    )

    target_requirements_for_applicability = list(
        target_application.get(
            "target_requirements",
            [],
        )
        or []
    )

    interest_source_for_applicability = str(
        interest_reason_for_applicability.get(
            "source",
            "",
        )
    ).strip().upper()

    interest_confidence_for_applicability = str(
        interest_reason_for_applicability.get(
            "confidence",
            "",
        )
    ).strip().upper()

    general_empty_target_authorized = (
        interest_source_for_applicability == "TARGET_JD"
        and interest_confidence_for_applicability == "JD_GENERAL"
        and len(target_requirements_for_applicability) == 0
        and str(
            target_application.get(
                "type",
                "",
            )
        )
        == "FUTURE_APPLICATION_NOT_HISTORICAL_CLAIM"
        and bool(
            normalize(
                interest_reason_for_applicability.get(
                    "reason",
                    "",
                )
            )
        )
    )

    specific_empty_contract_error = (
        interest_confidence_for_applicability == "JD_SPECIFIC"
        and len(target_requirements_for_applicability) == 0
    )

    checks["target_role_application_specific"] = (
        raw_target_role_application_specific
        or general_empty_target_authorized
    )

    #
    # Hook specificity and interest are separate concepts.
    # A paragraph-one opening is specific when it names the exact
    # employer + title and carries substantive target-responsibility
    # vocabulary. It does not need a number or an interest sentence.
    p1_target_token_hits = sorted(
        (
            content_tokens(
                target_requirement_text
            )
            & content_tokens(
                p1
            )
        )
        - generic_target_tokens
    )

    if (
        not checks[
            "paragraph1_specific_hook"
        ]
        and checks[
            "paragraph1_names_company"
        ]
        and checks[
            "paragraph1_names_position"
        ]
        and len(
            p1_target_token_hits
        )
        >= 2
    ):
        hook_evidence.extend(
            "target_role_token:"
            + token
            for token
            in p1_target_token_hits
        )

        checks[
            "paragraph1_specific_hook"
        ] = True

    interest_reason = (
        plan.get("interest_reason", {}) or {}
    )
    plan_interest = interest_reason.get(
        "reason",
        "",
    )

    planned_interest_signals = interest_signals(
        plan_interest
    )
    p3_interest_signals = interest_signals(p3)

    required_interest_signal_count = min(
        2,
        len(planned_interest_signals),
    )

    legacy_specific_interest = (
        required_interest_signal_count >= 1
        and len(
            set(planned_interest_signals)
            & set(p3_interest_signals)
        )
        >= required_interest_signal_count
    )

    plan_interest_is_jd_specific = (
        str(
            interest_reason.get("source", "")
        ).strip().upper()
        == "TARGET_JD"
        and str(
            interest_reason.get("confidence", "")
        ).strip().upper()
        == "JD_SPECIFIC"
        and bool(normalize(plan_interest))
    )

    # A role-specific value judgment expresses motivation without requiring
    # "interests me". It still needs the existing employer and JD-work gates.
    role_value_motivation = bool(re.search(
        r"\b(?:role|position|work|opportunity)(?:'s)?\b.{0,180}"
        r"\b(?:precisely where|why|matters? to me|worth pursuing|motivates me)\b", p3, re.I))
    generic_specific_interest = (
        plan_interest_is_jd_specific
        and checks["paragraph3_names_company"]
        and checks["target_role_application_specific"]
        and (has_interest_intent(p3) or role_value_motivation)
    )

    general_specific_interest = (
        general_empty_target_authorized
        and checks["paragraph3_names_company"]
        and has_interest_intent(p3)
    )

    checks["specific_interest"] = (
        legacy_specific_interest
        or generic_specific_interest
        or general_specific_interest
    )

    # JD_SPECIFIC with no target requirement is an inconsistent
    # planner/gate contract and remains fail-closed.
    if specific_empty_contract_error:
        checks["target_role_application_specific"] = False
        checks["specific_interest"] = False

    # Detect the common weak construction:
    # "I would apply [generic noun] to A, B, C, D, E..."
    p3_sentences = sentences(p3)
    keyword_stack_sentences = []

    for sentence in p3_sentences:
        comma_count = sentence.count(",")
        generic_future = any(
            marker in normalize(sentence)
            for marker in (
                "i would apply",
                "i would bring",
                "i can apply",
            )
        )

        if comma_count >= 4 and generic_future:
            keyword_stack_sentences.append(sentence)

    checks["no_paragraph3_keyword_stack"] = (
        not keyword_stack_sentences
    )

    # ================================================================
    # G. RESUME COMPLEMENTARITY, INCLUDING SEMANTIC DUPLICATION
    # ================================================================

    overlap_items = plan.get(
        "resume_overlap_exclusions",
        [],
    )

    semantic_copies = []

    for sentence in sentences(body):
        if len(words(sentence)) < 9:
            continue

        for item in overlap_items:
            bullet = item.get("text", "")
            containment, sequence = semantic_overlap(
                sentence,
                bullet,
            )

            has_reasoning = any(
                marker in normalize(sentence)
                for marker in REASONING_MARKERS
            )

            plan_validation_explanation = (
                plan_authorized_validation_explanation(
                    sentence,
                    validation_methods,
                    sequence,
                )
            )

            # High overlap without reasoning normally means the cover
            # is functioning as a prose rewrite of the resume.
            #
            # The only additional allowed case is a structurally
            # different validation explanation whose methods were
            # already authorized by the deterministic Cover Plan.
            if (
                containment >= 0.55
                or sequence >= 0.72
            ) and not (
                has_reasoning
                or plan_validation_explanation
            ):
                semantic_copies.append({
                    "cover_sentence": sentence,
                    "resume_text": bullet,
                    "token_containment":
                        containment,
                    "sequence_similarity":
                        sequence,
                })

    checks["semantic_resume_complementarity"] = (
        len(semantic_copies) == 0
    )

    # ================================================================
    # H. HUMAN LANGUAGE / AI-PATTERN CONTROLS
    # ================================================================

    canonical_banned = (
        rules.get("writing", {})
        .get("banned_generic_phrases", [])
    )

    # Backward-compatible fallback only.
    if not canonical_banned:
        canonical_banned = (
            rules.get("writing", {})
            .get("forbidden_phrases", [])
        )

    canonical_banned_hits = phrase_hits(
        body,
        canonical_banned,
    )

    ai_pattern_hits = phrase_hits(
        body,
        AI_PATTERN_FAMILIES,
    )

    checks["no_banned_generic_language"] = (
        len(canonical_banned_hits) == 0
    )

    checks["no_ai_pattern_language"] = (
        len(ai_pattern_hits) == 0
    )

    generic_praise_patterns = [
        r"\bprestigious\b",
        r"\brenowned\b",
        r"\bindustry[- ]leading\b",
        r"\bworld[- ]class\b",
        r"\bexceptional reputation\b",
        r"\bleading institution\b",
    ]

    generic_praise_hits = [
        pattern
        for pattern in generic_praise_patterns
        if re.search(pattern, body, re.I)
    ]

    checks["no_generic_company_praise"] = (
        len(generic_praise_hits) == 0
    )

    checks["no_em_dash"] = "—" not in body

    # Sentence cadence. This is deliberately light-touch.
    sentence_lengths = [
        len(words(sentence))
        for sentence in sentences(body)
    ]

    checks["sentence_cadence"] = (
        len(sentence_lengths) >= 5
        and (
            max(sentence_lengths)
            - min(sentence_lengths)
            >= 8
        )
        and len(set(sentence_lengths)) >= 4
    )

    # ================================================================
    # I. JD TERMINOLOGY
    # ================================================================

    jd_terms = cover.get("jd_terms_used", [])

    jd_min = int(
        rules.get("jd_terminology", {}).get(
            "supported_exact_terms_min",
            3,
        )
    )
    jd_max = int(
        rules.get("jd_terminology", {}).get(
            "supported_exact_terms_max",
            6,
        )
    )

    checks["jd_term_count"] = (
        jd_min <= len(jd_terms) <= jd_max
    )

    checks["jd_terms_present"] = all(
        normalize(term) in body_low
        for term in jd_terms
    )

    # ================================================================
    # J. REPORT
    # ================================================================

    from careerops_writing_mechanics import profile
    writing_mechanics = profile(paragraphs, keywords=jd_terms)
    checks['writing_mechanics'] = writing_mechanics['score'] >= 80
    details['writing_mechanics'] = writing_mechanics

    hard_checks = [
        "writing_mechanics",
        "paragraph_count",
        "body_word_count",
        "salutation",
        "closing",
        "signature",
        "final_sentence",
        "paragraph_2_longest",
        "exact_company",
        "exact_position",
        "paragraph1_names_company",
        "paragraph1_names_position",
        "paragraph3_names_company",
        "primary_evidence_matches_plan",
        "secondary_evidence_authorized",
        "anchor_count",
        "planned_anchors_present",
        "anchor_sources_match_primary",
        "technical_mechanics_depth",
        "validation_depth",
        "judgment_and_why_visible",
        "supported_output_visible",
        "paragraph1_specific_hook",
        "target_role_application_specific",
        "specific_interest",
        "semantic_resume_complementarity",
        "no_banned_generic_language",
        "no_generic_company_praise",
        "no_em_dash",
        "sentence_cadence",
        "jd_term_count",
        "jd_terms_present",
    ]

    # Calculated and reported, but not standalone release authority.
    style_advisory_checks = [
        "no_paragraph3_keyword_stack",
        "no_ai_pattern_language",
    ]

    style_warnings = [
        key
        for key in style_advisory_checks
        if not checks.get(key, False)
    ]

    from careerops_temporal_truth import completed_deliverable_errors
    facts = json.loads((SOURCE/'candidate_facts.json').read_text())
    temporal_errors = completed_deliverable_errors(' '.join(paragraphs),cover.get('primary_evidence_ids',[]),facts)
    checks['completed_deliverable_temporal_truth'] = not temporal_errors
    details['temporal_truth_errors'] = temporal_errors
    hard_checks.append('completed_deliverable_temporal_truth')

    failed = [
        key
        for key in hard_checks
        if not checks.get(key, False)
    ]

    passed = not failed

    details.update({
        "body_words": body_words,
        "paragraph_word_counts": [
            len(words(p))
            for p in paragraphs
        ],
        "planned_primary_evidence":
            planned_primary,
        "cover_primary_evidence":
            cover_primary,
        "anchor_validation":
            anchor_validation,
        "mechanic_matches":
            mechanic_matches,
        "validation_matches":
            validation_matches,
        "reasoning_markers_found":
            reasoning_markers_found,
        "decision_verbs_found":
            decision_verbs_found,
        "causal_decision_reasoning":
            causal_decision_reasoning,
        "output_matches":
            output_matches,
        "paragraph1_hook_evidence":
            hook_evidence,
        "target_application_hits":
            sorted(set(target_application_hits)),
        "planned_interest_signals":
            planned_interest_signals,
        "paragraph3_interest_signals":
            p3_interest_signals,
        "keyword_stack_sentences":
            keyword_stack_sentences,
        "semantic_resume_overlap":
            semantic_copies,
        "canonical_banned_phrase_hits":
            canonical_banned_hits,
        "ai_pattern_hits":
            ai_pattern_hits,
        "generic_praise_hits":
            generic_praise_hits,
        "sentence_lengths":
            sentence_lengths,
        "jd_terms_used":
            jd_terms,
    })

    report = {
        "gate": "careerops-cover-gate-v2",
        "cover": str(
            cover_path.relative_to(ROOT)
            if cover_path.is_relative_to(ROOT)
            else cover_path
        ),
        "plan": str(
            plan_path.relative_to(ROOT)
            if plan_path.is_relative_to(ROOT)
            else plan_path
        ),
        "checks": checks,
        "details": details,
        "pass": passed,
        "failed_checks": failed,
        "publication_blockers": failed,
        "style_warnings": style_warnings,
        "target_application_contract": {
            "interest_source": interest_source_for_applicability,
            "interest_confidence": interest_confidence_for_applicability,
            "target_requirement_count": len(target_requirements_for_applicability),
            "general_empty_target_authorized": general_empty_target_authorized,
            "specific_empty_contract_error": specific_empty_contract_error,
        },
        "content_modified": False,
        "model_calls": 0,
    }

    report_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    report_path.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )

    print("=" * 96)
    print("CAREEROPS COVER GATE V2")
    print("=" * 96)

    print("COVER:", report["cover"])
    print(
        "PRIMARY:",
        planned_primary,
        "->",
        "PASS"
        if checks["primary_evidence_matches_plan"]
        else "FAIL",
    )
    print(
        "TECHNICAL MECHANICS:",
        len(mechanic_matches),
    )
    print(
        "VALIDATION SIGNALS:",
        len(validation_matches),
    )
    print(
        "INTEREST SIGNALS:",
        p3_interest_signals,
    )
    print(
        "AI/BANNED HITS:",
        sorted(
            set(
                canonical_banned_hits
                + ai_pattern_hits
            )
        ),
    )
    print(
        "SEMANTIC RESUME COPIES:",
        len(semantic_copies),
    )
    print(
        "FAILED CHECKS:",
        failed if failed else "NONE",
    )

    print("-" * 96)
    print(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        )
    )
    print("=" * 96)
    print(
        "COVER GATE V2:",
        "PASS" if passed else "FAIL",
    )
    print("CONTENT MODIFIED: NO")
    print("MODEL CALLS: 0")
    print(
        "REPORT:",
        report_path.relative_to(ROOT)
        if report_path.is_relative_to(ROOT)
        else report_path,
    )
    print("=" * 96)

    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    from careerops_requirement_authority import run_guarded
    run_guarded(main,RUNTIME,'careerops_cover_gate_v2.py')
