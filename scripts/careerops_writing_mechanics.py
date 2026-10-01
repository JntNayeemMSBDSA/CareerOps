"""Writing mechanics shared by independent Human and Cover quality gates."""
import re,statistics
from collections import Counter

def profile(paragraphs,*,keywords=()):
 paragraphs=[str(x) for x in paragraphs if str(x).strip()]
 sentences=[s.strip() for p in paragraphs for s in re.split(r'(?<=[.!?])\s+',p) if len(re.findall(r'\b\w+\b',s))>=4]
 lengths=[len(re.findall(r'\b\w+\b',s)) for s in sentences]
 starts=[' '.join(re.findall(r"[A-Za-z']+",s.lower())[:2]) for s in sentences]
 repeated=[{'opening':k,'count':v} for k,v in Counter(starts).items() if v>=3]
 cadence_cv=statistics.pstdev(lengths)/statistics.mean(lengths) if len(lengths)>1 else 1.0
 low_cadence=len(lengths)>=6 and cadence_cv<0.18
 transitions=re.findall(r'\b(?:that combination|this work taught me|i would apply|i bring)\b',' '.join(paragraphs),re.I)
 repeated_transitions=[{'phrase':k,'count':v} for k,v in Counter(x.lower() for x in transitions).items() if v>=2]
 stacks=[]
 for s in sentences:
  if re.search(r'\b(?:would|will|could|plan to)\b',s,re.I):
   hits=sorted({str(k) for k in keywords if len(str(k))>=2 and re.search(r'(?<!\w)'+re.escape(str(k))+r'(?!\w)',s,re.I)})
   if len(hits)>=4:stacks.append({'sentence':s,'terms':hits})
 abstract=bool(paragraphs and re.match(r'^(?:my (?:background|experience)|i bring|i am (?:a |an )?(?:results.driven|passionate)|with (?:a |an )?(?:strong|proven|extensive) background)',paragraphs[0],re.I))
 penalty=min(30,sum(6+2*max(0,x['count']-3) for x in repeated)+6*int(low_cadence)+4*len(repeated_transitions)+5*len(stacks)+4*int(abstract))
 return {'score':100-penalty,'penalty':penalty,'sentence_count':len(sentences),'sentence_lengths':lengths,'cadence_coefficient_of_variation':round(cadence_cv,4),'uniform_cadence':low_cadence,'repeated_syntax_openings':repeated,'repeated_transitions':repeated_transitions,'abstract_opening':abstract,'future_keyword_stacks':stacks,'feature_based':True,'models_called':0}
