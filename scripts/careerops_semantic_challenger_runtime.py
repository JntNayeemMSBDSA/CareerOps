"""Per-run semantic challenge at the proven requirement-integrity seam.

Original source/intake/ledger remain immutable. The existing effective-view
owner reconstructs state; the existing requirement-integrity gate verifies it.
No writer, source truth, candidate facts, release, or publisher is called here.
"""
from __future__ import annotations
import contextlib
import copy
import hashlib
import json
import threading
from pathlib import Path
from urllib.parse import urlparse

from careerops_effective_runtime import build_effective_bundle, detect_document_constraints, ensure_effective_runtime
from careerops_requirement_integrity_gate import evaluate
from careerops_semantic_challenger_controller import AUTHORITY, challenge_case, run_local_challenge, source_hash, resolution_from_probe

_ENDPOINT_LOCK = threading.RLock()
SCHEMA = "career-ops-semantic-challenger-runtime-v1"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".semantic.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


@contextlib.contextmanager
def local_endpoint(endpoint=None):
    """Reuse the existing probe transport; optional override is localhost only."""
    if not endpoint:
        yield
        return
    parsed = urlparse(endpoint)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.path != "/api/chat" or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ValueError("LOCAL_QWEN_ENDPOINT_REQUIRED")
    import careerops_li_advisory_runner as li
    with _ENDPOINT_LOCK:
        modules = [li.base_probe, li.rag_probe.base]
        original = [module.ENDPOINT for module in modules]
        try:
            for module in modules:
                module.ENDPOINT = endpoint
            yield
        finally:
            for module, previous in zip(modules, original):
                module.ENDPOINT = previous


