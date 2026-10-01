#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import re


ROLE_RE = re.compile(
    r"\b("
    r"analyst|engineer|scientist|developer|manager|"
    r"specialist|consultant|architect|administrator|"
    r"researcher|coordinator|planner|strategist|"
    r"director|officer|technician"
    r")\b",
    re.I,
)

REQ_RE = re.compile(
    r"\b(?:"
    r"requisition|job\s*id|job\s*#|"
    r"req(?:uisition)?\s*id|position\s*id"
    r")\b"
    r"\s*[:#-]?\s*"
    r"([A-Za-z0-9][A-Za-z0-9._/-]*)",
    re.I,
)

SUB_RE = re.compile(
    r"\b("
    r"substitut\w*|in lieu of|"
    r"equivalent professional experience"
    r")\b",
    re.I,
)

EXPLICIT_SPONSOR_RE = re.compile(
    r"("
    r"without\s+(?:current\s+or\s+future|now\s+or\s+future)"
    r".{0,50}sponsor|"
    r"without.{0,40}(?:current\s+or\s+future).{0,40}sponsor|"
    r"\bno\s+(?:f-?1|opt|stem\s*opt)\b"
    r")",
    re.I,
)

GENERIC_SPONSOR_RE = re.compile(
    r"\b("
    r"do(?:es)?\s+not\s+sponsor|"
    r"unable\s+to\s+sponsor|"
    r"no\s+sponsorship"
    r")\b",
    re.I,
)

ACTIVE_CLEARANCE_RE = re.compile(
    r"("
    r"\bactive\s+(?:secret|top\s+secret|security)\b|"
    r"\bmust\s+possess.{0,40}clearance\b|"
    r"\bcurrent.{0,30}clearance\b"
    r")",
    re.I,
)

OBTAIN_CLEARANCE_RE = re.compile(
    r"("
    r"\bable\s+to\s+obtain\b|"
    r"\bability\s+to\s+obtain\b|"
    r"\bafter\s+hire\b"
    r")",
    re.I,
)

TOOL_TENURE_RE = re.compile(
    r"\b("
    r"(?:\w+\s+)?years?\s+of\s+experience\s+using|"
    r"(?:\w+\s+)?years?\s+using|"
    r"experience\s+using"
    r")\b",
    re.I,
)

OCCUPATIONAL_RE = re.compile(
    r"\b("
    r"(?:\w+|\d+)(?:\s*\(\d+\))?\s+years?"
    r"\s+of\s+professional"
    r"|professional.{0,40}experience"
    r")\b",
    re.I,
)

HISTORY_RE = re.compile(
    r"("
    r"\bour\s+organization\b|"
    r"\bour\s+company\b|"
    r"\bfounded\b|"
    r"\bsince\s+\d{4}\b|"
    r"\bfor\s+more\s+than\s+\d+\s+years\b"
    r")",
    re.I,
)


CONFIDENCE = {
    "HIGH": 0.95,
    "MEDIUM": 0.80,
    "LOW": 0.60,
}


def norm(value):
    return re.sub(
        r"\s+",
        " ",
        str(value or ""),
    ).strip()


def tokens(value):
    return {
        token
        for token in re.findall(
            r"[a-z0-9+#.-]+",
            norm(value).casefold(),
        )
        if len(token) > 1
        and token not in {
            "a",
            "an",
            "the",
            "is",
            "are",
            "of",
            "to",
            "in",
            "with",
            "and",
            "or",
            "for",
        }
    }


def lines(raw_source):
    return raw_source.splitlines()


def exact_quote(
    raw_source,
    start,
    end,
):
    source_lines = lines(
        raw_source
    )

    if (
        not isinstance(start, int)
        or not isinstance(end, int)
        or start < 1
        or end < start
        or end > len(source_lines)
    ):
        raise ValueError(
            f"INVALID_SPAN:{start}:{end}"
        )

    return "\n".join(
        source_lines[
            start - 1:end
        ]
    )


