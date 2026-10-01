#!/usr/bin/env python3

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PYTHON = Path(sys.executable)

ORCHESTRATOR = (
    ROOT
    / "scripts"
    / "careerops_production_orchestrator.py"
)

RUNS = (
    ROOT
    / "data"
    / "careerops-engine"
    / "runs"
)

BATCHES = (
    ROOT
    / "data"
    / "careerops-engine"
    / "batches"
)

STOP_CHOICES = {
    "pair_packet",
    "writer",
    "gates",
    "render",
    "release",
}


def now_utc():
    return (
        datetime.now(
            timezone.utc
        )
        .strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    )


def stamp():
    return (
        datetime.now(
            timezone.utc
        )
        .strftime(
            "%Y%m%dT%H%M%SZ"
        )
    )


def slug(
    value,
    limit=48,
):
    text = re.sub(
        r"[^a-z0-9]+",
        "_",
        str(
            value
            or ""
        ).casefold(),
    ).strip("_")

    text = (
        text[:limit]
        .strip("_")
    )

    return (
        text
        or "job"
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


def atomic_write_json(
    path,
    data,
):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tmp = path.with_suffix(
        path.suffix
        + ".tmp"
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


def validate_run_id(
    value,
):
    return bool(
        re.fullmatch(
            r"[A-Za-z0-9]"
            r"[A-Za-z0-9._-]{0,127}",
            str(value or ""),
        )
    )


def generated_run_id(
    batch_id,
    index,
    company,
    position,
):
    value = (
        batch_id
        + "_"
        + f"{index:03d}"
        + "_"
        + slug(
            company,
            28,
        )
        + "_"
        + slug(
            position,
            38,
        )
    )

    return value[:128]


def manifest_path(
    run_id,
):
    return (
        RUNS
        / run_id
        / "manifest.json"
    )


def release_report_path(
    run_id,
):
    return (
        RUNS
        / run_id
        / "runtime"
        / "pair_release_gate_report.json"
    )


def summarize_run(
    run_id,
    rc,
):
    manifest = (
        read_json(
            manifest_path(
                run_id
            )
        )
        or {}
    )

    release = (
        read_json(
            release_report_path(
                run_id
            )
        )
        or {}
    )

    execution = manifest.get(
        "execution",
        {},
    )

    summary = {
        "run_id":
            run_id,

        "process_rc":
            rc,

        "success":
            rc == 0,

        "lifecycle_status":
            manifest.get(
                "lifecycle_status"
            ),

        "resumable_from":
            manifest.get(
                "resumable_from"
            ),

        "model_calls":
            execution.get(
                "model_calls",
                0,
            ),

        "target_model":
            execution.get(
                "target_model"
            ),

        "release_ready":
            release.get(
                "release_ready"
            ),

        "manifest":
            str(
                manifest_path(
                    run_id
                ).relative_to(
                    ROOT
                )
            ),

        "release_report":
            (
                str(
                    release_report_path(
                        run_id
                    ).relative_to(
                        ROOT
                    )
                )
                if release_report_path(
                    run_id
                ).exists()
                else None
            ),
    }
    from careerops_run_outcome import emit_run_outcome
    summary.update(emit_run_outcome(run_id, rc, root=ROOT))
    return summary


def validate_new_job(
    job,
    index,
):
    company = str(
        job.get(
            "company",
            ""
        )
    ).strip()

    position = str(
        job.get(
            "position",
            ""
        )
    ).strip()

    jd_file = job.get(
        "jd_file"
    )

    jd_text = job.get(
        "jd_text"
    )

    if not company:
        raise ValueError(
            f"Job {index}: company is required."
        )

    if not position:
        raise ValueError(
            f"Job {index}: position is required."
        )

    if bool(
        jd_file
    ) == bool(
        jd_text
    ):
        raise ValueError(
            f"Job {index}: provide exactly one "
            "of jd_file or jd_text."
        )

    if jd_file:
        path = Path(
            jd_file
        ).expanduser()

        if not path.is_absolute():
            path = (
                ROOT
                / path
            )

        path = path.resolve()

        if not path.exists():
            raise ValueError(
                f"Job {index}: jd_file does "
                f"not exist: {path}"
            )


def validate_job(
    job,
    index,
):
    if not isinstance(
        job,
        dict,
    ):
        raise ValueError(
            f"Job {index}: entry must be an object."
        )

    resume_run = job.get(
        "resume_run"
    )

    if resume_run:
        if not validate_run_id(
            resume_run
        ):
            raise ValueError(
                f"Job {index}: invalid resume_run."
            )

        run_dir = (
            RUNS
            / resume_run
        )

        if not run_dir.exists():
            raise ValueError(
                f"Job {index}: resume_run does "
                f"not exist: {resume_run}"
            )

        if (
            job.get("jd_file")
            or job.get("jd_text")
            or job.get("run_id")
        ):
            raise ValueError(
                f"Job {index}: resume_run cannot "
                "be combined with jd_file, jd_text, "
                "or run_id."
            )

    else:
        validate_new_job(
            job,
            index,
        )

        run_id = job.get(
            "run_id"
        )

        if (
            run_id
            and not validate_run_id(
                run_id
            )
        ):
            raise ValueError(
                f"Job {index}: invalid run_id."
            )

    stop = job.get(
        "stop_after"
    )

    if (
        stop
        and stop not in STOP_CHOICES
    ):
        raise ValueError(
            f"Job {index}: invalid stop_after "
            f"{stop!r}."
        )


def load_batch_spec(
    path,
):
    spec = read_json(
        path
    )

    if isinstance(
        spec,
        list,
    ):
        jobs = spec

        metadata = {}

    elif isinstance(
        spec,
        dict,
    ):
        jobs = spec.get(
            "jobs"
        )

        metadata = {
            key:
                value
            for key, value
            in spec.items()
            if key != "jobs"
        }

    else:
        raise ValueError(
            "Batch manifest must be either "
            "an array or an object with jobs[]."
        )

    if (
        not isinstance(
            jobs,
            list,
        )
        or not jobs
    ):
        raise ValueError(
            "Batch manifest must contain "
            "at least one job."
        )

    for index, job in enumerate(
        jobs,
        start=1,
    ):
        validate_job(
            job,
            index,
        )

    return metadata, jobs


def make_command(
    job,
    *,
    batch_id,
    index,
    default_stop,
):
    resume_run = job.get(
        "resume_run"
    )

    stop_after = (
        job.get(
            "stop_after"
        )
        or default_stop
    )

    if resume_run:
        command = [
            PYTHON,
            ORCHESTRATOR,
            "--resume-run",
            resume_run,
            "--stop-after",
            stop_after,
        ]

        company = job.get(
            "company"
        )

        position = job.get(
            "position"
        )

        if company:
            command.extend([
                "--company",
                str(company),
            ])

        if position:
            command.extend([
                "--position",
                str(position),
            ])

        return (
            resume_run,
            command,
        )

    company = str(
        job["company"]
    ).strip()

    position = str(
        job["position"]
    ).strip()

    run_id = (
        job.get(
            "run_id"
        )
        or generated_run_id(
            batch_id,
            index,
            company,
            position,
        )
    )

    command = [
        PYTHON,
        ORCHESTRATOR,
        "--company",
        company,
        "--position",
        position,
        "--run-id",
        run_id,
        "--stop-after",
        stop_after,
    ]

    if job.get(
        "jd_file"
    ):
        source = Path(
            job[
                "jd_file"
            ]
        ).expanduser()

        if not source.is_absolute():
            source = (
                ROOT
                / source
            )

        command.extend([
            "--jd-file",
            source.resolve(),
        ])

    else:
        command.extend([
            "--jd-text",
            str(
                job[
                    "jd_text"
                ]
            ),
        ])

    if job.get(
        "application_url"
    ):
        command.extend([
            "--application-url",
            str(
                job[
                    "application_url"
                ]
            ),
        ])

    return (
        run_id,
        command,
    )


def self_test():
    checks = {
        "python_exists":
            PYTHON.exists(),

        "orchestrator_exists":
            ORCHESTRATOR.exists(),

        "stop_choices_match":
            STOP_CHOICES
            == {
                "pair_packet",
                "writer",
                "gates",
                "render",
                "release",
            },

        "run_id_validator_accepts_normal":
            validate_run_id(
                "batch_001_test_job"
            ),

        "run_id_validator_rejects_space":
            not validate_run_id(
                "bad run id"
            ),

        "generated_run_id_valid":
            validate_run_id(
                generated_run_id(
                    "example_batch",
                    1,
                    "Example Company",
                    "Data Analyst",
                )
            ),
    }

    source = (
        ORCHESTRATOR.read_text(
            encoding="utf-8"
        )
        if ORCHESTRATOR.exists()
        else ""
    )

    checks[
        "orchestrator_supports_run_id"
    ] = (
        "--run-id"
        in source
    )

    checks[
        "orchestrator_supports_resume"
    ] = (
        "--resume-run"
        in source
    )

    checks[
        "orchestrator_supports_stop"
    ] = (
        "--stop-after"
        in source
    )

    print(
        "=" * 88
    )

    print(
        "CAREEROPS BATCH RUNNER SELF-TEST"
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
        "BATCH RUNNER STATIC CONTRACT: PASS"
    )

    print(
        "MODEL CALLS: 0"
    )

    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Sequential isolated batch runner for "
            "the CareerOps Career-Ops production orchestrator."
        )
    )

    parser.add_argument(
        "--manifest",
        help=(
            "JSON batch manifest."
        ),
    )

    parser.add_argument(
        "--batch-id",
    )

    parser.add_argument(
        "--stop-after",
        choices=sorted(
            STOP_CHOICES
        ),
        default="release",
        help=(
            "Default stop stage. Individual jobs "
            "may override with stop_after."
        ),
    )

    parser.add_argument(
        "--continue-on-error",
        action="store_true",
    )

    parser.add_argument(
        "--self-test",
        action="store_true",
    )

    return parser


