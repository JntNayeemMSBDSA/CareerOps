from careerops_config import source_dir
#!/usr/bin/env python3

import json
import os
import re
import shutil
from pathlib import Path

from careerops_runtime import runtime_dir


ROOT = Path(
    __file__
).resolve().parents[1]

RUNTIME = runtime_dir(
    ROOT
)

SOURCE_REQ_PATH = (
    RUNTIME
    / "jd_requirements.json"
)

EFFECTIVE_REQ_PATH = (
    RUNTIME
    / "jd_requirements_effective.json"
)

if EFFECTIVE_REQ_PATH.is_file():
    REQ_PATH = EFFECTIVE_REQ_PATH
elif (RUNTIME.parent / "manifest.json").is_file():
    raise SystemExit(
        "STOP: production effective requirement ledger is missing."
    )
else:
    REQ_PATH = SOURCE_REQ_PATH

RESUME_PATH = Path(
    os.environ.get(
        "CAREEROPS_RESUME_INPUT",
        str(
            RUNTIME
            / "generated_resume_content_pair_candidate.json"
        ),
    )
)

COVERAGE_PATH = (
    source_dir(ROOT) / 'assumed_market_coverage.json'
)

OVERRIDE_PATH = (
    source_dir(ROOT) / 'candidate_attestations.json'
)

REPORT_PATH = (
    RUNTIME
    / "resume_ats_term_repair.json"
)


def load(path):
    return json.loads(
        Path(path).read_text(
            encoding="utf-8"
        )
    )


