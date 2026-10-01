"""Deterministic rendered DOCX page/header audit. Never changes content."""
from pathlib import Path
import subprocess,shutil,tempfile,json,hashlib,re,zipfile,xml.etree.ElementTree as ET,os

def normal(s):return re.sub(r"\s+"," ",s).strip().casefold()
def audit_docx_layout(path,runtime):
    path=Path(path);runtime=Path(runtime);out=runtime/"docx_layout"/path.stem;out.mkdir(parents=True,exist_ok=True)
    report_path=out/"layout_audit.json"
    backend=shutil.which("libreoffice") or shutil.which("soffice")
    if not backend:raise SystemExit("RENDERER_DOCX_LAYOUT_BACKEND_UNAVAILABLE")
    env=os.environ.copy()
    pdf=out/(path.stem+".pdf")
    if pdf.exists():pdf.unlink()
    with tempfile.TemporaryDirectory(prefix="docx_profile_") as profile:
        p=subprocess.run([backend,"-env:UserInstallation="+Path(profile).as_uri(),"--headless","--convert-to","pdf","--outdir",str(out),str(path)],env=env,text=True,capture_output=True,timeout=60)
    if p.returncode or not pdf.exists():raise SystemExit("RENDERER_DOCX_LAYOUT_CONVERSION_FAILED: "+p.stderr[-500:])
    info=subprocess.run(["pdfinfo",str(pdf)],capture_output=True,text=True,check=True).stdout
    pages=int(re.search(r"Pages:\s+(\d+)",info)[1])
    bbox=subprocess.run(["pdftotext","-bbox-layout",str(pdf),"-"],capture_output=True,text=True,check=True).stdout
    root=ET.fromstring(bbox);words=[];clipped=[]
    page_number=0
    for page in root.iter():
        if page.tag.endswith("}page"):
            page_number+=1
            width=float(page.attrib["width"]);height=float(page.attrib["height"])
            for w in page.iter():
                if w.tag.endswith("}word"):
                    x0,y0,x1,y1=[float(w.attrib[k]) for k in ['xMin','yMin','xMax','yMax']]
                    words.append((page_number,y0,x0,w.text or ""))
                    if x0<0 or y0<0 or x1>width or y1>height:clipped.append(w.text)
    # Combine visually aligned words even when LibreOffice emits date columns in separate blocks.
    rows=[]
    for number,y,x,t in sorted(words):
        if not rows or rows[-1][0]!=number or abs(rows[-1][1]-y)>2:rows.append([number,y,[]])
        rows[-1][2].append((x,t))
    lines=[normal(" ".join(t for x,t in sorted(row))) for number,y,row in rows]
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    with zipfile.ZipFile(path) as z:doc=ET.fromstring(z.read('word/document.xml'))
    paragraphs=doc.findall('.//w:body/w:p',ns);headers=[]
    for index,para in enumerate(paragraphs):
        if index<2 or para.find('.//w:tab',ns) is not None:
            text=''.join((node.text or '') if node.tag.endswith('}t') else ' ' for node in para.iter() if node.tag.endswith('}t') or node.tag.endswith('}tab'))
            if normal(text):headers.append(normal(text))
    header_checks=[{'text':h,'one_visual_line':any(h in line for line in lines)} for h in headers]
    checks={'one_page':pages==1,'no_physical_clipping':not clipped,'critical_headers_one_line':all(x['one_visual_line'] for x in header_checks)}
    report={'schema_version':'careerops-docx-layout-audit-v1','source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'backend':str(Path(backend).resolve()),'pages':pages,'checks':checks,'headers':header_checks,'content_changed':False,'model_calls':0,'pass':all(checks.values())}
    report_path.write_text(json.dumps(report,indent=2)+'\n')
    if not report['pass']:raise SystemExit("RENDERER_DOCX_LAYOUT_FAILED: "+json.dumps(checks))
    return report
