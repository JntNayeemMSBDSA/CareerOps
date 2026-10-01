#!/usr/bin/env python3

import json
import math
import os
import re
import statistics
from collections import Counter
from pathlib import Path
from careerops_requirement_regeneration import canonical_ledger_path

from careerops_runtime import runtime_dir
import careerops_human_gate_v2 as base


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = runtime_dir(ROOT)

RESUME_FILE = Path(
    os.environ.get(
        "CAREEROPS_RESUME_INPUT",
        str(
            RUNTIME
            / "generated_resume_content_pair_candidate.json"
        ),
    )
).expanduser().resolve()

TRUTH_FILE = RUNTIME / "local_truth_gate.json"
ATS_FILE = RUNTIME / "ats_gate.json"
ROUTE_FILE = RUNTIME / "role_routing.json"
REQUIREMENTS_FILE = canonical_ledger_path(RUNTIME)
EVIDENCE_FILE = RUNTIME / "requirement_evidence_map.json"
EXPERIENCE_FILE = RUNTIME / "experience_selection.json"
PROJECT_FILE = RUNTIME / "project_selection.json"
SKILLS_FILE = RUNTIME / "technical_skills_plan.json"

OUT = RUNTIME / "human_gate_v21.json"
AUDIT = RUNTIME / "human_audit_v21.json"

PASS_THRESHOLD = 85.0

LOCKED_DIMENSIONS = list(
    base.LOCKED_DIMENSIONS
)

HARD_FLOORS = dict(
    base.HARD_FLOORS
)

# Demonstrated technical evidence matters more in the
# current high-volume / skills-first market.
HARD_FLOORS[
    "technical_depth"
] = 60.0


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be",
    "by", "for", "from", "in", "into", "is",
    "of", "on", "or", "the", "to", "with",
    "using", "use", "used", "their", "all",
    "relevant", "required", "ability", "skills",
}


OWNERSHIP_VERBS = {
    "architected",
    "automated",
    "built",
    "created",
    "delivered",
    "designed",
    "developed",
    "directed",
    "engineered",
    "established",
    "implemented",
    "launched",
    "led",
    "managed",
    "modeled",
    "optimized",
    "owned",
    "produced",
    "redesigned",
    "streamlined",
}


DECISION_VALUE_TERMS = {
    "capacity",
    "commercial",
    "cost",
    "customer",
    "decision",
    "efficiency",
    "forecast",
    "leadership",
    "margin",
    "market",
    "operational",
    "operations",
    "planning",
    "pricing",
    "quality",
    "revenue",
    "risk",
    "stakeholder",
    "strategy",
}


ROLE_WEIGHT_MULTIPLIERS = {
    "DATA_TECHNICAL": {
        "technical_depth": 1.16,
        "specificity": 1.10,
        "first_evidence_strength": 1.05,
        "differentiation": 1.05,
    },

    "REPORTING_BI": {
        "business_relevance": 1.14,
        "technical_depth": 1.08,
        "first_evidence_strength": 1.08,
        "strongest_evidence_placement": 1.06,
    },

    "BUSINESS_ANALYSIS": {
        "business_relevance": 1.16,
        "career_coherence": 1.10,
        "natural_language": 1.06,
        "first_evidence_strength": 1.06,
    },

    "RESEARCH_INSTITUTIONAL": {
        "credibility": 1.15,
        "specificity": 1.10,
        "readability": 1.08,
        "business_relevance": 0.94,
    },

    "DEFAULT": {},
}


def load(path):
    if not path.exists():
        raise SystemExit(
            f"Missing required file: {path}"
        )

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def clamp(value):
    return base.clamp(
        value
    )


def tokens(text):
    return [
        token.lower()
        for token in re.findall(
            r"[A-Za-z0-9+#./-]+",
            str(text or ""),
        )
    ]


def meaningful_tokens(text):
    return {
        token
        for token in tokens(text)
        if (
            len(token) >= 3
            and token not in STOPWORDS
        )
    }


