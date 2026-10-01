#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import re
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(
        name,
        path,
    )

    module = importlib.util.module_from_spec(
        spec
    )

    spec.loader.exec_module(
        module
    )

    return module


base_probe = load_module(
    "li4_base_probe",
    SCRIPTS / "careerops_li_semantic_probe.py",
)

rag_context = load_module(
    "li4_rag_context",
    SCRIPTS / "careerops_li_rag_context.py",
)

rag_probe = load_module(
    "li4_rag_probe",
    SCRIPTS / "careerops_li_semantic_probe_rag.py",
)

hybrid = load_module(
    "li4_hybrid",
    SCRIPTS / "careerops_li_hybrid_shadow.py",
)

validator = load_module(
    "li4_validator",
    SCRIPTS / "careerops_validate_li_shadow.py",
)

grounding = load_module(
    "li4_grounding",
    SCRIPTS / "careerops_li_grounding_gate_v2.py",
)

disagreement = load_module(
    "li4_disagreement",
    SCRIPTS / "careerops_li_disagreement.py",
)


RISK_STATUS_TERMS = {
    "NEEDS_ATTENTION",
    "UNRESOLVED",
    "AMBIGUOUS",
    "CONFLICT",
    "PARTIAL",
    "REVIEW",
    "INCOMPLETE",
}


def norm(value):
    return re.sub(
        r"\s+",
        " ",
        str(value or ""),
    ).strip()


def walk(value, path="$"):
    if isinstance(
        value,
        dict,
    ):
        for key, child in value.items():
            child_path = (
                path
                + "."
                + str(key)
            )

            yield (
                child_path,
                child,
            )

            yield from walk(
                child,
                child_path,
            )

    elif isinstance(
        value,
        list,
    ):
        for index, child in enumerate(
            value
        ):
            child_path = (
                path
                + "["
                + str(index)
                + "]"
            )

            yield (
                child_path,
                child,
            )

            yield from walk(
                child,
                child_path,
            )


def meaningful_truthy(value):
    if value is True:
        return True

    if isinstance(
        value,
        (int, float),
    ):
        return bool(value)

    if isinstance(
        value,
        str,
    ):
        text = value.strip().upper()

        return text not in {
            "",
            "NONE",
            "NULL",
            "FALSE",
            "NO",
            "PASS",
            "OK",
            "COMPLETE",
            "COMPLETE_HIGH",
        }

    if isinstance(
        value,
        (list, dict),
    ):
        return bool(value)

    return False


def deterministic_risk_signals(
    deterministic,
):
    reasons = []

    for path, value in walk(
        deterministic
    ):
        path_lower = path.casefold()

        if isinstance(
            value,
            str,
        ):
            upper = value.strip().upper()

            leaf_key = path_lower.rsplit(".", 1)[-1]

            if (
                (
                    leaf_key == "status"
                    or leaf_key.endswith("_status")
                )
                and any(
                    term in upper
                    for term in RISK_STATUS_TERMS
                )
            ):
                reasons.append(
                    "STATE_STATUS:"
                    + path
                    + "="
                    + upper
                )

        if any(
            token in path_lower
            for token in (
                "ambigu",
                "conflict",
                "unresolved",
                "integrity_warning",
                "source_warning",
                "identity_warning",
            )
        ):
            if meaningful_truthy(
                value
            ):
                reasons.append(
                    "STATE_SIGNAL:"
                    + path
                )

    return sorted(
        set(
            reasons
        )
    )


def identity_risk_signals(
    raw_source,
    deterministic,
):
    reasons = []

    source_identity = (
        hybrid.header_identity(
            raw_source
        )
    )

    deterministic_identity = (
        hybrid.deterministic_identity(
            deterministic
        )
    )

    for field in (
        "employer_name",
        "job_title",
        "requisition_id",
    ):
        source_value = (
            source_identity.get(
                field
            )
        )

        deterministic_value = (
            deterministic_identity.get(
                field
            )
        )

        if (
            source_value
            and deterministic_value
            and norm(
                source_value
            ).casefold()
            != norm(
                deterministic_value
            ).casefold()
        ):
            reasons.append(
                "IDENTITY_CONFLICT:"
                + field
            )

        elif (
            source_value
            and not deterministic_value
            and field
            in {
                "employer_name",
                "job_title",
            }
        ):
            reasons.append(
                "IDENTITY_MISSING:"
                + field
            )

    return reasons


def extraction_risk_signals(
    raw_source,
    deterministic,
):
    reasons = []

    source_len = len(
        str(
            raw_source
            or ""
        )
    )

    requirement_count = len(
        hybrid.deterministic_requirements(
            deterministic
        )
    )

    if (
        source_len >= 3500
        and requirement_count <= 2
    ):
        reasons.append(
            "LARGE_SOURCE_LOW_REQUIREMENT_COUNT"
        )

    return reasons


