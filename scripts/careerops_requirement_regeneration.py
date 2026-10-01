"""Re-run the current source producer into a separately bound immutable revision."""
from pathlib import Path
import json,hashlib,subprocess,os,sys,tempfile
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def canonical_ledger_path(runtime):
 runtime=Path(runtime);original=runtime/'jd_requirements.json';pointer=runtime/'requirement_regeneration_authority.json'
 if not pointer.exists():return original
 record=json.loads(pointer.read_text());candidate=runtime/record['candidate_file']
 if candidate.parent!=runtime or record.get('authority')!='CURRENT_DETERMINISTIC_PRODUCER_AND_INDEPENDENT_GATE':raise RuntimeError('INVALID_REGENERATION_AUTHORITY')
 if sha(ROOT/'scripts/careerops_extract_requirements.py')!=record['producer_sha256']:raise RuntimeError('REGENERATION_PRODUCER_CHANGED_REBUILD_REQUIRED')
 if sha(original)!=record['original_ledger_sha256'] or sha(runtime/'jd_intake.json')!=record['intake_sha256'] or sha(candidate)!=record['candidate_sha256']:raise RuntimeError('REGENERATION_SOURCE_BINDING_CHANGED')
 from careerops_requirement_integrity_gate import evaluate
 gate=evaluate(json.loads((runtime/'jd_intake.json').read_text()),json.loads(candidate.read_text()))
 if gate['status']!='PASS':raise RuntimeError('REGENERATED_CANONICAL_LEDGER_NOT_PASS')
 return candidate

def reconstruct(intake,ledger):
 intake={**intake,"status":intake.get("status") or "INGESTED"}
 with tempfile.TemporaryDirectory(prefix='careerops_source_reextract_',dir=runtime) as td:
  d=Path(td);(d/'jd_intake.json').write_text(json.dumps(intake))
  env={**os.environ,'CAREEROPS_RUNTIME_DIR':str(d),'CAREEROPS_JOB_POSITION':ledger.get('target_role_title_candidate') or ''}
  p=subprocess.run([sys.executable,str(ROOT/'scripts/careerops_extract_requirements.py')],cwd=ROOT,env=env,capture_output=True,text=True,timeout=30)
  if p.returncode:raise RuntimeError('CURRENT_SOURCE_PRODUCER_REGENERATION_FAILED:'+p.stderr[-300:])
  candidate=json.loads((d/'jd_requirements.json').read_text())
 from careerops_requirement_integrity_gate import evaluate
 gate=evaluate(intake,candidate)
 from careerops_effective_runtime import build_effective_bundle
 bundle=build_effective_bundle(intake,candidate)
 return {'intake':intake,'canonical_ledger':candidate,'effective_ledger':bundle['effective_ledger'],'bundle_status':'PASS' if gate['status']=='PASS' else 'FAIL_CLOSED','regeneration_owner':'careerops_extract_requirements.py','source_ledger_preserved':True,'gate':gate}

def publish(runtime,candidate):
 runtime=Path(runtime);ledger=candidate.get('canonical_ledger',candidate.get('effective_ledger'))
 current=reconstruct(json.loads((runtime/'jd_intake.json').read_text()),json.loads((runtime/'jd_requirements.json').read_text()))['canonical_ledger']
 if ledger.get('requirements')!=current.get('requirements') or ledger.get('target_role_title_candidate')!=current.get('target_role_title_candidate'):raise RuntimeError('REGENERATION_NOT_CURRENT_PRODUCER_OUTPUT')
 from careerops_requirement_integrity_gate import evaluate
 gate=evaluate(json.loads((runtime/'jd_intake.json').read_text()),ledger)
 if gate['status']!='PASS':raise RuntimeError('REGENERATION_REVALIDATION_FAILED')
 text=json.dumps(ledger,indent=2)+'\n'
 path=runtime/('jd_requirements_regenerated_'+hashlib.sha256(text.encode()).hexdigest()[:16]+'.json')
 if path.exists() and path.read_text()!=text:raise RuntimeError('REGENERATED_REVISION_ALREADY_IMMUTABLE')
 if not path.exists():
  staged=path.with_name(path.name+".tmp");staged.write_text(text);staged.replace(path)
 record={'authority':'CURRENT_DETERMINISTIC_PRODUCER_AND_INDEPENDENT_GATE','candidate_file':path.name,'candidate_sha256':sha(path),'original_ledger_sha256':sha(runtime/'jd_requirements.json'),'intake_sha256':sha(runtime/'jd_intake.json'),'producer_sha256':sha(ROOT/'scripts/careerops_extract_requirements.py'),'model_values_applied':False,'release_authorized':False}
 pointer=runtime/'requirement_regeneration_authority.json';temporary=pointer.with_name(pointer.name+'.tmp');temporary.write_text(json.dumps(record,indent=2)+'\n');temporary.replace(pointer)
 return canonical_ledger_path(runtime)