def phrase_present(
    term,
    text,
):
    term = str(
        term or ""
    ).strip()

    text = str(
        text or ""
    )

    if not term:
        return False

    variants = [
        term
    ]

    if "/" in term:
        variants.extend(
            piece.strip()
            for piece in term.split("/")
            if piece.strip()
        )

    for variant in variants:
        pattern = (
            r"(?<![a-z0-9])"
            + re.escape(
                variant.lower()
            )
            + r"(?![a-z0-9])"
        )

        if re.search(
            pattern,
            text.lower(),
        ):
            return True

    return False


def resume_skill_text(
    resume,
):
    terms = []

    for line in resume.get(
        "skills",
        [],
    ):
        terms.extend(
            line.get(
                "terms",
                [],
            )
        )

    return " | ".join(
        str(x)
        for x in terms
    )


def resume_bullet_text(
    resume,
):
    return "\n".join(
        row["text"]
        for row in base.resume_bullets(
            resume
        )
    )


def requirement_lookup(
    requirements,
):
    return {
        row.get(
            "requirement_id"
        ): row
        for row in requirements.get(
            "requirements",
            [],
        )
        if row.get(
            "requirement_id"
        )
    }


def verified_requirement_ids(
    evidence_map,
):
    return {
        row.get(
            "requirement_id"
        )
        for row in evidence_map.get(
            "requirements",
            [],
        )
        if (
            row.get(
                "requirement_id"
            )
            and row.get(
                "coverage_state"
            )
            == "VERIFIED_EVIDENCE_AVAILABLE"
        )
    }


def priority_weight(
    priority,
):
    return {
        "P0": 5.0,
        "P1": 3.0,
    }.get(
        priority,
        0.0,
    )


def selected_entity_support(
    requirements,
    evidence_map,
    experience,
    projects,
):
    req_by_id = requirement_lookup(
        requirements
    )

    verified_ids = (
        verified_requirement_ids(
            evidence_map
        )
    )

    support = {}

    for block in experience.get(
        "selected_experience_blocks",
        [],
    ):
        key = (
            "experience",
            block.get(
                "block_id"
            ),
        )

        ids = [
            rid
            for rid in block.get(
                "supported_p0_p1_ids",
                [],
            )
            if (
                rid in verified_ids
                and req_by_id.get(
                    rid,
                    {},
                ).get(
                    "priority"
                )
                in {"P0", "P1"}
            )
        ]

        support[key] = ids

    for project in projects.get(
        "selected_projects",
        [],
    ):
        key = (
            "project",
            project.get(
                "entity_id"
            ),
        )

        ids = [
            rid
            for rid in project.get(
                "supported_p0_p1_ids",
                [],
            )
            if (
                rid in verified_ids
                and req_by_id.get(
                    rid,
                    {},
                ).get(
                    "priority"
                )
                in {"P0", "P1"}
            )
        ]

        support[key] = ids

    raw = {}

    for key, ids in support.items():
        raw[key] = sum(
            priority_weight(
                req_by_id.get(
                    rid,
                    {},
                ).get(
                    "priority"
                )
            )
            for rid in ids
        )

    max_raw = max(
        raw.values(),
        default=0.0,
    )

    return (
        req_by_id,
        support,
        raw,
        max_raw,
    )


