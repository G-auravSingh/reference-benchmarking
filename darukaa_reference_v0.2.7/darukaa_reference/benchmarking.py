"""
benchmarking.py -- v0.2.8 benchmark engine (Phase 3)
====================================================

Pure Python / numpy (no Earth Engine): every rule here is unit-testable with synthetic
fixtures whose answer is known. It turns (contract, site evidence, site value, reference
data) into ONE explicit status with a reason -- never a silent 0, null or `no_reference`.

Evaluation order (this also decides which references are worth computing):
  1. contract class (removed / pending / screening / contextual)  [after applicability]
  2. applicability: domain -> ecosystem -> required feature -> support floor
  3. site value present?
  4. reference present and non-empty?
  5. site/reference compatibility: construct, unit, temporal, spatial support, population
  6. documented minimum reference n
  7. estimator, with an explicit zero-inflation / zero-dispersion guard
  8. optional validation gate (require_validated)
  -> scored
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from darukaa_reference import estimators as _est
from darukaa_reference import indicator_contract as IC
from darukaa_reference import scoring as _scoring
from darukaa_reference.support import MATCHED_REFERENCE_SUPPORT, native_pixels_in_site

WINDOW_AREA_TOLERANCE = 0.15      # discretised disc vs site area (small sites are coarse)
TIE_FRACTION_LIMIT = 0.5          # a scale estimator is refused when >= 50 % of the reference is one value
_TIE_RTOL, _TIE_ATOL = 1e-9, 1e-12


# ----------------------------------------------------------------------------------------
# Metric descriptions and site/reference compatibility
# ----------------------------------------------------------------------------------------
@dataclass(frozen=True)
class MetricSpec:
    """What a value MEANS: used for both the site value and the reference values."""
    construct: str
    unit: str
    temporal: str
    support: str
    population: str
    window_area_m2: Optional[float] = None
    native_scale_m: Optional[float] = None


@dataclass
class ReferenceData:
    values: np.ndarray
    spec: MetricSpec
    tier: Optional[str]
    population_definition: str
    diagnostics: Dict = field(default_factory=dict)

    def finite(self) -> np.ndarray:
        v = np.asarray(self.values, dtype=float).ravel()
        return v[np.isfinite(v)]

    @property
    def reference_n(self) -> int:
        return int(self.finite().size)

    def summary(self) -> Dict:
        v = self.finite()
        if v.size == 0:
            return {"reference_n": 0}
        med = float(np.median(v))
        return {"reference_n": int(v.size), "reference_median": med,
                "reference_mad": float(np.median(np.abs(v - med))),
                "reference_p25": float(np.percentile(v, 25)), "reference_p75": float(np.percentile(v, 75)),
                "population": self.population_definition, "tier": self.tier,
                "support": self.spec.support}


def check_compatibility(site: MetricSpec, ref: MetricSpec, contract: IC.IndicatorContract,
                        site_area_m2: Optional[float] = None) -> List[str]:
    """Construct, unit, temporal, spatial-support and population compatibility (returns violations)."""
    v: List[str] = []
    if site.construct != ref.construct:
        v.append(f"construct differs: site {site.construct!r} vs reference {ref.construct!r}")
    if site.unit != ref.unit:
        v.append(f"unit differs: site {site.unit!r} vs reference {ref.unit!r}")
    if site.temporal != ref.temporal:
        v.append(f"temporal window differs: site {site.temporal!r} vs reference {ref.temporal!r}")
    expected = MATCHED_REFERENCE_SUPPORT.get(site.support)
    if ref.support != expected:
        v.append(f"spatial support differs: site {site.support!r} needs reference {expected!r}, got {ref.support!r}")
    if ref.support != contract.reference_support:
        v.append(f"reference support {ref.support!r} is not the contract's {contract.reference_support!r}")
    if ref.population != contract.reference_population:
        v.append(f"population differs: contract {contract.reference_population!r}, got {ref.population!r}")
    if site.native_scale_m and ref.native_scale_m and abs(site.native_scale_m - ref.native_scale_m) > 1e-9:
        v.append(f"native scale differs: site {site.native_scale_m} m vs reference {ref.native_scale_m} m")
    if ref.support.startswith("site_window") and site_area_m2:
        if ref.window_area_m2 is None:
            v.append("window reference does not declare its window area")
        elif abs(ref.window_area_m2 - site_area_m2) / site_area_m2 > WINDOW_AREA_TOLERANCE:
            v.append(f"window area {ref.window_area_m2:.0f} m2 differs from site area {site_area_m2:.0f} m2 "
                     f"by more than {WINDOW_AREA_TOLERANCE:.0%}")
    return v


# ----------------------------------------------------------------------------------------
# Estimators
# ----------------------------------------------------------------------------------------
def _direction_bool(direction: str) -> bool:
    if direction not in ("higher_is_better", "lower_is_better"):
        raise ValueError(f"a benchmark needs an explicit direction, got {direction!r}")
    return direction == "higher_is_better"


def percentile_benchmark(site_value: float, ref_values: Sequence[float], direction: str) -> Optional[Dict]:
    """Empirical-CDF benchmark, oriented so that a HIGHER score is always BETTER.

    score = P(reference worse than site) + 0.5 * P(reference tied with site)   (mid-rank ties)

    Ties and zero-loss reference windows are handled explicitly: the tied share and the
    fraction of exact zeros are reported, and ties get the mid-rank so a site that equals a
    tie-heavy reference sits mid-way, neither best nor worst. `score` is already in [0, 1];
    it is NOT passed through the logistic. The reference n and a distribution-free DKW 95 %
    half-width are returned so the resolution of the score is visible in the audit trail."""
    higher = _direction_bool(direction)
    r = np.asarray(ref_values, dtype=float).ravel()
    r = r[np.isfinite(r)]
    if r.size == 0 or site_value is None or not np.isfinite(site_value):
        return None
    tied = np.isclose(r, site_value, rtol=_TIE_RTOL, atol=_TIE_ATOL)
    p_tied = float(tied.mean())
    p_lt = float(((r < site_value) & ~tied).mean())
    p_gt = float(((r > site_value) & ~tied).mean())
    p_worse = p_lt if higher else p_gt
    p_better = p_gt if higher else p_lt
    score = p_worse + 0.5 * p_tied
    n = int(r.size)
    return {
        "estimator": "reference_percentile", "direction": direction,
        "benchmark": score, "score": score,
        "p_reference_worse": p_worse, "p_reference_tied": p_tied, "p_reference_better": p_better,
        "fraction_reference_zero": float(np.isclose(r, 0.0, atol=_TIE_ATOL).mean()),
        "reference_n": n,
        "score_halfwidth_dkw95": math.sqrt(math.log(2.0 / 0.05) / (2.0 * n)),
    }


def scale_estimator_guard(ref_values: Sequence[float]) -> Optional[str]:
    """Reason a location/scale estimator (robust z, log ratio) must NOT be used, or None.

    This is the explicit replacement for silently falling through to the old MAD logic on a
    zero-inflated distribution."""
    r = np.asarray(ref_values, dtype=float).ravel()
    r = r[np.isfinite(r)]
    if r.size == 0:
        return "empty_reference"
    vals, counts = np.unique(np.round(r, 12), return_counts=True)
    if counts.max() / r.size >= TIE_FRACTION_LIMIT:
        return "reference_zero_inflated_or_tie_heavy"
    med = float(np.median(r))
    if float(np.median(np.abs(r - med))) == 0.0:
        return "reference_zero_dispersion"
    return None


def benchmark_by_estimator(contract: IC.IndicatorContract, site_value: float,
                           ref_values: Sequence[float]) -> Dict:
    """Run the contract's estimator. Returns {"suppressed": reason} instead of ever guessing."""
    est = contract.estimator
    if est == "reference_percentile":
        out = percentile_benchmark(site_value, ref_values, contract.direction)
        return out if out is not None else {"suppressed": "empty_reference"}
    reason = scale_estimator_guard(ref_values)
    if reason:
        return {"suppressed": reason}
    r = np.asarray(ref_values, dtype=float).ravel(); r = r[np.isfinite(r)]
    med = float(np.median(r)); mad = float(np.median(np.abs(r - med)))
    higher = _direction_bool(contract.direction)
    if est == "robust_z":
        b = _est.robust_z(site_value, med, mad, higher)
        kind = "robust_z"
    elif est == "log_response_ratio":
        if site_value is None or site_value <= 0 or med <= 0:
            return {"suppressed": "log_ratio_undefined_for_nonpositive_values"}
        b = _est.log_response_ratio(site_value, med, higher)
        kind = "log_response_ratio"
    else:
        return {"suppressed": f"no_estimator_for_{est}"}
    if b is None:
        return {"suppressed": "estimator_undefined"}
    return {"estimator": kind, "direction": contract.direction, "benchmark": float(b),
            "score": float(_scoring.normalize(float(b), kind)), "reference_n": int(r.size),
            "reference_median": med, "reference_mad": mad}


