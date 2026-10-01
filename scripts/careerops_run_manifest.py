#!/usr/bin/env python3

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from careerops_requirement_regeneration import canonical_ledger_path

from careerops_runtime import (
    current_run_id,
    output_dir,
    run_dir,
    runtime_dir,
)


ROOT = Path(__file__).resolve().parents[1]

SCHEMA_VERSION = "careerops-run-manifest-v1"

VALID_STATUSES = {
    "PENDING",
    "RUNNING",
    "PASS",
    "FAIL",
    "BLOCKED",
    "SKIPPED",
    "UNKNOWN",
}


STAGE_ARTIFACTS = [
    (
        "ingest",
        "jd_intake.json",
    ),
    (
        "requirements",
        "jd_requirements.json",
    ),
    (
        "requirement_integrity",
        "requirement_integrity_gate.json",
    ),
    (
        "routing",
        "role_routing.json",
    ),
    (
        "semantics",
        "jd_semantic_map.json",
    ),
    (
        "entities",
        "candidate_entities.json",
    ),
    (
        "evidence_map",
        "requirement_evidence_map.json",
    ),
    (
        "constraints",
        "constraint_validation.json",
    ),
    (
        "experience_selection",
        "experience_selection.json",
    ),
    (
        "project_selection",
        "project_selection.json",
    ),
    (
        "skills",
        "technical_skills_plan.json",
    ),
    (
        "summary",
        "summary_route.json",
    ),
    (
        "resume_spec",
        "resume_generation_spec.json",
    ),
    (
        "cover_plan",
        "cover_plan.json",
    ),
    (
        "compact_packet",
        "compact_generation_packet.json",
    ),
    (
        "pair_packet",
        "pair_generation_packet.json",
    ),
]


POSTWRITER_STAGE_ORDER = [
    "writer",
    "deep_truth_gate",
    "local_truth_gate",
    "ats_gate",
    "human_gate",
    "cover_gate",
    "interview_defensibility",
    "resume_payload",
    "resume_render",
    "cover_render",
    "cover_roundtrip",
    "final_application_audit",
    "release",
]


FULL_STAGE_ORDER = (
    [
        name
        for name, _
        in STAGE_ARTIFACTS
    ]
    + POSTWRITER_STAGE_ORDER
)


def now_utc():
    return (
        datetime.now(
            timezone.utc
        )
        .replace(
            microsecond=0
        )
        .isoformat()
    )


def load_json(path):
    if not path.exists():
        return None

    try:
        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return None


def sha256_bytes(data):
    return hashlib.sha256(
        data
    ).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(
            lambda: f.read(
                1024 * 1024
            ),
            b"",
        ):
            h.update(
                chunk
            )

    return h.hexdigest()


def relative(path):
    try:
        return str(
            path.resolve()
            .relative_to(
                ROOT
            )
        )
    except Exception:
        return str(
            path.resolve()
        )


def atomic_write_json(
    path,
    data,
):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tmp = path.with_suffix(
        path.suffix + ".tmp"
    )

    tmp.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    tmp.replace(
        path
    )


def artifact_record(path):
    if not path.exists():
        return {
            "exists": False,
            "path": relative(
                path
            ),
            "sha256": None,
            "size_bytes": None,
        }

    return {
        "exists": True,
        "path": relative(
            path
        ),
        "sha256": (
            sha256_file(
                path
            )
            if path.is_file()
            else None
        ),
        "size_bytes": (
            path.stat().st_size
            if path.is_file()
            else None
        ),
    }


def gate_status(
    path,
    *,
    boolean_key=None,
    string_key="gate",
):
    data = load_json(
        path
    )

    if data is None:
        return "PENDING"

    if boolean_key:
        value = data.get(
            boolean_key
        )

        if value is True:
            return "PASS"

        if value is False:
            return "FAIL"

    raw = str(
        data.get(
            string_key,
            "",
        )
    ).strip().upper()

    if raw == "PASS":
        return "PASS"

    if raw == "FAIL":
        return "FAIL"

    return "UNKNOWN"


def choose_one(
    paths,
):
    existing = [
        p
        for p in paths
        if p.exists()
    ]

    if not existing:
        return None

    return sorted(
        existing,
        key=lambda p: (
            p.stat().st_mtime_ns,
            p.name,
        ),
        reverse=True,
    )[0]


