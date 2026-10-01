#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def norm(value):
    return re.sub(
        r"\s+",
        " ",
        str(value or ""),
    ).strip().casefold()


def deep_get(obj, candidates):
    for path in candidates:
        value = obj

        ok = True

        for part in path:
            if not isinstance(value, dict):
                ok = False
                break

            value = value.get(part)

            if value is None:
                ok = False
                break

        if ok:
            return value

    return None


def deterministic_identity(obj):
    return {
        "employer_name":
            deep_get(
                obj,
                [
                    ("company",),
                    ("employer",),
                    ("employer_name",),
                    ("identity", "company"),
                    ("identity", "employer"),
                    ("canonical_job", "company"),
                    ("canonical_job", "employer"),
                ],
            ),

        "job_title":
            deep_get(
                obj,
                [
                    ("title",),
                    ("job_title",),
                    ("position",),
                    ("identity", "title"),
                    ("canonical_job", "title"),
                ],
            ),

        "requisition_id":
            deep_get(
                obj,
                [
                    ("requisition_id",),
                    ("job_id",),
                    ("req_id",),
                    ("identity", "requisition_id"),
                    ("canonical_job", "requisition_id"),
                ],
            ),
    }


def collect_requirements(obj):
    found = {}

    def walk(value):
        if isinstance(value, dict):
            rid = value.get("requirement_id")

            if isinstance(rid, str):
                found[rid] = value

            for child in value.values():
                walk(child)

        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(obj)

    return found


def compare(deterministic, shadow):
    disagreements = []

    det_identity = deterministic_identity(
        deterministic
    )

    sh_identity = shadow.get(
        "identity",
        {},
    )

    for field in (
        "employer_name",
        "job_title",
        "requisition_id",
    ):
        det = det_identity.get(field)
        sh = sh_identity.get(field)

        if (
            det
            and sh
            and norm(det) != norm(sh)
        ):
            disagreements.append(
                {
                    "type":
                        "IDENTITY_DISAGREEMENT",

                    "field":
                        field,

                    "deterministic":
                        det,

                    "shadow":
                        sh,

                    "action":
                        "REVIEW_ONLY",
                }
            )

    for row in shadow.get(
        "boundaries",
        [],
    ):
        if not isinstance(row, dict):
            continue

        if row.get("material") is True:
            disagreements.append(
                {
                    "type":
                        "SOURCE_BOUNDARY_WARNING",

                    "boundary_type":
                        row.get("boundary_type"),

                    "exact_source_quote":
                        row.get("exact_source_quote"),

                    "confidence":
                        row.get("confidence"),

                    "action":
                        "REVIEW_ONLY",
                }
            )

    deterministic_requirements = collect_requirements(
        deterministic
    )

    for row in shadow.get(
        "requirements",
        [],
    ):
        if not isinstance(row, dict):
            continue

        rid = row.get("requirement_id")
        classification = row.get(
            "classification"
        )

        if classification in {
            "POSSIBLE_MISSED_REQUIREMENT",
            "POSSIBLE_FALSE_REQUIREMENT",
        }:
            disagreements.append(
                {
                    "type":
                        classification,

                    "requirement_id":
                        rid,

                    "exact_source_quote":
                        row.get("exact_source_quote"),

                    "confidence":
                        row.get("confidence"),

                    "action":
                        "REVIEW_ONLY",
                }
            )
            continue

        if not rid:
            continue

        det = deterministic_requirements.get(
            rid
        )

        if det is None:
            disagreements.append(
                {
                    "type":
                        "UNKNOWN_REQUIREMENT_REFERENCE",

                    "requirement_id":
                        rid,

                    "action":
                        "REVIEW_ONLY",
                }
            )
            continue

        shadow_priority = row.get(
            "suggested_priority"
        )

        det_priority = (
            det.get("effective_priority")
            or det.get("priority")
        )

        if (
            shadow_priority
            and det_priority
            and norm(shadow_priority)
            != norm(det_priority)
        ):
            disagreements.append(
                {
                    "type":
                        "PRIORITY_DISAGREEMENT",

                    "requirement_id":
                        rid,

                    "deterministic":
                        det_priority,

                    "shadow":
                        shadow_priority,

                    "confidence":
                        row.get("confidence"),

                    "action":
                        "REVIEW_ONLY",
                }
            )

        shadow_relation = row.get(
            "suggested_relation"
        )

        det_relation = (
            det.get("effective_relation")
            or det.get("relation")
            or det.get("relationship")
        )

        if (
            shadow_relation
            and shadow_relation != "NONE"
            and det_relation
            and norm(shadow_relation)
            != norm(det_relation)
        ):
            disagreements.append(
                {
                    "type":
                        "RELATION_DISAGREEMENT",

                    "requirement_id":
                        rid,

                    "deterministic":
                        det_relation,

                    "shadow":
                        shadow_relation,

                    "confidence":
                        row.get("confidence"),

                    "action":
                        "REVIEW_ONLY",
                }
            )

    return {
        "schema_version":
            "career-ops-li-disagreement-v1",

        "authority":
            "DIAGNOSTIC_ONLY",

        "may_override":
            False,

        "review_required":
            bool(disagreements),

        "disagreement_count":
            len(disagreements),

        "disagreements":
            disagreements,
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "deterministic_json"
    )

    parser.add_argument(
        "shadow_json"
    )

    parser.add_argument(
        "--output"
    )

    args = parser.parse_args()

    deterministic = json.loads(
        Path(
            args.deterministic_json
        ).read_text(
            encoding="utf-8"
        )
    )

    shadow = json.loads(
        Path(
            args.shadow_json
        ).read_text(
            encoding="utf-8"
        )
    )

    output = compare(
        deterministic,
        shadow,
    )

    text = (
        json.dumps(
            output,
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )

    if args.output:
        Path(
            args.output
        ).write_text(
            text,
            encoding="utf-8",
        )
    else:
        print(
            text,
            end="",
        )


if __name__ == "__main__":
    main()
