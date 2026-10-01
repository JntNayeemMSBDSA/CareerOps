"""Normalize copied URL wrappers without guessing a different target."""
import re,html
from urllib.parse import urlsplit

def normalize_job_url(value):
 original=str(value or '').strip();v=html.unescape(original).replace('\\/','/')
 m=re.fullmatch(r'\[([^\]]+)\]\((https?://[^\s]+)\)',v,re.I)
 if m:
  label,target=m.groups()
  if re.match(r'^https?://',label,re.I) and label.rstrip('/')!=target.rstrip('/'):
   raise ValueError('Markdown URL label and target conflict')
  v=target
 v=v.strip('<> \t\r\n')
 parsed=urlsplit(v)
 if parsed.scheme.lower() not in {'http','https'} or not parsed.hostname or re.search(r'\s',v):
  raise ValueError('Job URL requires one coherent http/https target')
 return v
