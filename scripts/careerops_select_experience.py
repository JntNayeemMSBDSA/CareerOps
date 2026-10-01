from careerops_config import experience_blocks, load_facts
#!/usr/bin/env python3

import json
from pathlib import Path


from careerops_runtime import runtime_dir

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = runtime_dir(ROOT)

EVIDENCE_MAP_PATH = (
    RUNTIME / 'requirement_evidence_map.json'
)

CONSTRAINT_PATH = (
    RUNTIME / 'constraint_validation.json'
)

ENTITIES_PATH = (
    RUNTIME / 'candidate_entities.json'
)

OUT = (
    RUNTIME / 'experience_selection.json'
)


PRIORITY_WEIGHT = {
    "P0": 5.0,
    "P1": 4.0,
    "P2": 2.0,
    "P3": 1.0
}


# Canonical Professional Experience structure.
#
# Multiple evidence entities may support ONE employment block
# without those entities being merged.
EXPERIENCE_BLOCKS = experience_blocks(ROOT)


ALTERNATE_ALTERNATE = load_facts(ROOT).get("alternate_experience_block")


def constraint_lookup(payload):
    return {
        row["requirement_id"]: row["overall_status"]
        for row in payload.get("requirements", [])
    }


def evidence_lookup(requirement):
    return {
        candidate["entity_id"]: candidate
        for candidate in requirement.get(
            "verified_evidence_candidates",
            []
        )
        if candidate.get('requirement_coverage', 'SUPPORTED') == 'SUPPORTED'
    }


def evaluate_block(block, requirements):
    contributions = []

    total_score = 0.0

    supported = set()

    supported_p0_p1 = set()

    for req in requirements:
        candidates = evidence_lookup(req)

        matches = [
            candidates[evidence_id]
            for evidence_id in block["evidence_ids"]
            if evidence_id in candidates
        ]

        if not matches:
            continue

        best = max(
            matches,
            key=lambda x: x["score"]
        )

        weighted = (
            best["score"]
            * PRIORITY_WEIGHT.get(
                req["priority"],
                1.0
            )
        )

        total_score += weighted

        supported.add(
            req["requirement_id"]
        )

        if req["priority"] in {
            "P0",
            "P1"
        }:
            supported_p0_p1.add(
                req["requirement_id"]
            )

        contributions.append({
            "requirement_id": req[
                "requirement_id"
            ],
            "priority": req[
                "priority"
            ],
            "evidence_id": best[
                "entity_id"
            ],
            "evidence_score": best[
                "score"
            ],
            "weighted_selection_score": round(
                weighted,
                2
            ),
            "exact_tool_matches": best.get(
                "verified_exact_tool_matches",
                []
            ),
            "exact_term_matches": best.get(
                "verified_exact_term_matches",
                []
            ),
            "semantic_matches": best.get(
                "verified_semantic_term_matches",
                []
            ),
            "technical_depth_matches": best.get(
                "verified_technical_depth_matches",
                []
            )
        })

    return {
        **block,

        "selection_score": round(
            total_score,
            2
        ),

        "supported_requirement_ids": sorted(
            supported
        ),

        "supported_p0_p1_ids": sorted(
            supported_p0_p1
        ),

        "requirement_contributions": contributions,

        "source_entities_remain_distinct": True
    }


