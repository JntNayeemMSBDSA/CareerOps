from careerops_config import source_dir
#!/usr/bin/env python3

import json
import re
from pathlib import Path
from careerops_requirement_regeneration import canonical_ledger_path


from careerops_runtime import runtime_dir
from careerops_effective_runtime import ensure_effective_runtime

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = runtime_dir(ROOT)

SEMANTIC_PATH = RUNTIME / 'jd_semantic_map.json'
ROUTE_PATH = RUNTIME / 'role_routing.json'
COVERAGE_PATH = source_dir(ROOT) / 'assumed_market_coverage.json'

FACTS_PATH = source_dir(ROOT) / 'candidate_facts.json'
OUT = RUNTIME / 'constraint_validation.json'


# ============================================================
# DIRECT USER-CONFIRMED FACTS
#
# These are authoritative candidate facts.
# They are NOT artifact-inferred and do not need to be.
# ============================================================

def load_candidate_facts():
    if not FACTS_PATH.exists():
        raise SystemExit(
            f"Missing canonical candidate facts: {FACTS_PATH}"
        )

    data = json.loads(
        FACTS_PATH.read_text()
    )

    if not isinstance(data, dict):
        raise SystemExit(
            "Canonical candidate facts must be a JSON object."
        )

    return data


DEGREE_RANK = {
    "high school": 0,
    "associate": 1,
    "associates": 1,
    "bachelor": 2,
    "bachelors": 2,
    "master": 3,
    "masters": 3,
    "mba": 3,
    "phd": 4,
    "doctorate": 4
}


SKILL_ALIASES = {
    "sql": ["sql"],
    "python": ["python"],
    "excel": ["excel"],
    "power bi": ["power bi", "bi", "business intelligence"],
    "cloud": [
        "cloud",
        "aws",
        "azure",
        "gcp",
        "snowflake"
    ]
}


ANALYTICS_CAPABILITY_TERMS = {
    "analytics",
    "analysis",
    "data analysis",
    "business intelligence",
    "reporting",
    "dashboard",
    "dashboards",
    "power bi",
    "tableau",
    "statistics",
    "data visualization"
}


def norm(text):
    text = str(text).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9+ ]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
}


def parse_year_number(value):
    value = str(value).strip().lower()

    if value.isdigit():
        return int(value)

    return NUMBER_WORDS.get(value)


def extract_required_years(phrases):
    """
    Return the minimum qualifying years required by the JD.

    Supports numeric and written-number requirements.

    Explicit ranges use the lower bound because that is the
    minimum experience needed to satisfy the stated range.
    """
    number = (
        r"(?:\d+|one|two|three|four|five|six|seven|eight|"
        r"nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
        r"sixteen|seventeen|eighteen|nineteen|twenty)"
    )

    range_minima = []
    values = []

    for phrase in phrases:
        raw = str(phrase).lower()

        range_patterns = [
            (
                rf"\b({number})\s*"
                rf"(?:-|–|—|to)\s*"
                rf"({number})\s+years?\b"
            ),
            (
                rf"\bbetween\s+({number})\s+and\s+"
                rf"({number})\s+years?\b"
            ),
        ]

        range_match = None

        for pattern in range_patterns:
            range_match = re.search(
                pattern,
                raw,
                flags=re.I
            )

            if range_match:
                break

        if range_match:
            low = parse_year_number(
                range_match.group(1)
            )
            high = parse_year_number(
                range_match.group(2)
            )

            if low is not None and high is not None:
                range_minima.append(
                    min(low, high)
                )

            continue

        single_patterns = [
            rf"\b({number})\s*\+\s*years?\b",

            # Equivalent serialization: "2 years+".
            # This changes no occupational relevance semantics.
            rf"\b({number})\s+years?\s*\+(?!\w)",
            rf"\bat least\s+({number})\s+years?\b",
            rf"\bminimum(?: of)?\s+({number})\s+years?\b",
            rf"\b({number})\s+years?\b",
        ]

        for pattern in single_patterns:
            match = re.search(
                pattern,
                raw,
                flags=re.I
            )

            if not match:
                continue

            value = parse_year_number(
                match.group(1)
            )

            if value is not None:
                values.append(value)

            break

    if range_minima:
        return max(range_minima)

    return max(values) if values else None



def required_degree_rank(phrases):
    text = norm(" ".join(phrases))

    hits = []

    for label, rank in DEGREE_RANK.items():
        if label in text:
            hits.append((label, rank))

    return max(hits, key=lambda x: x[1]) if hits else None


def highest_candidate_degree(facts):
    hits = []

    for row in facts["education"]:
        level = norm(row["degree_level"])

        if level in DEGREE_RANK:
            hits.append(
                (
                    row,
                    DEGREE_RANK[level]
                )
            )

    return max(hits, key=lambda x: x[1]) if hits else None


