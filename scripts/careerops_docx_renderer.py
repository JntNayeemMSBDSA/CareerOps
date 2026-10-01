from careerops_config import candidate_identity
from careerops_config import source_dir
#!/usr/bin/env python3
from careerops_docx_layout_audit import audit_docx_layout

import hashlib
import json
import os
import re
import math
from pathlib import Path

from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE


from careerops_runtime import runtime_dir

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = runtime_dir(ROOT)

EXPLICIT_RESUME_INPUT = os.environ.get(
    "CAREEROPS_RESUME_INPUT"
)

SOURCE_CANDIDATES = (
    [
        Path(
            EXPLICIT_RESUME_INPUT
        ).expanduser().resolve()
    ]
    if EXPLICIT_RESUME_INPUT
    else []
) + [
    RUNTIME / 'career_ops_cv_payload.json',
    RUNTIME / 'generated_resume_content.json',
]

OUTPUT = Path(
    os.environ.get(
        "CAREEROPS_RESUME_OUTPUT",
        str(
            ROOT
            / "output/careerops-da-v11-editable.docx"
        ),
    )
).expanduser().resolve()


# =====================================================================
# MASTER WORD LAYOUT
# Edit these later if desired.
# =====================================================================

CFG = {
    # Page
    "page_width": 8.50,
    "page_height": 11.00,
    "margin_top": 0.50,
    "margin_bottom": 0.50,
    "margin_left": 0.50,
    "margin_right": 0.50,

    # Body
    "body_font": "Calibri",
    "body_size": 10.5,
    "body_line": 11.5,

    # Name
    "name_font": "Times New Roman",
    "name_size": 14.0,
    "name_line": 14.5,

    # Contact
    "contact_font": "Times New Roman",
    "contact_size": 9.8,
    "contact_line": 10.4,

    # Headers
    "header_font": "Calibri",
    "header_size": 11.0,
    "header_line": 11.8,
    "section_size": 10.5,
    "section_line": 11.1,

    # Spacing
    "header_after": 5.0,
    "major_section_before": 4.2,
    "section_after": 1.2,

    "experience_after": 2.4,
    "project_after": 2.4,

    # 0.25 line between bullets
    "bullet_after": 2.7,

    "skill_after": 2.7,
    "cert_before": 0.7,

    # Bullet geometry
    "bullet_indent": 0.12,
}


# =====================================================================
# DATA HELPERS
# =====================================================================

def nk(x):
    return re.sub(r"[^a-z0-9]", "", str(x).lower())


def find_key(obj, names, default=None):
    if not isinstance(obj, dict):
        return default

    wanted = {nk(x) for x in names}

    for k, v in obj.items():
        if nk(k) in wanted:
            return v

    return default


def deep_find(obj, names):
    wanted = {nk(x) for x in names}

    if isinstance(obj, dict):
        for k, v in obj.items():
            if nk(k) in wanted:
                return v

        for v in obj.values():
            result = deep_find(v, names)
            if result is not None:
                return result

    elif isinstance(obj, list):
        for v in obj:
            result = deep_find(v, names)
            if result is not None:
                return result

    return None


def text(v):
    if v is None:
        return ""

    if isinstance(v, str):
        return v.strip()

    if isinstance(v, (int, float)):
        return str(v)

    if isinstance(v, list):
        return ", ".join(text(x) for x in v if text(x))

    if isinstance(v, dict):
        for key in [
            "text",
            "value",
            "name",
            "title",
            "label",
            "display",
            "description",
        ]:
            x = find_key(v, [key])
            if x is not None:
                return text(x)

    return str(v).strip()


def as_list(v):
    if v is None:
        return []

    if isinstance(v, list):
        return v

    if isinstance(v, tuple):
        return list(v)

    return [v]


