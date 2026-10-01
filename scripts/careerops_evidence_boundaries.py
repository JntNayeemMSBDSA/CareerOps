"""Entity-specific claim boundaries belong to candidate authority, never code defaults."""
import re

def entity_boundary_errors(text, entity_id, facts):
    rules=facts.get("entity_claim_boundaries",{}).get(entity_id,{})
    errors=[]
    for term in rules.get("forbidden_historical_terms",[]):
        if re.search(r"(?<!\w)"+re.escape(term)+r"(?!\w)",text,re.I):errors.append("historical_placement_blocked:"+term)
    for company in rules.get("not_employment_at",[]):
        if re.search(r"\b(?:employed by|worked at|employee of)\s+"+re.escape(company)+r"\b",text,re.I):errors.append("project_employment_boundary:"+company)
    # Model names and numeric values are checked within the same clause.
    for model,values in rules.get("forbidden_model_thresholds",{}).items():
        for clause in re.split(r";|[!?]+|(?<!\d)\.(?!\d)",text):
            if not re.search(r"(?<!\w)"+re.escape(model)+r"(?!\w)",clause,re.I):continue
            if any(re.search(r"(?<![\w.])"+re.escape(str(value))+r"(?![\w.])",clause) for value in values):
                # A distinctly named model assigning the value does not attach it to this model.
                others=rules.get("threshold_models",[])
                assigned=any(re.search(re.escape(other)+r".{0,50}\bthreshold\b",clause,re.I) for other in others if other.casefold()!=model.casefold())
                if not assigned:errors.append("model_attribution:"+model)
    return errors
