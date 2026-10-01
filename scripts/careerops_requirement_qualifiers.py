"""Explicit JD qualifier contracts; candidate evidence must retain their scope."""
import re

def qualifier_contract(text):
 text=str(text or '');mandatory=re.split(r'\b(?:preferably|preferred|nice to have|ideally|desirably)\b',text,flags=re.I)[0]
 result=[]
 patterns=[
  ('domain',r'\b(?:experience|background|worked|working)[^.;]{0,70}?\b(DTC|direct.to.consumer|e.commerce|ecommerce|insurance|clinical research|healthcare|health care|medical claims)\b'),
  ('industry',r'\b(?:within|in)\s+(?:the\s+)?([^.;]{3,75}?)\s+industry\b'),
  ('domain',r'\bfinancial services\b'),
  ('domain',r'\b(?:F2P|free.to.play|mobile gaming|Live ?Ops|monetization)\b'),
  ('method',r'\b(?:causal inference|causal experimentation|randomized (?:controlled )?(?:trials?|experiments?)|experimental design|hypothesis testing|A/B testing)\b'),
  ('environment',r'\b(?:high.volume|production|regulated)\s+(?:environment|systems?)\b'),
 ]
 for kind,pattern in patterns:
  for m in re.finditer(pattern,mandatory,re.I):
   phrase=m.group(1).strip() if m.lastindex else m.group().strip()
   # Enumerated occupational alternatives preceding the industry phrase
   # share the terminal industry qualifier, rather than defining its name.
   if kind=='industry':phrase=re.split(r'\bwithin\s+(?:the\s+)?',phrase,flags=re.I)[-1].strip()
   if kind=='industry' and len(phrase.split())>5:continue
   if not any(x['phrase'].casefold()==phrase.casefold() for x in result):result.append({'kind':kind,'phrase':phrase,'source_quote':m.group(),'mandatory':True})
 return result

def qualifier_supported(qualifier,evidence):
 phrase=qualifier['phrase'];variants=[phrase]
 if re.fullmatch(r'DTC|direct.to.consumer',phrase,re.I):variants+=['DTC','direct-to-consumer','direct to consumer']
 if re.fullmatch(r'e.commerce|ecommerce',phrase,re.I):variants+=['ecommerce','e-commerce','e commerce']
 if re.fullmatch(r'healthcare|health care',phrase,re.I):variants+=['hospital','emergency-department','emergency department','clinical research','patient data']

 if re.search(r'financial services',phrase,re.I):variants+=['financial-services','financial service']
 if re.search(r'A/B testing',phrase,re.I):variants+=['A/B test','randomized experiment']
 if re.search(r'Live ?Ops',phrase,re.I):variants+=['live operations','LiveOps','live ops']
 return any(re.search(r'(?<!\w)'+re.escape(v).replace(r'\ ',r'[\s-]+')+r'(?!\w)',str(evidence),re.I) for v in variants)

def evidence_qualifiers(text,evidence):
 qualifiers=qualifier_contract(text);unsupported=[q for q in qualifiers if not qualifier_supported(q,evidence)]
 return {'status':'QUALIFIER_UNVERIFIED' if unsupported else 'SUPPORTED','required_qualifiers':qualifiers,'unsupported_qualifiers':unsupported,'core_match_is_full_coverage':not unsupported}
