from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

SCHEMA_INTELLIGENCE_BUS = "career-ops-intelligence-bus-v1"
SCHEMA_ARBITRATION_CASE = "career-ops-semantic-arbitration-case-v1"
SCHEMA_ARBITRATION_BATCH = "career-ops-semantic-arbitration-batch-v1"

ALLOWED_FAILURE_TYPES = {
    "MECHANICAL",
    "SEMANTIC",
    "HARD_CONFLICT",
    "RENDERER",
    "HARNESS",
}

ALLOWED_ARBITRATION_ROUTES = {
    "DETERMINISTIC_REPAIR",
    "LOCAL_QWEN",
    "DETERMINISTIC_RECONSTRUCTION",
    "DETERMINISTIC_RESULT_STANDS",
    "SHARED_SOL_ADJUDICATION",
    "STOP_HARD_CONFLICT",
    "RENDERER_REPAIR",
    "HARNESS_REPAIR",
    "NEEDS_ATTENTION",
}


@dataclass(frozen=True)
class SkillIntelligence:
    term: str
    provenance: tuple[str, ...]
    proficiency: str
    candidate_confirmed: bool
    verified_evidence: bool
    market_prior: bool
    exact_jd: bool
    allowed_resume_skill: bool
    historical_claim_allowed: bool
    interview_status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_intelligence_bus(obj: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if not isinstance(obj, dict):
        return ["BUS_NOT_OBJECT"]

    if obj.get("schema_version") != SCHEMA_INTELLIGENCE_BUS:
        errors.append("BAD_BUS_SCHEMA")

    if not isinstance(obj.get("source_artifacts"), dict):
        errors.append("MISSING_SOURCE_ARTIFACTS")

    skills = obj.get("skills")

    if not isinstance(skills, dict):
        errors.append("MISSING_SKILLS_OBJECT")
        return errors

    for key in (
        "candidate_confirmed",
        "writer_safe_complements",
        "market_only_advisory",
        "ranked",
    ):
        if not isinstance(skills.get(key), list):
            errors.append(f"BAD_SKILLS_LIST:{key}")

    if not isinstance(obj.get("truth_boundaries"), dict):
        errors.append("MISSING_TRUTH_BOUNDARIES")

    if not isinstance(obj.get("writer_contract"), dict):
        errors.append("MISSING_WRITER_CONTRACT")

    return errors


def validate_arbitration_case(obj: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if not isinstance(obj, dict):
        return ["CASE_NOT_OBJECT"]

    if obj.get("schema_version") != SCHEMA_ARBITRATION_CASE:
        errors.append("BAD_CASE_SCHEMA")

    if obj.get("failure_type") not in ALLOWED_FAILURE_TYPES:
        errors.append("BAD_FAILURE_TYPE")

    if obj.get("route") not in ALLOWED_ARBITRATION_ROUTES:
        errors.append("BAD_ROUTE")

    if not obj.get("run_id"):
        errors.append("MISSING_RUN_ID")

    if not obj.get("stage"):
        errors.append("MISSING_STAGE")

    if not isinstance(obj.get("source_spans"), list):
        errors.append("BAD_SOURCE_SPANS")

    return errors