def find_outputs(
    out,
):
    resume_pdf = choose_one(
        list(
            out.glob(
                "careerops_resume_*.pdf"
            )
        )
    )

    resume_docx = choose_one(
        list(
            out.glob(
                "careerops_resume_*.docx"
            )
        )
    )

    cover_pdf = choose_one(
        list(
            out.glob(
                "careerops_cover_*.pdf"
            )
        )
    )

    cover_docx = choose_one(
        list(
            out.glob(
                "careerops_cover_*.docx"
            )
        )
    )

    return {
        "resume_pdf":
            resume_pdf,
        "resume_docx":
            resume_docx,
        "cover_pdf":
            cover_pdf,
        "cover_docx":
            cover_docx,
    }


def derive_job_identity(
    runtime,
    existing,
    company_override=None,
    position_override=None,
):
    job = dict(
        existing.get(
            "job",
            {}
        )
    )

    intake = load_json(
        runtime
        / "jd_intake.json"
    ) or {}

    requirements = load_json(
        canonical_ledger_path(runtime)
    ) or {}

    cover_plan = load_json(
        runtime
        / "cover_plan.json"
    ) or {}

    target_job = cover_plan.get(
        "target_job",
        {}
    )

    if not isinstance(
        target_job,
        dict,
    ):
        target_job = {}

    if company_override:
        job["company"] = (
            company_override
        )
    elif target_job.get(
        "company"
    ):
        job["company"] = (
            target_job.get(
                "company"
            )
        )
    else:
        job.setdefault(
            "company",
            None,
        )

    if position_override:
        job["position"] = (
            position_override
        )
    elif target_job.get(
        "position"
    ):
        job["position"] = (
            target_job.get(
                "position"
            )
        )
    elif requirements.get(
        "target_role_title_candidate"
    ):
        job["position"] = (
            requirements.get(
                "target_role_title_candidate"
            )
        )
    else:
        job.setdefault(
            "position",
            None,
        )

    job["source_type"] = (
        intake.get(
            "source_type"
        )
    )

    job["source_name"] = (
        intake.get(
            "source_name"
        )
    )

    job["source_url"] = (
        intake.get(
            "source_url"
        )
    )

    raw_jd = intake.get(
        "raw_jd_text"
    )

    if isinstance(
        raw_jd,
        str,
    ) and raw_jd:
        job["jd_sha256"] = (
            sha256_bytes(
                raw_jd.encode(
                    "utf-8"
                )
            )
        )
    else:
        job["jd_sha256"] = None

    semantic = load_json(
        runtime
        / "jd_semantic_map.json"
    ) or {}

    job[
        "requirements_fingerprint"
    ] = semantic.get(
        "requirements_fingerprint"
    )

    return job


