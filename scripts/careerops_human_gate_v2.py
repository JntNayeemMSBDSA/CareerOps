#!/usr/bin/env python3

import json
import math
import os
import re
from collections import Counter
from pathlib import Path

from careerops_runtime import runtime_dir
from careerops_human_gate import (
    ACTION_VERBS,
    TECHNICAL_TERMS,
    words,
    first_word,
    starts_with_action,
    contains_number,
    contains_technical_term,
    contains_purpose_or_result,
    generic_hits,
    provenance_hits,
    bullet_quality,
    summary_quality,
    repetition_score,
)


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

OUT = RUNTIME / "human_gate_v2.json"
AUDIT = RUNTIME / "human_audit_v2.json"

PASS_THRESHOLD = 85.0


LOCKED_DIMENSIONS = [
    "immediate_role_identity",
    "first_evidence_strength",
    "strongest_evidence_placement",
    "technical_depth",
    "specificity",
    "quantified_impact",
    "business_relevance",
    "credibility",
    "career_coherence",
    "information_density",
    "redundancy",
    "readability",
    "natural_language",
    "differentiation",
    "generic_ai_language",
]


WEIGHTS = {
    "immediate_role_identity": 0.07,
    "first_evidence_strength": 0.07,
    "strongest_evidence_placement": 0.05,
    "technical_depth": 0.09,
    "specificity": 0.09,
    "quantified_impact": 0.07,
    "business_relevance": 0.08,
    "credibility": 0.09,
    "career_coherence": 0.06,
    "information_density": 0.08,
    "redundancy": 0.05,
    "readability": 0.06,
    "natural_language": 0.05,
    "differentiation": 0.05,
    "generic_ai_language": 0.04,
}


HARD_FLOORS = {
    "immediate_role_identity": 65.0,
    "first_evidence_strength": 65.0,
    "strongest_evidence_placement": 65.0,
    "technical_depth": 55.0,
    "specificity": 60.0,
    "quantified_impact": 45.0,
    "business_relevance": 50.0,
    "credibility": 90.0,
    "career_coherence": 65.0,
    "information_density": 65.0,
    "redundancy": 65.0,
    "readability": 65.0,
    "natural_language": 65.0,
    "differentiation": 55.0,
    "generic_ai_language": 75.0,
}


AI_STYLE_PHRASES = [
    "results-driven",
    "dynamic professional",
    "passionate professional",
    "proven track record",
    "leveraged synergies",
    "synergistic",
    "cutting-edge",
    "game-changing",
    "best-in-class",
    "world-class",
    "seamlessly",
    "robust solutions",
    "strategic insights",
    "value-added",
    "forward-thinking",
    "highly motivated",
    "go-getter",
    "fast learner",
    "detail-oriented",
    "team player",
]


BUSINESS_RELEVANCE_TERMS = [
    "revenue",
    "cost",
    "margin",
    "market",
    "commercial",
    "customer",
    "client",
    "stakeholder",
    "decision",
    "operations",
    "operational",
    "capacity",
    "delivery",
    "performance",
    "forecast",
    "pricing",
    "risk",
    "quality",
    "product",
    "sales",
    "acquisition",
    "retention",
    "efficiency",
    "planning",
    "strategy",
    "reporting",
]


