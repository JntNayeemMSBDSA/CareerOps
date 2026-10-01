#!/usr/bin/env python3

from __future__ import annotations

import re


def norm(value):
    return re.sub(
        r"\s+",
        " ",
        str(value or ""),
    ).strip()


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


def sections(raw_source):
    state = None
    result = {}

    for i, line in enumerate(
        raw_source.splitlines(),
        start=1,
    ):
        heading = heading_kind(
            line
        )

        if heading:
            state = heading
            result[i] = (
                "HEADING_" + heading
            )
        else:
            result[i] = state

    return result


def deterministic_identity(
    deterministic,
):
    return {
        "employer_name":
            deterministic.get("company")
            or deterministic.get("employer")
            or deterministic.get(
                "employer_name"
            ),

        "job_title":
            deterministic.get("job_title")
            or deterministic.get("title"),

        "requisition_id":
            deterministic.get("requisition_id")
            or deterministic.get("job_id")
            or deterministic.get("req_id"),
    }


def known_ids(
    deterministic,
):
    result = set()

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
                result.add(
                    rid
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

    return result


def collect_rows(
    shadow,
):
    result = []

    for row in (
        shadow.get(
            "identity",
            {},
        ).get(
            "observations",
            [],
        )
        or []
    ):
        if isinstance(
            row,
            dict,
        ):
            result.append(
                (
                    "identity",
                    row,
                )
            )

    for row in (
        shadow.get(
            "boundaries",
            [],
        )
        or []
    ):
        if isinstance(
            row,
            dict,
        ):
            result.append(
                (
                    "boundary",
                    row,
                )
            )

    for row in (
        shadow.get(
            "requirements",
            [],
        )
        or []
    ):
        if isinstance(
            row,
            dict,
        ):
            result.append(
                (
                    "requirement",
                    row,
                )
            )

    return result


def validate(
    raw_source,
    deterministic,
    shadow,
):
    errors = []

    source_lines = (
        raw_source.splitlines()
    )

    sec = sections(
        raw_source
    )

    ids = known_ids(
        deterministic
    )

    det_identity = deterministic_identity(
        deterministic
    )

    shadow_identity = (
        shadow.get(
            "identity",
            {}
        )
        or {}
    )

    for surface, row in collect_rows(
        shadow
    ):
        quote = row.get(
            "exact_source_quote"
        )

        start = row.get(
            "start_line"
        )

        end = row.get(
            "end_line"
        )

        if (
            not isinstance(
                quote,
                str,
            )
            or not quote.strip()
        ):
            errors.append(
                f"{surface}:EMPTY_QUOTE"
            )
            continue

        if (
            not isinstance(
                start,
                int,
            )
            or not isinstance(
                end,
                int,
            )
            or start < 1
            or end < start
            or end > len(
                source_lines
            )
        ):
            errors.append(
                f"{surface}:INVALID_SPAN:{start}:{end}"
            )
            continue

        claimed = "\n".join(
            source_lines[
                start - 1:end
            ]
        )

        if (
            norm(
                quote
            )
            not in norm(
                claimed
            )
        ):
            errors.append(
                f"{surface}:QUOTE_NOT_IN_SPAN:{quote}"
            )

        confidence = row.get(
            "confidence"
        )

        if (
            not isinstance(
                confidence,
                (int, float),
            )
            or confidence < 0.5
            or confidence > 1
        ):
            errors.append(
                f"{surface}:BAD_CONFIDENCE:{confidence}"
            )

        if surface == "requirement":
            rid = row.get(
                "requirement_id"
            )

            if (
                rid is not None
                and rid not in ids
            ):
                errors.append(
                    f"requirement:INVENTED_ID:{rid}"
                )

            if (
                row.get(
                    "classification"
                )
                == "POSSIBLE_MISSED_REQUIREMENT"
                and rid is not None
            ):
                errors.append(
                    "requirement:MISSED_ID_MUST_BE_NULL"
                )

        for flag in (
            row.get(
                "semantic_flags",
                [],
            )
            or []
        ):
            value = norm(
                quote
            )

            section = sec.get(
                start
            )

            supported = True

            if (
                flag
                == "CURRENT_REQUISITION_IDENTITY_CONFLICT"
            ):
                supported = any(
                    shadow_identity.get(
                        key
                    )
                    and det_identity.get(
                        key
                    )
                    and norm(
                        shadow_identity[
                            key
                        ]
                    ).casefold()
                    != norm(
                        det_identity[
                            key
                        ]
                    ).casefold()
                    for key in (
                        "employer_name",
                        "job_title",
                        "requisition_id",
                    )
                )

            elif (
                flag
                == "EMPLOYER_HISTORY_NOT_CANDIDATE_TENURE"
            ):
                supported = (
                    section == "ABOUT"
                    or bool(
                        re.search(
                            r"("
                            r"\bour organization\b|"
                            r"\bour company\b|"
                            r"\bfounded\b|"
                            r"\bsince\s+\d{4}\b|"
                            r"\bfor\s+more\s+than\s+\d+\s+years\b"
                            r")",
                            value,
                            re.I,
                        )
                    )
                )

            elif (
                flag
                == "APPLICATION_QUESTION_NOT_JD_REQUIREMENT"
            ):
                supported = (
                    section == "APPLICATION"
                )

            elif (
                flag
                == "PAGE_CHROME_NOT_JD"
            ):
                supported = bool(
                    re.search(
                        r"\b("
                        r"sign in|search jobs|job alerts|"
                        r"return to search|navigation"
                        r")\b",
                        value,
                        re.I,
                    )
                )

            elif (
                flag
                == "PREFERRED_NOT_REQUIRED"
            ):
                supported = (
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

            elif (
                flag
                == "SECTION_CONTEXT_RESET"
            ):
                supported = (
                    section == "PREFERRED"
                    or heading_kind(
                        value
                    )
                    == "PREFERRED"
                )

            elif (
                flag
                == "EDUCATION_EXPERIENCE_SUBSTITUTION"
            ):
                supported = bool(
                    re.search(
                        r"\b("
                        r"substitut\w*|in lieu of|"
                        r"equivalent professional experience"
                        r")\b",
                        value,
                        re.I,
                    )
                )

            elif (
                flag
                == "GENERIC_NO_SPONSORSHIP_REVIEW_ONLY"
            ):
                supported = (
                    section != "APPLICATION"
                    and bool(
                        re.search(
                            r"\b("
                            r"do(?:es)?\s+not\s+sponsor|"
                            r"unable\s+to\s+sponsor|"
                            r"no\s+sponsorship"
                            r")\b",
                            value,
                            re.I,
                        )
                    )
                )

            elif (
                flag
                == "EXPLICIT_CURRENT_OR_FUTURE_SPONSORSHIP_HARD_BLOCK"
            ):
                supported = (
                    section != "APPLICATION"
                    and bool(
                        re.search(
                            r"("
                            r"without\s+(?:current\s+or\s+future|now\s+or\s+future)"
                            r".{0,50}sponsor|"
                            r"without.{0,40}(?:current\s+or\s+future).{0,40}sponsor|"
                            r"\bno\s+(?:f-?1|opt|stem\s*opt)\b"
                            r")",
                            value,
                            re.I,
                        )
                    )
                )

            elif (
                flag
                == "ACTIVE_CLEARANCE_REQUIRED"
            ):
                supported = bool(
                    re.search(
                        r"("
                        r"\bactive\s+(?:secret|top\s+secret|security)\b|"
                        r"\bmust\s+possess.{0,40}clearance\b|"
                        r"\bcurrent.{0,30}clearance\b"
                        r")",
                        value,
                        re.I,
                    )
                )

            elif (
                flag
                == "ABILITY_TO_OBTAIN_CLEARANCE_NOT_ACTIVE_BLOCKER"
            ):
                supported = bool(
                    re.search(
                        r"("
                        r"\bable\s+to\s+obtain\b|"
                        r"\bability\s+to\s+obtain\b|"
                        r"\bafter\s+hire\b"
                        r")",
                        value,
                        re.I,
                    )
                )

            elif (
                flag
                == "TOOL_TENURE_NOT_OCCUPATIONAL_TENURE"
            ):
                supported = bool(
                    re.search(
                        r"\b("
                        r"(?:\w+\s+)?years?\s+of\s+experience\s+using|"
                        r"(?:\w+\s+)?years?\s+using|"
                        r"experience\s+using"
                        r")\b",
                        value,
                        re.I,
                    )
                )

            elif (
                flag
                == "OCCUPATIONAL_DURATION_REQUIREMENT"
            ):
                supported = bool(
                    re.search(
                        r"\b("
                        r"(?:\w+|\d+)(?:\s*\(\d+\))?\s+years?"
                        r"\s+of\s+professional|"
                        r"professional.{0,40}experience"
                        r")\b",
                        value,
                        re.I,
                    )
                )

            elif (
                flag
                == "COMPOUND_REQUIREMENT"
            ):
                supported = (
                    " and "
                    in value.casefold()
                )

            if not supported:
                errors.append(
                    f"{surface}:UNSUPPORTED_FLAG:{flag}"
                )

    return errors
