"""Biodiversity-assessment readiness checks."""
from __future__ import annotations

from typing import Any, Dict


def assess_readiness(config, boundary_area_ha: float, metrics):
    years=[m.valid_observations for m in metrics if m.metric == "riparian_ndvi_sen_slope"]
    trend_years=years[0] if years else 0
    return {
        "geometry": {"status":"ready", "boundary_area_ha": round(boundary_area_ha,4), "boundary_type": config.site_boundary_type},
        "dynamic_water": {"status":"configured", "method":config.water.primary_dataset, "threshold":config.water.primary_probability_threshold},
        "temporal_trend": {"status":"ready" if trend_years >= config.temporal.min_years_for_trend else "insufficient_temporal_depth", "usable_years":trend_years, "minimum_years":config.temporal.min_years_for_trend},
        "ecological_thresholds": {"status":"not_configured", "reason":"No generic aquatic thresholds are silently imposed for proxy metrics."},
        "composite_son": {"status":"disabled_by_default" if not config.profile.composite_son_enabled else "enabled"},
        "field_validation": {"status":"required_for_validation", "reason":"Water-quality and biodiversity proxies require field observations for calibration/validation."},
    }
