from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from careerops_intelligence_contracts import (
    SCHEMA_INTELLIGENCE_BUS,
    SkillIntelligence,
    validate_intelligence_bus,
)

RUNTIME_INPUTS = {
    "jd_intake": "jd_intake.json",
    "ats_audit": "ats_audit.json",
    "ats_gate": "ats_gate.json",
    "role_routing": "role_routing.json",
    "semantic_map": "jd_semantic_map.json",
    "skills_plan": "technical_skills_plan.json",
    "evidence_map": "requirement_evidence_map.json",
    "experience_selection": "experience_selection.json",
    "project_selection": "project_selection.json",
    "summary_route": "summary_route.json",
    "cover_plan": "cover_plan.json",
}


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}

    try:
        obj = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def sha256(path: Path) -> str | None:
    if not path.is_file():
        return None

    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def norm(value: Any) -> str:
    return " ".join(
        str(value or "")
        .replace("\u00a0", " ")
        .split()
    )


def first_recursive(value: Any, keys: tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        for key in keys:
            if key in value:
                candidate = value[key]
                if candidate not in (None, "", [], {}):
                    return candidate

        for child in value.values():
            found = first_recursive(child, keys)
            if found not in (None, "", [], {}):
                return found

    elif isinstance(value, list):
        for child in value:
            found = first_recursive(child, keys)
            if found not in (None, "", [], {}):
                return found

    return None


def skill_name(row: dict[str, Any]) -> str:
    for key in (
        "canonical_skill",
        "display_name",
        "skill",
        "term",
        "name",
        "label",
    ):
        value = norm(row.get(key))
        if value:
            return value
    return ""


def provenance(row: dict[str, Any]) -> tuple[str, ...]:
    raw = row.get("provenance", [])

    if isinstance(raw, str):
        raw = [raw]

    if not isinstance(raw, list):
        raw = []

    return tuple(
        sorted(
            {
                norm(item).upper()
                for item in raw
                if norm(item)
            }
        )
    )


def has_any(values: tuple[str, ...], needles: tuple[str, ...]) -> bool:
    joined = "\n".join(values)
    return any(needle in joined for needle in needles)


def classify_skill(row: dict[str, Any]) -> SkillIntelligence | None:
    term = skill_name(row)

    if not term:
        return None

    prov = provenance(row)
    proficiency = norm(row.get("proficiency"))

    candidate_confirmed = has_any(
        prov,
        (
            "DIRECT_USER_CONFIRMED_PROFICIENCY",
            "CANDIDATE_FACT",
            "USER_CONFIRMED",
        ),
    )

    verified_evidence = has_any(
        prov,
        (
            "VERIFIED",
            "EVIDENCE",
            "EXPERIENCE",
            "PROJECT",
        ),
    )

    market_prior = "ROUTED_ROLE_MARKET_PRIOR" in prov

    exact_jd = has_any(
        prov,
        (
            "EXACT_JD",
            "JD_EXPLICIT",
            "JD_SKILL",
            "EXPLICIT_JD",
        ),
    )

    allowed_resume_skill = bool(
        candidate_confirmed
        or verified_evidence
    )

    historical_claim_allowed = bool(
        verified_evidence
    )

    if verified_evidence:
        interview_status = "VERIFIED_EVIDENCE"
    elif candidate_confirmed:
        interview_status = "CONFIRMED_CAPABILITY"
    elif market_prior:
        interview_status = "MARKET_ONLY_DO_NOT_CLAIM"
    elif exact_jd:
        interview_status = "JD_ONLY_NOT_CANDIDATE_EVIDENCE"
    else:
        interview_status = "UNVERIFIED_OR_ADVISORY"

    return SkillIntelligence(
        term=term,
        provenance=prov,
        proficiency=proficiency,
        candidate_confirmed=candidate_confirmed,
        verified_evidence=verified_evidence,
        market_prior=market_prior,
        exact_jd=exact_jd,
        allowed_resume_skill=allowed_resume_skill,
        historical_claim_allowed=historical_claim_allowed,
        interview_status=interview_status,
    )


def load_runtime(runtime_dir: Path):
    artifacts = {}
    sources = {}

    for key, filename in RUNTIME_INPUTS.items():
        path = runtime_dir / filename
        artifacts[key] = load_json(path)
        sources[key] = {
            "filename": filename,
            "exists": path.is_file(),
            "sha256": sha256(path),
        }

    return artifacts, sources


def dedupe(rows: list[SkillIntelligence]) -> list[dict[str, Any]]:
    seen = set()
    result = []

    for item in rows:
        key = item.term.casefold()

        if key in seen:
            continue

        seen.add(key)
        result.append(item.to_dict())

    return result


def build_intelligence_bus(runtime_dir: str | Path) -> dict[str, Any]:
    runtime_dir = Path(runtime_dir)
    artifacts, sources = load_runtime(runtime_dir)

    skills_plan = artifacts["skills_plan"]

    rows = skills_plan.get(
        "ranked_skill_candidates",
        [],
    )

    if not isinstance(rows, list):
        rows = []

    normalized: list[SkillIntelligence] = []

    for row in rows:
        if not isinstance(row, dict):
            continue

        item = classify_skill(row)

        if item is not None:
            normalized.append(item)

    candidate_confirmed = [
        x for x in normalized
        if x.candidate_confirmed
    ]

    writer_safe_complements = [
        x for x in normalized
        if x.market_prior
        and x.allowed_resume_skill
    ]

    market_only = [
        x for x in normalized
        if x.market_prior
        and not x.allowed_resume_skill
    ]

    role = artifacts["role_routing"]
    semantic = artifacts["semantic_map"]

    routed_role = (
        first_recursive(
            role,
            (
                "routed_market_role",
                "market_role",
                "primary_role",
                "role",
            ),
        )
        or first_recursive(
            semantic,
            (
                "routed_market_role",
                "canonical_role",
            ),
        )
    )

    route_confidence = first_recursive(
        role,
        (
            "route_confidence",
            "confidence",
        ),
    )

    related_market_terms = first_recursive(
        semantic,
        (
            "related_market_prior_terms",
        ),
    )

    if not isinstance(related_market_terms, list):
        related_market_terms = []

    ats_platform = None
    behavior_family = None

    for obj in (
        artifacts["jd_intake"],
        artifacts["ats_audit"],
        artifacts["ats_gate"],
    ):
        if not ats_platform:
            ats_platform = first_recursive(
                obj,
                (
                    "ats_platform",
                    "canonical_platform",
                    "platform",
                ),
            )

        if not behavior_family:
            behavior_family = first_recursive(
                obj,
                (
                    "behavior_family",
                    "ats_behavior_family",
                ),
            )

    expected_implicit = first_recursive(
        artifacts["ats_gate"],
        (
            "expected_implicit_skills",
        ),
    )

    result = {
        "schema_version":
            SCHEMA_INTELLIGENCE_BUS,

        "runtime_dir":
            str(runtime_dir),

        "source_artifacts":
            sources,

        "ats_strategy": {
            "platform":
                norm(ats_platform),

            "behavior_family":
                norm(behavior_family),

            "expected_implicit_skills_score":
                expected_implicit,

            "expected_implicit_skills_release_blocking":
                False,
        },

        "role_context": {
            "routed_market_role":
                norm(routed_role),

            "route_confidence":
                norm(route_confidence),
        },

        "market_intelligence": {
            "observed":
                bool(
                    related_market_terms
                    or any(
                        x.market_prior
                        for x in normalized
                    )
                ),

            "related_market_prior_terms": [
                norm(x)
                for x in related_market_terms
                if norm(x)
            ],

            "candidate_safe_market_complements":
                dedupe(writer_safe_complements),

            "market_only_advisory":
                dedupe(market_only),
        },

        "skills": {
            "ranked":
                dedupe(normalized),

            "candidate_confirmed":
                dedupe(candidate_confirmed),

            "writer_safe_complements":
                dedupe(writer_safe_complements),

            "market_only_advisory":
                dedupe(market_only),
        },

        "interview_defensibility": {
            "skills": [
                {
                    "term":
                        x.term,

                    "status":
                        x.interview_status,

                    "proficiency":
                        x.proficiency,

                    "historical_claim_allowed":
                        x.historical_claim_allowed,
                }
                for x in normalized
            ],
        },

        "truth_boundaries": {
            "market_prior_is_candidate_fact":
                False,

            "market_prior_can_create_employer_history":
                False,

            "market_prior_can_create_p0_or_p1":
                False,

            "direct_proficiency_proves_historical_ownership":
                False,

            "verified_evidence_required_for_historical_claim":
                True,

            "models_may_create_candidate_evidence":
                False,
        },

        "writer_contract": {
            "may_use_in_skills": [
                x.term
                for x in normalized
                if x.allowed_resume_skill
            ],

            "may_use_as_market_complement": [
                x.term
                for x in writer_safe_complements
            ],

            "advisory_only_do_not_claim": [
                x.term
                for x in market_only
            ],

            "historical_claim_requires_existing_evidence_owner":
                True,
        },
    }

    errors = validate_intelligence_bus(result)

    if errors:
        raise ValueError(
            "INTELLIGENCE_BUS_INVALID:"
            + ",".join(errors)
        )

    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    result = build_intelligence_bus(
        args.runtime_dir
    )

    output = Path(args.output)
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.write_text(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print("INTELLIGENCE_BUS=PASS")
    print("OUTPUT=", output)

    print(
        "CANDIDATE_CONFIRMED=",
        len(
            result["skills"][
                "candidate_confirmed"
            ]
        ),
    )

    print(
        "WRITER_SAFE_COMPLEMENTS=",
        len(
            result["skills"][
                "writer_safe_complements"
            ]
        ),
    )

    print(
        "MARKET_ONLY_ADVISORY=",
        len(
            result["skills"][
                "market_only_advisory"
            ]
        ),
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