def route(
    raw_source,
    deterministic,
):
    reasons = []

    reasons.extend(
        deterministic_risk_signals(
            deterministic
        )
    )

    reasons.extend(
        identity_risk_signals(
            raw_source,
            deterministic,
        )
    )

    reasons.extend(
        extraction_risk_signals(
            raw_source,
            deterministic,
        )
    )

    reasons = sorted(
        set(
            reasons
        )
    )

    mode = (
        "BM25_RAG"
        if reasons
        else
        "NO_RAG"
    )

    return {
        "mode":
            mode,

        "reasons":
            reasons,

        "policy":
            "CONDITIONAL_RAG_ONLY",

        "chosen_before_model_call":
            True,
    }


def unavailable(
    *,
    routing,
    attempted_calls,
    error,
    elapsed,
):
    return {
        "schema_version":
            "career-ops-li4-advisory-run-v1",

        "status":
            "SHADOW_UNAVAILABLE",

        "authority":
            "ADVISORY_ONLY",

        "may_override":
            False,

        "production_decision_effect":
            "NONE",

        "continue_deterministic_engine":
            True,

        "review_required":
            False,

        "routing":
            routing,

        "local_model_calls":
            attempted_calls,

        "elapsed_seconds":
            round(
                elapsed,
                3,
            ),

        "shadow":
            None,

        "disagreement":
            None,

        "error":
            error,
    }


def run(
    raw_source,
    deterministic,
    *,
    timeout=90,
    no_rag_call=None,
    rag_call=None,
):
    started = time.perf_counter()

    routing = route(
        raw_source,
        deterministic,
    )

    attempted_calls = 0
    retrieval = None

    try:
        if routing[
            "mode"
        ] == "BM25_RAG":
            retrieval = (
                rag_context.build_context(
                    raw_source,
                    deterministic,
                    gold_top_k=4,
                    failure_top_k=2,
                )
            )

            caller = (
                rag_call
                or rag_probe.call_probe_rag
            )

            attempted_calls = 1

            probe = caller(
                raw_source,
                deterministic,
                retrieval[
                    "results"
                ],
                timeout=timeout,
            )

        else:
            caller = (
                no_rag_call
                or base_probe.call_probe
            )

            attempted_calls = 1

            probe = caller(
                raw_source,
                deterministic,
                timeout=timeout,
            )

    except Exception as exc:
        return unavailable(
            routing=routing,
            attempted_calls=attempted_calls,
            error=repr(exc),
            elapsed=(
                time.perf_counter()
                - started
            ),
        )

    try:
        shadow = hybrid.assemble(
            raw_source,
            deterministic,
            probe,
        )

        if retrieval is not None:
            shadow[
                "retrieval_context"
            ] = retrieval[
                "results"
            ]

            shadow.setdefault(
                "model_metadata",
                {},
            )[
                "rag_backend"
            ] = "DETERMINISTIC_BM25"

        structural_errors = (
            validator.validate(
                shadow
            )
        )

        grounding_errors = (
            grounding.validate(
                raw_source,
                deterministic,
                shadow,
            )
        )

    except Exception as exc:
        return unavailable(
            routing=routing,
            attempted_calls=attempted_calls,
            error=(
                "SHADOW_ASSEMBLY_OR_VALIDATION:"
                + repr(exc)
            ),
            elapsed=(
                time.perf_counter()
                - started
            ),
        )

    if (
        structural_errors
        or grounding_errors
    ):
        return {
            "schema_version":
                "career-ops-li4-advisory-run-v1",

            "status":
                "SHADOW_INVALID",

            "authority":
                "ADVISORY_ONLY",

            "may_override":
                False,

            "production_decision_effect":
                "NONE",

            "continue_deterministic_engine":
                True,

            "review_required":
                False,

            "routing":
                routing,

            "local_model_calls":
                attempted_calls,

            "elapsed_seconds":
                round(
                    time.perf_counter()
                    - started,
                    3,
                ),

            "shadow":
                shadow,

            "structural_errors":
                structural_errors,

            "grounding_errors":
                grounding_errors,

            "disagreement":
                None,
        }

    try:
        disagree = disagreement.compare(
            deterministic,
            shadow,
        )

    except Exception as exc:
        return unavailable(
            routing=routing,
            attempted_calls=attempted_calls,
            error=(
                "DISAGREEMENT_ENGINE:"
                + repr(exc)
            ),
            elapsed=(
                time.perf_counter()
                - started
            ),
        )

    return {
        "schema_version":
            "career-ops-li4-advisory-run-v1",

        "status":
            "AVAILABLE",

        "authority":
            "ADVISORY_ONLY",

        "may_override":
            False,

        "production_decision_effect":
            "NONE",

        "continue_deterministic_engine":
            True,

        "review_required":
            bool(
                disagree.get(
                    "review_required"
                )
            ),

        "routing":
            routing,

        "local_model_calls":
            attempted_calls,

        "elapsed_seconds":
            round(
                time.perf_counter()
                - started,
                3,
            ),

        "shadow":
            shadow,

        "structural_errors":
            [],

        "grounding_errors":
            [],

        "disagreement":
            disagree,
    }


if __name__ == "__main__":
    raise SystemExit(
        "Import run() from CareerOps LI-4."
    )
