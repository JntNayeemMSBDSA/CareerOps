"""Bounded adapter over the existing LI runner and semantic arbitration.

Model output is a proposal. No source, candidate facts, blockers, gates, or
release state can be written by this module. Historical advisory disagreement
is deliberately not sufficient to propose a correction.
"""
from __future__ import annotations

import copy
import hashlib
from typing import Any

from careerops_semantic_arbitration import build_case, choose_route

SCHEMA = "career-ops-semantic-challenger-v1"
AUTHORITY = {
    "may_mutate_source": False,
    "may_create_candidate_facts": False,
    "may_waive_hard_blocker": False,
    "may_set_release_ready": False,
    "may_publish": False,
}
STATUSES = {"DETERMINISTIC_CORRECT", "PROPOSE_CORRECTION", "INCONCLUSIVE", "UNAVAILABLE"}


def source_hash(raw_source: str) -> str:
    return hashlib.sha256(raw_source.encode("utf-8")).hexdigest()


def ledger_of(deterministic: dict) -> dict:
    ledger = deterministic.get("requirements")
    if isinstance(ledger, dict):
        return ledger
    if isinstance(ledger, list):
        return {"requirements": ledger}
    return {}


def authority_violation(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if (key in AUTHORITY or key.startswith("model_may_")) and child is not False:
                return True
            if key in {"release_ready", "RELEASE_READY", "publish", "candidate_facts", "source_override", "blocker_waiver"}:
                return True
            if authority_violation(child):
                return True
    elif isinstance(value, list):
        return any(authority_violation(child) for child in value)
    return False


def validate_findings(raw_source: str, deterministic: dict, findings: Any) -> list[str]:
    from careerops_li_hybrid_shadow import model_finding_supported
    from careerops_requirement_integrity_gate import normalize

    if not isinstance(findings, list) or not findings or len(findings) > 12:
        return ["FINDINGS_MISSING_OR_UNBOUNDED"]
    lines = raw_source.splitlines()
    reqs = {q.get("requirement_id"): q for q in ledger_of(deterministic).get("requirements", []) if isinstance(q, dict)}
    errors = []
    allowed = {"finding_type", "start_line", "end_line", "requirement_id", "exact_source_quote", "confidence"}
    for i, finding in enumerate(findings):
        if not isinstance(finding, dict) or set(finding) - allowed:
            errors.append(f"MALFORMED_FINDING:{i}")
            continue
        start, end = finding.get("start_line"), finding.get("end_line")
        if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(lines):
            errors.append(f"INVALID_SOURCE_SPAN:{i}")
            continue
        quote = "\n".join(lines[start - 1:end])
        if not quote.strip() or finding.get("exact_source_quote") != quote:
            errors.append(f"SOURCE_QUOTE_MISMATCH:{i}")
        if finding.get("confidence") not in {"HIGH", "MEDIUM"}:
            errors.append(f"INSUFFICIENT_CONFIDENCE:{i}")
        rid = finding.get("requirement_id")
        if rid is not None and rid not in reqs:
            errors.append(f"INVENTED_REQUIREMENT_ID:{i}")
        elif rid is not None and finding.get("finding_type") != "SECTION_CONTEXT_RESET":
            if normalize(reqs[rid].get("exact_quote")) != normalize(quote):
                errors.append(f"REQUIREMENT_ANCHOR_MISMATCH:{i}")
        try:
            supported = model_finding_supported(finding, raw_source, deterministic)
        except Exception:
            supported = False
        if not supported:
            errors.append(f"FINDING_NOT_SOURCE_SUPPORTED:{i}")
    return errors


def _calls(result: dict) -> int:
    value = result.get("local_model_calls", 0)
    return value if type(value) is int and 0 <= value <= 1 else 0


def normalize_li_result(raw_source: str, deterministic: dict, result: Any) -> dict | None:
    if result is None:
        return None
    normalized = {
        "schema_version": SCHEMA, "status": "INCONCLUSIVE",
        "grounding_valid": False, "source_hash": source_hash(raw_source),
        "findings": [], "local_model_calls": 0,
        "authority_contract": dict(AUTHORITY), "errors": [],
    }
    if not isinstance(result, dict):
        normalized["errors"] = ["LI_RESULT_NOT_OBJECT"]
        return normalized
    normalized["local_model_calls"] = _calls(result)
    outer = result
    if isinstance(result.get("advisory_result"), dict):
        result = result["advisory_result"]
        normalized["local_model_calls"] = max(normalized["local_model_calls"], _calls(result))
    if authority_violation(outer):
        normalized["errors"] = ["MODEL_AUTHORITY_VIOLATION"]
        return normalized
    status = str(result.get("status", "")).upper()
    if status in {"UNAVAILABLE", "SHADOW_UNAVAILABLE", "TIMEOUT"}:
        normalized["status"] = "UNAVAILABLE"
        normalized["errors"] = ["LOCAL_MODEL_UNAVAILABLE"]
        return normalized
    if status in {"SHADOW_INVALID", "MALFORMED"} or result.get("structural_errors") or result.get("grounding_errors"):
        normalized["errors"] = ["LI_VALIDATION_FAILED"]
        return normalized
    resolution = result.get("semantic_resolution", result.get("challenge_result"))
    if not isinstance(resolution, dict):
        normalized["errors"] = ["ADVISORY_ONLY_NO_STRUCTURED_RESOLUTION"]
        return normalized
    allowed = {"status", "grounding_valid", "source_hash", "findings", "authority_contract"}
    verdict = resolution.get("status")
    if set(resolution) - allowed or verdict not in STATUSES:
        normalized["errors"] = ["MALFORMED_STRUCTURED_RESOLUTION"]
        return normalized
    if verdict in {"INCONCLUSIVE", "UNAVAILABLE"}:
        normalized["status"] = verdict
        return normalized
    if resolution.get("grounding_valid") is not True or resolution.get("source_hash") != source_hash(raw_source):
        normalized["errors"] = ["UNBOUND_OR_UNGROUNDED_RESOLUTION"]
        return normalized
    errors = validate_findings(raw_source, deterministic, resolution.get("findings"))
    if errors:
        normalized["errors"] = errors
        return normalized
    normalized.update(status=verdict, grounding_valid=True, findings=copy.deepcopy(resolution["findings"]))
    return normalized


def challenge_case(payload: dict, raw_source: str, deterministic: dict, li_result: Any = None) -> dict:
    digest = source_hash(raw_source)
    if payload.get("source_hash") not in {None, digest}:
        raise ValueError("CASE_SOURCE_HASH_MISMATCH")
    normalized = normalize_li_result(raw_source, deterministic, li_result)
    case = build_case({**payload, "source_hash": digest, "deterministic_state": copy.deepcopy(deterministic), "qwen_result": normalized})
    case["authority_contract"].update({"model_may_publish": False})
    case["challenger_authority"] = dict(AUTHORITY)
    return case


def resolution_from_probe(raw_source: str, deterministic: dict, probe: Any, report: dict) -> dict:
    """Promote only newly captured, structured, source-validated probe findings.

    The old shadow's disagreement and semantic values are never copied. The
    original deterministic priority owner decides the reconstruction values.
    Unsupported semantic phenomena remain unresolved for shared adjudication.
    """
    from careerops_requirement_integrity_gate import locate_source_lines, expected_priority, normalize
    resolution = {"status": "INCONCLUSIVE", "grounding_valid": False,
                  "source_hash": source_hash(raw_source), "findings": [], "authority_contract": dict(AUTHORITY)}
    if report.get("status") != "AVAILABLE" or report.get("structural_errors") or report.get("grounding_errors"):
        return resolution
    if not isinstance(probe, dict) or not isinstance(probe.get("findings"), list):
        return resolution
    lines = raw_source.splitlines()
    reqs = ledger_of(deterministic).get("requirements", [])
    source_rows, _ = locate_source_lines(raw_source)
    corrections = False
    for model_row in probe["findings"]:
        if not isinstance(model_row, dict) or model_row.get("finding_type") != "PREFERRED_REQUIREMENT":
            continue
        start, end = model_row.get("start_line"), model_row.get("end_line")
        if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(lines):
            continue
        quote = "\n".join(lines[start - 1:end])
        # Validate the original bounded model span before expanding exact
        # ledger anchors. Never derive a finding from advisory disagreement.
        if end - start > 7 or model_row.get("confidence") not in {"HIGH", "MEDIUM"}:
            continue
        from careerops_li_hybrid_shadow import model_finding_supported
        if not model_finding_supported(model_row, raw_source, deterministic):
            continue
        allowed_ids = {q.get("requirement_id") for q in reqs}
        if model_row.get("requirement_id") is not None and model_row.get("requirement_id") not in allowed_ids:
            continue
        for line_number in range(start, end + 1):
            exact_line = lines[line_number - 1]
            matched = [q for q in reqs if normalize(q.get("exact_quote")) == normalize(exact_line)]
            if len(matched) != 1:
                continue
            req = matched[0]
            row = {"finding_type": "PREFERRED_REQUIREMENT", "start_line": line_number,
                   "end_line": line_number, "confidence": model_row["confidence"],
                   "requirement_id": req.get("requirement_id"), "exact_source_quote": exact_line}
            if validate_findings(raw_source, deterministic, [row]):
                continue
            source_row = next((s for s in source_rows if s["line"] == line_number), None)
            if not source_row or expected_priority(source_row["text"], source_row["section"]) != "P3":
                continue
            if req.get("classification") == "HARD_BLOCK" or req.get("hard_blocker") is True or req.get("hard_blocker_phrases"):
                continue
            corrections |= req.get("priority") != "P3"
            if row not in resolution["findings"]:
                resolution["findings"].append(row)
    if resolution["findings"]:
        resolution["status"] = "PROPOSE_CORRECTION" if corrections else "DETERMINISTIC_CORRECT"
        resolution["grounding_valid"] = True
    return resolution


def run_local_challenge(payload: dict, raw_source: str, deterministic: dict, *, timeout=90, li_run=None, no_rag_call=None, rag_call=None) -> dict:
    initial = challenge_case(payload, raw_source, deterministic)
    if initial["route"] != "LOCAL_QWEN":
        return initial
    import careerops_li_advisory_runner as li
    captured = []
    def no_rag(source, state, *, timeout):
        probe = (no_rag_call or li.base_probe.call_probe)(source, state, timeout=timeout)
        captured.append(probe)
        return probe
    def rag(source, state, retrieval_context, *, timeout):
        probe = (rag_call or li.rag_probe.call_probe_rag)(source, state, retrieval_context, timeout=timeout)
        captured.append(probe)
        return probe
    try:
        report = (li_run or li.run)(raw_source, copy.deepcopy(deterministic), timeout=timeout, no_rag_call=no_rag, rag_call=rag)
        if isinstance(report, dict):
            report = copy.deepcopy(report)
            report["captured_probe"] = copy.deepcopy(captured[0]) if len(captured) == 1 else None
            report["challenge_result"] = resolution_from_probe(raw_source, deterministic, captured[0] if len(captured) == 1 else None, report)
    except Exception as exc:
        report = {"status": "UNAVAILABLE", "local_model_calls": 1, "error": f"{type(exc).__name__}:{exc}"}
    case = challenge_case(payload, raw_source, deterministic, report)
    case["li_report"] = report
    return case
