#!/usr/bin/env python3

import json
import os
import re
from collections import Counter
from pathlib import Path
from careerops_requirement_regeneration import canonical_ledger_path

from careerops_runtime import runtime_dir
from careerops_detect_ats import get_behavior_profile
from careerops_ats_gate import (
    tokens,
    meaningful_tokens,
    phrase_present,
    resume_surfaces,
    role_alignment,
    structure_score,
)


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = runtime_dir(ROOT)

SOURCE_REQ_FILE = canonical_ledger_path(RUNTIME)
EFFECTIVE_REQ_FILE = RUNTIME / "jd_requirements_effective.json"

# Canonical ledger owns the denominator. Derived semantic views annotate it.
REQ_FILE = SOURCE_REQ_FILE
CONSTRAINT_FILE = RUNTIME / "constraint_validation.json"
ROUTE_FILE = RUNTIME / "role_routing.json"
SKILLS_FILE = RUNTIME / "technical_skills_plan.json"
SUMMARY_FILE = RUNTIME / "summary_route.json"
SEMANTIC_FILE = RUNTIME / "jd_semantic_map.json"
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

OUT = RUNTIME / "ats_gate.json"
AUDIT = RUNTIME / "ats_audit.json"

PASS_THRESHOLD = 85.0


# ------------------------------------------------------------------
# These are INTERNAL Career-Ops simulation weights.
#
# They are not vendor weights and are never represented as such.
# Behavior-family research only determines which dimensions Career-Ops
# emphasizes while evaluating the resume.
# ------------------------------------------------------------------

DEFAULT_WEIGHTS = {
    "parse_structure_integrity": 0.08,
    "p0_coverage": 0.18,
    "p1_coverage": 0.10,
    "exact_jd_terminology": 0.12,
    "semantic_coverage": 0.10,
    "tools_technology": 0.08,
    "experience_coverage": 0.08,
    "education_coverage": 0.06,
    "role_title_alignment": 0.07,
    "recruiter_search_retrievability": 0.05,
    "keyword_naturalness": 0.05,
    "expected_implicit_skills": 0.03,
}


SEMANTIC_WEIGHTS = {
    "parse_structure_integrity": 0.07,
    "p0_coverage": 0.18,
    "p1_coverage": 0.10,
    "exact_jd_terminology": 0.08,
    "semantic_coverage": 0.16,
    "tools_technology": 0.09,
    "experience_coverage": 0.09,
    "education_coverage": 0.06,
    "role_title_alignment": 0.07,
    "recruiter_search_retrievability": 0.04,
    "keyword_naturalness": 0.04,
    "expected_implicit_skills": 0.02,
}


EXACT_SEARCH_WEIGHTS = {
    "parse_structure_integrity": 0.08,
    "p0_coverage": 0.18,
    "p1_coverage": 0.10,
    "exact_jd_terminology": 0.18,
    "semantic_coverage": 0.06,
    "tools_technology": 0.10,
    "experience_coverage": 0.07,
    "education_coverage": 0.05,
    "role_title_alignment": 0.07,
    "recruiter_search_retrievability": 0.06,
    "keyword_naturalness": 0.04,
    "expected_implicit_skills": 0.01,
}


INSTITUTIONAL_WEIGHTS = {
    "parse_structure_integrity": 0.10,
    "p0_coverage": 0.18,
    "p1_coverage": 0.09,
    "exact_jd_terminology": 0.10,
    "semantic_coverage": 0.07,
    "tools_technology": 0.07,
    "experience_coverage": 0.10,
    "education_coverage": 0.10,
    "role_title_alignment": 0.07,
    "recruiter_search_retrievability": 0.04,
    "keyword_naturalness": 0.06,
    "expected_implicit_skills": 0.02,
}


HIGH_VOLUME_WEIGHTS = {
    "parse_structure_integrity": 0.10,
    "p0_coverage": 0.24,
    "p1_coverage": 0.08,
    "exact_jd_terminology": 0.08,
    "semantic_coverage": 0.06,
    "tools_technology": 0.05,
    "experience_coverage": 0.12,
    "education_coverage": 0.08,
    "role_title_alignment": 0.06,
    "recruiter_search_retrievability": 0.04,
    "keyword_naturalness": 0.07,
    "expected_implicit_skills": 0.02,
}


FEDERAL_WEIGHTS = {
    "parse_structure_integrity": 0.10,
    "p0_coverage": 0.25,
    "p1_coverage": 0.08,
    "exact_jd_terminology": 0.12,
    "semantic_coverage": 0.05,
    "tools_technology": 0.04,
    "experience_coverage": 0.14,
    "education_coverage": 0.10,
    "role_title_alignment": 0.04,
    "recruiter_search_retrievability": 0.04,
    "keyword_naturalness": 0.03,
    "expected_implicit_skills": 0.01,
}


FAMILY_WEIGHT_GROUP = {
    "SEMANTIC_QUALIFICATION_GRADING":
        SEMANTIC_WEIGHTS,

    "CALIBRATED_SEMANTIC_MATCH":
        SEMANTIC_WEIGHTS,

    "SKILLS_ONTOLOGY_MATCH":
        SEMANTIC_WEIGHTS,

    "CONFIGURABLE_AI_RATING":
        SEMANTIC_WEIGHTS,

    "FULL_TEXT_STRUCTURED_SEARCH":
        EXACT_SEARCH_WEIGHTS,

    "LEGACY_ENTERPRISE_MATCH":
        EXACT_SEARCH_WEIGHTS,

    "PARSE_MATCH_RANK":
        EXACT_SEARCH_WEIGHTS,

    "SMB_ATS_SEARCH":
        EXACT_SEARCH_WEIGHTS,

    "STAFFING_CRM_SEARCH":
        EXACT_SEARCH_WEIGHTS,

    "HCM_WORKFLOW_SEARCH":
        EXACT_SEARCH_WEIGHTS,

    "INSTITUTIONAL_HUMAN_WORKFLOW":
        INSTITUTIONAL_WEIGHTS,

    "HIGH_VOLUME_STRUCTURED":
        HIGH_VOLUME_WEIGHTS,

    "FEDERAL_ASSESSMENT":
        FEDERAL_WEIGHTS,

    # Experience/CRM layers may sit above another ATS. Until the
    # underlying ATS is known, use the conservative mixed profile.
    "EXPERIENCE_LAYER_OR_CRM":
        DEFAULT_WEIGHTS,

    "UNKNOWN_CONSERVATIVE_MIXED":
        DEFAULT_WEIGHTS,
}


