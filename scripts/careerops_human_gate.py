#!/usr/bin/env python3

import json
import os
import re
from collections import Counter
from pathlib import Path

from careerops_runtime import runtime_dir

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = runtime_dir(ROOT)

RESUME_FILE = Path(
    os.environ.get(
        "CAREEROPS_RESUME_INPUT",
        str(RUNTIME / "generated_resume_content.json"),
    )
).expanduser().resolve()
TRUTH_FILE = RUNTIME / "local_truth_gate.json"
ATS_FILE = RUNTIME / "ats_gate.json"

OUT = RUNTIME / "human_gate.json"
AUDIT = RUNTIME / "human_audit.json"

PASS_THRESHOLD = 85.0

ACTION_VERBS = {
    "analyzed", "architected", "automated", "built", "compared",
    "created", "developed",
    "directed", "engineered", "evaluated", "implemented",
    "integrated", "led", "modeled", "optimized", "produced",
    "reconciled", "standardized", "trained", "transformed",
    "validated", "designed", "delivered", "applied",
    "combined", "supported", "prepared", "selected", "converted",
    "identified", "investigated", "quantified", "profiled",
    "segmented", "prioritized", "assessed", "audited",
    "calculated", "generated", "harmonized", "linked",
    "documented", "mapped", "established"
}

TECHNICAL_TERMS = [
    "fixed effects", "clustered standard errors", "race inference", "statistical specifications", "KEDA", "Azure Container Apps", "serverless", "event-driven architecture",
    "SQL", "Python", "Power BI", "Tableau", "Snowflake",
    "DuckDB", "PyArrow", "Parquet", "DAX", "Power Query",
    "SQL Server", "T-SQL", "BERT", "TF-IDF",
    "logistic regression", "CTE", "CTEs", "window functions",
    "stored procedures", "views", "indexes", "star-schema",
    "star schema", "data pipeline", "data pipelines",
    "reconciliation", "relational model", "forecast",
    "forecasting", "classification", "threshold",
    "checksum", "SHA-256", "Zstandard", "pandas",
    "GA4", "Jupyter", "ETL", "schema", "schemas",
    "data model", "data models", "relational bridge",
    "relational bridges", "sensitivity analysis",
    "scenario modeling", "data quality", "data-quality",
    "KPI", "KPIs", "cost variance", "variance analysis",
    "root cause", "root-cause", "QA"
]

PURPOSE_RESULT_TERMS = [
    "to support",
    "to create",
    "to identify",
    "to rank",
    "to communicate",
    "to expand",
    "to retain",
    "to evaluate",
    "to prioritize",
    "enabling",
    "contributing",
    "contributed",
    "resulting",
    "reduced",
    "increased",
    "improved",
    "supporting",
    "while",
    "for stakeholder",
    "for commercial",
    "for targeted",
    "for capacity",
    "for market",
    "for operational"
]

GENERIC_PHRASES = [
    "results-driven",
    "detail-oriented",
    "team player",
    "hard-working",
    "hardworking",
    "self-starter",
    "go-getter",
    "passionate professional",
    "dynamic professional",
    "proven track record",
    "leveraged synergies",
    "responsible for",
    "worked on",
    "helped with",
    "various tasks",
    "multiple projects",
    "excellent communication skills",
    "strong analytical skills",
    "fast learner"
]

PROVENANCE_LEAKS = [
    "reconstruction",
    "rebuilt study",
    "portfolio reconstruction",
    "independent reconstruction",
    "artifact verified",
    "direct user",
    "claim class",
    "evidence status",
    "verified historical"
]


def load(path):
    if not path.exists():
        raise SystemExit(f"Missing required file: {path}")
    return json.loads(path.read_text())


def words(text):
    return re.findall(
        r"\b[A-Za-z0-9][A-Za-z0-9+./%$-]*\b",
        str(text)
    )


def first_word(text):
    w = words(text)
    return w[0].lower() if w else ""


def starts_with_action(text):
    w = words(text)

    if not w:
        return False

    first = w[0].lower()

    if first in ACTION_VERBS:
        return True

    if (
        len(w) >= 2
        and first.endswith("ly")
        and w[1].lower() in ACTION_VERBS
    ):
        return True

    return False


def contains_number(text):
    return bool(
        re.search(
            r"(?:\$?\d[\d,.]*%?|\d+\s*(?:million|billion|thousand|M|B|K)\b)",
            text,
            re.I
        )
    )


