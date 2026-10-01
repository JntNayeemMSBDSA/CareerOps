from careerops_config import source_dir
#!/usr/bin/env python3

import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from careerops_runtime import runtime_dir
from careerops_content_contract import contract, expected_claim_count


ROOT = Path(__file__).resolve().parents[1]
SOURCE = source_dir(ROOT)
RUNTIME = runtime_dir(ROOT)

LOCAL_MAP = RUNTIME / "local_claim_map.json"
LOCAL_GATE = RUNTIME / "local_truth_gate.json"

INVENTORY = SOURCE / "verified_evidence_inventory.md"
FACTS = SOURCE / "candidate_facts.json"
OVERRIDES = SOURCE / "candidate_attestations.json"

CLAIM_MAP = RUNTIME / "claim_map.json"
GATE = RUNTIME / "truth_gate.json"

PROMPT = RUNTIME / "truth_gate_prompt.md"

AUDIT_STATE = (
    RUNTIME
    / "truth_gate_audit_state.json"
)

SEMANTIC_AUDIT = (
    RUNTIME
    / "semantic_truth_audit.json"
)


def now_utc():
    return (
        datetime.now(
            timezone.utc
        )
        .isoformat()
    )


def read_json(path):
    if not path.exists():
        raise SystemExit(
            "Missing required file: "
            + str(path)
        )

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def write_json(path, data):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tmp = path.with_suffix(
        path.suffix + ".tmp"
    )

    tmp.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    tmp.replace(path)


def parse_blocks(text):
    pattern = re.compile(
        r"^##\s+"
        r"((?:EXP|PRJ)-\d{3})"
        r"\s+-\s+(.+?)\s*$",
        re.M,
    )

    matches = list(
        pattern.finditer(text)
    )

    blocks = {}

    for index, match in enumerate(
        matches
    ):
        end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(text)
        )

        blocks[
            match.group(1)
        ] = (
            text[
                match.start():end
            ]
            .strip()
        )

    return blocks


def canonicalize_claims(
    local_claims,
):
    """
    Preserve the historical canonical claim-ID convention while
    accepting the deterministic local gate as the source validator.
    """

    exp_counts = {}
    project_counts = {}

    output = []

    for raw in local_claims:
        claim = dict(raw)

        location = str(
            claim.get(
                "location",
                "",
            )
        )

        if location == "summary":
            canonical_id = (
                "SUMMARY-001"
            )

        elif location.startswith(
            "experience."
        ):
            block_id = (
                location.split(
                    ".",
                    1,
                )[1]
            )

            exp_counts[block_id] = (
                exp_counts.get(
                    block_id,
                    0,
                )
                + 1
            )

            canonical_id = (
                f"{block_id}"
                f"-BULLET-"
                f"{exp_counts[block_id]:03d}"
            )

        elif location.startswith(
            "project."
        ):
            entity_id = (
                location.split(
                    ".",
                    1,
                )[1]
            )

            project_counts[
                entity_id
            ] = (
                project_counts.get(
                    entity_id,
                    0,
                )
                + 1
            )

            canonical_id = (
                f"{entity_id}"
                f"-BULLET-"
                f"{project_counts[entity_id]:03d}"
            )

        else:
            canonical_id = str(
                claim.get(
                    "claim_id"
                )
                or "UNKNOWN-CLAIM"
            )

        claim[
            "claim_id"
        ] = canonical_id

        output.append(
            claim
        )

    return output


def conflicts_from_claims(
    claims,
):
    metric = []
    provenance = []
    historical = []
    model = []

    for claim in claims:
        claim_id = claim.get(
            "claim_id"
        )

        for problem in claim.get(
            "unsupported_components",
            [],
        ):
            item = (
                str(claim_id)
                + ":"
                + str(problem)
            )

            if str(problem).startswith(
                "unsupported_number:"
            ):
                metric.append(
                    item
                )

            elif str(problem).startswith(
                "historical_placement"
            ):
                historical.append(
                    item
                )

            elif str(problem).startswith(
                "model_attribution:"
            ):
                model.append(
                    item
                )

            elif (
                str(problem).startswith(
                    "project_employment_boundary:"
                )
                or str(problem).startswith(
                    "forbidden_visible_language:"
                )
            ):
                provenance.append(
                    item
                )

    return {
        "metric_conflicts":
            metric,

        "provenance_conflicts":
            provenance,

        "historical_placement_conflicts":
            historical,

        "model_attribution_conflicts":
            model,
    }


