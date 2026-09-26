"""Assessment readiness and evidence-sufficiency diagnostics."""
from __future__ import annotations

from typing import Any, Dict, Iterable


def assess_readiness(config, boundary_area_ha: float, metrics: Iterable, benchmarks=None, scoring=None, observations=None, reference_diagnostics=None) -> Dict[str, Any]:
    metrics = list(metrics); benchmarks = list(benchmarks or []); observations = list(observations or [])
    usable = [m for m in metrics if m.status in {"ok", "usable"} and m.value is not None]
    approved = [b for b in benchmarks if b.reference_approved_for_scoring]
    scored = int(scoring.get("n_valid_pillars", 0)) if isinstance(scoring, dict) else 0
    return {
        "overall_status": "ready_for_baseline_reporting" if boundary_area_ha > 0 else "invalid_geometry",
        "geometry": {"status": "ready" if boundary_area_ha > 0 else "invalid", "boundary_area_ha": round(boundary_area_ha, 4), "boundary_type": config.site_boundary_type},
        "baseline": {"start": config.temporal.baseline_start_date, "end": config.temporal.baseline_end_date, "label": config.temporal.baseline_label, "historical_context": f"{config.temporal.start_year}-{config.temporal.end_year}"},
        "metrics": {"total": len(metrics), "usable": len(usable), "scored": sum(getattr(m, "score_eligible", False) for m in metrics)},
        "references": {"automatic_reference_strategy": config.reference.strategy, "approved_benchmarks": len(approved), "minimum_reference_n": config.reference.minimum_reference_n, "maximum_relative_se": config.reference.maximum_reference_relative_se, "diagnostics": reference_diagnostics or {}},
        "evidence": {"external_records": len(observations), "field": sum(r.source_type == "field" for r in observations), "acoustic": sum(r.source_type == "acoustic" for r in observations), "edna": sum(r.source_type == "edna" for r in observations)},
        "score_coverage": {"valid_pillars": scored, "required_for_four_pillar_son": config.scoring.total_pillars, "overall_son_available": bool(isinstance(scoring, dict) and scoring.get("overall_son_score_0_to_100") is not None)},
        "interpretation": "Cycle-1 outputs distinguish measured indicators, reference-benchmarked indicators, contextual trends and pending external evidence. No score is produced without an approved comparable reference and valid metric data.",
    }