def dates(item):
    direct = text(find_key(
        item,
        [
            "dates",
            "period",
            "date_range",
            "dateRange",
            "duration",
            "date",
            "year",
            "graduation",
            "graduation_date",
            "graduationDate",
        ]
    ))

    if direct:
        return direct

    start = text(find_key(
        item,
        ["start", "start_date", "startDate", "from"]
    ))

    end = text(find_key(
        item,
        ["end", "end_date", "endDate", "to"]
    ))

    if start and end:
        return f"{start} - {end}"

    return start or end


def bullets(item):
    if not isinstance(item, dict):
        return [text(item)] if text(item) else []

    value = find_key(
        item,
        [
            "bullets",
            "highlights",
            "achievements",
            "accomplishments",
            "points",
            "details",
            "descriptions",
            "description",
        ],
    )

    out = []

    for x in as_list(value):
        t = text(x).lstrip("•-* ").strip()

        if t:
            out.append(t)

    return out


# =====================================================================
# WORD HELPERS
# =====================================================================

def font_run(run, name, size, bold=None, italic=None, underline=None):
    run.font.name = name
    run.font.size = Pt(size)

    if bold is not None:
        run.bold = bold

    if italic is not None:
        run.italic = italic

    if underline is not None:
        run.underline = underline

    rpr = run._r.get_or_add_rPr()
    rf = rpr.rFonts

    if rf is None:
        rf = OxmlElement("w:rFonts")
        rpr.insert(0, rf)

    rf.set(qn("w:ascii"), name)
    rf.set(qn("w:hAnsi"), name)
    rf.set(qn("w:eastAsia"), name)


def exact_line(p, pt):
    p.paragraph_format.line_spacing = Pt(pt)
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY


def bottom_border(p, size=4):
    ppr = p._p.get_or_add_pPr()

    old = ppr.find(qn("w:pBdr"))
    if old is not None:
        ppr.remove(old)

    pbdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")

    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(size))
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "000000")

    pbdr.append(bottom)
    ppr.append(pbdr)


def hyperlink(p, label, url, *, name, size, underline=True):
    rel = p.part.relate_to(
        url,
        RELATIONSHIP_TYPE.HYPERLINK,
        is_external=True,
    )

    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), rel)

    run = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")

    fonts = OxmlElement("w:rFonts")
    fonts.set(qn("w:ascii"), name)
    fonts.set(qn("w:hAnsi"), name)
    rpr.append(fonts)

    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), str(round(size * 2)))
    rpr.append(sz)

    color = OxmlElement("w:color")
    color.set(qn("w:val"), "000000")
    rpr.append(color)

    u = OxmlElement("w:u")
    u.set(qn("w:val"), "single" if underline else "none")
    rpr.append(u)

    run.append(rpr)

    node = OxmlElement("w:t")
    node.text = label
    run.append(node)

    link.append(run)
    p._p.append(link)


def section_heading(doc, label, first=False):
    p = doc.add_paragraph()

    p.paragraph_format.space_before = Pt(
        0 if first else CFG["major_section_before"]
    )
    p.paragraph_format.space_after = Pt(CFG["section_after"])

    exact_line(p, CFG["section_line"])
    bottom_border(p, 4)

    r = p.add_run(label.upper())
    font_run(
        r,
        CFG["header_font"],
        CFG["section_size"],
        bold=True,
        italic=False,
    )

    return p


def body_paragraph(doc, value, after=0, justify=True):
    p = doc.add_paragraph()

    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(after)

    exact_line(p, CFG["body_line"])

    p.alignment = (
        WD_ALIGN_PARAGRAPH.JUSTIFY
        if justify
        else WD_ALIGN_PARAGRAPH.LEFT
    )

    r = p.add_run(value)
    font_run(r, CFG["body_font"], CFG["body_size"])

    return p


