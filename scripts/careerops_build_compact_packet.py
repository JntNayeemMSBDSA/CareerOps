from careerops_config import source_dir
#!/usr/bin/env python3

import json
import re
from pathlib import Path
from careerops_requirement_regeneration import canonical_ledger_path

from careerops_runtime import runtime_dir

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = runtime_dir(ROOT)
SOURCE = source_dir(ROOT)

OUT_JSON = RUNTIME / "compact_generation_packet.json"
OUT_MD = RUNTIME / "compact_generation_prompt.md"

INVENTORY = SOURCE / "verified_evidence_inventory.md"


def load_runtime(name):
    p = RUNTIME / name
    if not p.exists():
        raise SystemExit(f"Missing runtime file: {p}")
    return json.loads(p.read_text())


def load_source(name):
    p = SOURCE / name
    if not p.exists():
        raise SystemExit(f"Missing source file: {p}")
    return json.loads(p.read_text())


def parse_evidence_blocks(text):
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

        blocks[m.group(1)] = {
            "title": m.group(2).strip(),
            "text": text[m.start():end].strip(),
        }

    return blocks


KEEP_SECTIONS = {
    "problem / objective",
    "data and scale",
    "historical scale and outcomes",
    "historical facts",
    "tools and platforms",
    "technical methods",
    "methods",
    "historical methods",
    "statistical methods",
    "architecture",
    "data model",
    "results",
    "selected metrics",
    "selected modeled outputs",
    "split",
    "claim boundaries / integrity rules",
    "core outputs",
    "kpis / business logic",
    "business logic",
}


def compact_evidence_block(entity_id, block):
    """
    Preserve factual evidence while dropping verbose metadata that the
    generation model does not need every single run.
    """

    text = block["text"]
    lines = text.splitlines()

    result = [
        f"## {entity_id} - {block['title']}"
    ]

    active = True
    section_name = None

    for line in lines[1:]:
        stripped = line.strip()

        # Preserve important top-level factual metadata selectively.
        if stripped.startswith("**Organization/context:**"):
            result.append(stripped)
            continue

        if stripped.startswith("**Role:**"):
            result.append(stripped)
            continue

        if stripped.startswith("**Period:**"):
            result.append(stripped)
            continue

        if stripped.startswith("**Problem / objective:**"):
            result.append(stripped)
            continue

        # New subsection.
        if stripped.startswith("### "):
            section_name = stripped[4:].strip().lower()
            active = section_name in KEEP_SECTIONS

            if active:
                result.append("")
                result.append(stripped)

            continue

        if not active:
            continue

        # Remove empty noise, but retain paragraph separation.
        if not stripped:
            if result and result[-1] != "":
                result.append("")
            continue

        # Remove source-artifact filenames and role-family tags.
        if stripped.startswith("**Source artifacts"):
            active = False
            continue

        if stripped.startswith("### Role-family"):
            active = False
            continue

        result.append(line.rstrip())

    # Collapse repeated blanks.
    cleaned = []
    previous_blank = False

    for line in result:
        blank = not line.strip()

        if blank and previous_blank:
            continue

        cleaned.append(line)
        previous_blank = blank

    return "\n".join(cleaned).strip()


def compact_role_routing(routing):
    """
    Keep only final routing decisions, not all scoring internals.
    """

    result = {}

    for key in [
        "application_role",
        "application_role_score",
        "market_role",
        "market_role_score",
        "confidence",
        "margin",
        "routed_role",
        "primary_role",
        "top_roles",
        "top_candidates",
    ]:
        if key in routing:
            result[key] = routing[key]

    # If schema differs, retain a small set of scalar/top-level values.
    if not result:
        for key, value in routing.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                result[key] = value

    return result


