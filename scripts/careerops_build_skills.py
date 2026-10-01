from careerops_config import source_dir
#!/usr/bin/env python3

import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from careerops_requirement_regeneration import canonical_ledger_path


from careerops_runtime import runtime_dir
from careerops_effective_runtime import ensure_effective_runtime

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = runtime_dir(ROOT)

SEMANTIC_PATH = RUNTIME / 'jd_semantic_map.json'
REQ_PATH = canonical_ledger_path(RUNTIME)
EXP_PATH = RUNTIME / 'experience_selection.json'
PROJECT_PATH = RUNTIME / 'project_selection.json'
ROUTE_PATH = RUNTIME / 'role_routing.json'

COVERAGE_PATH = source_dir(ROOT) / 'assumed_market_coverage.json'
TOOL_MATRIX_PATH = source_dir(ROOT) / 'tool_evidence_matrix.csv'
FACTS_PATH = source_dir(ROOT) / 'candidate_facts.json'
OVERRIDE_PATH = source_dir(ROOT) / 'candidate_attestations.json'

OUT = RUNTIME / 'technical_skills_plan.json'


CATEGORY_ORDER = [
    "Programming & Querying",
    "BI & Reporting",
    "Data Engineering & Platforms",
    "ML & Statistical Modeling",
    "Tools & Workflow"
]


CATEGORY_LIMITS = {
    "Programming & Querying": 8,
    "BI & Reporting": 9,
    "Data Engineering & Platforms": 10,
    "ML & Statistical Modeling": 9,
    "Tools & Workflow": 7
}


# Used only to break equal-score ties for visible resume space.
# It does NOT change whether the user possesses a skill.
DISPLAY_PRIORITY = {
    "sql": 100,
    "python": 99,
    "power bi": 98,
    "excel": 97,
    "excel / google sheets": 97,
    "tableau": 96,
    "pandas": 95,
    "numpy": 94,
    "pyarrow": 93,
    "scipy": 92,
    "scikit-learn": 91,
    "scikit learn": 91,
    "t-sql": 90,
    "sql / t-sql": 90,
    "duckdb sql": 89,
    "postgresql": 88,
    "r": 87,
    "power query": 86,
    "dax": 85,
    "snowflake": 84,
    "databricks": 83,
    "sql server": 82,
    "docker": 81,
    "aws": 80,
    "aws s3": 80,
    "azure": 79,
    "redshift": 78,
    "etl": 77,
    "etl / elt": 77,
    "etl/elt": 77,
    "data pipelines": 76,
    "parquet": 75,
    "dbt": 74,
    "git": 73,
    "github": 72,
    "jupyter": 71,
    "jira": 70,
    "agile": 69,
    "scrum": 69,
    "agile/scrum": 69,
    "agile / scrum": 69,
    "git": 73,
    "github": 72,
    "confluence": 68,
    "statistics": 67,
    "machine learning": 67,
    "a/b testing": 66,
    "bert": 65
}


# Valid skills, but too implementation-specific / secondary to
# consume one-page resume space unless the JD explicitly asks for them.
SUPPRESS_FROM_VISIBLE_BY_DEFAULT = {
    "sqlite",
    "tableau hyper/twb/twbx"
}


def norm(text):
    text = str(text).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9+#./\- ]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def unique(items):
    seen = set()
    out = []

    for item in items:
        item = str(item).strip()

        if not item:
            continue

        key = norm(item)

        if key in seen:
            continue

        seen.add(key)
        out.append(item)

    return out


def parse_tool_matrix(path):
    by_entity = defaultdict(list)

    with path.open(
        newline="",
        encoding="utf-8-sig",
        errors="replace"
    ) as f:
        reader = csv.DictReader(f)

        for row in reader:
            tool = (
                row.get("Tool / Technology")
                or ""
            ).strip()

            ids = [
                x.strip()
                for x in (
                    row.get("Evidence IDs")
                    or ""
                ).split(";")
                if x.strip()
            ]

            for entity_id in ids:
                by_entity[entity_id].append(tool)

    return {
        k: unique(v)
        for k, v in by_entity.items()
    }


def category_for(term, registry_category=None):
    from careerops_skills_stack import category_for as classify
    return classify(term, registry_category or "")


