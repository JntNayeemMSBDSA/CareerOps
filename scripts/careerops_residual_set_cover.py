"""Select projects by uncovered mandatory/core coverage before secondary scores."""
from itertools import combinations

def select_projects(candidates,residual_ids,priorities,limit=2):
 if not candidates:return [],{}
 residual=set(residual_ids);size=min(limit,len(candidates))
 def objective(group):
  supported=set().union(*(set(x.get('supported_requirement_ids',[])) for x in group))
  marginal=supported & residual
  p0=sum(priorities.get(r)=='P0' for r in marginal);p1=sum(priorities.get(r)=='P1' for r in marginal)
  def component(name,fallback=None):return sum(x.get('components',{}).get(name,x.get('components',{}).get(fallback,0) if fallback else 0) for x in group)
  return (p0,p1,component('principal_output_similarity','jd_fit'),component('responsibility_similarity'),component('business_domain_similarity'),component('method_tool_similarity','method_depth'),component('evidence_quality'),component('scale_metrics'),component('complementarity'),len(marginal),sum(x.get('score',0) for x in group))

 groups=list(combinations(candidates,size));chosen=max(groups,key=objective)
 return list(chosen),{'objective_order':['residual_P0','residual_P1','principal_output_similarity','responsibility_similarity','business_domain_similarity','method_tool_similarity','evidence_quality','story_numerical_strength','diversity_novelty','other_residual_tiebreak','aggregate_tiebreak'], 'objective':list(objective(chosen)), 'residual_target_ids':sorted(residual),'filled_residual_ids':sorted(set().union(*(set(x.get('supported_requirement_ids',[])) for x in chosen)) & residual),'combinations_evaluated':len(groups),'verified_evidence_only':True}
