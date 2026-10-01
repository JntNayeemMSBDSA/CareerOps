#!/usr/bin/env python3

import argparse
import json
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile


from careerops_runtime import (
    runtime_dir,
    output_dir,
)

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = runtime_dir(ROOT)
OUTPUT_ROOT = output_dir(ROOT)

DEFAULT_SOURCE = (
    RUNTIME
    / "generated_cover_letter_pair_candidate.json"
)

DEFAULT_PDF = (
    OUTPUT_ROOT
    / "careerops_cover_"
      "indian_river_state_college_"
      "layout_candidate.pdf"
)

DEFAULT_DOCX = (
    OUTPUT_ROOT
    / "careerops_cover_"
      "indian_river_state_college_"
      "layout_candidate.docx"
)

DEFAULT_IDENTITY = (
    RUNTIME
    / "career_ops_cv_payload.json"
)

DEFAULT_REPORT = (
    RUNTIME
    / "cover_roundtrip_report.json"
)


W_NS = (
    "http://schemas.openxmlformats.org/"
    "wordprocessingml/2006/main"
)


def load_json(path):
    if not path.exists():
        raise SystemExit(
            f"Missing required file: {path}"
        )

    return json.loads(
        path.read_text(encoding="utf-8")
    )


def normalize(text):
    text = str(text or "")

    text = (
        text
        .replace("\u00a0", " ")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2013", "-")
        .replace("\u2014", "-")
    )

    # PDF extraction may split a hyphenated token at a visual
    # line boundary, e.g. "mapping- coverage" although the
    # source text is "mapping-coverage".
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


def expected_segments(source):
    paragraphs = source.get(
        "paragraphs",
        [],
    )

    if len(paragraphs) != 3:
        raise SystemExit(
            "Source cover does not contain "
            "exactly three paragraphs."
        )

    return {
        "company":
            source.get("company", ""),

        "position":
            source.get("position", ""),

        "salutation":
            source.get("salutation", ""),

        "paragraph_1":
            paragraphs[0],

        "paragraph_2":
            paragraphs[1],

        "paragraph_3":
            paragraphs[2],

        "closing":
            source.get("closing", ""),

        "signature":
            source.get("signature", ""),
    }


