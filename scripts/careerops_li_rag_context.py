#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(
        name,
        path,
    )

    module = importlib.util.module_from_spec(
        spec
    )

    spec.loader.exec_module(
        module
    )

    return module


retriever = load_module(
    "li_retriever_runtime",
    SCRIPTS / "careerops_li_retrieve.py",
)

hybrid = load_module(
    "li_hybrid_runtime",
    SCRIPTS / "careerops_li_hybrid_shadow.py",
)


EXCLUDED_GOLD_PATH_TERMS = {
    "candidate_facts",
    "assumed_market_coverage",
    "master_experience",
    "verified_evidence",
    "cover_letter_rules",
    "resume_layout",
    "generated_resume",
    "generated_cover",
}


def eligible_gold(row):
    source = str(
        row.get(
            "source_path",
            "",
        )
    ).casefold()

    return not any(
        term in source
        for term in EXCLUDED_GOLD_PATH_TERMS
    )


def build_query(
    raw_source,
    deterministic,
):
    sentinel_types = sorted(
        {
            row.get(
                "finding_type"
            )
            for row in hybrid.sentinel_findings(
                raw_source,
                deterministic,
            )
            if row.get(
                "finding_type"
            )
        }
    )

    identity = [
        deterministic.get("company"),
        deterministic.get("employer"),
        deterministic.get("job_title"),
        deterministic.get("title"),
        deterministic.get("requisition_id"),
        deterministic.get("job_id"),
    ]

    return "\n".join(
        [
            raw_source,
            "semantic phenomena: "
            + " ".join(
                value.replace(
                    "_",
                    " ",
                )
                for value in sentinel_types
            ),
            "deterministic identity: "
            + " ".join(
                str(value)
                for value in identity
                if value
            ),
        ]
    )


def compact(
    row,
    *,
    authority,
    max_chars=800,
):
    text = str(
        row.get(
            "text",
            "",
        )
    )

    if len(text) > max_chars:
        text = (
            text[:max_chars]
            + "…"
        )

    return {
        "corpus_class":
            row.get(
                "corpus_class"
            ),

        "authority":
            authority,

        "source_path":
            row.get(
                "source_path"
            ),

        "chunk_id":
            row.get(
                "chunk_id"
            ),

        "retrieval_score":
            row.get(
                "retrieval_score"
            ),

        "text":
            text,
    }


def build_context(
    raw_source,
    deterministic,
    *,
    gold_top_k=4,
    failure_top_k=2,
):
    query = build_query(
        raw_source,
        deterministic,
    )

    gold = [
        row
        for row in retriever.load(
            "gold"
        )
        if eligible_gold(
            row
        )
    ]

    failure = retriever.load(
        "failure"
    )

    gold_hits = retriever.bm25(
        gold,
        query,
        gold_top_k,
    )

    failure_hits = retriever.bm25(
        failure,
        query,
        failure_top_k,
    )

    context = [
        compact(
            row,
            authority=
                "GOLD_GUIDANCE_ONLY",
        )
        for row in gold_hits
    ]

    context.extend(
        compact(
            row,
            authority=
                "FAILURE_DIAGNOSTIC_ONLY",
        )
        for row in failure_hits
    )

    return {
        "backend":
            "DETERMINISTIC_BM25",

        "query":
            query,

        "gold_count":
            len(
                gold_hits
            ),

        "failure_count":
            len(
                failure_hits
            ),

        "results":
            context,
    }


if __name__ == "__main__":
    raise SystemExit(
        "Import build_context() from CareerOps LI."
    )