def compact_constraints(data):
    """
    Keep outcome and actual hard constraints. Drop verbose audit plumbing.
    """

    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return data

    result = {}

    preferred = [
        "gate",
        "status",
        "all_passed",
        "hard_constraints",
        "constraints",
        "results",
        "failed",
        "failures",
        "unresolved",
        "unresolved_hard_constraints",
    ]

    for key in preferred:
        if key in data:
            result[key] = data[key]

    if not result:
        for key, value in data.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                result[key] = value

    return result


def compact_experience_selection(data):
    selected = data.get(
        "selected_experience_blocks",
        []
    )

    result = []

    for x in selected:
        result.append({
            key: x[key]
            for key in [
                "block_id",
                "company",
                "title",
                "dates",
                "evidence_ids",
                "supports_requirements",
                "requirement_ids",
            ]
            if key in x
        })

    return result


def compact_project_selection(data):
    selected = data.get("selected_projects", [])

    result = []

    for x in selected:
        result.append({
            key: x[key]
            for key in [
                "entity_id",
                "canonical_name",
                "visible_name",

                "brand_context",
                "must_preserve_entities",
                "relationship_boundary",
                "supports_requirements",
                "requirement_ids",
                "selection_reason",
            ]
            if key in x
        })

    return result


def compact_candidate_facts(facts):
    return {
        key: facts[key]
        for key in [
            "education",
            "skill_duration_years",
            "core_proficiency",
            "identity_authority",
            "deliverable_state_authority",
        ]
        if key in facts
    }


def compact_overrides(overrides, selected_ids):
    result = {}

    # Project ownership rules matter whenever projects are selected.
    if any(x.startswith("PRJ-") for x in selected_ids):
        if "project_ownership" in overrides:
            result["project_ownership"] = overrides[
                "project_ownership"
            ]

    # Confirmed skills are globally authoritative.
    if "capability_status_override" in overrides:
        cap = overrides["capability_status_override"]

        result["capability_status_override"] = {
            "authority": cap.get("authority"),
            "all_assumed_market_coverage_capabilities_are_actual_user_skills":
                cap.get(
                    "all_assumed_market_coverage_capabilities_are_actual_user_skills"
                ),
            "claim_class": cap.get("claim_class"),
            "policy": cap.get("policy"),
        }

    for key in ("historical_work_attestation", "employment_provenance_attestation"):
        value = overrides.get(key)
        if value and set(value.get("entities", {})) & set(selected_ids):
            result[key] = value

    return result


