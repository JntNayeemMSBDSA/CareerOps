"""Production queue coordinator for the accepted shared Sol adjudicator."""
from pathlib import Path
import json,hashlib,fcntl,os,copy
from careerops_shared_semantic_adjudicator import adjudicate,build_packet,POLICY,invoke_sol
from careerops_capability_trace import record_shared_receipts,emit_trace
from careerops_effective_runtime import ensure_effective_runtime
from careerops_requirement_integrity_gate import evaluate
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def atomic(p,d):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_name(p.name+'.tmp');tmp.write_text(json.dumps(d,indent=2)+'\n');tmp.replace(p)
def queued_case(run_id,root=ROOT):
 from careerops_capability_trace import valid_run
 valid_run(run_id);runtime=Path(root)/'data/careerops-engine/runs'/run_id/'runtime';path=runtime/'semantic_challenger_report.json'
 if not path.exists():return None
 report=json.loads(path.read_text());case=report.get('case',{})
 if report.get('status')!='UNRESOLVED_FAIL_CLOSED' or case.get('route')!='SHARED_SOL_ADJUDICATION' or case.get('run_id')!=run_id:return None
 if not report.get('immutable_source_preserved'):return None
 for name,h in report.get('immutable_hashes',{}).items():
  if sha(runtime/name)!=h:raise ValueError('IMMUTABLE_SOURCE_CHANGED:'+run_id)
 return case

def apply_revalidated(decision,root=ROOT):
 if decision.get('status')!='REVALIDATED_PROPOSAL':return False
 runtime=Path(root)/'data/careerops-engine/runs'/decision['run_id']/'runtime';report=json.loads((runtime/'semantic_challenger_report.json').read_text());before=report['immutable_hashes']
 for name,h in before.items():assert sha(runtime/name)==h,'SOURCE_CHANGED_BEFORE_RECONSTRUCTION'
 from careerops_requirement_regeneration import publish
 publish(runtime,decision['reconstructed_candidate'])
 bundle=ensure_effective_runtime(runtime);intake=json.loads((runtime/'jd_intake.json').read_text());gate=evaluate(intake,bundle['effective_ledger'])
 assert bundle['effective_ledger']['requirements']==decision['reconstructed_candidate']['effective_ledger']['requirements'],'CANDIDATE_RECONSTRUCTION_CHANGED'
 if gate.get('status')!='PASS':return False
 for name,h in before.items():assert sha(runtime/name)==h,'SOURCE_MUTATED'
 old=runtime/'requirement_integrity_gate.pre_shared_reconstruction.json'
 if not old.exists():atomic(old,json.loads((runtime/'requirement_integrity_gate.json').read_text()))
 gate['semantic_reconstruction']={'authority':'DETERMINISTIC_REVALIDATION','source_ledger_immutable':True,'model_values_applied':False,'original_gate_owner':'careerops_requirement_integrity_gate.evaluate','resolution_path':'SHARED_SOL','immutable_hashes':before}
 atomic(runtime/'requirement_integrity_gate.json',gate)
 report.update(status='RECONSTRUCTED_REVALIDATED',resolution_path='SHARED_SOL',original_gate_after='PASS',immutable_source_preserved=True)
 atomic(runtime/'semantic_challenger_report.json',report);emit_trace(runtime,root=root);return True

def automatic_batch(run_ids,*,root=ROOT,transport=None):
 root=Path(root);cases=[];sources={}
 for run in dict.fromkeys(run_ids):
  case=queued_case(run,root)
  if case:
   cases.append(case);sources[run]=json.loads((root/'data/careerops-engine/runs'/run/'runtime/jd_intake.json').read_text())['raw_jd_text']
 if not cases:return {'status':'NOT_NEEDED','sol_semantic_adjudication_calls':0,'continued_runs':[]}
 packet=build_packet(cases,POLICY,sources);directory=root/'data/careerops-engine/shared-semantic-batches'/packet['batch_id'];directory.mkdir(parents=True,exist_ok=True);path=directory/'report.json';attempt=directory/'transport_attempt.json'
 with (directory/'batch.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  if path.exists():return json.loads(path.read_text())
  if attempt.exists():return {'status':'INTERRUPTED_TRANSPORT_FAIL_CLOSED','continued_runs':[],'sol_semantic_adjudication_calls':0,'batch_id':packet['batch_id'],'new_calls':0}
  def observed(p):
   atomic(attempt,{'status':'ATTEMPT_RECORDED_BEFORE_MODEL','batch_id':p['batch_id'],'case_count':p['case_count'],'model':'gpt-6.1-sol','reasoning':'high','sol_semantic_adjudication_calls':1,'source_hashes':{c['run_id']:c['source_hash'] for c in cases}})
   record_shared_receipts(p,path,root=root)
   response=(transport or invoke_sol)(p)
   atomic(directory/'raw_response.json',{'batch_id':p['batch_id'],'response':response,'authority':'UNTRUSTED_MODEL_PROPOSAL_ONLY'})
   return response
  result=adjudicate(cases,POLICY,sources,transport=observed);result['continued_runs']=[]
  for decision in result.get('decisions',[]):
   try:
    if apply_revalidated(decision,root):result['continued_runs'].append(decision['run_id'])
   except Exception as exc:decision.update(status='UNRESOLVED_FAIL_CLOSED',application_error=type(exc).__name__+':'+str(exc))
  result['production_application_status']='APPLIED_REVALIDATED' if len(result['continued_runs'])==len(cases) else 'UNRESOLVED_FAIL_CLOSED'
  atomic(path,result);record_shared_receipts(result['packet'],path,root=root,report=result);return result

def aggregate_accounting(run_ids,root=ROOT):
 from careerops_capability_trace import build_trace
 root=Path(root);totals={key:0 for key in ['qwen_attempted','qwen_completed','sol_semantic_adjudication_calls','sol_writer_calls','exceptional_writer_retry_calls','other_truth_audit_calls']};batches=set()
 for run in dict.fromkeys(run_ids):
  runtime=root/'data/careerops-engine/runs'/run/'runtime'
  if not runtime.is_dir():continue
  trace=build_trace(runtime,root=root)
  for key in totals:
   if key!='sol_semantic_adjudication_calls':totals[key]+=int(trace['model_accounting'].get(key,0) or 0)
  for path in runtime.glob('shared_sol_receipt_*.json'):
   receipt=json.loads(path.read_text())
   if receipt.get('run_id')==run and receipt.get('sol_semantic_adjudication_calls')==1:batches.add(receipt['batch_id'])
 cover_sol=sum(int(json.loads((root/'data/careerops-engine/runs'/run/'runtime/cover_semantic_challenger_report.json').read_text()).get('shared_sol_attempted',0)) for run in dict.fromkeys(run_ids) if (root/'data/careerops-engine/runs'/run/'runtime/cover_semantic_challenger_report.json').is_file())
 totals['sol_semantic_adjudication_calls']=len(batches)+cover_sol;totals['shared_semantic_batch_ids']=sorted(batches)
 totals['total_observed_model_attempts']=sum(totals[key] for key in ['qwen_attempted','sol_semantic_adjudication_calls','sol_writer_calls','exceptional_writer_retry_calls','other_truth_audit_calls'])
 return totals
