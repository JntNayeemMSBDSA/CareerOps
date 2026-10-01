#!/usr/bin/env python3

import json
import os
import re
from pathlib import Path

from careerops_runtime import runtime_dir

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = runtime_dir(ROOT)

REQ_FILE = RUNTIME / "jd_requirements.json"
CONSTRAINT_FILE = RUNTIME / "constraint_validation.json"
ROUTE_FILE = RUNTIME / "role_routing.json"
SKILLS_FILE = RUNTIME / "technical_skills_plan.json"
SUMMARY_FILE = RUNTIME / "summary_route.json"
RESUME_FILE = Path(
    os.environ.get(
        "CAREEROPS_RESUME_INPUT",
        str(RUNTIME / "generated_resume_content.json"),
    )
).expanduser().resolve()
TRUTH_FILE = RUNTIME / "local_truth_gate.json"

OUT = RUNTIME / "ats_gate.json"
AUDIT = RUNTIME / "ats_audit.json"

PASS_THRESHOLD = 85.0

PRIORITY_WEIGHT = {
    "P0": 5.0,
    "P1": 4.0,
    "P2": 2.0,
    "P3": 1.0,
}

STOPWORDS = {
    "a", "an", "and", "or", "the", "of", "to", "for", "with",
    "in", "on", "at", "by", "from", "as", "is", "are", "be",
    "have", "has", "having", "must", "should", "preferred",
    "prefer", "required", "requirement", "experience", "experienced",
    "year", "years", "plus", "minimum", "strong", "ability",
    "knowledge", "proficiency", "proficient",
}

SPECIAL_CANONICAL = {
    "built": "build",
    "building": "build",
    "builds": "build",

    "analyzed": "analyze",
    "analysed": "analyze",
    "analyzing": "analyze",
    "analysing": "analyze",
    "analysis": "analyze",
    "analytics": "analyze",
    "analytical": "analyze",

    "communicated": "communicate",
    "communicating": "communicate",
    "communication": "communicate",

    "findings": "finding",

    "stakeholders": "stakeholder",

    "dashboards": "dashboard",
    "dashboarding": "dashboard",

    "pipelines": "pipeline",

    "reports": "report",
    "reporting": "report",

    "models": "model",
    "modeling": "model",
    "modelling": "model",

    "developed": "develop",
    "developing": "develop",

    "created": "create",
    "creating": "create",

    "managed": "manage",
    "managing": "manage",

    "supported": "support",
    "supporting": "support",

    "automated": "automate",
    "automation": "automate",

    "visualizations": "visualization",
    "visualisation": "visualization",
    "visualisations": "visualization",
}


def load(path):
    if not path.exists():
        raise SystemExit(f"Missing required file: {path}")
    return json.loads(path.read_text())


def tokens(text):
    raw = re.findall(
        r"[A-Za-z0-9]+(?:\.[0-9]+)?",
        str(text).lower(),
    )

    out = []

    for token in raw:
        if token in SPECIAL_CANONICAL:
            token = SPECIAL_CANONICAL[token]

        elif token.endswith("ies") and len(token) > 4:
            token = token[:-3] + "y"

        elif (
            token.endswith("s")
            and len(token) > 4
            and not token.endswith("ss")
        ):
            token = token[:-1]

        out.append(token)

    return out


def meaningful_tokens(text):
    return [
        t for t in tokens(text)
        if t not in STOPWORDS
        and not t.isdigit()
        and len(t) > 1
    ]


def phrase_present(phrase, text):
    p = tokens(phrase)
    t = tokens(text)

    if not p:
        return False

    if len(p) == 1:
        return p[0] in set(t)

    plen = len(p)

    for i in range(len(t) - plen + 1):
        if t[i:i + plen] == p:
            return True

    return False


def concept_coverage(requirement, body_text):
    base = meaningful_tokens(
        requirement.get(
            "normalized_requirement",
            requirement.get("exact_quote", ""),
        )
    )

    body = set(tokens(body_text))

    def coverage(term_list):
        if not term_list:
            return 1.0

        matched = sum(
            token in body
            for token in term_list
        )

        return matched / len(term_list)

    scores = [coverage(base)]

    # Semantic equivalents are additive alternatives, not new
    # mandatory denominator terms.
    for equivalent in requirement.get(
        "semantic_equivalents",
        [],
    ):
        eq = meaningful_tokens(equivalent)

        if eq:
            scores.append(
                coverage(eq)
            )

    return max(scores) if scores else 1.0


