"""Canonical JD metadata ownership at every deterministic/writer boundary."""
from pathlib import Path
import hashlib,json,sys

STAGES = {
 'careerops_route_summary.py': (['technical_skills_plan.json','experience_selection.json','project_selection.json'], ['summary_route.json','resume_generation_spec.json']),
 'careerops_build_compact_packet.py': (['resume_generation_spec.json','technical_skills_plan.json','experience_selection.json','project_selection.json','constraint_validation.json'], ['compact_generation_packet.json']),
 'careerops_build_cover_plan.py': (['compact_generation_packet.json','role_routing.json','experience_selection.json','project_selection.json','requirement_evidence_map.json'], ['cover_plan.json']),
 'careerops_cover_gate_v2.py': (['pair_generation_packet.json','cover_plan.json'], ['cover_gate_v2_report.json']),
 'careerops_human_gate_v22.py': (['ats_gate.json','requirement_evidence_map.json','experience_selection.json','project_selection.json','technical_skills_plan.json'], ['human_gate.json','human_audit.json']),
 'careerops_ats_gate_v2.py': (['jd_semantic_map.json','constraint_validation.json','role_routing.json','technical_skills_plan.json','requirement_evidence_map.json'], ['ats_gate.json','ats_audit.json']),
 'careerops_route_role.py': ([], ['role_routing.json']),
 'careerops_expand_jd_semantics.py': (['role_routing.json'], ['jd_semantic_map.json']),
 'careerops_map_evidence.py': (['jd_semantic_map.json'], ['requirement_evidence_map.json']),
 'careerops_validate_constraints.py': (['jd_semantic_map.json','requirement_evidence_map.json'], ['constraint_validation.json']),
 'careerops_select_experience.py': (['jd_semantic_map.json','requirement_evidence_map.json','constraint_validation.json'], ['experience_selection.json']),
 'careerops_select_projects.py': (['jd_semantic_map.json','requirement_evidence_map.json','constraint_validation.json','experience_selection.json'], ['project_selection.json']),
 'careerops_build_skills.py': (['jd_semantic_map.json','requirement_evidence_map.json','constraint_validation.json'], ['technical_skills_plan.json']),
 'careerops_build_pair_packet.py': (['jd_semantic_map.json','requirement_evidence_map.json','constraint_validation.json','experience_selection.json','project_selection.json','technical_skills_plan.json'], ['pair_generation_packet.json']),
 'careerops_generate_pair.py': (['pair_generation_packet.json'], []),
}

def digest(value):
 return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

def authority(runtime):
 runtime=Path(runtime)
 from careerops_requirement_regeneration import canonical_ledger_path
 ledger_path=canonical_ledger_path(runtime);ledger=json.loads(ledger_path.read_text());intake=json.loads((runtime/'jd_intake.json').read_text())
 rows=ledger.get('requirements',[]);ids=[r['requirement_id'] for r in rows]
 if len(ids)!=len(set(ids)):raise RuntimeError('REQUIREMENT_AUTHORITY_DRIFT: duplicate canonical IDs')
 current={'schema':'canonical-requirement-authority-v1','intake_sha256':hashlib.sha256((runtime/'jd_intake.json').read_bytes()).hexdigest(),'ledger_sha256':hashlib.sha256(ledger_path.read_bytes()).hexdigest(),'application_title':ledger.get('target_role_title_candidate')}
 current['current_job_fingerprint']=digest(current)
 return current,{r['requirement_id']:r for r in rows}

def binding(row,current):
 return {'requirement_id':row['requirement_id'],'priority':row['priority'],'section':row['section'],'exact_quote_sha256':hashlib.sha256(row['exact_quote'].encode()).hexdigest(),'current_job_fingerprint':current['current_job_fingerprint']}

