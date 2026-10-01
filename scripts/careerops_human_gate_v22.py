#!/usr/bin/env python3

import json
import os
from pathlib import Path
from careerops_requirement_regeneration import canonical_ledger_path

from careerops_runtime import runtime_dir
import careerops_human_gate_v21 as v21


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
SOURCE_REQUIREMENTS_FILE = canonical_ledger_path(RUNTIME)
EFFECTIVE_REQUIREMENTS_FILE = RUNTIME / "jd_requirements_effective.json"

if EFFECTIVE_REQUIREMENTS_FILE.is_file():
    REQUIREMENTS_FILE = EFFECTIVE_REQUIREMENTS_FILE
elif (RUNTIME.parent / "manifest.json").is_file():
    raise SystemExit(
        "STOP: production effective requirement ledger is missing."
    )
else:
    REQUIREMENTS_FILE = SOURCE_REQUIREMENTS_FILE
EVIDENCE_FILE = RUNTIME / "requirement_evidence_map.json"
EXPERIENCE_FILE = RUNTIME / "experience_selection.json"
PROJECT_FILE = RUNTIME / "project_selection.json"
SKILLS_FILE = RUNTIME / "technical_skills_plan.json"

OUT = RUNTIME / "human_gate.json"
AUDIT = RUNTIME / "human_audit.json"

PASS_THRESHOLD = 85.0

LOCKED_DIMENSIONS = list(
    v21.LOCKED_DIMENSIONS
)

# These remain useful quality targets.
# Falling below one creates a warning, not automatically a failure.
QUALITY_TARGETS = dict(
    v21.HARD_FLOORS
)

# Only genuinely severe defects should independently block Human quality.
SEVERE_FLOORS = {
    "immediate_role_identity": 30.0,
    "first_evidence_strength": 30.0,
    "strongest_evidence_placement": 25.0,
    "technical_depth": 30.0,
    "specificity": 30.0,
    "business_relevance": 25.0,
    "career_coherence": 30.0,
    "information_density": 30.0,
    "redundancy": 40.0,
    "readability": 40.0,
    "natural_language": 40.0,
    "generic_ai_language": 45.0,
}

