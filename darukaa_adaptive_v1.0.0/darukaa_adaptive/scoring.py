"""Universal reference-relative 0–100 scoring and four-pillar aggregation."""
from __future__ import annotations

from math import exp, log
from typing import Any, Dict, Iterable, Optional

import pandas as pd

from .benchmark import benchmark_observation
from .registry import PILLARS


CONCERN_BANDS = [
    (80.0, 100.000001, "Very Low"),
    (60.0, 80.0, "Low"),
    (40.0, 60.0, "Moderate"),
    (20.0, 40.0, "High"),
    (0.0, 20.0, "Very High"),
]


def clamp_0_100(value: Optional[float]) -> Optional[float]:
    return None if value is None else max(0.0, min(100.0, float(value)))


def concern_label(score_0_100: Optional[float]) -> Optional[str]:
    if score_0_100 is None:
        return None
    x = round(clamp_0_100(score_0_100), 10)
    if x >= 80: return "Very Low"
    if x >= 60: return "Low"
    if x >= 40: return "Moderate"
    if x >= 20: return "High"
    return "Very High"


def geometric_mean(values: Iterable[float]) -> Optional[float]:
    vals = [float(v) for v in values if v is not None and pd.notna(v)]
    if not vals:
        return None
    if any(v < 0 for v in vals):
        raise ValueError("Geometric mean requires non-negative scores")
    if any(v == 0 for v in vals):
        return 0.0
    return float(exp(sum(log(v) for v in vals) / len(vals)))


def _limiting_row(df: pd.DataFrame):
    if df.empty:
        return None
    return df.loc[df["intactness_score_0_100"].astype(float).idxmin()]


def score_metric(metric_result, benchmark_result, config) -> Dict[str, Any]:
    row = metric_result.to_dict() if hasattr(metric_result, "to_dict") else dict(metric_result)
    out = {
        "metric": row.get("metric"), "pillar": row.get("pillar"), "construct": row.get("construct"),
        "subdimension": row.get("subdimension"), "domain": row.get("domain"),
        "raw_value": row.get("value"), "units": row.get("units"), "direction": row.get("direction"),
        "evidence_class": row.get("evidence_class", "measured"), "source_type": row.get("source_type", "eo"),
        "reference_value": None if benchmark_result is None else benchmark_result.reference_value,
        "reference_level": "none" if benchmark_result is None else benchmark_result.reference_level,
        "reference_source": "none" if benchmark_result is None else benchmark_result.reference_source,
        "reference_n": None if benchmark_result is None else benchmark_result.reference_n,
        "reference_se": None if benchmark_result is None else benchmark_result.reference_se,
        "raw_relative_ratio": None if benchmark_result is None else benchmark_result.raw_relative_ratio,
        "signed_benchmark": None if benchmark_result is None else benchmark_result.signed_benchmark,
        "percentile_in_reference": None if benchmark_result is None else benchmark_result.percentile_in_reference,
        "intactness_score_0_100": None if benchmark_result is None else benchmark_result.intactness_score_0_100,
        "concern_label": None,
        "score_eligible": False,
        "score_status": "not_eligible",
        "reference_approved_for_scoring": False if benchmark_result is None else bool(benchmark_result.reference_approved_for_scoring),
        "notes": row.get("notes", ""),
    }
    if not config.scoring.enabled:
        out["score_status"] = "scoring_disabled"; return out
    if row.get("value") is None or row.get("status") not in {"ok", "usable"}:
        out["score_status"] = "invalid_metric"; return out
    if benchmark_result is None:
        out["score_status"] = "reference_unavailable"; return out
    if not benchmark_result.reference_approved_for_scoring:
        out["score_status"] = "reference_not_approved"; return out
    if benchmark_result.intactness_score_0_100 is None:
        out["score_status"] = benchmark_result.benchmark_status or "reference_unusable"; return out
    score = clamp_0_100(benchmark_result.intactness_score_0_100)
    out.update({"intactness_score_0_100": score, "concern_label": concern_label(score), "score_eligible": True, "score_status": "scored"})
    return out


def aggregate_pillars(scored_df: pd.DataFrame, config) -> pd.DataFrame:
    rows = []
    for pillar, name in PILLARS.items():
        subset = scored_df[(scored_df["pillar"] == pillar) & (scored_df["score_eligible"]) & scored_df["intactness_score_0_100"].notna()].copy() if not scored_df.empty else pd.DataFrame()
        values = subset["intactness_score_0_100"].astype(float).tolist() if not subset.empty else []
        score = geometric_mean(values) if len(values) >= config.scoring.min_valid_metrics_per_pillar else None
        lim = _limiting_row(subset)
        rows.append({
            "pillar": pillar, "pillar_name": name, "score_0_to_100": score,
            "concern_label": concern_label(score), "n_scored_metrics": len(values),
            "minimum_metrics_required": config.scoring.min_valid_metrics_per_pillar,
            "limiting_metric": None if lim is None else lim["metric"],
            "limiting_metric_score_0_to_100": None if lim is None else float(lim["intactness_score_0_100"]),
            "status": "scored" if score is not None else "insufficient_metric_coverage",
            "aggregation_method": "geometric_mean_of_continuous_0_100_scores",
        })
    return pd.DataFrame(rows)


