"""Keep evidence facts separate from negative boundaries and targeting rules."""
import re

def positive_evidence(text):
 kept=[];excluded=False
 for line in str(text).splitlines():
  if re.match(r'^#{1,4}\s+',line):
   excluded=bool(re.search(r'claim boundaries|integrity rules|unresolved|targeting|do not claim|generation policy',line,re.I))
  if excluded:continue
  if re.search(r'\b(?:do not claim|must not claim|not advanced|not verified|unverified|unconfirmed|cannot claim|never claim)\b',line,re.I):continue
  kept.append(line)
 return '\n'.join(kept)

def source_supported_method(term,text):
 positive=positive_evidence(text).lower()
 if term.lower() == 'statistical analysis':
  return bool(re.search(r'###\s+statistical methods',positive)) and sum(x in positive for x in ['fixed effects','standard errors','regression','sensitivity analys','statistical specification']) >= 2
 return False
