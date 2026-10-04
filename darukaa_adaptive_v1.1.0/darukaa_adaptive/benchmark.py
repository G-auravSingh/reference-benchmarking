"""Reference comparison, automatic reference populations and uncertainty-aware benchmarking."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Iterable, Optional
import math
import pandas as pd

from .registry import get_indicator_spec
from .site import ee_geometry, make_shapely_domains
from .reference_engine import AutomaticReferenceEngine, ReferencePopulation
from .reference_condition import relative_departure, reference_attainment


@dataclass
class BenchmarkResult:
    metric: str
    observed_value: Optional[float]
    tier1_value: Optional[float]
    tier2_value: Optional[float]
    selected_reference: Optional[float]
    selected_reference_level: str
    raw_relative_ratio: Optional[float]
    intactness_ratio: Optional[float]
    intactness_score_0_100: Optional[float]
    comparison_method: str
    benchmark_status: str
    reference_approved_for_scoring: bool = False
    reference_n: Optional[int] = None
    reference_ci_low: Optional[float] = None
    reference_ci_high: Optional[float] = None
    reference_uncertainty: Optional[float] = None
    reference_method: str = ""
    notes: str = ""
    # R4 reference-condition fields. These are additive so older downstream
    # consumers can continue reading the legacy intactness fields.
    reference_state: str = ""
    reference_approval_basis: str = ""
    reference_diagnostics: Optional[Dict] = None
    relative_departure_pct: Optional[float] = None
    reference_attainment_0_100: Optional[float] = None
    interpretation_status: str = ""
    standardized_z: Optional[float] = None
    robust_z: Optional[float] = None

    def to_dict(self):
        return asdict(self)


def _cap01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def reference_relative_intactness(observed, reference, direction):
    if observed is None or reference is None:
        return None
    observed, reference = float(observed), float(reference)
    if direction == "higher_is_better":
        return None if reference == 0 else _cap01(observed / reference)
    if direction == "lower_is_better":
        if observed == 0:
            return 1.0 if reference >= 0 else None
        return _cap01(reference / observed)
    if direction == "reference_target":
        if reference == 0:
            return 1.0 if observed == 0 else 0.0
        return _cap01(1.0 - abs(observed - reference) / abs(reference))
    return None


def intactness_ratio(observed, reference, higher_is_better):
    return reference_relative_intactness(observed, reference, "higher_is_better" if higher_is_better else "lower_is_better")


def raw_relative_ratio(observed, reference, direction):
    if observed is None or reference is None:
        return None
    observed, reference = float(observed), float(reference)
    if reference == 0:
        return None
    if direction == "higher_is_better":
        return observed / reference
    if direction == "lower_is_better":
        return None if observed == 0 else reference / observed
    return observed / reference


def baseline_delta(current, baseline):
    return None if current is None or baseline is None else float(current - baseline)


def percent_change(current, baseline):
    return None if current is None or baseline in (None, 0) else float((current - baseline) / baseline * 100.0)



def _bootstrap_ci(values, n_boot=200):
    vals = pd.Series(values).dropna().astype(float).to_numpy()
    if len(vals) < 2:
        return None, None, None
    import numpy as np
    rng = np.random.default_rng(12345)
    medians = np.median(rng.choice(vals, size=(n_boot, len(vals)), replace=True), axis=1)
    low, high = np.percentile(medians, [2.5, 97.5])
    return float(low), float(high), float(np.std(medians, ddof=1))


def _reference_central_value(metric_record):
    """Use the spatial median as the default reference central estimator when available."""
    if metric_record is None:
        return None
    p50 = getattr(metric_record, "p50", None)
    return p50 if p50 is not None else getattr(metric_record, "value", None)


def _reference_distribution_diagnostics(metric_record):
    if metric_record is None:
        return {}
    keys = ("valid_pixels", "value", "std_dev", "p05", "p10", "p25", "p50", "p75", "p90", "p95")
    return {k: getattr(metric_record, k, None) for k in keys}


def benchmark_metric(metric_name, observed, tier1, tier2, allow_tier2=True, tier1_approved=False, tier2_approved=False,
                     reference_level=None, reference_n=None, reference_ci=None, reference_uncertainty=None,
                     reference_method="", reference_state="", reference_approval_basis="",
                     reference_diagnostics=None):
    spec = get_indicator_spec(metric_name)
    if not spec.reference_allowed:
        return BenchmarkResult(metric_name, observed, tier1, tier2, None, "none", None, None, None,
                               "not_referenceable", "not_referenceable", notes="Contextual/screening indicator; not automatically scored.",
                               reference_state=reference_state, reference_approval_basis=reference_approval_basis,
                               reference_diagnostics=reference_diagnostics, interpretation_status="screening_or_contextual")
    selected, level, approved = None, "none", False
    if tier1 is not None:
        selected, level, approved = float(tier1), "tier1", bool(tier1_approved)
    elif allow_tier2 and tier2 is not None:
        selected, level, approved = float(tier2), "tier2", bool(tier2_approved)
    if selected is None:
        return BenchmarkResult(metric_name, observed, tier1, tier2, None, "none", None, None, None,
                               "reference_unavailable", "reference_unavailable", notes="No comparable reference population/value was available.",
                               reference_state=reference_state, reference_approval_basis=reference_approval_basis,
                               reference_diagnostics=reference_diagnostics, interpretation_status="reference_unavailable")
    raw = raw_relative_ratio(observed, selected, spec.direction)
    intact = reference_relative_intactness(observed, selected, spec.direction)
    dep = relative_departure(observed, selected, spec.direction)
    attainment = reference_attainment(observed, selected, spec.direction)
    ci_low = ci_high = None
    if reference_ci:
        ci_low, ci_high = reference_ci
    interpretation = "at_or_above_reference" if (dep is not None and dep >= 0) else "below_reference"
    diagnostics = dict(reference_diagnostics or {})
    ref_sd = diagnostics.get("std_dev")
    ref_med = diagnostics.get("p50")
    ref_mad = None
    if diagnostics.get("p25") is not None and diagnostics.get("p75") is not None:
        # Approximate robust scale from IQR; retained as a diagnostic, not a score.
        ref_mad = (float(diagnostics["p75"]) - float(diagnostics["p25"])) / 1.349
    standardized_z = None
    robust_z = None
    if observed is not None and ref_sd not in (None, 0):
        standardized_z = (float(observed) - float(selected)) / float(ref_sd)
    if observed is not None and ref_mad not in (None, 0) and ref_med is not None:
        robust_z = (float(observed) - float(ref_med)) / float(ref_mad)
    if spec.direction == "reference_target" and dep is not None:
        interpretation = "near_reference_target" if dep == 0 else "departed_from_reference_target"
    return BenchmarkResult(metric_name, observed, tier1, tier2, selected, reference_level or level, raw,
                           intact, attainment,
                           "reference_relative_ratio" if spec.direction != "reference_target" else "distance_from_reference",
                           "ok", approved, reference_n, ci_low, ci_high, reference_uncertainty,
                           reference_method or "reference_population",
                           notes="Reference-relative comparison. The legacy intactness field is retained for compatibility; production interpretation uses reference attainment and the explicit reference state.",
                           reference_state=reference_state, reference_approval_basis=reference_approval_basis,
                           reference_diagnostics=reference_diagnostics, relative_departure_pct=None if dep is None else dep*100.0,
                           reference_attainment_0_100=attainment, interpretation_status=interpretation, standardized_z=standardized_z, robust_z=robust_z)

def benchmark_observation(metric_name, observed, reference, direction, reference_level="external", reference_approved=True):
    if reference is None:
        return BenchmarkResult(metric_name, observed, None, None, None, "none", None, None, None,
                               "reference_unavailable", "reference_unavailable",
                               reference_approved_for_scoring=False, reference_state="external",
                               reference_approval_basis="not_available", interpretation_status="reference_unavailable")
    raw = raw_relative_ratio(observed, reference, direction)
    intact = reference_relative_intactness(observed, reference, direction)
    dep = relative_departure(observed, reference, direction)
    interpretation = "at_or_above_reference" if dep is not None and dep >= 0 else "below_reference"
    if direction == "reference_target" and dep is not None:
        interpretation = "near_reference_target" if dep == 0 else "departed_from_reference_target"
    return BenchmarkResult(metric_name, observed, None, None, float(reference), reference_level, raw, intact,
                           None if intact is None else intact * 100,
                           "reference_relative_ratio" if direction != "reference_target" else "distance_from_reference",
                           "ok", bool(reference_approved), notes="External evidence uses the same scoring pathway.",
                           reference_state="external", reference_approval_basis="explicit_external_reference" if reference_approved else "not_approved",
                           relative_departure_pct=None if dep is None else dep * 100.0,
                           reference_attainment_0_100=None if intact is None else intact * 100.0,
                           interpretation_status=interpretation)


class ReferenceEngine:
    """Finite automatic reference engine: strict → least-disturbed → manual HMI."""
    def __init__(self, config, metrics):
        self.config, self.metrics = config, metrics
        self.auto = AutomaticReferenceEngine(config, getattr(metrics, "water", None))
        self.last_population: Optional[ReferencePopulation] = None

    def build_automatic_population(self, master_geometry, start, end, realm="aquatic"):
        pop = self.auto.build(master_geometry, realm, start, end)
        self.last_population = pop
        return pop.geometry, pop

    def _metric_reference_value(self, metric, geometry, start, end):
        if geometry is None: return None
        if metric == "water_extent": return self.metrics.water_extent(geometry, start, end).value
        if metric == "water_persistence": return self.metrics.water_persistence(geometry, start, end).value
        if metric == "ndci_proxy": return self.metrics.ndci(geometry, start, end).value
        if metric == "red_reflectance_turbidity_proxy": return self.metrics.turbidity_proxy(geometry, start, end).value
        if metric == "surface_algal_bloom_frequency": return self.metrics.bloom_frequency(geometry, start, end).value
        if metric == "riparian_ndvi":
            geometry = self._as_shapely_geometry(geometry)
            d=make_shapely_domains(geometry,self.config.spatial.riparian_buffer_m,self.config.spatial.context_buffer_km)
            return self.metrics.riparian_ndvi(ee_geometry(d["riparian_fixed"]),start,end).value
        if metric == "shoreline_disturbance_fraction":
            geometry = self._as_shapely_geometry(geometry)
            d=make_shapely_domains(geometry,self.config.spatial.riparian_buffer_m,self.config.spatial.context_buffer_km)
            return self.metrics.shoreline_disturbance(ee_geometry(d["riparian_fixed"]),start,end).value
        if metric in {"natural_landcover_fraction","terrestrial_ndvi","built_fraction"}:
            for rec in self.metrics.run(geometry,start,end):
                if rec.metric==metric: return rec.value
        return None

    @staticmethod
    def _as_shapely_geometry(geometry):
        if geometry is None: return None
        if hasattr(geometry, "__geo_interface__"):
            from shapely.geometry import shape
            return shape(geometry.__geo_interface__)
        if hasattr(geometry, "getInfo"):
            from shapely.geometry import shape
            info=geometry.getInfo()
            return shape(info) if info else None
        return geometry

    def _reference_record(self, metric, geometry, start, end):
        if geometry is None: return None
        if metric == "water_extent": return self.metrics.water_extent(geometry, start, end)
        if metric == "water_persistence": return self.metrics.water_persistence(geometry, start, end)
        if metric == "ndci_proxy": return self.metrics.ndci(geometry, start, end)
        if metric == "red_reflectance_turbidity_proxy": return self.metrics.turbidity_proxy(geometry, start, end)
        if metric == "surface_algal_bloom_frequency": return self.metrics.bloom_frequency(geometry, start, end)
        if metric == "riparian_ndvi":
            geometry=self._as_shapely_geometry(geometry); d=make_shapely_domains(geometry,self.config.spatial.riparian_buffer_m,self.config.spatial.context_buffer_km)
            return self.metrics.riparian_ndvi(ee_geometry(d["riparian_fixed"]),start,end)
        if metric == "shoreline_disturbance_fraction":
            geometry=self._as_shapely_geometry(geometry); d=make_shapely_domains(geometry,self.config.spatial.riparian_buffer_m,self.config.spatial.context_buffer_km)
            return self.metrics.shoreline_disturbance(ee_geometry(d["riparian_fixed"]),start,end)
        if metric in {"natural_landcover_fraction","terrestrial_ndvi","built_fraction"}:
            for rec in self.metrics.run(geometry,start,end):
                if rec.metric==metric: return rec
        return None

    def build(self, metric_results, master_geometry, baseline_start=None, baseline_end=None):
        if baseline_start is None or baseline_end is None:
            baseline_start, baseline_end = self.config.temporal.baseline_dates()
        auto_geom, auto_pop = (None, None)
        if self.config.reference.automatic_enabled:
            auto_geom, auto_pop = self.build_automatic_population(master_geometry, baseline_start, baseline_end, realm="aquatic")
        results=[]
        for result in metric_results:
            if not result.reference_allowed:
                results.append(benchmark_metric(result.metric, result.value, None, None))
                continue
            auto_record = None if result.metric == "water_extent" else self._reference_record(result.metric, auto_geom, baseline_start, baseline_end) if auto_geom is not None else None
            auto_value = _reference_central_value(auto_record)
            auto_uncertainty = None
            if auto_record is not None and auto_record.std_dev is not None and auto_record.valid_pixels and auto_record.valid_pixels > 1:
                auto_uncertainty=float(auto_record.std_dev)/(float(auto_record.valid_pixels)**0.5)
            if auto_value is not None and auto_pop and auto_pop.approval:
                selected_value, level, approved = auto_value, "automatic_reference", True
                ref_method=auto_pop.method; ref_state=auto_pop.reference_state; approval_basis="automated_reference_QA"
                ref_diag={**(auto_pop.diagnostics or {}),"reference_distribution":_reference_distribution_diagnostics(auto_record)}
            else:
                selected_value, level, approved = None, "none", False
                ref_method=auto_pop.method if auto_pop else "automatic_reference_unavailable"
                ref_state=auto_pop.reference_state if auto_pop else ""
                approval_basis="not_approved"
                ref_diag=(auto_pop.diagnostics if auto_pop else {}) | {"terminal_reference_status":auto_pop.status if auto_pop else "not_run"}
            status = benchmark_metric(result.metric,result.value,None,selected_value if level=="automatic_reference" else None,allow_tier2=True,tier2_approved=approved,reference_level=level,reference_uncertainty=auto_uncertainty,reference_method=ref_method,reference_state=ref_state,reference_approval_basis=approval_basis,reference_diagnostics=ref_diag)
            if level=="automatic_reference" and auto_pop:
                status.reference_n=auto_record.valid_pixels if auto_record is not None and auto_record.valid_pixels is not None else auto_pop.candidate_pixels
                status.reference_uncertainty=auto_uncertainty
                status.notes=f"Automatic reference population: {auto_pop.status}. Finite selection: strict low-pressure → least-disturbed quantile → optional manual HMI threshold." if result.metric!="water_extent" else "Water extent is a site-specific hydroperiod/footprint metric; no false 100% spatial benchmark is used."
            results.append(status)
        return results


def benchmark_dataframe(results: Iterable[BenchmarkResult]) -> pd.DataFrame:
    return pd.DataFrame([r.to_dict() for r in results])
