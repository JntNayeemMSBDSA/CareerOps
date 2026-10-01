"""Central deterministic repair ownership; no automatic writer retries."""
from __future__ import annotations
import argparse
import ast
import copy
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from careerops_semantic_arbitration import choose_route

ROOT = Path(__file__).resolve().parents[1]
AUDITED = {
    "careerops_apply_resume_invariants.py": "7d51cf5f1042b3aa40d43e2daedf4dcdf13fe507c4c3f5670f736a88ef7a9ebe",
    "careerops_repair_resume_ats_terms.py": "c9563aa8e278e696d1b4541317199b84b14d234000f9f592aeffbeb9b70d6ee5",
    "careerops_repair_cover_candidate.py": "ab1f8db64c9cec76eccab8f4ab3680d9420a2fbb797571d35812fcd746eb4610",
}
MECHANICAL_COVER = {"paragraph3_names_company", "no_ai_pattern_language", "no_paragraph3_keyword_stack", "jd_terms_present", "body_word_count"}
SEMANTIC_COVER = {"specific_interest", "semantic_resume_complementarity", "paragraph1_specific_hook", "judgment_and_why_visible", "target_role_application_specific", "writing_mechanics"}
CATEGORIES = {"MECHANICAL", "RESUME_INVARIANT", "ATS_TERMINOLOGY", "COVER_MECHANICAL", "RENDERER", "VALIDATOR", "HARNESS", "SEMANTIC", "HARD_CONFLICT", "WRITING"}


def audited_helpers(filename, functions, constants=()):
    """Load only reviewed pure AST nodes; legacy top-level code never runs."""
    path = ROOT/"scripts"/filename
    if hashlib.sha256(path.read_bytes()).hexdigest() != AUDITED[filename]:
        raise RuntimeError("AUDITED_REPAIR_OWNER_HASH_CHANGED")
    tree = ast.parse(path.read_text())
    selected = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in functions:
            selected.append(node)
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in constants for t in node.targets):
            selected.append(node)
    namespace = {"re": re}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    if any(name not in namespace for name in functions):
        raise RuntimeError("AUDITED_HELPER_MISSING")
    return namespace


def plan(category, *, detail=None, owner=None):
    category = str(category).upper()
    route = "NEEDS_OWNER_REPAIR"
    if category in {"MECHANICAL", "RESUME_INVARIANT", "ATS_TERMINOLOGY", "COVER_MECHANICAL"}:
        route = choose_route("MECHANICAL")
    elif category in {"RENDERER", "HARNESS", "HARD_CONFLICT", "SEMANTIC"}:
        route = choose_route(category)
    elif category == "VALIDATOR":
        route = "VALIDATOR_REPAIR"
    elif category == "WRITING":
        route = "EXCEPTIONAL_WRITER_REVIEW"
    return {"schema_version": "career-ops-deterministic-repair-plan-v1", "category": category,
            "route": route, "owner": owner or category, "detail": detail,
            "automatic_writer_retry": False, "second_writer_call_permitted": False,
            "original_gate_rerun_required": route != "STOP_HARD_CONFLICT", "model_calls": 0}


def plan_for_failure(stage, report, classification):
    normalized = str(stage).lower()
    report = report if isinstance(report, dict) else {}
    if "cover" in normalized:
        failed = set(report.get("failed_checks", []))
        if failed & SEMANTIC_COVER:
            return plan("SEMANTIC", owner="QWEN_SEMANTIC_CHALLENGER", detail=sorted(failed))
        if failed and failed <= MECHANICAL_COVER:
            return plan("COVER_MECHANICAL", owner="careerops_repair_cover_candidate.py", detail=sorted(failed))
    failure_class = classification.get("failure_class")
    if failure_class in {"RENDERER", "RENDER", "PDF_RENDER", "DOCX_RENDER"} or "render" in normalized:
        return plan("RENDERER", owner=normalized)
    if failure_class == "HARNESS" or "harness" in normalized:
        return plan("HARNESS", owner=normalized)
    if failure_class in {"ELIGIBILITY", "HARD_CONFLICT"}:
        return plan("HARD_CONFLICT", owner="CONSTRAINT_VALIDATION")
    if report.get("blocking_findings") == ["PRIORITY_DISTRIBUTION_COLLAPSE"]:
        return plan("SEMANTIC", owner="QWEN_SEMANTIC_CHALLENGER")
    if failure_class == "WRITING":
        return plan("WRITING", owner="WRITER_DEFECT_REVIEW")
    if failure_class in {"GATE", "VALIDATION", "VALIDATOR", "COVER_VALIDATION"} or "validator" in normalized:
        return plan("VALIDATOR", owner=normalized)
    return plan("UNCLASSIFIED", owner="FAILURE_OWNER_TRIAGE")


