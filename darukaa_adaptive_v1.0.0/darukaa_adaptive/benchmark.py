"""Reference comparison, automatic reference populations and uncertainty-aware benchmarking."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional
import math
import pandas as pd

from .registry import get_indicator_spec
from .site import ee_geometry, make_shapely_domains, read_kml
from .reference_engine import AutomaticReferenceEngine, ReferencePopulation


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


def load_reference_csv(path: str | Path) -> Dict[str, float]:
    df = pd.read_csv(path)
    if not {"metric", "value"}.issubset(df.columns):
        raise ValueError("Reference CSV must contain columns: ['metric', 'value']")
    return {str(r.metric).strip(): float(r.value) for r in df.itertuples() if pd.notna(r.value)}


def _bootstrap_ci(values, n_boot=200):
    vals = pd.Series(values).dropna().astype(float).to_numpy()
    if len(vals) < 2:
        return None, None, None
    import numpy as np
    rng = np.random.default_rng(12345)
    medians = np.median(rng.choice(vals, size=(n_boot, len(vals)), replace=True), axis=1)
    low, high = np.percentile(medians, [2.5, 97.5])
    return float(low), float(high), float(np.std(medians, ddof=1))


def benchmark_metric(metric_name, observed, tier1, tier2, allow_tier2=True, tier1_approved=False, tier2_approved=False,
                     reference_level=None, reference_n=None, reference_ci=None, reference_uncertainty=None,
                     reference_method=""):
    spec = get_indicator_spec(metric_name)
    if not spec.reference_allowed:
        return BenchmarkResult(metric_name, observed, tier1, tier2, None, "none", None, None, None,
                               "not_referenceable", "not_referenceable", notes="Contextual/screening indicator; not automatically scored.")
    selected, level, approved = None, "none", False
    if tier1 is not None:
        selected, level, approved = float(tier1), "tier1", bool(tier1_approved)
    elif allow_tier2 and tier2 is not None:
        selected, level, approved = float(tier2), "tier2", bool(tier2_approved)
    if selected is None:
        return BenchmarkResult(metric_name, observed, tier1, tier2, None, "none", None, None, None,
                               "reference_unavailable", "reference_unavailable", notes="No comparable reference population/value was available.")
    raw = raw_relative_ratio(observed, selected, spec.direction)
    intact = reference_relative_intactness(observed, selected, spec.direction)
    ci_low = ci_high = None
    if reference_ci:
        ci_low, ci_high = reference_ci
    return BenchmarkResult(metric_name, observed, tier1, tier2, selected, reference_level or level, raw,
                           intact, None if intact is None else intact * 100,
                           "reference_relative_ratio" if spec.direction != "reference_target" else "distance_from_reference",
                           "ok", approved, reference_n, ci_low, ci_high, reference_uncertainty,
                           reference_method or "reference_population", notes="Reference approval is gated by the profile/reference diagnostics.")


def benchmark_observation(metric_name, observed, reference, direction, reference_level="external", reference_approved=True):
    if reference is None:
        return BenchmarkResult(metric_name, observed, None, None, None, "none", None, None, None,
                               "reference_unavailable", "reference_unavailable")
    raw = raw_relative_ratio(observed, reference, direction)
    intact = reference_relative_intactness(observed, reference, direction)
    return BenchmarkResult(metric_name, observed, None, None, float(reference), reference_level, raw, intact,
                           None if intact is None else intact * 100,
                           "reference_relative_ratio" if direction != "reference_target" else "distance_from_reference",
                           "ok", bool(reference_approved), notes="External evidence uses the same scoring pathway.")


class ReferenceEngine:
    """Automatic reference engine with optional manual overrides."""
    def __init__(self, config, metrics):
        self.config, self.metrics = config, metrics
        self.auto = AutomaticReferenceEngine(config, getattr(metrics, "water", None))
        self.last_population: Optional[ReferencePopulation] = None

    def build_tier1_geometry(self, path):
        if not path:
            return None
        geom, _ = read_kml(path)
        return geom

    def build_automatic_population(self, master_geometry, start, end, realm="aquatic"):
        pop = self.auto.build(master_geometry, realm, start, end)
        self.last_population = pop
        return pop.geometry, pop

    def build_tier2_candidate_geometry(self, context_geometry, start, end):
        # Backward-compatible alias: this is now an automatically derived candidate,
        # not a generic context-ring benchmark.
        try:
            pop = self.auto.aquatic_candidate(context_geometry, start, end)
            return pop.geometry, pop.status
        except Exception as exc:
            return None, f"error:{exc}"

    def _metric_reference_value(self, metric, geometry, start, end):
        if geometry is None:
            return None
        if metric == "water_extent": return self.metrics.water_extent(geometry, start, end).value
        if metric == "water_persistence": return self.metrics.water_persistence(geometry, start, end).value
        if metric == "ndci_proxy": return self.metrics.ndci(geometry, start, end).value
        if metric == "red_reflectance_turbidity_proxy": return self.metrics.turbidity_proxy(geometry, start, end).value
        if metric == "surface_algal_bloom_frequency": return self.metrics.bloom_frequency(geometry, start, end).value
        if metric == "riparian_ndvi":
            domains = make_shapely_domains(geometry, self.config.spatial.riparian_buffer_m, self.config.spatial.context_buffer_km)
            return self.metrics.riparian_ndvi(ee_geometry(domains["riparian_fixed"]), start, end).value
        if metric == "shoreline_disturbance_fraction":
            domains = make_shapely_domains(geometry, self.config.spatial.riparian_buffer_m, self.config.spatial.context_buffer_km)
            return self.metrics.shoreline_disturbance(ee_geometry(domains["riparian_fixed"]), start, end).value
        if metric in {"natural_landcover_fraction", "terrestrial_ndvi", "built_fraction"}:
            for rec in self.metrics.run(geometry, start, end):
                if rec.metric == metric: return rec.value
        return None

    def _reference_record(self, metric, geometry, start, end):
        if geometry is None: return None
        if metric == "water_extent": return self.metrics.water_extent(geometry, start, end)
        if metric == "water_persistence": return self.metrics.water_persistence(geometry, start, end)
        if metric == "ndci_proxy": return self.metrics.ndci(geometry, start, end)
        if metric == "red_reflectance_turbidity_proxy": return self.metrics.turbidity_proxy(geometry, start, end)
        if metric == "surface_algal_bloom_frequency": return self.metrics.bloom_frequency(geometry, start, end)
        if metric == "riparian_ndvi":
            d=make_shapely_domains(geometry,self.config.spatial.riparian_buffer_m,self.config.spatial.context_buffer_km)
            return self.metrics.riparian_ndvi(ee_geometry(d["riparian_fixed"]),start,end)
        if metric == "shoreline_disturbance_fraction":
            d=make_shapely_domains(geometry,self.config.spatial.riparian_buffer_m,self.config.spatial.context_buffer_km)
            return self.metrics.shoreline_disturbance(ee_geometry(d["riparian_fixed"]),start,end)
        if metric in {"natural_landcover_fraction","terrestrial_ndvi","built_fraction"}:
            for rec in self.metrics.run(geometry,start,end):
                if rec.metric==metric: return rec
        return None

    def build(self, metric_results, master_geometry, tier1_geometry=None, tier2_geometry=None, baseline_start=None, baseline_end=None):
        if baseline_start is None or baseline_end is None:
            baseline_start, baseline_end = self.config.temporal.baseline_dates()
        manual = load_reference_csv(self.config.reference.tier1_reference_csv) if self.config.reference.tier1_reference_csv else {}
        auto_geom, auto_pop = (None, None)
        if self.config.reference.automatic_enabled and tier2_geometry is None:
            auto_geom, auto_pop = self.build_automatic_population(master_geometry, baseline_start, baseline_end, realm="aquatic")
        else:
            auto_geom = tier2_geometry
        results=[]
        for result in metric_results:
            if not result.reference_allowed:
                results.append(benchmark_metric(result.metric, result.value, None, None))
                continue
            tier1_value = manual.get(result.metric)
            if tier1_value is None and tier1_geometry is not None:
                tier1_value = self._metric_reference_value(result.metric, tier1_geometry, baseline_start, baseline_end)
            auto_record = None if result.metric == "water_extent" else self._reference_record(result.metric, auto_geom, baseline_start, baseline_end) if auto_geom is not None else None
            auto_value = None if auto_record is None else auto_record.value
            auto_uncertainty = None
            if auto_record is not None and auto_record.std_dev is not None and auto_record.valid_pixels and auto_record.valid_pixels > 1:
                # Conservative descriptive SE proxy; spatial autocorrelation means this is not a formal independent-pixel CI.
                auto_uncertainty = float(auto_record.std_dev) / (float(auto_record.valid_pixels) ** 0.5)
            level = "tier1" if tier1_value is not None else "auto_aquatic"
            approved = self.config.reference.tier1_approved_for_scoring if tier1_value is not None else bool(auto_pop and auto_pop.approval and auto_value is not None)
            status = benchmark_metric(result.metric, result.value, tier1_value, auto_value,
                                      allow_tier2=True, tier1_approved=approved if tier1_value is not None else False,
                                      tier2_approved=approved if tier1_value is None else False,
                                      reference_level=level, reference_uncertainty=auto_uncertainty)
            if tier1_value is None and auto_pop:
                status.reference_method = auto_pop.method
                status.reference_n = auto_pop.candidate_pixels
                status.reference_uncertainty = None
                status.notes = (f"Automatic reference candidate: {auto_pop.status}. Diagnostics: {auto_pop.diagnostics}" if result.metric != "water_extent" else "Water extent is a site-specific hydroperiod/footprint metric; automatic spatial water-pixel reference is not used as a false 100% benchmark. Use a matched temporal/hydrological reference or approved manual benchmark.")
            results.append(status)
        return results


def benchmark_dataframe(results: Iterable[BenchmarkResult]) -> pd.DataFrame:
    return pd.DataFrame([r.to_dict() for r in results])
