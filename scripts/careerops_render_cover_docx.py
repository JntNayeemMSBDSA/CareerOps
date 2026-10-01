from careerops_config import candidate_identity
#!/usr/bin/env python3
from careerops_docx_layout_audit import audit_docx_layout

import hashlib
import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.shared import Inches, Pt


from careerops_runtime import (
    runtime_dir,
    output_dir,
)

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = runtime_dir(ROOT)
OUTPUT_ROOT = output_dir(ROOT)
SIGNATURE_IMAGE = Path(os.environ.get("CAREEROPS_SIGNATURE_IMAGE", str(ROOT / "candidate/signature.png")))

DEFAULT_COVER = (
    RUNTIME
    / "generated_cover_letter_pair_candidate.json"
)

DEFAULT_IDENTITY = (
    RUNTIME
    / "career_ops_cv_payload.json"
)

DEFAULT_GATE = (
    RUNTIME
    / "cover_gate_v2_report.json"
)


CFG = {
    # Same page geometry as CareerOps resume.
    "page_width": 8.50,
    "page_height": 11.00,
    "margin_top": 0.50,
    "margin_bottom": 0.50,
    "margin_left": 0.50,
    "margin_right": 0.50,

    # CareerOps resume identity.
    "name_font": "Times New Roman",
    "name_size": 14.0,
    "name_line": 14.5,

    "contact_font": "Times New Roman",
    "contact_size": 9.8,
    "contact_line": 10.4,

    # Cover body.
    "body_font": "Calibri",
    "body_size": 10.5,
    "body_line": 13.3,

    # Vertical rhythm mirrors verified PDF renderer.
    "header_after": 14.0,
    "date_after": 8.0,
    "recipient_after": 0.0,
    "role_after": 13.0,
    "salutation_after": 10.0,
    "body_after": 10.0,
    "closing_before": 12.0,
    "signature_after": 0.0,
}


def load_json(path):
    if not path.exists():
        raise SystemExit(
            f"Missing required file: {path}"
        )

    return json.loads(
        path.read_text(encoding="utf-8")
    )


def font_run(
    run,
    name,
    size,
    *,
    bold=None,
    underline=None,
):
    run.font.name = name
    run.font.size = Pt(size)

    if bold is not None:
        run.bold = bold

    if underline is not None:
        run.underline = underline

    rpr = run._r.get_or_add_rPr()
    fonts = rpr.rFonts

    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.insert(0, fonts)

    fonts.set(qn("w:ascii"), name)
    fonts.set(qn("w:hAnsi"), name)
    fonts.set(qn("w:eastAsia"), name)


def exact_line(paragraph, pt):
    paragraph.paragraph_format.line_spacing = Pt(pt)
    paragraph.paragraph_format.line_spacing_rule = (
        WD_LINE_SPACING.EXACTLY
    )


def add_hyperlink(
    paragraph,
    label,
    url,
    *,
    font_name,
    font_size,
    underline=True,
):
    rel = paragraph.part.relate_to(
        url,
        RELATIONSHIP_TYPE.HYPERLINK,
        is_external=True,
    )

    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), rel)

    run = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")

    fonts = OxmlElement("w:rFonts")
    fonts.set(qn("w:ascii"), font_name)
    fonts.set(qn("w:hAnsi"), font_name)
    fonts.set(qn("w:eastAsia"), font_name)
    rpr.append(fonts)

    size = OxmlElement("w:sz")
    size.set(
        qn("w:val"),
        str(round(font_size * 2)),
    )
    rpr.append(size)

    color = OxmlElement("w:color")
    color.set(qn("w:val"), "000000")
    rpr.append(color)

    underline_node = OxmlElement("w:u")
    underline_node.set(
        qn("w:val"),
        "single" if underline else "none",
    )
    rpr.append(underline_node)

    run.append(rpr)

    text_node = OxmlElement("w:t")
    text_node.text = label
    run.append(text_node)

    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def link_value(value):
    if isinstance(value, dict):
        return str(value.get("url") or "").strip()

    return str(value or "").strip()


def link_label(value, fallback):
    if isinstance(value, dict):
        return str(
            value.get("display") or fallback
        ).strip()

    return fallback


def add_contact_text(paragraph, value):
    run = paragraph.add_run(value)

    font_run(
        run,
        CFG["contact_font"],
        CFG["contact_size"],
        underline=True,
    )


