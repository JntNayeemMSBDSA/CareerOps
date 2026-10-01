#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path


FORBIDDEN_KEYS = {
    "final_decision",
    "job_decision",
    "eligibility_decision",
    "release_decision",
    "authorize_rejection",
    "authorize_release",
    "candidate_fact_update",
}


VALID_REQUIREMENT_TYPES = {
    "REQUIRED",
    "PREFERRED",
    "RESPONSIBILITY",
    "CONTEXT",
    "SUBSTITUTION",
    "EQUIVALENT",
    "HARD_BLOCK",
    "POSSIBLE_MISSED_REQUIREMENT",
    "POSSIBLE_FALSE_REQUIREMENT",
}


VALID_PRIORITIES = {
    "P0",
    "P1",
    "P2",
    "P3",
    None,
}


VALID_RELATIONS = {
    "AND",
    "OR",
    "SUBSTITUTION",
    "EQUIVALENT",
    "NONE",
    None,
}


def recursive_keys(value):
    keys = set()

    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(str(key).casefold())
            keys.update(recursive_keys(child))

    elif isinstance(value, list):
        for child in value:
            keys.update(recursive_keys(child))

    return keys


def validate_span(row, prefix, errors):
    quote = row.get("exact_source_quote")

    if (
        not isinstance(quote, str)
        or not quote.strip()
    ):
        errors.append(
            prefix + "EXACT_SOURCE_QUOTE_REQUIRED"
        )

    start = row.get("start_line")
    end = row.get("end_line")

    if (
        not isinstance(start, int)
        or not isinstance(end, int)
        or start < 1
        or end < start
    ):
        errors.append(
            prefix + "VALID_SOURCE_LINE_RANGE_REQUIRED"
        )

    confidence = row.get("confidence")

    if (
        not isinstance(confidence, (int, float))
        or confidence < 0
        or confidence > 1
    ):
        errors.append(
            prefix + "CONFIDENCE_OUT_OF_RANGE"
        )


def validate(obj):
    errors = []

    if not isinstance(obj, dict):
        return ["TOP_LEVEL_MUST_BE_OBJECT"]

    if obj.get("schema_version") != "career-ops-li-shadow-output-v1":
        errors.append("BAD_SCHEMA_VERSION")

    if obj.get("authority") != "ADVISORY_ONLY":
        errors.append("AUTHORITY_MUST_BE_ADVISORY_ONLY")

    if obj.get("may_override") is not False:
        errors.append("MAY_OVERRIDE_MUST_BE_FALSE")

    if not isinstance(
        obj.get("source_fingerprint"),
        str,
    ):
        errors.append("SOURCE_FINGERPRINT_REQUIRED")

    keys = recursive_keys(obj)

    for forbidden in sorted(FORBIDDEN_KEYS):
        if forbidden.casefold() in keys:
            errors.append(
                "FORBIDDEN_AUTHORITY_FIELD:"
                + forbidden
            )

    identity = obj.get("identity")

    if not isinstance(identity, dict):
        errors.append("IDENTITY_MUST_BE_OBJECT")
        identity = {}

    confidence = identity.get(
        "current_posting_confidence"
    )

    if confidence is not None:
        if (
            not isinstance(confidence, (int, float))
            or confidence < 0
            or confidence > 1
        ):
            errors.append(
                "IDENTITY_CONFIDENCE_OUT_OF_RANGE"
            )

    observations = identity.get(
        "observations",
        [],
    )

    if not isinstance(observations, list):
        errors.append(
            "IDENTITY_OBSERVATIONS_MUST_BE_LIST"
        )
        observations = []

    for i, row in enumerate(observations):
        if not isinstance(row, dict):
            errors.append(
                f"IDENTITY_{i}:NOT_OBJECT"
            )
            continue

        validate_span(
            row,
            f"IDENTITY_{i}:",
            errors,
        )

    boundaries = obj.get("boundaries")

    if not isinstance(boundaries, list):
        errors.append("BOUNDARIES_MUST_BE_LIST")
        boundaries = []

    for i, row in enumerate(boundaries):
        if not isinstance(row, dict):
            errors.append(
                f"BOUNDARY_{i}:NOT_OBJECT"
            )
            continue

        validate_span(
            row,
            f"BOUNDARY_{i}:",
            errors,
        )

    requirements = obj.get("requirements")

    if not isinstance(requirements, list):
        errors.append("REQUIREMENTS_MUST_BE_LIST")
        requirements = []

    for i, row in enumerate(requirements):
        if not isinstance(row, dict):
            errors.append(
                f"REQ_{i}:NOT_OBJECT"
            )
            continue

        prefix = f"REQ_{i}:"

        if row.get(
            "classification"
        ) not in VALID_REQUIREMENT_TYPES:
            errors.append(
                prefix + "BAD_CLASSIFICATION"
            )

        if row.get(
            "suggested_priority"
        ) not in VALID_PRIORITIES:
            errors.append(
                prefix + "BAD_PRIORITY"
            )

        if row.get(
            "suggested_relation"
        ) not in VALID_RELATIONS:
            errors.append(
                prefix + "BAD_RELATION"
            )

        validate_span(
            row,
            prefix,
            errors,
        )

        rationale = row.get("rationale")

        if (
            not isinstance(rationale, str)
            or not rationale.strip()
        ):
            errors.append(
                prefix + "RATIONALE_REQUIRED"
            )

    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("shadow_json")
    args = parser.parse_args()

    obj = json.loads(
        Path(args.shadow_json).read_text(
            encoding="utf-8"
        )
    )

    errors = validate(obj)

    output = {
        "schema_version":
            "career-ops-li-shadow-validation-v1",

        "status":
            "PASS" if not errors else "FAIL",

        "authority_preserved":
            not any(
                error.startswith(
                    "FORBIDDEN_AUTHORITY_FIELD:"
                )
                for error in errors
            )
            and obj.get("authority") == "ADVISORY_ONLY"
            and obj.get("may_override") is False,

        "errors":
            errors,
    }

    print(
        json.dumps(
            output,
            indent=2,
            ensure_ascii=False,
        )
    )

    raise SystemExit(
        0 if not errors else 1
    )


if __name__ == "__main__":
    main()
