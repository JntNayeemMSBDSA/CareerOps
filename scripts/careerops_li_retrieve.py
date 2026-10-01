#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CORPUS_DIR = (
    ROOT
    / "examples/local-intelligence/corpus"
)

FILES = {
    "gold":
        CORPUS_DIR
        / "careerops_gold_corpus.jsonl",

    "failure":
        CORPUS_DIR
        / "careerops_failure_corpus.jsonl",
}


TOKEN_RE = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9_+./-]*"
)


def tokenize(text):
    return [
        token.casefold()
        for token in TOKEN_RE.findall(
            str(text or "")
        )
    ]


def load(kind):
    rows = []

    kinds = (
        ("gold", "failure")
        if kind == "all"
        else (kind,)
    )

    for name in kinds:
        path = FILES[name]

        for line in path.read_text(
            encoding="utf-8"
        ).splitlines():
            if line.strip():
                rows.append(
                    json.loads(line)
                )

    return rows


def bm25(rows, query, top_k):
    query_tokens = tokenize(query)

    docs = [
        tokenize(
            row.get("text", "")
        )
        for row in rows
    ]

    n = len(docs)

    if not n or not query_tokens:
        return []

    avgdl = (
        sum(len(doc) for doc in docs)
        / n
    )

    df = Counter()

    for doc in docs:
        df.update(set(doc))

    k1 = 1.5
    b = 0.75

    scored = []

    for row, doc in zip(rows, docs):
        tf = Counter(doc)
        score = 0.0
        dl = len(doc)

        for term in query_tokens:
            freq = tf.get(term, 0)

            if not freq:
                continue

            term_df = df.get(term, 0)

            idf = math.log(
                1
                + (
                    n
                    - term_df
                    + 0.5
                )
                / (
                    term_df
                    + 0.5
                )
            )

            denom = (
                freq
                + k1
                * (
                    1
                    - b
                    + b
                    * dl
                    / max(avgdl, 1)
                )
            )

            score += (
                idf
                * freq
                * (k1 + 1)
                / denom
            )

        if score > 0:
            item = dict(row)
            item["retrieval_score"] = round(
                score,
                8,
            )
            scored.append(item)

    scored.sort(
        key=lambda row: (
            -row["retrieval_score"],
            row["corpus_class"],
            row["source_path"],
            row["chunk_id"],
        )
    )

    return scored[:top_k]


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "query"
    )

    parser.add_argument(
        "--corpus",
        choices=[
            "gold",
            "failure",
            "all",
        ],
        default="all",
    )

    parser.add_argument(
        "--top-k",
        type=int,
        default=8,
    )

    args = parser.parse_args()

    rows = load(args.corpus)

    result = {
        "schema_version":
            "career-ops-li-retrieval-v1",

        "backend":
            "DETERMINISTIC_BM25",

        "query":
            args.query,

        "corpus":
            args.corpus,

        "results":
            bm25(
                rows,
                args.query,
                args.top_k,
            ),
    }

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
