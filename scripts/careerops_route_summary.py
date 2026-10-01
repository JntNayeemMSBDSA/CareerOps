from careerops_config import candidate_attestations
#!/usr/bin/env python3

import json
from pathlib import Path

from careerops_runtime import runtime_dir

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = runtime_dir(ROOT)
from careerops_requirement_authority import guard_before,guard_after
_authority_before=guard_before(RUNTIME,'careerops_route_summary.py')

SKILLS = RUNTIME / 'technical_skills_plan.json'
EXP = RUNTIME / 'experience_selection.json'
PROJ = RUNTIME / 'project_selection.json'
JD_INTAKE = RUNTIME / 'jd_intake.json'
ATS = RUNTIME / 'last_ats_probe.json'

SUMMARY_OUT = RUNTIME / 'summary_route.json'
SPEC_OUT = RUNTIME / 'resume_generation_spec.json'

skills = json.loads(SKILLS.read_text())
exp = json.loads(EXP.read_text())
proj = json.loads(PROJ.read_text())

# Presentation cleanup only.
for line in skills["visible_skill_lines"]:
    line["terms"] = [
        x for x in line["terms"]
        if x != "Microsoft Office"
    ]

workflow = next(
    (
        x for x in skills["visible_skill_lines"]
        if x["category"] == "Tools & Workflow"
    ),
    None
)

if workflow is not None and "Microsoft Office" not in workflow["terms"]:
    workflow["terms"].append("Microsoft Office")

SKILLS.write_text(
    json.dumps(skills, indent=2, ensure_ascii=False) + "\n"
)

def extract_ats_platform(payload):
    if not isinstance(payload, dict):
        return None

    current = payload.get("ats")

    if isinstance(current, dict):
        platform = current.get("platform")
        if platform:
            return platform

    final_detection = payload.get("final_detection")

    if isinstance(final_detection, dict):
        platform = final_detection.get("platform")
        if platform:
            return platform

    return (
        payload.get("detected_platform")
        or payload.get("platform")
    )


ats_platform = "UNKNOWN"

# Current job intake is the authoritative ATS source.
if JD_INTAKE.exists():
    try:
        current_jd = json.loads(
            JD_INTAKE.read_text()
        )
        ats_platform = (
            extract_ats_platform(current_jd)
            or "UNKNOWN"
        )
    except Exception:
        pass

# Legacy/global probe is fallback only. Never allow it to replace
# a valid ATS attached to the current job.
if ats_platform == "UNKNOWN" and ATS.exists():
    try:
        legacy_probe = json.loads(
            ATS.read_text()
        )
        ats_platform = (
            extract_ats_platform(legacy_probe)
            or "UNKNOWN"
        )
    except Exception:
        pass

summary = {
    "schema_version": "summary-route-v1",
    "mode": "ONE_LINE",
    "ats_platform": ats_platform,
    "ats_behavior_profile_supported": False,
    "reason": (
        "Preserve one-page technical density until a supported "
        "ATS-specific summary profile says otherwise."
    )
}

SUMMARY_OUT.write_text(
    json.dumps(summary, indent=2, ensure_ascii=False) + "\n"
)

spec = {
    "schema_version": "resume-generation-spec-v1",

    "summary_mode": "ONE_LINE",
    "one_page_required": True,

    "selected_experience_blocks": exp["selected_experience_blocks"],
    "selected_projects": proj["selected_projects"],
    "technical_skills_plan": skills["visible_skill_lines"],

    "generation_policy": {
        "technical_density": "TARGET_RELEVANT_AND_READABLE",

        "bullet_formula": (
            "ACTION + TARGET_RELEVANT_METHOD + PURPOSE_OR_SUPPORTED_RESULT; "
            "one useful scale anchor; one clear claim; max 34 words"
        ),

        "write_for_experienced_technical_reader": True,
        "make_hands_on_implementation_obvious": True,

        "prefer_supported_numbers": True,
        "prefer_exact_dataset_scale": True,
        "prefer_exact_stack_names": True,
        "prefer_data_grain": True,
        "prefer_architecture_detail": True,
        "prefer_query_and_transformation_detail": True,
        "prefer_model_or_statistical_method_detail": True,
        "prefer_validation_and_quality_controls": True,
        "prefer_business_or_research_purpose": True,
        "prefer_measurable_result": True,

        "avoid_generic_resume_language": True,
        "avoid_jd_paraphrase": True,
        "avoid_ai_buzzwords": True,
        "avoid_shallow_tool_listing": True,

        "every_bullet_interview_defensible": True,

        "direct_user_confirmed_capabilities_are_real_skills": True,
        "artifact_not_required_for_skill_possession": True,
        "historical_tool_placement_requires_support": True,

        "no_new_metrics": True,
        "no_new_scale": True,
        "no_new_employer": True,
        "no_new_product": True,
        "no_new_certification": True,
        "no_new_realized_outcome": True,

        "all_projects_owned_by_user": candidate_attestations(ROOT).get("project_ownership",{}).get("all_projects_owned_by_user",False),
        "group_project_wording_forbidden": candidate_attestations(ROOT).get("project_ownership",{}).get("never_label_as_group_project",False),
        "team_authorship_wording_forbidden": candidate_attestations(ROOT).get("project_ownership",{}).get("never_describe_as_team_authored",False),
        "project_to_employment_conversion_forbidden": True,

        "distinct_project_entities_must_not_be_merged": True
    },

    "quality_gates": {
        "ATS_MIN": 85,
        "HUMAN_MIN": 85,
        "TRUTH_REQUIRED": True,
        "PARSER_REQUIRED": True,
        "ONE_PAGE_REQUIRED": True
    }
}

SPEC_OUT.write_text(
    json.dumps(spec, indent=2, ensure_ascii=False) + "\n"
)

print("SUMMARY ROUTING: CREATED")
print("MODE: ONE_LINE")
print("ATS:", ats_platform)
print("TECHNICAL DENSITY: TARGET_RELEVANT_AND_READABLE")
print("EXPERIENCED TECHNICAL READER STANDARD: ACTIVE")
print("SUPPORTED NUMBERS / SCALE / STACK / METHODS: REQUIRED")
print("INTERVIEW DEFENSIBLE: REQUIRED")
print("ONE PAGE: REQUIRED")
print()
print("SKILLS:")
for line in skills["visible_skill_lines"]:
    print(
        f"- {line['category']}: "
        + ", ".join(line["terms"])
    )
print()
print("OUTPUT:", SUMMARY_OUT.relative_to(ROOT))
print("OUTPUT:", SPEC_OUT.relative_to(ROOT))

guard_after(RUNTIME,'careerops_route_summary.py',_authority_before)