def derive_stage_map(
    runtime,
    out,
    existing_stages,
):
    stages = {}

    for (
        stage,
        artifact_name,
    ) in STAGE_ARTIFACTS:
        path = (
            runtime
            / artifact_name
        )

        old = dict(
            existing_stages.get(
                stage,
                {}
            )
        )

        inferred = (
            "PASS"
            if path.exists()
            else "PENDING"
        )

        explicit = old.get(
            "explicit_status"
        )

        status = (
            explicit
            if explicit
            else inferred
        )

        stages[stage] = {
            **old,
            "status":
                status,
            "artifact":
                artifact_record(
                    path
                ),
        }

    resume_candidate = (
        runtime
        / "generated_resume_content_pair_candidate.json"
    )

    cover_candidate = (
        runtime
        / "generated_cover_letter_pair_candidate.json"
    )

    old_writer = dict(
        existing_stages.get(
            "writer",
            {}
        )
    )

    writer_inferred = (
        "PASS"
        if (
            resume_candidate.exists()
            and cover_candidate.exists()
        )
        else "PENDING"
    )

    writer_status = (
        old_writer.get(
            "explicit_status"
        )
        or writer_inferred
    )

    stages["writer"] = {
        **old_writer,
        "status":
            writer_status,
        "artifacts": {
            "resume_candidate":
                artifact_record(
                    resume_candidate
                ),
            "cover_candidate":
                artifact_record(
                    cover_candidate
                ),
        },
    }

    gate_specs = [

        #
        # STAGE_ARTIFACTS gives this stage its correct deterministic
        # lifecycle position. This gate spec then makes the report's
        # PASS status authoritative rather than treating mere artifact
        # existence as sufficient.
        (
            "requirement_integrity",
            runtime
            / "requirement_integrity_gate.json",
            None,
            "status",
        ),
        (
            "deep_truth_gate",
            runtime
            / "truth_gate.json",
            None,
            "gate",
        ),
        (
            "local_truth_gate",
            runtime
            / "local_truth_gate.json",
            None,
            "gate",
        ),
        (
            "ats_gate",
            runtime
            / "ats_gate.json",
            None,
            "gate",
        ),
        (
            "human_gate",
            runtime
            / "human_gate.json",
            None,
            "gate",
        ),
        (
            "cover_gate",
            runtime
            / "cover_gate_v2_report.json",
            "pass",
            "gate",
        ),
        (
            "interview_defensibility",
            runtime / "interview_defensibility_report.json",
            None,
            "gate",
        ),
        (
            "cover_roundtrip",
            runtime
            / "cover_roundtrip_report.json",
            "pass",
            "gate",
        ),

        (
            "final_application_audit",
            runtime
            / "final_application_audit_report.json",
            "pass",
            "gate",
        ),
    ]

    for (
        stage,
        path,
        boolean_key,
        string_key,
    ) in gate_specs:
        old = dict(
            existing_stages.get(
                stage,
                {}
            )
        )

        inferred = gate_status(
            path,
            boolean_key=boolean_key,
            string_key=string_key,
        )

        explicit = old.get(
            "explicit_status"
        )

        # A gate report is the current artifact authority.
        #
        # A previous explicit FAIL records a historical failed
        # attempt, but must not permanently override a later
        # successful rerun whose current gate artifact says PASS.
        #
        # BLOCKED remains sticky because it represents an
        # intentional lifecycle stop rather than a transient
        # failed gate execution.
        if (
            inferred == "PASS"
            and explicit == "FAIL"
        ):
            old.pop(
                "explicit_status",
                None,
            )

            old.pop(
                "detail",
                None,
            )

            explicit = None

        stages[stage] = {
            **old,
            "status":
                (
                    explicit
                    or inferred
                ),
            "artifact":
                artifact_record(
                    path
                ),
        }

    payload = (
        runtime
        / "career_ops_cv_payload.json"
    )

    old = dict(
        existing_stages.get(
            "resume_payload",
            {}
        )
    )

    stages["resume_payload"] = {
        **old,
        "status":
            (
                old.get(
                    "explicit_status"
                )
                or (
                    "PASS"
                    if payload.exists()
                    else "PENDING"
                )
            ),
        "artifact":
            artifact_record(
                payload
            ),
    }

    outputs = find_outputs(
        out
    )

    old = dict(
        existing_stages.get(
            "resume_render",
            {}
        )
    )

    stages["resume_render"] = {
        **old,
        "status":
            (
                old.get(
                    "explicit_status"
                )
                or (
                    "PASS"
                    if (
                        outputs[
                            "resume_pdf"
                        ]
                        and outputs[
                            "resume_docx"
                        ]
                    )
                    else "PENDING"
                )
            ),
        "artifacts": {
            "pdf":
                artifact_record(
                    outputs[
                        "resume_pdf"
                    ]
                    if outputs[
                        "resume_pdf"
                    ]
                    else (
                        out
                        / "__missing_resume.pdf"
                    )
                ),
            "docx":
                artifact_record(
                    outputs[
                        "resume_docx"
                    ]
                    if outputs[
                        "resume_docx"
                    ]
                    else (
                        out
                        / "__missing_resume.docx"
                    )
                ),
        },
    }

    old = dict(
        existing_stages.get(
            "cover_render",
            {}
        )
    )

    stages["cover_render"] = {
        **old,
        "status":
            (
                old.get(
                    "explicit_status"
                )
                or (
                    "PASS"
                    if (
                        outputs[
                            "cover_pdf"
                        ]
                        and outputs[
                            "cover_docx"
                        ]
                    )
                    else "PENDING"
                )
            ),
        "artifacts": {
            "pdf":
                artifact_record(
                    outputs[
                        "cover_pdf"
                    ]
                    if outputs[
                        "cover_pdf"
                    ]
                    else (
                        out
                        / "__missing_cover.pdf"
                    )
                ),
            "docx":
                artifact_record(
                    outputs[
                        "cover_docx"
                    ]
                    if outputs[
                        "cover_docx"
                    ]
                    else (
                        out
                        / "__missing_cover.docx"
                    )
                ),
        },
    }

    release_report = (
        runtime
        / "pair_release_gate_report.json"
    )

    old = dict(
        existing_stages.get(
            "release",
            {}
        )
    )

    release_data = load_json(
        release_report
    )

    if release_data is None:
        release_inferred = (
            "PENDING"
        )
    elif (
        release_data.get(
            "release_ready"
        )
        is True
    ):
        release_inferred = (
            "PASS"
        )
    elif (
        release_data.get(
            "release_ready"
        )
        is False
    ):
        release_inferred = (
            "FAIL"
        )
    else:
        release_inferred = (
            "UNKNOWN"
        )

    stages["release"] = {
        **old,
        "status":
            (
                old.get(
                    "explicit_status"
                )
                or release_inferred
            ),
        "artifact":
            artifact_record(
                release_report
            ),
    }

    return stages


