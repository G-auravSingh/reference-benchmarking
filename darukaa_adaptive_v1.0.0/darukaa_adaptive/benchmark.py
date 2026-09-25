"""Reference comparison and direction-aware intactness benchmarking."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

import pandas as pd

from .registry import get_indicator_spec
from .site import ee_geometry, make_shapely_domains, read_kml


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
    notes: str = ""

    def to_dict(self):
        return asdict(self)


def _cap01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def reference_relative_intactness(
    observed: Optional[float],
    reference: Optional[float],
    direction: str,
) -> Optional[float]:
    """Return bounded 0-1 intactness against a comparable reference.

    direction:
      - higher_is_better: observed/reference
      - lower_is_better: reference/observed
      - reference_target: 1 - absolute proportional departure from reference

    The reference_target form is for metrics where departure in either direction can
    represent loss of comparability/condition. It is explicitly declared in the registry.
    """
    if observed is None or reference is None:
        return None
    observed = float(observed)
    reference = float(reference)

    if direction == "higher_is_better":
        if reference == 0:
            return None
        return _cap01(observed / reference)

    if direction == "lower_is_better":
        if observed == 0:
            return 1.0 if reference >= 0 else None
        return _cap01(reference / observed)

    if direction == "reference_target":
        if reference == 0:
            return 1.0 if observed == 0 else 0.0
        return _cap01(1.0 - abs(observed - reference) / abs(reference))

    return None


def intactness_ratio(observed: float, reference: float, higher_is_better: bool) -> Optional[float]:
    """Backward-compatible high/low directional ratio."""
    return reference_relative_intactness(
        observed,
        reference,
        "higher_is_better" if higher_is_better else "lower_is_better",
    )


def raw_relative_ratio(
    observed: Optional[float],
    reference: Optional[float],
    direction: str,
) -> Optional[float]:
    if observed is None or reference is None:
        return None
    observed = float(observed)
    reference = float(reference)
    if reference == 0:
        return None
    if direction == "higher_is_better":
        return float(observed / reference)
    if direction == "lower_is_better":
        if observed == 0:
            return None
        return float(reference / observed)
    if direction == "reference_target":
        return float(observed / reference) if reference != 0 else None
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


def benchmark_metric(
    metric_name: str,
    observed: Optional[float],
    tier1: Optional[float],
    tier2: Optional[float],
    allow_tier2: bool = True,
    tier1_approved: bool = False,
    tier2_approved: bool = False,
) -> BenchmarkResult:
    spec = get_indicator_spec(metric_name)

    if not spec.reference_allowed:
        return BenchmarkResult(
            metric=metric_name,
            observed_value=observed,
            tier1_value=tier1,
            tier2_value=tier2,
            selected_reference=None,
            selected_reference_level="none",
            raw_relative_ratio=None,
            intactness_ratio=None,
            intactness_score_0_100=None,
            comparison_method="not_referenceable",
            benchmark_status="not_referenceable",
            reference_approved_for_scoring=False,
            notes="This metric is intentionally contextual and has no generic ecological reference comparison.",
        )

    selected = None
    level = "none"
    approved = False
    if tier1 is not None:
        selected, level = float(tier1), "tier1"
        approved = bool(tier1_approved)
    elif allow_tier2 and tier2 is not None:
        selected, level = float(tier2), "tier2"
        approved = bool(tier2_approved)

    if selected is None:
        return BenchmarkResult(
            metric=metric_name,
            observed_value=observed,
            tier1_value=tier1,
            tier2_value=tier2,
            selected_reference=None,
            selected_reference_level="none",
            raw_relative_ratio=None,
            intactness_ratio=None,
            intactness_score_0_100=None,
            comparison_method="reference_unavailable",
            benchmark_status="reference_unavailable",
            reference_approved_for_scoring=False,
            notes="Reference value is not available for this metric.",
        )

    raw = raw_relative_ratio(observed, selected, spec.direction)
    intact = reference_relative_intactness(observed, selected, spec.direction)
    return BenchmarkResult(
        metric=metric_name,
        observed_value=observed,
        tier1_value=tier1,
        tier2_value=tier2,
        selected_reference=selected,
        selected_reference_level=level,
        raw_relative_ratio=raw,
        intactness_ratio=intact,
        intactness_score_0_100=None if intact is None else intact * 100.0,
        comparison_method=(
            "reference_relative_ratio"
            if spec.direction in {"higher_is_better", "lower_is_better"}
            else "distance_from_reference"
        ),
        benchmark_status="ok",
        reference_approved_for_scoring=approved,
        notes="Tier-1 is preferred over Tier-2 when both are available. Scoring requires explicit approval of the selected reference tier.",
    )


def benchmark_observation(
    metric_name: str,
    observed: Optional[float],
    reference: Optional[float],
    direction: str,
    reference_level: str = "external",
    reference_approved: bool = True,
) -> BenchmarkResult:
    """Benchmark an external/field/acoustic observation using supplied metadata.

    This deliberately does not require the metric to be hard-coded in the aquatic
    registry. The caller is responsible for supplying the metric's pillar and direction
    in the observation table.
    """
    if reference is None:
        return BenchmarkResult(
            metric=metric_name,
            observed_value=observed,
            tier1_value=None,
            tier2_value=None,
            selected_reference=None,
            selected_reference_level="none",
            raw_relative_ratio=None,
            intactness_ratio=None,
            intactness_score_0_100=None,
            comparison_method="reference_unavailable",
            benchmark_status="reference_unavailable",
            reference_approved_for_scoring=False,
            notes="External reference value was not supplied.",
        )

    raw = raw_relative_ratio(observed, reference, direction)
    intact = reference_relative_intactness(observed, reference, direction)
    return BenchmarkResult(
        metric=metric_name,
        observed_value=observed,
        tier1_value=None,
        tier2_value=None,
        selected_reference=float(reference),
        selected_reference_level=reference_level,
        raw_relative_ratio=raw,
        intactness_ratio=intact,
        intactness_score_0_100=None if intact is None else intact * 100.0,
        comparison_method=(
            "reference_relative_ratio"
            if direction in {"higher_is_better", "lower_is_better"}
            else "distance_from_reference"
        ),
        benchmark_status="ok",
        reference_approved_for_scoring=bool(reference_approved),
        notes="External observation scored using the same Darukaa fixed intactness bands.",
    )


class ReferenceEngine:
    """Build metric-specific Tier-1 and Tier-2 reference comparisons."""

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
        """Return the fixed context ring only when minimum reference checks pass."""
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
        if metric == "water_extent":
            return self.metrics.water_extent(geometry, start, end).value
        if metric == "water_persistence":
            return self.metrics.water_persistence(geometry, start, end).value
        if metric == "ndci_proxy":
            return self.metrics.ndci(geometry, start, end).value
        if metric == "red_reflectance_turbidity_proxy":
            return self.metrics.turbidity_proxy(geometry, start, end).value
        if metric == "surface_algal_bloom_frequency":
            return self.metrics.bloom_frequency(geometry, start, end).value
        if metric == "riparian_ndvi":
            domains = make_shapely_domains(
                geometry,
                self.config.spatial.riparian_buffer_m,
                self.config.spatial.context_buffer_km,
            )
            return self.metrics.riparian_ndvi(
                ee_geometry(domains["riparian_fixed"]),
                start,
                end,
            ).value
        if metric == "shoreline_disturbance_fraction":
            domains = make_shapely_domains(
                geometry,
                self.config.spatial.riparian_buffer_m,
                self.config.spatial.context_buffer_km,
            )
            return self.metrics.shoreline_disturbance(
                ee_geometry(domains["riparian_fixed"]),
                start,
                end,
            ).value
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
                results.append(
                    benchmark_metric(
                        result.metric,
                        result.value,
                        None,
                        None,
                        tier1_approved=self.config.reference.tier1_approved_for_scoring,
                        tier2_approved=self.config.reference.tier2_approved_for_scoring,
                    )
                )
                continue

            tier1_value = table.get(result.metric)
            if tier1_value is None and self.config.reference.tier1_enabled and tier1_geometry is not None:
                tier1_value = self._metric_reference_value(
                    result.metric,
                    tier1_geometry,
                    baseline_start,
                    baseline_end,
                    True,
                )

            tier2_value = None
            if self.config.reference.tier2_enabled and tier2_geometry is not None:
                tier2_value = self._metric_reference_value(
                    result.metric,
                    tier2_geometry,
                    baseline_start,
                    baseline_end,
                    False,
                )

            results.append(
                benchmark_metric(
                    result.metric,
                    result.value,
                    tier1_value,
                    tier2_value,
                    allow_tier2=self.config.reference.tier2_enabled,
                    tier1_approved=self.config.reference.tier1_approved_for_scoring,
                    tier2_approved=self.config.reference.tier2_approved_for_scoring,
                )
            )
        return results


def benchmark_dataframe(results: Iterable[BenchmarkResult]) -> pd.DataFrame:
    return pd.DataFrame([r.to_dict() for r in results])