def bullet_paragraph(doc, value, after=None):
    if after is None:
        after = CFG["bullet_after"]

    p = doc.add_paragraph()

    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(after)

    p.paragraph_format.left_indent = Inches(CFG["bullet_indent"])
    p.paragraph_format.first_line_indent = Inches(-CFG["bullet_indent"])

    exact_line(p, CFG["body_line"])
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    r = p.add_run("• ")
    font_run(r, CFG["body_font"], CFG["body_size"])

    r = p.add_run(value)
    font_run(r, CFG["body_font"], CFG["body_size"])

    return p


def entry_header(doc, parts, date_value=""):
    p = doc.add_paragraph()

    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)

    exact_line(p, CFG["header_line"])

    usable = (
        CFG["page_width"]
        - CFG["margin_left"]
        - CFG["margin_right"]
    )

    p.paragraph_format.tab_stops.add_tab_stop(
        Inches(usable),
        WD_TAB_ALIGNMENT.RIGHT,
    )

    for i, item in enumerate(parts):
        if i:
            r = p.add_run(" | ")
            font_run(
                r,
                CFG["header_font"],
                CFG["header_size"],
            )

        r = p.add_run(item["text"])

        font_run(
            r,
            CFG["header_font"],
            CFG["header_size"],
            bold=item.get("bold", True),
            italic=item.get("italic", False),
        )

    if date_value:
        p.add_run("\t")

        r = p.add_run(date_value)
        font_run(
            r,
            CFG["header_font"],
            CFG["header_size"],
            bold=True,
        )

    return p


# =====================================================================
# LOAD ENGINE PAYLOAD
# =====================================================================

source = next((p for p in SOURCE_CANDIDATES if p.exists()), None)

if source is None:
    raise SystemExit("ERROR: Resume runtime JSON not found.")

with source.open("r", encoding="utf-8") as f:
    data = json.load(f)

print(f"SOURCE: {source}")


# Consume the existing solver's bounded geometry; no content edits or new solver.
layout_path = RUNTIME / "adaptive_layout_report.json"
if layout_path.exists():
    layout = json.loads(layout_path.read_text())
    if layout.get("status") != "PASS" or layout.get("payload_sha256") != hashlib.sha256(source.read_bytes()).hexdigest():
        raise SystemExit("RENDERER_RESUME_LAYOUT_BINDING_MISMATCH")
    t = layout["typography"]; rhythm = layout["rhythm"]
    if not 10.249 <= t["body_pt"] <= 12.001 or not 10.399 <= t["entry_and_date_pt"] <= 12.201 or not 9.749 <= t["contact_pt"] <= 11.501 or not 0 <= rhythm["factor"] <= 1:
        raise SystemExit("RENDERER_RESUME_LAYOUT_OUT_OF_BOUNDS")
    edge = layout["fixed_geometry"]["target_all_edges_px"] / 96
    if not 0.40 <= edge < 1:
        raise SystemExit("RENDERER_RESUME_PAGE_GEOMETRY_INVALID")
    CFG["margin_top"] = edge
    CFG["margin_bottom"] = edge
    CFG['margin_left'] = layout['fixed_geometry']['left_px'] / 96
    CFG['margin_right'] = layout['fixed_geometry']['right_px'] / 96
    if min(CFG['margin_left'], CFG['margin_right']) < 0.40:
        raise SystemExit('RENDERER_PROFESSIONAL_MARGIN_FLOOR')
    CFG["body_size"] = math.ceil(t["body_pt"]*2)/2
    CFG["body_line"] = t['body_line_px'] * 72 / 96
    CFG['name_size']=t['name_pt'];CFG['name_line']=t['name_pt']*1.04
    CFG['contact_size']=round(t['contact_pt']*2)/2;CFG['contact_line']=t['contact_pt']*1.06122449
    CFG['header_size']=round(t['entry_and_date_pt']*2)/2;CFG['header_line']=t['entry_and_date_pt']*1.07
    CFG['major_section_before']=rhythm['section_gap_pt']
    CFG['experience_after']=rhythm['job_gap_pt']
    CFG['project_after']=rhythm['project_gap_pt']
    CFG['bullet_after']=rhythm['bullet_gap_px']*72/96
    CFG['skill_after']=rhythm['skill_gap_px']*72/96
    CFG['header_after']=rhythm['header_to_first_section_px']*72/96
    CFG['name_line']=t.get('name_line_px',CFG['name_line']*96/72)*72/96
    CFG['contact_line']=t.get('contact_line_px',CFG['contact_line']*96/72)*72/96
    CFG['header_line']=t.get('entry_line_px',CFG['header_line']*96/72)*72/96
    CFG['section_size']=CFG['body_size']
    CFG['section_line']=t.get('section_line_px',CFG['section_line']*96/72)*72/96
    CFG['section_after']=rhythm.get('section_title_gap_pt',CFG['section_after'])
    CFG['cert_before']=rhythm.get('cert_gap_pt',CFG['cert_before'])

