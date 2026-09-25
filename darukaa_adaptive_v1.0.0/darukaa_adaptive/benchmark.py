"""Metric-level Tier-1/Tier-2 reference benchmarking."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

import pandas as pd

from .registry import get_indicator_spec
from .site import make_shapely_domains, read_kml, ee_geometry


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
    benchmark_status: str
    notes: str = ""

    def to_dict(self):
        return asdict(self)


def intactness_ratio(observed: float, reference: float, higher_is_better: bool) -> Optional[float]:
    """Return a 0-1 capped direction-aware intactness ratio."""
    if observed is None or reference is None or reference == 0:
        return None
    if higher_is_better:
        raw = observed / reference
    else:
        if observed == 0:
            return 1.0 if reference >= 0 else None
        raw = reference / observed
    return max(0.0, min(1.0, float(raw)))


def raw_relative_ratio(observed: Optional[float], reference: Optional[float], direction: str) -> Optional[float]:
    if observed is None or reference is None or reference == 0:
        return None
    if direction == "higher_is_better":
        return float(observed / reference)
    if direction == "lower_is_better":
        if observed == 0:
            return None
        return float(reference / observed)
    return None


def baseline_delta(current: Optional[float], baseline: Optional[float]):
    if current is None or baseline is None:
        return None
    return float(current - baseline)


def percent_change(current: Optional[float], baseline: Optional[float]):
    if current is None or baseline in (None, 0):
        return None
    return float((current - baseline) / baseline * 100.0)


def load_reference_csv(path: str | Path) -> Dict[str, float]:
    df = pd.read_csv(path)
    required = {"metric", "value"}
    if not required.issubset(df.columns):
        raise ValueError(f"Reference CSV must contain columns: {sorted(required)}")
    out = {}
    for _, row in df.iterrows():
        metric = str(row["metric"]).strip()
        if not metric or metric.startswith("#"):
            continue
        if pd.notna(row["value"]):
            out[metric] = float(row["value"])
    return out


def benchmark_metric(metric_name: str, observed: Optional[float], tier1: Optional[float], tier2: Optional[float],
                     allow_tier2: bool = True) -> BenchmarkResult:
    spec = get_indicator_spec(metric_name)
    if not spec.reference_allowed:
        return BenchmarkResult(metric_name, observed, tier1, tier2, None, "none", None, None,
                                "not_referenceable", "This metric is intentionally contextual and has no generic ecological reference ratio.")

    selected = None
    level = "none"
    if tier1 is not None:
        selected, level = tier1, "tier1"
    elif allow_tier2 and tier2 is not None:
        selected, level = tier2, "tier2"

    if selected is None:
        return BenchmarkResult(metric_name, observed, tier1, tier2, None, "none", None, None,
                                "reference_unavailable", "Reference value is not available for this metric.")

    raw = raw_relative_ratio(observed, selected, spec.direction)
    intact = None if raw is None else max(0.0, min(1.0, raw))
    return BenchmarkResult(metric_name, observed, tier1, tier2, selected, level, raw, intact, "ok",
                           "Tier-1 is preferred over Tier-2 when both are available.")


class ReferenceEngine:
    """Build benchmark values from optional Tier-1 inputs and an automatic Tier-2 candidate zone."""

    def __init__(self, config, metrics):
        self.config = config
        self.metrics = metrics

    @staticmethod
    def _reference_metric_csv(config) -> Dict[str, float]:
        path = config.reference.tier1_reference_csv
        if not path:
            return {}
        return load_reference_csv(path)

    def build_tier1_geometry(self, path: Optional[str]):
        if not path:
            return None
        geom, _ = read_kml(path)
        return geom

    def build_tier2_candidate_geometry(self, context_geometry, start: str, end: str):
        """Return the fixed context ring only when it meets minimum water-reference checks."""
        if not self.config.reference.tier2_enabled:
            return None, "disabled"
        try:
            summary = self.metrics.water.area_summary(context_geometry, start, end)
            occurrence = summary.get("occurrence_fraction")
            water_area = summary.get("water_area_ha")
            if occurrence is None or water_area is None:
                return None, "insufficient_data"
            if occurrence < self.config.reference.tier2_min_water_occurrence:
                return None, f"occurrence_below_threshold:{occurrence:.4f}"
            if water_area < self.config.reference.tier2_min_area_ha:
                return None, f"water_area_below_threshold:{water_area:.4f}"
            return context_geometry, "candidate_ready"
        except Exception as exc:
            return None, f"validation_error:{exc}"

    def _metric_reference_value(self, metric: str, geometry, start: str, end: str, is_tier1: bool):
        if geometry is None:
            return None
        if metric == "ndci_proxy":
            return self.metrics.ndci(geometry, start, end).value
        if metric == "red_reflectance_turbidity_proxy":
            return self.metrics.turbidity_proxy(geometry, start, end).value
        if metric == "surface_algal_bloom_frequency":
            return self.metrics.bloom_frequency(geometry, start, end).value
        if metric == "shoreline_disturbance_fraction":
            if not is_tier1:
                return None
            domains = make_shapely_domains(geometry, self.config.spatial.riparian_buffer_m,
                                           self.config.spatial.context_buffer_km)
            return self.metrics.shoreline_disturbance(ee_geometry(domains["riparian_fixed"]), start, end).value
        return None

    def build(
        self,
        metric_results,
        master_geometry,
        tier1_geometry=None,
        tier2_geometry=None,
        baseline_start: Optional[str] = None,
        baseline_end: Optional[str] = None,
    ) -> list[BenchmarkResult]:
        if baseline_start is None or baseline_end is None:
            baseline_start, baseline_end = self.config.temporal.baseline_dates()

        table = self._reference_metric_csv(self.config) if self.config.reference.enabled else {}
        results: list[BenchmarkResult] = []
        for result in metric_results:
            if not result.reference_allowed:
                results.append(benchmark_metric(result.metric, result.value, None, None))
                continue

            tier1_value = table.get(result.metric)
            if tier1_value is None and self.config.reference.tier1_enabled and tier1_geometry is not None:
                tier1_value = self._metric_reference_value(result.metric, tier1_geometry, baseline_start, baseline_end, True)

            tier2_value = None
            if self.config.reference.tier2_enabled and tier2_geometry is not None:
                tier2_value = self._metric_reference_value(result.metric, tier2_geometry, baseline_start, baseline_end, False)

            results.append(
                benchmark_metric(
                    result.metric,
                    result.value,
                    tier1_value,
                    tier2_value,
                    allow_tier2=self.config.reference.tier2_enabled,
                )
            )
        return results


def benchmark_dataframe(results: Iterable[BenchmarkResult]) -> pd.DataFrame:
    return pd.DataFrame([r.to_dict() for r in results])
