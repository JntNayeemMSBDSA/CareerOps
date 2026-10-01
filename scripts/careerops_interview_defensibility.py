"""Interview defensibility is an additional quality contract, never truth authority.

SAFE: source-bound and explainable. SUPPORTABLE_WITH_CONTEXT: confirmed skill or
explicit future transfer, not historical proof. WEAK: needs bounded clarification.
PROHIBITED: unsupported, conflicting, market-only, or wrong historical owner.
WEAK and PROHIBITED block this gate. No model, writer, source edits, or release.
"""
from __future__ import annotations
from careerops_config import source_dir
import argparse, hashlib, json, os, re
from collections import Counter
from pathlib import Path
import careerops_local_truth_gate as truth

ROOT=Path(__file__).resolve().parents[1]
SUPPORTED={"SUPPORTED","SUPPORTED_BY_DIRECT_USER_OVERRIDE"}
ALLOWED={"SAFE","SUPPORTABLE_WITH_CONTEXT"}
STOP=set("a an and are as at be been by for from has have i in is it its my of on or our that the their these this through to using was were with work built developed implemented analysis data project model reporting".split())
DANGEROUS={
 "ownership":r"\b(?:sole author|sole owner|invented|founded|created the company|company-wide owner)\b",
 "unbounded_scope":r"\b(?:all company|entire enterprise|enterprise-wide|organization-wide|guaranteed|zero defects|perfect accuracy)\b",
 "causal_outcome":r"\b(?:saved|generated revenue|increased revenue|reduced costs|reduced cost|boosted revenue|drove revenue|caused)\b",
}

def norm(text): return re.sub(r'\s+',' ',str(text).casefold()).strip()
def tokens(text): return {x for x in re.findall(r'[a-z][a-z0-9]+',norm(text)) if x not in STOP and len(x)>2}
def contains(text,term):
    return bool(term and re.search(r'(?<!\w)'+re.escape(norm(term))+r'(?!\w)',norm(text)))
def owner_supports_term(support_text,term):
    """Generic reporting includes dashboards, only within this claim's owner evidence.

    This activity equivalence supplies no technology, specialty, metric, or scope.
    Direct proficiency and other owners are not supplied to historical claims.
    """
    if contains(support_text,term): return True
    return norm(term)=='reporting' and any(contains(support_text,x) for x in ('report','reports','dashboard','dashboards'))

def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path): return json.loads(Path(path).read_text())

def classify_material_claim(text, *, context, support_text='', truth_supported=True,
                            source_ids=(), confirmed_terms=(), risk_terms=(), market_terms=()):
    """Pure policy function. Runtime supplies source text, not model assertions."""
    reasons=[]; prohibited=[]; weak=[]
    if not text or not truth_supported: prohibited.append('truth_or_content_not_supported')
    if context=='skill':
        if norm(text) in {norm(x) for x in confirmed_terms}:
            return {'classification':'SUPPORTABLE_WITH_CONTEXT','reasons':['direct_user_confirmed_skill_only'],'historical_use_established':False}
        if contains(support_text,text):
            return {'classification':'SAFE','reasons':['verified_inventory_skill'],'historical_use_established':False}
        return {'classification':'PROHIBITED','reasons':['market_or_unverified_skill_is_not_candidate_evidence'],'historical_use_established':False}
    if not source_ids or not support_text: prohibited.append('missing_evidence_owner')
    supported_numbers,bad_numbers=truth.numbers_supported(text,support_text)
    if bad_numbers: prohibited.append('unsupported_numeric_claim:'+','.join(bad_numbers))
    for term in risk_terms:
        if contains(text,term) and not owner_supports_term(support_text,term):
            prohibited.append('historical_term_without_owner_evidence:'+term)
    for term in market_terms:
        if contains(text,term) and not owner_supports_term(support_text,term) and norm(term) not in {norm(x) for x in confirmed_terms}:
            prohibited.append('market_only_claim:'+term)
    for name,pattern in DANGEROUS.items():
        for m in re.finditer(pattern,text,re.I):
            if not contains(support_text,m.group()): weak.append('unsupported_'+name+':'+m.group())
    if re.search(r'\b(?:synthetic|hypothetical|modeled|simulated|forecast)\b',support_text,re.I):
        if re.search(r'\b(?:saved|generated revenue|increased revenue|reduced costs|realized|production deployment)\b',text,re.I) and not re.search(r'\b(?:synthetic|hypothetical|modeled|simulated|forecast)\b',text,re.I):
            prohibited.append('modeled_scope_claimed_as_realized_outcome')
    shared=tokens(text)&tokens(support_text)
    if len(tokens(text))>=5 and len(shared)<3: weak.append('insufficient_explainable_source_context')
    classification='PROHIBITED' if prohibited else 'WEAK' if weak else 'SAFE'
    if context in {'summary','future_transfer'} and classification=='SAFE':
        classification='SUPPORTABLE_WITH_CONTEXT'; reasons.append('general_capability_or_explicit_transfer_not_historical_proof')
    return {'classification':classification,'reasons':prohibited+weak+reasons or ['source_bound_explainable_claim'],
            'evidence_owners':list(source_ids),'explainability_terms':sorted(shared)[:12],
            'historical_use_established':classification=='SAFE' and context in {'experience','project','cover_history'}}