def duration_for_skill(facts, skill):
    target = norm(skill)

    for canonical, aliases in SKILL_ALIASES.items():

        if target not in aliases and target != canonical:
            continue

        for stored_name, record in facts[
            "skill_duration_years"
        ].items():

            stored = norm(stored_name)

            if stored == canonical:
                return {
                    "skill": stored_name,
                    "years": float(record["years"]),
                    "claim_class": record["claim_class"]
                }

    return None


def requirement_skill_terms(text):
    t = norm(text)
    found = []

    for canonical, aliases in SKILL_ALIASES.items():
        for alias in aliases:
            if re.search(
                r"(?<![a-z0-9])"
                + re.escape(alias)
                + r"(?![a-z0-9])",
                t
            ):
                found.append(canonical)
                break

    return found


def has_analytics_requirement(text):
    t = norm(text)
    if re.search(r'\bdata analyst\b', t):
        return True

    return any(
        term in t
        for term in ANALYTICS_CAPABILITY_TERMS
    )


def month_index(value):
    match = re.fullmatch(
        r"(\d{4})-(\d{2})",
        str(value).strip(),
    )

    if not match:
        return None

    year = int(
        match.group(1)
    )

    month = int(
        match.group(2)
    )

    if month < 1 or month > 12:
        return None

    return (
        year * 12
        + month
        - 1
    )


def chronology_duration_support(
    facts,
    capability_family,
):
    rows = []

    for row in facts.get(
        "professional_chronology",
        [],
    ):
        families = {
            str(x)
            .strip()
            .casefold()
            .replace("-", "_")
            .replace(" ", "_")
            for x in row.get(
                "capability_families",
                [],
            )
        }

        target = (
            str(capability_family)
            .strip()
            .casefold()
            .replace("-", "_")
            .replace(" ", "_")
        )

        if target not in families:
            continue

        start = month_index(
            row.get(
                "start_month"
            )
        )

        end = month_index(
            row.get(
                "end_month"
            )
        )

        if (
            start is None
            or end is None
            or end < start
        ):
            continue

        rows.append(
            (
                start,
                end,
                row,
            )
        )

    if not rows:
        return None

    rows.sort(
        key=lambda x: (
            x[0],
            x[1],
        )
    )

    merged = []

    for start, end, row in rows:
        if (
            not merged
            or start
            > merged[-1][1] + 1
        ):
            merged.append(
                [
                    start,
                    end,
                ]
            )
        else:
            merged[-1][1] = max(
                merged[-1][1],
                end,
            )

    months = sum(
        end - start + 1
        for start, end
        in merged
    )

    evidence_entities = [
        row.get(
            "evidence_id"
        )
        for _, _, row
        in rows
        if row.get(
            "evidence_id"
        )
    ]

    chronology = "; ".join(
        (
            f"{row.get('start_month')} through "
            f"{row.get('end_month')} "
            f"({row.get('evidence_id')})"
        )
        for _, _, row
        in rows
    )

    return {
        "months":
            months,

        "years":
            round(
                months / 12.0,
                2,
            ),

        "claim_class":
            "VERIFIED_CHRONOLOGY_DERIVED",

        "evidence_entities":
            evidence_entities,

        "chronology":
            chronology,
    }


def related_field_semantic_compatibility(
    requirement_text,
    capability_family,
):
    family = (
        str(capability_family)
        .strip()
        .casefold()
        .replace("-", "_")
        .replace(" ", "_")
    )

    if family == "data_analytics":
        compatible = (
            has_analytics_requirement(
                requirement_text
            )
        )

        return {
            "compatible":
                compatible,

            "basis":
                (
                    "REQUIREMENT_TEXT_MATCHES_ANALYTICS_FAMILY"
                    if compatible
                    else
                    "REQUIREMENT_TEXT_DOES_NOT_ESTABLISH_ANALYTICS_AS_RELATED_FIELD"
                ),
        }

    return {
        "compatible": False,
        "basis":
            "NO_SEMANTIC_COMPATIBILITY_RULE_FOR_CAPABILITY_FAMILY",
    }


def analytics_duration_support(facts, required_years):
    chronology = chronology_duration_support(
        facts,
        "data_analytics",
    )

    if (
        chronology
        and chronology.get(
            "years",
            0,
        )
        >= required_years
    ):
        return {
            "status":
                "PASS",

            "basis":
                "VERIFIED_PROFESSIONAL_CHRONOLOGY",

            "years":
                chronology[
                    "years"
                ],

            "evidence_entities":
                chronology.get(
                    "evidence_entities",
                    [],
                ),

            "chronology":
                chronology.get(
                    "chronology"
                ),

            "reason":
                (
                    "Verified professional data-analytics chronology "
                    f"supports {chronology['years']:g} years against "
                    f"the {required_years:g}-year minimum."
                ),
        }

    power_bi = duration_for_skill(
        facts,
        "power bi",
    )

    result = {
        "status":
            "REVIEW_REQUIRED",

        "basis":
            "OCCUPATIONAL_DURATION_NOT_PROVEN",

        "reason":
            (
                "Verified professional chronology does not currently "
                "prove the requested analytics-duration minimum."
            ),
    }

    if power_bi:
        result[
            "supporting_skill"
        ] = "Power BI"

        result[
            "supporting_skill_years"
        ] = power_bi.get(
            "years"
        )

        result[
            "supporting_skill_policy"
        ] = (
            "Tool tenure is corroborating capability evidence only; "
            "it does not independently establish occupational tenure."
        )

    if chronology:
        result[
            "verified_chronology_years"
        ] = chronology.get(
            "years"
        )

        result[
            "evidence_entities"
        ] = chronology.get(
            "evidence_entities",
            [],
        )

    return result

