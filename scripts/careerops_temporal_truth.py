"""Distinguish current employment from completed, source-owned deliverables."""
import re

def completed_deliverable_errors(text, source_ids, facts):
    errors=[]
    for entity in source_ids:
        row=facts.get("deliverable_state_authority",{}).get(entity,{})
        if row.get("deliverable_state")!="BUILT_AND_VALIDATED":continue
        keywords=row.get("match_terms",[]) or re.findall(r"[a-z]{4,}",str(row.get("deliverable","")).lower())
        if not keywords:continue
        for sentence in re.split(r"(?<=[.!?])\s+",str(text)):
            ongoing=re.search(r"\b(?:i am|i'm|we are|currently|am|is)\s+(?:still\s+)?(?:building|developing|harmonizing|constructing)\b",sentence,re.I)
            same=any(re.search(r"(?<!\w)"+re.escape(term)+r"(?!\w)",sentence,re.I) for term in keywords)
            if ongoing and same:errors.append("COMPLETED_DELIVERABLE_PRESENTED_AS_ONGOING:"+sentence)
    return errors
