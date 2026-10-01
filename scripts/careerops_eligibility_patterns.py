"""Explicit currently-held clearance syntax, shared by extraction and eligibility."""
import re
ACTIVE_CLEARANCE_PATTERN=(r"\b(?:active|current)\s+(?:top\s+secret(?:\s*/\s*sci|\s+sci)?|ts\s*/\s*sci|secret)\s*(?:\(\s*or\s+higher\s*\)\s*)?(?:security\s+)?clearance\b"
 r"|\bmust\s+(?:currently\s+|already\s+)?(?:hold|possess|maintain)\s+(?:an?\s+)?(?:active\s+|current\s+)?(?:top\s+secret|secret)(?:\s+(?:security\s+)?clearance)?\b"
 r"|\binterim\s+(?:top\s+secret|secret)(?:\s+(?:security\s+)?clearance)?\s+(?:is\s+)?(?:acceptable|required)\b")
def active_clearance_requirement(text):
 value=str(text or '')
 if re.search(r'\b(?:ability|eligible|eligibility)\s+to\s+obtain|\bnot\s+required|\bno\s+clearance\s+required',value,re.I):return False
 return bool(re.search(ACTIVE_CLEARANCE_PATTERN,value,re.I))