def confirmed_skills(facts,overrides,assumed):
    terms=set()
    if facts.get('source_authority',{}).get('direct_user_confirmed') is True:
        terms.update(facts.get('core_proficiency',{}));terms.update(facts.get('skill_duration_years',{}))
    cap=overrides.get('capability_status_override',{})
    if cap.get('authority')=='DIRECT_USER_CORRECTION' and cap.get('all_assumed_market_coverage_capabilities_are_actual_user_skills') is True:
        for registry,field in [('explicit_skill_registry','canonical_term'),('skill_family_registry','family'),('deep_capability_registry','term')]:
            terms.update(x[field] for x in assumed.get(registry,[]) if isinstance(x,dict) and x.get(field))
        # Compound source labels represent separately confirmed capabilities.
        # Normalize only existing source terms; a plan or JD cannot grant facts.
        from careerops_skills_stack import components, canonical
        for profile in assumed.get('role_coverage_profiles', []):
            for section in profile.get('deep_capability_sections', []):
                terms.update(section.get('items', []))
        terms.update(canonical(part) for term in list(terms) for part in components(term))
    return terms

def source_for(ids,blocks,overrides):
    parts=[blocks[x] for x in ids if x in blocks]
    if any(x in overrides.get('employment_provenance_attestation',{}).get('entities',{}) for x in ids):
        parts.append(truth.employment_override_text(overrides))
    rn=overrides.get('historical_work_attestation',{})
    for x in ids:
        if x in rn.get('roles',{}):
            parts.append(json.dumps({'organization':rn.get('organization'),'role':rn['roles'][x]},ensure_ascii=False))
    return '\n'.join(parts)

