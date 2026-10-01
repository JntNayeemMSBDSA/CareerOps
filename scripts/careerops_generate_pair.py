from careerops_config import candidate_identity
#!/usr/bin/env python3

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


from careerops_runtime import runtime_dir

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = runtime_dir(ROOT)

PAIR_JSON = RUNTIME / "pair_generation_packet.json"
PAIR_PROMPT = RUNTIME / "pair_generation_prompt.md"
RESUME_SPEC = RUNTIME / "resume_generation_spec.json"

# Pair generation now stages candidates here.
RESUME_CANDIDATE = (
    RUNTIME / "generated_resume_content_pair_candidate.json"
)
COVER_CANDIDATE = (
    RUNTIME / "generated_cover_letter_pair_candidate.json"
)


def require(path):
    if not path.exists():
        raise SystemExit(f"Missing required file: {path}")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def count_words(text):
    return len(text.split())


def atomic_write_json(path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def normalize_contract_id(value):
    return "".join(
        ch
        for ch in str(value or "").upper()
        if ch.isalnum()
    )


def build_current_job_contract(
    spec,
    pair_packet,
):
    selected_exp = spec.get(
        "selected_experience_blocks",
        [],
    )

    selected_projects = spec.get(
        "selected_projects",
        [],
    )

    skill_plan = spec.get(
        "technical_skills_plan",
        [],
    )

    application_context = pair_packet.get(
        "application_context",
        {},
    )

    generation_contract = (
        application_context.get(
            "generation_contract",
            {},
        )
    )

    candidate_facts = (
        application_context.get(
            "candidate_facts",
            {},
        )
    )

    raw_exp_counts = (
        generation_contract.get(
            "experience_bullet_counts",
            {},
        )
    )

    exp_counts = {
        normalize_contract_id(key): value
        for key, value in raw_exp_counts.items()
    }

    experience_contract = []

    for block in selected_exp:
        block_id = block.get(
            "block_id"
        )

        normalized_id = (
            normalize_contract_id(
                block_id
            )
        )

        bullet_count = exp_counts.get(
            normalized_id
        )

        if (
            not isinstance(
                bullet_count,
                int,
            )
            or bullet_count < 1
        ):
            raise SystemExit(
                "Missing valid current-job bullet contract for "
                f"{block_id!r}."
            )

        identity = {
            "block_id":
                block_id,

            "company":
                (
                    block.get("company")
                    or block.get(
                        "organization"
                    )
                ),

            "title":
                block.get("title"),

            "dates":
                (
                    block.get("dates")
                    or block.get(
                        "period"
                    )
                ),

            "bullet_count":
                bullet_count,
        }

        missing = [
            key
            for key in [
                "block_id",
                "company",
                "title",
                "dates",
            ]
            if not identity.get(key)
        ]

        if missing:
            raise SystemExit(
                "Current deterministic experience selection "
                "is missing identity fields: "
                + ", ".join(missing)
            )

        experience_contract.append(
            identity
        )

    expected_project_count = (
        generation_contract.get(
            "project_count"
        )
    )

    project_bullets_each = (
        generation_contract.get(
            "project_bullets_each"
        )
    )

    if (
        not isinstance(
            expected_project_count,
            int,
        )
        or expected_project_count < 0
    ):
        raise SystemExit(
            "Missing valid current-job project-count contract."
        )

    if len(
        selected_projects
    ) != expected_project_count:
        raise SystemExit(
            "Current deterministic project selection count "
            "does not match current-job generation contract."
        )

    if (
        not isinstance(
            project_bullets_each,
            int,
        )
        or project_bullets_each < 1
    ):
        raise SystemExit(
            "Missing valid current-job project bullet contract."
        )

    project_contract = []

    for project in selected_projects:
        entity_id = project.get(
            "entity_id"
        )

        if not entity_id:
            raise SystemExit(
                "Current deterministic project selection "
                "is missing entity_id."
            )

        project_name = (
            project.get(
                "visible_name"
            )
            or project.get(
                "canonical_name"
            )
            or project.get("name")
            or project.get(
                "project_name"
            )
            or project.get("title")
            or project.get(
                "display_name"
            )
            or project.get(
                "entity_name"
            )
            or project.get(
                "evidence_name"
            )
        )

        item = {
            "entity_id":
                entity_id,

            "bullet_count":
                generation_contract.get("project_bullet_counts", {}).get(entity_id, project_bullets_each),
        }

        if project_name:
            item["name"] = (
                project_name
            )

        project_contract.append(
            item
        )

    skill_categories = [
        item.get("category")
        for item in skill_plan
    ]

    if (
        not skill_categories
        or any(
            not isinstance(
                x,
                str,
            )
            or not x.strip()
            for x in skill_categories
        )
    ):
        raise SystemExit(
            "Current-job skill-category contract is invalid."
        )

    source_education = (
        candidate_facts.get(
            "education",
            [],
        )
    )

    if not source_education:
        raise SystemExit(
            "Canonical candidate education facts are missing."
        )

    education = []

    for item in source_education:
        institution = item.get(
            "institution"
        )

        degree = (
            item.get(
                "resume_degree"
            )
            or item.get(
                "degree"
            )
        )

        graduation = (
            item.get(
                "graduation"
            )
            or item.get(
                "completion"
            )
        )

        gpa = item.get(
            "gpa"
        )

        if not all([
            institution,
            degree,
            graduation,
            gpa,
        ]):
            raise SystemExit(
                "Canonical education record is incomplete "
                f"for {institution!r}."
            )

        rendered = {
            "institution":
                institution,
            "degree":
                degree,
            "graduation":
                graduation,
            "gpa":
                gpa,
        }

        honors = item.get(
            "honors"
        )

        if honors:
            rendered[
                "honors"
            ] = honors

        education.append(
            rendered
        )

    return {
        "top_level_key_order": [
            "summary",
            "experience",
            "projects",
            "skills",
            "education",
        ],

        "experience":
            experience_contract,

        "projects":
            project_contract,

        "skill_categories":
            skill_categories,
        "skills_stack_contract": application_context.get("skills_stack_contract"),

        "education":
            education,

        "rules": [
            (
                "Experience identity comes from the current "
                "job's deterministic selection and must be "
                "copied unchanged."
            ),
            (
                "Experience bullet counts come from the "
                "current job's generation contract."
            ),
            (
                "Project identity and count come from the "
                "current job's deterministic selection and "
                "generation contract."
            ),
            (
                "Skill categories come from the current "
                "job's technical skills plan."
            ),
            (
                "Education comes from canonical candidate "
                "facts and must be copied unchanged."
            ),
            (
                "Tailor summary and bullets to the current job. "
                "Copy the approved skills_stack_contract.visible_skill_lines exactly when supplied; otherwise tailor skill terms."
            ),
            "Use the exact top-level key names and ordering.",
            "The skills key is named skills, never technical_skills.",
            "Do not add schema_version.",
            "Do not add target_position.",
            "Do not add summary_mode.",
            "Do not add evidence_ids to resume blocks.",
        ],
    }


def validate_resume(resume, job_contract):
    expected_top = [
        "summary",
        "experience",
        "projects",
        "skills",
        "education",
    ]

    if list(resume.keys()) != expected_top:
        raise SystemExit(
            "PAIR RESUME SCHEMA FAIL\n"
            f"Expected top-level keys: {expected_top}\n"
            f"Received: {list(resume.keys())}"
        )

    if not isinstance(resume["summary"], str):
        raise SystemExit(
            "Resume summary must be a string."
        )

    if not resume["summary"].strip():
        raise SystemExit(
            "Resume summary is empty."
        )

    # --------------------------------------------------------
    # EXPERIENCE
    # Current deterministic job selection is authoritative.
    # --------------------------------------------------------

    locked_exp = job_contract["experience"]

    if len(resume["experience"]) != len(locked_exp):
        raise SystemExit(
            "Resume experience-block count changed."
        )

    expected_exp_keys = [
        "block_id",
        "company",
        "title",
        "dates",
        "bullets",
    ]

    for i, (new, locked) in enumerate(
        zip(resume["experience"], locked_exp)
    ):
        if list(new.keys()) != expected_exp_keys:
            raise SystemExit(
                f"Experience block {i + 1} schema changed.\n"
                f"Expected: {expected_exp_keys}\n"
                f"Received: {list(new.keys())}"
            )

        for field in [
            "block_id",
            "company",
            "title",
            "dates",
        ]:
            if new[field] != locked[field]:
                raise SystemExit(
                    "Current-job experience identity changed: "
                    f"block {i + 1}, field={field!r}\n"
                    f"Expected: {locked[field]!r}\n"
                    f"Received: {new[field]!r}"
                )

        if len(new["bullets"]) != locked["bullet_count"]:
            raise SystemExit(
                f"Experience block {i + 1} bullet count changed. "
                f"Expected {locked['bullet_count']}, "
                f"received {len(new['bullets'])}."
            )

        if not all(
            isinstance(x, str) and x.strip()
            for x in new["bullets"]
        ):
            raise SystemExit(
                f"Experience block {i + 1} has invalid bullets."
            )

    # --------------------------------------------------------
    # PROJECTS
    # Current deterministic project entity IDs are authoritative.
    # --------------------------------------------------------

    locked_projects = job_contract["projects"]

    if len(resume["projects"]) != len(
        locked_projects
    ):
        raise SystemExit(
            "Resume project count changed."
        )

    expected_project_keys = [
        "entity_id",
        "name",
        "bullets",
    ]

    for i, (new, locked) in enumerate(
        zip(
            resume["projects"],
            locked_projects,
        )
    ):
        if list(new.keys()) != expected_project_keys:
            raise SystemExit(
                f"Project {i + 1} schema changed.\n"
                f"Expected: {expected_project_keys}\n"
                f"Received: {list(new.keys())}"
            )

        if new["entity_id"] != locked["entity_id"]:
            raise SystemExit(
                "Current-job project identity changed: "
                f"project {i + 1}\n"
                f"Expected entity_id: "
                f"{locked['entity_id']!r}\n"
                f"Received: {new['entity_id']!r}"
            )

        if (
            locked.get("name")
            and new["name"] != locked["name"]
        ):
            raise SystemExit(
                "Current-job project name changed: "
                f"project {i + 1}\n"
                f"Expected: {locked['name']!r}\n"
                f"Received: {new['name']!r}"
            )

        if not (
            isinstance(new["name"], str)
            and new["name"].strip()
        ):
            raise SystemExit(
                f"Project {i + 1} has invalid name."
            )

        if len(new["bullets"]) != locked["bullet_count"]:
            raise SystemExit(
                f"Project {i + 1} bullet count changed. "
                f"Expected {locked['bullet_count']}, "
                f"received {len(new['bullets'])}."
            )

        if not all(
            isinstance(x, str) and x.strip()
            for x in new["bullets"]
        ):
            raise SystemExit(
                f"Project {i + 1} has invalid bullets."
            )

    # --------------------------------------------------------
    # SKILLS
    # Categories/layout remain locked, terms are job-specific.
    # --------------------------------------------------------

    locked_categories = job_contract[
        "skill_categories"
    ]

    if len(resume["skills"]) != len(
        locked_categories
    ):
        raise SystemExit(
            "Resume skill-category count changed."
        )

    expected_skill_keys = [
        "category",
        "terms",
    ]

    for i, (new, locked_category) in enumerate(
        zip(
            resume["skills"],
            locked_categories,
        )
    ):
        if list(new.keys()) != expected_skill_keys:
            raise SystemExit(
                f"Skills block {i + 1} schema changed."
            )

        if new["category"] != locked_category:
            raise SystemExit(
                "Locked skills category changed: "
                f"{locked_category!r} -> "
                f"{new['category']!r}"
            )

        if not isinstance(new["terms"], list):
            raise SystemExit(
                f"Skills block {i + 1} terms must be a list."
            )

        if not all(
            isinstance(x, str) and x.strip()
            for x in new["terms"]
        ):
            raise SystemExit(
                f"Skills block {i + 1} contains invalid terms."
            )

    skills_contract = job_contract.get("skills_stack_contract")
    if skills_contract:
        from careerops_skills_stack import audit_stack
        stack_audit = audit_stack(resume["skills"], skills_contract)
        if stack_audit["gate"] != "PASS":
            raise SystemExit("SKILLS_STACK_WRITER_FAIL: " + json.dumps(stack_audit["findings"]))
        if resume["skills"] != skills_contract["visible_skill_lines"]:
            raise SystemExit("Approved source-bound skills stack changed; regenerate the deterministic plan first.")

    # --------------------------------------------------------
    # EDUCATION
    # Still locked to approved factual template.
    # --------------------------------------------------------

    if resume["education"] != job_contract["education"]:
        raise SystemExit(
            "Locked education content changed."
        )

    # --------------------------------------------------------
    # GLOBAL BASIC CONTENT CHECKS
    # --------------------------------------------------------

    serialized = json.dumps(
        resume,
        ensure_ascii=False,
    )

    if "technical_skills" in resume:
        raise SystemExit(
            "Resume used forbidden key: technical_skills"
        )

    if "—" in serialized:
        raise SystemExit(
            "Resume contains an em dash."
        )


def validate_cover(cover):
    expected_keys = [
        "company",
        "position",
        "salutation",
        "paragraphs",
        "closing",
        "signature",
        "primary_evidence_ids",
        "secondary_evidence_ids",
        "numerical_anchors",
        "jd_terms_used",
    ]

    if list(cover.keys()) != expected_keys:
        raise SystemExit(
            "PAIR COVER SCHEMA FAIL\n"
            f"Expected keys: {expected_keys}\n"
            f"Received: {list(cover.keys())}"
        )

    paragraphs = cover["paragraphs"]

    if len(paragraphs) != 3:
        raise SystemExit(
            "Cover must contain exactly 3 paragraphs."
        )

    if not all(
        isinstance(x, str) and x.strip()
        for x in paragraphs
    ):
        raise SystemExit(
            "Cover contains an empty/invalid paragraph."
        )

    body = "\n\n".join(paragraphs)
    body_words = count_words(body)

    if not cover["company"].strip():
        raise SystemExit(
            "Cover company missing."
        )

    if not cover["position"].strip():
        raise SystemExit(
            "Cover position missing."
        )

    if cover["salutation"] != "Dear Hiring Manager,":
        raise SystemExit(
            "Unexpected cover salutation."
        )

    if cover["closing"] != "Sincerely,":
        raise SystemExit(
            "Unexpected cover closing."
        )

    if cover["signature"] != candidate_identity(ROOT)["name"]:
        raise SystemExit(
            "Unexpected cover signature."
        )

    if len(cover["primary_evidence_ids"]) < 1:
        raise SystemExit(
            "Cover has no primary evidence entity."
        )

    if len(cover["secondary_evidence_ids"]) > 1:
        raise SystemExit(
            "Cover has more than one secondary evidence entity."
        )

    if len(cover["numerical_anchors"]) < 2:
        raise SystemExit(
            "Cover has fewer than 2 numerical anchors."
        )

    if not (
        3 <= len(cover["jd_terms_used"]) <= 6
    ):
        raise SystemExit(
            "Cover must track 3-6 JD terms."
        )

    if "—" in body:
        raise SystemExit(
            "Cover contains an em dash."
        )

    if not (
        190 <= body_words <= 240
    ):
        raise SystemExit(
            f"Cover body length outside 190-240: "
            f"{body_words}"
        )

    required_end = (
        "Thank you for your consideration."
    )

    if not paragraphs[2].strip().endswith(
        required_end
    ):
        raise SystemExit(
            "Paragraph 3 does not end with the "
            "required sentence."
        )

    return body_words


def build_isolated_packet(
    original_packet,
    job_contract,
):
    packet = json.loads(
        json.dumps(original_packet)
    )

    # The model must not decide its own output schema.
    packet["output_contract"]["resume"]["path"] = (
        "resume_candidate.json"
    )

    packet["output_contract"]["cover_letter"]["path"] = (
        "cover_candidate.json"
    )

    packet["output_contract"]["resume"]["schema"] = {
        "summary": "string",
        "experience": [
            {
                "block_id": "string",
                "company": "string",
                "title": "string",
                "dates": "string",
                "bullets": ["string"],
            }
        ],
        "projects": [
            {
                "entity_id": "string",
                "name": "string",
                "bullets": ["string"],
            }
        ],
        "skills": [
            {
                "category": "string",
                "terms": ["string"],
            }
        ],
        "education": [
            {
                "institution": "string",
                "degree": "string",
                "graduation": "string",
                "gpa": "string",
            }
        ],
    }

    packet["output_contract"]["resume"][
        "forbidden_output_keys"
    ] = [
        "schema_version",
        "target_position",
        "summary_mode",
        "technical_skills",
        "evidence_ids",
    ]

    # IMPORTANT:
    # This contract comes from the CURRENT JOB'S deterministic
    # selection. It must never inherit project/experience identity
    # from the previous tailored resume.
    packet["locked_resume_identity_contract"] = (
        job_contract
    )

    return packet


def main():
    from careerops_writer_accounting import prepare, invoke, save
    invocation_state = prepare(RUNTIME)
    require(PAIR_JSON)
    require(PAIR_PROMPT)
    require(RESUME_SPEC)

    from careerops_model_policy import preflight
    preflight("xhigh", RUNTIME)

    original_packet = json.loads(
        PAIR_JSON.read_text(
            encoding="utf-8"
        )
    )

    current_spec = json.loads(
        RESUME_SPEC.read_text(
            encoding="utf-8"
        )
    )

    job_contract = build_current_job_contract(
        current_spec,
        original_packet,
    )

    isolated_packet = build_isolated_packet(
        original_packet,
        job_contract,
    )

    prompt_text = PAIR_PROMPT.read_text(
        encoding="utf-8"
    )

    # Rewrite CURRENT run output locations only in the
    # isolated writer copy.
    resume_declared_path = (
        original_packet
        .get("output_contract", {})
        .get("resume", {})
        .get("path")
    )

    cover_declared_path = (
        original_packet
        .get("output_contract", {})
        .get("cover_letter", {})
        .get("path")
    )

    if not resume_declared_path:
        raise SystemExit(
            "Pair packet is missing resume output path."
        )

    if not cover_declared_path:
        raise SystemExit(
            "Pair packet is missing cover output path."
        )

    prompt_text = prompt_text.replace(
        resume_declared_path,
        "resume_candidate.json",
    )

    prompt_text = prompt_text.replace(
        cover_declared_path,
        "cover_candidate.json",
    )

    if resume_declared_path in prompt_text:
        raise SystemExit(
            "Repository resume output path remains in "
            "isolated writer prompt."
        )

    if cover_declared_path in prompt_text:
        raise SystemExit(
            "Repository cover output path remains in "
            "isolated writer prompt."
        )

    prompt_text += """

============================================================
STRICT ISOLATED-WRITER RULES
============================================================

This directory is intentionally isolated from the Career-Ops repository.

DO NOT:
- search for a repository
- load AGENTS.md
- load any skill
- load Career-Ops
- read parent directories
- run onboarding
- run doctor
- run update-system
- search the web
- search for additional candidate facts
- redo JD analysis
- redo role routing
- redo evidence retrieval
- change the resume schema

The only authorities for this writing task are:
1. writer_instructions.md
2. pair_generation_packet.json

Write exactly:
- resume_candidate.json
- cover_candidate.json

The resume MUST use exactly these top-level keys in this order:

summary
experience
projects
skills
education

Never output technical_skills.

The locked identity contract inside pair_generation_packet.json
must be copied exactly.

Do not create any other files.
"""

    env = os.environ.copy()

    for key in [
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "CODEX_API_KEY",
        "CODEX_ACCESS_TOKEN",
    ]:
        env.pop(key, None)

    with tempfile.TemporaryDirectory(
        prefix="careerops-pair-writer-"
    ) as temp_name:

        workdir = Path(temp_name)

        (
            workdir / "writer_instructions.md"
        ).write_text(
            prompt_text,
            encoding="utf-8",
        )

        (
            workdir / "pair_generation_packet.json"
        ).write_text(
            json.dumps(
                isolated_packet,
                indent=2,
                ensure_ascii=False,
            ) + "\n",
            encoding="utf-8",
        )

        command = [
            "codex",
            "exec",
            "--skip-git-repo-check",
            "-m",
            "gpt-6.1-sol",
            "-c",
            'model_reasoning_effort="xhigh"',
            "--sandbox",
            "workspace-write",
            (
                "Do not load any skill, repository instruction, "
                "AGENTS.md, or external context. "
                "This isolated directory contains the complete "
                "authority for the task. "
                "Read writer_instructions.md completely. "
                "Then read pair_generation_packet.json completely. "
                "Generate exactly resume_candidate.json and "
                "cover_candidate.json. "
                "Do not create or modify any other file."
            ),
        ]

        print()
        print("=" * 96)
        print(
            "STARTING ISOLATED GPT-6.1 SOL / XHIGH "
            "PAIR WRITER"
        )
        print("=" * 96)
        print(
            "Repository discovery: DISABLED BY ISOLATION"
        )
        print(
            "Approved resume overwrite: FORBIDDEN"
        )
        print(
            "API environment variables: REMOVED"
        )
        print()

        return_code = invoke(RUNTIME, invocation_state, command, cwd=workdir, env=env)

        if return_code != 0:
            raise SystemExit(f"Codex exited with code {return_code}")

        temp_resume = (
            workdir / "resume_candidate.json"
        )

        temp_cover = (
            workdir / "cover_candidate.json"
        )

        require(temp_resume)
        require(temp_cover)

        try:
            resume = json.loads(
                temp_resume.read_text(
                    encoding="utf-8"
                )
            )
        except Exception as exc:
            raise SystemExit(
                f"Resume JSON invalid: {exc}"
            )

        try:
            cover = json.loads(
                temp_cover.read_text(
                    encoding="utf-8"
                )
            )
        except Exception as exc:
            raise SystemExit(
                f"Cover JSON invalid: {exc}"
            )

        validate_resume(
            resume,
            job_contract,
        )

        body_words = validate_cover(
            cover
        )
        invocation_state['output_validated'] = True
        save(RUNTIME, invocation_state)

        # Staging only.
        # The approved resume is deliberately NOT promoted/replaced.
        atomic_write_json(
            RESUME_CANDIDATE,
            resume,
        )

        atomic_write_json(
            COVER_CANDIDATE,
            cover,
        )

    print()
    print("=" * 96)
    print("PAIR WRITER CANDIDATE GENERATION: PASS")
    print("=" * 96)
    print(
        "Prior-resume dependency: NONE"
    )
    print(
        "Resume schema: EXACT LOCKED SCHEMA"
    )
    print(
        "Experience blocks:",
        len(resume["experience"]),
    )
    print(
        "Projects:",
        len(resume["projects"]),
    )
    print(
        "Skills key:",
        "skills",
    )
    print(
        "Cover paragraphs:",
        len(cover["paragraphs"]),
    )
    print(
        "Cover body words:",
        body_words,
    )
    print()
    print(
        "STAGED RESUME:",
        RESUME_CANDIDATE.relative_to(ROOT),
    )
    print(
        "STAGED COVER:",
        COVER_CANDIDATE.relative_to(ROOT),
    )
    print()
    print(
        "Generated resume and cover remain staged "
        "inside the active run."
    )
    print("=" * 96)


if __name__ == "__main__":
    from careerops_requirement_authority import run_guarded
    run_guarded(main, RUNTIME, "careerops_generate_pair.py")