# ----------------------------------------------------------------------------------------
# Contextual diagnostics (reported BESIDE the score, never inside it)
# ----------------------------------------------------------------------------------------
def _absolute_natural_reference(site_value: float) -> Dict:
    """Departure from an IDEAL (100 % natural) condition -- distinct from the regional benchmark."""
    return {"absolute_natural_reference": {
        "reference_condition": "100 % natural cover", "site_percent_natural": float(site_value),
        "departure_percentage_points": 100.0 - float(site_value),
        "ratio_to_reference_condition": (float(site_value) / 100.0)}}


DIAGNOSTICS = {"absolute_natural_reference": _absolute_natural_reference}


# ----------------------------------------------------------------------------------------
# Applicability
# ----------------------------------------------------------------------------------------
@dataclass
class SiteEvidence:
    domain: str                                   # tile realm: terrestrial | aquatic | mixed
    site_area_m2: float
    ecosystem_tags: frozenset = frozenset()       # e.g. {"woody"}, {"open_water"}
    forest_baseline_m2: Optional[float] = None    # >=30 % canopy baseline forest area inside the site
    water_body_valid: Optional[bool] = None       # a valid water-body geometry exists for the site
    n_pure_water_px: Optional[int] = None
    # E4: a non-project polygon used ONLY to validate a method (e.g. forest loss when no project zone has
    # >= 5 ha of baseline forest). It is labelled, and its assessments can never enter project scoring.
    validation_dataset_label: Optional[str] = None


