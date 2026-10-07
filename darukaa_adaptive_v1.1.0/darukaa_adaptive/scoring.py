"""Evidence-aware metric, subdimension, pillar and condition scoring.

The scoring layer deliberately separates:
1. statistical/reference benchmarking at metric level;
2. common 0–100 attainment for aggregation;
3. within-subdimension geometric aggregation;
4. pillar limiting-factor selection; and
5. overall condition geometric aggregation with the limiting pillar reported.

Pressure is never mixed into the State-of-Nature condition score.
"""
from __future__ import annotations
from types import SimpleNamespace
from typing import Any
import math
import pandas as pd
from .benchmark import benchmark_observation
from .registry import PILLARS, get_indicator_spec, effective_scoring_role

BANDS = ((0,20,"Very High"),(20,40,"High"),(40,60,"Moderate"),(60,80,"Low"),(80,100.000001,"Very Low"))


def clamp_score(value):
    if value is None or not math.isfinite(float(value)): return None
    return max(0.0, min(100.0, float(value)))


def concern_label(score):
    score = clamp_score(score)
    if score is None: return None
    for lo, hi, label in BANDS:
        if lo <= score < hi: return label
    return "Very Low"


def geometric_mean(values):
    vals=[float(v) for v in values if v is not None and math.isfinite(float(v))]
    if not vals: return None
    if any(v < 0 for v in vals): raise ValueError("geometric mean requires non-negative values")
    return float(math.exp(sum(math.log(max(v,1e-12)) for v in vals)/len(vals)))


def _metadata(record):
    spec = get_indicator_spec(record.metric)
    return {
        "metric": record.metric, "pillar": spec.pillar, "construct": spec.construct,
        "subdimension": spec.subdimension, "raw_value": getattr(record,"value",None),
        "units": getattr(record,"units",spec.units), "direction": getattr(record,"direction",spec.direction),
        "reference_allowed": getattr(record,"reference_allowed",spec.reference_allowed),
        "status": getattr(record,"status","ok"), "scoring_role": effective_scoring_role(spec, getattr(record, "_config", None)),
        "notes": getattr(record,"notes",""), "domain": getattr(record,"domain",spec.domain),
    }


def score_metric(metric_result, benchmark_result, config):
    meta=_metadata(metric_result); meta["scoring_role"] = effective_scoring_role(get_indicator_spec(metric_result.metric), config); b=benchmark_result
    attainment = getattr(b,"reference_attainment_0_100",None) if b else None
    out={
        "metric":meta["metric"],"pillar":meta["pillar"],"construct":meta["construct"],"subdimension":meta["subdimension"],
        "raw_value":meta["raw_value"],"units":meta["units"],
        "reference_value":getattr(b,"selected_reference",None) if b else None,
        "reference_level":getattr(b,"selected_reference_level","none") if b else "none",
        "reference_n":getattr(b,"reference_n",None) if b else None,
        "reference_uncertainty":getattr(b,"reference_uncertainty",None) if b else None,
        "reference_ci_low":getattr(b,"reference_ci_low",None) if b else None,
        "reference_ci_high":getattr(b,"reference_ci_high",None) if b else None,
        "raw_relative_ratio":getattr(b,"raw_relative_ratio",None) if b else None,
        "relative_departure_pct":getattr(b,"relative_departure_pct",None) if b else None,
        "reference_attainment_0_100":clamp_score(attainment),
        "intactness_score_0_100":clamp_score(attainment),
        "reference_state":getattr(b,"reference_state","") if b else "",
        "reference_approval_basis":getattr(b,"reference_approval_basis","") if b else "",
        "reference_diagnostics":getattr(b,"reference_diagnostics",None) if b else None,
        "standardized_z":getattr(b,"standardized_z",None) if b else None,
        "robust_z":getattr(b,"robust_z",None) if b else None,
        "interpretation_status":getattr(b,"interpretation_status","") if b else "",
        "concern_label":None,"score_eligible":False,"score_status":"not_eligible",
        "reference_approved_for_scoring":bool(getattr(b,"reference_approved_for_scoring",False)) if b else False,
        "scoring_role":meta["scoring_role"],"evidence_type":getattr(metric_result,"evidence_type","EO"),
        "domain":meta["domain"],"notes":meta["notes"],
    }
    if not config.scoring.enabled: out["score_status"]="scoring_disabled"; return out
    if meta["scoring_role"] in {"CONTEXTUAL","DIAGNOSTIC","PENDING"}: out["score_status"]="contextual_not_scored"; return out
    if meta["raw_value"] is None or meta["status"] not in {"ok","usable","calculated"}: out["score_status"]="invalid_metric"; return out
    if not meta["reference_allowed"]: out["score_status"]="not_referenceable"; return out
    if attainment is None: out["score_status"]="reference_unavailable"; return out
    if not getattr(b,"reference_approved_for_scoring",False): out["score_status"]="reference_not_approved_for_scoring"; return out
    out.update({"reference_attainment_0_100":clamp_score(attainment),"intactness_score_0_100":clamp_score(attainment),
                "concern_label":concern_label(attainment),"score_eligible":True,"score_status":"scored"})
    return out


