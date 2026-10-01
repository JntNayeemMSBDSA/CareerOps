from careerops_evidence_boundaries import entity_boundary_errors
from careerops_config import source_dir
#!/usr/bin/env python3

import json
import os
import math
import re
from pathlib import Path

from careerops_runtime import runtime_dir

ROOT = Path(__file__).resolve().parents[1]
SOURCE = source_dir(ROOT)
RUNTIME = runtime_dir(ROOT)

CONTENT = Path(
    os.environ.get(
        "CAREEROPS_RESUME_INPUT",
        str(RUNTIME / "generated_resume_content.json"),
    )
).expanduser().resolve()
PACKET = RUNTIME / "compact_generation_packet.json"
EXPERIENCE_SELECTION = (
    RUNTIME / "experience_selection.json"
)
INVENTORY = SOURCE / "verified_evidence_inventory.md"
FACTS = SOURCE / "candidate_facts.json"
OVERRIDES = SOURCE / "candidate_attestations.json"
ASSUMED_MARKET = SOURCE / "assumed_market_coverage.json"

OUT_MAP = RUNTIME / "local_claim_map.json"
OUT_GATE = RUNTIME / "local_truth_gate.json"

REFERENCE_GATE = RUNTIME / "truth_gate.json"


TECH_TERMS = [
    "SQL Server 2022",
    "SQL Server",
    "BULK INSERT",
    "Power Query",
    "Power BI",
    "Tableau Hyper",
    "Tableau",
    "Snowflake",
    "DuckDB",
    "PyArrow",
    "Parquet",
    "Zstandard",
    "pandas",
    "Python",
    "T-SQL",
    "SQL",
    "DAX",
    "Jupyter",
    "TF-IDF",
    "Logistic Regression",
    "BERT",
    "Docker",
    "BigQuery",
    "Looker",
    "dbt",
    "AWS",
    "GitHub",
    "Git",
    "Jira",
    "Confluence",
]

METHOD_TERMS = [
    "MRR",
    "ARR",
    "CAC",
    "LTV",
    "break-even",
    "join-explosion",
    "row hashing",
    "window functions",
    "reporting views",
    "relational constraints",
    "structural-missingness",
    "fail-closed",
    "chronological",
    "train-validation-test",
    "class-weighted",
]

FORBIDDEN_VISIBLE = [
    "group project",
    "team-authored",
    "team project",
    "independent reconstruction",
    "public reconstruction",
    "portfolio reconstruction",
    "public portfolio implementation",
    "later reconstruction",
    "reconstruction evidence",
    "rebuilt study",
]

# Historical placement specifically prohibited unless a future
# direct-user correction explicitly authorizes it.
RN_HISTORICAL_TECH_FORBIDDEN = []


def read_json(path):
    if not path.exists():
        raise SystemExit(f"Missing required file: {path}")
    return json.loads(path.read_text())


def parse_blocks(text):
    pattern = re.compile(
        r"^##\s+((?:EXP|PRJ)-\d{3})\s+-\s+(.+?)\s*$",
        re.M,
    )

    matches = list(pattern.finditer(text))
    blocks = {}

    for i, m in enumerate(matches):
        end = (
            matches[i + 1].start()
            if i + 1 < len(matches)
            else len(text)
        )

        blocks[m.group(1)] = text[m.start():end]

    return blocks


