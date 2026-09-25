"""Universal 0–100 intactness and concern scoring.

Product convention:
  80–100% = Very Low concern
  60–<80%  = Low
  40–<60%  = Moderate
  20–<40%  = High
  0–<20%   = Very High

These five bands are a declared Darukaa product convention. They are not presented as
universal ecological thresholds.

The scoring order is:
raw value → reference comparison → intactness (0–100) → indicator concern →
pillar geometric mean → pillar concern → overall geometric mean → overall concern.

Concern labels are never averaged.
"""
from __future__ import annotations

from math import exp, log
from types import SimpleNamespace
from typing import Any, Dict, Iterable, Optional

import pandas as pd

from .benchmark import benchmark_metric, benchmark_observation
from .registry import PILLARS, get_indicator_spec


CONCERN_BANDS = {
    "very_high": (0.0, 20.0),
    "high": (20.0, 40.0),
    "moderate": (40.0, 60.0),
    "low": (60.0, 80.0),
    "very_low": (80.0, 100.0),
}


def clamp_intactness(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return max(0.0, min(100.0, float(value)))


def concern_label(intactness_score_0_100: Optional[float]) -> Optional[str]:
    """Map continuous 0–100 intactness to the five fixed concern bands."""
    if intactness_score_0_100 is None:
        return None
    x = clamp_intactness(intactness_score_0_100)
    if x < 20.0:
        return "Very High"
    if x < 40.0:
        return "High"
    if x < 60.0:
        return "Moderate"
    if x < 80.0:
        return "Low"
    return "Very Low"


def overall_concern_label(score_0_100: Optional[float]) -> Optional[str]:
    return concern_label(score_0_100)


def geometric_mean(values: Iterable[float]) -> Optional[float]:
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return None
    if any(v < 0 for v in vals):
        raise ValueError("Geometric mean requires non-negative values")
    if any(v == 0 for v in vals):
        return 0.0
    return exp(sum(log(v) for v in vals) / len(vals))


def _metadata(record) -> Dict[str, Any]:
    if isinstance(record, dict):
        raw = record.get("raw_value", record.get("value"))
        return {
            "metric": record["metric"],
            "pillar": record.get("pillar"),
            "raw_value": raw,
            "direction": record.get("direction"),
            "reference_allowed": record.get("reference_allowed", True),
            "reference_type": record.get("reference_type", "external"),
            "units": record.get("units", ""),
            "status": record.get("status", "ok"),
            "notes": record.get("notes", ""),
        }
    # External/field/acoustic observations carry their own scoring metadata and do not
    # need to be hard-coded into the aquatic registry.
    if all(hasattr(record, key) for key in ("pillar", "direction")):
        return {
            "metric": record.metric,
            "pillar": record.pillar,
            "raw_value": getattr(record, "value", getattr(record, "raw_value", None)),
            "direction": record.direction,
            "reference_allowed": getattr(record, "reference_allowed", True),
            "reference_type": getattr(record, "reference_type", "external"),
            "units": getattr(record, "units", ""),
            "status": getattr(record, "status", "ok"),
            "notes": getattr(record, "notes", ""),
        }

    spec = get_indicator_spec(record.metric)
    return {
        "metric": record.metric,
        "pillar": spec.pillar,
        "raw_value": getattr(record, "value", None),
        "direction": spec.direction,
        "reference_allowed": spec.reference_allowed,
        "reference_type": spec.reference_type,
        "units": spec.units,
        "status": getattr(record, "status", "ok"),
        "notes": getattr(record, "notes", ""),
    }


def score_metric(metric_result, benchmark_result, config) -> Dict[str, Any]:
    """Score one registered metric from its approved reference-relative intactness."""
    meta = _metadata(metric_result)
    metric = meta["metric"]
    out = {
        "metric": metric,
        "pillar": meta["pillar"],
        "raw_value": meta["raw_value"],
        "units": meta["units"],
        "reference_value": getattr(benchmark_result, "selected_reference", None),
        "reference_level": getattr(benchmark_result, "selected_reference_level", "none"),
        "raw_relative_ratio": getattr(benchmark_result, "raw_relative_ratio", None),
        "intactness_score_0_100": getattr(benchmark_result, "intactness_score_0_100", None),
        "concern_label": None,
        "scoring_method": "not_scored",
        "score_eligible": False,
        "score_status": "not_eligible",
        "reference_approved_for_scoring": bool(
            getattr(benchmark_result, "reference_approved_for_scoring", False)
        ),
        "notes": meta["notes"],
    }

    if not config.scoring.enabled:
        out["score_status"] = "scoring_disabled"
        return out

    if meta["raw_value"] is None or meta["status"] not in {"ok", "usable"}:
        out["score_status"] = "invalid_metric"
        return out

    if not meta["reference_allowed"]:
        out["score_status"] = "not_referenceable"
        return out

    intact = getattr(benchmark_result, "intactness_score_0_100", None)
    if intact is None:
        out["score_status"] = "reference_unavailable"
        return out

    if not getattr(benchmark_result, "reference_approved_for_scoring", False):
        out["score_status"] = "reference_not_approved_for_scoring"
        return out

    out.update(
        {
            "intactness_score_0_100": clamp_intactness(intact),
            "concern_label": concern_label(intact),
            "scoring_method": "reference_relative_fixed_bands",
            "score_eligible": True,
            "score_status": "scored",
        }
    )
    return out


def _limiting_metric(subset: pd.DataFrame) -> tuple[Optional[str], Optional[float]]:
    if subset.empty:
        return None, None
    row = subset.loc[subset["intactness_score_0_100"].astype(float).idxmin()]
    return str(row["metric"]), float(row["intactness_score_0_100"])


def aggregate_pillars(scored_df: pd.DataFrame, config) -> pd.DataFrame:
    rows = []
    for pillar, pillar_name in PILLARS.items():
        subset = scored_df[
            (scored_df["pillar"] == pillar) &
            (scored_df["score_eligible"]) &
            (scored_df["intactness_score_0_100"].notna())
        ].copy()

        n_metrics = int(len(subset))
        values = subset["intactness_score_0_100"].astype(float).tolist()
        score = (
            geometric_mean(values)
            if n_metrics >= config.scoring.min_valid_metrics_per_pillar
            else None
        )
        limiting_metric, limiting_value = _limiting_metric(subset)

        rows.append(
            {
                "pillar": pillar,
                "pillar_name": pillar_name,
                "score_0_to_100": score,
                "concern_label": concern_label(score),
                "n_scored_metrics": n_metrics,
                "minimum_metrics_required": config.scoring.min_valid_metrics_per_pillar,
                "limiting_metric": limiting_metric,
                "limiting_metric_score_0_to_100": limiting_value,
                "status": "scored" if score is not None else "insufficient_metric_coverage",
                "aggregation_method": "geometric_mean",
            }
        )

    return pd.DataFrame(rows)


def aggregate_overall(pillar_df: pd.DataFrame, config) -> Dict[str, Any]:
    if not config.scoring.composite_son_enabled:
        return {
            "status": "composite_disabled",
            "score_0_to_100": None,
            "concern_label": None,
            "n_valid_pillars": int(pillar_df["score_0_to_100"].notna().sum()) if not pillar_df.empty else 0,
            "required_pillars": config.scoring.total_pillars,
            "aggregation_method": "geometric_mean",
        }

    scored = pillar_df[pillar_df["score_0_to_100"].notna()].copy()
    n = len(scored)

    if n < config.scoring.min_valid_pillars:
        return {
            "status": "insufficient_pillar_coverage",
            "score_0_to_100": None,
            "concern_label": None,
            "n_valid_pillars": n,
            "required_pillars": config.scoring.total_pillars,
            "limiting_pillar": None,
            "limiting_metric": None,
            "aggregation_method": "geometric_mean",
        }

    if config.scoring.require_complete_pillars and n != config.scoring.total_pillars:
        return {
            "status": "incomplete_pillar_coverage",
            "score_0_to_100": None,
            "concern_label": None,
            "n_valid_pillars": n,
            "required_pillars": config.scoring.total_pillars,
            "limiting_pillar": None,
            "limiting_metric": None,
            "aggregation_method": "geometric_mean",
        }

    score = geometric_mean(scored["score_0_to_100"].astype(float).tolist())
    limiting_row = scored.loc[scored["score_0_to_100"].astype(float).idxmin()]
    limiting_pillar = str(limiting_row["pillar"])
    limiting_pillar_score = float(limiting_row["score_0_to_100"])
    limiting_metric = limiting_row.get("limiting_metric")
    limiting_metric_score = limiting_row.get("limiting_metric_score_0_to_100")

    return {
        "status": "scored",
        "score_0_to_100": score,
        "concern_label": concern_label(score),
        "n_valid_pillars": n,
        "required_pillars": config.scoring.total_pillars,
        "limiting_pillar": limiting_pillar,
        "limiting_pillar_score_0_to_100": limiting_pillar_score,
        "limiting_metric": None if pd.isna(limiting_metric) else limiting_metric,
        "limiting_metric_score_0_to_100": None if pd.isna(limiting_metric_score) else float(limiting_metric_score),
        "aggregation_method": "geometric_mean",
        "concern_rule": "fixed five equal bands on 0–100 intactness; labels are not averaged",
    }


def build_scorecard(metric_results: Iterable, benchmark_results: Iterable, config):
    """Build metric concern, pillar and overall scorecards."""
    benchmarks = {b.metric: b for b in benchmark_results}
    rows = [score_metric(m, benchmarks.get(m.metric), config) for m in metric_results]
    scored_df = pd.DataFrame(rows)

    if scored_df.empty:
        pillar_df = pd.DataFrame(
            [
                {
                    "pillar": p,
                    "pillar_name": n,
                    "score_0_to_100": None,
                    "concern_label": None,
                    "n_scored_metrics": 0,
                    "minimum_metrics_required": config.scoring.min_valid_metrics_per_pillar,
                    "limiting_metric": None,
                    "limiting_metric_score_0_to_100": None,
                    "status": "no_metrics",
                    "aggregation_method": "geometric_mean",
                }
                for p, n in PILLARS.items()
            ]
        )
        overall = aggregate_overall(pillar_df, config)
        return scored_df, pillar_df, overall

    pillar_df = aggregate_pillars(scored_df, config)
    overall = aggregate_overall(pillar_df, config)
    return scored_df, pillar_df, overall


def score_external_observations(
    observations: pd.DataFrame,
    config,
) -> tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """Score field/terrestrial/acoustic observations without changing the aquatic registry.

    Required columns:
      metric, pillar, raw_value, direction, reference_value

    Optional:
      units, reference_type, reference_level, reference_approved_for_scoring, status, notes
    """
    required = {"metric", "pillar", "raw_value", "direction", "reference_value"}
    missing = required - set(observations.columns)
    if missing:
        raise ValueError(f"External observations missing columns: {sorted(missing)}")

    rows = []
    for _, row in observations.iterrows():
        record = SimpleNamespace(
            metric=str(row["metric"]),
            pillar=str(row["pillar"]),
            value=float(row["raw_value"]) if pd.notna(row["raw_value"]) else None,
            units=str(row.get("units", "")),
            direction=str(row["direction"]),
            reference_allowed=True,
            reference_type=str(row.get("reference_type", "external")),
            status=str(row.get("status", "ok")),
            notes=str(row.get("notes", "")),
        )
        bench = benchmark_observation(
            metric_name=record.metric,
            observed=record.value,
            reference=float(row["reference_value"]) if pd.notna(row["reference_value"]) else None,
            direction=record.direction,
            reference_level=str(row.get("reference_level", "external")),
            reference_approved=bool(row.get("reference_approved_for_scoring", True)),
        )
        rows.append(score_metric(record, bench, config))

    scored_df = pd.DataFrame(rows)
    pillar_df = aggregate_pillars(scored_df, config)
    overall = aggregate_overall(pillar_df, config)
    return scored_df, pillar_df, overall


def summarize_composite(metric_records, thresholds_by_metric: Dict[str, Dict[str, float]] | None = None) -> Dict[str, Any]:
    """Compatibility helper for old notebooks.

    New production scoring does not use metric-specific raw thresholds. It uses approved
    reference values and the fixed 0–100 intactness bands.
    """
    return {
        "enabled": False,
        "score_0_to_100": None,
        "n_metrics": 0,
        "reason": "Legacy helper retained for compatibility; use build_scorecard() or score_external_observations().",
    }