def generic_relevant_experience_route_dispatch(
    requirement_text,
    required_years,
    routing,
):
    """
    Decide only whether an unqualified generic "relevant experience"
    duration requirement may reuse the existing verified data-analytics
    chronology for an analytics-family routed role.

    This function does NOT calculate duration and does NOT create
    candidate facts. It is only a conservative semantic dispatcher.

    Narrower requirements remain outside this bridge, for example:
      relevant experience in higher education
      relevant healthcare experience
      relevant experience with PeopleSoft
      financial analyst experience
    """
    if required_years is None:
        return {
            "dispatch": False,
            "basis": "NO_REQUIRED_DURATION",
        }

    text = norm(
        requirement_text
    )

    # Explicit analytics wording already has its established path.
    # Do not duplicate or replace it here.
    if has_analytics_requirement(
        text
    ):
        return {
            "dispatch": False,
            "basis": "EXPLICIT_ANALYTICS_PATH_ALREADY_APPLIES",
        }

    if not re.search(
        r"\brelevant\s+experience\b",
        text,
        flags=re.I,
    ):
        return {
            "dispatch": False,
            "basis": "NOT_GENERIC_RELEVANT_EXPERIENCE",
        }

    # Remove only duration/administrative language.
    # Anything substantive left means the requirement is qualified
    # by a domain, system, specialty, or other condition and therefore
    # must not be satisfied by role routing alone.
    residual = re.sub(
        r"\brelevant\s+experience\b",
        " ",
        text,
        flags=re.I,
    )

    residual = re.sub(
        (
            r"\b(?:"
            r"required|"
            r"minimum|"
            r"at|"
            r"least|"
            r"between|"
            r"to|"
            r"and|"
            r"of|"
            r"years?|"
            r"plus"
            r")\b"
        ),
        " ",
        residual,
        flags=re.I,
    )

    number_words = (
        "one|two|three|four|five|six|seven|eight|nine|ten|"
        "eleven|twelve|thirteen|fourteen|fifteen|sixteen|"
        "seventeen|eighteen|nineteen|twenty"
    )

    residual = re.sub(
        rf"\b(?:\d+|{number_words})\b",
        " ",
        residual,
        flags=re.I,
    )

    residual = residual.replace(
        "+",
        " ",
    )

    residual = re.sub(
        r"\s+",
        " ",
        residual,
    ).strip()

    if residual:
        return {
            "dispatch": False,
            "basis": "RELEVANT_EXPERIENCE_HAS_NARROWER_QUALIFIER",
            "residual": residual,
        }

    primary = (
        routing.get(
            "market_route",
            {},
        )
        .get(
            "primary",
            {},
        )
    )

    routed_role = norm(
        primary.get(
            "role",
            "",
        )
    )

    analytics_route_signals = (
        "data analyst",
        "data scientist",
        "analytics",
        "business intelligence",
        "reporting analyst",
        "marketing data analyst",
        "data quality analyst",
    )

    if not any(
        signal in routed_role
        for signal in analytics_route_signals
    ):
        return {
            "dispatch": False,
            "basis": "ROUTED_ROLE_NOT_ANALYTICS_FAMILY",
            "routed_role": routed_role,
        }

    return {
        "dispatch": True,
        "basis": "GENERIC_RELEVANT_EXPERIENCE_ANALYTICS_ROUTE",
        "routed_role": routed_role,
    }


def general_experience_duration_support(facts, text, required_years):
    """Unqualified professional years use the same union chronology."""
    if required_years is None:
        return None
    mandatory = re.split(r'\b(?:preferably|preferred|nice.to.have)\b', norm(text), maxsplit=1)[0]
    stripped = re.sub(r'\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+)\b|\b(?:plus|minimum|at|least|between|to|of|relevant|professional|work|required|years?|experience)\b|[^a-z]', ' ', mandatory)
    if stripped.strip():
        return None
    return analytics_duration_support(facts, required_years)


