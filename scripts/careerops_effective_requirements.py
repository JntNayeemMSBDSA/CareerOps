#!/usr/bin/env python3

import argparse
import json
from pathlib import Path


SCHEMA_VERSION = (
    "career-ops-effective-requirements-v1"
)


def build_effective_view(
    ledger,
    sidecar,
):
    source_rows = (
        ledger.get(
            "requirements",
            [],
        )
        or []
    )

    annotations = (
        sidecar.get(
            "annotations",
            [],
        )
        or []
    )

    source_ids = [
        row.get(
            "requirement_id"
        )
        for row in source_rows
    ]

    annotation_ids = [
        row.get(
            "requirement_id"
        )
        for row in annotations
    ]

    problems = []

    if len(
        source_rows
    ) != len(
        annotations
    ):
        problems.append(
            "ANNOTATION_COUNT_MISMATCH"
        )

    if source_ids != annotation_ids:
        problems.append(
            "REQUIREMENT_ID_ORDER_MISMATCH"
        )

    unresolved = (
        sidecar.get(
            "unresolved_source_anchor_ids",
            [],
        )
        or []
    )

    ambiguous = (
        sidecar.get(
            "ambiguous_source_anchor_ids",
            [],
        )
        or []
    )

    if unresolved:
        problems.append(
            "UNRESOLVED_SOURCE_ALIGNMENT"
        )

    if ambiguous:
        problems.append(
            "AMBIGUOUS_SOURCE_ALIGNMENT"
        )

    annotation_index = {
        row.get(
            "requirement_id"
        ):
            row
        for row in annotations
    }

    effective = []

    for source in source_rows:
        requirement_id = source.get(
            "requirement_id"
        )

        semantic = annotation_index.get(
            requirement_id,
            {},
        )

        priority = source.get("priority")

        semantic_class = semantic.get(
            "semantic_class"
        )

        active = semantic.get(
            "active_for_decision",
            True,
        )
        if priority=="P0":active=True

        if semantic_class == "HARD_BLOCK":
            decision_role = (
                "EXPLICIT_HARD_BLOCKER_CANDIDATE"
            )

            constraint_validation = True

        elif (
            priority == "P0"
            and active
        ):
            decision_role = (
                "MANDATORY_CONSTRAINT_CANDIDATE"
            )

            constraint_validation = True

        elif priority == "P1":
            decision_role = "CORE_WORK"
            constraint_validation = False

        elif priority == "P2":
            decision_role = (
                "SUPPORTING_CAPABILITY"
            )

            constraint_validation = False

        elif priority == "P3":
            decision_role = "PREFERRED"
            constraint_validation = False

        else:
            decision_role = (
                "CONTEXT_OR_NON_DECISION"
            )

            constraint_validation = False

        effective.append(
            {
                "requirement_id":
                    requirement_id,

                "exact_quote":
                    source.get(
                        "exact_quote"
                    ),

                "source_priority":
                    source.get(
                        "priority"
                    ),

                "effective_priority":
                    priority,

                "semantic_class":
                    semantic_class,

                "modality":
                    semantic.get(
                        "modality"
                    ),

                "qualification_relation":
                    semantic.get(
                        "qualification_relation"
                    ),

                "active_for_decision":
                    active,

                "decision_role":
                    decision_role,

                "eligible_for_constraint_validation":
                    constraint_validation,

                "semantic_sidecar_can_auto_reject":
                    False,

                "source_section":
                    source.get(
                        "section"
                    ),

                "effective_source_section": source.get("section"),

                "source_section_basis":
                    semantic.get(
                        "source_section_basis"
                    ),

                "source_anchor_start_line":
                    semantic.get(
                        "source_anchor_start_line"
                    ),

                "source_anchor_end_line":
                    semantic.get(
                        "source_anchor_end_line"
                    ),

                "source_anchor_method":
                    semantic.get(
                        "source_anchor_method"
                    ),

                "source_anchor_confidence":
                    semantic.get(
                        "source_anchor_confidence"
                    ),

                "semantic_reason_codes":
                    semantic.get(
                        "reason_codes"
                    )
                    or [],

                "source_fields":
                    source,
            }
        )

    return {
        "schema_version":
            SCHEMA_VERSION,

        "mode":
            "SHADOW_ONLY",

        "status":
            (
                "PASS"
                if not problems
                else "NEEDS_ATTENTION"
            ),

        "problems":
            problems,

        "source_requirement_count":
            len(
                source_rows
            ),

        "effective_requirement_count":
            len(
                effective
            ),

        "target_role_title_candidate":
            ledger.get(
                "target_role_title_candidate"
            ),

        "policy": {
            "source_ledger_immutable":
                True,

            "stable_requirement_ids_preserved":
                True,

            "one_effective_row_per_source_requirement":
                True,

            "semantic_sidecar_cannot_authorize_rejection":
                True,

            "P0_requires_deterministic_constraint_validation":
                True,

            "P2_is_active_for_tailoring_but_not_auto_rejection":
                True,

            "uncertainty_is_needs_attention_not_rejected":
                True,
        },

        "requirements":
            effective,
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--requirements",
        required=True,
    )

    parser.add_argument(
        "--sidecar",
        required=True,
    )

    parser.add_argument(
        "--output",
        required=True,
    )

    args = parser.parse_args()

    ledger = json.loads(
        Path(
            args.requirements
        ).read_text(
            encoding="utf-8"
        )
    )

    sidecar = json.loads(
        Path(
            args.sidecar
        ).read_text(
            encoding="utf-8"
        )
    )

    result = build_effective_view(
        ledger,
        sidecar,
    )

    output = Path(
        args.output
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.write_text(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        "EFFECTIVE REQUIREMENT VIEW:",
        result[
            "status"
        ],
    )

    print(
        "source_count=",
        result[
            "source_requirement_count"
        ],
    )

    print(
        "effective_count=",
        result[
            "effective_requirement_count"
        ],
    )

    print(
        "problems=",
        result[
            "problems"
        ],
    )


if __name__ == "__main__":
    main()
