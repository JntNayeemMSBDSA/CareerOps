#!/usr/bin/env python3

import argparse
import json
from pathlib import Path
from careerops_requirement_regeneration import canonical_ledger_path


def load_optional(path):
    path = Path(
        path
    )

    if not path.is_file():
        return {}

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def requirement_index(ledger):
    return {
        row.get(
            "requirement_id"
        ):
            row
        for row in (
            ledger.get(
                "requirements",
                [],
            )
            or []
        )
        if row.get(
            "requirement_id"
        )
    }


def constraint_index(payload):
    return {
        row.get(
            "requirement_id"
        ):
            row
        for row in (
            payload.get(
                "requirements",
                [],
            )
            or []
        )
        if row.get(
            "requirement_id"
        )
    }


def unresolved_ids(experience):
    return (
        experience.get(
            "residual_gaps",
            {},
        ).get(
            "unresolved_hard_constraint_ids",
            [],
        )
        or []
    )


def constraint_status(row):
    return (
        row.get(
            "overall_status"
        )
        or row.get(
            "status"
        )
        or row.get(
            "result"
        )
    )


def constraint_reason(row):
    return (
        row.get(
            "reason"
        )
        or row.get(
            "message"
        )
        or row.get(
            "detail"
        )
        or row.get(
            "basis"
        )
    )


def build_receipt(
    ledger,
    integrity,
    constraints,
    experience,
    manifest,
    failure,
):
    rows = requirement_index(
        ledger
    )

    cindex = constraint_index(
        constraints
    )

    gate_status = (
        integrity.get(
            "status"
        )
        or integrity.get(
            "gate_status"
        )
    )

    blocking_findings = (
        integrity.get(
            "blocking_findings",
            [],
        )
        or []
    )

    writer_calls = (
        manifest.get(
            "writer_calls"
        )
        or manifest.get(
            "model_usage",
            {},
        ).get(
            "writer_calls"
        )
        or 0
    )

    if (
        gate_status
        in {
            "FAIL_CLOSED",
            "FAIL",
            "BLOCKED",
        }
        or blocking_findings
    ):
        return {
            "schema_version":
                "career-ops-job-decision-receipt-v2",

            "decision":
                "NEEDS_ATTENTION",

            "decision_class":
                "SOURCE_OR_SEMANTIC_INTEGRITY",

            "reason":
                (
                    "Job processing stopped because source or "
                    "requirement integrity was not proven. "
                    "This is not a candidate rejection."
                ),

            "blocking_findings":
                blocking_findings,

            "failure_class":
                failure.get(
                    "failure_class"
                ),

            "requirements":
                [],

            "writer_calls":
                writer_calls,

            "writer_called_before_decision":
                bool(
                    writer_calls
                ),
        }

    proven_failures = []
    unresolved_reviews = []

    failure_ids = set()
    review_ids = set()

    def normalized_status(
        row,
    ):
        return str(
            row.get(
                "overall_status"
            )
            or row.get(
                "status"
            )
            or row.get(
                "result"
            )
            or ""
        ).upper()

    def primary_check(
        row,
    ):
        checks = (
            row.get(
                "checks",
                [],
            )
            or []
        )

        if not checks:
            return {}

        for check in checks:
            if str(
                check.get(
                    "status"
                )
                or check.get(
                    "result"
                )
                or ""
            ).upper() in {
                "FAIL",
                "REVIEW_REQUIRED",
                "UNKNOWN",
                "UNRESOLVED",
            }:
                return check

        return checks[
            0
        ]

    def build_detail(
        requirement_id,
        validation,
        forced_status=None,
    ):
        source_row = rows.get(
            requirement_id,
            {},
        )

        check = primary_check(
            validation
        )

        status = (
            forced_status
            or normalized_status(
                validation
            )
            or str(
                check.get(
                    "status"
                )
                or check.get(
                    "result"
                )
                or ""
            ).upper()
        )

        priority = (
            validation.get(
                "priority"
            )
            or source_row.get(
                "priority"
            )
        )

        exact_quote = (
            validation.get(
                "exact_jd_quote"
            )
            or source_row.get(
                "exact_quote"
            )
        )

        hard_phrases = (
            source_row.get(
                "hard_blocker_phrases",
                [],
            )
            or []
        )

        reason = (
            validation.get(
                "reason"
            )
            or validation.get(
                "message"
            )
            or validation.get(
                "detail"
            )
            or check.get(
                "reason"
            )
            or check.get(
                "message"
            )
            or check.get(
                "detail"
            )
        )

        if (
            not reason
            and hard_phrases
        ):
            reason = (
                "Explicit employer hard blocker: "
                + "; ".join(
                    hard_phrases
                )
            )

        if not reason:
            reason = (
                "Mandatory candidate/job constraint failed."
                if status == "FAIL"
                else (
                    "Mandatory candidate/job constraint "
                    "could not be deterministically verified."
                )
            )

        constraint_type = (
            validation.get(
                "constraint_type"
            )
            or check.get(
                "constraint_type"
            )
        )

        basis = (
            validation.get(
                "basis"
            )
            or validation.get(
                "claim_class"
            )
            or validation.get(
                "reason_code"
            )
            or check.get(
                "basis"
            )
            or check.get(
                "claim_class"
            )
            or check.get(
                "reason_code"
            )
            or status
        )

        return {
            "requirement_id":
                requirement_id,

            "priority":
                priority,

            "exact_jd_quote":
                exact_quote,

            "constraint_type":
                constraint_type,

            "constraint_status":
                status,

            "deterministic_reason":
                reason,

            "candidate_conflict_or_evidence_basis":
                basis,
        }

    for validation in (
        constraints.get(
            "requirements",
            [],
        )
        or []
    ):
        requirement_id = validation.get(
            "requirement_id"
        )

        if not requirement_id:
            continue

        detail = build_detail(
            requirement_id,
            validation,
        )

        priority = detail.get(
            "priority"
        )

        status = detail.get(
            "constraint_status"
        )

        if (
            priority == "P0"
            and status == "FAIL"
        ):
            if requirement_id not in failure_ids:
                proven_failures.append(
                    detail
                )

                failure_ids.add(
                    requirement_id
                )

        elif (
            priority == "P0"
            and status
            in {
                "REVIEW_REQUIRED",
                "UNKNOWN",
                "UNRESOLVED",
            }
        ):
            if (
                requirement_id
                not in failure_ids
                and requirement_id
                not in review_ids
            ):
                unresolved_reviews.append(
                    detail
                )

                review_ids.add(
                    requirement_id
                )

    unresolved = unresolved_ids(
        experience
    )

    for requirement_id in unresolved:
        if requirement_id in failure_ids:
            continue

        constraint_row = cindex.get(
            requirement_id,
            {},
        )

        detail = build_detail(
            requirement_id,
            constraint_row,
            forced_status=(
                normalized_status(
                    constraint_row
                )
                or "UNRESOLVED"
            ),
        )

        priority = detail.get(
            "priority"
        )

        status = detail.get(
            "constraint_status"
        )

        if (
            priority == "P0"
            and status == "FAIL"
        ):
            proven_failures.append(
                detail
            )

            failure_ids.add(
                requirement_id
            )

            if requirement_id in review_ids:
                unresolved_reviews = [
                    row
                    for row in unresolved_reviews
                    if row.get(
                        "requirement_id"
                    )
                    != requirement_id
                ]

                review_ids.discard(
                    requirement_id
                )

        elif (
            priority == "P0"
            and requirement_id
            not in review_ids
        ):
            unresolved_reviews.append(
                detail
            )

            review_ids.add(
                requirement_id
            )

    if proven_failures:
        return {
            "schema_version":
                "career-ops-job-decision-receipt-v2",

            "decision":
                "REJECTED",

            "decision_class":
                "PROVEN_MANDATORY_CONSTRAINT_CONFLICT",

            "reason":
                (
                    "One or more explicit mandatory job requirements "
                    "are deterministically incompatible with the "
                    "candidate's authoritative facts."
                ),

            "requirements":
                proven_failures,

            "other_unresolved_requirements":
                unresolved_reviews,

            "writer_calls":
                writer_calls,

            "writer_called_before_decision":
                bool(
                    writer_calls
                ),
        }

    if unresolved_reviews:
        return {
            "schema_version":
                "career-ops-job-decision-receipt-v2",

            "decision":
                "NEEDS_ATTENTION",

            "decision_class":
                "UNRESOLVED_MANDATORY_CONSTRAINT",

            "reason":
                (
                    "At least one mandatory requirement is unresolved. "
                    "This is not yet a proven candidate rejection."
                ),

            "requirements":
                unresolved_reviews,

            "writer_calls":
                writer_calls,

            "writer_called_before_decision":
                bool(
                    writer_calls
                ),
        }

    return {
        "schema_version":
            "career-ops-job-decision-receipt-v2",

        "decision":
            "CONTINUE",

        "decision_class":
            "NO_PROVEN_PREWRITER_REJECTION",

        "reason":
            (
                "No proven mandatory candidate/job conflict "
                "is currently present."
            ),

        "requirements":
            [],

        "writer_calls":
            writer_calls,

        "writer_called_before_decision":
            bool(
                writer_calls
            ),
    }



