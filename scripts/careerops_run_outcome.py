"""Structured outcome presentation over existing decision and release authority.
No eligibility decision, model call, writer retry, or publication is made here.
"""
from __future__ import annotations
import hashlib,json,re,datetime,uuid
from pathlib import Path
from careerops_run_manifest import atomic_write_json
ROOT=Path(__file__).resolve().parents[1]
STAGE_ORDER=['ingest','requirements','requirement_integrity','routing','semantics','entities','evidence_map','constraints','constraint_validation','experience_selection','project_selection','skills','summary','pair_packet','writer','deep_truth_gate','local_truth_gate','ats_gate','human_gate','cover_gate','interview_defensibility','resume_payload','resume_render','cover_render','cover_roundtrip','final_application_audit','release']
OWNERS={'routing':'ROUTING','semantics':'SEMANTIC_MAP','entities':'ENTITY_RESOLUTION','evidence_map':'EVIDENCE_MAPPING','experience_selection':'EXPERIENCE_SELECTION','project_selection':'PROJECT_SELECTION','skills':'SKILLS_PLANNING','summary':'SUMMARY_ROUTING','pair_packet':'PAIR_PACKET','ingest':'SOURCE_INGESTION','requirements':'REQUIREMENT_EXTRACTION','requirement_integrity':'REQUIREMENT_INTEGRITY','constraints':'CONSTRAINT_VALIDATOR','constraint_validation':'CONSTRAINT_VALIDATOR','local_truth_gate':'TRUTH_GATE','deep_truth_gate':'TRUTH_GATE','ats_gate':'ATS_GATE','human_gate':'HUMAN_GATE','interview_defensibility':'INTERVIEW_DEFENSIBILITY','cover_gate':'COVER_GATE','writer':'PAIR_WRITER','render':'RENDERER','resume_render':'RESUME_RENDERER','cover_render':'COVER_RENDERER','resume_payload':'PAYLOAD_VALIDATOR','cover_roundtrip':'ROUNDTRIP_VALIDATOR','final_application_audit':'FINAL_AUDIT','release':'RELEASE_GATE'}

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path):
    if not path.is_file():return {}
    value=json.loads(path.read_text())
    if not isinstance(value,dict):raise ValueError('Expected structured object: '+str(path))
    return value

def input_outcome(resolution,reason,*,identity_conflict=False):
    status='SOURCE_IDENTITY_MISMATCH' if identity_conflict or resolution=='SOURCE_IDENTITY_MISMATCH' else 'NEEDS_JOB_IDENTITY' if resolution=='NEEDS_JOB_IDENTITY' else 'NEEDS_MANUAL_JD'
    return {'schema_version':'career-ops-run-outcome-v1','status':status,'owner':'SOURCE_IDENTITY' if status in {'SOURCE_IDENTITY_MISMATCH','NEEDS_JOB_IDENTITY'} else 'SOURCE_INGESTION','reason':reason or 'A usable current job description was not established.','success':False,'release_ready':False,'may_publish':False,'process_rc':None,'process_success':False,'writer_calls':0,'model_calls':0,'next_action':'Supply the correct current-requisition identity and raw JD.'}

def emit_input_outcome(resolution,reason,*,identity_conflict=False,root=ROOT,metadata=None):
    result=input_outcome(resolution,reason,identity_conflict=identity_conflict)
    path=Path(root)/"data/careerops-engine/intake_outcomes"/("intake_"+uuid.uuid4().hex+".json")
    result.update(metadata=metadata or {},outcome_path=str(path))
    atomic_write_json(path,result);print_outcome(result,root=root);return result

def owner_for(stage,failure):
    route=failure.get('repair_dispatch',{}).get('route')
    if route in {'HARNESS_REPAIR','RENDERER_REPAIR','VALIDATOR_REPAIR'}:return {'HARNESS_REPAIR':'HARNESS','RENDERER_REPAIR':'RENDERER','VALIDATOR_REPAIR':'VALIDATOR'}[route]
    return OWNERS.get(stage) or failure.get('failure_class') or 'ORCHESTRATOR'