def broad_analyst_duration_support(
    facts,
    requirement_text,
    required_years,
):
    """
    Validate an explicitly broad duration requirement such as
    '3 years of analyst experience' against verified professional
    data-analytics chronology.

    This deliberately does NOT satisfy narrower historical-domain
    claims such as 'financial analyst experience', 'retail analyst
    experience', or another specifically modified analyst title.
    """
    if required_years is None:
        return None

    text = norm(
        requirement_text
    )

    # Require the genuinely broad construction:
    # "... years of analyst experience ..."
    #
    # Examples accepted:
    #   3 years of analyst experience
    #   3-5 years of analyst experience
    #
    # Examples intentionally NOT accepted:
    #   3 years of financial analyst experience
    #   3 years of retail analyst experience
    if not re.search(
        r"\byears?\s+of\s+analyst\s+experience\b",
        text,
        flags=re.I,
    ):
        return None

    support = chronology_duration_support(
        facts,
        "data_analytics",
    )

    if not support:
        return {
            "status":
                "REVIEW_REQUIRED",
            "basis":
                "NO_VERIFIED_BROAD_ANALYST_CHRONOLOGY",
            "required_years":
                required_years,
            "reason": (
                "The JD contains a broad analyst-experience "
                "duration requirement, but no canonical verified "
                "data-analytics professional chronology is available."
            ),
        }

    years = float(
        support.get(
            "years",
            0,
        )
    )

    if years >= required_years:
        return {
            "status":
                "PASS",
            "basis":
                "VERIFIED_BROAD_ANALYST_CHRONOLOGY",
            "years":
                years,
            "required_years":
                required_years,
            "claim_class":
                support.get(
                    "claim_class"
                ),
            "evidence_entities":
                support.get(
                    "evidence_entities",
                    [],
                ),
            "chronology":
                support.get(
                    "chronology",
                ),
            "domain_claim_created":
                False,
            "reason": (
                f"The JD requires broad analyst experience. "
                f"Verified professional data-analytics chronology "
                f"supports {years:g} years against the "
                f"{required_years:g}-year minimum. No narrower "
                f"industry or analyst-specialty history is inferred."
            ),
        }

    return {
        "status":
            "REVIEW_REQUIRED",
        "basis":
            "BROAD_ANALYST_DURATION_BELOW_MINIMUM",
        "years":
            years,
        "required_years":
            required_years,
        "claim_class":
            support.get(
                "claim_class"
            ),
        "evidence_entities":
            support.get(
                "evidence_entities",
                [],
            ),
        "chronology":
            support.get(
                "chronology",
            ),
        "domain_claim_created":
            False,
        "reason": (
            f"Verified professional data-analytics chronology "
            f"supports {years:g} years, below the "
            f"{required_years:g}-year minimum."
        ),
    }


def related_field_duration_support(
    facts,
    requirement_text,
    required_years,
    routing,
):
    """
    Validate broad "related field(s)" experience alternatives
    against conservative verified professional chronology.

    This must never convert related-field experience into a
    target-domain historical claim.
    """
    if required_years is None:
        return None

    text = norm(requirement_text)

    if not re.search(
        r"\brelated\s+fields?\b",
        text,
        flags=re.I,
    ):
        return None

    primary = (
        routing.get("market_route", {})
        .get("primary", {})
    )

    routed_role = norm(
        primary.get("role", "")
    )

    analytics_route_signals = (
        "data analyst",
        "data scientist",
        "analytics",
        "business intelligence",
        "reporting analyst",
        "marketing data analyst",
        "data quality analyst",
    )

    if not any(
        signal in routed_role
        for signal in analytics_route_signals
    ):
        return {
            "status": "REVIEW_REQUIRED",
            "basis":
                "RELATED_FIELD_ROUTE_NOT_ESTABLISHED",
            "reason": (
                "The JD permits a related-field alternative, "
                "but the current routed role does not establish "
                "that the stored analytics chronology is a "
                "relevant related field."
            )
        }

    compatibility = (
        related_field_semantic_compatibility(
            requirement_text,
            "data_analytics",
        )
    )

    if not compatibility.get(
        "compatible"
    ):
        return {
            "status":
                "REVIEW_REQUIRED",

            "basis":
                "RELATED_FIELD_SEMANTIC_COMPATIBILITY_NOT_ESTABLISHED",

            "compatibility":
                compatibility,

            "reason": (
                "The JD permits a related-field alternative, "
                "but the requirement text does not establish "
                "data analytics as semantically related to the "
                "named field. Role routing alone is insufficient "
                "to convert analytics chronology into qualifying "
                "domain experience."
            ),
        }

    support = (
        chronology_duration_support(
            facts,
            "data_analytics",
        )
    )

    if not support:
        return {
            "status":
                "REVIEW_REQUIRED",

            "basis":
                "NO_VERIFIED_RELATED_FIELD_CHRONOLOGY",

            "reason": (
                "The requirement is semantically compatible with "
                "the analytics capability family, but no valid "
                "canonical professional chronology is available."
            ),
        }

    years = float(
        support.get(
            "years",
            0,
        )
    )

    if years >= required_years:
        return {
            "status": "PASS",
            "basis":
                "VERIFIED_RELATED_FIELD_CHRONOLOGY",
            "years": years,
            "required_years": required_years,
            "claim_class":
                support.get("claim_class"),
            "evidence_entities":
                support.get("evidence_entities", []),
            "chronology":
                support.get("chronology"),
            "domain_claim_created": False,
            "reason": (
                f"The JD explicitly permits experience in "
                f"'related fields'. Verified consecutive "
                f"analytics-related professional chronology "
                f"supports at least {years:g} years, exceeding "
                f"the {required_years:g}-year minimum. "
                f"This does not claim prior higher-education, "
                f"student-records, or PeopleSoft experience."
            )
        }

    return {
        "status": "REVIEW_REQUIRED",
        "basis":
            "RELATED_FIELD_DURATION_BELOW_MINIMUM",
        "years": years,
        "required_years": required_years,
        "reason": (
            "Verified related-field chronology does not meet "
            "the minimum duration."
        )
    }


