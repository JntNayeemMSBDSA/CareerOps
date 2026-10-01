"""Independent physical PDF/DOCX geometry parity; no content or release authority."""
from pathlib import Path
import json,hashlib,zipfile,xml.etree.ElementTree as ET
from collections import Counter
import subprocess,re
from careerops_docx_layout_audit import audit_docx_layout

def measure(path):
 info=subprocess.run(['pdfinfo',str(path)],capture_output=True,text=True,check=True).stdout
 pages=int(re.search(r'Pages:\s+(\d+)',info)[1]);size=re.search(r'Page size:\s+([\d.]+) x ([\d.]+)',info)
 bbox=subprocess.run(['pdftotext','-bbox',str(path),'-'],capture_output=True,text=True,check=True).stdout
 xml=ET.fromstring(bbox[bbox.index('<html'):]);words=[x for x in xml.iter() if x.tag.endswith('}word') or x.tag=='word']
 box=[min(float(w.attrib['xMin']) for w in words),min(float(w.attrib['yMin']) for w in words),max(float(w.attrib['xMax']) for w in words),max(float(w.attrib['yMax']) for w in words)] if words else None
 html=subprocess.run(['pdftohtml','-xml','-stdout','-i','-zoom','2',str(path)],capture_output=True,text=True,check=True).stdout
 tree=ET.fromstring(html[html.index('<?xml'):]);fonts={x.attrib['id']:float(x.attrib['size'])/2 for x in tree.iter('fontspec')};weighted=Counter()
 for x in tree.iter('text'):weighted[fonts[x.attrib['font']]]+=len(''.join(x.itertext()))
 return {'pages':pages,'width_pt':float(size[1]),'height_pt':float(size[2]),'ink_bounds_pt':box,'dominant_font_pt':weighted.most_common(1)[0][0] if weighted else None,'font_sizes_weighted':dict(weighted),'font_measurement':'POPPLER_XML_HALF_POINT_MEASUREMENT'}

def audit_pair_geometry(pdf,docx,runtime,kind):
 pdf=Path(pdf);docx=Path(docx);runtime=Path(runtime)
 layout=audit_docx_layout(docx,runtime)
 converted=runtime/'docx_layout'/docx.stem/(docx.stem+'.pdf')
 a=measure(pdf);b=measure(converted)
 ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
 with zipfile.ZipFile(docx) as archive:xml=ET.fromstring(archive.read('word/document.xml'))
 margin=xml.find('.//w:sectPr/w:pgMar',ns)
 margins={key:int(margin.attrib['{'+ns['w']+'}'+key])/1440 for key in ['top','bottom','left','right']}
 def inside(m):
  box=m['ink_bounds_pt']
  return bool(box and box[0]>=margins['left']*72-1.5 and box[1]>=margins['top']*72-1.5 and box[2]<=m['width_pt']-margins['right']*72+1.5 and box[3]<=m['height_pt']-margins['bottom']*72+1.5)
 checks={'professional_margin_floor':min(margins.values())>=0.4,'both_one_page':a['pages']==b['pages']==1,'both_letter':all(abs(m['width_pt']-612)<1 and abs(m['height_pt']-792)<1 for m in [a,b]),'pdf_respects_docx_margins':inside(a),'rendered_docx_respects_own_margins':inside(b),'body_font_parity':a['dominant_font_pt'] is not None and b['dominant_font_pt'] is not None and abs(a['dominant_font_pt']-b['dominant_font_pt'])<=0.35,'vertical_footprint_parity':a['ink_bounds_pt'] is not None and b['ink_bounds_pt'] is not None and abs((a['ink_bounds_pt'][3]-a['ink_bounds_pt'][1])-(b['ink_bounds_pt'][3]-b['ink_bounds_pt'][1]))<=36,'docx_headers_and_clipping':layout['pass']}
 layout_path=runtime/('cover_adaptive_layout_report.json' if kind=='cover' else 'adaptive_layout_report.json')
 if layout_path.is_file():
  planned=json.loads(layout_path.read_text())
  expected=planned.get('geometry',{}).get('margins_in') if kind=='cover' else {'left':planned.get('fixed_geometry',{}).get('left_px',0)/96,'right':planned.get('fixed_geometry',{}).get('right_px',0)/96}
  checks['shared_margin_contract_parity']=bool(expected) and all(abs(margins[k]-v)<=.012 for k,v in expected.items())
  checks['horizontal_ink_parity']=bool(a['ink_bounds_pt'] and b['ink_bounds_pt']) and max(abs(a['ink_bounds_pt'][i]-b['ink_bounds_pt'][i]) for i in (0,2))<=2
 report={'schema_version':'careerops-pdf-docx-physical-parity-v1','kind':kind,'pass':all(checks.values()),'checks':checks,'docx_margins_in':margins,'pdf':a,'rendered_docx':b,'input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [pdf,docx]},'model_calls':0,'does_not_authorize_release':True}
 destination=runtime/(kind+'_physical_parity.json');destination.write_text(json.dumps(report,indent=2)+'\n')
 if not report['pass']:raise RuntimeError('PDF_DOCX_PHYSICAL_PARITY_FAILED: '+json.dumps(checks))
 return report