def contains_technical_term(text):
    lower = text.lower()
    return any(
        term.lower() in lower
        for term in TECHNICAL_TERMS
    )


def contains_purpose_or_result(text):
    """
    Detect an explicit purpose, transformation, output, or result.

    This is grammatical/semantic detection, not a role-specific
    keyword list. A dense technical bullet should receive result
    credit when it clearly states what the work produced, preserved,
    enabled, changed, guided, ranked, acquired, or supported.
    """
    lower = str(text or "").lower()

    if any(
        term in lower
        for term in PURPOSE_RESULT_TERMS
    ):
        return True

    # Explicit infinitive purpose clauses.
    if re.search(
        r"\bto\s+"
        r"(?:support|guide|enable|inform|improve|reduce|increase|"
        r"create|identify|rank|communicate|expand|retain|evaluate|"
        r"prioritize|produce|deliver|generate|maintain|ensure|"
        r"validate|compare)\b",
        lower,
    ):
        return True

    # Participial result / consequence constructions.
    if re.search(
        r"\b(?:producing|resulting|enabling|supporting|"
        r"preserving|separating|rejecting|yielding)\b",
        lower,
    ):
        return True

    # Direct transformation / delivered-output / business-result verbs.
    if re.search(
        r"\b(?:transformed|converted|delivered|produced|"
        r"acquired|grew|increased|reduced|improved|ranked)\b",
        lower,
    ):
        return True

    # Clear downstream-purpose phrases.
    if re.search(
        r"\bfor\s+"
        r"(?:downstream|decision|account|research|reporting|"
        r"analysis|commercial|operational|market|capacity)\b",
        lower,
    ):
        return True

    return False


def generic_hits(text):
    lower = text.lower()
    return [
        x for x in GENERIC_PHRASES
        if x in lower
    ]


def provenance_hits(text):
    lower = text.lower()
    return [
        x for x in PROVENANCE_LEAKS
        if x in lower
    ]


def bullet_quality(text):
    wc = len(words(text))

    starts_action = starts_with_action(
        text
    )

    quantified = contains_number(text)
    technical = contains_technical_term(text)
    purpose_result = contains_purpose_or_result(text)

    generics = generic_hits(text)
    leaks = provenance_hits(text)

    first_person = bool(
        re.search(
            r"\b(I|my|me|we|our)\b",
            text,
            re.I
        )
    )

    # Length scoring:
    # 20-44 is ideal for dense technical one-page bullets.
    # 45-54 remains acceptable.
    # Beyond that becomes increasingly difficult to scan.
    if 20 <= wc <= 44:
        length_score = 100.0
    elif 16 <= wc <= 54:
        length_score = 85.0
    elif 12 <= wc <= 62:
        length_score = 65.0
    else:
        length_score = 35.0

    score = (
        20.0 * starts_action
        + 20.0 * quantified
        + 20.0 * technical
        + 20.0 * purpose_result
        + 20.0 * (length_score / 100.0)
    )

    if generics:
        score -= 10.0 * len(generics)

    if leaks:
        score -= 25.0 * len(leaks)

    if first_person:
        score -= 10.0

    score = max(
        0.0,
        min(100.0, score)
    )

    return {
        "score": round(score, 2),
        "word_count": wc,
        "starts_with_action_verb": starts_action,
        "quantified": quantified,
        "technical_specificity": technical,
        "purpose_or_result": purpose_result,
        "generic_phrase_hits": generics,
        "provenance_leaks": leaks,
        "first_person": first_person
    }


def collect_bullets(resume):
    result = []

    for exp in resume.get(
        "experience",
        []
    ):
        for i, bullet in enumerate(
            exp.get("bullets", [])
        ):
            result.append({
                "location":
                    f"experience.{exp['block_id']}.bullets[{i}]",
                "section": "experience",
                "text": bullet
            })

    for project in resume.get(
        "projects",
        []
    ):
        for i, bullet in enumerate(
            project.get("bullets", [])
        ):
            result.append({
                "location":
                    f"project.{project['entity_id']}.bullets[{i}]",
                "section": "project",
                "text": bullet
            })

    return result