# =====================================================================
# EXTRACT CONTENT
# =====================================================================

candidate = deep_find(
    data,
    ["candidate", "personal_info", "personalInfo", "basics", "header"]
)

candidate = candidate if isinstance(candidate, dict) else {}

authority = candidate_identity(ROOT)
name = text(find_key(candidate, ["name", "full_name", "fullName"])) or authority["name"]
location = text(find_key(candidate, ["location"])) or authority["location"]
phone = text(find_key(candidate, ["phone", "phone_number", "phoneNumber"])) or authority["phone"]
email = text(find_key(candidate, ["email"])) or authority["email"]
from careerops_contact_identity import link_target
linkedin = link_target(find_key(candidate, ["linkedin", "linkedin_url", "linkedinUrl"])) or link_target(authority["linkedin"])
github = link_target(find_key(candidate, ["github", "github_url", "githubUrl"])) or link_target(authority["github"])


summary = text(deep_find(
    data,
    ["professional_summary", "professionalSummary", "summary"]
))


experiences = as_list(deep_find(
    data,
    [
        "professional_experience",
        "professionalExperience",
        "work_experience",
        "workExperience",
        "experiences",
        "experience",
    ]
))


projects = as_list(deep_find(
    data,
    ["selected_projects", "selectedProjects", "projects"]
))


skills = deep_find(
    data,
    ["technical_skills", "technicalSkills", "skills"]
)


certifications = as_list(deep_find(
    data,
    ["certifications", "certificates"]
))


education = as_list(deep_find(
    data,
    ["education", "educations"]
))


# =====================================================================
# DOCUMENT
# =====================================================================

doc = Document()

sec = doc.sections[0]

sec.page_width = Inches(CFG["page_width"])
sec.page_height = Inches(CFG["page_height"])

sec.top_margin = Inches(CFG["margin_top"])
sec.bottom_margin = Inches(CFG["margin_bottom"])
sec.left_margin = Inches(CFG["margin_left"])
sec.right_margin = Inches(CFG["margin_right"])


normal = doc.styles["Normal"]

normal.font.name = CFG["body_font"]
normal.font.size = Pt(CFG["body_size"])

normal.paragraph_format.space_before = Pt(0)
normal.paragraph_format.space_after = Pt(0)
normal.paragraph_format.line_spacing = Pt(CFG["body_line"])
normal.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY


# =====================================================================
# HEADER
# =====================================================================

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(0)
p.paragraph_format.space_after = Pt(0)
exact_line(p, CFG["name_line"])

r = p.add_run(name)
font_run(
    r,
    CFG["name_font"],
    CFG["name_size"],
    bold=True,
)


# Contact line.
# Underline is applied to the text itself, so it ends exactly
# where the visible contact line ends.

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(0)
p.paragraph_format.space_after = Pt(CFG["header_after"])
exact_line(p, CFG["contact_line"])


def contact_text(value):
    r = p.add_run(value)
    font_run(
        r,
        CFG["contact_font"],
        CFG["contact_size"],
        underline=True,
    )