DEFAULT_FLOORS = {
    "parse_structure_integrity": 85.0,
    "p0_coverage": 65.0,
    "p1_coverage": 45.0,
    "exact_jd_terminology": 50.0,
    "semantic_coverage": 40.0,
    "tools_technology": 50.0,
    "experience_coverage": 65.0,
    "education_coverage": 70.0,
    "role_title_alignment": 45.0,
    "recruiter_search_retrievability": 55.0,
    "keyword_naturalness": 65.0,
}


FAMILY_FLOOR_OVERRIDES = {
    "FULL_TEXT_STRUCTURED_SEARCH": {
        "exact_jd_terminology": 65.0,
        "recruiter_search_retrievability": 65.0,
    },

    "LEGACY_ENTERPRISE_MATCH": {
        "exact_jd_terminology": 65.0,
        "recruiter_search_retrievability": 65.0,
    },

    "PARSE_MATCH_RANK": {
        "parse_structure_integrity": 90.0,
        "exact_jd_terminology": 60.0,
        "recruiter_search_retrievability": 60.0,
    },

    "STAFFING_CRM_SEARCH": {
        "exact_jd_terminology": 60.0,
        "recruiter_search_retrievability": 65.0,
    },

    "SKILLS_ONTOLOGY_MATCH": {
        "semantic_coverage": 60.0,
        "tools_technology": 60.0,
    },

    "SEMANTIC_QUALIFICATION_GRADING": {
        "semantic_coverage": 60.0,
        "p0_coverage": 70.0,
    },

    "CALIBRATED_SEMANTIC_MATCH": {
        "semantic_coverage": 60.0,
        "p0_coverage": 70.0,
    },

    "CONFIGURABLE_AI_RATING": {
        "experience_coverage": 70.0,
        "education_coverage": 70.0,
        "tools_technology": 55.0,
    },

    "INSTITUTIONAL_HUMAN_WORKFLOW": {
        "education_coverage": 75.0,
        "experience_coverage": 70.0,
        "keyword_naturalness": 70.0,
    },

    "HIGH_VOLUME_STRUCTURED": {
        "p0_coverage": 70.0,
        "experience_coverage": 70.0,
        "keyword_naturalness": 70.0,
    },

    "FEDERAL_ASSESSMENT": {
        "p0_coverage": 75.0,
        "experience_coverage": 80.0,
        "education_coverage": 80.0,
        "exact_jd_terminology": 60.0,
    },
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


def unique_casefold(values):
    out = []
    seen = set()

    for value in values:
        value = str(value or "").strip()

        if not value:
            continue

        key = value.casefold()

        if key in seen:
            continue

        seen.add(key)
        out.append(value)

    return out


def recursive_strings(obj):
    out = []

    if isinstance(obj, str):
        value = obj.strip()

        if value:
            out.append(value)

    elif isinstance(obj, list):
        for item in obj:
            out.extend(
                recursive_strings(item)
            )

    elif isinstance(obj, dict):
        for value in obj.values():
            out.extend(
                recursive_strings(value)
            )

    return out


def semantic_map_by_requirement(
    semantic_map,
):
    return {
        row.get("requirement_id"):
            row
        for row in semantic_map.get(
            "requirements",
            [],
        )
        if row.get("requirement_id")
    }


def semantic_phrases(
    requirement,
    semantic_entry,
):
    phrases = []

    base = requirement.get(
        "normalized_requirement"
    ) or requirement.get(
        "exact_quote",
        "",
    )

    if base:
        phrases.append(base)

    for item in requirement.get(
        "semantic_equivalents",
        [],
    ):
        phrases.append(item)

    if semantic_entry:
        layer = semantic_entry.get(
            "semantic_layer",
            {},
        )

        for item in recursive_strings(layer):
            # Avoid treating huge prose blobs as one semantic synonym.
            if (
                2
                <= len(
                    meaningful_tokens(item)
                )
                <= 12
            ):
                phrases.append(item)

    return unique_casefold(
        phrases
    )


def exact_terms_for_requirement(
    requirement,
):
    terms = []

    for field in [
        "exact_tools_technologies",
        "exact_work_products",
        "exact_methods",
    ]:
        terms.extend(
            requirement.get(
                field,
                [],
            )
        )

    return unique_casefold(
        terms
    )


def aggregate_terms(
    requirements,
    category,
):
    return unique_casefold(
        requirements.get(
            "aggregate_exact_terms",
            {},
        ).get(
            category,
            [],
        )
    )


def token_coverage(
    phrase,
    text,
):
    expected = meaningful_tokens(
        phrase
    )

    if not expected:
        return 1.0

    visible = set(
        tokens(text)
    )

    return (
        sum(
            token in visible
            for token in expected
        )
        / len(expected)
    )


def best_semantic_coverage(
    requirement,
    semantic_entry,
    text,
):
    phrases = semantic_phrases(
        requirement,
        semantic_entry,
    )

    if not phrases:
        return 1.0

    return max(
        token_coverage(
            phrase,
            text,
        )
        for phrase in phrases
    )


def exact_term_coverage(
    terms,
    text,
):
    terms = unique_casefold(
        terms
    )

    if not terms:
        return 1.0, [], []

    found = [
        term
        for term in terms
        if phrase_present(
            term,
            text,
        )
    ]

    missing = [
        term
        for term in terms
        if term not in found
    ]

    return (
        len(found) / len(terms),
        found,
        missing,
    )

def verified_chronology_structured_support(
    requirement,
):
    """
    Credit structured ATS visibility only when:

    1. deterministic constraint validation says the requirement PASSes,
    2. that PASS is backed by VERIFIED_CHRONOLOGY_DERIVED evidence,
    3. the exact evidence entities used to establish the duration are
       present in the generated resume experience section.

    This does not invent keywords, duration, industry history, or
    employer/project placement. It models what a structured parser can
    derive from visible role/date chronology already on the resume.
    """

    if (
        not CONSTRAINT_FILE.exists()
        or not RESUME_FILE.exists()
    ):
        return None

    try:
        constraints = json.loads(
            CONSTRAINT_FILE.read_text(
                encoding="utf-8"
            )
        )

        resume = json.loads(
            RESUME_FILE.read_text(
                encoding="utf-8"
            )
        )

    except Exception:
        return None

    rid = requirement.get(
        "requirement_id"
    )

    if not rid:
        return None

    constraint = next(
        (
            row
            for row in constraints.get(
                "requirements",
                [],
            )
            if row.get(
                "requirement_id"
            ) == rid
        ),
        None,
    )

    if not constraint:
        return None

    if str(
        constraint.get(
            "overall_status",
            "",
        )
    ).upper() != "PASS":
        return None

    verified_nodes = []

    def walk(value):
        if isinstance(value, dict):

            evidence_entities = (
                value.get(
                    "evidence_entities",
                    [],
                )
                or []
            )

            if (
                str(
                    value.get(
                        "status",
                        "",
                    )
                ).upper() == "PASS"
                and str(
                    value.get(
                        "claim_class",
                        "",
                    )
                ).upper()
                in {"VERIFIED_CHRONOLOGY_DERIVED", ""}
                and (value.get('claim_class') == 'VERIFIED_CHRONOLOGY_DERIVED' or value.get('basis') == 'VERIFIED_PROFESSIONAL_CHRONOLOGY')
                and evidence_entities
            ):
                verified_nodes.append(
                    value
                )

            for child in value.values():
                walk(child)

        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(constraint)

    if not verified_nodes:
        return None

    #
    # Generated resumes expose experience blocks such as EXPBLOCK-003,
    # while verified chronology is attached to source evidence entities
    # such as EXP-004. Resolve that namespace boundary through the
    # deterministic experience-selection artifact.
    #
    # Backward compatibility:
    # - if a resume row directly carries entity_id/evidence_id, use it;
    # - otherwise map block_id -> evidence_ids from experience selection.

    selection_path = (
        RUNTIME
        / "experience_selection.json"
    )

    selection = {}

    if selection_path.exists():
        try:
            selection = json.loads(
                selection_path.read_text(
                    encoding="utf-8"
                )
            )
        except Exception:
            selection = {}

    block_to_evidence = {}

    def collect_block_evidence(value):
        if isinstance(value, dict):

            block_id = str(
                value.get(
                    "block_id",
                    "",
                )
            ).strip()

            evidence_ids = {
                str(x).strip()
                for x in (
                    value.get(
                        "evidence_ids",
                        [],
                    )
                    or []
                )
                if str(x).strip()
            }

            if (
                block_id
                and evidence_ids
            ):
                block_to_evidence.setdefault(
                    block_id,
                    set(),
                ).update(
                    evidence_ids
                )

            for child in value.values():
                collect_block_evidence(
                    child
                )

        elif isinstance(value, list):
            for child in value:
                collect_block_evidence(
                    child
                )

    collect_block_evidence(
        selection
    )

    resume_experience_ids = set()

    for row in resume.get(
        "experience",
        [],
    ):
        if not isinstance(
            row,
            dict,
        ):
            continue

        for field in (
            "entity_id",
            "evidence_id",
        ):
            value = str(
                row.get(
                    field,
                    "",
                )
            ).strip()

            if value:
                resume_experience_ids.add(
                    value
                )

        for value in (
            row.get(
                "evidence_ids",
                [],
            )
            or []
        ):
            value = str(
                value
            ).strip()

            if value:
                resume_experience_ids.add(
                    value
                )

        block_id = str(
            row.get(
                "block_id",
                "",
            )
        ).strip()

        if block_id:
            resume_experience_ids.update(
                block_to_evidence.get(
                    block_id,
                    set(),
                )
            )

    if not resume_experience_ids:
        return None

    for node in verified_nodes:

        evidence_entities = {
            str(x).strip()
            for x in node.get(
                "evidence_entities",
                [],
            )
            if str(x).strip()
        }

        if (
            evidence_entities
            and evidence_entities.issubset(
                resume_experience_ids
            )
        ):
            return {
                "basis":
                    "VERIFIED_CHRONOLOGY_VISIBLE_IN_STRUCTURED_EXPERIENCE",

                "evidence_entities":
                    sorted(
                        evidence_entities
                    ),

                "resume_experience_entities":
                    sorted(
                        resume_experience_ids
                    ),

                "years":
                    node.get(
                        "years"
                    ),

                "required_years":
                    node.get(
                        "required_years"
                    ),
            }

    return None


def requirement_visibility(
    requirement,
    semantic_entry,
    surfaces,
):
    exact_terms = (
        exact_terms_for_requirement(
            requirement
        )
    )

    exact_cov, found, missing = (
        exact_term_coverage(
            exact_terms,
            surfaces["full"],
        )
    )

    semantic_cov = (
        best_semantic_coverage(
            requirement,
            semantic_entry,
            surfaces["full"],
        )
    )

    structured_constraint_support = (
        verified_chronology_structured_support(
            requirement
        )
    )

    if structured_constraint_support:
        semantic_cov = max(
            semantic_cov,
            1.0,
        )

    if exact_terms:
        visibility = (
            0.70 * exact_cov
            + 0.30 * semantic_cov
        )
        basis = (
            "EXACT_PLUS_SEMANTIC"
        )
        searchable = True

    else:
        if structured_constraint_support:
            visibility = 1.0
            basis = (
                "STRUCTURED_VERIFIED_CHRONOLOGY"
            )
            searchable = True
        else:
            visibility = semantic_cov
            basis = "SEMANTIC_ONLY"
            searchable = False

    return {
        "requirement_id":
            requirement.get(
                "requirement_id"
            ),

        "priority":
            requirement.get(
                "priority"
            ),

        "section":
            requirement.get(
                "section"
            ),

        "visibility":
            round(
                visibility,
                4,
            ),

        "visibility_pct":
            round(
                visibility * 100,
                2,
            ),

        "exact_term_coverage_pct":
            round(
                exact_cov * 100,
                2,
            ),

        "semantic_coverage_pct":
            round(
                semantic_cov * 100,
                2,
            ),

        "exact_terms":
            exact_terms,

        "found_exact_terms":
            found,

        "missing_exact_terms":
            missing,

        "searchable":
            searchable,

        "basis":
            basis,
    }


def constraint_map(
    constraints,
):
    return {
        row.get("requirement_id"):
            row
        for row in constraints.get(
            "requirements",
            [],
        )
        if row.get(
            "requirement_id"
        )
    }


def priority_coverage_dimension(
    requirements,
    visibility_rows,
    target_priority,
):
    by_id = {
        row["requirement_id"]: row
        for row in visibility_rows
    }

    weighted_num = 0.0
    weighted_den = 0.0
    considered = []

    for requirement in requirements.get(
        "requirements",
        [],
    ):
        priority = requirement.get(
            "priority"
        )

        if priority != target_priority:
            continue

        row = by_id.get(
            requirement.get(
                "requirement_id"
            )
        )

        if not row:
            row = {'requirement_id':requirement['requirement_id'], 'searchable':False,
                   'visibility':0.0, 'visibility_pct':0.0}

        if target_priority == "P0":
            weight = (
                5.0
                if row["searchable"]
                else 1.5
            )
        else:
            weight = (
                4.0
                if row["searchable"]
                else 0.75
            )

        weighted_num += (
            row["visibility"]
            * weight
        )

        weighted_den += weight

        considered.append({
            "requirement_id":
                row["requirement_id"],

            "priority":
                target_priority,

            "searchable":
                row["searchable"],

            "weight":
                weight,

            "visibility_pct":
                row["visibility_pct"],
        })

    score = (
        100.0
        * weighted_num
        / weighted_den
        if weighted_den
        else 100.0
    )

    return (
        round(score, 2),
        considered,
    )


def structured_semantic_phrases(
    semantic_entry,
):
    """
    Return only explicit deterministic semantic payload.

    This is intentionally separate from semantic_phrases(), because
    semantic_phrases() also supports requirement-visibility logic used by
    P0/P1 dimensions. The semantic_coverage dimension must not score raw
    requirement prose, provenance metadata, or market priors.
    """
    if not isinstance(
        semantic_entry,
        dict,
    ):
        return []

    layer = (
        semantic_entry.get(
            "semantic_layer",
            {},
        )
        or {}
    )

    phrases = []

    for field in (
        "concepts",
        "semantic_equivalents",
        "technical_depth_terms",
    ):
        for item in (
            layer.get(
                field,
                [],
            )
            or []
        ):
            value = str(
                item or ""
            ).strip()

            if value:
                phrases.append(
                    value
                )

    return unique_casefold(
        phrases
    )


def structured_semantic_dimension(
    requirements,
    semantic_map,
    surfaces,
):
    """
    Score only genuine structured semantic signals.

    P0 weight = 2
    P1 weight = 1

    Rows without a structured semantic signal are excluded from this one
    dimension only. P0/P1 visibility, exact terminology, experience,
    education, Human Gate, and all hard floors remain independent.
    """
    semantic_by_id = (
        semantic_map_by_requirement(
            semantic_map
        )
    )

    numerator = 0.0
    denominator = 0.0

    for requirement in requirements.get(
        "requirements",
        [],
    ):
        priority = requirement.get(
            "priority"
        )

        if priority not in {
            "P0",
            "P1",
        }:
            continue

        rid = requirement.get(
            "requirement_id"
        )

        phrases = (
            structured_semantic_phrases(
                semantic_by_id.get(
                    rid,
                    {},
                )
            )
        )

        if not phrases:
            continue

        coverage = max(
            token_coverage(
                phrase,
                surfaces["full"],
            )
            for phrase in phrases
        )

        weight = (
            2.0
            if priority == "P0"
            else 1.0
        )

        numerator += (
            coverage
            * 100.0
            * weight
        )

        denominator += weight

    if not denominator:
        return 100.0

    return round(
        numerator / denominator,
        2,
    )


def semantic_dimension(
    requirements,
    visibility_rows,
):
    rows = [
        row
        for row in visibility_rows
        if row["priority"]
        in {"P0", "P1"}
    ]

    if not rows:
        return 100.0

    numerator = 0.0
    denominator = 0.0

    for row in rows:
        weight = (
            2.0
            if row["priority"]
            == "P0"
            else 1.0
        )

        numerator += (
            row[
                "semantic_coverage_pct"
            ]
            * weight
        )

        denominator += weight

    return round(
        numerator / denominator,
        2,
    )


def experience_or_education_dimension(
    requirements,
    constraints,
    visibility_rows,
    resume,
    target_kind,
):
    cmap = constraint_map(
        constraints
    )

    by_id = {
        row["requirement_id"]:
            row
        for row in visibility_rows
    }

    candidates = []

    for requirement in requirements.get(
        "requirements",
        [],
    ):
        if requirement.get(
            "priority"
        ) != "P0":
            continue

        quote = str(
            requirement.get(
                "exact_quote",
                "",
            )
        )

        section = str(
            requirement.get(
                "section",
                "",
            )
        ).lower()

        is_education = (
            section == "education"
            or bool(
                re.search(
                    r"\b("
                    r"degree|"
                    r"bachelor|"
                    r"master|"
                    r"education"
                    r")\b",
                    quote,
                    flags=re.I,
                )
            )
        )

        is_experience = bool(
            re.search(
                r"\b("
                r"experience|"
                r"\d+\s*(?:\+|-|to)?\s*"
                r"\d*\s*years?"
                r")\b",
                quote,
                flags=re.I,
            )
        )

        if (
            target_kind == "education"
            and not is_education
        ):
            continue

        if (
            target_kind == "experience"
            and not is_experience
        ):
            continue

        rid = requirement.get(
            "requirement_id"
        )

        visibility = by_id.get(
            rid,
            {},
        ).get(
            "visibility",
            0.0,
        )

        constraint = cmap.get(
            rid
        )

        cstatus = str(
            (
                constraint
                or {}
            ).get(
                "overall_status",
                "",
            )
        ).upper()

        if cstatus == "PASS":
            capability = 1.0
        elif cstatus:
            capability = 0.0
        else:
            capability = 0.5

        if target_kind == "education":
            structure_visible = (
                1.0
                if resume.get("education")
                else 0.0
            )
        else:
            structure_visible = (
                1.0
                if resume.get("experience")
                else 0.0
            )

        score = (
            0.45 * capability
            + 0.35 * structure_visible
            + 0.20 * visibility
        )

        candidates.append({
            "requirement_id":
                rid,

            "kind":
                target_kind,

            "constraint_status":
                cstatus or None,

            "visibility_pct":
                round(
                    visibility * 100,
                    2,
                ),

            "structured_section_present":
                bool(
                    structure_visible
                ),

            "score_pct":
                round(
                    score * 100,
                    2,
                ),
        })

    if not candidates:
        return 100.0, []

    return (
        round(
            sum(
                row["score_pct"]
                for row in candidates
            )
            / len(candidates),
            2,
        ),
        candidates,
    )


def extract_selected_skill_names(
    skills,
):
    values = []

    selected = skills.get(
        "selected_evidence_tools",
        [],
    )

    if isinstance(
        selected,
        list,
    ):
        for item in selected:
            if isinstance(
                item,
                str,
            ):
                values.append(
                    item
                )

            elif isinstance(
                item,
                dict,
            ):
                for key in [
                    "term",
                    "skill",
                    "name",
                    "canonical",
                    "display",
                    "tool",
                ]:
                    value = item.get(
                        key
                    )

                    if isinstance(
                        value,
                        str,
                    ):
                        values.append(
                            value
                        )

    return unique_casefold(
        values
    )


def market_prior_terms(
    semantic_map,
):
    aggregate = semantic_map.get(
        "aggregate",
        {},
    )

    result = []

    for key in [
        "technical_depth_terms",
        "related_market_prior_terms",
    ]:
        value = aggregate.get(
            key,
            [],
        )

        if isinstance(
            value,
            list,
        ):
            for item in value:
                if isinstance(
                    item,
                    str,
                ):
                    result.append(
                        item
                    )

                elif isinstance(
                    item,
                    dict,
                ):
                    result.extend(
                        recursive_strings(
                            item
                        )
                    )

    return unique_casefold(
        result
    )


def implicit_skill_dimension(
    semantic_map,
    skills,
    surfaces,
):
    market = market_prior_terms(
        semantic_map
    )

    supported = (
        extract_selected_skill_names(
            skills
        )
    )

    expected = []

    for market_term in market:
        mtokens = set(
            meaningful_tokens(
                market_term
            )
        )

        if not mtokens:
            continue

        for supported_term in supported:
            stokens = set(
                meaningful_tokens(
                    supported_term
                )
            )

            if not stokens:
                continue

            if (
                mtokens <= stokens
                or stokens <= mtokens
                or mtokens
                & stokens
            ):
                expected.append(
                    market_term
                )
                break

    expected = unique_casefold(
        expected
    )[:15]

    if not expected:
        return (
            100.0,
            {
                "basis":
                    "NO_SUPPORTED_IMPLICIT_EXPECTATIONS",

                "expected":
                    [],

                "found":
                    [],

                "missing":
                    [],
            },
        )

    score, found, missing = (
        exact_term_coverage(
            expected,
            surfaces["full"],
        )
    )

    return (
        round(
            score * 100,
            2,
        ),
        {
            "basis":
                "SUPPORTED_MARKET_EXPECTATIONS",

            "expected":
                expected,

            "found":
                found,

            "missing":
                missing,
        },
    )


def keyword_naturalness(
    exact_terms,
    surfaces,
    resume=None,
):
    # Keyword naturalness measures repetition in narrative prose.
    #
    # Structured Skills is intentionally excluded: a canonical skill
    # appearing once in Skills and again in truthful prose is normal ATS
    # structure, not keyword stuffing.
    if isinstance(resume, dict):
        narrative_parts = [
            str(
                resume.get(
                    "summary",
                    "",
                )
            )
        ]

        for section in (
            "experience",
            "projects",
        ):
            for block in resume.get(
                section,
                [],
            ):
                if not isinstance(
                    block,
                    dict,
                ):
                    continue

                narrative_parts.extend(
                    str(bullet)
                    for bullet
                    in block.get(
                        "bullets",
                        [],
                    )
                    if str(
                        bullet
                    ).strip()
                )

        text = "\n".join(
            narrative_parts
        ).casefold()

        surface_scope = (
            "NARRATIVE_PROSE_EXCLUDES_STRUCTURED_SKILLS"
        )

    else:
        text = str(
            surfaces["full"]
        ).casefold()

        surface_scope = (
            "LEGACY_FULL_SURFACE"
        )

    penalties = []
    counts = {}

    for term in unique_casefold(
        exact_terms
    ):
        normalized = str(
            term
        ).strip().casefold()

        if not normalized:
            continue

        pattern = (
            r"(?<![a-z0-9])"
            + re.escape(
                normalized
            )
            + r"(?![a-z0-9])"
        )

        count = len(
            re.findall(
                pattern,
                text,
                flags=re.I,
            )
        )

        counts[term] = count

        term_token_count = len(
            meaningful_tokens(
                term
            )
        )

        allowed = (
            6
            if term_token_count <= 1
            else 3
        )

        excess = max(
            0,
            count - allowed,
        )

        if excess:
            penalties.append({
                "term":
                    term,

                "count":
                    count,

                "allowed":
                    allowed,

                "excess":
                    excess,
            })

    total_excess = sum(
        row["excess"]
        for row in penalties
    )

    score = max(
        0.0,
        100.0
        - 8.0 * total_excess,
    )

    return (
        round(score, 2),
        {
            "term_counts":
                counts,

            "penalties":
                penalties,

            "total_excess_occurrences":
                total_excess,

            "surface_scope":
                surface_scope,
        },
    )


def family_weights(
    family,
):
    weights = FAMILY_WEIGHT_GROUP.get(
        family,
        DEFAULT_WEIGHTS,
    )

    if abs(
        sum(weights.values())
        - 1.0
    ) > 0.000001:
        raise RuntimeError(
            f"ATS V2 weights do not sum to 1.0 "
            f"for family {family}"
        )

    return dict(
        weights
    )


def family_floors(
    family,
):
    floors = dict(
        DEFAULT_FLOORS
    )

    floors.update(
        FAMILY_FLOOR_OVERRIDES.get(
            family,
            {},
        )
    )

    return floors


def resolve_platform(
    requirements,
    summary_route,
):
    platform = (
        requirements.get(
            "ats",
            {},
        ).get(
            "platform"
        )
        or summary_route.get(
            "ats_platform"
        )
        or "UNKNOWN_ATS"
    )

    if str(
        platform
    ).upper() in {
        "UNKNOWN",
        "",
        "NONE",
    }:
        platform = "UNKNOWN_ATS"

    return platform


def evaluate(
    requirements,
    constraints,
    route,
    skills,
    summary_route,
    semantic_map,
    resume,
    truth,
    evidence_map=None,
):
    surfaces = resume_surfaces(
        resume
    )

    semantic_by_id = (
        semantic_map_by_requirement(
            semantic_map
        )
    )

    visibility_rows = []

    for requirement in requirements.get(
        "requirements",
        [],
    ):
        rid = requirement.get(
            "requirement_id"
        )

        visibility_rows.append(
            requirement_visibility(
                requirement,
                semantic_by_id.get(
                    rid
                ),
                surfaces,
            )
        )

    # Constraint coverage is earned by the validated supporting record,
    # visible in structured education/date fields, rather than JD wording.
    for visible in visibility_rows:
        constraint = constraint_map(constraints).get(visible['requirement_id'])
        if not constraint or constraint.get('overall_status') != 'PASS':
            continue
        checks = constraint.get('checks', [])
        proved = []
        for check in checks:
            if check.get('status') != 'PASS':
                continue
            if check.get('constraint_type') == 'education':
                degree = check.get('candidate_degree', {})
                institution = str(degree.get('institution', '')).casefold()
                if institution and any(institution == str(e.get('institution','')).casefold() for e in resume.get('education', [])):
                    proved.append('VISIBLE_VALIDATED_EDUCATION')
            if check.get('constraint_type') in {'experience_years','experience'}:
                if verified_chronology_structured_support(next(q for q in requirements['requirements'] if q['requirement_id']==visible['requirement_id'])):
                    proved.append('VISIBLE_VALIDATED_CHRONOLOGY')
        if proved and len(proved) == len(checks):
            visible.update(visibility=1.0, visibility_pct=100.0, searchable=True,
                           basis='+'.join(proved), support_status='VALIDATED_STRUCTURED_RECORD')

    # Visibility cannot turn unsupported factual scope into coverage.
    constraints_by_id = constraint_map(constraints)
    evidence_by_id = {x['requirement_id']:x for x in (evidence_map or {}).get('requirements', [])}
    coverage_blockers = []
    for row in visibility_rows:
        rid = row['requirement_id']
        constraint = constraints_by_id.get(rid)
        evidence = evidence_by_id.get(rid, {})
        reason = None
        if constraint and constraint.get('overall_status') != 'PASS':
            reason = 'CONSTRAINT_NOT_PASS'
        elif evidence.get('qualification_coverage') == 'QUALIFIER_UNVERIFIED':
            reason = 'QUALIFIER_UNVERIFIED'
        elif evidence.get('coverage_state') == 'UNMAPPED':
            reason = 'UNMAPPED_CANONICAL_REQUIREMENT'
        if reason:
            row.update(visibility=0.0, visibility_pct=0.0, support_status=reason,
                       visible_terminology_does_not_prove_truth=True)
            if row['priority'] == 'P0':coverage_blockers.append(rid+':'+reason)

    platform = resolve_platform(
        requirements,
        summary_route,
    )

    behavior = get_behavior_profile(
        platform
    )

    profile = behavior[
        "profile"
    ]

    family = profile.get(
        "behavior_family",
        "UNKNOWN_CONSERVATIVE_MIXED",
    )

    weights = family_weights(
        family
    )

    floors = family_floors(
        family
    )

    p0_score, p0_rows = (
        priority_coverage_dimension(
            requirements,
            visibility_rows,
            "P0",
        )
    )

    p1_score, p1_rows = (
        priority_coverage_dimension(
            requirements,
            visibility_rows,
            "P1",
        )
    )

    exact_terms = unique_casefold(
        aggregate_terms(
            requirements,
            "tools_technologies",
        )
        + aggregate_terms(
            requirements,
            "work_products",
        )
        + aggregate_terms(
            requirements,
            "methods",
        )
    )

    exact_fraction, found_exact, missing_exact = (
        exact_term_coverage(
            exact_terms,
            surfaces["full"],
        )
    )

    exact_score = round(
        exact_fraction * 100,
        2,
    )

    #
    # Keep requirement_visibility() and P0/P1 dimensions unchanged.
    # Only the dedicated semantic_coverage dimension uses structured
    # deterministic semantic signals.
    semantic_score = (
        structured_semantic_dimension(
            requirements,
            semantic_map,
            surfaces,
        )
    )

    tool_terms = aggregate_terms(
        requirements,
        "tools_technologies",
    )

    tool_fraction, found_tools, missing_tools = (
        exact_term_coverage(
            tool_terms,
            surfaces["full"],
        )
    )

    tool_score = round(
        tool_fraction * 100,
        2,
    )

    experience_score, experience_rows = (
        experience_or_education_dimension(
            requirements,
            constraints,
            visibility_rows,
            resume,
            "experience",
        )
    )

    education_score, education_rows = (
        experience_or_education_dimension(
            requirements,
            constraints,
            visibility_rows,
            resume,
            "education",
        )
    )

    role_score, role_basis = (
        role_alignment(
            requirements,
            route,
            surfaces,
        )
    )

    structure_score_value, structure_checks = (
        structure_score(
            resume,
            summary_route,
            truth,
        )
    )

    recruiter_score = round(
        (
            0.45 * exact_score
            + 0.25 * role_score
            + 0.20 * tool_score
            + 0.10 * structure_score_value
        ),
        2,
    )

    naturalness_score, naturalness_detail = (
        keyword_naturalness(
            exact_terms,
            surfaces,
            resume=resume,
        )
    )

    implicit_score, implicit_detail = (
        implicit_skill_dimension(
            semantic_map,
            skills,
            surfaces,
        )
    )

    dimensions = {
        "parse_structure_integrity":
            structure_score_value,

        "p0_coverage":
            p0_score,

        "p1_coverage":
            p1_score,

        "exact_jd_terminology":
            exact_score,

        "semantic_coverage":
            semantic_score,

        "tools_technology":
            tool_score,

        "experience_coverage":
            experience_score,

        "education_coverage":
            education_score,

        "role_title_alignment":
            role_score,

        "recruiter_search_retrievability":
            recruiter_score,

        "keyword_naturalness":
            naturalness_score,

        "expected_implicit_skills":
            implicit_score,
    }

    #
    # Advisory dimensions remain visible in diagnostics but cannot
    # independently lower a release-blocking aggregate below threshold.
    #
    # This preserves:
    # - the original family-specific weight definitions,
    # - all hard floors,
    # - all searchable P0/P1 requirement floors,
    # - the global PASS_THRESHOLD.
    #
    # Only the release-blocking aggregate is normalized across dimensions
    # that are actually release-blocking.
    advisory_dimensions = {
        "expected_implicit_skills",
    }

    raw_weighted_overall = round(
        sum(
            dimensions[name]
            * weight
            for name, weight
            in weights.items()
        ),
        2,
    )

    release_blocking_weight = sum(
        weight
        for name, weight
        in weights.items()
        if name not in advisory_dimensions
    )

    if release_blocking_weight <= 0:
        raise RuntimeError(
            "ATS V2 release-blocking weight sum must be positive"
        )

    overall = round(
        sum(
            dimensions[name]
            * weight
            for name, weight
            in weights.items()
            if name not in advisory_dimensions
        )
        / release_blocking_weight,
        2,
    )

    hard_fail_reasons = list(coverage_blockers)

    if truth.get(
        "gate"
    ) != "PASS":
        hard_fail_reasons.append(
            "LOCAL_TRUTH_GATE_NOT_PASS"
        )

    cmap = constraint_map(
        constraints
    )

    for requirement in requirements.get(
        "requirements",
        [],
    ):
        rid = requirement.get(
            "requirement_id"
        )

        priority = requirement.get(
            "priority"
        )

        constraint = cmap.get(
            rid
        )

        if (
            priority == "P0"
            and constraint
        ):
            status = str(
                constraint.get(
                    "overall_status",
                    "",
                )
            ).upper()

            if status != "PASS":
                hard_fail_reasons.append(
                    f"{rid}:"
                    "P0_CONSTRAINT_NOT_PASS"
                )

        blockers = requirement.get(
            "hard_blocker_phrases",
            [],
        )

        if (
            blockers
            and not constraint
        ):
            hard_fail_reasons.append(
                f"{rid}:"
                "UNRESOLVED_HARD_BLOCKER"
            )

    # Individual searchable P0/P1 floors prevent aggregate masking.
    for row in visibility_rows:
        if (
            row["priority"] == "P0"
            and row["searchable"]
            and row["visibility"]
            < 0.45
        ):
            hard_fail_reasons.append(
                f"{row['requirement_id']}:"
                "P0_SEARCHABLE_COVERAGE_BELOW_45"
            )

        if (
            row["priority"] == "P1"
            and row["searchable"]
            and row["visibility"]
            < 0.30
        ):
            hard_fail_reasons.append(
                f"{row['requirement_id']}:"
                "P1_SEARCHABLE_COVERAGE_BELOW_30"
            )

    floor_failures = []

    for name, floor in floors.items():
        score = dimensions.get(
            name
        )

        if (
            score is not None
            and score < floor
        ):
            floor_failures.append({
                "dimension":
                    name,

                "score":
                    score,

                "floor":
                    floor,
            })

            hard_fail_reasons.append(
                f"{name.upper()}:"
                f"BELOW_FLOOR_{floor:.0f}"
            )

    if overall < PASS_THRESHOLD:
        hard_fail_reasons.append(f'OVERALL_SCORE_BELOW_THRESHOLD_{PASS_THRESHOLD:g}')

    # Expected implicit skills remain a low-weight advisory dimension.
    # They never independently block release.
    gate = (
        "PASS"
        if (
            overall >= PASS_THRESHOLD
            and not hard_fail_reasons
        )
        else "FAIL"
    )

    audit = {
        "schema_version":
            "careerops-internal-ats-audit-v2",

        "score_type":
            "INTERNAL_DETERMINISTIC_ATS_COMPATIBILITY_SIMULATION",

        "external_vendor_score":
            False,

        "platform":
            platform,

        "behavior_profile_source":
            behavior.get(
                "profile_source"
            ),

        "behavior_family":
            family,

        "simulation_profile":
            profile.get(
                "simulation_profile"
            ),

        "feature_state":
            profile.get(
                "feature_state"
            ),

        "behavior_confidence":
            profile.get(
                "confidence"
            ),

        "never_assume":
            profile.get(
                "never_assume",
                [],
            ),

        "underlying_ats_resolution_recommended":
            (
                family
                == "EXPERIENCE_LAYER_OR_CRM"
            ),

        "internal_simulation_weights":
            weights,

        "hard_floors":
            floors,

        "threshold":
            PASS_THRESHOLD,

        "dimensions":
            dimensions,

        "overall":
            overall,

        "raw_weighted_overall":
            raw_weighted_overall,

        "release_blocking_weight":
            release_blocking_weight,

        "advisory_dimensions":
            sorted(
                advisory_dimensions
            ),

        "floor_failures":
            floor_failures,

        "hard_fail_reasons":
            unique_casefold(
                hard_fail_reasons
            ),

        "requirement_visibility":
            visibility_rows,

        "p0_coverage_detail":
            p0_rows,

        "p1_coverage_detail":
            p1_rows,

        "exact_jd_terminology": {
            "all":
                exact_terms,

            "found":
                found_exact,

            "missing":
                missing_exact,
        },

        "tools_technology": {
            "all":
                tool_terms,

            "found":
                found_tools,

            "missing":
                missing_tools,
        },

        "experience_coverage_detail":
            experience_rows,

        "education_coverage_detail":
            education_rows,

        "role_title_alignment": {
            "score":
                role_score,

            "basis":
                role_basis,
        },

        "recruiter_search_retrievability": {
            "score":
                recruiter_score,

            "components": {
                "exact_jd_terminology":
                    exact_score,

                "role_title_alignment":
                    role_score,

                "tools_technology":
                    tool_score,

                "content_structure":
                    structure_score_value,
            },
        },

        "keyword_naturalness":
            naturalness_detail,

        "expected_implicit_skills":
            implicit_detail,

        "structure_checks":
            structure_checks,

        "policy": {
            "vendor_private_weights_claimed":
                False,

            "employer_configuration_assumed":
                False,

            "ai_module_assumed_enabled":
                False,

            "keyword_frequency_equals_rank":
                False,

            "match_score_equals_hiring_decision":
                False,

            "expected_implicit_skills_release_blocking":
                False,

            "advisory_dimensions_excluded_from_release_score":
                True,

            "release_score_weight_normalized":
                True,

            "deterministic_only":
                True,
        },

        "model_calls":
            0,
    }

    result = {
        "schema_version":
            "careerops-internal-ats-gate-v2",

        "gate":
            gate,

        "score":
            overall,

        "threshold":
            PASS_THRESHOLD,

        "score_type":
            "INTERNAL_DETERMINISTIC_ATS_COMPATIBILITY_SIMULATION",

        "external_vendor_score":
            False,

        "ats_platform":
            platform,

        "behavior_family":
            family,

        "simulation_profile":
            profile.get(
                "simulation_profile"
            ),

        "behavior_profile_source":
            behavior.get(
                "profile_source"
            ),

        "dimensions":
            dimensions,

        "hard_floors":
            floors,

        "floor_failures":
            floor_failures,

        "hard_fail_reasons":
            unique_casefold(
                hard_fail_reasons
            ),

        "missing_exact_jd_terms":
            missing_exact,

        "missing_tools_technology":
            missing_tools,

        "requirement_gaps": [
            row["requirement_id"]
            for row in visibility_rows
            if row["visibility"] < 0.50
        ],

        "requirement_partials": [
            row["requirement_id"]
            for row in visibility_rows
            if (
                0.50
                <= row["visibility"]
                < 0.80
            )
        ],

        "underlying_ats_resolution_recommended":
            (
                family
                == "EXPERIENCE_LAYER_OR_CRM"
            ),

        "model_calls":
            0,

        "model_tokens":
            0,
    }

    return result, audit


def main():
    requirements = load(
        REQ_FILE
    )

    constraints = load(
        CONSTRAINT_FILE
    )

    route = load(
        ROUTE_FILE
    )

    skills = load(
        SKILLS_FILE
    )

    summary_route = load(
        SUMMARY_FILE
    )

    semantic_map = load(
        SEMANTIC_FILE
    )

    resume = load(
        RESUME_FILE
    )

    truth = load(
        TRUTH_FILE
    )

    result, audit = evaluate(
        requirements,
        constraints,
        route,
        skills,
        summary_route,
        semantic_map,
        resume,
        truth,
        evidence_map=load(RUNTIME / 'requirement_evidence_map.json'),
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

    OUT.write_text(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    print("=" * 96)
    print("ATS GATE V2")
    print("=" * 96)

    print(
        "GATE:",
        result["gate"],
    )

    print(
        "SCORE:",
        f"{result['score']:.2f}/100",
    )

    print(
        "PLATFORM:",
        result["ats_platform"],
    )

    print(
        "BEHAVIOR FAMILY:",
        result["behavior_family"],
    )

    print()
    print("DIMENSIONS")

    for name, score in result[
        "dimensions"
    ].items():
        floor = result[
            "hard_floors"
        ].get(
            name
        )

        suffix = (
            f" | floor={floor:.2f}"
            if floor is not None
            else " | advisory"
        )

        print(
            f"  {name}: "
            f"{score:.2f}"
            f"{suffix}"
        )

    print()
    print(
        "HARD FAIL REASONS:",
        (
            result[
                "hard_fail_reasons"
            ]
            or "NONE"
        ),
    )

    print(
        "EXTERNAL ATS/VENDOR SCORE: NO"
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
    from careerops_requirement_authority import run_guarded
    run_guarded(main, RUNTIME, "careerops_ats_gate_v2.py")
