"""Source-bound, concept-aware skills curation and independent stack audit.

No models, runtime writes, employment backfills or release decisions. All inventory
capabilities require the existing direct-user-confirmed capability override.
"""
from __future__ import annotations
import copy
import re
from collections import defaultdict

LANG = "Programming & Data Analysis"
BI = "BI & Spreadsheet Analytics"
ENG = "Data Engineering & Platforms"
ML = "Statistical Modeling & Machine Learning"
DEV = "Development & Delivery"
QUALITY = "Data Quality & Governance"
BUSINESS = "Business Analysis & Delivery"
FIN = "Financial Modeling & Risk Analytics"
MARKETING = "Customer & Digital Analytics"
HEALTH = "Healthcare Analytics & Data Systems"
OPS = "Operations & Supply Chain Analytics"
PEOPLE = "People Analytics & HR Systems"
SUSTAIN = "Sustainability & Energy Analytics"
ORDER = [LANG, BI, ENG, ML, QUALITY, BUSINESS, FIN, MARKETING, HEALTH, OPS, PEOPLE, SUSTAIN, DEV]
# These are display relationships, never a source of candidate capabilities.
ALIASES = {
    "reports": "Reporting", "visualizations": "Data Visualization", "warehouse": "Data Warehouse", "star schema": "Star-schema Modeling", "semantic model": "Semantic Modeling", "calibration": "Model Calibration", "pipelines": "Data Pipelines", "joins": "SQL Joins", "ml": "Machine Learning", "machine learning": "Machine Learning",
    "bi": "Business Intelligence", "business intelligence": "Business Intelligence",
    "github ci": "GitHub CI", "github actions": "GitHub Actions",
    "power bi reporting": "Power BI", "powerbi": "Power BI",
    "etl elt": "ETL/ELT", "etl/elt": "ETL/ELT", "etl / elt": "ETL/ELT",
    "cross validation": "Cross-validation", "cross-validation": "Cross-validation",
    "scikit learn": "scikit-learn", "sklearn": "scikit-learn",
    "feature engineering": "Feature Engineering", "predictive modeling": "Predictive Modeling",
    "model evaluation": "Model Evaluation", "classification": "Classification",
    "logistic regression": "Logistic Regression", "linear regression": "Linear Regression",
    "hypothesis testing": "Hypothesis Testing", "confidence intervals": "Confidence Intervals",
    "feature selection": "Feature Selection", "gradient boosting": "Gradient Boosting",
    "random forest": "Random Forest", "time series": "Time-series Analysis",
    "time-series analysis": "Time-series Analysis", "data visualization": "Data Visualization",
    "data visualisation": "Data Visualization", "version control": "Version Control",
    "agile / scrum": "Agile/Scrum", "agile/scrum": "Agile/Scrum",
    "sql / t-sql": "SQL/T-SQL", "sql/t-sql": "SQL/T-SQL",
    "excel / google sheets": "Excel/Google Sheets", "excel/google sheets": "Excel/Google Sheets",
    "dashboarding": "Dashboard Development", "dashboards": "Dashboard Development",
    "dashboard development": "Dashboard Development",
    "train/validation/test": "Train/validation/test", "precision/recall/f1": "Precision/Recall/F1",
    "roc-auc/pr-auc": "ROC-AUC/PR-AUC", "rmse/mae": "RMSE/MAE",
    "xgboost/gradient boosting": "XGBoost",
    "ctes": "CTEs", "window functions": "Window Functions", "query optimization": "Query Optimization",
    "star-schema modeling": "Star-schema Modeling", "star schema modeling": "Star-schema Modeling",
    "semantic modeling": "Semantic Modeling", "data validation": "Data Validation",
    "data quality": "Data Quality", "data governance": "Data Governance",
    "temporal validation": "Temporal Validation", "leakage control": "Leakage Control",
    "data leakage": "Leakage Control", "class imbalance": "Class-imbalance Handling",
    "class-imbalance handling": "Class-imbalance Handling", "threshold tuning": "Threshold Tuning",
    "pytest": "pytest", "ruff": "Ruff", "git": "Git", "github": "GitHub",
    "python": "Python", "sql": "SQL", "r": "R", "pandas": "pandas",
    "numpy": "NumPy", "xgboost": "XGBoost", "power query": "Power Query", "dax": "DAX",
    "excel": "Excel", "google sheets": "Google Sheets", "jupyter": "Jupyter",
    "power bi": "Power BI", "tableau": "Tableau", "duckdb": "DuckDB", "parquet": "Parquet",
}
BROAD = {"programming", "querying", "machine learning", "ml", "business intelligence", "bi",
         "statistics", "statistical modeling", "reporting", "visualization", "data visualization",
         "data engineering", "ai", "artificial intelligence", "statistical analysis", "cloud", "database", "version control", "analytics", "data analysis", "data quality", "data governance", "business analysis", "development", "crm", "finance", "financial modeling", "risk analysis", "marketing analytics", "healthcare analytics", "operations", "supply chain", "analytics"}