def main():
    for path in [
        EVIDENCE_MAP_PATH,
        CONSTRAINT_PATH,
        ENTITIES_PATH
    ]:
        if not path.exists():
            raise SystemExit(
                f"Missing required source: {path}"
            )

    evidence_map = json.loads(
        EVIDENCE_MAP_PATH.read_text()
    )

    constraints = json.loads(
        CONSTRAINT_PATH.read_text()
    )

    entities_payload = json.loads(
        ENTITIES_PATH.read_text()
    )

    canonical_entity_ids = {
        e["entity_id"]
        for e in entities_payload[
            "entities"
        ]
    }

    all_block_ids = set()

    for block in (
        EXPERIENCE_BLOCKS
        + ([ALTERNATE_ALTERNATE] if ALTERNATE_ALTERNATE else [])
    ):
        all_block_ids.update(
            block["evidence_ids"]
        )

    missing_entities = (
        all_block_ids
        - canonical_entity_ids
    )

    if missing_entities:
        raise SystemExit(
            "Experience block references unknown "
            "canonical entities: "
            + ", ".join(
                sorted(missing_entities)
            )
        )

    requirements = evidence_map[
        "requirements"
    ]

    constraint_status = constraint_lookup(
        constraints
    )

    evaluated = [
        evaluate_block(
            block,
            requirements
        )
        for block in EXPERIENCE_BLOCKS
    ]

    alternate = evaluate_block(ALTERNATE_ALTERNATE, requirements) if ALTERNATE_ALTERNATE else {"supported_p0_p1_ids": []}

    # --------------------------------------------------
    # Alternate replacement rule
    #
    # Alternate may replace the last default experience only
    # if it adds real P0/P1 requirement coverage that
    # the last default block does not provide.
    # --------------------------------------------------

    last = evaluated[-1]

    covered_by_preceding = set().union(*(set(x['supported_p0_p1_ids']) for x in evaluated[:-1]))
    default_coverage = covered_by_preceding | set(last['supported_p0_p1_ids'])
    alternate_coverage = covered_by_preceding | set(alternate['supported_p0_p1_ids'])
    alternate_extra_p0_p1 = alternate_coverage - default_coverage
    last_lost_p0_p1 = default_coverage - alternate_coverage

    priorities={x['requirement_id']:x['priority'] for x in requirements}
    def priority_coverage(ids):return tuple(sum(priorities.get(x)==priority for x in ids) for priority in ['P0','P1'])
    use_alternate = bool(ALTERNATE_ALTERNATE and alternate_extra_p0_p1 and priority_coverage(alternate_coverage)>priority_coverage(default_coverage))

    if use_alternate:
        selected = (
            evaluated[:-1]
            + [alternate]
        )

        alternate_decision = {
            "alternate_selected": True,
            "reason": (
                "Alternate materially adds P0/P1 "
                "coverage over the last "
                "default experience block."
            ),
            "added_p0_p1": sorted(
                alternate_extra_p0_p1
            ),
            "lost_p0_p1": sorted(
                last_lost_p0_p1
            )
        }

    else:
        selected = evaluated

        alternate_decision = {
            "alternate_selected": False,
            "reason": (
                "Alternate does not materially improve "
                "P0/P1 coverage over the canonical "
                "last experience block."
            ),
            "added_p0_p1": sorted(
                alternate_extra_p0_p1
            ),
            "lost_p0_p1": sorted(
                last_lost_p0_p1
            )
        }

    selected_evidence_ids = {
        entity_id
        for block in selected
        for entity_id in block[
            "evidence_ids"
        ]
    }

    # --------------------------------------------------
    # Experience-stage requirement coverage
    # --------------------------------------------------

    requirement_results = []

    residual_project_targets = []
    unresolved_constraints = []

    for req in requirements:

        candidates = evidence_lookup(
            req
        )

        experience_matches = [
            candidates[evidence_id]
            for evidence_id
            in selected_evidence_ids
            if evidence_id in candidates
        ]

        experience_supported = bool(
            experience_matches
        )

        constraint = constraint_status.get(
            req["requirement_id"]
        )

        #
        # The constraint validator is authoritative for whether this
        # requisition requirement has a factual/eligibility constraint.
        # Legacy semantic metadata remains supported, but a validator
        # result must never be ignored merely because a newer constraint
        # class (for example sponsorship/citizenship/clearance) was not
        # represented by the old semantic flag.
        has_constraint = bool(
            req.get(
                "constraint_validation_required",
                False
            )
            or constraint is not None
        )

        # Education-only requirement can be satisfied
        # entirely by the hard-constraint validator.
        if (
            has_constraint
            and constraint == "PASS"
            and not candidates
        ):
            stage_status = (
                "COVERED_BY_CANDIDATE_FACT"
            )

        # Requirement contains both a factual constraint
        # and skill/work evidence.
        elif (
            has_constraint
            and constraint == "PASS"
            and experience_supported
        ):
            stage_status = (
                "COVERED_BY_EXPERIENCE_AND_CANDIDATE_FACT"
            )

        #
        # P0 is the mandatory tier. A factual constraint that is not
        # verified at P0 must block the writer. P1/P2/P3 constraints
        # remain visible for audit/scoring but are not falsely promoted
        # into PRE-WRITER hard blockers.
        elif (
            has_constraint
            and constraint != "PASS"
            and req["priority"] == "P0"
        ):
            stage_status = (
                "UNRESOLVED_HARD_CONSTRAINT"
            )

            unresolved_constraints.append(
                req["requirement_id"]
            )

        elif (
            has_constraint
            and constraint != "PASS"
        ):
            stage_status = (
                "NON_MANDATORY_CONSTRAINT_NOT_VERIFIED"
            )

        elif experience_supported:
            stage_status = (
                "COVERED_BY_EXPERIENCE"
            )

        else:
            stage_status = (
                "RESIDUAL_GAP_FOR_PROJECT_SELECTION"
            )

            residual_project_targets.append(
                req["requirement_id"]
            )

        requirement_results.append({
            "requirement_id": req[
                "requirement_id"
            ],
            "priority": req[
                "priority"
            ],
            "exact_jd_quote": req[
                "exact_jd_quote"
            ],
            "constraint_status": constraint,
            "experience_supported": (
                experience_supported
            ),
            "supporting_experience_evidence_ids": [
                x["entity_id"]
                for x in experience_matches
            ],
            "experience_stage_status": (
                stage_status
            )
        })

    selected_p0_p1 = {
        requirement_id
        for block in selected
        for requirement_id
        in block[
            "supported_p0_p1_ids"
        ]
    }

    all_p0_p1 = {
        req["requirement_id"]
        for req in requirements
        if req["priority"] in {
            "P0",
            "P1"
        }
    }

    output = {
        "schema_version": (
            "experience-selection-v1"
        ),

        "policy": {
            "experience_selected_before_projects": True,
            "canonical_four_experiences_are_default": True,
            "alternate_may_only_replace_last": True,
            "alternate_requires_material_p0_p1_gain": True,
            "source_evidence_entities_remain_distinct": True,
            "project_entities_not_selected_here": True,
            "hard_constraints_use_constraint_validator": True,
            "hard_constraint_priorities": ["P0"],
            "non_p0_constraint_failures_are_advisory": True
        },

        "selected_experience_blocks": selected,

        "alternate_alternate": {
            **alternate,
            "decision": alternate_decision
        },

        "p0_p1": {
            "all_requirement_ids": sorted(
                all_p0_p1
            ),
            "experience_supported_ids": sorted(
                selected_p0_p1
            )
        },

        "requirement_coverage": (
            requirement_results
        ),

        "residual_gaps": {
            "project_fill_target_ids": (
                residual_project_targets
            ),
            "unresolved_hard_constraint_ids": (
                unresolved_constraints
            )
        }
    }

    OUT.write_text(
        json.dumps(
            output,
            indent=2,
            ensure_ascii=False
        )
        + "\n"
    )

    print("EXPERIENCE SELECTION: CREATED")

    print("\nSELECTED EXPERIENCE:")

    for i, block in enumerate(
        selected,
        start=1
    ):
        print(
            f"{i}. {block['organization']} | "
            f"{block['title']} | "
            f"{block['period']}"
        )

        print(
            "   EVIDENCE:",
            ", ".join(
                block["evidence_ids"]
            )
        )

        print(
            "   SCORE:",
            block["selection_score"]
        )

        print(
            "   SUPPORT:",
            ", ".join(
                block[
                    "supported_requirement_ids"
                ]
            )
            or "NONE"
        )

    print(
        "\nALTERNATE SELECTED:",
        alternate_decision[
            "alternate_selected"
        ]
    )

    print("\nREQUIREMENT COVERAGE:")

    for row in requirement_results:
        print(
            f"  {row['requirement_id']} "
            f"{row['priority']} => "
            f"{row['experience_stage_status']}"
        )

    print(
        "\nPROJECT FILL TARGETS:",
        ", ".join(
            residual_project_targets
        )
        or "NONE"
    )

    print(
        "UNRESOLVED HARD CONSTRAINTS:",
        ", ".join(
            unresolved_constraints
        )
        or "NONE"
    )

    print(
        "\nOUTPUT:",
        OUT.relative_to(ROOT)
    )


if __name__ == "__main__":
    from careerops_requirement_authority import run_guarded
    run_guarded(main, RUNTIME, "careerops_select_experience.py")
