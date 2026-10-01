from careerops_config import source_dir
#!/usr/bin/env python3

import csv
import json
import re
from collections import defaultdict
from pathlib import Path


from careerops_runtime import runtime_dir

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = runtime_dir(ROOT)

SEMANTIC_PATH = (
    RUNTIME / 'jd_semantic_map.json'
)

ENTITIES_PATH = (
    RUNTIME / 'candidate_entities.json'
)

INVENTORY_PATH = (
    source_dir(ROOT) / 'verified_evidence_inventory.md'
)

TOOL_MATRIX_PATH = (
    source_dir(ROOT) / 'tool_evidence_matrix.csv'
)

COVERAGE_PATH = (
    source_dir(ROOT) / 'assumed_market_coverage.json'
)

OUT = (
    RUNTIME / 'requirement_evidence_map.json'
)


ENTITY_HEADING = re.compile(
    r"^##\s+((?:EXP|PRJ)-\d{3})\s+-\s+(.+?)\s*$",
    re.M
)


IMPORTANT_SHORT_TERMS = {
    "sql",
    "etl",
    "elt",
    "bi",
    "qa",
    "r",
    "aws",
    "gcp"
}


def normalize(text):
    text = str(text).lower()

    replacements = {
        "&": " and ",
        "powerbi": "power bi",
        "postgres": "postgresql",
        "scikit learn": "scikit-learn"
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(
        r"[^a-z0-9+#./\- ]+",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def unique(items):
    seen = set()
    out = []

    for item in items:
        if item is None:
            continue

        value = str(item).strip()

        if not value:
            continue

        key = normalize(value)

        if key in seen:
            continue

        seen.add(key)
        out.append(value)

    return out


def phrase_present(term, text):
    term_norm = normalize(term)
    text_norm = normalize(text)

    if not term_norm:
        return False

    if (
        len(term_norm) < 3
        and term_norm not in IMPORTANT_SHORT_TERMS
    ):
        return False

    pattern = (
        r"(?<![a-z0-9])"
        + re.escape(term_norm)
        + r"(?![a-z0-9])"
    )

    return bool(
        re.search(
            pattern,
            text_norm,
            re.I
        )
    )


def parse_inventory_blocks(text):
    matches = list(
        ENTITY_HEADING.finditer(text)
    )

    blocks = {}

    for i, match in enumerate(matches):
        entity_id = match.group(1)

        start = match.start()

        end = (
            matches[i + 1].start()
            if i + 1 < len(matches)
            else len(text)
        )

        blocks[entity_id] = text[
            start:end
        ].strip()

    return blocks


def extract_claim_boundaries(block):
    pattern = re.compile(
        r"^###\s+Claim boundaries / integrity rules\s*$"
        r"(.*?)"
        r"(?=^###\s+|\Z)",
        re.M | re.S | re.I
    )

    match = pattern.search(block)

    if not match:
        return ""

    return match.group(1).strip()


def parse_tool_matrix(path):
    mapping = defaultdict(set)

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

            evidence_ids = [
                x.strip()
                for x in (
                    row.get("Evidence IDs")
                    or ""
                ).split(";")
                if x.strip()
            ]

            if not tool:
                continue

            mapping[
                normalize(tool)
            ].update(
                evidence_ids
            )

    return mapping


def nested_dedupe(terms):
    """
    Keep the more informative phrase when terms are nested.

    Example:
      data pipelines + pipelines
    becomes:
      data pipelines
    """

    terms = unique(terms)

    normalized = [
        (term, normalize(term))
        for term in terms
    ]

    result = []

    for term, norm_term in normalized:
        contained = False

        for other, norm_other in normalized:
            if term == other:
                continue

            if (
                norm_term != norm_other
                and norm_term in norm_other
                and len(norm_other) > len(norm_term)
            ):
                contained = True
                break

        if not contained:
            result.append(term)

    return result


def capability_relevant(capability, source_terms):
    cap = normalize(capability)

    if not cap:
        return False

    for term in source_terms:
        t = normalize(term)

        if not t:
            continue

        if cap == t:
            return True

        # Multiword containment is allowed only when the
        # shorter concept is still meaningful.
        if len(cap) >= 4 and cap in t:
            return True

        if len(t) >= 4 and t in cap:
            return True

    return False


def main():
    for path in [
        SEMANTIC_PATH,
        ENTITIES_PATH,
        INVENTORY_PATH,
        TOOL_MATRIX_PATH,
        COVERAGE_PATH
    ]:
        if not path.exists():
            raise SystemExit(
                f"Missing required source: {path}"
            )

    semantic = json.loads(
        SEMANTIC_PATH.read_text()
    )

    resolved = json.loads(
        ENTITIES_PATH.read_text()
    )

    coverage = json.loads(
        COVERAGE_PATH.read_text()
    )

    inventory_text = (
        INVENTORY_PATH.read_text(
            encoding="utf-8",
            errors="replace"
        )
    )

    blocks = parse_inventory_blocks(
        inventory_text
    )

    tool_matrix = parse_tool_matrix(
        TOOL_MATRIX_PATH
    )

    entities = {
        e["entity_id"]: e
        for e in resolved["entities"]
    }

    # Hard validation: mapping must use the resolved
    # canonical entities, not invent IDs.
    if set(blocks) != set(entities):
        raise SystemExit(
            "Evidence block IDs and resolved entity IDs differ."
        )

    routed_role = semantic[
        "routed_market_role"
    ]

    explicit_registry = [
        x for x in coverage[
            "explicit_skill_registry"
        ]
        if x.get(
            "allowed_for_market_matching",
            False
        )
    ]

    deep_registry = [
        x for x in coverage[
            "deep_capability_registry"
        ]
        if x.get(
            "allowed_for_market_matching",
            False
        )
    ]

    results = []

    verified_requirements = 0
    contextual_only_requirements = 0
    unmapped_requirements = 0

    for req in semantic["requirements"]:

        exact_layer = req["exact_layer"]
        semantic_layer = req[
            "semantic_layer"
        ]

        exact_terms = nested_dedupe(
            exact_layer[
                "tools_technologies"
            ]
            + exact_layer[
                "work_products"
            ]
            + exact_layer[
                "methods"
            ]
        )

        semantic_terms = unique(
            semantic_layer[
                "semantic_equivalents"
            ]
        )

        depth_terms = unique(
            semantic_layer[
                "technical_depth_terms"
            ]
        )

        concept_terms = unique(
            semantic_layer[
                "concepts"
            ]
        )

        entity_matches = {}

        def ensure_entity(entity_id):
            if entity_id not in entities:
                return None

            if entity_id not in entity_matches:
                entity = entities[
                    entity_id
                ]

                entity_matches[
                    entity_id
                ] = {
                    "entity_id": entity_id,
                    "canonical_name": entity[
                        "canonical_name"
                    ],
                    "entity_type": entity[
                        "entity_type"
                    ],
                    "organization": entity[
                        "organization"
                    ],
                    "ownership_status": entity[
                        "ownership_status"
                    ],
                    "evidence_status": entity[
                        "evidence_status"
                    ],
                    "merge_status": entity[
                        "resolution"
                    ][
                        "merge_status"
                    ],

                    "verified_exact_tool_matches": [],
                    "verified_exact_term_matches": [],
                    "verified_semantic_term_matches": [],
                    "verified_technical_depth_matches": [],

                    "role_affinity": (
                        routed_role
                        in entity.get(
                            "role_tags",
                            []
                        )
                    ),

                    "score": 0.0,

                    "claim_boundaries": (
                        extract_claim_boundaries(
                            blocks[entity_id]
                        )
                    )
                }

            return entity_matches[
                entity_id
            ]

        # --------------------------------------------------
        # 1. Exact tool -> verified evidence matrix
        # --------------------------------------------------

        for tool in exact_layer[
            "tools_technologies"
        ]:

            tool_key = normalize(tool)

            for entity_id in tool_matrix.get(
                tool_key,
                set()
            ):
                match = ensure_entity(
                    entity_id
                )

                if match is None:
                    continue

                match[
                    "verified_exact_tool_matches"
                ].append(tool)

        # --------------------------------------------------
        # 2. Literal exact JD terms -> evidence blocks
        # --------------------------------------------------

        for entity_id, original_block in blocks.items():
            from careerops_positive_evidence import positive_evidence, source_supported_method
            block = positive_evidence(original_block)

            exact_hits = [
                term
                for term in exact_terms
                if phrase_present(
                    term,
                    block
                )
            ]

            method_family_hits = [term for term in exact_terms if source_supported_method(term, block) and term not in exact_hits]

            semantic_hits = [
                term
                for term in semantic_terms
                if phrase_present(
                    term,
                    block
                )
            ]

            depth_hits = [
                term
                for term in depth_terms
                if phrase_present(
                    term,
                    block
                )
            ]

            if not (
                exact_hits
                or semantic_hits
                or method_family_hits
                or depth_hits
            ):
                continue

            match = ensure_entity(
                entity_id
            )

            match[
                "verified_exact_term_matches"
            ].extend(
                exact_hits
            )

            match[
                "verified_semantic_term_matches"
            ].extend(
                semantic_hits + method_family_hits
            )

            match[
                "verified_technical_depth_matches"
            ].extend(
                depth_hits
            )

        # --------------------------------------------------
        # 3. Score candidate evidence entities
        #
        # These scores rank candidate evidence for later
        # selection. They are NOT ATS scores and are NOT
        # final fit scores.
        # --------------------------------------------------

        ranked = []

        for match in entity_matches.values():

            match[
                "verified_exact_tool_matches"
            ] = unique(
                match[
                    "verified_exact_tool_matches"
                ]
            )

            match[
                "verified_exact_term_matches"
            ] = unique(
                match[
                    "verified_exact_term_matches"
                ]
            )

            match[
                "verified_semantic_term_matches"
            ] = unique(
                match[
                    "verified_semantic_term_matches"
                ]
            )

            match[
                "verified_technical_depth_matches"
            ] = unique(
                match[
                    "verified_technical_depth_matches"
                ]
            )

            score = (
                5.0
                * len(
                    match[
                        "verified_exact_tool_matches"
                    ]
                )
                + 3.0
                * len(
                    match[
                        "verified_exact_term_matches"
                    ]
                )
                + 1.5
                * len(
                    match[
                        "verified_semantic_term_matches"
                    ]
                )
                + 1.0
                * len(
                    match[
                        "verified_technical_depth_matches"
                    ]
                )
                + (
                    0.5
                    if match[
                        "role_affinity"
                    ]
                    else 0.0
                )
            )

            match["score"] = round(
                score,
                2
            )

            match["provenance"] = {
                "claim_class": (
                    "ARTIFACT_VERIFIED"
                ),
                "evidence_id": match[
                    "entity_id"
                ],
                "source": (
                    "verified_evidence_inventory"
                ),
                "tool_matrix_used": bool(
                    match[
                        "verified_exact_tool_matches"
                    ]
                )
            }

            from careerops_requirement_qualifiers import evidence_qualifiers
            match['qualification_support'] = evidence_qualifiers(
                req['exact_jd_quote'], positive_evidence(blocks.get(match['entity_id'], '')))
            match['requirement_coverage'] = (
                'PARTIAL' if match['qualification_support']['unsupported_qualifiers'] else 'SUPPORTED')
            ranked.append(match)

        ranked.sort(
            key=lambda x: (
                x["score"],
                len(
                    x[
                        "verified_exact_tool_matches"
                    ]
                ),
                len(
                    x[
                        "verified_exact_term_matches"
                    ]
                )
            ),
            reverse=True
        )

        # --------------------------------------------------
        # 4. Direct-user-confirmed capabilities
        #
        # V3 policy:
        # Actual skills confirmed by the user.
        # They may be used for matching and generation under
        # the V3 placement rules, but are NEVER silently
        # relabeled as artifact verified.
        # --------------------------------------------------

        contextual_source_terms = unique(
            exact_terms
            + semantic_terms
            + depth_terms
        )

        contextual = []

        for item in explicit_registry:

            if (
                routed_role
                not in item.get(
                    "roles",
                    []
                )
            ):
                continue

            term = item[
                "canonical_term"
            ]

            if not capability_relevant(
                term,
                contextual_source_terms
            ):
                continue

            contextual.append({
                "term": term,
                "type": "explicit_skill",
                "claim_class": (
                    "DIRECT_USER_CONFIRMED_CAPABILITY"
                ),
                "source_status": item.get(
                    "coverage_status"
                ),
                "artifact_verified_overlay": item.get(
                    "artifact_verified_overlay",
                    False
                ),
                "verified_evidence_ids": item.get(
                    "verified_evidence_ids",
                    []
                ),
                "may_be_relabelled_as_artifact_verified": False,
                "requires_generation_policy_checks": True
            })

        for item in deep_registry:

            if (
                routed_role
                not in item.get(
                    "roles",
                    []
                )
            ):
                continue

            term = item["term"]

            if not capability_relevant(
                term,
                contextual_source_terms
            ):
                continue

            contextual.append({
                "term": term,
                "type": "deep_capability",
                "claim_class": (
                    "DIRECT_USER_CONFIRMED_CAPABILITY"
                ),
                "source_status": item.get(
                    "coverage_status"
                ),
                "artifact_verified_overlay": False,
                "verified_evidence_ids": [],
                "may_be_relabelled_as_artifact_verified": False,
                "requires_generation_policy_checks": True
            })

        seen_contextual = set()
        contextual_deduped = []

        for item in contextual:
            key = (
                normalize(
                    item["term"]
                ),
                item["type"]
            )

            if key in seen_contextual:
                continue

            seen_contextual.add(key)
            contextual_deduped.append(
                item
            )

        # --------------------------------------------------
        # 5. Requirement coverage state
        #
        # IMPORTANT:
        # Evidence of a tool/method does NOT automatically
        # satisfy education or years-of-experience constraints.
        # Those require a separate candidate-fact validator.
        # --------------------------------------------------

        has_experience_constraint = bool(
            exact_layer["experience_years"]
        )

        has_education_constraint = bool(
            exact_layer["education"]
        )

        has_hard_factual_constraint = (
            has_experience_constraint
            or has_education_constraint
        )

        if ranked and has_hard_factual_constraint:
            coverage_state = (
                "EVIDENCE_MATCH_CONSTRAINT_VALIDATION_REQUIRED"
            )

        elif (
            contextual_deduped
            and has_hard_factual_constraint
        ):
            coverage_state = (
                "CONTEXTUAL_MATCH_CONSTRAINT_VALIDATION_REQUIRED"
            )

        elif has_hard_factual_constraint:
            coverage_state = (
                "CONSTRAINT_VALIDATION_REQUIRED"
            )

        elif ranked:
            coverage_state = (
                "VERIFIED_EVIDENCE_AVAILABLE"
            )

            verified_requirements += 1

        elif contextual_deduped:
            coverage_state = (
                "CONTEXTUAL_CAPABILITY_ONLY"
            )

            contextual_only_requirements += 1

        else:
            coverage_state = (
                "UNMAPPED"
            )

            unmapped_requirements += 1

        from careerops_requirement_qualifiers import qualifier_contract
        required_qualifiers = qualifier_contract(req['exact_jd_quote'])
        qualified_candidates = [x for x in ranked if x['requirement_coverage'] == 'SUPPORTED']
        if ranked and required_qualifiers and not qualified_candidates:
            coverage_state = 'QUALIFIER_UNVERIFIED'

        results.append({
            "mandatory_qualifiers": required_qualifiers,
            "qualification_coverage": 'QUALIFIER_UNVERIFIED' if required_qualifiers and not qualified_candidates else 'SUPPORTED',
            "requirement_id": req[
                "requirement_id"
            ],

            "priority": req[
                "priority"
            ],

            "exact_jd_quote": req[
                "exact_jd_quote"
            ],

            "coverage_state": coverage_state,

            "verified_evidence_candidates": (
                ranked[:10]
            ),

            "contextual_capability_candidates": (
                contextual_deduped
            ),

            "residual_gap": (
                coverage_state
                != "VERIFIED_EVIDENCE_AVAILABLE"
            ),

            "constraint_validation_required": (
                has_hard_factual_constraint
            ),

            "constraints": {
                "experience_years": exact_layer[
                    "experience_years"
                ],
                "education": exact_layer[
                    "education"
                ]
            }
        })

    output = {
        "schema_version": (
            "requirement-evidence-map-v1"
        ),

        "routed_role": routed_role,

        "policy": {
            "entity_resolution_precedes_mapping": True,
            "canonical_entities_may_not_be_auto_merged": True,
            "role_tags_are_affinity_not_proof": True,
            "tool_matrix_is_verified_tool_provenance": True,
            "semantic_match_requires_term_in_verified_evidence": True,
            "direct_user_confirmed_capability_is_not_artifact_verified": True,
            "candidate_selection_performed": False,
            "resume_generation_performed": False,
            "final_fit_scoring_performed": False
        },

        "summary": {
            "requirement_count": len(
                results
            ),
            "verified_evidence_available": (
                verified_requirements
            ),
            "contextual_capability_only": (
                contextual_only_requirements
            ),
            "unmapped": (
                unmapped_requirements
            )
        },

        "requirements": results
    }

    OUT.write_text(
        json.dumps(
            output,
            indent=2,
            ensure_ascii=False
        )
    )

    print("EVIDENCE MAPPING: CREATED")
    print("ROUTED ROLE:", routed_role)

    print(
        "REQUIREMENTS:",
        len(results)
    )

    print(
        "VERIFIED:",
        verified_requirements
    )

    print(
        "CONTEXTUAL ONLY:",
        contextual_only_requirements
    )

    print(
        "UNMAPPED:",
        unmapped_requirements
    )

    print("\nPER REQUIREMENT:")

    for req in results:

        print(
            f"\n{req['requirement_id']} "
            f"{req['priority']} | "
            f"{req['coverage_state']}"
        )

        candidates = req[
            "verified_evidence_candidates"
        ]

        if candidates:
            print("  VERIFIED CANDIDATES:")

            for candidate in candidates[:5]:
                print(
                    "   ",
                    candidate["entity_id"],
                    "|",
                    candidate["canonical_name"],
                    "| score=",
                    candidate["score"]
                )
        else:
            print(
                "  VERIFIED CANDIDATES: NONE"
            )

        contextual = req[
            "contextual_capability_candidates"
        ]

        if contextual:
            print(
                "  CONTEXTUAL:",
                ", ".join(
                    x["term"]
                    for x in contextual[:10]
                )
            )
        else:
            print(
                "  CONTEXTUAL: NONE"
            )

    print(
        "\nOUTPUT:",
        OUT.relative_to(ROOT)
    )


if __name__ == "__main__":
    from careerops_requirement_authority import run_guarded
    run_guarded(main, RUNTIME, "careerops_map_evidence.py")