def print_receipt(receipt):
    print(
        "=" * 88
    )

    print(
        "JOB DECISION:",
        receipt.get(
            "decision"
        ),
    )

    print(
        "CLASS:",
        receipt.get(
            "decision_class"
        ),
    )

    print(
        "REASON:",
        receipt.get(
            "reason"
        ),
    )

    for row in (
        receipt.get(
            "requirements",
            [],
        )
        or []
    ):
        print()

        print(
            "REQUIREMENT:",
            row.get(
                "requirement_id"
            ),
        )

        print(
            "JD EVIDENCE:",
            row.get(
                "exact_jd_quote"
            ),
        )

        print(
            "CONSTRAINT:",
            row.get(
                "constraint_type"
            ),
        )

        print(
            "WHY:",
            row.get(
                "deterministic_reason"
            ),
        )

        print(
            "EVIDENCE BASIS:",
            row.get(
                "candidate_conflict_or_evidence_basis"
            ),
        )

    findings = (
        receipt.get(
            "blocking_findings",
            [],
        )
        or []
    )

    if findings:
        print(
            "INTEGRITY FINDINGS:",
            ", ".join(
                findings
            ),
        )

    print(
        "WRITER CALLS BEFORE DECISION:",
        receipt.get(
            "writer_calls",
            0,
        ),
    )

    print(
        "=" * 88
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--runtime",
        required=True,
    )

    parser.add_argument(
        "--output",
        required=True,
    )

    args = parser.parse_args()

    runtime = Path(
        args.runtime
    )

    receipt = build_receipt(
        load_optional(
            canonical_ledger_path(runtime)
        ),
        load_optional(
            runtime
            / "requirement_integrity_gate.json"
        ),
        load_optional(
            runtime
            / "constraint_validation.json"
        ),
        load_optional(
            runtime
            / "experience_selection.json"
        ),
        load_optional(
            runtime.parent
            / "manifest.json"
        ),
        load_optional(
            runtime
            / "failure_classification.json"
        ),
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
            receipt,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    print_receipt(
        receipt
    )

    print(
        "OUTPUT:",
        output,
    )


if __name__ == "__main__":
    main()
