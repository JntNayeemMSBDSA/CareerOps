#!/usr/bin/env python3

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from careerops_requirement_regeneration import canonical_ledger_path


ROOT = Path(__file__).resolve().parents[1]


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by",
    "for", "from", "in", "into", "is", "it", "of", "on",
    "or", "that", "the", "their", "this", "to", "with",
    "will", "would", "should", "must", "may", "can",
    "ability", "abilities", "knowledge", "strong",
    "excellent", "skills", "skill", "required",
    "preferred", "support", "development", "develop",
}


SOFT_CONCEPT_ALIASES = {
    "analytical": {
        "analysis",
        "analytical",
        "analyze",
        "statistical",
        "modeling",
        "models",
    },

    "attention_detail": {
        "validation",
        "validate",
        "validated",
        "quality",
        "qa",
        "reconciliation",
        "audit",
        "audits",
        "fail-closed",
        "integrity",
    },

    "communication": {
        "communication",
        "report",
        "reports",
        "reporting",
        "recommendation",
        "recommendations",
        "dashboard",
        "dashboards",
    },

    #
    # These are behavioral manifestations of JD soft-skill
    # requirements. They are intentionally narrow and are used
    # only when the source requirement itself contains the
    # corresponding concept.
    "critical_thinking": {
        "reasoning",
        "reconcile",
        "reconciliation",
        "interpret",
        "interpretation",
        "evaluate",
        "evaluation",
        "problem-solving",
        "problem",
    },

    "interpersonal": {
        "audience",
        "audiences",
        "stakeholder",
        "stakeholders",
        "collaborate",
        "collaboration",
        "cross-functional",
    },

    "patterns_trends_anomalies": {
        "pattern",
        "patterns",
        "trend",
        "trends",
        "anomaly",
        "anomalies",
    },

    "optimization": {
        "optimize",
        "optimization",
        "improve",
        "improvement",
        "efficiency",
    },
}


FAILURE_PRIORITY = [
    "EVIDENCE",
    "SELECTION",
    "SKILLS",
    "COVER_VALIDATION",
    "WRITING",
    "REQUIREMENTS",
]


