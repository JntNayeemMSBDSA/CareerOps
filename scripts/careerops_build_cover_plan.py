#!/usr/bin/env python3

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from careerops_requirement_regeneration import canonical_ledger_path

from careerops_runtime import runtime_dir

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = runtime_dir(ROOT)

COMPACT_JSON = RUNTIME / "compact_generation_packet.json"
REQUIREMENTS_JSON = canonical_ledger_path(RUNTIME)
ROLE_JSON = RUNTIME / "role_routing.json"
EXPERIENCE_JSON = RUNTIME / "experience_selection.json"
PROJECT_JSON = RUNTIME / "project_selection.json"
EVIDENCE_MAP_JSON = RUNTIME / "requirement_evidence_map.json"
RESUME_CANDIDATE_JSON = RUNTIME / "generated_resume_content_pair_candidate.json"
COVER_CANDIDATE_JSON = RUNTIME / "generated_cover_letter_pair_candidate.json"
OUTPUT_JSON = RUNTIME / "cover_plan.json"

SCHEMA_VERSION = "careerops-cover-plan-v2"

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "in", "into", "is", "it", "of", "on", "or", "such", "that", "the",
    "their", "this", "to", "with", "will", "work", "works", "working",
    "ability", "including", "required", "position", "responsibilities",
    "general", "direction", "strong", "excellent", "current"
}

METRIC_PRIORITY = {
    "revenue": 100,
    "cost": 95,
    "accuracy": 94,
    "f1": 94,
    "recall": 93,
    "precision": 93,
    "coverage": 92,
    "reduction": 91,
    "improvement": 90,
    "throughput": 89,
    "latency": 88,
    "encounters": 86,
    "records": 84,
    "rows": 83,
    "files": 87,
    "gb": 72,
    "facilities": 70,
    "npis": 70,
}

METHOD_PRIORITY = [
    "fail-closed",
    "schema",
    "structural missingness",
    "crosswalk",
    "relational",
    "bridge",
    "grain",
    "reconciliation",
    "provenance",
    "validation",
    "checksum",
    "mapping coverage",
    "checkpoint",
    "atomic",
    "partition",
    "normalization",
    "query",
    "etl",
]

WORKFLOW_SIGNAL_WEIGHTS = {
    "data quality": 6.0,
    "database changes": 6.0,
    "state reporting": 6.0,
    "submission": 4.5,
    "accuracy": 4.0,
    "governance": 4.0,
    "privacy": 4.0,
    "user needs": 4.0,
    "input and output requirements": 4.0,
    "subject matter expert": 4.0,
    "workflow": 4.0,
    "new processes": 4.0,
    "database": 3.0,
    "query": 3.0,
    "report": 2.5,
    "visualization": 2.5,
    "data request": 2.5,
    "recurring": 2.0,
    "annual": 2.0,
    "research": 2.0,
    "decision-making": 2.0,
    "strategic planning": 2.0,
    "audit": 2.0,
    "technical and non-technical": 2.0,
    "deadline": 1.5,
}

ACTION_VERBS = {
    "collects", "collect", "analyzes", "analyze", "compiles", "compile",
    "creates", "create", "develops", "develop", "maintains", "maintain",
    "queries", "query", "reviews", "review", "verifies", "verify",
    "submits", "submit", "documents", "document", "communicates",
    "communicate", "evaluates", "evaluate", "improves", "improve",
    "researches", "research", "fulfills", "fulfill", "confers",
    "adheres", "works", "updates", "update",
}

VALIDATION_TERMS = (
    "validation",
    "reconciliation",
    "checksum",
    "sha-256",
    "coverage",
    "audit",
    "qa",
    "data quality",
    "data-quality",
    "quality check",
    "quality control",
    "test",
    "holdout",
    "cross-validation",
)

OUTPUT_TERMS = (
    "release",
    "dataset",
    "fact",
    "bridge",
    "master",
    "cohort",
    "matrix",
    "report",
    "dashboard",
    "model",
    "forecast",
    "workflow",
    "mart",
    "workbook",
    "snapshot",
)

#
# Verified evidence was intentionally authored across several project /
# experience schemas. Cover planning must interpret semantic section
# families rather than requiring one literal markdown heading.
METHOD_SECTION_FAMILY = (
    "Technical methods",
    "Methods",
    "Statistical methods",
)

OUTPUT_SECTION_FAMILY = (
    "Core outputs",
    "Outputs",
    "Deliverables",
    "Data model",
    "Selected modeled outputs",
)

METRIC_SECTION_FAMILY = (
    "Data and scale",
    "Historical facts",
    "Historical scale and outcomes",
    "Metrics",
    "Results",
    "Outcomes",
    "Selected modeled outputs",
    "Selected outputs",
)


def load_json(path, required=True):
    if not path.exists():
        if required:
            raise SystemExit(f"Missing required file: {path}")
        return None
    return json.loads(path.read_text())