NON_BLOCKING_TARGETS = {
    "quantified_impact",
    "differentiation",
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


def classify_extremely_weak(
    reasons,
):
    locations = []

    for reason in reasons:
        if not reason.startswith(
            "EXTREMELY_WEAK_BULLET:"
        ):
            continue

        payload = reason.split(
            ":",
            1,
        )[1]

        locations.extend(
            item.strip()
            for item in payload.split(",")
            if item.strip()
        )

    first_evidence_weak = any(
        location
        == "experience[0].bullets[0]"
        for location in locations
    )

    severe = (
        first_evidence_weak
        or len(locations) >= 2
    )

    return {
        "locations":
            locations,

        "first_evidence_weak":
            first_evidence_weak,

        "severe":
            severe,
    }


def calibrate(
    result,
    audit,
):
    dimensions = dict(
        result[
            "dimensions"
        ]
    )

    warning_dimensions = []

    for name, target in (
        QUALITY_TARGETS.items()
    ):
        score = dimensions[
            name
        ]

        if (
            score < target
            and name
            not in NON_BLOCKING_TARGETS
        ):
            warning_dimensions.append({
                "dimension":
                    name,

                "score":
                    score,

                "quality_target":
                    target,
            })

    advisory_dimensions = []

    for name in sorted(
        NON_BLOCKING_TARGETS
    ):
        target = QUALITY_TARGETS[
            name
        ]

        score = dimensions[
            name
        ]

        if score < target:
            advisory_dimensions.append({
                "dimension":
                    name,

                "score":
                    score,

                "quality_target":
                    target,
            })

    severe_failures = []

    for name, floor in (
        SEVERE_FLOORS.items()
    ):
        score = dimensions[
            name
        ]

        if score < floor:
            severe_failures.append({
                "dimension":
                    name,

                "score":
                    score,

                "severe_floor":
                    floor,
            })

    v21_details = audit.get(
        "details",
        {},
    )

    credibility = v21_details.get(
        "credibility",
        {},
    )

    provenance_leaks = credibility.get(
        "visible_provenance_leaks",
        [],
    )

    hard_fail_reasons = []

    if provenance_leaks:
        hard_fail_reasons.append(
            "INTERNAL_PROVENANCE_LANGUAGE_VISIBLE"
        )

    structural_score = result.get(
        "structural_sameness_score",
        100.0,
    )

    if structural_score < 45.0:
        hard_fail_reasons.append(
            "SEVERE_STRUCTURAL_AI_SAMENESS"
        )

    for failure in severe_failures:
        hard_fail_reasons.append(
            (
                failure[
                    "dimension"
                ].upper()
                + ":SEVERE_BELOW_"
                + str(
                    int(
                        failure[
                            "severe_floor"
                        ]
                    )
                )
            )
        )

    weak = classify_extremely_weak(
        result.get(
            "human_fail_reasons",
            [],
        )
    )

    if weak[
        "severe"
    ]:
        hard_fail_reasons.append(
            "SEVERE_WEAK_EVIDENCE:"
            + ",".join(
                weak[
                    "locations"
                ]
            )
        )

    hard_fail_reasons = list(
        dict.fromkeys(
            hard_fail_reasons
        )
    )

    warning_reasons = []

    severe_names = {
        row[
            "dimension"
        ]
        for row in severe_failures
    }

    for row in warning_dimensions:
        if row[
            "dimension"
        ] in severe_names:
            continue

        warning_reasons.append(
            (
                row[
                    "dimension"
                ].upper()
                + ":BELOW_QUALITY_TARGET_"
                + str(
                    int(
                        row[
                            "quality_target"
                        ]
                    )
                )
            )
        )

    if (
        weak[
            "locations"
        ]
        and not weak[
            "severe"
        ]
    ):
        warning_reasons.append(
            "WEAK_BULLET_WARNING:"
            + ",".join(
                weak[
                    "locations"
                ]
            )
        )

    warning_reasons = list(
        dict.fromkeys(
            warning_reasons
        )
    )

    score = result[
        "score"
    ]

    below_overall_threshold = (
        score < PASS_THRESHOLD
    )

    quality_gate = (
        "FAIL"
        if (
            below_overall_threshold
            or hard_fail_reasons
        )
        else "PASS"
    )

    if quality_gate == "FAIL":
        quality_status = "FAIL"

    elif (
        warning_reasons
        or advisory_dimensions
    ):
        quality_status = (
            "PASS_WITH_WARNINGS"
        )

    else:
        quality_status = "PASS"

    upstream_blockers = list(
        result.get(
            "upstream_blockers",
            [],
        )
    )

    release_eligible = (
        quality_gate == "PASS"
        and not upstream_blockers
    )

    calibrated = dict(
        result
    )

    calibrated.update({
        "schema_version":
            "careerops-human-gate-v2.2",

        "gate":
            quality_gate,

        "quality_gate":
            quality_gate,

        "quality_status":
            quality_status,

        "threshold":
            PASS_THRESHOLD,

        "release_eligible":
            release_eligible,

        "upstream_blockers":
            upstream_blockers,

        "quality_targets":
            QUALITY_TARGETS,

        "severe_floors":
            SEVERE_FLOORS,

        "hard_floors":
            SEVERE_FLOORS,

        "hard_fail_reasons":
            hard_fail_reasons,

        "human_fail_reasons":
            hard_fail_reasons,

        "warning_reasons":
            warning_reasons,

        "warning_dimensions":
            warning_dimensions,

        "advisory_dimensions":
            advisory_dimensions,

        "severe_failures":
            severe_failures,

        "below_overall_threshold":
            below_overall_threshold,

        "weak_dimensions":
            [
                row[
                    "dimension"
                ]
                for row
                in warning_dimensions
            ],

        "calibration_policy":
            {
                "overall_score_below_85_blocks":
                    True,

                "severe_quality_defects_block":
                    True,

                "moderate_quality_misses_warn":
                    True,

                "quantified_impact_is_advisory":
                    True,

                "differentiation_is_advisory":
                    True,

                "ats_truth_remain_upstream":
                    True,

                "market_research_is_design_prior_not_rejection_model":
                    True,

                "real_recruiter_rejection_probability_claimed":
                    False,
            },
    })

    calibrated_audit = dict(
        audit
    )

    calibrated_audit.update({
        "schema_version":
            "careerops-human-audit-v2.2",

        "quality_gate":
            quality_gate,

        "quality_status":
            quality_status,

        "release_eligible":
            release_eligible,

        "upstream_blockers":
            upstream_blockers,

        "quality_targets":
            QUALITY_TARGETS,

        "severe_floors":
            SEVERE_FLOORS,

        "hard_fail_reasons":
            hard_fail_reasons,

        "warning_reasons":
            warning_reasons,

        "warning_dimensions":
            warning_dimensions,

        "advisory_dimensions":
            advisory_dimensions,

        "severe_failures":
            severe_failures,

        "extremely_weak_evidence":
            weak,

        "below_overall_threshold":
            below_overall_threshold,

        "calibration_policy":
            calibrated[
                "calibration_policy"
            ],

        "model_calls":
            0,
    })

    return (
        calibrated,
        calibrated_audit,
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
    result, audit = (
        v21.evaluate(
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
    )

    from careerops_writing_mechanics import profile
    prose = [resume.get('summary','')] + [str(b) for e in resume.get('experience',[]) for b in e.get('bullets',[])] + [str(b) for e in resume.get('projects',[]) for b in e.get('bullets',[])]
    mechanics = profile(prose)
    # Mechanics belongs to the locked natural-language dimension. Applying
    # its entire 0-100 penalty to the total score double-counted repetition
    # already measured by redundancy and gave syntax more weight than truth.
    old_natural = result['dimensions']['natural_language']
    result['dimensions']['natural_language'] = min(old_natural, mechanics['score'])
    mechanics_weight = audit.get('weights', {}).get('natural_language', 0.05)
    weighted_penalty = (old_natural - result['dimensions']['natural_language']) * mechanics_weight
    result['score'] = round(max(0,result['score'] - weighted_penalty),2)
    audit['dimensions']['natural_language'] = result['dimensions']['natural_language']
    mechanics['overall_weighted_penalty'] = round(weighted_penalty,4)
    mechanics['scoring_dimension'] = 'natural_language'

    result['writing_mechanics'] = mechanics
    audit.setdefault('details',{})['writing_mechanics'] = mechanics
    audit['overall_after_writing_mechanics'] = result['score']
    result, audit = calibrate(result, audit)
    if skills.get("skills_stack_contract"):
        from careerops_skills_stack import audit_stack
        stack_audit = audit_stack(resume.get("skills", []), skills["skills_stack_contract"])
        result["skills_stack_audit"] = stack_audit
        audit.setdefault("details", {})["skills_stack_audit"] = stack_audit
        if stack_audit["gate"] != "PASS":
            result.update(gate="FAIL", quality_gate="FAIL", quality_status="SKILLS_STACK_FAIL", release_eligible=False)
            audit.update(quality_gate="FAIL", quality_status="SKILLS_STACK_FAIL", release_eligible=False)
            result.setdefault("hard_fail_reasons", []).append("SKILLS_STACK_QUALITY")
            audit.setdefault("hard_fail_reasons", []).append("SKILLS_STACK_QUALITY")
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
    print("HUMAN GATE V2.2")
    print("=" * 96)

    print(
        "QUALITY GATE:",
        result[
            "quality_gate"
        ],
    )

    print(
        "QUALITY STATUS:",
        result[
            "quality_status"
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
    print(
        "HARD FAIL REASONS:",
        result[
            "hard_fail_reasons"
        ]
        or "NONE",
    )

    print(
        "WARNINGS:",
        result[
            "warning_reasons"
        ]
        or "NONE",
    )

    print(
        "ADVISORIES:",
        [
            row[
                "dimension"
            ]
            for row in result[
                "advisory_dimensions"
            ]
        ]
        or "NONE",
    )

    print()
    print("DIMENSIONS")

    for name in (
        LOCKED_DIMENSIONS
    ):
        target = (
            QUALITY_TARGETS[
                name
            ]
        )

        severe = (
            SEVERE_FLOORS.get(
                name
            )
        )

        print(
            f"  {name}: "
            f"{result['dimensions'][name]:.2f} "
            f"| target={target:.2f} "
            f"| severe="
            f"{severe if severe is not None else 'ADVISORY_ONLY'}"
        )

    print()
    print(
        "MODEL CALLS: 0"
    )


if __name__ == "__main__":
    from careerops_requirement_authority import run_guarded
    run_guarded(main,RUNTIME,'careerops_human_gate_v22.py')
