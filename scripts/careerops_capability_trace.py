"""Per-run observation only. Evidence presence is not proof of current-code execution.

Invocation events bind the owner hash at launch. Artifact observations retain
manifest provenance. Accounting is separate; shared batch ids must be deduped
across runs. This observer never changes gates, facts, release, or model usage.
"""
from __future__ import annotations
import argparse, datetime, hashlib, json, os, re, sys, uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SPEC={
 'ingestion':('ingest','jd_intake.json','careerops_ingest_jd.py'),
 'requirement_extraction':('requirements','jd_requirements.json','careerops_extract_requirements.py'),
 'requirement_integrity':('requirement_integrity','requirement_integrity_gate.json','careerops_requirement_integrity_gate.py'),
 'role_routing':('routing','role_routing.json','careerops_route_role.py'),
 'semantic_map':('semantics','jd_semantic_map.json','careerops_expand_jd_semantics.py'),
 'evidence_mapping':('evidence_map','requirement_evidence_map.json','careerops_map_evidence.py'),
 'constraint_validation':('constraints','constraint_validation.json','careerops_validate_constraints.py'),
 'experience_planning':('experience_selection','experience_selection.json','careerops_select_experience.py'),
 'project_planning':('project_selection','project_selection.json','careerops_select_projects.py'),
 'skills_planning':('skills','technical_skills_plan.json','careerops_build_skills.py'),
 'writer':('writer','generated_resume_content_pair_candidate.json','careerops_generate_pair.py'),
 'local_truth_gate':('local_truth_gate','local_truth_gate.json','careerops_local_truth_gate.py'),
 'truth_gate':('deep_truth_gate','truth_gate.json','careerops_truth_gate.py'),
 'ats_gate':('ats_gate','ats_gate.json','careerops_ats_gate_v2.py'),
 'human_gate':('human_gate','human_gate.json','careerops_human_gate_v22.py'),
 'cover_gate':('cover_gate','cover_gate_v2_report.json','careerops_cover_gate_v2.py'),
 'renderer':('resume_render',None,'careerops_docx_renderer.py'),
 'cover_renderer':('cover_render',None,'careerops_render_cover_docx.py'),
 'roundtrip':(None,'resume_roundtrip_report.json','careerops_resume_roundtrip.py'),
 'cover_roundtrip':('cover_roundtrip','cover_roundtrip_report.json','careerops_cover_roundtrip.py'),
 'final_audit':('final_application_audit','final_application_audit_report.json','careerops_final_application_audit.py'),
 'release':('release','pair_release_gate_report.json','careerops_pair_release_gate.py'),
}

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(path,errors):
    if not path.exists(): return {}
    try:
        value=json.loads(path.read_text())
        if not isinstance(value,dict): raise ValueError('expected object')
        return value
    except (OSError,ValueError) as error: errors.append({'path':str(path),'error':str(error)});return {}
def atomic(path,data):
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp');temp.write_text(json.dumps(data,indent=2)+'\n');temp.replace(path)
def valid_run(run_id):
    if not re.fullmatch(r'[A-Za-z0-9_-]+',str(run_id)): raise ValueError('INVALID_RUN_ID')
    return run_id
def artifact(path):
    return {'path':str(path),'exists':path.exists(),'sha256':sha(path) if path.is_file() else None}
def events_from(runtime,errors):
    path=runtime/'capability_invocations.jsonl';rows=[]
    if path.exists():
        for number,line in enumerate(path.read_text().splitlines(),1):
            try:
                row=json.loads(line)
                if row.get('run_id')!=runtime.parent.name: raise ValueError('CROSS_RUN_EVENT')
                rows.append(row)
            except (ValueError,AttributeError) as error: errors.append({'path':str(path),'line':number,'error':str(error)})
    return rows

