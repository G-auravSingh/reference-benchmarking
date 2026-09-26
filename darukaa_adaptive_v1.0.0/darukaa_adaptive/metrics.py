"""Earth-observation metric calculations with explicit domains and provenance."""
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
    evidence_class: str = "measured"
    source_type: str = "eo"
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _window_label(start: str, end_exclusive: str) -> str:
    try:
        end_inclusive = date.fromisoformat(str(end_exclusive)) - timedelta(days=1)
        return f"{start}:{end_inclusive.isoformat()}"
    except Exception:
        return f"{start}:{end_exclusive}"


class LakeMetrics:
    def __init__(self, config, water_detector):
        self.config = config
        self.water = water_detector

    def _s2(self, geometry, start, end):
        import ee
        def mask(img):
            img = ee.Image(img)
            scl = img.select("SCL")
            good = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))
            return img.updateMask(good).divide(10000).copyProperties(img, ["system:time_start"])
        return (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterBounds(geometry).filterDate(start, end)
                .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", self.config.temporal.max_cloud_pct))
                .map(mask))

    @staticmethod
    def _collection_size(collection) -> int:
        return int(collection.size().getInfo())

    @staticmethod
    def _reduce_stats(image, geometry, scale=10):
        import ee
        reducer = (ee.Reducer.mean()
                   .combine(ee.Reducer.stdDev(), sharedInputs=True)
                   .combine(ee.Reducer.percentile([5, 95]), sharedInputs=True)
                   .combine(ee.Reducer.count(), sharedInputs=True))
        data = image.reduceRegion(reducer=reducer, geometry=geometry, scale=scale, maxPixels=1e8, bestEffort=True).getInfo() or {}
        def pick(keyword):
            for k, v in data.items():
                if keyword in k.lower() and v is not None:
                    return float(v)
            return None
        count = pick("count")
        return {"mean": pick("mean"), "std_dev": pick("stddev"), "p05": pick("p5"), "p95": pick("p95"), "count": int(count) if count is not None else None}

    def _make(self, metric, value, status, window, dataset, scale, valid_observations=None, stats=None, notes=""):
        spec = get_indicator_spec(metric)
        stats = stats or {}
        return MetricResult(
            metric=metric, pillar=spec.pillar, construct=spec.construct, subdimension=spec.subdimension,
            domain=spec.domain, value=value, units=spec.units, status=status, temporal_window=window,
            dataset=dataset, scale_m=scale, direction=spec.direction, evidence_tier=spec.evidence_tier,
            reference_type=spec.reference_type, reference_allowed=spec.reference_allowed,
            valid_observations=valid_observations, valid_pixels=stats.get("count"), std_dev=stats.get("std_dev"),
            p05=stats.get("p05"), p95=stats.get("p95"), evidence_class=spec.evidence_class,
            source_type=spec.source_type, notes=notes,
        )

    def _dw_label_mode(self, geometry, start, end):
        import ee
        return (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(geometry).filterDate(start, end).select("label").mode())

    def water_extent(self, geometry, start, end):
        r = self.water.area_summary(geometry, start, end)
        return self._make("water_extent", r["water_fraction_pct"], r["status"], _window_label(start, end), r["method"], 10, r["images_used"],
                          notes="Descriptive dynamic surface-water extent. It remains contextual because absolute lake extent is system-specific.")

    def water_persistence(self, geometry, start, end):
        r = self.water.persistence(geometry, start, end)
        return self._make("water_persistence", r["water_occurrence_fraction"], r["status"], _window_label(start, end), r["method"], 10, r["n_images"],
                          notes="Fraction of valid observations classified as water, spatially averaged over the assessment boundary.")

    def ndci(self, geometry, start, end):
        s2 = self._s2(geometry, start, end); n = self._collection_size(s2)
        if n == 0:
            return self._make("ndci_proxy", None, "insufficient_data", _window_label(start, end), "COPERNICUS/S2_SR_HARMONIZED", 20, 0)
        composite = s2.median(); wm, method, _ = self.water.water_mask_for_period(geometry, start, end)
        img = composite.normalizedDifference(["B5", "B4"]).updateMask(wm).rename("NDCI")
        stats = self._reduce_stats(img, geometry, 20)
        return self._make("ndci_proxy", stats["mean"], "ok" if stats["mean"] is not None else "insufficient_water_or_data", _window_label(start, end),
                          "COPERNICUS/S2_SR_HARMONIZED + " + method, 20, n, stats,
                          "Red-edge normalized difference proxy. Interpret after automatic reference comparison and retain field-validation caveat.")

    def turbidity_proxy(self, geometry, start, end):
        s2 = self._s2(geometry, start, end); n = self._collection_size(s2)
        if n == 0:
            return self._make("red_reflectance_turbidity_proxy", None, "insufficient_data", _window_label(start, end), "COPERNICUS/S2_SR_HARMONIZED", 20, 0)
        composite = s2.median(); wm, method, _ = self.water.water_mask_for_period(geometry, start, end)
        img = composite.select("B4").updateMask(wm).rename("red_reflectance")
        stats = self._reduce_stats(img, geometry, 20)
        return self._make("red_reflectance_turbidity_proxy", stats["mean"], "ok" if stats["mean"] is not None else "insufficient_water_or_data", _window_label(start, end),
                          "COPERNICUS/S2_SR_HARMONIZED + " + method, 20, n, stats,
                          "Red-band reflectance proxy for suspended material/clarity. Direct turbidity calibration is not assumed.")

    def bloom_frequency(self, geometry, start, end):
        import ee
        s2 = self._s2(geometry, start, end); n = self._collection_size(s2)
        if n == 0:
            return self._make("surface_algal_bloom_frequency", None, "insufficient_data", _window_label(start, end), "COPERNICUS/S2_SR_HARMONIZED", 20, 0)
        wm, method, _ = self.water.water_mask_for_period(geometry, start, end)
        def fai(img):
            img = ee.Image(img)
            red = img.select("B4"); nir = img.select("B8"); swir = img.select("B11")
            baseline = red.add(swir.subtract(red).multiply((842.0 - 665.0) / (1610.0 - 665.0)))
            return nir.subtract(baseline).rename("FAI").copyProperties(img, ["system:time_start"])
        blooms = s2.map(lambda img: ee.Image(fai(ee.Image(img))).gt(self.config.water.fai_bloom_threshold).rename("bloom").updateMask(wm))
        frequency = blooms.mean().rename("bloom_frequency")
        stats = self._reduce_stats(frequency, geometry, 20)
        return self._make("surface_algal_bloom_frequency", stats["mean"], "ok" if stats["mean"] is not None else "insufficient_water_or_data", _window_label(start, end),
                          "COPERNICUS/S2_SR_HARMONIZED + " + method, 20, n, stats,
                          f"FAI bloom-proxy frequency using threshold {self.config.water.fai_bloom_threshold}; confirm with water chemistry, microscopy and chlorophyll/phycocyanin where relevant.")

    def riparian_ndvi(self, riparian_zone, start, end):
        import ee
        s2 = self._s2(riparian_zone, start, end); n = self._collection_size(s2)
        if n == 0:
            return self._make("riparian_ndvi", None, "insufficient_data", _window_label(start, end), "COPERNICUS/S2_SR_HARMONIZED", 10, 0)
        ndvi = s2.map(lambda img: ee.Image(img).normalizedDifference(["B8", "B4"]).rename("NDVI")).median()
        stats = self._reduce_stats(ndvi, riparian_zone, 10)
        return self._make("riparian_ndvi", stats["mean"], "ok" if stats["mean"] is not None else "insufficient_data", _window_label(start, end),
                          "COPERNICUS/S2_SR_HARMONIZED", 10, n, stats, "Mean NDVI of the fixed 100 m riparian domain for the baseline window.")

    def shoreline_disturbance(self, riparian_zone, start, end):
        import ee
        try:
            col = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(riparian_zone).filterDate(start, end).select("label")
            n = self._collection_size(col)
            if n == 0:
                raise ValueError("no Dynamic World observations")
            dw = col.mode().rename("label")
        except Exception:
            return self._make("shoreline_disturbance_fraction", None, "insufficient_data", _window_label(start, end), "GOOGLE/DYNAMICWORLD/V1", 10, 0)
        disturb = dw.eq(4).Or(dw.eq(6)).Or(dw.eq(7)).rename("disturbance")
        stats = self._reduce_stats(disturb, riparian_zone, 10)
        return self._make("shoreline_disturbance_fraction", stats["mean"], "ok" if stats["mean"] is not None else "insufficient_data", _window_label(start, end),
                          "GOOGLE/DYNAMICWORLD/V1", 10, n, stats,
                          "Fraction of the fixed riparian ring occupied by crops, built or bare-ground classes. Pressure proxy, not direct biodiversity loss.")

    def landcover_composition(self, geometry, start, end):
        dw = self._dw_label_mode(geometry, start, end); result = {}
        for cls in range(9):
            stats = self._reduce_stats(dw.eq(cls).rename("fraction"), geometry, 10)
            result[str(cls)] = stats["mean"]
        return result

    def riparian_ndvi_trend(self, riparian_zone, start_year, end_year):
        import ee
        import numpy as np
        from scipy.stats import kendalltau, theilslopes
        years, values = [], []
        months = sorted(set(self.config.temporal.monitoring_months))
        for year in range(start_year, end_year + 1):
            s2 = self._s2(riparian_zone, f"{year}-01-01", f"{year + 1}-01-01")
            if months != list(range(1, 13)):
                s2 = s2.map(lambda img: ee.Image(img).set("_month", ee.Image(img).date().get("month")))
                s2 = s2.filter(ee.Filter.inList("_month", months))
            n = self._collection_size(s2)
            if n == 0:
                continue
            ndvi = s2.map(lambda img: ee.Image(img).normalizedDifference(["B8", "B4"]).rename("NDVI")).median()
            stats = self._reduce_stats(ndvi, riparian_zone, 10)
            if stats["mean"] is not None:
                years.append(year); values.append(stats["mean"])
        if len(values) < self.config.temporal.min_years_for_trend:
            return self._make("riparian_ndvi_sen_slope", None, "insufficient_temporal_depth", f"{start_year}:{end_year}", "COPERNICUS/S2_SR_HARMONIZED", 10, len(values), notes=f"Only {len(values)} years had usable annual composites; minimum is {self.config.temporal.min_years_for_trend}.")
        slope, _, _, _ = theilslopes(np.asarray(values), np.asarray(years, dtype=float)); p = float(kendalltau(years, values).pvalue)
        return self._make("riparian_ndvi_sen_slope", float(slope), "ok", f"{start_year}:{end_year}", "COPERNICUS/S2_SR_HARMONIZED", 10, len(values),
                          notes=f"Theil-Sen slope over {len(values)} annual composites; Kendall tau p={p:.4g}. Descriptive Cycle-1 trend; not converted into an intactness score.")

    def run(self, boundary, riparian_zone, baseline_start=None, baseline_end=None):
        if baseline_start is None or baseline_end is None:
            baseline_start, baseline_end = self.config.temporal.baseline_dates()
        return [
            self.water_extent(boundary, baseline_start, baseline_end),
            self.water_persistence(boundary, baseline_start, baseline_end),
            self.ndci(boundary, baseline_start, baseline_end),
            self.turbidity_proxy(boundary, baseline_start, baseline_end),
            self.bloom_frequency(boundary, baseline_start, baseline_end),
            self.riparian_ndvi(riparian_zone, baseline_start, baseline_end),
            self.shoreline_disturbance(riparian_zone, baseline_start, baseline_end),
            self.riparian_ndvi_trend(riparian_zone, self.config.temporal.start_year, self.config.temporal.end_year),
        ]