def main():

    for path in [
        SEMANTIC_PATH,
        REQ_PATH,
        EXP_PATH,
        PROJECT_PATH,
        ROUTE_PATH,
        COVERAGE_PATH,
        TOOL_MATRIX_PATH,
        FACTS_PATH,
        OVERRIDE_PATH
    ]:
        if not path.exists():
            raise SystemExit(
                f"Missing required source: {path}"
            )

    semantic = json.loads(
        SEMANTIC_PATH.read_text()
    )

    requirements_ledger = ensure_effective_runtime(
        RUNTIME
    )["effective_ledger"]

    experience = json.loads(
        EXP_PATH.read_text()
    )

    projects = json.loads(
        PROJECT_PATH.read_text()
    )

    routing = json.loads(
        ROUTE_PATH.read_text()
    )

    coverage = json.loads(
        COVERAGE_PATH.read_text()
    )

    facts = json.loads(
        FACTS_PATH.read_text()
    )

    overrides = json.loads(
        OVERRIDE_PATH.read_text()
    )

    capability_override = overrides.get(
        "capability_status_override",
        {}
    )

    if not capability_override.get(
        "all_assumed_market_coverage_capabilities_are_actual_user_skills",
        False
    ):
        raise SystemExit(
            "Direct-user-confirmed capability override is not active."
        )

    tools_by_entity = parse_tool_matrix(
        TOOL_MATRIX_PATH
    )

    routed_role = semantic[
        "routed_market_role"
    ]

    #
    # Keep Skills aligned with semantic expansion and project selection:
    # a LOW-confidence market-role guess must not contribute market-prior
    # vocabulary to the visible resume. Exact JD terms, verified evidence,
    # and direct-user-confirmed capabilities remain fully eligible.
    market_primary = routing[
        "market_route"
    ]["primary"]

    route_confidence = (
        market_primary.get(
            "confidence",
            "LOW"
        )
        or "LOW"
    ).upper()

    market_prior_enabled = (
        route_confidence
        in {"HIGH", "MEDIUM"}
    )

    role_profile = next(
        x
        for x in coverage[
            "role_coverage_profiles"
        ]
        if x["role"] == routed_role
    )

    explicit_registry = {
        norm(x["canonical_term"]): x
        for x in coverage[
            "explicit_skill_registry"
        ]
    }

    # Global verified-tool authority.
    #
    # Selection determines which experiences/projects appear on this
    # resume. It must not erase a real candidate capability from the
    # Skills section when that capability is verified elsewhere in the
    # existing evidence matrix and is explicitly requested by the JD.
    global_verified_tool_keys = {
        norm(tool)
        for entity_tools in tools_by_entity.values()
        for tool in entity_tools
        if tool
    }

    selected_entity_ids = set()

    for block in experience[
        "selected_experience_blocks"
    ]:
        selected_entity_ids.update(
            block["evidence_ids"]
        )

    for project in projects[
        "selected_projects"
    ]:
        selected_entity_ids.add(
            project["entity_id"]
        )

    evidence_tools = unique(
        tool
        for entity_id in selected_entity_ids
        for tool in tools_by_entity.get(
            entity_id,
            []
        )
    )

    exact_jd_tools = unique(
        tool
        for req in semantic[
            "requirements"
        ]
        for tool in req[
            "exact_layer"
        ][
            "tools_technologies"
        ]
    )

    semantic_terms = unique(
        semantic[
            "aggregate"
        ][
            "semantic_equivalents"
        ]
    )

    #
    # Preserve exact employer terminology from high-priority
    # requirements during presentation-only semantic cleanup.
    #
    # This does NOT force every P0/P1 term into Technical Skills.
    # It only prevents an already-eligible visible term from being
    # removed as redundant when the employer explicitly used it.
    protected_exact_p0_p1_terms = unique(
        term
        for req in requirements_ledger.get(
            "requirements",
            []
        )
        if req.get("priority") in {"P0", "P1"}
        for field in (
            "exact_tools_technologies",
            "exact_work_products",
            "exact_methods",
        )
        for term in req.get(field, [])
        if term
    )

    protected_exact_p0_p1_keys = {
        norm(term)
        for term in protected_exact_p0_p1_terms
    }

    role_skills = (
        role_profile.get(
            "explicit_market_skills",
            []
        )
        if market_prior_enabled
        else []
    )

    scores = defaultdict(float)
    provenance = defaultdict(list)
    display = {}

    def add(term, points, source):
        key = norm(term)

        if not key:
            return

        display.setdefault(
            key,
            term
        )

        scores[key] += points

        if source not in provenance[key]:
            provenance[key].append(
                source
            )

    # Exact employer terminology dominates.
    for term in exact_jd_tools:
        add(
            term,
            100,
            "EXACT_JD_TOOL"
        )

    # Verified selected experiences/projects.
    for term in evidence_tools:
        add(
            term,
            45,
            "SELECTED_VERIFIED_EVIDENCE"
        )

    # Routed-role prior.
    for term in role_skills:
        add(
            term,
            30,
            "ROUTED_ROLE_MARKET_PRIOR"
        )

    # --------------------------------------------------
    # Global confirmed workflow capabilities
    #
    # The user has explicitly confirmed that capabilities
    # in the assumed-market registry are actual skills.
    # These do not need to appear in the current JD to be
    # eligible for the compact Tools & Workflow line.
    # We only add them when they actually exist in the
    # confirmed capability registry.
    # --------------------------------------------------

    workflow_alias_groups = [
        ["Jira"],
        ["Agile"],
        ["Scrum"],
        ["Agile/Scrum", "Agile / Scrum"],
        ["Git"],
        ["GitHub"],
        ["Confluence"]
    ]

    added_workflow_keys = set()

    for aliases in workflow_alias_groups:
        for alias in aliases:
            key = norm(alias)

            if key not in explicit_registry:
                continue

            canonical = explicit_registry[
                key
            ]["canonical_term"]

            canonical_key = norm(
                canonical
            )

            if canonical_key in added_workflow_keys:
                break

            add(
                canonical,
                24,
                "DIRECT_USER_CONFIRMED_GLOBAL_CAPABILITY"
            )

            added_workflow_keys.add(
                canonical_key
            )

            break

    # Semantic JD concepts only if they correspond to an
    # actual user-confirmed explicit capability.
    for term in semantic_terms:
        key = norm(term)

        if key in explicit_registry:
            add(
                explicit_registry[
                    key
                ][
                    "canonical_term"
                ],
                25,
                "JD_SEMANTIC_CONFIRMED_CAPABILITY"
            )

    # Official direct-user proficiency gets reinforcement.
    proficiency = facts.get(
        "core_proficiency",
        {}
    )

    PROF_POINTS = {
        "expert": 15,
        "advanced": 12,
        "intermediate to advanced": 9,
        "intermediate": 6
    }

    for skill, level in proficiency.items():
        add(
            skill,
            PROF_POINTS.get(
                norm(level),
                4
            ),
            "DIRECT_USER_CONFIRMED_PROFICIENCY"
        )

    # Keep only actual confirmed capabilities / evidence tools.
    candidates = []

    for key, score in scores.items():

        term = display[key]

        registry = explicit_registry.get(
            key
        )

        evidence_backed = any(
            p == "SELECTED_VERIFIED_EVIDENCE"
            for p in provenance[key]
        )

        globally_verified_tool = (
            key in global_verified_tool_keys
        )

        direct_fact = any(
            p == "DIRECT_USER_CONFIRMED_PROFICIENCY"
            for p in provenance[key]
        )

        inventory_confirmed = (
            registry is not None
        )

        if not (
            evidence_backed
            or globally_verified_tool
            or direct_fact
            or inventory_confirmed
        ):
            continue

        # Record the actual authority used to admit this capability. A JD
        # match is a request, while registry confirmation is candidate fact.
        if inventory_confirmed and 'DIRECT_USER_CONFIRMED_CAPABILITY_REGISTRY' not in provenance[key]:
            provenance[key].append('DIRECT_USER_CONFIRMED_CAPABILITY_REGISTRY')
        if globally_verified_tool and 'GLOBAL_VERIFIED_EVIDENCE' not in provenance[key]:
            provenance[key].append('GLOBAL_VERIFIED_EVIDENCE')

        category = category_for(
            term,
            (
                registry.get(
                    "category"
                )
                if registry
                else None
            )
        )

        if category is None:
            continue

        # Presentation classification only.
        if norm(term) == "microsoft office":
            category = "Tools & Workflow"

        candidates.append({
            "term": term,
            "score": round(
                score,
                2
            ),
            "category": category,
            "provenance": provenance[
                key
            ],
            "claim_class": (
                "ARTIFACT_VERIFIED"
                if (
                    evidence_backed
                    or globally_verified_tool
                )
                else "DIRECT_USER_CONFIRMED_CAPABILITY"
            ),
            "authority_partition": 'HISTORICAL_EVIDENCE_WITH_OWNER' if evidence_backed or globally_verified_tool else 'DIRECT_CONFIRMED_CURRENT_CAPABILITY',
            "historical_evidence_owner_ids": sorted(entity_id for entity_id, tools in tools_by_entity.items() if key in {norm(x) for x in tools}),
            "current_capability_confirmed": bool(direct_fact or inventory_confirmed),
            "historical_placement_requires_owner": True,
            "proficiency": proficiency.get(
                term
            )
        })

    exact_jd_keys = {
        norm(x)
        for x in exact_jd_tools
    }

    candidates = [
        x for x in candidates
        if (
            norm(x["term"])
            not in SUPPRESS_FROM_VISIBLE_BY_DEFAULT
            or norm(x["term"]) in exact_jd_keys
        )
    ]

    from careerops_skills_stack import curate_stack
    stack = curate_stack(coverage, candidates, requirements_ledger, semantic,
                         role_profile, market_prior_enabled=market_prior_enabled)
    visible_lines = stack["visible_skill_lines"]
    candidates = stack["ranked_skill_candidates"]
    semantic_redundancy_removed = stack["selection_decisions"]
    if stack["audit"]["gate"] != "PASS":
        raise SystemExit("SKILLS_STACK_PLAN_FAIL: " + json.dumps(stack["audit"]["findings"]))

    output = {
        "schema_version": (
            "technical-skills-plan-v1"
        ),

        "routed_role": routed_role,

        "policy": {
            "skills_built_after_experience_and_project_selection": True,
            "exact_jd_terms_prioritized": True,
            "direct_user_confirmed_capabilities_are_actual_skills": True,
            "artifact_not_required_for_skill_possession": True,
            "historical_placement_still_requires_support": True,
            "no_keyword_dumping": True,
            "deep_capability_terms_eligible_for_visible_skills": True
        },

        "exact_jd_tools": exact_jd_tools,

        "protected_exact_p0_p1_terms":
            protected_exact_p0_p1_terms,

        "selected_evidence_tools": evidence_tools,

        "visible_skill_lines": visible_lines,
        "skills_stack_contract": stack,

        "semantic_redundancy_removed": semantic_redundancy_removed,

        "authority_partitions": {
            "historical_by_entity": tools_by_entity,
            "direct_confirmed_current_capabilities": [x['term'] for x in candidates if x['current_capability_confirmed']],
            "jd_requests_without_candidate_authority": [x for x in exact_jd_tools if norm(x) not in {norm(c['term']) for c in candidates}],
            "market_only_advisory": [x for x in role_skills if norm(x) not in {norm(c['term']) for c in candidates}],
            "historical_backfill_from_current_capability_forbidden": True,
        },
        "ranked_skill_candidates": candidates
    }

    OUT.write_text(
        json.dumps(
            output,
            indent=2,
            ensure_ascii=False
        )
        + "\n"
    )

    print(
        "TECHNICAL SKILLS PLAN: CREATED"
    )

    print(
        "ROUTED ROLE:",
        routed_role
    )

    print(
        "EXACT JD TOOLS:",
        ", ".join(
            exact_jd_tools
        )
        or "NONE"
    )

    print("\nVISIBLE SKILL LINES:")

    for line in visible_lines:
        print(
            f"- {line['category']}: "
            + ", ".join(
                line["terms"]
            )
        )

    print(
        "\nOUTPUT:",
        OUT.relative_to(ROOT)
    )


if __name__ == "__main__":
    from careerops_requirement_authority import run_guarded
    run_guarded(main, RUNTIME, "careerops_build_skills.py")