def heading_kind(text):
    value = norm(
        text
    ).casefold()

    if re.fullmatch(
        r"application questions?",
        value,
    ):
        return "APPLICATION"

    if re.fullmatch(
        r"(?:preferred|desired) qualifications?",
        value,
    ):
        return "PREFERRED"

    if re.fullmatch(
        r"(?:minimum|required) qualifications?",
        value,
    ):
        return "REQUIRED"

    if re.fullmatch(
        r"qualifications?",
        value,
    ):
        return "REQUIRED"

    if re.fullmatch(
        r"requirements?",
        value,
    ):
        return "REQUIRED"

    if value.startswith(
        "about "
    ):
        return "ABOUT"

    return None


def section_map(raw_source):
    result = {}
    current = None

    for i, line in enumerate(
        lines(raw_source),
        start=1,
    ):
        heading = heading_kind(
            line
        )

        if heading:
            current = heading
            result[i] = (
                "HEADING_" + heading
            )
        else:
            result[i] = current

    return result


def deterministic_requirements(
    deterministic,
):
    rows = []

    def walk(value):
        if isinstance(
            value,
            dict,
        ):
            rid = value.get(
                "requirement_id"
            )

            if isinstance(
                rid,
                str,
            ):
                rows.append(
                    value
                )

            for child in value.values():
                walk(
                    child
                )

        elif isinstance(
            value,
            list,
        ):
            for child in value:
                walk(
                    child
                )

    walk(
        deterministic
    )

    return rows


def allowed_ids(
    deterministic,
):
    return {
        row.get(
            "requirement_id"
        )
        for row in deterministic_requirements(
            deterministic
        )
    }


def match_requirement_id(
    source_text,
    deterministic,
):
    source_norm = norm(
        source_text
    ).casefold()

    source_tokens = tokens(
        source_text
    )

    scored = []

    for row in deterministic_requirements(
        deterministic
    ):
        quote = (
            row.get("quote")
            or row.get("text")
            or row.get(
                "requirement_text"
            )
        )

        if not quote:
            continue

        qnorm = norm(
            quote
        ).casefold()

        if not qnorm:
            continue

        if qnorm == source_norm:
            return row.get(
                "requirement_id"
            )

        if (
            qnorm in source_norm
            or source_norm in qnorm
        ):
            scored.append(
                (
                    1.0,
                    row.get(
                        "requirement_id"
                    ),
                )
            )
            continue

        qt = tokens(
            quote
        )

        if not qt or not source_tokens:
            continue

        overlap = len(
            qt & source_tokens
        ) / max(
            1,
            len(qt),
        )

        scored.append(
            (
                overlap,
                row.get(
                    "requirement_id"
                ),
            )
        )

    scored.sort(
        reverse=True
    )

    if (
        scored
        and scored[0][0] >= 0.72
        and (
            len(scored) == 1
            or scored[0][0]
            > scored[1][0]
        )
    ):
        return scored[0][1]

    return None


def deterministic_identity(
    deterministic,
):
    return {
        "employer_name":
            deterministic.get(
                "company"
            )
            or deterministic.get(
                "employer"
            )
            or deterministic.get(
                "employer_name"
            ),

        "job_title":
            deterministic.get(
                "job_title"
            )
            or deterministic.get(
                "title"
            ),

        "requisition_id":
            deterministic.get(
                "requisition_id"
            )
            or deterministic.get(
                "job_id"
            )
            or deterministic.get(
                "req_id"
            ),
    }


def grounded_model_identity(
    raw_source,
    source_identity,
    value_key,
    line_key,
):
    value = source_identity.get(
        value_key
    )

    line_no = source_identity.get(
        line_key
    )

    source_lines = lines(
        raw_source
    )

    if (
        not isinstance(value, str)
        or not value.strip()
        or not isinstance(line_no, int)
        or line_no < 1
        or line_no > len(source_lines)
    ):
        return None, None

    if (
        norm(value).casefold()
        in norm(
            source_lines[
                line_no - 1
            ]
        ).casefold()
    ):
        return value, line_no

    return None, None