def resume_surfaces(resume):
    summary = resume.get("summary", "")

    experience_bullets = []
    experience_titles = []

    for exp in resume.get("experience", []):
        experience_titles.extend([
            exp.get("company", ""),
            exp.get("title", ""),
        ])

        experience_bullets.extend(
            exp.get("bullets", [])
        )

    project_text = []

    for project in resume.get("projects", []):
        project_text.append(
            project.get("name", "")
        )
        project_text.extend(
            project.get("bullets", [])
        )

    skill_text = []

    for line in resume.get("skills", []):
        skill_text.append(
            line.get("category", "")
        )
        skill_text.extend(
            line.get("terms", [])
        )

    education_text = []

    for edu in resume.get("education", []):
        education_text.extend([
            edu.get("institution", ""),
            edu.get("degree", ""),
            edu.get("graduation", ""),
            edu.get("gpa", ""),
        ])

    body_text = "\n".join([
        summary,
        *experience_titles,
        *experience_bullets,
        *project_text,
        *education_text,
    ])

    full_text = "\n".join([
        body_text,
        *skill_text,
    ])

    return {
        "summary": summary,
        "body": body_text,
        "skills": "\n".join(skill_text),
        "full": full_text,
        "titles": "\n".join(experience_titles),
    }


def unique_terms(requirements):
    result = []

    for category in [
        "tools_technologies",
        "work_products",
        "methods",
    ]:
        for term in requirements.get(
            "aggregate_exact_terms",
            {},
        ).get(category, []):
            if term.lower() not in {
                x.lower()
                for x in result
            }:
                result.append(term)

    return result


def requirement_score(
    requirement,
    constraint,
    surfaces,
):
    req_id = requirement["requirement_id"]

    # Explicit validated constraint is authoritative.
    if constraint:
        status = str(
            constraint.get(
                "overall_status",
                "",
            )
        ).upper()

        if status == "PASS":
            return {
                "requirement_id": req_id,
                "priority": requirement["priority"],
                "coverage": 1.0,
                "coverage_pct": 100.0,
                "status": "FULL",
                "basis": "VALIDATED_CONSTRAINT",
                "constraint_status": "PASS",
                "score_eligible": True,
                "release_blocking": True,
                "exact_terms": [],
                "missing_exact_terms": [],
                "concept_coverage_pct": 100.0,
                "exact_quote_present": phrase_present(
                    requirement.get(
                        "exact_quote",
                        "",
                    ),
                    surfaces["full"],
                ),
            }

        return {
            "requirement_id": req_id,
            "priority": requirement["priority"],
            "coverage": 0.0,
            "coverage_pct": 0.0,
            "status": "GAP",
            "basis": "FAILED_OR_UNRESOLVED_CONSTRAINT",
            "constraint_status": status or "UNKNOWN",
            "score_eligible": True,
            "release_blocking": True,
            "exact_terms": [],
            "missing_exact_terms": [],
            "concept_coverage_pct": 0.0,
            "exact_quote_present": False,
        }

    exact_terms = []

    for field in [
        "exact_tools_technologies",
        "exact_work_products",
        "exact_methods",
    ]:
        for term in requirement.get(
            field,
            [],
        ):
            if term.lower() not in {
                x.lower()
                for x in exact_terms
            }:
                exact_terms.append(term)

    found_terms = [
        term for term in exact_terms
        if phrase_present(
            term,
            surfaces["full"],
        )
    ]

    missing_terms = [
        term for term in exact_terms
        if term not in found_terms
    ]

    term_coverage = (
        len(found_terms) / len(exact_terms)
        if exact_terms
        else None
    )

    concept = concept_coverage(
        requirement,
        surfaces["body"],
    )

    if term_coverage is None:
        # Narrative responsibilities, behavioral requirements,
        # employer-specific procedures, mission/culture language,
        # and similar prose remain visible in the audit and generation
        # context, but are not reliable deterministic ATS-score inputs.
        coverage = concept
        basis = "ADVISORY_CONCEPT_COVERAGE"
        score_eligible = False

    else:
        # Concrete ATS-searchable JD entities are the primary retrieval
        # signal. Context remains meaningful, but raw whole-sentence
        # lexical overlap must not dominate a tailored resume.
        coverage = (
            0.85 * term_coverage
            + 0.15 * concept
        )

        basis = (
            "EXACT_TERM_AND_BODY_CONCEPT_COVERAGE"
        )
        score_eligible = True

    coverage = max(
        0.0,
        min(1.0, coverage),
    )

    if coverage >= 0.80:
        status = "FULL"
    elif coverage >= 0.50:
        status = "PARTIAL"
    else:
        status = "GAP"

    return {
        "requirement_id": req_id,
        "priority": requirement["priority"],
        "coverage": round(coverage, 4),
        "coverage_pct": round(
            coverage * 100,
            2,
        ),
        "status": status,
        "basis": basis,
        "constraint_status": None,
        "score_eligible": score_eligible,
        "release_blocking": bool(
            score_eligible
            and requirement["priority"] in {
                "P0",
                "P1",
            }
        ),
        "exact_terms": exact_terms,
        "found_exact_terms": found_terms,
        "missing_exact_terms": missing_terms,
        "concept_coverage_pct": round(
            concept * 100,
            2,
        ),
        "exact_quote_present": phrase_present(
            requirement.get(
                "exact_quote",
                "",
            ),
            surfaces["full"],
        ),
    }


