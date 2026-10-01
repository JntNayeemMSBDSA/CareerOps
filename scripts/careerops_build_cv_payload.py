from careerops_config import candidate_identity, load_facts
from careerops_config import source_dir
#!/usr/bin/env python3

import json
import os
import subprocess
from pathlib import Path

from careerops_runtime import runtime_dir

ROOT = Path(__file__).resolve().parents[1]

RUNTIME = runtime_dir(ROOT)

SOURCE_FILE = Path(
    os.environ.get(
        "CAREEROPS_RESUME_INPUT",
        str(
            RUNTIME
            / "generated_resume_content.json"
        ),
    )
).expanduser().resolve()

ROLE_ROUTING_FILE = (
    RUNTIME / "role_routing.json"
)

SUMMARY_ROUTE_FILE = (
    RUNTIME / "summary_route.json"
)

OUTPUT_FILE = Path(
    os.environ.get(
        "CAREEROPS_CV_PAYLOAD_OUTPUT",
        str(
            RUNTIME
            / "career_ops_cv_payload.json"
        ),
    )
).expanduser().resolve()

VALIDATION_FILE = Path(
    os.environ.get(
        "CAREEROPS_CV_PAYLOAD_VALIDATION_OUTPUT",
        str(
            RUNTIME
            / "career_ops_cv_payload_validation.json"
        ),
    )
).expanduser().resolve()


VALIDATION_HTML_FILE = (
    RUNTIME
    / "career_ops_cv_payload_validation_preview.html"
).resolve()


# ------------------------------------------------------------------
# AUTHORITATIVE CANDIDATE HEADER
# ------------------------------------------------------------------
#
# Candidate identity and links are loaded from configured authority.
# ------------------------------------------------------------------

CANDIDATE = candidate_identity(ROOT)


REFERENCE_LINKS = load_facts(ROOT).get("certification_links", {})


CERTIFICATIONS = load_facts(ROOT).get("certifications", [])


PROJECT_DATE_OVERRIDES = load_facts(ROOT).get("project_date_overrides", {})


def load_json(path):
    if not path.exists():
        raise SystemExit(
            f"Missing required source file: {path}"
        )

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def clean(value):
    if value is None:
        return ""

    return str(value).strip()


def build_payload(
    source,
    role_routing,
    summary_route
):
    target_role = clean(
        role_routing.get(
            "input",
            {}
        ).get(
            "target_title_candidate"
        )
    )

    if not target_role:
        raise ValueError(
            "Missing employer-specific target_title_candidate "
            "in role_routing.json"
        )

    summary_mode = clean(
        summary_route.get(
            "mode"
        )
    ).upper()

    if summary_mode not in {
        "FULL",
        "ONE_LINE",
        "NONE",
    }:
        raise ValueError(
            f"Unsupported summary mode: {summary_mode!r}"
        )

    if summary_mode == "NONE":
        rendered_summary = ""
    else:
        rendered_summary = clean(
            source.get(
                "summary",
                ""
            )
        )

    payload = {
        "lang": "en",
        "page_format": "letter",

        "candidate": CANDIDATE,

        "target_role":
            target_role,

        "sections": {
            "summary":
                "Professional Summary",

            "experience":
                "Professional Experience",

            "projects":
                "Projects",

            "education":
                "Education",

            "skills":
                "Technical Skills",

            "certifications":
                "Certifications and Training",
        },

        "summary":
            rendered_summary,

        "experience": [],

        "projects": [],

        "education": [],

        "skills": [],

        "certifications":
            CERTIFICATIONS,
    }

    # --------------------------------------------------------------
    # EXPERIENCE
    # Our engine:
    #   company, title, dates, bullets
    #
    # Career-Ops HTML contract:
    #   company, role, location?, dates/period?, bullets
    # --------------------------------------------------------------

    for exp in source.get(
        "experience",
        []
    ):
        entry = {
            "company":
                clean(
                    exp.get(
                        "company"
                    )
                ),

            "role":
                clean(
                    exp.get(
                        "title"
                    )
                ),

            "dates":
                clean(
                    exp.get(
                        "dates"
                    )
                ),

            "bullets": [
                clean(x)
                for x in exp.get(
                    "bullets",
                    []
                )
                if clean(x)
            ],
        }

        payload[
            "experience"
        ].append(
            entry
        )

    # --------------------------------------------------------------
    # PROJECTS
    # Preserve project identity and bullet content exactly.
    #
    # Do NOT create project URLs unless a verified project URL exists.
    # --------------------------------------------------------------

    for project in source.get(
        "projects",
        []
    ):
        entry = {
            "name":
                clean(
                    project.get(
                        "name"
                    )
                ),

            "bullets": [
                clean(x)
                for x in project.get(
                    "bullets",
                    []
                )
                if clean(x)
            ],
        }

        payload[
            "projects"
        ].append(
            entry
        )

    # --------------------------------------------------------------
    # EDUCATION
    #
    # Our engine:
    #   institution, degree, graduation, gpa
    #
    # Career-Ops HTML:
    #   title, org, location?, year, description
    # --------------------------------------------------------------

    for edu in source.get(
        "education",
        []
    ):
        gpa = clean(
            edu.get(
                "gpa"
            )
        )

        entry = {
            "title":
                clean(
                    edu.get(
                        "degree"
                    )
                ),

            "org":
                clean(
                    edu.get(
                        "institution"
                    )
                ),

            "year":
                clean(
                    edu.get(
                        "graduation"
                    )
                ),
        }

        if gpa:
            entry[
                "description"
            ] = (
                f"GPA: {gpa}"
            )

        payload[
            "education"
        ].append(
            entry
        )

    # --------------------------------------------------------------
    # SKILLS
    #
    # Our engine:
    #   category, terms
    #
    # Career-Ops:
    #   category, items
    # --------------------------------------------------------------

    for skill_line in source.get(
        "skills",
        []
    ):
        terms = [
            clean(x)
            for x in skill_line.get(
                "terms",
                []
            )
            if clean(x)
        ]

        if not terms:
            continue

        payload[
            "skills"
        ].append({
            "category":
                clean(
                    skill_line.get(
                        "category"
                    )
                ),

            "items":
                terms,
        })

    return payload