def main():
    jd = load_runtime("jd_intake.json")
    reqs = json.loads(canonical_ledger_path(RUNTIME).read_text())
    routing = load_runtime("role_routing.json")
    constraints = load_runtime("constraint_validation.json")
    experience = load_runtime("experience_selection.json")
    projects = load_runtime("project_selection.json")
    skills = load_runtime("technical_skills_plan.json")
    summary = load_runtime("summary_route.json")

    facts = load_source("candidate_facts.json")
    overrides = load_source("candidate_attestations.json")

    inventory_text = INVENTORY.read_text(
        encoding="utf-8",
        errors="replace",
    )

    evidence_blocks = parse_evidence_blocks(
        inventory_text
    )

    selected_ids = []

    for x in experience.get(
        "selected_experience_blocks",
        []
    ):
        selected_ids.extend(
            x.get("evidence_ids", [])
        )

    for x in projects.get(
        "selected_projects",
        []
    ):
        entity_id = x.get("entity_id")

        if entity_id:
            selected_ids.append(entity_id)

    selected_ids = list(
        dict.fromkeys(selected_ids)
    )

    compact_evidence = {}

    for entity_id in selected_ids:
        if entity_id not in evidence_blocks:
            raise SystemExit(
                f"Selected evidence block missing: {entity_id}"
            )

        compact_evidence[entity_id] = (
            compact_evidence_block(
                entity_id,
                evidence_blocks[entity_id],
            )
        )

    visible_skills = skills.get(
        "visible_skill_lines",
        skills,
    )

    selected_blocks = experience.get('selected_experience_blocks', [])
    if not selected_blocks or any(not x.get('block_id') for x in selected_blocks):
        raise SystemExit('Current selection cannot establish the configured experience bullet contract.')
    from careerops_adaptive_content_budget import allocate
    from careerops_skills_stack import compact_contract
    skills_contract = compact_contract(skills)
    content_budget=allocate(experience,projects,reqs,visible_skills)
    current_bullet_counts=content_budget['experience_bullet_counts']
    slot_counts=[current_bullet_counts[re.sub(r'[^A-Z0-9]','',x['block_id'].upper())] for x in selected_blocks]

    packet = {
        "schema_version":
            "careerops-compact-generation-packet-v1",

        "target_job": jd,

        "requirements": reqs,

        "role_routing":
            compact_role_routing(routing),

        "hard_constraints":
            compact_constraints(constraints),

        "selected_experience":
            compact_experience_selection(
                experience
            ),

        "selected_projects":
            compact_project_selection(
                projects
            ),

        "technical_skills":
            visible_skills,
        "skills_stack_contract": skills_contract,

        "summary_mode":
            summary.get("mode"),

        "candidate_facts":
            compact_candidate_facts(facts),

        "candidate_attestations":
            compact_overrides(
                overrides,
                selected_ids,
            ),

        "selected_evidence_ids":
            selected_ids,

        "evidence": compact_evidence,

        "generation_contract": {
            "resume_length": "ONE_PAGE",

            "experience_bullet_counts": current_bullet_counts,
            "experience_bullet_contract_basis": 'ADAPTIVE_CURRENT_VERIFIED_COVERAGE_AND_PAGE_BUDGET',
            "experience_slot_bullet_counts": slot_counts,

            "project_count": len(projects.get("selected_projects",[])),
            "project_bullet_counts": content_budget["project_bullet_counts"],
            "content_budget": content_budget,
            "project_bullets_each": 2,

            "bullet_style":
                "ACTION + TARGET_RELEVANT_SUPPORTED_METHOD + PURPOSE_OR_RESULT; "
                "include one useful scale anchor when it strengthens the evidence",

            "technical_density": "TARGET_RELEVANT_AND_READABLE",

            "reader":
                "experienced technical hiring manager "
                "and recruiter",

            "rules": [
                "Never invent metrics, scale, tools, employers, "
                "products, certifications, or outcomes.",

                "Every substantive claim must map to supplied "
                "evidence or an explicit direct-user fact/override.",

                "Direct-user-confirmed capabilities are real skills.",

                "Do not back-project a skill into a historical "
                "employer/project without evidence or direct correction.",

                "Preserve employment and project boundaries.",

                "Project authorship and completion must match source-owned evidence.",

                "When selected_projects[].visible_name is present, "
                "use it as the candidate-facing project name and do not "
                "replace it with canonical_name.",

                "Preserve selected project must_preserve_entities while "
                "obeying relationship_boundary. Organization or brand "
                "context must never be converted into employment.",

                "Never expose internal provenance labels such as "
                "reconstruction, rebuild, group project, or team-authored.",

                "Resolve project identity before selecting project evidence.",

                "Do not merge metrics from incompatible project iterations.",

                "Model thresholds and metrics must retain their source model and entity.",

                "Keep reporting layers distinct from underlying processing pipelines.",

                "Historical placement requires entity-specific source authority.",
            ],
        },
    }

    OUT_JSON.write_text(
        json.dumps(
            packet,
            indent=2,
            ensure_ascii=False,
        ) + "\n"
    )

    evidence_md = "\n\n".join(
        compact_evidence[x]
        for x in selected_ids
    )

    prompt = f"""
# CAREEROPS COMPACT RESUME GENERATION

Create exactly:

data/careerops-engine/runtime/generated_resume_content.json

Do not modify any other file.

The JSON packet below is the complete generation authority for this run.
Do not search the repository for additional candidate facts.
Do not load generic Career-Ops CV/profile material.
Do not invent missing facts.

============================================================
COMPACT GENERATION PACKET
============================================================

{json.dumps({
    k: v
    for k, v in packet.items()
    if k != "evidence"
}, indent=2, ensure_ascii=False)}

============================================================
SELECTED EVIDENCE
============================================================

{evidence_md}

============================================================
OUTPUT REQUIREMENTS
============================================================

Return the same generated_resume_content.json schema already used by
the CareerOps resume engine.

Mandatory structure:

- one summary sentence when summary_mode = ONE_LINE
- exactly 4 experience blocks
- experience bullets = 3 / 3 / 2 / 2
- exactly 2 selected projects
- exactly 2 bullets per project
- preserve supplied Technical Skills categories
- preserve supplied education facts
- generally 28-45 words per substantive bullet
- candidate-facing text only
- no internal provenance terminology
- no unsupported claims
- no invented metrics
- every bullet must be interview-defensible

Write the file and stop.
"""

    try:
        _runtime_prompt_prefix = (
            RUNTIME.relative_to(ROOT)
            .as_posix()
        )
    except ValueError:
        _runtime_prompt_prefix = (
            RUNTIME.as_posix()
        )

    prompt = prompt.replace(
        "data/careerops-engine/runtime/",
        _runtime_prompt_prefix.rstrip("/")
        + "/",
    )

    OUT_MD.write_text(
        prompt.strip() + "\n",
        encoding="utf-8",
    )

    old_prompt = RUNTIME / "resume_generation_prompt.md"

    old_chars = (
        len(old_prompt.read_text())
        if old_prompt.exists()
        else 0
    )

    new_chars = len(OUT_MD.read_text())

    print("=" * 80)
    print("COMPACT GENERATION PACKET: CREATED")
    print("=" * 80)
    print("Selected evidence:", ", ".join(selected_ids))
    print()
    print(f"OLD PROMPT: {old_chars:,} chars")
    print(f"NEW PROMPT: {new_chars:,} chars")

    if old_chars:
        reduction = (
            1 - (new_chars / old_chars)
        ) * 100

        print(
            f"REDUCTION: {reduction:.1f}%"
        )

    print()
    print(
        "ROUGH OLD TEXT TOKENS:",
        f"~{round(old_chars / 4):,}"
    )
    print(
        "ROUGH NEW TEXT TOKENS:",
        f"~{round(new_chars / 4):,}"
    )
    print()
    print(
        "PACKET:",
        OUT_JSON.relative_to(ROOT)
    )
    print(
        "PROMPT:",
        OUT_MD.relative_to(ROOT)
    )