def build_outcome(run_id,manifest,receipt,failure,release,intake,override,*,process_rc=None,override_valid=False,error=None):
    stages=manifest.get('stages',{});execution=manifest.get('execution',{});decision=receipt.get('decision')
    failed=sorted([stage for stage,row in stages.items() if row.get('status') in {'FAIL','BLOCKED'}],key=lambda s:STAGE_ORDER.index(s) if s in STAGE_ORDER else len(STAGE_ORDER))
    latest_failure_stage=failure.get('normalized_stage') or failure.get('stage')
    stage=failed[0] if failed else latest_failure_stage or manifest.get('resumable_from')
    current_failure=failure if latest_failure_stage==stage else {}
    owner=owner_for(stage,current_failure);details=receipt.get('requirements',[])
    reason=(current_failure.get('detail') or current_failure.get('message') or stages.get(stage,{}).get('detail') or error)
    blockers=[{'stage':s,'owner':owner_for(s,failure if s==latest_failure_stage else {}),'reason':stages[s].get('detail')} for s in failed]
    diagnostic_failures=[failure] if failure and latest_failure_stage!=stage else []
    ready=(manifest.get('lifecycle_status')=='RELEASE_READY' and stages.get('release',{}).get('status')=='PASS' and release.get('release_ready') is True and not failed)
    if intake.get('status')=='SOURCE_IDENTITY_MISMATCH':
        status='SOURCE_IDENTITY_MISMATCH';owner='SOURCE_IDENTITY';reason=intake.get('reason') or intake.get('instruction') or 'Source identity conflicts with the current requisition.'
    elif intake.get('status') in {'NEEDS_MANUAL_JD','MANUAL_REQUIRED'}:
        status='NEEDS_MANUAL_JD';owner='SOURCE_INGESTION';reason=intake.get('instruction') or intake.get('reason') or intake.get('fetch_error')
    elif override:
        ready=False
        if override_valid:
            status='USER_OVERRIDE_GENERATED';owner='EXPLICIT_USER_OVERRIDE';reason=override.get('user_reason')
        else:status='NEEDS_ATTENTION';owner='OVERRIDE_VALIDATOR';reason='Override evidence is incomplete, stale, or crosses the normal release boundary.'
    elif decision=='REJECTED':
        status='REJECTED';ready=False;owner='CONSTRAINT_VALIDATOR';reason=receipt.get('reason')
    elif decision=='NEEDS_ATTENTION' or failed or process_rc not in {None,0}:
        status='NEEDS_ATTENTION';ready=False
        reason=reason or receipt.get('reason') or 'Execution stopped before a structured stage reason was recorded.'
    elif ready:
        status='RELEASE_READY';owner='RELEASE_GATE';reason='The original release gate approved the exact run artifacts.'
    elif manifest.get('lifecycle_status')=='RELEASE_READY' or release.get('release_ready') is True:
        status='NEEDS_ATTENTION';ready=False;owner='RELEASE_GATE';reason='Manifest and release evidence disagree; output is not reported as released.'
    else:
        status='CANDIDATE_GENERATED' if stages.get('writer',{}).get('status')=='PASS' else 'IN_PROGRESS'
        reason='Requested pipeline boundary reached; release has not been approved.';owner=owner or 'ORCHESTRATOR'
    return {'schema_version':'career-ops-run-outcome-v1','run_id':run_id,'status':status,'owner':owner,'reason':reason or 'Required source evidence is unavailable.','failing_stage':stage if failed or status=='NEEDS_ATTENTION' else None,
      'first_release_blocker':blockers[0] if blockers else {'stage':stage,'owner':owner,'reason':reason} if status in {'NEEDS_ATTENTION','REJECTED'} else None,
      'current_owner':blockers[0]['owner'] if blockers else owner,
      'all_release_blockers':blockers,
      'resumable_from':failed[0] if failed else manifest.get('resumable_from'),
      'diagnostic_failures':diagnostic_failures,
      'original_automated_decision':receipt,'automatic_lifecycle_status':manifest.get('lifecycle_status'),'requirements':details,'failure_class':failure.get('failure_class'),'repair_dispatch':failure.get('repair_dispatch'),
      'override_generated':status=='USER_OVERRIDE_GENERATED','override_is_release':False,'release_ready':ready,'may_publish':False,
      'process_rc':process_rc,'process_success':process_rc==0,'success':process_rc==0 and status in {'RELEASE_READY','IN_PROGRESS','CANDIDATE_GENERATED','USER_OVERRIDE_GENERATED'},
      'automatic_writer_calls':execution.get('writer_calls',0),'override_additional_writer_calls':override.get('additional_writer_calls',0) if override_valid else 0,'writer_calls':execution.get('writer_calls',0)+(override.get('additional_writer_calls',0) if override_valid else 0),'truth_audit_calls':execution.get('truth_audit_calls',0),'model_calls':execution.get('model_calls',0)+(override.get('additional_writer_calls',0) if override_valid else 0),
      'next_action':'Use released artifacts.' if ready else 'Review isolated unreleased artifacts; original automated decision remains preserved.' if status=='USER_OVERRIDE_GENERATED' else 'Resolve the reported owner issue and rerun its deterministic gate.' if status=='NEEDS_ATTENTION' else 'Review the explicit mandatory conflict.' if status=='REJECTED' else 'Complete the remaining pipeline stages.'}