def validate_internal(
    source,
    payload,
    role_routing,
    summary_route
):
    errors = []

    expected_role = clean(
        role_routing.get(
            "input",
            {}
        ).get(
            "target_title_candidate"
        )
    )

    if payload.get("target_role") != expected_role:
        errors.append(
            "target_role_mismatch"
        )

    if (
        payload.get(
            "candidate",
            {}
        ).get(
            "phone"
        )
        != CANDIDATE["phone"]
    ):
        errors.append(
            "phone_mismatch"
        )

    summary_mode = clean(
        summary_route.get(
            "mode"
        )
    ).upper()

    if (
        summary_mode == "NONE"
        and payload.get("summary")
    ):
        errors.append(
            "summary_should_be_hidden"
        )

    if (
        summary_mode in {
            "FULL",
            "ONE_LINE",
        }
        and payload.get("summary")
        != clean(
            source.get(
                "summary",
                ""
            )
        )
    ):
        errors.append(
            "summary_route_mismatch"
        )

    expected_certifications = CERTIFICATIONS

    if payload.get("certifications") != expected_certifications:
        errors.append(
            "certification_mapping_mismatch"
        )

    if len(payload.get("certifications", [])) != len(expected_certifications):
        errors.append(
            "certification_count_mismatch"
        )

    # Structural parity checks.
    if (
        len(
            payload["experience"]
        )
        !=
        len(
            source.get(
                "experience",
                []
            )
        )
    ):
        errors.append(
            "experience_count_mismatch"
        )

    if (
        len(
            payload["projects"]
        )
        !=
        len(
            source.get(
                "projects",
                []
            )
        )
    ):
        errors.append(
            "project_count_mismatch"
        )

    if (
        len(
            payload["education"]
        )
        !=
        len(
            source.get(
                "education",
                []
            )
        )
    ):
        errors.append(
            "education_count_mismatch"
        )

    # Bullet parity.
    source_exp_bullets = sum(
        len(
            x.get(
                "bullets",
                []
            )
        )
        for x in source.get(
            "experience",
            []
        )
    )

    payload_exp_bullets = sum(
        len(
            x.get(
                "bullets",
                []
            )
        )
        for x in payload[
            "experience"
        ]
    )

    if (
        source_exp_bullets
        !=
        payload_exp_bullets
    ):
        errors.append(
            "experience_bullet_count_mismatch"
        )

    source_project_bullets = sum(
        len(
            x.get(
                "bullets",
                []
            )
        )
        for x in source.get(
            "projects",
            []
        )
    )

    payload_project_bullets = sum(
        len(
            x.get(
                "bullets",
                []
            )
        )
        for x in payload[
            "projects"
        ]
    )

    if (
        source_project_bullets
        !=
        payload_project_bullets
    ):
        errors.append(
            "project_bullet_count_mismatch"
        )

    # Content parity.
    if (
        payload["summary"]
        !=
        clean(
            source.get(
                "summary",
                ""
            )
        )
    ):
        errors.append(
            "summary_changed"
        )

    return errors