def header_identity(
    raw_source,
):
    source_lines = lines(
        raw_source
    )

    requisition = None
    requisition_line = None

    for i, line in enumerate(
        source_lines,
        start=1,
    ):
        match = REQ_RE.search(
            line
        )

        if match:
            requisition = match.group(
                1
            )
            requisition_line = i
            break

    title = None
    title_line = None

    for i, line in enumerate(
        source_lines[:12],
        start=1,
    ):
        value = norm(
            line
        )

        if not value:
            continue

        if heading_kind(
            value
        ):
            continue

        if REQ_RE.search(
            value
        ):
            continue

        if ROLE_RE.search(
            value
        ):
            title = value
            title_line = i
            break

    employer = None
    employer_line = None

    if title_line:
        for j in range(
            title_line - 1,
            0,
            -1,
        ):
            value = norm(
                source_lines[
                    j - 1
                ]
            )

            if not value:
                continue

            if heading_kind(
                value
            ):
                continue

            if REQ_RE.search(
                value
            ):
                continue

            if ROLE_RE.search(
                value
            ):
                continue

            employer = value
            employer_line = j
            break

    return {
        "employer_name":
            employer,

        "employer_line":
            employer_line,

        "job_title":
            title,

        "job_title_line":
            title_line,

        "requisition_id":
            requisition,

        "requisition_line":
            requisition_line,
    }


def source_fingerprint(
    raw_source,
):
    return hashlib.sha256(
        raw_source.encode(
            "utf-8"
        )
    ).hexdigest()


def make_finding(
    finding_type,
    start,
    end,
    *,
    requirement_id=None,
    confidence="HIGH",
):
    return {
        "finding_type":
            finding_type,

        "start_line":
            start,

        "end_line":
            end,

        "requirement_id":
            requirement_id,

        "confidence":
            confidence,
    }


def sentinel_findings(
    raw_source,
    deterministic,
):
    source_lines = lines(
        raw_source
    )

    sections = section_map(
        raw_source
    )

    findings = []

    # Section-level sentinels.
    for i, line in enumerate(
        source_lines,
        start=1,
    ):
        heading = heading_kind(
            line
        )

        if heading == "PREFERRED":
            findings.append(
                make_finding(
                    "SECTION_CONTEXT_RESET",
                    i,
                    i,
                )
            )

    # Line-level source semantics.
    for i, line in enumerate(
        source_lines,
        start=1,
    ):
        value = norm(
            line
        )

        if not value:
            continue

        section = sections.get(
            i
        )

        # Application question has highest precedence.
        if section == "APPLICATION":
            findings.append(
                make_finding(
                    "APPLICATION_QUESTION",
                    i,
                    i,
                    requirement_id=
                        match_requirement_id(
                            value,
                            deterministic,
                        ),
                )
            )
            continue

        # Employer background/history.
        if (
            section == "ABOUT"
            or HISTORY_RE.search(
                value
            )
        ):
            if not heading_kind(
                value
            ):
                findings.append(
                    make_finding(
                        "EMPLOYER_HISTORY",
                        i,
                        i,
                    )
                )

        # Preferred section semantics.
        if (
            section == "PREFERRED"
            and not heading_kind(
                value
            )
        ):
            findings.append(
                make_finding(
                    "PREFERRED_REQUIREMENT",
                    i,
                    i,
                    requirement_id=
                        match_requirement_id(
                            value,
                            deterministic,
                        ),
                )
            )

        # Substitution.
        if SUB_RE.search(
            value
        ):
            findings.append(
                make_finding(
                    "EDUCATION_EXPERIENCE_SUBSTITUTION",
                    i,
                    i,
                    requirement_id=
                        match_requirement_id(
                            value,
                            deterministic,
                        ),
                )
            )

        # Sponsorship. Never interpret an application question as JD eligibility.
        if EXPLICIT_SPONSOR_RE.search(
            value
        ):
            findings.append(
                make_finding(
                    "EXPLICIT_CURRENT_OR_FUTURE_NO_SPONSORSHIP",
                    i,
                    i,
                    requirement_id=
                        match_requirement_id(
                            value,
                            deterministic,
                        ),
                )
            )

        elif GENERIC_SPONSOR_RE.search(
            value
        ):
            findings.append(
                make_finding(
                    "GENERIC_NO_SPONSORSHIP",
                    i,
                    i,
                    requirement_id=
                        match_requirement_id(
                            value,
                            deterministic,
                        ),
                )
            )

        # Clearance.
        if ACTIVE_CLEARANCE_RE.search(
            value
        ):
            findings.append(
                make_finding(
                    "ACTIVE_CLEARANCE_REQUIRED",
                    i,
                    i,
                    requirement_id=
                        match_requirement_id(
                            value,
                            deterministic,
                        ),
                )
            )

        elif OBTAIN_CLEARANCE_RE.search(
            value
        ):
            findings.append(
                make_finding(
                    "ABILITY_TO_OBTAIN_CLEARANCE_AFTER_HIRE",
                    i,
                    i,
                    requirement_id=
                        match_requirement_id(
                            value,
                            deterministic,
                        ),
                )
            )

        # Experience semantics.
        if TOOL_TENURE_RE.search(
            value
        ):
            findings.append(
                make_finding(
                    "TOOL_TENURE",
                    i,
                    i,
                    requirement_id=
                        match_requirement_id(
                            value,
                            deterministic,
                        ),
                )
            )

        if OCCUPATIONAL_RE.search(
            value
        ):
            findings.append(
                make_finding(
                    "OCCUPATIONAL_DURATION",
                    i,
                    i,
                    requirement_id=
                        match_requirement_id(
                            value,
                            deterministic,
                        ),
                )
            )

    # Compound partial-capture sentinel.
    det_rows = deterministic_requirements(
        deterministic
    )

    for i, line in enumerate(
        source_lines,
        start=1,
    ):
        value = norm(
            line
        )

        if (
            " and " not in value.casefold()
            or heading_kind(
                value
            )
        ):
            continue

        source_tokens = tokens(
            value
        )

        for row in det_rows:
            quote = (
                row.get("quote")
                or row.get("text")
                or row.get(
                    "requirement_text"
                )
            )

            if not quote:
                continue

            qnorm = norm(
                quote
            )

            if not qnorm:
                continue

            if (
                qnorm.casefold()
                == value.casefold()
            ):
                continue

            qt = tokens(
                qnorm
            )

            if not qt:
                continue

            overlap = len(
                qt & source_tokens
            ) / max(
                1,
                len(qt),
            )

            if overlap >= 0.65:
                findings.append(
                    make_finding(
                        "COMPOUND_REQUIREMENT_MISSING_COMPONENT",
                        i,
                        i,
                        requirement_id=None,
                    )
                )
                break

    # Dedupe.
    unique = {}

    for row in findings:
        key = (
            row[
                "finding_type"
            ],
            row[
                "start_line"
            ],
            row[
                "end_line"
            ],
        )

        if key not in unique:
            unique[key] = row

    return list(
        unique.values()
    )


