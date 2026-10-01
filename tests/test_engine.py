"""Offline synthetic contracts: source authority, constraints, provenance and release."""
import ast, copy, json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
os.environ["CAREEROPS_SOURCE_DIR"]="examples/source"
os.environ["CAREEROPS_RUNTIME_DIR"]=str(ROOT/".local-checks/unit-runtime")
from careerops_config import candidate_identity, experience_blocks, source_dir
from careerops_constraint_logic import tool_tenure_logic, evaluate_tool_tenure, education_field_support
from careerops_requirement_qualifiers import qualifier_contract, qualifier_supported
from careerops_effective_requirements import build_effective_view
from careerops_evidence_boundaries import entity_boundary_errors
from careerops_temporal_truth import completed_deliverable_errors
from careerops_local_truth_gate import numeric_atoms, numbers_supported, terms_supported
from careerops_semantic_arbitration import choose_route
from careerops_run_outcome import build_outcome
from careerops_daily_output import publish_validated_result
from careerops_skills_stack import concept, category_for, curate_stack, audit_stack
from careerops_writer_accounting import prepare, invoke
from careerops_contact_identity import link_target
from careerops_detect_ats import detect, get_behavior_profile, VALID_PLATFORMS
from careerops_failure_classifier import classify_failure

class EngineTests(unittest.TestCase):
    def test_identity_comes_from_explicit_authority(self):
        self.assertEqual(candidate_identity(ROOT)["name"],"Morgan Vale")
        self.assertEqual(len(experience_blocks(ROOT)),2)
    def test_missing_authority_fails_closed(self):
        with patch.dict(os.environ,{"CAREEROPS_SOURCE_DIR":"candidate/missing"}):
            with self.assertRaises(RuntimeError):candidate_identity(ROOT)
    def test_source_default_has_no_external_fallback(self):
        with patch.dict(os.environ,{},clear=True):self.assertEqual(source_dir(ROOT),ROOT/"candidate/source")
    def test_tool_or_accepts_one_verified_branch(self):
        logic=tool_tenure_logic("Two years SQL or Python",["SQL","Python"],{})
        self.assertEqual(evaluate_tool_tenure(logic,[{"skill":"SQL","status":"PASS"}]),"PASS")
    def test_tool_and_requires_both(self):
        logic=tool_tenure_logic("Two years SQL and Python",["SQL","Python"],{})
        self.assertEqual(evaluate_tool_tenure(logic,[{"skill":"SQL","status":"PASS"}]),"REVIEW_REQUIRED")
    def test_optional_tool_is_not_tenure_requirement(self):
        logic=tool_tenure_logic("Two years SQL; preferably Python",["SQL","Python"],{})
        self.assertEqual(logic["mandatory_skills"],["SQL"])
    def test_education_degree_and_field_same_record(self):
        facts={"education":[{"degree_level":"bachelor","degree":"Mathematics"},{"degree_level":"master","degree":"History"}]}
        self.assertEqual(education_field_support("Master degree in mathematics",facts,2)["status"],"REVIEW_REQUIRED")
    def test_explicit_related_field_is_supported(self):
        facts={"education":[{"degree_level":"bachelor","degree":"Applied Mathematics"}]}
        self.assertEqual(education_field_support("Bachelor degree in statistics or related field",facts,1)["status"],"PASS")
    def test_domain_qualifier_cannot_be_generic_analytics(self):
        q=qualifier_contract("Experience in insurance required")[0]
        self.assertFalse(qualifier_supported(q,"Built a museum analytics dashboard"))
    def test_domain_qualifier_accepts_owner_evidence(self):
        q=qualifier_contract("Experience in insurance required")[0]
        self.assertTrue(qualifier_supported(q,"Insurance policy reconciliation"))
    def test_preferred_domain_is_not_mandatory(self):
        self.assertEqual(qualifier_contract("SQL required; preferably insurance experience"),[])
    def test_semantic_annotation_cannot_disable_p0(self):
        ledger={"requirements":[{"requirement_id":"REQ-001","priority":"P0","exact_quote":"SQL required"}]}
        result=build_effective_view(ledger,{"annotations":[{"requirement_id":"REQ-001","active_for_decision":False}]})
        encoded=json.dumps(result)
        self.assertIn('"active_for_decision": true',encoded)
        self.assertIn('"effective_priority": "P0"',encoded)
    def test_semantic_annotation_mismatch_is_reported(self):
        result=build_effective_view({"requirements":[{"requirement_id":"REQ-001","priority":"P1"}]},{"annotations":[]})
        self.assertIn("ANNOTATION_COUNT_MISMATCH",json.dumps(result))
    def test_private_project_employment_boundary_is_configured(self):
        facts={"entity_claim_boundaries":{"PRJ-101":{"not_employment_at":["Example Vendor"]}}}
        self.assertTrue(entity_boundary_errors("Worked at Example Vendor","PRJ-101",facts))
    def test_unrelated_entity_cannot_inherit_boundary(self):
        facts={"entity_claim_boundaries":{"PRJ-101":{"not_employment_at":["Example Vendor"]}}}
        self.assertEqual(entity_boundary_errors("Worked at Example Vendor","PRJ-102",facts),[])
    def test_model_threshold_attribution_is_owner_bound(self):
        facts={"entity_claim_boundaries":{"PRJ-101":{"forbidden_model_thresholds":{"random forest":[0.61]},"threshold_models":["logistic regression"]}}}
        self.assertTrue(entity_boundary_errors("Random forest threshold 0.61","PRJ-101",facts))
        self.assertEqual(entity_boundary_errors("Random forest compared; logistic regression threshold 0.61","PRJ-101",facts),[])
    def test_completed_deliverable_not_current_work(self):
        facts={"deliverable_state_authority":{"EXP-101":{"deliverable_state":"BUILT_AND_VALIDATED","match_terms":["attendance"]}}}
        self.assertTrue(completed_deliverable_errors("I am building attendance reporting",["EXP-101"],facts))
        self.assertEqual(completed_deliverable_errors("Built attendance reporting",["EXP-101"],facts),[])
    def test_unowned_deliverable_state_does_not_transfer(self):
        facts={"deliverable_state_authority":{"EXP-101":{"deliverable_state":"BUILT_AND_VALIDATED","match_terms":["attendance"]}}}
        self.assertEqual(completed_deliverable_errors("I am building attendance reporting",["EXP-102"],facts),[])
    def test_unsupported_numbers_are_rejected(self):
        supported,missing=numbers_supported("Processed 77,000 records","Processed 240,000 records")
        self.assertTrue(missing)
    def test_supported_numeric_compaction(self):
        supported,missing=numbers_supported("Processed 240K records","Processed 240,000 records")
        self.assertFalse(missing)
    def test_tool_does_not_transfer_between_sources(self):
        supported,missing=terms_supported("Built a DuckDB pipeline","Built a SQL Server pipeline")
        self.assertIn("DuckDB",missing)
    def test_excel_category(self):self.assertEqual(category_for("Excel"),"BI & Spreadsheet Analytics")
    def test_aliases_are_concepts(self):
        self.assertEqual(concept("ML"),concept("Machine Learning"))
        self.assertEqual(concept("Power BI Reporting"),concept("Power BI"))
    def test_skills_stay_within_confirmed_inventory(self):
        coverage=json.loads((ROOT/"examples/source/assumed_market_coverage.json").read_text())
        plan=curate_stack(coverage,[],{"requirements":[{"priority":"P1","exact_quote":"SQL Python Power BI Excel Kubernetes","exact_tools_technologies":["SQL","Python","Power BI","Excel","Kubernetes"]}]},{},coverage["role_coverage_profiles"][0])
        terms=[x for line in plan["visible_skill_lines"] for x in line["terms"]]
        self.assertNotIn("Kubernetes",terms)
        self.assertGreater(len(terms),12)
        self.assertEqual(len(terms),len(set(concept(x) for x in terms)))
    def test_sparse_parent_echo_is_detected(self):
        result=audit_stack([{"category":"Machine Learning","terms":["Machine Learning"]}])
        self.assertEqual(result["gate"],"FAIL"); self.assertTrue(result["findings"])
    def test_nonsemantic_failure_does_not_request_model(self):
        self.assertEqual(choose_route("MECHANICAL"),"DETERMINISTIC_REPAIR")
        self.assertEqual(choose_route("HARD_CONFLICT"),"STOP_HARD_CONFLICT")
    def test_writer_budget_blocks_unapproved_second_attempt(self):
        with tempfile.TemporaryDirectory(dir=ROOT/".local-checks") as td:
            r=Path(td);prepare(r);(r/"writer_invocation_state.json").write_text(json.dumps({"transport_started":True,"writer_calls":1}))
            with self.assertRaises(RuntimeError):prepare(r)
    def test_mocked_writer_is_durably_counted(self):
        with tempfile.TemporaryDirectory(dir=ROOT/".local-checks") as td:
            r=Path(td);state=prepare(r)
            class Process:
                pid=123
                def wait(self):return 0
            with patch("careerops_writer_accounting.subprocess.Popen",return_value=Process()) as transport:
                self.assertEqual(invoke(r,state,["mock-writer","-m","mock-model"],cwd=r,env={}),0)
            receipt=json.loads((r/"writer_invocation_state.json").read_text())
            self.assertEqual(receipt["writer_calls"],1);self.assertTrue(receipt["transport_completed"]);transport.assert_called_once()
    def test_manifest_alone_cannot_release(self):
        outcome=build_outcome("example",{"lifecycle_status":"RELEASE_READY"},{},{},{},{},{})
        self.assertFalse(outcome["release_ready"])
    def test_gate_alone_cannot_release(self):
        outcome=build_outcome("example",{}, {}, {}, {"release_ready":True},{},{})
        self.assertFalse(outcome["release_ready"])
    def test_consistent_release_evidence(self):
        manifest={"lifecycle_status":"RELEASE_READY","stages":{"release":{"status":"PASS"}}}
        outcome=build_outcome("example",manifest,{},{},{"release_ready":True},{},{})
        self.assertTrue(outcome["release_ready"])
    def test_override_never_becomes_automatic_release(self):
        manifest={"lifecycle_status":"RELEASE_READY","stages":{"release":{"status":"PASS"}}}
        outcome=build_outcome("example",manifest,{},{},{"release_ready":True},{},{"user_reason":"Synthetic test"},override_valid=True)
        self.assertFalse(outcome["release_ready"]);self.assertFalse(outcome["override_is_release"])
    def test_daily_output_does_not_trust_forged_ready(self):
        with tempfile.TemporaryDirectory(dir=ROOT/".local-checks") as td:
            result=publish_validated_result({"status":"RELEASE_READY","run_id":"forged"},root=td)
            self.assertEqual(result["status"],"NOT_ELIGIBLE")
            self.assertFalse((Path(td)/"Daily Output").exists())
    def test_contact_targets_preserve_exact_url(self):
        self.assertEqual(link_target({"url":"https://example.invalid/morgan","display":"GitHub"}),"https://example.invalid/morgan")
        self.assertEqual(link_target("javascript:bad"),"")
    def test_unknown_ats_uses_conservative_profile(self):
        self.assertEqual(get_behavior_profile("unknown")["profile_source"],"UNKNOWN_FALLBACK")
        self.assertEqual(len(VALID_PLATFORMS),50)
    def test_classifier_does_not_grant_automatic_writer_retry(self):
        result=classify_failure(stage="ingest",message="Missing complete source text",return_code=1)
        self.assertFalse(result.get("automatic_writer_retry",False))
    def test_public_source_compiles(self):
        for p in (ROOT/"scripts").glob("*.py"):ast.parse(p.read_text(),filename=p.name)

if __name__=="__main__":unittest.main()
