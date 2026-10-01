#!/usr/bin/env python3

import copy
import hashlib
import json
import re
from pathlib import Path

from careerops_semantic_sidecar import (
    build_sidecar,
)

from careerops_effective_requirements import (
    build_effective_view,
)


from careerops_eligibility_patterns import ACTIVE_CLEARANCE_PATTERN
STRICT_RULES = [{"constraint_type":"security_clearance","reason_code":"ACTIVE_CLEARANCE_REQUIRED","reason":"The posting requires a currently held active or acceptable interim clearance.","pattern":re.compile(ACTIVE_CLEARANCE_PATTERN,re.I)},
    {
        "constraint_type":
            "work_authorization",

        "reason_code":
            "EXPLICIT_OPT_STEM_EXCLUSION",

        "reason":
            (
                "The posting explicitly excludes F-1 OPT "
                "or STEM OPT employment authorization."
            ),

        "pattern":
            re.compile(
                (
                    r"\b(?:does|do|will)\s+not\s+"
                    r"(?:accept|support|permit|allow)\b"
                    r"[^.?!]{0,140}"
                    r"\b(?:f-?1|opt|stem\s+opt)\b"
                    r"|"
                    r"\b(?:f-?1|opt|stem\s+opt)\b"
                    r"[^.?!]{0,140}"
                    r"\bnot\s+(?:accepted|supported|"
                    r"permitted|allowed|eligible)\b"
                ),
                re.I,
            ),
    },

    {
        "constraint_type":
            "sponsorship",

        "reason_code":
            "CURRENT_FUTURE_SPONSORSHIP_EXCLUSION",

        "reason":
            (
                "The posting explicitly requires a candidate "
                "who will not need current or future employment sponsorship."
            ),

        "pattern":
            re.compile(
                (

                    # Explicit requirement to work without current/future
                    # employer/employment/visa/work sponsorship is a strict
                    # document-level sponsorship exclusion.
                    r"\bwithout\s+(?:current\s+or\s+future|"
                    r"now\s+or\s+(?:in\s+the\s+)?future)\s+"
                    r"(?:employer\s+|employment\s+|visa\s+|work\s+)?"
                    r"sponsorship\b"
                    r"|"
                    r"\bmust\s+not\s+require\b"
                    r"[^.?!]{0,120}"
                    r"\b(?:current\s+or\s+future|"
                    r"now\s+or\s+(?:in\s+the\s+)?future)\b"
                    r"[^.?!]{0,100}"
                    r"\bsponsorship\b"
                    r"|"
                    r"\b(?:does|do|will)\s+not\s+"
                    r"(?:provide|offer)\b"
                    r"[^.?!]{0,120}"
                    r"\b(?:current\s+or\s+future|"
                    r"now\s+or\s+(?:in\s+the\s+)?future)\b"
                    r"[^.?!]{0,100}"
                    r"\bsponsorship\b"
                    r"|"
                    r"\b(?:current\s+or\s+future|"
                    r"now\s+or\s+(?:in\s+the\s+)?future)\b"
                    r"[^.?!]{0,100}"
                    r"\bsponsorship\b"
                    r"[^.?!]{0,80}"
                    r"\b(?:not\s+available|unavailable)\b"
                ),
                re.I,
            ),
    },

    {
        "constraint_type":
            "citizenship",

        "reason_code":
            "EXPLICIT_US_CITIZENSHIP_REQUIREMENT",

        "reason":
            (
                "The posting explicitly requires United States citizenship."
            ),

        "pattern":
            re.compile(
                (
                    r"\b(?:must|shall|required\s+to)\s+be\s+"
                    r"(?:a\s+)?(?:u\.?s\.?|united\s+states)\s+citizens?\b"
                    r"|"
                    r"\b(?:u\.?s\.?|united\s+states)\s+citizenship"
                    r"\s+(?:is\s+)?required\b"
                    r"|"
                    r"\b(?:must|shall)\s+(?:have|hold)\s+"
                    r"(?:u\.?s\.?|united\s+states)\s+citizenship\b"
                ),
                re.I,
            ),
    },

    {
        "constraint_type":
            "permanent_residency",

        "reason_code":
            "EXPLICIT_PERMANENT_RESIDENT_REQUIREMENT",

        "reason":
            (
                "The posting explicitly requires permanent-resident "
                "or Green Card status."
            ),

        "pattern":
            re.compile(
                (
                    r"\b(?:must|shall|required\s+to)\s+be\s+"
                    r"(?:a\s+)?(?:u\.?s\.?\s+)?permanent\s+resident\b"
                    r"|"
                    r"\bgreen\s+card\s+(?:is\s+)?required\b"
                ),
                re.I,
            ),
    },

    {
        "constraint_type":
            "security_clearance",

        "reason_code":
            "ACTIVE_CLEARANCE_REQUIRED",

        "reason":
            (
                "The posting explicitly requires a currently held "
                "active security clearance."
            ),

        "pattern":
            re.compile(
                (
                    r"\bmust\s+(?:currently\s+)?"
                    r"(?:hold|possess|maintain)\s+"
                    r"(?:an?\s+)?(?:active\s+|current\s+)"
                    r"(?:top\s+secret(?:\s*/\s*sci|\s+sci)?|"
                    r"ts\s*/\s*sci|secret)\s+"
                    r"(?:security\s+)?clearance\b"
                    r"|"
                    r"\b(?:active|current)\s+"
                    r"(?:top\s+secret(?:\s*/\s*sci|\s+sci)?|"
                    r"ts\s*/\s*sci|secret)\s+"
                    r"(?:security\s+)?clearance\s+"
                    r"(?:is\s+)?required\b"
                ),
                re.I,
            ),
    },

    {
        "constraint_type": "sponsorship",
        "reason_code": "CURRENT_FUTURE_SPONSORSHIP_EXCLUSION",
        "reason": (
            "The posting explicitly requires a candidate who will not need "
            "current or future employment sponsorship."
        ),
        "pattern": re.compile(
            (
                r"\bwithout\s+(?:(?:the\s+)?need\s+for|reliance\s+on)\s+"
                r"(?:current\s+or\s+future|now\s+or\s+(?:in\s+the\s+)?future)\s+"
                r"(?:employer\s+|employment\s+|visa\s+|work\s+)?sponsorship\b"
                r"(?:\s+from\s+(?:an?\s+)?(?:employer|company))?"
            ),
            re.I,
        ),
    },

    {
        "constraint_type": "security_clearance",
        "reason_code": "ACTIVE_CLEARANCE_REQUIRED",
        "reason": (
            "The posting explicitly requires a currently held "
            "active security clearance."
        ),
        "pattern": re.compile(
            (
                r"\bmust\s+have\s+(?:an?\s+)?(?:active\s+|current\s+)"
                r"(?:top\s+secret(?:\s*/\s*sci|\s+sci)?|ts\s*/\s*sci|secret)"
                r"\s+(?:security\s+)?clearance\b"
                r"|"
                r"\b(?:active|current)\s+"
                r"(?:top\s+secret(?:\s*/\s*sci|\s+sci)?|ts\s*/\s*sci|secret)"
                r"\s+(?:security\s+)?clearance\s+(?:is\s+)?mandatory\b"
            ),
            re.I,
        ),
    },

    {
        "constraint_type": "sponsorship",
        "reason_code": "CURRENT_FUTURE_SPONSORSHIP_EXCLUSION",
        "reason": (
            "The posting explicitly requires a candidate who will not need "
            "current or future employment sponsorship."
        ),
        "pattern": re.compile(
            (
                r"\bno\s+(?:current\s+or\s+future|now\s+or\s+(?:in\s+the\s+)?future)\s+"
                r"(?:employer\s+|employment\s+|visa\s+|work\s+)?sponsorship\s+"
                r"(?:is\s+)?available\b"
                r"|"
                r"\brequire\b[^.?!\n]{0,100}"
                r"\b(?:employer\s+|employment\s+|visa\s+|work\s+)?sponsorship\b"
                r"[^.?!\n]{0,100}"
                r"\b(?:current\s+or\s+future|now\s+or\s+(?:in\s+the\s+)?future)\b"
                r"[^.?!\n]{0,100}\bnot\s+eligible\b"
                r"|"
                r"\bwithout\s+(?:employer\s+|employment\s+|visa\s+|work\s+)?"
                r"sponsorship\b[^.?!\n]{0,80}"
                r"\b(?:current\s+or\s+future|now\s+or\s+(?:in\s+the\s+)?future)\b"
                r"|"
                r"\b(?:employer\s+|employment\s+|visa\s+|work\s+)?sponsorship\s+"
                r"(?:will\s+not\s+be|is\s+not)\s+available\b"
                r"[^.?!\n]{0,80}"
                r"\b(?:current\s+or\s+future|now\s+or\s+(?:in\s+the\s+)?future)\b"
            ),
            re.I,
        ),
    },

    {
        "constraint_type": "citizenship",
        "reason_code": "EXPLICIT_US_CITIZENSHIP_REQUIREMENT",
        "reason": "The posting explicitly requires United States citizenship.",
        "pattern": re.compile(
            r"\blimited\s+to\s+(?:u\.?s\.?|united\s+states)\s+citizens?\b",
            re.I,
        ),
    },

    {
        "constraint_type": "permanent_residency",
        "reason_code": "EXPLICIT_PERMANENT_RESIDENT_REQUIREMENT",
        "reason": (
            "The posting explicitly requires permanent-resident "
            "or Green Card status."
        ),
        "pattern": re.compile(
            r"\bpermanent\s+residents?\s+only\b",
            re.I,
        ),
    },

    {
        "constraint_type": "security_clearance",
        "reason_code": "ACTIVE_CLEARANCE_REQUIRED",
        "reason": (
            "The posting explicitly requires a currently held "
            "active security clearance."
        ),
        "pattern": re.compile(
            (
                r"\bmust\s+already\s+hold\s+(?:an?\s+)?"
                r"(?:active\s+|current\s+)?"
                r"(?:top\s+secret(?:\s*/\s*sci|\s+sci)?|"
                r"ts\s*/\s*sci|secret)\s+"
                r"(?:security\s+)?clearance\b"
            ),
            re.I,
        ),
    },

    {
        "constraint_type":
            "sponsorship",

        "reason_code":
            "CURRENT_FUTURE_SPONSORSHIP_EXCLUSION",

        "reason":
            (
                "The posting explicitly requires a candidate who will not "
                "need current or future employment sponsorship."
            ),

        "pattern":
            re.compile(
                (
                    r"\b(?:cannot|can't|can\s+not)\s+"
                    r"(?:provide|offer)\b"
                    r"[^.?!\n]{0,100}"
                    r"\b(?:employer\s+|employment\s+|visa\s+|work\s+)?"
                    r"sponsorship\b"
                    r"[^.?!\n]{0,80}"
                    r"\b(?:current\s+or\s+future|"
                    r"now\s+or\s+(?:in\s+the\s+)?future)\b"
                ),
                re.I,
            ),
    },

]


