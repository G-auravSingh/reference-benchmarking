"""Reference-condition contracts, diagnostics and metric-relative comparison.

This module contains the *scientific contract* that sits between spatial candidate
construction and ecological scoring.  It deliberately separates four things that
must not be conflated:

1. reference-state definition (what kind of state is sought);
2. candidate population construction (where comparable pixels/patches are found);
3. reference QA/approval (whether the candidate is defensible for scoring); and
4. metric-relative departure (how an observation compares with the approved reference).

The spatial candidate builders live in :mod:`reference_engine`; the pure functions in
this module are unit-testable without Earth Engine and should remain stable even when
individual EO datasets or metric formulas are upgraded.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, Optional
import math

import numpy as np


REFERENCE_STATES = {
    "undisturbed_minimally_disturbed",
    "least_disturbed_contemporary",
    "historical",
    "best_attainable",
    "paired_control",
    "published_target",
}


@dataclass(frozen=True)
class ReferenceQA:
    """Auditable structural QA for a reference population."""

    population_ok: bool
    ecological_match_ok: bool
    pressure_screen_ok: bool
    temporal_match_ok: bool
    spatial_quality_ok: bool
    diagnostics: Dict[str, Any]
    approval_recommendation: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _finite(values: Iterable[float]) -> np.ndarray:
    x = np.asarray(list(values), dtype=float).ravel()
    return x[np.isfinite(x)]


def reference_distribution(values: Iterable[float], bootstrap_n: int = 1000,
                           seed: int = 12345) -> Dict[str, Any]:
    """Return a reproducible reference distribution summary.

    The reference is a population/distribution, not just a single benchmark value.
    The median remains the default central estimator because it is robust to skew and
    outliers. Bootstrap intervals describe uncertainty in the *sample median*; they
    are not confidence intervals for independent pixels because spatial
    autocorrelation reduces effective sample size.
    """
    x = _finite(values)
    if x.size == 0:
        return {"n": 0, "median": None, "p10": None, "p25": None,
                "p75": None, "p90": None, "mad": None,
                "bootstrap_ci_low": None, "bootstrap_ci_high": None,
                "bootstrap_se": None}
    med = float(np.median(x))
    mad = float(np.median(np.abs(x - med)))
    out = {
        "n": int(x.size),
        "mean": float(np.mean(x)),
        "median": med,
        "std": float(np.std(x, ddof=1)) if x.size > 1 else 0.0,
        "mad": mad,
        "p10": float(np.percentile(x, 10)),
        "p25": float(np.percentile(x, 25)),
        "p75": float(np.percentile(x, 75)),
        "p90": float(np.percentile(x, 90)),
    }
    if x.size >= 2 and bootstrap_n > 0:
        rng = np.random.default_rng(seed)
        medians = np.median(rng.choice(x, size=(int(bootstrap_n), x.size), replace=True), axis=1)
        out.update({
            "bootstrap_ci_low": float(np.percentile(medians, 2.5)),
            "bootstrap_ci_high": float(np.percentile(medians, 97.5)),
            "bootstrap_se": float(np.std(medians, ddof=1)),
        })
    else:
        out.update({"bootstrap_ci_low": None, "bootstrap_ci_high": None, "bootstrap_se": None})
    return out


def evaluate_reference_candidate(*, candidate_area_ha: Optional[float], candidate_pixels: Optional[int],
                                 min_area_ha: float, min_pixels: int,
                                 ecological_match_score: float = 1.0,
                                 min_ecological_match_score: float = 0.8,
                                 pressure_screen_pass: bool = True,
                                 temporal_match_pass: bool = True,
                                 spatial_quality_pass: bool = True,
                                 reference_state: str = "least_disturbed_contemporary",
                                 auto_approve: bool = True,
                                 extra: Optional[Dict[str, Any]] = None) -> ReferenceQA:
    """Apply the structural reference-approval gate.

    ``auto_approve`` is only a permission to approve *after* QA. It is never an
    unconditional switch. This prevents a configuration flag from turning an
    arbitrary spatial candidate into a benchmark.
    """
    if reference_state not in REFERENCE_STATES:
        raise ValueError(f"Unknown reference state: {reference_state}")
    area_ok = candidate_area_ha is not None and float(candidate_area_ha) >= float(min_area_ha)
    pixels_ok = candidate_pixels is not None and int(candidate_pixels) >= int(min_pixels)
    eco_ok = float(ecological_match_score) >= float(min_ecological_match_score)
    population_ok = bool(area_ok and pixels_ok)
    diagnostics = {
        "candidate_area_ha": candidate_area_ha,
        "candidate_pixels": candidate_pixels,
        "minimum_area_ha": min_area_ha,
        "minimum_pixels": min_pixels,
        "ecological_match_score": ecological_match_score,
        "minimum_ecological_match_score": min_ecological_match_score,
        "population_ok": population_ok,
        "area_ok": area_ok,
        "pixels_ok": pixels_ok,
        "ecological_match_ok": eco_ok,
        "pressure_screen_ok": bool(pressure_screen_pass),
        "temporal_match_ok": bool(temporal_match_pass),
        "spatial_quality_ok": bool(spatial_quality_pass),
        "reference_state": reference_state,
    }
    if extra:
        diagnostics.update(extra)
    approval = bool(auto_approve and population_ok and eco_ok and pressure_screen_pass
                    and temporal_match_pass and spatial_quality_pass)
    return ReferenceQA(population_ok, eco_ok, bool(pressure_screen_pass),
                       bool(temporal_match_pass), bool(spatial_quality_pass),
                       diagnostics, approval)


def relative_departure(observed: Optional[float], reference: Optional[float], direction: str) -> Optional[float]:
    """Signed departure from the reference median, expressed as a proportion.

    Positive means directionally better than the reference; negative means worse.
    This is descriptive and is *not* itself an ecological condition score.
    """
    if observed is None or reference is None or not math.isfinite(float(observed)) or not math.isfinite(float(reference)):
        return None
    o, r = float(observed), float(reference)
    if r == 0:
        return None
    if direction == "higher_is_better":
        return (o - r) / abs(r)
    if direction == "lower_is_better":
        if o == 0:
            return None
        return (r - o) / abs(r)
    if direction == "reference_target":
        return -abs(o - r) / abs(r)
    raise ValueError(f"Unknown direction: {direction}")


def reference_percentile(observed: Optional[float], reference_values: Optional[Iterable[float]]) -> Optional[float]:
    """Percentile rank of an observation within the reference population (0–100)."""
    if observed is None or reference_values is None:
        return None
    x = _finite(reference_values)
    if x.size == 0 or not math.isfinite(float(observed)):
        return None
    o = float(observed)
    # Mid-rank handles ties without falsely implying a finer resolution than exists.
    return float(100.0 * ((x < o).sum() + 0.5 * (x == o).sum()) / x.size)


def reference_attainment(observed: Optional[float], reference: Optional[float], direction: str) -> Optional[float]:
    """Legacy-compatible 0–100 reference-attainment display value.

    IMPORTANT: this is *not* labelled ecological intactness. It is capped at the
    reference level because exceeding a reference does not establish a biologically
    perfect condition. Metric-specific response functions can replace this later
    without changing the reference-population contract.
    """
    if observed is None or reference is None:
        return None
    o, r = float(observed), float(reference)
    if direction == "higher_is_better":
        if r <= 0:
            return None
        return max(0.0, min(100.0, 100.0 * o / r))
    if direction == "lower_is_better":
        if o <= 0:
            return 100.0
        return max(0.0, min(100.0, 100.0 * r / o))
    if direction == "reference_target":
        if r == 0:
            return 100.0 if o == 0 else 0.0
        return max(0.0, min(100.0, 100.0 * (1.0 - abs(o - r) / abs(r))))
    return None
