#!/usr/bin/env python3

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from zipfile import ZipFile

from careerops_runtime import (
    current_run_id,
    output_dir,
    runtime_dir,
)


ROOT = Path(__file__).resolve().parents[1]

RUN_ID = current_run_id()
RUNTIME = runtime_dir(ROOT)
OUTPUT = output_dir(ROOT)

ATS_MIN = 85.0
HUMAN_MIN = 85.0


def load_json(path):
    if not path or not path.exists():
        return None

    try:
        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return None


def sha256(path):
    if not path or not path.exists():
        return None

    h = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(
            lambda: f.read(
                1024 * 1024
            ),
            b"",
        ):
            h.update(chunk)

    return h.hexdigest()


def relative(path):
    if path is None:
        return None

    try:
        return str(
            path.resolve().relative_to(
                ROOT
            )
        )
    except Exception:
        return str(
            path.resolve()
        )


def report_gate_pass(obj):
    if not isinstance(
        obj,
        dict,
    ):
        return False

    if obj.get("pass") is True:
        return True

    if obj.get("passed") is True:
        return True

    return (
        str(
            obj.get(
                "gate",
                "",
            )
        ).strip().upper()
        == "PASS"
    )


def score(obj):
    if not isinstance(
        obj,
        dict,
    ):
        return None

    value = obj.get(
        "score"
    )

    try:
        return float(value)
    except Exception:
        return None


def pdf_pages(path):
    if (
        path is None
        or not path.exists()
    ):
        return None

    exe = shutil.which(
        "pdfinfo"
    )

    if not exe:
        return None

    result = subprocess.run(
        [
            exe,
            str(path),
        ],
        text=True,
        capture_output=True,
    )

    if result.returncode != 0:
        return None

    match = re.search(
        r"^Pages:\s+(\d+)\s*$",
        result.stdout,
        flags=re.M,
    )

    if not match:
        return None

    return int(
        match.group(1)
    )


def pdf_text_extractable(path):
    if (
        path is None
        or not path.exists()
    ):
        return False

    exe = shutil.which(
        "pdftotext"
    )

    if not exe:
        return False

    result = subprocess.run(
        [
            exe,
            str(path),
            "-",
        ],
        text=True,
        capture_output=True,
    )

    return (
        result.returncode == 0
        and len(
            re.sub(
                r"\s+",
                "",
                result.stdout,
            )
        ) > 100
    )


def docx_valid(path):
    if (
        path is None
        or not path.exists()
    ):
        return False

    try:
        with ZipFile(path) as z:
            names = set(
                z.namelist()
            )

            return (
                "[Content_Types].xml"
                in names
                and
                "word/document.xml"
                in names
            )
    except Exception:
        return False


def release_safe_name(path):
    if path is None:
        return False

    bad = (
        "layout_candidate",
        "preview",
        "geometry",
        "headerfix",
        "should_not_exist",
    )

    name = path.name.lower()

    return not any(
        token in name
        for token in bad
    )


def is_within(path, parent):
    if path is None:
        return False

    try:
        path.resolve().relative_to(
            parent.resolve()
        )
        return True
    except Exception:
        return False


def resolve_path(value):
    if value is None:
        return None

    path = Path(
        value
    ).expanduser()

    if not path.is_absolute():
        path = (
            ROOT
            / path
        )

    return path.resolve()


def discover_output(
    explicit,
    pattern,
):
    """
    Resolve one release artifact.

    Explicit CLI paths win.

    Otherwise discover exactly one release-safe file inside
    the active run's output directory.

    Never choose "latest". Multiple eligible outputs are an
    ambiguity and therefore fail closed.
    """

    if explicit:
        path = resolve_path(
            explicit
        )

        return {
            "path":
                path,

            "mode":
                "EXPLICIT",

            "candidate_count":
                1,

            "candidates": [
                relative(path)
            ],
        }

    matches = sorted(
        [
            p.resolve()
            for p in OUTPUT.glob(
                pattern
            )
            if p.is_file()
        ],
        key=lambda p:
            p.name,
    )

    release_safe = [
        p
        for p in matches
        if release_safe_name(p)
    ]

    if len(release_safe) == 1:
        return {
            "path":
                release_safe[0],

            "mode":
                "DISCOVERED",

            "candidate_count":
                1,

            "candidates": [
                relative(
                    release_safe[0]
                )
            ],
        }

    if not matches:
        mode = "MISSING"

    elif not release_safe:
        mode = (
            "NO_RELEASE_SAFE_MATCH"
        )

    else:
        mode = "AMBIGUOUS"

    return {
        "path":
            None,

        "mode":
            mode,

        "candidate_count":
            len(release_safe),

        "candidates": [
            relative(p)
            for p in release_safe
        ],
    }