def build_trace(runtime, *, root=ROOT, env=None):
    runtime=Path(runtime);root=Path(root);run_id=valid_run(runtime.parent.name);errors=[];env=dict(env or {})
    config_path=root/'examples/local-intelligence/config/runtime.json'
    config=read(config_path,errors) if config_path.is_file() else {}
    normal=config.get('normal_production',{})
    for key,name in [('CAREEROPS_SEMANTIC_CHALLENGER','semantic_challenger'),('CAREEROPS_INTERVIEW_DEFENSIBILITY','interview_defensibility'),('CAREEROPS_SHARED_SOL_SEMANTIC','shared_sol_semantic')]:
        env.setdefault(key,'1' if normal.get(name) is True else '0')
    manifest=read(runtime.parent/'manifest.json',errors)
    if manifest and manifest.get('run_id')!=run_id: errors.append({'error':'CROSS_RUN_MANIFEST'});manifest={}
    events=events_from(runtime,errors);caps={};stages=manifest.get('stages',{})
    def observe(name,filename,owner,stage=None):
        path=runtime/filename if filename else None;data=read(path,errors) if path else {}
        entry=stages.get(stage,{}) if stage else {};state=entry.get('status','OBSERVED' if data else 'NOT_RUN')
        if path and not path.exists() and state in {'PASS','FAIL'}: state='UNVERIFIED_MANIFEST_STATUS'
        recorded=entry.get('artifact',{}).get('sha256')
        if path and recorded and path.exists() and recorded!=sha(path): state='STALE_MANIFEST_EVIDENCE'
        declared=list(entry.get('artifacts',{}).values()) if isinstance(entry.get('artifacts'),dict) else []
        for item in declared:
            if not isinstance(item,dict) or not item.get('path'): continue
            declared_path=Path(item['path']);declared_path=declared_path if declared_path.is_absolute() else root/declared_path
            if not declared_path.resolve().is_relative_to(runtime.parent.resolve()):
                state='CROSS_RUN_ARTIFACT_REFERENCE';continue
            if item.get('exists') and (not declared_path.is_file() or (item.get('sha256') and sha(declared_path)!=item['sha256'])):
                state='STALE_MANIFEST_EVIDENCE'
        if not stage and data.get('gate',data.get('status')) in {'PASS','FAIL'}: state=data.get('gate',data.get('status'))
        owner_path=root/'scripts'/owner
        matching=[x for x in events if x.get('owner_path')==str(owner_path)]
        if matching and matching[-1].get('phase')=='STARTED': state='RUNNING'
        return {'state':state,'owner':artifact(owner_path),'artifact':artifact(path) if path else None,
          'observation_kind':'OWNER_INVOCATION_RECORDED' if matching else 'ARTIFACT_EVIDENCE_ONLY' if data or entry else 'AVAILABLE_NOT_USED',
          'invocations':[{'invocation_id':x['invocation_id'],'phase':x['phase'],'owner_sha256':x.get('owner_sha256'),'return_code':x.get('return_code')} for x in matching]}
    for name,(stage,file,owner) in SPEC.items(): caps[name]=observe(name,file,owner,stage)
    intake=read(runtime/'jd_intake.json',errors);ats=intake.get('ats',{});raw=intake.get('raw_jd_text')
    caps['ats_detection_profile']={'state':'OBSERVED' if ats.get('platform') else 'NOT_RUN','platform':ats.get('platform'),'confidence':ats.get('confidence'),'behavior_family':ats.get('behavior_family'),'evidence':artifact(runtime/'jd_intake.json')}
    identity=intake.get('identity_evidence')
    caps['source_identity']={'state':'OBSERVED' if identity else 'NOT_RUN','raw_source_sha256':hashlib.sha256(raw.encode()).hexdigest() if isinstance(raw,str) else None,'identity_evidence':identity,'evidence':artifact(runtime/'jd_intake.json')}
    caps['semantic_sidecar']=observe('semantic_sidecar','jd_semantic_sidecar.json','careerops_semantic_sidecar.py')
    caps['effective_view']=observe('effective_view','effective_requirements.json','careerops_effective_runtime.py')
    skills=read(runtime/'technical_skills_plan.json',errors);ranked=skills.get('ranked_skill_candidates',[])
    for name,signal in [('market_prior','ROUTED_ROLE_MARKET_PRIOR'),('candidate_proficiency','DIRECT_USER_CONFIRMED_PROFICIENCY')]:
        terms=[x.get('term') for x in ranked if signal in x.get('provenance',[])]
        caps[name]={'state':'OBSERVED_IN_SKILLS_PLAN' if terms else 'AVAILABLE_NOT_USED','terms':terms,'candidate_evidence_authority':name=='candidate_proficiency','plan_evidence':artifact(runtime/'technical_skills_plan.json')}
    q=read(runtime/'semantic_challenger_report.json',errors);ad=read(runtime/'li_advisory_report.json',errors);counts=q.get('model_accounting',{})
    def count(value,label):
        if not isinstance(value,int) or isinstance(value,bool) or value<0:
            errors.append({'error':'INVALID_MODEL_ACCOUNTING','counter':label});return 0
        return value
    if q and q.get('run_id')!=run_id:
        errors.append({'error':'CROSS_RUN_QWEN_REPORT'});q={};counts={}
    if ad and ad.get('run_id')!=run_id:
        errors.append({'error':'CROSS_RUN_ADVISORY_REPORT'});ad={}
    qa=count(counts.get('qwen_attempted',0),'qwen_attempted');qc=count(counts.get('qwen_completed',0),'qwen_completed')
    advisory=count(ad.get('local_model_calls',0),'advisory_calls')
    # The semantic runtime writes the compatible advisory envelope for the same call.
    qa=max(qa,advisory);qc=max(qc,advisory if ad.get('status')=='AVAILABLE' else 0)
    cover_review=read(runtime/'cover_semantic_challenger_report.json',errors)
    if cover_review:
        if cover_review.get('run_id')!=run_id:
            errors.append({'error':'CROSS_RUN_COVER_QWEN_REPORT'})
        else:
            qa+=count(cover_review.get('qwen_attempted',0),'cover_qwen_attempted')
            qc+=count(cover_review.get('qwen_completed',0),'cover_qwen_completed')
            caps['cover_semantic_challenger']={'state':cover_review.get('status'),'owner':artifact(root/'scripts/careerops_cover_semantic_challenger.py'),'artifact':artifact(runtime/'cover_semantic_challenger_report.json'),'may_release':False}

    caps['qwen']=observe('qwen','semantic_challenger_report.json','careerops_semantic_challenger_runtime.py')
    caps['qwen'].update(state=q.get('status') or ('UNAVAILABLE_FAIL_OPEN' if ad.get('status') in {'SHADOW_UNAVAILABLE','SHADOW_INVALID'} else 'CALLED_ONCE_ADVISORY_ONLY' if advisory==1 else 'AVAILABLE_GUARDED_NOT_ENABLED' if str(env.get('CAREEROPS_SEMANTIC_CHALLENGER','')).strip().casefold() not in {'1','true','yes','on'} else 'NOT_NEEDED'),semantic_guard_enabled=str(env.get('CAREEROPS_SEMANTIC_CHALLENGER','')).strip().casefold() in {'1','true','yes','on'},advisory_evidence=artifact(runtime/'li_advisory_report.json'))
    receipts=[]
    for path in sorted(runtime.glob('shared_sol_receipt_*.json')):
        receipt=read(path,errors)
        if receipt.get('run_id')!=run_id or not receipt.get('batch_id'):errors.append({'error':'CROSS_RUN_OR_INVALID_SHARED_RECEIPT','path':str(path)});continue
        report_path=Path(receipt.get('report_path',''))
        if receipt.get('report_sha256') and (not report_path.is_file() or sha(report_path)!=receipt['report_sha256']):errors.append({'error':'STALE_SHARED_BATCH_REPORT','path':str(path)})
        receipts.append(receipt)
    bybatch={x['batch_id']:x for x in receipts};sol=sum(count(x.get('sol_semantic_adjudication_calls',0),'shared_batch_calls') for x in bybatch.values())
    cover_cloud=read(runtime/'cover_semantic_challenger_report.json',errors)
    sol+=count(cover_cloud.get('shared_sol_attempted',0),'cover_shared_sol_calls')
    needs_shared=q.get('case',{}).get('route')=='SHARED_SOL_ADJUDICATION'
    caps['shared_sol_adjudicator']={'state':'CALLED_ONCE_SHARED_BATCH' if sol==1 else 'CALLED_SHARED_BATCHES' if sol>1 else 'PENDING_SHARED_BATCH' if needs_shared else 'AVAILABLE_AUTOMATIC_NOT_NEEDED' if env.get('CAREEROPS_SHARED_SOL_SEMANTIC')=='1' else 'AVAILABLE_EXPLICIT_BATCH_NOT_INVOKED',
      'owner':artifact(root/'scripts/careerops_shared_semantic_adjudicator.py'),'automatic_per_job_sol':False,'automatic_escalation_enabled':env.get('CAREEROPS_SHARED_SOL_SEMANTIC')=='1','batch_ids':sorted(bybatch),'receipts':receipts,'batch_accounting_policy':'dedupe batch_id across runs; one shared call attributed to each member, never sum members blindly'}
    caps['deterministic_repair_dispatcher']=observe('deterministic_repair_dispatcher','deterministic_repair_dispatch.json','careerops_deterministic_repair_dispatcher.py')
    classification=read(runtime/'failure_classification.json',errors)
    caps['deterministic_repair_dispatcher']['routing_plan_observed']=classification.get('repair_dispatch')
    caps['interview_defensibility']=observe('interview_defensibility','interview_defensibility_report.json','careerops_interview_defensibility.py')
    interview=read(runtime/'interview_defensibility_report.json',errors)
    if interview:
        bindings=interview.get('input_sha256',{})
        if not bindings or any(not Path(p).is_file() or sha(p)!=h for p,h in bindings.items()): caps['interview_defensibility']['state']='STALE_OR_UNBOUND_INTERVIEW_REPORT'
    elif env.get('CAREEROPS_INTERVIEW_DEFENSIBILITY')!='1': caps['interview_defensibility']['state']='AVAILABLE_GUARDED_NOT_ENABLED'
    caps['interview_defensibility']['guard_enabled']=env.get('CAREEROPS_INTERVIEW_DEFENSIBILITY')=='1'
    execution=manifest.get('execution',{});writer=count(execution.get('writer_calls',0),'writer_calls')
    if writer is None: writer=0
    retries=count(execution.get('exceptional_writer_retry_calls',0),'exceptional_writer_retry_calls')
    accounting={'qwen_attempted':qa,'qwen_completed':qc,'sol_semantic_adjudication_calls':sol,'sol_writer_calls':max(0,writer-retries),'exceptional_writer_retry_calls':retries,
      'other_truth_audit_calls':execution.get('truth_audit_calls',0),'writer_count_evidence':'canonical_manifest' if 'writer_calls' in execution else 'no_recorded_writer_call','unclassified_repeat_writer_calls':max(0,writer-1-retries)}
    if any(not isinstance(v,int) or isinstance(v,bool) or v<0 for v in [qa,qc,sol,writer,retries]) or qc>qa: errors.append({'error':'INVALID_MODEL_ACCOUNTING'})
    return {'schema_version':'career-ops-capability-trace-v1','run_id':run_id,'observed_at_utc':now(),'trace_status':'COMPLETE_OBSERVATION' if not errors else 'OBSERVATION_ERRORS',
      'authority':'OBSERVER_ONLY','may_release':False,'may_create_candidate_facts':False,'candidate_components_promoted':False,
      'capabilities':caps,'model_accounting':accounting,'observation_errors':errors,
      'manifest_evidence':artifact(runtime.parent/'manifest.json'),'observer_owner':artifact(root/'scripts/careerops_capability_trace.py'),
      'event_evidence':artifact(runtime/'capability_invocations.jsonl'),'limits':'Artifact presence alone does not prove current-code execution or consumption. Runtime status never grants release authority.'}

