#!/usr/bin/env python3

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


ENDPOINT = "http://127.0.0.1:11434/api/chat"
MODEL = "qwen3:8b"


FINDING_TYPES = [
    "EMPLOYER_HISTORY",
    "APPLICATION_QUESTION",
    "PAGE_CHROME",
    "PREFERRED_REQUIREMENT",
    "EDUCATION_EXPERIENCE_SUBSTITUTION",
    "GENERIC_NO_SPONSORSHIP",
    "EXPLICIT_CURRENT_OR_FUTURE_NO_SPONSORSHIP",
    "ACTIVE_CLEARANCE_REQUIRED",
    "ABILITY_TO_OBTAIN_CLEARANCE_AFTER_HIRE",
    "TOOL_TENURE",
    "OCCUPATIONAL_DURATION",
    "COMPOUND_REQUIREMENT_MISSING_COMPONENT",
    "SECTION_CONTEXT_RESET",
    "MISSED_REQUIREMENT",
    "FALSE_REQUIREMENT",
]


SYSTEM = """
You are a narrow CareerOps source-review probe.

Do NOT make a hiring or eligibility decision.
Do NOT output CareerOps priorities, classifications, relations or semantic flags.
Do NOT invent requirement IDs.
Do NOT quote text.

Your only tasks are:

1. Read the numbered RAW SOURCE.
2. Extract the visible employer, job title and requisition/job ID when present.
3. Identify only the semantic phenomena listed in finding_type.
4. Point to the exact source line or lines supporting each finding.
5. Select a requirement_id only from the supplied allowed IDs, otherwise null.

finding_type meanings:

EMPLOYER_HISTORY
Company history/background that is not applicant tenure.

APPLICATION_QUESTION
Application-form question rather than a JD qualification.

PAGE_CHROME
Navigation/site chrome rather than JD content.

PREFERRED_REQUIREMENT
Source makes a qualification preferred, desired, optional or "a plus".

EDUCATION_EXPERIENCE_SUBSTITUTION
Experience may substitute for education, or education may substitute for experience.

GENERIC_NO_SPONSORSHIP
Generic statement such as "we do not sponsor employment visas".

EXPLICIT_CURRENT_OR_FUTURE_NO_SPONSORSHIP
Explicit wording that applicant must work without current/future employer sponsorship,
or explicit no F-1/OPT/STEM equivalent.

ACTIVE_CLEARANCE_REQUIRED
Applicant must already possess/currently hold an active clearance.

ABILITY_TO_OBTAIN_CLEARANCE_AFTER_HIRE
Applicant may obtain clearance/Public Trust after hire rather than already possessing it.

TOOL_TENURE
Years of experience USING a tool/technology, not occupational tenure.

OCCUPATIONAL_DURATION
Years of professional/occupational experience.

COMPOUND_REQUIREMENT_MISSING_COMPONENT
One source sentence contains multiple required components and deterministic state captures
only part of it.

SECTION_CONTEXT_RESET
A heading changes semantic state, especially Minimum -> Preferred Qualifications.

MISSED_REQUIREMENT
A substantive source requirement is absent from deterministic state.

FALSE_REQUIREMENT
Deterministic state treats source material as a requirement when source context shows it
is not one.

Be conservative. Output no finding when the phenomenon is not actually present.
""".strip()


def post(payload, timeout):
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(
            payload
        ).encode("utf-8"),
        headers={
            "Content-Type":
                "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(
        req,
        timeout=timeout,
    ) as response:
        return json.loads(
            response.read().decode(
                "utf-8"
            )
        )


def numbered(text):
    return "\n".join(
        f"{i}: {line}"
        for i, line in enumerate(
            text.splitlines(),
            start=1,
        )
    )