def derive_resumable_from(
    stages,
):
    for stage in FULL_STAGE_ORDER:
        status = (
            stages.get(
                stage,
                {}
            ).get(
                "status",
                "PENDING",
            )
        )

        if status not in {"PASS", "SKIPPED"}:
            return stage

    return None


def derive_lifecycle_status(
    stages,
    receipt=None,
):
    release = (
        stages.get(
            "release",
            {}
        ).get(
            "status"
        )
    )

    if (receipt or {}).get('decision')=='REJECTED':
        return 'REJECTED'
    blocking=[name for name in FULL_STAGE_ORDER if stages.get(name,{}).get('status') in {'FAIL','BLOCKED'} and name not in {'li_advisory'}]
    if release == "PASS":
        return "NEEDS_ATTENTION" if blocking else "RELEASE_READY"

    if release in {
        "FAIL",
        "BLOCKED",
    }:
        return "RELEASE_BLOCKED"

    for stage in FULL_STAGE_ORDER:
        status = (
            stages.get(
                stage,
                {}
            ).get(
                "status"
            )
        )

        if status in {
            "FAIL",
            "BLOCKED",
        }:
            return "NEEDS_ATTENTION"

    if all(
        stages.get(
            stage,
            {}
        ).get(
            "status"
        )
        in {"PASS", "SKIPPED"}
        for stage in FULL_STAGE_ORDER
    ):
        return "COMPLETE"

    return "IN_PROGRESS"


def discover_artifacts(
    runtime,
    out,
):
    outputs = find_outputs(
        out
    )

    known = {
        "resume_candidate_json":
            runtime
            / "generated_resume_content_pair_candidate.json",

        "cover_candidate_json":
            runtime
            / "generated_cover_letter_pair_candidate.json",

        "career_ops_cv_payload":
            runtime
            / "career_ops_cv_payload.json",

        "local_truth_gate":
            runtime
            / "local_truth_gate.json",

        "ats_gate":
            runtime
            / "ats_gate.json",

        "human_gate":
            runtime
            / "human_gate.json",

        "cover_gate":
            runtime
            / "cover_gate_v2_report.json",

        "cover_roundtrip":
            runtime
            / "cover_roundtrip_report.json",

        "release_report":
            runtime
            / "pair_release_gate_report.json",
    }

    result = {
        key:
            artifact_record(
                path
            )
        for key, path
        in known.items()
    }

    for key, path in outputs.items():
        result[key] = (
            artifact_record(
                path
            )
            if path
            else {
                "exists": False,
                "path": None,
                "sha256": None,
                "size_bytes": None,
            }
        )

    return result