def model_finding_supported(
    finding,
    raw_source,
    deterministic,
):
    start = finding.get(
        "start_line"
    )

    end = finding.get(
        "end_line"
    )

    try:
        quote = exact_quote(
            raw_source,
            start,
            end,
        )
    except Exception:
        return False

    section = section_map(
        raw_source
    ).get(
        start
    )

    ftype = finding.get(
        "finding_type"
    )

    value = norm(
        quote
    )

    if ftype == "EMPLOYER_HISTORY":
        return (
            section == "ABOUT"
            or bool(
                HISTORY_RE.search(
                    value
                )
            )
        )

    if ftype == "APPLICATION_QUESTION":
        return (
            section == "APPLICATION"
        )

    if ftype == "PAGE_CHROME":
        return bool(
            re.search(
                r"\b("
                r"sign in|search jobs|job alerts|"
                r"return to search|navigation"
                r")\b",
                value,
                re.I,
            )
        )

    if ftype == "PREFERRED_REQUIREMENT":
        return (
            section == "PREFERRED"
            or bool(
                re.search(
                    r"\b("
                    r"preferred|a plus|nice to have|desired"
                    r")\b",
                    value,
                    re.I,
                )
            )
        )

    if ftype == "EDUCATION_EXPERIENCE_SUBSTITUTION":
        return bool(
            SUB_RE.search(
                value
            )
        )

    if ftype == "GENERIC_NO_SPONSORSHIP":
        return (
            section != "APPLICATION"
            and bool(
                GENERIC_SPONSOR_RE.search(
                    value
                )
            )
            and not bool(
                EXPLICIT_SPONSOR_RE.search(
                    value
                )
            )
        )

    if ftype == "EXPLICIT_CURRENT_OR_FUTURE_NO_SPONSORSHIP":
        return (
            section != "APPLICATION"
            and bool(
                EXPLICIT_SPONSOR_RE.search(
                    value
                )
            )
        )

    if ftype == "ACTIVE_CLEARANCE_REQUIRED":
        return bool(
            ACTIVE_CLEARANCE_RE.search(
                value
            )
        )

    if ftype == "ABILITY_TO_OBTAIN_CLEARANCE_AFTER_HIRE":
        return (
            bool(
                OBTAIN_CLEARANCE_RE.search(
                    value
                )
            )
            and not bool(
                ACTIVE_CLEARANCE_RE.search(
                    value
                )
            )
        )

    if ftype == "TOOL_TENURE":
        return bool(
            TOOL_TENURE_RE.search(
                value
            )
        )

    if ftype == "OCCUPATIONAL_DURATION":
        return bool(
            OCCUPATIONAL_RE.search(
                value
            )
        )

    if ftype == "COMPOUND_REQUIREMENT_MISSING_COMPONENT":
        return (
            " and "
            in value.casefold()
        )

    if ftype == "SECTION_CONTEXT_RESET":
        return (
            heading_kind(
                value
            )
            == "PREFERRED"
        )

    # Keep free-form missed/false findings out until LI-3 gives
    # them retrieval-backed verification.
    if ftype in {
        "MISSED_REQUIREMENT",
        "FALSE_REQUIREMENT",
    }:
        return False

    return False


