from careerops_config import source_dir
#!/usr/bin/env python3

import csv
import json
import re
from pathlib import Path
from careerops_requirement_regeneration import canonical_ledger_path


from careerops_runtime import runtime_dir

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = runtime_dir(ROOT)

MAP_PATH = RUNTIME / 'requirement_evidence_map.json'
EXP_PATH = RUNTIME / 'experience_selection.json'
ENTITIES_PATH = RUNTIME / 'candidate_entities.json'
ROUTE_PATH = RUNTIME / 'role_routing.json'

INDEX_PATH = source_dir(ROOT) / 'verified_evidence_index.csv'
INVENTORY_PATH = source_dir(ROOT) / 'verified_evidence_inventory.md'
TOOL_MATRIX_PATH = source_dir(ROOT) / 'tool_evidence_matrix.csv'
COVERAGE_PATH = source_dir(ROOT) / 'assumed_market_coverage.json'
OVERRIDE_PATH = source_dir(ROOT) / 'candidate_attestations.json'

OUT = RUNTIME / 'project_selection.json'


PRIORITY_WEIGHT = {
    "P0": 5.0,
    "P1": 4.0,
    "P2": 2.0,
    "P3": 1.0
}


ENTITY_HEADING = re.compile(
    r"^##\s+((?:EXP|PRJ)-\d{3})\s+-\s+(.+?)\s*$",
    re.M
)


def norm(x):
    x = str(x).lower()
    x = re.sub(r"[^a-z0-9+#./\- ]+", " ", x)
    x = re.sub(r"\s+", " ", x)
    return x.strip()


def unique(items):
    seen = set()
    out = []

    for item in items:
        if item is None:
            continue

        item = str(item).strip()

        if not item:
            continue

        key = norm(item)

        if key in seen:
            continue

        seen.add(key)
        out.append(item)

    return out


def parse_blocks(text):
    matches = list(
        ENTITY_HEADING.finditer(text)
    )

    blocks = {}

    for i, m in enumerate(matches):
        start = m.start()

        end = (
            matches[i + 1].start()
            if i + 1 < len(matches)
            else len(text)
        )

        blocks[m.group(1)] = text[
            start:end
        ].strip()

    return blocks


def section_text(block, names):
    for name in names:
        pattern = re.compile(
            rf"^###\s+{re.escape(name)}\s*$"
            r"(.*?)"
            r"(?=^###\s+|\Z)",
            re.M | re.S | re.I
        )

        m = pattern.search(block)

        if m:
            return m.group(1).strip()

    return ""


def bullet_count(text):
    return sum(
        1
        for line in text.splitlines()
        if re.match(
            r"^\s*[-*]\s+",
            line
        )
    )


def numeric_bullet_count(text):
    return sum(
        1
        for line in text.splitlines()
        if (
            re.match(
                r"^\s*[-*]\s+",
                line
            )
            and re.search(
                r"\d",
                line
            )
        )
    )


def parse_index(path):
    rows = {}

    with path.open(
        newline="",
        encoding="utf-8-sig",
        errors="replace"
    ) as f:
        reader = csv.DictReader(f)

        for row in reader:
            rows[
                row["ID"].strip()
            ] = row

    return rows


def parse_tool_matrix(path):
    project_tools = {}

    with path.open(
        newline="",
        encoding="utf-8-sig",
        errors="replace"
    ) as f:
        reader = csv.DictReader(f)

        for row in reader:
            tool = (
                row.get(
                    "Tool / Technology"
                )
                or ""
            ).strip()

            ids = [
                x.strip()
                for x in (
                    row.get(
                        "Evidence IDs"
                    )
                    or ""
                ).split(";")
                if x.strip()
            ]

            for entity_id in ids:
                project_tools.setdefault(
                    entity_id,
                    []
                ).append(
                    tool
                )

    return {
        k: unique(v)
        for k, v in project_tools.items()
    }


def candidate_terms(candidate):
    return unique(
        candidate.get(
            "verified_exact_tool_matches",
            []
        )
        + candidate.get(
            "verified_exact_term_matches",
            []
        )
        + candidate.get(
            "verified_semantic_term_matches",
            []
        )
        + candidate.get(
            "verified_technical_depth_matches",
            []
        )
    )


def evidence_quality_score(status):
    s = norm(status)

    if s == "strong":
        return 8.0

    if "strong_with" in s:
        return 8.0

    if "strong" in s:
        return 7.0

    if "moderate" in s:
        return 4.0

    return 2.0