def valid_override(report,run_id,run_root,manifest_path):
    if report.get('status')!='USER_OVERRIDE_GENERATED' or report.get('run_id')!=run_id or report.get('authority')!='EXPLICIT_USER':return False
    if report.get('automatic_engine_decision_preserved') is not True or report.get('release_ready') is not False or report.get('root_publish_authorized') is not False or report.get('normal_release_gate_invoked') is not False:return False
    if report.get('original_decision_receipt')!=load(run_root/'runtime/job_decision_receipt.json'):return False
    if report.get('automatic_manifest_sha256')!=digest(manifest_path):return False
    execution=load(manifest_path).get("execution",{})
    generation_root=run_root
    if report.get('generation_run_id'):
        child_name=report['generation_run_id']
        if not re.fullmatch(r'[A-Za-z0-9_-]+',str(child_name)):return False
        child=run_root.parent/child_name;child_manifest=load(child/'manifest.json')
        if child_manifest.get('automatic_parent_run')!=run_id or child_manifest.get('overall_override_only') is not True:return False
        if child_manifest.get('lifecycle_status')=='RELEASE_READY' or child_manifest.get('stages',{}).get('release',{}).get('status')=='PASS':return False
        generation_root=child
        additional=report.get('additional_writer_calls')
        if (execution.get('writer_calls'),additional) not in {(0,1),(1,0)}:return False
        execution=child_manifest.get('execution',{})
        if digest(child/'runtime/jd_intake.json')!=digest(run_root/'runtime/jd_intake.json'):return False
        if additional==0:
            if digest(child/'runtime/jd_requirements.json')!=digest(run_root/'runtime/jd_requirements.json'):return False
        else:
            from careerops_overall_override import quarantine_authorized
            if not quarantine_authorized(child/'runtime',digest(child/'runtime/jd_intake.json'),digest(child/'runtime/jd_requirements.json')):return False
        for value,h in report.get('automatic_source_hashes',{}).items():
            p=Path(value)
            if not p.resolve().is_relative_to(run_root.resolve()) or not p.is_file() or digest(p)!=h:return False
        for filename in ['local_truth_gate.json','truth_gate.json']:
            if load(child/'runtime'/filename).get('gate')!='PASS':return False
    authorization=load(generation_root/'runtime/user_generation_override_authorization.json')
    retry_pair=(execution.get('writer_calls')==2 and authorization.get('mode') in {'EXPLICIT_FAILED_TRANSPORT_ONE_RETRY_ALLOWED','POST_WRITER_FAILURE_REUSE_EXISTING_PAIR'} and authorization.get('max_total_writer_calls')==2 and authorization.get('execution_before_override',{}).get('writer_calls') in {1,2} and execution.get('exceptional_writer_retry_calls')==1)
    if execution.get("writer_calls")!=1 and not retry_pair:return False
    writer_sources=report.get("writer_sources",{})
    if set(writer_sources)!={"resume_candidate","cover_candidate"}:return False
    for item in writer_sources.values():
        p=Path(item.get("path",""))
        if not p.is_file() or not p.resolve().is_relative_to((generation_root/"runtime").resolve()) or digest(p)!=item.get("sha256"):return False
    outputs=report.get('outputs',{})
    if set(outputs)!={'resume_pdf','resume_docx','cover_pdf','cover_docx'}:return False
    for item in outputs.values():
        p=Path(item.get('path',''))
        if not p.is_file() or not p.resolve().is_relative_to((generation_root/'output/user_override').resolve()) or digest(p)!=item.get('sha256'):return False
    return True

def resolved_failure_evidence(failure, manifest, runtime):
    """A prior failure is historical only after its exact owner gate is revalidated.

    Preserve the old failure/process receipt, but do not treat its stale mutable
    process-error path as a new error once a newer manifest-bound gate passed.
    """
    stage=failure.get('normalized_stage') or failure.get('stage')
    row=manifest.get('stages',{}).get(stage,{})
    if row.get('status')!='PASS' or not failure.get('recorded_at_utc') or not row.get('updated_at_utc'): return None
    try:
        if datetime.datetime.fromisoformat(row['updated_at_utc'])<=datetime.datetime.fromisoformat(failure['recorded_at_utc']):return None
        path=Path(failure.get('artifact',''))
        if not path.is_absolute():path=ROOT/path
        declared=row.get('artifact',{})
        if not path.is_file() or not path.resolve().is_relative_to(Path(runtime).resolve()) or declared.get('sha256')!=digest(path):return None
        gate=load(path)
        if not (gate.get('gate')=='PASS' or gate.get('status')=='PASS' or gate.get('pass') is True):return None
        return {'status':'RESOLVED_BY_ORIGINAL_GATE_RERUN','stage':stage,'original_failure':failure,'current_gate':{'path':str(path),'sha256':digest(path)},'stage_updated_at_utc':row['updated_at_utc']}
    except (OSError,ValueError,TypeError):return None

