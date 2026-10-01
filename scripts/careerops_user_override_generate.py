import sys
#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


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

MODEL_ENV_KEYS = {
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_ORG_ID",
    "CODEX_API_KEY",
    "CODEX_ACCESS_TOKEN",
}


def sha(path):
    path = Path(path)

    if not path.is_file():
        return None

    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def load_json(path):
    path = Path(path)

    if not path.is_file():
        return {}

    try:
        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except Exception:
        return {}


def atomic_json(
    path,
    payload,
):
    path = Path(path)

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


def slug(
    value,
    limit=72,
):
    value = re.sub(
        r"[^A-Za-z0-9]+",
        "_",
        str(
            value
            or ""
        ).strip(),
    ).strip(
        "_"
    ).lower()

    return (
        value[
            :limit
        ]
        or "job"
    )


def stage_status(
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


def clean_env(extra=None):
    env = os.environ.copy()

    for key in MODEL_ENV_KEYS:
        env.pop(
            key,
            None,
        )

    if extra:
        for key, value in extra.items():
            env[
                str(
                    key
                )
            ] = str(
                value
            )

    return env


def run_command(
    title,
    command,
    env,
):
    print()
    print(
        "=" * 96
    )
    print(
        title
    )
    print(
        "=" * 96
    )
    print(
        "COMMAND:",
        " ".join(
            str(
                x
            )
            for x in command
        ),
    )

    result = subprocess.run(
        [
            str(
                x
            )
            for x in command
        ],
        cwd=ROOT,
        env=env,
        check=False,
    )

    print(
        "RC:",
        result.returncode,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"{title} failed with RC "
            f"{result.returncode}."
        )


def job_identity(
    manifest,
    cover,
):
    job = (
        manifest.get(
            "job"
        )
        or {}
    )

    company = str(
        job.get(
            "company"
        )
        or manifest.get(
            "company"
        )
        or cover.get(
            "company"
        )
        or ""
    ).strip()

    position = str(
        job.get(
            "position"
        )
        or manifest.get(
            "position"
        )
        or cover.get(
            "position"
        )
        or ""
    ).strip()

    if not company:
        raise RuntimeError(
            "Could not resolve company identity "
            "for override rendering."
        )

    if not position:
        raise RuntimeError(
            "Could not resolve position identity "
            "for override rendering."
        )

    return (
        company,
        position,
    )


def failure_snapshot(
    runtime,
    manifest,
):
    names = [
        "job_decision_receipt.json",
        "failure_classification.json",
        "constraint_validation.json",
        "local_truth_gate.json",
        "truth_gate.json",
        "ats_gate.json",
        "human_gate.json",
        "cover_gate_v2_report.json",
        "final_application_audit_report.json",
        "pair_release_gate_report.json",
    ]

    artifacts = {}

    for name in names:
        path = (
            runtime
            / name
        )

        obj = load_json(
            path
        )

        artifacts[
            name
        ] = {
            "exists":
                path.is_file(),

            "sha256":
                sha(
                    path
                ),

            "status":
                (
                    obj.get(
                        "status"
                    )
                    if isinstance(
                        obj,
                        dict,
                    )
                    else None
                ),

            "gate":
                (
                    obj.get(
                        "gate"
                    )
                    if isinstance(
                        obj,
                        dict,
                    )
                    else None
                ),

            "pass":
                (
                    obj.get(
                        "pass"
                    )
                    if isinstance(
                        obj,
                        dict,
                    )
                    else None
                ),

            "decision":
                (
                    obj.get(
                        "decision"
                    )
                    if isinstance(
                        obj,
                        dict,
                    )
                    else None
                ),

            "decision_class":
                (
                    obj.get(
                        "decision_class"
                    )
                    if isinstance(
                        obj,
                        dict,
                    )
                    else None
                ),
        }

    return {
        "lifecycle_status":
            (
                manifest.get(
                    "lifecycle_status"
                )
                or manifest.get(
                    "lifecycle"
                )
            ),

        "resumable_from":
            manifest.get(
                "resumable_from"
            ),

        "artifacts":
            artifacts,
    }


def generate_override(
    run_id,
    reason,
    *,
    runs_root=RUNS,
):
    run_id = str(
        run_id
        or ""
    ).strip()

    reason = str(
        reason
        or ""
    ).strip()

    if not run_id:
        raise RuntimeError(
            "run_id is required."
        )

    if not reason:
        raise RuntimeError(
            "Explicit override reason is required."
        )

    runs_root = Path(
        runs_root
    )

    run_root = (
        runs_root
        / run_id
    )

    runtime = (
        run_root
        / "runtime"
    )

    manifest_path = (
        run_root
        / "manifest.json"
    )

    if not manifest_path.is_file():
        raise RuntimeError(
            "Run manifest not found: "
            + str(
                manifest_path
            )
        )

    manifest = load_json(
        manifest_path
    )
    from careerops_overall_override import blockers
    if blockers(runtime):raise RuntimeError('Irreducible eligibility hard block: override unavailable.')


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
        raise RuntimeError(
            "Run is already RELEASE_READY; "
            "override rendering is unnecessary."
        )

    execution = (
        manifest.get(
            "execution"
        )
        or {}
    )

    writer_calls = int(
        execution.get(
            "writer_calls",
            0,
        )
        or 0
    )

    writer_status = (
        stage_status(
            manifest,
            "writer",
        )
    )

    authorization_bound=load_json(runtime/'user_generation_override_authorization.json') or {}
    explicit_retry_pair=(writer_calls==2 and authorization_bound.get('mode') in {'EXPLICIT_FAILED_TRANSPORT_ONE_RETRY_ALLOWED','POST_WRITER_FAILURE_REUSE_EXISTING_PAIR'} and authorization_bound.get('max_total_writer_calls')==2 and authorization_bound.get('execution_before_override',{}).get('writer_calls') in {1,2} and execution.get('exceptional_writer_retry_calls')==1)
    if (
        (writer_calls != 1 and not explicit_retry_pair)
        or writer_status != "PASS"
    ):
        raise RuntimeError(
            "Override rendering requires exactly one "
            "successful writer call. "
            f"writer_calls={writer_calls}, "
            f"writer_status={writer_status!r}."
        )

    resume_candidate = (
        runtime
        / "generated_resume_content_pair_candidate.json"
    )

    cover_candidate = (
        runtime
        / "generated_cover_letter_pair_candidate.json"
    )

    if not resume_candidate.is_file():
        raise RuntimeError(
            "Resume writer candidate is missing."
        )

    if not cover_candidate.is_file():
        raise RuntimeError(
            "Cover writer candidate is missing."
        )

    cover = load_json(
        cover_candidate
    )

    company, position = job_identity(
        manifest,
        cover,
    )

    job_slug = (
        slug(
            company,
            45,
        )
        + "_"
        + slug(
            position,
            55,
        )
    )

    override_runtime = (
        runtime
        / "user_override"
    )

    override_output = (
        run_root
        / "output"
        / "user_override"
    )

    override_runtime.mkdir(
        parents=True,
        exist_ok=True,
    )

    override_output.mkdir(
        parents=True,
        exist_ok=True,
    )

    #
    # The resume payload builder is intentionally runtime-relative for
    # deterministic job context. An isolated override renderer therefore
    # carries forward only the exact preserved context inputs that the
    # already-accepted payload builder requires. It does not reconstruct
    # them, reinterpret them, or mutate the original run.
    required_render_context = (
        "role_routing.json",
        "summary_route.json",
    )

    for context_name in required_render_context:
        source_context = (
            runtime
            / context_name
        )

        if not source_context.is_file():
            raise RuntimeError(
                "Override rendering requires preserved payload context: "
                + str(source_context)
            )

        target_context = (
            override_runtime
            / context_name
        )

        target_context.write_bytes(
            source_context.read_bytes()
        )

        if sha(target_context) != sha(source_context):
            raise RuntimeError(
                "Override payload-context copy mismatch: "
                + context_name
            )

    payload = (
        override_runtime
        / "career_ops_cv_payload.json"
    )

    payload_validation = (
        override_runtime
        / "career_ops_cv_payload_validation.json"
    )

    resume_html = (
        override_runtime
        / "resume_render.html"
    )

    adaptive_html = (
        override_runtime
        / "resume_adaptive.html"
    )

    adaptive_report = (
        override_runtime
        / "adaptive_layout_report.json"
    )

    cover_html = (
        override_runtime
        / "cover_render.html"
    )

    resume_pdf = (
        override_output
        / (
            "careerops_resume_"
            + job_slug
            + "_user_override_unreleased.pdf"
        )
    )

    resume_docx = (
        override_output
        / (
            "careerops_resume_"
            + job_slug
            + "_user_override_unreleased.docx"
        )
    )

    cover_pdf = (
        override_output
        / (
            "careerops_cover_"
            + job_slug
            + "_user_override_unreleased.pdf"
        )
    )

    cover_docx = (
        override_output
        / (
            "careerops_cover_"
            + job_slug
            + "_user_override_unreleased.docx"
        )
    )

    manifest_before = sha(
        manifest_path
    )

    env = clean_env({
        "CAREEROPS_RUN_ID":
            run_id,

        "CAREEROPS_RUNTIME_DIR":
            str(
                override_runtime
            ),

        "CAREEROPS_OUTPUT_DIR":
            str(
                override_output
            ),

        "CAREEROPS_JOB_COMPANY":
            company,

        "CAREEROPS_JOB_POSITION":
            position,

        "CAREEROPS_RESUME_INPUT":
            str(
                resume_candidate
            ),

        "CAREEROPS_CV_PAYLOAD_OUTPUT":
            str(
                payload
            ),

        "CAREEROPS_CV_PAYLOAD_VALIDATION_OUTPUT":
            str(
                payload_validation
            ),

        "CAREEROPS_RESUME_OUTPUT":
            str(
                resume_docx
            ),

        "CAREER_OPS_PDF_INDEX":
            str(
                override_runtime
                / "pdf-index.tsv"
            ),
    })

    from careerops_adaptive_content_budget import select_existing_pair
    from careerops_requirement_regeneration import canonical_ledger_path
    def load_page_input(name):return json.loads((runtime / name).read_text())
    full_content=json.loads(resume_candidate.read_text())
    subset,selection=select_existing_pair(full_content,load_page_input('experience_selection.json'),load_page_input('project_selection.json'),json.loads(canonical_ledger_path(runtime).read_text()),load_page_input('technical_skills_plan.json'))
    if selection['omitted_but_preserved_in_original_pair']:
        audited={x['text'] for x in load_page_input('claim_map.json').get('claims',[]) if x.get('status') in {'SUPPORTED','SUPPORTED_BY_DIRECT_USER_OVERRIDE'}}
        if any(x['text'] not in audited for x in selection['retained']):raise RuntimeError('Override page subset contains an unaudited claim.')
        subset_path=override_runtime/'generated_resume_render_subset.json'
        subset_path.write_text(json.dumps(subset,indent=2)+'\n')
        env['CAREEROPS_RESUME_INPUT']=str(subset_path)
    (override_runtime/'page_content_selection.json').write_text(json.dumps(selection,indent=2)+'\n')

    run_command(
        "USER OVERRIDE: BUILD RESUME PAYLOAD",
        [
            PYTHON,
            ROOT
            / "scripts"
            / "careerops_build_cv_payload.py",
        ],
        env,
    )

    env[
        "CAREEROPS_RESUME_INPUT"
    ] = str(
        payload
    )

    run_command(
        "USER OVERRIDE: RESUME HTML",
        [
            "node",
            ROOT
            / "build-cv-html.mjs",
            payload,
            resume_html,
            TEMPLATE,
        ],
        env,
    )

    run_command(
        "USER OVERRIDE: ADAPTIVE ONE-PAGE SOLVER",
        [
            "node",
            ROOT
            / "scripts"
            / "careerops_adaptive_layout.mjs",
            resume_html,
            adaptive_html,
            adaptive_report,
        ],
        env,
    )

    run_command(
        "USER OVERRIDE: RESUME PDF",
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
        env,
    )

    run_command(
        "USER OVERRIDE: RESUME DOCX",
        [
            PYTHON,
            ROOT
            / "scripts"
            / "careerops_docx_renderer.py",
        ],
        env,
    )

    run_command(
        "USER OVERRIDE: COVER PDF UNGATED",
        [
            "node",
            ROOT
            / "scripts"
            / "careerops_render_cover.mjs",
            "--cover",
            cover_candidate,
            "--identity",
            payload,
            "--allow-ungated",
            "--out",
            cover_pdf,
            "--html",
            cover_html,
        ],
        env,
    )

    run_command(
        "USER OVERRIDE: COVER DOCX UNGATED",
        [
            PYTHON,
            ROOT
            / "scripts"
            / "careerops_render_cover_docx.py",
            "--cover",
            cover_candidate,
            "--identity",
            payload,
            "--allow-ungated",
            "--out",
            cover_docx,
        ],
        env,
    )

    artifacts = {
        "resume_pdf":
            resume_pdf,

        "resume_docx":
            resume_docx,

        "cover_pdf":
            cover_pdf,

        "cover_docx":
            cover_docx,
    }

    missing = [
        name
        for name, path in artifacts.items()
        if (
            not path.is_file()
            or path.stat().st_size <= 0
        )
    ]

    if missing:
        raise RuntimeError(
            "Override renderer did not create: "
            + ", ".join(
                missing
            )
        )

    manifest_after = sha(
        manifest_path
    )

    if (
        manifest_after
        != manifest_before
    ):
        raise RuntimeError(
            "Automatic run manifest changed during "
            "isolated override rendering."
        )

    authorization = load_json(
        runtime
        / "user_generation_override_authorization.json"
    )

    decision_receipt = load_json(
        runtime
        / "job_decision_receipt.json"
    )

    report = {
        "schema_version":
            "career-ops-user-override-generated-v2",

        "created_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "status":
            "USER_OVERRIDE_GENERATED",

        "authority":
            "EXPLICIT_USER",

        "run_id":
            run_id,

        "company":
            company,

        "position":
            position,

        "user_reason":
            reason,

        "automatic_engine_decision_preserved":
            True,

        "automatic_manifest_sha256":
            manifest_after,

        "original_decision_receipt":
            decision_receipt,

        "authorization":
            authorization,

        "failure_snapshot":
            failure_snapshot(
                runtime,
                manifest,
            ),

        "execution": {
            "model_calls":
                int(
                    execution.get(
                        "model_calls",
                        0,
                    )
                    or 0
                ),

            "writer_calls":
                writer_calls,

            "truth_audit_calls":
                int(
                    execution.get(
                        "truth_audit_calls",
                        0,
                    )
                    or 0
                ),
        },

        "writer_sources": {
            "resume_candidate": {
                "path":
                    str(
                        resume_candidate
                    ),

                "sha256":
                    sha(
                        resume_candidate
                    ),
            },

            "cover_candidate": {
                "path":
                    str(
                        cover_candidate
                    ),

                "sha256":
                    sha(
                        cover_candidate
                    ),
            },
        },

        "outputs": {
            name: {
                "path":
                    str(
                        path
                    ),

                "sha256":
                    sha(
                        path
                    ),

                "size_bytes":
                    path.stat().st_size,
            }

            for name, path in artifacts.items()
        },

        "release_ready":
            False,

        "normal_release_gate_invoked":
            False,

        "root_publish_authorized":
            False,

        "output_class":
            "UNRELEASED_USER_OVERRIDE",

        "warning":
            (
                "These documents were produced under explicit user "
                "override. Automatic CareerOps rejection/failure "
                "evidence remains authoritative and was not cleared."
            ),
    }

    report_path = (
        override_runtime
        / "user_override_generation_report.json"
    )

    atomic_json(
        report_path,
        report,
    )

    print()
    print(
        "=" * 96
    )
    print(
        "USER OVERRIDE OUTPUT STATUS: USER_OVERRIDE_GENERATED"
    )
    print(
        "RELEASE READY: NO"
    )
    print(
        "ROOT PUBLISH AUTHORIZED: NO"
    )
    print(
        "WRITER CALLS:",
        writer_calls,
    )
    print(
        "OUTPUT DIRECTORY:",
        override_output,
    )
    print(
        "REPORT:",
        report_path,
    )
    print(
        "=" * 96
    )

    return report


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Explicit user-authorized unreleased CareerOps "
            "resume/cover renderer."
        )
    )

    parser.add_argument(
        "--run-id",
        required=True,
    )

    parser.add_argument(
        "--reason",
        required=True,
    )

    args = parser.parse_args()

    generate_override(
        args.run_id,
        args.reason,
    )


if __name__ == "__main__":
    main()
