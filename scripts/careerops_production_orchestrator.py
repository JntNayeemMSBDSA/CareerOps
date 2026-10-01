#!/usr/bin/env python3

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import careerops_failure_classifier as failure_classifier


ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable)

RUNS = (
    ROOT
    / "data"
    / "careerops-engine"
    / "runs"
)

TEMPLATE = (
    ROOT
    / "templates"
    / "careerops"
    / "cv-template.careerops-locked.html"
)


DETERMINISTIC_STAGES = [
    (
        "requirements",
        "scripts/careerops_extract_requirements.py",
        "jd_requirements.json",
    ),
    (
        "requirement_integrity",
        "scripts/careerops_requirement_integrity_gate.py",
        "requirement_integrity_gate.json",
    ),
    (
        "routing",
        "scripts/careerops_route_role.py",
        "role_routing.json",
    ),
    (
        "semantics",
        "scripts/careerops_expand_jd_semantics.py",
        "jd_semantic_map.json",
    ),
    (
        "entities",
        "scripts/careerops_resolve_entities.py",
        "candidate_entities.json",
    ),
    (
        "evidence_map",
        "scripts/careerops_map_evidence.py",
        "requirement_evidence_map.json",
    ),
    (
        "constraints",
        "scripts/careerops_validate_constraints.py",
        "constraint_validation.json",
    ),
    (
        "experience_selection",
        "scripts/careerops_select_experience.py",
        "experience_selection.json",
    ),
    (
        "project_selection",
        "scripts/careerops_select_projects.py",
        "project_selection.json",
    ),
    (
        "skills",
        "scripts/careerops_build_skills.py",
        "technical_skills_plan.json",
    ),
    (
        "summary",
        "scripts/careerops_route_summary.py",
        "summary_route.json",
    ),
]


PAIR_ARTIFACTS = [
    "resume_generation_spec.json",
    "cover_plan.json",
    "compact_generation_packet.json",
    "pair_generation_packet.json",
]


STOP_CHOICES = [
    "pair_packet",
    "writer",
    "gates",
    "render",
    "release",
]


def slug(value, limit=55):
    text = re.sub(
        r"[^a-z0-9]+",
        "_",
        str(value or "").casefold(),
    ).strip("_")

    text = text[:limit].strip("_")

    return text or "job"


def generated_run_id(
    company,
    position,
):
    stamp = (
        datetime.now(timezone.utc)
        .strftime("%Y%m%dT%H%M%SZ")
    )

    return (
        "production_"
        + stamp
        + "_"
        + slug(company, 32)
        + "_"
        + slug(position, 42)
    )


def read_json(path):
    try:
        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return None


def clean_run_env(run_id):
    env = os.environ.copy()
    for key in ['CAREEROPS_RUNTIME_DIR', 'CAREEROPS_OUTPUT_DIR', 'CAREEROPS_RESUME_INPUT', 'CAREEROPS_RESUME_OUTPUT', 'CAREEROPS_CV_PAYLOAD_OUTPUT', 'CAREEROPS_CV_PAYLOAD_VALIDATION_OUTPUT', 'CAREEROPS_JOB_COMPANY', 'CAREEROPS_JOB_POSITION', 'CAREER_OPS_PDF_INDEX']:
        env.pop(key, None)
    env['CAREEROPS_RUN_ID'] = run_id
    from careerops_production_configuration import apply
    return apply(env)