def write_final_outputs(
    claims,
    *,
    validation_mode,
    model_calls,
    notes,
    semantic_audit_claim_count=0,
):
    supported = sum(
        claim.get("status")
        == "SUPPORTED"
        for claim in claims
    )

    overridden = sum(
        claim.get("status")
        == "SUPPORTED_BY_DIRECT_USER_OVERRIDE"
        for claim in claims
    )

    partial = sum(
        claim.get("status")
        == "PARTIAL"
        for claim in claims
    )

    unsupported = sum(
        claim.get("status")
        == "UNSUPPORTED"
        for claim in claims
    )

    failed_ids = [
        claim.get("claim_id")
        for claim in claims
        if claim.get("status")
        in {
            "PARTIAL",
            "UNSUPPORTED",
        }
    ]

    gate_status = (
        "PASS"
        if (
            len(claims) == expected_claim_count(contract(RUNTIME))
            and partial == 0
            and unsupported == 0
        )
        else "FAIL"
    )

    conflicts = (
        conflicts_from_claims(
            claims
        )
    )

    claim_map = {
        "schema_version":
            "claim-map-v1",

        "validation_mode":
            validation_mode,

        "claims":
            claims,
    }

    gate = {
        "schema_version":
            "truth-gate-v1",

        "validation_mode":
            validation_mode,

        "gate":
            gate_status,

        "total_claims":
            len(claims),

        "supported":
            supported,

        "supported_by_direct_user_override":
            overridden,

        "partial":
            partial,

        "unsupported":
            unsupported,

        **conflicts,

        "failed_claim_ids":
            failed_ids,

        "model_calls":
            int(model_calls),

        "semantic_audit_claim_count":
            int(
                semantic_audit_claim_count
            ),

        "notes":
            list(notes),
    }

    write_json(
        CLAIM_MAP,
        claim_map,
    )

    write_json(
        GATE,
        gate,
    )

    return gate


def classify_failures(
    claims,
    local_gate,
):
    """
    Hard deterministic defects never go to a model.

    Only unsupported_term:* can enter the semantic ambiguity
    path. Even then, the semantic auditor may only decide whether
    the specific term has an equivalent expression in the already
    authorized evidence.
    """

    hard = []
    ambiguous = []

    structure_errors = list(
        local_gate.get(
            "structure_errors",
            [],
        )
    )

    hard.extend(
        "structure:"
        + str(item)
        for item in structure_errors
    )

    for claim in claims:
        if claim.get(
            "status"
        ) != "UNSUPPORTED":
            continue

        problems = list(
            claim.get(
                "unsupported_components",
                [],
            )
        )

        if not problems:
            hard.append(
                str(
                    claim.get(
                        "claim_id"
                    )
                )
                + ":unclassified_failure"
            )

            continue

        for problem in problems:
            value = str(problem)

            if value.startswith(
                "unsupported_term:"
            ):
                ambiguous.append({
                    "claim_id":
                        claim.get(
                            "claim_id"
                        ),

                    "location":
                        claim.get(
                            "location"
                        ),

                    "text":
                        claim.get(
                            "text"
                        ),

                    "source_entities":
                        list(
                            claim.get(
                                "source_entities",
                                [],
                            )
                        ),

                    "problem":
                        value,
                })

            else:
                hard.append(
                    str(
                        claim.get(
                            "claim_id"
                        )
                    )
                    + ":"
                    + value
                )

    return hard, ambiguous


def relevant_evidence(
    ambiguous,
    blocks,
):
    entity_ids = []

    for item in ambiguous:
        for source in item.get(
            "source_entities",
            [],
        ):
            value = str(source)

            if re.fullmatch(
                r"(?:EXP|PRJ)-\d{3}",
                value,
            ):
                entity_ids.append(
                    value
                )

    entity_ids = list(
        dict.fromkeys(
            entity_ids
        )
    )

    missing = [
        entity_id
        for entity_id in entity_ids
        if entity_id not in blocks
    ]

    if missing:
        raise SystemExit(
            "Semantic audit cannot resolve "
            "missing evidence entities: "
            + ", ".join(
                missing
            )
        )

    return {
        entity_id:
            blocks[entity_id]
        for entity_id in entity_ids
    }


