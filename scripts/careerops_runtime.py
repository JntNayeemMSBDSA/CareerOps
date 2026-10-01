#!/usr/bin/env python3

import os
import re
from pathlib import Path


RUN_ID_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
)


def _resolve_under_root(root: Path, raw: str) -> Path:
    value = Path(raw).expanduser()

    if value.is_absolute():
        return value.resolve()

    return (root / value).resolve()


def current_run_id():
    raw = os.environ.get(
        "CAREEROPS_RUN_ID",
        "",
    ).strip()

    if not raw:
        return None

    if not RUN_ID_RE.fullmatch(raw):
        raise RuntimeError(
            "Invalid CAREEROPS_RUN_ID. "
            "Allowed: letters, digits, dot, underscore, hyphen; "
            "maximum 128 characters."
        )

    return raw


def runtime_dir(root: Path) -> Path:
    """
    Resolve the active Career-Ops runtime.

    Priority:
      1. CAREEROPS_RUNTIME_DIR
      2. CAREEROPS_RUN_ID
      3. legacy global runtime

    This preserves backward compatibility while allowing each job
    to execute in a fully isolated runtime workspace.
    """
    root = Path(root).resolve()

    explicit = os.environ.get(
        "CAREEROPS_RUNTIME_DIR",
        "",
    ).strip()

    if explicit:
        runtime = _resolve_under_root(
            root,
            explicit,
        )
    else:
        run_id = current_run_id()

        if run_id:
            runtime = (
                root
                / "data"
                / "careerops-engine"
                / "runs"
                / run_id
                / "runtime"
            )
        else:
            runtime = (
                root
                / "data"
                / "careerops-engine"
                / "runtime"
            )

    runtime.mkdir(
        parents=True,
        exist_ok=True,
    )

    return runtime


def run_dir(root: Path) -> Path:
    runtime = runtime_dir(root)

    run_id = current_run_id()

    if run_id:
        return runtime.parent

    explicit = os.environ.get(
        "CAREEROPS_RUNTIME_DIR",
        "",
    ).strip()

    if explicit:
        return runtime.parent

    return runtime


def output_dir(root: Path) -> Path:
    """
    Candidate-facing output directory.

    Explicit CAREEROPS_OUTPUT_DIR wins.

    With CAREEROPS_RUN_ID, outputs default to:
      data/careerops-engine/runs/<run_id>/output

    Legacy behavior remains:
      output/
    """
    root = Path(root).resolve()

    explicit = os.environ.get(
        "CAREEROPS_OUTPUT_DIR",
        "",
    ).strip()

    if explicit:
        out = _resolve_under_root(
            root,
            explicit,
        )

    else:
        run_id = current_run_id()

        if run_id:
            out = (
                root
                / "data"
                / "careerops-engine"
                / "runs"
                / run_id
                / "output"
            )
        else:
            out = root / "output"

    out.mkdir(
        parents=True,
        exist_ok=True,
    )

    return out