def bullet_market_rows(
    resume,
    requirements,
    evidence_map,
    experience,
    projects,
):
    base_rows = (
        base.bullet_audit_rows(
            resume
        )
    )

    (
        req_by_id,
        support,
        raw,
        max_raw,
    ) = selected_entity_support(
        requirements,
        evidence_map,
        experience,
        projects,
    )

    rows = []

    for row in base_rows:
        if (
            row["section"]
            == "experience"
        ):
            resume_block = resume.get(
                "experience",
                [],
            )[
                row[
                    "section_index"
                ]
            ]

            entity_key = (
                "experience",
                resume_block.get(
                    "block_id"
                ),
            )

        else:
            resume_block = resume.get(
                "projects",
                [],
            )[
                row[
                    "section_index"
                ]
            ]

            entity_key = (
                "project",
                resume_block.get(
                    "entity_id"
                ),
            )

        supported_ids = support.get(
            entity_key,
            [],
        )

        entity_relevance = (
            raw.get(
                entity_key,
                0.0,
            )
            / max_raw
            if max_raw
            else 0.0
        )

        bullet_tokens = (
            meaningful_tokens(
                row["text"]
            )
        )

        lexical_scores = []

        for rid in supported_ids:
            requirement = req_by_id.get(
                rid,
                {},
            )

            req_tokens = (
                meaningful_tokens(
                    requirement.get(
                        "exact_quote",
                        "",
                    )
                )
            )

            if req_tokens:
                lexical_scores.append(
                    len(
                        bullet_tokens
                        & req_tokens
                    )
                    / len(
                        req_tokens
                    )
                )

        lexical_relevance = max(
            lexical_scores,
            default=0.0,
        )

        job_relevance = (
            0.80
            * entity_relevance
            + 0.20
            * min(
                1.0,
                lexical_relevance
                * 3.0,
            )
        )

        rows.append({
            **row,

            "entity_key":
                list(
                    entity_key
                ),

            "supported_p0_p1_ids":
                supported_ids,

            "entity_relevance":
                round(
                    entity_relevance,
                    4,
                ),

            "lexical_relevance":
                round(
                    lexical_relevance,
                    4,
                ),

            "job_relevance":
                round(
                    job_relevance,
                    4,
                ),
        })

    return rows


def relevance_aware_first_evidence(
    bullets,
):
    if not bullets:
        return 0.0, {}

    first = bullets[0]

    quality = first[
        "score"
    ]

    relevance = first[
        "job_relevance"
    ]

    score = (
        0.55
        * quality
        + 45.0
        * relevance
    )

    return clamp(score), {
        "location":
            first[
                "location"
            ],

        "base_bullet_quality":
            quality,

        "job_relevance":
            relevance,

        "supported_p0_p1_ids":
            first[
                "supported_p0_p1_ids"
            ],

        "market_signal_policy":
            (
                "Strong first evidence must be both "
                "well-written and materially relevant "
                "to the target job."
            ),
    }


def relevance_aware_strongest_placement(
    bullets,
):
    if not bullets:
        return 0.0, {}

    effective = []

    for row in bullets:
        strength = (
            0.60
            * row["score"]
            + 40.0
            * row[
                "job_relevance"
            ]
        )

        effective.append(
            strength
        )

    best = max(
        effective
    )

    best_indices = [
        i
        for i, value
        in enumerate(
            effective
        )
        if abs(
            value - best
        ) < 0.000001
    ]

    first_best = min(
        best_indices
    )

    if first_best <= 1:
        placement = 100.0
    elif first_best <= 3:
        placement = 90.0
    elif first_best <= 5:
        placement = 80.0
    elif first_best <= 8:
        placement = 65.0
    else:
        placement = 50.0

    first_block_rows = [
        (
            i,
            row
        )
        for i, row in enumerate(
            bullets
        )
        if (
            row[
                "section"
            ]
            == "experience"
            and row[
                "section_index"
            ]
            == 0
        )
    ]

    first_block_strength = max(
        (
            effective[i]
            for i, _ in first_block_rows
        ),
        default=0.0,
    )

    score = (
        0.85
        * placement
        + 0.15
        * first_block_strength
    )

    return clamp(score), {
        "best_effective_strength":
            round(
                best,
                2,
            ),

        "first_best_global_index":
            first_best,

        "best_locations":
            [
                bullets[i][
                    "location"
                ]
                for i in best_indices
            ],

        "first_experience_block_strength":
            round(
                first_block_strength,
                2,
            ),
    }