REVIEW_SPONSORSHIP = re.compile(
    (
        r"\b(?:will|does|do|can)\s+not\s+sponsor\b"
        r"|"
        r"\b(?:unable|not\s+able)\s+to\s+sponsor\b"
        r"|"
        r"\b(?:no|without)\s+"
        r"(?:employer\s+|employment\s+|visa\s+|work\s+)?sponsorship\b"
        r"|"
        r"\b(?:cannot|can't)\s+(?:provide|offer)\s+"
        r"(?:visa\s+|employment\s+|work\s+|employer\s+)?sponsorship\b"
        r"|"
        r"\b(?:visa\s+|employment\s+|work\s+|employer\s+)?"
        r"sponsorship\s+is\s+not\s+available\b"
        r"|"
        r"\b(?:this\s+role|this\s+position|the\s+role|the\s+position)"
        r"\s+is\s+not\s+eligible\s+for\s+"
        r"(?:employer\s+|employment\s+|visa\s+|work\s+)?sponsorship\b"
    ),
    re.I,
)


GEOGRAPHIC_RESIDENCY = re.compile(
    (
        r"\b(?:applicants?|candidates?|employees?)\b"
        r"[^.?!]{0,120}"
        r"\bmust\s+(?:currently\s+)?reside\b"
        r"[^.?!]{0,180}"
    ),
    re.I,
)


