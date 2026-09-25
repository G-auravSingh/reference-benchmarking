"""Aquatic/lake metric calculations with explicit spatial domains and provenance."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


@dataclass
class MetricResult:
    metric: str
    pillar: str
    domain: str
    value: Optional[float]
    units: str
    status: str
    temporal_window: str
    dataset: str
    scale_m: int
    direction: str
    score_eligible: bool
    valid_observations: Optional[int] = None
    notes: str = ""

    def to_dict(self):
        return asdict(self)


class LakeMetrics:
    """Metrics are deliberately kept interpretable and domain-specific.

    Metrics without validated ecological thresholds are returned as raw proxies and
    are not automatically included in a composite State-of-Nature score.
    """
    def __init__(self, config, water_detector):
        self.config = config
        self.water = water_detector

    def _s2(self, geometry, start, end):
        import ee
        def mask(img):
            scl = img.select("SCL")
            good = (scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11)))
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
            .filterBounds(geometry).filterDate(start, end).select("label").mode()
        )

    def _reduce(self, image, geometry, scale=10):
        import ee
        out = image.reduceRegion(
            reducer=ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True),
            geometry=geometry, scale=scale, maxPixels=1e8, bestEffort=True,
        ).getInfo() or {}
        mean = None; count = None
        for k, v in out.items():
            lk = k.lower()
            if "mean" in lk and v is not None: mean = float(v)
            if "count" in lk and v is not None: count = int(v)
        return mean, count

    def _make(self, metric, pillar, domain, value, units, status, window, dataset, scale,
              direction="none", score_eligible=False, valid_observations=None, notes=""):
        return MetricResult(metric, pillar, domain, value, units, status, window, dataset, scale,
                            direction, score_eligible, valid_observations, notes)

    def water_extent(self, geometry, start, end):
        r = self.water.area_summary(geometry, start, end)
        return self._make("water_extent", "P1_ecosystem_extent", "dynamic_water",
                          r["water_fraction_pct"], "% of master boundary", "ok" if r["water_fraction_pct"] is not None else "insufficient_data",
                          f"{start}:{end}", r["method"], 10, "context_dependent", False, r["images_used"],
                          "Dynamic surface-water extent; not treated as inherently better/worse because hydroperiod is system-specific.")

    def water_persistence(self, geometry, start, end):
        r = self.water.persistence(geometry, start, end)
        return self._make("water_persistence", "P1_ecosystem_extent", "master_boundary",
                          r["water_occurrence_fraction"], "fraction", "ok" if r["water_occurrence_fraction"] is not None else "insufficient_data",
                          f"{start}:{end}", r["method"], 10, "higher_is_more_persistent", False, r["n_images"],
                          "Fraction of valid Dynamic World observations classified as water at each pixel, spatially averaged.")

    def ndci(self, geometry, start, end):
        import ee
        s2 = self._s2(geometry, start, end)
        if int(s2.size().getInfo()) == 0:
            return self._make("ndci_proxy", "P2_ecosystem_condition", "dynamic_water", None, "NDCI", "insufficient_data",
                              f"{start}:{end}", "COPERNICUS/S2_SR_HARMONIZED", 20, "lower_is_better", False, 0)
        comp = s2.median()
        wm, method, _ = self.water.water_mask_for_period(geometry, start, end)
        img = comp.normalizedDifference(["B5", "B4"]).updateMask(wm)
        value, count = self._reduce(img, geometry, 20)
        return self._make("ndci_proxy", "P2_ecosystem_condition", "dynamic_water", value, "NDCI", "ok" if value is not None else "insufficient_water_or_data",
                          f"{start}:{end}", "COPERNICUS/S2_SR_HARMONIZED + " + method, 20, "lower_is_better", False, count,
                          "Chlorophyll/trophic proxy. Raw value only; site- and water-type calibration is required before ecological threshold scoring.")

    def turbidity_proxy(self, geometry, start, end):
        import ee
        s2 = self._s2(geometry, start, end)
        if int(s2.size().getInfo()) == 0:
            return self._make("red_reflectance_turbidity_proxy", "P2_ecosystem_condition", "dynamic_water", None, "unitless", "insufficient_data",
                              f"{start}:{end}", "COPERNICUS/S2_SR_HARMONIZED", 20, "lower_is_better", False, 0)
        comp=s2.median(); wm, method, _ = self.water.water_mask_for_period(geometry, start, end)
        img=comp.select("B4").updateMask(wm)
        value,count=self._reduce(img,geometry,20)
        return self._make("red_reflectance_turbidity_proxy", "P2_ecosystem_condition", "dynamic_water", value, "surface reflectance", "ok" if value is not None else "insufficient_water_or_data",
                          f"{start}:{end}", "COPERNICUS/S2_SR_HARMONIZED + " + method, 20, "lower_is_better", False, count,
                          "Water-masked red-band proxy. Do not interpret as calibrated turbidity without field/sensor validation.")

    def bloom_frequency(self, geometry, start, end):
        import ee
        s2=self._s2(geometry,start,end)
        n=int(s2.size().getInfo())
        if n==0:
            return self._make("surface_algal_bloom_frequency", "P2_ecosystem_condition", "dynamic_water", None, "fraction", "insufficient_data",
                              f"{start}:{end}", "COPERNICUS/S2_SR_HARMONIZED", 20, "lower_is_better", False, 0)
        wm, method, _=self.water.water_mask_for_period(geometry,start,end)
        def fai(img):
            red=img.select("B4"); nir=img.select("B8"); swir=img.select("B11")
            baseline=red.add(swir.subtract(red).multiply((842-665)/(1610-665)))
            return nir.subtract(baseline).rename("FAI").copyProperties(img,["system:time_start"])
        blooms=s2.map(fai).map(lambda img: img.gt(self.config.water.fai_bloom_threshold).rename("bloom").updateMask(wm))
        frac=blooms.mean()
        value,count=self._reduce(frac,geometry,20)
        return self._make("surface_algal_bloom_frequency", "P2_ecosystem_condition", "dynamic_water", value, "fraction", "ok" if value is not None else "insufficient_water_or_data",
                          f"{start}:{end}", "COPERNICUS/S2_SR_HARMONIZED + " + method, 20, "lower_is_better", False, count,
                          f"FAI bloom-proxy frequency using configurable threshold {self.config.water.fai_bloom_threshold}; threshold requires validation.")

    def shoreline_disturbance(self, riparian_zone, start, end):
        import ee
        dw=self._dw_label_mode(riparian_zone,start,end)
        disturb=dw.eq(4).Or(dw.eq(6)).Or(dw.eq(7))  # crops, built, bare
        value,count=self._reduce(disturb,riparian_zone,10)
        return self._make("shoreline_disturbance_fraction", "P2_ecosystem_condition", "fixed_riparian_100m", value, "fraction", "ok" if value is not None else "insufficient_data",
                          f"{start}:{end}", "GOOGLE/DYNAMICWORLD/V1", 10, "lower_is_better", False, count,
                          "Share of standardized 100 m fixed riparian ring mapped as crops, built area, or bare ground. Contextual pressure metric; not automatically scored.")

    def landcover_composition(self, geometry, start, end):
        import ee
        dw=self._dw_label_mode(geometry,start,end)
        labels=list(range(9)); result={}
        for cls in labels:
            mask=dw.eq(cls)
            _,count=self._reduce(mask,geometry,10)
            # Because a boolean selfMask has mean = fraction of true pixels.
            value,_=self._reduce(mask,geometry,10)
            result[str(cls)] = value
        return result

    def riparian_ndvi_trend(self, riparian_zone, start_year, end_year):
        """Annual seasonal median NDVI; Sen slope + Mann-Kendall p computed client-side."""
        import ee
        import numpy as np
        from scipy.stats import kendalltau, theilslopes
        years=[]; values=[]; image_counts=[]
        months=set(self.config.temporal.monitoring_months)
        for y in range(start_year,end_year+1):
            start=f"{y}-01-01"; end=f"{y}-12-31"
            # Use full calendar year unless monitoring_months is a subset.
            s2=self._s2(riparian_zone,start,end)
            if months != set(range(1,13)):
                def add_month(img):
                    return img.set("month", img.date().get("month"))
                s2=s2.map(add_month).filter(ee.Filter.inList("month", list(months)))
            n=int(s2.size().getInfo())
            if n==0:
                continue
            ndvi=s2.map(lambda img: img.normalizedDifference(["B8","B4"]).rename("NDVI")).median()
            v,cnt=self._reduce(ndvi,riparian_zone,10)
            if v is not None:
                years.append(y); values.append(v); image_counts.append(n)
        if len(values)<self.config.temporal.min_years_for_trend:
            return self._make("riparian_ndvi_sen_slope", "P2_ecosystem_condition", "fixed_riparian_100m", None, "NDVI/year", "insufficient_temporal_depth",
                              f"{start_year}:{end_year}", "COPERNICUS/S2_SR_HARMONIZED", 10, "higher_is_better", False, len(values),
                              f"Only {len(values)} years with usable annual composites; minimum {self.config.temporal.min_years_for_trend}.")
        slope,_,_,_=theilslopes(values,years)
        p=float(kendalltau(years,values).pvalue)
        return self._make("riparian_ndvi_sen_slope", "P2_ecosystem_condition", "fixed_riparian_100m", float(slope), "NDVI/year", "ok",
                          f"{start_year}:{end_year}", "COPERNICUS/S2_SR_HARMONIZED", 10, "higher_is_better", False, len(values),
                          f"Robust Sen/Theil slope across {len(values)} annual seasonal composites; Mann-Kendall/Kendall tau p={p:.4g}. Raw trend statistic, not a claim of ecological causation.")

    def run(self, boundary, riparian_zone, baseline_window: tuple[int,int] | None = None) -> list[MetricResult]:
        y=end=self.config.temporal.end_year
        if baseline_window is None:
            start_year=self.config.temporal.start_year
        else:
            start_year=baseline_window[0]; end=baseline_window[1]
        start=f"{start_year}-01-01"; end_date=f"{end+1}-01-01"
        out=[
            self.water_extent(boundary,start,end_date),
            self.water_persistence(boundary,start,end_date),
            self.ndci(boundary,start,end_date),
            self.turbidity_proxy(boundary,start,end_date),
            self.bloom_frequency(boundary,start,end_date),
            self.shoreline_disturbance(riparian_zone,start,end_date),
            self.riparian_ndvi_trend(riparian_zone,start_year,end),
        ]
        return out