def add_body_paragraph(
    doc,
    value,
    *,
    after=0,
    before=0,
    bold=False,
    justify=False,
):
    paragraph = doc.add_paragraph()

    paragraph.paragraph_format.space_before = Pt(
        before
    )
    paragraph.paragraph_format.space_after = Pt(
        after
    )

    exact_line(
        paragraph,
        CFG["body_line"],
    )

    paragraph.alignment = (
        WD_ALIGN_PARAGRAPH.JUSTIFY
        if justify
        else WD_ALIGN_PARAGRAPH.LEFT
    )

    run = paragraph.add_run(value)

    font_run(
        run,
        CFG["body_font"],
        CFG["body_size"],
        bold=bold,
    )

    return paragraph


def detroit_date():
    now = datetime.now(
        ZoneInfo("America/Detroit")
    )

    return (
        f"{now.strftime('%B')} "
        f"{now.day}, "
        f"{now.year}"
    )


def safe_output_path(raw):
    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = Path(raw).expanduser()

    if not path.is_absolute():
        path = ROOT / path

    path = path.resolve()

    try:
        path.relative_to(
            OUTPUT_ROOT.resolve()
        )
    except ValueError:
        raise SystemExit(
            "Refusing to write cover DOCX "
            f"outside active output root: {path}"
        )

    return path


def slug(value):
    result = re.sub(
        r"[^a-z0-9]+",
        "_",
        str(value or "").lower(),
    ).strip("_")

    return result or "company"