def _sha(
    path,
):
    return hashlib.sha256(
        Path(
            path
        ).read_bytes()
    ).hexdigest()


def _norm(
    value,
):
    value = (
        str(
            value
            or ""
        )
        .replace(
            "\r\n",
            "\n",
        )
        .replace(
            "\r",
            "\n",
        )
        .replace(
            "’",
            "'",
        )
        .casefold()
    )

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def _paragraphs(
    raw_jd,
):
    lines = (
        str(
            raw_jd
            or ""
        )
        .replace(
            "\r\n",
            "\n",
        )
        .replace(
            "\r",
            "\n",
        )
        .splitlines()
    )

    paragraphs = []
    current = []

    for number, raw in enumerate(
        lines,
        start=1,
    ):
        text = str(
            raw
            or ""
        ).strip()

        if not text:
            if current:
                paragraphs.append(
                    current
                )

                current = []

            continue

        current.append(
            (
                number,
                text,
            )
        )

    if current:
        paragraphs.append(
            current
        )

    return (
        lines,
        paragraphs,
    )


def _windows(
    raw_jd,
    max_width=4,
):
    _lines, paragraphs = (
        _paragraphs(
            raw_jd
        )
    )

    for paragraph in paragraphs:
        maximum = min(
            max_width,
            len(
                paragraph
            ),
        )

        for width in range(
            1,
            maximum + 1,
        ):
            for start in range(
                0,
                len(
                    paragraph
                )
                - width
                + 1,
            ):
                part = paragraph[
                    start:
                    start + width
                ]

                yield {
                    "start_line":
                        part[
                            0
                        ][
                            0
                        ],

                    "end_line":
                        part[
                            -1
                        ][
                            0
                        ],

                    "text":
                        " ".join(
                            value
                            for _line, value
                            in part
                        ),
                }


