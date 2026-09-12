"""
Cycle-2+ Change Scoring (monitoring mode)
=========================================

In cycle 1 (baseline), in-situ metrics are reported as observed values + uncertainty +
within-project rank — never concern classes (self-referential thresholds are not a
baseline; see OPEN_DECISIONS). From cycle 2 onward, the defensible thing a restoration
baseline exists to measure becomes available: CHANGE against the site's own Year-0.

This module scores change:
  - delta vs the site's own baseline (per indicator), with propagated uncertainty and a
    detection test (does the change exceed measurement noise?);
  - the BACI contrast where a matched control exists (change at impact BEYOND the change
    the control showed) — the strongest attribution available.

Pure functions (numpy/stdlib); unit-tested. Consumes the site's stored Year-0 artifact
(value + CI per indicator) and the current cycle's values.
"""
from __future__ import annotations

import math
from typing import Dict, Optional, Tuple


def _halfwidth(ci: Optional[Tuple[float, float]]) -> Optional[float]:
    if ci is None:
        return None
    lo, hi = ci
    if lo is None or hi is None:
        return None
    return abs(hi - lo) / 2.0


def change_score(baseline_value: Optional[float],
                 current_value: Optional[float],
                 baseline_ci: Optional[Tuple[float, float]] = None,
                 current_ci: Optional[Tuple[float, float]] = None,
                 higher_is_better: bool = True,
                 k_detect: float = 1.0) -> Dict:
    """Change of a metric vs its own baseline, oriented so delta_oriented > 0 = improvement.

    Detection: the change is 'detected' when |delta| exceeds the combined uncertainty
    (quadrature sum of baseline & current CI half-widths) times k_detect. Absent CIs,
    detection is reported as None (unknown), not asserted.
    """
    if baseline_value is None or current_value is None:
        return {"delta": None, "delta_oriented": None, "detected": None,
                "note": "missing baseline or current value"}
    delta = current_value - baseline_value
    delta_oriented = delta if higher_is_better else -delta

    hb = _halfwidth(baseline_ci); hc = _halfwidth(current_ci)
    combined = None
    if hb is not None or hc is not None:
        combined = math.sqrt((hb or 0.0) ** 2 + (hc or 0.0) ** 2)
    detected = None
    if combined is not None:
        detected = abs(delta) > k_detect * combined

    direction = ("improved" if delta_oriented > 0 else
                 "declined" if delta_oriented < 0 else "no change")
    note = f"{direction}"
    if detected is False:
        note += " (within measurement uncertainty — not a detected change)"
    elif detected is True:
        note += " (exceeds measurement uncertainty)"
    return {
        "baseline_value": baseline_value, "current_value": current_value,
        "delta": delta, "delta_oriented": delta_oriented,
        "combined_uncertainty": combined, "detected": detected, "note": note,
    }


def baci_contrast(impact_baseline: float, impact_current: float,
                  control_baseline: float, control_current: float,
                  higher_is_better: bool = True) -> Dict:
    """BACI effect = (impact change) - (control change), oriented so > 0 = the
    intervention improved the impact site beyond the control's trajectory.

    This isolates the intervention effect from background/landscape change that both
    sites experienced.
    """
    impact_delta = impact_current - impact_baseline
    control_delta = control_current - control_baseline
    effect = impact_delta - control_delta
    effect_oriented = effect if higher_is_better else -effect
    return {
        "impact_delta": impact_delta,
        "control_delta": control_delta,
        "baci_effect": effect,
        "baci_effect_oriented": effect_oriented,
        "note": ("intervention outperformed control" if effect_oriented > 0 else
                 "intervention underperformed control" if effect_oriented < 0 else
                 "no differential effect"),
    }


def score_cycle(baseline: Dict[str, Dict],
                current: Dict[str, Dict],
                directions: Optional[Dict[str, bool]] = None,
                controls: Optional[Dict[str, Dict]] = None) -> Dict:
    """Score a monitoring cycle against the stored baseline.

    baseline/current : {indicator: {"value": v, "ci": (lo, hi)}}
    directions       : {indicator: higher_is_better}; default True.
    controls         : optional {indicator: {"baseline": v, "current": v}} for BACI.

    Returns per-indicator change (+ BACI where available) and a summary.
    """
    directions = directions or {}
    controls = controls or {}
    out: Dict[str, Dict] = {}
    n_improved = n_declined = n_detected = 0

    for ind, cur in current.items():
        base = baseline.get(ind)
        if base is None:
            out[ind] = {"note": "no baseline for this indicator (new metric)"}
            continue
        hib = directions.get(ind, True)
        cs = change_score(base.get("value"), cur.get("value"),
                          base.get("ci"), cur.get("ci"), higher_is_better=hib)
        if ind in controls and controls[ind].get("baseline") is not None:
            c = controls[ind]
            cs["baci"] = baci_contrast(base.get("value"), cur.get("value"),
                                       c["baseline"], c["current"], higher_is_better=hib)
        out[ind] = cs
        if cs.get("delta_oriented") is not None:
            if cs["delta_oriented"] > 0: n_improved += 1
            elif cs["delta_oriented"] < 0: n_declined += 1
        if cs.get("detected") is True:
            n_detected += 1

    return {
        "per_indicator": out,
        "summary": {"n_indicators": len(current), "n_improved": n_improved,
                    "n_declined": n_declined, "n_detected_changes": n_detected},
    }


def from_report(report: Dict) -> Dict[str, Dict]:
    """Extract {indicator: {"value", "ci"}} from a darukaa_reference report dict, so two
    cycles' reports can be diffed directly by score_cycle(). Uses the signed benchmark
    if present, else the site value; CI from the bootstrap CI when available."""
    out: Dict[str, Dict] = {}
    for r in report.get("scorecard", []):
        val = r.get("tier2_benchmark")
        if val is None:
            val = r.get("site_value")
        ci = r.get("intactness_bootstrap_ci")
        out[r.get("indicator")] = {"value": val, "ci": tuple(ci) if isinstance(ci, (list, tuple)) else None}
    return out
