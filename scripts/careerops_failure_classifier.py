#!/usr/bin/env python3

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


LOCKED_FAILURE_CLASSES = [
    "SOURCE",
    "JD_STRUCTURE",
    "REQUIREMENTS",
    "ROUTING",
    "SEMANTICS",
    "EVIDENCE",
    "CONSTRAINT",
    "SELECTION",
    "SKILLS",
    "ATS_VALIDATION",
    "HUMAN_VALIDATION",
    "COVER_VALIDATION",
    "RENDERING",
    "WRITING",
]


POLICY = {
    "SOURCE": {
        "response":
            "DETERMINISTIC_SOURCE_RETRY_OR_MANUAL_JD",
        "deterministic_repair_permitted":
            True,
        "block_if_unrepaired":
            True,
    },

    "JD_STRUCTURE": {
        "response":
            "DETERMINISTIC_STRUCTURE_REPAIR_OR_BLOCK",
        "deterministic_repair_permitted":
            True,
        "block_if_unrepaired":
            True,
    },

    "REQUIREMENTS": {
        "response":
            "DETERMINISTIC_REQUIREMENT_REPAIR_OR_BLOCK",
        "deterministic_repair_permitted":
            True,
        "block_if_unrepaired":
            True,
    },

    "ROUTING": {
        "response":
            "DETERMINISTIC_ROUTING_REPAIR_OR_BLOCK",
        "deterministic_repair_permitted":
            True,
        "block_if_unrepaired":
            True,
    },

    "SEMANTICS": {
        "response":
            "DETERMINISTIC_SEMANTIC_REPAIR_OR_BLOCK",
        "deterministic_repair_permitted":
            True,
        "block_if_unrepaired":
            True,
    },

    "EVIDENCE": {
        "response":
            "DETERMINISTIC_EVIDENCE_REPAIR_OR_BLOCK",
        "deterministic_repair_permitted":
            True,
        "block_if_unrepaired":
            True,
    },

    "CONSTRAINT": {
        "response":
            "BLOCK_UNTIL_CONSTRAINT_RESOLVED",
        "deterministic_repair_permitted":
            False,
        "block_if_unrepaired":
            True,
    },

    "SELECTION": {
        "response":
            "DETERMINISTIC_SELECTION_REPAIR_OR_BLOCK",
        "deterministic_repair_permitted":
            True,
        "block_if_unrepaired":
            True,
    },

    "SKILLS": {
        "response":
            "DETERMINISTIC_SKILLS_REPAIR_OR_BLOCK",
        "deterministic_repair_permitted":
            True,
        "block_if_unrepaired":
            True,
    },

    "ATS_VALIDATION": {
        "response":
            "DETERMINISTIC_ATS_DIAGNOSIS_REPAIR_OR_BLOCK",
        "deterministic_repair_permitted":
            True,
        "block_if_unrepaired":
            True,
    },

    "HUMAN_VALIDATION": {
        "response":
            "DETERMINISTIC_HUMAN_DIAGNOSIS_REPAIR_OR_BLOCK",
        "deterministic_repair_permitted":
            True,
        "block_if_unrepaired":
            True,
    },

    "COVER_VALIDATION": {
        "response":
            "DETERMINISTIC_COVER_REPAIR_OR_BLOCK",
        "deterministic_repair_permitted":
            True,
        "block_if_unrepaired":
            True,
    },

    "RENDERING": {
        "response":
            "DETERMINISTIC_RERENDER_OR_RENDERER_REPAIR",
        "deterministic_repair_permitted":
            True,
        "block_if_unrepaired":
            True,
    },

    "WRITING": {
        "response":
            "DIAGNOSE_WRITING_DEFECT_THEN_OPTIONAL_SECOND_WRITER",
        "deterministic_repair_permitted":
            True,
        "block_if_unrepaired":
            True,
    },
}


