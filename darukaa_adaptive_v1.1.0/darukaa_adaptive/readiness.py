"""Evidence and biodiversity-credit readiness checks."""
from __future__ import annotations
from typing import Any, Dict, Iterable

def assess_readiness(config,boundary_area_ha,metrics:Iterable,benchmarks=None,scoring=None,evidence_df=None)->Dict[str,Any]:
    metrics=list(metrics); benchmarks=list(benchmarks or []); scoring=scoring or {}; evidence_df=evidence_df
    usable=[m for m in metrics if getattr(m,'status',None) in {'ok','usable'} and getattr(m,'value',None) is not None]
    scoreable=[b for b in benchmarks if getattr(b,'reference_approved_for_scoring',False) and (getattr(b,'reference_attainment_0_100',None) is not None or getattr(b,'intactness_score_0_100',None) is not None)]
    evidence_types=[]
    if evidence_df is not None and not evidence_df.empty: evidence_types=sorted(set(evidence_df.get('evidence_type',[]).astype(str)))
    return {
      'geometry':{'status':'ready' if boundary_area_ha>0 else 'invalid','boundary_area_ha':round(boundary_area_ha,6),'boundary_type':config.site_boundary_type},
      'temporal_baseline':{'status':'configured','label':config.temporal.baseline_label,'start':config.temporal.baseline_start_date,'end':config.temporal.baseline_end_date},
      'historical_context':{'start_year':config.temporal.start_year,'end_year':config.temporal.end_year,'minimum_years_for_trend':config.temporal.min_years_for_trend},
      'metric_coverage':{'total_metrics':len(metrics),'usable_metrics':len(usable),'referenceable_metrics':sum(bool(getattr(m,'reference_allowed',False)) for m in metrics)},
      'reference_readiness':{'status':'available' if scoreable else 'partial_or_unavailable','benchmarked_metrics':len(scoreable),'automatic_reference_enabled':config.reference.automatic_enabled,'automatic_reference_approval_is_QA_gated':True,'manual_reference_optional':True},
      'evidence':{'types_available':evidence_types,'edna_optional':True,'note':'eDNA is integrated only when supplied and validated; persistence-potential proxies remain contextual unless a defensible scoring reference is provided.'},
      'scoring':{'condition_pressure_separated':config.scoring.pressure_separate_from_condition,'condition_min_pillars':config.scoring.min_condition_pillars,'composite_son_enabled':config.scoring.composite_son_enabled,'status':scoring.get('status') if isinstance(scoring,dict) else None},
      'qa':{'principle':'measurement validity, reference comparability and ecological interpretation are separate gates'},
    }
