from careerops_config import source_dir
#!/usr/bin/env python3

import json
import hashlib
import math
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from careerops_requirement_regeneration import canonical_ledger_path


from careerops_runtime import runtime_dir
from careerops_effective_runtime import ensure_effective_runtime

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = runtime_dir(ROOT)

MARKET = source_dir(ROOT) / 'market_research_50_roles.md'
APPLICATION = source_dir(ROOT) / 'application_role_universe_top50.json'
REQ = canonical_ledger_path(RUNTIME)
OUT = RUNTIME / 'role_routing.json'


STOPWORDS = {
    "a", "an", "and", "or", "the", "of", "for", "to", "with",
    "in", "on", "at", "by", "from", "into", "through", "using",
    "used", "where", "when", "as", "plus", "role"
}

LEVEL_WORDS = {
    "junior", "jr", "senior", "sr", "lead", "principal",
    "associate", "staff", "level", "i", "ii", "iii", "iv"
}

TITLE_GENERIC = {
    "data",
    "analyst",
    "analytics",
    "business",
    "intelligence",
    "developer",
    "scientist",
    "reporting"
}

ALIASES = {
    "bi": ["business", "intelligence"],
    "powerbi": ["power", "bi"],
    "visualisation": ["visualization"],
    "modelling": ["modeling"],
    "dashboards": ["dashboard"],
    "pipelines": ["pipeline"],
    "reports": ["reporting"],
    "kpis": ["kpi"]
}


def tokenize(text, remove_levels=False):
    text = str(text).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[/_|,+()\-]+", " ", text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)

    result = []

    for token in text.split():
        if token in STOPWORDS:
            continue

        if remove_levels and token in LEVEL_WORDS:
            continue

        expanded = ALIASES.get(token, [token])

        for item in expanded:
            if item not in STOPWORDS:
                result.append(item)

    return result


def normalized(text, remove_levels=False):
    return " ".join(tokenize(text, remove_levels=remove_levels))


def title_similarity(a, b):
    a_norm = normalized(a, remove_levels=True)
    b_norm = normalized(b, remove_levels=True)

    if not a_norm or not b_norm:
        return 0.0

    if a_norm == b_norm:
        return 1.0

    a_set = set(a_norm.split())
    b_set = set(b_norm.split())

    inter = len(a_set & b_set)
    union = len(a_set | b_set)

    jaccard = inter / union if union else 0.0

    containment = max(
        inter / len(a_set) if a_set else 0.0,
        inter / len(b_set) if b_set else 0.0
    )

    sequence = SequenceMatcher(
        None,
        a_norm,
        b_norm
    ).ratio()

    return min(
        1.0,
        0.45 * jaccard
        + 0.30 * containment
        + 0.25 * sequence
    )


def parse_market_roles(text):
    pattern = re.compile(
        r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|",
        re.M
    )

    roles = {}

    for match in pattern.finditer(text):
        number = int(match.group(1))

        if number < 1:
            continue

        roles[number] = {
            "role_number": number,
            "role": match.group(2).strip(),
            "technical_center": match.group(3).strip()
        }

    return [
        roles[n]
        for n in sorted(roles)
    ]


def build_idf(market_roles):
    """
    Common terms such as SQL/Data receive less routing power.
    Rare role-defining terms receive more routing power.
    """
    docs = [
        set(tokenize(r["technical_center"]))
        for r in market_roles
    ]

    df = Counter()

    for doc in docs:
        for token in doc:
            df[token] += 1

    n = len(docs)

    return {
        token: math.log((n + 1) / (count + 1)) + 1
        for token, count in df.items()
    }


def weighted_center_match(jd_text, center, idf):
    jd_tokens = set(tokenize(jd_text))
    center_tokens = set(tokenize(center))

    if not center_tokens:
        return 0.0, []

    denominator = sum(
        idf.get(t, 1.0)
        for t in center_tokens
    )

    matched = sorted(
        jd_tokens & center_tokens
    )

    numerator = sum(
        idf.get(t, 1.0)
        for t in matched
    )

    score = (
        numerator / denominator
        if denominator
        else 0.0
    )

    return score, matched