def build_compact_prompt(
    ambiguous,
    evidence,
    facts,
    overrides,
):
    return f"""
# CAREEROPS COMPACT SEMANTIC TRUTH AUDIT

You are resolving ONLY deterministic term ambiguities found by
Career-Ops.

Do not rewrite the resume.

Do not broaden the evidence.

Do not use outside knowledge.

Do not approve a technology, method, employer placement,
ownership claim, metric, or outcome merely because it sounds
plausible.

You may resolve ONLY the listed unsupported_term:* findings.

A term may be marked SUPPORTED only when the authorized evidence
contains the same capability or a clearly equivalent naming
variant.

Return exactly one JSON file named:

semantic_truth_audit.json

Use:

{{
  "schema_version": "semantic-truth-audit-v1",
  "claims": [
    {{
      "claim_id": "...",
      "status": "SUPPORTED",
      "supported_components": ["..."],
      "unsupported_components": [],
      "notes": "..."
    }}
  ]
}}

Allowed status values:

SUPPORTED
SUPPORTED_BY_DIRECT_USER_OVERRIDE
UNSUPPORTED

Every listed claim_id must appear exactly once.

============================================================
AMBIGUOUS CLAIMS
============================================================

{json.dumps(
    ambiguous,
    indent=2,
    ensure_ascii=False,
)}

============================================================
RELEVANT AUTHORIZED EVIDENCE ONLY
============================================================

{json.dumps(
    evidence,
    indent=2,
    ensure_ascii=False,
)}

============================================================
DIRECT USER FACTS
============================================================

{json.dumps(
    facts,
    indent=2,
    ensure_ascii=False,
)}

============================================================
DIRECT USER OVERRIDES
============================================================

{json.dumps(
    overrides,
    indent=2,
    ensure_ascii=False,
)}

============================================================
NON-NEGOTIABLE RULE
============================================================

If equivalence is uncertain, return UNSUPPORTED.
""".strip() + "\n"


def run_semantic_audit(
    prompt,
    expected_claim_ids,
):
    write_json(
        AUDIT_STATE,
        {
            "schema_version":
                "truth-audit-state-v1",

            "attempted_calls":
                1,

            "model":
                "gpt-6.1-sol",

            "reasoning_effort":
                "high",

            "status":
                "RUNNING",

            "started_at_utc":
                now_utc(),
        },
    )

    env = os.environ.copy()

    for key in [
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "CODEX_API_KEY",
        "CODEX_ACCESS_TOKEN",
    ]:
        env.pop(
            key,
            None,
        )

    with tempfile.TemporaryDirectory(
        prefix="careerops-semantic-truth-"
    ) as temp_name:
        workdir = Path(
            temp_name
        )

        (
            workdir
            / "truth_gate_prompt.md"
        ).write_text(
            prompt,
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                "codex",
                "exec",
                "--skip-git-repo-check",
                "-m",
                "gpt-6.1-sol",
                "-c",
                'model_reasoning_effort="high"',
                "--sandbox",
                "workspace-write",
                (
                    "Do not load skills, repository instructions, "
                    "AGENTS.md, or external context. "
                    "Read truth_gate_prompt.md completely. "
                    "Create exactly semantic_truth_audit.json "
                    "in the current directory and no other file."
                ),
            ],
            cwd=workdir,
            env=env,
        )

        if result.returncode != 0:
            state = read_json(
                AUDIT_STATE
            )

            state[
                "status"
            ] = "ERROR"

            state[
                "returncode"
            ] = result.returncode

            state[
                "finished_at_utc"
            ] = now_utc()

            write_json(
                AUDIT_STATE,
                state,
            )

            raise SystemExit(
                "Compact semantic truth audit "
                "failed with RC "
                + str(
                    result.returncode
                )
            )

        result_file = (
            workdir
            / "semantic_truth_audit.json"
        )

        if not result_file.exists():
            raise SystemExit(
                "Compact semantic audit did not "
                "create semantic_truth_audit.json."
            )

        audit = json.loads(
            result_file.read_text(
                encoding="utf-8"
            )
        )

    claims = audit.get(
        "claims",
        [],
    )

    returned_ids = [
        item.get(
            "claim_id"
        )
        for item in claims
    ]

    if sorted(
        returned_ids
    ) != sorted(
        expected_claim_ids
    ):
        raise SystemExit(
            "Semantic audit claim-ID mismatch."
        )

    allowed = {
        "SUPPORTED",
        "SUPPORTED_BY_DIRECT_USER_OVERRIDE",
        "UNSUPPORTED",
    }

    if any(
        item.get(
            "status"
        )
        not in allowed
        for item in claims
    ):
        raise SystemExit(
            "Semantic audit returned "
            "an invalid status."
        )

    write_json(
        SEMANTIC_AUDIT,
        audit,
    )

    state = read_json(
        AUDIT_STATE
    )

    state[
        "status"
    ] = "COMPLETE"

    state[
        "finished_at_utc"
    ] = now_utc()

    write_json(
        AUDIT_STATE,
        state,
    )

    return audit