def role_alignment(
    req,
    route,
    surfaces,
):
    candidates = []

    target = req.get(
        "target_role_title_candidate",
        "",
    )

    primary = (
        route.get(
            "application_route",
            {},
        )
        .get("primary", {})
        .get("search_title", "")
    )

    for role in [target, primary]:
        if (
            role
            and role.lower()
            not in {
                x.lower()
                for x in candidates
            }
        ):
            candidates.append(role)

    if not candidates:
        return 100.0, "NO_TARGET_ROLE_AVAILABLE"

    summary_and_titles = "\n".join([
        surfaces["summary"],
        surfaces["titles"],
    ])

    if any(
        phrase_present(
            role,
            summary_and_titles,
        )
        for role in candidates
    ):
        return 100.0, "TARGET_ROLE_VISIBLE"

    #
    # Candidate titles are aliases, not a vocabulary that should be
    # unioned into one synthetic mega-title. A portal/page title can
    # contain navigation text such as "Applicant Portal | ...".
    #
    # Score every legitimate available role representation separately
    # and use the strongest alignment. This prevents unrelated portal
    # tokens from diluting an otherwise correct role match.
    visible = set(
        meaningful_tokens(
            summary_and_titles
        )
    )

    candidate_scores = []

    for role in candidates:
        role_tokens = set(
            meaningful_tokens(role)
        )

        if not role_tokens:
            continue

        overlap = (
            len(
                role_tokens
                & visible
            )
            / len(
                role_tokens
            )
        )

        candidate_scores.append(
            overlap
        )

    if not candidate_scores:
        return (
            100.0,
            "NO_MEANINGFUL_ROLE_TOKENS",
        )

    return (
        round(
            max(candidate_scores)
            * 100,
            2,
        ),
        "BEST_ROLE_ALIAS_TOKEN_OVERLAP",
    )


def structure_score(
    resume,
    summary_route,
    truth_gate,
):
    checks = {
        "truth_gate_pass":
            truth_gate.get("gate") == "PASS",

        "experience_present":
            bool(resume.get("experience")),

        "projects_present":
            bool(resume.get("projects")),

        "skills_present":
            bool(resume.get("skills")),

        "education_present":
            bool(resume.get("education")),
    }

    mode = str(
        summary_route.get(
            "mode",
            "",
        )
    ).upper()

    summary = str(
        resume.get(
            "summary",
            "",
        )
    ).strip()

    if mode == "NONE":
        checks["summary_route_compliant"] = (
            summary == ""
        )
    else:
        checks["summary_route_compliant"] = (
            bool(summary)
        )

    score = (
        100.0
        * sum(checks.values())
        / len(checks)
    )

    return round(score, 2), checks