def attempt(runtime, run_id, *, timeout=90, endpoint=None, no_rag_call=None, rag_call=None, company=None, position=None):
    runtime = Path(runtime)
    protected = [runtime / name for name in ["jd_intake.json", "jd_requirements.json", "jd_source_original.txt"] if (runtime / name).is_file()]
    before = {path.name: sha(path) for path in protected}
    intake = json.loads((runtime / "jd_intake.json").read_text())
    ledger = json.loads((runtime / "jd_requirements.json").read_text())
    raw = str(intake.get("raw_jd_text") or "")
    original_gate = evaluate(intake, ledger)
    report_path = runtime / "semantic_challenger_report.json"
    report = {"schema_version": SCHEMA, "run_id": run_id, "status": "NOT_APPLICABLE",
              "authority_contract": dict(AUTHORITY), "source_hash": source_hash(raw),
              "immutable_hashes": before, "model_accounting": {"qwen_attempted": 0, "qwen_completed": 0,
              "sol_semantic_adjudication_calls": 0, "sol_writer_calls": 0, "exceptional_writer_retry_calls": 0}}
    if original_gate.get("status") == "PASS":
        return report
    codes = set(original_gate.get("blocking_findings", []))
    # Only source-bound section/priority ambiguity is supported here. Other
    # requirement failures retain their actual owner and fail closed.
    if not raw.strip() or codes != {"PRIORITY_DISTRIBUTION_COLLAPSE"}:
        return report
    deterministic = {"requirements": ledger, "requirement_integrity": original_gate, "semantic_ambiguity": True}
    payload = {"run_id": run_id, "stage": "requirement_integrity", "failure_type": "SEMANTIC",
               "failure_code": "PRIORITY_DISTRIBUTION_COLLAPSE", "source_hash": source_hash(raw),
               "source_spans": [], "policy_context": {"source_ledger_immutable": True, "original_gate_required": True}}
    hard = [x for x in detect_document_constraints(intake) if x.get("policy") == "HARD_BLOCK"]
    if hard:
        case = challenge_case({**payload, "failure_type": "HARD_CONFLICT"}, raw, deterministic)
    else:
        cached = None
        stale = False
        if report_path.is_file():
            try:
                previous = json.loads(report_path.read_text())
                if previous.get("run_id") == run_id and previous.get("immutable_hashes") == before:
                    cached = previous.get("case", {}).get("li_report") or {"status": "UNAVAILABLE", "error": "INTERRUPTED_OR_EMPTY_CHALLENGE"}
                    report["model_accounting"] = previous.get("model_accounting", report["model_accounting"])
                else:
                    stale = True
            except Exception:
                stale = True
        advisory_path = runtime / "li_advisory_report.json"
        if cached is None and advisory_path.is_file():
            try:
                cached = json.loads(advisory_path.read_text())
            except Exception:
                cached = {"status": "MALFORMED"}
        if stale:
            cached = {"status": "UNAVAILABLE", "error": "STALE_CHALLENGER_CACHE"}
        if cached is not None:
            if isinstance(cached, dict) and isinstance(cached.get("captured_probe"), dict):
                cached = copy.deepcopy(cached)
                cached["challenge_result"] = resolution_from_probe(raw, deterministic, cached["captured_probe"], cached)
            case = challenge_case(payload, raw, deterministic, cached)
            case["li_report"] = cached
        else:
            # Record the attempt BEFORE inference so an interrupted process
            # cannot spend a second local call when this run resumes.
            report["status"] = "QWEN_ATTEMPT_IN_PROGRESS"
            report["model_accounting"]["qwen_attempted"] = 1
            atomic_json(report_path, report)
            with local_endpoint(endpoint):
                case = run_local_challenge(payload, raw, deterministic, timeout=timeout, no_rag_call=no_rag_call, rag_call=rag_call)
            li_result = case.get("li_report") or {}
            report["model_accounting"]["qwen_completed"] = int(li_result.get("status") == "AVAILABLE")
            # The existing optional advisory seam reuses this evidence rather
            # than making a second local call after a successful reconstruction.
            if not advisory_path.exists():
                atomic_json(advisory_path, {"schema_version": "career-ops-li6-production-advisory-v1",
                    "status": li_result.get("status", "SHADOW_UNAVAILABLE"), "authority": "ADVISORY_ONLY",
                    "may_override": False, "production_decision_effect": "NONE", "continue_deterministic_engine": True,
                    "review_required": bool(li_result.get("review_required")), "run_id": run_id,
                    "company": company, "position": position,
                    "source_kind": "JD_INTAKE_AUTHORITY", "local_model_calls": li_result.get("local_model_calls", 1),
                    "advisory_result": li_result})
    report["case"] = case
    report["status"] = "UNRESOLVED_FAIL_CLOSED"
    if case["route"] in {"DETERMINISTIC_RECONSTRUCTION", "DETERMINISTIC_RESULT_STANDS"}:
        try:
            bundle = build_effective_bundle(intake, ledger, intake_sha=before["jd_intake.json"], ledger_sha=before["jd_requirements.json"])
            rerun = evaluate(intake, bundle["effective_ledger"])
            if rerun["status"] != "PASS":
                from careerops_requirement_regeneration import reconstruct,publish
                regenerated=reconstruct(intake,ledger)
                rerun=regenerated["gate"]
                if regenerated["bundle_status"]=="PASS":
                    publish(runtime,regenerated)
                    bundle=ensure_effective_runtime(runtime)
                    report["source_regeneration_owner"]="CURRENT_PRODUCER_WITH_IMMUTABLE_ORIGINAL_LEDGER"
            report["deterministic_reconstruction_owner"] = "careerops_effective_runtime.build_effective_bundle"
            report["original_gate_owner"] = "careerops_requirement_integrity_gate.evaluate"
            report["original_gate_before"] = original_gate["status"]
            report["original_gate_after"] = rerun["status"]
            if bundle["status"] == "PASS" and rerun["status"] == "PASS":
                actual = ensure_effective_runtime(runtime)
                if actual["effective_ledger"] != bundle["effective_ledger"]:
                    raise RuntimeError("RECONSTRUCTION_CHANGED_DURING_REVALIDATION")
                if {path.name: sha(path) for path in protected} != before:
                    raise RuntimeError("IMMUTABLE_SOURCE_MUTATED")
                archive = runtime / "requirement_integrity_gate.pre_semantic_reconstruction.json"
                if not archive.exists():
                    atomic_json(archive, original_gate)
                rerun["semantic_reconstruction"] = {"authority": "DETERMINISTIC_REVALIDATION", "source_ledger_immutable": True,
                    "model_values_applied": False, "effective_ledger": "jd_requirements_effective.json",
                    "immutable_hashes": before, "challenger_report": "semantic_challenger_report.json"}
                atomic_json(runtime / "requirement_integrity_gate.json", rerun)
                report["status"] = "RECONSTRUCTED_REVALIDATED"
            else:
                report["case"]["route"] = "SHARED_SOL_ADJUDICATION"
                report["reconstruction_error"] = "ORIGINAL_GATE_OR_EFFECTIVE_VIEW_NOT_PASS"
        except Exception as exc:
            report["case"]["route"] = "SHARED_SOL_ADJUDICATION"
            report["reconstruction_error"] = f"{type(exc).__name__}:{exc}"
    report["immutable_source_preserved"] = {path.name: sha(path) for path in protected} == before
    if not report["immutable_source_preserved"]:
        report["status"] = "STOP_HARD_CONFLICT"
    atomic_json(report_path, report)
    return report
