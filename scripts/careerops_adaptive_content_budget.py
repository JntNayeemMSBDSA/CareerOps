"""Allocate finite page space using current verified coverage, never slot position."""
import re
from collections import Counter
def allocate(experience,projects,requirements,visible_skills):
 blocks=experience.get('selected_experience_blocks',[]); projs=projects.get('selected_projects',[])
 priorities={r['requirement_id']:r.get('priority','P2') for r in requirements.get('requirements',[])}
 rows=[]
 for kind,items,key in [('experience',blocks,'block_id'),('project',projs,'entity_id')]:
  for item in items:
   ids=set(item.get('supported_p0_p1_ids',[])); rows.append({'kind':kind,'id':re.sub(r'[^A-Z0-9]','',item[key].upper()) if kind=='experience' else item[key],'ids':ids,'item':item,'count':1})
 frequency=Counter(rid for row in rows for rid in row['ids'])
 for row in rows:
  weight=sum((5 if priorities.get(rid)=='P0' else 4)/frequency[rid] for rid in row['ids'])
  depth=min(len(row['item'].get('requirement_contributions',[])),6) if row['kind']=='experience' else min(row['item'].get('method_bullet_count',0),6)
  row['value']=weight+depth*.3
 # Two body lines per bullet at comfortable margins, with extra reserve for long Skills.
 skill_chars=len(str(visible_skills)); total_budget=10 if skill_chars>850 else 12
 while sum(x['count'] for x in rows)<total_budget:
  candidates=[x for x in rows if x['count']<(3 if x['kind']=='experience' else 2) and x['ids']]
  if not candidates:break
  best=max(candidates,key=lambda x:(x['value']/(x['count']**1.8),len(x['ids']),x['id']))
  best['count']+=1
 return {'experience_bullet_counts':{x['id']:x['count'] for x in rows if x['kind']=='experience'},'project_bullet_counts':{x['id']:x['count'] for x in rows if x['kind']=='project'},'total_bullet_budget':total_budget,'allocated_bullets':sum(x['count'] for x in rows),'max_bullet_words':34,'basis':'CURRENT_P0_P1_COVERAGE_UNIQUENESS_SUPPORTED_DEPTH_AND_PAGE_SPACE','rationale':[{'id':x['id'],'kind':x['kind'],'bullet_count':x['count'],'coverage_value':round(x['value'],3),'supported_requirement_ids':sorted(x['ids'])} for x in rows]}


def select_existing_pair(content, experience, projects, requirements, visible_skills):
 """Render a truthful subset of a completed legacy pair without a new writer.
 Whole audited bullets remain byte-identical; original response is retained.
 This does not grant automatic release or alter the writer contract.
 """
 import copy
 result=copy.deepcopy(content);budget=allocate(experience,projects,requirements,visible_skills)
 source_terms=[]
 for row in requirements.get('requirements',[]):
  if row.get('priority') in {'P0','P1'}:
   terms=set(re.findall(r'[a-z][a-z0-9+#-]{2,}',row.get('exact_quote','').lower()))-{'the','and','with','for','that','this','will','have','your','from','such','data'}
   source_terms.append((5 if row.get('priority')=='P0' else 3,terms))
 omitted=[];retained=[]
 for kind,key,counts in [('experience','block_id',budget['experience_bullet_counts']),('projects','entity_id',budget['project_bullet_counts'])]:
  for block in result.get(kind,[]):
   identity=re.sub(r'[^A-Z0-9]','',block[key].upper()) if kind=='experience' else block[key]
   limit=counts.get(identity,1)
   original=block.get('bullets',[])
   scored=[]
   for index,text in enumerate(original):
    tokens=set(re.findall(r'[a-z][a-z0-9+#-]{2,}',text.lower()))
    score=sum(weight*len(tokens&terms)/max(1,len(terms)) for weight,terms in source_terms)
    scored.append((score/max(1,len(text.split()))**.35,index))
   selected={index for _,index in sorted(scored,reverse=True)[:limit]}
   block['bullets']=[text for index,text in enumerate(original) if index in selected]
   for index,text in enumerate(original):(retained if index in selected else omitted).append({'id':identity,'index':index,'text':text})
 return result,{'status':'PASS','mode':'WHOLE_AUDITED_BULLET_SUBSET_FOR_UNRELEASED_RENDER','original_pair_unchanged':True,'text_rewritten':False,'new_model_calls':0,'release_authorized':False,'budget':budget,'retained':retained,'omitted_but_preserved_in_original_pair':omitted}