def _question_like(
    text,
):
    normalized = _norm(
        text
    )

    return bool(
        "?"
        in str(
            text
        )
        and re.search(
            (
                r"\b(sponsor|sponsorship|"
                r"authorized to work|work authorization|"
                r"citizenship|clearance)\b"
            ),
            normalized,
            re.I,
        )
    )


STRICT_RULES.append({
    'constraint_type':'work_authorization','reason_code':'CURRENT_FUTURE_SPONSORSHIP_EXCLUDED',
    'reason':'The posting explicitly excludes candidates requiring employer sponsorship now or in the future.',
    'pattern':re.compile(r"\bmust\s+not\s+require\b[^.?!\n]{0,100}\bsponsorship\b[^.?!\n]{0,80}\bnow\s+or\s+in\s+(?:the\s+)?future\b",re.I),
})

def detect_document_constraints(
    intake,
):
    raw_jd = intake.get(
        "raw_jd_text",
        "",
    )

    findings = []

    def overlaps_existing(
        candidate,
    ):
        for item in findings:
            if (
                item[
                    "policy"
                ]
                == candidate[
                    "policy"
                ]
                and item[
                    "constraint_type"
                ]
                == candidate[
                    "constraint_type"
                ]
                and not (
                    candidate[
                        "end_line"
                    ]
                    < item[
                        "start_line"
                    ]
                    or candidate[
                        "start_line"
                    ]
                    > item[
                        "end_line"
                    ]
                )
            ):
                return True

        return False

    for window in _windows(
        raw_jd
    ):
        text = window[
            "text"
        ]

        if _question_like(
            text
        ):
            continue

        strict_match = None
        strict_rule = None

        for rule in STRICT_RULES:
            if rule["constraint_type"]=="security_clearance":
                from careerops_eligibility_patterns import active_clearance_requirement
                if not active_clearance_requirement(text):continue
            match = rule[
                "pattern"
            ].search(
                text
            )

            if match:
                strict_match = match
                strict_rule = rule
                break

        if strict_rule:
            candidate = {
                "policy":
                    "HARD_BLOCK",

                "constraint_type":
                    strict_rule[
                        "constraint_type"
                    ],

                "reason_code":
                    strict_rule[
                        "reason_code"
                    ],

                "deterministic_reason":
                    strict_rule[
                        "reason"
                    ],

                "start_line":
                    window[
                        "start_line"
                    ],

                "end_line":
                    window[
                        "end_line"
                    ],

                "exact_source_quote":
                    text,

                "matched_text":
                    strict_match.group(
                        0
                    ),
            }

            if not overlaps_existing(
                candidate
            ):
                findings.append(
                    candidate
                )

            continue

        review = (
            REVIEW_SPONSORSHIP
            .search(
                text
            )
        )

        if review:
            candidate = {
                "policy":
                    "REVIEW_ONLY",

                "constraint_type":
                    "sponsorship",

                "reason_code":
                    "GENERIC_NO_SPONSORSHIP_REVIEW_ONLY",

                "deterministic_reason":
                    (
                        "The posting contains a generic no-sponsorship "
                        "statement, but it does not explicitly exclude "
                        "F-1/OPT/STEM OPT or require a candidate who will "
                        "not need current/future sponsorship."
                    ),

                "start_line":
                    window[
                        "start_line"
                    ],

                "end_line":
                    window[
                        "end_line"
                    ],

                "exact_source_quote":
                    text,

                "matched_text":
                    review.group(
                        0
                    ),
            }

            if not overlaps_existing(
                candidate
            ):
                findings.append(
                    candidate
                )

            continue

        geographic = (
            GEOGRAPHIC_RESIDENCY
            .search(
                text
            )
        )

        if geographic:
            candidate = {
                "policy":
                    "VALIDATE_PROFILE",

                "constraint_type":
                    "geographic_residency",

                "reason_code":
                    "CURRENT_RESIDENCY_REQUIREMENT",

                "deterministic_reason":
                    (
                        "The posting appears to impose a current-residency "
                        "requirement and therefore requires candidate-profile "
                        "geography validation."
                    ),

                "start_line":
                    window[
                        "start_line"
                    ],

                "end_line":
                    window[
                        "end_line"
                    ],

                "exact_source_quote":
                    text,

                "matched_text":
                    geographic.group(
                        0
                    ),
            }

            if not overlaps_existing(
                candidate
            ):
                findings.append(
                    candidate
                )

    findings.sort(
        key=lambda row: (
            row[
                "start_line"
            ],
            row[
                "end_line"
            ],
            row[
                "constraint_type"
            ],
        )
    )

    counters = {
        "HARD_BLOCK":
            0,
        "REVIEW_ONLY":
            0,
        "VALIDATE_PROFILE":
            0,
    }

    prefixes = {
        "HARD_BLOCK":
            "DOC-HARD",
        "REVIEW_ONLY":
            "DOC-REVIEW",
        "VALIDATE_PROFILE":
            "DOC-GEO",
    }

    for row in findings:
        policy = row[
            "policy"
        ]

        counters[
            policy
        ] += 1

        row[
            "semantic_constraint_id"
        ] = (
            f"{prefixes[policy]}-"
            f"{counters[policy]:03d}"
        )

    return findings