def evaluate(content,claim_map,truth_report,selection,inventory,facts,overrides,assumed,skills_plan,cover=None,cover_plan=None):
    blocks=truth.parse_blocks(inventory);confirmed=confirmed_skills(facts,overrides,assumed)
    risk={x.get('term','') for x in skills_plan.get('ranked_skill_candidates',[]) if isinstance(x,dict)}
    risk.update(facts.get('core_proficiency',{}));risk.discard('')
    market={x.get('term','') for x in skills_plan.get('ranked_skill_candidates',[]) if 'ROUTED_ROLE_MARKET_PRIOR' in x.get('provenance',[]) and x.get('term')}
    selected={x['block_id']:x for x in selection.get('selected_experience_blocks',[]) if x.get('block_id')}
    mapped=Counter((x.get('location'),x.get('text')) for x in claim_map.get('claims',[]))
    claims={}
    for x in claim_map.get('claims',[]): claims.setdefault((x.get('location'),x.get('text')),[]).append(x)
    rows=[];errors=[];expected=[]
    if truth_report.get('gate')!='PASS': errors.append('original_truth_gate_not_pass')
    def add(text,location,context,ids,support,require_map=True):
        entries=claims.get((location,text),[])
        valid=(not require_map or (len(entries)==1 and entries[0].get('status') in SUPPORTED and set(entries[0].get('source_entities',[]))==set(ids)))
        if require_map: expected.append((location,text))
        if any(x not in blocks for x in ids): valid=False
        result=classify_material_claim(text,context=context,support_text=support,truth_supported=valid,source_ids=ids,confirmed_terms=confirmed,risk_terms=risk if context in {'experience','project','cover_history'} else (),market_terms=market)
        rows.append({'location':location,'text':text,**result})
    for match in re.finditer(r'(\d+)\s+years?\s+(?:of\s+)?(?:(?:experience|expertise|proficiency)\s+(?:with|in)\s+)?([A-Za-z][A-Za-z +/#-]{0,35})',content.get('summary',''),re.I):
        duration,tail=match.groups()
        matches=[term for term in facts.get('skill_duration_years',{}) if contains(tail,term)]
        if not matches or not all(facts['skill_duration_years'][term].get('years')==float(duration) for term in matches):
            errors.append('skill_duration_not_bound_to_confirmed_skill:'+match.group())
    allids=next((x.get('source_entities',[]) for x in claim_map.get('claims',[]) if x.get('location')=='summary'),[])
    summarysupport=source_for(allids,blocks,overrides)+'\n'+json.dumps(facts)+'\n'+json.dumps({'confirmed_skills':sorted(confirmed)})
    add(content.get('summary',''),'summary','summary',allids,summarysupport)
    for exp in content.get('experience',[]):
        owner=selected.get(exp.get('block_id'),{});ids=owner.get('evidence_ids',[])
        if any(norm(exp.get(k,''))!=norm(owner.get(v,'')) for k,v in [('company','organization'),('title','title'),('dates','period')]): errors.append('experience_identity_mismatch:'+str(exp.get('block_id')))
        for bullet in exp.get('bullets',[]): add(bullet,'experience.'+str(exp.get('block_id')),'experience',ids,source_for(ids,blocks,overrides))
    for project in content.get('projects',[]):
        ids=[project.get('entity_id')]
        for bullet in project.get('bullets',[]): add(bullet,'project.'+str(project.get('entity_id')),'project',ids,source_for(ids,blocks,overrides))
    if Counter(expected)!=mapped: errors.append('claim_map_not_exact_current_candidate')
    if not content.get('experience') or not content.get('projects'): errors.append('missing_material_claim_sections')
    for line in content.get('skills',[]):
        for term in line.get('terms',[]): rows.append({'location':'skills.'+str(line.get('category')),'text':term,**classify_material_claim(term,context='skill',support_text=inventory,confirmed_terms=confirmed)})
    if not content.get('skills'): errors.append('missing_skills')
    # Education is primary candidate data, independent of selected project evidence.
    education=norm(json.dumps(facts.get('education',{})))
    for row in content.get('education',[]):
        for key,value in row.items():
            check=str(value).replace('/4.00','') if key=='gpa' else str(value)
            if norm(check) not in education: errors.append('education_not_bound_to_primary_facts:'+key)
    if cover is not None:
        plan=cover_plan or {}; primary=plan.get('primary_evidence',{}).get('evidence_id');secondary=plan.get('secondary_evidence',{})
        ids=[primary]+([secondary.get('evidence_id')] if secondary.get('use_secondary_story') else [])
        if cover.get('primary_evidence_ids')!=[primary] or set(cover.get('secondary_evidence_ids',[]))!=set(ids[1:]): errors.append('cover_evidence_owner_mismatch')
        support=source_for(ids,blocks,overrides)
        for i,paragraph in enumerate(cover.get('paragraphs',[])):
            # Job interest and explicitly future-facing transfer are not historical claims.
            for j,sentence in enumerate(re.split(r'(?<=[.!?])\s+',paragraph)):
                future=bool(re.search(r'\b(?:would|could|hope to|interests me|thank you)\b',sentence,re.I))
                material=bool(re.search(r'\b(?:built|developed|implemented|organized|chose|applied|selected|managed|led|created|delivered|reduced|increased|\d)\b',sentence,re.I))
                past=bool(re.search(r'\b(?:built|developed|implemented|organized|chose|applied|selected|managed|led|created|delivered|reduced|increased|used)\b',sentence,re.I))
                if material and (not future or past): add(sentence,f'cover.{i}.{j}','cover_history',ids,support,False)
                elif future:
                    rows.append({'location':f'cover.{i}.{j}','text':sentence,'classification':'SUPPORTABLE_WITH_CONTEXT','reasons':['explicit_future_transfer_or_interest_not_historical_evidence'],'historical_use_established':False})
    counts=Counter(x['classification'] for x in rows)
    blocked=[x for x in rows if x['classification'] not in ALLOWED]
    return {'schema_version':'interview-defensibility-v1','gate':'PASS' if not errors and not blocked else 'FAIL',
      'classifications':dict(counts),'claims':rows,'errors':errors,'blocking_claim_count':len(blocked),
      'truth_gate_weakened':False,'market_prior_is_candidate_evidence':False,'direct_proficiency_proves_historical_use':False,
      'may_mutate_source':False,'may_release':False,'model_calls':0}

def run_gate(runtime,source_dir=None):
    runtime=Path(runtime);source_dir=Path(source_dir or source_dir(ROOT))
    paths={'content':runtime/'generated_resume_content_pair_candidate.json','claim_map':runtime/'claim_map.json','truth_report':runtime/'truth_gate.json',
      'selection':runtime/'experience_selection.json','inventory':source_dir/'verified_evidence_inventory.md','facts':source_dir/'candidate_facts.json',
      'overrides':source_dir/'candidate_attestations.json','assumed':source_dir/'assumed_market_coverage.json','skills_plan':runtime/'technical_skills_plan.json',
      'cover':runtime/'generated_cover_letter_pair_candidate.json','cover_plan':runtime/'cover_plan.json'}
    try:
        bindings={str(p):digest(p) for p in paths.values()}
        args={k:(p.read_text() if k=='inventory' else load(p)) for k,p in paths.items()}
        report=evaluate(**args)
        if any(digest(p)!=bindings[str(p)] for p in paths.values()): raise ValueError('INPUT_CHANGED_DURING_VALIDATION')
        report['input_sha256']=bindings
    except (OSError,ValueError,KeyError,TypeError) as error:
        report={'schema_version':'interview-defensibility-v1','gate':'FAIL','errors':[str(error)],'model_calls':0,'may_release':False}
    (runtime/'interview_defensibility_report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--runtime',required=True);args=parser.parse_args()
    report=run_gate(args.runtime);print('INTERVIEW DEFENSIBILITY:',report['gate']);return 0 if report['gate']=='PASS' else 2
if __name__=='__main__': raise SystemExit(main())