def normalize_space(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_key(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def dedupe(items):
    seen = set()
    out = []
    for item in items:
        key = json.dumps(item, sort_keys=True) if isinstance(item, dict) else str(item)
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def tokenize(text):
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9+#./-]*", str(text).lower())
    return {
        w for w in words
        if len(w) >= 4 and w not in STOPWORDS
    }


def parse_markdown_sections(text):
    sections = {}
    current = "__root__"

    for raw in str(text).splitlines():
        line = raw.strip()
        if not line:
            continue

        heading = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if heading:
            current = normalize_key(heading.group(1))
            sections.setdefault(current, [])
            continue

        sections.setdefault(current, []).append(line)

    return sections


def bullet_texts(lines):
    out = []
    for line in lines or []:
        m = re.match(r"^-\s+(.*)$", line.strip())
        if m:
            out.append(normalize_space(m.group(1)))
    return out


def parse_bold_fields(text):
    fields = {}
    for raw in str(text).splitlines():
        line = raw.strip()
        m = re.match(r"^\*\*(.+?):\*\*\s*(.+)$", line)
        if m:
            fields[normalize_key(m.group(1))] = normalize_space(m.group(2))
    return fields


def strip_markdown(text):
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", str(text))
    text = re.sub(r"`(.+?)`", r"\1", text)
    return normalize_space(text)


def section_lines(sections, *names):
    for name in names:
        key = normalize_key(name)
        if key in sections:
            return sections[key]
    return []

def collect_section_lines(sections, *names):
    """
    Return the union of all matching semantic section aliases.

    Unlike section_lines(), this intentionally does not stop after the
    first match because one evidence record may contain both Methods and
    Statistical methods, or Results plus another metric section.
    """
    out = []

    for name in names:
        key = normalize_key(name)

        for line in sections.get(key, []):
            if line not in out:
                out.append(line)

    return out


def extract_story_material(sections, fields):
    method_lines = bullet_texts(
        collect_section_lines(
            sections,
            *METHOD_SECTION_FAMILY,
        )
    )

    explicit_output_lines = bullet_texts(
        collect_section_lines(
            sections,
            *OUTPUT_SECTION_FAMILY,
        )
    )

    # Some evidence records encode concrete artifacts inside a Methods
    # section (for example a dashboard, mart, workbook, or snapshot).
    # choose_outputs() remains conservative and only keeps artifact-like
    # terms from OUTPUT_TERMS.
    output_source = dedupe(
        explicit_output_lines
        + method_lines
    )

    metric_lines = collect_section_lines(
        sections,
        *METRIC_SECTION_FAMILY,
    )

    methods = choose_methods(
        method_lines,
        maximum=5,
    )

    # Quality controls may be recorded under Tools/platforms as well as
    # Methods. Preserve the exact source wording when selecting them.
    control_lines=bullet_texts(collect_section_lines(sections,'Tools and platforms','Validation','Data quality controls'))
    validation = choose_validation(method_lines + control_lines, output_source)
    for item in method_lines + control_lines:
        if any(term in item.lower() for term in ['source profiling','safe numeric conversion','null standardization','qa queries','assumption registry with source']):
            if item not in validation:validation.append(item)


    outputs = choose_outputs(output_source)
    # Explicit modeled outputs are valid outcomes of an analytical model.
    # They retain their source labels and must never become actual revenue.
    modeled_outputs=bullet_texts(collect_section_lines(sections,'Selected modeled outputs'))
    outputs=dedupe(outputs+modeled_outputs)


    metrics = parse_metrics(
        metric_lines
    )

    objective = normalize_space(
        fields.get("problem objective")
        or fields.get("objective")
        or fields.get("problem")
    )

    # These are the deterministic plan-side prerequisites implied by
    # Cover Gate V2. If they cannot be populated, the writer would be
    # asked to satisfy a contract that the planner itself did not supply.
    gate_plan_viable = (
        len(methods) >= 2
        and len(validation) >= 2
        and len(outputs) >= 1
        and len(metrics) >= 2
    )

    return {
        "methods": methods,
        "validation": validation,
        "outputs": outputs,
        "metrics": metrics,
        "objective": objective,
        "gate_plan_viable": gate_plan_viable,
    }


def requirement_centrality(requirements):
    p1 = [
        r for r in requirements
        if r.get("priority") == "P1"
        and str(r.get("section", "")).lower() == "responsibilities"
    ]

    if not p1:
        p1 = [
            r for r in requirements
            if r.get("priority") in {"P0", "P1"}
        ]

    token_sets = {
        r["requirement_id"]:
            tokenize(r.get("normalized_requirement", ""))
        for r in p1
    }

    scored = []

    for idx, req in enumerate(p1):
        rid = req["requirement_id"]
        text = normalize_space(
            req.get("normalized_requirement", "")
        )
        low = text.lower()
        mine = token_sets[rid]

        overlap = 0.0
        for other_id, other in token_sets.items():
            if other_id == rid or not mine or not other:
                continue

            overlap += (
                len(mine & other)
                / max(1, len(mine | other))
            )

        exact_density = (
            len(req.get("exact_tools_technologies", []))
            + len(req.get("exact_work_products", []))
            + len(req.get("exact_methods", []))
        )

        workflow_score = sum(
            weight
            for signal, weight in WORKFLOW_SIGNAL_WEIGHTS.items()
            if signal in low
        )

        action_count = sum(
            1
            for token in tokenize(text)
            if token in ACTION_VERBS
        )

        # REQ-001-like overview responsibilities often summarize the job,
        # so preserve a modest first-responsibility bonus without allowing
        # it to dominate specific operational requirements.
        overview_bonus = 3.0 if idx == 0 else 0.0

        # Very short requirements can be important, but lexical repetition
        # alone should not make a generic recurring task outrank a richer
        # quality/governance/workflow responsibility.
        depth_bonus = min(len(mine), 35) / 7.0

        # An explicit responsibility time allocation is a source-authorized
        # principal-work signal, stronger than keyword density.
        allocation = re.search(r"(?:-|:)\s*(\d{1,2})\s*%\s*$", text)
        allocation_weight = float(allocation[1]) if allocation else 0.0
        centrality = (
            allocation_weight
            + overlap * 6.0
            + exact_density * 1.5
            + workflow_score
            + min(action_count, 6) * 0.8
            + overview_bonus
            + depth_bonus
        )

        scored.append({
            "requirement": req,
            "centrality_score":
                round(centrality, 4),
            "jd_order": idx,
        })

    scored.sort(
        key=lambda x: (
            -x["centrality_score"],
            x["jd_order"],
        )
    )

    chosen = scored[:5]
    chosen.sort(key=lambda x: x["jd_order"])
    return chosen


def evidence_map_index(mapping):
    return {
        item.get("requirement_id"): item
        for item in mapping.get("requirements", [])
        if item.get("requirement_id")
    }


def candidate_scores(
    critical,
    mapping_idx,
    experience,
    projects,
    compact,
):
    """
    Rank cover-story candidates without creating a second evidence-selection engine.

    Existing experience_selection/project_selection already own deep relevance.
    The cover planner therefore uses:
      1. coverage of the CENTRAL target requirements,
      2. existing upstream selection strength,
      3. a modest preference for actual experience when otherwise comparable,
      4. raw mapper evidence scores only as a tiny tiebreak/diagnostic signal.

    This prevents a project with high term-level mapper scores from displacing
    a more analogous already-selected experience merely because mapper scores
    happen to be numerically larger.
    """

    selected_ids = set()

    exp_blocks = {}
    for block in experience.get("selected_experience_blocks", []):
        for eid in block.get("evidence_ids", []):
            selected_ids.add(eid)
            exp_blocks[eid] = block

    project_rows = {}
    for row in projects.get("selected_projects", []):
        eid = row.get("entity_id")
        if eid:
            selected_ids.add(eid)
            project_rows[eid] = row

    scores = {}

    for eid in selected_ids:
        source_type = (
            "experience"
            if eid in exp_blocks
            else "project"
        )

        if eid in exp_blocks:
            upstream_selection_score = float(
                exp_blocks[eid].get(
                    "selection_score",
                    0.0,
                )
            )
            p0_p1_support_count = len(
                exp_blocks[eid].get(
                    "supported_p0_p1_ids",
                    [],
                )
            )
        else:
            upstream_selection_score = float(
                project_rows[eid].get(
                    "score",
                    0.0,
                )
            )
            p0_p1_support_count = len(
                project_rows[eid].get(
                    "supported_p0_p1_ids",
                    [],
                )
            )

        evidence_text = (
            compact.get("evidence", {}).get(eid)
            or ""
        )

        evidence_sections = parse_markdown_sections(
            evidence_text
        )

        evidence_fields = parse_bold_fields(
            evidence_text
        )

        story_material = extract_story_material(
            evidence_sections,
            evidence_fields,
        )

        story_methods = story_material["methods"]
        story_validation = story_material["validation"]
        story_outputs = story_material["outputs"]
        story_metrics = story_material["metrics"]
        story_objective = story_material["objective"]
        story_gate_plan_viable = story_material[
            "gate_plan_viable"
        ]

        # Bounded cover-story readiness.
        #
        # Critical JD coverage remains the dominant signal.
        # This component only rewards evidence that can support
        # the actual Cover Planner V2 story contract:
        # reasoning + implementation + validation + output.
        story_readiness_score = (
            min(len(story_methods), 4) * 2.0
            + min(len(story_validation), 3) * 3.0
            + min(len(story_outputs), 3) * 1.0
            + (2.0 if story_objective else 0.0)
        )

        principal=compact.get('requirements',{}).get('requirements',[])
        target_work=' '.join(x.get('exact_quote','') for x in principal if x.get('priority')=='P1').lower() or ' '.join(x['requirement'].get('exact_quote','') for x in critical).lower()
        output_work=' '.join([story_objective]+story_outputs).lower()
        families=[('financial','revenue','margin','profit','budget','pricing'),('forecast','demand','sales','customer','retail','commercial','prospect','account'),('research','patient','health','cohort','encounter'),('dashboard','report','stakeholder','executive'),('pipeline','etl','schema','database','warehouse')]
        target_families={i for i,terms in enumerate(families) if sum(t in target_work for t in terms)>=2}
        output_families={i for i,terms in enumerate(families) if sum(t in output_work for t in terms)>=2}
        output_similarity=len(target_families & output_families)/max(1,len(target_families))
        scores[eid] = {
            'target_output_similarity':round(output_similarity,4),
            "evidence_id": eid,
            "source_type": source_type,
            "upstream_selection_score":
                upstream_selection_score,
            "p0_p1_support_count":
                p0_p1_support_count,

            "critical_requirements_supported": [],
            "critical_requirement_count": 0,

            # Sum of target-requirement centrality for requirements
            # that this evidence actually supports.
            "critical_coverage_weight": 0.0,

            # Mapper scores are retained only as a low-impact
            # diagnostic/tiebreak signal.
            "mapper_support_quality": 0.0,

            # Cover-specific readiness is intentionally bounded.
            "story_method_count":
                len(story_methods),
            "story_validation_count":
                len(story_validation),
            "story_output_count":
                len(story_outputs),
            "story_metric_count":
                len(story_metrics),
            "story_has_objective":
                bool(story_objective),
            "story_gate_plan_viable":
                bool(story_gate_plan_viable),
            "story_readiness_score":
                round(story_readiness_score, 4),
        }

    for critical_row in critical:
        req = critical_row["requirement"]
        rid = req["requirement_id"]
        centrality = float(
            critical_row.get(
                "centrality_score",
                0.0,
            )
        )

        mapped = mapping_idx.get(rid, {})

        for candidate in mapped.get(
            "verified_evidence_candidates",
            [],
        ):
            eid = candidate.get("entity_id")

            if eid not in scores:
                continue

            scores[eid][
                "critical_requirements_supported"
            ].append(rid)

            scores[eid][
                "critical_coverage_weight"
            ] += centrality

            # Cap each mapper contribution. These scores were built for
            # evidence mapping, not for replacing upstream selection.
            scores[eid][
                "mapper_support_quality"
            ] += min(
                float(candidate.get("score", 0.0)),
                5.0,
            )

    critical_total_weight = sum(
        float(row.get("centrality_score", 0.0))
        for row in critical
    )

    critical_total_count = len(critical)

    for row in scores.values():
        supported = dedupe(
            row["critical_requirements_supported"]
        )

        row[
            "critical_requirements_supported"
        ] = supported

        row[
            "critical_requirement_count"
        ] = len(supported)

        row[
            "critical_coverage_ratio"
        ] = round(
            len(supported)
            / max(1, critical_total_count),
            4,
        )

        row[
            "critical_coverage_weight_ratio"
        ] = round(
            row["critical_coverage_weight"]
            / max(1.0, critical_total_weight),
            4,
        )

        # Experience and project evidence compete symmetrically.
        # Source type alone must never increase cover-story relevance.
        experience_bonus = 0.0

        # Coverage is the dominant cover-story requirement.
        # Upstream selection remains the relevance authority.
        # Mapper quality is intentionally tiny.
        row["planner_score"] = round(
            row[
                "critical_coverage_weight_ratio"
            ] * 100.0
            + row[
                "critical_coverage_ratio"
            ] * 40.0
            + min(
                row["upstream_selection_score"],
                150.0,
            ) * 0.35
            + min(
                row["p0_p1_support_count"],
                12,
            ) * 1.5
            + min(
                row["mapper_support_quality"],
                25.0,
            ) * 0.20
            + min(
                row["story_readiness_score"],
                22.0,
            )
            + experience_bonus,
            4,
        )

    return sorted(
        scores.values(),
        key=lambda x: (
            -x["target_output_similarity"],
            -x["critical_coverage_weight_ratio"],
            -x["critical_coverage_ratio"],
            -x["planner_score"],
            -x["upstream_selection_score"],
            x["evidence_id"],
        ),
    )


def evidence_context(primary_id, experience, projects):
    for block in experience.get("selected_experience_blocks", []):
        if primary_id in block.get("evidence_ids", []):
            return {
                "context_type": "research_or_employment_experience",
                "organization": block.get("organization"),
                "title": block.get("title"),
                "period": block.get("period"),
                "block_id": block.get("block_id"),
            }

    for row in projects.get("selected_projects", []):
        if row.get("entity_id") == primary_id:
            return {
                "context_type": "project",
                "organization": row.get("brand_context") or row.get("canonical_name"),
                "title": row.get("visible_name") or row.get("canonical_name"),
                "period": None,
                "block_id": None,
                "relationship_boundary": row.get("relationship_boundary"),
            }

    return {
        "context_type": "unknown",
        "organization": None,
        "title": None,
        "period": None,
        "block_id": None,
    }


def primary_mapping_records(primary_id, critical, mapping_idx):
    out = []

    for row in critical:
        req = row["requirement"]
        rid = req["requirement_id"]
        mapped = mapping_idx.get(rid, {})

        candidate = next(
            (
                c for c in mapped.get("verified_evidence_candidates", [])
                if c.get("entity_id") == primary_id
            ),
            None,
        )

        out.append({
            "requirement_id": rid,
            "priority": req.get("priority"),
            "exact_jd_quote": req.get("exact_quote"),
            "normalized_requirement": req.get("normalized_requirement"),
            "centrality_score": row["centrality_score"],
            "primary_evidence_support": bool(candidate),
            "primary_evidence_score": (
                candidate.get("score") if candidate else None
            ),
            "coverage_state": mapped.get("coverage_state"),
            "residual_gap": bool(mapped.get("residual_gap")),
        })

    return out


def choose_methods(methods, maximum=5):
    if not methods:
        return []

    scored = []
    for idx, item in enumerate(methods):
        low = item.lower()
        score = 0

        for rank, term in enumerate(METHOD_PRIORITY):
            if term in low:
                score += len(METHOD_PRIORITY) - rank

        scored.append((score, -idx, item))

    scored.sort(reverse=True)

    chosen = [item for score, _, item in scored if score > 0][:maximum]

    if len(chosen) < min(maximum, len(methods)):
        for item in methods:
            if item not in chosen:
                chosen.append(item)
            if len(chosen) >= maximum:
                break

    return chosen[:maximum]


def choose_validation(methods, core_outputs):
    pool = dedupe(methods + core_outputs)
    scored = []

    weights = {
        "independent release validation": 100,
        "source-to-output record-count reconciliation": 95,
        "reconciliation": 90,
        "mapping-coverage measurement": 85,
        "mapping coverage": 85,
        "sha-256": 80,
        "checksum": 75,
        "audit": 70,
        "validation": 65,
        "qa": 60,
        "test": 55,
        "holdout": 55,
        "cross-validation": 55,
    }

    for idx, item in enumerate(pool):
        low = item.lower()

        if not any(
            term in low
            for term in VALIDATION_TERMS
        ):
            continue

        score = max(
            (
                weight
                for term, weight in weights.items()
                if term in low
            ),
            default=1,
        )

        scored.append((score, -idx, item))

    scored.sort(reverse=True)

    return [
        item
        for _, _, item in scored[:5]
    ]


def choose_outputs(core_outputs):
    chosen = []

    for item in core_outputs:
        low = item.lower()
        if any(term in low for term in OUTPUT_TERMS):
            chosen.append(item)

    return dedupe(chosen)[:5]


def parse_metrics(data_lines):
    metrics = []

    for idx, raw in enumerate(data_lines or []):
        text = strip_markdown(raw)
        text = re.sub(r"^-\s*", "", text)

        if ":" not in text:
            continue

        key, value = text.split(":", 1)
        key = normalize_space(key)
        value = normalize_space(value)

        if not re.search(r"\d", value):
            continue

        score = 0
        key_low = key.lower()

        for term, weight in METRIC_PRIORITY.items():
            if term in key_low:
                score = max(score, weight)

        if score == 0:
            score = max(10, 50 - idx)

        metrics.append({
            "label": key,
            "value": value,
            "raw_supported_fact": f"{key}: {value}",
            "priority_score": score,
        })

    metrics.sort(
        key=lambda x: (-x["priority_score"], x["label"].lower())
    )

    selected = []
    labels = set()

    for metric in metrics:
        family = re.sub(r"[^a-z]+", " ", metric["label"].lower()).strip()
        if family in labels:
            continue
        labels.add(family)
        selected.append(metric)
        if len(selected) == 2:
            break

    return selected


def resume_overlap(primary_id, primary_context, resume):
    exclusions = []

    block_id = primary_context.get("block_id")

    if block_id:
        for block in resume.get("experience", []):
            if block.get("block_id") == block_id:
                for bullet in block.get("bullets", []):
                    exclusions.append({
                        "location": f"resume.experience.{block_id}",
                        "text": bullet,
                        "rule":
                            "Fact may be reused, but cover must add constraint, "
                            "decision rationale, implementation reasoning, validation, "
                            "or target-role application rather than paraphrasing this bullet.",
                    })

    for project in resume.get("projects", []):
        if project.get("entity_id") == primary_id:
            for bullet in project.get("bullets", []):
                exclusions.append({
                    "location": f"resume.projects.{primary_id}",
                    "text": bullet,
                    "rule":
                        "Fact may be reused, but cover must add reasoning or context "
                        "that the resume bullet does not already provide.",
                })

    summary = normalize_space(resume.get("summary"))
    if summary and primary_context.get("organization"):
        org_words = tokenize(primary_context["organization"])
        if org_words & tokenize(summary):
            exclusions.append({
                "location": "resume.summary",
                "text": summary,
                "rule":
                    "Do not reproduce the summary's framing. Use the primary story "
                    "to show how the work was reasoned through.",
            })

    return exclusions


def identity(args, requirements, compact, existing_cover):
    position = (
        args.position
        or requirements.get("target_role_title_candidate")
        or None
    )

    company = args.company
    company_source = "CLI" if company else None

    #
    # URL intake may intentionally leave legacy top-level company
    # fields empty while current-requisition structured identity
    # evidence is resolved at HIGH confidence. Use that canonical
    # identity before considering historical/existing-cover fallback.
    if not company:
        target_job = (
            compact.get("target_job", {})
            or {}
        )

        identity_company = (
            target_job
            .get("identity_evidence", {})
            .get("company", {})
            or {}
        )

        candidate_company = normalize_space(
            identity_company.get("value")
        )

        if (
            candidate_company
            and str(
                identity_company.get("status", "")
            ).upper() == "RESOLVED_HIGH"
            and str(
                identity_company.get("confidence", "")
            ).upper() == "HIGH"
            and identity_company.get(
                "confirmed_in_current_job"
            ) is True
        ):
            company = candidate_company
            company_source = (
                "target_job.identity_evidence.company"
            )

    # Never reuse a staged cover's employer merely because the title matches.
    # A previous Research Analyst application could belong to another employer.
    # Staged-cover fallback is allowed only if that employer name is visibly
    # present in the CURRENT job intake.
    if not company and existing_cover:
        candidate_company = normalize_space(
            existing_cover.get("company")
        )
        candidate_position = normalize_key(
            existing_cover.get("position")
        )
        current_position = normalize_key(position)

        target_job = compact.get("target_job", {})
        current_job_text = " ".join([
            str(target_job.get("source_name", "")),
            str(target_job.get("source_url", "")),
            str(target_job.get("raw_jd_text", "")),
        ]).lower()

        company_confirmed_in_current_job = (
            candidate_company
            and candidate_company.lower() in current_job_text
        )

        position_matches = (
            candidate_position
            and current_position
            and (
                candidate_position == current_position
                or candidate_position in current_position
                or current_position in candidate_position
            )
        )

        if (
            company_confirmed_in_current_job
            and position_matches
        ):
            company = candidate_company
            company_source = (
                "CURRENT_JD_CONFIRMED_STAGED_IDENTITY_FALLBACK"
            )

    return {
        "company": company,
        "position": position,
        "company_source":
            company_source or "UNRESOLVED",
        "position_source": (
            "CLI"
            if args.position
            else "jd_requirements.target_role_title_candidate"
        ),
    }


def build_employer_need(critical_records):
    texts = [row.get('normalized_requirement', '') for row in critical_records]
    joined = ' '.join(text for text in texts if isinstance(text, str)).lower()

    def hit(needles, minimum=1):
        return sum((1 for needle in needles if needle in joined)) >= minimum
    theme_specs = [('cost and financial analysis', ('cost', 'financial', 'variance'), 2), ('budgeting, forecasting, and KPI measurement', ('budget', 'forecast', 'kpi'), 2), ('dashboarding and reporting', ('dashboard', 'power bi', 'spotfire', 'report'), 2), ('data quality and integrity', ('data quality', 'accuracy', 'consistency', 'integrity', 'validation'), 2), ('recurring performance reporting', ('weekly', 'monthly', 'quarterly', 'annual', 'recurring', 'performance report'), 2), ('SQL and enterprise data analysis', ('sql', 'enterprise dataset', 'query'), 1), ('data collection and analysis', ('collect', 'analy'), 1), ('database and query work', ('database', 'query'), 1), ('stakeholder-defined requirements', ('user needs', 'input and output requirements', 'stakeholder', 'subject matter', 'personnel'), 1), ('workflow and process improvement', ('workflow', 'new processes', 'continuous improvement', 'process improvement'), 1), ('data governance', ('governance',), 1), ('privacy controls', ('privacy', 'ferpa'), 1), ('technical and non-technical communication', ('technical and non-technical', 'communication', 'presentation'), 1)]
    themes = [label for label, needles, minimum in theme_specs if hit(needles, minimum)][:5]
    if not themes:
        themes = ['reliable analysis and reporting']
    if len(themes) == 1:
        thesis = f'Deliver {themes[0]}.'
    else:
        thesis = 'Deliver reliable ' + ', '.join(themes[:-1]) + ', and ' + themes[-1] + '.'
    return {'thesis': thesis, 'principal_themes': themes, 'authority': 'TARGET_JD'}


def target_application(primary_id, critical_map, methods, validation):
    supported = [
        row for row in critical_map
        if row.get("primary_evidence_support")
    ]

    target_requirements = [
        {
            "requirement_id": row["requirement_id"],
            "target_responsibility": row["normalized_requirement"],
        }
        for row in supported[:4]
    ]

    approach = []

    if methods:
        approach.extend(methods[:3])

    if validation:
        approach.extend(validation[:2])

    return {
        "type": "FUTURE_APPLICATION_NOT_HISTORICAL_CLAIM",
        "target_requirements": target_requirements,
        "past_reasoning_to_apply": dedupe(approach),
        "instruction":
            "Explain operationally how the reasoning used in the primary evidence "
            "would be applied to the listed target responsibilities. Do not claim "
            "that target-domain work already occurred unless candidate evidence proves it.",
    }


def interest_reason(identity_data, critical_records):

    #
    # An interest reason labeled TARGET_JD / JD_SPECIFIC must be
    # grounded in actual target-JD requirement text.
    #
    # Do not infer a larger prewritten concept from partial keyword
    # matches. For example:
    #   "recurring" must not become "recurring and annual reporting"
    #   "data quality" must not become "formal submissions"
    #
    # The writer may paraphrase these requirements naturally later,
    # but the planner's factual grounding remains the employer's own JD.
    company = normalize_space(
        identity_data.get("company")
    )
    position = normalize_space(
        identity_data.get("position")
    )

    subject = (
        f"{company}'s {position} role"
        if company and position
        else position or "this role"
    )

    responsibility_records = [
        row
        for row in critical_records
        if normalize_key(
            row.get("section", "")
        ) == "responsibilities"
        and normalize_space(
            row.get("normalized_requirement", "")
        )
    ]

    source_records = (
        responsibility_records
        if responsibility_records
        else [
            row
            for row in critical_records
            if normalize_space(
                row.get("normalized_requirement", "")
            )
        ]
    )

    grounding = []

    for row in source_records:
        requirement_id = normalize_space(
            row.get("requirement_id", "")
        )
        requirement_text = normalize_space(
            row.get("normalized_requirement", "")
        )

        if not requirement_text:
            continue

        item = {
            "requirement_id": requirement_id,
            "requirement_text": requirement_text,
            "section": normalize_space(
                row.get("section", "")
            ),
            "priority": normalize_space(
                row.get("priority", "")
            ),
        }

        if item not in grounding:
            grounding.append(item)

        if len(grounding) >= 2:
            break

    if grounding:
        quoted_work = " ".join(
            item["requirement_text"].rstrip(".") + "."
            for item in grounding
        )

        reason = (
            f"Explain WHY this concrete target work interests the candidate: which stated stakeholder or decision it serves and how that connects to the selected verified story. Do not merely restate duties. Grounding: "
            f"The specific interest point is the concrete work defined "
            f"in {subject}: {quoted_work}"
        )

        confidence = "JD_SPECIFIC"

    else:
        reason = (
            f"The interest point is the analytical work described in "
            f"{subject}."
        )

        # Fail safely rather than claiming JD-specific grounding when
        # there is no specific critical requirement available.
        confidence = "JD_GENERAL"

    return {
        "reason": reason,
        "source": "TARGET_JD",
        "confidence": confidence,
        "grounding_requirement_ids": [
            item["requirement_id"]
            for item in grounding
            if item["requirement_id"]
        ],
        "grounding_requirement_texts": [
            item["requirement_text"]
            for item in grounding
        ],
        "swap_test_note":
            "Interest grounding comes directly from selected critical "
            "target-JD requirements. No unmatched workflow concept may "
            "be introduced by the planner.",
    }


def build_claim_ledger(
    primary_id,
    evidence_type,
    context,
    objective,
    methods,
    validation,
    outputs,
    metrics,
    boundaries,
    target_requirement_ids,
):
    claims = []

    def add(kind, fact, metric=None, tool_method=None):
        if not fact:
            return

        claims.append({
            "claim_id": f"COVER-{len(claims) + 1:03d}",
            "claim_kind": kind,
            "planned_fact": fact,
            "evidence_id": primary_id,
            "evidence_type": evidence_type,
            "supported_fact": fact,
            "metric": metric,
            "tool_or_method": tool_method,
            "work_context": context,
            "ownership": "USE_EXISTING_CANDIDATE_AUTHORITY",
            "reconstruction_boundary": boundaries,
            "target_jd_requirement_ids": target_requirement_ids,
        })

    add("problem_objective", objective)

    for item in methods[:4]:
        add(
            "implementation_or_judgment",
            item,
            tool_method=item,
        )

    for item in validation[:3]:
        add(
            "validation",
            item,
            tool_method=item,
        )

    for item in outputs[:3]:
        add("output", item)

    for metric in metrics:
        add(
            "numerical_anchor",
            metric["raw_supported_fact"],
            metric={
                "label": metric["label"],
                "value": metric["value"],
                "interpretation": "SCALE_OR_COMPLEXITY_UNLESS_EVIDENCE_SAYS_OTHERWISE",
            },
        )

    return claims


def main():
    parser = argparse.ArgumentParser(
        description="Build deterministic Cover Planner V2 output."
    )
    parser.add_argument("--company")
    parser.add_argument("--position")
    parser.add_argument(
        "--output",
        default=str(OUTPUT_JSON),
    )
    args = parser.parse_args()

    compact = load_json(COMPACT_JSON)
    requirements = load_json(REQUIREMENTS_JSON)
    role = load_json(ROLE_JSON)
    experience = load_json(EXPERIENCE_JSON)
    projects = load_json(PROJECT_JSON)
    mapping = load_json(EVIDENCE_MAP_JSON)
    # In pair-generation mode the resume candidate does not exist yet.
    # Cover planning must therefore be able to run from deterministic
    # application/evidence state alone. Actual resume-vs-cover overlap
    # is enforced after the pair writer by Cover Gate V2.
    resume = (
        load_json(
            RESUME_CANDIDATE_JSON,
            required=False
        )
        or {}
    )
    existing_cover = load_json(
        COVER_CANDIDATE_JSON,
        required=False
    )

    identity_data = identity(
        args,
        requirements,
        compact,
        existing_cover,
    )

    critical = requirement_centrality(
        requirements.get("requirements", [])
    )

    critical_records = [
        {
            "requirement_id": row["requirement"]["requirement_id"],
            "priority": row["requirement"].get("priority"),
            "section": row["requirement"].get("section"),
            "exact_jd_quote": row["requirement"].get("exact_quote"),
            "normalized_requirement":
                row["requirement"].get("normalized_requirement") or row['requirement'].get('exact_quote', ''),
            "centrality_score": row["centrality_score"],
        }
        for row in critical
    ]

    mapping_idx = evidence_map_index(mapping)

    ranked_candidates = candidate_scores(
        critical,
        mapping_idx,
        experience,
        projects,
        compact,
    )

    if not ranked_candidates:
        raise SystemExit(
            "No selected evidence candidates available for cover planning."
        )

    #
    # Preserve dynamic relevance ranking, but only among evidence records
    # capable of supplying the deterministic inputs required by Cover
    # Gate V2. This prevents an internally impossible plan from consuming
    # the single writer call.
    viable_candidates = [
        row
        for row in ranked_candidates
        if row.get(
            "story_gate_plan_viable"
        )
    ]

    if not viable_candidates:
        raise SystemExit(
            "FAIL CLOSED: no selected evidence candidate can supply "
            "the minimum cover-story plan contract "
            "(2 mechanics, 2 validation methods, 1 output, 2 anchors)."
        )

    primary_rank = viable_candidates[0]
    primary_id = primary_rank["evidence_id"]

    evidence_text = compact.get("evidence", {}).get(primary_id)
    if not evidence_text:
        raise SystemExit(
            f"Primary evidence {primary_id} is missing from compact packet."
        )

    sections = parse_markdown_sections(evidence_text)
    fields = parse_bold_fields(evidence_text)

    story_material = extract_story_material(
        sections,
        fields,
    )

    methods = story_material["methods"]
    validation = story_material["validation"]
    outputs = story_material["outputs"]
    metrics = story_material["metrics"]
    objective = story_material["objective"]

    if not story_material["gate_plan_viable"]:
        raise SystemExit(
            "FAIL CLOSED: selected primary evidence no longer satisfies "
            "the Cover Gate V2 plan prerequisites."
        )

    boundaries = bullet_texts(
        collect_section_lines(
            sections,
            "Claim boundaries / integrity rules",
            "Claim boundaries",
            "Integrity rules",
        )
    )
    primary_context = evidence_context(
        primary_id,
        experience,
        projects,
    )

    primary_requirement_map = primary_mapping_records(
        primary_id,
        critical,
        mapping_idx,
    )

    supported_critical = [
        row["requirement_id"]
        for row in primary_requirement_map
        if row["primary_evidence_support"]
    ]

    unsupported_critical = [
        row["requirement_id"]
        for row in primary_requirement_map
        if not row["primary_evidence_support"]
    ]

    overlap = resume_overlap(
        primary_id,
        primary_context,
        resume,
    )

    employer_need = build_employer_need(
        critical_records
    )

    target_role_application = target_application(
        primary_id,
        primary_requirement_map,
        methods,
        validation,
    )

    interest = interest_reason(
        identity_data,
        critical_records,
    )

    metric_anchors = [
        {
            "text": metric["raw_supported_fact"],
            "label": metric["label"],
            "value": metric["value"],
            "source_entity": primary_id,
            "interpretation":
                "SCALE_OR_COMPLEXITY_UNLESS_EVIDENCE_EXPLICITLY_SUPPORTS_OUTCOME",
        }
        for metric in metrics
    ]

    context_type = fields.get("type") or primary_context.get("context_type")
    organization = (
        fields.get("organization context")
        or primary_context.get("organization")
    )
    role_text = fields.get("role") or primary_context.get("title")

    constraint_candidates = []
    for item in methods:
        low = item.lower()
        if any(
            term in low
            for term in (
                "schema",
                "missing",
                "out-of-core",
                "grain",
                "relational",
                "provenance",
            )
        ):
            constraint_candidates.append(item)

    if not constraint_candidates:
        constraint_candidates = methods[:2]

    judgment_candidates = []
    for item in methods:
        low = item.lower()
        if any(
            term in low
            for term in (
                "fail-closed",
                "structural",
                "relational",
                "crosswalk",
                "fallback",
                "threshold",
                "fixed effects",
            )
        ):
            judgment_candidates.append(item)

    if not judgment_candidates:
        judgment_candidates = methods[:2]

    claim_ledger = build_claim_ledger(
        primary_id=primary_id,
        evidence_type=context_type,
        context={
            "organization": organization,
            "role": role_text,
            "context_type": context_type,
        },
        objective=objective,
        methods=methods,
        validation=validation,
        outputs=outputs,
        metrics=metrics,
        boundaries=boundaries,
        target_requirement_ids=supported_critical,
    )

    market_primary = role.get("market_route", {}).get("primary", {})
    application_primary = role.get("application_route", {}).get("primary", {})

    critical_text = " ".join(
        row.get("normalized_requirement", "")
        for row in critical_records
    ).lower()

    concept_specs = [
        (
            "cost and financial analysis",
            ("cost", "financial", "variance"),
            2,
        ),
        (
            "budgeting, forecasting, and KPI measurement",
            ("budget", "forecast", "kpi"),
            2,
        ),
        (
            "Power BI dashboards and reporting",
            ("power bi", "dashboard", "spotfire", "report"),
            2,
        ),
        (
            "data quality and integrity",
            (
                "data quality",
                "accuracy",
                "consistency",
                "integrity",
                "validation",
            ),
            2,
        ),
        (
            "recurring performance reporting",
            (
                "weekly",
                "monthly",
                "quarterly",
                "annual",
                "recurring",
                "performance report",
            ),
            2,
        ),
        (
            "SQL and enterprise data analysis",
            ("sql", "enterprise dataset", "query"),
            1,
        ),
        (
            "stakeholder-defined requirements",
            (
                "user needs",
                "input and output requirements",
                "stakeholder",
                "subject matter",
            ),
            1,
        ),
        (
            "data governance",
            ("data governance",),
            1,
        ),
        (
            "privacy controls",
            ("privacy", "ferpa"),
            1,
        ),
        (
            "technical and non-technical communication",
            (
                "technical and non-technical",
                "communication",
                "presentation",
            ),
            1,
        ),
        (
            "workflow and process improvement",
            (
                "workflow",
                "new processes",
                "continuous improvement",
                "process improvement",
            ),
            1,
        ),
    ]

    jd_concepts = []

    for label, needles, minimum in concept_specs:
        count = sum(
            1 for needle in needles
            if needle in critical_text
        )

        if count >= minimum:
            jd_concepts.append(label)

    jd_concepts = dedupe(jd_concepts)[:6]

    modeled_lines=bullet_texts(collect_section_lines(sections,'Selected modeled outputs'))
    boundary_lines=bullet_texts(collect_section_lines(sections,'Claim boundaries / integrity rules'))
    for anchor in metric_anchors:
        normalized_anchor=normalize_key(anchor.get('text',''))
        direct_modeled=any(normalized_anchor in normalize_key(line) or normalize_key(line) in normalized_anchor for line in modeled_lines if normalize_key(line))
        revenue_boundary=next((line for line in boundary_lines if 'modeled revenue' in line.lower() and 'not actual' in line.lower()),None)
        if direct_modeled or ('revenue' in str(anchor.get('label','')).lower() and revenue_boundary):
            anchor['provenance_class']='MODELED_NOT_ACTUAL_COMPANY_RESULTS'
            anchor['interpretation']='ANALYTICAL_MODEL_OUTPUT; NEVER_ACTUAL_COMPANY_REVENUE_OR_ACHIEVEMENT'
            anchor['source_boundary']=revenue_boundary or 'Selected modeled outputs'
    plan = {
        "schema_version": SCHEMA_VERSION,
        "status": "PLANNED",
        "planner_mode": "DETERMINISTIC_NO_MODEL",
        "target_job": identity_data,

        "routed_role": {
            "application_role":
                application_primary.get("search_title"),
            "market_role":
                market_primary.get("role"),
            "technical_center":
                market_primary.get("technical_center"),
            "confidence":
                market_primary.get("confidence"),
        },

        "employer_need_thesis": employer_need,

        "critical_high_requirements": critical_records,

        "source_claim_boundaries": bullet_texts(collect_section_lines(sections,"Claim boundaries / integrity rules")),
        "candidate_deliverable_state": compact.get("candidate_facts",{}).get("deliverable_state_authority",{}),
        "primary_evidence": {
            "evidence_id": primary_id,
            "planner_score": primary_rank["planner_score"],
            "source_type": primary_rank["source_type"],
            "context_type": context_type,
            "organization": organization,
            "role": role_text,
            "objective": objective,
            "supported_critical_requirement_ids":
                supported_critical,
            "unsupported_critical_requirement_ids":
                unsupported_critical,
            "requirement_map":
                primary_requirement_map,
            "selection_reason":
                "Principal-work output similarity, followed by verified central coverage: highest deterministic story score among already-selected "
                "experience/project evidence that can satisfy the Cover Gate V2 "
                "plan prerequisites. Central JD requirement support and existing "
                "selection strength remain dominant; experience and project "
                "evidence compete symmetrically.",
            "story_gate_plan_viable":
                bool(
                    primary_rank.get(
                        "story_gate_plan_viable"
                    )
                ),
        },

        "secondary_evidence": {
            "use_secondary_story": False,
            "evidence_id": None,
            "reason":
                "No secondary story is authorized by default. Add one only when "
                "a material critical requirement cannot be demonstrated through "
                "the primary story and another already-selected evidence entity "
                "provides verified support.",
        },

        "story": {
            "real_problem": objective,

            "context": {
                "work_type": context_type,
                "organization": organization,
                "role": role_text,
                "preserve_context_exactly": True,
            },

            "constraint_complexity": {
                "supported_evidence_points":
                    dedupe(constraint_candidates)[:3],
                "instruction":
                    "Explain what made the work difficult without inventing a "
                    "constraint not present in the evidence.",
            },

            "judgment_decision": {
                "supported_evidence_points":
                    dedupe(judgment_candidates)[:3],
                "instruction":
                    "Show the technical or analytical decision represented by "
                    "these methods. Do not reduce the explanation to a tool name.",
            },

            "why_that_decision": {
                "instruction":
                    "Explain why the selected method fit the documented problem "
                    "and constraint. Reasoning may connect verified facts, but it "
                    "must not introduce unsupported historical events, outcomes, "
                    "stakeholders, or domain claims.",
            },

            "exact_implementation": {
                "supported_mechanics":
                    methods[:4],
                "instruction":
                    "Use two to four meaningful mechanics. Every mechanic must "
                    "remain attached to this evidence entity.",
            },

            "validation": {
                "supported_validation_methods":
                    validation[:4],
                "instruction":
                    "Explain how reliability was checked. Prefer reconciliation, "
                    "coverage, checksums, audit controls, and independent validation "
                    "when supported.",
            },

            "output": {
                "supported_outputs":
                    outputs[:4],
            },

            "consequence": {
                "supported_interpretation":
                    "The evidence supports a reproducible analytical platform, "
                    "research-ready outputs, and validation/audit artifacts. "
                    "Do not invent a business outcome.",
                "do_not_label_scale_as_impact": True,
            },

            "stakeholder_or_consumer": {
                "supported_context":
                    organization,
                "instruction":
                    "Use only a stakeholder or consumer explicitly supported by "
                    "candidate evidence. Do not invent institutional users.",
            },
        },

        "numerical_anchors": metric_anchors,

        "target_role_application": target_role_application,

        "interest_reason": interest,

        "jd_concepts": {
            "preferred_supported_concepts": jd_concepts,
            "minimum_to_use_naturally": 3,
            "maximum_to_use": 6,
            "keyword_stacking_forbidden": True,
        },

        "resume_overlap_exclusions": overlap,

        "truth_boundaries": {
            "primary_evidence_boundaries": boundaries,
            "domain_drift_rule":
                "Do not relabel the primary evidence domain as the employer's "
                "domain. Transfer methodology and reasoning, not historical context.",
            "capability_rule":
                "Direct-user-confirmed capabilities may establish current skill "
                "possession but may not establish historical use in this evidence "
                "entity without support.",
            "scale_rule":
                "Scale and complexity are not business outcomes.",
            "future_application_rule":
                "Statements about how the approach would be used in the target role "
                "are future application, not claims of prior target-domain experience.",
        },

        "claim_ledger": claim_ledger,

        "writer_contract": {
            "paragraph_count": 3,
            "draft_order": [
                "paragraph_2_core_story",
                "paragraph_1_hook_connection",
                "paragraph_3_target_application_interest",
            ],
            "paragraph_1":
                "Hook with a concrete aspect of the primary story and connect it "
                "to the exact company, position, and central work by the end.",
            "paragraph_2":
                "Develop problem, constraint, judgment, rationale, implementation, "
                "validation, output, and consequence. This is the longest paragraph.",
            "paragraph_3":
                "Map the past reasoning to exact target responsibilities, give the "
                "specific interest reason, then close concisely.",
            "resume_bullet_to_prose_forbidden": True,
            "generic_company_praise_forbidden": True,
            "em_dash_forbidden": True,
            "technical_depth":
                "High but recruiter-readable.",
            "candidate_claims_must_resolve_to_claim_ledger": True,
        },

        "planner_diagnostics": {
            "candidate_ranking": ranked_candidates,
            "primary_evidence_exists_in_compact_packet": True,
            "primary_resume_overlap_items": len(overlap),
            "primary_claim_ledger_items": len(claim_ledger),
            "critical_requirement_count": len(critical_records),
            "primary_supported_critical_count": len(supported_critical),
            "primary_unsupported_critical_count": len(unsupported_critical),
            "model_calls": 0,
            "resume_modified": False,
        },
    }

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = ROOT / output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(plan, indent=2, ensure_ascii=False) + "\n"
    )

    print("=" * 96)
    print("COVER PLANNER V2: BUILT")
    print("=" * 96)
    print("Output:", output_path.relative_to(ROOT))
    print("Company:", identity_data["company"])
    print("Position:", identity_data["position"])
    print("Routed role:", market_primary.get("role"))
    print("Primary evidence:", primary_id)
    print("Primary planner score:", primary_rank["planner_score"])
    print(
        "Critical requirements:",
        ", ".join(r["requirement_id"] for r in critical_records),
    )
    print(
        "Primary-supported critical:",
        ", ".join(supported_critical) or "NONE",
    )
    print(
        "Primary-unsupported critical:",
        ", ".join(unsupported_critical) or "NONE",
    )
    print("Numerical anchors:", len(metric_anchors))
    for anchor in metric_anchors:
        print("  -", anchor["text"])
    print("Implementation mechanics:", len(methods[:4]))
    for item in methods[:4]:
        print("  -", item)
    print("Validation methods:", len(validation[:4]))
    for item in validation[:4]:
        print("  -", item)
    print("Resume overlap exclusions:", len(overlap))
    print("Claim ledger items:", len(claim_ledger))
    print("Model calls: 0")
    print("Resume modified: NO")
    print("=" * 96)

    print("\n===== COVER PLAN STORY CORE =====")
    print(json.dumps({
        "employer_need_thesis": plan["employer_need_thesis"],
        "primary_evidence": plan["primary_evidence"],
        "story": plan["story"],
        "numerical_anchors": plan["numerical_anchors"],
        "target_role_application": plan["target_role_application"],
        "interest_reason": plan["interest_reason"],
        "jd_concepts": plan["jd_concepts"],
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    from careerops_requirement_authority import run_guarded
    run_guarded(main,RUNTIME,'careerops_build_cover_plan.py')
