"""Durable writer transport accounting after deterministic preflight."""
from pathlib import Path
from datetime import datetime,timezone
import json,subprocess,hashlib

def save(runtime,state):
 path=Path(runtime)/'writer_invocation_state.json';temporary=path.with_suffix('.tmp');state['updated_at_utc']=datetime.now(timezone.utc).isoformat();temporary.write_text(json.dumps(state,indent=2)+'\n');temporary.replace(path)

def prepare(runtime):
 runtime=Path(runtime);path=runtime/'writer_invocation_state.json'
 old=json.loads(path.read_text()) if path.is_file() else {}
 manifest=runtime.parent/'manifest.json'
 legacy=json.loads(manifest.read_text()).get('execution',{}).get('writer_calls',0) if manifest.is_file() else 0
 prior_calls=int(old.get('writer_calls',legacy))
 already_attempted=old.get('transport_started') or old.get('writer_attempt_started') or prior_calls
 authorization={}
 if already_attempted:
  auth_path=runtime/'user_generation_override_authorization.json'
  authorization=json.loads(auth_path.read_text()) if auth_path.is_file() else {}
  receipt_sha=hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
  valid=(authorization.get('authority')=='EXPLICIT_USER' and authorization.get('status')=='AUTHORIZED'
         and authorization.get('run_id')==runtime.parent.name and authorization.get('writer_receipt_sha256')==receipt_sha)
  first=(prior_calls==0 and authorization.get('mode')=='TRUTHFUL_CURRENT_PACKET_FIRST_WRITER_ALLOWED' and authorization.get('max_total_writer_calls')==1)
  retry=(prior_calls==1 and old.get('transport_completed') and old.get('model_completed') is False
         and authorization.get('mode')=='EXPLICIT_FAILED_TRANSPORT_ONE_RETRY_ALLOWED' and authorization.get('max_total_writer_calls')==2)
  if not valid or not (first or retry):
   raise RuntimeError('WRITER_BUDGET_ALREADY_STARTED: explicit bounded retry policy required')
 history=list(old.get('previous_attempts',[]))
 if already_attempted:history.append({k:v for k,v in old.items() if k!='previous_attempts'})
 state={'schema_version':'writer-invocation-v2','preflight_started':True,'preflight_completed':False,'writer_attempt_started':False,'transport_started':False,'model_completed':False,'output_validated':False,'writer_calls':prior_calls,'attempted_calls':int(old.get('attempted_calls',0)),'previous_attempts':history,'exceptional_writer_retry_calls':max(0,prior_calls-1),'max_total_writer_calls':authorization.get('max_total_writer_calls',1)}

 save(runtime,state);return state

def invoke(runtime,state,command,*,cwd,env):
 if state['writer_calls']>=state['max_total_writer_calls']:raise RuntimeError('WRITER_TRANSPORT_BOUND_EXCEEDED')
 state.update(preflight_completed=True,writer_attempt_started=True,attempted_calls=state.get('attempted_calls',0)+1)
 state['transport_command']=list(map(str,command))
 state['model']=str(command[command.index('-m')+1]) if '-m' in command else None
 state['reasoning_effort']='xhigh' if any('model_reasoning_effort="xhigh"' in str(x) for x in command) else 'high' if any('model_reasoning_effort="high"' in str(x) for x in command) else None
 save(runtime,state)
 try:
  process=subprocess.Popen(command,cwd=cwd,env=env)
 except OSError as exc:
  state.update(transport_start_failed=True,error=str(exc))
  save(runtime,state);raise
 state.update(transport_started=True,writer_calls=state['writer_calls']+1,pid=process.pid)
 state['exceptional_writer_retry_calls']=max(0,state['writer_calls']-1)
 save(runtime,state)
 code=process.wait();state.update(transport_completed=True,return_code=code,model_completed=code==0)
 save(runtime,state);return code