def main():
    req = load(REQ_FILE)
    constraints = load(CONSTRAINT_FILE)
    route = load(ROUTE_FILE)
    skills = load(SKILLS_FILE)
    summary_route = load(SUMMARY_FILE)
    resume = load(RESUME_FILE)
    truth = load(TRUTH_FILE)

    surfaces = resume_surfaces(
        resume
    )

    constraint_map = {
        x["requirement_id"]: x
        for x in constraints.get(
            "requirements",
            [],
        )
    }

    requirement_results = []

    for requirement in req.get(
        "requirements",
        [],
    ):
        requirement_results.append(
            requirement_score(
                requirement,
                constraint_map.get(
                    requirement[
                        "requirement_id"
                    ]
                ),
                surfaces,
            )
        )

    weighted_num = 0.0
    weighted_den = 0.0

    for result in requirement_results:
        if not result.get(
            "score_eligible",
            False,
        ):
            continue

        weight = PRIORITY_WEIGHT.get(
            result["priority"],
            1.0,
        )

        weighted_num += (
            result["coverage"]
            * weight
        )

        weighted_den += weight

    requirement_score_pct = (
        100.0 * weighted_num / weighted_den
        if weighted_den
        else 100.0
    )

    exact_terms = unique_terms(req)

    found_exact = [
        term for term in exact_terms
        if phrase_present(
            term,
            surfaces["full"],
        )
    ]

    missing_exact = [
        term for term in exact_terms
        if term not in found_exact
    ]

    exact_score = (
        100.0
        * len(found_exact)
        / len(exact_terms)
        if exact_terms
        else 100.0
    )

    role_score, role_basis = (
        role_alignment(
            req,
            route,
            surfaces,
        )
    )

    struct_score, struct_checks = (
        structure_score(
            resume,
            summary_route,
            truth,
        )
    )

    overall = (
        0.70 * requirement_score_pct
        + 0.15 * exact_score
        + 0.10 * role_score
        + 0.05 * struct_score
    )

    overall = round(
        overall,
        2,
    )

    hard_fail_reasons = []

    if truth.get("gate") != "PASS":
        hard_fail_reasons.append(
            "LOCAL_TRUTH_GATE_NOT_PASS"
        )

    # Explicit constraint failures on P0 requirements.
    for result in requirement_results:
        if (
            result["priority"] == "P0"
            and result.get(
                "constraint_status"
            )
            not in {None, "PASS"}
        ):
            hard_fail_reasons.append(
                f"{result['requirement_id']}:"
                "P0_CONSTRAINT_NOT_PASS"
            )

        # A P0 requirement without a formal constraint check still
        # cannot be badly uncovered.
        if (
            result["priority"] == "P0"
            and result.get(
                "score_eligible",
                False,
            )
            and result["coverage"] < 0.50
        ):
            hard_fail_reasons.append(
                f"{result['requirement_id']}:"
                "P0_COVERAGE_BELOW_50"
            )

        # P1 is a major/core responsibility. Extremely weak
        # coverage is a release blocker even if aggregate score is high.
        if (
            result["priority"] == "P1"
            and result.get(
                "score_eligible",
                False,
            )
            and result["coverage"] < 0.35
        ):
            hard_fail_reasons.append(
                f"{result['requirement_id']}:"
                "P1_MAJOR_GAP"
            )

    # Any explicit hard blocker language that the constraint layer has
    # not resolved must not silently pass.
    for requirement in req.get(
        "requirements",
        [],
    ):
        blockers = requirement.get(
            "hard_blocker_phrases",
            [],
        )

        if not blockers:
            continue

        validated = constraint_map.get(
            requirement[
                "requirement_id"
            ]
        )

        if not validated:
            hard_fail_reasons.append(
                f"{requirement['requirement_id']}:"
                "UNRESOLVED_HARD_BLOCKER"
            )

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
            "careerops-internal-ats-audit-v1",

        "score_type":
            "INTERNAL_DETERMINISTIC_RESUME_TO_JD_COVERAGE",

        "external_vendor_score":
            False,

        "ats_platform":
            req.get(
                "ats",
                {},
            ).get(
                "platform",
                "UNKNOWN",
            ),

        "ats_specific_behavior_applied":
            bool(
                summary_route.get(
                    "ats_behavior_profile_supported",
                    False,
                )
            ),

        "threshold": PASS_THRESHOLD,

        "scores": {
            "overall": overall,
            "requirements":
                round(
                    requirement_score_pct,
                    2,
                ),
            "exact_jd_terms":
                round(
                    exact_score,
                    2,
                ),
            "role_alignment":
                role_score,
            "content_structure":
                struct_score,
        },

        "weights": {
            "requirements": 0.70,
            "exact_jd_terms": 0.15,
            "role_alignment": 0.10,
            "content_structure": 0.05,
        },

        "requirement_priority_weights":
            PRIORITY_WEIGHT,

        "score_eligible_requirements": [
            x["requirement_id"]
            for x in requirement_results
            if x.get("score_eligible")
        ],

        "advisory_requirements": [
            x["requirement_id"]
            for x in requirement_results
            if not x.get("score_eligible")
        ],

        "requirements":
            requirement_results,

        "exact_jd_terms": {
            "all": exact_terms,
            "found": found_exact,
            "missing": missing_exact,
        },

        "role_alignment": {
            "score": role_score,
            "basis": role_basis,
            "target_role_title":
                req.get(
                    "target_role_title_candidate"
                ),
            "application_primary":
                route.get(
                    "application_route",
                    {},
                ).get(
                    "primary",
                    {},
                ).get(
                    "search_title"
                ),
        },

        "structure_checks":
            struct_checks,

        "truth_gate":
            truth.get("gate"),

        "hard_fail_reasons":
            hard_fail_reasons,

        "visible_exact_jd_tools":
            skills.get(
                "exact_jd_tools",
                [],
            ),
    }

    result = {
        "schema_version":
            "careerops-internal-ats-gate-v1",

        "gate": gate,

        "score": overall,

        "threshold":
            PASS_THRESHOLD,

        "score_type":
            "INTERNAL_DETERMINISTIC",

        "external_vendor_score":
            False,

        "hard_fail_reasons":
            hard_fail_reasons,

        "missing_exact_jd_terms":
            missing_exact,

        "requirement_gaps": [
            x["requirement_id"]
            for x in requirement_results
            if x["status"] == "GAP"
        ],

        "requirement_partials": [
            x["requirement_id"]
            for x in requirement_results
            if x["status"] == "PARTIAL"
        ],

        "model_calls": 0,
        "model_tokens": 0,
    }

    AUDIT.write_text(
        json.dumps(
            audit,
            indent=2,
            ensure_ascii=False,
        ) + "\n"
    )

    OUT.write_text(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        ) + "\n"
    )

    print("=" * 96)
    print("INTERNAL DETERMINISTIC ATS GATE")
    print("=" * 96)

    print(
        "GATE:",
        gate,
    )

    print(
        "OVERALL SCORE:",
        f"{overall:.2f}/100",
    )

    print(
        "THRESHOLD:",
        f"{PASS_THRESHOLD:.2f}",
    )

    print()
    print("COMPONENT SCORES")

    print(
        "  Requirements:",
        f"{requirement_score_pct:.2f}",
    )

    print(
        "  Exact JD terms:",
        f"{exact_score:.2f}",
    )

    print(
        "  Role alignment:",
        f"{role_score:.2f}",
    )

    print(
        "  Content structure:",
        f"{struct_score:.2f}",
    )

    print()
    print("REQUIREMENT AUDIT")

    for x in requirement_results:
        print(
            f"  {x['requirement_id']} "
            f"{x['priority']} | "
            f"{x['status']} | "
            f"{x['coverage_pct']:.2f}% | "
            f"{'SCORED' if x.get('score_eligible') else 'ADVISORY'}"
        )

        if x.get(
            "missing_exact_terms"
        ):
            print(
                "    Missing exact:",
                ", ".join(
                    x[
                        "missing_exact_terms"
                    ]
                ),
            )

        print(
            "    Concept coverage:",
            f"{x['concept_coverage_pct']:.2f}%",
        )

    print()
    print(
        "EXACT JD TERMS FOUND:",
        (
            ", ".join(found_exact)
            if found_exact
            else "NONE"
        ),
    )

    print(
        "EXACT JD TERMS MISSING:",
        (
            ", ".join(missing_exact)
            if missing_exact
            else "NONE"
        ),
    )

    print()
    print(
        "HARD FAIL REASONS:",
        (
            hard_fail_reasons
            if hard_fail_reasons
            else "NONE"
        ),
    )

    print()
    print(
        "SCORE TYPE: INTERNAL DETERMINISTIC "
        "RESUME-TO-JD COVERAGE"
    )

    print(
        "EXTERNAL ATS/VENDOR SCORE: NO"
    )

    print("MODEL CALLS: 0")
    print("MODEL TOKENS: 0")

    print()
    print(
        "OUTPUT:",
        OUT.relative_to(ROOT),
    )

    print(
        "AUDIT:",
        AUDIT.relative_to(ROOT),
    )


if __name__ == "__main__":
    main()