def _map_document_constraint(
    constraint,
    annotations,
):
    candidates = []

    for row in annotations:
        start = row.get(
            "source_anchor_start_line"
        )

        end = row.get(
            "source_anchor_end_line"
        )

        if not isinstance(
            start,
            int,
        ):
            continue

        if not isinstance(
            end,
            int,
        ):
            end = start

        overlap = not (
            end
            < constraint[
                "start_line"
            ]
            or start
            > constraint[
                "end_line"
            ]
        )

        if overlap:
            distance = 0
        else:
            distance = min(
                abs(
                    start
                    - constraint[
                        "start_line"
                    ]
                ),
                abs(
                    end
                    - constraint[
                        "end_line"
                    ]
                ),
            )

        candidates.append(
            (
                1
                if overlap
                else 0,
                -distance,
                row,
            )
        )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: (
            item[
                0
            ],
            item[
                1
            ],
        ),
        reverse=True,
    )

    overlap_flag, negative_distance, row = (
        candidates[
            0
        ]
    )

    if (
        overlap_flag == 0
        and -negative_distance
        > 1
    ):
        return None

    return row.get(
        "requirement_id"
    )


def _sponsorship_only_quote(
    quote,
):
    normalized = _norm(
        quote
    )

    if not re.search(
        r"\bsponsor|sponsorship\b",
        normalized,
    ):
        return False

    return not bool(
        re.search(
            (
                r"\b(degree|education|experience|"
                r"proficiency|knowledge|skill|ability|"
                r"sql|python|tableau|power bi|excel)\b"
            ),
            normalized,
        )
    )