contact_text(location)
contact_text(" | ")
contact_text(phone)
contact_text(" | ")

hyperlink(
    p,
    email,
    f"mailto:{email}",
    name=CFG["contact_font"],
    size=CFG["contact_size"],
    underline=True,
)

contact_text(" | ")

hyperlink(
    p,
    "LinkedIn",
    linkedin,
    name=CFG["contact_font"],
    size=CFG["contact_size"],
    underline=True,
)

contact_text(" | ")

hyperlink(
    p,
    "GitHub",
    github,
    name=CFG["contact_font"],
    size=CFG["contact_size"],
    underline=True,
)


# =====================================================================
# SUMMARY
# =====================================================================

section_heading(doc, "Professional Summary", first=True)

if summary:
    body_paragraph(doc, summary)


# =====================================================================
# EXPERIENCE
# =====================================================================

if experiences:
    section_heading(doc, "Professional Experience")

    valid_exp = [x for x in experiences if isinstance(x, dict)]

    for ei, exp in enumerate(valid_exp):
        company = text(find_key(
            exp,
            ["company", "employer", "organization", "organisation"]
        ))

        role = text(find_key(
            exp,
            ["role", "title", "job_title", "jobTitle", "position"]
        ))

        left = []

        if company:
            left.append({
                "text": company,
                "bold": True,
                "italic": False,
            })

        if role:
            left.append({
                "text": role,
                "bold": True,
                "italic": False,
            })

        entry_header(doc, left, dates(exp))

        bs = bullets(exp)

        for bi, b in enumerate(bs):
            last_bullet = bi == len(bs) - 1
            last_entry = ei == len(valid_exp) - 1

            if last_bullet:
                after = 0 if last_entry else CFG["experience_after"]
            else:
                after = CFG["bullet_after"]

            bullet_paragraph(doc, b, after=after)


# =====================================================================
# PROJECTS
# =====================================================================

if projects:
    section_heading(doc, "Selected Projects")

    valid_projects = [x for x in projects if isinstance(x, dict)]

    for pi, project in enumerate(valid_projects):
        pname = text(find_key(
            project,
            ["name", "title", "project", "project_name", "projectName"]
        ))

        entry_header(
            doc,
            [{
                "text": pname,
                "bold": True,
                "italic": False,
            }],
            dates(project),
        )

        bs = bullets(project)

        for bi, b in enumerate(bs):
            last_bullet = bi == len(bs) - 1
            last_entry = pi == len(valid_projects) - 1

            if last_bullet:
                after = 0 if last_entry else CFG["project_after"]
            else:
                after = CFG["bullet_after"]

            bullet_paragraph(doc, b, after=after)


# =====================================================================
# TECHNICAL SKILLS
# =====================================================================

if skills:
    section_heading(
        doc,
        (
            "Technical Skills and Certifications"
            if certifications
            else "Technical Skills"
        ),
    )

    rows = []

    if isinstance(skills, dict):
        for category, values in skills.items():
            rows.append((text(category), text(values)))

    elif isinstance(skills, list):
        for item in skills:
            if isinstance(item, dict):
                category = text(find_key(
                    item,
                    ["category", "name", "title", "label"]
                ))

                values = text(find_key(
                    item,
                    [
                        "items",
                        "terms",
                        "skills",
                        "values",
                        "technologies",
                        "text",
                    ]
                ))

                rows.append((category, values))
            else:
                rows.append(("", text(item)))

    for i, (category, values) in enumerate(rows):
        p = doc.add_paragraph()

        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(
            0 if i == len(rows) - 1 else CFG["skill_after"]
        )

        p.paragraph_format.left_indent = Inches(CFG["bullet_indent"])
        p.paragraph_format.first_line_indent = Inches(-CFG["bullet_indent"])

        exact_line(p, CFG["body_line"])

        r = p.add_run("• ")
        font_run(r, CFG["body_font"], CFG["body_size"])

        if category:
            r = p.add_run(category + ": ")
            font_run(
                r,
                CFG["body_font"],
                CFG["body_size"],
                bold=True,
            )

        r = p.add_run(values)
        font_run(r, CFG["body_font"], CFG["body_size"])