def merge_semantic_results(
    claims,
    audit,
):
    results = {
        item[
            "claim_id"
        ]:
            item
        for item in audit.get(
            "claims",
            [],
        )
    }

    merged = []

    for raw in claims:
        claim = dict(raw)

        claim_id = claim.get(
            "claim_id"
        )

        result = results.get(
            claim_id
        )

        if result is None:
            merged.append(
                claim
            )

            continue

        status = result.get(
            "status"
        )

        if status in {
            "SUPPORTED",
            "SUPPORTED_BY_DIRECT_USER_OVERRIDE",
        }:
            claim[
                "status"
            ] = status

            claim[
                "unsupported_components"
            ] = [
                item
                for item in claim.get(
                    "unsupported_components",
                    [],
                )
                if not str(
                    item
                ).startswith(
                    "unsupported_term:"
                )
            ]

            claim[
                "supported_components"
            ] = list(
                claim.get(
                    "supported_components",
                    [],
                )
            ) + [
                "semantic_equivalence:"
                + str(item)
                for item in result.get(
                    "supported_components",
                    [],
                )
            ]

        claim[
            "notes"
        ] = (
            str(
                claim.get(
                    "notes",
                    "",
                )
            ).strip()
            + " "
            + str(
                result.get(
                    "notes",
                    "",
                )
            ).strip()
        ).strip()

        merged.append(
            claim
        )

    return merged


