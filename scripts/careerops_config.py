"""Explicit candidate authority and local resource configuration; no private fallback."""
from pathlib import Path
import json, os

def source_dir(root):
    raw=os.environ.get("CAREEROPS_SOURCE_DIR", "candidate/source")
    path=Path(raw).expanduser()
    return (path if path.is_absolute() else Path(root)/path).resolve()

def load_facts(root):
    path=source_dir(root)/"candidate_facts.json"
    if not path.is_file(): raise RuntimeError("CANDIDATE_AUTHORITY_MISSING: configure CAREEROPS_SOURCE_DIR")
    facts=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(facts,dict):raise RuntimeError("CANDIDATE_AUTHORITY_INVALID")
    return facts

def candidate_identity(root):
    candidate=load_facts(root).get("candidate_identity",{})
    required=("name","email","phone","location","linkedin","github")
    if not isinstance(candidate,dict) or any(not candidate.get(k) for k in required):
        raise RuntimeError("CANDIDATE_IDENTITY_INCOMPLETE")
    return candidate

def experience_blocks(root):
    rows=load_facts(root).get("experience_blocks",[])
    if not rows:raise RuntimeError("CANDIDATE_EXPERIENCE_BLOCKS_MISSING")
    for row in rows:
        if any(not row.get(k) for k in ("block_id","organization","title","period","evidence_ids")):
            raise RuntimeError("CANDIDATE_EXPERIENCE_BLOCK_INVALID")
    return rows

def candidate_attestations(root):
    path=source_dir(root)/"candidate_attestations.json"
    if not path.is_file():raise RuntimeError("CANDIDATE_ATTESTATIONS_MISSING")
    data=json.loads(path.read_text())
    if not isinstance(data,dict):raise RuntimeError("CANDIDATE_ATTESTATIONS_INVALID")
    return data
