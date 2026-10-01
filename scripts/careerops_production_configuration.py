"""Local model-stage configuration. Explicit flags override offline defaults."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
def apply(env):
    result=dict(env)
    path=ROOT/"config/runtime.json"
    config=json.loads(path.read_text()) if path.is_file() else {}
    normal=config.get("normal_production",{})
    for key,name in [("CAREEROPS_SEMANTIC_CHALLENGER","semantic_challenger"),("CAREEROPS_INTERVIEW_DEFENSIBILITY","interview_defensibility"),("CAREEROPS_SHARED_SOL_SEMANTIC","shared_sol_semantic"),("CAREEROPS_LI_ADVISORY","li_advisory")]:
        result.setdefault(key,"1" if normal.get(name,name=="interview_defensibility") is True else "0")
    result.setdefault("CAREEROPS_LI_OLLAMA_ENDPOINT",config.get("endpoint","http://127.0.0.1:11434").rstrip("/")+"/api/chat")
    return result