def demonstrated_skill_coverage(
    resume,
    skills,
):
    skill_text = resume_skill_text(
        resume
    )

    bullet_text = resume_bullet_text(
        resume
    )

    ranked = sorted(
        skills.get(
            "ranked_skill_candidates",
            [],
        ),
        key=lambda row: float(
            row.get(
                "score",
                0.0,
            )
            or 0.0
        ),
        reverse=True,
    )

    candidates = []

    for row in ranked:
        term = str(
            row.get(
                "term",
                "",
            )
        ).strip()

        if not term:
            continue

        if (
            row.get(
                "claim_class"
            )
            != "ARTIFACT_VERIFIED"
        ):
            continue

        if not phrase_present(
            term,
            skill_text,
        ):
            continue

        candidates.append({
            "term":
                term,

            "weight":
                max(
                    1.0,
                    float(
                        row.get(
                            "score",
                            1.0,
                        )
                        or 1.0
                    ),
                ),
        })

        if len(
            candidates
        ) >= 8:
            break

    if not candidates:
        return 100.0, {
            "basis":
                "NO_VISIBLE_ARTIFACT_VERIFIED_SKILLS",

            "evaluated":
                [],

            "demonstrated":
                [],

            "not_demonstrated":
                [],
        }

    total_weight = sum(
        row["weight"]
        for row in candidates
    )

    demonstrated = []

    missing = []

    demonstrated_weight = 0.0

    for row in candidates:
        if phrase_present(
            row[
                "term"
            ],
            bullet_text,
        ):
            demonstrated.append(
                row["term"]
            )

            demonstrated_weight += (
                row[
                    "weight"
                ]
            )

        else:
            missing.append(
                row["term"]
            )

    score = (
        100.0
        * demonstrated_weight
        / total_weight
        if total_weight
        else 100.0
    )

    return clamp(score), {
        "basis":
            (
                "VISIBLE_ARTIFACT_VERIFIED_SKILLS_"
                "SHOULD_BE_DEMONSTRATED_IN_EVIDENCE"
            ),

        "evaluated":
            [
                row["term"]
                for row in candidates
            ],

        "demonstrated":
            demonstrated,

        "not_demonstrated":
            missing,
    }


def ownership_decision_signal(
    bullets,
):
    if not bullets:
        return (
            0.0,
            0.0,
            {},
        )

    ownership_rows = []

    decision_rows = []

    for row in bullets:
        starter = base.first_word(
            row["text"]
        ).lower()

        if starter in OWNERSHIP_VERBS:
            ownership_rows.append(
                row[
                    "location"
                ]
            )

        lower_tokens = set(
            tokens(
                row["text"]
            )
        )

        if (
            lower_tokens
            & DECISION_VALUE_TERMS
        ):
            decision_rows.append(
                row[
                    "location"
                ]
            )

    ownership_ratio = (
        len(
            ownership_rows
        )
        / len(
            bullets
        )
    )

    decision_ratio = (
        len(
            decision_rows
        )
        / len(
            bullets
        )
    )

    ownership_score = (
        100.0
        * min(
            1.0,
            ownership_ratio
            / 0.55,
        )
    )

    decision_score = (
        100.0
        * min(
            1.0,
            decision_ratio
            / 0.40,
        )
    )

    return (
        clamp(
            ownership_score
        ),
        clamp(
            decision_score
        ),
        {
            "ownership_ratio":
                round(
                    ownership_ratio,
                    4,
                ),

            "decision_value_ratio":
                round(
                    decision_ratio,
                    4,
                ),

            "ownership_locations":
                ownership_rows,

            "decision_value_locations":
                decision_rows,
        },
    )


def seniority_level(
    text,
):
    lower = str(
        text or ""
    ).lower()

    if re.search(
        r"\b("
        r"chief|vice president|vp|"
        r"director|head"
        r")\b",
        lower,
    ):
        return "EXECUTIVE_OR_DIRECTOR"

    if re.search(
        r"\b("
        r"manager|lead|principal"
        r")\b",
        lower,
    ):
        return "LEAD_OR_MANAGER"

    if re.search(
        r"\bsenior\b",
        lower,
    ):
        return "SENIOR"

    if re.search(
        r"\b("
        r"junior|entry|associate"
        r")\b",
        lower,
    ):
        return "ENTRY"

    return "INDIVIDUAL"


def target_title(
    route,
):
    value = (
        route.get(
            "input",
            {},
        ).get(
            "target_title_candidate"
        )
    )

    if value:
        return str(
            value
        )

    return str(
        route.get(
            "application_route",
            {},
        ).get(
            "primary",
            {},
        ).get(
            "search_title",
            "",
        )
    )


