"""Generalized terrestrial Earth-observation metrics."""
from __future__ import annotations

from dataclasses import asdict
from typing import Dict, Optional

from .metrics import MetricResult, _window_label
from .registry import get_indicator_spec


class TerrestrialMetrics:
    def __init__(self, config):
        self.config = config

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
    def _size(col):
        return int(col.size().getInfo())

    @staticmethod
    def _sample(image, geometry, scale=10, n=3000, seed=123):
        import ee
        fc = image.rename("value").sample(region=geometry, scale=scale, numPixels=n, seed=seed, geometries=False)
        vals = fc.aggregate_array("value").getInfo() or []
        vals = [float(x) for x in vals if x is not None]
        return vals

    def _make(self, metric, value, status, start, end, dataset, scale, observations=None, notes=""):
        spec = get_indicator_spec(metric)
        return MetricResult(metric, spec.pillar, spec.construct, spec.subdimension, spec.domain,
                            value, spec.units, status, _window_label(start, end), dataset, scale,
                            spec.direction, spec.evidence_tier, spec.reference_type,
                            spec.reference_allowed, False, observations, None, None, None, None, notes)

    def natural_habitat_fraction(self, geometry, start, end):
        import ee
        dw = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(geometry).filterDate(start, end)
        n = self._size(dw)
        if n == 0:
            return self._make("natural_habitat_fraction", None, "insufficient_data", start, end, "GOOGLE/DYNAMICWORLD/V1", 10, 0)
        label = dw.select("label").mode()
        natural = label.eq(1).Or(label.eq(2)).Or(label.eq(3)).Or(label.eq(5)).rename("natural")
        value = natural.reduceRegion(ee.Reducer.mean(), geometry, 10, maxPixels=1e8, bestEffort=True).get("natural")
        value = None if value is None else value.getInfo()
        return self._make("natural_habitat_fraction", None if value is None else float(value), "ok" if value is not None else "insufficient_data", start, end, "GOOGLE/DYNAMICWORLD/V1", 10, n,
                          "Natural habitat classes: trees, grass, flooded vegetation, shrub/scrub. Built/crops are treated as modified; water is excluded from the natural-land cover fraction.")

    def vegetation_ndvi(self, geometry, start, end):
        import ee
        s2 = self._s2(geometry, start, end)
        n = self._size(s2)
        if n == 0:
            return self._make("vegetation_ndvi", None, "insufficient_data", start, end, "COPERNICUS/S2_SR_HARMONIZED", 10, 0)
        ndvi = s2.map(lambda img: ee.Image(img).normalizedDifference(["B8", "B4"]).rename("NDVI")).median()
        label = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(geometry).filterDate(start, end).select("label").mode()
        natural = label.eq(1).Or(label.eq(2)).Or(label.eq(3)).Or(label.eq(5))
        img = ndvi.updateMask(natural)
        value = img.reduceRegion(ee.Reducer.mean(), geometry, 10, maxPixels=1e8, bestEffort=True).get("NDVI")
        value = None if value is None else value.getInfo()
        return self._make("vegetation_ndvi", None if value is None else float(value), "ok" if value is not None else "insufficient_data", start, end, "COPERNICUS/S2_SR_HARMONIZED + Dynamic World", 10, n,
                          "NDVI median composite masked to natural vegetation classes; contextual vegetation QA remains available in the raw raster outputs.")

    def habitat_connectivity_proxy(self, geometry, start, end):
        import ee
        label = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(geometry).filterDate(start, end).select("label").mode()
        natural = label.eq(1).Or(label.eq(2)).Or(label.eq(3)).Or(label.eq(5)).rename("natural")
        # Focal mean is a local connected-neighbour proxy, not a graph-theoretic connectivity index.
        connectivity = natural.focal_mean(radius=100, units="meters").rename("connectivity")
        value = connectivity.reduceRegion(ee.Reducer.mean(), geometry, 10, maxPixels=1e8, bestEffort=True).get("connectivity")
        value = None if value is None else value.getInfo()
        return self._make("habitat_connectivity_proxy", None if value is None else float(value), "ok" if value is not None else "insufficient_data", start, end, "GOOGLE/DYNAMICWORLD/V1", 10,
                          self._size(ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(geometry).filterDate(start, end)),
                          "Local 100 m neighbourhood natural-cover mean; a connectivity proxy rather than a formal landscape graph metric.")

    def built_up_fraction(self, geometry, start, end):
        import ee
        dw = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(geometry).filterDate(start, end)
        n = self._size(dw)
        if n == 0:
            return self._make("built_up_fraction", None, "insufficient_data", start, end, "GOOGLE/DYNAMICWORLD/V1", 10, 0)
        built = dw.select("built").mean().rename("built")
        value = built.reduceRegion(ee.Reducer.mean(), geometry, 10, maxPixels=1e8, bestEffort=True).get("built")
        value = None if value is None else value.getInfo()
        return self._make("built_up_fraction", None if value is None else float(value), "ok" if value is not None else "insufficient_data", start, end, "GOOGLE/DYNAMICWORLD/V1", 10, n,
                          "Mean Dynamic World built probability; interpreted as land-use pressure only after reference comparison.")

    def human_modification(self, geometry, start, end):
        import ee
        image = ee.Image(self.config.reference.human_modification_dataset)
        value = image.reduceRegion(ee.Reducer.mean(), geometry, 100, maxPixels=1e8, bestEffort=True).get("gHM")
        value = None if value is None else value.getInfo()
        return self._make("human_modification", None if value is None else float(value), "ok" if value is not None else "insufficient_data", start, end,
                          self.config.reference.human_modification_dataset, 100, None,
                          f"Global Human Modification mean; reference selection uses a {self.config.reference.human_modification_threshold:.2f} least-modified filter where available.")

    def run(self, geometry, start, end):
        return [
            self.natural_habitat_fraction(geometry, start, end),
            self.vegetation_ndvi(geometry, start, end),
            self.habitat_connectivity_proxy(geometry, start, end),
            self.built_up_fraction(geometry, start, end),
            self.human_modification(geometry, start, end),
        ]
