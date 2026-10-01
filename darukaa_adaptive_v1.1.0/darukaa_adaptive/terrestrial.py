"""Terrestrial EO core sharing the adaptive scoring contract."""
from __future__ import annotations

from .metrics import MetricResult
from .registry import get_indicator_spec


class TerrestrialMetrics:
    """Minimal terrestrial EO core with the same QA/provenance contract as aquatic metrics."""

    def __init__(self, config):
        self.config = config

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

    @staticmethod
    def _stats(image, geometry, band, scale=10):
        import ee

        reducer = (
            ee.Reducer.mean()
            .combine(ee.Reducer.stdDev(), sharedInputs=True)
            .combine(ee.Reducer.percentile([5, 10, 25, 50, 75, 90, 95]), sharedInputs=True)
            .combine(ee.Reducer.count(), sharedInputs=True)
        )
        data = image.reduceRegion(
            reducer=reducer, geometry=geometry, scale=scale,
            maxPixels=1e9, bestEffort=True,
        ).getInfo() or {}

        def pick(name):
            value = data.get(f"{band}_{name}")
            return None if value is None else float(value)

        count = data.get(f"{band}_count")
        return {
            "mean": pick("mean"),
            "std_dev": pick("stdDev"),
            "p05": pick("p5"),
            "p10": pick("p10"),
            "p25": pick("p25"),
            "p50": pick("p50"),
            "p75": pick("p75"),
            "p90": pick("p90"),
            "p95": pick("p95"),
            "count": int(count) if count is not None else None,
        }

    def _make(self, name, value, status, window, dataset, scale, direction,
              valid_observations, stats, notes=""):
        spec = get_indicator_spec(name)
        stats = stats or {}
        return MetricResult(
            metric=name,
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
            direction=direction,
            evidence_tier=spec.evidence_tier,
            reference_type=spec.reference_type,
            reference_allowed=spec.reference_allowed,
            score_eligible=False,
            valid_observations=valid_observations,
            valid_pixels=stats.get("count"),
            std_dev=stats.get("std_dev"),
            p05=stats.get("p05"),
            p10=stats.get("p10"),
            p25=stats.get("p25"),
            p50=stats.get("p50"),
            p75=stats.get("p75"),
            p90=stats.get("p90"),
            p95=stats.get("p95"),
            notes=notes,
        )

    def run(self, geometry, start, end):
        import ee

        s2 = self._s2(geometry, start, end)
        s2_n = int(s2.size().getInfo())
        dw_collection = (
            ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
            .filterBounds(geometry)
            .filterDate(start, end)
            .select("label")
        )
        dw_n = int(dw_collection.size().getInfo())

        if dw_n < 1:
            return [
                self._make(name, None, "insufficient_data", f"{start}:{end}", dataset, scale, direction, s2_n if name == "terrestrial_ndvi" else dw_n, None,
                           notes="Dynamic World observations were unavailable for the configured period." if name != "terrestrial_ndvi" else "No Sentinel-2 observations met the configured cloud filter.")
                for name, dataset, scale, direction in [
                    ("natural_landcover_fraction", "GOOGLE/DYNAMICWORLD/V1", 10, "higher_is_better"),
                    ("terrestrial_ndvi", "COPERNICUS/S2_SR_HARMONIZED", 10, "higher_is_better"),
                    ("built_fraction", "GOOGLE/DYNAMICWORLD/V1", 10, "lower_is_better"),
                ]
            ]

        dw = dw_collection.mode()
        natural = dw.eq(1).Or(dw.eq(2)).Or(dw.eq(3)).Or(dw.eq(5)).Or(dw.eq(7)).rename("fraction")
        built = dw.eq(6).rename("fraction")
        natural_stats = self._stats(natural, geometry, "fraction", 10)
        built_stats = self._stats(built, geometry, "fraction", 10)

        if s2_n < 1:
            ndvi_stats = None
            ndvi_value = None
            ndvi_status = "insufficient_data"
        else:
            land_mask = dw.neq(0)
            ndvi = s2.median().normalizedDifference(["B8", "B4"]).rename("ndvi").updateMask(land_mask)
            ndvi_stats = self._stats(ndvi, geometry, "ndvi", 10)
            ndvi_value = ndvi_stats["mean"]
            ndvi_status = "ok" if ndvi_value is not None else "insufficient_land_or_data"

        window = f"{start}:{end}"
        return [
            self._make("natural_landcover_fraction", natural_stats["mean"], "ok" if natural_stats["mean"] is not None else "insufficient_data", window,
                       "GOOGLE/DYNAMICWORLD/V1", 10, "higher_is_better", dw_n, natural_stats,
                       "Natural/semi-natural land-cover fraction; EO screening proxy. Dynamic World modal label is used over the configured period."),
            self._make("terrestrial_ndvi", ndvi_value, ndvi_status, window,
                       "COPERNICUS/S2_SR_HARMONIZED + Dynamic World land mask", 10, "higher_is_better", s2_n, ndvi_stats,
                       "Terrestrial NDVI condition proxy, masked to Dynamic World non-water land classes."),
            self._make("built_fraction", built_stats["mean"], "ok" if built_stats["mean"] is not None else "insufficient_data", window,
                       "GOOGLE/DYNAMICWORLD/V1", 10, "lower_is_better", dw_n, built_stats,
                       "Built-up fraction is a land-use pressure proxy."),
        ]
