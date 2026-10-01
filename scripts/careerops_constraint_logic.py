"""Conservative typed logic for explicit tool tenure alternatives and examples."""
import re

def tool_tenure_logic(text,skill_terms,aliases):
 text=text.casefold()
 optional=re.search(r"\b(?:e\.g\.(?=\s)|such as\b|for example\b|including examples\b|ideally\b|preferably\b|preferred\b|nice.to.have\b)",text)
 core=text[:optional.start()] if optional else text
 occurrences=[]
 for skill in skill_terms:
  hits=[m for alias in aliases.get(skill,[skill]) for m in re.finditer(r"(?<![a-z0-9])"+re.escape(alias.casefold())+r"(?![a-z0-9])",core)]
  if hits:
   hit=min(hits,key=lambda x:x.start());occurrences.append((hit.start(),hit.end(),skill))
 occurrences.sort();branches=[];current=[];ambiguous=False
 for index,(start,end,skill) in enumerate(occurrences):
  if index:
   connector=core[occurrences[index-1][1]:start]
   if '(' in connector or ')' in connector:ambiguous=True
   pure=re.fullmatch(r"[\s,()]*?(?:(?:and/or|and|or)[\s,()]*)?",connector)
   if pure and re.search(r"\bor\b",connector):
    branches.append(current);current=[]
   elif not pure:
    ambiguous=True
  current.append(skill)
 if current:branches.append(current)
 # Comma lists ending in 'or' express alternatives for all list items.
 if len(occurrences)>2:
  connectors=[core[occurrences[i-1][1]:occurrences[i][0]] for i in range(1,len(occurrences))]
  if re.search(r"\bor\b",connectors[-1]) and all(re.fullmatch(r"[\s,()]*",x) for x in connectors[:-1]):branches=[[x[2]] for x in occurrences]
 return {'mandatory_skills':[x[2] for x in occurrences],'alternatives':branches,'ambiguous':ambiguous,'example_or_optional_terms':[x for x in skill_terms if x not in [v[2] for v in occurrences]],'basis':'LITERAL_SCOPED_TOOL_TENURE_LOGIC'}

def evaluate_tool_tenure(logic,checks):
 statuses={x['skill']:x['status'] for x in checks}
 if not logic['mandatory_skills']:return None
 if logic['ambiguous']:return 'PASS' if all(statuses.get(x)=='PASS' for x in logic['mandatory_skills']) else 'REVIEW_REQUIRED'
 return 'PASS' if any(all(statuses.get(x)=='PASS' for x in branch) for branch in logic['alternatives']) else 'REVIEW_REQUIRED'

EDUCATION_FIELDS=['computer science','information systems','data science','biostatistics','statistics','mathematics','economics','engineering','public health','epidemiology','accounting','finance','marketing','business']
def education_field_support(text,facts,minimum_rank=0):
 text=str(text);match=re.search(r"(?:degree|bachelor.{0,8}|master.{0,8}|ph\.?d\.?|m\.?s\.?|b\.?s\.?)\s+(?:degree\s+)?in\s+([^.;]+)",text,re.I)
 if not match:return None
 scope=re.split(r'\b(?:with|plus|and\s+(?:\d+|at least)|experience|preferred)\b',match.group(1),maxsplit=1,flags=re.I)[0]
 fields=[x for x in EDUCATION_FIELDS if re.search(r'(?<!\w)'+re.escape(x)+r'(?!\w)',scope,re.I)]
 related=bool(re.search(r'\brelated\s+(?:field|discipline|area)|\bquantitative\s+(?:field|discipline)|\bSTEM\b',scope,re.I))
 ranks={'bachelor':1,'bachelors':1,'master':2,'masters':2,'doctorate':3,'phd':3}
 eligible=[x for x in facts.get('education',[]) if ranks.get(str(x.get('degree_level','')).casefold(),0)>=minimum_rank]
 matches=[]
 for row in eligible:
  title=str(row.get('degree',''))+' '+str(row.get('resume_degree',''))
  exact=[x for x in fields if re.search(r'(?<!\w)'+re.escape(x)+r'(?!\w)',title,re.I)]
  quantitative=related and any(x in title.casefold() for x in ['data science','statistics','mathematics','engineering','computer science','economics'])
  if exact or quantitative:matches.append({'degree':row.get('degree'),'matched_fields':exact,'explicit_related_field_basis':quantitative})
 return {'constraint_type':'education_field','status':'PASS' if matches else 'REVIEW_REQUIRED','required_source_scope':scope.strip(),'required_fields':fields,'explicit_related_field_allowed':related,'same_record_meets_degree_level':True,'support':matches,'reason_code':'VERIFIED_DEGREE_FIELD_SUPPORTED' if matches else 'EDUCATION_FIELD_UNVERIFIED'}