def main():
    local_map = read_json(
        LOCAL_MAP
    )

    local_gate = read_json(
        LOCAL_GATE
    )

    local_claims = (
        local_map.get(
            "claims",
            [],
        )
    )

    claims = canonicalize_claims(
        local_claims
    )

    if len(claims) != expected_claim_count(contract(RUNTIME)) or local_gate.get("structure_errors"):
        gate = write_final_outputs(
            claims,
            validation_mode=(
                "DETERMINISTIC_FIRST_V2"
            ),
            model_calls=0,
            notes=[
                "Deterministic local truth "
                "returned invalid source-bound structure or temporal truth."
            ],
        )

        print(
            "TRUTH GATE V2:",
            gate["gate"],
        )

        return 1

    local_status = (
        local_gate.get(
            "gate"
        )
    )

    if local_status == "PASS":
        for stale in [
            PROMPT,
            AUDIT_STATE,
            SEMANTIC_AUDIT,
        ]:
            if stale.exists():
                stale.unlink()

        gate = write_final_outputs(
            claims,
            validation_mode=(
                "DETERMINISTIC_FIRST_V2"
            ),
            model_calls=0,
            notes=[
                (
                    "All claims passed the "
                    "deterministic local atomic "
                    "truth validator."
                ),
                (
                    "No semantic model audit "
                    "was required."
                ),
            ],
        )

        print(
            "=" * 88
        )
        print(
            "TRUTH GATE V2"
        )
        print(
            "=" * 88
        )

        print(
            "GATE:",
            gate["gate"],
        )

        print(
            "VALIDATION:",
            "DETERMINISTIC_FIRST_V2",
        )

        print(
            "MODEL AUDIT CALLS: 0"
        )

        print(
            "NORMAL PATH: ONE TOTAL MODEL CALL "
            "INCLUDING WRITER"
        )

        return (
            0
            if gate["gate"]
            == "PASS"
            else 1
        )

    hard, ambiguous = (
        classify_failures(
            claims,
            local_gate,
        )
    )

    if hard:
        for stale in [
            PROMPT,
            AUDIT_STATE,
            SEMANTIC_AUDIT,
        ]:
            if stale.exists():
                stale.unlink()

        gate = write_final_outputs(
            claims,
            validation_mode=(
                "DETERMINISTIC_FIRST_V2_HARD_FAIL"
            ),
            model_calls=0,
            notes=[
                (
                    "Deterministic truth failure "
                    "is not model-repairable."
                ),
                *hard,
            ],
        )

        print(
            "=" * 88
        )
        print(
            "TRUTH GATE V2: HARD FAIL"
        )
        print(
            "=" * 88
        )

        for item in hard:
            print(
                "-",
                item,
            )

        print(
            "MODEL AUDIT CALLS: 0"
        )

        return 1

    if not ambiguous:
        gate = write_final_outputs(
            claims,
            validation_mode=(
                "DETERMINISTIC_FIRST_V2_FAIL_CLOSED"
            ),
            model_calls=0,
            notes=[
                (
                    "Local truth gate failed "
                    "without a permitted semantic "
                    "ambiguity class."
                )
            ],
        )

        print(
            "TRUTH GATE V2:",
            gate["gate"],
        )

        return 1

    inventory_text = (
        INVENTORY.read_text(
            encoding="utf-8",
            errors="replace",
        )
    )

    blocks = parse_blocks(
        inventory_text
    )

    facts = read_json(
        FACTS
    )

    overrides = read_json(
        OVERRIDES
    )

    evidence = relevant_evidence(
        ambiguous,
        blocks,
    )

    prompt = build_compact_prompt(
        ambiguous,
        evidence,
        facts,
        overrides,
    )

    PROMPT.write_text(
        prompt,
        encoding="utf-8",
    )

    if os.environ.get(
        "CAREEROPS_TRUTH_AUDIT_DRY_RUN"
    ) == "1":
        write_json(
            AUDIT_STATE,
            {
                "schema_version":
                    "truth-audit-state-v1",

                "attempted_calls":
                    0,

                "status":
                    "DRY_RUN",

                "ambiguity_claim_count":
                    len(
                        ambiguous
                    ),

                "prompt_words":
                    len(
                        prompt.split()
                    ),

                "prompt_chars":
                    len(
                        prompt
                    ),
            },
        )

        print(
            "TRUTH GATE V2 SEMANTIC AUDIT:"
        )

        print(
            "DRY RUN ONLY"
        )

        print(
            "AMBIGUOUS CLAIMS:",
            len(
                ambiguous
            ),
        )

        print(
            "PROMPT WORDS:",
            len(
                prompt.split()
            ),
        )

        print(
            "MODEL CALLS: 0"
        )

        return 4

    local_review=read_json(RUNTIME/'semantic_challenger_report.json') if (RUNTIME/'semantic_challenger_report.json').is_file() else {}
    if os.environ.get('CAREEROPS_TRUTH_SEMANTIC_AUDIT_AUTHORIZED')!='1' or not local_review.get('model_accounting',{}).get('qwen_completed') or local_review.get('status') not in {'UNRESOLVED_FAIL_CLOSED','QWEN_INVOKED_UNRESOLVED'}:
        write_final_outputs(claims,validation_mode='DETERMINISTIC_FIRST_V2_FAIL_CLOSED',model_calls=0,notes=['Unresolved truth equivalence requires a source-bound local semantic review and explicit authorization before any exceptional cloud truth audit. No candidate fact may be created.'])
        return 1
    from careerops_model_policy import preflight
    preflight('high',RUNTIME)

    audit = run_semantic_audit(
        prompt,
        [
            item[
                "claim_id"
            ]
            for item in ambiguous
        ],
    )

    merged = (
        merge_semantic_results(
            claims,
            audit,
        )
    )

    gate = write_final_outputs(
        merged,
        validation_mode=(
            "DETERMINISTIC_FIRST_V2"
            "_SEMANTIC_EXCEPTION"
        ),
        model_calls=1,
        semantic_audit_claim_count=(
            len(
                ambiguous
            )
        ),
        notes=[
            (
                "Only unresolved deterministic "
                "term ambiguities were submitted "
                "to the semantic auditor."
            ),
            (
                "All non-ambiguous defects remain "
                "fail-closed and cannot be "
                "overridden by the model."
            ),
        ],
    )

    print(
        "=" * 88
    )
    print(
        "TRUTH GATE V2: SEMANTIC EXCEPTION"
    )
    print(
        "=" * 88
    )

    print(
        "GATE:",
        gate["gate"],
    )

    print(
        "SEMANTIC AUDIT CLAIMS:",
        len(
            ambiguous
        ),
    )

    print(
        "MODEL AUDIT CALLS: 1"
    )

    return (
        0
        if gate["gate"]
        == "PASS"
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