def _valid_scored(df):
    if df is None or df.empty: return pd.DataFrame()
    out=df.copy()
    aliases={"C1_extent":"P1_extent_configuration","C2_vegetation":"P2_ecosystem_condition","C3_fauna":"P3_biodiversity_integrity","C4_pressure":"P4_pressure"}
    out["pillar"]=out["pillar"].map(lambda x: aliases.get(x,x))
    if "subdimension" not in out.columns:
        out["subdimension"]=out["metric"].astype(str)
    else:
        out["subdimension"]=out["subdimension"].fillna(out["metric"].astype(str))
    if "score_eligible" not in out.columns:
        out["score_eligible"]=True
    return out[out["score_eligible"] & out["intactness_score_0_100"].notna()].copy()


def aggregate_subdimensions(scored_df, config):
    """Geometric mean complementary metrics within each ecological subdimension."""
    sdf=_valid_scored(scored_df)
    rows=[]
    for (pillar, subdimension), g in sdf.groupby(["pillar","subdimension"], dropna=False):
        vals=g["intactness_score_0_100"].astype(float).tolist()
        if len(vals) < config.scoring.min_valid_metrics_per_subdimension:
            score=None; status="insufficient_metric_coverage"
        else:
            score=geometric_mean(vals); status="scored"
        lm=None; lv=None
        if vals:
            idx=g["intactness_score_0_100"].astype(float).idxmin(); lm=str(g.loc[idx,"metric"]); lv=float(g.loc[idx,"intactness_score_0_100"])
        rows.append({"pillar":pillar,"pillar_name":PILLARS.get(pillar,pillar),"subdimension":subdimension,
                     "score_0_to_100":score,"concern_label":concern_label(score),"n_scored_metrics":len(vals),
                     "limiting_metric":lm,"limiting_metric_score_0_to_100":lv,"status":status,
                     "aggregation_method":"geometric_mean"})
    return pd.DataFrame(rows)


def aggregate_pillars(scored_df, config):
    """Pillar headline = weakest defensible subdimension, with metric traceability."""
    subdf=aggregate_subdimensions(scored_df,config)
    rows=[]
    for pillar,name in PILLARS.items():
        g=subdf[(subdf["pillar"]==pillar) & subdf["score_0_to_100"].notna()] if not subdf.empty else pd.DataFrame()
        if g.empty:
            rows.append({"pillar":pillar,"pillar_name":name,"score_0_to_100":None,"concern_label":None,
                         "n_scored_metrics":0,"n_scored_subdimensions":0,"minimum_metrics_required":config.scoring.min_valid_metrics_per_pillar,
                         "limiting_subdimension":None,"limiting_metric":None,"limiting_metric_score_0_to_100":None,
                         "status":"insufficient_metric_coverage","aggregation_method":"limiting_factor"})
            continue
        idx=g["score_0_to_100"].astype(float).idxmin(); r=g.loc[idx]
        rows.append({"pillar":pillar,"pillar_name":name,"score_0_to_100":float(r["score_0_to_100"]),
                     "concern_label":concern_label(r["score_0_to_100"]),"n_scored_metrics":int(g["n_scored_metrics"].sum()),
                     "n_scored_subdimensions":int(len(g)),"minimum_metrics_required":config.scoring.min_valid_metrics_per_pillar,
                     "limiting_subdimension":str(r["subdimension"]),"limiting_metric":r["limiting_metric"],
                     "limiting_metric_score_0_to_100":r["limiting_metric_score_0_to_100"],"status":"scored",
                     "aggregation_method":"limiting_factor_over_geometric_mean_subdimensions"})
    return pd.DataFrame(rows)