def check_applicability(c: IC.IndicatorContract, ev: SiteEvidence) -> Tuple[Optional[str], str, List[str]]:
    """-> (not_applicable_reason | None, detail, non-blocking flags)."""
    ap, flags = c.applicability, []
    if ev.domain not in ap.domains:
        return "domain_mismatch", f"{c.name} applies to {ap.domains}; tile is {ev.domain}", flags
    if ap.ecosystem in ("woody", "open_water") and ap.ecosystem not in ev.ecosystem_tags:
        return "ecosystem_type_mismatch", f"needs a {ap.ecosystem} ecosystem", flags
    if ap.requires_feature == "water_body" and not ev.water_body_valid:
        return "target_feature_absent", "no valid water-body geometry for this site", flags
    if ap.requires_feature == "forest_baseline_5ha":
        if ev.forest_baseline_m2 is None or ev.forest_baseline_m2 < IC.FOREST_BASELINE_MIN_M2:
            have = "unknown" if ev.forest_baseline_m2 is None else f"{ev.forest_baseline_m2 / 1e4:.2f} ha"
            return "target_feature_absent", f"baseline forest {have} < 5 ha", flags
    if ap.floor_basis == "pure_water_pixels":
        if (ev.n_pure_water_px or 0) < (ap.min_pure_water_pixels or IC.MIN_PURE_WATER_PIXELS):
            return ("insufficient_pure_water",
                    f"{ev.n_pure_water_px or 0} pure-water px < {ap.min_pure_water_pixels}", flags)
    elif ap.floor_basis == "polygon_native_pixels" and c.native_resolution_m:
        need = IC.effective_min_native_pixels(c)
        have = native_pixels_in_site(ev.site_area_m2, c.native_resolution_m)
        if need and have < need:
            return ("site_below_product_resolution",
                    f"{have:.1f} native px ({c.native_resolution_m:g} m) < floor {need}", flags)
    elif ap.floor_basis == "exempt_landscape_pressure" and c.native_resolution_m:
        if native_pixels_in_site(ev.site_area_m2, c.native_resolution_m) < IC.GENERIC_MIN_NATIVE_PIXELS:
            flags.append("below_generic_floor_landscape_pressure_exempt")
    return None, "", flags


# ----------------------------------------------------------------------------------------
# The status engine
# ----------------------------------------------------------------------------------------
@dataclass
class IndicatorAssessment:
    indicator: str
    status: str
    reason: str = ""
    detail: str = ""
    site_value: Optional[float] = None
    estimator: Optional[str] = None
    direction: Optional[str] = None
    reference_tier: Optional[str] = None
    reference_population: Optional[str] = None
    reference_support: Optional[str] = None
    reference_n: Optional[int] = None
    reference_median: Optional[float] = None
    reference_mad: Optional[float] = None
    benchmark: Optional[float] = None
    score: Optional[float] = None
    benchmark_details: Dict = field(default_factory=dict)
    diagnostics: Dict = field(default_factory=dict)
    flags: List[str] = field(default_factory=list)
    other_references: Dict = field(default_factory=dict)
    validation_only: bool = False                 # E4: methodological validation dataset, never project scoring

    def __post_init__(self):
        assert self.status in IC.INDICATOR_STATUSES, self.status