ANALYTIC_ROLE_TERMS = {
    "data",
    "analyst",
    "analytics",
    "business",
    "intelligence",
    "reporting",
    "research",
    "science",
    "scientist",
    "engineer",
    "engineering",
    "marketing",
    "supply",
    "chain",
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
    return round(
        max(
            0.0,
            min(
                100.0,
                float(value),
            ),
        ),
        2,
    )


def resume_bullets(resume):
    rows = []

    for exp_i, exp in enumerate(
        resume.get(
            "experience",
            [],
        )
    ):
        for bullet_i, text in enumerate(
            exp.get(
                "bullets",
                [],
            )
        ):
            rows.append({
                "location":
                    (
                        f"experience[{exp_i}]"
                        f".bullets[{bullet_i}]"
                    ),

                "section":
                    "experience",

                "section_index":
                    exp_i,

                "bullet_index":
                    bullet_i,

                "text":
                    str(text or "").strip(),
            })

    for project_i, project in enumerate(
        resume.get(
            "projects",
            [],
        )
    ):
        for bullet_i, text in enumerate(
            project.get(
                "bullets",
                [],
            )
        ):
            rows.append({
                "location":
                    (
                        f"projects[{project_i}]"
                        f".bullets[{bullet_i}]"
                    ),

                "section":
                    "project",

                "section_index":
                    project_i,

                "bullet_index":
                    bullet_i,

                "text":
                    str(text or "").strip(),
            })

    return rows


def target_role(route):
    candidates = []

    def walk(obj, key_path=""):
        if isinstance(
            obj,
            dict,
        ):
            for key, value in obj.items():
                new_path = (
                    f"{key_path}.{key}"
                    if key_path
                    else key
                )

                if (
                    isinstance(
                        value,
                        str,
                    )
                    and key.lower()
                    in {
                        "search_title",
                        "target_role",
                        "target_role_title",
                        "canonical_role",
                        "job_title",
                        "position",
                    }
                ):
                    candidates.append(
                        (
                            new_path,
                            value.strip(),
                        )
                    )

                walk(
                    value,
                    new_path,
                )

        elif isinstance(
            obj,
            list,
        ):
            for i, value in enumerate(
                obj
            ):
                walk(
                    value,
                    f"{key_path}[{i}]",
                )

    walk(route)

    preferred_order = [
        ".primary.search_title",
        "primary.search_title",
        "search_title",
        "target_role_title",
        "target_role",
        "canonical_role",
        "job_title",
        "position",
    ]

    for preferred in preferred_order:
        for path, value in candidates:
            if (
                path.endswith(
                    preferred
                )
                and value
            ):
                return value

    if candidates:
        return candidates[0][1]

    return ""


def normalized_tokens(text):
    return [
        token.lower()
        for token in words(
            text
        )
        if len(token) >= 2
    ]


def role_tokens(text):
    return {
        token
        for token in normalized_tokens(
            text
        )
        if (
            token
            in ANALYTIC_ROLE_TERMS
        )
    }


def phrase_count(
    text,
    phrases,
):
    lower = str(
        text or ""
    ).lower()

    return [
        phrase
        for phrase in phrases
        if phrase.lower()
        in lower
    ]


def bullet_audit_rows(
    resume,
):
    rows = []

    for item in resume_bullets(
        resume
    ):
        text = item[
            "text"
        ]

        quality = bullet_quality(
            text
        )

        lower = text.lower()

        business_hits = [
            term
            for term in BUSINESS_RELEVANCE_TERMS
            if re.search(
                r"(?<![a-z0-9])"
                + re.escape(
                    term.lower()
                )
                + r"(?![a-z0-9])",
                lower,
            )
        ]

        ai_hits = phrase_count(
            text,
            AI_STYLE_PHRASES,
        )

        rows.append({
            **item,
            **quality,

            "business_relevance_hits":
                business_hits,

            "ai_style_hits":
                ai_hits,
        })

    return rows


def immediate_role_identity_score(
    resume,
    route,
):
    summary = str(
        resume.get(
            "summary",
            "",
        )
    ).strip()

    target = target_role(
        route
    )

    if not target:
        # If routing has no target title, do not fabricate one.
        return 75.0, {
            "target_role":
                "",

            "basis":
                "TARGET_ROLE_UNAVAILABLE",
        }

    target_role_tokens = role_tokens(
        target
    )

    summary_role_tokens = role_tokens(
        summary
    )

    exact_phrase = (
        target.lower()
        in summary.lower()
        if summary
        else False
    )

    overlap = (
        len(
            target_role_tokens
            & summary_role_tokens
        )
        / len(
            target_role_tokens
        )
        if target_role_tokens
        else 0.0
    )

    score = (
        100.0
        if exact_phrase
        else (
            55.0
            + 45.0 * overlap
            if summary
            else 25.0
        )
    )

    return clamp(score), {
        "target_role":
            target,

        "exact_role_phrase_visible":
            exact_phrase,

        "target_role_tokens":
            sorted(
                target_role_tokens
            ),

        "summary_role_tokens":
            sorted(
                summary_role_tokens
            ),

        "role_token_overlap":
            round(
                overlap,
                4,
            ),
    }


def first_evidence_score(
    bullets,
):
    if not bullets:
        return 0.0, {
            "location":
                None,

            "reason":
                "NO_BULLETS",
        }

    first = bullets[0]

    return clamp(
        first["score"]
    ), {
        "location":
            first["location"],

        "bullet_quality":
            first["score"],

        "word_count":
            first["word_count"],

        "quantified":
            first["quantified"],

        "technical":
            first[
                "technical_specificity"
            ],

        "purpose_or_result":
            first[
                "purpose_or_result"
            ],
    }


def strongest_evidence_placement_score(
    bullets,
):
    if not bullets:
        return 0.0, {
            "reason":
                "NO_BULLETS",
        }

    best_score = max(
        row["score"]
        for row in bullets
    )

    best_indices = [
        i
        for i, row in enumerate(
            bullets
        )
        if row["score"]
        == best_score
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
        placement = 70.0
    else:
        placement = 55.0

    # Strong evidence in the first professional block matters
    # even when a later project has an equally strong bullet.
    first_exp_scores = [
        row["score"]
        for row in bullets
        if (
            row["section"]
            == "experience"
            and row[
                "section_index"
            ]
            == 0
        )
    ]

    if first_exp_scores:
        first_exp_best = max(
            first_exp_scores
        )
        strength_bonus = (
            0.10
            * first_exp_best
        )

        score = (
            0.90 * placement
            + strength_bonus
        )
    else:
        score = placement

    return clamp(score), {
        "best_bullet_score":
            best_score,

        "first_best_global_index":
            first_best,

        "best_locations":
            [
                bullets[i][
                    "location"
                ]
                for i in best_indices
            ],

        "first_experience_best":
            (
                max(
                    first_exp_scores
                )
                if first_exp_scores
                else None
            ),
    }


def technical_depth_score(
    bullets,
):
    if not bullets:
        return 0.0, {}

    technical_rows = [
        row
        for row in bullets
        if row[
            "technical_specificity"
        ]
    ]

    full_text = " ".join(
        row["text"]
        for row in bullets
    ).lower()

    unique_terms = sorted({
        term
        for term in TECHNICAL_TERMS
        if term.lower()
        in full_text
    })

    ratio = (
        len(
            technical_rows
        )
        / len(bullets)
    )

    breadth = min(
        1.0,
        len(
            unique_terms
        )
        / 8.0,
    )

    score = (
        65.0 * min(
            1.0,
            ratio / 0.60,
        )
        + 35.0 * breadth
    )

    return clamp(score), {
        "technical_bullet_count":
            len(
                technical_rows
            ),

        "bullet_count":
            len(bullets),

        "technical_bullet_ratio":
            round(
                ratio,
                4,
            ),

        "unique_detected_technical_terms":
            unique_terms,
    }


def specificity_score(
    bullets,
):
    if not bullets:
        return 0.0, {}

    row_scores = []

    for row in bullets:
        components = [
            row[
                "starts_with_action_verb"
            ],
            row[
                "quantified"
            ],
            row[
                "technical_specificity"
            ],
            row[
                "purpose_or_result"
            ],
        ]

        score = (
            25.0
            * sum(
                bool(x)
                for x in components
            )
        )

        row_scores.append(
            score
        )

    return clamp(
        sum(
            row_scores
        )
        / len(
            row_scores
        )
    ), {
        "per_bullet_scores":
            [
                round(
                    value,
                    2,
                )
                for value in row_scores
            ],
    }


def quantified_impact_score(
    bullets,
):
    if not bullets:
        return 0.0, {}

    quantified = [
        row
        for row in bullets
        if row[
            "quantified"
        ]
    ]

    quantified_result = [
        row
        for row in quantified
        if row[
            "purpose_or_result"
        ]
    ]

    ratio = (
        len(
            quantified
        )
        / len(
            bullets
        )
    )

    result_ratio = (
        len(
            quantified_result
        )
        / len(
            bullets
        )
    )

    score = (
        65.0
        * min(
            1.0,
            ratio / 0.55,
        )
        + 35.0
        * min(
            1.0,
            result_ratio / 0.35,
        )
    )

    return clamp(score), {
        "quantified_bullet_count":
            len(
                quantified
            ),

        "quantified_result_bullet_count":
            len(
                quantified_result
            ),

        "bullet_count":
            len(bullets),

        "quantified_ratio":
            round(
                ratio,
                4,
            ),

        "quantified_result_ratio":
            round(
                result_ratio,
                4,
            ),
    }


def business_relevance_score(
    bullets,
):
    if not bullets:
        return 0.0, {}

    relevant = [
        row
        for row in bullets
        if (
            row[
                "purpose_or_result"
            ]
            or row[
                "business_relevance_hits"
            ]
        )
    ]

    result_rows = [
        row
        for row in bullets
        if row[
            "purpose_or_result"
        ]
    ]

    business_rows = [
        row
        for row in bullets
        if row[
            "business_relevance_hits"
        ]
    ]

    relevant_ratio = (
        len(relevant)
        / len(bullets)
    )

    result_ratio = (
        len(result_rows)
        / len(bullets)
    )

    business_ratio = (
        len(business_rows)
        / len(bullets)
    )

    score = (
        45.0
        * min(
            1.0,
            relevant_ratio / 0.70,
        )
        + 30.0
        * min(
            1.0,
            result_ratio / 0.55,
        )
        + 25.0
        * min(
            1.0,
            business_ratio / 0.45,
        )
    )

    return clamp(score), {
        "relevant_bullet_count":
            len(relevant),

        "purpose_result_count":
            len(result_rows),

        "business_term_bullet_count":
            len(
                business_rows
            ),

        "relevant_ratio":
            round(
                relevant_ratio,
                4,
            ),
    }


def credibility_score(
    resume,
    truth,
    bullets,
):
    text_parts = [
        str(
            resume.get(
                "summary",
                "",
            )
        )
    ]

    text_parts.extend(
        row["text"]
        for row in bullets
    )

    visible_text = "\n".join(
        text_parts
    )

    leaks = provenance_hits(
        visible_text
    )

    truth_pass = (
        truth.get(
            "gate"
        )
        == "PASS"
    )

    score = (
        80.0
        if truth_pass
        else 0.0
    )

    if not leaks:
        score += 20.0

    return clamp(score), {
        "truth_gate_pass":
            truth_pass,

        "visible_provenance_leaks":
            leaks,
    }


def career_coherence_score(
    resume,
    route,
):
    target = target_role(
        route
    )

    target_tokens = role_tokens(
        target
    )

    summary_tokens = role_tokens(
        resume.get(
            "summary",
            "",
        )
    )

    titles = [
        str(
            exp.get(
                "title",
                "",
            )
        )
        for exp in resume.get(
            "experience",
            [],
        )
    ]

    title_tokens = [
        role_tokens(
            title
        )
        for title in titles
    ]

    if not target_tokens:
        return 75.0, {
            "target_role":
                target,

            "basis":
                "TARGET_ROLE_UNAVAILABLE",
        }

    summary_overlap = (
        len(
            target_tokens
            & summary_tokens
        )
        / len(
            target_tokens
        )
    )

    title_overlaps = [
        (
            len(
                target_tokens
                & tokenset
            )
            / len(
                target_tokens
            )
        )
        for tokenset in title_tokens
    ]

    best_title_overlap = max(
        title_overlaps,
        default=0.0,
    )

    adjacent_analytic_title = any(
        tokenset
        & ANALYTIC_ROLE_TERMS
        for tokenset in title_tokens
    )

    score = (
        50.0
        * summary_overlap
        + 35.0
        * best_title_overlap
        + 15.0
        * adjacent_analytic_title
    )

    return clamp(score), {
        "target_role":
            target,

        "summary_overlap":
            round(
                summary_overlap,
                4,
            ),

        "best_title_overlap":
            round(
                best_title_overlap,
                4,
            ),

        "adjacent_analytic_title":
            adjacent_analytic_title,

        "titles":
            titles,
    }


def information_density_score(
    bullets,
):
    if not bullets:
        return 0.0, {}

    scores = []

    for row in bullets:
        wc = row[
            "word_count"
        ]

        if 20 <= wc <= 44:
            length = 1.0
        elif 16 <= wc <= 54:
            length = 0.85
        elif 12 <= wc <= 62:
            length = 0.65
        else:
            length = 0.35

        signal_count = sum([
            bool(
                row[
                    "starts_with_action_verb"
                ]
            ),
            bool(
                row[
                    "quantified"
                ]
            ),
            bool(
                row[
                    "technical_specificity"
                ]
            ),
            bool(
                row[
                    "purpose_or_result"
                ]
            ),
        ])

        signal = (
            signal_count
            / 4.0
        )

        scores.append(
            45.0 * length
            + 55.0 * signal
        )

    return clamp(
        sum(scores)
        / len(scores)
    ), {
        "per_bullet_density":
            [
                round(
                    value,
                    2,
                )
                for value in scores
            ],

        "average_word_count":
            round(
                sum(
                    row[
                        "word_count"
                    ]
                    for row in bullets
                )
                / len(bullets),
                2,
            ),
    }


def normalized_bullet_key(
    text,
):
    return " ".join(
        normalized_tokens(
            text
        )
    )


def redundancy_score(
    bullets,
):
    if not bullets:
        return 100.0, {}

    base_score, repeated = (
        repetition_score(
            bullets
        )
    )

    normalized = [
        normalized_bullet_key(
            row["text"]
        )
        for row in bullets
    ]

    counts = Counter(
        normalized
    )

    exact_duplicates = {
        key: count
        for key, count in counts.items()
        if (
            key
            and count > 1
        )
    }

    duplicate_penalty = min(
        30.0,
        sum(
            count - 1
            for count in exact_duplicates.values()
        )
        * 15.0,
    )

    score = (
        base_score
        - duplicate_penalty
    )

    return clamp(score), {
        "opening_repetition_score":
            base_score,

        "repeated_openings":
            repeated,

        "exact_duplicate_groups":
            exact_duplicates,

        "duplicate_penalty":
            duplicate_penalty,
    }


def readability_score(
    resume,
    bullets,
):
    if not bullets:
        return 0.0, {}

    word_counts = [
        row[
            "word_count"
        ]
        for row in bullets
    ]

    ideal = sum(
        16 <= wc <= 54
        for wc in word_counts
    )

    overly_long = sum(
        wc > 62
        for wc in word_counts
    )

    overly_short = sum(
        wc < 12
        for wc in word_counts
    )

    semicolon_heavy = sum(
        row["text"].count(";")
        >= 2
        for row in bullets
    )

    ratio_ideal = (
        ideal
        / len(bullets)
    )

    score = (
        100.0
        * ratio_ideal
        - 18.0
        * overly_long
        - 10.0
        * overly_short
        - 6.0
        * semicolon_heavy
    )

    summary_wc = len(
        words(
            resume.get(
                "summary",
                "",
            )
        )
    )

    if (
        summary_wc
        and not (
            10
            <= summary_wc
            <= 42
        )
    ):
        score -= 10.0

    return clamp(score), {
        "ideal_length_bullets":
            ideal,

        "overly_long_bullets":
            overly_long,

        "overly_short_bullets":
            overly_short,

        "semicolon_heavy_bullets":
            semicolon_heavy,

        "bullet_count":
            len(bullets),

        "summary_word_count":
            summary_wc,
    }


def natural_language_score(
    resume,
    bullets,
):
    if not bullets:
        return 0.0, {}

    starters = [
        first_word(
            row["text"]
        )
        for row in bullets
        if first_word(
            row["text"]
        )
    ]

    unique_starter_ratio = (
        len(
            set(starters)
        )
        / len(starters)
        if starters
        else 0.0
    )

    generic_total = sum(
        len(
            row[
                "generic_phrase_hits"
            ]
        )
        for row in bullets
    )

    ai_total = sum(
        len(
            row[
                "ai_style_hits"
            ]
        )
        for row in bullets
    )

    summary_text = str(
        resume.get(
            "summary",
            "",
        )
    )

    generic_total += len(
        generic_hits(
            summary_text
        )
    )

    ai_total += len(
        phrase_count(
            summary_text,
            AI_STYLE_PHRASES,
        )
    )

    score = (
        65.0
        + 35.0
        * min(
            1.0,
            unique_starter_ratio
            / 0.70,
        )
        - 12.0
        * generic_total
        - 10.0
        * ai_total
    )

    return clamp(score), {
        "unique_starter_ratio":
            round(
                unique_starter_ratio,
                4,
            ),

        "generic_hit_count":
            generic_total,

        "ai_style_hit_count":
            ai_total,

        "starters":
            starters,
    }


def differentiation_score(
    bullets,
):
    if not bullets:
        return 0.0, {}

    differentiated = [
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

    full_text = " ".join(
        row["text"]
        for row in bullets
    )

    scale_markers = re.findall(
        r"(?:"
        r"\$?\d[\d,.]*%?"
        r"|million"
        r"|billion"
        r"|GB\b"
        r"|TB\b"
        r"|rows?\b"
        r"|records?\b"
        r"|relationships?\b"
        r")",
        full_text,
        flags=re.I,
    )

    ratio = (
        len(
            differentiated
        )
        / len(
            bullets
        )
    )

    scale_score = min(
        1.0,
        len(
            scale_markers
        )
        / 8.0,
    )

    score = (
        70.0
        * min(
            1.0,
            ratio / 0.45,
        )
        + 30.0
        * scale_score
    )

    return clamp(score), {
        "differentiated_bullet_count":
            len(
                differentiated
            ),

        "bullet_count":
            len(bullets),

        "differentiated_ratio":
            round(
                ratio,
                4,
            ),

        "scale_marker_count":
            len(
                scale_markers
            ),
    }


def generic_ai_language_score(
    resume,
    bullets,
):
    texts = [
        str(
            resume.get(
                "summary",
                "",
            )
        )
    ]

    texts.extend(
        row["text"]
        for row in bullets
    )

    generic = []
    ai_style = []

    for text in texts:
        generic.extend(
            generic_hits(
                text
            )
        )

        ai_style.extend(
            phrase_count(
                text,
                AI_STYLE_PHRASES,
            )
        )

    generic = sorted(
        set(generic)
    )

    ai_style = sorted(
        set(ai_style)
    )

    penalty = (
        12.0
        * len(
            generic
        )
        + 10.0
        * len(
            ai_style
        )
    )

    score = (
        100.0
        - penalty
    )

    return clamp(score), {
        "generic_phrase_hits":
            generic,

        "ai_style_phrase_hits":
            ai_style,

        "penalty":
            penalty,
    }


def evaluate(
    resume,
    truth,
    ats,
    route,
):
    bullets = bullet_audit_rows(
        resume
    )

    (
        immediate_role_identity,
        immediate_role_identity_detail,
    ) = immediate_role_identity_score(
        resume,
        route,
    )

    (
        first_evidence_strength,
        first_evidence_detail,
    ) = first_evidence_score(
        bullets
    )

    (
        strongest_evidence_placement,
        strongest_evidence_detail,
    ) = strongest_evidence_placement_score(
        bullets
    )

    (
        technical_depth,
        technical_depth_detail,
    ) = technical_depth_score(
        bullets
    )

    (
        specificity,
        specificity_detail,
    ) = specificity_score(
        bullets
    )

    (
        quantified_impact,
        quantified_impact_detail,
    ) = quantified_impact_score(
        bullets
    )

    (
        business_relevance,
        business_relevance_detail,
    ) = business_relevance_score(
        bullets
    )

    (
        credibility,
        credibility_detail,
    ) = credibility_score(
        resume,
        truth,
        bullets,
    )

    (
        career_coherence,
        career_coherence_detail,
    ) = career_coherence_score(
        resume,
        route,
    )

    (
        information_density,
        information_density_detail,
    ) = information_density_score(
        bullets
    )

    (
        redundancy,
        redundancy_detail,
    ) = redundancy_score(
        bullets
    )

    (
        readability,
        readability_detail,
    ) = readability_score(
        resume,
        bullets,
    )

    (
        natural_language,
        natural_language_detail,
    ) = natural_language_score(
        resume,
        bullets,
    )

    (
        differentiation,
        differentiation_detail,
    ) = differentiation_score(
        bullets
    )

    (
        generic_ai_language,
        generic_ai_language_detail,
    ) = generic_ai_language_score(
        resume,
        bullets,
    )

    dimensions = {
        "immediate_role_identity":
            immediate_role_identity,

        "first_evidence_strength":
            first_evidence_strength,

        "strongest_evidence_placement":
            strongest_evidence_placement,

        "technical_depth":
            technical_depth,

        "specificity":
            specificity,

        "quantified_impact":
            quantified_impact,

        "business_relevance":
            business_relevance,

        "credibility":
            credibility,

        "career_coherence":
            career_coherence,

        "information_density":
            information_density,

        "redundancy":
            redundancy,

        "readability":
            readability,

        "natural_language":
            natural_language,

        "differentiation":
            differentiation,

        "generic_ai_language":
            generic_ai_language,
    }

    if list(
        dimensions.keys()
    ) != LOCKED_DIMENSIONS:
        raise RuntimeError(
            "Human Gate V2 dimension contract drift"
        )

    if abs(
        sum(
            WEIGHTS.values()
        )
        - 1.0
    ) > 0.000001:
        raise RuntimeError(
            "Human Gate V2 weights do not sum to 1.0"
        )

    overall = round(
        sum(
            dimensions[name]
            * WEIGHTS[name]
            for name in LOCKED_DIMENSIONS
        ),
        2,
    )

    floor_failures = []

    for name, floor in HARD_FLOORS.items():
        score = dimensions[
            name
        ]

        if score < floor:
            floor_failures.append({
                "dimension":
                    name,

                "score":
                    score,

                "floor":
                    floor,
            })

    hard_fail_reasons = []

    if truth.get(
        "gate"
    ) != "PASS":
        hard_fail_reasons.append(
            "TRUTH_GATE_NOT_PASS"
        )

    if ats.get(
        "gate"
    ) != "PASS":
        hard_fail_reasons.append(
            "ATS_GATE_NOT_PASS"
        )

    visible_provenance = (
        credibility_detail[
            "visible_provenance_leaks"
        ]
    )

    if visible_provenance:
        hard_fail_reasons.append(
            "INTERNAL_PROVENANCE_LANGUAGE_VISIBLE"
        )

    for failure in floor_failures:
        hard_fail_reasons.append(
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
        row["location"]
        for row in bullets
        if row[
            "score"
        ] < 45.0
    ]

    if extremely_weak:
        hard_fail_reasons.append(
            "EXTREMELY_WEAK_BULLET:"
            + ",".join(
                extremely_weak
            )
        )

    hard_fail_reasons = list(
        dict.fromkeys(
            hard_fail_reasons
        )
    )

    gate_status = (
        "PASS"
        if (
            overall
            >= PASS_THRESHOLD
            and not hard_fail_reasons
        )
        else "FAIL"
    )

    details = {
        "immediate_role_identity":
            immediate_role_identity_detail,

        "first_evidence_strength":
            first_evidence_detail,

        "strongest_evidence_placement":
            strongest_evidence_detail,

        "technical_depth":
            technical_depth_detail,

        "specificity":
            specificity_detail,

        "quantified_impact":
            quantified_impact_detail,

        "business_relevance":
            business_relevance_detail,

        "credibility":
            credibility_detail,

        "career_coherence":
            career_coherence_detail,

        "information_density":
            information_density_detail,

        "redundancy":
            redundancy_detail,

        "readability":
            readability_detail,

        "natural_language":
            natural_language_detail,

        "differentiation":
            differentiation_detail,

        "generic_ai_language":
            generic_ai_language_detail,
    }

    audit = {
        "schema_version":
            "careerops-human-audit-v2",

        "score_type":
            (
                "INTERNAL_DETERMINISTIC_"
                "RECRUITER_HIRING_MANAGER_QUALITY_SIMULATION"
            ),

        "real_recruiter_score":
            False,

        "threshold":
            PASS_THRESHOLD,

        "overall":
            overall,

        "dimensions":
            dimensions,

        "weights":
            WEIGHTS,

        "hard_floors":
            HARD_FLOORS,

        "floor_failures":
            floor_failures,

        "details":
            details,

        "bullets":
            bullets,

        "summary":
            summary_quality(
                resume.get(
                    "summary",
                    "",
                )
            ),

        "hard_fail_reasons":
            hard_fail_reasons,

        "policy": {
            "deterministic_only":
                True,

            "normal_llm_reviewer":
                False,

            "real_recruiter_score_claimed":
                False,

            "truth_gate_required":
                True,

            "ats_gate_required":
                True,

            "generic_ai_language_penalized":
                True,

            "provenance_language_forbidden":
                True,
        },

        "model_calls":
            0,
    }

    result = {
        "schema_version":
            "careerops-human-gate-v2",

        "gate":
            gate_status,

        "score":
            overall,

        "threshold":
            PASS_THRESHOLD,

        "score_type":
            "INTERNAL_DETERMINISTIC",

        "real_recruiter_score":
            False,

        "dimensions":
            dimensions,

        "hard_floors":
            HARD_FLOORS,

        "floor_failures":
            floor_failures,

        "hard_fail_reasons":
            hard_fail_reasons,

        "weak_dimension_count":
            len(
                floor_failures
            ),

        "weak_dimensions":
            [
                failure[
                    "dimension"
                ]
                for failure
                in floor_failures
            ],

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

    result, audit = evaluate(
        resume,
        truth,
        ats,
        route,
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
    print("HUMAN GATE V2")
    print("=" * 96)

    print(
        "GATE:",
        result[
            "gate"
        ],
    )

    print(
        "SCORE:",
        f"{result['score']:.2f}/100",
    )

    print()
    print("DIMENSIONS")

    for name in LOCKED_DIMENSIONS:
        score = result[
            "dimensions"
        ][
            name
        ]

        floor = result[
            "hard_floors"
        ][
            name
        ]

        print(
            f"  {name}: "
            f"{score:.2f} "
            f"| floor={floor:.2f}"
        )

    print()
    print(
        "HARD FAIL REASONS:",
        result[
            "hard_fail_reasons"
        ]
        or "NONE",
    )

    print(
        "REAL RECRUITER SCORE: NO"
    )

    print(
        "MODEL CALLS: 0"
    )

    print(
        "OUTPUT:",
        OUT.relative_to(
            ROOT
        ),
    )

    print(
        "AUDIT:",
        AUDIT.relative_to(
            ROOT
        ),
    )


if __name__ == "__main__":
    main()