def aggregate_overall(pillar_df, config):
    row={"status":"insufficient_condition_coverage","condition_score_0_to_100":None,"condition_concern_label":None,
         "pressure_intactness_score_0_to_100":None,"pressure_concern_label":None,
         # Backward-compatible alias retained for downstream consumers. The
         # client-facing reports use the explicit pressure_intactness name.
         "pressure_score_0_to_100":None,
         "condition_pillars":[],"condition_pillar_count":0,"condition_pillar_total":3,
         "condition_coverage":"none","pressure_pillar":"P4_pressure",
         "limiting_pillar":None,"limiting_metric":None,"limiting_metric_score_0_to_100":None,
         "aggregation_method":"geometric_mean_condition_pillars","son_score_0_to_100":None,"son_concern_label":None}
    if pillar_df is None or pillar_df.empty: return row
    cond=pillar_df[pillar_df.pillar.isin(["P1_extent_configuration","P2_ecosystem_condition","P3_biodiversity_integrity"]) & pillar_df.score_0_to_100.notna()].copy()
    press=pillar_df[(pillar_df.pillar=="P4_pressure") & pillar_df.score_0_to_100.notna()]
    if len(press)==1:
        pi=float(press.iloc[0].score_0_to_100)
        row["pressure_intactness_score_0_to_100"]=pi
        row["pressure_score_0_to_100"]=pi
        row["pressure_concern_label"]=concern_label(pi)
    row["condition_pillars"]=cond.pillar.tolist()
    row["condition_pillar_count"]=int(len(cond))
    row["condition_coverage"]=("complete" if len(cond)==3 else "partial" if len(cond)>0 else "none")
    fauna_required=bool(getattr(config.scoring,"require_fauna_for_condition",False))
    fauna_present="P3_biodiversity_integrity" in set(cond.pillar)
    condition_gate=(len(cond)>=config.scoring.min_condition_pillars and (not fauna_required or fauna_present))
    if condition_gate:
        row["condition_score_0_to_100"]=geometric_mean(cond.score_0_to_100.astype(float).tolist())
        row["condition_concern_label"]=concern_label(row["condition_score_0_to_100"])
        row["status"]="condition_scored" if len(cond)==3 else "condition_scored_partial"
    elif fauna_required and not fauna_present: row["status"]="insufficient_fauna_coverage"
    if not cond.empty:
        r=cond.loc[cond.score_0_to_100.astype(float).idxmin()]; row["limiting_pillar"]=str(r.pillar); row["limiting_metric"]=None if pd.isna(r.limiting_metric) else str(r.limiting_metric); row["limiting_metric_score_0_to_100"]=None if pd.isna(r.limiting_metric_score_0_to_100) else float(r.limiting_metric_score_0_to_100)
    return row


def build_scorecard(metric_results, benchmark_results, config):
    b={x.metric:x for x in benchmark_results}; rows=[score_metric(m,b.get(m.metric),config) for m in metric_results]
    df=pd.DataFrame(rows); sub=aggregate_subdimensions(df,config); pillars=aggregate_pillars(df,config); overall=aggregate_overall(pillars,config)
    return df,pillars,overall


def score_external_observations(observations: pd.DataFrame, config):
    required={"metric","pillar","raw_value","direction","reference_value"}; missing=required-set(observations.columns)
    if missing: raise ValueError(f"External observations missing columns: {sorted(missing)}")
    rows=[]
    for _,r in observations.iterrows():
        spec=get_indicator_spec(str(r.metric))
        rec=SimpleNamespace(metric=str(r.metric),pillar=spec.pillar,value=float(r.raw_value) if pd.notna(r.raw_value) else None,
            units=str(r.get("units",spec.units)),direction=spec.direction,reference_allowed=spec.reference_allowed,
            status=str(r.get("status","ok")),notes=str(r.get("notes",spec.notes)),domain=spec.domain,evidence_type=str(r.get("evidence_type","external")))
        bench=benchmark_observation(rec.metric,rec.value,float(r.reference_value) if pd.notna(r.reference_value) else None,rec.direction,str(r.get("reference_level","external")),bool(r.get("reference_approved_for_scoring",False)))
        rows.append(score_metric(rec,bench,config))
    df=pd.DataFrame(rows); pillars=aggregate_pillars(df,config); return df,pillars,aggregate_overall(pillars,config)