def inspect_payload(payload,current,rows,*,stamp=False):
 findings=[]
 recorded=payload.get('requirement_authority') if isinstance(payload,dict) else None
 if recorded is not None and recorded!=current:findings.append({'code':'CURRENT_REQUISITION_FINGERPRINT_MISMATCH'})
 def walk(value,path='$'):
  if isinstance(value,dict):
   rid=value.get('requirement_id')
   if isinstance(rid,str) and rid.startswith('REQ-'):
    source=rows.get(rid)
    if source is None:findings.append({'path':path,'code':'UNKNOWN_CANONICAL_REQUIREMENT_ID','id':rid})
    else:
     expected=binding(source,current)
     for key in ['priority','effective_priority','source_priority']:
      if key in value and value[key]!=source['priority']:findings.append({'path':path+'.'+key,'code':'CANONICAL_PRIORITY_MISMATCH','id':rid})
     for key in ['exact_quote','exact_jd_quote']:
      if key in value and value[key]!=source['exact_quote']:findings.append({'path':path+'.'+key,'code':'CANONICAL_QUOTE_MISMATCH','id':rid})
     if 'canonical_reference' in value and value['canonical_reference']!=expected:findings.append({'path':path,'code':'CANONICAL_REFERENCE_MISMATCH','id':rid})
     # Semantic raw-section interpretation belongs in annotations; a row's
     # source section remains owned by the immutable ledger.
     if 'section' in value and value['section']!=source['section']:findings.append({'path':path+'.section','code':'CANONICAL_SECTION_MISMATCH','id':rid})
     for key in ['jd_line','source_span','priority_basis','normalized_requirement','exact_tools_technologies','exact_work_products','exact_methods','experience_years_phrases','education_phrases','work_authorization_phrases','clearance_phrases','hard_blocker_phrases']:
      if key in value and key in source and value[key]!=source[key]:findings.append({'path':path+'.'+key,'code':'CANONICAL_METADATA_MISMATCH','id':rid})
     if 'exact_layer' in value:
      aliases={'tools_technologies':'exact_tools_technologies','work_products':'exact_work_products','methods':'exact_methods','experience_years':'experience_years_phrases','education':'education_phrases'}
      for copied,original in aliases.items():
       if copied in value['exact_layer'] and original in source and value['exact_layer'][copied]!=source[original]:findings.append({'path':path+'.exact_layer.'+copied,'code':'CANONICAL_METADATA_MISMATCH','id':rid})
     if stamp:value['canonical_reference']=expected
   for key,item in list(value.items()):
    if key not in {'canonical_reference','requirement_authority'}:walk(item,path+'.'+key)
  elif isinstance(value,list):
   for index,item in enumerate(value):walk(item,path+'['+str(index)+']')
  elif isinstance(value,str) and value.startswith('REQ-') and value[4:].isdigit() and value not in rows:
   findings.append({'path':path,'code':'UNKNOWN_CANONICAL_REQUIREMENT_ID','id':value})
 walk(payload)
 if stamp and isinstance(payload,dict):payload['requirement_authority']=current
 return findings

def check_artifact(runtime,name,*,stamp=False,require_stamp=False):
 runtime=Path(runtime);path=runtime/name
 if not path.is_file():raise RuntimeError('Missing required current-job artifact: '+name)
 current,rows=authority(runtime);data=json.loads(path.read_text());findings=inspect_payload(data,current,rows,stamp=stamp)
 if require_stamp and data.get('requirement_authority') is None:findings.append({'code':'MISSING_CURRENT_CANONICAL_BINDING'})
 if findings:
  report={'status':'FAIL_CLOSED','code':'REQUIREMENT_AUTHORITY_DRIFT','artifact':name,'findings':findings,'resumable_from':'REGENERATE_ARTIFACT_FROM_CANONICAL_LEDGER','canonical_authority':current,'model_calls':0}
  (runtime/'requirement_authority_failure.json').write_text(json.dumps(report,indent=2)+'\n')
  raise RuntimeError('REQUIREMENT_AUTHORITY_DRIFT: '+name+'; '+','.join(sorted({f['code'] for f in findings})))
 if stamp:
  temporary=path.with_name(path.name+'.authority.tmp');temporary.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n');temporary.replace(path)
 return data

def guard_before(runtime,stage):
 inputs,_=STAGES[stage]
 before,_=authority(runtime)
 for name in inputs:check_artifact(runtime,name,require_stamp=True)
 return before

def guard_after(runtime,stage,before):
 after,_=authority(runtime)
 if before != after:raise RuntimeError('REQUIREMENT_AUTHORITY_DRIFT: source ledger/intake mutated by '+stage)
 for name in STAGES[stage][1]:check_artifact(runtime,name,stamp=True)

def run_guarded(main,runtime,stage):
 before=guard_before(runtime,stage)
 try:result=main()
 except SystemExit:
  guard_after(runtime,stage,before)
  raise
 guard_after(runtime,stage,before)
 return result

def rehydrate_immutable(payload,runtime):
 """Explicit deterministic recovery only for the same source fingerprint.
 Annotations survive; unknown IDs/stale requisitions are never repaired.
 The repaired object must still pass the next independent gate.
 """
 import copy
 result=copy.deepcopy(payload);current,rows=authority(runtime)
 if result.get('requirement_authority') != current:
  raise RuntimeError('REQUIREMENT_AUTHORITY_DRIFT: stale or unbound artifact requires owner regeneration')
 def walk(value):
  if isinstance(value,dict):
   rid=value.get('requirement_id')
   if isinstance(rid,str) and rid.startswith('REQ-'):
    if rid not in rows:raise RuntimeError('REQUIREMENT_AUTHORITY_DRIFT: unknown canonical ID')
    row=rows[rid]
    for key in list(value):
     if key in row:value[key]=copy.deepcopy(row[key])
     elif key in {'source_priority','effective_priority'}:value[key]=row['priority']
     elif key=='exact_jd_quote':value[key]=row['exact_quote']
    if 'exact_layer' in value:
     for k,v in {'tools_technologies':'exact_tools_technologies','work_products':'exact_work_products','methods':'exact_methods','experience_years':'experience_years_phrases','education':'education_phrases'}.items():
      if v in row:value['exact_layer'][k]=copy.deepcopy(row[v])
    value['canonical_reference']=binding(row,current)
   for key,child in value.items():
    if key not in {'canonical_reference','requirement_authority'}:walk(child)
  elif isinstance(value,list):
   for child in value:walk(child)
 walk(result)
 if inspect_payload(result,current,rows):raise RuntimeError('REQUIREMENT_AUTHORITY_DRIFT: recovery incomplete')
 return result