DEFAULT_GENERIC = {"microsoft office", "agile", "scrum", "agile/scrum", "github", "jira", "confluence", "users", "sessions", "events", "testing", "documentation", "workflow", "parameters", "relationships", "refresh", "measures", "qa", "monitoring", "automation", "financial"}
METHOD_PRIORITY = {"cross-validation": 18, "feature engineering": 18, "logistic regression": 17,
                   "classification": 16, "hypothesis testing": 17, "confidence intervals": 15,
                   "predictive modeling": 16, "xgboost": 17, "feature selection": 13,
                   "window functions": 18, "ctes": 18, "query optimization": 17,
                   "semantic modeling": 17, "star-schema modeling": 17, "data validation": 16,
                   "leakage control": 14, "temporal validation": 14, "precision/recall/f1": 14, "pytest": 10, "ruff": 8, "github actions": 8, "data profiling": 13, "reconciliation": 12, "data cleaning": 10, "data quality": 12}


def norm(text):
    text = str(text).casefold().replace("&", " and ")
    text = re.sub(r"[^a-z0-9+#./ -]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def canonical(term):
    return ALIASES.get(norm(term), str(term).strip())


def concept(term):
    return norm(canonical(term))


def components(term):
    value = str(term).strip()
    key = norm(value)
    # Combined aliases are resolved into their distinct underlying capabilities.
    combined = {"sql/t-sql": ["SQL", "T-SQL"], "sql / t-sql": ["SQL", "T-SQL"],
                "excel/google sheets": ["Excel", "Google Sheets"], "excel / google sheets": ["Excel", "Google Sheets"],
                "agile/scrum": ["Agile", "Scrum"], "agile / scrum": ["Agile", "Scrum"]}
    if key in combined:
        return combined[key]
    if key in ALIASES:
        return [canonical(value)]
    if "/" in value and key not in {"a/b testing", "roc-auc", "pr-auc"}:
        parts = [x.strip() for x in value.split("/")]
        # Avoid interpreting descriptive slash phrases as independently verified tools.
        if 1 < len(parts) <= 5 and all(category_for(x) for x in parts):
            return [canonical(x) for x in parts]
    return [canonical(value)]


def category_for(term, registry_category=""):
    t = norm(term); c = norm(registry_category)
    if t in {"excel", "google sheets", "excel/google sheets", "power query", "dax"}:
        return BI
    if t in {"sas", "spss", "stata"}:return ML
    if t in {"python", "sql", "t-sql", "r", "vba", "java", "javascript", "pandas", "numpy", "scipy", "pyarrow", "sql/t-sql", "matlab", "html", "css", "bash"}:
        return LANG
    if any(x in t for x in ["power bi", "tableau", "looker", "dashboard", "visualization", "semantic modeling", "metrics/kpi", "ga4"]):
        return BI
    if t in {"data modeling", "schema design", "salesforce", "crm", "crm/cdp", "sap", "erp", "netsuite", "oracle", "workday", "hris", "successfactors"}:return ENG
    if t in {"windows", "linux", "system administration", "technical support", "scheduled tasks", "windows permissions", "windows file systems"}:return DEV
    if t in {"qualtrics", "redcap"}:return BI
    if any(x in t for x in ["google analytics", "adobe analytics", "google tag manager", "amplitude", "mixpanel", "contentsquare", "hotjar", "optimizely", "funnel analysis", "channel attribution", "cohort analysis"]):return MARKETING
    if t in {"ai", "artificial intelligence", "gcn"}:return ML
    if t in {"ctes", "sql joins", "joins", "window functions", "aggregation", "subqueries", "query optimization"}:
        return LANG
    if any(x in t for x in ["data quality", "data validation", "reconciliation", "data governance", "lineage", "data profiling", "access control", "data cleaning"]):
        return QUALITY
    if any(x in t for x in ["xgboost", "scikit", "regression", "classification", "random forest", "clustering", "k-means", "dbscan", "feature", "validation/test", "cross-validation", "temporal validation", "leakage", "class-imbalance", "precision", "recall", "roc-auc", "pr-auc", "rmse", "mae", "calibration", "threshold tuning", "predictive", "hypothesis", "confidence interval", "anova", "statistic", "machine learning", "model evaluation", "a/b testing", "experiment", "forecast", "time series", "time-series", "bert", "nlp", "resnet", "tf-idf", "pytorch", "tensorflow", "pca"]):
        return ML
    if any(x in t for x in ["git", "pytest", "ruff", "jupyter", "docker", "ci/cd", "devops", "jenkins", "jira", "scrum", "agile", "confluence", "version control", "unit testing"]):
        return DEV
    if any(x in t for x in ["snowflake", "databricks", "spark", "dbt", "etl", "elt", "pipeline", "aws", "azure", "redshift", "bigquery", "parquet", "duckdb", "sql server", "postgresql", "data warehouse", "data lake", "airflow", "kafka", "star-schema", "dimensional model"]):
        return ENG
    if any(x in t for x in ["requirements elicitation", "business requirement", "process mapping", "uat", "acceptance criteria", "user stories", "sdlc", "stakeholder", "business process"]):
        return BUSINESS
    if t in {"reporting", "business intelligence", "bi", "visualization"}:return BI
    if t in {"cloud", "database", "data engineering"}:return ENG
    if t == "microsoft office":return DEV
    if "programming" in c or "query" in c:return LANG
    if c.startswith("bi ") or "visualization" in c:return BI
    if "statistics" in c or "machine learning" in c:return ML
    if "quality" in c or "governance" in c:return QUALITY
    if "cloud" in c or "data platform" in c:return ENG
    if "business analysis" in c or "delivery" in c:return BUSINESS
    if registry_category in ORDER:return registry_category
    if "finance" in c or "risk" in c or "financial" in c:return FIN
    if "marketing" in c or "customer" in c or "digital" in c:return MARKETING
    if "healthcare" in c or "clinical" in c or "public health" in c:return HEALTH
    if "supply chain" in c or "logistics" in c or "manufacturing" in c:return OPS
    if "hr" in c or "people" in c:return PEOPLE
    if "sustainability" in c or "energy" in c:return SUSTAIN
    return None


def capability_context(section, role=""):
    """Inventory-owned section context classifies shorthand without adding facts."""
    section=norm(section);role=norm(role)
    if section in {"sql", "python", "r", "programming"}:return LANG
    if section in {"excel", "power bi", "tableau", "semantic layer"}:return BI
    if any(x in section for x in ["validation", "features", "ml", "models", "statistics", "experimentation"]):return ML
    if any(x in section for x in ["financial", "fp a", "investment", "pricing", "risk", "controls", "three lines"]):return FIN
    if any(x in section for x in ["ga4", "gtm", "adobe", "event architecture", "behavioral", "tracking", "attribution"]):return MARKETING
    if any(x in section for x in ["requirements", "process", "delivery"]):return BUSINESS
    if any(x in section for x in ["governance", "data quality", "data controls"]):return QUALITY
    if any(x in role for x in ["financial", "risk", "pricing", "underwriting", "business controls"]):return FIN
    if any(x in role for x in ["marketing", "digital", "media", "customer", "product analytics", "sales operations"]):return MARKETING
    if any(x in role for x in ["healthcare", "clinical"]):return HEALTH
    if any(x in role for x in ["supply chain", "logistics", "manufacturing", "operations data"]):return OPS
    if any(x in role for x in ["people", "hr data"]):return PEOPLE
    if "sustainability" in role:return SUSTAIN
    return None


def short_capability(term):
    text = str(term).strip()
    return bool(text) and len(text) <= 58 and len(text.split()) <= 6 and not re.search(r"[;:=]|\b(?:where|unless|requires|usually|including|versus)\b", text, re.I)


def _strings(value):
    if isinstance(value, str):yield value
    elif isinstance(value, dict):
        for item in value.values():yield from _strings(item)
    elif isinstance(value, list):
        for item in value:yield from _strings(item)


def _phrase(term, text):
    return bool(re.search(r"(?<!\w)" + re.escape(norm(term)) + r"(?!\w)", norm(text)))


def curate_stack(coverage, existing_candidates, requirements, semantic, role_profile, *, market_prior_enabled=True, max_categories=6, max_items=8):
    """Admit only source-backed capabilities; preserve their ownership partition."""
    pool = {}; aliases = defaultdict(set)
    def admit(raw, source, base=0, owners=(), claim="DIRECT_USER_CONFIRMED_CAPABILITY", registry_category=""):
        for term in components(raw):
            if not short_capability(term):continue
            family = category_for(term, registry_category)
            if not family:continue
            key = concept(term)
            row = pool.setdefault(key, {"term": canonical(term), "concept_id": key, "category": family,
                     "score": 0.0, "provenance": [], "source_labels": [], "historical_evidence_owner_ids": [],
                     "claim_class": claim, "current_capability_confirmed": False,
                     "historical_placement_requires_owner": True})
            row["score"] = max(row["score"], float(base))
            if source not in row["provenance"]:row["provenance"].append(source)
            if raw not in row["source_labels"]:row["source_labels"].append(raw)
            row["historical_evidence_owner_ids"] = sorted(set(row["historical_evidence_owner_ids"]) | set(owners))
            if owners and claim == "ARTIFACT_VERIFIED":row["claim_class"] = claim
            if source.startswith("DIRECT_USER_CONFIRMED"):row["current_capability_confirmed"] = True
            aliases[key].add(norm(raw));aliases[key].add(norm(term))
    for item in coverage.get("explicit_skill_registry", []):
        admit(item["canonical_term"], "DIRECT_USER_CONFIRMED_EXPLICIT_REGISTRY", registry_category=item.get("category", ""))
    for item in coverage.get("deep_capability_registry", []):
        admit(item["term"], "DIRECT_USER_CONFIRMED_DEEP_REGISTRY", registry_category=next((capability_context(section, role) for role in item.get("roles", []) for section in item.get("sections", []) if capability_context(section, role)), ""))
    # Role sections provide source-backed shorthand and methodological context.
    for profile in coverage.get("role_coverage_profiles", []):
        for section in profile.get("deep_capability_sections", []):
            for term in section.get("items", []):admit(term, "DIRECT_USER_CONFIRMED_ROLE_CAPABILITY", registry_category=capability_context(section.get("section", ""), profile.get("role", "")) or "")
    for item in existing_candidates:
        admit(item["term"], "EXISTING_AUTHORITY_BOUND_CANDIDATE", item.get("score", 0), item.get("historical_evidence_owner_ids", []), item.get("claim_class", "DIRECT_USER_CONFIRMED_CAPABILITY"), item.get("category", ""))
        for term in components(item["term"]):
            if concept(term) in pool:
                row=pool[concept(term)]
                row["provenance"] = list(dict.fromkeys(row["provenance"]+item.get("provenance", [])))
                row["current_capability_confirmed"] |= item.get("current_capability_confirmed", False)
    # GitHub CI is a generic implementation label. Prefer Actions only when
    # independently confirmed in the inventory; otherwise retain GitHub CI.
    if "github ci" in pool and "github actions" in pool and not _phrase("GitHub CI", " ".join(_strings(requirements))):
        src=pool.pop("github ci");dst=pool["github actions"]
        dst["score"]=max(dst["score"],src["score"])
        dst["provenance"]=list(dict.fromkeys(dst["provenance"]+src["provenance"]))
        dst["source_labels"]+=src["source_labels"]
        # CI does not establish historical Actions ownership.
        aliases["github actions"].add("github ci")
    requested=[];protected=[];jd_text=" ".join(_strings(requirements))
    for req in requirements.get("requirements", []):
        for field in ("exact_tools_technologies", "exact_methods", "exact_work_products"):
            for term in req.get(field, []):
                requested.append(term)
                if req.get("priority") in {"P0", "P1"}:protected.append(term)
    for req in semantic.get("requirements", []):
        for term in req.get("exact_layer", {}).get("tools_technologies", []):requested.append(term)
    requested=list(dict.fromkeys(requested));protected=list(dict.fromkeys(protected))
    if "github ci" in pool and "github actions" in pool and any(concept(x)=="github ci" for x in requested):
        pool.pop("github actions")
    # ETL/ELT includes ETL retrieval while retaining the separately confirmed
    # broader capability. Never infer ELT from ETL alone.
    if "etl" in pool and "etl/elt" in pool:
        src=pool.pop("etl");dst=pool["etl/elt"]
        dst["score"]=max(dst["score"],src["score"])
        dst["provenance"]=list(dict.fromkeys(dst["provenance"]+src["provenance"]))
        aliases["etl/elt"].add("etl")
    role_terms=set()
    if market_prior_enabled:
        for section in role_profile.get("deep_capability_sections", []):
            role_terms.update(concept(x) for item in section.get("items", []) for x in components(item))
    active_families={category_for(term) for term in requested if category_for(term)}
    active_families |= {x["category"] for x in pool.values() if x["score"] >= 40}
    if market_prior_enabled:active_families |= {pool[key]["category"] for key in role_terms if key in pool}
    for key,row in pool.items():
        matched=[term for term in requested if concept(term)==key or norm(term) in aliases[key]]
        row["jd_requested_terms"]=matched
        row["protected_terms"]=[term for term in protected if term in matched]
        row["score"]+=100 if matched else 0
        if _phrase(row["term"],jd_text) and (category_for(row["term"]) or matched or key in role_terms):row["score"]+=35
        if key in role_terms:row["score"]+=35
        elif row["category"] in active_families and key in METHOD_PRIORITY:row["score"]+=22
        relevant = bool(matched or row["score"] > 0 or key in role_terms or row["category"] in active_families and key in METHOD_PRIORITY)
        if relevant:row["score"]+=METHOD_PRIORITY.get(key,0)
        if key in DEFAULT_GENERIC and not matched:row["score"]-=100
        row["score"]=round(row["score"],2)
        row["authority_partition"]="HISTORICAL_EVIDENCE_WITH_OWNER" if row["historical_evidence_owner_ids"] else "DIRECT_CONFIRMED_CURRENT_CAPABILITY"
    labels={family:family for family in ORDER}
    if any(concept(x)=="statistics" for x in requested):labels[ML]="Statistics & Machine Learning"
    if any(norm(x)=="ml" for x in requested):labels[ML]+=" (ML)"
    if any(concept(x)=="business intelligence" for x in requested):labels[BI]="Business Intelligence & Spreadsheet Analytics"
    # Broad requested concepts are represented as context, not repeated children.
    if any(concept(x)=="reporting" for x in requested):
        labels[BI]="BI, Reporting & Spreadsheet Analytics" if labels[BI]==BI else "Business Intelligence, Reporting & Analytics"
    if any(concept(x)=="data visualization" for x in requested) and not any(concept(x)=="reporting" for x in requested):labels[BI]="BI, Data Visualization & Spreadsheets"
    requested_keys={concept(x) for x in requested}
    if "data visualization" in requested_keys and "reporting" in requested_keys:
        labels[BI]="Business Intelligence, Reporting & Data Visualization" if "business intelligence" in requested_keys else "BI, Reporting & Data Visualization"
    if "ai" in requested_keys or "artificial intelligence" in requested_keys:labels[ML]+=" & AI"
    if "statistical modeling" in requested_keys and "statistics" in requested_keys:
        labels[ML]="Statistics, Statistical Modeling & Machine Learning"
    if "cloud" in requested_keys or "database" in requested_keys:
        contexts=[x for x in ["Cloud" if "cloud" in requested_keys else "", "Database" if "database" in requested_keys else ""] if x]
        labels[ENG]="Data Engineering, " + " & ".join(contexts) + " Platforms"
    if "crm" in requested_keys:labels[ENG]="Data Engineering & CRM Platforms"
    if "version control" in requested_keys:labels[DEV]="Version Control & Development"
    rejected=[];eligible=[]
    for key,row in pool.items():
        if key in BROAD:
            rejected.append({"term":row["term"],"reason":"BROAD_CONCEPT_CONTEXT_ONLY"});continue
        if row["score"]<=0:continue
        eligible.append(row)
    # Specific coverage dominates generic/role-prior lists; a small adjacent
    # reserve supplies defensible depth without dumping all confirmed inventory.
    eligible.sort(key=lambda x:(bool(x["protected_terms"]), bool(x["jd_requested_terms"]), x["score"], bool(x["historical_evidence_owner_ids"]), x["term"]),reverse=True)
    grouped=defaultdict(list)
    for row in eligible:
        family=row["category"]
        if len(grouped[family])>=max_items:continue
        # Generic GitHub is redundant beside specifically confirmed CI actions.
        if row["concept_id"]=="github" and any(x["concept_id"]=="github actions" for x in grouped[DEV]) and not row["protected_terms"]:
            rejected.append({"term":row["term"],"reason":"SPECIFIC_WORKFLOW_ALREADY_PRESENT"});continue
        # ETL and ETL/ELT overlap; the broader capability must itself be confirmed.
        if row["concept_id"]=="etl" and "etl/elt" in pool and pool["etl/elt"]["score"]>0 and not row["protected_terms"]:continue
        grouped[family].append(row)
    families=[x for x in ORDER if grouped[x]]
    if len(families)>max_categories:
        # Keep categories carrying exact requirements first.
        families=sorted(families,key=lambda f:(any(x["protected_terms"] for x in grouped[f]),sum(x["score"] for x in grouped[f][:4])),reverse=True)[:max_categories]
        families=[x for x in ORDER if x in families]
    def display_term(row):
        # Preserve a specifically required surface phrase; ordinary aliases use
        # the clearer canonical name. Broad concepts belong in headings.
        exact=row.get("protected_terms", [])
        return exact[0] if exact and concept(exact[0])==row["concept_id"] and norm(exact[0])!=norm(row["term"]) else row["term"]
    lines=[{"category":labels[f],"terms":[display_term(x) for x in grouped[f]]} for f in families]
    # A small quality group scans naturally beside its data platforms. Preserve
    # every selected capability rather than padding a separate thin heading.
    if QUALITY in families and ENG in families and len(grouped[QUALITY])<4 and len(grouped[ENG])+len(grouped[QUALITY])<=9:
        eng_line=next(x for x in lines if x["category"]==labels[ENG])
        eng_line["category"]=labels[ENG].replace(" & ", ", ")+" & Data Quality"
        eng_line["terms"] += [display_term(x) for x in grouped[QUALITY]]
        lines=[x for x in lines if x["category"]!=labels[QUALITY]]
    visible={concept(x) for row in lines for x in row["terms"]}
    decisions=[]
    for term in protected:
        key=concept(term);locations=[]
        for line in lines:
            if _phrase(term,line["category"]):locations.append({"surface":"CATEGORY","text":line["category"]})
            for item in line["terms"]:
                if key==concept(item) or _phrase(term,item):locations.append({"surface":"SKILL","text":item})
        decisions.append({"term":term,"concept_id":key,"supported":key in pool,"locations":locations,
                          "requirement":"FINAL_RESUME_VISIBILITY" if key in pool else "NO_CANDIDATE_AUTHORITY"})
    plan={"schema_version":"skills-stack-contract-v1","visible_skill_lines":lines,
          "ranked_skill_candidates":eligible,"eligible_concepts":pool,"protected_term_locations":decisions,
          "selection_decisions":rejected,"policy":{"minimum_categories_target":4,"maximum_categories":max_categories,
              "items_per_category_target":[5,9],"count_targets_are_not_filler_quotas":True,
              "deep_registry_is_visible_candidate_source":True,"historical_backfill_forbidden":True},
          "model_calls":0}
    plan["audit"]=audit_stack(lines,plan)
    return plan


def audit_stack(lines, plan=None):
    """Independent check over emitted lines, including writer drift."""
    plan=plan or {};pool=plan.get("eligible_concepts",{});findings=[];seen={};total=0
    for line in lines:
        category=str(line.get("category",""));terms=line.get("terms",[])
        for raw in terms:
            total+=1
            parts=components(raw)
            for term in parts:
                key=concept(term)
                if key in seen:findings.append({"code":"DUPLICATE_CONCEPT","term":raw,"first":seen[key]})
                else:seen[key]=category
                if key in BROAD:findings.append({"code":"LOW_INFORMATION_OR_CATEGORY_CHILD","term":raw,"category":category})
                expected=category_for(term) or pool.get(key,{}).get("category")
                # Heading wording can vary; its semantic family must not.
                heading=norm(category)
                heading_family = (LANG if "programming" in heading else BI if "spreadsheet" in heading or heading.startswith("bi ") or heading.startswith("bi,") or "business intelligence" in heading else ML if "machine learning" in heading or "statistics" in heading or "statistical modeling" in heading else QUALITY if "data quality" in heading else ENG if "data engineering" in heading else BUSINESS if "business analysis" in heading else DEV if "development" in heading else None)
                if category in {FIN, MARKETING, HEALTH, OPS, PEOPLE, SUSTAIN}:heading_family=category
                if expected and heading_family!=expected and not (expected==ENG and "data engineering" in heading and "data quality" in heading):findings.append({"code":"MISCLASSIFIED_SKILL","term":raw,"category":category,"expected":expected})
                if pool and key not in pool:findings.append({"code":"NO_CANDIDATE_AUTHORITY","term":raw})
    if "github" in seen and "github actions" in seen:
        explicit=pool.get("github",{}).get("protected_terms",[])
        if not explicit:findings.append({"code":"GENERIC_AND_SPECIFIC_OVERLAP","term":"GitHub + GitHub Actions"})
    if "etl" in seen and "etl/elt" in seen:findings.append({"code":"OVERLAPPING_REPRESENTATION","term":"ETL + ETL/ELT"})
    warnings=[]
    if pool:
        for line in lines:
            family=category_for(line["terms"][0]) if line.get("terms") else None
            alternatives=[x for x in pool.values() if x["category"]==family and x["score"]>20 and x["concept_id"] not in BROAD]
            if len(line.get("terms",[]))<4 and len(alternatives)>=5:warnings.append({"code":"AVAILABLE_DEPTH_UNDERUSED","category":line["category"]})
    return {"gate":"PASS" if not findings else "FAIL","findings":findings,"warnings":warnings,
            "unique_concept_count":len(seen),"displayed_item_count":total,"category_count":len(lines)}


def compact_contract(plan):
    stack=plan.get("skills_stack_contract")
    if not stack:return None
    selected={concept(term) for line in stack["visible_skill_lines"] for term in line["terms"]}
    return {"schema_version":stack["schema_version"],"visible_skill_lines":stack["visible_skill_lines"],
            "eligible_concepts":{key:row for key,row in stack["eligible_concepts"].items() if key in selected},
            "protected_term_locations":stack["protected_term_locations"],"selection_locked":True}


def enforce_final_stack(resume, plan):
    stack=plan.get("skills_stack_contract")
    if not stack:return None
    result=audit_stack(resume.get("skills", []),stack)
    if resume.get("skills", [])!=stack["visible_skill_lines"]:
        result["findings"].append({"code":"APPROVED_STACK_DRIFT"})
        result["gate"]="FAIL"
    return result