def specialization_terms(role_name):
    """
    Dynamically derive role-defining title terms.

    Examples:
      Sustainability Data Analyst -> sustainability
      Healthcare Data Analyst     -> healthcare
      Marketing Data Analyst      -> marketing
      Supply Chain Analyst        -> supply, chain
      Data Analyst                -> no specialization
    """
    raw = tokenize(
        role_name,
        remove_levels=True
    )

    return [
        token
        for token in raw
        if token not in TITLE_GENERIC
    ]


def specialization_guard(role_name, evidence_text):
    terms = specialization_terms(role_name)

    if not terms:
        return 0.0, [], []

    evidence_tokens = set(
        tokenize(evidence_text)
    )

    matched = [
        term
        for term in terms
        if term in evidence_tokens
    ]

    missing = [
        term
        for term in terms
        if term not in evidence_tokens
    ]

    coverage = len(matched) / len(terms)

    # Maximum penalty = 25 routing points.
    penalty = 0.25 * (1.0 - coverage)

    return penalty, matched, missing


def application_route(target_title, app_roles):
    scored = []

    for row in app_roles:
        score = title_similarity(
            target_title,
            row["search_title"]
        )

        scored.append({
            "rank": row["rank"],
            "search_title": row["search_title"],
            "title_match_score": round(
                score * 100,
                2
            )
        })

    scored.sort(
        key=lambda x: (
            x["title_match_score"],
            -x["rank"]
        ),
        reverse=True
    )

    return scored


def joined_requirements(reqs, priorities=None):
    parts = []

    for r in reqs["requirements"]:
        if (
            priorities is not None
            and r["priority"] not in priorities
        ):
            continue

        parts.append(r["exact_quote"])

        parts.extend(
            r.get(
                "exact_tools_technologies",
                []
            )
        )

        parts.extend(
            r.get(
                "exact_work_products",
                []
            )
        )

        parts.extend(
            r.get(
                "exact_methods",
                []
            )
        )

    return " ".join(parts)


