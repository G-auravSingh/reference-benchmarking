"""Shared condition/pressure scoring for EO, field, acoustic, eDNA and modelled evidence."""
from __future__ import annotations
from types import SimpleNamespace
from typing import Any, Dict, Iterable, Optional
import math
import pandas as pd
from .benchmark import benchmark_observation
from .registry import PILLARS

BANDS = ((0,20,"Very High"),(20,40,"High"),(40,60,"Moderate"),(60,80,"Low"),(80,100.000001,"Very Low"))

def clamp_intactness(value):
    if value is None or not math.isfinite(float(value)): return None
    return max(0.0, min(100.0, float(value)))

def concern_label(score):
    if score is None or not math.isfinite(float(score)): return None
    x=clamp_intactness(score)
    for lo,hi,label in BANDS:
        if lo <= x < hi: return label
    return "Very Low"

def geometric_mean(values):
    vals=[float(v) for v in values if v is not None and math.isfinite(float(v))]
    if not vals: return None
    if any(v < 0 for v in vals): raise ValueError("geometric mean requires non-negative values")
    return float(math.exp(sum(math.log(max(v,1e-12)) for v in vals)/len(vals)))

def _metadata(record):
    return {
        "metric": record.metric, "pillar": record.pillar, "raw_value": getattr(record,"value",None),
        "units": getattr(record,"units",""), "direction": getattr(record,"direction",None),
        "reference_allowed": getattr(record,"reference_allowed",False), "status": getattr(record,"status","ok"),
        "notes": getattr(record,"notes","")
    }

def score_metric(metric_result, benchmark_result, config):
    meta=_metadata(metric_result); b=benchmark_result
    out={"metric":meta["metric"],"pillar":meta["pillar"],"raw_value":meta["raw_value"],"units":meta["units"],
         "reference_value":getattr(b,"selected_reference",None) if b else None,
         "reference_level":getattr(b,"selected_reference_level","none") if b else "none",
         "reference_n":getattr(b,"reference_n",None) if b else None,
         "reference_uncertainty":getattr(b,"reference_uncertainty",None) if b else None,
         "raw_relative_ratio":getattr(b,"raw_relative_ratio",None) if b else None,
         "intactness_score_0_100":getattr(b,"intactness_score_0_100",None) if b else None,
         "reference_attainment_0_100":getattr(b,"reference_attainment_0_100",None) if b else None,
         "relative_departure_pct":getattr(b,"relative_departure_pct",None) if b else None,
         "reference_state":getattr(b,"reference_state","") if b else "",
         "reference_approval_basis":getattr(b,"reference_approval_basis","") if b else "",
         "reference_diagnostics":getattr(b,"reference_diagnostics",None) if b else None,
         "interpretation_status":getattr(b,"interpretation_status","") if b else "",
         "concern_label":None,"score_eligible":False,"score_status":"not_eligible",
         "reference_approved_for_scoring":bool(getattr(b,"reference_approved_for_scoring",False)) if b else False,
         "evidence_type":getattr(metric_result,"evidence_type","EO"),"domain":getattr(metric_result,"domain",""),"notes":meta["notes"]}
    if not config.scoring.enabled: out["score_status"]="scoring_disabled"; return out
    if meta["raw_value"] is None or meta["status"] not in {"ok","usable"}: out["score_status"]="invalid_metric"; return out
    if not meta["reference_allowed"]: out["score_status"]="not_referenceable"; return out
    intact=getattr(b,"reference_attainment_0_100",None) if b else getattr(b,"intactness_score_0_100",None) if b else None
    if intact is None: out["score_status"]="reference_unavailable"; return out
    if not getattr(b,"reference_approved_for_scoring",False): out["score_status"]="reference_not_approved_for_scoring"; return out
    out.update({"reference_attainment_0_100":clamp_intactness(intact),"intactness_score_0_100":clamp_intactness(intact),"concern_label":concern_label(intact),"score_eligible":True,"score_status":"scored"})
    return out

def _limiting_metric(df):
    if df.empty: return None,None
    r=df.loc[df["intactness_score_0_100"].astype(float).idxmin()]
    return str(r["metric"]),float(r["intactness_score_0_100"])

