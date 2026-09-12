"""
Profile-First Hybrid Scoring (CS-4 / CS-5)
==========================================

Implements the aggregation decided in Phase 2:

    - PROFILE-FIRST: the per-component profile is the primary output. The roll-up is
      optional, secondary, and always published WITH the minimum component and a
      plain-language framing block.
    - NON-COMPENSATORY throughout:
        * within a component, across subdimensions -> LIMITING-FACTOR rule (the
          component is reported at its weakest subdimension; full profile shown).
        * across components -> penalised GEOMETRIC MEAN + published MINIMUM (a strong
          component cannot mask a weak one; the minimum makes masking impossible to hide).
    - STATE vs PRESSURE kept separate: condition (C1-C3) and pressure (C4) are scored
      on separate axes and combined only into a condition x pressure MATRIX cell,
      never a single blended number (Phase 2 §7).
    - The signed, uncapped benchmark (estimators.py) is the input; a declared,
      reversible logistic maps it to a 0-1 aggregation score for the roll-up only.
      The raw signed value + CI is always what the profile shows.

Nothing here assigns universal concern-class bands (those were retired, C-G2). Where a
published per-indicator threshold exists it can be attached later; absent one, we report
the score + uncertainty with no categorical class.

Pure functions (numpy/math only); unit-tested.
"""
from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional, Sequence

import numpy as np

logger = logging.getLogger(__name__)

# Declared logistic slopes for mapping signed benchmarks -> [0,1] (aggregation only).
# 0.5 = at reference; >0.5 better than reference; <0.5 worse. These are PRODUCT
# choices [X], declared and reversible — not ecological truths.
K_LRR = 1.0     # LRR = ln(2) (a doubling) -> ~0.67
K_Z = 0.5       # robust_z = 2 -> ~0.73

FRAMING_BLOCK = (
    "What this score is: a transparent summary of ecological components, combined with "
    "weights chosen in advance and published; a decision aid for prioritising attention "
    "and spend. What it is not: a measurement of biodiversity, a probability of success, "
    "or a value comparable to another organisation's score or across our own projects "
    "unless the module set and reference basis match. A change in this number is not by "
    "itself evidence of ecological change — read the component profile and its "
    "uncertainty. How to use it: read the minimum component first, the profile second, "
    "the roll-up last and only for triage."
)


def _band(score: Optional[float]) -> Optional[str]:
    """Coarse 3-band label for stability testing (declared cut points [X])."""
    if score is None:
        return None
    if score >= 0.6:
        return "good"
    if score >= 0.4:
        return "moderate"
    return "poor"


def sensitivity_report(component_headlines: Dict[str, Optional[float]]) -> Dict:
    """Recompute the condition roll-up under alternative weightings and report whether
    the result is STABLE (CS-5 condition 4).

    Scenarios: equal weights + each component up-weighted 3x in turn. If the roll-up's
    coarse band flips across scenarios, the roll-up is flagged UNSTABLE and should be
    published as such (or withheld), with the profile shown regardless.
    """
    comps = [k for k, v in component_headlines.items() if v is not None]
    if len(comps) < 2:
        return {"stable": True, "rollup_min": None, "rollup_max": None,
                "bands": [], "note": "too few components to test"}

    rollups = []
    scenarios = [None] + [{c: 3.0} for c in comps]  # equal, then each tilted
    for w in scenarios:
        r = condition_rollup(component_headlines, weights=w)
        if r["rollup"] is not None:
            rollups.append(r["rollup"])

    bands = sorted(set(_band(r) for r in rollups))
    stable = len(bands) <= 1
    return {
        "stable": stable,
        "rollup_min": min(rollups) if rollups else None,
        "rollup_max": max(rollups) if rollups else None,
        "bands": bands,
        "note": ("roll-up band is robust to weighting" if stable
                 else "roll-up band FLIPS under alternative weights — publish as unstable "
                      "or withhold; read the component profile instead"),
    }


def normalize(value: Optional[float], estimator: str) -> Optional[float]:
    """Map a signed, uncapped benchmark to a 0-1 aggregation score (0.5 = reference).

    Declared logistic; reversible; for roll-up aggregation and banding only. The
    profile always also carries the raw signed value + CI.
    """
    if value is None:
        return None
    k = K_LRR if estimator == "log_response_ratio" else K_Z
    return 1.0 / (1.0 + math.exp(-k * value))


def geometric_mean(scores: Sequence[float]) -> Optional[float]:
    """Penalised geometric mean of 0-1 scores (a low score drags the whole)."""
    vals = [s for s in scores if s is not None]
    if not vals:
        return None
    # clip away exact zeros to keep the log finite; 0 -> very low but defined
    vals = [min(max(v, 1e-6), 1.0) for v in vals]
    return float(np.exp(np.mean(np.log(vals))))


def component_score(subdimension_scores: Dict[str, Optional[float]]) -> Dict:
    """Aggregate subdimensions into a component via the LIMITING-FACTOR rule.

    Returns the component headline (the MINIMUM subdimension = binding constraint),
    the mean (context only), the limiting subdimension name, and the full profile.
    """
    valid = {k: v for k, v in subdimension_scores.items() if v is not None}
    if not valid:
        return {"headline": None, "limiting_subdimension": None, "mean": None,
                "profile": dict(subdimension_scores)}
    limiting = min(valid, key=valid.get)
    return {
        "headline": valid[limiting],            # limiting factor (non-compensatory)
        "limiting_subdimension": limiting,
        "mean": float(np.mean(list(valid.values()))),  # context only, never the headline
        "profile": dict(subdimension_scores),
    }


