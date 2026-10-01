import sys
"""Explicit overall generation override, isolated from automatic release authority."""
import hashlib,json,os,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable)
def read(p):
    return json.loads(Path(p).read_text()) if Path(p).is_file() else {}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);t=p.with_name(p.name+'.tmp');t.write_text(json.dumps(v,indent=2)+'\n');t.replace(p)
def blockers(runtime):
    from careerops_effective_runtime import detect_document_constraints
    intake=read(Path(runtime)/'jd_intake.json')
    if not intake.get('raw_jd_text'):raise RuntimeError('Override unavailable: complete immutable JD is missing.')
    return [x for x in detect_document_constraints(intake) if x.get('policy')=='HARD_BLOCK']
def preflight(run_root):
    run_root=Path(run_root);m=read(run_root/'manifest.json');rt=run_root/'runtime'
    result={'eligible':False,'reason':'Override requires an automatic failed or rejected run.'}
    if m.get('lifecycle_status') not in {'REJECTED','NEEDS_ATTENTION','RELEASE_BLOCKED'}:return result
    try:
        hard=blockers(rt)
        if hard:return {'eligible':False,'reason':'Irreducible eligibility hard block; generation is unavailable.','hard_blocks':hard}
        job=m.get('job',{})
        if not job.get('company') or not job.get('position'):raise RuntimeError('Canonical job identity is missing.')
        calls=m.get('execution',{}).get('writer_calls',0)
        state=read(rt/'writer_invocation_state.json')
        if calls==0:return {'eligible':True,'mode':'OVERALL_TRUTHFUL_QUARANTINE_FIRST_WRITER','reason':'A source-bound isolated packet may be prepared with unresolved automatic diagnostics retained.'}
        if calls==1 and m.get('stages',{}).get('writer',{}).get('status')=='PASS' and all((rt/p).is_file() for p in ('generated_resume_content_pair_candidate.json','generated_cover_letter_pair_candidate.json')):
            return {'eligible':True,'mode':'POST_WRITER_REUSE_EXISTING_PAIR','reason':'Reuse the saved pair with zero additional writer calls.'}
        return {'eligible':False,'reason':'Writer accounting does not authorize another model call.'}
    except (RuntimeError,ValueError,OSError) as exc:result['reason']=str(exc);return result

def quarantine_authorized(runtime,intake_hash,ledger_hash):
    marker=read(Path(runtime)/'quarantine_generation_authorization.json')
    original=Path(marker.get('automatic_run_root','/nonexistent'))
    if marker.get('authority')!='EXPLICIT_USER' or not marker.get('reason') or marker.get('release_authorized') is not False:return False
    if marker.get('intake_sha256')!=intake_hash or marker.get('ledger_sha256')!=ledger_hash:return False
    if not (original/'manifest.json').is_file() or marker.get('automatic_manifest_sha256')!=sha(original/'manifest.json'):return False
    return not blockers(runtime)

