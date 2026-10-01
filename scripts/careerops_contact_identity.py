"""Contact targets preserve URL authority independently of display labels."""
from pathlib import Path
import subprocess,zipfile,re,html,xml.etree.ElementTree as ET

def link_target(value):
    if isinstance(value,dict):
        value=next((value[k] for k in ('url','href','link') if value.get(k)),None)
    value=str(value or '').strip()
    return value if value.startswith(('https://','http://','mailto:')) else ''

def artifact_contact_targets(path):
    path=Path(path)
    if path.suffix.lower()=='.docx':
        with zipfile.ZipFile(path) as z:
            root=ET.fromstring(z.read('word/_rels/document.xml.rels'))
            return [row.get('Target') for row in root if row.get('TargetMode')=='External']
    if path.suffix.lower()=='.pdf':
        result=subprocess.run(['pdftohtml','-stdout','-s','-i',str(path)],capture_output=True,text=True,timeout=20)
        if result.returncode:raise ValueError('PDF contact extraction failed')
        return [html.unescape(value) for value in re.findall(r'href="([^"]+)"',result.stdout)]
    raise ValueError('Unsupported contact artifact')

def verify_contacts(paths,candidate):
    expected=[link_target(candidate.get('github')),link_target(candidate.get('linkedin')),'mailto:'+str(candidate.get('email') or '').strip()]
    issues=[];rows=[]
    if any(not value or value=='mailto:' for value in expected):issues.append('Missing canonical contact target')
    for path in paths:
        try:
            targets=artifact_contact_targets(path)
            missing=[value for value in expected if value not in targets]
            if missing:issues.append(str(path)+': missing or incorrect '+', '.join(missing))
            rows.append({'path':str(path),'missing':missing})
        except (OSError,ValueError,TypeError,zipfile.BadZipFile,ET.ParseError,KeyError,subprocess.TimeoutExpired) as exc:
            issues.append(str(path)+': '+type(exc).__name__)
    return {'pass':not issues and len(rows)==4,'expected_targets':expected,'artifacts':rows,'issues':issues,'model_calls':0}