STAGE_CLASS = {
    # Source / ingestion
    "ingest":
        "SOURCE",
    "source":
        "SOURCE",
    "prepare_input":
        "SOURCE",
    "url_probe":
        "SOURCE",
    "manual_jd":
        "SOURCE",
    "ats_probe":
        "SOURCE",

    # JD structure
    "normalize":
        "JD_STRUCTURE",
    "normalize_jd":
        "JD_STRUCTURE",
    "jd_structure":
        "JD_STRUCTURE",
    "structure":
        "JD_STRUCTURE",

    # Requirements
    "requirements":
        "REQUIREMENTS",
    "requirement_integrity":
        "REQUIREMENTS",
    "requirement_extraction":
        "REQUIREMENTS",

    # Routing
    "routing":
        "ROUTING",
    "route":
        "ROUTING",
    "role_routing":
        "ROUTING",
    "summary_route":
        "ROUTING",
    "summary":
        "ROUTING",

    # Semantics
    "semantics":
        "SEMANTICS",
    "semantic":
        "SEMANTICS",
    "semantic_expansion":
        "SEMANTICS",
    "entity_resolution":
        "SEMANTICS",
    "entities":
        "SEMANTICS",

    # Evidence / truth
    "evidence":
        "EVIDENCE",
    "evidence_map":
        "EVIDENCE",
    "local_truth_gate":
        "EVIDENCE",
    "deep_truth_gate":
        "EVIDENCE",
    "truth_gate":
        "EVIDENCE",

    # Constraints
    "constraint":
        "CONSTRAINT",
    "constraints":
        "CONSTRAINT",
    "constraint_validation":
        "CONSTRAINT",
    "pre_writer_constraint":
        "CONSTRAINT",

    # Selection
    "experience_selection":
        "SELECTION",
    "residual_gap":
        "SELECTION",
    "project_selection":
        "SELECTION",
    "cover_plan":
        "SELECTION",
    "compact_packet":
        "SELECTION",
    "pair_packet":
        "SELECTION",

    # Skills
    "skills":
        "SKILLS",
    "skill":
        "SKILLS",
    "technical_skills":
        "SKILLS",

    # Validation
    "ats_gate":
        "ATS_VALIDATION",
    "human_gate":
        "HUMAN_VALIDATION",
    "cover_gate":
        "COVER_VALIDATION",

    # Rendering
    "render":
        "RENDERING",
    "rendering":
        "RENDERING",
    "resume_pdf":
        "RENDERING",
    "resume_docx":
        "RENDERING",
    "cover_pdf":
        "RENDERING",
    "cover_docx":
        "RENDERING",
    "cover_roundtrip":
        "RENDERING",
    "resume_roundtrip":
        "RENDERING",
    "release":
        "RENDERING",

    # Writer
    "writer":
        "WRITING",
    "pair_writer":
        "WRITING",
    "generate_pair":
        "WRITING",
}


ARTIFACT_CLASS = {
    "jd_intake.json":
        "SOURCE",
    "jd_normalized.json":
        "JD_STRUCTURE",
    "jd_requirements.json":
        "REQUIREMENTS",
    "requirement_integrity_gate.json":
        "REQUIREMENTS",
    "role_routing.json":
        "ROUTING",
    "semantic_requirements.json":
        "SEMANTICS",
    "requirement_evidence_map.json":
        "EVIDENCE",
    "constraint_validation.json":
        "CONSTRAINT",
    "experience_selection.json":
        "SELECTION",
    "residual_gap_analysis.json":
        "SELECTION",
    "project_selection.json":
        "SELECTION",
    "technical_skills_plan.json":
        "SKILLS",
    "ats_gate.json":
        "ATS_VALIDATION",
    "human_gate.json":
        "HUMAN_VALIDATION",
    "cover_gate_v2_report.json":
        "COVER_VALIDATION",
    "render_validation.json":
        "RENDERING",
    "cover_roundtrip.json":
        "RENDERING",
    "generated_resume_content_pair_candidate.json":
        "WRITING",
    "generated_cover_letter_pair_candidate.json":
        "WRITING",
}


