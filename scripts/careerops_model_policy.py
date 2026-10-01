"""Check authenticated CLI metadata before starting a cloud inference."""
import json,hashlib,os
from pathlib import Path
MODEL='gpt-6.1-sol'
def preflight(effort,runtime=None):
 if effort not in {'high','xhigh'}:raise RuntimeError('UNAUTHORIZED_PRODUCTION_REASONING_EFFORT')
 cache=Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))/'models_cache.json'
 if not cache.is_file():raise RuntimeError('MODEL_CATALOG_MISSING: refresh Codex app-server model/list; no inference started')
 payload=json.loads(cache.read_text());models=payload.get('models',[]) if isinstance(payload,dict) else payload
 found=next((x for x in models if x.get('slug',x.get('id'))==MODEL),None)
 if not found:raise RuntimeError('TARGET_MODEL_UNAVAILABLE: '+MODEL+'; update CLI and refresh authenticated model/list before inference')
 choices=found.get('supported_reasoning_levels',found.get('supportedReasoningEfforts',[]))
 supported={x.get('effort',x.get('reasoningEffort',x.get('reasoning_effort'))) if isinstance(x,dict) else x for x in choices}
 if supported and effort not in supported:raise RuntimeError('TARGET_REASONING_EFFORT_UNAVAILABLE: '+effort)
 result={'status':'PASS','model':MODEL,'reasoning_effort':effort,'catalog_sha256':hashlib.sha256(cache.read_bytes()).hexdigest(),'inference_calls':0}
 if runtime:(Path(runtime)/'model_preflight.json').write_text(json.dumps(result,indent=2)+'\n')
 return result