def education_only_alternative_pass(text, facts):
    """
    Detect compound qualification structures such as:

      Master's degree
      OR
      Bachelor's degree + two years experience

    If an independent education-only branch is already satisfied,
    the overall alternative qualification is satisfied without
    incorrectly requiring conditions from the other OR branch.

    This does not waive requirements inside a branch.
    """
    if not re.search(
        r"\bor\b",
        str(text),
        flags=re.I
    ):
        return None

    # An OR inside a field list or "foreign equivalent" modifies a
    # single education condition. It never detaches a trailing AND years.
    text = str(text)
    independent_degree_branch = re.search(
        r"\bor\s+(?:(?:a|an)\s+)?(?:bachelor|master|doctor|Ph\.?D)", text, re.I)
    if not independent_degree_branch:
        return None

    branches = re.split(
        r"\s*;\s*or\s+|\s+or\s+",
        str(text),
        flags=re.I
    )

    if len(branches) < 2:
        return None

    candidate = highest_candidate_degree(
        facts
    )

    if not candidate:
        return None

    for index, branch in enumerate(
        branches,
        start=1
    ):
        required_degree = required_degree_rank(
            [branch]
        )

        required_years = extract_required_years(
            [branch]
        )

        # Only short-circuit on a genuinely independent
        # education-only branch.
        if (
            required_degree
            and required_years is None
            and candidate[1] >= required_degree[1]
            and ((__import__('careerops_constraint_logic').education_field_support(branch,facts,required_degree[1]) or {}).get('status','PASS')=='PASS')
        ):
            return {
                "constraint_type":
                    "alternative_qualification",
                "status": "PASS",
                "claim_class":
                    "DIRECT_USER_CONFIRMED",
                "satisfied_branch": index,
                "satisfied_branch_text":
                    branch.strip(),
                "required_degree":
                    required_degree[0],
                "candidate_degree":
                    candidate[0],
                "reason": (
                    "An independent education-only OR branch "
                    "is satisfied; conditions belonging to a "
                    "different alternative branch are not "
                    "cumulative."
                )
            }

    return None