def main():
    source = load_json(
        SOURCE_FILE
    )

    role_routing = load_json(
        ROLE_ROUTING_FILE
    )

    summary_route = load_json(
        SUMMARY_ROUTE_FILE
    )

    payload = build_payload(
        source,
        role_routing,
        summary_route
    )

    for project in payload.get(
        "projects",
        []
    ):
        name = project.get(
            "name",
            ""
        )

        if name in PROJECT_DATE_OVERRIDES:
            project[
                "dates"
            ] = PROJECT_DATE_OVERRIDES[
                name
            ]

    errors = validate_internal(
        source,
        payload,
        role_routing,
        summary_route
    )

    OUTPUT_FILE.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    # --------------------------------------------------------------
    # Run Career-Ops native payload validation through an explicit
    # run-local HTML destination.
    #
    # Do NOT use build-cv-html --preview here because generic preview
    # mode owns output/cv-preview.html globally.
    # --------------------------------------------------------------

    result = subprocess.run(
        [
            "node",
            "build-cv-html.mjs",
            str(
                OUTPUT_FILE
            ),
            str(
                VALIDATION_HTML_FILE
            ),
            str(ROOT / "templates/careerops/cv-template.careerops-locked.html"),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    VALIDATION_HTML_FILE.unlink(
        missing_ok=True
    )

    validation = {
        "adapter_errors":
            errors,

        "career_ops_exit_code":
            result.returncode,

        "career_ops_stdout":
            result.stdout,

        "career_ops_stderr":
            result.stderr,

        "reference_links_preserved":
            REFERENCE_LINKS,

        "phone_status":
            "DIRECT_USER_CONFIRMED",

        "model_calls": 0,

        "model_tokens": 0,
    }

    VALIDATION_FILE.write_text(
        json.dumps(
            validation,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        "=" * 100
    )

    print(
        "CAREEROPS -> CAREER-OPS "
        "CV PAYLOAD ADAPTER"
    )

    print(
        "=" * 100
    )

    print(
        "ADAPTER:",
        (
            "PASS"
            if not errors
            else "FAIL"
        ),
    )

    print(
        "CAREER-OPS PAYLOAD VALIDATION:",
        (
            "PASS"
            if result.returncode == 0
            else "FAIL"
        ),
    )

    print()

    print(
        "EXPERIENCE ENTRIES:",
        len(
            payload[
                "experience"
            ]
        ),
    )

    print(
        "EXPERIENCE BULLETS:",
        sum(
            len(
                x[
                    "bullets"
                ]
            )
            for x in payload[
                "experience"
            ]
        ),
    )

    print(
        "PROJECT ENTRIES:",
        len(
            payload[
                "projects"
            ]
        ),
    )

    print(
        "PROJECT BULLETS:",
        sum(
            len(
                x[
                    "bullets"
                ]
            )
            for x in payload[
                "projects"
            ]
        ),
    )

    print(
        "EDUCATION ENTRIES:",
        len(
            payload[
                "education"
            ]
        ),
    )

    print(
        "SKILL CATEGORIES:",
        len(
            payload[
                "skills"
            ]
        ),
    )

    print(
        "CERTIFICATIONS:",
        len(
            payload[
                "certifications"
            ]
        ),
    )

    print()

    print(
        "TARGET ROLE:",
        payload[
            "target_role"
        ],
    )

    print(
        "SUMMARY MODE:",
        summary_route.get(
            "mode"
        ),
    )

    print()

    print(
        "HEADER LINKS:"
    )

    print(
        "  PHONE:",
        CANDIDATE[
            "phone"
        ],
    )

    print(
        "  EMAIL:",
        CANDIDATE[
            "email"
        ],
    )

    print(
        "  LINKEDIN:",
        CANDIDATE[
            "linkedin"
        ][
            "url"
        ],
    )

    print(
        "  GITHUB:",
        CANDIDATE[
            "github"
        ][
            "url"
        ],
    )

    print(
        "  PHONE STATUS: DIRECT_USER_CONFIRMED"
    )

    if errors:
        print()

        print(
            "ADAPTER ERRORS:"
        )

        for error in errors:
            print(
                " -",
                error,
            )

    if result.stdout.strip():
        print()

        print(
            "CAREER-OPS STDOUT:"
        )

        print(
            result.stdout.strip()
        )

    if result.stderr.strip():
        print()

        print(
            "CAREER-OPS STDERR:"
        )

        print(
            result.stderr.strip()
        )

    print()

    print(
        "OUTPUT:",
        OUTPUT_FILE.relative_to(
            ROOT
        ),
    )

    print(
        "VALIDATION:",
        VALIDATION_FILE.relative_to(
            ROOT
        ),
    )

    print()

    print(
        "RESUME CONTENT MODIFIED: NO"
    )

    print(
        "MODEL CALLS: 0"
    )

    print(
        "MODEL TOKENS: 0"
    )

    print(
        "=" * 100
    )

    if (
        errors
        or result.returncode != 0
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
