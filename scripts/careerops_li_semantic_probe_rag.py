#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
import time
import urllib.error
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(SCRIPT_DIR),
    )

import careerops_li_semantic_probe as base


RAG_GUARDRAILS = """
RETRIEVAL CONTEXT RULES
-----------------------
The retrieval context is internal CareerOps memory.

GOLD_GUIDANCE_ONLY:
- may help you recognize a policy or semantic pattern;
- is NOT evidence about the current employer or current posting;
- never copy employer/title/requisition values from retrieval.

FAILURE_DIAGNOSTIC_ONLY:
- describes historical mistake patterns;
- is NEVER authority;
- is NEVER the correct answer merely because it was retrieved;
- use it only as a warning about what mistake to avoid.

RAW SOURCE is the only source of current-posting evidence.
Deterministic state is the thing being audited.
Retrieval may guide attention but cannot create facts, quotes,
requirements, eligibility conditions, or identity values.

Your output job remains narrow:
source identity + semantic finding types + exact source line numbers only.
""".strip()


def call_probe_rag(
    raw_source,
    deterministic,
    retrieval_context,
    *,
    timeout=120,
):
    ids = base.requirement_ids(
        deterministic
    )

    schema = base.make_schema(
        ids
    )

    user = {
        "raw_source_with_line_numbers":
            base.numbered(
                raw_source
            ),

        "deterministic_state":
            deterministic,

        "allowed_requirement_ids":
            ids,

        "retrieval_context":
            retrieval_context,

        "instruction":
            (
                "Read RAW SOURCE first. "
                "Use retrieval only as non-authoritative pattern guidance. "
                "Return only source identity and material findings. "
                "Use exact source line numbers. Do not invent IDs."
            ),
    }

    payload = {
        "model":
            base.MODEL,

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
                    base.SYSTEM
                    + "\n\n"
                    + RAG_GUARDRAILS,
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
                8192,

            "num_predict":
                1100,
        },

        "keep_alive":
            "15m",
    }

    started = time.perf_counter()
    compatibility_retry = False

    try:
        response = base.post(
            payload,
            timeout,
        )

    except urllib.error.HTTPError as exc:
        body = exc.read().decode(
            "utf-8",
            errors="replace",
        )

        if exc.code != 400:
            raise RuntimeError(
                f"RAG_PROBE_HTTP_{exc.code}:{body}"
            ) from exc

        # Match the already-accepted Ollama compatibility
        # contract. A 400 may indicate an older runtime that
        # does not accept the think field. The failed HTTP
        # request performs no model inference.
        compatibility_retry = True
        payload.pop("think", None)

        response = base.post(
            payload,
            timeout,
        )

    elapsed = (
        time.perf_counter()
        - started
    )

    content = (
        response
        .get(
            "message",
            {},
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
            "RAG_PROBE_CONTENT_NOT_TEXT"
        )

    try:
        obj = json.loads(
            content
        )

    except Exception as exc:
        done_reason = response.get(
            "done_reason"
        )

        eval_count = response.get(
            "eval_count"
        )

        output_budget_exhausted = (
            done_reason == "length"
            or (
                isinstance(
                    eval_count,
                    int,
                )
                and eval_count >= 1100
            )
        )

        if output_budget_exhausted:
            raise RuntimeError(
                "RAG_PROBE_TRUNCATED_OUTPUT="
                + repr(
                    content[:1200]
                )
            ) from exc

        # Deliberately do not guess/repair malformed model JSON.
        # Local intelligence is advisory and remains fail-open.
        raise RuntimeError(
            "RAG_PROBE_NON_JSON="
            + repr(
                content[:1200]
            )
        ) from exc

    obj["_metadata"] = {
        "runtime":
            "OLLAMA",

        "model":
            base.MODEL,

        "mode":
            "BM25_RAG",

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

        "compatibility_retry":
            compatibility_retry,

        "done_reason":
            response.get(
                "done_reason"
            ),

        "output_token_budget":
            1100,

        "retrieval_result_count":
            len(
                retrieval_context
            ),
    }

    return obj


if __name__ == "__main__":
    raise SystemExit(
        "Import call_probe_rag() from CareerOps LI."
    )