def normalize_prose(payload, context):
    result = copy.deepcopy(payload)
    def clean(value):
        if isinstance(value, str):
            return re.sub(r"[ \t]+", " ", value).strip()
        if isinstance(value, list):
            return [clean(v) for v in value]
        return value
    for key in ["summary", "paragraphs"]:
        if key in result:
            result[key] = clean(result[key])
    for key in ["experience", "projects"]:
        for row in result.get(key, []):
            if isinstance(row, dict) and "bullets" in row:
                row["bullets"] = clean(row["bullets"])
    return result


def repair_invariants(payload, context):
    helpers = audited_helpers("careerops_apply_resume_invariants.py", {"strip_decimal", "compact_integer", "compact_large_numbers"}, {"NUMBER_PATTERN"})
    result = copy.deepcopy(payload)
    # Numeric compression must be lossless. The old helper rounds some values;
    # those replacements are rejected rather than weakening a source metric.
    def compact(text):
        revised, changes = helpers["compact_large_numbers"](text)
        for old, new in changes:
            original = int(re.sub(r"[^0-9]", "", old))
            matched = re.fullmatch(r"\$?([0-9.]+)([KMB])", new)
            if not matched or float(matched.group(1)) * {"K": 1000, "M": 1000000, "B": 1000000000}[matched.group(2)] != original:
                revised = revised.replace(new, old, 1)
        return revised
    for key in ["experience", "projects"]:
        for row in result.get(key, []):
            row["bullets"] = [compact(str(x)) for x in row.get("bullets", [])]
    return result


def repair_ats_terms(payload, context):
    helpers = audited_helpers("careerops_repair_resume_ats_terms.py", {"norm", "unique", "phrase_present"})
    norm = helpers["norm"]
    requested = helpers["unique"](context.get("missing_jd_terms", []))
    authorized = {norm(x) for x in context.get("direct_user_confirmed_terms", []) + context.get("verified_skill_terms", [])}
    if not requested or len(requested) > 4 or any(norm(term) not in authorized for term in requested):
        raise ValueError("SEMANTIC_OR_UNAUTHORIZED_ATS_PLACEMENT")
    result = copy.deepcopy(payload)
    category = next((row for row in result.get("skills", []) if isinstance(row, dict) and row.get("category") == context.get("skills_category", "Tools & Workflow") and isinstance(row.get("terms"), list)), None)
    if category is None:
        raise ValueError("NO_EXISTING_AUTHORIZED_SKILLS_SURFACE")
    existing = {norm(x) for x in category["terms"]}
    for term in requested:
        if norm(term) not in existing:
            category["terms"].append(term)
            existing.add(norm(term))
    return result


def dispatch(category, payload, context, *, original_gate=None, handler=None):
    decision = plan(category)
    report = {**decision, "status": "NEEDS_OWNER_REPAIR", "candidate": None}
    if decision["route"] in {"LOCAL_QWEN", "STOP_HARD_CONFLICT", "EXCEPTIONAL_WRITER_REVIEW", "NEEDS_OWNER_REPAIR"}:
        report["status"] = decision["route"]
        return report
    if original_gate is None:
        report["error"] = "ORIGINAL_GATE_REQUIRED"
        return report
    handlers = {"MECHANICAL": normalize_prose, "RESUME_INVARIANT": repair_invariants, "ATS_TERMINOLOGY": repair_ats_terms}
    repair = handler or handlers.get(str(category).upper())
    if repair is None:
        return report
    original = copy.deepcopy(payload)
    try:
        candidate = repair(copy.deepcopy(payload), copy.deepcopy(context))
        gate = original_gate(copy.deepcopy(candidate))
        report["original_gate"] = gate
        if payload != original:
            raise RuntimeError("AUTHORITATIVE_INPUT_MUTATED")
        if gate.get("status") == "PASS":
            report.update(status="REPAIRED_REVALIDATED", candidate=candidate)
        else:
            report["status"] = "FAIL_CLOSED_ORIGINAL_GATE"
    except (Exception, SystemExit) as exc:
        report.update(status="NEEDS_OWNER_REPAIR", error=f"{type(exc).__name__}:{exc}")
        if "SEMANTIC_OR_UNAUTHORIZED" in str(exc):
            report.update(route="LOCAL_QWEN", status="LOCAL_QWEN")
    return report


