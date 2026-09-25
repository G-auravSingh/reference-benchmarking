"""Benchmark helpers. Aquatic metrics are not forced into arbitrary reference ratios."""
from __future__ import annotations

from typing import Optional


def intactness_ratio(observed: float, reference: float, higher_is_better: bool) -> Optional[float]:
    if observed is None or reference is None or reference == 0:
        return None
    r = observed / reference if higher_is_better else reference / observed if observed != 0 else None
    return None if r is None else max(0.0, min(1.0, float(r)))


def baseline_delta(current: Optional[float], baseline: Optional[float]):
    if current is None or baseline is None:
        return None
    return float(current - baseline)


def percent_change(current: Optional[float], baseline: Optional[float]):
    if current is None or baseline in (None, 0):
        return None
    return float((current - baseline) / baseline * 100.0)
