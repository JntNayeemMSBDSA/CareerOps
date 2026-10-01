#!/usr/bin/env python3

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PYTHON = Path(sys.executable)

ORCHESTRATOR = (
    ROOT
    / "scripts"
    / "careerops_production_orchestrator.py"
)

USER_OVERRIDE_GENERATOR = (
    ROOT
    / "scripts"
    / "careerops_user_override_generate.py"
)

INGEST = (
    ROOT
    / "scripts"
    / "careerops_ingest_jd.py"
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

PASTE_TERMINATOR = "::ENDJD::"

MODEL_ENV_KEYS = {
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "CODEX_API_KEY",
    "CODEX_ACCESS_TOKEN",
}


def now_utc():
    return datetime.now(
        timezone.utc
    ).isoformat()


def stamp():
    return datetime.now(
        timezone.utc
    ).strftime(
        "%Y%m%dT%H%M%SZ"
    )


def slug(value, limit=42):
    value = re.sub(
        r"[^A-Za-z0-9]+",
        "_",
        str(value or "").strip(),
    ).strip("_").lower()

    return (
        value[:limit]
        or "job"
    )


def clean_env(extra=None):
    env = os.environ.copy()

    for key in MODEL_ENV_KEYS:
        env.pop(
            key,
            None,
        )

    if extra:
        env.update(
            {
                str(k): str(v)
                for k, v
                in extra.items()
            }
        )

    return env


def atomic_json(path, data):
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

    tmp.replace(path)


def read_json(path):
    try:
        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return None


def validate_text(text):
    text = str(
        text or ""
    ).strip()

    if len(text) < 150:
        raise ValueError(
            "JD text is too short. Paste the full "
            "job description, not only the title."
        )

    return text


def read_raw_paste(
    company,
    position,
):
    print()
    print("=" * 88)
    print("RAW JD PASTE")
    print("=" * 88)
    print("COMPANY:", company)
    print("POSITION:", position)
    print()
    print(
        "Paste the job description exactly as copied."
    )
    print(
        "No reformatting, Markdown, JSON, or cleanup is required."
    )
    print()
    print(
        f"When finished, type {PASTE_TERMINATOR}"
    )
    print(
        "on its own line and press Enter."
    )
    print("=" * 88)
    print()

    lines = []

    for raw in sys.stdin:
        line = raw.rstrip(
            "\n"
        )

        if (
            line.strip()
            == PASTE_TERMINATOR
        ):
            break

        lines.append(
            line
        )

    text = "\n".join(
        lines
    ).strip()

    return validate_text(
        text
    )


class ClipboardText(str):
    def __new__(cls, value, metadata):
        obj = str.__new__(cls, value)
        obj.metadata = metadata
        return obj


def clipboard_text():
    """Windows owns the clipboard; transport Unicode and HTML MIME losslessly."""
    import base64
    powershell = shutil.which('powershell.exe')
    if not powershell:
        raise RuntimeError('powershell.exe is unavailable for the Windows clipboard.')
    script = r"""
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Windows.Forms
$careerObject = [System.Windows.Forms.Clipboard]::GetDataObject()
$careerText = Get-Clipboard -Raw
$careerHtml = if ($careerObject -and $careerObject.GetDataPresent('HTML Format')) { [string]$careerObject.GetData('HTML Format') } else { '' }
$careerFormats = if ($careerObject) { @($careerObject.GetFormats()) } else { @() }
@{schema='windows-clipboard-mime-v1';formats=$careerFormats;text_utf8_base64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes([string]$careerText));html_utf8_base64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($careerHtml))} | ConvertTo-Json -Compress
"""
    encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    result = subprocess.run([powershell,'-STA','-NoProfile','-NonInteractive','-EncodedCommand',encoded],cwd=ROOT,capture_output=True,check=False)
    if result.returncode:
        raise RuntimeError('Windows clipboard transport failed: '+result.stderr.decode('utf-8',errors='replace').strip())
    try:
        metadata = json.loads(result.stdout.decode('utf-8-sig'))
        text = base64.b64decode(metadata['text_utf8_base64']).decode('utf-8')
        html = base64.b64decode(metadata['html_utf8_base64']).decode('utf-8')
    except (ValueError,KeyError,UnicodeError) as exc:
        raise RuntimeError('Invalid Windows clipboard MIME transport') from exc
    if not text.strip() and html:
        from careerops_ingest_jd import html_to_text
        start = html.find('<')
        text = html_to_text(html[start:] if start >= 0 else html)
        metadata['selected_representation'] = 'HTML_VISIBLE_TEXT'
    else:
        metadata['selected_representation'] = 'UNICODE_TEXT'
    return ClipboardText(validate_text(text), metadata)


def probe_url(url):
    """
    Deterministic URL probe only.

    No model call occurs here.
    """

    # careerops_ingest_jd.py reports its output relative to ROOT.
    # Keep deterministic probe runtimes inside Career-Ops so its
    # existing output/reporting contract remains valid.
    url = validate_job_url(url)

    probe_parent = (
        ROOT
        / "data"
        / "careerops-engine"
        / "probe-runtime"
    )

    probe_parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with tempfile.TemporaryDirectory(
        prefix="career-ops-url-probe-",
        dir=probe_parent,
    ) as td:
        runtime = Path(td)

        result = subprocess.run(
            [
                str(PYTHON),
                str(INGEST),
                "--url",
                str(url),
            ],
            cwd=ROOT,
            env=clean_env(
                {
                    "CAREEROPS_RUNTIME_DIR":
                        str(runtime),
                }
            ),
            text=True,
            capture_output=True,
            check=False,
        )

        intake_path = (
            runtime
            / "jd_intake.json"
        )

        intake = (
            read_json(
                intake_path
            )
            or {}
        )

        if (
            result.returncode
            not in {
                0,
                3,
            }
        ):
            return {
                "status":
                    "PROBE_ERROR",

                "source_url":
                    str(url),

                "fetch_error":
                    (
                        result.stderr.strip()
                        or result.stdout.strip()
                        or (
                            "URL probe returned RC "
                            + str(
                                result.returncode
                            )
                        )
                    ),

                "raw_jd_text":
                    None,
            }

        return intake


def save_text(
    path,
    text,
):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        validate_text(
            text
        )
        + "\n",
        encoding="utf-8",
    )

    return path


def generated_run_id(
    company,
    position,
    *,
    prefix="production",
):
    value = (
        prefix
        + "_"
        + stamp()
        + "_"
        + slug(
            company,
            28,
        )
        + "_"
        + slug(
            position,
            42,
        )
    )

    return value[:128]


def build_orchestrator_command(
    *,
    company=None,
    position=None,
    jd_file=None,
    application_url=None,
    url_first=False,
    run_id=None,
    resume_run=None,
    stop_after="release",
    user_override_generate=False,
    override_reason=None,
):
    command = [
        str(PYTHON),
        str(ORCHESTRATOR),
    ]

    if resume_run:
        command.extend([
            "--resume-run",
            str(resume_run),
            "--stop-after",
            str(stop_after),
        ])

        if user_override_generate:
            reason = str(
                override_reason
                or ""
            ).strip()

            if not reason:
                raise ValueError(
                    "User override generation requires "
                    "a non-empty reason."
                )

            command.extend([
                "--user-override-generate",
                "--override-reason",
                reason,
            ])

        elif override_reason:
            raise ValueError(
                "override_reason requires "
                "user_override_generate=True."
            )

        return command

    command.extend([
        "--company",
        str(company),
        "--position",
        str(position),
        "--jd-file",
        str(
            Path(
                jd_file
            ).resolve()
        ),
        "--stop-after",
        str(stop_after),
    ])

    if run_id:
        command.extend([
            "--run-id",
            str(run_id),
        ])

    if application_url:
        command.extend([
            "--application-url",
            str(
                application_url
            ),
        ])

    if url_first:
        command.append(
            "--url-first"
        )

    return command


def print_command(command):
    print()
    print("CAREER-OPS ENGINE COMMAND:")
    print(
        shlex.join(
            [
                str(x)
                for x in command
            ]
        )
    )

#
# User-facing UX only.
#
# Deterministic CareerOps still owns the automatic decision.
# This helper merely surfaces the already-accepted explicit override
# capability after an eligible interactive single/resume failure.
#
# Batch/noninteractive execution never waits for user input.


def _careerops_command_value(
    command,
    flag,
):
    values = [
        str(x)
        for x in command
    ]

    try:
        index = values.index(
            str(flag)
        )
    except ValueError:
        return None

    if (
        index + 1
        >= len(values)
    ):
        return None

    return values[
        index + 1
    ]