def run(run_root,reason):
    run_root=Path(run_root).resolve();original_rt=run_root/'runtime';m=read(run_root/'manifest.json')
    if not str(reason or '').strip():raise RuntimeError('Explicit override reason is required.')
    availability=preflight(run_root)
    if not availability.get('eligible'):raise RuntimeError(availability['reason'])
    automatic_files=[run_root/'manifest.json']+[original_rt/p for p in ('jd_intake.json','jd_requirements.json','job_decision_receipt.json','failure_classification.json') if (original_rt/p).is_file()]
    before={str(p):sha(p) for p in automatic_files}
    old_report=read(original_rt/'user_override'/'user_override_generation_report.json')
    renderer_sources={str(ROOT/'scripts'/name):sha(ROOT/'scripts'/name) for name in ['careerops_build_cv_payload.py','careerops_docx_renderer.py','careerops_render_cover_docx.py','careerops_contact_identity.py','careerops_user_override_generate.py']}
    legacy_id=run_root.name[:90]+'__overall_override';legacy=run_root.parent/legacy_id
    legacy_owner=read(legacy/'manifest.json').get('automatic_parent_run')==run_root.name or read(legacy/'runtime/quarantine_generation_authorization.json').get('automatic_run_root')==str(run_root)
    child_id=old_report.get('generation_run_id') or (legacy_id if legacy_owner else run_root.name[:80]+'__'+hashlib.sha256(run_root.name.encode()).hexdigest()[:10]+'__overall_override')
    import re
    if not re.fullmatch(r'[A-Za-z0-9_-]+',child_id):raise RuntimeError('INVALID_OVERRIDE_CHILD_IDENTITY')
    child=run_root.parent/child_id;rt=child/'runtime';rt.mkdir(parents=True,exist_ok=True)
    existing_owner=read(child/'manifest.json').get('automatic_parent_run')
    if existing_owner and existing_owner!=run_root.name:raise RuntimeError('CROSS_RUN_OVERRIDE_CHILD_REFUSED')
    if old_report.get('status')=='USER_OVERRIDE_GENERATED' and old_report.get('renderer_source_hashes')==renderer_sources and old_report.get('automatic_manifest_sha256')==sha(run_root/'manifest.json') and all(Path(p).is_file() and sha(p)==h for p,h in old_report.get('automatic_source_hashes',{}).items()) and len(old_report.get('outputs',{}))==4 and all(Path(x['path']).is_file() and sha(x['path'])==x['sha256'] for x in old_report.get('outputs',{}).values()):
        old_report['original_decision_receipt']=read(original_rt/'job_decision_receipt.json')
        old_report['new_writer_calls_this_invocation']=0
        old_report.setdefault('automatic_source_hashes',before)
        write(original_rt/'user_override'/'user_override_generation_report.json',old_report)
        return old_report
    for filename in ('jd_intake.json','jd_requirements.json','jd_source_original.txt'):
        p=original_rt/filename
        if p.exists() and not (rt/filename).exists():shutil.copy2(p,rt/filename)
    env=os.environ.copy();env.update(CAREEROPS_RUNTIME_DIR=str(rt),CAREEROPS_RUN_ID=child_id,CAREEROPS_OUTPUT_DIR=str(child/'output'),CAREEROPS_JOB_COMPANY=m['job']['company'],CAREEROPS_JOB_POSITION=m['job']['position'])
    def execute(script,args=(),allowed=(0,)):
        command=[str(PYTHON),'-B',str(ROOT/'scripts'/script),*args]
        result=subprocess.run(command,env=env,capture_output=True,text=True)
        with (rt/'overall_override.log').open('a') as stream:stream.write('COMMAND '+script+'\n'+result.stdout+'\n'+result.stderr+'\n')
        if result.returncode not in allowed:raise RuntimeError('Override owner failed: '+script+'; '+result.stderr[-1200:])
        return result.returncode
    diagnostics=read(original_rt/'requirement_integrity_gate.json')
    existing_state=read(rt/'writer_invocation_state.json')
    reuse=availability['mode']=='POST_WRITER_REUSE_EXISTING_PAIR'
    if reuse:
        for p in original_rt.glob('*.json'):
            if p.name not in ('user_generation_override_authorization.json',):shutil.copy2(p,rt/p.name)
    elif not existing_state.get('transport_started'):
        execute('careerops_extract_requirements.py')
        gate_rc=execute('careerops_requirement_integrity_gate.py',allowed=(0,1,2))
        write(rt/'quarantine_generation_authorization.json',{'authority':'EXPLICIT_USER','reason':reason,'automatic_run_root':str(run_root),'automatic_manifest_sha256':sha(run_root/'manifest.json'),'intake_sha256':sha(rt/'jd_intake.json'),'ledger_sha256':sha(rt/'jd_requirements.json'),'release_authorized':False,'automatic_integrity_diagnostics':diagnostics,'quarantine_integrity_rc':gate_rc})
        from careerops_production_orchestrator import DETERMINISTIC_STAGES
        for stage,script,_ in DETERMINISTIC_STAGES:
            if stage not in ('requirements','requirement_integrity'):execute(Path(script).name)
        execute('careerops_build_pair_packet.py',['--company',m['job']['company'],'--position',m['job']['position']])
        packet=read(rt/'pair_generation_packet.json');packet['quarantine_generation']={'authority':'EXPLICIT_USER','release_authorized':False,'unresolved_automatic_issues':json.dumps(diagnostics),'full_jd_sha256':sha(rt/'jd_intake.json')};write(rt/'pair_generation_packet.json',packet)
        execute('careerops_generate_pair.py')
    else:
        if not existing_state.get('model_completed') or not existing_state.get('output_validated'):raise RuntimeError('A prior override writer attempt exists; no implicit retry is authorized.')
    # Truthfulness remains mandatory for unreleased override documents.
    env['CAREEROPS_RESUME_INPUT']=str(rt/'generated_resume_content_pair_candidate.json')
    execute('careerops_local_truth_gate.py')
    execute('careerops_truth_gate.py')
    execute('careerops_run_manifest.py',['refresh','--company',m['job']['company'],'--position',m['job']['position']])
    execute('careerops_run_manifest.py',['mark','--stage','writer','--status','PASS','--company',m['job']['company'],'--position',m['job']['position'],'--detail','Explicit isolated overall override; normal release remains unauthorized.'])
    cm=read(child/'manifest.json');cm['lifecycle_status']='NEEDS_ATTENTION';cm['overall_override_only']=True;cm['automatic_parent_run']=run_root.name;write(child/'manifest.json',cm)
    write(rt/'user_generation_override_authorization.json',{'authority':'EXPLICIT_USER','status':'AUTHORIZED','mode':'POST_WRITER_FAILURE_REUSE_EXISTING_PAIR' if reuse else 'OVERALL_TRUTHFUL_QUARANTINE_FIRST_WRITER','user_reason':reason,'max_total_writer_calls':1,'automatic_release_not_authorized':True,'original_failure_classification':read(original_rt/'failure_classification.json')})
    from careerops_user_override_generate import generate_override
    report=generate_override(child_id,reason,runs_root=run_root.parent)
    if any(sha(Path(p))!=h for p,h in before.items()):raise RuntimeError('Automatic authority changed during isolated override.')
    report.update(renderer_source_hashes=renderer_sources,automatic_source_hashes=before,original_decision_receipt=read(original_rt/'job_decision_receipt.json'),new_writer_calls_this_invocation=0 if reuse or existing_state.get('model_completed') else 1,run_id=run_root.name,generation_run_id=child_id,automatic_manifest_sha256=before[str(run_root/'manifest.json')],automatic_engine_decision_preserved=True,additional_writer_calls=0 if reuse else 1,unresolved_automatic_issues=diagnostics)
    write(original_rt/'user_override'/'user_override_generation_report.json',report)
    return report