def exceptional_writer_permission(classification, exclusions, defect_evidence):
    required = {"MECHANICAL", "RESUME_INVARIANT", "ATS_TERMINOLOGY", "COVER_MECHANICAL", "RENDERER", "VALIDATOR", "HARNESS"}
    allowed = (classification.get("failure_class") == "WRITING" and classification.get("writing_defect_confirmed") is True
               and set(exclusions) == required and all(v in {"RULED_OUT", "NOT_APPLICABLE"} for v in exclusions.values())
               and isinstance(defect_evidence, dict) and bool(defect_evidence.get("exact_defective_text"))
               and bool(defect_evidence.get("original_gate_failure")))
    return {"second_writer_call_permitted": allowed, "automatic_writer_retry": False, "requires_explicit_exceptional_retry": allowed, "exceptional_writer_retry_calls": 0}


def canonical_identity_dependency(cover, cover_plan, gate):
    """Only a missing full name whose absence also blocks existing JD interest."""
    from careerops_cover_gate_v2 import has_interest_intent
    failed=set(gate.get('failed_checks',[]))
    if not failed or not failed <= {'paragraph3_names_company','specific_interest'} or 'paragraph3_names_company' not in failed:return False
    company=cover_plan.get('target_job',{}).get('company')
    if not company or cover.get('company')!=company or len(cover.get('paragraphs',[]))!=3:return False
    acronym=audited_helpers('careerops_repair_cover_candidate.py',['acronym_from_company'])['acronym_from_company'](company)
    paragraph=cover['paragraphs'][2];interest=cover_plan.get('interest_reason',{})
    return bool(acronym and re.search(r'\b'+re.escape(acronym)+r'\b',paragraph) and company not in paragraph and has_interest_intent(paragraph) and gate.get('checks',{}).get('target_role_application_specific') is True and interest.get('source')=='TARGET_JD' and interest.get('confidence')=='JD_SPECIFIC' and cover_plan.get('target_role_application',{}).get('target_requirements'))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cover', required=True)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    cover, plan_path, gate_path = [Path(x).resolve() for x in [args.cover, args.plan, args.report]]
    if len({x.parent for x in [cover, plan_path, gate_path]}) != 1:
        raise ValueError('CROSS_RUN_REPAIR_PATHS')
    gate = json.loads(gate_path.read_text())
    failed = set(gate.get('failed_checks', []))
    decision = plan_for_failure('cover_gate', gate, {'failure_class': 'COVER_VALIDATION'})
    report = {**decision, 'status': 'NEEDS_OWNER_REPAIR', 'source_gate': str(gate_path)}
    result_code = 2
    if canonical_identity_dependency(json.loads(cover.read_text()), json.loads(plan_path.read_text()), gate):
        original_gate_path = gate_path
        gate_path = cover.parent / 'canonical_identity_dependency_repair_input.json'
        minimal = copy.deepcopy(gate)
        minimal['failed_checks'] = ['paragraph3_names_company']
        minimal['dependency_note'] = 'Existing interest intent and JD-specific target application pass; specific_interest depends on exact canonical identity. Original full gate rerun remains mandatory.'
        gate_path.write_text(json.dumps(minimal, indent=2) + '\n')
        failed = {'paragraph3_names_company'}
        decision = plan('COVER_MECHANICAL', owner='careerops_repair_cover_candidate.py')
        report.update(decision, source_gate=str(original_gate_path), identity_dependency_only=True)
        backup = cover.with_name(cover.stem + '.pre_canonical_identity.json')
        if not backup.exists():backup.write_bytes(cover.read_bytes())
    if decision['route'] == 'DETERMINISTIC_REPAIR' and failed <= MECHANICAL_COVER:
        script = ROOT / 'scripts/careerops_repair_cover_candidate.py'
        if hashlib.sha256(script.read_bytes()).hexdigest() != AUDITED[script.name]:
            raise RuntimeError('AUDITED_COVER_REPAIR_HASH_CHANGED')
        before = json.loads(cover.read_text())
        result = subprocess.run([sys.executable, str(script), '--cover', str(cover), '--plan', str(plan_path), '--report', str(gate_path)], capture_output=True, text=True)
        after = json.loads(cover.read_text())
        preserved = all((before.get(k) == after.get(k) for k in ['company', 'position', 'signature', 'primary_evidence_ids', 'secondary_evidence_ids', 'numerical_anchors']))
        report.update(repair_return_code=result.returncode, protected_claim_fields_preserved=preserved, repair_output=result.stdout)
        if result.returncode == 0 and preserved:
            report['status'] = 'REPAIRED_PENDING_ORIGINAL_GATE'
            result_code = 0
    elif decision['route'] == 'LOCAL_QWEN':
        report['status'] = 'SEMANTIC_CHALLENGE_REQUIRED'
    (cover.parent / 'deterministic_repair_dispatch.json').write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'])
    return result_code

if __name__=="__main__":
    raise SystemExit(main())