def artifact_delivery_command(run_id, artifact_key, *, root=ROOT):
    """Build argv only; authentication, validation and launching belong to delivery."""
    if not re.fullmatch(r"[A-Za-z0-9._-]+", str(run_id)) or str(run_id) in {".", ".."}:
        raise ValueError("Invalid run identity")
    from careerops_artifact_delivery import KEYS
    if artifact_key not in (*KEYS, "folder"):
        raise ValueError("Unknown artifact key")
    root = Path(root).resolve()
    command = [str(root / ".venv/bin/python"), str(root / "scripts/careerops_artifact_delivery.py"), "--run-id", str(run_id)]
    return command + (["--open-folder"] if artifact_key == "folder" else ["--open-file", artifact_key])


def artifact_delivery_actions(result, *, root=ROOT):
    """Keep canonical storage separate from parent-bound delivery operations."""
    import shlex
    delivery = result.get("delivery", {})
    keys = list(delivery.get("files", {}))
    if delivery.get("folder", {}).get("linux_path"):
        keys.append("folder")
    actions = {}
    for key in keys:
        argv = artifact_delivery_command(result["run_id"], key, root=root)
        actions[key] = {"run_id": result["run_id"], "artifact_key": key,
                        "authority": "AUTHENTICATED_ARTIFACT_DELIVERY", "argv": argv,
                        "command": shlex.join(argv), "automatic_open": False}
    return actions


def print_artifact_delivery(result, *, root=ROOT):
    delivery = result.get("delivery", {})
    if not delivery.get("files"):
        return
    print("ARTIFACT PARENT RUN:", result["run_id"])
    print("ARTIFACT DISPOSITION:", delivery["disposition"])
    daily=result.get("daily_output", {})
    if daily.get("status")=="COPIED":
        print("DAILY OUTPUT (FOUR DOCUMENT COPIES):", daily["directory"])
    elif daily.get("status")=="DELIVERY_FAILED":
        print("DAILY OUTPUT DELIVERY FAILED:", daily.get("reason"))
    print("STORAGE REFERENCES (AUDIT ONLY; use the OPEN commands below):")
    for key, item in delivery["files"].items():
        print(key.upper() + " STORAGE:", json.dumps({"artifact_path": item["linux_path"],
              "windows_storage_path": item.get("windows_path")}, ensure_ascii=False))
    # Reconstruct actions from this job's identity; never trust a cached action
    # or a child/canonical path as a launch target.
    for key, action in artifact_delivery_actions(result, root=root).items():
        print("OPEN " + key.replace("_", " ").upper() + ":", action["command"])


def print_batch_artifact_delivery(report, *, root=ROOT):
    for job in report.get("jobs", []):
        print_artifact_delivery(job, root=root)


