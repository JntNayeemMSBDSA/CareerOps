from careerops_config import source_dir
#!/usr/bin/env python3

import json
import hashlib
import re
from pathlib import Path
from careerops_requirement_regeneration import canonical_ledger_path


from careerops_runtime import runtime_dir
from careerops_effective_runtime import ensure_effective_runtime

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = runtime_dir(ROOT)

REQ_PATH = canonical_ledger_path(RUNTIME)
ROUTE_PATH = RUNTIME / 'role_routing.json'
COVERAGE_PATH = source_dir(ROOT) / 'assumed_market_coverage.json'

OUT = RUNTIME / 'jd_semantic_map.json'


SEMANTIC_RULES = [
    {"concept":"relational_databases","patterns":[r"\b(?:relational )?databases?\b"],"semantic_equivalents":["SQL Server","DuckDB","relational model","SQL joins"],"technical_depth_terms":["reconciliation queries","database integrity","relational modeling"]},
    {"concept":"data_quality","patterns":[r"\b(?:clean|validate|maintain)\b.{0,100}\bdata\b",r"\bdata quality\b"],"semantic_equivalents":["data validation","reconciliation","QA queries","integrity checks"],"technical_depth_terms":["grain validation","checksum validation","join checks"]},
    {"concept":"business_function_support","patterns":[r"\bbusiness functions?\b",r"\bbusiness (?:support|insights?)\b"],"semantic_equivalents":["capacity planning","operations","cost variance","sales","business development"],"technical_depth_terms":["Power BI dashboards","contribution-margin analysis","operational model"]},

    {
        "concept": "sql_querying",
        "patterns": [
            r"\bsql\b",
            r"(?<!power )\bquery\b",
            r"(?<!power )\bqueries\b"
        ],
        "semantic_equivalents": [
            "relational querying",
            "data extraction",
            "data retrieval"
        ],
        "technical_depth_terms": [
            "joins",
            "CTEs",
            "window functions",
            "aggregation",
            "subqueries",
            "query optimization"
        ]
    },
    {
        "concept": "data_pipelines",
        "patterns": [
            r"\bdata pipelines?\b",
            r"\bpipelines?\b",
            r"\betl\b",
            r"\belt\b"
        ],
        "semantic_equivalents": [
            "ETL",
            "ELT",
            "data integration",
            "data ingestion",
            "data transformation"
        ],
        "technical_depth_terms": [
            "pipeline orchestration",
            "data validation",
            "reconciliation",
            "refresh workflows"
        ]
    },
    {
        "concept": "business_intelligence",
        "patterns": [
            r"\bpower bi\b",
            r"\bbusiness intelligence\b",
            r"\bbi\b"
        ],
        "semantic_equivalents": [
            "business intelligence",
            "BI reporting",
            "analytics reporting"
        ],
        "technical_depth_terms": [
            "semantic modeling",
            "metrics/KPIs",
            "refresh/QA"
        ]
    },
    {
        "concept": "dashboarding",
        "patterns": [
            r"\bdashboards?\b",
            r"\bdashboarding\b"
        ],
        "semantic_equivalents": [
            "dashboarding",
            "data visualization",
            "BI visualization",
            "visual reporting"
        ],
        "technical_depth_terms": [
            "metrics/KPIs",
            "semantic modeling",
            "refresh/QA"
        ]
    },
    {
        "concept": "data_analysis",
        "patterns": [
            r"\banaly[sz]e\b",
            r"\banalysis\b",
            r"\banalytics\b"
        ],
        "semantic_equivalents": [
            "data analysis",
            "analytical reporting",
            "decision support"
        ],
        "technical_depth_terms": [
            "trend analysis",
            "descriptive analysis",
            "diagnostic analysis"
        ]
    },
    {
        "concept": "business_performance",
        "patterns": [
            r"\bbusiness performance\b",
            r"\bperformance\b",
            r"\bkpis?\b",
            r"\bmetrics?\b"
        ],
        "semantic_equivalents": [
            "performance analysis",
            "KPI analysis",
            "metric analysis",
            "business performance reporting"
        ],
        "technical_depth_terms": [
            "variance analysis",
            "trend analysis",
            "metrics/KPIs"
        ]
    },
    {
        "concept": "stakeholder_communication",
        "patterns": [
            r"\bstakeholders?\b",
            r"\bcommunicat",
            r"\bpresent",
            r"\btranslate.*business"
        ],
        "semantic_equivalents": [
            "stakeholder communication",
            "insight communication",
            "business translation"
        ],
        "technical_depth_terms": [
            "decision support",
            "business interpretation"
        ]
    },
    {
        "concept": "reporting",
        "patterns": [
            r"\breports?\b",
            r"\breporting\b"
        ],
        "semantic_equivalents": [
            "reporting",
            "business reporting",
            "analytics reporting"
        ],
        "technical_depth_terms": [
            "metric ownership",
            "report QA",
            "refresh workflows"
        ]
    },
    {
        "concept": "data_quality",
        "patterns": [
            r"\bdata quality\b",
            r"\bdata validation\b",
            r"\bdata accuracy\b",
            r"\bdata consistency\b",
            r"\bdata integrity\b",
            r"\bvalidation\b",
            r"\breconciliation\b"
        ],
        "semantic_equivalents": [
            "data quality",
            "data validation",
            "data integrity"
        ],
        "technical_depth_terms": [
            "reconciliation",
            "deduplication",
            "quality assurance"
        ]
    },
    {
        "concept": "python",
        "patterns": [
            r"\bpython\b"
        ],
        "semantic_equivalents": [
            "Python programming",
            "programmatic analysis"
        ],
        "technical_depth_terms": []
    }
]