def build_effective_bundle(
    intake,
    ledger,
    *,
    intake_sha=None,
    ledger_sha=None,
):
    sidecar = build_sidecar(
        intake,
        ledger,
        intake_sha,
        ledger_sha,
    )

    effective = (
        build_effective_view(
            ledger,
            sidecar,
        )
    )

    annotations = (
        sidecar.get(
            "annotations",
            [],
        )
        or []
    )

    effective_rows = (
        effective.get(
            "requirements",
            [],
        )
        or []
    )

    effective_by_id = {
        row.get(
            "requirement_id"
        ):
            row
        for row in effective_rows
    }

    source_by_id = {
        row.get(
            "requirement_id"
        ):
            row
        for row in (
            ledger.get(
                "requirements",
                [],
            )
            or []
        )
    }

    document_constraints = (
        detect_document_constraints(
            intake
        )
    )

    for constraint in document_constraints:
        requirement_id = (
            _map_document_constraint(
                constraint,
                annotations,
            )
        )

        constraint[
            "mapped_requirement_id"
        ] = requirement_id

        if not requirement_id:
            continue

        row = effective_by_id.get(
            requirement_id
        )

        if not row:
            continue

        if (
            constraint[
                "policy"
            ]
            == "HARD_BLOCK"
        ):
            row[
                "decision_priority"
            ] = "P0"

            row[
                "semantic_class"
            ] = "HARD_BLOCK"

            row[
                "modality"
            ] = "REQUIRED"

            row[
                "active_for_decision"
            ] = True

            row[
                "decision_role"
            ] = (
                "EXPLICIT_HARD_BLOCKER_CANDIDATE"
            )

            row[
                "eligible_for_constraint_validation"
            ] = True

            row[
                "effective_hard_blocker_phrases"
            ] = [
                constraint[
                    "matched_text"
                ]
            ]

            row[
                "document_policy"
            ] = "HARD_BLOCK"

            row[
                "document_constraint_id"
            ] = constraint[
                "semantic_constraint_id"
            ]

        elif (
            constraint[
                "policy"
            ]
            == "REVIEW_ONLY"
        ):
            row[
                "effective_hard_blocker_phrases"
            ] = []

            row[
                "document_policy"
            ] = "REVIEW_ONLY"

            row[
                "document_constraint_id"
            ] = constraint[
                "semantic_constraint_id"
            ]

            source = source_by_id.get(
                requirement_id,
                {},
            )

            if _sponsorship_only_quote(
                source.get(
                    "exact_quote",
                    "",
                )
            ):
                row[
                    "decision_priority"
                ] = None

                row[
                    "semantic_class"
                ] = (
                    "WORK_AUTHORIZATION_REVIEW"
                )

                row[
                    "modality"
                ] = "REVIEW"

                row[
                    "active_for_decision"
                ] = False

                row[
                    "decision_role"
                ] = (
                    "REVIEW_ONLY_NON_DECISION"
                )

                row[
                    "eligible_for_constraint_validation"
                ] = False

        elif (
            constraint[
                "policy"
            ]
            == "VALIDATE_PROFILE"
        ):
            row[
                "document_policy"
            ] = "VALIDATE_PROFILE"

            row[
                "document_constraint_id"
            ] = constraint[
                "semantic_constraint_id"
            ]

            row[
                "eligible_for_constraint_validation"
            ] = True

    recognized_policy_ids = {
        row.get(
            "mapped_requirement_id"
        )
        for row in document_constraints
        if row.get(
            "mapped_requirement_id"
        )
    }

    unknown_source_hard_blockers = []

    for requirement_id, source in (
        source_by_id.items()
    ):
        source_hard = (
            source.get(
                "hard_blocker_phrases",
                [],
            )
            or []
        )

        if (
            source_hard
            and requirement_id
            not in recognized_policy_ids
        ):
            unknown_source_hard_blockers.append(
                requirement_id
            )

    problems = list(
        effective.get(
            "problems",
            [],
        )
        or []
    )

    if unknown_source_hard_blockers:
        problems.append(
            "UNCLASSIFIED_SOURCE_HARD_BLOCKER"
        )

    if sidecar.get(
        "unresolved_source_anchor_count",
        0,
    ):
        problems.append(
            "UNRESOLVED_SOURCE_ALIGNMENT"
        )

    if sidecar.get(
        "ambiguous_source_anchor_count",
        0,
    ):
        problems.append(
            "AMBIGUOUS_SOURCE_ALIGNMENT"
        )

    problems = list(
        dict.fromkeys(
            problems
        )
    )

    effective[
        "status"
    ] = (
        "PASS"
        if not problems
        else "NEEDS_ATTENTION"
    )

    effective[
        "problems"
    ] = problems

    effective[
        "document_constraints"
    ] = document_constraints

    effective[
        "unknown_source_hard_blocker_ids"
    ] = unknown_source_hard_blockers

    effective.setdefault(
        "policy",
        {},
    )[
        "generic_no_sponsorship_is_review_only"
    ] = True

    effective[
        "policy"
    ][
        "strict_current_future_sponsorship_exclusion_is_hard_block"
    ] = True

    effective[
        "policy"
    ][
        "line_wrapped_eligibility_is_reconstructed"
    ] = True

    derived = copy.deepcopy(
        ledger
    )

    derived_requirements = []

    for source in (
        ledger.get(
            "requirements",
            [],
        )
        or []
    ):
        requirement_id = source.get(
            "requirement_id"
        )

        semantic = effective_by_id.get(
            requirement_id
        )

        if not semantic:
            continue

        if not semantic.get(
            "active_for_decision",
            True,
        ):
            continue

        row = copy.deepcopy(
            source
        )

        row[
            "source_priority"
        ] = source.get(
            "priority"
        )

        row["priority"] = source.get("priority")

        row[
            "semantic_class"
        ] = semantic.get(
            "semantic_class"
        )

        row[
            "semantic_modality"
        ] = semantic.get(
            "modality"
        )

        row[
            "qualification_relation"
        ] = semantic.get(
            "qualification_relation"
        )

        row[
            "effective_source_section"
        ] = semantic.get(
            "effective_source_section"
        )

        row[
            "source_section_basis"
        ] = semantic.get(
            "source_section_basis"
        )

        row[
            "active_for_decision"
        ] = True

        row[
            "eligible_for_constraint_validation"
        ] = semantic.get(
            "eligible_for_constraint_validation",
            False,
        )

        row[
            "document_policy"
        ] = semantic.get(
            "document_policy"
        )

        # Immutable phrases and duration metadata remain owned by the ledger.
        row["document_hard_blocker_phrases"] = semantic.get("effective_hard_blocker_phrases") or []
        derived_requirements.append(
            row
        )

    priority_counts = {}

    for row in derived_requirements:
        priority = row.get(
            "priority"
        )

        if priority:
            priority_counts[
                priority
            ] = (
                priority_counts.get(
                    priority,
                    0,
                )
                + 1
            )

    derived[
        "schema_version"
    ] = (
        "jd-requirements-effective-v1"
    )

    derived[
        "source_schema_version"
    ] = ledger.get(
        "schema_version"
    )

    derived[
        "source_requirement_count"
    ] = len(
        ledger.get(
            "requirements",
            [],
        )
        or []
    )

    derived[
        "requirement_count"
    ] = len(
        derived_requirements
    )

    derived[
        "priority_counts"
    ] = priority_counts

    derived[
        "requirements"
    ] = derived_requirements

    derived[
        "document_constraints"
    ] = document_constraints

    derived[
        "semantic_sidecar_status"
    ] = effective[
        "status"
    ]

    derived[
        "policy"
    ] = {
        **(
            derived.get(
                "policy",
                {},
            )
            or {}
        ),

        "derived_not_source":
            True,

        "source_ledger_immutable":
            True,

        "inactive_context_removed_from_downstream":
            True,

        "P2_supporting_retained_for_tailoring":
            True,

        "semantic_layer_cannot_itself_authorize_rejection":
            True,
    }

    return {
        "status":
            effective[
                "status"
            ],

        "sidecar":
            sidecar,

        "effective_view":
            effective,

        "effective_ledger":
            derived,

        "document_constraints":
            document_constraints,

        "unknown_source_hard_blocker_ids":
            unknown_source_hard_blockers,
    }