def emit_trace(runtime,*,root=ROOT,env=None):
    runtime=Path(runtime);runtime.mkdir(parents=True,exist_ok=True);data=build_trace(runtime,root=root,env=env);atomic(runtime/'capability_trace.json',data);return data

def observe_command(run_id,title,command,phase, *, return_code=None,env=None,root=ROOT,invocation_id=None):
    """Best effort telemetry; an observation error cannot alter pipeline behavior."""
    try:
        valid_run(run_id);root=Path(root);runtime=root/'data/careerops-engine/runs'/run_id/'runtime';runtime.mkdir(parents=True,exist_ok=True)
        owners=[]
        for value in command:
            p=Path(str(value))
            if p.suffix in {'.py','.mjs'}:
                p=p if p.is_absolute() else root/p
                if p.resolve().is_relative_to(root.resolve()) and p.is_file(): owners.append(p)
        invocation_id=invocation_id or uuid.uuid4().hex
        for p in owners:
            row={'schema_version':'capability-invocation-v1','run_id':run_id,'invocation_id':invocation_id,'phase':phase,'title':title,'owner_path':str(p),'owner_sha256':sha(p),'return_code':return_code,'at_utc':now()}
            with (runtime/'capability_invocations.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
        emit_trace(runtime,root=root,env=env);return invocation_id
    except Exception as error:
        print('CAPABILITY TRACE OBSERVER ERROR:',type(error).__name__,file=sys.stderr);return invocation_id

def record_shared_receipts(packet,report_path,*,root=ROOT,report=None):
    root=Path(root);batch=packet['batch_id']
    if not re.fullmatch(r'[A-Za-z0-9_-]+',batch):raise ValueError('INVALID_BATCH_ID')
    for case in packet['cases']:
        run_id=valid_run(case['run_id']);runtime=root/'data/careerops-engine/runs'/run_id/'runtime'
        if not runtime.is_dir():raise ValueError('MISSING_RUN_RUNTIME')
        data={'schema_version':'shared-sol-observation-receipt-v1','run_id':run_id,'batch_id':batch,'case_id':case['case_id'],'source_hash':case['source_hash'],
          'sol_semantic_adjudication_calls':1,'status':report.get('status') if report else 'ATTEMPT_RECORDED_BEFORE_MODEL',
          'adjudicator_owner_sha256_at_attempt':sha(root/'scripts/careerops_shared_semantic_adjudicator.py') if (root/'scripts/careerops_shared_semantic_adjudicator.py').is_file() else None,
          'report_path':str(Path(report_path).resolve()),'report_sha256':sha(report_path) if report is not None else None,'observer_only':True}
        atomic(runtime/('shared_sol_receipt_'+batch+'.json'),data);emit_trace(runtime,root=root)

def main():
    p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);args=p.parse_args();valid_run(args.run_id)
    runtime=ROOT/'data/careerops-engine/runs'/args.run_id/'runtime'
    if not runtime.is_dir():raise ValueError('MISSING_RUN_RUNTIME')
    trace=emit_trace(runtime,env=os.environ);print(trace['trace_status']);return 0 if not trace['observation_errors'] else 2
if __name__=='__main__':raise SystemExit(main())