def build_manifest(
    existing,
    *,
    company=None,
    position=None,
):
    run_id = current_run_id()

    if not run_id:
        raise SystemExit(
            "CAREEROPS_RUN_ID is required for run manifests. "
            "Refusing to create a manifest in legacy global runtime."
        )

    runtime = runtime_dir(
        ROOT
    )

    run = run_dir(
        ROOT
    )

    out = output_dir(
        ROOT
    )

    existing = (
        existing
        if isinstance(
            existing,
            dict,
        )
        else {}
    )

    stages = derive_stage_map(
        runtime,
        out,
        existing.get(
            "stages",
            {},
        ),
    )

    execution = dict(
        existing.get(
            "execution",
            {}
        )
    )

    execution.setdefault(
        "target_model",
        None,
    )

    pair = load_json(
        runtime
        / "pair_generation_packet.json"
    ) or {}

    optimization = pair.get(
        "optimization",
        {}
    )

    if (
        isinstance(
            optimization,
            dict,
        )
        and optimization.get(
            "target_model"
        )
    ):
        execution[
            "target_model"
        ] = optimization.get(
            "target_model"
        )

    execution.setdefault(
        "model_calls",
        0,
    )

    execution.setdefault(
        "writer_calls",
        0,
    )

    execution.setdefault(
        "truth_audit_calls",
        0,
    )

    execution.setdefault(
        "writer_model_call_recorded",
        False,
    )

    writer_state = load_json(runtime / 'writer_invocation_state.json')
    if writer_state:
        execution['writer_calls'] = int(writer_state.get('writer_calls', 0))
        execution['writer_model_call_recorded'] = bool(writer_state.get('transport_started'))
        execution['writer_invocation'] = writer_state
        execution['exceptional_writer_retry_calls'] = int(writer_state.get('exceptional_writer_retry_calls',0))

    # Truth Gate V2 records an audit attempt before launching Codex.
    # The artifact is authoritative and makes refresh idempotent.
    audit_state = (
        load_json(
            runtime
            / "truth_gate_audit_state.json"
        )
        or {}
    )

    artifact_audit_calls = int(
        audit_state.get(
            "attempted_calls",
            0,
        )
        or 0
    )

    execution[
        "truth_audit_calls"
    ] = artifact_audit_calls

    # model_calls now means TOTAL model calls for this run,
    # not only pair-writer calls.
    execution[
        "model_calls"
    ] = (
        int(
            execution.get(
                "writer_calls",
                0,
            )
            or 0
        )
        + artifact_audit_calls
    )

    created = (
        existing.get(
            "created_at_utc"
        )
        or now_utc()
    )

    manifest = {
        "schema_version":
            SCHEMA_VERSION,

        "run_id":
            run_id,

        "created_at_utc":
            created,

        "updated_at_utc":
            now_utc(),

        "lifecycle_status":
            derive_lifecycle_status(
                stages,
                load_json(runtime/'job_decision_receipt.json') or {},
            ),

        "resumable_from":
            derive_resumable_from(
                stages
            ),

        "paths": {
            "run":
                relative(
                    run
                ),
            "runtime":
                relative(
                    runtime
                ),
            "output":
                relative(
                    out
                ),
            "manifest":
                relative(
                    run
                    / "manifest.json"
                ),
        },

        "job":
            derive_job_identity(
                runtime,
                existing,
                company_override=company,
                position_override=position,
            ),

        "execution":
            execution,

        "stages":
            stages,

        "artifacts":
            discover_artifacts(
                runtime,
                out,
            ),

        "events":
            list(
                existing.get(
                    "events",
                    [],
                )
            ),
    }

    return manifest


def manifest_path():
    run_id = current_run_id()

    if not run_id:
        raise SystemExit(
            "CAREEROPS_RUN_ID is required."
        )

    return (
        run_dir(
            ROOT
        )
        / "manifest.json"
    )


def load_manifest():
    path = manifest_path()

    if not path.exists():
        return {}

    data = load_json(
        path
    )

    return (
        data
        if isinstance(
            data,
            dict,
        )
        else {}
    )


def cmd_refresh(args):
    path = manifest_path()

    existing = load_manifest()

    manifest = build_manifest(
        existing,
        company=args.company,
        position=args.position,
    )

    atomic_write_json(
        path,
        manifest,
    )

    print_manifest_summary(
        manifest
    )

    return 0


def cmd_mark(args):
    if args.status not in VALID_STATUSES:
        raise SystemExit(
            "Invalid status."
        )

    if args.stage not in FULL_STAGE_ORDER:
        raise SystemExit(
            "Unknown stage: "
            + args.stage
        )

    path = manifest_path()

    existing = load_manifest()

    manifest = build_manifest(
        existing,
        company=args.company,
        position=args.position,
    )

    stage = dict(
        manifest[
            "stages"
        ].get(
            args.stage,
            {}
        )
    )

    stage[
        "explicit_status"
    ] = args.status

    stage[
        "status"
    ] = args.status

    stage[
        "updated_at_utc"
    ] = now_utc()

    if args.detail:
        stage[
            "detail"
        ] = args.detail

    manifest[
        "stages"
    ][
        args.stage
    ] = stage

    if args.model:
        manifest[
            "execution"
        ][
            "target_model"
        ] = args.model

    if (
        args.model_call
        and args.stage
        == "writer"
        and not manifest[
            "execution"
        ].get(
            "writer_model_call_recorded",
            False,
        )
    ):
        manifest[
            "execution"
        ][
            "model_calls"
        ] = (
            int(
                manifest[
                    "execution"
                ].get(
                    "model_calls",
                    0,
                )
            )
            + 1
        )

        manifest[
            "execution"
        ][
            "writer_calls"
        ] = (
            int(
                manifest[
                    "execution"
                ].get(
                    "writer_calls",
                    0,
                )
            )
            + 1
        )

        manifest[
            "execution"
        ][
            "writer_model_call_recorded"
        ] = True

    event = {
        "at_utc":
            now_utc(),

        "stage":
            args.stage,

        "status":
            args.status,

        "detail":
            args.detail,

        "model_call":
            bool(
                args.model_call
            ),

        "model":
            args.model,
    }

    manifest.setdefault(
        "events",
        [],
    ).append(
        event
    )

    manifest[
        "updated_at_utc"
    ] = now_utc()

    manifest[
        "lifecycle_status"
    ] = derive_lifecycle_status(
        manifest[
            "stages"
        ]
    )

    manifest[
        "resumable_from"
    ] = derive_resumable_from(
        manifest[
            "stages"
        ]
    )

    atomic_write_json(
        path,
        manifest,
    )

    print_manifest_summary(
        manifest
    )

    return 0