REASON_PATTERNS = [
    (
        "ATS_VALIDATION",
        re.compile(
            r"\bATS\b|P0_COVERAGE|P1_COVERAGE|"
            r"SEARCHABLE_COVERAGE|SEMANTIC_COVERAGE",
            re.I,
        ),
    ),

    (
        "HUMAN_VALIDATION",
        re.compile(
            r"HUMAN|READABILITY|REDUNDANCY|"
            r"NATURAL_LANGUAGE|GENERIC_AI|"
            r"FIRST_EVIDENCE|CAREER_COHERENCE",
            re.I,
        ),
    ),

    (
        "COVER_VALIDATION",
        re.compile(
            r"COVER_GATE|COVER VALIDATION|"
            r"PARAGRAPH|COVER LETTER",
            re.I,
        ),
    ),

    (
        "RENDERING",
        re.compile(
            r"RENDER|PDF|DOCX|ROUNDTRIP|ROUND-TRIP|"
            r"CLIPPING|BROKEN CHARACTER",
            re.I,
        ),
    ),

    (
        "CONSTRAINT",
        re.compile(
            r"CONSTRAINT|ELIGIBILITY|SPONSORSHIP|"
            r"CLEARANCE|WORK AUTHORIZATION",
            re.I,
        ),
    ),

    (
        "REQUIREMENTS",
        re.compile(
            r"REQUIREMENT|UNDEREXTRACT|"
            r"PRIORITY_DISTRIBUTION|"
            r"P0_P1_SOURCE_CONCEPTS|"
            r"COMPOUND_REQUIREMENT",
            re.I,
        ),
    ),

    (
        "SOURCE",
        re.compile(
            r"SOURCE|INGEST|URL|MANUAL JD|"
            r"INACCESSIBLE|NEEDS_MANUAL_JD",
            re.I,
        ),
    ),

    (
        "JD_STRUCTURE",
        re.compile(
            r"JD_STRUCTURE|STRUCTURAL HEADING|"
            r"PAGE_CHROME|POST_JD_BOUNDARY|"
            r"METADATA",
            re.I,
        ),
    ),

    (
        "SKILLS",
        re.compile(
            r"\bSKILL(?:S)?\b|TECHNICAL_SKILLS",
            re.I,
        ),
    ),

    (
        "SELECTION",
        re.compile(
            r"EXPERIENCE_SELECTION|PROJECT_SELECTION|"
            r"RESIDUAL_GAP|SELECTION",
            re.I,
        ),
    ),

    (
        "SEMANTICS",
        re.compile(
            r"SEMANTIC_EXPANSION|ENTITY_RESOLUTION|"
            r"SEMANTICS",
            re.I,
        ),
    ),

    (
        "ROUTING",
        re.compile(
            r"ROLE_ROUTING|SUMMARY_ROUTE|ROUTING",
            re.I,
        ),
    ),

    (
        "EVIDENCE",
        re.compile(
            r"EVIDENCE|UNSUPPORTED CLAIM|"
            r"TRUTH_GATE|TRUTH GATE|"
            r"CLAIM SUPPORT",
            re.I,
        ),
    ),
]


def normalize_stage(stage):
    value = str(
        stage or ""
    ).strip().lower()

    value = re.sub(
        r"^stage:\s*",
        "",
        value,
    )

    value = value.replace(
        "v2.2",
        "",
    )

    value = value.replace(
        "v2",
        "",
    )

    value = re.sub(
        r"[^a-z0-9]+",
        "_",
        value,
    ).strip("_")

    return value


def explicit_report_class(report):
    if not isinstance(
        report,
        dict,
    ):
        return None

    value = report.get(
        "failure_class"
    )

    if value in LOCKED_FAILURE_CLASSES:
        return value

    values = report.get(
        "failure_classes"
    )

    if isinstance(
        values,
        list,
    ):
        valid = [
            value
            for value in values
            if value in LOCKED_FAILURE_CLASSES
        ]

        if len(
            set(valid)
        ) == 1:
            return valid[0]

    return None


def flatten_failure_text(
    message,
    report,
):
    pieces = [
        str(
            message or ""
        )
    ]

    if isinstance(
        report,
        dict,
    ):
        for key in [
            "hard_fail_reasons",
            "human_fail_reasons",
            "blocking_findings",
            "failed_checks",
            "errors",
            "warning_reasons",
            "status",
            "gate",
        ]:
            value = report.get(
                key
            )

            if isinstance(
                value,
                list,
            ):
                pieces.extend(
                    str(x)
                    for x in value
                )

            elif value is not None:
                pieces.append(
                    str(value)
                )

    return "\n".join(
        pieces
    )


def artifact_class(
    artifact,
):
    if not artifact:
        return None

    name = Path(
        str(
            artifact
        )
    ).name.lower()

    for key, failure_class in (
        ARTIFACT_CLASS.items()
    ):
        if name == key.lower():
            return failure_class

    return None


def stage_class(
    stage,
):
    normalized = normalize_stage(
        stage
    )

    if normalized in STAGE_CLASS:
        return STAGE_CLASS[
            normalized
        ]

    # Match longer aliases contained in descriptive stage labels.
    ordered = sorted(
        STAGE_CLASS.items(),
        key=lambda item: len(
            item[0]
        ),
        reverse=True,
    )

    for alias, failure_class in ordered:
        if alias in normalized:
            return failure_class

    return None


def reason_class(
    text,
):
    for failure_class, pattern in (
        REASON_PATTERNS
    ):
        if pattern.search(
            text
        ):
            return failure_class

    return None