def norm(text):
    text = str(text).lower()
    text = re.sub(r"[^a-z0-9+#./ ]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def unique(seq):
    seen = set()
    out = []

    for item in seq:
        key = norm(item)

        if not key or key in seen:
            continue

        seen.add(key)
        out.append(item)

    return out


def matched_rules(text):
    results = []

    for rule in SEMANTIC_RULES:
        if any(
            re.search(pattern, text, re.I)
            for pattern in rule["patterns"]
        ):
            results.append(rule)

    return results


def find_role_profile(coverage, role_name):
    for profile in coverage["role_coverage_profiles"]:
        if profile["role"].lower() == role_name.lower():
            return profile

    return None


def flatten_deep_profile(profile):
    rows = []

    for section in profile.get("deep_capability_sections", []):
        section_name = section["section"]

        for item in section.get("items", []):
            rows.append({
                "section": section_name,
                "term": item
            })

    return rows


def term_relevant(term, semantic_terms, exact_text):
    term_norm = norm(term)

    if not term_norm:
        return False

    exact_norm = norm(exact_text)

    # Direct occurrence must respect token boundaries.
    #
    # This prevents short terms such as "R" from matching arbitrary
    # letters inside words such as "research" or "reporting".
    direct_pattern = (
        r"(?<!\w)"
        + re.escape(term_norm)
        + r"(?!\w)"
    )

    if re.search(direct_pattern, exact_norm, re.I):
        return True

    term_tokens = set(term_norm.split())

    semantic_tokens = set()

    for s in semantic_terms:
        semantic_tokens.update(
            norm(s).split()
        )

    # Require meaningful lexical relation.
    meaningful = {
        x for x in term_tokens
        if len(x) >= 3
    }

    if meaningful & semantic_tokens:
        return True

    return False


def requirements_fingerprint(reqs):
    """
    Must exactly match the fingerprint written by the role router.
    """
    payload = {
        "target_role_title_candidate": reqs.get(
            "target_role_title_candidate"
        ),
        "requirements": [
            {
                "requirement_id": r.get("requirement_id"),
                "priority": r.get("priority"),
                "exact_quote": r.get("exact_quote"),
            }
            for r in reqs.get("requirements", [])
        ],
    }

    canonical = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def main():
    for path in [
        REQ_PATH,
        ROUTE_PATH,
        COVERAGE_PATH
    ]:
        if not path.exists():
            raise SystemExit(
                f"Missing required source: {path}"
            )

    requirements = ensure_effective_runtime(
        RUNTIME
    )["effective_ledger"]

    routing = json.loads(
        ROUTE_PATH.read_text()
    )

    coverage = json.loads(
        COVERAGE_PATH.read_text()
    )

    current_fingerprint = requirements_fingerprint(
        requirements
    )

    routed_fingerprint = (
        routing.get("input", {})
        .get("requirements_fingerprint")
    )

    if not routed_fingerprint:
        raise SystemExit(
            "FAIL CLOSED: role_routing.json has no current-job "
            "requirements fingerprint. Run careerops_route_role.py "
            "for the CURRENT job before semantic expansion."
        )

    if routed_fingerprint != current_fingerprint:
        raise SystemExit(
            "FAIL CLOSED: role_routing.json belongs to a different "
            "requirement ledger. Run careerops_route_role.py for the "
            "CURRENT job before semantic expansion."
        )

    market_primary = routing[
        "market_route"
    ]["primary"]

    primary_role = market_primary[
        "role"
    ]

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

    role_profile = find_role_profile(
        coverage,
        primary_role
    )

    if role_profile is None:
        raise SystemExit(
            f"No coverage profile for routed role: {primary_role}"
        )

    role_explicit_skills = (
        role_profile.get(
            "explicit_market_skills",
            []
        )
        if market_prior_enabled
        else []
    )

    role_deep = (
        flatten_deep_profile(
            role_profile
        )
        if market_prior_enabled
        else []
    )

    expanded_requirements = []

    aggregate_exact = []
    aggregate_semantic = []
    aggregate_depth = []
    aggregate_market = []

    for req in requirements["requirements"]:
        quote = req["exact_quote"]

        rules = matched_rules(
            quote
        )

        semantic_terms = []
        depth_terms = []
        concept_labels = []

        for rule in rules:
            concept_labels.append(
                rule["concept"]
            )

            semantic_terms.extend(
                rule["semantic_equivalents"]
            )

            depth_terms.extend(
                rule["technical_depth_terms"]
            )

        semantic_terms = unique(
            semantic_terms
        )

        depth_terms = unique(
            depth_terms
        )

        exact_terms = unique(
            req.get(
                "exact_tools_technologies",
                []
            )
            + req.get(
                "exact_work_products",
                []
            )
            + req.get(
                "exact_methods",
                []
            )
        )

        market_skills = [
            skill
            for skill in role_explicit_skills
            if term_relevant(
                skill,
                semantic_terms + exact_terms,
                quote
            )
        ]

        market_deep_terms = []

        for row in role_deep:
            if term_relevant(
                row["term"],
                (
                    semantic_terms
                    + depth_terms
                    + exact_terms
                ),
                quote
            ):
                market_deep_terms.append({
                    "term": row["term"],
                    "section": row["section"],
                    "source": (
                        f"role_profile:"
                        f"{primary_role}:"
                        f"{row['section']}"
                    )
                })

        market_skills = unique(
            market_skills
        )

        # Prevent exact terms from being duplicated as
        # semantic or market-only terms.
        exact_norms = {
            norm(x)
            for x in exact_terms
        }

        semantic_terms = [
            x for x in semantic_terms
            if norm(x) not in exact_norms
        ]

        market_skills = [
            x for x in market_skills
            if norm(x) not in exact_norms
        ]

        expanded = {
            "requirement_id": req[
                "requirement_id"
            ],

            "priority": req[
                "priority"
            ],

            "exact_jd_quote": quote,

            "exact_layer": {
                "tools_technologies": req.get(
                    "exact_tools_technologies",
                    []
                ),
                "work_products": req.get(
                    "exact_work_products",
                    []
                ),
                "methods": req.get(
                    "exact_methods",
                    []
                ),
                "experience_years": req.get(
                    "experience_years_phrases",
                    []
                ),
                "education": req.get(
                    "education_phrases",
                    []
                )
            },

            "semantic_layer": {
                "concepts": unique(
                    concept_labels
                ),
                "semantic_equivalents": semantic_terms,
                "technical_depth_terms": depth_terms,
                "provenance": (
                    "DETERMINISTIC_JD_SEMANTIC_RULE"
                )
            },

            "market_prior_layer": {
                "canonical_role": primary_role,
                "related_explicit_market_skills": market_skills,
                "related_deep_capabilities": market_deep_terms,
                "coverage_status": (
                    "ASSUMED_MARKET_COVERAGE"
                ),
                "may_change_requirement_priority": False,
                "may_be_treated_as_exact_jd_term": False,
                "may_be_treated_as_candidate_fact": False
            }
        }

        expanded_requirements.append(
            expanded
        )

        aggregate_exact.extend(
            exact_terms
        )

        aggregate_semantic.extend(
            semantic_terms
        )

        aggregate_depth.extend(
            depth_terms
        )

        aggregate_market.extend(
            market_skills
        )

    output = {
        "schema_version": "jd-semantic-map-v1",

        "target_role": requirements.get(
            "target_role_title_candidate"
        ),

        "routed_market_role": primary_role,

        "requirements_fingerprint": current_fingerprint,

        "routing_provenance": {
            "requirements_fingerprint":
                routed_fingerprint,
            "current_job_match": True
        },

        "policy": {
            "exact_jd_terms_preserved": True,
            "semantic_terms_do_not_replace_exact_terms": True,
            "market_prior_does_not_override_jd": True,
            "market_prior_cannot_create_p0_or_p1": True,
            "candidate_evidence_used": False,
            "assumed_market_coverage_is_not_verified_evidence": True,
            "resume_claims_generated": False
        },

        "requirements": expanded_requirements,

        "aggregate": {
            "exact_terms": unique(
                aggregate_exact
            ),
            "semantic_equivalents": unique(
                aggregate_semantic
            ),
            "technical_depth_terms": unique(
                aggregate_depth
            ),
            "related_market_prior_terms": unique(
                aggregate_market
            )
        }
    }

    OUT.write_text(
        json.dumps(
            output,
            indent=2,
            ensure_ascii=False
        )
    )

    # Semantic expansion occurs AFTER role routing.
    # Update route metadata only after the semantic map is safely written.
    routing.setdefault(
        "policy",
        {}
    )["semantic_expansion_performed"] = True

    routing["policy"][
        "semantic_expansion_used_for_routing"
    ] = False

    routing["semantic_expansion"] = {
        "status": "COMPLETED_POST_ROUTE",
        "requirements_fingerprint":
            current_fingerprint,
        "semantic_map":
            "data/careerops-engine/runtime/jd_semantic_map.json"
    }

    ROUTE_PATH.write_text(
        json.dumps(
            routing,
            indent=2,
            ensure_ascii=False
        )
    )

    print("JD SEMANTIC MAP: CREATED")
    print("ROUTED ROLE:", primary_role)
    print(
        "REQUIREMENTS:",
        len(expanded_requirements)
    )

    print("\nPER REQUIREMENT:")

    for r in expanded_requirements:
        print(
            f"\n{r['requirement_id']} "
            f"{r['priority']}"
        )

        print(
            "  EXACT:",
            ", ".join(
                unique(
                    r["exact_layer"][
                        "tools_technologies"
                    ]
                    + r["exact_layer"][
                        "work_products"
                    ]
                    + r["exact_layer"][
                        "methods"
                    ]
                )
            ) or "NONE"
        )

        print(
            "  CONCEPTS:",
            ", ".join(
                r["semantic_layer"][
                    "concepts"
                ]
            ) or "NONE"
        )

        print(
            "  SEMANTIC:",
            ", ".join(
                r["semantic_layer"][
                    "semantic_equivalents"
                ]
            ) or "NONE"
        )

        print(
            "  TECH DEPTH:",
            ", ".join(
                r["semantic_layer"][
                    "technical_depth_terms"
                ]
            ) or "NONE"
        )

        print(
            "  MARKET PRIOR:",
            ", ".join(
                r["market_prior_layer"][
                    "related_explicit_market_skills"
                ]
            ) or "NONE"
        )

    print(
        "\nOUTPUT:",
        OUT.relative_to(ROOT)
    )


if __name__ == "__main__":
    from careerops_requirement_authority import run_guarded
    run_guarded(main, RUNTIME, "careerops_expand_jd_semantics.py")