def main():

    for path in [
        SEMANTIC_PATH,
        ROUTE_PATH,
        COVERAGE_PATH
    ]:
        if not path.exists():
            raise SystemExit(
                f"Missing required source: {path}"
            )

    semantic_map = json.loads(
        SEMANTIC_PATH.read_text()
    )

    routing = json.loads(
        ROUTE_PATH.read_text()
    )

    #
    # Constraint validation consumes semantic constraints plus
    # exact hard-blocker phrases from the canonical requirement
    # ledger for this same requisition.
    requirements_path = (
        canonical_ledger_path(RUNTIME)
    )

    if not requirements_path.exists():
        raise SystemExit(
            "FAIL CLOSED: jd_requirements.json is "
            "required for hard-blocker validation."
        )

    effective_bundle = ensure_effective_runtime(
        RUNTIME
    )

    requirements_ledger = effective_bundle[
        "effective_ledger"
    ]

    ledger_by_id = {
        row.get("requirement_id"): row
        for row in requirements_ledger.get(
            "requirements",
            [],
        )
        if row.get(
            "requirement_id"
        )
    }

    # --------------------------------------------------------
    # CURRENT-JOB SAFETY
    #
    # Constraint validation must never consume a semantic map
    # or route produced for another requisition.
    # --------------------------------------------------------

    semantic_fingerprint = (
        semantic_map.get(
            "requirements_fingerprint"
        )
    )

    route_fingerprint = (
        routing.get("input", {})
        .get("requirements_fingerprint")
    )

    if not semantic_fingerprint:
        raise SystemExit(
            "FAIL CLOSED: jd_semantic_map.json has no "
            "current-job requirements fingerprint."
        )

    if not route_fingerprint:
        raise SystemExit(
            "FAIL CLOSED: role_routing.json has no "
            "current-job requirements fingerprint."
        )

    if semantic_fingerprint != route_fingerprint:
        raise SystemExit(
            "FAIL CLOSED: semantic map and role routing "
            "belong to different requirement ledgers."
        )

    if not (
        semantic_map.get(
            "routing_provenance",
            {}
        ).get(
            "current_job_match"
        )
    ):
        raise SystemExit(
            "FAIL CLOSED: semantic map is not confirmed "
            "against the current job route."
        )

    # Load this intentionally so the validator knows the
    # authorized assumed-capability layer exists.
    coverage = json.loads(
        COVERAGE_PATH.read_text()
    )

    facts = load_candidate_facts()

    validations = []

    for req in semantic_map["requirements"]:

        exact_layer = req.get(
            "exact_layer",
            {}
        )

        education_phrases = exact_layer.get(
            "education",
            []
        )

        experience_phrases = exact_layer.get(
            "experience_years",
            []
        )

        ledger_requirement = (
            ledger_by_id.get(
                req.get(
                    "requirement_id"
                ),
                {},
            )
            or {}
        )

        hard_blocker_phrases = (
            ledger_requirement.get(
                "hard_blocker_phrases",
                [],
            )
            or []
        )

        from careerops_requirement_qualifiers import qualifier_contract, qualifier_supported
        mandatory_qualifiers = qualifier_contract(req['exact_jd_quote'])
        constraint_validation_required = bool(
            education_phrases or experience_phrases or hard_blocker_phrases
            or mandatory_qualifiers
        )

        if not constraint_validation_required:
            continue

        # An explicit requisition eligibility exclusion is not
        # reparable by experience evidence, projects, assumed
        # capability, or writer phrasing.
        if hard_blocker_phrases:
            validations.append({
                "requirement_id":
                    req[
                        "requirement_id"
                    ],

                "priority":
                    req[
                        "priority"
                    ],

                "exact_jd_quote":
                    req[
                        "exact_jd_quote"
                    ],

                "overall_status":
                    "FAIL",

                "checks": [
                    {
                        "constraint_type":
                            "hard_blocker",

                        "status":
                            "FAIL",

                        "hard_blocker_phrases":
                            hard_blocker_phrases,

                        "policy":
                            (
                                "Explicit requisition eligibility "
                                "blockers cannot be repaired by "
                                "candidate evidence, projects, "
                                "assumed market coverage, or "
                                "writer wording."
                            ),
                    }
                ],
            })

            continue

        checks = []

        alternative_pass = (
            education_only_alternative_pass(
                req["exact_jd_quote"],
                facts
            )
        )

        if alternative_pass:
            validations.append({
                "requirement_id": req[
                    "requirement_id"
                ],
                "priority": req[
                    "priority"
                ],
                "exact_jd_quote": req[
                    "exact_jd_quote"
                ],
                "overall_status": "PASS",
                "checks": [
                    alternative_pass
                ]
            })

            continue

        # ====================================================
        # EDUCATION
        # ====================================================

        if education_phrases:

            required = required_degree_rank(
                education_phrases
            )

            candidate = highest_candidate_degree(
                facts
            )

            if (
                required
                and candidate
                and candidate[1] >= required[1]
            ):
                checks.append({
                    "constraint_type": "education",
                    "status": "PASS",
                    "claim_class": "DIRECT_USER_CONFIRMED",
                    "required_phrases": education_phrases,
                    "candidate_degree": candidate[0],
                    "reason": (
                        f"Candidate degree exceeds or satisfies "
                        f"the requested degree level."
                    )
                })

            else:
                checks.append({
                    "constraint_type": "education",
                    "status": "REVIEW_REQUIRED",
                    "required_phrases": education_phrases
                })

        if education_phrases:
            from careerops_constraint_logic import education_field_support
            field_check=education_field_support(req['exact_jd_quote'],facts,required[1] if required else 0)
            if field_check:checks.append(field_check)

        # ====================================================
        # YEARS OF EXPERIENCE
        # ====================================================

        if experience_phrases:

            required_years = extract_required_years(
                experience_phrases
            )

            requirement_text = (
                req["exact_jd_quote"]
            )

            skill_terms = requirement_skill_terms(
                requirement_text
            )

            from careerops_constraint_logic import tool_tenure_logic,evaluate_tool_tenure
            tool_logic=tool_tenure_logic(requirement_text,skill_terms,SKILL_ALIASES)
            skill_checks = []

            for skill in tool_logic['mandatory_skills']:

                direct = duration_for_skill(
                    facts,
                    skill
                )

                if (
                    direct
                    and required_years is not None
                    and direct["years"] >= required_years
                ):
                    skill_checks.append({
                        "skill": skill,
                        "status": "PASS",
                        "years": direct["years"],
                        "required_years": required_years,
                        "claim_class": direct[
                            "claim_class"
                        ],
                        "basis": "DIRECT_USER_CONFIRMED_DURATION"
                    })

                else:
                    skill_checks.append({
                        "skill": skill,
                        "status": "REVIEW_REQUIRED",
                        "required_years": required_years
                    })

            analytics_check = None

            explicit_analytics_requirement = (
                required_years is not None
                and has_analytics_requirement(
                    requirement_text
                )
            )

            generic_relevant_dispatch = (
                generic_relevant_experience_route_dispatch(
                    requirement_text,
                    required_years,
                    routing,
                )
            )

            if (
                required_years is not None
                and (
                    explicit_analytics_requirement
                    or generic_relevant_dispatch.get(
                        "dispatch"
                    )
                )
            ):
                analytics_check = (
                    analytics_duration_support(
                        facts,
                        required_years
                    )
                )

                if (
                    analytics_check
                    and generic_relevant_dispatch.get(
                        "dispatch"
                    )
                    and not explicit_analytics_requirement
                ):
                    analytics_check = dict(
                        analytics_check
                    )

                    analytics_check[
                        "dispatch_basis"
                    ] = generic_relevant_dispatch.get(
                        "basis"
                    )

                    analytics_check[
                        "routed_role"
                    ] = generic_relevant_dispatch.get(
                        "routed_role"
                    )

            analyst_duration_check = (
                broad_analyst_duration_support(
                    facts,
                    requirement_text,
                    required_years,
                )
            )

            related_field_check = (
                related_field_duration_support(
                    facts,
                    requirement_text,
                    required_years,
                    routing,
                )
            )

            general_check = general_experience_duration_support(facts, requirement_text, required_years)
            tool_status=evaluate_tool_tenure(tool_logic,skill_checks)
            statuses = [tool_status] if tool_status is not None else []
            if general_check:
                statuses.append(general_check['status'])

            if analytics_check:
                statuses.append(
                    analytics_check["status"]
                )

            if analyst_duration_check:
                statuses.append(
                    analyst_duration_check["status"]
                )

            if related_field_check:
                statuses.append(
                    related_field_check["status"]
                )

            if (
                statuses
                and all(
                    x == "PASS"
                    for x in statuses
                )
            ):
                overall = "PASS"
            else:
                overall = "REVIEW_REQUIRED"

            checks.append({
                "constraint_type": "experience_years",
                "status": overall,
                "required_years": required_years,
                "required_phrases": experience_phrases,
                "skill_duration_checks": skill_checks,
                "tool_tenure_logic": tool_logic,
                "tool_tenure_status": tool_status,
                "analytics_duration_check": analytics_check,
                "general_experience_check": general_check,
                "analyst_duration_check":
                    analyst_duration_check,
                "related_field_duration_check":
                    related_field_check,
                "policy": (
                    "Direct user-confirmed duration is "
                    "authoritative candidate fact. "
                    "Artifact evidence is not required "
                    "for a direct user-confirmed duration."
                )
            })

        if mandatory_qualifiers:
            evidence_map = json.loads((RUNTIME / 'requirement_evidence_map.json').read_text())
            mapped = next((x for x in evidence_map.get('requirements', [])
                           if x['requirement_id'] == req['requirement_id']), {})
            qualified = [x for x in mapped.get('verified_evidence_candidates', [])
                         if x.get('requirement_coverage') == 'SUPPORTED']
            if experience_phrases:
                # Duration must come from chronology in this scope. A
                # finance portfolio project does not prove industry tenure.
                eligible = [row for row in facts.get('professional_chronology', [])
                            if all(qualifier_supported(q, json.dumps(row)) for q in mandatory_qualifiers)]
                scoped = dict(facts, professional_chronology=eligible)
                support = chronology_duration_support(scoped, 'data_analytics')
                required = extract_required_years(experience_phrases)
                qualified_status = 'PASS' if support and required is not None and support['years'] >= required else 'REVIEW_REQUIRED'
            else:
                support = {'evidence_ids':[x['entity_id'] for x in qualified]}
                qualified_status = 'PASS' if qualified else 'REVIEW_REQUIRED'
            checks.append({'constraint_type':'mandatory_qualifiers', 'status':qualified_status,
                           'reason_code': 'QUALIFIER_SUPPORTED' if qualified_status == 'PASS' else 'QUALIFIER_UNVERIFIED',
                           'qualifiers':mandatory_qualifiers, 'scoped_support':support,
                           'policy':'Generic core evidence and unqualified tenure do not prove mandatory scope.'})

        statuses = [
            check["status"]
            for check in checks
        ]

        if statuses and all(
            x == "PASS"
            for x in statuses
        ):
            overall_status = "PASS"
        elif "FAIL" in statuses:
            overall_status = "FAIL"
        else:
            overall_status = "REVIEW_REQUIRED"

        validations.append({
            "requirement_id": req[
                "requirement_id"
            ],
            "priority": req[
                "priority"
            ],
            "exact_jd_quote": req[
                "exact_jd_quote"
            ],
            "overall_status": overall_status,
            "checks": checks
        })

    # PHASE_B_DOCUMENT_CONSTRAINT_AUTHORITY_V1
    #
    # Explicit document-level constraints normally map to an effective
    # requirement. When a wrapped hard constraint does not map cleanly,
    # preserve it as a supplemental deterministic validation row.
    validated_ids = {
        row.get(
            "requirement_id"
        )
        for row in validations
    }

    for document_constraint in (
        effective_bundle.get(
            "document_constraints",
            [],
        )
        or []
    ):
        policy = document_constraint.get(
            "policy"
        )

        mapped_id = document_constraint.get(
            "mapped_requirement_id"
        )

        if (
            policy == "HARD_BLOCK"
            and (
                not mapped_id
                or mapped_id
                not in validated_ids
            )
        ):
            semantic_id = (
                mapped_id
                or document_constraint.get(
                    "semantic_constraint_id"
                )
            )

            validations.append(
                {
                    "requirement_id":
                        semantic_id,

                    "priority":
                        "P0",

                    "exact_jd_quote":
                        document_constraint.get(
                            "exact_source_quote"
                        ),

                    "overall_status":
                        "FAIL",

                    "checks": [
                        {
                            "constraint_type":
                                "hard_blocker",

                            "status":
                                "FAIL",

                            "reason_code":
                                document_constraint.get(
                                    "reason_code"
                                ),

                            "reason":
                                document_constraint.get(
                                    "deterministic_reason"
                                ),

                            "basis":
                                "IMMUTABLE_RAW_JD",

                            "matched_text":
                                document_constraint.get(
                                    "matched_text"
                                ),
                        }
                    ],
                }
            )

            validated_ids.add(
                semantic_id
            )

        elif (
            policy == "VALIDATE_PROFILE"
            and (
                not mapped_id
                or mapped_id
                not in validated_ids
            )
        ):
            semantic_id = (
                mapped_id
                or document_constraint.get(
                    "semantic_constraint_id"
                )
            )

            validations.append(
                {
                    "requirement_id":
                        semantic_id,

                    "priority":
                        "P0",

                    "exact_jd_quote":
                        document_constraint.get(
                            "exact_source_quote"
                        ),

                    "overall_status":
                        "REVIEW_REQUIRED",

                    "checks": [
                        {
                            "constraint_type":
                                "geographic_residency",

                            "status":
                                "REVIEW_REQUIRED",

                            "reason_code":
                                document_constraint.get(
                                    "reason_code"
                                ),

                            "reason":
                                document_constraint.get(
                                    "deterministic_reason"
                                ),

                            "basis":
                                "CANDIDATE_GEOGRAPHY_VALIDATION_REQUIRED",
                        }
                    ],
                }
            )

            validated_ids.add(
                semantic_id
            )

    output = {
        "schema_version": "constraint-validation-v2",

        "candidate_fact_layers": {
            "artifact_verified": (
                "Specific historical/project evidence."
            ),
            "direct_user_confirmed": (
                "Authoritative candidate facts explicitly "
                "provided by CareerOps, including skill duration "
                "and proficiency."
            ),
            "assumed_market_coverage": (
                "Authorized contextual capability layer; "
                "not silently relabelled as artifact verified."
            )
        },

        "assumed_market_inventory_loaded": bool(
            coverage
        ),

        "source": {
            "constraint_source":
                "jd_semantic_map.json",
            "requirements_fingerprint":
                semantic_fingerprint,
            "current_job_match": True,
            "evidence_map_dependency": False
        },

        "validation_count": len(
            validations
        ),

        "requirements": validations
    }

    OUT.write_text(
        json.dumps(
            output,
            indent=2,
            ensure_ascii=False
        )
        + "\n"
    )

    print("CONSTRAINT VALIDATION V2: CREATED")

    print("\nDIRECT USER-CONFIRMED DURATIONS:")

    for skill, item in facts[
        "skill_duration_years"
    ].items():
        print(
            f"  {skill}: {item['years']:g} years"
        )

    print("\nVALIDATIONS:")

    for item in validations:

        print(
            f"\n{item['requirement_id']} "
            f"{item['priority']} | "
            f"{item['overall_status']}"
        )

        print(
            " ",
            item["exact_jd_quote"]
        )

        for check in item["checks"]:

            print(
                "  ",
                check["constraint_type"],
                "=>",
                check["status"]
            )

            if (
                check["constraint_type"]
                == "experience_years"
            ):
                for s in check[
                    "skill_duration_checks"
                ]:
                    print(
                        "     ",
                        s["skill"],
                        "=>",
                        s["status"],
                        (
                            f"| {s.get('years')} years"
                            if "years" in s
                            else ""
                        )
                    )

                a = check.get(
                    "analytics_duration_check"
                )

                if a:
                    print(
                        "      analytics =>",
                        a["status"],
                        (
                            f"| {a.get('years')} years "
                            f"via {a.get('supporting_skill')}"
                            if "years" in a
                            else ""
                        )
                    )

    print(
        "\nFACTS:",
        FACTS_PATH.relative_to(ROOT)
    )

    print(
        "OUTPUT:",
        OUT.relative_to(ROOT)
    )


if __name__ == "__main__":
    from careerops_requirement_authority import run_guarded
    run_guarded(main, RUNTIME, "careerops_validate_constraints.py")