def emit_run_outcome(run_id,process_rc=None,*,root=ROOT,error=None,print_human=False, export_daily_output=True):
    if not re.fullmatch(r'[A-Za-z0-9._-]+',str(run_id)) or str(run_id) in {'.','..'}:raise ValueError('Invalid run identity')
    root=Path(root);run=root/'data/careerops-engine/runs'/run_id;runtime=run/'runtime';runtime.mkdir(parents=True,exist_ok=True)
    names=['manifest.json','job_decision_receipt.json','failure_classification.json','pair_release_gate_report.json','jd_intake.json','user_override/user_override_generation_report.json']
    paths=[run/names[0]]+[runtime/name for name in names[1:]]
    errors=[];objects=[]
    for p in paths:
        try:objects.append(load(p))
        except (OSError,ValueError) as exc:objects.append({});errors.append(str(exc))
    manifest,receipt,failure,release,intake,override=objects
    if not override and (runtime/"user_generation_override_authorization.json").exists():
        override={"status":"AUTHORIZED_BUT_NOT_GENERATED"}
    existing=load(runtime/'run_outcome.json') if (runtime/'run_outcome.json').is_file() else {}
    if not error and existing.get('process_rc')==process_rc:error=existing.get('execution_error')
    valid=False
    if override and paths[0].is_file():
        try:valid=valid_override(override,run_id,run,paths[0])
        except (OSError,ValueError):valid=False
    if manifest and manifest.get('run_id')!=run_id:errors.append('Cross-run manifest identity');manifest={}
    if failure.get('run_id') and failure['run_id']!=run_id:errors.append('Cross-run failure identity');failure={}
    resolved=resolved_failure_evidence(failure,manifest,runtime)
    if resolved:failure={}
    result=build_outcome(run_id,manifest,receipt,failure,release,intake,override,process_rc=process_rc,override_valid=valid,error=error)
    if resolved:result['resolved_prior_failure']=resolved
    process_evidence=failure.get("process_error_evidence",{})
    if process_evidence and not result.get('release_ready'):
        captured_path=Path(process_evidence.get("path",""))
        if captured_path.is_file() and captured_path.resolve().is_relative_to(runtime.resolve()) and digest(captured_path)==process_evidence.get("sha256"):
            captured=load(captured_path)
            if captured.get("run_id")==run_id:
                tail=captured.get("output_tail","");lines=[x.strip() for x in tail.splitlines() if x.strip()]
                result["process_error"]={"owner_paths":captured.get("owner_paths"),"return_code":captured.get("return_code"),"evidence":process_evidence}
                if lines:result["reason"]+=" Underlying error: "+lines[-1]
                if "UNCLASSIFIED_SOURCE_HARD_BLOCKER" in tail:
                    result["stage_owner"]=result["owner"];result["owner"]="EFFECTIVE_REQUIREMENTS"
                    result["cause_code"]="UNCLASSIFIED_SOURCE_HARD_BLOCKER"
        else:errors.append("Stale process error evidence")
    artifact_value=failure.get("artifact")
    failed_checks=[]
    if artifact_value:
        report_path=Path(artifact_value)
        if not report_path.is_absolute():report_path=root/report_path
        if report_path.resolve().is_relative_to(run.resolve()) and report_path.is_file():
            try:
                gate=load(report_path) if report_path.suffix==".json" else {}
                failed_checks=[k for k,v in gate.get("checks",{}).items() if v is False]+list(gate.get("blocking_findings",[]))+list(gate.get("failed_checks",[]))
            except (OSError,ValueError,AttributeError):errors.append("Invalid current-run failure report")
        else:errors.append("Missing or cross-run failure artifact")
    result["failed_checks"]=list(dict.fromkeys(str(x) for x in failed_checks))
    if result["failed_checks"] and not result.get('release_ready'):result["reason"]+=" Checks: "+", ".join(result["failed_checks"])
    if result.get("release_ready"):
        declared=manifest.get("stages",{}).get("release",{}).get("artifact",{}).get("sha256")
        if declared!=digest(paths[3]):errors.append("Release evidence is not bound to current manifest")

    if errors:
        result['underlying_owner']=result['owner'];result['underlying_reason']=result['reason']
        result.update(status='NEEDS_ATTENTION',owner='OUTCOME_EVIDENCE_VALIDATOR',reason='; '.join(errors),evidence_errors=errors,success=False,release_ready=False)
    result.update(observed_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),execution_error=error,evidence_sha256={str(p):digest(p) for p in paths if p.is_file()},outcome_path=str(runtime/'run_outcome.json'))
    from careerops_artifact_delivery import build_delivery
    result["delivery"] = build_delivery(run, manifest, result, override)
    result["artifact_delivery_actions"] = artifact_delivery_actions(result, root=root)
    if export_daily_output:
        from careerops_daily_output import publish_validated_result
        try:
            result["daily_output"] = publish_validated_result(result, root=root)
        except (OSError, ValueError) as exc:
            # Delivery failure never rewrites release/override authority.
            result["daily_output"] = {"status": "DELIVERY_FAILED", "reason": str(exc),
                                      "authority": "DELIVERY_ONLY", "may_release": False,
                                      "model_calls": 0, "writer_calls": 0}
    atomic_write_json(runtime/'run_outcome.json',result)
    if print_human:print_outcome(result,root=root)
    return result

def print_outcome(result, *, root=ROOT):
    print('\nCAREEROPS OUTCOME:',result['status']);print('OWNER:',result['owner']);print('REASON:',result['reason'])
    for detail in result.get('requirements',[]):
        print('REQUIREMENT:',detail.get('requirement_id'),'|',detail.get('exact_jd_quote'));print('WHY:',detail.get('deterministic_reason'))
    print('NEXT ACTION:',result['next_action']);print('RELEASE READY:', 'YES' if result.get('release_ready') else 'NO')
    print_artifact_delivery(result, root=root)
    if result.get('outcome_path'):print('OUTCOME RECEIPT:',result['outcome_path'])
