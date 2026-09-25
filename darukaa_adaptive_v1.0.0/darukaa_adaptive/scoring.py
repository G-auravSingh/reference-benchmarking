"""Explicit metric, pillar and overall concern scoring.

Scoring is only activated when approved thresholds or explicitly enabled reference-relative
bands are supplied. No generic aquatic thresholds are invented by this module.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

import pandas as pd

from .registry import get_indicator_spec


CONCERN_LABELS = {1: "Very Low", 2: "Low", 3: "Moderate", 4: "High", 5: "Very High"}


def score_with_thresholds(value: Optional[float], thresholds: Dict[str, float], lower_is_better: bool) -> Optional[int]:
    if value is None:
        return None
    t1, t2, t3, t4 = [float(thresholds[k]) for k in ("t1", "t2", "t3", "t4")]
    if not t1 < t2 < t3 < t4:
        raise ValueError("Thresholds t1<t2<t3<t4 are required")
    if lower_is_better:
        if value >= t4:
            return 5
        if value >= t3:
            return 4
        if value >= t2:
            return 3
        if value >= t1:
            return 2
        return 1
    if value <= t1:
        return 5
    if value <= t2:
        return 4
    if value <= t3:
        return 3
    if value <= t4:
        return 2
    return 1


def score_from_intactness(value: Optional[float], thresholds: Dict[str, float]) -> Optional[int]:
    """Map 0-1 intactness to concern 1-5.

    r1..r4 are ascending intactness thresholds. Higher intactness means lower concern.
    """
    if value is None:
        return None
    r1, r2, r3, r4 = [float(thresholds[k]) for k in ("r1", "r2", "r3", "r4")]
    if not r1 < r2 < r3 < r4:
        raise ValueError("r1<r2<r3<r4 is required")
    if value <= r1:
        return 5
    if value <= r2:
        return 4
    if value <= r3:
        return 3
    if value <= r4:
        return 2
    return 1


def concern_label(score: Optional[float]) -> Optional[str]:
    if score is None:
        return None
    score = float(score)
    if score <= 1.5:
        return "Very Low"
    if score <= 2.5:
        return "Low"
    if score <= 3.5:
        return "Moderate"
    if score <= 4.25:
        return "High"
    return "Very High"


def overall_concern_label(score_0_10: Optional[float]) -> Optional[str]:
    if score_0_10 is None:
        return None
    score_0_10 = float(score_0_10)
    if score_0_10 < 4:
        return "Very Low"
    if score_0_10 < 5:
        return "Low"
    if score_0_10 < 7:
        return "Moderate"
    if score_0_10 < 8:
        return "High"
    return "Very High"


def score_metric(metric_result, benchmark_result, config) -> Dict[str, Any]:
    spec = get_indicator_spec(metric_result.metric)
    out = {
        "metric": metric_result.metric,
        "pillar": spec.pillar,
        "raw_value": metric_result.value,
        "concern_score_1_to_5": None,
        "concern_label": None,
        "scoring_method": "not_scored",
        "score_eligible": False,
        "score_status": "not_eligible",
    }

    if not config.scoring.enabled or not config.scoring.composite_son_enabled:
        out["score_status"] = "composite_disabled"
        return out
    if metric_result.value is None or metric_result.status not in {"ok", "usable"}:
        out["score_status"] = "invalid_metric"
        return out
    if not spec.reference_allowed and metric_result.metric not in config.scoring.thresholds_by_metric:
        out["score_status"] = "contextual_metric"
        return out

    if metric_result.metric in config.scoring.thresholds_by_metric:
        if spec.direction == "context_dependent":
            out["score_status"] = "direction_context_dependent"
            return out
        thresholds = config.scoring.thresholds_by_metric[metric_result.metric]
        lower_is_better = spec.direction == "lower_is_better"
        score = score_with_thresholds(metric_result.value, thresholds, lower_is_better)
        out.update({
            "concern_score_1_to_5": score,
            "concern_label": CONCERN_LABELS.get(score),
            "scoring_method": "approved_thresholds",
            "score_eligible": score is not None,
            "score_status": "scored" if score is not None else "invalid_metric",
        })
        return out

    if config.scoring.reference_relative_enabled:
        thresholds = config.scoring.reference_ratio_thresholds_by_metric.get(metric_result.metric)
        approved_reference = bool(
            benchmark_result
            and (
                benchmark_result.selected_reference_level == "tier1" and config.reference.tier1_approved_for_scoring
                or benchmark_result.selected_reference_level == "tier2" and config.reference.tier2_approved_for_scoring
            )
        )
        if thresholds and approved_reference and benchmark_result.intactness_ratio is not None:
            score = score_from_intactness(benchmark_result.intactness_ratio, thresholds)
            out.update({
                "concern_score_1_to_5": score,
                "concern_label": CONCERN_LABELS.get(score),
                "scoring_method": "reference_relative_intactness",
                "score_eligible": score is not None,
                "score_status": "scored" if score is not None else "invalid_benchmark",
            })
            return out

    out["score_status"] = "thresholds_or_reference_band_required"
    return out


def aggregate_pillars(scored_df: pd.DataFrame, config) -> pd.DataFrame:
    rows = []
    for pillar in [f"P{i}_" + n for i, n in enumerate([
        "ecosystem_condition", "species_assemblage", "species_status", "threats"
    ], start=1)]:
        subset = scored_df[(scored_df["pillar"] == pillar) & (scored_df["score_eligible"])]
        n_metrics = int(len(subset))
        score = float(subset["concern_score_1_to_5"].mean()) if n_metrics >= config.scoring.min_valid_metrics_per_pillar else None
        rows.append({
            "pillar": pillar,
            "score_1_to_5": score,
            "concern_label": concern_label(score),
            "n_scored_metrics": n_metrics,
            "minimum_metrics_required": config.scoring.min_valid_metrics_per_pillar,
            "status": "scored" if score is not None else "insufficient_metric_coverage",
        })
    return pd.DataFrame(rows)


def aggregate_overall(pillar_df: pd.DataFrame, config) -> Dict[str, Any]:
    scored = pillar_df[pillar_df["score_1_to_5"].notna()].copy()
    n = len(scored)
    if n < config.scoring.min_valid_pillars:
        return {
            "status": "insufficient_pillar_coverage",
            "score_0_to_10": None,
            "concern_label": None,
            "n_valid_pillars": n,
            "required_pillars": config.scoring.min_valid_pillars,
            "formula": "((sum(mean pillar scores)-n)/(n*4))*10",
        }
    if config.scoring.require_complete_pillars and n != config.scoring.total_pillars:
        return {
            "status": "incomplete_pillar_coverage",
            "score_0_to_10": None,
            "concern_label": None,
            "n_valid_pillars": n,
            "required_pillars": config.scoring.total_pillars,
            "formula": "((sum(mean pillar scores)-n)/(n*4))*10",
        }

    score = ((float(scored["score_1_to_5"].sum()) - n) / (n * 4.0)) * 10.0
    score = max(0.0, min(10.0, score))
    return {
        "status": "scored",
        "score_0_to_10": score,
        "concern_label": overall_concern_label(score),
        "n_valid_pillars": n,
        "required_pillars": config.scoring.total_pillars,
        "formula": "((sum(mean pillar scores)-n)/(n*4))*10",
    }


def build_scorecard(metric_results: Iterable, benchmark_results: Iterable, config):
    benchmarks = {b.metric: b for b in benchmark_results}
    rows = [score_metric(m, benchmarks.get(m.metric), config) for m in metric_results]
    scored_df = pd.DataFrame(rows)
    if scored_df.empty:
        pillar_df = pd.DataFrame()
        overall = {"status": "no_metrics", "score_0_to_10": None}
    else:
        pillar_df = aggregate_pillars(scored_df, config)
        overall = aggregate_overall(pillar_df, config)
    return scored_df, pillar_df, overall


def summarize_composite(metric_records, thresholds_by_metric: Dict[str, Dict[str, float]]) -> Dict[str, Any]:
    """Backward-compatible helper for older notebook calls."""
    scored = []
    for metric in metric_records:
        th = thresholds_by_metric.get(metric.metric)
        if not th:
            continue
        lower_is_better = metric.direction == "lower_is_better"
        value = score_with_thresholds(metric.value, th, lower_is_better)
        if value is not None:
            scored.append(value)
    if not scored:
        return {"enabled": False, "score": None, "n_metrics": 0, "reason": "No explicitly thresholded eligible metrics."}
    mean = sum(scored) / len(scored)
    return {"enabled": True, "score_1_to_5": mean, "n_metrics": len(scored), "label": concern_label(mean)}