def seniority_calibration(
    resume,
    route,
):
    target = target_title(
        route
    )

    target_level = seniority_level(
        target
    )

    summary_level = seniority_level(
        resume.get(
            "summary",
            "",
        )
    )

    elevated = {
        "SENIOR",
        "LEAD_OR_MANAGER",
        "EXECUTIVE_OR_DIRECTOR",
    }

    mismatch = (
        target_level
        in {
            "INDIVIDUAL",
            "ENTRY",
        }
        and summary_level
        in elevated
    )

    penalty = (
        45.0
        if mismatch
        else 0.0
    )

    return penalty, {
        "target_title":
            target,

        "target_level":
            target_level,

        "summary_level":
            summary_level,

        "seniority_mismatch":
            mismatch,

        "penalty":
            penalty,
    }


def structural_sameness_score(
    bullets,
):
    if len(
        bullets
    ) < 4:
        return 100.0, {
            "basis":
                "TOO_FEW_BULLETS_FOR_STRUCTURE_TEST"
        }

    starters = [
        base.first_word(
            row["text"]
        ).lower()
        for row in bullets
    ]

    starter_counts = Counter(
        starters
    )

    max_starter_share = (
        max(
            starter_counts.values()
        )
        / len(
            starters
        )
        if starters
        else 0.0
    )

    prefixes = []

    for row in bullets:
        row_tokens = tokens(
            row["text"]
        )

        prefixes.append(
            " ".join(
                row_tokens[:2]
            )
        )

    prefix_counts = Counter(
        prefixes
    )

    max_prefix_share = (
        max(
            prefix_counts.values()
        )
        / len(
            prefixes
        )
        if prefixes
        else 0.0
    )

    lengths = [
        row[
            "word_count"
        ]
        for row in bullets
    ]

    mean_length = statistics.mean(
        lengths
    )

    length_cv = (
        statistics.pstdev(
            lengths
        )
        / mean_length
        if mean_length
        else 0.0
    )

    comma_ing = 0

    for row in bullets:
        if re.search(
            r",\s+[a-z]+ing\b",
            row["text"].lower(),
        ):
            comma_ing += 1

    comma_ing_ratio = (
        comma_ing
        / len(
            bullets
        )
    )

    penalty = 0.0
    signals = []

    if max_starter_share >= 0.70:
        penalty += 35.0
        signals.append(
            "HIGH_STARTER_REPETITION"
        )

    elif max_starter_share >= 0.55:
        penalty += 20.0
        signals.append(
            "MODERATE_STARTER_REPETITION"
        )

    if max_prefix_share >= 0.70:
        penalty += 30.0
        signals.append(
            "HIGH_PREFIX_REPETITION"
        )

    elif max_prefix_share >= 0.55:
        penalty += 15.0
        signals.append(
            "MODERATE_PREFIX_REPETITION"
        )

    if (
        len(
            bullets
        ) >= 6
        and comma_ing_ratio
        >= 0.85
        and length_cv
        < 0.10
    ):
        penalty += 10.0
        signals.append(
            "UNIFORM_COMMA_GERUND_TEMPLATE"
        )

    if (
        len(
            bullets
        ) >= 6
        and length_cv
        < 0.05
    ):
        penalty += 15.0
        signals.append(
            "EXTREMELY_UNIFORM_BULLET_LENGTH"
        )

    score = (
        100.0
        - penalty
    )

    return clamp(score), {
        "max_starter_share":
            round(
                max_starter_share,
                4,
            ),

        "max_two_token_prefix_share":
            round(
                max_prefix_share,
                4,
            ),

        "length_cv":
            round(
                length_cv,
                4,
            ),

        "comma_gerund_ratio":
            round(
                comma_ing_ratio,
                4,
            ),

        "signals":
            signals,

        "penalty":
            penalty,
    }