def summary_quality(summary):
    wc = len(words(summary))

    if 14 <= wc <= 34:
        length_score = 100.0
    elif 10 <= wc <= 42:
        length_score = 80.0
    else:
        length_score = 50.0

    quantified = contains_number(summary)
    technical = contains_technical_term(summary)
    generics = generic_hits(summary)
    leaks = provenance_hits(summary)

    score = (
        40.0 * (length_score / 100.0)
        + 35.0 * technical
        + 25.0 * (not generics)
    )

    if leaks:
        score -= 25.0

    return {
        "score": round(
            max(0.0, min(100.0, score)),
            2
        ),
        "word_count": wc,
        "quantified": quantified,
        "technical_specificity": technical,
        "generic_phrase_hits": generics,
        "provenance_leaks": leaks
    }


def repetition_score(bullets):
    starters = [
        first_word(x["text"])
        for x in bullets
        if first_word(x["text"])
    ]

    counts = Counter(starters)

    repeated = {
        k: v for k, v in counts.items()
        if v >= 3
    }

    if not bullets:
        return 100.0, repeated

    max_repeat = (
        max(counts.values())
        if counts
        else 0
    )

    ratio = max_repeat / len(bullets)

    if ratio <= 0.20:
        score = 100.0
    elif ratio <= 0.30:
        score = 90.0
    elif ratio <= 0.40:
        score = 75.0
    else:
        score = 55.0

    return score, repeated


def skills_quality(resume):
    lines = resume.get(
        "skills",
        []
    )

    if not lines:
        return 0.0, {
            "line_count": 0,
            "term_count": 0
        }

    terms = []

    for line in lines:
        terms.extend(
            line.get(
                "terms",
                []
            )
        )

    unique = {
        x.strip().lower()
        for x in terms
        if x.strip()
    }

    duplicate_count = (
        len(terms) - len(unique)
    )

    # Broad enough to signal capability, but not a wall of keywords.
    if 18 <= len(unique) <= 40:
        density_score = 100.0
    elif 12 <= len(unique) <= 48:
        density_score = 85.0
    else:
        density_score = 65.0

    duplicate_penalty = min(
        20.0,
        duplicate_count * 2.0
    )

    score = max(
        0.0,
        density_score - duplicate_penalty
    )

    return round(score, 2), {
        "line_count": len(lines),
        "term_count": len(terms),
        "unique_term_count": len(unique),
        "duplicate_term_count":
            duplicate_count
    }