def build_document(cover, candidate, date_value):
    paragraphs = cover.get('paragraphs', [])
    if not isinstance(paragraphs, list) or len(paragraphs) != 3:
        raise SystemExit('Cover DOCX renderer requires exactly three body paragraphs.')
    doc = Document()
    section = doc.sections[0]
    section.page_width = Inches(CFG['page_width'])
    section.page_height = Inches(CFG['page_height'])
    section.top_margin = Inches(CFG['margin_top'])
    section.bottom_margin = Inches(CFG['margin_bottom'])
    section.left_margin = Inches(CFG['margin_left'])
    section.right_margin = Inches(CFG['margin_right'])
    normal = doc.styles['Normal']
    normal.font.name = CFG['body_font']
    normal.font.size = Pt(CFG['body_size'])
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.line_spacing = Pt(CFG['body_line'])
    normal.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    name = str(candidate.get('name') or candidate_identity(ROOT)['name']).strip()
    location = str(candidate.get('location') or '').strip()
    phone = str(candidate.get('phone') or '').strip()
    email = str(candidate.get('email') or '').strip()
    linkedin_raw = candidate.get('linkedin')
    github_raw = candidate.get('github')
    linkedin = link_value(linkedin_raw)
    github = link_value(github_raw)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    exact_line(p, CFG['name_line'])
    run = p.add_run(name)
    font_run(run, CFG['name_font'], CFG['name_size'], bold=True)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(CFG['header_after'])
    exact_line(p, CFG['contact_line'])
    contact_items = []
    if location:
        contact_items.append(('text', location, None))
    if phone:
        contact_items.append(('text', phone, None))
    if email:
        contact_items.append(('link', email, f'mailto:{email}'))
    if linkedin:
        contact_items.append(('link', link_label(linkedin_raw, 'LinkedIn'), linkedin))
    if github:
        contact_items.append(('link', link_label(github_raw, 'GitHub'), github))
    for i, (kind, label, target) in enumerate(contact_items):
        if i:
            add_contact_text(p, ' | ')
        if kind == 'link':
            add_hyperlink(p, label, target, font_name=CFG['contact_font'], font_size=CFG['contact_size'], underline=True)
        else:
            add_contact_text(p, label)
    add_body_paragraph(doc, date_value, after=CFG['date_after'])
    add_body_paragraph(doc, cover.get('company', ''), after=CFG['recipient_after'], bold=True)
    add_body_paragraph(doc, cover.get('position', ''), after=CFG['role_after'])
    add_body_paragraph(doc, cover.get('salutation', 'Dear Hiring Manager,'), after=CFG['salutation_after'])
    for paragraph_text in paragraphs:
        add_body_paragraph(doc, paragraph_text, after=CFG['body_after'], justify=True)
    add_body_paragraph(doc, cover.get('closing', 'Sincerely,'), before=CFG['closing_before'], after=0)
    if SIGNATURE_IMAGE.exists():
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.left_indent = Inches(0.0)
        p.paragraph_format.space_before = Pt(CFG.get('signature_before', 14))
        p.paragraph_format.space_after = Pt(CFG.get('image_after', 10))
        run = p.add_run()
        run.add_picture(str(SIGNATURE_IMAGE), width=Inches(1.2))
    add_body_paragraph(doc, cover.get('signature', name), before=CFG.get('signature_name_before', 4), after=CFG['signature_after'])
    return doc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cover', default=str(DEFAULT_COVER))
    parser.add_argument('--identity', default=str(DEFAULT_IDENTITY))
    parser.add_argument('--gate', default=str(DEFAULT_GATE))
    parser.add_argument('--out', default=None)
    parser.add_argument('--date', default=None)
    parser.add_argument('--allow-ungated', action='store_true')
    args = parser.parse_args()
    cover_path = Path(args.cover).expanduser()
    if not cover_path.is_absolute():
        cover_path = (ROOT / cover_path).resolve()
    identity_path = Path(args.identity).expanduser()
    if not identity_path.is_absolute():
        identity_path = (ROOT / identity_path).resolve()
    gate_path = Path(args.gate).expanduser()
    if not gate_path.is_absolute():
        gate_path = (ROOT / gate_path).resolve()
    cover = load_json(cover_path)
    identity = load_json(identity_path)
    candidate = identity.get('candidate', {})
    if not isinstance(candidate, dict):
        raise SystemExit('Identity payload has no candidate object.')
    if not candidate.get('name'):
        raise SystemExit('Identity payload is missing candidate.name.')
    if not args.allow_ungated:
        gate = load_json(gate_path)
        if gate.get('pass') is not True:
            raise SystemExit('Cover Gate V2 is not PASS. Refusing candidate-facing DOCX render.')
    if args.out:
        output = safe_output_path(args.out)
    else:
        output = safe_output_path(OUTPUT_ROOT / ('careerops_cover_' + slug(cover.get('company')) + '.docx'))
    layout = load_json(RUNTIME / "cover_adaptive_layout_report.json")
    expected = {"cover_sha256": hashlib.sha256(cover_path.read_bytes()).hexdigest(), "identity_sha256": hashlib.sha256(identity_path.read_bytes()).hexdigest()}
    if layout.get("status") != "PASS" or layout.get("binding") != expected:
        raise SystemExit("RENDERER_COVER_LAYOUT_BINDING_MISMATCH")
    g = layout["geometry"]
    if not 10.5 <= g["body_pt"] <= 11.0 or not 0.65 <= g["rhythm"] <= 1 or not 9.75 <= g["contact_pt"] <= 10.0:
        raise SystemExit("RENDERER_COVER_LAYOUT_OUT_OF_BOUNDS")
    expected_geometry = {"body_line_pt": g["body_pt"]*(1.10+0.1666666667*g["rhythm"]), "contact_line_pt":g["contact_pt"]*1.06122449}
    for key, base in {"header_after":14,"date_after":8,"role_after":13,"salutation_after":10,"body_after":10,"closing_before":18,"signature_before":16,"signature_after":10,"signature_name_before":6}.items():
        expected_geometry[key+"_pt"] = base*g["rhythm"]
    if any(abs(g.get(key,-100)-value)>0.000001 for key,value in expected_geometry.items()):
        raise SystemExit("RENDERER_COVER_LAYOUT_GEOMETRY_MISMATCH")
    margins = g.get('margins_in',{})
    if set(margins)!= {'top','bottom','left','right'} or any(not .4<=float(value)<=1.0 for value in margins.values()):
        raise SystemExit('RENDERER_COVER_MARGIN_CONTRACT_INVALID')
    CFG.update({ 'margin_'+side:float(value) for side,value in margins.items() })
    CFG.update(body_size=g["body_pt"],body_line=g["body_line_pt"],contact_size=g["contact_pt"],contact_line=g["contact_line_pt"])
    for key in ["header_after","date_after","role_after","salutation_after","body_after","closing_before"]: CFG[key]=g[key+"_pt"]
    CFG.update(signature_before=g["signature_before_pt"],image_after=g["signature_after_pt"],signature_name_before=g["signature_name_before_pt"])
    date_value = args.date or detroit_date()
    doc = build_document(cover, candidate, date_value)
    output.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output)
    audit_docx_layout(output, RUNTIME)
    print('=' * 96)
    print('CAREEROPS COVER DOCX RENDERER')
    print('=' * 96)
    print('CONTENT SOURCE:', cover_path.relative_to(ROOT))
    print('IDENTITY SOURCE:', identity_path.relative_to(ROOT))
    print('GATE MODE:', 'LAYOUT_SMOKE_ONLY' if args.allow_ungated else 'GATE_V2_REQUIRED')
    print('COMPANY:', cover.get('company'))
    print('POSITION:', cover.get('position'))
    print('OUTPUT:', output.relative_to(ROOT))
    print('PAGE:', 'US Letter 8.5 x 11')
    print('MARGINS:', '0.50 in all sides')
    print('NAME:', 'Times New Roman 14 pt')
    print('CONTACT:', 'Times New Roman 9.8 pt')
    print('BODY:', 'Calibri 10.5 pt')
    print('GENERIC COVER HEADING:', 'REMOVED')
    print('MODEL CALLS:', 0)
    print('=' * 96)


if __name__ == "__main__":
    main()
