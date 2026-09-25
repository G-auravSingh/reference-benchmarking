"""Explicit scoring utilities; no aquatic thresholds are invented by default."""
from __future__ import annotations

from typing import Any, Dict, Optional


CONCERN_LABELS = {1: "Very Low", 2: "Low", 3: "Moderate", 4: "High", 5: "Very High"}


def score_with_thresholds(value: Optional[float], thresholds: Dict[str, float], lower_is_better: bool) -> Optional[int]:
    """Map an indicator to 1-5 only when thresholds are explicitly supplied.

    thresholds must contain t1..t4 in ascending value order. For higher-is-worse
    metrics, values <= t1 -> 1 and values > t4 -> 5. For lower-is-worse metrics,
    the mapping is reversed.
    """
    if value is None:
        return None
    t1,t2,t3,t4=[float(thresholds[k]) for k in ("t1","t2","t3","t4")]
    if not (t1 < t2 < t3 < t4):
        raise ValueError("Thresholds t1<t2<t3<t4 are required")
    if lower_is_better:
        # Higher values are more concerning.
        if value >= t4: return 5
        if value >= t3: return 4
        if value >= t2: return 3
        if value >= t1: return 2
        return 1
    # Higher values are better, so lower values are more concerning.
    if value <= t1: return 5
    if value <= t2: return 4
    if value <= t3: return 3
    if value <= t4: return 2
    return 1


def summarize_composite(metric_records, thresholds_by_metric: Dict[str, Dict[str,float]]) -> Dict[str, Any]:
    scored=[]
    for m in metric_records:
        th=thresholds_by_metric.get(m.metric)
        if not th or not m.score_eligible:
            continue
        lower_is_better=(m.direction == "lower_is_better")
        s=score_with_thresholds(m.value,th,lower_is_better)
        if s is not None: scored.append(s)
    if not scored:
        return {"enabled": False, "score": None, "n_metrics": 0, "reason":"No explicitly thresholded eligible aquatic metrics."}
    mean=sum(scored)/len(scored)
    return {"enabled": True, "score_1_to_5": mean, "n_metrics": len(scored), "label": CONCERN_LABELS[int(round(mean))]}