def main():

    required = [
        MAP_PATH,
        EXP_PATH,
        ENTITIES_PATH,
        ROUTE_PATH,
        INDEX_PATH,
        INVENTORY_PATH,
        TOOL_MATRIX_PATH,
        COVERAGE_PATH,
        OVERRIDE_PATH
    ]

    for path in required:
        if not path.exists():
            raise SystemExit(
                f"Missing required source: {path}"
            )

    evidence_map = json.loads(
        MAP_PATH.read_text()
    )

    experience = json.loads(
        EXP_PATH.read_text()
    )

    entity_payload = json.loads(
        ENTITIES_PATH.read_text()
    )

    routing = json.loads(
        ROUTE_PATH.read_text()
    )

    coverage = json.loads(
        COVERAGE_PATH.read_text()
    )

    overrides = json.loads(
        OVERRIDE_PATH.read_text()
    )

    if not overrides.get(
        "project_ownership",
        {}
    ).get(
        "all_projects_owned_by_user",
        False
    ):
        raise SystemExit(
            "Project ownership override is not active."
        )

    inventory_text = INVENTORY_PATH.read_text(
        encoding="utf-8",
        errors="replace"
    )

    blocks = parse_blocks(
        inventory_text
    )

    index = parse_index(
        INDEX_PATH
    )

    tools_by_entity = parse_tool_matrix(
        TOOL_MATRIX_PATH
    )

    entities = {
        e["entity_id"]: e
        for e in entity_payload[
            "entities"
        ]
    }

    market_primary = routing[
        "market_route"
    ]["primary"]

    routed_role = market_primary[
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

    role_profile = next(
        (
            x
            for x in coverage[
                "role_coverage_profiles"
            ]
            if x["role"] == routed_role
        ),
        None
    )

    if role_profile is None:
        raise SystemExit(
            f"No market role profile: {routed_role}"
        )

    role_market_terms = {
        norm(x)
        for x in role_profile.get(
            "explicit_market_skills",
            []
        )
    }

    for section in role_profile.get(
        "deep_capability_sections",
        []
    ):
        role_market_terms.update(
            norm(x)
            for x in section.get(
                "items",
                []
            )
        )

    selected_exp_ids = {
        evidence_id
        for block in experience[
            "selected_experience_blocks"
        ]
        for evidence_id in block[
            "evidence_ids"
        ]
    }

    residual_targets = set(
        experience[
            "residual_gaps"
        ][
            "project_fill_target_ids"
        ]
    )

    experience_terms = set()

    for req in evidence_map[
        "requirements"
    ]:
        for candidate in req[
            "verified_evidence_candidates"
        ]:
            if (
                candidate[
                    "entity_id"
                ]
                in selected_exp_ids
            ):
                experience_terms.update(
                    norm(x)
                    for x in candidate_terms(
                        candidate
                    )
                )

    # Only PRJ entities are eligible for Selected Projects.
    project_ids = sorted(
        entity_id
        for entity_id in entities
        if entity_id.startswith(
            "PRJ-"
        )
    )

    scored = []

    for project_id in project_ids:

        entity = entities[
            project_id
        ]

        block = blocks.get(
            project_id,
            ""
        )

        index_row = index.get(
            project_id,
            {}
        )

        # ==================================================
        # 1. JD FIT
        # ==================================================

        jd_raw = 0.0
        supported = []
        supported_p0_p1 = []
        exact_terms = []
        semantic_terms = []
        depth_terms = []

        for req in evidence_map[
            "requirements"
        ]:

            candidate = next(
                (
                    x
                    for x in req[
                        "verified_evidence_candidates"
                    ]
                    if x[
                        "entity_id"
                    ] == project_id
                ),
                None
            )

            if candidate is None or candidate.get('requirement_coverage', 'SUPPORTED') != 'SUPPORTED':
                continue

            req_id = req[
                "requirement_id"
            ]

            weight = PRIORITY_WEIGHT.get(
                req["priority"],
                1.0
            )

            # Residual gaps dominate when present.
            if req_id in residual_targets:
                weight *= 2.5

            # Cap individual evidence contribution so one
            # lexical match cannot dominate the entire score.
            evidence_component = min(
                candidate[
                    "score"
                ],
                10.0
            )

            jd_raw += (
                evidence_component
                * weight
            )

            supported.append(
                req_id
            )

            if req[
                "priority"
            ] in {
                "P0",
                "P1"
            }:
                supported_p0_p1.append(
                    req_id
                )

            exact_terms.extend(
                candidate.get(
                    "verified_exact_tool_matches",
                    []
                )
            )

            exact_terms.extend(
                candidate.get(
                    "verified_exact_term_matches",
                    []
                )
            )

            semantic_terms.extend(
                candidate.get(
                    "verified_semantic_term_matches",
                    []
                )
            )

            depth_terms.extend(
                candidate.get(
                    "verified_technical_depth_matches",
                    []
                )
            )

        # Normalize JD fit to max 40 points.
        jd_fit_score = min(
            jd_raw / 4.0,
            40.0
        )

        # ==================================================
        # 2. ROLE RELEVANCE
        # ==================================================

        role_tags = [
            x.strip()
            for x in (
                index_row.get(
                    "Role Tags"
                )
                or ""
            ).split(";")
            if x.strip()
        ]

        role_affinity = (
            market_prior_enabled
            and routed_role
            in role_tags
        )

        role_score = (
            10.0
            if role_affinity
            else 0.0
        )

        # ==================================================
        # 3. VERIFIED TECHNICAL BREADTH
        # ==================================================

        verified_tools = tools_by_entity.get(
            project_id,
            []
        )

        technical_breadth_score = min(
            len(
                verified_tools
            ) * 1.5,
            12.0
        )

        # ==================================================
        # 4. MARKET-ROLE TECHNICAL ALIGNMENT
        # ==================================================

        market_overlap = [
            tool
            for tool in verified_tools
            if (
                market_prior_enabled
                and norm(tool)
                in role_market_terms
            )
        ]

        market_score = min(
            len(
                market_overlap
            ) * 2.0,
            10.0
        )

        # ==================================================
        # 5. VERIFIED SCALE / METRICS
        # ==================================================

        scale_text = "\n".join(
            x
            for x in [
                section_text(
                    block,
                    [
                        "Data and scale",
                        "Validated rebuild scale",
                        "Scale",
                        "Selected metrics",
                        "Results",
                        "Data And Outcomes"
                    ]
                )
            ]
            if x
        )

        metric_count = numeric_bullet_count(
            scale_text
        )

        scale_score = min(
            metric_count * 1.5,
            10.0
        )

        # ==================================================
        # 6. METHOD / TECHNICAL DEPTH
        # ==================================================

        methods_text = section_text(
            block,
            [
                "Methods",
                "Technical methods",
                "Statistical methods",
                "Architecture"
            ]
        )

        method_count = bullet_count(
            methods_text
        )

        method_score = min(
            method_count * 1.0,
            10.0
        )

        # ==================================================
        # 7. EVIDENCE QUALITY
        # ==================================================

        evidence_quality = evidence_quality_score(
            index_row.get(
                "Evidence Status",
                ""
            )
        )

        # ==================================================
        # 8. COMPLEMENTARITY VS EXPERIENCE
        # ==================================================

        all_project_terms = unique(
            verified_tools
            + exact_terms
            + semantic_terms
            + depth_terms
        )

        novel_terms = [
            x
            for x in all_project_terms
            if norm(x)
            not in experience_terms
        ]

        complementarity_score = min(
            len(
                novel_terms
            ) * 1.0,
            8.0
        )

        total = round(
            jd_fit_score
            + role_score
            + technical_breadth_score
            + market_score
            + scale_score
            + method_score
            + evidence_quality
            + complementarity_score,
            2
        )

        scored.append({
            "entity_id": project_id,
            "canonical_name": entity[
                "canonical_name"
            ],

            "candidate_facing_ownership": (
                "USER_OWNED"
            ),

            "visible_group_project_label_allowed": False,

            "score": total,

            "components": {
                "jd_fit": round(
                    jd_fit_score,
                    2
                ),
                "role_relevance": round(
                    role_score,
                    2
                ),
                "technical_breadth": round(
                    technical_breadth_score,
                    2
                ),
                "market_role_alignment": round(
                    market_score,
                    2
                ),
                "scale_metrics": round(
                    scale_score,
                    2
                ),
                "method_depth": round(
                    method_score,
                    2
                ),
                "evidence_quality": round(
                    evidence_quality,
                    2
                ),
                "complementarity": round(
                    complementarity_score,
                    2
                )
            },

            "supported_requirement_ids": (
                unique(
                    supported
                )
            ),

            "supported_p0_p1_ids": (
                unique(
                    supported_p0_p1
                )
            ),

            "role_tags": role_tags,

            "verified_tools": (
                verified_tools
            ),

            "market_overlap_tools": (
                market_overlap
            ),

            "verified_metric_count": (
                metric_count
            ),

            "method_bullet_count": (
                method_count
            ),

            "novel_terms_vs_experience": (
                novel_terms
            )
        })

    ranked = sorted(
        scored,
        key=lambda x: (
            x["score"],
            len(
                x[
                    "supported_p0_p1_ids"
                ]
            ),
            x[
                "verified_metric_count"
            ],
            x[
                "method_bullet_count"
            ]
        ),
        reverse=True
    )

    #
    # Evidence identity and candidate-facing display identity are
    # intentionally separate. Never merge evidence entities merely
    # to preserve a valuable organization/brand reference.
    project_display_overrides = overrides.get(
        "project_display_overrides",
        {}
    )

    provenance_suffixes = [
        r"\s*-\s*Independent Reconstruction\s*$",
        r"\s*-\s*Reconstruction\s*$",
        r"\s*-\s*Rebuild\s*$",
        r"\s*\(Reconstruction\)\s*$",
        r"\s*\(Rebuild\)\s*$",
    ]

    for row in ranked:
        visible_name = row["canonical_name"]

        for pattern in provenance_suffixes:
            visible_name = re.sub(
                pattern,
                "",
                visible_name,
                flags=re.I,
            )

        visible_name = visible_name.strip()

        display_rule = project_display_overrides.get(
            row["entity_id"],
            {}
        )

        row["visible_name"] = (
            display_rule.get("visible_name")
            or visible_name
        )

        if display_rule.get("brand_context"):
            row["brand_context"] = (
                display_rule["brand_context"]
            )

        if display_rule.get("must_preserve_entities"):
            row["must_preserve_entities"] = list(
                display_rule["must_preserve_entities"]
            )

        if display_rule.get("relationship_boundary"):
            row["relationship_boundary"] = (
                display_rule["relationship_boundary"]
            )

    # Ranking annotations are grounded in canonical source work and verified entity text.
    from careerops_requirement_qualifiers import qualifier_contract,qualifier_supported
    canonical={x['requirement_id']:x for x in json.loads((canonical_ledger_path(RUNTIME)).read_text())['requirements']}
    for row in ranked:
        supported=[canonical[x] for x in row['supported_requirement_ids'] if x in canonical]
        entity_text=str(blocks.get(row['entity_id'],''))
        products=set(x for source in supported if source['priority']=='P1' for x in source.get('exact_work_products',[]))
        output_hits=[x for x in products if re.search(r'(?<![a-z0-9])'+re.escape(x)+r'(?:s)?(?![a-z0-9])',entity_text,re.I)]
        domains=[q for source in supported if source['priority'] in {'P0','P1'} for q in qualifier_contract(source['exact_quote']) if qualifier_supported(q,entity_text)]
        row['components'].update(principal_output_similarity=len(output_hits),responsibility_similarity=sum(x['priority']=='P1' for x in supported),business_domain_similarity=len(domains),method_tool_similarity=row['components']['method_depth'])
        row['principal_output_hits']=sorted(output_hits)
    from careerops_residual_set_cover import select_projects
    priorities = {x['requirement_id']:x['priority'] for x in evidence_map['requirements']}
    selected, selection_objective = select_projects(ranked, residual_targets, priorities, limit=2)

    mode = (
        "GAP_FILL"
        if residual_targets
        else "REINFORCEMENT_ONLY"
    )

    output = {
        "schema_version": (
            "project-selection-v3"
        ),

        "selection_mode": mode,
        "selection_objective": selection_objective,

        "routed_role": routed_role,

        "policy": {
            "experience_selected_first": True,
            "residual_gaps_dominate_when_present": True,
            "no_fake_gap_creation": True,
            "jd_fit_is_not_only_selection_factor": True,
            "verified_scale_and_metrics_count": True,
            "technical_depth_counts": True,
            "role_relevance_counts": True,
            "market_role_alignment_counts": True,
            "human_screen_value_counts": True,
            "technical_complementarity_counts": True,
            "all_projects_owned_by_user": True,
            "group_project_label_forbidden": True,
            "projects_do_not_become_employment": True,
            "max_projects": 2
        },

        "selected_projects": (
            selected
        ),

        "ranked_project_candidates": (
            ranked
        )
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
        "PROJECT SELECTION V3: CREATED"
    )

    print(
        "MODE:",
        mode
    )

    print(
        "ROUTED ROLE:",
        routed_role
    )

    print("\nTOP 8:")

    for i, row in enumerate(
        ranked[:8],
        start=1
    ):
        c = row[
            "components"
        ]

        print(
            f"{i}. {row['entity_id']} | "
            f"{row['score']} | "
            f"{row['canonical_name']}"
        )

        print(
            "   JD=",
            c["jd_fit"],
            "| ROLE=",
            c["role_relevance"],
            "| TECH=",
            c["technical_breadth"],
            "| MARKET=",
            c["market_role_alignment"],
            "| SCALE=",
            c["scale_metrics"],
            "| METHODS=",
            c["method_depth"],
            "| EVIDENCE=",
            c["evidence_quality"],
            "| NOVEL=",
            c["complementarity"]
        )

    print("\nSELECTED:")

    for row in selected:
        print(
            "-",
            row["entity_id"],
            "|",
            row["canonical_name"],
            "|",
            row["score"]
        )

    print(
        "\nOUTPUT:",
        OUT.relative_to(ROOT)
    )


if __name__ == "__main__":
    from careerops_requirement_authority import run_guarded
    run_guarded(main, RUNTIME, "careerops_select_projects.py")