def _careerops_stage_status(
    manifest,
    stage,
):
    value = (
        manifest.get(
            "stages",
            {}
        ).get(
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


def _careerops_override_availability(
    command,
):
    values = [
        str(x)
        for x in command
    ]

    run_id = (
        _careerops_command_value(
            values,
            "--resume-run",
        )
        or
        _careerops_command_value(
            values,
            "--run-id",
        )
    )

    result = {
        "eligible": False,
        "run_id": run_id,
        "lifecycle": None,
        "mode": None,
        "reason": None,
        "writer_calls": None,
    }

    if not run_id:
        result["reason"] = (
            "No isolated CareerOps run ID is available."
        )

        return result

    if (
        "--user-override-generate"
        in values
    ):
        result["reason"] = (
            "This is already an explicit override execution."
        )

        return result

    run_root = (
        RUNS
        / str(run_id)
    )

    manifest_path = (
        run_root
        / "manifest.json"
    )

    manifest = (
        read_json(
            manifest_path
        )
        or {}
    )

    if not manifest:
        result["reason"] = (
            "Run manifest is unavailable."
        )

        return result

    lifecycle = (
        manifest.get(
            "lifecycle_status"
        )
        or manifest.get(
            "lifecycle"
        )
    )

    result[
        "lifecycle"
    ] = lifecycle

    if lifecycle not in {
        "REJECTED",
        "NEEDS_ATTENTION",
        "RELEASE_BLOCKED",
    }:
        result["reason"] = (
            "Run is not in an override-eligible failure lifecycle."
        )

        return result

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

    result[
        "writer_calls"
    ] = writer_calls

    runtime = (
        run_root
        / "runtime"
    )

    pair_packet = (
        runtime
        / "pair_generation_packet.json"
    )

    resume_pair = (
        runtime
        / "generated_resume_content_pair_candidate.json"
    )

    cover_pair = (
        runtime
        / "generated_cover_letter_pair_candidate.json"
    )

    writer_status = (
        _careerops_stage_status(
            manifest,
            "writer",
        )
    )

    from careerops_overall_override import preflight
    overall = preflight(run_root)
    if writer_calls == 0 or overall.get('hard_blocks'):
        result.update(overall)
        return result
    state=read_json(runtime/'writer_invocation_state.json') or {}
    if writer_calls==0:
        result.update(eligible=True,mode='TRUTHFUL_CURRENT_PACKET_FIRST_WRITER_ALLOWED',reason='Explicit approval may authorize exactly one first writer call; automatic failure remains preserved.')
        return result
    if writer_status=='PASS' and resume_pair.is_file() and cover_pair.is_file() and (writer_calls==1 or writer_calls==2 and state.get('exceptional_writer_retry_calls')==1):
        result.update(eligible=True,mode='POST_WRITER_REUSE_EXISTING_PAIR',reason='Explicit approval may reuse the exact existing pair with zero new writer calls.')
        return result
    if writer_calls==1 and state.get('transport_completed') and state.get('model_completed') is False:
        allowed=os.environ.get('CAREEROPS_ALLOW_EXCEPTIONAL_WRITER_RETRY')=='1' and os.environ.get('CAREEROPS_RETRY_CAPACITY_CONFIRMED')=='1'
        result.update(eligible=allowed,mode='EXPLICIT_FAILED_TRANSPORT_ONE_RETRY_ALLOWED' if allowed else None,reason='A single transport retry requires explicit retry policy and capacity confirmation; no automatic retry is permitted.')
        return result

    result["reason"] = (
        "Writer accounting is not compatible with override generation."
    )

    return result


def _careerops_offer_user_override(
    command,
    original_rc,
    *,
    interactive=None,
):
    availability = (
        _careerops_override_availability(
            command
        )
    )

    lifecycle = availability.get(
        "lifecycle"
    )

    if not availability.get(
        "eligible"
    ):
        if lifecycle in {
            "REJECTED",
            "NEEDS_ATTENTION",
        }:
            print()
            print("=" * 88)
            print("USER OVERRIDE GENERATION")
            print("=" * 88)
            print(
                "STATUS: UNAVAILABLE FOR THIS FAILURE STATE"
            )
            print(
                "RUN ID:",
                availability.get(
                    "run_id"
                ),
            )
            print(
                "LIFECYCLE:",
                lifecycle,
            )
            print(
                "REASON:",
                availability.get(
                    "reason"
                ),
            )
            print(
                "The automatic failure remains authoritative."
            )
            print("=" * 88)

        return None

    run_id = str(
        availability[
            "run_id"
        ]
    )

    if interactive is None:
        interactive = (
            sys.stdin.isatty()
            and sys.stdout.isatty()
        )

    print()
    print("=" * 88)
    print("CAREEROPS STOPPED BEFORE NORMAL RELEASE")
    print("=" * 88)
    print(
        "RUN ID:",
        run_id,
    )
    print(
        "LIFECYCLE:",
        availability.get(
            "lifecycle"
        ),
    )
    print(
        "OVERRIDE MODE:",
        availability.get(
            "mode"
        ),
    )
    print(
        "AUTOMATIC DECISION: PRESERVED"
    )
    print(
        "NORMAL RELEASE_READY: NOT FORGED"
    )
    print(
        "ROOT PUBLICATION: DISABLED"
    )
    print(
        "WRITER CALLS SO FAR:",
        availability.get(
            "writer_calls"
        ),
    )
    print(
        "OUTPUT STATE IF GENERATED: USER_OVERRIDE_GENERATED"
    )
    print()
    print(
        "You may explicitly request isolated resume/cover output "
        "despite this failed/rejected run."
    )

    if not interactive:
        print()
        print(
            "Interactive approval is unavailable in this execution mode."
        )
        print(
            "To authorize manually, run:"
        )
        print()
        print(
            shlex.join([
                str(PYTHON),
                str(
                    Path(__file__).resolve()
                ),
                "resume",
                run_id,
                "--stop-after",
                "render",
                "--user-override-generate",
                "--override-reason",
                "YOUR EXPLICIT REASON",
            ])
        )
        print("=" * 88)

        return None

    print()

    answer = input(
        "Generate isolated unreleased output anyway? [y/N]: "
    ).strip().lower()

    if answer not in {
        "y",
        "yes",
    }:
        print()
        print(
            "USER OVERRIDE: DECLINED"
        )
        print(
            "Original CareerOps failure preserved."
        )
        print("=" * 88)

        return None

    reason = input(
        "Override reason (required): "
    ).strip()

    if not reason:
        print()
        print(
            "USER OVERRIDE: CANCELLED"
        )
        print(
            "A non-empty explicit reason is required."
        )
        print(
            "Original CareerOps failure preserved."
        )
        print("=" * 88)

        return None

    override_command = (
        build_orchestrator_command(
            resume_run=run_id,
            stop_after="render",
            user_override_generate=True,
            override_reason=reason,
        )
    )

    print()
    print("=" * 88)
    print("EXPLICIT USER OVERRIDE AUTHORIZED")
    print("=" * 88)
    print(
        "Automatic failure remains preserved."
    )
    print(
        "Generating only isolated USER_OVERRIDE_GENERATED output."
    )
    print(
        "No automatic RELEASE_READY or root publication is authorized."
    )
    print(
        "OVERRIDE REASON:",
        reason,
    )

    print_command(
        override_command
    )

    override_result = (
        subprocess.run(
            [
                str(x)
                for x
                in override_command
            ],
            cwd=ROOT,
            check=False,
        )
    )

    print()
    print(
        "USER_OVERRIDE_RC:",
        override_result.returncode,
    )

    if override_result.returncode == 0:
        print(
            "USER_OVERRIDE_GENERATION: COMPLETED"
        )
    else:
        print(
            "USER_OVERRIDE_GENERATION: FAILED"
        )

    print("=" * 88)

    return override_result.returncode


def execute_orchestrator(
    command,
    *,
    plan_only=False,
    source_metadata_file=None,
):
    print_command(
        command
    )

    if plan_only:
        print()
        print(
            "PLAN ONLY: orchestrator was not executed."
        )
        print(
            "MODEL CALLS: 0"
        )

        return 0

    result = subprocess.run(
        [
            str(x)
            for x in command
        ],
        cwd=ROOT,
        env={**os.environ, **({'CAREEROPS_SOURCE_MIME_METADATA':str(source_metadata_file)} if source_metadata_file else {})},
        check=False,
    )

    override_rc = None

    if (
        len(sys.argv) > 1
        and str(sys.argv[1]) in {
            "single",
            "resume",
        }
        and "--user-override-generate"
        not in [
            str(x)
            for x in command
        ]
    ):
        override_rc = (
            _careerops_offer_user_override(
                command,
                result.returncode,
                interactive=(
                    sys.stdin.isatty()
                    and sys.stdout.isatty()
                ),
            )
        )

    final_rc = override_rc if override_rc is not None else result.returncode
    run_id = _careerops_command_value(command, "--run-id") or _careerops_command_value(command, "--resume-run")
    if run_id:
        from careerops_run_outcome import emit_run_outcome
        emit_run_outcome(run_id, final_rc, root=ROOT, print_human=True)
    return final_rc


def resolve_single_source(
    args,
):
    """
    Resolve the user's selected single-job input into one JD file.

    URL mode probes first so the wrapper knows immediately whether
    manual JD text is required.

    The production orchestrator still receives --url-first together
    with a safe fallback file, preserving the existing canonical
    URL-first/fallback architecture.
    """

    company = args.company
    position = args.position

    if args.jd_file:
        source = Path(
            args.jd_file
        ).expanduser().resolve()

        if not source.exists():
            raise ValueError(
                "JD file does not exist: "
                + str(source)
            )

        return {
            "jd_file":
                source,

            "application_url":
                args.application_url,

            "url_first":
                bool(
                    args.application_url
                    and not args.skip_url_probe
                ),

            "resolution":
                "JD_FILE",
        }

    if args.clipboard:
        text = clipboard_text()

        temp = tempfile.NamedTemporaryFile(
            prefix="career-ops-clipboard-",
            suffix=".txt",
            delete=False,
            mode="w",
            encoding="utf-8",
        )

        with temp:
            temp.write(
                text
                + "\n"
            )

        metadata_file = Path(temp.name + '.clipboard-mime.json')
        metadata_file.write_text(json.dumps(text.metadata, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')

        return {
            "jd_file":
                Path(
                    temp.name
                ),

            "temporary":
                True,

            "application_url":
                args.application_url,

            "url_first":
                bool(
                    args.application_url
                    and not args.skip_url_probe
                ),

            "source_metadata_file": metadata_file,
            "resolution":
                "CLIPBOARD",
        }

    if args.paste:
        text = read_raw_paste(
            company,
            position,
        )

        temp = tempfile.NamedTemporaryFile(
            prefix="career-ops-paste-",
            suffix=".txt",
            delete=False,
            mode="w",
            encoding="utf-8",
        )

        with temp:
            temp.write(
                text
                + "\n"
            )

        return {
            "jd_file":
                Path(
                    temp.name
                ),

            "temporary":
                True,

            "application_url":
                args.application_url,

            "url_first":
                bool(
                    args.application_url
                    and not args.skip_url_probe
                ),

            "resolution":
                "RAW_PASTE",
        }

    if args.url:
        print()
        print("=" * 88)
        print("URL JD PROBE")
        print("=" * 88)
        print("COMPANY:", company)
        print("POSITION:", position)
        print("URL:", args.url)
        print()

        intake = probe_url(
            args.url
        )

        status = intake.get(
            "status"
        )

        print(
            "URL STATUS:",
            status,
        )

        if status == "INGESTED":
            text = validate_text(
                intake.get(
                    "raw_jd_text"
                )
            )

            temp = tempfile.NamedTemporaryFile(
                prefix="career-ops-url-",
                suffix=".txt",
                delete=False,
                mode="w",
                encoding="utf-8",
            )

            with temp:
                temp.write(
                    text
                    + "\n"
                )

            print(
                "MANUAL JD REQUIRED: NO"
            )

            return {
                "jd_file":
                    Path(
                        temp.name
                    ),

                "temporary":
                    True,

                "application_url":
                    args.url,

                "url_first":
                    True,

                "resolution":
                    "URL_INGESTED",

                "identity_evidence":
                    intake.get(
                        "identity_evidence"
                    ),
            }

        reason = (
            intake.get(
                "instruction"
            )
            or intake.get(
                "fetch_error"
            )
            or "URL did not provide a usable JD."
        )

        print(
            "MANUAL JD REQUIRED: YES"
        )

        print(
            "REASON:",
            reason,
        )

        if args.no_prompt:
            return {
                "manual_required":
                    True,

                "application_url":
                    args.url,

                "reason":
                    reason,

                "resolution":
                    "NEEDS_MANUAL_JD",
            }

        text = read_raw_paste(
            company,
            position,
        )

        temp = tempfile.NamedTemporaryFile(
            prefix="career-ops-manual-",
            suffix=".txt",
            delete=False,
            mode="w",
            encoding="utf-8",
        )

        with temp:
            temp.write(
                text
                + "\n"
            )

        return {
            "jd_file":
                Path(
                    temp.name
                ),

            "temporary":
                True,

            "application_url":
                args.url,

            "url_first":
                True,

            "resolution":
                "MANUAL_JD_FALLBACK",
        }

    # No explicit source means raw paste.
    text = read_raw_paste(
        company,
        position,
    )

    temp = tempfile.NamedTemporaryFile(
        prefix="career-ops-paste-",
        suffix=".txt",
        delete=False,
        mode="w",
        encoding="utf-8",
    )

    with temp:
        temp.write(
            text
            + "\n"
        )

    return {
        "jd_file":
            Path(
                temp.name
            ),

        "temporary":
            True,

        "application_url":
            args.application_url,

        "url_first":
            bool(
                args.application_url
                and not args.skip_url_probe
            ),

        "resolution":
            "RAW_PASTE",
    }

#
# Single-job UX policy:
# - explicit user company/title remain authoritative
# - missing values may auto-fill only from HIGH-confidence,
#   CURRENT-requisition-confirmed deterministic evidence
# - conflicting HIGH values never silently resolve
# - interactive mode asks only for the unresolved field(s)
# - --no-prompt stops before the engine rather than guessing


def probe_identity_from_jd_file(
    jd_file,
):
    if not jd_file:
        return None

    source = Path(
        jd_file
    )

    if not source.exists():
        return None

    probe_parent = (
        ROOT
        / "data"
        / "careerops-engine"
        / "ux_identity_probes"
    )

    probe_parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with tempfile.TemporaryDirectory(
        prefix="career-ops-identity-file-",
        dir=probe_parent,
    ) as td:
        runtime = Path(
            td
        )

        result = subprocess.run(
            [
                str(PYTHON),
                str(INGEST),
                "--file",
                str(source),
            ],
            cwd=ROOT,
            env=clean_env(
                {
                    "CAREEROPS_RUNTIME_DIR":
                        str(runtime),
                }
            ),
            text=True,
            capture_output=True,
            check=False,
        )

        intake = (
            read_json(
                runtime
                / "jd_intake.json"
            )
            or {}
        )

        if result.returncode != 0:
            return None

        return intake.get(
            "identity_evidence"
        )


def collect_single_identity_evidence(
    source,
):
    evidence_sets = []

    existing = source.get(
        "identity_evidence"
    )

    if existing:
        evidence_sets.append(
            {
                "origin":
                    "SOURCE_RESOLUTION",
                "evidence":
                    existing,
            }
        )

    application_url = str(
        source.get(
            "application_url"
        )
        or ""
    ).strip()

    # If the source itself was not already the successful URL probe,
    # an application URL can contribute structured JSON-LD/H1/title
    # evidence without changing the selected JD source.
    if (
        application_url
        and source.get(
            "resolution"
        )
        != "URL_INGESTED"
    ):
        try:
            intake = probe_url(
                application_url
            )
        except Exception:
            intake = {}

        url_evidence = (
            intake.get(
                "identity_evidence"
            )
            if isinstance(
                intake,
                dict,
            )
            else None
        )

        if url_evidence:
            evidence_sets.append(
                {
                    "origin":
                        "APPLICATION_URL_PROBE",
                    "evidence":
                        url_evidence,
                }
            )

    file_evidence = (
        probe_identity_from_jd_file(
            source.get(
                "jd_file"
            )
        )
    )

    if file_evidence:
        evidence_sets.append(
            {
                "origin":
                    "JD_FILE_INGEST",
                "evidence":
                    file_evidence,
            }
        )

    return evidence_sets


def high_identity_options(
    evidence_sets,
    field,
):
    options = {}

    def add_option(
        value,
        *,
        origin,
        sources,
    ):
        value = str(
            value or ""
        ).strip()

        if not value:
            return

        key = re.sub(
            r"[^a-z0-9]+",
            " ",
            value.casefold(),
        ).strip()

        if not key:
            return

        row = options.setdefault(
            key,
            {
                "value":
                    value,
                "origins":
                    set(),
                "sources":
                    set(),
            },
        )

        row[
            "origins"
        ].add(
            origin
        )

        for source_name in (
            sources
            or []
        ):
            if source_name:
                row[
                    "sources"
                ].add(
                    str(
                        source_name
                    )
                )

    for bundle in evidence_sets:
        origin = bundle.get(
            "origin"
        )

        evidence = (
            bundle.get(
                "evidence"
            )
            or {}
        )

        row = (
            evidence.get(
                field
            )
            or {}
        )

        if (
            row.get(
                "confidence"
            )
            == "HIGH"
            and row.get(
                "confirmed_in_current_job"
            )
            and row.get(
                "value"
            )
        ):
            add_option(
                row.get(
                    "value"
                ),
                origin=origin,
                sources=row.get(
                    "sources"
                ),
            )

        # Preserve explicit ambiguity from the deterministic evidence
        # layer so the UX can ask rather than guess.
        for alt in (
            row.get(
                "alternatives"
            )
            or []
        ):
            if not (
                alt.get(
                    "confirmed_in_current_job"
                )
                and alt.get(
                    "has_high_source"
                )
            ):
                continue

            add_option(
                alt.get(
                    "value"
                ),
                origin=origin,
                sources=alt.get(
                    "sources"
                ),
            )

    result = []

    for row in options.values():
        result.append(
            {
                "value":
                    row[
                        "value"
                    ],
                "origins":
                    sorted(
                        row[
                            "origins"
                        ]
                    ),
                "sources":
                    sorted(
                        row[
                            "sources"
                        ]
                    ),
            }
        )

    result.sort(
        key=lambda row:
            row[
                "value"
            ].casefold()
    )

    return result


def prompt_identity_value(
    label,
    options,
):
    print()
    print(
        label.upper(),
        "requires confirmation."
    )

    if options:
        print(
            "Current requisition candidates:"
        )

        for index, row in enumerate(
            options,
            start=1,
        ):
            print(
                f"  {index}.",
                row[
                    "value"
                ],
            )

    value = input(
        f"{label}: "
    ).strip()

    if not value:
        raise ValueError(
            f"{label} is required."
        )

    return value


def resolve_single_identity(
    args,
    source,
):
    explicit_company = str(
        args.company
        or ""
    ).strip()

    explicit_position = str(
        args.position
        or ""
    ).strip()

    evidence_sets = (
        collect_single_identity_evidence(
            source
        )
    )

    company_options = (
        high_identity_options(
            evidence_sets,
            "company",
        )
    )

    position_options = (
        high_identity_options(
            evidence_sets,
            "position",
        )
    )

    company = (
        explicit_company
        or (
            company_options[
                0
            ][
                "value"
            ]
            if len(
                company_options
            )
            == 1
            else ""
        )
    )

    position = (
        explicit_position
        or (
            position_options[
                0
            ][
                "value"
            ]
            if len(
                position_options
            )
            == 1
            else ""
        )
    )

    company_mode = (
        "USER_SUPPLIED"
        if explicit_company
        else (
            "AUTO_HIGH"
            if company
            else (
                "AMBIGUOUS"
                if len(
                    company_options
                )
                > 1
                else "UNRESOLVED"
            )
        )
    )

    position_mode = (
        "USER_SUPPLIED"
        if explicit_position
        else (
            "AUTO_HIGH"
            if position
            else (
                "AMBIGUOUS"
                if len(
                    position_options
                )
                > 1
                else "UNRESOLVED"
            )
        )
    )

    if (
        not company
        or not position
    ):
        if args.no_prompt:
            return {
                "ready":
                    False,
                "company":
                    company or None,
                "position":
                    position or None,
                "company_mode":
                    company_mode,
                "position_mode":
                    position_mode,
                "company_options":
                    company_options,
                "position_options":
                    position_options,
                "evidence_sets":
                    evidence_sets,
            }

        if not company:
            company = (
                prompt_identity_value(
                    "Company",
                    company_options,
                )
            )

            company_mode = (
                "USER_CONFIRMED"
            )

        if not position:
            position = (
                prompt_identity_value(
                    "Position",
                    position_options,
                )
            )

            position_mode = (
                "USER_CONFIRMED"
            )

    return {
        "ready":
            True,
        "company":
            company,
        "position":
            position,
        "company_mode":
            company_mode,
        "position_mode":
            position_mode,
        "company_options":
            company_options,
        "position_options":
            position_options,
        "evidence_sets":
            evidence_sets,
    }



def command_single(args):
    temporary = None

    # Explicit identity remains authoritative when supplied.
    # Missing identity is resolved only after the current source/JD
    # has been obtained so no stale job identity can be reused.
    args.company = str(
        args.company
        or ""
    ).strip()

    args.position = str(
        args.position
        or ""
    ).strip()

    try:
        source = resolve_single_source(
            args
        )

        if source.get(
            "manual_required"
        ):
            print()
            print("=" * 88)
            print("MANUAL JD QUEUE")
            print("=" * 88)
            print(
                "COMPANY:",
                args.company
                or "(not yet resolved)",
            )
            print(
                "POSITION:",
                args.position
                or "(not yet resolved)",
            )
            print(
                "URL:",
                source.get(
                    "application_url"
                ),
            )
            print(
                "REASON:",
                source.get(
                    "reason"
                ),
            )
            print()
            print(
                "Rerun without --no-prompt and "
                "paste the raw JD."
            )

            from careerops_run_outcome import emit_input_outcome
            emit_input_outcome("NEEDS_MANUAL_JD", source.get("reason"), root=ROOT, metadata={"company":args.company,"position":args.position,"application_url":source.get("application_url")})
            return 3

        if source.get(
            "temporary"
        ):
            temporary = source.get(
                "jd_file"
            )

        identity = (
            resolve_single_identity(
                args,
                source,
            )
        )

        if not identity.get(
            "ready"
        ):
            print()
            print("=" * 88)
            print("JOB IDENTITY REQUIRED")
            print("=" * 88)
            print(
                "COMPANY:",
                identity.get(
                    "company"
                )
                or "(unresolved)",
            )
            print(
                "COMPANY MODE:",
                identity.get(
                    "company_mode"
                ),
            )
            print(
                "POSITION:",
                identity.get(
                    "position"
                )
                or "(unresolved)",
            )
            print(
                "POSITION MODE:",
                identity.get(
                    "position_mode"
                ),
            )

            if identity.get(
                "company_options"
            ):
                print(
                    "COMPANY CANDIDATES:",
                    ", ".join(
                        row[
                            "value"
                        ]
                        for row
                        in identity[
                            "company_options"
                        ]
                    ),
                )

            if identity.get(
                "position_options"
            ):
                print(
                    "POSITION CANDIDATES:",
                    ", ".join(
                        row[
                            "value"
                        ]
                        for row
                        in identity[
                            "position_options"
                        ]
                    ),
                )

            print(
                "No engine run was started. "
                "Supply only the unresolved/correct identity value."
            )
            print("=" * 88)

            from careerops_run_outcome import emit_input_outcome
            emit_input_outcome("NEEDS_JOB_IDENTITY", "Current job identity could not be established at high confidence.", root=ROOT, metadata=identity)
            return 4

        args.company = str(
            identity[
                "company"
            ]
        ).strip()

        args.position = str(
            identity[
                "position"
            ]
        ).strip()

        print()
        print("=" * 88)
        print("JOB IDENTITY")
        print("=" * 88)
        print(
            "COMPANY:",
            args.company,
            "|",
            identity.get(
                "company_mode"
            ),
        )
        print(
            "POSITION:",
            args.position,
            "|",
            identity.get(
                "position_mode"
            ),
        )
        print("=" * 88)

        run_id = (
            args.run_id
            or generated_run_id(
                args.company,
                args.position,
            )
        )

        print()
        print("=" * 88)
        print("CAREER-OPS SINGLE JOB")
        print("=" * 88)
        print(
            "COMPANY:",
            args.company,
        )
        print(
            "POSITION:",
            args.position,
        )
        print(
            "INPUT RESOLUTION:",
            source.get(
                "resolution"
            ),
        )
        print(
            "RUN ID:",
            run_id,
        )
        print(
            "STOP AFTER:",
            args.stop_after,
        )
        print("=" * 88)

        command = (
            build_orchestrator_command(
                company=args.company,
                position=args.position,
                jd_file=source[
                    "jd_file"
                ],
                application_url=source.get(
                    "application_url"
                ),
                url_first=source.get(
                    "url_first",
                    False,
                ),
                run_id=run_id,
                stop_after=args.stop_after,
            )
        )

        return execute_orchestrator(
            command,
            plan_only=args.plan_only,
            source_metadata_file=source.get('source_metadata_file'),
        )

    finally:
        if (
            temporary
            and Path(
                temporary
            ).exists()
        ):
            Path(
                temporary
            ).unlink(
                missing_ok=True
            )


def command_open(args):
    from careerops_run_outcome import artifact_delivery_command
    command = artifact_delivery_command(args.run_id, args.artifact_key, root=ROOT)
    return subprocess.run(command, cwd=ROOT, check=False, env=clean_env()).returncode


def command_resume(args):
    override = bool(
        args.user_override_generate
    )

    if (
        args.override_reason
        and not override
    ):
        raise ValueError(
            "--override-reason requires "
            "--user-override-generate."
        )

    reason = str(
        args.override_reason
        or ""
    ).strip()

    if (
        override
        and not reason
    ):
        raise ValueError(
            "User override generation requires "
            "--override-reason."
        )

    command = (
        build_orchestrator_command(
            resume_run=args.run_id,
            stop_after=(
                "writer"
                if override
                else args.stop_after
            ),
            user_override_generate=override,
            override_reason=reason,
        )
    )

    rc = execute_orchestrator(
        command,
        plan_only=args.plan_only,
    )

    if (
        rc != 0
        or not override
    ):
        return rc

    if args.plan_only:
        return 0

    from careerops_run_outcome import emit_run_outcome
    existing_outcome = emit_run_outcome(args.run_id, rc, root=ROOT)
    if existing_outcome.get("status")=="USER_OVERRIDE_GENERATED":
        print("USER OVERRIDE: reusing the exact isolated renderer output; no duplicate render.")
        return 0

    override_command = [
        str(PYTHON),
        str(
            USER_OVERRIDE_GENERATOR
        ),
        "--run-id",
        str(
            args.run_id
        ),
        "--reason",
        reason,
    ]

    return execute_orchestrator(
        override_command,
        plan_only=args.plan_only,
    )


def resolve_batch_file(
    path_value,
):
    path = Path(
        path_value
    ).expanduser()

    if not path.is_absolute():
        path = (
            ROOT
            / path
        )

    return path.resolve()



def validate_batch_job(
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

    if job.get(
        "resume_run"
    ):
        return

    company = str(
        job.get(
            "company",
            "",
        )
    ).strip()

    position = str(
        job.get(
            "position",
            "",
        )
    ).strip()

    jd_file = bool(
        job.get(
            "jd_file"
        )
    )

    jd_text = bool(
        str(
            job.get(
                "jd_text",
                "",
            )
        ).strip()
    )

    application_url = bool(
        str(
            job.get(
                "application_url",
                "",
            )
        ).strip()
    )

    if (
        int(jd_file)
        + int(jd_text)
        > 1
    ):
        raise ValueError(
            f"Job {index}: provide at most one "
            "of jd_file or jd_text."
        )

    if not (
        jd_file
        or jd_text
        or application_url
    ):
        raise ValueError(
            f"Job {index}: provide jd_file, jd_text, "
            "or application_url."
        )

    #
    # A truly URL-only row may omit company/title because those values
    # are resolved from Scope-4 current-requisition evidence after the
    # URL is probed. Existing JD-file/JD-text manifest behavior remains
    # unchanged and still requires explicit identity.
    url_only = bool(
        application_url
        and not jd_file
        and not jd_text
    )

    if not company and not url_only:
        raise ValueError(
            f"Job {index}: company is required."
        )

    if not position and not url_only:
        raise ValueError(
            f"Job {index}: position is required."
        )

    if jd_file:
        path = resolve_batch_file(
            job[
                "jd_file"
            ]
        )

        if not path.exists():
            raise ValueError(
                f"Job {index}: jd_file does not exist: "
                + str(path)
            )

    stop_after = job.get(
        "stop_after"
    )

    if (
        stop_after
        and stop_after
        not in STOP_CHOICES
    ):
        raise ValueError(
            f"Job {index}: invalid stop_after "
            f"{stop_after!r}."
        )


def load_batch_manifest(path):
    data = read_json(
        path
    )

    if isinstance(
        data,
        list,
    ):
        metadata = {}
        jobs = data

    elif isinstance(
        data,
        dict,
    ):
        jobs = data.get(
            "jobs"
        )

        metadata = {
            key:
                value
            for key, value
            in data.items()
            if key != "jobs"
        }

    else:
        raise ValueError(
            "Batch manifest must be a JSON array "
            "or an object containing jobs[]."
        )

    if (
        not isinstance(
            jobs,
            list,
        )
        or not jobs
    ):
        raise ValueError(
            "Batch manifest contains no jobs."
        )

    for index, job in enumerate(
        jobs,
        start=1,
    ):
        validate_batch_job(
            job,
            index,
        )

    return metadata, jobs



def batch_run_id(
    *,
    batch_id,
    index,
    company,
    position,
    provided=None,
):
    if str(
        provided
        or ""
    ).strip():
        return str(
            provided
        ).strip()

    return (
        batch_id
        + "_"
        + f"{index:03d}"
        + "_"
        + slug(
            company,
            24,
        )
        + "_"
        + slug(
            position,
            32,
        )
    )[:128]


def resolve_batch_identity_values(
    *,
    company,
    position,
    identity_evidence,
    origin,
):
    company = str(
        company
        or ""
    ).strip()

    position = str(
        position
        or ""
    ).strip()

    evidence_sets = []

    if identity_evidence:
        evidence_sets.append(
            {
                "origin":
                    origin,
                "evidence":
                    identity_evidence,
            }
        )

    company_options = (
        high_identity_options(
            evidence_sets,
            "company",
        )
    )

    position_options = (
        high_identity_options(
            evidence_sets,
            "position",
        )
    )

    explicit_company = bool(
        company
    )

    explicit_position = bool(
        position
    )

    if (
        not company
        and len(
            company_options
        ) == 1
    ):
        company = (
            company_options[
                0
            ][
                "value"
            ]
        )

    if (
        not position
        and len(
            position_options
        ) == 1
    ):
        position = (
            position_options[
                0
            ][
                "value"
            ]
        )

    company_mode = (
        "USER_SUPPLIED"
        if explicit_company
        else (
            "AUTO_HIGH"
            if company
            else (
                "AMBIGUOUS"
                if len(
                    company_options
                ) > 1
                else "UNRESOLVED"
            )
        )
    )

    position_mode = (
        "USER_SUPPLIED"
        if explicit_position
        else (
            "AUTO_HIGH"
            if position
            else (
                "AMBIGUOUS"
                if len(
                    position_options
                ) > 1
                else "UNRESOLVED"
            )
        )
    )

    return {
        "ready":
            bool(
                company
                and position
            ),
        "company":
            company,
        "position":
            position,
        "company_mode":
            company_mode,
        "position_mode":
            position_mode,
        "company_options":
            company_options,
        "position_options":
            position_options,
    }

def _url_identity_tokens(value):
    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        str(value or "").casefold(),
    )

    stop = {
        "a", "an", "and", "at",
        "career", "careers",
        "company", "corp", "corporation",
        "inc", "job", "jobs",
        "llc", "ltd", "of", "the",
        "us", "usa",
        "i", "ii", "iii", "iv", "v",
    }

    return {
        token
        for token in value.split()
        if (
            len(token) >= 2
            and token not in stop
        )
    }


def _url_identity_hints(application_url):
    from urllib.parse import (
        unquote,
        urlparse,
    )

    try:
        parsed = urlparse(
            str(application_url or "").strip()
        )
    except Exception:
        return {
            "applicable": False,
            "source": None,
            "company_hint": None,
            "position_hint": None,
        }

    host = (
        parsed.hostname.casefold()
        if parsed.hostname
        else ""
    )

    parts = [
        unquote(part)
        for part in parsed.path.split("/")
        if part
    ]

    if "myworkdayjobs.com" in host:
        lowered = [
            part.casefold()
            for part in parts
        ]

        if (
            "job" in lowered
            and parts
        ):
            slug = parts[-1]

            slug = re.sub(
                r"_[A-Za-z0-9-]*\d[A-Za-z0-9-]*$",
                "",
                slug,
            )

            title = re.sub(
                r"[-_]+",
                " ",
                slug,
            ).strip()

            if title:
                return {
                    "applicable":
                        True,
                    "source":
                        "WORKDAY_READABLE_JOB_SLUG",
                    "company_hint":
                        None,
                    "position_hint":
                        title,
                }

    if (
        host == "himalayas.app"
        or host.endswith(".himalayas.app")
    ):
        lowered = [
            part.casefold()
            for part in parts
        ]

        try:
            company_i = lowered.index(
                "companies"
            )
            job_i = lowered.index(
                "jobs"
            )
        except ValueError:
            company_i = None
            job_i = None

        if (
            company_i is not None
            and job_i is not None
            and company_i + 1 < len(parts)
            and job_i + 1 < len(parts)
        ):
            company_hint = re.sub(
                r"[-_]+",
                " ",
                parts[company_i + 1],
            ).strip()

            job_slug = re.sub(
                r"-\d{5,}$",
                "",
                parts[job_i + 1],
            )

            position_hint = re.sub(
                r"[-_]+",
                " ",
                job_slug,
            ).strip()

            return {
                "applicable":
                    True,
                "source":
                    "HIMALAYAS_READABLE_COMPANY_AND_JOB_SLUG",
                "company_hint":
                    company_hint or None,
                "position_hint":
                    position_hint or None,
            }

    return {
        "applicable": False,
        "source": None,
        "company_hint": None,
        "position_hint": None,
    }


def _url_identity_coherence(
    application_url,
    company,
    position,
):
    hints = _url_identity_hints(
        application_url
    )

    if not hints["applicable"]:
        return {
            "status":
                "NOT_APPLICABLE",
            **hints,
            "checks":
                [],
            "failure_reasons":
                [],
        }

    checks = []

    for field, hint, resolved in (
        (
            "company",
            hints.get("company_hint"),
            company,
        ),
        (
            "position",
            hints.get("position_hint"),
            position,
        ),
    ):
        if not hint:
            continue

        hint_tokens = _url_identity_tokens(
            hint
        )

        resolved_tokens = _url_identity_tokens(
            resolved
        )

        overlap = (
            hint_tokens
            & resolved_tokens
        )

        coverage = (
            len(overlap)
            / len(hint_tokens)
            if hint_tokens
            else 0.0
        )

        passed = bool(
            hint_tokens
            and resolved_tokens
            and overlap
            and coverage >= 0.55
        )

        checks.append({
            "field":
                field,
            "url_hint":
                hint,
            "resolved_value":
                resolved,
            "hint_coverage":
                round(coverage, 4),
            "overlap":
                sorted(overlap),
            "passed":
                passed,
        })

    failures = [
        row
        for row in checks
        if not row["passed"]
    ]

    return {
        "status":
            (
                "FAIL_CLOSED"
                if failures
                else "PASS"
            ),
        **hints,
        "checks":
            checks,
        "failure_reasons": [
            (
                row["field"]
                + " conflicts with readable URL requisition identity"
            )
            for row in failures
        ],
    }

def resolve_batch_job(
    *,
    job,
    index,
    batch_id,
    batch_dir,
    default_stop,
):
    if job.get(
        "resume_run"
    ):
        return {
            "index":
                index,
            "company":
                job.get(
                    "company"
                ),
            "position":
                job.get(
                    "position"
                ),
            "run_id":
                str(
                    job[
                        "resume_run"
                    ]
                ),
            "resume_run":
                str(
                    job[
                        "resume_run"
                    ]
                ),
            "stop_after":
                (
                    job.get(
                        "stop_after"
                    )
                    or default_stop
                ),
            "resolution":
                "RESUME_RUN",
            "ready":
                True,
        }

    company = str(
        job.get(
            "company",
            "",
        )
    ).strip()

    position = str(
        job.get(
            "position",
            "",
        )
    ).strip()

    application_url = str(
        job.get(
            "application_url",
            "",
        )
    ).strip() or None

    provided_run_id = str(
        job.get(
            "run_id",
            "",
        )
    ).strip() or None

    resolved_dir = (
        batch_dir
        / "resolved_inputs"
    )

    resolved_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    base = {
        "index":
            index,
        "company":
            company,
        "position":
            position,
        "application_url":
            application_url,
        "run_id":
            provided_run_id,
        "stop_after":
            (
                job.get(
                    "stop_after"
                )
                or default_stop
            ),
        "ready":
            True,
    }

    # Existing JD-file behavior remains explicit-identity based.
    if job.get(
        "jd_file"
    ):
        run_id = batch_run_id(
            batch_id=batch_id,
            index=index,
            company=company,
            position=position,
            provided=provided_run_id,
        )

        base.update({
            "run_id":
                run_id,
            "jd_file":
                str(
                    resolve_batch_file(
                        job[
                            "jd_file"
                        ]
                    )
                ),
            "url_first":
                bool(
                    application_url
                    and job.get(
                        "url_first",
                        True,
                    )
                ),
            "resolution":
                "JD_FILE",
        })

        return base

    # Existing JD-text behavior remains explicit-identity based.
    if str(
        job.get(
            "jd_text",
            "",
        )
    ).strip():
        text = validate_text(
            job[
                "jd_text"
            ]
        )

        target = (
            resolved_dir
            / (
                f"job_{index:03d}"
                "_manifest_jd.txt"
            )
        )

        save_text(
            target,
            text,
        )

        run_id = batch_run_id(
            batch_id=batch_id,
            index=index,
            company=company,
            position=position,
            provided=provided_run_id,
        )

        base.update({
            "run_id":
                run_id,
            "jd_file":
                str(
                    target
                ),
            "url_first":
                bool(
                    application_url
                    and job.get(
                        "url_first",
                        True,
                    )
                ),
            "resolution":
                "JD_TEXT",
        })

        return base

    # URL-only path.
    intake = probe_url(
        application_url
    )

    status = intake.get(
        "status"
    )

    if status == "INGESTED":
        text = validate_text(
            intake.get(
                "raw_jd_text"
            )
        )

        target = (
            resolved_dir
            / (
                f"job_{index:03d}"
                "_url_jd.txt"
            )
        )

        save_text(
            target,
            text,
        )

        identity = (
            resolve_batch_identity_values(
                company=company,
                position=position,
                identity_evidence=intake.get(
                    "identity_evidence"
                ),
                origin="URL_BATCH_PROBE",
            )
        )

        base.update({
            "company":
                identity[
                    "company"
                ],
            "position":
                identity[
                    "position"
                ],
            "company_mode":
                identity[
                    "company_mode"
                ],
            "position_mode":
                identity[
                    "position_mode"
                ],
            "company_options":
                identity[
                    "company_options"
                ],
            "position_options":
                identity[
                    "position_options"
                ],
            "jd_file":
                str(
                    target
                ),
            "url_first":
                True,
            "url_probe_status":
                status,
        })

        if not identity[
            "ready"
        ]:
            base.update({
                "ready":
                    False,
                "resolution":
                    "NEEDS_JOB_IDENTITY",
                "reason":
                    (
                        "URL supplied a usable JD, but company/title "
                        "could not both be resolved at high confidence."
                    ),
            })

            return base

        coherence = _url_identity_coherence(
            application_url,
            identity["company"],
            identity["position"],
        )

        base[
            "url_identity_coherence"
        ] = coherence

        if coherence[
            "status"
        ] == "FAIL_CLOSED":
            base.update({
                "company":
                    identity["company"],
                "position":
                    identity["position"],
                "company_mode":
                    identity["company_mode"],
                "position_mode":
                    identity["position_mode"],
                "company_options":
                    identity["company_options"],
                "position_options":
                    identity["position_options"],
                "ready":
                    False,
                "resolution":
                    "NEEDS_MANUAL_JD",
                "reason":
                    (
                        "Readable application URL conflicts with "
                        "resolved current-requisition identity. "
                        "Fail closed before production run creation."
                    ),
            })
            return base

        base[
            "run_id"
        ] = batch_run_id(
            batch_id=batch_id,
            index=index,
            company=identity[
                "company"
            ],
            position=identity[
                "position"
            ],
            provided=provided_run_id,
        )

        base[
            "resolution"
        ] = "URL_INGESTED"

        return base

    # Blocked/unreadable URL. Keep it isolated in the manual-JD queue.
    base.update({
        "ready":
            False,
        "resolution":
            "NEEDS_MANUAL_JD",
        "url_probe_status":
            status,
        "reason":
            (
                intake.get(
                    "instruction"
                )
                or intake.get(
                    "fetch_error"
                )
                or (
                    "URL did not provide "
                    "a usable JD."
                )
            ),
    })

    return base


def print_manual_queue(
    queued,
):
    print()
    print("=" * 100)
    print(
        f"MANUAL JD QUEUE: {len(queued)} JOB"
        + (
            ""
            if len(queued) == 1
            else "S"
        )
    )
    print("=" * 100)

    for queue_index, row in enumerate(
        queued,
        start=1,
    ):
        print()
        print(
            f"[{queue_index}/{len(queued)}]"
        )
        print(
            "BATCH JOB:",
            row[
                "index"
            ],
        )
        print(
            "COMPANY:",
            row[
                "company"
            ],
        )
        print(
            "POSITION:",
            row[
                "position"
            ],
        )
        print(
            "URL:",
            row.get(
                "application_url"
            ),
        )
        print(
            "REASON:",
            row.get(
                "reason"
            ),
        )

    print()
    print("=" * 100)



def resolve_manual_queue(
    rows,
    *,
    batch_dir,
):
    queue = [
        row
        for row in rows
        if not row.get(
            "ready"
        )
    ]

    if not queue:
        return rows

    print_manual_queue(
        queue
    )

    resolved_dir = (
        batch_dir
        / "resolved_inputs"
    )

    for queue_index, row in enumerate(
        queue,
        start=1,
    ):
        print()
        print("#" * 100)
        print(
            f"MANUAL RESOLUTION {queue_index}/{len(queue)}"
        )
        print("#" * 100)

        resolution = row.get(
            "resolution"
        )

        target = None

        if resolution == "NEEDS_MANUAL_JD":
            text = read_raw_paste(
                row.get(
                    "company"
                )
                or "(not yet resolved)",
                row.get(
                    "position"
                )
                or "(not yet resolved)",
            )

            target = (
                resolved_dir
                / (
                    f"job_{row['index']:03d}"
                    "_manual_jd.txt"
                )
            )

            save_text(
                target,
                text,
            )

            row[
                "jd_file"
            ] = str(
                target
            )

        elif resolution == "NEEDS_JOB_IDENTITY":
            target_value = row.get(
                "jd_file"
            )

            if target_value:
                target = Path(
                    target_value
                )

        identity_evidence = (
            probe_identity_from_jd_file(
                target
            )
            if target
            else None
        )

        identity = (
            resolve_batch_identity_values(
                company=row.get(
                    "company"
                ),
                position=row.get(
                    "position"
                ),
                identity_evidence=identity_evidence,
                origin="BATCH_MANUAL_RESOLUTION",
            )
        )

        company = identity[
            "company"
        ]

        position = identity[
            "position"
        ]

        if not company:
            company = prompt_identity_value(
                "Company",
                identity[
                    "company_options"
                ],
            )

            identity[
                "company_mode"
            ] = "USER_CONFIRMED"

        if not position:
            position = prompt_identity_value(
                "Position",
                identity[
                    "position_options"
                ],
            )

            identity[
                "position_mode"
            ] = "USER_CONFIRMED"

        row[
            "company"
        ] = company

        row[
            "position"
        ] = position

        row[
            "company_mode"
        ] = identity[
            "company_mode"
        ]

        row[
            "position_mode"
        ] = identity[
            "position_mode"
        ]

        row[
            "run_id"
        ] = batch_run_id(
            batch_id=batch_dir.name,
            index=row[
                "index"
            ],
            company=company,
            position=position,
            provided=row.get(
                "run_id"
            ),
        )

        row[
            "url_first"
        ] = True

        row[
            "resolution"
        ] = (
            "MANUAL_JD_FALLBACK"
            if resolution
            == "NEEDS_MANUAL_JD"
            else "URL_INGESTED_IDENTITY_CONFIRMED"
        )

        row[
            "ready"
        ] = True

    return rows


def summarize_run(
    run_id,
    rc,
):
    manifest_path = (
        RUNS
        / run_id
        / "manifest.json"
    )

    release_path = (
        RUNS
        / run_id
        / "runtime"
        / "pair_release_gate_report.json"
    )

    manifest = (
        read_json(
            manifest_path
        )
        or {}
    )

    release = (
        read_json(
            release_path
        )
        or {}
    )

    execution = manifest.get(
        "execution",
        {},
    )

    summary = {
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

        "writer_calls":
            execution.get(
                "writer_calls",
                0,
            ),

        "truth_audit_calls":
            execution.get(
                "truth_audit_calls",
                0,
            ),

        "model_calls":
            execution.get(
                "model_calls",
                0,
            ),

        "release_ready":
            release.get(
                "release_ready"
            ),

        "manifest":
            (
                str(
                    manifest_path
                )
                if manifest_path.exists()
                else None
            ),

        "release_report":
            (
                str(
                    release_path
                )
                if release_path.exists()
                else None
            ),
    }
    from careerops_run_outcome import emit_run_outcome
    summary.update(emit_run_outcome(run_id, rc, root=ROOT))
    return summary



URL_LIST_TERMINATOR = "::ENDURLS::"


def validate_job_url(value):
    from careerops_url_normalization import normalize_job_url
    return normalize_job_url(value)


def read_url_list_paste():
    print()
    print("=" * 88)
    print("JOB URL LIST")
    print("=" * 88)
    print(
        "Paste one job URL per line."
    )
    print(
        f"When finished, type {URL_LIST_TERMINATOR}"
    )
    print(
        "on its own line and press Enter."
    )
    print("=" * 88)
    print()

    values = []

    for raw in sys.stdin:
        line = raw.strip()

        if line == URL_LIST_TERMINATOR:
            break

        if line:
            values.append(
                line
            )

    return values


def command_url_batch(args):

    values = []

    for value in (
        args.urls
        or []
    ):
        if str(
            value
            or ""
        ).strip():
            values.append(
                str(
                    value
                ).strip()
            )

    if args.file:
        source = Path(
            args.file
        ).expanduser()

        if not source.is_absolute():
            source = (
                ROOT
                / source
            )

        source = source.resolve()

        if not source.exists():
            raise ValueError(
                "URL list file does not exist: "
                + str(
                    source
                )
            )

        for line in source.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines():
            line = line.strip()

            if line:
                values.append(
                    line
                )

    if (
        args.paste
        or not values
    ):
        values.extend(
            read_url_list_paste()
        )

    normalized = []
    seen = set()

    for value in values:
        url = validate_job_url(
            value
        )

        if url in seen:
            continue

        seen.add(
            url
        )

        normalized.append(
            url
        )

    if not normalized:
        raise ValueError(
            "No job URLs were supplied."
        )

    batch_id = (
        args.batch_id
        or (
            "url_batch_"
            + stamp()
        )
    )

    manifest_dir = (
        ROOT
        / "data"
        / "careerops-engine"
        / "url_batch_manifests"
    )

    manifest_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    manifest_path = (
        manifest_dir
        / (
            batch_id
            + ".json"
        )
    )

    atomic_json(
        manifest_path,
        {
            "schema_version":
                "careerops-direct-url-batch-v1",
            "batch_id":
                batch_id,
            "created_at":
                now_utc(),
            "source":
                "career-ops urls",
            "job_count":
                len(
                    normalized
                ),
            "jobs":
                [
                    {
                        "application_url":
                            url,
                    }
                    for url in normalized
                ],
        },
    )

    print()
    print("=" * 100)
    print("DIRECT URL BATCH")
    print("=" * 100)
    print(
        "URLS:",
        len(
            normalized
        ),
    )
    print(
        "MANIFEST:",
        manifest_path,
    )
    print(
        "BATCH ID:",
        batch_id,
    )
    print("=" * 100)

    delegated = argparse.Namespace(
        manifest=str(
            manifest_path
        ),
        batch_id=batch_id,
        stop_after=args.stop_after,
        no_prompt=args.no_prompt,
        # Direct URL batches are independent by design:
        # one failed run must not prevent later URLs from executing.
        continue_on_error=True,
        plan_only=args.plan_only,
    )

    return command_batch(
        delegated
    )




def _careerops_review_batch_overrides(
    report,
    *,
    interactive,
):
    """
    Review only already-failed isolated runs after the batch processing pass.

    This does NOT change any automatic CareerOps decision.
    It delegates entirely to the existing user-override authority:
      - REJECTED / NEEDS_ATTENTION only
      - first and only writer when eligible
      - otherwise reuse the exact passed writer pair
      - no second writer
      - USER_OVERRIDE_GENERATED only
      - never counterfeit RELEASE_READY
    """
    jobs = (
        report.get(
            "jobs",
            [],
        )
        or []
    )

    candidates = []

    for row in jobs:
        process_rc = row.get(
            "process_rc"
        )

        run_id = str(
            row.get(
                "run_id"
            )
            or ""
        ).strip()

        if not run_id:
            continue

        command = (
            build_orchestrator_command(
                resume_run=run_id,
                stop_after="render",
            )
        )

        availability = (
            _careerops_override_availability(
                command
            )
        )

        if availability.get(
            "lifecycle"
        ) not in {
            "REJECTED",
            "NEEDS_ATTENTION",
            "RELEASE_BLOCKED",
        }:
            continue

        candidates.append({
            "row":
                row,

            "command":
                command,

            "availability":
                availability,
        })

    report['non_release_review_count'] = len(candidates)
    report['eligible_override_count'] = sum(bool(x['availability'].get('eligible')) for x in candidates)
    if not candidates:
        return []

    print()
    print("=" * 100)
    print(
        "BATCH USER-OVERRIDE REVIEW:",
        len(candidates),
        "FAILED RUN"
        + (
            ""
            if len(candidates) == 1
            else "S"
        ),
    )
    print("=" * 100)

    results = []

    for index, item in enumerate(
        candidates,
        start=1,
    ):
        row = item[
            "row"
        ]

        availability = item[
            "availability"
        ]

        print()
        print(
            f"[{index}/{len(candidates)}]"
        )
        print(
            "RUN ID:",
            row.get(
                "run_id"
            ),
        )
        print(
            "COMPANY:",
            row.get(
                "company"
            ),
        )
        print(
            "POSITION:",
            row.get(
                "position"
            ),
        )
        print(
            "LIFECYCLE:",
            availability.get(
                "lifecycle"
            ),
        )
        print(
            "OVERRIDE ELIGIBLE:",
            bool(
                availability.get(
                    "eligible"
                )
            ),
        )
        print(
            "OVERRIDE MODE:",
            availability.get(
                "mode"
            ),
        )

        override_rc = (
            _careerops_offer_user_override(
                item[
                    "command"
                ],
                row.get(
                    "process_rc"
                ),
                interactive=interactive,
            )
        )

        results.append({
            "run_id":
                row.get(
                    "run_id"
                ),

            "automatic_process_rc":
                row.get(
                    "process_rc"
                ),

            "automatic_lifecycle":
                availability.get(
                    "lifecycle"
                ),

            "override_eligible":
                bool(
                    availability.get(
                        "eligible"
                    )
                ),

            "override_mode":
                availability.get(
                    "mode"
                ),

            "override_execution_rc":
                override_rc,

            "automatic_decision_preserved":
                True,

            "release_ready_forged":
                False,
        })

    print()
    print("=" * 100)
    print(
        "BATCH OVERRIDE REVIEW COMPLETE"
    )
    print(
        "Automatic batch failures remain preserved."
    )
    print("=" * 100)

    return results



def command_batch(args):
    from careerops_run_outcome import input_outcome
    manifest_file = Path(args.manifest).expanduser()
    if not manifest_file.is_absolute():
        manifest_file = ROOT / manifest_file
    manifest_file = manifest_file.resolve()
    if not manifest_file.exists():
        raise ValueError('Batch manifest does not exist: ' + str(manifest_file))
    metadata, jobs = load_batch_manifest(manifest_file)
    batch_id = args.batch_id or metadata.get('batch_id') or 'batch_' + stamp()
    if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9._-]{0,127}', batch_id):
        raise ValueError('Invalid batch_id.')
    batch_dir = BATCHES / batch_id
    if batch_dir.exists():
        raise ValueError('Batch directory already exists: ' + str(batch_dir))
    batch_dir.mkdir(parents=True)
    print()
    print('=' * 100)
    print('CAREER-OPS BATCH INTAKE')
    print('=' * 100)
    print('BATCH ID:', batch_id)
    print('JOBS:', len(jobs))
    print()
    resolved = []
    for index, job in enumerate(jobs, start=1):
        row = resolve_batch_job(job=job, index=index, batch_id=batch_id, batch_dir=batch_dir, default_stop=args.stop_after)
        resolved.append(row)
        print(f'{index:02d}', '|', row.get('company') or 'RESUME', '|', row.get('position') or row.get('run_id'), '|', row.get('resolution'))
    queued = [row for row in resolved if not row.get('ready')]
    queue_path = batch_dir / 'manual_jd_queue.json'
    atomic_json(queue_path, {'schema_version': 'careerops-manual-jd-queue-v1', 'batch_id': batch_id, 'created_at': now_utc(), 'pending_count': len(queued), 'jobs': queued})
    if queued:
        print_manual_queue(queued)
        print('QUEUE FILE:', queue_path)
        if not args.no_prompt:
            resolved = resolve_manual_queue(resolved, batch_dir=batch_dir)
            atomic_json(queue_path, {'schema_version': 'careerops-manual-jd-queue-v1', 'batch_id': batch_id, 'updated_at': now_utc(), 'pending_count': 0, 'jobs': []})
    report_path = batch_dir / 'batch_report.json'
    report = {'schema_version': 'careerops-career-ops-batch-v1', 'batch_id': batch_id, 'created_at': now_utc(), 'source_manifest': str(manifest_file), 'job_count': len(jobs), 'manual_jd_queue': str(queue_path), 'jobs': [], 'total_writer_calls': 0, 'total_truth_audit_calls': 0, 'total_model_calls': 0, 'completed': False, 'success': False}
    atomic_json(report_path, report)
    unresolved = [row for row in resolved if not row.get('ready')]
    if unresolved:
        print()
        print('Unresolved manual-JD jobs will NOT be sent to the writer.')
    any_failure = False
    semantic_pending = []
    for row in resolved:
        if not row.get('ready'):
            report['jobs'].append({**row, 'status': row.get('resolution') or 'NEEDS_MANUAL_JD', 'process_rc': None, 'model_calls': 0, **input_outcome(row.get('resolution'), row.get('reason'), identity_conflict=row.get('url_identity_coherence', {}).get('status') == 'FAIL_CLOSED')})
            continue
        print()
        print('=' * 100)
        print(f"BATCH JOB {row['index']}/{len(resolved)}")
        print('=' * 100)
        print('COMPANY:', row.get('company'))
        print('POSITION:', row.get('position'))
        print('RUN ID:', row.get('run_id'))
        print('INPUT:', row.get('resolution'))
        print('=' * 100)
        if row.get('resume_run'):
            command = build_orchestrator_command(resume_run=row['resume_run'], stop_after=row['stop_after'])
        else:
            command = build_orchestrator_command(company=row['company'], position=row['position'], jd_file=row['jd_file'], application_url=row.get('application_url'), url_first=row.get('url_first', False), run_id=row['run_id'], stop_after=row['stop_after'])
        print_command(command)
        if args.plan_only:
            rc = 0
            summary = {'process_rc': 0, 'success': True, 'status': 'PLAN_ONLY', 'writer_calls': 0, 'truth_audit_calls': 0, 'model_calls': 0, 'release_ready': None}
        else:
            result = subprocess.run([str(x) for x in command], cwd=ROOT, check=False, env=clean_env({'CAREEROPS_SHARED_SEMANTIC_DEFER': '1'}))
            rc = result.returncode
            summary = summarize_run(row['run_id'], rc)
        summary.update({'index': row['index'], 'company': row.get('company'), 'position': row.get('position'), 'run_id': row.get('run_id'), 'input_resolution': row.get('resolution'), 'application_url': row.get('application_url'), 'stop_after': row.get('stop_after')})
        report['jobs'].append(summary)
        if rc != 0 or not summary.get('success'):
            from careerops_automatic_semantic_escalation import queued_case
            from careerops_production_configuration import apply
            if not args.plan_only and apply(os.environ).get('CAREEROPS_SHARED_SOL_SEMANTIC') == '1' and queued_case(row['run_id']):
                semantic_pending.append(row)
                continue
            any_failure = True
            if not args.continue_on_error:
                break
    if semantic_pending and (not args.plan_only):
        from careerops_automatic_semantic_escalation import automatic_batch
        semantic_result = automatic_batch([row['run_id'] for row in semantic_pending])
        report['shared_semantic_escalation'] = semantic_result
        for pending in semantic_pending:
            if pending['run_id'] not in semantic_result.get('continued_runs', []):
                continue
            command = build_orchestrator_command(resume_run=pending['run_id'], stop_after=pending['stop_after'])
            result = subprocess.run([str(x) for x in command], cwd=ROOT, check=False)
            updated = summarize_run(pending['run_id'], result.returncode)
            for row in report['jobs']:
                if row['run_id'] == pending['run_id']:
                    row.update(updated)
        any_failure = any((not row.get('success') for row in report['jobs']))
    report['total_writer_calls'] = sum((int(row.get('writer_calls', 0) or 0) for row in report['jobs']))
    report['total_truth_audit_calls'] = sum((int(row.get('truth_audit_calls', 0) or 0) for row in report['jobs']))
    report['total_model_calls'] = sum((int(row.get('model_calls', 0) or 0) for row in report['jobs']))
    report['completed'] = len(report['jobs']) == len(jobs)
    report['success'] = report['completed'] and (not any_failure) and (not unresolved) and all((row.get('status') != 'NEEDS_MANUAL_JD' for row in report['jobs']))
    if not args.plan_only:
        from careerops_automatic_semantic_escalation import aggregate_accounting
        report['model_accounting'] = aggregate_accounting([row['run_id'] for row in report['jobs'] if row.get('run_id')])
        report['total_model_calls'] = report['model_accounting']['total_observed_model_attempts']
    report['finished_at'] = now_utc()
    atomic_json(report_path, report)
    print()
    print('=' * 100)
    print('CAREER-OPS BATCH COMPLETE')
    print('=' * 100)
    print('BATCH ID:', batch_id)
    print('JOBS REQUESTED:', len(jobs))
    print('JOBS RECORDED:', len(report['jobs']))
    print('WRITER CALLS:', report['total_writer_calls'])
    print('TRUTH AUDIT CALLS:', report['total_truth_audit_calls'])
    print('TOTAL MODEL CALLS:', report['total_model_calls'])
    print('MANUAL JD PENDING:', len(unresolved))
    print('SUCCESS:', report['success'])
    print('REPORT:', report_path)
    print('QUEUE:', queue_path)
    if args.plan_only:
        return 0
    if unresolved:
        from careerops_run_outcome import print_batch_artifact_delivery
        print_batch_artifact_delivery(report, root=ROOT)
        return 3
    if not args.plan_only:
        report['override_review'] = _careerops_review_batch_overrides(report, interactive=not args.no_prompt and sys.stdin.isatty() and sys.stdout.isatty())
        atomic_json(report_path, report)
    from careerops_run_outcome import print_batch_artifact_delivery
    print_batch_artifact_delivery(report, root=ROOT)
    return 0 if report['success'] else 1


def command_self_test():
    checks = {
        "python_exists":
            PYTHON.exists(),

        "orchestrator_exists":
            ORCHESTRATOR.exists(),

        "ingest_exists":
            INGEST.exists(),

        "powershell_optional":
            True,

        "url_only_job_valid":
            True,

        "raw_text_validator":
            False,

        "run_id_generator":
            False,
    }

    try:
        validate_batch_job(
            {
                "company":
                    "Example Company",

                "position":
                    "Data Analyst",

                "application_url":
                    "https://example.invalid/job/1",
            },
            1,
        )

    except Exception:
        checks[
            "url_only_job_valid"
        ] = False

    try:
        validate_text(
            "Responsibilities and qualifications "
            * 12
        )

        checks[
            "raw_text_validator"
        ] = True

    except Exception:
        pass

    generated = (
        generated_run_id(
            "Example Company",
            "Data Analyst",
        )
    )

    checks[
        "run_id_generator"
    ] = bool(
        re.fullmatch(
            r"[A-Za-z0-9._-]+",
            generated,
        )
    )

    print("=" * 88)
    print("CAREER-OPS EVERYDAY UX SELF-TEST")
    print("=" * 88)

    for name, ok in checks.items():
        print(
            name,
            "=",
            (
                "PASS"
                if ok
                else "FAIL"
            ),
        )

    print()
    print(
        "POWERSHELL CLIPBOARD:",
        (
            "AVAILABLE"
            if shutil.which(
                "powershell.exe"
            )
            else "NOT AVAILABLE"
        ),
    )

    print(
        "PASTE TERMINATOR:",
        PASTE_TERMINATOR,
    )

    print(
        "MODEL CALLS: 0"
    )

    return (
        0
        if all(
            checks.values()
        )
        else 1
    )


def add_common_job_args(
    parser,
):
    parser.add_argument(
        "--company",
        required=False,
        help=(
            "Optional company override. When omitted, "
            "Career-Ops auto-resolves only from high-confidence "
            "current-requisition evidence."
        ),
    )

    parser.add_argument(
        "--position",
        required=False,
        help=(
            "Optional position override. When omitted, "
            "Career-Ops auto-resolves only from high-confidence "
            "current-requisition evidence."
        ),
    )

    parser.add_argument(
        "--application-url",
    )

    parser.add_argument(
        "--run-id",
    )

    parser.add_argument(
        "--stop-after",
        choices=sorted(
            STOP_CHOICES
        ),
        default="release",
    )

    parser.add_argument(
        "--plan-only",
        action="store_true",
        help=(
            "Resolve input and show the production "
            "command without executing the engine."
        ),
    )


def build_parser():
    parser = argparse.ArgumentParser(
        prog="career-ops",
        description=(
            "Everyday interface for CareerOps's "
            "Career-Ops production resume + cover engine."
        ),
    )

    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )

    single = sub.add_parser(
        "single",
        help=(
            "Run one job from URL, raw paste, "
            "clipboard, or JD file."
        ),
    )

    add_common_job_args(
        single
    )

    sources = (
        single.add_mutually_exclusive_group()
    )

    sources.add_argument(
        "--url",
        help=(
            "Application/job URL. Career-Ops tries "
            "the URL first and asks for the raw JD "
            "only if needed."
        ),
    )

    sources.add_argument(
        "--jd-file",
    )

    sources.add_argument(
        "--paste",
        action="store_true",
        help=(
            "Paste raw JD text directly. No formatting required."
        ),
    )

    sources.add_argument(
        "--clipboard",
        action="store_true",
        help=(
            "Use the current Windows clipboard as raw JD text."
        ),
    )

    single.add_argument(
        "--no-prompt",
        action="store_true",
        help=(
            "For a failed URL, report NEEDS_MANUAL_JD "
            "instead of prompting."
        ),
    )

    single.add_argument(
        "--skip-url-probe",
        action="store_true",
        help=(
            "When supplying JD text/file plus application URL, "
            "do not retry the URL inside the production engine."
        ),
    )

    single.set_defaults(
        func=command_single
    )

    batch = sub.add_parser(
        "batch",
        help=(
            "Run a mixed batch. URL-only jobs are allowed."
        ),
    )

    batch.add_argument(
        "manifest",
        help=(
            "JSON manifest containing jobs[]."
        ),
    )

    batch.add_argument(
        "--batch-id",
    )

    batch.add_argument(
        "--stop-after",
        choices=sorted(
            STOP_CHOICES
        ),
        default="release",
    )

    batch.add_argument(
        "--no-prompt",
        action="store_true",
        help=(
            "Write the manual-JD queue but do not "
            "prompt for missing JDs."
        ),
    )

    batch.add_argument(
        "--continue-on-error",
        action="store_true",
    )

    batch.add_argument(
        "--plan-only",
        action="store_true",
        help=(
            "Resolve inputs and print commands without "
            "executing the production engine."
        ),
    )

    batch.set_defaults(
        func=command_batch
    )


    urls = sub.add_parser(
        "urls",
        help=(
            "Run a batch directly from job URLs. "
            "Company/title are auto-resolved when safe."
        ),
    )

    urls.add_argument(
        "urls",
        nargs="*",
        help=(
            "Job URLs. You may also use --file or --paste."
        ),
    )

    urls.add_argument(
        "--file",
        help=(
            "Text file containing one job URL per line."
        ),
    )

    urls.add_argument(
        "--paste",
        action="store_true",
        help=(
            "Paste one job URL per line interactively."
        ),
    )

    urls.add_argument(
        "--batch-id",
    )

    urls.add_argument(
        "--stop-after",
        choices=sorted(
            STOP_CHOICES
        ),
        default="release",
    )

    urls.add_argument(
        "--no-prompt",
        action="store_true",
        help=(
            "Queue blocked URLs or unresolved identity "
            "without prompting."
        ),
    )

    urls.add_argument(
        "--continue-on-error",
        action="store_true",
    )

    urls.add_argument(
        "--plan-only",
        action="store_true",
        help=(
            "Resolve URLs and print production commands "
            "without executing the production engine."
        ),
    )

    urls.set_defaults(
        func=command_url_batch
    )

    open_artifact = sub.add_parser("open", help="Open an existing artifact through authenticated delivery; no generation.")
    open_artifact.add_argument("run_id", help="Original parent run ID.")
    open_artifact.add_argument("artifact_key", choices=("resume_pdf", "resume_docx", "cover_pdf", "cover_docx", "folder"))
    open_artifact.set_defaults(func=command_open)

    resume = sub.add_parser(
        "resume",
        help=(
            "Resume an existing production run."
        ),
    )

    resume.add_argument(
        "run_id",
    )

    resume.add_argument(
        "--stop-after",
        choices=sorted(
            STOP_CHOICES
        ),
        default="release",
    )

    resume.add_argument(
        "--user-override-generate",
        action="store_true",
        help=(
            "Explicitly obtain isolated unreleased resume/cover "
            "files from an existing failed/rejected run."
        ),
    )

    resume.add_argument(
        "--override-reason",
        help=(
            "Required reason for explicit user override generation."
        ),
    )

    resume.add_argument(
        "--plan-only",
        action="store_true",
    )

    resume.set_defaults(
        func=command_resume
    )

    self_test = sub.add_parser(
        "self-test",
        help=(
            "Zero-model UX self-test."
        ),
    )

    self_test.set_defaults(
        func=lambda args:
            command_self_test()
    )

    return parser


def main():
    parser = build_parser()

    args = parser.parse_args()

    try:
        return args.func(
            args
        )

    except (
        ValueError,
        RuntimeError,
    ) as exc:
        print(
            "CAREER-OPS ERROR:",
            str(exc),
            file=sys.stderr,
        )

        return 2


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