def main():
    args = build_parser().parse_args()
    if args.self_test:
        return self_test()
    if not args.manifest:
        raise SystemExit('--manifest is required.')
    manifest_file = Path(args.manifest).expanduser()
    if not manifest_file.is_absolute():
        manifest_file = ROOT / manifest_file
    manifest_file = manifest_file.resolve()
    if not manifest_file.exists():
        raise SystemExit('Batch manifest does not exist: ' + str(manifest_file))
    try:
        metadata, jobs = load_batch_spec(manifest_file)
    except ValueError as exc:
        raise SystemExit(str(exc))
    batch_id = args.batch_id or metadata.get('batch_id') or 'batch_' + stamp()
    if not validate_run_id(batch_id):
        raise SystemExit('Invalid batch_id.')
    batch_dir = BATCHES / batch_id
    if batch_dir.exists():
        raise SystemExit('Batch directory already exists: ' + str(batch_dir))
    batch_dir.mkdir(parents=True)
    report_path = batch_dir / 'batch_report.json'
    report = {'schema_version': 'careerops-batch-runner-v1', 'batch_id': batch_id, 'created_at': now_utc(), 'source_manifest': str(manifest_file.relative_to(ROOT) if manifest_file.is_relative_to(ROOT) else manifest_file), 'default_stop_after': args.stop_after, 'continue_on_error': args.continue_on_error, 'job_count': len(jobs), 'jobs': [], 'completed': False, 'success': False, 'total_model_calls': 0}
    atomic_write_json(report_path, report)
    any_failure = False
    semantic_pending = []
    for index, job in enumerate(jobs, start=1):
        run_id, command = make_command(job, batch_id=batch_id, index=index, default_stop=args.stop_after)
        print()
        print('=' * 100)
        print(f'BATCH JOB {index}/{len(jobs)}')
        print('RUN ID:', run_id)
        if job.get('resume_run'):
            print('MODE: RESUME')
        else:
            print('COMPANY:', job.get('company'))
            print('POSITION:', job.get('position'))
        print('=' * 100)
        result = subprocess.run([str(x) for x in command], cwd=ROOT, check=False, env={**__import__('os').environ, 'CAREEROPS_SHARED_SEMANTIC_DEFER': '1'})
        summary = summarize_run(run_id, result.returncode)
        summary['index'] = index
        summary['company'] = job.get('company')
        summary['position'] = job.get('position')
        summary['stop_after'] = job.get('stop_after') or args.stop_after
        report['jobs'].append(summary)
        report['total_model_calls'] = sum((int(row.get('model_calls') or 0) for row in report['jobs']))
        atomic_write_json(report_path, report)
        if result.returncode != 0:
            from careerops_automatic_semantic_escalation import queued_case
            from careerops_production_configuration import apply
            if apply(__import__('os').environ).get('CAREEROPS_SHARED_SOL_SEMANTIC') == '1' and queued_case(run_id):
                semantic_pending.append((run_id, job.get('stop_after') or args.stop_after))
                continue
            any_failure = True
            if not args.continue_on_error:
                print()
                print(f'BATCH FAIL-FAST: stopping after job {index}.')
                break
    if semantic_pending:
        from careerops_automatic_semantic_escalation import automatic_batch
        semantic_result = automatic_batch([run for run, stop in semantic_pending])
        report['shared_semantic_escalation'] = semantic_result
        for run, stop in semantic_pending:
            if run not in semantic_result.get('continued_runs', []):
                continue
            command = [str(sys.executable), str(ROOT / 'scripts/careerops_production_orchestrator.py'), '--resume-run', run, '--stop-after', stop]
            result = subprocess.run(command, cwd=ROOT, check=False)
            updated = summarize_run(run, result.returncode)
            for row in report['jobs']:
                if row['run_id'] == run:
                    row.update(updated)
    report['completed'] = len(report['jobs']) == len(jobs)
    report['success'] = report['completed'] and (not any((not row.get('success') for row in report['jobs'])))
    from careerops_automatic_semantic_escalation import aggregate_accounting
    report['model_accounting'] = aggregate_accounting([row['run_id'] for row in report['jobs'] if row.get('run_id')])
    report['total_model_calls'] = report['model_accounting']['total_observed_model_attempts']
    report['finished_at'] = now_utc()
    report['total_model_calls'] = sum((int(row.get('model_calls') or 0) for row in report['jobs']))
    atomic_write_json(report_path, report)
    print()
    print('=' * 100)
    print('CAREEROPS BATCH RUNNER V1: COMPLETE')
    print('=' * 100)
    print('BATCH ID:', batch_id)
    print('JOBS REQUESTED:', len(jobs))
    print('JOBS EXECUTED:', len(report['jobs']))
    print('TOTAL MODEL CALLS:', report['total_model_calls'])
    print('SUCCESS:', report['success'])
    print('REPORT:', report_path)
    from careerops_run_outcome import print_batch_artifact_delivery
    print_batch_artifact_delivery(report, root=ROOT)
    return 0 if report['success'] else 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