def make_schema(allowed_ids):
    requirement_enum = [
        None,
        *sorted(
            set(
                allowed_ids
            )
        ),
    ]

    return {
        "type":
            "object",

        "additionalProperties":
            False,

        "required": [
            "source_identity",
            "findings",
        ],

        "properties": {
            "source_identity": {
                "type":
                    "object",

                "additionalProperties":
                    False,

                "required": [
                    "employer_name",
                    "employer_line",
                    "job_title",
                    "job_title_line",
                    "requisition_id",
                    "requisition_line",
                ],

                "properties": {
                    "employer_name": {
                        "type": [
                            "string",
                            "null",
                        ],
                    },

                    "employer_line": {
                        "type": [
                            "integer",
                            "null",
                        ],
                    },

                    "job_title": {
                        "type": [
                            "string",
                            "null",
                        ],
                    },

                    "job_title_line": {
                        "type": [
                            "integer",
                            "null",
                        ],
                    },

                    "requisition_id": {
                        "type": [
                            "string",
                            "null",
                        ],
                    },

                    "requisition_line": {
                        "type": [
                            "integer",
                            "null",
                        ],
                    },
                },
            },

            "findings": {
                "type":
                    "array",

                "maxItems":
                    12,

                "items": {
                    "type":
                        "object",

                    "additionalProperties":
                        False,

                    "required": [
                        "finding_type",
                        "start_line",
                        "end_line",
                        "requirement_id",
                        "confidence",
                    ],

                    "properties": {
                        "finding_type": {
                            "type":
                                "string",

                            "enum":
                                FINDING_TYPES,
                        },

                        "start_line": {
                            "type":
                                "integer",
                        },

                        "end_line": {
                            "type":
                                "integer",
                        },

                        "requirement_id": {
                            "enum":
                                requirement_enum,
                        },

                        "confidence": {
                            "type":
                                "string",

                            "enum": [
                                "HIGH",
                                "MEDIUM",
                                "LOW",
                            ],
                        },
                    },
                },
            },
        },
    }


def requirement_ids(deterministic):
    found = set()

    def walk(value):
        if isinstance(value, dict):
            rid = value.get(
                "requirement_id"
            )

            if isinstance(
                rid,
                str,
            ):
                found.add(
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

    return sorted(
        found
    )


def call_probe(
    raw_source,
    deterministic,
    timeout=90,
):
    ids = requirement_ids(
        deterministic
    )

    schema = make_schema(
        ids
    )

    user = {
        "raw_source_with_line_numbers":
            numbered(
                raw_source
            ),

        "deterministic_state":
            deterministic,

        "allowed_requirement_ids":
            ids,

        "instruction":
            (
                "Return only source identity and material findings. "
                "Use exact source line numbers. Do not invent IDs."
            ),
    }

    payload = {
        "model":
            MODEL,

        "stream":
            False,

        "think":
            False,

        "format":
            schema,

        "messages": [
            {
                "role":
                    "system",

                "content":
                    SYSTEM,
            },
            {
                "role":
                    "user",

                "content":
                    json.dumps(
                        user,
                        ensure_ascii=False,
                    ),
            },
        ],

        "options": {
            "temperature":
                0,

            "num_ctx":
                4096,

            "num_predict":
                600,
        },

        "keep_alive":
            "15m",
    }

    started = time.perf_counter()

    try:
        response = post(
            payload,
            timeout,
        )

    except urllib.error.HTTPError as exc:
        body = exc.read().decode(
            "utf-8",
            errors="replace",
        )

        raise RuntimeError(
            f"OLLAMA_HTTP_{exc.code}:{body}"
        )

    elapsed = (
        time.perf_counter()
        - started
    )

    content = (
        response
        .get(
            "message",
            {}
        )
        .get(
            "content"
        )
    )

    if not isinstance(
        content,
        str,
    ):
        raise RuntimeError(
            "PROBE_CONTENT_NOT_TEXT"
        )

    try:
        obj = json.loads(
            content
        )

    except Exception as exc:
        raise RuntimeError(
            "PROBE_NON_JSON="
            + repr(
                content[:1200]
            )
        ) from exc

    obj["_metadata"] = {
        "runtime":
            "OLLAMA",

        "model":
            MODEL,

        "elapsed_seconds":
            round(
                elapsed,
                3,
            ),

        "prompt_eval_count":
            response.get(
                "prompt_eval_count"
            ),

        "eval_count":
            response.get(
                "eval_count"
            ),
    }

    return obj