def classify_failure(
    *,
    stage,
    artifact=None,
    message="",
    return_code=None,
    report=None,
    writing_defect_confirmed=False,
):
    explicit = explicit_report_class(
        report
    )

    artifact_guess = artifact_class(
        artifact
    )

    stage_guess = stage_class(
        stage
    )

    failure_text = flatten_failure_text(
        message,
        report,
    )

    reason_guess = reason_class(
        failure_text
    )

    normalized_stage = normalize_stage(
        stage
    )

    # Truth/evidence failures are deliberately conservative.
    # They become WRITING only after a separate deterministic
    # diagnosis explicitly proves the writer, rather than the
    # evidence/validator layer, is the remaining defect.
    truth_like = (
        stage_guess == "EVIDENCE"
        and (
            "truth"
            in normalized_stage
            or "truth"
            in failure_text.lower()
        )
    )

    if (
        truth_like
        and writing_defect_confirmed
    ):
        failure_class = "WRITING"
        source = (
            "CONFIRMED_WRITING_DEFECT_AFTER_TRUTH_VALIDATION"
        )

    elif explicit:
        failure_class = explicit
        source = "EXPLICIT_REPORT_FAILURE_CLASS"

    elif reason_guess:
        failure_class = reason_guess
        source = "FAILURE_REASON_PATTERN"

    elif artifact_guess:
        failure_class = artifact_guess
        source = "ARTIFACT_CONTRACT"

    elif stage_guess:
        failure_class = stage_guess
        source = "STAGE_CONTRACT"

    else:
        failure_class = None
        source = "UNRESOLVED_FAIL_CLOSED"

    classification_resolved = (
        failure_class
        in LOCKED_FAILURE_CLASSES
    )

    policy = (
        POLICY.get(
            failure_class,
            {
                "response":
                    "BLOCK_UNCLASSIFIED_FAILURE",
                "deterministic_repair_permitted":
                    False,
                "block_if_unrepaired":
                    True,
            },
        )
    )

    second_writer_call_permitted = (
        failure_class
        == "WRITING"
        and bool(
            writing_defect_confirmed
        )
    )

    # Critical invariant:
    # classification may permit a future manual/controlled writer
    # retry, but the classifier NEVER launches or auto-authorizes it.
    automatic_writer_retry = False

    result = {
        "schema_version":
            "career-ops-failure-classification-v1",

        "classification_status":
            (
                "RESOLVED"
                if classification_resolved
                else "UNRESOLVED_FAIL_CLOSED"
            ),

        "failure_class":
            failure_class,

        "classification_source":
            source,

        "stage":
            str(
                stage or ""
            ),

        "normalized_stage":
            normalized_stage,

        "artifact":
            (
                str(
                    artifact
                )
                if artifact
                else None
            ),

        "return_code":
            return_code,

        "response":
            policy[
                "response"
            ],

        "deterministic_repair_permitted":
            bool(
                policy[
                    "deterministic_repair_permitted"
                ]
            ),

        "block_if_unrepaired":
            bool(
                policy[
                    "block_if_unrepaired"
                ]
            ),

        "writing_defect_confirmed":
            bool(
                writing_defect_confirmed
            ),

        "second_writer_call_permitted":
            second_writer_call_permitted,

        "automatic_writer_retry":
            automatic_writer_retry,

        "policy": {
            "only_writing_may_permit_second_writer":
                True,

            "permission_is_not_automatic_retry":
                True,

            "unresolved_failure_fails_closed":
                True,

            "gate_validator_renderer_failure_never_implies_writer_retry":
                True,
        },

        "model_calls":
            0,
    }

    return result


def load_report(path):
    if not path:
        return None

    p = Path(
        path
    )

    if not p.exists():
        raise SystemExit(
            f"Report does not exist: {p}"
        )

    return json.loads(
        p.read_text(
            encoding="utf-8"
        )
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--stage",
        required=True,
    )

    parser.add_argument(
        "--artifact",
    )

    parser.add_argument(
        "--message",
        default="",
    )

    parser.add_argument(
        "--return-code",
        type=int,
    )

    parser.add_argument(
        "--report",
    )

    parser.add_argument(
        "--writing-defect-confirmed",
        action="store_true",
    )

    parser.add_argument(
        "--output",
    )

    args = parser.parse_args()

    report = load_report(
        args.report
    )

    result = classify_failure(
        stage=args.stage,
        artifact=args.artifact,
        message=args.message,
        return_code=args.return_code,
        report=report,
        writing_defect_confirmed=(
            args.writing_defect_confirmed
        ),
    )

    if args.output:
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
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        )
    )

    if (
        result[
            "classification_status"
        ]
        != "RESOLVED"
    ):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