# =====================================================================
# CERTIFICATIONS
# =====================================================================

if certifications:
    p = doc.add_paragraph()

    p.paragraph_format.space_before = Pt(CFG["cert_before"])
    p.paragraph_format.space_after = Pt(0)

    p.paragraph_format.left_indent = Inches(CFG["bullet_indent"])
    p.paragraph_format.first_line_indent = Inches(-CFG["bullet_indent"])

    exact_line(p, CFG["body_line"])

    r = p.add_run("• ")
    font_run(r, CFG["body_font"], CFG["body_size"])

    r = p.add_run("Certifications and Training: ")
    font_run(
        r,
        CFG["body_font"],
        CFG["body_size"],
        bold=True,
    )

    for i, cert in enumerate(certifications):
        if i:
            r = p.add_run("; ")
            font_run(r, CFG["body_font"], CFG["body_size"])

        if isinstance(cert, dict):
            title = text(find_key(
                cert,
                ["title", "name", "certificate", "certification"]
            ))

            url = text(find_key(
                cert,
                ["url", "link", "href", "credential_url", "credentialUrl"]
            ))
        else:
            title = text(cert)
            url = ""

        label = f"({i + 1}) {title}"

        if url:
            hyperlink(
                p,
                label,
                url,
                name=CFG["body_font"],
                size=CFG["body_size"],
                underline=True,
            )
        else:
            r = p.add_run(label)
            font_run(
                r,
                CFG["body_font"],
                CFG["body_size"],
                underline=True,
            )


# =====================================================================
# EDUCATION
# =====================================================================

if education:
    section_heading(doc, 'Education')
    for edu in education:
        if not isinstance(edu, dict):
            body_paragraph(doc, text(edu), justify=False)
            continue
        degree = text(find_key(edu, ['degree', 'program', 'title', 'qualification']))
        school = text(find_key(edu, ['institution', 'school', 'university', 'organization', 'org']))
        left = []
        if school:
            left.append({'text': school, 'bold': True, 'italic': False})
        if degree:
            left.append({'text': degree, 'bold': True, 'italic': False})

        extras = []
        description = text(find_key(edu, ['description', 'details', 'detail']))
        gpa = text(find_key(edu, ['gpa', 'cgpa']))
        honors = text(find_key(edu, ['honors', 'honours', 'distinction']))
        if description:
            extras.append(description)
        if gpa:
            gpa_text = f'GPA: {gpa}'
            if gpa_text not in extras:
                extras.append(gpa_text)
        if honors:
            if honors not in extras:
                extras.append(honors)
        # Match the existing PDF's compact education geometry while retaining every source character.
        compact_gpa = len(extras) == 1 and extras[0].startswith('GPA:') and len(extras[0]) <= 30
        if compact_gpa:
            left.append({'text': extras[0], 'bold': False, 'italic': False})
        entry_header(doc, left, dates(edu))
        if extras and not compact_gpa:
            body_paragraph(doc, ' | '.join(extras), justify=False)


# =====================================================================
# SAVE
# =====================================================================

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
doc.save(OUTPUT)
audit_docx_layout(OUTPUT, RUNTIME)

print()
print("=" * 76)
print("EDITABLE WORD RESUME GENERATED")
print("=" * 76)
print(f"OUTPUT: {OUTPUT}")
print("Page:       US Letter 8.5 x 11")
print('Margins:   ',{k:CFG['margin_'+k] for k in ['top','bottom','left','right']})
print("Name:       14 pt")
print("Headers:    11 pt")
print("Body:       10.5 pt")
print("Bullets:    0.25-line spacing")
print("DOCX:       Native editable Word file")
print("=" * 76)