def run_command(
    title,
    command,
    env,
    *,
    allowed=(0,),
):
    print()
    print(
        "=" * 96
    )
    print(title)
    print(
        "=" * 96
    )

    print(
        "COMMAND:",
        " ".join(
            str(x)
            for x in command
        ),
    )

    from careerops_capability_trace import observe_command
    trace_id = observe_command(env.get("CAREEROPS_RUN_ID"), title, command, "STARTED", env=env, root=ROOT)
    result = subprocess.run(
        [
            str(x)
            for x in command
        ],
        cwd=ROOT,
        env=env,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    child_output = getattr(result, "stdout", None) or ""
    if child_output:
        print(child_output, end="" if child_output.endswith("\n") else "\n")
    if result.returncode not in allowed and env.get("CAREEROPS_RUN_ID"):
        failure_path = runtime_path(env["CAREEROPS_RUN_ID"])/"last_process_error.json"
        failure_path.parent.mkdir(parents=True, exist_ok=True)
        owners = [str(value) for value in command if str(value).endswith((".py", ".mjs"))]
        failure_path.write_text(json.dumps({"run_id":env["CAREEROPS_RUN_ID"], "return_code":result.returncode,
            "title":title, "owner_paths":owners, "output_tail":child_output[-12000:],
            "recorded_at_utc":datetime.now(timezone.utc).isoformat()}, indent=2)+"\n")
    observe_command(env.get("CAREEROPS_RUN_ID"), title, command, "COMPLETED",
                    return_code=result.returncode, env=env, root=ROOT, invocation_id=trace_id)
    print(
        "RC:",
        result.returncode,
    )

    return (
        result.returncode
        in allowed
    ), result.returncode


def manifest_path(run_id):
    return (
        RUNS
        / run_id
        / "manifest.json"
    )


def runtime_path(run_id):
    return (
        RUNS
        / run_id
        / "runtime"
    )


def output_path(run_id):
    return (
        RUNS
        / run_id
        / "output"
    )


def load_manifest(run_id):
    path = manifest_path(
        run_id
    )

    if not path.exists():
        return {}

    return (
        read_json(path)
        or {}
    )


def stage_status(
    run_id,
    stage,
):
    manifest = load_manifest(
        run_id
    )

    return (
        manifest
        .get(
            "stages",
            {}
        )
        .get(
            stage,
            {}
        )
        .get(
            "status"
        )
    )


def refresh_manifest(
    run_id,
    company,
    position,
    env,
):
    ok, rc = run_command(
        "MANIFEST REFRESH",
        [
            PYTHON,
            ROOT
            / "scripts"
            / "careerops_run_manifest.py",
            "refresh",
            "--company",
            company,
            "--position",
            position,
        ],
        env,
    )

    if not ok:
        raise SystemExit(
            "Manifest refresh failed "
            f"with RC {rc}."
        )


def mark_manifest(
    run_id,
    company,
    position,
    env,
    stage,
    status,
    *,
    detail=None,
    model=None,
    model_call=False,
):
    command = [
        PYTHON,
        ROOT
        / "scripts"
        / "careerops_run_manifest.py",
        "mark",
        "--stage",
        stage,
        "--status",
        status,
        "--company",
        company,
        "--position",
        position,
    ]

    if detail:
        command.extend([
            "--detail",
            detail,
        ])

    if model:
        command.extend([
            "--model",
            model,
        ])

    if model_call:
        command.append(
            "--model-call"
        )

    ok, rc = run_command(
        f"MANIFEST MARK: {stage} -> {status}",
        command,
        env,
    )

    if not ok:
        raise SystemExit(
            "Manifest mark failed "
            f"with RC {rc}."
        )


FAILURE_REPORT_BY_STAGE = {
    "requirement_integrity":
        "requirement_integrity_gate.json",

    "local_truth_gate":
        "local_truth_gate.json",

    "deep_truth_gate":
        "truth_gate.json",

    "truth_gate":
        "truth_gate.json",

    "ats_gate":
        "ats_gate.json",

    "human_gate":
        "human_gate.json",

    "cover_gate":
        "cover_gate_v2_report.json",
}


def classify_failure_event(
    run_id,
    stage,
    detail,
    *,
    return_code=None,
    artifact=None,
    report_path=None,
    writing_defect_confirmed=False,
):
    runtime = runtime_path(
        run_id
    )

    runtime.mkdir(
        parents=True,
        exist_ok=True,
    )

    normalized_stage = (
        failure_classifier
        .normalize_stage(
            stage
        )
    )

    resolved_report_path = None

    if report_path:
        resolved_report_path = Path(
            report_path
        )

    elif normalized_stage in (
        FAILURE_REPORT_BY_STAGE
    ):
        candidate = (
            runtime
            / FAILURE_REPORT_BY_STAGE[
                normalized_stage
            ]
        )

        if candidate.exists():
            resolved_report_path = (
                candidate
            )

    report = None
    report_read_error = None

    if (
        resolved_report_path
        and resolved_report_path.exists()
    ):
        try:
            loaded = json.loads(
                resolved_report_path
                .read_text(
                    encoding="utf-8"
                )
            )

            if isinstance(
                loaded,
                dict,
            ):
                report = loaded

        except Exception as exc:
            report_read_error = (
                f"{type(exc).__name__}: "
                f"{exc}"
            )

    artifact_value = artifact

    if (
        artifact_value is None
        and resolved_report_path
    ):
        artifact_value = str(
            resolved_report_path
        )

    try:
        result = (
            failure_classifier
            .classify_failure(
                stage=stage,
                artifact=artifact_value,
                message=detail,
                return_code=return_code,
                report=report,
                writing_defect_confirmed=(
                    writing_defect_confirmed
                ),
            )
        )

    except Exception as exc:
        result = {
            "schema_version":
                "career-ops-failure-classification-v1",

            "classification_status":
                "UNRESOLVED_FAIL_CLOSED",

            "failure_class":
                None,

            "classification_source":
                "CLASSIFIER_EXCEPTION_FAIL_CLOSED",

            "stage":
                str(
                    stage or ""
                ),

            "normalized_stage":
                normalized_stage,

            "artifact":
                (
                    str(
                        artifact_value
                    )
                    if artifact_value
                    else None
                ),

            "return_code":
                return_code,

            "response":
                "BLOCK_UNCLASSIFIED_FAILURE",

            "deterministic_repair_permitted":
                False,

            "block_if_unrepaired":
                True,

            "writing_defect_confirmed":
                bool(
                    writing_defect_confirmed
                ),

            "second_writer_call_permitted":
                False,

            "automatic_writer_retry":
                False,

            "classifier_exception":
                (
                    f"{type(exc).__name__}: "
                    f"{exc}"
                ),

            "model_calls":
                0,
        }

    from careerops_deterministic_repair_dispatcher import plan_for_failure
    result["repair_dispatch"] = plan_for_failure(stage, report, result)

    process_error = runtime/"last_process_error.json"
    if process_error.is_file():
        captured = read_json(process_error) or {}
        if captured.get("run_id")==run_id:
            result["process_error_evidence"] = {"path":str(process_error),
                "sha256":__import__("hashlib").sha256(process_error.read_bytes()).hexdigest()}

    record = dict(
        result
    )

    record[
        "run_id"
    ] = run_id

    record[
        "recorded_at_utc"
    ] = datetime.now(
        timezone.utc
    ).isoformat()

    record[
        "detail"
    ] = detail

    if report_read_error:
        record[
            "report_read_error"
        ] = report_read_error

    current = (
        runtime
        / "failure_classification.json"
    )

    history = (
        runtime
        / "failure_classification_history.jsonl"
    )

    current.write_text(
        json.dumps(
            record,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    with history.open(
        "a",
        encoding="utf-8",
    ) as handle:
        handle.write(
            json.dumps(
                record,
                ensure_ascii=False,
            )
            + "\n"
        )

    print()
    print(
        "FAILURE CLASSIFICATION:",
        record.get(
            "failure_class"
        )
        or "UNRESOLVED_FAIL_CLOSED",
    )

    print(
        "CLASSIFICATION STATUS:",
        record.get(
            "classification_status"
        ),
    )

    print(
        "ALLOWED RESPONSE:",
        record.get(
            "response"
        ),
    )

    print(
        "SECOND WRITER CALL PERMITTED:",
        record.get(
            "second_writer_call_permitted"
        ),
    )

    print(
        "AUTOMATIC WRITER RETRY:",
        record.get(
            "automatic_writer_retry"
        ),
    )

    return record


def fail_stage(
    run_id,
    company,
    position,
    env,
    stage,
    detail,
    return_code=None,
    artifact=None,
    report_path=None,
):
    classify_failure_event(
        run_id,
        stage,
        detail,
        return_code=return_code,
        artifact=artifact,
        report_path=report_path,
        writing_defect_confirmed=False,
    )

    try:
        mark_manifest(
            run_id,
            company,
            position,
            env,
            stage,
            "FAIL",
            detail=detail,
        )

    except Exception:
        pass

    raise SystemExit(
        detail
    )

def should_skip(run_id, stage, resume_mode):
    if not resume_mode or stage_status(run_id,stage) != 'PASS':return False
    owner_map={stage:[script] for stage,script,_ in DETERMINISTIC_STAGES if stage not in ('requirements','requirement_integrity')}
    owner_map.update({'pair_packet':['scripts/careerops_build_pair_packet.py'],'deep_truth_gate':['scripts/careerops_truth_gate.py','scripts/careerops_local_truth_gate.py'],'ats_gate':['scripts/careerops_ats_gate_v2.py'],'human_gate':['scripts/careerops_human_gate_v22.py'],'cover_gate':['scripts/careerops_cover_gate_v2.py'],'resume_render':['scripts/careerops_adaptive_layout.mjs','scripts/careerops_docx_renderer.py'],'cover_render':['scripts/careerops_render_cover_docx.py','scripts/careerops_render_cover.mjs']})
    event_path=runtime_path(run_id)/'capability_invocations.jsonl'
    events=[json.loads(line) for line in event_path.read_text().splitlines() if line.strip()] if event_path.is_file() else []
    for filename in owner_map.get(stage,[]):
        owner=ROOT/filename
        completed=[e for e in events if e.get('owner_path')==str(owner) and e.get('phase')=='COMPLETED' and e.get('return_code')==0]
        if completed and completed[-1].get('owner_sha256')!=__import__('hashlib').sha256(owner.read_bytes()).hexdigest():
            print('REGENERATE CHANGED OWNER:',stage,filename)
            return False
    bound_artifacts={'routing':'role_routing.json','semantics':'jd_semantic_map.json','evidence_map':'requirement_evidence_map.json','constraints':'constraint_validation.json','experience_selection':'experience_selection.json','project_selection':'project_selection.json','skills':'technical_skills_plan.json','summary':'summary_route.json','resume_spec':'resume_generation_spec.json','compact_packet':'compact_generation_packet.json','pair_packet':'pair_generation_packet.json','ats_gate':'ats_gate.json','human_gate':'human_gate.json','cover_gate':'cover_gate_v2_report.json'}
    if stage in bound_artifacts:
        from careerops_requirement_authority import check_artifact
        try:check_artifact(runtime_path(run_id),bound_artifacts[stage],require_stamp=True)
        except RuntimeError as exc:
            if str(exc).startswith('REQUIREMENT_AUTHORITY_DRIFT:') or str(exc).startswith('Missing required current-job artifact:'):
                print('REGENERATE STALE OWNER:',stage)
                return False
            raise
    return True


def require_scripts():
    required = [
        "scripts/careerops_ingest_jd.py",
        "scripts/careerops_failure_classifier.py",
        "scripts/careerops_extract_requirements.py",
        "scripts/careerops_requirement_integrity_gate.py",
        "scripts/careerops_route_role.py",
        "scripts/careerops_expand_jd_semantics.py",
        "scripts/careerops_resolve_entities.py",
        "scripts/careerops_map_evidence.py",
        "scripts/careerops_validate_constraints.py",
        "scripts/careerops_select_experience.py",
        "scripts/careerops_select_projects.py",
        "scripts/careerops_build_skills.py",
        "scripts/careerops_route_summary.py",
        "scripts/careerops_build_pair_packet.py",
        "scripts/careerops_generate_pair.py",
        "scripts/careerops_truth_gate.py",
        "scripts/careerops_local_truth_gate.py",
        "scripts/careerops_ats_gate_v2.py",
        "scripts/careerops_human_gate_v22.py",
        "scripts/careerops_cover_gate_v2.py",
        "scripts/careerops_repair_cover_candidate.py",
        "scripts/careerops_build_cv_payload.py",
        "scripts/careerops_docx_renderer.py",
        "scripts/careerops_resume_roundtrip.py",
        "scripts/careerops_final_application_audit.py",
        "scripts/careerops_adaptive_layout.mjs",
        "scripts/careerops_render_cover.mjs",
        "scripts/careerops_render_cover_docx.py",
        "scripts/careerops_cover_roundtrip.py",
        "scripts/careerops_pair_release_gate.py",
        "scripts/careerops_run_manifest.py",
        "build-cv-html.mjs",
        "generate-pdf.mjs",
        "templates/careerops/cv-template.careerops-locked.html",
        "templates/careerops/cover-letter.careerops.html",
    ]

    missing = [
        rel
        for rel in required
        if not (
            ROOT / rel
        ).exists()
    ]

    if missing:
        raise SystemExit(
            "Missing orchestrator dependencies:\n"
            + "\n".join(
                missing
            )
        )

    if not PYTHON.exists():
        raise SystemExit(
            "Missing virtualenv Python: "
            + str(PYTHON)
        )


def self_test():
    require_scripts()

    manifest_source = (
        ROOT
        / "scripts"
        / "careerops_run_manifest.py"
    ).read_text(
        encoding="utf-8"
    )

    release_source = (
        ROOT
        / "scripts"
        / "careerops_pair_release_gate.py"
    ).read_text(
        encoding="utf-8"
    )

    writer_source = (
        ROOT
        / "scripts"
        / "careerops_generate_pair.py"
    ).read_text(
        encoding="utf-8"
    )

    checks = {
        "deterministic_stage_count":
            len(
                DETERMINISTIC_STAGES
            )
            == 11,

        "pair_builder_exists":
            (
                ROOT
                / "scripts"
                / "careerops_build_pair_packet.py"
            ).exists(),

        "manifest_model_call_flag":
            "--model-call"
            in manifest_source,

        "manifest_resumability":
            "derive_resumable_from"
            in manifest_source,

        "writer_pair_candidate_resume":
            (
                "generated_resume_content_pair_candidate.json"
                in writer_source
            ),

        "writer_pair_candidate_cover":
            (
                "generated_cover_letter_pair_candidate.json"
                in writer_source
            ),

        "release_gate_v2":
            (
                "careerops-pair-release-gate-v2"
                in release_source
            ),

        "release_gate_run_local":
            (
                "all_release_artifacts_run_local"
                in release_source
            ),

        "locked_resume_template":
            TEMPLATE.exists(),
    }

    print(
        "=" * 88
    )
    print(
        "CAREEROPS PRODUCTION ORCHESTRATOR SELF-TEST"
    )
    print(
        "=" * 88
    )

    for name, ok in checks.items():
        print(
            name,
            "=",
            "PASS"
            if ok
            else "FAIL",
        )

    if not all(
        checks.values()
    ):
        return 1

    print()
    print(
        "ORCHESTRATOR STATIC CONTRACT: PASS"
    )
    print(
        "MODEL CALLS: 0"
    )

    return 0


def prepare_input(
    args,
    run_id,
    run_root,
):
    if args.resume_run:
        return None

    if bool(
        args.jd_file
    ) == bool(
        args.jd_text
    ):
        raise SystemExit(
            "For a new run provide exactly one of "
            "--jd-file or --jd-text."
        )

    stored = (
        run_root
        / "input_jd.txt"
    )

    if args.jd_file:
        source = Path(
            args.jd_file
        ).expanduser().resolve()

        if not source.exists():
            raise SystemExit(
                "JD file does not exist: "
                + str(source)
            )

        shutil.copy2(
            source,
            stored,
        )

    else:
        stored.write_text(
            args.jd_text.strip()
            + "\n",
            encoding="utf-8",
        )

    return stored


def try_semantic_requirement_repair(run_id, env, *, company=None, position=None):
    """Opt-in candidate seam; original deterministic gate retains authority."""
    if str(env.get('CAREEROPS_SEMANTIC_CHALLENGER', '')).strip().casefold() not in {'1', 'true', 'yes', 'on'}:
        return False
    from careerops_semantic_challenger_runtime import attempt
    from careerops_capability_trace import observe_command
    semantic_owner = [ROOT / 'scripts/careerops_semantic_challenger_runtime.py']
    trace_id = observe_command(run_id, 'SEMANTIC CHALLENGER', semantic_owner, 'STARTED', env=env, root=ROOT)
    try:
        timeout = max(1, min(int(env.get('CAREEROPS_LI_ADVISORY_TIMEOUT', '90')), 180))
        report = attempt(runtime_path(run_id), run_id, timeout=timeout, endpoint=env.get('CAREEROPS_LI_OLLAMA_ENDPOINT'), company=company, position=position)
    except Exception as exc:
        observe_command(run_id, 'SEMANTIC CHALLENGER', semantic_owner, 'COMPLETED', return_code=2, env=env, root=ROOT, invocation_id=trace_id)
        print('SEMANTIC CHALLENGER: UNRESOLVED_FAIL_CLOSED', type(exc).__name__, str(exc))
        return False
    observe_command(run_id, 'SEMANTIC CHALLENGER', semantic_owner, 'COMPLETED', return_code=0 if report.get('status') == 'RECONSTRUCTED_REVALIDATED' else 2, env=env, root=ROOT, invocation_id=trace_id)
    print('SEMANTIC CHALLENGER:', report.get('status'))
    if report.get('status') == 'RECONSTRUCTED_REVALIDATED':
        return True
    if env.get('CAREEROPS_SHARED_SOL_SEMANTIC') == '1' and env.get('CAREEROPS_SHARED_SEMANTIC_DEFER') != '1':
        from careerops_automatic_semantic_escalation import automatic_batch
        result = automatic_batch([run_id])
        return run_id in result.get('continued_runs', [])
    return False


def run_deterministic(args, run_id, company, position, env, jd_file, resume_mode):
    runtime = runtime_path(run_id)
    if not should_skip(run_id, 'ingest', resume_mode):
        if jd_file is None:
            raise SystemExit('Run is not past ingest and no stored JD input was supplied.')
        manual_ingest_needed = True
        url_probe_status = None
        url_probe_rc = None
        url_probe_saved = False
        if args.url_first:
            if not args.application_url:
                fail_stage(run_id, company, position, env, 'ingest', '--url-first requires --application-url.')
            probe_ok, url_probe_rc = run_command('STAGE: URL-FIRST JD INGEST PROBE', [PYTHON, ROOT / 'scripts' / 'careerops_ingest_jd.py', '--url', args.application_url], env, allowed=(0, 3))
            if not probe_ok:
                fail_stage(run_id, company, position, env, 'ingest', f'URL-first ingestion failed unexpectedly with RC {url_probe_rc}.')
            probe_path = runtime / 'jd_intake.json'
            probe = read_json(probe_path) or {}
            url_probe_status = probe.get('status')
            if probe_path.exists():
                shutil.copy2(probe_path, runtime / 'url_probe_jd_intake.json')
                url_probe_saved = True
            if url_probe_rc == 0 and url_probe_status == 'INGESTED':
                manual_ingest_needed = False
                print()
                print('URL-FIRST RESULT: INGESTED')
                print('MANUAL JD FALLBACK: NOT NEEDED')
            elif url_probe_rc == 3 and url_probe_status == 'NEEDS_MANUAL_JD':
                manual_ingest_needed = True
                print()
                print('URL-FIRST RESULT: NEEDS_MANUAL_JD')
                print('MANUAL JD FALLBACK: ACTIVATED')
            else:
                fail_stage(run_id, company, position, env, 'ingest', f'URL-first ingestion returned an unexpected status/RC combination: status={url_probe_status!r}, rc={url_probe_rc}.')
        if manual_ingest_needed:
            command = [PYTHON, ROOT / 'scripts' / 'careerops_ingest_jd.py', '--file', jd_file]
            if args.application_url:
                command.extend(['--application-url', args.application_url])
            ok, rc = run_command('STAGE: MANUAL JD FALLBACK' if args.url_first else 'STAGE: INGEST', command, env)
            if not ok:
                fail_stage(run_id, company, position, env, 'ingest', f'Manual JD ingestion failed with RC {rc}.')
        final_intake_path = runtime / 'jd_intake.json'
        final_intake = read_json(final_intake_path) or {}
        if final_intake.get('status') != 'INGESTED':
            fail_stage(run_id, company, position, env, 'ingest', 'Final JD authority is not INGESTED.')
        resolution = {'schema_version': 'careerops-intake-resolution-v1', 'url_first': bool(args.url_first), 'application_url': args.application_url, 'url_probe_rc': url_probe_rc, 'url_probe_status': url_probe_status, 'url_probe_saved': url_probe_saved, 'manual_fallback_used': bool(args.url_first and manual_ingest_needed), 'final_status': final_intake.get('status'), 'final_source_type': final_intake.get('source_type'), 'final_source_url': final_intake.get('source_url'), 'resolved_at_utc': datetime.now(timezone.utc).isoformat()}
        (runtime / 'intake_resolution.json').write_text(json.dumps(resolution, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        refresh_manifest(run_id, company, position, env)
    else:
        print('SKIP ingest: manifest already PASS')
    for stage, rel_script, artifact in DETERMINISTIC_STAGES:
        if should_skip(run_id, stage, resume_mode):
            print(f'SKIP {stage}: manifest already PASS')
            continue
        ok, rc = run_command(f'STAGE: {stage}', [PYTHON, ROOT / rel_script], env)
        if not ok and stage == 'requirement_integrity':
            ok = try_semantic_requirement_repair(run_id, env, company=company, position=position)
        if not ok:
            fail_stage(run_id, company, position, env, stage, f'{stage} failed with RC {rc}.')
        if not (runtime / artifact).exists():
            fail_stage(run_id, company, position, env, stage, f'{stage} returned success but {artifact} is missing.')
        refresh_manifest(run_id, company, position, env)
    if not should_skip(run_id, 'pair_packet', resume_mode):
        ok, rc = run_command('STAGE: PAIR PACKET', [PYTHON, ROOT / 'scripts' / 'careerops_build_pair_packet.py', '--company', company, '--position', position], env)
        if not ok:
            fail_stage(run_id, company, position, env, 'pair_packet', f'Pair packet build failed with RC {rc}.')
        missing = [name for name in PAIR_ARTIFACTS if not (runtime / name).exists()]
        if missing:
            fail_stage(run_id, company, position, env, 'pair_packet', 'Pair build returned success but artifacts are missing: ' + ', '.join(missing))
        if stage_status(run_id, 'pair_packet') == 'FAIL':
            mark_manifest(run_id, company, position, env, 'pair_packet', 'PASS', detail='Deterministic packet owner rerun succeeded; all required artifacts verified.')
        refresh_manifest(run_id, company, position, env)
    else:
        print('SKIP pair_packet: manifest already PASS')



def unresolved_hard_constraint_ids(
    run_id,
):
    data = (
        read_json(
            runtime_path(
                run_id
            )
            / "experience_selection.json"
        )
        or {}
    )

    raw = (
        data.get(
            "residual_gaps",
            {},
        ).get(
            "unresolved_hard_constraint_ids",
            [],
        )
        or []
    )

    return sorted({
        str(value)
        for value in raw
        if value
    })


def _enforce_pre_writer_constraint_gate_strict(
    run_id,
    company,
    position,
    env,
):
    from careerops_job_decision_receipt import (
        build_receipt,
        load_optional,
        print_receipt,
    )

    runtime = runtime_path(
        run_id
    )

    receipt = build_receipt(
        load_optional(
            runtime
            / "jd_requirements.json"
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

    receipt_path = (
        runtime
        / "job_decision_receipt.json"
    )

    receipt_path.write_text(
        json.dumps(
            receipt,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    print()

    print_receipt(
        receipt
    )

    unresolved = (
        unresolved_hard_constraint_ids(
            run_id
        )
    )

    decision = receipt.get(
        "decision"
    )

    if (
        decision == "CONTINUE"
        and unresolved
    ):
        decision = (
            "NEEDS_ATTENTION"
        )

        receipt[
            "decision"
        ] = decision

        receipt[
            "decision_class"
        ] = (
            "LEGACY_UNRESOLVED_CONSTRAINT_SAFETY_NET"
        )

        receipt[
            "reason"
        ] = (
            "Legacy deterministic selection still reports unresolved "
            "mandatory constraints. Writer remains blocked."
        )

        receipt_path.write_text(
            json.dumps(
                receipt,
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    if decision == "CONTINUE":
        print()

        print(
            "PRE-WRITER DECISION GATE: PASS"
        )

        return

    detail = (
        f"{decision}: "
        + str(
            receipt.get(
                "reason"
            )
            or "pre-writer decision blocked"
        )
    )

    classification = classify_failure_event(
        run_id,
        "constraint_validation",
        detail,
        artifact=(
            runtime
            / "constraint_validation.json"
        ),
        writing_defect_confirmed=False,
    )

    if (
        classification.get(
            "second_writer_call_permitted"
        )
        is True
    ):
        print(
            "PRE-WRITER DECISION CLASSIFICATION: FAIL CLOSED"
        )

    mark_manifest(
        run_id,
        company,
        position,
        env,
        "writer",
        "BLOCKED",
        detail=detail,
    )

    refresh_manifest(
        run_id,
        company,
        position,
        env,
    )

    print()
    print(
        "=" * 96
    )

    print(
        "PRE-WRITER DECISION GATE:",
        decision,
    )

    for row in (
        receipt.get(
            "requirements",
            [],
        )
        or []
    ):
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
            "WHY:",
            row.get(
                "deterministic_reason"
            ),
        )

    print(
        "MODEL WRITER CALLS: 0"
    )

    print(
        "=" * 96
    )

    raise SystemExit(
        2
    )

def _override_stage_status(
    manifest,
    stage,
):
    value = (
        manifest.get(
            "stages",
            {},
        )
        .get(
            stage
        )
    )

    if isinstance(
        value,
        dict,
    ):
        return value.get(
            "status"
        )

    return value


def _write_override_json(
    path,
    payload,
):
    path = Path(
        path
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tmp = path.with_name(
        path.name
        + ".tmp"
    )

    tmp.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    os.replace(
        tmp,
        path,
    )


def _normalize_user_generation_override_args(
    args,
    resume_mode,
):
    requested = bool(
        getattr(
            args,
            "user_override_generate",
            False,
        )
    )

    reason = str(
        getattr(
            args,
            "override_reason",
            "",
        )
        or ""
    ).strip()

    if (
        reason
        and not requested
    ):
        raise SystemExit(
            "--override-reason requires "
            "--user-override-generate."
        )

    if not requested:
        return args

    if not resume_mode:
        raise SystemExit(
            "User override generation is resume-only. "
            "Run CareerOps normally first so the automatic "
            "decision/failure is preserved, then explicitly "
            "resume that run with the override."
        )

    if not reason:
        raise SystemExit(
            "User override generation requires a non-empty "
            "--override-reason."
        )

    # The override lane deliberately stops immediately after
    # the run's one writer stage. All unreleased rendering is
    # performed separately in an isolated override workspace.
    args.stop_after = (
        "writer"
    )

    args.override_reason = (
        reason
    )

    return args


def _authorize_user_generation_override(
    run_id,
    override_reason,
):
    reason = str(
        override_reason
        or ""
    ).strip()

    if not reason:
        raise SystemExit(
            "User override reason is empty."
        )

    manifest = load_manifest(
        run_id
    )

    lifecycle_status = (
        manifest.get(
            "lifecycle_status"
        )
        or manifest.get(
            "lifecycle"
        )
    )

    if (
        lifecycle_status
        == "RELEASE_READY"
    ):
        raise SystemExit(
            "This run is already RELEASE_READY; "
            "override generation is unnecessary."
        )

    execution = (
        manifest.get(
            "execution"
        )
        or {}
    )

    model_calls = int(
        execution.get(
            "model_calls",
            0,
        )
        or 0
    )

    writer_calls = int(
        execution.get(
            "writer_calls",
            0,
        )
        or 0
    )

    writer_status = (
        _override_stage_status(
            manifest,
            "writer",
        )
    )

    runtime = runtime_path(
        run_id
    )

    receipt = (
        read_json(
            runtime
            / "job_decision_receipt.json"
        )
        or {}
    )

    failure = (
        read_json(
            runtime
            / "failure_classification.json"
        )
        or {}
    )

    unresolved = (
        unresolved_hard_constraint_ids(
            run_id
        )
    )

    resume_candidate = (
        runtime
        / "generated_resume_content_pair_candidate.json"
    )

    cover_candidate = (
        runtime
        / "generated_cover_letter_pair_candidate.json"
    )

    from careerops_requirement_authority import check_artifact, authority
    from careerops_generate_pair import build_current_job_contract
    from careerops_overall_override import blockers
    if blockers(runtime):raise SystemExit('Irreducible eligibility hard block: override unavailable.')
    integrity=read_json(runtime/'requirement_integrity_gate.json') or {}
    if integrity.get('status') != 'PASS':
        raise SystemExit('Override requires a current passing independent Requirement Integrity gate.')
    packet=check_artifact(runtime,'pair_generation_packet.json',require_stamp=True)
    build_current_job_contract(read_json(runtime/'resume_generation_spec.json') or {},packet)
    current_authority,_=authority(runtime)
    state=read_json(runtime/'writer_invocation_state.json') or {}
    max_writer_calls=1
    if writer_calls == 0:
        if lifecycle_status not in {'REJECTED','NEEDS_ATTENTION'} and writer_status != 'FAIL':
            raise SystemExit('First-writer override requires a preserved automatic rejection or failed run.')
        mode='TRUTHFUL_CURRENT_PACKET_FIRST_WRITER_ALLOWED'
        writer_policy='EXACTLY_ONE_FIRST_WRITER_CALL_ALLOWED'
    elif writer_status == 'PASS' and resume_candidate.is_file() and cover_candidate.is_file():
        if writer_calls > 2 or (writer_calls==2 and state.get('exceptional_writer_retry_calls')!=1):
            raise SystemExit('Writer call bound exceeded; cannot reuse an unclassified repeated writer.')
        mode='POST_WRITER_FAILURE_REUSE_EXISTING_PAIR'
        writer_policy='REUSE_ONLY_SECOND_WRITER_FORBIDDEN'
        max_writer_calls=writer_calls
    elif (writer_calls == 1 and state.get('transport_started') and state.get('transport_completed')
          and state.get('model_completed') is False and not (resume_candidate.is_file() and cover_candidate.is_file())):
        if os.environ.get('CAREEROPS_ALLOW_EXCEPTIONAL_WRITER_RETRY') != '1' or os.environ.get('CAREEROPS_RETRY_CAPACITY_CONFIRMED') != '1':
            raise SystemExit('Failed transport retry requires explicit CAREEROPS_ALLOW_EXCEPTIONAL_WRITER_RETRY=1 and CAREEROPS_RETRY_CAPACITY_CONFIRMED=1 in addition to the user override and reason.')
        mode='EXPLICIT_FAILED_TRANSPORT_ONE_RETRY_ALLOWED'
        writer_policy='EXACTLY_ONE_ADDITIONAL_TRANSPORT_CALL_MAX_TOTAL_TWO'
        max_writer_calls=2
    else:
        raise SystemExit('No valid pair to reuse and no eligible explicitly bounded failed-transport retry.')

    authorization = {
        "schema_version":
            "career-ops-user-generation-override-authorization-v2",

        "created_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "status":
            "AUTHORIZED",

        "authority":
            "EXPLICIT_USER",

        "run_id":
            run_id,

        "user_reason":
            reason,

        "mode":
            mode,
        "max_total_writer_calls": max_writer_calls,
        "current_requirement_authority": current_authority,
        "writer_receipt_sha256": __import__('hashlib').sha256((runtime/'writer_invocation_state.json').read_bytes()).hexdigest() if (runtime/'writer_invocation_state.json').is_file() else None,

        "writer_policy":
            writer_policy,

        "automatic_engine_decision_preserved":
            True,

        "original_lifecycle":
            lifecycle_status,

        "original_decision_receipt":
            receipt,

        "original_failure_classification":
            failure,

        "unresolved_hard_constraint_ids":
            unresolved,

        "execution_before_override": {
            "model_calls":
                model_calls,

            "writer_calls":
                writer_calls,

            "writer_status":
                writer_status,
        },

        "invariants": {
            "does_not_reclassify_job_as_eligible":
                True,

            "does_not_weaken_sponsorship_rules":
                True,

            "does_not_weaken_clearance_rules":
                True,

            "automatic_release_not_authorized":
                True,

            "root_publish_not_authorized":
                True,

            "release_ready_not_forged":
                True,

            "second_writer_call_not_authorized":
                mode != 'EXPLICIT_FAILED_TRANSPORT_ONE_RETRY_ALLOWED',

            "unreleased_renderer_isolated":
                True,
        },
    }

    _write_override_json(
        runtime
        / "user_generation_override_authorization.json",
        authorization,
    )

    print()
    print(
        "=" * 96
    )
    print(
        "EXPLICIT USER GENERATION OVERRIDE: AUTHORIZED"
    )
    print(
        "RUN ID:",
        run_id,
    )
    print(
        "MODE:",
        mode,
    )
    print(
        "AUTOMATIC DECISION PRESERVED: YES"
    )
    print(
        "NORMAL RELEASE AUTHORIZED: NO"
    )
    print(
        "SECOND WRITER AUTHORIZED: NO"
    )
    print(
        "=" * 96
    )

    return authorization


def enforce_pre_writer_constraint_gate(
    run_id,
    company,
    position,
    env,
    *,
    user_override_generate=False,
    override_reason=None,
):
    if not user_override_generate:
        return (
            _enforce_pre_writer_constraint_gate_strict(
                run_id,
                company,
                position,
                env,
            )
        )

    return (
        _authorize_user_generation_override(
            run_id,
            override_reason,
        )
    )

def run_li_advisory_diagnostic(
    run_id,
    company,
    position,
    env,
):
    """
    Optional local semantic shadow.

    This diagnostic is deliberately OUTSIDE the deterministic
    lifecycle authority chain. It may observe and report only.

    It must never:
    - alter eligibility or constraint decisions;
    - mark a manifest stage PASS/FAIL;
    - change resumability or release authority;
    - trigger or retry the Sol writer;
    - block deterministic CareerOps execution.

    Enable explicitly with:
        CAREEROPS_LI_ADVISORY=1
    """

    enabled = (
        str(
            env.get(
                "CAREEROPS_LI_ADVISORY",
                "",
            )
            or ""
        )
        .strip()
        .casefold()
        in {
            "1",
            "true",
            "yes",
            "on",
        }
    )

    if not enabled:
        print(
            "LI6 ADVISORY: DISABLED"
        )
        return None

    runtime = runtime_path(
        run_id
    )

    report_path = (
        runtime
        / "li_advisory_report.json"
    )

    #
    # Advisory is per-run diagnostic evidence, not a lifecycle
    # stage. A resumed deterministic run must not spend another
    # local-model call merely because execution resumes after the
    # advisory point.
    #
    # If a report already exists, never invoke the local model
    # again for this run. Reuse a valid report byte-for-byte.
    # Invalid existing evidence is fail-open normalized without a
    # new local-model call.
    if report_path.exists():
        try:
            existing = json.loads(
                report_path.read_text(
                    encoding="utf-8"
                )
            )

        except Exception:
            existing = None

        existing_valid = (
            isinstance(
                existing,
                dict,
            )
            and existing.get(
                "schema_version"
            )
            == "career-ops-li6-production-advisory-v1"
            and existing.get(
                "status"
            )
            in {
                "AVAILABLE",
                "SHADOW_UNAVAILABLE",
                "SHADOW_INVALID",
            }
            and existing.get(
                "authority"
            )
            == "ADVISORY_ONLY"
            and existing.get(
                "may_override"
            )
            is False
            and existing.get(
                "production_decision_effect"
            )
            == "NONE"
            and existing.get(
                "continue_deterministic_engine"
            )
            is True
            and existing.get(
                "run_id"
            )
            == run_id
            and existing.get(
                "company"
            )
            == company
            and existing.get(
                "position"
            )
            == position
            and isinstance(
                existing.get(
                    "local_model_calls",
                    0,
                ),
                int,
            )
            and 0
            <= existing.get(
                "local_model_calls",
                0,
            )
            <= 1
        )

        if existing_valid:
            print(
                "LI6 ADVISORY: REUSED_EXISTING",
                existing.get(
                    "status"
                ),
                "local_model_calls_new=0",
                "decision_effect=NONE",
            )

            return existing

        invalid_existing = {
            "schema_version":
                "career-ops-li6-production-advisory-v1",

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
                True,

            "run_id":
                run_id,

            "company":
                company,

            "position":
                position,

            "source_kind":
                "EXISTING_REPORT_INVALID",

            "local_model_calls":
                0,

            "error":
                "EXISTING_ADVISORY_REPORT_INVALID_NO_RETRY",
        }

        tmp_existing = (
            report_path
            .with_name(
                report_path.name
                + ".tmp"
            )
        )

        tmp_existing.write_text(
            json.dumps(
                invalid_existing,
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        tmp_existing.replace(
            report_path
        )

        print(
            "LI6 ADVISORY: SHADOW_INVALID",
            "local_model_calls_new=0",
            "decision_effect=NONE",
        )

        return invalid_existing

    def load_runtime_json(
        filename,
    ):
        path = (
            runtime
            / filename
        )

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

    deterministic_files = {
        "jd_intake":
            "jd_intake.json",

        "requirements":
            "jd_requirements.json",

        "requirement_integrity":
            "requirement_integrity_gate.json",

        "role_routing":
            "role_routing.json",

        "semantic_map":
            "jd_semantic_map.json",

        "entities":
            "candidate_entities.json",

        "evidence_map":
            "requirement_evidence_map.json",

        "constraints":
            "constraint_validation.json",

        "experience_selection":
            "experience_selection.json",

        "project_selection":
            "project_selection.json",

        "skills":
            "technical_skills_plan.json",

        "summary":
            "summary_route.json",

        "cover_plan":
            "cover_plan.json",

        "pair_packet":
            "pair_generation_packet.json",
    }

    deterministic = {
        "company":
            company,

        "job_title":
            position,

        "run_id":
            run_id,
    }

    for key, filename in (
        deterministic_files.items()
    ):
        value = load_runtime_json(
            filename
        )

        if value is not None:
            deterministic[
                key
            ] = value

    original_source = (
        runtime
        / "jd_source_original.txt"
    )

    source_kind = None
    raw_source = ""

    if original_source.exists():
        raw_source = (
            original_source
            .read_text(
                encoding="utf-8"
            )
        )

        source_kind = (
            "JD_SOURCE_ORIGINAL"
        )

    else:
        intake = (
            deterministic.get(
                "jd_intake"
            )
            or {}
        )

        raw_source = str(
            intake.get(
                "raw_jd_text"
            )
            or ""
        )

        source_kind = (
            "JD_INTAKE_FALLBACK"
        )

    def fail_open(
        error,
        *,
        observed_local_model_calls=0,
    ):
        return {
            "schema_version":
                "career-ops-li6-production-advisory-v1",

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

            "run_id":
                run_id,

            "company":
                company,

            "position":
                position,

            "source_kind":
                source_kind,

            "local_model_calls":
                (
                    observed_local_model_calls
                    if isinstance(
                        observed_local_model_calls,
                        int,
                    )
                    and 0
                    <= observed_local_model_calls
                    <= 1
                    else 0
                ),

            "error":
                str(
                    error
                ),
        }

    try:
        if not raw_source.strip():
            envelope = fail_open(
                "EMPTY_ADVISORY_SOURCE"
            )

        else:
            import careerops_li_advisory_runner as li_advisory

            try:
                timeout = int(
                    str(
                        env.get(
                            "CAREEROPS_LI_ADVISORY_TIMEOUT",
                            "90",
                        )
                    )
                )

            except Exception:
                timeout = 90

            timeout = max(
                1,
                min(
                    timeout,
                    180,
                ),
            )

            result = (
                li_advisory.run(
                    raw_source,
                    deterministic,
                    timeout=timeout,
                )
            )

            valid = (
                isinstance(
                    result,
                    dict,
                )
                and result.get(
                    "authority"
                )
                == "ADVISORY_ONLY"
                and result.get(
                    "may_override"
                )
                is False
                and result.get(
                    "production_decision_effect"
                )
                == "NONE"
                and result.get(
                    "continue_deterministic_engine"
                )
                is True
                and result.get(
                    "status"
                )
                in {
                    "AVAILABLE",
                    "SHADOW_UNAVAILABLE",
                    "SHADOW_INVALID",
                }
                and isinstance(
                    result.get(
                        "local_model_calls",
                        0,
                    ),
                    int,
                )
                and 0
                <= result.get(
                    "local_model_calls",
                    0,
                )
                <= 1
            )

            if not valid:
                observed = (
                    result.get(
                        "local_model_calls",
                        0,
                    )
                    if isinstance(
                        result,
                        dict,
                    )
                    else 0
                )

                envelope = fail_open(
                    "ADVISORY_AUTHORITY_CONTRACT_VIOLATION",
                    observed_local_model_calls=observed,
                )

                envelope[
                    "status"
                ] = "SHADOW_INVALID"

            else:
                envelope = {
                    "schema_version":
                        "career-ops-li6-production-advisory-v1",

                    "status":
                        result.get(
                            "status"
                        ),

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
                            result.get(
                                "review_required"
                            )
                        ),

                    "run_id":
                        run_id,

                    "company":
                        company,

                    "position":
                        position,

                    "source_kind":
                        source_kind,

                    "local_model_calls":
                        result.get(
                            "local_model_calls",
                            0,
                        ),

                    "advisory_result":
                        result,
                }

    except Exception as exc:
        envelope = fail_open(
            "LI6_ADVISORY_EXCEPTION:"
            + repr(
                exc
            )
        )

    tmp = (
        report_path
        .with_name(
            report_path.name
            + ".tmp"
        )
    )

    tmp.write_text(
        json.dumps(
            envelope,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    tmp.replace(
        report_path
    )

    print(
        "LI6 ADVISORY:",
        envelope.get(
            "status"
        ),
        "local_model_calls=",
        envelope.get(
            "local_model_calls",
            0,
        ),
        "decision_effect=NONE",
    )

    return envelope


def _run_user_override_renderer(
    run_id,
    reason,
    env,
):
    """
    Complete the accepted explicit-user-override lane.

    The normal pipeline stops at the writer boundary. The already
    generated pair is then rendered only in the isolated unreleased
    override workspace. Normal gates, Final Audit, Release and root
    publication are not invoked here, and this helper cannot call
    the pair writer.
    """
    reason = str(
        reason
        or ""
    ).strip()

    if not reason:
        raise SystemExit(
            "User override renderer requires a non-empty reason."
        )

    ok, rc = run_command(
        "USER OVERRIDE: ISOLATED UNRELEASED RENDER",
        [
            PYTHON,
            ROOT
            / "scripts"
            / "careerops_user_override_generate.py",
            "--run-id",
            run_id,
            "--reason",
            reason,
        ],
        env,
    )

    if not ok:
        raise SystemExit(
            "Isolated user-override renderer failed "
            f"with RC {rc}."
        )

    return 0


def run_writer(
    run_id,
    company,
    position,
    env,
    resume_mode,
):
    if should_skip(
        run_id,
        "writer",
        resume_mode,
    ):
        print(
            "SKIP writer: manifest already PASS"
        )
        return

    # The writer owns the durable inference receipt after preflight.
    # Launching a local preflight process consumes no writer call.
    mark_manifest(
        run_id,
        company,
        position,
        env,
        "writer",
        "RUNNING",
        detail=(
            "Launching isolated pair writer."
        ),
        model="gpt-6.1-sol",
        model_call=False,
    )

    ok, rc = run_command(
        "STAGE: ONE ISOLATED PAIR WRITER CALL",
        [
            PYTHON,
            ROOT
            / "scripts"
            / "careerops_generate_pair.py",
        ],
        env,
    )

    if not ok:
        fail_stage(
            run_id,
            company,
            position,
            env,
            "writer",
            (
                "Pair writer failed "
                f"with RC {rc}."
            ),
        )

    mark_manifest(
        run_id,
        company,
        position,
        env,
        "writer",
        "PASS",
        detail=(
            "Resume and cover candidates written."
        ),
        model="gpt-6.1-sol",
    )

    refresh_manifest(
        run_id,
        company,
        position,
        env,
    )


def run_gate(
    title,
    stage,
    script,
    run_id,
    company,
    position,
    env,
    resume_mode,
):
    if should_skip(
        run_id,
        stage,
        resume_mode,
    ):
        print(
            f"SKIP {stage}: manifest already PASS"
        )
        return

    ok, rc = run_command(
        title,
        [
            PYTHON,
            ROOT
            / "scripts"
            / script,
        ],
        env,
    )

    if not ok:
        fail_stage(
            run_id,
            company,
            position,
            env,
            stage,
            (
                f"{stage} failed "
                f"with RC {rc}."
            ),
        )

    refresh_manifest(
        run_id,
        company,
        position,
        env,
    )


def run_cover_gate(
    run_id,
    company,
    position,
    env,
    resume_mode,
):
    if should_skip(
        run_id,
        "cover_gate",
        resume_mode,
    ):
        print(
            "SKIP cover_gate: manifest already PASS"
        )
        return

    runtime = runtime_path(
        run_id
    )

    gate_script = (
        ROOT
        / "scripts"
        / "careerops_cover_gate_v2.py"
    )

    ok, first_rc = run_command(
        "STAGE: COVER GATE V2",
        [
            PYTHON,
            gate_script,
        ],
        env,
    )

    if not ok:
        report = (
            runtime
            / "cover_gate_v2_report.json"
        )

        if not report.exists():
            fail_stage(
                run_id,
                company,
                position,
                env,
                "cover_gate",
                (
                    "Cover Gate V2 failed "
                    "without producing a report."
                ),
            )

        # COVER_FAILURE_CLASSIFICATION_BEFORE_REPAIR_V1
        classification = classify_failure_event(
            run_id,
            "cover_gate",
            (
                "Cover Gate V2 failed before "
                "deterministic repair."
            ),
            return_code=first_rc,
            artifact=report,
            report_path=report,
            writing_defect_confirmed=False,
        )

        if (
            classification.get(
                "failure_class"
            )
            != "COVER_VALIDATION"
            or classification.get(
                "deterministic_repair_permitted"
            )
            is not True
            or classification.get(
                "second_writer_call_permitted"
            )
            is True
            or classification.get(
                "automatic_writer_retry"
            )
            is True
        ):
            fail_stage(
                run_id,
                company,
                position,
                env,
                "cover_gate",
                (
                    "Cover Gate V2 failure was not "
                    "classified as deterministic "
                    "COVER_VALIDATION repair."
                ),
                return_code=first_rc,
                artifact=report,
                report_path=report,
            )

        print()
        print(
            "Cover Gate V2 failed. "
            "Classified COVER_VALIDATION. "
            "Attempting deterministic repair only."
        )

        repair_ok, repair_rc = run_command(
            "DETERMINISTIC COVER REPAIR",
            [
                PYTHON,
                ROOT
                / "scripts"
                / "careerops_deterministic_repair_dispatcher.py",
                "--cover",
                runtime
                / "generated_cover_letter_pair_candidate.json",
                "--plan",
                runtime
                / "cover_plan.json",
                "--report",
                report,
            ],
            env,
        )

        dispatch = read_json(runtime / 'deterministic_repair_dispatch.json') or {}
        if not repair_ok and dispatch.get('status') == 'SEMANTIC_CHALLENGE_REQUIRED':
            from careerops_cover_semantic_challenger import attempt
            from careerops_capability_trace import observe_command
            owners = [ROOT / 'scripts/careerops_cover_semantic_challenger.py']
            trace = observe_command(run_id, 'COVER SEMANTIC CHALLENGER', owners, 'STARTED', env=env, root=ROOT)
            review = attempt(runtime, run_id, env)
            observe_command(run_id, 'COVER SEMANTIC CHALLENGER', owners, 'COMPLETED', return_code=0 if review.get('qwen_completed') else 2, env=env, root=ROOT, invocation_id=trace)
            print('COVER SEMANTIC CHALLENGER:', review.get('status'), review.get('reason'))
            # Independent original gate remains decisive. Qwen never sets PASS.
            revalidated, review_rc = run_command('COVER GATE AFTER SOURCE-BOUND SEMANTIC REVIEW', [PYTHON, gate_script], env)
            if revalidated:
                repair_ok = True
            else:
                fail_stage(run_id, company, position, env, 'cover_gate',
                    'Cover semantic review '+str(review.get('status'))+'; original Cover Gate remains blocked. '+str(review.get('reason')),
                    return_code=review_rc, artifact=report, report_path=report)

        if not repair_ok:
            fail_stage(
                run_id,
                company,
                position,
                env,
                "cover_gate",
                (
                    "Cover failed V2 and deterministic "
                    "repair refused or failed "
                    f"with RC {repair_rc}. "
                    "No second writer call was made."
                ),
            )

        ok, second_rc = run_command(
            "STAGE: COVER GATE V2 AFTER DETERMINISTIC REPAIR",
            [
                PYTHON,
                gate_script,
            ],
            env,
        )

        if not ok:
            fail_stage(
                run_id,
                company,
                position,
                env,
                "cover_gate",
                (
                    "Cover Gate V2 still failed after "
                    "deterministic repair "
                    f"with RC {second_rc}. "
                    "No model repair was invoked."
                ),
            )

    refresh_manifest(
        run_id,
        company,
        position,
        env,
    )


def run_rendering(
    run_id,
    company,
    position,
    env,
    resume_mode,
):
    runtime = runtime_path(
        run_id
    )

    output = output_path(
        run_id
    )

    job_slug = (
        slug(company, 45)
        + "_"
        + slug(position, 55)
    )

    resume_pdf = (
        output
        / (
            "careerops_resume_"
            + job_slug
            + ".pdf"
        )
    )

    resume_docx = (
        output
        / (
            "careerops_resume_"
            + job_slug
            + ".docx"
        )
    )

    cover_pdf = (
        output
        / (
            "careerops_cover_"
            + job_slug
            + ".pdf"
        )
    )

    cover_docx = (
        output
        / (
            "careerops_cover_"
            + job_slug
            + ".docx"
        )
    )

    candidate = (
        runtime
        / "generated_resume_content_pair_candidate.json"
    )

    cover = (
        runtime
        / "generated_cover_letter_pair_candidate.json"
    )

    payload = (
        runtime
        / "career_ops_cv_payload.json"
    )

    payload_validation = (
        runtime
        / "career_ops_cv_payload_validation.json"
    )

    resume_html = (
        runtime
        / "resume_render.html"
    )

    adaptive_html = (
        runtime
        / "resume_adaptive.html"
    )

    adaptive_report = (
        runtime
        / "adaptive_layout_report.json"
    )

    cover_html = (
        runtime
        / "cover_render.html"
    )

    cover_gate = (
        runtime
        / "cover_gate_v2_report.json"
    )

    roundtrip = (
        runtime
        / "cover_roundtrip_report.json"
    )

    render_env = env.copy()

    render_env[
        "CAREEROPS_RESUME_INPUT"
    ] = str(candidate)

    render_env[
        "CAREEROPS_CV_PAYLOAD_OUTPUT"
    ] = str(payload)

    render_env[
        "CAREEROPS_CV_PAYLOAD_VALIDATION_OUTPUT"
    ] = str(payload_validation)

    render_env[
        "CAREEROPS_RESUME_OUTPUT"
    ] = str(resume_docx)

    render_env[
        "CAREER_OPS_PDF_INDEX"
    ] = str(
        runtime
        / "pdf-index.tsv"
    )

    if not should_skip(
        run_id,
        "resume_payload",
        resume_mode,
    ):
        ok, rc = run_command(
            "STAGE: RESUME PAYLOAD",
            [
                PYTHON,
                ROOT
                / "scripts"
                / "careerops_build_cv_payload.py",
            ],
            render_env,
        )

        if not ok:
            fail_stage(
                run_id,
                company,
                position,
                env,
                "resume_payload",
                (
                    "Resume payload failed "
                    f"with RC {rc}."
                ),
            )

        refresh_manifest(
            run_id,
            company,
            position,
            env,
        )

    if not should_skip(
        run_id,
        "resume_render",
        resume_mode,
    ):

        #
        # PDF and DOCX must render from the same final structured
        # payload. The payload builder has already validated the
        # approved writer content before this point.
        render_env[
            "CAREEROPS_RESUME_INPUT"
        ] = str(
            payload
        )

        commands = [
            (
                "RESUME HTML",
                [
                    "node",
                    ROOT
                    / "build-cv-html.mjs",
                    payload,
                    resume_html,
                    TEMPLATE,
                ],
            ),
            (
                "ADAPTIVE ONE-PAGE SOLVER",
                [
                    "node",
                    ROOT
                    / "scripts"
                    / "careerops_adaptive_layout.mjs",
                    resume_html,
                    adaptive_html,
                    adaptive_report,
                ],
            ),
            (
                "RESUME PDF",
                [
                    "node",
                    ROOT
                    / "generate-pdf.mjs",
                    adaptive_html,
                    resume_pdf,
                    "--format=letter",
                    "--max-pages=1",
                    "--strict-pages",
                    "--skip-fact-check",
                ],
            ),
            (
                "RESUME DOCX",
                [
                    PYTHON,
                    ROOT
                    / "scripts"
                    / "careerops_docx_renderer.py",
                ],
            ),
        ]

        for title, command in commands:
            ok, rc = run_command(
                title,
                command,
                render_env,
            )

            if not ok:
                fail_stage(
                    run_id,
                    company,
                    position,
                    env,
                    "resume_render",
                    (
                        f"{title} failed "
                        f"with RC {rc}."
                    ),
                )

        #
        # A prior explicit FAIL must be superseded when this stage
        # is successfully rerun. Merely refreshing the manifest is
        # insufficient because explicit_status intentionally has
        # precedence over artifact inference.
        mark_manifest(
            run_id,
            company,
            position,
            env,
            "resume_render",
            "PASS",
            detail=(
                "Resume HTML, adaptive layout, PDF, and DOCX "
                "rendered successfully."
            ),
        )

        resume_roundtrip_report = (
            runtime
            / "resume_roundtrip_report.json"
        )

        ok, rc = run_command(
            "STAGE: RESUME PDF/DOCX ROUND-TRIP",
            [
                PYTHON,
                ROOT
                / "scripts"
                / "careerops_resume_roundtrip.py",
                "--source",
                payload,
                "--pdf",
                resume_pdf,
                "--docx",
                resume_docx,
                "--identity",
                payload,
                "--report",
                resume_roundtrip_report,
            ],
            render_env,
        )

        if not ok:
            fail_stage(
                run_id,
                company,
                position,
                env,
                "resume_roundtrip",
                (
                    "Resume PDF/DOCX round-trip "
                    f"validation failed with RC {rc}."
                ),
                return_code=rc,
                artifact=resume_roundtrip_report,
                report_path=resume_roundtrip_report,
            )

        refresh_manifest(
            run_id,
            company,
            position,
            env,
        )

    if not should_skip(
        run_id,
        "cover_render",
        resume_mode,
    ):
        ok, rc = run_command(
            "COVER PDF",
            [
                "node",
                ROOT
                / "scripts"
                / "careerops_render_cover.mjs",
                "--cover",
                cover,
                "--identity",
                payload,
                "--gate",
                cover_gate,
                "--out",
                cover_pdf,
                "--html",
                cover_html,
            ],
            render_env,
        )

        if not ok:
            fail_stage(
                run_id,
                company,
                position,
                env,
                "cover_render",
                (
                    "Cover PDF render failed "
                    f"with RC {rc}."
                ),
            )

        ok, rc = run_command(
            "COVER DOCX",
            [
                PYTHON,
                ROOT
                / "scripts"
                / "careerops_render_cover_docx.py",
                "--cover",
                cover,
                "--identity",
                payload,
                "--gate",
                cover_gate,
                "--out",
                cover_docx,
            ],
            render_env,
        )

        if not ok:
            fail_stage(
                run_id,
                company,
                position,
                env,
                "cover_render",
                (
                    "Cover DOCX render failed "
                    f"with RC {rc}."
                ),
            )

        refresh_manifest(
            run_id,
            company,
            position,
            env,
        )

    if not should_skip(
        run_id,
        "cover_roundtrip",
        resume_mode,
    ):
        ok, rc = run_command(
            "COVER ROUNDTRIP",
            [
                PYTHON,
                ROOT
                / "scripts"
                / "careerops_cover_roundtrip.py",
                "--source",
                cover,
                "--pdf",
                cover_pdf,
                "--docx",
                cover_docx,
                "--identity",
                payload,
                "--report",
                roundtrip,
            ],
            render_env,
        )

        if not ok:
            fail_stage(
                run_id,
                company,
                position,
                env,
                "cover_roundtrip",
                (
                    "Cover roundtrip failed "
                    f"with RC {rc}."
                ),
            )

        refresh_manifest(
            run_id,
            company,
            position,
            env,
        )

    from careerops_pdf_docx_geometry import audit_pair_geometry
    physical_reports=[]
    for kind,pdf,docx in [('resume',resume_pdf,resume_docx),('cover',cover_pdf,cover_docx)]:
        try:physical_reports.append(audit_pair_geometry(pdf,docx,runtime,kind))
        except (RuntimeError,SystemExit,OSError) as exc:
            fail_stage(run_id,company,position,env,kind+'_render','Physical PDF/DOCX parity failed: '+str(exc))
    _write_override_json(runtime/'render_physical_parity_report.json',{'status':'PASS','model_calls':0,'pairs':physical_reports})
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


def publish_released_artifacts(
    run_id,
    artifacts,
):
    """
    Publish the exact release-approved artifacts from the
    isolated run output directory to the user-facing root output/.

    This is a copy-only operation. It never regenerates content.
    """

    if (runtime_path(run_id)/"user_generation_override_authorization.json").exists() or (runtime_path(run_id)/"user_override/user_override_generation_report.json").exists():
        raise SystemExit("Override artifacts are unreleased; normal release and publication are forbidden.")
    manifest = load_manifest(
        run_id
    )

    release_status = (
        manifest
        .get(
            "stages",
            {}
        )
        .get(
            "release",
            {}
        )
        .get(
            "status"
        )
    )

    if release_status != "PASS":
        raise SystemExit(
            "Refusing root-output publish: "
            "release stage is not PASS."
        )

    release_report = (
        runtime_path(
            run_id
        )
        / "pair_release_gate_report.json"
    )

    report = (
        read_json(
            release_report
        )
        or {}
    )

    if report.get(
        "release_ready"
    ) is not True:
        raise SystemExit(
            "Refusing root-output publish: "
            "release_ready is not true."
        )

    required = (
        "resume_pdf",
        "resume_docx",
        "cover_pdf",
        "cover_docx",
    )

    run_output = (
        output_path(
            run_id
        )
        .resolve()
    )

    root_output = (
        ROOT
        / "output"
    ).resolve()

    root_output.mkdir(
        parents=True,
        exist_ok=True,
    )

    published = {}

    for key in required:

        value = artifacts.get(
            key
        )

        if not value:
            raise SystemExit(
                "Refusing root-output publish: "
                f"missing artifact mapping for {key}."
            )

        source = Path(
            value
        ).resolve()

        if (
            not source.exists()
            or not source.is_file()
        ):
            raise SystemExit(
                "Refusing root-output publish: "
                f"source artifact missing: {source}"
            )

        try:
            source.relative_to(
                run_output
            )
        except ValueError:
            raise SystemExit(
                "Refusing root-output publish: "
                "artifact is outside the active "
                f"run output directory: {source}"
            )

        destination = (
            root_output
            / source.name
        )

        temporary = (
            root_output
            / (
                source.name
                + ".publish_tmp"
            )
        )

        if temporary.exists():
            temporary.unlink()

        shutil.copy2(
            source,
            temporary,
        )

        if (
            source.read_bytes()
            != temporary.read_bytes()
        ):
            temporary.unlink(
                missing_ok=True
            )

            raise SystemExit(
                "Root-output publish verification "
                f"failed before commit: {source.name}"
            )

        temporary.replace(
            destination
        )

        if (
            source.read_bytes()
            != destination.read_bytes()
        ):
            raise SystemExit(
                "Root-output publish verification "
                f"failed after commit: {source.name}"
            )

        published[
            key
        ] = destination

    print()
    print(
        "=" * 96
    )
    print(
        "ROOT OUTPUT PUBLISH: PASS"
    )
    print(
        "=" * 96
    )

    for key in required:
        print(
            key.upper() + " STORAGE (AUDIT ONLY):",
            published[
                key
            ],
        )

    print(
        "SOURCE:",
        run_output,
    )

    print(
        "DESTINATION:",
        root_output,
    )

    print(
        "CONTENT CHANGED: NO"
    )

    print(
        "MODEL CALLS: 0"
    )

    print(
        "=" * 96
    )

    return published

def run_final_application_audit(
    run_id,
    company,
    position,
    env,
    resume_mode,
):
    stage = (
        "final_application_audit"
    )

    if should_skip(
        run_id,
        stage,
        resume_mode,
    ):
        print(
            "SKIP final_application_audit: "
            "manifest already PASS"
        )

        return

    runtime = runtime_path(
        run_id
    )

    report = (
        runtime
        / "final_application_audit_report.json"
    )

    ok, rc = run_command(
        "STAGE: INDEPENDENT FINAL APPLICATION AUDIT",
        [
            PYTHON,
            ROOT
            / "scripts"
            / "careerops_final_application_audit.py",
            "--runtime",
            runtime,
            "--report",
            report,
        ],
        env,
    )

    if not ok:
        fail_stage(
            run_id,
            company,
            position,
            env,
            stage,
            (
                "Independent final application audit "
                f"failed with RC {rc}."
            ),
            return_code=rc,
            artifact=report,
            report_path=report,
        )

    data = read_json(
        report
    ) or {}

    if (
        data.get(
            "gate"
        )
        != "PASS"
        or data.get(
            "pass"
        )
        is not True
    ):
        fail_stage(
            run_id,
            company,
            position,
            env,
            stage,
            (
                "Independent final application audit "
                "returned success without gate=PASS "
                "and pass=true."
            ),
            artifact=report,
            report_path=report,
        )

    if data.get(
        "model_calls"
    ) != 0:
        fail_stage(
            run_id,
            company,
            position,
            env,
            stage,
            (
                "Independent final application audit "
                "reported nonzero model calls."
            ),
            artifact=report,
            report_path=report,
        )

    # Explicit PASS is intentional. Unlike simple artifact
    # inference, this preserves resumability for this new
    # multi-class deterministic gate.
    mark_manifest(
        run_id,
        company,
        position,
        env,
        stage,
        "PASS",
        detail=(
            "Independent final application audit passed "
            "with zero model calls."
        ),
    )

    refresh_manifest(
        run_id,
        company,
        position,
        env,
    )

def enforce_interview_defensibility(run_id, company, position, env):
    # Production default is enabled; explicit emergency disable is recorded as skipped.
    if env.get("CAREEROPS_INTERVIEW_DEFENSIBILITY") != "1":
        mark_manifest(run_id, company, position, env, "interview_defensibility", "SKIPPED", detail="Explicit emergency guard disable.")
        return
    from careerops_interview_defensibility import run_gate as interview_gate
    from careerops_capability_trace import observe_command
    interview_owner = [ROOT/"scripts/careerops_interview_defensibility.py"]
    trace_id = observe_command(run_id, "INTERVIEW DEFENSIBILITY", interview_owner, "STARTED", env=env, root=ROOT)
    report = interview_gate(runtime_path(run_id))
    observe_command(run_id, "INTERVIEW DEFENSIBILITY", interview_owner, "COMPLETED",
                    return_code=0 if report.get("gate")=="PASS" else 2, env=env, root=ROOT, invocation_id=trace_id)
    if report.get("gate") != "PASS":
        fail_stage(run_id, company, position, env, "interview_defensibility",
                   "Interview defensibility blocked release; no writer retry.",
                   artifact=runtime_path(run_id)/"interview_defensibility_report.json")
    mark_manifest(run_id, company, position, env, "interview_defensibility", "PASS", detail="Source-bound interview gate passed.")


def run_release(
    run_id,
    company,
    position,
    env,
    artifacts,
    resume_mode,
):
    if (runtime_path(run_id)/"user_generation_override_authorization.json").exists() or (runtime_path(run_id)/"user_override/user_override_generation_report.json").exists():
        raise SystemExit("Override artifacts are unreleased; normal release and publication are forbidden.")
    enforce_interview_defensibility(run_id, company, position, env)
    if should_skip(
        run_id,
        "release",
        resume_mode,
    ):
        print(
            "SKIP release: manifest already PASS"
        )

        publish_released_artifacts(
            run_id,
            artifacts,
        )

        return

    command = [
        PYTHON,
        ROOT
        / "scripts"
        / "careerops_pair_release_gate.py",
        "--resume-pdf",
        artifacts[
            "resume_pdf"
        ],
        "--resume-docx",
        artifacts[
            "resume_docx"
        ],
        "--cover-pdf",
        artifacts[
            "cover_pdf"
        ],
        "--cover-docx",
        artifacts[
            "cover_docx"
        ],
    ]

    ok, rc = run_command(
        "STAGE: UNIVERSAL RELEASE GATE V2",
        command,
        env,
    )

    refresh_manifest(
        run_id,
        company,
        position,
        env,
    )

    if not ok:
        fail_stage(
            run_id,
            company,
            position,
            env,
            "release",
            (
                "Universal release gate blocked "
                f"release with RC {rc}."
            ),
        )

    report = read_json(
        runtime_path(
            run_id
        )
        / "pair_release_gate_report.json"
    ) or {}

    if report.get(
        "release_ready"
    ) is not True:
        fail_stage(
            run_id,
            company,
            position,
            env,
            "release",
            (
                "Release process returned success "
                "without release_ready=true."
            ),
        )

    #
    # A previous explicit release FAIL must not permanently override a
    # later successful deterministic rerun. Once the release gate has
    # returned RC 0 and its current-run report says release_ready=true,
    # record the new authoritative explicit PASS before refresh/publish.
    mark_manifest(
        run_id,
        company,
        position,
        env,
        "release",
        "PASS",
        detail=(
            "Universal release gate passed with "
            "release_ready=true."
        ),
    )

    refresh_manifest(
        run_id,
        company,
        position,
        env,
    )

    publish_released_artifacts(
        run_id,
        artifacts,
    )


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Global production orchestrator for "
            "the CareerOps Career-Ops application engine."
        )
    )

    parser.add_argument(
        "--self-test",
        action="store_true",
    )

    parser.add_argument(
        "--jd-file",
    )

    parser.add_argument(
        "--jd-text",
    )

    parser.add_argument(
        "--application-url",
    )

    parser.add_argument(
        "--url-first",
        action="store_true",
        help=(
            "Attempt URL ingestion first. If the URL cannot "
            "supply a usable JD and ingestion returns "
            "NEEDS_MANUAL_JD, automatically fall back to the "
            "supplied --jd-file or --jd-text content."
        ),
    )

    parser.add_argument(
        "--company",
    )

    parser.add_argument(
        "--position",
    )

    parser.add_argument(
        "--run-id",
    )

    parser.add_argument(
        "--resume-run",
    )

    parser.add_argument(
        "--user-override-generate",
        action="store_true",
        help=(
            "Explicit user authority to obtain unreleased "
            "resume/cover output from an existing failed/rejected run."
        ),
    )

    parser.add_argument(
        "--override-reason",
        help=(
            "Required reason for --user-override-generate."
        ),
    )

    parser.add_argument(
        "--stop-after",
        choices=STOP_CHOICES,
        default="release",
    )

    return parser


def main():
    args = (
        build_parser()
        .parse_args()
    )

    if args.self_test:
        raise SystemExit(
            self_test()
        )

    require_scripts()

    resume_mode = bool(
        args.resume_run
    )

    _normalize_user_generation_override_args(
        args,
        resume_mode,
    )

    if (
        args.resume_run
        and args.run_id
    ):
        raise SystemExit(
            "Use --resume-run or --run-id, not both."
        )

    if resume_mode:
        run_id = args.resume_run

        run_root = (
            RUNS
            / run_id
        )

        if not run_root.exists():
            raise SystemExit(
                "Resume run does not exist: "
                + run_id
            )

        existing = load_manifest(
            run_id
        )

        company = (
            args.company
            or existing
            .get(
                "job",
                {}
            )
            .get(
                "company"
            )
        )

        position = (
            args.position
            or existing
            .get(
                "job",
                {}
            )
            .get(
                "position"
            )
        )

        company = str(
            company
            or ""
        ).strip()

        position = str(
            position
            or ""
        ).strip()

        if not company or not position:
            raise SystemExit(
                "Resume run has no recoverable "
                "company/position identity."
            )

    else:
        if not args.company:
            raise SystemExit(
                "--company is required for a new run."
            )

        if not args.position:
            raise SystemExit(
                "--position is required for a new run."
            )

        company = str(
            args.company
            or ""
        ).strip()

        position = str(
            args.position
            or ""
        ).strip()

        run_id = (
            args.run_id
            or generated_run_id(
                company,
                position,
            )
        )

        run_root = (
            RUNS
            / run_id
        )

        if run_root.exists():
            raise SystemExit(
                "Run already exists. "
                "Use --resume-run instead: "
                + run_id
            )

        run_root.mkdir(
            parents=True,
        )

    if args.user_override_generate:
        from careerops_overall_override import run as run_overall_override
        report = run_overall_override(run_root, args.override_reason)
        print("CAREEROPS OUTCOME:", report.get("status"), "RELEASE READY: NO")
        return 0
    if (run_root/'runtime'/'quarantine_generation_authorization.json').is_file() or load_manifest(run_id).get('overall_override_only'):
        raise SystemExit('Isolated override runtime cannot enter automatic production release.')

    runtime = runtime_path(
        run_id
    )

    output = output_path(
        run_id
    )

    runtime.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.mkdir(
        parents=True,
        exist_ok=True,
    )

    global _ACTIVE_OUTCOME_RUN_ID
    _ACTIVE_OUTCOME_RUN_ID = run_id
    env = clean_run_env(
        run_id
    )

    #
    # Deterministic JD stages must consume the same authoritative
    # company/position identity that the orchestrator and manifest use.
    env[
        "CAREEROPS_JOB_COMPANY"
    ] = company

    env[
        "CAREEROPS_JOB_POSITION"
    ] = position

    refresh_manifest(
        run_id,
        company,
        position,
        env,
    )

    jd_file = prepare_input(
        args,
        run_id,
        run_root,
    )

    if (
        resume_mode
        and stage_status(
            run_id,
            "ingest",
        )
        != "PASS"
    ):
        stored = (
            run_root
            / "input_jd.txt"
        )

        if stored.exists():
            jd_file = stored

    run_deterministic(
        args,
        run_id,
        company,
        position,
        env,
        jd_file,
        resume_mode,
    )

    if args.stop_after == "pair_packet":
        print()
        print(
            "STOP AFTER: pair_packet"
        )
        print(
            "MODEL WRITER CALLS: 0"
        )
        return 0

    run_li_advisory_diagnostic(
        run_id,
        company,
        position,
        env,
    )

    enforce_pre_writer_constraint_gate(
        run_id,
        company,
        position,
        env,
        user_override_generate=(
            args.user_override_generate
        ),
        override_reason=(
            args.override_reason
        ),
    )

    run_writer(
        run_id,
        company,
        position,
        env,
        resume_mode,
    )

    if args.stop_after == "writer":

        #
        # Override normalization intentionally stops the normal pipeline
        # at the one-writer boundary. Only an explicit override continues
        # into the isolated unreleased renderer.
        if bool(
            getattr(
                args,
                "user_override_generate",
                False,
            )
        ):
            return _run_user_override_renderer(
                run_id,
                args.override_reason,
                env,
            )

        print()
        print(
            "STOP AFTER: writer"
        )
        return 0

    runtime = runtime_path(
        run_id
    )

    gate_env = env.copy()

    gate_env[
        "CAREEROPS_RESUME_INPUT"
    ] = str(
        runtime
        / "generated_resume_content_pair_candidate.json"
    )

    # Truth Gate V2 is deterministic-first.
    #
    # Local atomic validation runs before the canonical truth gate.
    # On local PASS, careerops_truth_gate.py synthesizes the canonical
    # truth outputs with zero additional model calls.
    #
    # A semantic model audit is permitted only when the local gate
    # reports the narrowly defined ambiguity class handled by V2.
    run_gate(
        "STAGE: LOCAL DETERMINISTIC TRUTH GATE",
        "local_truth_gate",
        "careerops_local_truth_gate.py",
        run_id,
        company,
        position,
        gate_env,
        resume_mode,
    )

    run_gate(
        "STAGE: TRUTH GATE V2",
        "deep_truth_gate",
        "careerops_truth_gate.py",
        run_id,
        company,
        position,
        gate_env,
        resume_mode,
    )

    run_gate(
        "STAGE: ATS GATE V2",
        "ats_gate",
        "careerops_ats_gate_v2.py",
        run_id,
        company,
        position,
        gate_env,
        resume_mode,
    )

    run_gate(
        "STAGE: HUMAN GATE V2.2",
        "human_gate",
        "careerops_human_gate_v22.py",
        run_id,
        company,
        position,
        gate_env,
        resume_mode,
    )

    run_cover_gate(
        run_id,
        company,
        position,
        gate_env,
        resume_mode,
    )

    enforce_interview_defensibility(run_id, company, position, gate_env)

    if args.stop_after == "gates":
        print()
        print(
            "STOP AFTER: gates"
        )
        return 0

    artifacts = run_rendering(
        run_id,
        company,
        position,
        gate_env,
        resume_mode,
    )

    if args.stop_after == "render":
        print()
        print(
            "STOP AFTER: render"
        )
        return 0

    run_final_application_audit(
        run_id,
        company,
        position,
        gate_env,
        resume_mode,
    )

    run_release(
        run_id,
        company,
        position,
        gate_env,
        artifacts,
        resume_mode,
    )

    manifest = load_manifest(
        run_id
    )

    print()
    print(
        "=" * 96
    )
    print(
        "CAREEROPS GLOBAL PRODUCTION ORCHESTRATOR: COMPLETE"
    )
    print(
        "=" * 96
    )

    print(
        "RUN ID:",
        run_id,
    )

    print(
        "COMPANY:",
        company,
    )

    print(
        "POSITION:",
        position,
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

    print(
        "MODEL CALLS:",
        manifest.get(
            "execution",
            {}
        ).get(
            "model_calls"
        ),
    )

    print(
        "RESUME PDF STORAGE (AUDIT ONLY):",
        artifacts[
            "resume_pdf"
        ],
    )

    print(
        "RESUME DOCX STORAGE (AUDIT ONLY):",
        artifacts[
            "resume_docx"
        ],
    )

    print(
        "COVER PDF STORAGE (AUDIT ONLY):",
        artifacts[
            "cover_pdf"
        ],
    )

    print(
        "COVER DOCX STORAGE (AUDIT ONLY):",
        artifacts[
            "cover_docx"
        ],
    )

    print(
        "RELEASE READY: YES"
    )

    return 0


_ACTIVE_OUTCOME_RUN_ID = None

def cli_main():
    from careerops_run_outcome import emit_run_outcome
    result = None
    error = None
    try:
        result = main()
        return result
    except SystemExit as exc:
        result = exc.code if isinstance(exc.code, int) else 1
        error = str(exc.code) if not isinstance(exc.code, int) else None
        raise
    except Exception as exc:
        result = 1
        error = type(exc).__name__ + ": " + str(exc)
        raise
    finally:
        if _ACTIVE_OUTCOME_RUN_ID:
            try:
                emit_run_outcome(_ACTIVE_OUTCOME_RUN_ID, result, root=ROOT, error=error, print_human=True)
            except Exception as exc:
                print("OUTCOME PRESENTATION ERROR:", type(exc).__name__, str(exc))


if __name__ == "__main__":
    raise SystemExit(
        cli_main()
    )