def extract_pdf_text(pdf_path):
    pdftotext = shutil.which(
        "pdftotext"
    )

    if not pdftotext:
        raise SystemExit(
            "pdftotext is required for "
            "cover round-trip validation."
        )

    with tempfile.TemporaryDirectory() as tmp:
        txt = Path(tmp) / "cover.txt"

        result = subprocess.run(
            [
                pdftotext,
                "-layout",
                str(pdf_path),
                str(txt),
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
            str(pdf_path),
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
        int(match.group(1))
        if match
        else None
    )


def extract_docx_text(docx_path):
    with ZipFile(docx_path) as z:
        xml = z.read(
            "word/document.xml"
        )

    root = ET.fromstring(xml)

    paragraphs = []

    for p in root.iter(
        f"{{{W_NS}}}p"
    ):
        pieces = []

        for node in p.iter():
            if node.tag == f"{{{W_NS}}}t":
                pieces.append(
                    node.text or ""
                )

            elif node.tag == f"{{{W_NS}}}tab":
                pieces.append("\t")

            elif node.tag == f"{{{W_NS}}}br":
                pieces.append("\n")

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


def docx_relationships(docx_path):
    with ZipFile(docx_path) as z:
        rels = z.read(
            "word/_rels/document.xml.rels"
        ).decode(
            "utf-8",
            errors="replace",
        )

    return rels


def all_segments_present(
    rendered_text,
    segments,
):
    rendered = normalize(
        rendered_text
    )

    results = {}

    for key, value in segments.items():
        results[key] = (
            bool(value)
            and normalize(value)
            in rendered
        )

    return results


def ordered_segments_present(
    rendered_text,
    segments,
):
    rendered = normalize(
        rendered_text
    )

    cursor = 0
    positions = {}

    for key in (
        "company",
        "position",
        "salutation",
        "paragraph_1",
        "paragraph_2",
        "paragraph_3",
        "closing",
        "signature",
    ):
        needle = normalize(
            segments[key]
        )

        pos = rendered.find(
            needle,
            cursor,
        )

        positions[key] = pos

        if pos < 0:
            return False, positions

        cursor = (
            pos
            + len(needle)
        )

    return True, positions


def source_letter_text(source):
    return "\n".join([
        source.get("company", ""),
        source.get("position", ""),
        source.get("salutation", ""),
        *source.get("paragraphs", []),
        source.get("closing", ""),
        source.get("signature", ""),
    ])


def pdf_urls_present(
    pdf_path,
    candidate,
):
    raw = pdf_path.read_bytes()

    expected = {
        "email":
            f"mailto:{candidate.get('email', '')}",

        "linkedin":
            (
                candidate.get(
                    "linkedin",
                    {},
                ).get("url", "")
                if isinstance(
                    candidate.get("linkedin"),
                    dict,
                )
                else candidate.get(
                    "linkedin",
                    "",
                )
            ),

        "github":
            (
                candidate.get(
                    "github",
                    {},
                ).get("url", "")
                if isinstance(
                    candidate.get("github"),
                    dict,
                )
                else candidate.get(
                    "github",
                    "",
                )
            ),
    }

    results = {}

    for key, value in expected.items():
        if not value:
            results[key] = False
            continue

        probes = [
            value,
            value.replace(
                "https://",
                "",
            ),
        ]

        results[key] = any(
            probe.encode(
                "utf-8"
            ) in raw
            for probe in probes
            if probe
        )

    return results


def docx_urls_present(
    rels,
    candidate,
):
    linkedin = candidate.get(
        "linkedin",
        {},
    )

    github = candidate.get(
        "github",
        {},
    )

    if isinstance(
        linkedin,
        dict,
    ):
        linkedin = linkedin.get(
            "url",
            "",
        )

    if isinstance(
        github,
        dict,
    ):
        github = github.get(
            "url",
            "",
        )

    expected = {
        "email":
            f"mailto:{candidate.get('email', '')}",

        "linkedin":
            linkedin,

        "github":
            github,
    }

    return {
        key:
            bool(value)
            and value in rels

        for key, value
        in expected.items()
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--source",
        default=str(
            DEFAULT_SOURCE
        ),
    )

    parser.add_argument(
        "--pdf",
        default=str(
            DEFAULT_PDF
        ),
    )

    parser.add_argument(
        "--docx",
        default=str(
            DEFAULT_DOCX
        ),
    )

    parser.add_argument(
        "--identity",
        default=str(
            DEFAULT_IDENTITY
        ),
    )

    parser.add_argument(
        "--report",
        default=str(
            DEFAULT_REPORT
        ),
    )

    args = parser.parse_args()

    def resolve_path(value):
        p = Path(
            value
        ).expanduser()

        return (
            p
            if p.is_absolute()
            else ROOT / p
        ).resolve()

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

    for path in (
        source_path,
        pdf_path,
        docx_path,
        identity_path,
    ):
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

    candidate = identity.get(
        "candidate",
        {},
    )

    segments = expected_segments(
        source
    )

    pdf_text = extract_pdf_text(
        pdf_path
    )

    docx_text = extract_docx_text(
        docx_path
    )

    pdf_segment_checks = (
        all_segments_present(
            pdf_text,
            segments,
        )
    )

    docx_segment_checks = (
        all_segments_present(
            docx_text,
            segments,
        )
    )

    pdf_order_ok, pdf_positions = (
        ordered_segments_present(
            pdf_text,
            segments,
        )
    )

    docx_order_ok, docx_positions = (
        ordered_segments_present(
            docx_text,
            segments,
        )
    )

    source_normalized = normalize(
        source_letter_text(
            source
        )
    )

    pdf_normalized = normalize(
        "\n".join([
            source.get(
                "company",
                "",
            ),
            source.get(
                "position",
                "",
            ),
            source.get(
                "salutation",
                "",
            ),
            *[
                p
                for p
                in source.get(
                    "paragraphs",
                    [],
                )
                if normalize(p)
                in normalize(
                    pdf_text
                )
            ],
            source.get(
                "closing",
                "",
            ),
            source.get(
                "signature",
                "",
            ),
        ])
    )

    docx_normalized = normalize(
        "\n".join([
            source.get(
                "company",
                "",
            ),
            source.get(
                "position",
                "",
            ),
            source.get(
                "salutation",
                "",
            ),
            *[
                p
                for p
                in source.get(
                    "paragraphs",
                    [],
                )
                if normalize(p)
                in normalize(
                    docx_text
                )
            ],
            source.get(
                "closing",
                "",
            ),
            source.get(
                "signature",
                "",
            ),
        ])
    )

    page_count = pdf_page_count(
        pdf_path
    )

    pdf_link_checks = (
        pdf_urls_present(
            pdf_path,
            candidate,
        )
    )

    docx_rels = (
        docx_relationships(
            docx_path
        )
    )

    docx_link_checks = (
        docx_urls_present(
            docx_rels,
            candidate,
        )
    )

    candidate_name = str(
        candidate.get(
            "name",
            "",
        )
    )

    candidate_location = str(
        candidate.get(
            "location",
            "",
        )
    )

    candidate_phone = str(
        candidate.get(
            "phone",
            "",
        )
    )

    candidate_email = str(
        candidate.get(
            "email",
            "",
        )
    )

    identity_values = [
        candidate_name,
        candidate_location,
        candidate_phone,
        candidate_email,
    ]

    identity_pdf = all(
        normalize(value)
        in normalize(pdf_text)
        for value in identity_values
        if value
    )

    identity_docx = all(
        normalize(value)
        in normalize(docx_text)
        for value in identity_values
        if value
    )

    checks = {
        "pdf_one_page":
            page_count == 1,

        "pdf_all_source_segments":
            all(
                pdf_segment_checks.values()
            ),

        "docx_all_source_segments":
            all(
                docx_segment_checks.values()
            ),

        "pdf_segment_order":
            pdf_order_ok,

        "docx_segment_order":
            docx_order_ok,

        "pdf_identity":
            identity_pdf,

        "docx_identity":
            identity_docx,

        "pdf_links":
            all(
                pdf_link_checks.values()
            ),

        "docx_links":
            all(
                docx_link_checks.values()
            ),

        "pdf_no_generic_heading":
            "cover letter:"
            not in normalize(
                pdf_text
            ),

        "docx_no_generic_heading":
            "cover letter:"
            not in normalize(
                docx_text
            ),

        "pdf_source_fidelity":
            pdf_normalized
            == source_normalized,

        "docx_source_fidelity":
            docx_normalized
            == source_normalized,
    }

    failed = [
        key
        for key, value
        in checks.items()
        if not value
    ]

    report = {
        "validator":
            "careerops-cover-roundtrip-v1",

        "source":
            str(
                source_path.relative_to(
                    ROOT
                )
            ),

        "pdf":
            str(
                pdf_path.relative_to(
                    ROOT
                )
            ),

        "docx":
            str(
                docx_path.relative_to(
                    ROOT
                )
            ),

        "checks":
            checks,

        "details": {
            "pdf_page_count":
                page_count,

            "pdf_segment_checks":
                pdf_segment_checks,

            "docx_segment_checks":
                docx_segment_checks,

            "pdf_positions":
                pdf_positions,

            "docx_positions":
                docx_positions,

            "pdf_link_checks":
                pdf_link_checks,

            "docx_link_checks":
                docx_link_checks,

            "source_body_words":
                len(
                    re.findall(
                        r"\b[\w'-]+\b",
                        " ".join(
                            source.get(
                                "paragraphs",
                                [],
                            )
                        ),
                    )
                ),
        },

        "pass":
            not failed,

        "failed_checks":
            failed,

        "content_modified":
            False,

        "model_calls":
            0,
    }

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
        "CAREEROPS COVER ROUND-TRIP VALIDATOR"
    )
    print("=" * 96)

    print(
        "SOURCE:",
        report["source"],
    )

    print(
        "PDF:",
        report["pdf"],
    )

    print(
        "DOCX:",
        report["docx"],
    )

    print(
        "PDF PAGES:",
        page_count,
    )

    print()

    for key, value in checks.items():
        print(
            f"{key}:",
            "PASS" if value else "FAIL",
        )

    print()
    print(
        "ROUND-TRIP:",
        (
            "PASS"
            if report["pass"]
            else "FAIL"
        ),
    )

    print(
        "FAILED CHECKS:",
        (
            failed
            if failed
            else "NONE"
        ),
    )

    print(
        "CONTENT MODIFIED:",
        "NO",
    )

    print(
        "MODEL CALLS:",
        0,
    )

    print(
        "REPORT:",
        report_path.relative_to(
            ROOT
        ),
    )

    print("=" * 96)

    raise SystemExit(
        0
        if report["pass"]
        else 1
    )


if __name__ == "__main__":
    main()