def main():
    resume = load(RESUME_FILE)
    truth = load(TRUTH_FILE)
    ats = load(ATS_FILE)

    bullets = collect_bullets(
        resume
    )

    bullet_audit = []

    for item in bullets:
        q = bullet_quality(
            item["text"]
        )

        bullet_audit.append({
            **item,
            **q
        })

    if bullet_audit:
        bullet_score = sum(
            x["score"]
            for x in bullet_audit
        ) / len(bullet_audit)
    else:
        bullet_score = 0.0

    summary = summary_quality(
        resume.get(
            "summary",
            ""
        )
    )

    rep_score, repeats = (
        repetition_score(
            bullets
        )
    )

    skill_score, skill_meta = (
        skills_quality(
            resume
        )
    )

    # Section architecture is already truth/ATS checked.
    section_score = 100.0

    overall = (
        0.65 * bullet_score
        + 0.15 * summary["score"]
        + 0.10 * rep_score
        + 0.05 * skill_score
        + 0.05 * section_score
    )

    overall = round(
        overall,
        2
    )

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

    leak_locations = [
        x["location"]
        for x in bullet_audit
        if x["provenance_leaks"]
    ]

    if summary[
        "provenance_leaks"
    ]:
        leak_locations.append(
            "summary"
        )

    if leak_locations:
        hard_fail_reasons.append(
            "INTERNAL_PROVENANCE_LANGUAGE_VISIBLE:"
            + ",".join(leak_locations)
        )

    extremely_weak = [
        x["location"]
        for x in bullet_audit
        if x["score"] < 50
    ]

    if extremely_weak:
        hard_fail_reasons.append(
            "EXTREMELY_WEAK_BULLET:"
            + ",".join(extremely_weak)
        )

    gate = (
        "PASS"
        if (
            overall >= PASS_THRESHOLD
            and not hard_fail_reasons
        )
        else "FAIL"
    )

    weak_bullets = [
        {
            "location": x["location"],
            "score": x["score"],
            "text": x["text"],
            "issues": {
                "word_count":
                    x["word_count"],
                "action_verb":
                    x["starts_with_action_verb"],
                "quantified":
                    x["quantified"],
                "technical":
                    x["technical_specificity"],
                "purpose_result":
                    x["purpose_or_result"],
                "generic":
                    x["generic_phrase_hits"]
            }
        }
        for x in bullet_audit
        if x["score"] < 80
    ]

    audit = {
        "schema_version":
            "careerops-human-audit-v1",

        "score_type":
            "INTERNAL_DETERMINISTIC_HUMAN_READABILITY_AND_EVIDENCE_DENSITY",

        "real_recruiter_score":
            False,

        "threshold":
            PASS_THRESHOLD,

        "scores": {
            "overall":
                overall,
            "bullet_quality":
                round(
                    bullet_score,
                    2
                ),
            "summary_quality":
                summary["score"],
            "opening_repetition":
                round(
                    rep_score,
                    2
                ),
            "skills_density":
                skill_score,
            "section_architecture":
                section_score
        },

        "weights": {
            "bullet_quality": 0.65,
            "summary_quality": 0.15,
            "opening_repetition": 0.10,
            "skills_density": 0.05,
            "section_architecture": 0.05
        },

        "summary":
            summary,

        "bullets":
            bullet_audit,

        "repeated_openings":
            repeats,

        "skills":
            skill_meta,

        "weak_bullets":
            weak_bullets,

        "hard_fail_reasons":
            hard_fail_reasons
    }

    result = {
        "schema_version":
            "careerops-human-gate-v1",

        "gate":
            gate,

        "score":
            overall,

        "threshold":
            PASS_THRESHOLD,

        "score_type":
            "INTERNAL_DETERMINISTIC",

        "real_recruiter_score":
            False,

        "weak_bullet_count":
            len(weak_bullets),

        "weak_bullet_locations":
            [
                x["location"]
                for x in weak_bullets
            ],

        "hard_fail_reasons":
            hard_fail_reasons,

        "model_calls": 0,
        "model_tokens": 0
    }

    AUDIT.write_text(
        json.dumps(
            audit,
            indent=2,
            ensure_ascii=False
        ) + "\n"
    )

    OUT.write_text(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False
        ) + "\n"
    )

    print("=" * 96)
    print(
        "INTERNAL DETERMINISTIC HUMAN SCREEN GATE"
    )
    print("=" * 96)

    print(
        "GATE:",
        gate
    )

    print(
        "OVERALL SCORE:",
        f"{overall:.2f}/100"
    )

    print(
        "THRESHOLD:",
        f"{PASS_THRESHOLD:.2f}"
    )

    print()
    print("COMPONENT SCORES")

    print(
        "  Bullet quality:",
        f"{bullet_score:.2f}"
    )

    print(
        "  Summary quality:",
        f"{summary['score']:.2f}"
    )

    print(
        "  Opening repetition:",
        f"{rep_score:.2f}"
    )

    print(
        "  Skills density:",
        f"{skill_score:.2f}"
    )

    print(
        "  Section architecture:",
        f"{section_score:.2f}"
    )

    print()
    print("BULLET AUDIT")

    for x in bullet_audit:
        print(
            f"  {x['location']} | "
            f"{x['score']:.2f} | "
            f"{x['word_count']} words | "
            f"action={x['starts_with_action_verb']} | "
            f"number={x['quantified']} | "
            f"technical={x['technical_specificity']} | "
            f"result={x['purpose_or_result']}"
        )

    print()
    print(
        "WEAK BULLETS (<80):",
        (
            len(weak_bullets)
            if weak_bullets
            else "NONE"
        )
    )

    for x in weak_bullets:
        print(
            " ",
            x["location"],
            f"| {x['score']:.2f}"
        )

    print()
    print(
        "REPEATED OPENINGS:",
        repeats if repeats else "NONE"
    )

    print(
        "HARD FAIL REASONS:",
        (
            hard_fail_reasons
            if hard_fail_reasons
            else "NONE"
        )
    )

    print()
    print(
        "SCORE TYPE: INTERNAL DETERMINISTIC "
        "HUMAN-READABILITY / EVIDENCE-DENSITY HEURISTIC"
    )

    print(
        "REAL RECRUITER SCORE: NO"
    )

    print(
        "MODEL CALLS: 0"
    )

    print(
        "MODEL TOKENS: 0"
    )

    print()
    print(
        "OUTPUT:",
        OUT.relative_to(ROOT)
    )

    print(
        "AUDIT:",
        AUDIT.relative_to(ROOT)
    )


if __name__ == "__main__":
    main()