def _aggregate_pillar_set(pillar_df: pd.DataFrame, pillars: list[str], min_n: int):
    if pillar_df.empty:
        return None, 0, None
    sub = pillar_df[pillar_df["pillar"].isin(pillars) & pillar_df["score_0_to_100"].notna()].copy()
    if len(sub) < min_n:
        return None, len(sub), None
    score = geometric_mean(sub["score_0_to_100"].astype(float).tolist())
    lim = sub.loc[sub["score_0_to_100"].astype(float).idxmin()]
    return score, len(sub), lim


def aggregate_overall(pillar_df: pd.DataFrame, config) -> Dict[str, Any]:
    condition_score, n_condition, condition_lim = _aggregate_pillar_set(pillar_df, config.scoring.condition_pillars, 3)
    pressure_sub = pillar_df[pillar_df["pillar"] == config.scoring.pressure_pillar] if not pillar_df.empty else pd.DataFrame()
    pressure_score = float(pressure_sub["score_0_to_100"].iloc[0]) if not pressure_sub.empty and pd.notna(pressure_sub["score_0_to_100"].iloc[0]) else None
    son_score = None
    son_lim = None
    valid_all = pillar_df[pillar_df["score_0_to_100"].notna()].copy() if not pillar_df.empty else pd.DataFrame()
    if config.scoring.composite_son_enabled and len(valid_all) == config.scoring.total_pillars:
        son_score = geometric_mean(valid_all["score_0_to_100"].astype(float).tolist())
        son_lim = valid_all.loc[valid_all["score_0_to_100"].astype(float).idxmin()]
    return {
        "status": "scored" if son_score is not None else "incomplete_four_pillar_coverage",
        "overall_son_score_0_to_100": son_score,
        "overall_son_concern": concern_label(son_score),
        "overall_son_limiting_pillar": None if son_lim is None else son_lim["pillar"],
        "overall_son_limiting_pillar_score": None if son_lim is None else float(son_lim["score_0_to_100"]),
        "overall_son_limiting_metric": None if son_lim is None else son_lim.get("limiting_metric"),
        "overall_son_limiting_metric_score": None if son_lim is None or pd.isna(son_lim.get("limiting_metric_score_0_to_100")) else float(son_lim.get("limiting_metric_score_0_to_100")),
        "condition_score_0_to_100": condition_score,
        "condition_concern": concern_label(condition_score),
        "condition_limiting_pillar": None if condition_lim is None else condition_lim["pillar"],
        "condition_limiting_pillar_score": None if condition_lim is None else float(condition_lim["score_0_to_100"]),
        "pressure_score_0_to_100": pressure_score,
        "pressure_concern": concern_label(pressure_score),
        "n_condition_pillars": n_condition,
        "n_valid_pillars": len(valid_all),
        "required_pillars": config.scoring.total_pillars,
        "aggregation_method": "geometric_mean_of_continuous_0_100_scores",
        "concern_convention": "80-100 Very Low; 60-<80 Low; 40-<60 Moderate; 20-<40 High; 0-<20 Very High",
        "reference_point": "50% is the declared reference-condition midpoint of the normalised score; labels are applied only after aggregation.",
        "condition_pressure_separation": True,
    }


def build_scorecard(metric_results: Iterable, benchmark_results: Iterable, config):
    benchmarks = {b.metric: b for b in benchmark_results}
    rows = [score_metric(m, benchmarks.get(m.metric), config) for m in metric_results]
    scored_df = pd.DataFrame(rows)
    pillars = aggregate_pillars(scored_df, config)
    overall = aggregate_overall(pillars, config)
    return scored_df, pillars, overall


def build_external_scorecard(records, config):
    rows = []
    benchmarks = []
    for rec in records:
        b = benchmark_observation(rec, config); benchmarks.append(b)
        rows.append({
            "metric": rec.metric, "pillar": rec.pillar, "construct": "external", "subdimension": "external",
            "domain": rec.source_type, "raw_value": rec.raw_value, "units": rec.units,
            "direction": rec.direction, "evidence_class": rec.evidence_class, "source_type": rec.source_type,
            "reference_value": b.reference_value, "reference_level": b.reference_level, "reference_source": b.reference_source,
            "reference_n": b.reference_n, "reference_se": b.reference_se, "raw_relative_ratio": b.raw_relative_ratio,
            "signed_benchmark": b.signed_benchmark, "percentile_in_reference": b.percentile_in_reference,
            "intactness_score_0_100": b.intactness_score_0_100, "concern_label": concern_label(b.intactness_score_0_100),
            "score_eligible": b.reference_approved_for_scoring, "score_status": "scored" if b.reference_approved_for_scoring else b.benchmark_status,
            "reference_approved_for_scoring": b.reference_approved_for_scoring, "notes": rec.notes,
        })
    return pd.DataFrame(rows), benchmarks