def norm(value):
    text = str(
        value
        or ""
    ).lower()

    text = re.sub(
        r"[^a-z0-9+#./\- ]+",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def phrase_present(
    phrase,
    text,
):
    phrase_n = norm(
        phrase
    )

    text_n = norm(
        text
    )

    if not phrase_n:
        return False

    return (
        phrase_n
        in text_n
    )


def unique(values):
    result = []
    seen = set()

    for value in values:
        value = str(
            value
            or ""
        ).strip()

        key = norm(
            value
        )

        if (
            not key
            or key in seen
        ):
            continue

        seen.add(
            key
        )

        result.append(
            value
        )

    return result


def english_join(values):
    values = [
        str(x).strip()
        for x in values
        if str(x).strip()
    ]

    if len(values) == 1:
        return values[0]

    if len(values) == 2:
        return (
            values[0]
            + " and "
            + values[1]
        )

    return (
        ", ".join(
            values[:-1]
        )
        + ", and "
        + values[-1]
    )


def main():
    for path in [
        REQ_PATH,
        RESUME_PATH,
        COVERAGE_PATH,
        OVERRIDE_PATH,
    ]:
        if not path.exists():
            raise SystemExit(
                "Missing required source: "
                + str(path)
            )

    req = load(
        REQ_PATH
    )

    resume = load(
        RESUME_PATH
    )

    coverage = load(
        COVERAGE_PATH
    )

    overrides = load(
        OVERRIDE_PATH
    )

    override = (
        overrides
        .get(
            "capability_status_override",
            {},
        )
    )

    if not override.get(
        "all_assumed_market_coverage_capabilities_are_actual_user_skills",
        False,
    ):
        raise SystemExit(
            "STOP: direct-user capability authority is not active."
        )

    explicit_terms = {
        norm(
            row.get(
                "canonical_term"
            )
        )
        for row
        in coverage.get(
            "explicit_skill_registry",
            [],
        )
        if row.get(
            "canonical_term"
        )
    }

    skill_family_terms = {
        norm(
            row.get(
                "family"
            )
        )
        for row
        in coverage.get(
            "skill_family_registry",
            [],
        )
        if row.get(
            "family"
        )
    }

    deep_terms = {
        norm(
            row.get(
                "term"
            )
        )
        for row
        in coverage.get(
            "deep_capability_registry",
            [],
        )
        if row.get(
            "term"
        )
    }

    #
    # Direct-user authority explicitly applies to all three
    # assumed-market capability registries.
    authority_terms = (
        explicit_terms
        | skill_family_terms
        | deep_terms
    )

    current_text = json.dumps(
        resume,
        ensure_ascii=False,
    )

    missing = []

    for requirement in req.get(
        "requirements",
        [],
    ):
        if requirement.get(
            "priority"
        ) not in {
            "P0",
            "P1",
        }:
            continue

        for field in (
            "exact_tools_technologies",
            "exact_work_products",
            "exact_methods",
        ):
            for term in requirement.get(
                field,
                [],
            ):
                term = str(
                    term
                    or ""
                ).strip()

                if not term:
                    continue

                if phrase_present(
                    term,
                    current_text,
                ):
                    continue

                missing.append(
                    term
                )

    missing = unique(
        missing
    )

    if not missing:
        report = {
            "schema_version":
                "careerops-resume-ats-term-repair-v1",

            "status":
                "NO_CHANGE",

            "authorized_missing_terms":
                [],

            "unauthorized_missing_terms":
                [],

            "content_modified":
                False,

            "model_calls":
                0,
        }

        REPORT_PATH.write_text(
            json.dumps(
                report,
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        print(
            "ATS TERM REPAIR: NO CHANGE"
        )

        return

    authorized = []
    unauthorized = []

    for term in missing:
        key = norm(
            term
        )

        # Exact registry/deep-capability authority is preferred.
        if key in authority_terms:
            authorized.append(
                term
            )
            continue

        # Safe canonical containment for cases such as employer term
        # "visualization" and confirmed capability "Data visualization".
        if (
            len(key) >= 5
            and any(
                (
                    key in candidate
                    or candidate in key
                )
                for candidate
                in authority_terms
                if len(candidate) >= 5
            )
        ):
            authorized.append(
                term
            )
            continue

        unauthorized.append(
            term
        )

    if unauthorized:
        report = {
            "schema_version":
                "careerops-resume-ats-term-repair-v1",

            "status":
                "BLOCKED_UNAUTHORIZED_TERM",

            "authorized_missing_terms":
                authorized,

            "unauthorized_missing_terms":
                unauthorized,

            "content_modified":
                False,

            "model_calls":
                0,
        }

        REPORT_PATH.write_text(
            json.dumps(
                report,
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        raise SystemExit(
            "STOP: one or more missing P0/P1 ATS terms "
            "lack candidate capability authority: "
            + ", ".join(
                unauthorized
            )
        )

    if len(
        authorized
    ) > 4:
        raise SystemExit(
            "STOP: deterministic ATS repair would add more "
            "than four terms; manual semantic review required."
        )

    #
    # Capability-only exact JD terms belong on the Skills surface
    # whenever an appropriate existing category is available.
    #
    # Do not lengthen a concise professional summary merely to
    # satisfy deterministic exact-term coverage. This preserves
    # summary readability and prevents layout failures caused by
    # capability keyword appendages.
    summary = str(
        resume.get(
            "summary",
            "",
        )
    ).strip()

    before = summary

    skills = resume.get(
        "skills",
        [],
    )

    if not isinstance(
        skills,
        list,
    ):
        raise SystemExit(
            "STOP: resume skills surface is not a list."
        )

    def preferred_category(term):
        key = norm(
            term
        )

        if any(
            token in key
            for token in (
                "visual",
                "dashboard",
                "reporting",
                "report ",
            )
        ):
            return "BI & Reporting"

        if any(
            token in key
            for token in (
                "data model",
                "schema",
                "database",
                "warehouse",
                "etl",
                "pipeline",
            )
        ):
            return "Data Engineering & Platforms"

        return "Tools & Workflow"

    def display_term(term):
        term = str(
            term
        ).strip()

        if not term:
            return term

        return (
            term[0].upper()
            + term[1:]
        )

    placements = []

    for term in authorized:
        category_name = preferred_category(
            term
        )

        category = next(
            (
                row
                for row in skills
                if isinstance(
                    row,
                    dict,
                )
                and str(
                    row.get(
                        "category",
                        "",
                    )
                ).strip()
                == category_name
            ),
            None,
        )

        if category is None:
            category = next(
                (
                    row
                    for row in skills
                    if isinstance(
                        row,
                        dict,
                    )
                    and str(
                        row.get(
                            "category",
                            "",
                        )
                    ).strip()
                    == "Tools & Workflow"
                ),
                None,
            )

        if category is None:
            raise SystemExit(
                "STOP: no existing safe Skills category "
                "is available for ATS capability placement."
            )

        terms = category.setdefault(
            "terms",
            [],
        )

        existing = {
            norm(
                value
            )
            for value in terms
        }

        if norm(
            term
        ) not in existing:
            terms.append(
                display_term(
                    term
                )
            )

        placements.append(
            {
                "term":
                    term,

                "category":
                    category.get(
                        "category"
                    ),
            }
        )

    resume[
        "skills"
    ] = skills

    # Summary deliberately remains unchanged.
    summary = before

    backup = (
        RESUME_PATH.parent
        / (
            RESUME_PATH.stem
            + ".pre_ats_term_repair.json"
        )
    )

    if not backup.exists():
        shutil.copy2(
            RESUME_PATH,
            backup,
        )

    RESUME_PATH.write_text(
        json.dumps(
            resume,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    report = {
        "schema_version":
            "careerops-resume-ats-term-repair-v1",

        "status":
            "REPAIRED",

        "policy": {
            "p0_p1_only":
                True,

            "candidate_capability_authority_required":
                True,

            "historical_employer_attribution_added":
                False,

            "metrics_added":
                False,

            "outcomes_added":
                False,

            "model_calls":
                0,
        },

        "authorized_missing_terms":
            authorized,

        "unauthorized_missing_terms":
            [],

        "placement_surface":
            "skills",

        "skill_placements":
            placements,

        "summary_before":
            before,

        "summary_after":
            summary,

        "content_modified":
            True,

        "model_calls":
            0,
    }

    REPORT_PATH.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        "ATS TERM REPAIR: REPAIRED"
    )

    print(
        "AUTHORIZED TERMS:",
        ", ".join(
            authorized
        ),
    )

    print(
        "MODEL CALLS: 0"
    )


if __name__ == "__main__":
    main()