def artifact_record(path):
    if (
        path is None
        or not path.exists()
    ):
        return {
            "exists":
                False,

            "path":
                relative(path),

            "sha256":
                None,

            "size_bytes":
                None,
        }

    return {
        "exists":
            True,

        "path":
            relative(path),

        "sha256":
            sha256(path),

        "size_bytes":
            path.stat().st_size,
    }


def main():
    if (RUNTIME/'quarantine_generation_authorization.json').is_file() or (RUNTIME/'user_generation_override_authorization.json').is_file():
        raise SystemExit('Unreleased user override cannot invoke normal release authority.')

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--resume-pdf",
        default=None,
    )

    parser.add_argument(
        "--resume-docx",
        default=None,
    )

    parser.add_argument(
        "--cover-pdf",
        default=None,
    )

    parser.add_argument(
        "--cover-docx",
        default=None,
    )

    parser.add_argument(
        "--report",
        default=str(
            RUNTIME
            / "pair_release_gate_report.json"
        ),
    )

    args = parser.parse_args()

    from careerops_requirement_authority import check_artifact
    for artifact in ['ats_gate.json','human_gate.json','cover_gate_v2_report.json','final_application_audit_report.json']:
        check_artifact(RUNTIME, artifact, require_stamp=True)

    report_path = resolve_path(
        args.report
    )

    resume_pdf_discovery = (
        discover_output(
            args.resume_pdf,
            "careerops_resume_*.pdf",
        )
    )

    resume_docx_discovery = (
        discover_output(
            args.resume_docx,
            "careerops_resume_*.docx",
        )
    )

    cover_pdf_discovery = (
        discover_output(
            args.cover_pdf,
            "careerops_cover_*.pdf",
        )
    )

    cover_docx_discovery = (
        discover_output(
            args.cover_docx,
            "careerops_cover_*.docx",
        )
    )

    resume_pdf = (
        resume_pdf_discovery[
            "path"
        ]
    )

    resume_docx = (
        resume_docx_discovery[
            "path"
        ]
    )

    cover_pdf = (
        cover_pdf_discovery[
            "path"
        ]
    )

    cover_docx = (
        cover_docx_discovery[
            "path"
        ]
    )

    # ------------------------------------------------------------
    # Canonical current-run content authorities
    # ------------------------------------------------------------

    resume_candidate = (
        RUNTIME
        / "generated_resume_content_pair_candidate.json"
    )

    cover_candidate = (
        RUNTIME
        / "generated_cover_letter_pair_candidate.json"
    )

    # ------------------------------------------------------------
    # Current-run gate reports
    # ------------------------------------------------------------

    truth_path = (
        RUNTIME
        / "truth_gate.json"
    )

    local_truth_path = (
        RUNTIME
        / "local_truth_gate.json"
    )

    ats_path = (
        RUNTIME
        / "ats_gate.json"
    )

    human_path = (
        RUNTIME
        / "human_gate.json"
    )

    cover_gate_path = (
        RUNTIME
        / "cover_gate_v2_report.json"
    )

    cover_roundtrip_path = (
        RUNTIME
        / "cover_roundtrip_report.json"
    )

    requirement_integrity_path = (
        RUNTIME
        / "requirement_integrity_gate.json"
    )

    resume_roundtrip_path = (
        RUNTIME
        / "resume_roundtrip_report.json"
    )

    final_application_audit_path = (
        RUNTIME
        / "final_application_audit_report.json"
    )

    truth = load_json(
        truth_path
    )

    local_truth = load_json(
        local_truth_path
    )

    ats = load_json(
        ats_path
    )

    human = load_json(
        human_path
    )

    cover_gate = load_json(
        cover_gate_path
    )

    cover_roundtrip = load_json(
        cover_roundtrip_path
    )

    requirement_integrity = load_json(
        requirement_integrity_path
    )

    resume_roundtrip = load_json(
        resume_roundtrip_path
    )

    final_application_audit = load_json(
        final_application_audit_path
    )

    ats_value = score(
        ats
    )

    human_value = score(
        human
    )

    resume_pages = pdf_pages(
        resume_pdf
    )

    cover_pages = pdf_pages(
        cover_pdf
    )

    output_paths = [
        resume_pdf,
        resume_docx,
        cover_pdf,
        cover_docx,
    ]

    # ------------------------------------------------------------
    # Fail-closed universal release checks
    # ------------------------------------------------------------

    from careerops_contact_identity import verify_contacts
    contact_identity = verify_contacts(output_paths, (load_json(RUNTIME / 'career_ops_cv_payload.json') or {}).get('candidate',{}))
    checks = {
        'canonical_contact_link_targets': contact_identity['pass'],
        # --------------------------------------------------------
        # RUN ISOLATION
        # --------------------------------------------------------

        "run_id_present":
            bool(RUN_ID),

        "report_is_runtime_local":
            is_within(
                report_path,
                RUNTIME,
            ),

        "all_release_artifacts_resolved":
            all(
                path is not None
                for path
                in output_paths
            ),

        "all_release_artifacts_run_local":
            all(
                is_within(
                    path,
                    OUTPUT,
                )
                for path
                in output_paths
                if path is not None
            )
            and all(
                path is not None
                for path
                in output_paths
            ),

        # --------------------------------------------------------
        # CURRENT JOB CONTENT AUTHORITIES
        # --------------------------------------------------------

        "resume_candidate_exists":
            resume_candidate.exists(),

        "resume_candidate_json_valid":
            load_json(
                resume_candidate
            ) is not None,

        "cover_candidate_exists":
            cover_candidate.exists(),

        "cover_candidate_json_valid":
            load_json(
                cover_candidate
            ) is not None,

        # --------------------------------------------------------
        # RESUME CONTENT QUALITY
        # --------------------------------------------------------

        "resume_truth_gate":
            report_gate_pass(
                truth
            ),

        "resume_local_truth_gate":
            report_gate_pass(
                local_truth
            ),

        "requirement_integrity_gate":
            (
                isinstance(
                    requirement_integrity,
                    dict,
                )
                and requirement_integrity.get(
                    "schema_version"
                )
                == "requirement-integrity-gate-v1"
                and requirement_integrity.get(
                    "status"
                )
                == "PASS"
                and requirement_integrity.get(
                    "model_calls"
                )
                == 0
                and not requirement_integrity.get(
                    "blocking_findings",
                    [],
                )
            ),

        "resume_ats_gate":
            (
                isinstance(
                    ats,
                    dict,
                )
                and ats.get(
                    "schema_version"
                )
                == "careerops-internal-ats-gate-v2"
                and report_gate_pass(
                    ats
                )
                and ats_value is not None
                and ats_value >= ATS_MIN
                and ats.get(
                    "model_calls"
                )
                == 0
                and not ats.get(
                    "hard_fail_reasons",
                    [],
                )
            ),

        "resume_human_gate":
            (
                isinstance(
                    human,
                    dict,
                )
                and human.get(
                    "schema_version"
                )
                == "careerops-human-gate-v2.2"
                and report_gate_pass(
                    human
                )
                and human.get(
                    "quality_gate"
                )
                == "PASS"
                # Human Gate V2.2 distinguishes blocking failures
                # from non-blocking quality warnings. PASS_WITH_WARNINGS
                # is release-valid when the canonical gate/quality_gate
                # pass, score clears threshold, and no hard/human failure
                # reasons remain.
                and human.get(
                    "quality_status"
                )
                in {
                    "PASS",
                    "PASS_WITH_WARNINGS",
                }
                and human_value
                is not None
                and human_value
                >= HUMAN_MIN
                and human.get(
                    "model_calls"
                )
                == 0
                and not human.get(
                    "hard_fail_reasons",
                    [],
                )
                and not human.get(
                    "human_fail_reasons",
                    [],
                )
            ),

        # --------------------------------------------------------
        # RESUME RELEASE ARTIFACTS
        # --------------------------------------------------------

        "resume_pdf_exists":
            (
                resume_pdf
                is not None
                and
                resume_pdf.exists()
            ),

        "resume_pdf_one_page":
            resume_pages == 1,

        "resume_pdf_text_extractable":
            pdf_text_extractable(
                resume_pdf
            ),

        "resume_pdf_release_safe_name":
            release_safe_name(
                resume_pdf
            ),

        "resume_docx_exists":
            (
                resume_docx
                is not None
                and
                resume_docx.exists()
            ),

        "resume_docx_valid":
            docx_valid(
                resume_docx
            ),

        "resume_docx_release_safe_name":
            release_safe_name(
                resume_docx
            ),

        # --------------------------------------------------------
        # RESUME PDF/DOCX ROUND-TRIP
        # --------------------------------------------------------

        "resume_roundtrip":
            (
                isinstance(
                    resume_roundtrip,
                    dict,
                )
                and resume_roundtrip.get(
                    "schema_version"
                )
                == "careerops-resume-roundtrip-v1"
                and resume_roundtrip.get(
                    "gate"
                )
                == "PASS"
                and resume_roundtrip.get(
                    "pass"
                )
                is True
                and resume_roundtrip.get(
                    "model_calls"
                )
                == 0
                and not resume_roundtrip.get(
                    "failed_checks",
                    [],
                )
                and resume_roundtrip.get(
                    "checks",
                    {},
                ).get(
                    "pdf_no_content_loss"
                )
                is True
                and resume_roundtrip.get(
                    "checks",
                    {},
                ).get(
                    "docx_no_content_loss"
                )
                is True
                and resume_roundtrip.get(
                    "checks",
                    {},
                ).get(
                    "pdf_docx_consistency"
                )
                is True
            ),

        # --------------------------------------------------------
        # INDEPENDENT FINAL APPLICATION AUDIT
        # --------------------------------------------------------

        "final_application_audit":
            (
                isinstance(
                    final_application_audit,
                    dict,
                )
                and final_application_audit.get(
                    "schema_version"
                )
                == "career-ops-final-application-audit-v1"
                and final_application_audit.get(
                    "gate"
                )
                == "PASS"
                and final_application_audit.get(
                    "pass"
                )
                is True
                and final_application_audit.get(
                    "model_calls"
                )
                == 0
                and final_application_audit.get(
                    "summary",
                    {},
                ).get(
                    "blocking_finding_count"
                )
                == 0
            ),

        # --------------------------------------------------------
        # COVER CONTENT QUALITY
        # --------------------------------------------------------

        "cover_gate_v2":
            (
                isinstance(
                    cover_gate,
                    dict,
                )
                and
                cover_gate.get(
                    "pass"
                ) is True
            ),

        # --------------------------------------------------------
        # COVER ROUNDTRIP
        # --------------------------------------------------------

        "cover_roundtrip":
            (
                isinstance(
                    cover_roundtrip,
                    dict,
                )
                and
                cover_roundtrip.get(
                    "pass"
                ) is True
            ),

        # --------------------------------------------------------
        # COVER RELEASE ARTIFACTS
        # --------------------------------------------------------

        "cover_pdf_exists":
            (
                cover_pdf
                is not None
                and
                cover_pdf.exists()
            ),

        "cover_pdf_one_page":
            cover_pages == 1,

        "cover_pdf_text_extractable":
            pdf_text_extractable(
                cover_pdf
            ),

        "cover_pdf_release_safe_name":
            release_safe_name(
                cover_pdf
            ),

        "cover_docx_exists":
            (
                cover_docx
                is not None
                and
                cover_docx.exists()
            ),

        "cover_docx_valid":
            docx_valid(
                cover_docx
            ),

        "cover_docx_release_safe_name":
            release_safe_name(
                cover_docx
            ),
    }

    failed = [
        key
        for key, value
        in checks.items()
        if not value
    ]

    release_ready = (
        len(failed) == 0
    )

    gate_reports = {
        "truth_gate":
            artifact_record(
                truth_path
            ),

        "local_truth_gate":
            artifact_record(
                local_truth_path
            ),

        "ats_gate":
            artifact_record(
                ats_path
            ),

        "human_gate":
            artifact_record(
                human_path
            ),

        "cover_gate_v2":
            artifact_record(
                cover_gate_path
            ),

        "cover_roundtrip":
            artifact_record(
                cover_roundtrip_path
            ),

        "requirement_integrity":
            artifact_record(
                requirement_integrity_path
            ),

        "resume_roundtrip":
            artifact_record(
                resume_roundtrip_path
            ),

        "final_application_audit":
            artifact_record(
                final_application_audit_path
            ),
    }

    artifacts = {
        "resume_candidate_json":
            artifact_record(
                resume_candidate
            ),

        "cover_candidate_json":
            artifact_record(
                cover_candidate
            ),

        "resume_pdf":
            artifact_record(
                resume_pdf
            ),

        "resume_docx":
            artifact_record(
                resume_docx
            ),

        "cover_pdf":
            artifact_record(
                cover_pdf
            ),

        "cover_docx":
            artifact_record(
                cover_docx
            ),

        "resume_pdf_pages":
            resume_pages,

        "cover_pdf_pages":
            cover_pages,
    }

    discovery = {
        "resume_pdf": {
            key: (
                relative(value)
                if key == "path"
                and value is not None
                else value
            )
            for key, value
            in resume_pdf_discovery.items()
        },

        "resume_docx": {
            key: (
                relative(value)
                if key == "path"
                and value is not None
                else value
            )
            for key, value
            in resume_docx_discovery.items()
        },

        "cover_pdf": {
            key: (
                relative(value)
                if key == "path"
                and value is not None
                else value
            )
            for key, value
            in cover_pdf_discovery.items()
        },

        "cover_docx": {
            key: (
                relative(value)
                if key == "path"
                and value is not None
                else value
            )
            for key, value
            in cover_docx_discovery.items()
        },
    }

    report = {
        "schema_version":
            "careerops-pair-release-gate-v2",

        "gate":
            "careerops-pair-release-gate-v2",

        "run_id":
            RUN_ID,

        "runtime":
            relative(
                RUNTIME
            ),

        "output_root":
            relative(
                OUTPUT
            ),

        "contact_identity": contact_identity,
        "release_ready":
            release_ready,

        "thresholds": {
            "ats_min":
                ATS_MIN,

            "human_min":
                HUMAN_MIN,

            "resume_pdf_max_pages":
                1,

            "cover_pdf_max_pages":
                1,
        },

        "scores": {
            "ats":
                ats_value,

            "human":
                human_value,
        },

        "discovery":
            discovery,

        "artifacts":
            artifacts,

        "gate_reports":
            gate_reports,

        "checks":
            checks,

        "failed_checks":
            failed,

        "model_calls":
            0,
    }

    report_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tmp = report_path.with_suffix(
        report_path.suffix
        + ".tmp"
    )

    tmp.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    tmp.replace(
        report_path
    )

    print()
    print(
        "=" * 88
    )

    print(
        "CAREEROPS UNIVERSAL PAIR RELEASE GATE V2"
    )

    print(
        "=" * 88
    )

    print(
        "RUN ID:",
        RUN_ID
        or "MISSING",
    )

    print(
        "RUNTIME:",
        relative(
            RUNTIME
        ),
    )

    print(
        "OUTPUT:",
        relative(
            OUTPUT
        ),
    )

    print(
        "ATS:",
        ats_value,
    )

    print(
        "HUMAN:",
        human_value,
    )

    print(
        "RESUME PAGES:",
        resume_pages,
    )

    print(
        "COVER PAGES:",
        cover_pages,
    )

    print(
        "RELEASE READY:",
        "YES"
        if release_ready
        else "NO",
    )

    if failed:
        print()
        print(
            "FAILED CHECKS:"
        )

        for key in failed:
            print(
                " -",
                key,
            )

    print()
    print(
        "REPORT:",
        relative(
            report_path
        ),
    )

    print(
        "MODEL CALLS: 0"
    )

    raise SystemExit(
        0
        if release_ready
        else 1
    )


if __name__ == "__main__":
    main()
