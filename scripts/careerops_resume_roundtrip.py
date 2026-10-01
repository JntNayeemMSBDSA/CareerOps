#!/usr/bin/env python3

import argparse
import json
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]

W_NS = (
    "http://schemas.openxmlformats.org/"
    "wordprocessingml/2006/main"
)

BROKEN_MARKERS = [
    "\ufffd",
    "\x00",
]


HEADING_ALIASES = {
    "summary": [
        "PROFESSIONAL SUMMARY",
        "SUMMARY",
    ],

    "experience": [
        "PROFESSIONAL EXPERIENCE",
        "WORK EXPERIENCE",
        "EXPERIENCE",
    ],

    "projects": [
        "SELECTED PROJECTS",
        "RELEVANT PROJECTS",
        "PROJECTS",
    ],

    "skills": [
        "TECHNICAL SKILLS AND CERTIFICATIONS",
        "TECHNICAL SKILLS & CERTIFICATIONS",
        "TECHNICAL SKILLS",
        "CORE SKILLS",
        "SKILLS",
    ],

    "education": [
        "EDUCATION",
    ],
}


def load_json(path):
    if not path.exists():
        raise SystemExit(
            f"Missing required file: {path}"
        )

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def normalize(text):
    text = str(
        text or ""
    )

    text = (
        text
        .replace("\u00a0", " ")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2022", " ")
        .replace("\uf0b7", " ")
    )

    text = re.sub(
        r"(?<=\w)-\s+(?=\w)",
        "-",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def normalize_case(text):
    return normalize(
        text
    ).casefold()


def normalized_lines(text):
    out = []

    for line in str(
        text or ""
    ).splitlines():
        value = normalize(
            line
        )

        if value:
            out.append(
                value
            )

    return out


def extract_pdf_text(pdf_path):
    pdftotext = shutil.which(
        "pdftotext"
    )

    if not pdftotext:
        raise SystemExit(
            "pdftotext is required for "
            "resume round-trip validation."
        )

    with tempfile.TemporaryDirectory() as tmp:
        txt = Path(
            tmp
        ) / "resume.txt"

        result = subprocess.run(
            [
                pdftotext,
                "-layout",
                str(
                    pdf_path
                ),
                str(
                    txt
                ),
            ],
            text=True,
            capture_output=True,
        )

        if result.returncode != 0:
            raise SystemExit(
                "pdftotext failed:\n"
                + result.stderr
            )

        return txt.read_text(
            encoding="utf-8",
            errors="replace",
        )


def pdf_page_count(pdf_path):
    pdfinfo = shutil.which(
        "pdfinfo"
    )

    if not pdfinfo:
        return None

    result = subprocess.run(
        [
            pdfinfo,
            str(
                pdf_path
            ),
        ],
        text=True,
        capture_output=True,
    )

    if result.returncode != 0:
        return None

    match = re.search(
        r"^Pages:\s+(\d+)\s*$",
        result.stdout,
        re.M,
    )

    return (
        int(
            match.group(1)
        )
        if match
        else None
    )


def extract_docx_text(docx_path):
    try:
        with ZipFile(
            docx_path
        ) as z:
            xml = z.read(
                "word/document.xml"
            )

    except Exception as exc:
        raise SystemExit(
            "Unable to read DOCX XML: "
            f"{type(exc).__name__}: {exc}"
        )

    root = ET.fromstring(
        xml
    )

    paragraphs = []

    for paragraph in root.iter(
        f"{{{W_NS}}}p"
    ):
        pieces = []

        for node in paragraph.iter(
            f"{{{W_NS}}}t"
        ):
            pieces.append(
                node.text or ""
            )

        value = "".join(
            pieces
        ).strip()

        if value:
            paragraphs.append(
                value
            )

    return "\n".join(
        paragraphs
    )


def scalar_text(value):
    if value is None:
        return ""

    if isinstance(
        value,
        (str, int, float),
    ):
        return str(
            value
        ).strip()

    return ""


def list_values(value):
    if isinstance(
        value,
        list,
    ):
        return value

    if value is None:
        return []

    return [
        value
    ]


def first_text(
    item,
    keys,
):
    if not isinstance(
        item,
        dict,
    ):
        return ""

    for key in keys:
        value = scalar_text(
            item.get(
                key
            )
        )

        if value:
            return value

    return ""


def source_segments(source):
    segments = {
        "summary": [],
        "employers": [],
        "titles": [],
        "dates": [],
        "experience_bullets": [],
        "project_names": [],
        "project_dates": [],
        "project_bullets": [],
        "skill_categories": [],
        "skills": [],
        "certifications": [],
        "education_institutions": [],
        "education_degrees": [],
        "education_graduation": [],
        "education_description": [],
    }

    summary = scalar_text(
        source.get(
            "summary"
        )
    )

    if summary:
        segments[
            "summary"
        ].append(
            summary
        )

    for item in list_values(
        source.get(
            "experience"
        )
    ):
        if not isinstance(
            item,
            dict,
        ):
            continue

        company = first_text(
            item,
            [
                "company",
                "employer",
                "organization",
                "org",
            ],
        )

        title = first_text(
            item,
            [
                "role",
                "title",
                "job_title",
                "position",
            ],
        )

        date_value = first_text(
            item,
            [
                "dates",
                "period",
                "date_range",
                "date",
            ],
        )

        if company:
            segments[
                "employers"
            ].append(
                company
            )

        if title:
            segments[
                "titles"
            ].append(
                title
            )

        if date_value:
            segments[
                "dates"
            ].append(
                date_value
            )

        for bullet in list_values(
            item.get(
                "bullets"
            )
        ):
            value = scalar_text(
                bullet
            )

            if value:
                segments[
                    "experience_bullets"
                ].append(
                    value
                )

    for item in list_values(
        source.get(
            "projects"
        )
    ):
        if not isinstance(
            item,
            dict,
        ):
            continue

        name = first_text(
            item,
            [
                "name",
                "title",
                "project",
            ],
        )

        date_value = first_text(
            item,
            [
                "dates",
                "period",
                "date",
                "year",
            ],
        )

        if name:
            segments[
                "project_names"
            ].append(
                name
            )

        if date_value:
            segments[
                "project_dates"
            ].append(
                date_value
            )

        for bullet in list_values(
            item.get(
                "bullets"
            )
        ):
            value = scalar_text(
                bullet
            )

            if value:
                segments[
                    "project_bullets"
                ].append(
                    value
                )

    for item in list_values(
        source.get(
            "skills"
        )
    ):
        if isinstance(
            item,
            dict,
        ):
            category = first_text(
                item,
                [
                    "category",
                    "name",
                    "title",
                    "label",
                ],
            )

            if category:
                segments[
                    "skill_categories"
                ].append(
                    category
                )

            terms = (
                item.get(
                    "items"
                )
            )

            if terms is None:
                terms = item.get(
                    "terms"
                )

            for term in list_values(
                terms
            ):
                value = scalar_text(
                    term
                )

                if value:
                    segments[
                        "skills"
                    ].append(
                        value
                    )

        else:
            value = scalar_text(
                item
            )

            if value:
                segments[
                    "skills"
                ].append(
                    value
                )

    for cert in list_values(
        source.get(
            "certifications"
        )
    ):
        if isinstance(
            cert,
            dict,
        ):
            value = first_text(
                cert,
                [
                    "title",
                    "name",
                    "certificate",
                    "certification",
                ],
            )

        else:
            value = scalar_text(
                cert
            )

        if value:
            segments[
                "certifications"
            ].append(
                value
            )

    for item in list_values(
        source.get(
            "education"
        )
    ):
        if not isinstance(
            item,
            dict,
        ):
            continue

        institution = first_text(
            item,
            [
                "institution",
                "school",
                "university",
                "organization",
                "org",
            ],
        )

        degree = first_text(
            item,
            [
                "degree",
                "program",
                "title",
                "qualification",
            ],
        )

        graduation = first_text(
            item,
            [
                "graduation",
                "graduation_date",
                "year",
                "dates",
                "date",
            ],
        )

        description = first_text(
            item,
            [
                "description",
                "details",
            ],
        )

        gpa = first_text(
            item,
            [
                "gpa",
                "cgpa",
            ],
        )

        honors = first_text(
            item,
            [
                "honors",
                "honours",
                "distinction",
            ],
        )

        if institution:
            segments[
                "education_institutions"
            ].append(
                institution
            )

        if degree:
            segments[
                "education_degrees"
            ].append(
                degree
            )

        if graduation:
            segments[
                "education_graduation"
            ].append(
                graduation
            )

        if description:
            segments[
                "education_description"
            ].append(
                description
            )

        else:
            extras = []

            if gpa:
                extras.append(
                    f"GPA: {gpa}"
                )

            if honors:
                extras.append(
                    honors
                )

            if extras:
                segments[
                    "education_description"
                ].append(
                    " | ".join(
                        extras
                    )
                )

    return segments

def identity_values(identity):
    if not isinstance(
        identity,
        dict,
    ):
        return {}

    candidate = identity.get(
        "candidate"
    )

    if not isinstance(
        candidate,
        dict,
    ):
        candidate = identity

    values = {}

    aliases = {
        "name": [
            "name",
            "full_name",
            "fullName",
        ],

        "location": [
            "location",
            "city_state",
        ],

        "phone": [
            "phone",
            "telephone",
        ],

        "email": [
            "email",
        ],
    }

    for canonical, names in (
        aliases.items()
    ):
        for name in names:
            value = scalar_text(
                candidate.get(
                    name
                )
            )

            if value:
                values[
                    canonical
                ] = value

                break

    return values


def section_expectations(source):
    expected = []

    if normalize(
        source.get(
            "summary",
            ""
        )
    ):
        expected.append(
            "summary"
        )

    if source.get(
        "experience"
    ):
        expected.append(
            "experience"
        )

    if source.get(
        "projects"
    ):
        expected.append(
            "projects"
        )

    if source.get(
        "skills"
    ):
        expected.append(
            "skills"
        )

    if source.get(
        "education"
    ):
        expected.append(
            "education"
        )

    return expected


def heading_positions(
    rendered_text,
    source,
):
    lines = normalized_lines(
        rendered_text
    )

    positions = {}

    matched_text = {}

    for section in section_expectations(
        source
    ):
        aliases = {
            normalize_case(
                alias
            )
            for alias
            in HEADING_ALIASES[
                section
            ]
        }

        found = None
        found_text = None

        for index, line in enumerate(
            lines
        ):
            if normalize_case(
                line
            ) in aliases:
                found = index
                found_text = line
                break

        positions[
            section
        ] = found

        matched_text[
            section
        ] = found_text

    expected = section_expectations(
        source
    )

    order_ok = True
    previous = -1

    for section in expected:
        position = positions.get(
            section
        )

        if (
            position is None
            or position <= previous
        ):
            order_ok = False
            break

        previous = position

    headings_present = all(
        positions.get(
            section
        )
        is not None
        for section in expected
    )

    return {
        "expected":
            expected,

        "positions":
            positions,

        "matched_text":
            matched_text,

        "headings_present":
            headings_present,

        "order_ok":
            order_ok,
    }



CATEGORY_SECTION = {
    "summary":
        "summary",

    "employers":
        "experience",

    "titles":
        "experience",

    "dates":
        "experience",

    "experience_bullets":
        "experience",

    "project_names":
        "projects",

    "project_dates":
        "projects",

    "project_bullets":
        "projects",

    "skill_categories":
        "skills",

    "skills":
        "skills",

    "certifications":
        "skills",

    "education_institutions":
        "education",

    "education_degrees":
        "education",

    "education_graduation":
        "education",

    "education_description":
        "education",
}


def section_blocks(
    rendered_text,
    source,
):
    lines = normalized_lines(
        rendered_text
    )

    heading = heading_positions(
        rendered_text,
        source,
    )

    expected = heading[
        "expected"
    ]

    positions = heading[
        "positions"
    ]

    blocks = {}

    for index, section in enumerate(
        expected
    ):
        start = positions.get(
            section
        )

        if start is None:
            blocks[
                section
            ] = ""

            continue

        end = len(
            lines
        )

        for later in expected[
            index + 1:
        ]:
            later_position = positions.get(
                later
            )

            if (
                later_position
                is not None
                and later_position > start
            ):
                end = later_position
                break

        blocks[
            section
        ] = "\n".join(
            lines[
                start + 1:
                end
            ]
        )

    return blocks


def presence_map(
    values,
    rendered_text,
):
    haystack = normalize_case(
        rendered_text
    )

    return [
        {
            "text":
                value,

            "present":
                (
                    normalize_case(
                        value
                    )
                    in haystack
                ),
        }
        for value in values
        if normalize(
            value
        )
    ]


def all_present(rows):
    return all(
        row[
            "present"
        ]
        for row in rows
    )


def ordered_occurrences(
    values,
    rendered_text,
):
    haystack = normalize_case(
        rendered_text
    )

    cursor = 0

    positions = []

    for value in values:
        needle = normalize_case(
            value
        )

        if not needle:
            continue

        position = haystack.find(
            needle,
            cursor,
        )

        positions.append({
            "text":
                value,

            "position":
                position,
        })

        if position < 0:
            return False, positions

        cursor = (
            position
            + len(
                needle
            )
        )

    return True, positions


def broken_character_check(
    rendered_text,
):
    text = str(
        rendered_text or ""
    )

    hits = [
        marker
        for marker in BROKEN_MARKERS
        if marker in text
    ]

    suspicious_controls = [
        f"U+{ord(ch):04X}"
        for ch in text
        if (
            ord(ch) < 32
            and ch not in {
                "\n",
                "\r",
                "\t",
                "\f",
            }
        )
    ]

    return {
        "pass":
            (
                not hits
                and not suspicious_controls
            ),

        "marker_hits":
            hits,

        "suspicious_controls":
            suspicious_controls,
    }


def token_counter(text):
    return Counter(
        re.findall(
            r"[a-z0-9][a-z0-9+.#/&'-]*",
            normalize_case(
                text
            ),
        )
    )


def multiset_similarity(
    left,
    right,
):
    a = token_counter(
        left
    )

    b = token_counter(
        right
    )

    if not a and not b:
        return 1.0

    if not a or not b:
        return 0.0

    shared = sum(
        (
            a
            & b
        ).values()
    )

    total = max(
        sum(
            a.values()
        ),
        sum(
            b.values()
        ),
    )

    return (
        shared
        / total
        if total
        else 0.0
    )


def evaluate(
    source,
    identity,
    pdf_text,
    docx_text,
    *,
    pdf_page_count_value=None,
):
    segments = source_segments(
        source
    )

    identity_expected = identity_values(
        identity
    )

    pdf_presence = {}
    docx_presence = {}

    pdf_blocks = section_blocks(
        pdf_text,
        source,
    )

    docx_blocks = section_blocks(
        docx_text,
        source,
    )

    for category, values in (
        segments.items()
    ):
        section = CATEGORY_SECTION.get(
            category
        )

        pdf_scope = (
            pdf_blocks.get(
                section,
                "",
            )
            if section
            else pdf_text
        )

        docx_scope = (
            docx_blocks.get(
                section,
                "",
            )
            if section
            else docx_text
        )

        pdf_presence[
            category
        ] = presence_map(
            values,
            pdf_scope,
        )

        docx_presence[
            category
        ] = presence_map(
            values,
            docx_scope,
        )

    identity_pdf = presence_map(
        list(
            identity_expected.values()
        ),
        pdf_text,
    )

    identity_docx = presence_map(
        list(
            identity_expected.values()
        ),
        docx_text,
    )

    pdf_headings = heading_positions(
        pdf_text,
        source,
    )

    docx_headings = heading_positions(
        docx_text,
        source,
    )

    pdf_experience_order, pdf_experience_positions = (
        ordered_occurrences(
            segments[
                "employers"
            ],
            pdf_text,
        )
    )

    docx_experience_order, docx_experience_positions = (
        ordered_occurrences(
            segments[
                "employers"
            ],
            docx_text,
        )
    )

    pdf_project_order, pdf_project_positions = (
        ordered_occurrences(
            segments[
                "project_names"
            ],
            pdf_text,
        )
    )

    docx_project_order, docx_project_positions = (
        ordered_occurrences(
            segments[
                "project_names"
            ],
            docx_text,
        )
    )

    bullet_sequence = (
        segments[
            "experience_bullets"
        ]
        + segments[
            "project_bullets"
        ]
    )

    pdf_bullet_order, pdf_bullet_positions = (
        ordered_occurrences(
            bullet_sequence,
            pdf_text,
        )
    )

    docx_bullet_order, docx_bullet_positions = (
        ordered_occurrences(
            bullet_sequence,
            docx_text,
        )
    )

    pdf_broken = broken_character_check(
        pdf_text
    )

    docx_broken = broken_character_check(
        docx_text
    )

    expected_segment_count = sum(
        len(
            values
        )
        for values in segments.values()
    )

    pdf_present_count = sum(
        row[
            "present"
        ]
        for rows in pdf_presence.values()
        for row in rows
    )

    docx_present_count = sum(
        row[
            "present"
        ]
        for rows in docx_presence.values()
        for row in rows
    )

    pdf_coverage = (
        pdf_present_count
        / expected_segment_count
        if expected_segment_count
        else 1.0
    )

    docx_coverage = (
        docx_present_count
        / expected_segment_count
        if expected_segment_count
        else 1.0
    )

    pdf_docx_similarity = (
        multiset_similarity(
            pdf_text,
            docx_text,
        )
    )

    identity_source_available = (
        bool(
            identity_expected
        )
        and bool(
            identity_expected.get(
                "name"
            )
        )
    )

    checks = {
        "identity_source_available":
            identity_source_available,

        "pdf_identity":
            (
                identity_source_available
                and all_present(
                    identity_pdf
                )
            ),

        "docx_identity":
            (
                identity_source_available
                and all_present(
                    identity_docx
                )
            ),

        "pdf_headings_present":
            pdf_headings[
                "headings_present"
            ],

        "docx_headings_present":
            docx_headings[
                "headings_present"
            ],

        "pdf_section_order":
            pdf_headings[
                "order_ok"
            ],

        "docx_section_order":
            docx_headings[
                "order_ok"
            ],

        "pdf_employers":
            all_present(
                pdf_presence[
                    "employers"
                ]
            ),

        "docx_employers":
            all_present(
                docx_presence[
                    "employers"
                ]
            ),

        "pdf_titles":
            all_present(
                pdf_presence[
                    "titles"
                ]
            ),

        "docx_titles":
            all_present(
                docx_presence[
                    "titles"
                ]
            ),

        "pdf_dates":
            all_present(
                pdf_presence[
                    "dates"
                ]
            ),

        "docx_dates":
            all_present(
                docx_presence[
                    "dates"
                ]
            ),

        "pdf_education":
            all(
                all_present(
                    pdf_presence[
                        category
                    ]
                )
                for category in [
                    "education_institutions",
                    "education_degrees",
                    "education_graduation",
                    "education_description",
                ]
            ),

        "docx_education":
            all(
                all_present(
                    docx_presence[
                        category
                    ]
                )
                for category in [
                    "education_institutions",
                    "education_degrees",
                    "education_graduation",
                    "education_description",
                ]
            ),

        "pdf_skills":
            (
                all_present(
                    pdf_presence[
                        "skill_categories"
                    ]
                )
                and all_present(
                    pdf_presence[
                        "skills"
                    ]
                )
            ),

        "docx_skills":
            (
                all_present(
                    docx_presence[
                        "skill_categories"
                    ]
                )
                and all_present(
                    docx_presence[
                        "skills"
                    ]
                )
            ),

        "pdf_bullets":
            (
                all_present(
                    pdf_presence[
                        "experience_bullets"
                    ]
                )
                and all_present(
                    pdf_presence[
                        "project_bullets"
                    ]
                )
            ),

        "docx_bullets":
            (
                all_present(
                    docx_presence[
                        "experience_bullets"
                    ]
                )
                and all_present(
                    docx_presence[
                        "project_bullets"
                    ]
                )
            ),

        "pdf_experience_order":
            pdf_experience_order,

        "docx_experience_order":
            docx_experience_order,

        "pdf_project_dates":
            all_present(
                pdf_presence[
                    "project_dates"
                ]
            ),

        "docx_project_dates":
            all_present(
                docx_presence[
                    "project_dates"
                ]
            ),

        "pdf_certifications":
            all_present(
                pdf_presence[
                    "certifications"
                ]
            ),

        "docx_certifications":
            all_present(
                docx_presence[
                    "certifications"
                ]
            ),

        "pdf_project_order":
            pdf_project_order,

        "docx_project_order":
            docx_project_order,

        "pdf_bullet_order":
            pdf_bullet_order,

        "docx_bullet_order":
            docx_bullet_order,

        "pdf_no_broken_characters":
            pdf_broken[
                "pass"
            ],

        "docx_no_broken_characters":
            docx_broken[
                "pass"
            ],

        "pdf_no_content_loss":
            (
                expected_segment_count > 0
                and pdf_coverage
                == 1.0
            ),

        "docx_no_content_loss":
            (
                expected_segment_count > 0
                and docx_coverage
                == 1.0
            ),

        "pdf_docx_consistency":
            pdf_docx_similarity
            >= 0.95,
    }

    failed = [
        name
        for name, value
        in checks.items()
        if not value
    ]

    report = {
        "schema_version":
            "careerops-resume-roundtrip-v1",

        "gate":
            (
                "PASS"
                if not failed
                else "FAIL"
            ),

        "pass":
            not failed,

        "checks":
            checks,

        "failed_checks":
            failed,

        "details": {
            "expected_segment_count":
                expected_segment_count,

            "pdf_present_segment_count":
                pdf_present_count,

            "docx_present_segment_count":
                docx_present_count,

            "pdf_source_coverage":
                round(
                    pdf_coverage,
                    6,
                ),

            "docx_source_coverage":
                round(
                    docx_coverage,
                    6,
                ),

            "pdf_docx_similarity":
                round(
                    pdf_docx_similarity,
                    6,
                ),

            "pdf_page_count":
                pdf_page_count_value,

            "identity_expected":
                identity_expected,

            "identity_pdf":
                identity_pdf,

            "identity_docx":
                identity_docx,

            "pdf_headings":
                pdf_headings,

            "docx_headings":
                docx_headings,

            "pdf_presence":
                pdf_presence,

            "docx_presence":
                docx_presence,

            "pdf_experience_positions":
                pdf_experience_positions,

            "docx_experience_positions":
                docx_experience_positions,

            "pdf_project_positions":
                pdf_project_positions,

            "docx_project_positions":
                docx_project_positions,

            "pdf_bullet_positions":
                pdf_bullet_positions,

            "docx_bullet_positions":
                docx_bullet_positions,

            "pdf_broken_characters":
                pdf_broken,

            "docx_broken_characters":
                docx_broken,
        },

        "failure_class":
            (
                None
                if not failed
                else "RENDERING"
            ),

        "content_modified":
            False,

        "model_calls":
            0,
    }

    return report


def resolve_path(value):
    p = Path(
        value
    ).expanduser()

    return (
        p
        if p.is_absolute()
        else ROOT / p
    ).resolve()


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--source",
        required=True,
    )

    parser.add_argument(
        "--pdf",
        required=True,
    )

    parser.add_argument(
        "--docx",
        required=True,
    )

    parser.add_argument(
        "--identity",
        required=True,
    )

    parser.add_argument(
        "--report",
        required=True,
    )

    args = parser.parse_args()

    source_path = resolve_path(
        args.source
    )

    pdf_path = resolve_path(
        args.pdf
    )

    docx_path = resolve_path(
        args.docx
    )

    identity_path = resolve_path(
        args.identity
    )

    report_path = resolve_path(
        args.report
    )

    for path in [
        source_path,
        pdf_path,
        docx_path,
        identity_path,
    ]:
        if not path.exists():
            raise SystemExit(
                f"Missing required file: {path}"
            )

    source = load_json(
        source_path
    )

    identity = load_json(
        identity_path
    )

    pdf_text = extract_pdf_text(
        pdf_path
    )

    docx_text = extract_docx_text(
        docx_path
    )

    report = evaluate(
        source,
        identity,
        pdf_text,
        docx_text,
        pdf_page_count_value=(
            pdf_page_count(
                pdf_path
            )
        ),
    )

    report[
        "source"
    ] = str(
        source_path
    )

    report[
        "pdf"
    ] = str(
        pdf_path
    )

    report[
        "docx"
    ] = str(
        docx_path
    )

    report[
        "identity"
    ] = str(
        identity_path
    )

    report_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    report_path.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    print("=" * 96)
    print(
        "CAREEROPS RESUME PDF/DOCX ROUND-TRIP VALIDATOR"
    )
    print("=" * 96)

    print(
        "SOURCE:",
        source_path,
    )

    print(
        "PDF:",
        pdf_path,
    )

    print(
        "DOCX:",
        docx_path,
    )

    print(
        "PDF PAGES:",
        report[
            "details"
        ][
            "pdf_page_count"
        ],
    )

    print(
        "SOURCE COVERAGE PDF:",
        report[
            "details"
        ][
            "pdf_source_coverage"
        ],
    )

    print(
        "SOURCE COVERAGE DOCX:",
        report[
            "details"
        ][
            "docx_source_coverage"
        ],
    )

    print(
        "PDF/DOCX SIMILARITY:",
        report[
            "details"
        ][
            "pdf_docx_similarity"
        ],
    )

    print()

    for name, value in (
        report[
            "checks"
        ].items()
    ):
        print(
            f"{name}:",
            value,
        )

    print()
    print(
        "FAILED CHECKS:",
        report[
            "failed_checks"
        ]
        or "NONE",
    )

    print(
        "ROUND-TRIP:",
        report[
            "gate"
        ],
    )

    print(
        "MODEL CALLS: 0"
    )

    print(
        "REPORT:",
        report_path,
    )

    if not report[
        "pass"
    ]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