def role_family(
    route,
):
    role = str(
        route.get(
            "market_route",
            {},
        ).get(
            "primary",
            {},
        ).get(
            "role",
            "",
        )
    ).lower()

    if (
        "reporting" in role
        or "business intelligence"
        in role
        or role.startswith(
            "bi "
        )
    ):
        return "REPORTING_BI"

    if "business analyst" in role:
        return "BUSINESS_ANALYSIS"

    if (
        "research" in role
        or "institutional" in role
    ):
        return "RESEARCH_INSTITUTIONAL"

    if any(
        phrase in role
        for phrase in [
            "data analyst",
            "data engineer",
            "data scientist",
            "analytics engineer",
            "data quality",
        ]
    ):
        return "DATA_TECHNICAL"

    return "DEFAULT"


def weights_for_route(
    route,
):
    family = role_family(
        route
    )

    weights = dict(
        base.WEIGHTS
    )

    multipliers = (
        ROLE_WEIGHT_MULTIPLIERS.get(
            family,
            {},
        )
    )

    for name, multiplier in (
        multipliers.items()
    ):
        weights[name] *= (
            multiplier
        )

    total = sum(
        weights.values()
    )

    weights = {
        name:
            value
            / total
        for name, value
        in weights.items()
    }

    return (
        family,
        weights,
    )