if __name__ == "__main__":
    from careerops_requirement_authority import run_guarded
    run_guarded(main,RUNTIME,'careerops_build_compact_packet.py')

if __name__ == "__main__":
    budget_path = source_dir(ROOT) / "resume_layout_budget.json"
    if not budget_path.is_file():raise SystemExit("Missing configured physical layout budget")
    budget = json.loads(budget_path.read_text())
    packet = json.loads(OUT_JSON.read_text())
    instruction = """
HARD PHYSICAL ONE-PAGE LAYOUT BUDGET
The rendered geometry gate is authoritative. No minimum word count applies.
Follow the current packet's allocated experience/project bullet counts exactly.
Preserve exact supported JD terms, source-owned metrics and technical methods.
Compress repeated words and low-information clauses first. Never invent claims,
alter employer/role/date/project identity, merge unrelated projects, or back-project
capabilities into unsupported history. Every bullet remains subject to truth and
provenance checks. Use system-installed fonts and the configured physical budget.
"""
    OUT_MD.write_text(OUT_MD.read_text().rstrip()+"\n\n"+instruction+json.dumps({"physical_layout":budget,"current_content_budget":packet["generation_contract"]["content_budget"]},indent=2)+"\n")
    print("PHYSICAL LINE BUDGET: CONFIGURED CURRENT PACKET")
