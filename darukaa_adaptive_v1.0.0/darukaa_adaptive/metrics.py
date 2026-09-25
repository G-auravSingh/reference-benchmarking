"""Aquatic/lake metric calculations with explicit spatial domains and provenance."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any, Dict, Optional

from .registry import get_indicator_spec


@dataclass
class MetricResult:
    metric: str
    pillar: str
    construct: str
    subdimension: str
    domain: str
    value: Optional[float]
    units: str
    status: str
    temporal_window: str
    dataset: str
    scale_m: int
    direction: str
    evidence_tier: str
    reference_type: str
    reference_allowed: bool
    score_eligible: bool = False
    valid_observations: Optional[int] = None
    valid_pixels: Optional[int] = None
    std_dev: Optional[float] = None
    p05: Optional[float] = None
    p95: Optional[float] = None
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _window_label(start: str, end_exclusive: str) -> str:
    try:
        end_inclusive = date.fromisoformat(end_exclusive) - timedelta(days=1)
        return f"{start}:{end_inclusive.isoformat()}"
    except Exception:
        return f"{start}:{end_exclusive}"


class LakeMetrics:
    """Metric runner for the aquatic lake profile.

    Metric extraction is separate from reference benchmarking and scoring. This is
    deliberate: a value can be valid and reportable without being benchmarkable or
    score-eligible.
    """

    def __init__(self, config, water_detector):
        self.config = config
        self.water = water_detector

    def _s2(self, geometry, start, end):
        import ee

        def mask(img):
            img = ee.Image(img)
            scl = img.select("SCL")
            good = (
                scl.neq(3)
                .And(scl.neq(8))
                .And(scl.neq(9))
                .And(scl.neq(10))
                .And(scl.neq(11))
            )
            return img.updateMask(good).divide(10000).copyProperties(img, ["system:time_start"])

        return (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(geometry)
            .filterDate(start, end)
            .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", self.config.temporal.max_cloud_pct))
            .map(mask)
        )

    def _dw_label_mode(self, geometry, start, end):
        import ee
        return (
            ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
            .filterBounds(geometry)
            .filterDate(start, end)
            .select("label")
            .mode()
        )

    @staticmethod
    def _collection_size(collection) -> int:
        return int(collection.size().getInfo())

    def _reduce_stats(self, image, geometry, scale=10) -> Dict[str, Optional[float]]:
        import ee

        reducer = (
            ee.Reducer.mean()
            .combine(ee.Reducer.stdDev(), sharedInputs=True)
            .combine(ee.Reducer.percentile([5, 95]), sharedInputs=True)
            .combine(ee.Reducer.count(), sharedInputs=True)
        )
        data = image.reduceRegion(
            reducer=reducer,
            geometry=geometry,
            scale=scale,
            maxPixels=1e8,
            bestEffort=True,
        ).getInfo() or {}

        def pick(keyword: str) -> Optional[float]:
            for key, value in data.items():
                if keyword in key.lower() and value is not None:
                    return float(value)
            return None

        count = pick("count")
        return {
            "mean": pick("mean"),
            "std_dev": pick("stddev"),
            "p05": pick("p5"),
            "p95": pick("p95"),
            "count": int(count) if count is not None else None,
        }

    def _make(self, metric: str, value: Optional[float], status: str, window: str, dataset: str,
              scale: int, valid_observations: Optional[int] = None, stats: Optional[Dict] = None,
              notes: str = "") -> MetricResult:
        spec = get_indicator_spec(metric)
        stats = stats or {}
        return MetricResult(
            metric=metric,
            pillar=spec.pillar,
            construct=spec.construct,
            subdimension=spec.subdimension,
            domain=spec.domain,
            value=value,
            units=spec.units,
            status=status,
            temporal_window=window,
            dataset=dataset,
            scale_m=scale,
            direction=spec.direction,
            evidence_tier=spec.evidence_tier,
            reference_type=spec.reference_type,
            reference_allowed=spec.reference_allowed,
            score_eligible=False,
            valid_observations=valid_observations,
            valid_pixels=stats.get("count"),
            std_dev=stats.get("std_dev"),
            p05=stats.get("p05"),
            p95=stats.get("p95"),
            notes=notes,
        )

    def water_extent(self, geometry, start, end):
        r = self.water.area_summary(geometry, start, end)
        return self._make(
            "water_extent", r["water_fraction_pct"],
            r["status"], _window_label(start, end), r["method"], 10,
            r["images_used"], None,
            "Dynamic surface-water extent; not treated as inherently better/worse because hydroperiod is system-specific.",
        )

    def water_persistence(self, geometry, start, end):
        r = self.water.persistence(geometry, start, end)
        return self._make(
            "water_persistence", r["water_occurrence_fraction"],
            r["status"], _window_label(start, end), r["method"], 10,
            r["n_images"], None,
            "Fraction of valid observations classified as water, spatially averaged over the master boundary.",
        )

    def ndci(self, geometry, start, end):
        s2 = self._s2(geometry, start, end)
        n = self._collection_size(s2)
        if n == 0:
            return self._make("ndci_proxy", None, "insufficient_data", _window_label(start, end),
                              "COPERNICUS/S2_SR_HARMONIZED", 20, 0,
                              notes="No Sentinel-2 observations met the configured cloud filter.")
        composite = s2.median()
        wm, method, _ = self.water.water_mask_for_period(geometry, start, end)
        img = composite.normalizedDifference(["B5", "B4"]).updateMask(wm).rename("NDCI")
        stats = self._reduce_stats(img, geometry, 20)
        return self._make(
            "ndci_proxy", stats["mean"], "ok" if stats["mean"] is not None else "insufficient_water_or_data",
            _window_label(start, end), "COPERNICUS/S2_SR_HARMONIZED + " + method, 20, n, stats,
            "Water-masked chlorophyll/trophic proxy. Requires site and water-type calibration before ecological threshold scoring.",
        )

    def turbidity_proxy(self, geometry, start, end):
        s2 = self._s2(geometry, start, end)
        n = self._collection_size(s2)
        if n == 0:
            return self._make("red_reflectance_turbidity_proxy", None, "insufficient_data",
                              _window_label(start, end), "COPERNICUS/S2_SR_HARMONIZED", 20, 0)
        composite = s2.median()
        wm, method, _ = self.water.water_mask_for_period(geometry, start, end)
        img = composite.select("B4").updateMask(wm).rename("red_reflectance")
        stats = self._reduce_stats(img, geometry, 20)
        return self._make(
            "red_reflectance_turbidity_proxy", stats["mean"],
            "ok" if stats["mean"] is not None else "insufficient_water_or_data",
            _window_label(start, end), "COPERNICUS/S2_SR_HARMONIZED + " + method, 20, n, stats,
            "Water-masked red-band proxy. Do not report as calibrated turbidity without field/sensor validation.",
        )

    def bloom_frequency(self, geometry, start, end):
        import ee

        s2 = self._s2(geometry, start, end)
        n = self._collection_size(s2)
        if n == 0:
            return self._make("surface_algal_bloom_frequency", None, "insufficient_data",
                              _window_label(start, end), "COPERNICUS/S2_SR_HARMONIZED", 20, 0)

        wm, method, _ = self.water.water_mask_for_period(geometry, start, end)

        def fai(img):
            img = ee.Image(img)
            red = img.select("B4")
            nir = img.select("B8")
            swir = img.select("B11")
            baseline = red.add(
                swir.subtract(red).multiply((842.0 - 665.0) / (1610.0 - 665.0))
            )
            return nir.subtract(baseline).rename("FAI").copyProperties(img, ["system:time_start"])

        blooms = s2.map(
            lambda img: (
                ee.Image(fai(ee.Image(img)))
                .gt(self.config.water.fai_bloom_threshold)
                .rename("bloom")
                .updateMask(wm)
            )
        )
        frequency = blooms.mean().rename("bloom_frequency")
        stats = self._reduce_stats(frequency, geometry, 20)
        return self._make(
            "surface_algal_bloom_frequency", stats["mean"],
            "ok" if stats["mean"] is not None else "insufficient_water_or_data",
            _window_label(start, end), "COPERNICUS/S2_SR_HARMONIZED + " + method, 20, n, stats,
            f"FAI bloom-proxy frequency using threshold {self.config.water.fai_bloom_threshold}; validate against field observations.",
        )

    def shoreline_disturbance(self, riparian_zone, start, end):
        try:
            dw = self._dw_label_mode(riparian_zone, start, end)
            img_count = self._collection_size(
                __import__("ee").ImageCollection("GOOGLE/DYNAMICWORLD/V1")
                .filterBounds(riparian_zone).filterDate(start, end).select("label")
            )
        except Exception:
            return self._make("shoreline_disturbance_fraction", None, "insufficient_data",
                              _window_label(start, end), "GOOGLE/DYNAMICWORLD/V1", 10, 0)
        disturb = dw.eq(4).Or(dw.eq(6)).Or(dw.eq(7)).rename("disturbance")
        stats = self._reduce_stats(disturb, riparian_zone, 10)
        return self._make(
            "shoreline_disturbance_fraction", stats["mean"],
            "ok" if stats["mean"] is not None else "insufficient_data",
            _window_label(start, end), "GOOGLE/DYNAMICWORLD/V1", 10, img_count, stats,
            "Share of the fixed 100 m ring mapped as crops, built or bare ground. This is a pressure proxy, not direct biodiversity loss.",
        )

    def landcover_composition(self, geometry, start, end) -> Dict[str, Optional[float]]:
        dw = self._dw_label_mode(geometry, start, end)
        result: Dict[str, Optional[float]] = {}
        for cls in range(9):
            stats = self._reduce_stats(dw.eq(cls).rename("fraction"), geometry, 10)
            result[str(cls)] = stats["mean"]
        return result

    def riparian_ndvi_trend(self, riparian_zone, start_year, end_year):
        """Annual median NDVI with Theil-Sen slope and Kendall tau p-value."""
        import numpy as np
        from scipy.stats import kendalltau, theilslopes

        years, values, image_counts = [], [], []
        import ee

        months = sorted(set(self.config.temporal.monitoring_months))
        for year in range(start_year, end_year + 1):
            s2 = self._s2(riparian_zone, f"{year}-01-01", f"{year + 1}-01-01")
            if months != list(range(1, 13)):
                s2 = s2.map(
                    lambda img: ee.Image(img).set(
                        "_month",
                        ee.Image(img).date().get("month"),
                    )
                )
                s2 = s2.filter(ee.Filter.inList("_month", months))
            n = self._collection_size(s2)
            if n == 0:
                continue
            ndvi = s2.map(
                lambda img: ee.Image(img)
                .normalizedDifference(["B8", "B4"])
                .rename("NDVI")
            ).median()
            stats = self._reduce_stats(ndvi, riparian_zone, 10)
            if stats["mean"] is not None:
                years.append(year)
                values.append(stats["mean"])
                image_counts.append(n)

        if len(values) < self.config.temporal.min_years_for_trend:
            return self._make(
                "riparian_ndvi_sen_slope", None, "insufficient_temporal_depth",
                f"{start_year}:{end_year}", "COPERNICUS/S2_SR_HARMONIZED", 10, len(values),
                notes=f"Only {len(values)} years had usable annual composites; minimum is {self.config.temporal.min_years_for_trend}.",
            )

        slope, _, _, _ = theilslopes(np.asarray(values), np.asarray(years, dtype=float))
        p = float(kendalltau(years, values).pvalue)
        return self._make(
            "riparian_ndvi_sen_slope", float(slope), "ok",
            f"{start_year}:{end_year}", "COPERNICUS/S2_SR_HARMONIZED", 10, len(values),
            notes=(f"Theil-Sen slope over {len(values)} annual composites; Kendall tau p={p:.4g}. "
                   "Trend is descriptive and not automatically interpreted as ecological recovery."),
        )

    def run(self, boundary, riparian_zone, baseline_start: Optional[str] = None,
            baseline_end: Optional[str] = None) -> list[MetricResult]:
        """Run the baseline metrics using an explicit date window."""
        if baseline_start is None or baseline_end is None:
            baseline_start, baseline_end = self.config.temporal.baseline_dates()

        out = [
            self.water_extent(boundary, baseline_start, baseline_end),
            self.water_persistence(boundary, baseline_start, baseline_end),
            self.ndci(boundary, baseline_start, baseline_end),
            self.turbidity_proxy(boundary, baseline_start, baseline_end),
            self.bloom_frequency(boundary, baseline_start, baseline_end),
            self.shoreline_disturbance(riparian_zone, baseline_start, baseline_end),
            self.riparian_ndvi_trend(
                riparian_zone,
                self.config.temporal.start_year,
                self.config.temporal.end_year,
            ),
        ]
        return out