def normalize_text(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def numeric_atoms(text):
    """
    Extract normalized numeric claims.

    Handles:
      240,000
      12.5 million
      4.5 million
      73.2%
      pct approx: 73.2
      0.61
      $7,500
      36-month

    Important:
    Magnitude suffixes such as M/B/K are accepted only as complete
    tokens. This prevents:
      "42 machines" -> 42 million
      "18 BI tables" -> 18 billion
      "SHA-256 manifests" -> 256 million

    Evidence lines using labels such as "pct", "percent", or
    "percentage" are treated as percentage-valued even when the value
    itself does not contain a literal % sign.
    """

    pattern = re.compile(
        r"""
        (?<![A-Za-z0-9_])
        \$?
        (?P<num>
            \d{1,3}(?:,\d{3})+(?:\.\d+)?
            |
            \d+(?:\.\d+)?
        )
        (?:
            \s*
            (?P<suffix>
                billion
                | million
                | thousand
                | bn
                | mm
                | k
                | m
                | b
            )
            \b
        )?
        \s*
        (?P<pct>%?)
        """,
        re.I | re.X,
    )

    atoms = []

    for m in pattern.finditer(text):
        raw = m.group(0).strip()

        num = float(
            m.group("num").replace(",", "")
        )

        suffix = (
            m.group("suffix") or ""
        ).lower()

        multiplier = 1.0

        if suffix in {
            "billion",
            "bn",
            "b",
        }:
            multiplier = 1_000_000_000.0

        elif suffix in {
            "million",
            "mm",
            "m",
        }:
            multiplier = 1_000_000.0

        elif suffix in {
            "thousand",
            "k",
        }:
            multiplier = 1_000.0

        value = num * multiplier

        # Percentage context must belong to THIS numeric field.
        #
        # Do not inspect the entire line/block because compact JSON or
        # flattened evidence may contain an unrelated "pct" field much
        # later in the same line. That previously caused values such as
        # $12K, $7K, 0.61, and 6 to be misclassified as percentages.
        line_start = text.rfind(
            "\n",
            0,
            m.start(),
        ) + 1

        context_start = max(
            line_start,
            m.start() - 120,
        )

        preceding_context = text[
            context_start:m.start()
        ].lower()

        percentage_context = bool(
            re.search(
                r"\b(?:pct|percent|percentage)\b",
                preceding_context,
            )
        )

        pct = (
            bool(m.group("pct"))
            or percentage_context
        )

        atoms.append({
            "raw": raw,
            "value": value,
            "percent": pct,
        })

    return atoms


def numbers_supported(claim, support_text):
    claim_atoms = numeric_atoms(claim)
    support_atoms = numeric_atoms(support_text)

    failures = []
    supported = []

    for c in claim_atoms:
        matches = []

        for s in support_atoms:
            if c["percent"] != s["percent"]:
                continue

            cv = c["value"]
            sv = s["value"]

            # Exact for small numbers; allow tiny rounding tolerance
            # for abbreviated large values such as 12.5 million.
            if cv == sv:
                matches.append(s)
                continue

            denom = max(abs(cv), abs(sv), 1.0)
            relative_error = abs(cv - sv) / denom

            if relative_error <= 0.005:
                matches.append(s)

        if matches:
            supported.append(c["raw"])
        else:
            failures.append(c["raw"])

    return supported, failures


def contains_term(text, term):
    term = str(term).strip()

    if not term:
        return False

    pattern = re.compile(
        r"(?<![A-Za-z0-9_])"
        + re.escape(term)
        + r"(?![A-Za-z0-9_])",
        re.I,
    )

    return bool(
        pattern.search(str(text))
    )


def find_terms(text, terms):
    found = []

    for term in terms:
        if contains_term(text, term):
            found.append(term)

    return found


def terms_supported(claim, support_text):
    terms = find_terms(
        claim,
        TECH_TERMS + METHOD_TERMS,
    )

    supported = []
    failures = []

    aliases = {
        "sql": ["sql", "t-sql", "duckdb sql"],
        "logistic regression": ["logistic regression"],
        "class-weighted": [
            "class-weighted",
            "weighted bert",
            "class-weighted cross-entropy",
        ],
        "train-validation-test": [
            "train/validation/test",
            "train-validation-test",
            "chronological train",
        ],
        "relational constraints": [
            "constraint",
            "constraints",
            "foreign-key/constraint",
        ],
        "reporting views": [
            "reporting views",
            "views",
        ],
    }

    for term in terms:
        candidates = aliases.get(
            term.lower(),
            [term.lower()],
        )

        if any(
            contains_term(
                support_text,
                candidate,
            )
            for candidate in candidates
        ):
            supported.append(term)
        else:
            failures.append(term)

    return supported, failures


def forbidden_visible_violations(text):
    lower = text.lower()

    return [
        phrase
        for phrase in FORBIDDEN_VISIBLE
        if phrase in lower
    ]


def historical_override_text(overrides):
    return json.dumps(
        overrides.get(
            "historical_work_attestation",
            {},
        ),
        ensure_ascii=False,
    )


def employment_override_text(overrides):
    return json.dumps(
        overrides.get(
            "employment_provenance_attestation",
            {},
        ),
        ensure_ascii=False,
    )


def assumed_capability_support_text(
    assumed_market,
    overrides,
):
    capability_override = overrides.get(
        "capability_status_override",
        {},
    )

    if not capability_override.get(
        "all_assumed_market_coverage_capabilities_are_actual_user_skills",
        False,
    ):
        return ""

    authorized_registries = {
        "explicit_skill_registry",
        "skill_family_registry",
        "deep_capability_registry",
    }

    applies_to = set(
        capability_override.get(
            "applies_to",
            [],
        )
        or []
    )

    allowed = (
        authorized_registries
        & applies_to
    )

    payload = {
        key:
            assumed_market.get(
                key,
                [],
            )
        for key in sorted(
            allowed
        )
    }

    return json.dumps(
        payload,
        ensure_ascii=False,
    )


def summary_support_text(
    facts,
    overrides,
    selected_blocks,
    assumed_market=None,
):
    return "\n".join([
        json.dumps(
            facts,
            ensure_ascii=False,
        ),
        json.dumps(
            overrides.get(
                "capability_status_override",
                {},
            ),
            ensure_ascii=False,
        ),
        assumed_capability_support_text(
            assumed_market or {},
            overrides,
        ),
        *selected_blocks,
    ])


def claim_result(
    claim_id,
    location,
    text,
    source_entities,
    support_text,
    override_backed=False,
    extra_checks=None,
):
    supported_numbers, bad_numbers = (
        numbers_supported(
            text,
            support_text,
        )
    )

    supported_terms, bad_terms = (
        terms_supported(
            text,
            support_text,
        )
    )

    forbidden = (
        forbidden_visible_violations(text)
    )

    violations = []

    violations.extend(
        f"unsupported_number:{x}"
        for x in bad_numbers
    )

    violations.extend(
        f"unsupported_term:{x}"
        for x in bad_terms
    )

    violations.extend(
        f"forbidden_visible_language:{x}"
        for x in forbidden
    )

    if extra_checks:
        violations.extend(
            extra_checks(text)
        )

    if violations:
        status = "UNSUPPORTED"
    elif override_backed:
        status = (
            "SUPPORTED_BY_DIRECT_USER_OVERRIDE"
        )
    else:
        status = "SUPPORTED"

    return {
        "claim_id": claim_id,
        "location": location,
        "text": text,
        "status": status,
        "source_entities": source_entities,
        "support_type": (
            [
                "VERIFIED_EVIDENCE",
                "DIRECT_USER_CORRECTION",
            ]
            if override_backed
            else ["VERIFIED_EVIDENCE"]
        ),
        "supported_components": (
            [f"number:{x}" for x in supported_numbers]
            + [f"term:{x}" for x in supported_terms]
        ),
        "unsupported_components": violations,
        "notes": (
            "Local deterministic atomic validation."
        ),
    }








def main():
    content = read_json(CONTENT)
    packet = read_json(PACKET)
    experience_selection = read_json(
        EXPERIENCE_SELECTION
    )
    facts = read_json(FACTS)
    overrides = read_json(OVERRIDES)
    assumed_market = read_json(
        ASSUMED_MARKET
    )

    inventory_text = INVENTORY.read_text(
        encoding="utf-8",
        errors="replace",
    )

    blocks = parse_blocks(
        inventory_text
    )

    selected_ids = packet.get(
        "selected_evidence_ids",
        [],
    )

    selected_block_text = [
        blocks[x]
        for x in selected_ids
        if x in blocks
    ]

    claims = []

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    claims.append(
        claim_result(
            "SUMMARY-001",
            "summary",
            content.get("summary", ""),
            selected_ids,
            summary_support_text(
                facts,
                overrides,
                selected_block_text,
                assumed_market,
            ),
            override_backed=True,
        )
    )

    # --------------------------------------------------------
    # EXPERIENCE
    # --------------------------------------------------------

    exp_sources = {
        block["block_id"]: list(
            block.get(
                "evidence_ids",
                [],
            )
        )
        for block in experience_selection.get(
            "selected_experience_blocks",
            [],
        )
        if block.get("block_id")
    }

    exp_counter = 0

    for exp in content.get(
        "experience",
        [],
    ):
        block_id = exp.get("block_id")
        source_entities = exp_sources.get(
            block_id,
            [],
        )

        support_parts = [
            blocks[x]
            for x in source_entities
            if x in blocks
        ]

        override_backed = any(
            entity_id in {
                *overrides.get("employment_provenance_attestation", {}).get("entities", {}),
            }
            for entity_id in source_entities
        )

        if override_backed:
            support_parts.append(
                employment_override_text(
                    overrides
                )
            )

        support_text = "\n".join(
            support_parts
        )

        for bullet in exp.get(
            "bullets",
            [],
        ):
            exp_counter += 1

            extra = None

            if any(
                entity_id in {
                    *overrides.get("historical_work_attestation", {}).get("roles", {}),
                }
                for entity_id in source_entities
            ):
                support_parts.append(
                    historical_override_text(
                        overrides
                    )
                )
                support_text = "\n".join(
                    support_parts
                )
                override_backed = True
                extra = lambda value: [error for owner in source_entities for error in entity_boundary_errors(value, owner, facts)]

            claims.append(
                claim_result(
                    f"EXPERIENCE-{exp_counter:03d}",
                    (
                        f"experience."
                        f"{block_id}"
                    ),
                    bullet,
                    source_entities,
                    support_text,
                    override_backed=(
                        override_backed
                    ),
                    extra_checks=extra,
                )
            )

    # --------------------------------------------------------
    # PROJECTS
    # --------------------------------------------------------

    project_counter = 0

    for project in content.get(
        "projects",
        [],
    ):
        entity_id = project.get(
            "entity_id"
        )

        support_text = blocks.get(
            entity_id,
            "",
        )

        for bullet in project.get(
            "bullets",
            [],
        ):
            project_counter += 1

            extra = None

            extra = lambda value: entity_boundary_errors(value, entity_id, facts)

            claims.append(
                claim_result(
                    f"PROJECT-{project_counter:03d}",
                    (
                        f"project."
                        f"{entity_id}"
                    ),
                    bullet,
                    [entity_id],
                    support_text,
                    extra_checks=extra,
                )
            )

    # --------------------------------------------------------
    # STRUCTURE
    # --------------------------------------------------------

    from careerops_content_contract import contract, structure, expected_claim_count
    current_contract = contract(RUNTIME)
    structure_errors = structure(content, current_contract)
    expected_count = expected_claim_count(current_contract)
    from careerops_temporal_truth import completed_deliverable_errors
    for exp in content.get('experience',[]):
        source_ids = exp_sources.get(exp.get('block_id'),[])
        structure_errors.extend(completed_deliverable_errors(' '.join(exp.get('bullets',[])),source_ids,facts))

    if len(claims) != expected_count:
        structure_errors.append(f"claim_count:{len(claims)} expected:{expected_count}")

    # --------------------------------------------------------
    # FINAL LOCAL GATE
    # --------------------------------------------------------

    supported = sum(
        x["status"] == "SUPPORTED"
        for x in claims
    )

    overridden = sum(
        x["status"]
        == "SUPPORTED_BY_DIRECT_USER_OVERRIDE"
        for x in claims
    )

    unsupported = sum(
        x["status"] == "UNSUPPORTED"
        for x in claims
    )

    failed_ids = [
        x["claim_id"]
        for x in claims
        if x["status"] == "UNSUPPORTED"
    ]

    gate_status = (
        "PASS"
        if (
            not structure_errors
            and unsupported == 0
            and len(claims) == expected_count
        )
        else "FAIL"
    )

    claim_map = {
        "schema_version":
            "local-claim-map-v1",
        "validation_mode":
            "DETERMINISTIC_LOCAL_ATOMIC",
        "claims": claims,
    }

    gate = {
        "schema_version":
            "local-truth-gate-v1",

        "validation_mode":
            "DETERMINISTIC_LOCAL_ATOMIC",

        "gate": gate_status,
        "total_claims": len(claims),
        "supported": supported,
        "supported_by_direct_user_override":
            overridden,
        "partial": 0,
        "unsupported": unsupported,
        "structure_errors":
            structure_errors,
        "failed_claim_ids": failed_ids,
        "model_calls": 0,
        "estimated_model_tokens": 0,

        "policy": {
            "on_pass":
                "accept local truth gate",

            "on_fail":
                "do not release; inspect exact "
                "failed claims and escalate to "
                "GPT-6.1 Sol High only if ambiguity "
                "cannot be resolved deterministically",
        },
    }

    OUT_MAP.write_text(
        json.dumps(
            claim_map,
            indent=2,
            ensure_ascii=False,
        ) + "\n"
    )

    OUT_GATE.write_text(
        json.dumps(
            gate,
            indent=2,
            ensure_ascii=False,
        ) + "\n"
    )

    # --------------------------------------------------------
    # PRINT
    # --------------------------------------------------------

    print("=" * 88)
    print(
        "LOCAL DETERMINISTIC TRUTH GATE"
    )
    print("=" * 88)

    print("GATE:", gate_status)
    print(
        "TOTAL CLAIMS:",
        len(claims),
    )
    print(
        "SUPPORTED:",
        supported,
    )
    print(
        "SUPPORTED BY DIRECT USER OVERRIDE:",
        overridden,
    )
    print(
        "UNSUPPORTED:",
        unsupported,
    )
    print(
        "STRUCTURE ERRORS:",
        (
            structure_errors
            if structure_errors
            else "NONE"
        ),
    )
    print(
        "FAILED CLAIMS:",
        failed_ids if failed_ids else "NONE",
    )

    print()
    print("CLAIM AUDIT:")

    for claim in claims:
        print(
            f"- {claim['claim_id']}: "
            f"{claim['status']}"
        )

        if claim[
            "unsupported_components"
        ]:
            for problem in claim[
                "unsupported_components"
            ]:
                print(
                    f"    ! {problem}"
                )

    print()
    print("MODEL CALLS: 0")
    print("MODEL TOKENS: 0")

    # Compare to our expensive Sol baseline,
    # but NEVER use it as validation input.
    if REFERENCE_GATE.exists():
        reference = read_json(
            REFERENCE_GATE
        )

        print()
        print("=" * 88)
        print(
            "COMPARISON WITH LOCKED "
            "GPT-5.6 SOL BASELINE"
        )
        print("=" * 88)

        print(
            "SOL GATE:",
            reference.get("gate"),
        )
        print(
            "LOCAL GATE:",
            gate_status,
        )

        print(
            "SOL COUNTS:",
            reference.get("supported"),
            "supported /",
            reference.get(
                "supported_by_direct_user_override"
            ),
            "override /",
            reference.get("unsupported"),
            "unsupported",
        )

        print(
            "LOCAL COUNTS:",
            supported,
            "supported /",
            overridden,
            "override /",
            unsupported,
            "unsupported",
        )

        parity = (
            reference.get("gate")
            == gate_status
            and reference.get(
                "supported"
            ) == supported
            and reference.get(
                "supported_by_direct_user_override"
            ) == overridden
            and reference.get(
                "unsupported"
            ) == unsupported
        )

        print(
            "BASELINE PARITY:",
            "PASS" if parity else "REVIEW",
        )

    print()
    print(
        "OUTPUT:",
        OUT_MAP.relative_to(ROOT),
    )
    print(
        "OUTPUT:",
        OUT_GATE.relative_to(ROOT),
    )


if __name__ == "__main__":
    main()