MAPPING = {
    "EMPLOYER_HISTORY": {
        "surface":
            "boundary",

        "boundary_type":
            "EMPLOYER_HISTORY",

        "flags": [
            "EMPLOYER_HISTORY_NOT_CANDIDATE_TENURE",
        ],
    },

    "APPLICATION_QUESTION": {
        "surface":
            "boundary",

        "boundary_type":
            "APPLICATION_QUESTION",

        "flags": [
            "APPLICATION_QUESTION_NOT_JD_REQUIREMENT",
        ],
    },

    "PAGE_CHROME": {
        "surface":
            "boundary",

        "boundary_type":
            "PAGE_CHROME",

        "flags": [
            "PAGE_CHROME_NOT_JD",
        ],
    },

    "SECTION_CONTEXT_RESET": {
        "surface":
            "boundary",

        "boundary_type":
            "SECTION_HEADER",

        "flags": [
            "SECTION_CONTEXT_RESET",
        ],
    },

    "PREFERRED_REQUIREMENT": {
        "surface":
            "requirement",

        "classification":
            "PREFERRED",

        "priority":
            "P1",

        "relation":
            "OR",

        "flags": [
            "PREFERRED_NOT_REQUIRED",
        ],
    },

    "EDUCATION_EXPERIENCE_SUBSTITUTION": {
        "surface":
            "requirement",

        "classification":
            "SUBSTITUTION",

        "priority":
            "P0",

        "relation":
            "SUBSTITUTION",

        "flags": [
            "EDUCATION_EXPERIENCE_SUBSTITUTION",
        ],
    },

    "GENERIC_NO_SPONSORSHIP": {
        "surface":
            "requirement",

        "classification":
            "CONTEXT",

        "priority":
            "P0",

        "relation":
            "NONE",

        "flags": [
            "GENERIC_NO_SPONSORSHIP_REVIEW_ONLY",
        ],
    },

    "EXPLICIT_CURRENT_OR_FUTURE_NO_SPONSORSHIP": {
        "surface":
            "requirement",

        "classification":
            "HARD_BLOCK",

        "priority":
            "P0",

        "relation":
            "AND",

        "flags": [
            "EXPLICIT_CURRENT_OR_FUTURE_SPONSORSHIP_HARD_BLOCK",
        ],
    },

    "ACTIVE_CLEARANCE_REQUIRED": {
        "surface":
            "requirement",

        "classification":
            "HARD_BLOCK",

        "priority":
            "P0",

        "relation":
            "AND",

        "flags": [
            "ACTIVE_CLEARANCE_REQUIRED",
        ],
    },

    "ABILITY_TO_OBTAIN_CLEARANCE_AFTER_HIRE": {
        "surface":
            "requirement",

        "classification":
            "CONTEXT",

        "priority":
            "P0",

        "relation":
            "AND",

        "flags": [
            "ABILITY_TO_OBTAIN_CLEARANCE_NOT_ACTIVE_BLOCKER",
        ],
    },

    "TOOL_TENURE": {
        "surface":
            "requirement",

        "classification":
            "REQUIRED",

        "priority":
            "P0",

        "relation":
            "AND",

        "flags": [
            "TOOL_TENURE_NOT_OCCUPATIONAL_TENURE",
        ],
    },

    "OCCUPATIONAL_DURATION": {
        "surface":
            "requirement",

        "classification":
            "REQUIRED",

        "priority":
            "P0",

        "relation":
            "AND",

        "flags": [
            "OCCUPATIONAL_DURATION_REQUIREMENT",
        ],
    },

    "COMPOUND_REQUIREMENT_MISSING_COMPONENT": {
        "surface":
            "requirement",

        "classification":
            "POSSIBLE_MISSED_REQUIREMENT",

        "priority":
            "P1",

        "relation":
            "AND",

        "force_null_id":
            True,

        "flags": [
            "COMPOUND_REQUIREMENT",
        ],
    },
}