def aggregate_pillars(scored_df, config):
    rows=[]
    for pillar,name in PILLARS.items():
        sub=scored_df[(scored_df["pillar"]==pillar)&(scored_df["score_eligible"])&scored_df["intactness_score_0_100"].notna()].copy() if not scored_df.empty else pd.DataFrame()
        vals=sub["intactness_score_0_100"].astype(float).tolist() if not sub.empty else []
        score=geometric_mean(vals) if len(vals)>=config.scoring.min_valid_metrics_per_pillar else None
        lm,lv=_limiting_metric(sub)
        rows.append({"pillar":pillar,"pillar_name":name,"score_0_to_100":score,"concern_label":concern_label(score),
                     "n_scored_metrics":len(vals),"minimum_metrics_required":config.scoring.min_valid_metrics_per_pillar,
                     "limiting_metric":lm,"limiting_metric_score_0_to_100":lv,
                     "status":"scored" if score is not None else "insufficient_metric_coverage","aggregation_method":"geometric_mean"})
    return pd.DataFrame(rows)

def aggregate_overall(pillar_df, config):
    """Return separate condition and pressure summaries.

    Condition is C1+C2+C3. C4 is pressure and is never silently mixed into condition.
    An overall condition composite is shown only when the configured minimum condition
    pillar coverage is met. A complete four-pillar SoN is optional and disabled by default.
    """
    row={"status":"insufficient_condition_coverage","condition_score_0_to_100":None,"condition_concern_label":None,
         "pressure_score_0_to_100":None,"pressure_concern_label":None,"condition_pillars":[],"pressure_pillar":"C4_pressure",
         "limiting_pillar":None,"limiting_metric":None,"limiting_metric_score_0_to_100":None,
         "aggregation_method":"geometric_mean","son_score_0_to_100":None,"son_concern_label":None}
    if pillar_df.empty: return row
    cond=pillar_df[pillar_df.pillar.isin(["C1_extent","C2_vegetation","C3_fauna"]) & pillar_df.score_0_to_100.notna()]
    press=pillar_df[(pillar_df.pillar=="C4_pressure") & pillar_df.score_0_to_100.notna()]
    if len(press)==1:
        row["pressure_score_0_to_100"]=float(press.iloc[0].score_0_to_100); row["pressure_concern_label"]=concern_label(row["pressure_score_0_to_100"])
    row["condition_pillars"]=cond.pillar.tolist()
    if len(cond)>=config.scoring.min_condition_pillars:
        row["condition_score_0_to_100"]=geometric_mean(cond.score_0_to_100.astype(float).tolist()); row["condition_concern_label"]=concern_label(row["condition_score_0_to_100"]); row["status"]="condition_scored"
    if len(cond)>0:
        r=cond.loc[cond.score_0_to_100.astype(float).idxmin()]; row["limiting_pillar"]=str(r.pillar); row["limiting_metric"]=None if pd.isna(r.limiting_metric) else str(r.limiting_metric); row["limiting_metric_score_0_to_100"]=None if pd.isna(r.limiting_metric_score_0_to_100) else float(r.limiting_metric_score_0_to_100)
    if config.scoring.composite_son_enabled and len(pillar_df[pillar_df.score_0_to_100.notna()])==4:
        vals=pillar_df.score_0_to_100.astype(float).tolist(); row["son_score_0_to_100"]=geometric_mean(vals); row["son_concern_label"]=concern_label(row["son_score_0_to_100"])
    return row

def build_scorecard(metric_results, benchmark_results, config):
    b={x.metric:x for x in benchmark_results}; rows=[score_metric(m,b.get(m.metric),config) for m in metric_results]
    df=pd.DataFrame(rows); pillars=aggregate_pillars(df,config); overall=aggregate_overall(pillars,config); return df,pillars,overall

def score_external_observations(observations: pd.DataFrame, config):
    required={"metric","pillar","raw_value","direction","reference_value"}; missing=required-set(observations.columns)
    if missing: raise ValueError(f"External observations missing columns: {sorted(missing)}")
    rows=[]
    for _,r in observations.iterrows():
        rec=SimpleNamespace(metric=str(r.metric),pillar=str(r.pillar),value=float(r.raw_value) if pd.notna(r.raw_value) else None,
                            units=str(r.get("units","")),direction=str(r.direction),reference_allowed=True,status=str(r.get("status","ok")),notes=str(r.get("notes","")),domain=str(r.get("domain","external")),evidence_type=str(r.get("evidence_type","external")))
        bench=benchmark_observation(rec.metric,rec.value,float(r.reference_value) if pd.notna(r.reference_value) else None,rec.direction,str(r.get("reference_level","external")),bool(r.get("reference_approved_for_scoring",False)))
        rows.append(score_metric(rec,bench,config))
    df=pd.DataFrame(rows); return df,aggregate_pillars(df,config),aggregate_overall(aggregate_pillars(df,config),config)