def evaluate(
    resume,
    truth,
    ats,
    route,
    requirements,
    evidence_map,
    experience,
    projects,
    skills,
):
    baseline_result, baseline_audit = (
        base.evaluate(
            resume,
            truth,
            ats,
            route,
        )
    )

    bullets = bullet_market_rows(
        resume,
        requirements,
        evidence_map,
        experience,
        projects,
    )

    (
        first_score,
        first_detail,
    ) = relevance_aware_first_evidence(
        bullets
    )

    (
        placement_score,
        placement_detail,
    ) = (
        relevance_aware_strongest_placement(
            bullets
        )
    )

    (
        demonstrated_score,
        demonstrated_detail,
    ) = demonstrated_skill_coverage(
        resume,
        skills,
    )

    base_technical = baseline_result[
        "dimensions"
    ][
        "technical_depth"
    ]

    technical_score = clamp(
        0.55
        * base_technical
        + 0.45
        * demonstrated_score
    )

    (
        ownership_score,
        decision_score,
        ownership_detail,
    ) = ownership_decision_signal(
        bullets
    )

    base_business = baseline_result[
        "dimensions"
    ][
        "business_relevance"
    ]

    business_score = clamp(
        0.65
        * base_business
        + 0.20
        * ownership_score
        + 0.15
        * decision_score
    )

    differentiated_rows = [
        row
        for row in bullets
        if (
            row[
                "quantified"
            ]
            and (
                row[
                    "technical_specificity"
                ]
                or row[
                    "purpose_or_result"
                ]
            )
        )
    ]

    differentiated_relevance = (
        sum(
            row[
                "job_relevance"
            ]
            for row in differentiated_rows
        )
        / len(
            differentiated_rows
        )
        if differentiated_rows
        else 0.0
    )

    base_differentiation = (
        baseline_result[
            "dimensions"
        ][
            "differentiation"
        ]
    )

    differentiation_score = clamp(
        0.65
        * base_differentiation
        + 35.0
        * differentiated_relevance
    )

    (
        seniority_penalty,
        seniority_detail,
    ) = seniority_calibration(
        resume,
        route,
    )

    career_score = clamp(
        baseline_result[
            "dimensions"
        ][
            "career_coherence"
        ]
        - seniority_penalty
    )

    (
        structure_score,
        structure_detail,
    ) = structural_sameness_score(
        bullets
    )

    generic_score = clamp(
        0.65
        * baseline_result[
            "dimensions"
        ][
            "generic_ai_language"
        ]
        + 0.35
        * structure_score
    )

    natural_score = clamp(
        0.80
        * baseline_result[
            "dimensions"
        ][
            "natural_language"
        ]
        + 0.20
        * structure_score
    )

    provenance_leaks = (
        baseline_audit.get(
            "details",
            {},
        ).get(
            "credibility",
            {},
        ).get(
            "visible_provenance_leaks",
            [],
        )
    )

    credibility_score = (
        100.0
        if not provenance_leaks
        else 0.0
    )

    dimensions = dict(
        baseline_result[
            "dimensions"
        ]
    )

    dimensions[
        "first_evidence_strength"
    ] = first_score

    dimensions[
        "strongest_evidence_placement"
    ] = placement_score

    dimensions[
        "technical_depth"
    ] = technical_score

    dimensions[
        "business_relevance"
    ] = business_score

    dimensions[
        "credibility"
    ] = credibility_score

    dimensions[
        "career_coherence"
    ] = career_score

    dimensions[
        "natural_language"
    ] = natural_score

    dimensions[
        "differentiation"
    ] = differentiation_score

    dimensions[
        "generic_ai_language"
    ] = generic_score

    if list(
        dimensions.keys()
    ) != LOCKED_DIMENSIONS:
        raise RuntimeError(
            "Human V2.1 dimension contract drift"
        )

    family, weights = (
        weights_for_route(
            route
        )
    )

    overall = round(
        sum(
            dimensions[name]
            * weights[name]
            for name in LOCKED_DIMENSIONS
        ),
        2,
    )

    floor_failures = []

    for name, floor in (
        HARD_FLOORS.items()
    ):
        if (
            dimensions[
                name
            ]
            < floor
        ):
            floor_failures.append({
                "dimension":
                    name,

                "score":
                    dimensions[
                        name
                    ],

                "floor":
                    floor,
            })

    human_fail_reasons = []

    if provenance_leaks:
        human_fail_reasons.append(
            "INTERNAL_PROVENANCE_LANGUAGE_VISIBLE"
        )

    for failure in floor_failures:
        human_fail_reasons.append(
            (
                failure[
                    "dimension"
                ].upper()
                + ":BELOW_FLOOR_"
                + str(
                    int(
                        failure[
                            "floor"
                        ]
                    )
                )
            )
        )

    extremely_weak = [
        row[
            "location"
        ]
        for row in bullets
        if row[
            "score"
        ] < 45.0
    ]

    if extremely_weak:
        human_fail_reasons.append(
            "EXTREMELY_WEAK_BULLET:"
            + ",".join(
                extremely_weak
            )
        )

    human_fail_reasons = list(
        dict.fromkeys(
            human_fail_reasons
        )
    )

    quality_gate = (
        "PASS"
        if (
            overall
            >= PASS_THRESHOLD
            and not human_fail_reasons
        )
        else "FAIL"
    )

    upstream_blockers = []

    if truth.get(
        "gate"
    ) != "PASS":
        upstream_blockers.append(
            "TRUTH"
        )

    if ats.get(
        "gate"
    ) != "PASS":
        upstream_blockers.append(
            "ATS"
        )

    release_eligible = (
        quality_gate
        == "PASS"
        and not upstream_blockers
    )

    details = dict(
        baseline_audit.get(
            "details",
            {},
        )
    )

    details[
        "first_evidence_strength"
    ] = first_detail

    details[
        "strongest_evidence_placement"
    ] = placement_detail

    details[
        "demonstrated_skill_coverage"
    ] = {
        "score":
            demonstrated_score,

        **demonstrated_detail,
    }

    details[
        "ownership_decision_value"
    ] = {
        "ownership_score":
            ownership_score,

        "decision_value_score":
            decision_score,

        **ownership_detail,
    }

    details[
        "seniority_calibration"
    ] = seniority_detail

    details[
        "structural_sameness"
    ] = {
        "score":
            structure_score,

        **structure_detail,
    }

    details[
        "job_relevance_bullets"
    ] = [
        {
            "location":
                row[
                    "location"
                ],

            "job_relevance":
                row[
                    "job_relevance"
                ],

            "supported_p0_p1_ids":
                row[
                    "supported_p0_p1_ids"
                ],
        }
        for row in bullets
    ]

    audit = {
        "schema_version":
            "careerops-human-audit-v2.1",

        "score_type":
            (
                "INTERNAL_DETERMINISTIC_"
                "MARKET_AWARE_HUMAN_QUALITY"
            ),

        "real_recruiter_score":
            False,

        "quality_gate":
            quality_gate,

        "release_eligible":
            release_eligible,

        "upstream_blockers":
            upstream_blockers,

        "overall":
            overall,

        "threshold":
            PASS_THRESHOLD,

        "role_family":
            family,

        "dimensions":
            dimensions,

        "weights":
            weights,

        "hard_floors":
            HARD_FLOORS,

        "floor_failures":
            floor_failures,

        "human_fail_reasons":
            human_fail_reasons,

        "details":
            details,

        "policy": {
            "deterministic_only":
                True,

            "normal_llm_reviewer":
                False,

            "market_research_used_as_design_prior":
                True,

            "market_research_used_as_candidate_fact":
                False,

            "market_research_used_as_employer_fact":
                False,

            "job_relevance_aware_evidence":
                True,

            "demonstrated_skill_signal":
                True,

            "ownership_decision_signal":
                True,

            "role_family_weighting":
                True,

            "seniority_calibration":
                True,

            "structural_ai_sameness_detection":
                True,

            "quality_gate_separate_from_upstream":
                True,
        },

        "model_calls":
            0,
    }

    result = {
        "schema_version":
            "careerops-human-gate-v2.1",

        # HUMAN quality only.
        "gate":
            quality_gate,

        "quality_gate":
            quality_gate,

        "score":
            overall,

        "threshold":
            PASS_THRESHOLD,

        "release_eligible":
            release_eligible,

        "upstream_blockers":
            upstream_blockers,

        "role_family":
            family,

        "dimensions":
            dimensions,

        "hard_floors":
            HARD_FLOORS,

        "floor_failures":
            floor_failures,

        "hard_fail_reasons":
            human_fail_reasons,

        "human_fail_reasons":
            human_fail_reasons,

        "weak_dimensions":
            [
                row[
                    "dimension"
                ]
                for row in floor_failures
            ],

        "demonstrated_skill_coverage":
            demonstrated_score,

        "structural_sameness_score":
            structure_score,

        "model_calls":
            0,

        "model_tokens":
            0,
    }

    return result, audit


