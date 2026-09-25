"""Biodiversity-assessment readiness and evidence-sufficiency checks."""
from __future__ import annotations

from typing import Any, Dict, Iterable


def assess_readiness(config, boundary_area_ha: float, metrics: Iterable, benchmarks=None, scoring=None) -> Dict[str, Any]:
    metrics = list(metrics)
    benchmarks = list(benchmarks or [])
    scoring = scoring or {}

    usable = [m for m in metrics if m.status in {"ok", "usable"} and m.value is not None]
    eligible_reference = [m for m in metrics if m.reference_allowed]
    trend = next((m for m in metrics if m.metric == "riparian_ndvi_sen_slope"), None)
    benchmark_ok = [b for b in benchmarks if b.benchmark_status == "ok"]

    return {
        "geometry": {
            "status": "ready" if boundary_area_ha > 0 else "invalid",
            "boundary_area_ha": round(boundary_area_ha, 6),
            "boundary_type": config.site_boundary_type,
        },
        "temporal_baseline": {
            "status": "configured",
            "label": config.temporal.baseline_label,
            "start": config.temporal.baseline_start_date,
            "end": config.temporal.baseline_end_date,
        },
        "temporal_trend": {
            "status": "ready" if trend and trend.status == "ok" else "insufficient_temporal_depth",
            "usable_years": trend.valid_observations if trend else 0,
            "minimum_years": config.temporal.min_years_for_trend,
        },
        "metric_coverage": {
            "total_metrics": len(metrics),
            "usable_metrics": len(usable),
            "referenceable_metrics": len(eligible_reference),
        },
        "reference_readiness": {
            "status": "available" if benchmark_ok else "partial_or_unavailable",
            "benchmarked_metrics": len(benchmark_ok),
            "tier1_enabled": config.reference.tier1_enabled,
            "tier1_approved_for_scoring": config.reference.tier1_approved_for_scoring,
            "tier2_enabled": config.reference.tier2_enabled,
            "tier2_approved_for_scoring": config.reference.tier2_approved_for_scoring,
        },
        "ecological_thresholds": {
            "status": "configured" if config.scoring.thresholds_by_metric else "not_configured",
            "n_threshold_sets": len(config.scoring.thresholds_by_metric),
            "reference_relative_enabled": config.scoring.reference_relative_enabled,
        },
        "composite_son": {
            "status": "ready_when_evidence_is_sufficient" if config.scoring.composite_son_enabled else "disabled_by_default",
            "reason": "P2/P3 biological evidence is not created from EO proxies alone.",
        },
        "field_validation": {
            "status": "required_for_calibration",
            "reason": "Water-quality and biodiversity proxies require independent observations for calibration/validation.",
        },
        "scoring_result": scoring,
    }