def read_json(path):
    if not path.exists():
        raise SystemExit(
            f"Missing required file: {path}"
        )

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def normalize(text):
    value = str(
        text or ""
    )

    value = (
        value
        .replace("\u00a0", " ")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2022", " ")
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def norm(text):
    return normalize(
        text
    ).casefold()


def words(text):
    return re.findall(
        r"[a-z0-9][a-z0-9+.#/'-]*",
        norm(
            text
        ),
    )


def stem(word):
    value = word.casefold()

    for suffix in [
        "ization",
        "ation",
        "ments",
        "ment",
        "ings",
        "ing",
        "ies",
        "ed",
        "es",
        "s",
    ]:
        if (
            value.endswith(
                suffix
            )
            and len(
                value
            )
            > len(
                suffix
            ) + 3
        ):
            if suffix == "ies":
                return (
                    value[
                        :-3
                    ]
                    + "y"
                )

            return value[
                :-len(
                    suffix
                )
            ]

    return value


def content_stems(text):
    return {
        stem(
            token
        )
        for token in words(
            text
        )
        if (
            token not in STOPWORDS
            and len(
                token
            )
            >= 3
        )
    }


def phrase_present(
    phrase,
    text,
):
    needle = norm(
        phrase
    )

    haystack = norm(
        text
    )

    if not needle:
        return False

    return needle in haystack

def concept_token_forms(
    token,
):
    """
    Conservative deterministic morphology for concept matching.

    Keep the existing stemmer, but also retain the common plural
    singular produced by removing a terminal 's'. This avoids the
    legacy stemmer turning words such as 'databases' into 'databas'.
    """
    value = str(
        token
        or ""
    ).casefold()

    forms = {
        value,
        stem(
            value
        ),
    }

    if (
        value.endswith(
            "s"
        )
        and not value.endswith(
            "ss"
        )
        and len(
            value
        ) >= 4
    ):
        singular = value[:-1]

        forms.add(
            singular
        )

        forms.add(
            stem(
                singular
            )
        )

    return {
        item
        for item in forms
        if item
    }


def concept_present(
    phrase,
    text,
):
    """
    Deterministic concept visibility only.

    Exact normalized phrase is preferred. Otherwise every meaningful
    token in the phrase must have a morphological equivalent somewhere
    in the target text. No new semantic synonym is invented here.
    """
    if phrase_present(
        phrase,
        text,
    ):
        return True

    phrase_tokens = [
        token
        for token in words(
            phrase
        )
        if (
            token not in STOPWORDS
            and len(
                token
            ) >= 3
        )
    ]

    text_tokens = [
        token
        for token in words(
            text
        )
        if (
            token not in STOPWORDS
            and len(
                token
            ) >= 3
        )
    ]

    if not phrase_tokens:
        return False

    text_forms = [
        concept_token_forms(
            token
        )
        for token in text_tokens
    ]

    for phrase_token in phrase_tokens:
        phrase_forms = (
            concept_token_forms(
                phrase_token
            )
        )

        if not any(
            phrase_forms
            & candidate_forms
            for candidate_forms
            in text_forms
        ):
            return False

    return True


def resume_units(resume):
    units = []

    summary = normalize(
        resume.get(
            "summary",
            ""
        )
    )

    if summary:
        units.append({
            "location":
                "summary",

            "text":
                summary,

            "kind":
                "summary",
        })

    for block in resume.get(
        "experience",
        [],
    ):
        block_id = (
            block.get(
                "block_id"
            )
            or "UNKNOWN"
        )

        for index, bullet in enumerate(
            block.get(
                "bullets",
                []
            ),
            start=1,
        ):
            units.append({
                "location":
                    f"experience.{block_id}",

                "text":
                    normalize(
                        bullet
                    ),

                "kind":
                    "experience",

                "index":
                    index,
            })

    for project in resume.get(
        "projects",
        [],
    ):
        entity_id = (
            project.get(
                "entity_id"
            )
            or "UNKNOWN"
        )

        for index, bullet in enumerate(
            project.get(
                "bullets",
                []
            ),
            start=1,
        ):
            units.append({
                "location":
                    f"project.{entity_id}",

                "text":
                    normalize(
                        bullet
                    ),

                "kind":
                    "project",

                "index":
                    index,
            })

    return units


def resume_text(resume):
    parts = [
        normalize(
            resume.get(
                "summary",
                ""
            )
        )
    ]

    for block in resume.get(
        "experience",
        [],
    ):
        parts.extend([
            normalize(
                block.get(
                    "company",
                    ""
                )
            ),
            normalize(
                block.get(
                    "title",
                    ""
                )
            ),
            normalize(
                block.get(
                    "dates",
                    ""
                )
            ),
        ])

        parts.extend(
            normalize(
                bullet
            )
            for bullet in block.get(
                "bullets",
                []
            )
        )

    for project in resume.get(
        "projects",
        [],
    ):
        parts.append(
            normalize(
                project.get(
                    "name",
                    ""
                )
            )
        )

        parts.extend(
            normalize(
                bullet
            )
            for bullet in project.get(
                "bullets",
                []
            )
        )

    for row in resume.get(
        "skills",
        [],
    ):
        parts.append(
            normalize(
                row.get(
                    "category",
                    ""
                )
            )
        )

        parts.extend(
            normalize(
                term
            )
            for term in row.get(
                "terms",
                []
            )
        )

    for row in resume.get(
        "education",
        [],
    ):
        for key in [
            "institution",
            "degree",
            "graduation",
            "gpa",
            "honors",
        ]:
            parts.append(
                normalize(
                    row.get(
                        key,
                        ""
                    )
                )
            )

    return "\n".join(
        value
        for value in parts
        if value
    )


def cover_text(cover):
    parts = [
        cover.get(
            "company",
            ""
        ),
        cover.get(
            "position",
            ""
        ),
        cover.get(
            "salutation",
            ""
        ),
        *cover.get(
            "paragraphs",
            [],
        ),
        cover.get(
            "closing",
            ""
        ),
        cover.get(
            "signature",
            ""
        ),
    ]

    return "\n".join(
        normalize(
            value
        )
        for value in parts
        if normalize(
            value
        )
    )


def company_position_from_raw_jd(
    raw_jd,
    requirements,
):
    company = ""
    position = ""

    for line in str(
        raw_jd or ""
    ).splitlines():
        clean = normalize(
            line
        )

        company_match = re.match(
            r"(?i)^company\s*:\s*(.+)$",
            clean,
        )

        if company_match:
            company = normalize(
                company_match.group(1)
            )

        position_match = re.match(
            r"(?i)^position\s*:\s*(.+)$",
            clean,
        )

        if position_match:
            position = normalize(
                position_match.group(1)
            )

    if not position:
        position = normalize(
            requirements.get(
                "target_role_title_candidate",
                ""
            )
        )

    return company, position


def longest_common_contiguous_words(
    left,
    right,
):
    a = words(
        left
    )

    b = words(
        right
    )

    if not a or not b:
        return 0

    previous = [
        0
    ] * (
        len(
            b
        )
        + 1
    )

    best = 0

    for token_a in a:
        current = [
            0
        ] * (
            len(
                b
            )
            + 1
        )

        for j, token_b in enumerate(
            b,
            start=1,
        ):
            if token_a == token_b:
                current[
                    j
                ] = (
                    previous[
                        j - 1
                    ]
                    + 1
                )

                best = max(
                    best,
                    current[
                        j
                    ],
                )

        previous = current

    return best


def requirement_alias_hits(
    requirement_text,
    final_text,
):
    req = norm(
        requirement_text
    )

    final_stems = content_stems(
        final_text
    )

    hits = []

    checks = [
        (
            "analytical",
            (
                "analytical"
                in req
                or "analysis"
                in req
            ),
        ),

        (
            "attention_detail",
            (
                "attention to detail"
                in req
            ),
        ),

        (
            "critical_thinking",
            (
                "critical thinking"
                in req
            ),
        ),

        (
            "interpersonal",
            (
                "interpersonal"
                in req
            ),
        ),

        (
            "communication",
            (
                "communication"
                in req
            ),
        ),

        (
            "patterns_trends_anomalies",
            any(
                value in req
                for value in [
                    "patterns",
                    "trends",
                    "anomalies",
                ]
            ),
        ),

        (
            "optimization",
            any(
                value in req
                for value in [
                    "optimize",
                    "efficiency",
                ]
            ),
        ),
    ]

    for alias_name, applicable in checks:
        if not applicable:
            continue

        aliases = (
            SOFT_CONCEPT_ALIASES[
                alias_name
            ]
        )

        if any(
            stem(
                alias
            )
            in final_stems
            for alias in aliases
        ):
            hits.append(
                alias_name
            )

    return hits


def behavioral_visibility_hits(
    requirement_text,
    final_text,
):
    """
    Recognize strong behavioral manifestations only when the
    SOURCE requirement activates a known concept and the final
    application contains at least two independent manifestations.

    This is deliberately source-conditioned. It does not lower
    the generic lexical/semantic visibility thresholds.
    """
    req = norm(
        requirement_text
    )

    checks = [
        (
            "visualization_presentation",
            (
                sum(
                    concept_present(
                        marker,
                        req,
                    )
                    for marker in (
                        "table",
                        "chart",
                        "graph",
                        "visual",
                        "publication",
                        "presentation",
                    )
                )
                >= 2
            ),
            (
                "data visualization",
                "visualization",
                "visuals",
                "dashboard",
                "dashboards",
                "tableau",
                "power bi",
                "chart",
                "charts",
                "graph",
                "graphs",
                "publication",
                "publications",
                "presentation",
                "presentations",
            ),
            2,
        ),
        (
            "communication",
            (
                "communicat"
                in req
                or (
                    "spoken"
                    in req
                    and
                    "written"
                    in req
                )
            ),
            (
                "communication",
                "communicate",
                "communicated",
                "report",
                "reports",
                "reporting",
                "recommendation",
                "recommendations",
                "dashboard",
                "dashboards",
                "stakeholder",
                "stakeholders",
                "documentation",
                "documented",
                "briefing",
                "briefings",
                "presentation",
                "presentations",
            ),
            2,
        ),
    ]

    hits = []

    for (
        concept,
        applicable,
        aliases,
        minimum_hits,
    ) in checks:
        if not applicable:
            continue

        matched = []

        for alias in aliases:
            if concept_present(
                alias,
                final_text,
            ):
                normalized = norm(
                    alias
                )

                if normalized not in matched:
                    matched.append(
                        normalized
                    )

        if len(
            matched
        ) >= minimum_hits:
            hits.append({
                "concept":
                    concept,

                "matched_aliases":
                    matched,

                "minimum_hits":
                    minimum_hits,
            })

    return hits


def semantic_visibility_hits(
    semantic_requirement,
    final_text,
):
    """
    Use only the deterministic semantic layer already produced
    from the JD.

    Semantic evidence supplements lexical visibility. It does
    not change requirement priority, candidate evidence, or
    historical truth.
    """
    semantic_layer = (
        semantic_requirement
        or {}
    ).get(
        "semantic_layer",
        {}
    )

    candidates = []

    for key in [
        "semantic_equivalents",
        "technical_depth_terms",
    ]:
        for value in semantic_layer.get(
            key,
            [],
        ):
            value = normalize(
                value
            )

            if value:
                candidates.append(
                    value
                )

    candidates = list(
        dict.fromkeys(
            candidates
        )
    )

    final_stems = content_stems(
        final_text
    )

    hits = []

    for value in candidates:
        candidate_stems = content_stems(
            value
        )

        if not candidate_stems:
            continue

        matched = (
            candidate_stems
            & final_stems
        )

        coverage = (
            len(
                matched
            )
            / len(
                candidate_stems
            )
        )

        exact = phrase_present(
            value,
            final_text,
        )

        if (
            exact
            or coverage >= 0.50
        ):
            hits.append({
                "semantic_phrase":
                    value,

                "exact":
                    exact,

                "matched_stems":
                    sorted(
                        matched
                    ),

                "coverage":
                    round(
                        coverage,
                        4,
                    ),
            })

    return hits

def requirement_visibility(
    requirement,
    final_text,
    semantic_requirement=None,
):
    quote = normalize(
        requirement.get(
            "exact_quote"
        )
        or requirement.get(
            "normalized_requirement"
        )
        or ""
    )

    req_stems = content_stems(
        quote
    )

    final_stems = content_stems(
        final_text
    )

    matched_stems = sorted(
        req_stems
        & final_stems
    )

    ratio = (
        len(
            matched_stems
        )
        / len(
            req_stems
        )
        if req_stems
        else 1.0
    )

    anchors = []

    for key in [
        "exact_tools_technologies",
        "exact_work_products",
        "exact_methods",
    ]:
        for value in requirement.get(
            key,
            [],
        ):
            if normalize(
                value
            ):
                anchors.append(
                    normalize(
                        value
                    )
                )

    anchor_hits = [
        value
        for value in anchors
        if concept_present(
            value,
            final_text,
        )
    ]

    alias_hits = requirement_alias_hits(
        quote,
        final_text,
    )

    exact_present = phrase_present(
        quote,
        final_text,
    )

    anchor_ok = (
        not anchors
        or bool(
            anchor_hits
        )
    )

    semantic_hits = (
        semantic_visibility_hits(
            semantic_requirement,
            final_text,
        )
    )

    behavioral_hits = behavioral_visibility_hits(
        quote,
        final_text,
    )

    visible = (
        bool(
            behavioral_hits
        )
        or
        exact_present
        or (
            ratio >= 0.35
            and anchor_ok
        )
        or (
            ratio >= 0.20
            and len(
                alias_hits
            )
            >= 2
        )
        or (
            len(
                alias_hits
            )
            >= 3
        )
        or (
            ratio >= 0.25
            and bool(
                semantic_hits
            )
            and anchor_ok
        )
        or (
            ratio >= 0.20
            and len(
                semantic_hits
            )
            >= 2
            and anchor_ok
        )
    )

    return {
        "visible":
            visible,

        "exact_present":
            exact_present,

        "content_stem_ratio":
            round(
                ratio,
                4,
            ),

        "matched_stems":
            matched_stems,

        "anchors":
            anchors,

        "anchor_hits":
            anchor_hits,

        "alias_hits":
            alias_hits,

        "semantic_hits":
            semantic_hits,
    }


def recursive_entity_ids(
    value,
):
    found = []

    if isinstance(
        value,
        dict,
    ):
        for item in value.values():
            found.extend(
                recursive_entity_ids(
                    item
                )
            )

    elif isinstance(
        value,
        list,
    ):
        for item in value:
            found.extend(
                recursive_entity_ids(
                    item
                )
            )

    elif isinstance(
        value,
        str,
    ):
        found.extend(
            re.findall(
                r"\b(?:EXP|PRJ)-\d{3}\b",
                value,
            )
        )

    return list(
        dict.fromkeys(
            found
        )
    )


def plan_ids_for_key(
    plan,
    key_fragment,
):
    found = []

    def walk(value):
        if isinstance(
            value,
            dict,
        ):
            for key, item in value.items():
                if (
                    key_fragment
                    in str(
                        key
                    ).casefold()
                ):
                    found.extend(
                        recursive_entity_ids(
                            item
                        )
                    )

                walk(
                    item
                )

        elif isinstance(
            value,
            list,
        ):
            for item in value:
                walk(
                    item
                )

    walk(
        plan
    )

    return list(
        dict.fromkeys(
            found
        )
    )


def add_finding(
    findings,
    code,
    failure_class,
    detail,
    *,
    severity="BLOCK",
    context=None,
):
    findings.append({
        "code":
            code,

        "failure_class":
            failure_class,

        "severity":
            severity,

        "detail":
            detail,

        "context":
            context or {},
    })


def choose_failure_class(
    findings,
):
    classes = {
        finding.get(
            "failure_class"
        )
        for finding in findings
        if finding.get(
            "severity"
        )
        == "BLOCK"
    }

    for value in FAILURE_PRIORITY:
        if value in classes:
            return value

    return None

def historical_term_supported(
    term,
    matching_claims,
    supported_components,
):
    """
    Historical capability placement is legitimate when:

    1. the claim map explicitly supports term:<term>, OR
    2. the exact final historical unit has already passed the
       canonical truth architecture as a direct-user override,
       has DIRECT_USER_CORRECTION provenance, contains the
       capability term, and has no unsupported components.

    A generic assumed capability without either condition
    remains blocked.
    """
    normalized_term = normalize(
        term
    )

    if not normalized_term:
        return False

    component_key = (
        "term:"
        + normalized_term
    ).casefold()

    if (
        component_key
        in supported_components
    ):
        return True

    for claim in matching_claims:
        support_types = {
            str(
                value
            )
            for value in claim.get(
                "support_type",
                [],
            )
        }

        if (
            claim.get(
                "status"
            )
            == "SUPPORTED"
            and
            "VERIFIED_EVIDENCE"
            in support_types
            and not claim.get(
                "unsupported_components",
                [],
            )
            and concept_present(
                normalized_term,
                claim.get(
                    "text",
                    "",
                ),
            )
        ):
            return True

    for claim in matching_claims:
        if (
            claim.get(
                "status"
            )
            !=
            "SUPPORTED_BY_DIRECT_USER_OVERRIDE"
        ):
            continue

        support_types = {
            str(
                value
            )
            for value in claim.get(
                "support_type",
                [],
            )
        }

        if (
            "DIRECT_USER_CORRECTION"
            not in support_types
        ):
            continue

        if claim.get(
            "unsupported_components",
            []
        ):
            continue

        if not phrase_present(
            normalized_term,
            claim.get(
                "text",
                "",
            ),
        ):
            continue

        return True

    return False


def audit_runtime(
    runtime,
):
    runtime = Path(
        runtime
    ).resolve()

    from careerops_requirement_authority import authority, check_artifact
    current_authority, canonical_rows = authority(runtime)
    for artifact in ['jd_semantic_map.json','requirement_evidence_map.json','constraint_validation.json','experience_selection.json','project_selection.json','technical_skills_plan.json','cover_plan.json']:
        check_artifact(runtime, artifact, require_stamp=True)

    jd_intake = read_json(
        runtime
        / "jd_intake.json"
    )

    requirements = read_json(
        canonical_ledger_path(runtime)
    )

    semantic_map_path = (
        runtime
        / "jd_semantic_map.json"
    )

    semantic_map = (
        read_json(
            semantic_map_path
        )
        if semantic_map_path.exists()
        else {
            "requirements": []
        }
    )

    semantic_by_id = {
        row.get(
            "requirement_id"
        ): row
        for row in semantic_map.get(
            "requirements",
            [],
        )
        if row.get(
            "requirement_id"
        )
    }

    evidence_map = read_json(
        runtime
        / "requirement_evidence_map.json"
    )

    experience_selection = read_json(
        runtime
        / "experience_selection.json"
    )

    project_selection = read_json(
        runtime
        / "project_selection.json"
    )

    skills_plan = read_json(
        runtime
        / "technical_skills_plan.json"
    )

    resume = read_json(
        runtime
        / "generated_resume_content_pair_candidate.json"
    )

    cover = read_json(
        runtime
        / "generated_cover_letter_pair_candidate.json"
    )

    claim_map = read_json(
        runtime
        / "claim_map.json"
    )

    truth_gate = read_json(
        runtime
        / "truth_gate.json"
    )

    local_truth_gate = read_json(
        runtime
        / "local_truth_gate.json"
    )

    cover_plan_path = (
        runtime
        / "cover_plan.json"
    )

    cover_plan = (
        read_json(
            cover_plan_path
        )
        if cover_plan_path.exists()
        else {}
    )

    findings = []

    raw_jd = jd_intake.get(
        "raw_jd_text",
        ""
    )

    raw_jd_norm = norm(
        raw_jd
    )

    resume_final = resume_text(
        resume
    )

    cover_final = cover_text(
        cover
    )

    combined_final = (
        resume_final
        + "\n"
        + cover_final
    )

    # ========================================================
    # 1. ORIGINAL JD -> REQUIREMENT GRAPH PROVENANCE
    # ========================================================

    req_rows = requirements.get(
        "requirements",
        [],
    )

    if (
        requirements.get(
            "requirement_count"
        )
        != len(
            req_rows
        )
    ):
        add_finding(
            findings,
            "REQ_COUNT_MISMATCH",
            "REQUIREMENTS",
            (
                "Requirement count does not match "
                "requirement ledger length."
            ),
        )

    for row in req_rows:
        requirement_id = row.get(
            "requirement_id"
        )

        quote = normalize(
            row.get(
                "exact_quote",
                ""
            )
        )

        if not quote:
            add_finding(
                findings,
                "REQ_MISSING_EXACT_QUOTE",
                "REQUIREMENTS",
                (
                    f"{requirement_id} has no exact "
                    "original-JD quote."
                ),
                context={
                    "requirement_id":
                        requirement_id,
                },
            )

            continue

        if norm(
            quote
        ) not in raw_jd_norm:
            add_finding(
                findings,
                "REQ_QUOTE_NOT_IN_ORIGINAL_JD",
                "REQUIREMENTS",
                (
                    f"{requirement_id} exact quote is "
                    "not present in the original JD."
                ),
                context={
                    "requirement_id":
                        requirement_id,

                    "quote":
                        quote,
                },
            )

    # ========================================================
    # 2. P0/P1 SUPPORTED REQUIREMENT VISIBILITY
    # ========================================================

    evidence_by_id = {
        row.get(
            "requirement_id"
        ):
            row
        for row in evidence_map.get(
            "requirements",
            [],
        )
    }

    visibility_rows = []

    for row in req_rows:
        if row.get(
            "priority"
        ) not in {
            "P0",
            "P1",
        }:
            continue

        requirement_id = row.get(
            "requirement_id"
        )

        mapped = evidence_by_id.get(
            requirement_id,
            {},
        )

        verified = bool(
            mapped.get(
                "verified_evidence_candidates"
            )
        )

        contextual = bool(
            mapped.get(
                "contextual_capability_candidates"
            )
        )

        supported = (
            verified
            or contextual
            or mapped.get(
                "coverage_state"
            )
            == "VERIFIED_EVIDENCE_AVAILABLE"
        )

        result = requirement_visibility(
            row,
            combined_final,
            semantic_by_id.get(
                requirement_id,
                {},
            ),
        )

        visibility_rows.append({
            "requirement_id":
                requirement_id,

            "priority":
                row.get(
                    "priority"
                ),

            "supported_upstream":
                supported,

            **result,
        })

        if (
            supported
            and not result[
                "visible"
            ]
        ):
            priority = row.get(
                "priority"
            )

            if priority == "P0":
                add_finding(
                    findings,
                    "SUPPORTED_P0_P1_OMITTED",
                    "WRITING",
                    (
                        f"{requirement_id} has verified or "
                        "authorized support but is not visibly "
                        "represented in the final application."
                    ),
                    context={
                        "requirement_id":
                            requirement_id,

                        "priority":
                            priority,

                        "quote":
                            row.get(
                                "exact_quote"
                            ),

                        "visibility":
                            result,
                    },
                )

            else:

                #
                # P1 means core work/responsibility, not dispositive
                # eligibility. Keep the diagnostic but do not fail
                # release merely because a one-page application does
                # not visibly restate every supported core duty.
                add_finding(
                    findings,
                    "SUPPORTED_P1_NOT_VISIBLE",
                    "WRITING",
                    (
                        f"{requirement_id} is supported upstream "
                        "but is not visibly represented in the "
                        "final application."
                    ),
                    severity="ADVISORY",
                    context={
                        "requirement_id":
                            requirement_id,

                        "priority":
                            priority,

                        "quote":
                            row.get(
                                "exact_quote"
                            ),

                        "visibility":
                            result,
                    },
                )

    # ========================================================
    # 3. EXPECTED / PROTECTED SKILL VISIBILITY
    # ========================================================

    #
    # exact_jd_tools may contain preferred/P3 terms. Release-critical
    # protection comes only from the deterministic P0/P1 contract.
    protected_terms = []

    protected_terms.extend(
        skills_plan.get(
            "protected_exact_p0_p1_terms",
            [],
        )
    )

    protected_terms = list(
        dict.fromkeys(
            normalize(
                value
            )
            for value in protected_terms
            if normalize(
                value
            )
        )
    )

    #
    # protected_exact_p0_p1_terms is a presentation-cleanup
    # protection inventory. The Skills builder explicitly says
    # it does NOT force every protected term onto Technical Skills.
    #
    # Final Audit therefore release-blocks a protected skill only
    # when the deterministic Skills planner itself selected that
    # term onto visible_skill_lines and the final application then
    # omitted it.
    planned_skill_terms = [
        value
        for skill_line
        in skills_plan.get(
            "visible_skill_lines",
            [],
        )
        if isinstance(
            skill_line,
            dict,
        )
        for value
        in skill_line.get(
            "terms",
            [],
        )
        if normalize(
            value
        )
    ]

    planned_skill_text = " ".join(
        str(
            value
        )
        for value in planned_skill_terms
    )

    release_protected_terms = [
        term
        for term in protected_terms
        if concept_present(
            term,
            planned_skill_text,
        )
    ]

    unplanned_missing_protected_terms = [
        term
        for term in protected_terms
        if not concept_present(
            term,
            planned_skill_text,
        )
        and not concept_present(
            term,
            combined_final,
        )
    ]

    if unplanned_missing_protected_terms:
        add_finding(
            findings,
            "PROTECTED_TERM_NOT_SELECTED_FOR_VISIBLE_SKILLS",
            "SKILLS",
            (
                "P0/P1 exact terms were protected from "
                "presentation cleanup but were not selected "
                "by the deterministic Skills planner for the "
                "visible Skills surface."
            ),
            severity="ADVISORY",
            context={
                "terms":
                    unplanned_missing_protected_terms,
            },
        )

    missing_protected_terms = [
        term
        for term in release_protected_terms
        if not concept_present(
            term,
            combined_final,
        )
    ]

    if missing_protected_terms:
        add_finding(
            findings,
            "SUPPORTED_EXPECTED_SKILL_OMISSION",
            "SKILLS",
            (
                "Protected JD-relevant terms from the "
                "deterministic skills plan are missing "
                "from the final application."
            ),
            context={
                "missing_terms":
                    missing_protected_terms,
            },
        )

    # ========================================================
    # 4. SELECTED ARTIFACT OMISSIONS
    # ========================================================

    selected_exp_ids = [
        row.get(
            "block_id"
        )
        for row in experience_selection.get(
            "selected_experience_blocks",
            [],
        )
        if row.get(
            "block_id"
        )
    ]

    final_exp_ids = [
        row.get(
            "block_id"
        )
        for row in resume.get(
            "experience",
            [],
        )
        if row.get(
            "block_id"
        )
    ]

    if selected_exp_ids != final_exp_ids:
        add_finding(
            findings,
            "SELECTED_EXPERIENCE_OMISSION_OR_REORDER",
            "SELECTION",
            (
                "Final resume experience identities do "
                "not exactly match deterministic selection."
            ),
            context={
                "selected":
                    selected_exp_ids,

                "final":
                    final_exp_ids,
            },
        )

    selected_project_ids = [
        row.get(
            "entity_id"
        )
        for row in project_selection.get(
            "selected_projects",
            [],
        )
        if row.get(
            "entity_id"
        )
    ]

    final_project_ids = [
        row.get(
            "entity_id"
        )
        for row in resume.get(
            "projects",
            [],
        )
        if row.get(
            "entity_id"
        )
    ]

    if selected_project_ids != final_project_ids:
        add_finding(
            findings,
            "SELECTED_PROJECT_OMISSION_OR_REORDER",
            "SELECTION",
            (
                "Final resume project identities do not "
                "exactly match deterministic selection."
            ),
            context={
                "selected":
                    selected_project_ids,

                "final":
                    final_project_ids,
            },
        )

    planned_categories = [
        normalize(
            row.get(
                "category"
            )
        )
        for row in skills_plan.get(
            "visible_skill_lines",
            [],
        )
        if normalize(
            row.get(
                "category"
            )
        )
    ]

    final_categories = [
        normalize(
            row.get(
                "category"
            )
        )
        for row in resume.get(
            "skills",
            [],
        )
        if normalize(
            row.get(
                "category"
            )
        )
    ]

    if (
        planned_categories
        and planned_categories
        != final_categories
    ):
        add_finding(
            findings,
            "SKILL_CATEGORY_STRUCTURE_OMISSION",
            "SKILLS",
            (
                "Final skill-category structure does not "
                "match deterministic skills plan."
            ),
            context={
                "planned":
                    planned_categories,

                "final":
                    final_categories,
            },
        )

    # ========================================================
    # 5. CLAIM MAP COMPLETENESS + TRUTH STATUS
    # ========================================================

    final_units = resume_units(
        resume
    )

    claim_rows = claim_map.get(
        "claims",
        [],
    )

    claim_by_text = {}

    for claim in claim_rows:
        claim_by_text.setdefault(
            norm(
                claim.get(
                    "text",
                    ""
                )
            ),
            [],
        ).append(
            claim
        )

    missing_claim_units = []

    for unit in final_units:
        matches = claim_by_text.get(
            norm(
                unit[
                    "text"
                ]
            ),
            [],
        )

        if not matches:
            missing_claim_units.append(
                unit
            )

    if missing_claim_units:
        add_finding(
            findings,
            "FINAL_RESUME_CLAIM_NOT_AUDITED",
            "EVIDENCE",
            (
                "One or more final factual resume units "
                "are absent from the canonical claim map."
            ),
            context={
                "missing_units":
                    missing_claim_units,
            },
        )

    allowed_statuses = {
        "SUPPORTED",
        "SUPPORTED_BY_DIRECT_USER_OVERRIDE",
    }

    bad_claims = [
        {
            "claim_id":
                claim.get(
                    "claim_id"
                ),

            "status":
                claim.get(
                    "status"
                ),

            "unsupported_components":
                claim.get(
                    "unsupported_components",
                    [],
                ),
        }
        for claim in claim_rows
        if (
            claim.get(
                "status"
            )
            not in allowed_statuses
            or claim.get(
                "unsupported_components"
            )
        )
    ]

    if bad_claims:
        add_finding(
            findings,
            "UNSUPPORTED_FINAL_RESUME_CLAIM",
            "EVIDENCE",
            (
                "Canonical truth map contains unsupported "
                "or partially supported final claims."
            ),
            context={
                "claims":
                    bad_claims,
            },
        )

    if (
        truth_gate.get(
            "gate"
        )
        != "PASS"
        or local_truth_gate.get(
            "gate"
        )
        != "PASS"
    ):
        add_finding(
            findings,
            "UPSTREAM_TRUTH_GATE_NOT_PASS",
            "EVIDENCE",
            (
                "Final application audit requires both "
                "deterministic truth gates to pass."
            ),
            context={
                "truth_gate":
                    truth_gate.get(
                        "gate"
                    ),

                "local_truth_gate":
                    local_truth_gate.get(
                        "gate"
                    ),
            },
        )

    # ========================================================
    # 6. ASSUMED/DIRECT CAPABILITY HISTORICAL PROJECTION
    # ========================================================

    direct_only_terms = []

    for row in skills_plan.get(
        "ranked_skill_candidates",
        [],
    ):
        if row.get(
            "claim_class"
        ) != "DIRECT_USER_CONFIRMED_CAPABILITY":
            continue

        provenance = set(
            row.get(
                "provenance",
                [],
            )
        )

        if (
            "SELECTED_VERIFIED_EVIDENCE"
            not in provenance
        ):
            term = normalize(
                row.get(
                    "term"
                )
            )

            if term:
                direct_only_terms.append(
                    term
                )

    direct_only_terms = list(
        dict.fromkeys(
            direct_only_terms
        )
    )

    historical_projection_findings = []

    for unit in final_units:
        if unit[
            "kind"
        ] not in {
            "experience",
            "project",
        }:
            continue

        matching_claims = claim_by_text.get(
            norm(
                unit[
                    "text"
                ]
            ),
            [],
        )

        supported_components = {
            str(
                component
            ).casefold()
            for claim in matching_claims
            for component in claim.get(
                "supported_components",
                [],
            )
        }

        for term in direct_only_terms:
            if not phrase_present(
                term,
                unit[
                    "text"
                ],
            ):
                continue

            explicit_support = (
                historical_term_supported(
                    term,
                    matching_claims,
                    supported_components,
                )
            )

            if not explicit_support:
                historical_projection_findings.append({
                    "term":
                        term,

                    "location":
                        unit[
                            "location"
                        ],

                    "text":
                        unit[
                            "text"
                        ],
                })

    if historical_projection_findings:
        add_finding(
            findings,
            "ASSUMED_SKILL_HISTORICAL_PROJECTION",
            "EVIDENCE",
            (
                "A direct-user/market capability appears "
                "inside historical experience/project text "
                "without explicit claim-map support."
            ),
            context={
                "placements":
                    historical_projection_findings,
            },
        )

    # ========================================================
    # 7. COVER EVIDENCE / ANCHOR / PLAN BOUNDARIES
    # ========================================================

    company, position = company_position_from_raw_jd(
        raw_jd,
        requirements,
    )

    if (
        company
        and normalize(
            cover.get(
                "company"
            )
        )
        != company
    ):
        add_finding(
            findings,
            "COVER_COMPANY_MISMATCH",
            "COVER_VALIDATION",
            (
                "Cover company does not match original JD."
            ),
            context={
                "expected":
                    company,

                "actual":
                    cover.get(
                        "company"
                    ),
            },
        )

    if (
        position
        and normalize(
            cover.get(
                "position"
            )
        )
        != position
    ):
        add_finding(
            findings,
            "COVER_POSITION_MISMATCH",
            "COVER_VALIDATION",
            (
                "Cover position does not match original JD."
            ),
            context={
                "expected":
                    position,

                "actual":
                    cover.get(
                        "position"
                    ),
            },
        )

    cover_evidence_ids = list(
        dict.fromkeys(
            cover.get(
                "primary_evidence_ids",
                [],
            )
            + cover.get(
                "secondary_evidence_ids",
                [],
            )
        )
    )

    known_evidence_ids = set(
        selected_project_ids
    )

    for row in experience_selection.get(
        "selected_experience_blocks",
        [],
    ):
        known_evidence_ids.update(
            row.get(
                "evidence_ids",
                [],
            )
        )

    for row in evidence_map.get(
        "requirements",
        [],
    ):
        known_evidence_ids.update(
            item.get(
                "entity_id"
            )
            for item in row.get(
                "verified_evidence_candidates",
                [],
            )
            if isinstance(
                item,
                dict,
            )
            and item.get(
                "entity_id"
            )
        )

    unknown_cover_evidence = [
        value
        for value in cover_evidence_ids
        if value not in known_evidence_ids
    ]

    if unknown_cover_evidence:
        add_finding(
            findings,
            "COVER_UNKNOWN_EVIDENCE_ID",
            "COVER_VALIDATION",
            (
                "Cover declares evidence IDs not present "
                "in authorized evidence artifacts."
            ),
            context={
                "unknown_ids":
                    unknown_cover_evidence,
            },
        )

    cover_paragraph_text = "\n".join(
        cover.get(
            "paragraphs",
            [],
        )
    )

    bad_anchors = []

    for anchor in cover.get(
        "numerical_anchors",
        [],
    ):
        anchor_text = normalize(
            anchor.get(
                "text"
            )
        )

        source_entity = anchor.get(
            "source_entity"
        )

        if (
            not anchor_text
            or not phrase_present(
                anchor_text,
                cover_paragraph_text,
            )
            or source_entity
            not in cover_evidence_ids
        ):
            bad_anchors.append(
                anchor
            )

    if bad_anchors:
        add_finding(
            findings,
            "COVER_NUMERICAL_ANCHOR_INVALID",
            "COVER_VALIDATION",
            (
                "Cover numerical anchors are missing from "
                "body text or point outside declared evidence."
            ),
            context={
                "anchors":
                    bad_anchors,
            },
        )

    declared_jd_terms = [
        normalize(
            value
        )
        for value in cover.get(
            "jd_terms_used",
            [],
        )
        if normalize(
            value
        )
    ]

    invalid_jd_terms = [
        value
        for value in declared_jd_terms
        if (
            not phrase_present(
                value,
                raw_jd,
            )
            or not phrase_present(
                value,
                cover_paragraph_text,
            )
        )
    ]

    if invalid_jd_terms:
        add_finding(
            findings,
            "COVER_DECLARED_JD_TERM_INVALID",
            "COVER_VALIDATION",
            (
                "Cover declares JD terms not grounded in "
                "both original JD and final cover text."
            ),
            context={
                "invalid_terms":
                    invalid_jd_terms,
            },
        )

    plan_primary = plan_ids_for_key(
        cover_plan,
        "primary_evidence",
    )

    if (
        plan_primary
        and cover.get(
            "primary_evidence_ids",
            [],
        )
        != plan_primary
    ):
        add_finding(
            findings,
            "COVER_PRIMARY_EVIDENCE_PLAN_DRIFT",
            "COVER_VALIDATION",
            (
                "Final cover primary evidence differs from "
                "deterministic cover plan."
            ),
            context={
                "plan":
                    plan_primary,

                "cover":
                    cover.get(
                        "primary_evidence_ids",
                        [],
                    ),
            },
        )

    # ========================================================
    # 8. JD COPYING
    # ========================================================

    final_text_units = [
        *[
            unit[
                "text"
            ]
            for unit in final_units
        ],
        *[
            normalize(
                paragraph
            )
            for paragraph in cover.get(
                "paragraphs",
                [],
            )
        ],
    ]

    copy_hits = []

    for row in req_rows:
        quote = normalize(
            row.get(
                "exact_quote",
                ""
            )
        )

        quote_words = words(
            quote
        )

        if len(
            quote_words
        ) < 8:
            continue

        for final_unit in final_text_units:
            common = (
                longest_common_contiguous_words(
                    quote,
                    final_unit,
                )
            )

            ratio = (
                common
                / len(
                    quote_words
                )
            )

            exact_requirement_copy = (
                len(
                    quote_words
                )
                >= 8
                and phrase_present(
                    quote,
                    final_unit,
                )
            )

            length_aware_near_copy = (
                common >= 12
                or (
                    common >= 10
                    and ratio >= 0.85
                )
                or (
                    common >= 8
                    and ratio >= 0.90
                )
            )

            if (
                exact_requirement_copy
                or length_aware_near_copy
            ):
                copy_hits.append({
                    "requirement_id":
                        row.get(
                            "requirement_id"
                        ),

                    "common_contiguous_words":
                        common,

                    "requirement_word_count":
                        len(
                            quote_words
                        ),

                    "ratio":
                        round(
                            ratio,
                            4,
                        ),

                    "jd_quote":
                        quote,

                    "final_unit":
                        final_unit,
                })

    if copy_hits:
        add_finding(
            findings,
            "JD_NEAR_VERBATIM_COPYING",
            "WRITING",
            (
                "Final application contains a long "
                "near-verbatim sequence from the JD."
            ),
            context={
                "matches":
                    copy_hits,
            },
        )

    # ========================================================
    # 9. RESUME BULLET -> COVER COPYING
    # ========================================================

    resume_bullets = [
        unit[
            "text"
        ]
        for unit in final_units
        if unit[
            "kind"
        ] in {
            "experience",
            "project",
        }
    ]

    overlap_hits = []

    for bullet in resume_bullets:
        bullet_words = words(
            bullet
        )

        if len(
            bullet_words
        ) < 12:
            continue

        for paragraph in cover.get(
            "paragraphs",
            [],
        ):
            common = (
                longest_common_contiguous_words(
                    bullet,
                    paragraph,
                )
            )

            ratio = (
                common
                / len(
                    bullet_words
                )
            )

            if (
                common >= 14
                or (
                    common >= 12
                    and ratio >= 0.70
                )
            ):
                overlap_hits.append({
                    "common_contiguous_words":
                        common,

                    "bullet_word_count":
                        len(
                            bullet_words
                        ),

                    "ratio":
                        round(
                            ratio,
                            4,
                        ),

                    "bullet":
                        bullet,

                    "cover_paragraph":
                        normalize(
                            paragraph
                        ),
                })

    if overlap_hits:
        add_finding(
            findings,
            "COVER_RESUME_BULLET_COPYING",
            "WRITING",
            (
                "Cover letter copies too much contiguous "
                "resume-bullet language."
            ),
            context={
                "matches":
                    overlap_hits,
            },
        )

    # ========================================================
    # 10. KEYWORD STUFFING
    # ========================================================

    stuffing_hits = []

    for term in list(
        dict.fromkeys(
            declared_jd_terms
            + protected_terms
        )
    ):
        if len(
            words(
                term
            )
        ) < 2:
            continue

        count = len(
            re.findall(
                re.escape(
                    norm(
                        term
                    )
                ),
                norm(
                    combined_final
                ),
            )
        )

        if count > 5:
            stuffing_hits.append({
                "term":
                    term,

                "count":
                    count,
            })

    if stuffing_hits:
        add_finding(
            findings,
            "JD_KEYWORD_STUFFING",
            "WRITING",
            (
                "JD phrase repetition exceeds deterministic "
                "naturalness threshold."
            ),
            context={
                "terms":
                    stuffing_hits,
            },
        )

    if skills_plan.get("skills_stack_contract"):
        from careerops_skills_stack import audit_stack
        stack_audit = audit_stack(resume.get("skills", []), skills_plan["skills_stack_contract"])
        if stack_audit["gate"] != "PASS":
            add_finding(findings, "SKILLS_STACK_QUALITY", "SKILLS",
                        "Final skills contain duplicated, misplaced, generic or unsupported concepts.",
                        context=stack_audit)
        if resume.get("skills", []) != skills_plan["skills_stack_contract"]["visible_skill_lines"]:
            add_finding(findings, "APPROVED_SKILLS_STACK_DRIFT", "SKILLS",
                        "Final skills differ from the current source-bound curated plan.")

    blocking = [
        finding
        for finding in findings
        if finding.get(
            "severity"
        )
        == "BLOCK"
    ]

    report = {
        "schema_version":
            "career-ops-final-application-audit-v1",

        "gate":
            (
                "PASS"
                if not blocking
                else "FAIL"
            ),

        "pass":
            not blocking,

        "failure_class":
            choose_failure_class(
                findings
            ),

        "model_calls":
            0,

        "policy": {
            "original_jd_compared_directly":
                True,

            "requirement_ledger_not_blindly_trusted":
                True,

            "truth_map_reused_not_reinvented":
                True,

            "direct_user_capability_allowed_as_skill":
                True,

            "historical_skill_placement_requires_support":
                True,

            "final_resume_claim_map_completeness_required":
                True,

            "supported_p0_p1_visibility_required":
                False,

            "supported_p0_visibility_required":
                True,

            "supported_p1_visibility_advisory":
                True,

            "protected_skill_release_critical_only_if_planned_visible":
                True,

            "jd_copying_blocked":
                True,

            "keyword_stuffing_blocked":
                True,
        },

        "summary": {
            "requirement_count":
                len(
                    req_rows
                ),

            "p0_p1_count":
                sum(
                    row.get(
                        "priority"
                    )
                    in {
                        "P0",
                        "P1",
                    }
                    for row in req_rows
                ),

            "resume_factual_unit_count":
                len(
                    final_units
                ),

            "claim_map_count":
                len(
                    claim_rows
                ),

            "protected_term_count":
                len(
                    protected_terms
                ),

            "finding_count":
                len(
                    findings
                ),

            "blocking_finding_count":
                len(
                    blocking
                ),
        },

        "requirement_visibility":
            visibility_rows,

        "protected_terms":
            protected_terms,

        "findings":
            findings,
    }

    report["requirement_authority"] = current_authority
    return report


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--runtime",
        required=True,
    )

    parser.add_argument(
        "--report",
        required=True,
    )

    args = parser.parse_args()

    runtime = Path(
        args.runtime
    ).expanduser().resolve()

    report_path = Path(
        args.report
    ).expanduser()

    if not report_path.is_absolute():
        report_path = (
            ROOT
            / report_path
        )

    report_path = (
        report_path
        .resolve()
    )

    report = audit_runtime(
        runtime
    )

    report_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    report_path.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    print("=" * 96)
    print(
        "INDEPENDENT FINAL APPLICATION AUDIT"
    )
    print("=" * 96)

    print(
        "runtime:",
        runtime,
    )

    print(
        "gate:",
        report[
            "gate"
        ],
    )

    print(
        "failure_class:",
        report[
            "failure_class"
        ],
    )

    print(
        "requirements:",
        report[
            "summary"
        ][
            "requirement_count"
        ],
    )

    print(
        "p0_p1:",
        report[
            "summary"
        ][
            "p0_p1_count"
        ],
    )

    print(
        "resume_factual_units:",
        report[
            "summary"
        ][
            "resume_factual_unit_count"
        ],
    )

    print(
        "claim_map_count:",
        report[
            "summary"
        ][
            "claim_map_count"
        ],
    )

    print(
        "findings:",
        report[
            "summary"
        ][
            "finding_count"
        ],
    )

    print(
        "blocking_findings:",
        report[
            "summary"
        ][
            "blocking_finding_count"
        ],
    )

    print()

    for finding in report[
        "findings"
    ]:
        print(
            finding[
                "severity"
            ],
            finding[
                "failure_class"
            ],
            finding[
                "code"
            ],
            "::",
            finding[
                "detail"
            ],
        )

    print()
    print(
        "model_calls: 0"
    )

    print(
        "report:",
        report_path,
    )

    if not report[
        "pass"
    ]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