def main():
    resume = load(
        RESUME_FILE
    )

    truth = load(
        TRUTH_FILE
    )

    ats = load(
        ATS_FILE
    )

    route = load(
        ROUTE_FILE
    )

    requirements = load(
        REQUIREMENTS_FILE
    )

    evidence_map = load(
        EVIDENCE_FILE
    )

    experience = load(
        EXPERIENCE_FILE
    )

    projects = load(
        PROJECT_FILE
    )

    skills = load(
        SKILLS_FILE
    )

    result, audit = evaluate(
        resume,
        truth,
        ats,
        route,
        requirements,
        evidence_map,
        experience,
        projects,
        skills,
    )

    OUT.write_text(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    AUDIT.write_text(
        json.dumps(
            audit,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    print("=" * 96)
    print("HUMAN GATE V2.1")
    print("=" * 96)

    print(
        "QUALITY GATE:",
        result[
            "quality_gate"
        ],
    )

    print(
        "SCORE:",
        f"{result['score']:.2f}/100",
    )

    print(
        "ROLE FAMILY:",
        result[
            "role_family"
        ],
    )

    print(
        "UPSTREAM BLOCKERS:",
        result[
            "upstream_blockers"
        ]
        or "NONE",
    )

    print(
        "RELEASE ELIGIBLE:",
        result[
            "release_eligible"
        ],
    )

    print()
    print("DIMENSIONS")

    for name in (
        LOCKED_DIMENSIONS
    ):
        print(
            f"  {name}: "
            f"{result['dimensions'][name]:.2f} "
            f"| floor="
            f"{result['hard_floors'][name]:.2f}"
        )

    print()
    print(
        "HUMAN FAIL REASONS:",
        result[
            "human_fail_reasons"
        ]
        or "NONE",
    )

    print(
        "DEMONSTRATED SKILL COVERAGE:",
        result[
            "demonstrated_skill_coverage"
        ],
    )

    print(
        "STRUCTURAL SAMENESS SCORE:",
        result[
            "structural_sameness_score"
        ],
    )

    print(
        "MODEL CALLS: 0"
    )


if __name__ == "__main__":
    main()
