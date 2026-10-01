from __future__ import annotations

import hashlib
import json
from typing import Any

from careerops_intelligence_contracts import (
    SCHEMA_ARBITRATION_CASE,
    SCHEMA_ARBITRATION_BATCH,
    validate_arbitration_case,
)


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def qwen_state(result):
    if not isinstance(result, dict):
        return "NOT_RUN", False

    status = str(
        result.get(
            "status",
            result.get(
                "verdict",
                "UNKNOWN",
            ),
        )
        or "UNKNOWN"
    ).upper()

    return (
        status,
        bool(
            result.get(
                "grounding_valid",
                False,
            )
        ),
    )


def choose_route(failure_type, qwen_result=None):
    failure_type = str(
        failure_type or ""
    ).upper()

    if failure_type == "MECHANICAL":
        return "DETERMINISTIC_REPAIR"

    if failure_type == "RENDERER":
        return "RENDERER_REPAIR"

    if failure_type == "HARNESS":
        return "HARNESS_REPAIR"

    if failure_type == "HARD_CONFLICT":
        return "STOP_HARD_CONFLICT"

    if failure_type != "SEMANTIC":
        return "NEEDS_ATTENTION"

    status, grounded = qwen_state(
        qwen_result
    )

    if status == "NOT_RUN":
        return "LOCAL_QWEN"

    if (
        status
        in {
            "RESOLVED",
            "PROPOSE_CORRECTION",
        }
        and grounded
    ):
        return "DETERMINISTIC_RECONSTRUCTION"

    if (
        status
        in {
            "AGREE",
            "DETERMINISTIC_CORRECT",
        }
        and grounded
    ):
        return "DETERMINISTIC_RESULT_STANDS"

    return "SHARED_SOL_ADJUDICATION"


def build_case(payload):
    failure_type = str(
        payload.get(
            "failure_type",
            "",
        )
    ).upper()

    qwen_result = payload.get(
        "qwen_result"
    )

    route = choose_route(
        failure_type,
        qwen_result,
    )

    case = {
        "schema_version":
            SCHEMA_ARBITRATION_CASE,

        "case_id":
            str(
                payload.get("case_id")
                or canonical_hash(
                    {
                        "run_id":
                            payload.get("run_id"),

                        "stage":
                            payload.get("stage"),

                        "failure_code":
                            payload.get("failure_code"),

                        "source_hash":
                            payload.get("source_hash"),
                    }
                )[:20]
            ),

        "run_id":
            str(
                payload.get(
                    "run_id",
                    "",
                )
            ),

        "stage":
            str(
                payload.get(
                    "stage",
                    "",
                )
            ),

        "failure_type":
            failure_type,

        "failure_code":
            str(
                payload.get(
                    "failure_code",
                    "",
                )
            ),

        "source_hash":
            str(
                payload.get(
                    "source_hash",
                    "",
                )
            ),

        "source_spans":
            payload.get(
                "source_spans",
                [],
            )
            if isinstance(
                payload.get(
                    "source_spans",
                    [],
                ),
                list,
            )
            else [],

        "deterministic_state":
            payload.get(
                "deterministic_state",
                {},
            )
            if isinstance(
                payload.get(
                    "deterministic_state",
                    {},
                ),
                dict,
            )
            else {},

        "policy_context":
            payload.get(
                "policy_context",
                {},
            )
            if isinstance(
                payload.get(
                    "policy_context",
                    {},
                ),
                dict,
            )
            else {},

        "qwen_result":
            qwen_result
            if isinstance(
                qwen_result,
                dict,
            )
            else None,

        "route":
            route,

        "authority_contract": {
            "model_may_mutate_source":
                False,

            "model_may_create_candidate_facts":
                False,

            "model_may_waive_hard_blocker":
                False,

            "model_may_set_release_ready":
                False,

            "deterministic_revalidation_required":
                route
                in {
                    "DETERMINISTIC_RECONSTRUCTION",
                    "SHARED_SOL_ADJUDICATION",
                },
        },
    }

    errors = validate_arbitration_case(
        case
    )

    if errors:
        raise ValueError(
            "ARBITRATION_CASE_INVALID:"
            + ",".join(errors)
        )

    return case


def build_batch_packet(cases, common_policy):
    selected = [
        case
        for case in cases
        if case.get("route")
        == "SHARED_SOL_ADJUDICATION"
    ]

    return {
        "schema_version":
            SCHEMA_ARBITRATION_BATCH,

        "purpose":
            "UNRESOLVED_SEMANTIC_ADJUDICATION",

        "common_policy":
            common_policy,

        "common_policy_hash":
            canonical_hash(
                common_policy
            ),

        "case_count":
            len(selected),

        "cases":
            selected,

        "response_contract": {
            "allowed_verdicts": [
                "DETERMINISTIC_CORRECT",
                "PROPOSE_CORRECTION",
                "INCONCLUSIVE",
            ],

            "must_return_case_id":
                True,

            "must_cite_source_spans":
                True,

            "may_create_candidate_facts":
                False,

            "may_set_release_ready":
                False,

            "deterministic_revalidation_required":
                True,
        },
    }
