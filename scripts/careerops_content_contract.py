"""Validate all written blocks against the current source-bound writer contract."""
import json
from careerops_generate_pair import build_current_job_contract, normalize_contract_id

def contract(runtime):
    spec=json.loads((runtime/'resume_generation_spec.json').read_text())
    pair=json.loads((runtime/'pair_generation_packet.json').read_text())
    return build_current_job_contract(spec,pair)

def structure(content, current):
    errors=[]
    for kind, id_key in [('experience','block_id'),('projects','entity_id')]:
        expected=current.get(kind,[])
        actual=content.get(kind,[])
        expected_by_id={normalize_contract_id(x[id_key]):x for x in expected}
        actual_ids=[normalize_contract_id(x.get(id_key)) for x in actual]
        if len(actual_ids)!=len(set(actual_ids)) or set(actual_ids)!=set(expected_by_id):
            errors.append(kind+'_identity_set')
        for item in actual:
            identity=normalize_contract_id(item.get(id_key)); wanted=expected_by_id.get(identity)
            if not wanted:continue
            if len(item.get('bullets',[]))!=wanted['bullet_count']:
                errors.append(kind+'_bullet_count:'+identity)
            for field in ('company','title','dates') if kind=='experience' else ('name',):
                if field in wanted and item.get(field)!=wanted[field]:errors.append(kind+'_identity:'+identity+':'+field)
    return errors

def expected_claim_count(current):
    return 1+sum(x['bullet_count'] for kind in ('experience','projects') for x in current.get(kind,[]))