def condition_rollup(component_headlines: Dict[str, Optional[float]],
                     weights: Optional[Dict[str, float]] = None) -> Dict:
    """Combine component headlines into the optional CONDITION roll-up.

    Non-compensatory: penalised geometric mean, published alongside the MINIMUM
    component. If weights are given they are applied in log-space (declared,
    pre-registered). Includes a stability flag placeholder (sensitivity analysis
    result is attached by the caller).
    """
    vals = {k: v for k, v in component_headlines.items() if v is not None}
    if not vals:
        return {"rollup": None, "minimum": None, "minimum_component": None,
                "profile": dict(component_headlines), "framing": FRAMING_BLOCK}
    if weights:
        # weighted geometric mean
        clipped = {k: min(max(v, 1e-6), 1.0) for k, v in vals.items()}
        wsum = sum(weights.get(k, 1.0) for k in clipped)
        logmean = sum(weights.get(k, 1.0) * math.log(v) for k, v in clipped.items()) / wsum
        rollup = float(math.exp(logmean))
    else:
        rollup = geometric_mean(list(vals.values()))
    min_comp = min(vals, key=vals.get)
    return {
        "rollup": rollup,                 # secondary, triage only
        "minimum": vals[min_comp],        # published ALWAYS with the roll-up
        "minimum_component": min_comp,
        "profile": dict(component_headlines),   # PRIMARY output
        "weights": weights or "equal_default",
        "framing": FRAMING_BLOCK,
    }


# Condition x Pressure matrix (Phase 2 §7). Thresholds are display bands [X], declared.
def matrix_cell(condition_score: Optional[float], pressure_score: Optional[float],
                good: float = 0.5, low_pressure: float = 0.5) -> str:
    """Return the management quadrant. condition/pressure are 0-1 (higher=better;
    for pressure, higher score = LOWER pressure since benchmarks are direction-oriented).
    """
    if condition_score is None or pressure_score is None:
        return "insufficient_data"
    good_cond = condition_score >= good
    low_press = pressure_score >= low_pressure
    if good_cond and low_press:
        return "protect_maintain"
    if good_cond and not low_press:
        return "defend_abate_threat"
    if not good_cond and low_press:
        return "restore"
    return "stabilise_then_restore"


def build_site_profile(benchmarks: List[Dict],
                       weights: Optional[Dict[str, float]] = None,
                       seed_kernel: bool = False,
                       seed_delta: float = 0.5) -> Dict:
    """Assemble the full profile-first output for one site from scored-indicator
    benchmarks.

    Each item in ``benchmarks`` is a dict:
        {name, construct, subdimension, value(signed), estimator, ci(optional)}
    Only CONDITION constructs (C1/C2/C3) feed the condition roll-up; C4_pressure feeds
    the pressure axis; the two are combined into the matrix cell, never averaged.

    If ``seed_kernel`` is True (OD-4), a whole-construct SEED similarity-to-reference
    (exp kernel over |signed benchmark|) is attached per construct as an optional view,
    alongside — never replacing — the direction-aware component score.
    """
    # group normalized scores by construct -> subdimension
    cond_constructs = ("C1_landscape", "C2_vegetation", "C3_fauna")
    by_comp: Dict[str, Dict[str, list]] = {}
    press_scores: Dict[str, list] = {}
    raw_by_comp: Dict[str, list] = {}   # signed benchmarks for the SEED kernel

    for b in benchmarks:
        s = normalize(b.get("value"), b.get("estimator", ""))
        if s is None:
            continue
        if b["construct"] == "C4_pressure":
            press_scores.setdefault(b.get("subdimension", "pressure"), []).append(s)
        elif b["construct"] in cond_constructs:
            by_comp.setdefault(b["construct"], {}).setdefault(
                b.get("subdimension", "_"), []).append(s)
            raw_by_comp.setdefault(b["construct"], []).append(b.get("value"))
        else:
            # REAL BUG FIXED HERE (Aug 2026, found by an automated
            # unused-variable check — cond_constructs was declared but
            # never actually used to validate anything): a bare `else`
            # here silently treated ANY construct label that wasn't
            # literally "C4_pressure" as a valid condition construct, with
            # no check against the three declared condition constructs at
            # all. A typo'd or unexpected construct label from upstream
            # data would have been silently folded into the condition
            # rollup as if it were real. Now explicitly validated and
            # skipped with a real warning instead.
            logger.warning(
                f"Benchmark with unrecognised construct {b['construct']!r} "
                f"(expected one of {cond_constructs} or 'C4_pressure') — skipped, "
                "not silently folded into the condition rollup.")

    # component scores (limiting-factor across subdimensions; average within subdim)
    comp_out = {}
    comp_headlines = {}
    for comp, subs in by_comp.items():
        subdim_scores = {k: float(np.mean(v)) for k, v in subs.items()}
        cs = component_score(subdim_scores)
        if seed_kernel:
            try:
                from darukaa_reference import estimators as _est
                cs["seed_similarity"] = _est.construct_seed_similarity(
                    raw_by_comp.get(comp, []), delta=seed_delta)
            except Exception:
                cs["seed_similarity"] = None
        comp_out[comp] = cs
        comp_headlines[comp] = cs["headline"]

    condition = condition_rollup(comp_headlines, weights)
    condition["sensitivity"] = sensitivity_report(comp_headlines)

    # pressure axis (limiting-factor across pressure subdimensions)
    press_subdim = {k: float(np.mean(v)) for k, v in press_scores.items()}
    pressure = component_score(press_subdim) if press_subdim else {"headline": None, "profile": {}}

    cell = matrix_cell(condition.get("rollup"), pressure.get("headline"))

    return {
        "components": comp_out,          # PRIMARY: per-component profiles
        "condition": condition,          # optional roll-up + minimum + framing
        "pressure": pressure,            # separate pressure axis
        "matrix_cell": cell,             # condition x pressure decision quadrant
    }