_CONTRACT_CLASS_STATUS = {"contextual": "contextual_only", "screening": "screening_only",
                          "pending_methodology": "pending_methodology"}


def evaluate_indicator(contract: IC.IndicatorContract, evidence: SiteEvidence,
                       site_value: Optional[float], site_spec: Optional[MetricSpec],
                       references: Optional[Dict[str, ReferenceData]] = None,
                       require_validated: bool = False) -> IndicatorAssessment:
    references = references or {}
    ref = references.get(contract.reference_tier) if contract.reference_tier else None
    a = IndicatorAssessment(indicator=contract.name, status="not_applicable", site_value=site_value,
                            direction=contract.direction, estimator=contract.estimator,
                            reference_population=contract.reference_population,
                            reference_support=contract.reference_support,
                            reference_tier=contract.reference_tier)
    # every reference that exists stays visible, whether or not it is used for scoring
    a.other_references = {t: r.summary() for t, r in references.items()}
    if evidence.validation_dataset_label:
        a.validation_only = True
        a.flags.append(f"methodological_validation_dataset:{evidence.validation_dataset_label}")

    # 2. applicability (before the contract class: an aquatic context indicator on a dry tile is N/A)
    reason, detail, flags = check_applicability(contract, evidence)
    a.flags = list(a.flags) + list(flags)
    if contract.proposed_scoreability == "removed":
        a.status, a.reason = "not_applicable", "indicator_removed"
        return a
    if reason:
        a.status, a.reason, a.detail = "not_applicable", reason, detail
        return a
    # 1. contract class
    if contract.proposed_scoreability in _CONTRACT_CLASS_STATUS:
        a.status = _CONTRACT_CLASS_STATUS[contract.proposed_scoreability]
        a.reason = contract.scoreability_reason
        return a
    # 3. site value
    if site_value is None or not np.isfinite(site_value):
        a.status, a.reason = "applicable_but_no_site_value", "site_value_not_computed"
        return a
    # 4. reference
    if ref is None or ref.reference_n == 0:
        a.status, a.reason = "applicable_but_no_reference", f"no_{contract.reference_tier}_reference_units"
        return a
    a.reference_n = ref.reference_n
    a.reference_population = ref.population_definition
    summ = ref.summary()
    a.reference_median, a.reference_mad = summ.get("reference_median"), summ.get("reference_mad")
    # 5. compatibility
    if site_spec is None:
        a.status, a.reason = "reference_available_but_not_scoreable", "site_metric_spec_missing"
        return a
    bad = check_compatibility(site_spec, ref.spec, contract, evidence.site_area_m2)
    if bad:
        a.status, a.reason, a.detail = "reference_available_but_not_scoreable", "incompatible_site_reference", "; ".join(bad)
        return a
    # 6. documented minimum reference n
    if contract.min_reference_n and ref.reference_n < contract.min_reference_n:
        a.status, a.reason = "reference_available_but_not_scoreable", "insufficient_reference_n"
        a.detail = f"reference_n {ref.reference_n} < documented minimum {contract.min_reference_n}"
        return a
    # 7. estimator (explicit guard, never a silent fall-through)
    out = benchmark_by_estimator(contract, site_value, ref.finite())
    if "suppressed" in out:
        a.status, a.reason = "suppressed_for_stability", out["suppressed"]
        return a
    a.benchmark, a.score, a.benchmark_details = out["benchmark"], out["score"], out
    for d in contract.diagnostics:
        a.diagnostics.update(DIAGNOSTICS[d](site_value))
    # 8. validation gate
    if require_validated and not contract.validated:
        a.status, a.reason = "reference_available_but_not_scoreable", "awaiting_live_validation"
        return a
    a.status, a.reason = "scored", ""
    return a


def project_assessments(assessments: Sequence[IndicatorAssessment]) -> List[IndicatorAssessment]:
    """The assessments that may enter a project's scoring / reference populations: validation-dataset
    results (E4) are excluded here, by construction."""
    return [a for a in assessments if not a.validation_only]