def requirements_fingerprint(reqs):
    """
    Deterministic identity for the CURRENT requirement ledger.

    Prevents downstream stages from consuming role routing produced
    for a different job in the shared runtime workspace.
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
    for path in [MARKET, APPLICATION, REQ]:
        if not path.exists():
            raise SystemExit(
                f"Missing required source: {path}"
            )

    market_text = MARKET.read_text(
        encoding="utf-8",
        errors="replace"
    )

    market_roles = parse_market_roles(
        market_text
    )

    app_payload = json.loads(APPLICATION.read_text())
    app_roles = app_payload["roles"]
    expected = app_payload.get("role_count")
    if not isinstance(expected, int) or expected < 1:
        raise SystemExit("Configured role count must be a positive integer")
    if len(market_roles) != expected or len(app_roles) != expected:
        raise SystemExit("Configured market/application role counts do not match")
    if len({row["search_title"] for row in app_roles}) != len(app_roles):
        raise SystemExit("Duplicate configured application roles")

    req = ensure_effective_runtime(
        RUNTIME
    )["effective_ledger"]

    target_title = (
        req.get(
            "target_role_title_candidate"
        )
        or ""
    )

    req_fingerprint = requirements_fingerprint(
        req
    )

    # P1 = actual core work.
    responsibility_text = joined_requirements(
        req,
        {"P1"}
    )

    # All requirements remain employer-specific evidence.
    all_requirement_text = joined_requirements(
        req
    )

    app_results = application_route(
        target_title,
        app_roles
    )

    best_app = app_results[0]

    idf = build_idf(
        market_roles
    )

    # Specialization can be supported by title OR actual JD.
    specialization_evidence_text = " ".join([
        target_title,
        best_app["search_title"],
        all_requirement_text
    ])

    market_results = []

    for role in market_roles:
        target_title_score = title_similarity(
            target_title,
            role["role"]
        )

        app_title_score = title_similarity(
            best_app["search_title"],
            role["role"]
        )

        responsibility_score, responsibility_hits = (
            weighted_center_match(
                responsibility_text,
                role["technical_center"],
                idf
            )
        )

        all_req_score, all_req_hits = (
            weighted_center_match(
                all_requirement_text,
                role["technical_center"],
                idf
            )
        )

        (
            specialization_penalty,
            specialization_hits,
            specialization_missing
        ) = specialization_guard(
            role["role"],
            specialization_evidence_text
        )

        # JD content is the majority of the score.
        raw_score = (
            0.20 * target_title_score
            + 0.15 * app_title_score
            + 0.45 * responsibility_score
            + 0.20 * all_req_score
        )

        final_score = max(
            0.0,
            raw_score - specialization_penalty
        )

        market_results.append({
            "role_number": role[
                "role_number"
            ],
            "role": role["role"],
            "technical_center": role[
                "technical_center"
            ],

            "target_title_score": round(
                target_title_score * 100,
                2
            ),

            "application_title_score": round(
                app_title_score * 100,
                2
            ),

            "responsibility_score": round(
                responsibility_score * 100,
                2
            ),

            "all_requirement_score": round(
                all_req_score * 100,
                2
            ),

            "specialization_penalty": round(
                specialization_penalty * 100,
                2
            ),

            "specialization_matched": specialization_hits,
            "specialization_missing": specialization_missing,

            "routing_score": round(
                final_score * 100,
                2
            ),

            "responsibility_match_evidence": responsibility_hits,
            "requirement_match_evidence": all_req_hits
        })

    market_results.sort(
        key=lambda x: (
            x["routing_score"],
            x["responsibility_score"],
            x["target_title_score"]
        ),
        reverse=True
    )

    # Exact role family plus corresponding principal work constrains the
    # market prior. Shared SQL/Python words cannot turn engineering into DS.
    family_binding = None
    family_pattern = None
    core_work_pattern = None
    if re.search(r'\bdata engineer(?:ing)?\b', target_title, re.I):
        family_binding, family_pattern = 'Data Engineer', r'\bdata engineer(?:ing)?\b'
        core_work_pattern = r'\b(?:pipelines?|ETL|ELT|data warehouses?|data lakes?|ingestion|data engineering)\b'
    elif re.search(r'\b(?:business intelligence|BI) analyst\b', target_title, re.I):
        family_binding, family_pattern = 'Business Intelligence Analyst', r'\bbusiness intelligence analyst\b'
        core_work_pattern = r'\b(?:dashboards?|reporting|Power BI|Tableau|business intelligence)\b'
    family_candidates = [x for x in market_results if family_pattern and re.search(family_pattern,x['role'],re.I)]
    binding_evidence = re.findall(core_work_pattern, responsibility_text, re.I) if core_work_pattern else []
    principal_rows=[r.get('exact_quote','') for r in req.get('requirements',[]) if r.get('priority')=='P1']
    engineering_work=r'\b(?:pipelines?|ETL|ELT|data warehouses?|data lakes?|ingestion|orchestration)\b'
    reporting_work=r'\b(?:dashboards?|reporting|Power BI|Tableau|business intelligence)\b'
    supporting_rows=sum(bool(re.search(core_work_pattern,text,re.I)) for text in principal_rows) if core_work_pattern else 0
    competing_pattern=reporting_work if family_binding=='Data Engineer' else engineering_work
    competing_rows=sum(bool(re.search(competing_pattern,text,re.I)) for text in principal_rows)
    principal_work_supports_family=bool(supporting_rows and supporting_rows>=competing_rows)
    if family_candidates and binding_evidence and principal_work_supports_family:
        eligible_ids = {x['role_number'] for x in family_candidates}
        market_results.sort(key=lambda x:(x['role_number'] in eligible_ids,x['routing_score']),reverse=True)
    else:
        prior_family=family_binding
        family_binding = None
        # A misleading exact title cannot outweigh a clear majority of
        # principal duties. A single collaboration/tool line is insufficient.
        if prior_family and competing_rows>=max(2,math.ceil(len(principal_rows)*.6)) and competing_rows>=supporting_rows+2:
            family_binding='Data Engineer' if prior_family=='Business Intelligence Analyst' else 'Business Intelligence Analyst'
            pattern=r'\bdata engineer(?:ing)?\b' if family_binding=='Data Engineer' else r'\bbusiness intelligence analyst\b'
            family_candidates=[x for x in market_results if re.search(pattern,x['role'],re.I)]
            if family_candidates:
                eligible_ids={x['role_number'] for x in family_candidates}
                market_results.sort(key=lambda x:(x['role_number'] in eligible_ids,x['routing_score']),reverse=True)
                supporting_rows,competing_rows=competing_rows,supporting_rows
                binding_evidence=re.findall(competing_pattern,responsibility_text,re.I)
            else:family_binding=None
    binding_basis='PRINCIPAL_DUTIES_OVERRIDE_MISLEADING_TITLE' if family_binding and 'prior_family' in locals() else 'EXACT_TITLE_AND_PRINCIPAL_WORK'
    primary = market_results[0]
    second = (family_candidates[1] if family_binding and len(family_candidates)>1 else market_results[1])

    margin = (
        primary["routing_score"]
        - second["routing_score"]
    )

    if (
        primary["routing_score"] >= 55
        and margin >= 10
    ):
        confidence = "HIGH"

    elif (
        primary["routing_score"] >= 40
        and margin >= 5
    ):
        confidence = "MEDIUM"

    else:
        confidence = "LOW"

    if family_binding and len(set(x.casefold() for x in binding_evidence)) >= 2 and supporting_rows>=max(2,math.ceil(len(principal_rows)*.4)):
        confidence = 'HIGH'
    output = {
        "schema_version": "role-routing-v2",
        "exact_application_title": target_title,
        "family_binding": {'family':family_binding,'basis':binding_basis if family_binding else None,'source_work_terms':sorted(set(binding_evidence)) if family_binding else [],'supporting_principal_rows':supporting_rows,'competing_principal_rows':competing_rows},

        "policy": {
            "target_jd_is_employer_specific_authority": True,
            "application_role_universe_is_separate": True,
            "market_ontology_is_separate_prior": True,
            "title_alone_may_not_determine_role": True,
            "jd_content_weight": 0.65,
            "title_layers_weight": 0.35,
            "dynamic_specialization_guard": True,

            # Routing intentionally happens BEFORE semantic expansion.
            # Only exact employer-specific JD evidence participates here.
            "semantic_expansion_used_for_routing": False,
            "semantic_expansion_performed": False,
            "routing_stage": "PRE_SEMANTIC_EXPANSION"
        },

        "input": {
            "target_title_candidate": target_title,
            "requirement_count": req[
                "requirement_count"
            ],
            "requirements_fingerprint": req_fingerprint
        },

        "application_route": {
            "primary": best_app,
            "top_5": app_results[:5]
        },

        "market_route": {
            "primary": {
                **primary,
                "confidence": confidence,
                "margin_to_second": round(
                    margin,
                    2
                )
            },
            "top_5": market_results[:5],
            "all_50": market_results
        }
    }

    OUT.write_text(
        json.dumps(
            output,
            indent=2,
            ensure_ascii=False
        )
    )

    print("ROLE ROUTING V2: CREATED")
    print("APPLICATION ROLES:", len(app_roles))
    print("MARKET ROLES:", len(market_roles))
    print("TARGET TITLE:", target_title)

    print(
        "APPLICATION ROUTE:",
        best_app["search_title"],
        "|",
        best_app["title_match_score"]
    )

    print(
        "MARKET ROUTE:",
        primary["role"]
    )

    print(
        "ROUTING SCORE:",
        primary["routing_score"]
    )

    print(
        "CONFIDENCE:",
        confidence
    )

    print(
        "MARGIN TO #2:",
        round(margin, 2)
    )

    print("\nTOP 5 MARKET ROUTES:")

    for i, role in enumerate(
        market_results[:5],
        start=1
    ):
        print(
            f"{i}. {role['role']} | "
            f"route={role['routing_score']:.2f} | "
            f"title={role['target_title_score']:.2f} | "
            f"app={role['application_title_score']:.2f} | "
            f"work={role['responsibility_score']:.2f} | "
            f"req={role['all_requirement_score']:.2f} | "
            f"spec_penalty={role['specialization_penalty']:.2f}"
        )

    print(
        "\nOUTPUT:",
        OUT.relative_to(ROOT)
    )


if __name__ == "__main__":
    from careerops_requirement_authority import run_guarded
    run_guarded(main, RUNTIME, "careerops_route_role.py")