def _atomic_json(
    path,
    payload,
):
    path = Path(
        path
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = path.with_suffix(
        path.suffix
        + ".tmp"
    )

    temporary.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    temporary.replace(
        path
    )


def ensure_effective_runtime(
    runtime,
):
    runtime = Path(
        runtime
    )

    intake_path = (
        runtime
        / "jd_intake.json"
    )

    from careerops_requirement_regeneration import canonical_ledger_path
    ledger_path = canonical_ledger_path(runtime)

    if not intake_path.is_file():
        raise RuntimeError(
            f"Missing immutable intake: {intake_path}"
        )

    if not ledger_path.is_file():
        raise RuntimeError(
            f"Missing immutable source ledger: {ledger_path}"
        )

    intake_before = _sha(
        intake_path
    )

    ledger_before = _sha(
        ledger_path
    )

    intake = json.loads(
        intake_path.read_text(
            encoding="utf-8"
        )
    )

    ledger = json.loads(
        ledger_path.read_text(
            encoding="utf-8"
        )
    )

    bundle = build_effective_bundle(
        intake,
        ledger,
        intake_sha=intake_before,
        ledger_sha=ledger_before,
    )

    if _sha(
        intake_path
    ) != intake_before:
        raise RuntimeError(
            "FAIL CLOSED: jd_intake.json was mutated"
        )

    if _sha(
        ledger_path
    ) != ledger_before:
        raise RuntimeError(
            "FAIL CLOSED: jd_requirements.json was mutated"
        )

    from careerops_overall_override import quarantine_authorized
    explicit_quarantine = quarantine_authorized(runtime, intake_before, ledger_before) if (runtime/'quarantine_generation_authorization.json').is_file() else False
    if bundle[
        "status"
    ] != "PASS" and not explicit_quarantine:
        raise RuntimeError(
            "FAIL CLOSED: effective requirement view not PASS: "
            + ", ".join(
                bundle[
                    "effective_view"
                ].get(
                    "problems",
                    [],
                )
            )
        )

    _atomic_json(
        runtime
        / "jd_semantic_sidecar.json",
        bundle[
            "sidecar"
        ],
    )

    _atomic_json(
        runtime
        / "effective_requirements.json",
        bundle[
            "effective_view"
        ],
    )

    _atomic_json(
        runtime
        / "jd_requirements_effective.json",
        bundle[
            "effective_ledger"
        ],
    )

    from careerops_requirement_authority import check_artifact
    for name in ['effective_requirements.json', 'jd_requirements_effective.json']:
        check_artifact(runtime, name, stamp=True)

    return bundle