def assemble(
    raw_source,
    deterministic,
    probe,
):
    model_identity = (
        probe.get(
            "source_identity"
        )
        or {}
    )

    header = header_identity(
        raw_source
    )

    identity = {}

    identity_fields = [
        (
            "employer_name",
            "employer_line",
        ),
        (
            "job_title",
            "job_title_line",
        ),
        (
            "requisition_id",
            "requisition_line",
        ),
    ]

    resolved_lines = {}

    for value_key, line_key in identity_fields:
        value, line_no = grounded_model_identity(
            raw_source,
            model_identity,
            value_key,
            line_key,
        )

        if value is None:
            value = header.get(
                value_key
            )

            line_no = header.get(
                line_key
            )

        identity[
            value_key
        ] = value

        resolved_lines[
            value_key
        ] = line_no

    identity[
        "current_posting_confidence"
    ] = 0.95

    identity[
        "observations"
    ] = []

    det_identity = deterministic_identity(
        deterministic
    )

    for value_key, _ in identity_fields:
        value = identity.get(
            value_key
        )

        line_no = resolved_lines.get(
            value_key
        )

        if (
            not value
            or not isinstance(
                line_no,
                int,
            )
        ):
            continue

        det = det_identity.get(
            value_key
        )

        conflict = (
            det is not None
            and norm(
                value
            ).casefold()
            != norm(
                det
            ).casefold()
        )

        identity[
            "observations"
        ].append(
            {
                "observation_type":
                    (
                        "IDENTITY_CONFLICT"
                        if conflict
                        else
                        "IDENTITY_CONFIRMATION"
                    ),

                "exact_source_quote":
                    exact_quote(
                        raw_source,
                        line_no,
                        line_no,
                    ),

                "start_line":
                    line_no,

                "end_line":
                    line_no,

                "confidence":
                    0.95,

                "rationale":
                    (
                        f"Source {value_key} differs from deterministic state."
                        if conflict
                        else
                        f"Source confirms {value_key}."
                    ),

                "semantic_flags":
                    (
                        [
                            "CURRENT_REQUISITION_IDENTITY_CONFLICT"
                        ]
                        if conflict
                        else []
                    ),
            }
        )

    # Deterministic sentinels are authoritative only for this advisory
    # shadow representation, never for production eligibility/release.
    findings = sentinel_findings(
        raw_source,
        deterministic,
    )

    sentinel_keys = {
        (
            row[
                "finding_type"
            ],
            row[
                "start_line"
            ],
            row[
                "end_line"
            ],
        )
        for row in findings
    }

    rejected_model_findings = []

    for row in (
        probe.get(
            "findings"
        )
        or []
    ):
        if not isinstance(
            row,
            dict,
        ):
            continue

        key = (
            row.get(
                "finding_type"
            ),
            row.get(
                "start_line"
            ),
            row.get(
                "end_line"
            ),
        )

        if key in sentinel_keys:
            continue

        if not model_finding_supported(
            row,
            raw_source,
            deterministic,
        ):
            rejected_model_findings.append(
                {
                    **row,
                    "rejected_reason":
                        "NOT_DETERMINISTICALLY_SOURCE_SUPPORTED",
                }
            )
            continue

        proposed_id = row.get(
            "requirement_id"
        )

        if (
            proposed_id is not None
            and proposed_id
            not in allowed_ids(
                deterministic
            )
        ):
            proposed_id = None

        accepted = {
            **row,
            "requirement_id":
                proposed_id,
        }

        findings.append(
            accepted
        )

        sentinel_keys.add(
            key
        )

    boundaries = []
    requirements = []

    for finding in findings:
        mapping = MAPPING.get(
            finding.get(
                "finding_type"
            )
        )

        if not mapping:
            continue

        start = finding.get(
            "start_line"
        )

        end = finding.get(
            "end_line"
        )

        try:
            quote = exact_quote(
                raw_source,
                start,
                end,
            )
        except Exception:
            continue

        confidence = CONFIDENCE.get(
            finding.get(
                "confidence"
            ),
            0.80,
        )

        proposed_id = finding.get(
            "requirement_id"
        )

        rid = None

        if (
            proposed_id
            and proposed_id
            in allowed_ids(
                deterministic
            )
        ):
            rid = proposed_id

        if rid is None:
            rid = match_requirement_id(
                quote,
                deterministic,
            )

        if mapping.get(
            "force_null_id"
        ):
            rid = None

        if (
            mapping[
                "surface"
            ]
            == "boundary"
        ):
            boundaries.append(
                {
                    "boundary_type":
                        mapping[
                            "boundary_type"
                        ],

                    "material":
                        True,

                    "exact_source_quote":
                        quote,

                    "start_line":
                        start,

                    "end_line":
                        end,

                    "confidence":
                        confidence,

                    "rationale":
                        (
                            "Source-structure sentinel identified "
                            + finding[
                                "finding_type"
                            ]
                            + "."
                        ),

                    "semantic_flags":
                        list(
                            mapping[
                                "flags"
                            ]
                        ),
                }
            )

        else:
            flags = list(
                mapping[
                    "flags"
                ]
            )

            if (
                mapping[
                    "classification"
                ]
                == "PREFERRED"
                and section_map(
                    raw_source
                ).get(
                    start
                )
                == "PREFERRED"
            ):
                if (
                    "SECTION_CONTEXT_RESET"
                    not in flags
                ):
                    flags.append(
                        "SECTION_CONTEXT_RESET"
                    )

            requirements.append(
                {
                    "requirement_id":
                        rid,

                    "classification":
                        mapping[
                            "classification"
                        ],

                    "suggested_priority":
                        mapping[
                            "priority"
                        ],

                    "suggested_relation":
                        mapping[
                            "relation"
                        ],

                    "exact_source_quote":
                        quote,

                    "start_line":
                        start,

                    "end_line":
                        end,

                    "confidence":
                        confidence,

                    "rationale":
                        (
                            "Verified source sentinel identified "
                            + finding[
                                "finding_type"
                            ]
                            + "."
                        ),

                    "semantic_flags":
                        sorted(
                            set(
                                flags
                            )
                        ),
                }
            )

    def row_key(row):
        return (
            row.get(
                "boundary_type"
            )
            or row.get(
                "classification"
            ),
            row.get(
                "requirement_id"
            ),
            row.get(
                "start_line"
            ),
            row.get(
                "end_line"
            ),
            tuple(
                row.get(
                    "semantic_flags",
                    [],
                )
            ),
        )

    boundaries = list(
        {
            row_key(row): row
            for row in boundaries
        }.values()
    )

    requirements = list(
        {
            row_key(row): row
            for row in requirements
        }.values()
    )

    metadata = (
        probe.get(
            "_metadata"
        )
        or {}
    )

    return {
        "schema_version":
            "career-ops-li-shadow-output-v1",

        "authority":
            "ADVISORY_ONLY",

        "may_override":
            False,

        "source_fingerprint":
            source_fingerprint(
                raw_source
            ),

        "identity":
            identity,

        "boundaries":
            boundaries,

        "requirements":
            requirements,

        "retrieval_context":
            [],

        "model_metadata": {
            **metadata,

            "architecture":
                "LI2E_HYBRID_V1",

            "deterministic_sentinel_count":
                len(
                    sentinel_findings(
                        raw_source,
                        deterministic,
                    )
                ),

            "rejected_model_findings":
                rejected_model_findings,

            "rejected_model_finding_count":
                len(
                    rejected_model_findings
                ),
        },
    }
