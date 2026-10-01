import sys
from careerops_config import candidate_identity
from careerops_config import source_dir
#!/usr/bin/env python3

import argparse
import json
import subprocess
from pathlib import Path

from careerops_runtime import runtime_dir
from careerops_intelligence_bus import build_intelligence_bus

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = runtime_dir(ROOT)
SOURCE = source_dir(ROOT)

COMPACT_JSON = RUNTIME / "compact_generation_packet.json"
COVER_RULES = SOURCE / "cover_letter_rules.json"
COVER_PLAN = RUNTIME / "cover_plan.json"
INTELLIGENCE_BUS = RUNTIME / "intelligence_bus.json"

PAIR_JSON = RUNTIME / "pair_generation_packet.json"
PAIR_PROMPT = RUNTIME / "pair_generation_prompt.md"


def load_json(path):
    if not path.exists():
        raise SystemExit(f"Missing required file: {path}")
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(
        description="Build coordinated resume + cover generation packet."
    )
    parser.add_argument("--company")
    parser.add_argument("--position")
    args = parser.parse_args()

    # Rebuild the existing compact application context.
    # This is the SAME analysis already used by the resume engine.
    # REFRESH CURRENT RESUME SPEC BEFORE COMPACT PAIR BUILD
    summary_result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/careerops_route_summary.py"),
        ],
        cwd=ROOT,
    )

    if summary_result.returncode != 0:
        raise SystemExit(
            "Resume-spec refresh failed with code "
            f"{summary_result.returncode}"
        )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/careerops_build_compact_packet.py",
        ],
        cwd=ROOT
    )

    if result.returncode != 0:
        raise SystemExit(
            "Existing compact packet builder failed."
        )

    application = load_json(COMPACT_JSON)
    cover_rules = load_json(COVER_RULES)
    from careerops_compile_cover_authority import compile_cover_authority
    compiled_cover_authority = compile_cover_authority(COVER_RULES)

    # Build the deterministic cover story from the SAME already-computed
    # application intelligence. This is planning only, not generation.
    cover_command = [
        sys.executable,
        "scripts/careerops_build_cover_plan.py",
    ]

    if args.company:
        cover_command.extend([
            "--company",
            args.company,
        ])

    if args.position:
        cover_command.extend([
            "--position",
            args.position,
        ])

    cover_plan_result = subprocess.run(
        cover_command,
        cwd=ROOT
    )

    if cover_plan_result.returncode != 0:
        raise SystemExit(
            "Cover Planner V2 failed."
        )

    cover_plan = load_json(COVER_PLAN)

    # Build the deterministic intelligence integration bus from the
    # already-computed runtime artifacts. This does NOT perform another
    # JD, market, evidence, or model-analysis pass.
    intelligence_bus = build_intelligence_bus(RUNTIME)

    INTELLIGENCE_BUS.write_text(
        json.dumps(
            intelligence_bus,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )

    try:
        runtime_prompt_prefix = (
            RUNTIME.relative_to(ROOT)
            .as_posix()
        )
    except ValueError:
        runtime_prompt_prefix = (
            RUNTIME.as_posix()
        )

    packet = {
        "schema_version":
            "careerops-pair-generation-packet-v1",

        "generation_mode":
            "RESUME_AND_COVER_PAIR",

        "optimization": {
            "shared_jd_analysis": True,
            "shared_role_routing": True,
            "shared_evidence_resolution": True,
            "shared_candidate_authority": True,
            "single_model_generation_call": True,
            "separate_post_generation_gates": True,
            "target_model": "gpt-6.1-sol",
            "reasoning_effort": "xhigh"
        },

        "application_context":
            application,

        "intelligence_bus":
            intelligence_bus,

        "cover_letter_rules":
            cover_rules,
        "compiled_cover_authority": compiled_cover_authority,

        "cover_plan":
            cover_plan,

        "output_contract": {

            "resume": {
                "path":
                    "data/careerops-engine/runtime/"
                    "generated_resume_content.json",

                "schema":
                    "USE THE EXISTING RESUME JSON SCHEMA "
                    "ALREADY DEFINED IN application_context",

                "coordination_rule":
                    "Generate the strongest JD-tailored resume "
                    "using the existing resume rules."
            },

            "cover_letter": {
                "path":
                    "data/careerops-engine/runtime/"
                    "generated_cover_letter.json",

                "schema": {
                    "company":
                        "exact employer name",

                    "position":
                        "exact job title",

                    "salutation":
                        "Dear Hiring Manager,",

                    "paragraphs": [
                        "paragraph 1",
                        "paragraph 2",
                        "paragraph 3"
                    ],

                    "closing":
                        "Sincerely,",

                    "signature":
                        candidate_identity(ROOT)["name"],

                    "primary_evidence_ids":
                        ["EXP-XXX"],

                    "secondary_evidence_ids":
                        [],

                    "numerical_anchors": [
                        {
                            "text": "anchor as used in letter",
                            "source_entity": "EXP-XXX"
                        }
                    ],

                    "jd_terms_used":
                        ["supported exact JD term"]
                },

                "coordination_rule":
                    "The cover letter must complement the resume, "
                    "not convert resume bullets into prose."
            }
        },

        "cross_document_rules": [
            "Separate ongoing employment from completed deliverables. Use candidate_facts.deliverable_state_authority; completed built-and-validated work uses past tense in both documents.",
            "Respect adaptive content_budget: one clear claim per bullet, at most 34 words; select useful detail rather than stacking every scale/table/tool in one bullet.",
            "In cover paragraph 3 explicitly name the employer, state a specific reason you want this work tied to a concrete target stakeholder or decision, then explain your contribution. A list of duties alone is not an interest reason.",
            "Vary sentence structure naturally. Do not repeatedly use At COMPANY I would apply the same reasoning. Ground interest in the supplied JD without inventing company facts.",
            "Resume and cover letter must use the same candidate authority.",
            "Direct-user-confirmed capabilities are real skills.",
            "Use intelligence_bus.writer_contract as the deterministic skill and complementary-capability use contract.",
            "Market-prior-only skills in intelligence_bus.writer_contract.advisory_only_do_not_claim are context only and must not be presented as candidate skills.",
            "A direct-user-confirmed capability may appear as a skill but does not prove historical employer/project placement.",
            "Historical placement still requires existing verified evidence ownership.",
            "Do not invent historical placement of a capability.",
            "Do not contradict employer, role, dates, metrics, tools, ownership, or outcomes across documents.",
            "The cover letter should deepen one primary evidence story rather than summarize the resume.",
            "The deterministic cover_plan is the cover story-selection authority.",
            "Do not replace cover_plan.primary_evidence with another story unless the plan explicitly authorizes secondary evidence.",
            "Use cover_plan.resume_overlap_exclusions to avoid bullet-to-prose rewriting.",
            "Use cover_plan.claim_ledger and truth_boundaries for factual cover claims.",
            "Preserve cover_plan.target_role_application as future application, not historical experience.",
            "Use cover_plan.interest_reason as the required employer/role-specific interest basis.",
            "Generate both documents from this one shared application context.",
            "Do not perform another JD, market, or evidence-analysis pass.",
            "Do not search the repository for additional candidate facts.",
            "Never use an em dash."
        ]
    }

    packet["output_contract"]["resume"]["path"] = (
        runtime_prompt_prefix.rstrip("/")
        + "/generated_resume_content.json"
    )

    packet["output_contract"]["cover_letter"]["path"] = (
        runtime_prompt_prefix.rstrip("/")
        + "/generated_cover_letter.json"
    )

    PAIR_JSON.write_text(
        json.dumps(
            packet,
            indent=2,
            ensure_ascii=False
        ) + "\n"
    )

    prompt = f"""
# CAREEROPS APPLICATION PAIR GENERATION

Generate TWO coordinated application documents from ONE shared
application context:

1. Resume content
2. Cover-letter content

The complete generation authority is contained in:

data/careerops-engine/runtime/pair_generation_packet.json

For the cover letter, compiled_cover_authority is the compact paragraph,
voice, and truth checklist. Apply its draft_checklist before finalizing.
cover_plan inside that packet is the deterministic story plan. Do not perform a new cover-story selection pass.

Do not search the repository for additional candidate facts.
Do not repeat JD analysis.
Do not repeat market analysis.
Do not repeat evidence retrieval.

Use intelligence_bus inside pair_generation_packet.json as the
deterministic ATS/role/skill/proficiency/complementary-capability
integration contract. Obey its writer_contract and truth_boundaries.
Never convert market-only advisory terms into candidate claims.
Direct-user-confirmed proficiency may support a Skills entry but does
not establish historical use at an employer or project without existing
verified evidence.

============================================================
OUTPUT 1
============================================================

Create:

data/careerops-engine/runtime/generated_resume_content.json

Use the SAME resume JSON schema and resume generation rules already
contained in the application_context.

Do not weaken or redesign the existing resume.

============================================================
OUTPUT 2
============================================================

Create:

data/careerops-engine/runtime/generated_cover_letter.json

Required JSON structure:

{{
  "company": "Exact Company",
  "position": "Exact Position",
  "salutation": "Dear Hiring Manager,",
  "paragraphs": [
    "Paragraph 1",
    "Paragraph 2",
    "Paragraph 3"
  ],
  "closing": "Sincerely,",
  "signature": "{candidate_identity(ROOT)['name']}",
  "primary_evidence_ids": ["EXP-XXX"],
  "secondary_evidence_ids": [],
  "numerical_anchors": [
    {{
      "text": "...",
      "source_entity": "EXP-XXX"
    }},
    {{
      "text": "...",
      "source_entity": "EXP-XXX"
    }}
  ],
  "jd_terms_used": ["...", "...", "..."]
}}

============================================================
PAIR COORDINATION
============================================================

The resume and cover letter are a pair.

The cover letter must:
- use cover_plan.primary_evidence as the dominant evidence story
- follow cover_plan.story for problem, constraint, judgment, reasoning, implementation, validation, output, and consequence
- use cover_plan.target_role_application to connect the reasoning to the target role
- use cover_plan.interest_reason for the specific employer/role interest
- obey cover_plan.claim_ledger and truth_boundaries
- respect cover_plan.resume_overlap_exclusions
- deepen the strongest relevant evidence
- explain mechanics, reasoning, QA, constraints, or purpose
- avoid simply rewriting resume bullets
- remain consistent with every factual resume claim
- contain exactly 3 body paragraphs
- use at least 2 meaningful numerical anchors
- use 3 to 6 supported central JD terms naturally
- end Paragraph 3 with:
  "Thank you for your consideration."
- never use an em dash
- contain no generic cover-letter filler

============================================================
AUTHORITY
============================================================

Direct-user corrections and candidate_attestations are authoritative.

Direct-user-confirmed capabilities are REAL candidate skills.

Artifact proof is not required merely to establish possession of a
direct-user-confirmed capability.

However, do not invent that a capability was used at a particular
historical employer or project unless that placement is supported by
the supplied evidence or a direct-user correction.

============================================================
FINAL SELF-CHECK
============================================================

Before writing either file:

RESUME
- preserve existing resume structure
- preserve existing truth rules
- preserve one-page content discipline

COVER
- exactly 3 paragraphs
- roughly 190-240 body words
- exact company present
- exact position present
- one dominant evidence story
- no more than one secondary evidence story
- at least 2 supported numerical anchors
- at least one anchor in Paragraph 2
- no resume-bullet copying
- no generic opening
- no generic company praise
- no unsupported historical placement
- no banned generic language
- no em dash

CROSS-DOCUMENT
- no factual contradictions
- no metric contradictions
- no tool-placement contradictions
- no ownership contradictions
- no role/date contradictions
"""

    prompt = prompt.replace(
        "data/careerops-engine/runtime/",
        runtime_prompt_prefix.rstrip("/")
        + "/",
    )

    PAIR_PROMPT.write_text(
        prompt.strip() + "\n"
    )

    print("=" * 96)
    print("PAIR GENERATION PACKET: CREATED")
    print("=" * 96)
    print("Existing JD analysis reused: YES")
    print("Existing role routing reused: YES")
    print("Existing evidence mapping reused: YES")
    print("Existing authority reused: YES")
    print("Resume engine modified: NO")
    print("Resume formatter modified: NO")
    print("Model calls: 0")
    print()
    print("PAIR JSON:", PAIR_JSON.relative_to(ROOT))
    print("PAIR PROMPT:", PAIR_PROMPT.relative_to(ROOT))
    print("=" * 96)


if __name__ == "__main__":
    from careerops_requirement_authority import run_guarded
    run_guarded(main, RUNTIME, "careerops_build_pair_packet.py")