def cmd_show(args):
    path = manifest_path()

    if not path.exists():
        raise SystemExit(
            "Manifest does not exist: "
            + relative(
                path
            )
        )

    manifest = load_manifest()

    if args.json:
        print(
            json.dumps(
                manifest,
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print_manifest_summary(
            manifest
        )

    return 0


def print_manifest_summary(
    manifest,
):
    print(
        "=" * 88
    )

    print(
        "CAREEROPS RUN MANIFEST"
    )

    print(
        "=" * 88
    )

    print(
        "RUN ID:",
        manifest.get(
            "run_id"
        ),
    )

    print(
        "LIFECYCLE:",
        manifest.get(
            "lifecycle_status"
        ),
    )

    print(
        "RESUMABLE FROM:",
        manifest.get(
            "resumable_from"
        ),
    )

    job = manifest.get(
        "job",
        {},
    )

    print(
        "COMPANY:",
        job.get(
            "company"
        ),
    )

    print(
        "POSITION:",
        job.get(
            "position"
        ),
    )

    execution = manifest.get(
        "execution",
        {},
    )

    print(
        "TARGET MODEL:",
        execution.get(
            "target_model"
        ),
    )

    print(
        "MODEL CALLS:",
        execution.get(
            "model_calls"
        ),
    )

    print(
        "WRITER CALLS:",
        execution.get(
            "writer_calls"
        ),
    )

    print(
        "TRUTH AUDIT CALLS:",
        execution.get(
            "truth_audit_calls"
        ),
    )

    print()

    for stage in FULL_STAGE_ORDER:
        print(
            f"{stage:24}",
            manifest.get(
                "stages",
                {},
            ).get(
                stage,
                {},
            ).get(
                "status",
                "PENDING",
            ),
        )

    print()

    print(
        "MANIFEST:",
        manifest.get(
            "paths",
            {},
        ).get(
            "manifest"
        ),
    )

    print(
        "=" * 88
    )


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Run-local lifecycle and resumability manifest "
            "for the CareerOps Career-Ops engine."
        )
    )

    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )

    refresh = sub.add_parser(
        "refresh"
    )

    refresh.add_argument(
        "--company"
    )

    refresh.add_argument(
        "--position"
    )

    refresh.set_defaults(
        func=cmd_refresh
    )

    mark = sub.add_parser(
        "mark"
    )

    mark.add_argument(
        "--stage",
        required=True,
        choices=FULL_STAGE_ORDER,
    )

    mark.add_argument(
        "--status",
        required=True,
        choices=sorted(
            VALID_STATUSES
        ),
    )

    mark.add_argument(
        "--detail"
    )

    mark.add_argument(
        "--company"
    )

    mark.add_argument(
        "--position"
    )

    mark.add_argument(
        "--model"
    )

    mark.add_argument(
        "--model-call",
        action="store_true",
    )

    mark.set_defaults(
        func=cmd_mark
    )

    show = sub.add_parser(
        "show"
    )

    show.add_argument(
        "--json",
        action="store_true",
    )

    show.set_defaults(
        func=cmd_show
    )

    return parser


def main():
    parser = build_parser()

    args = parser.parse_args()

    raise SystemExit(
        args.func(
            args
        )
    )


if __name__ == "__main__":
    main()
