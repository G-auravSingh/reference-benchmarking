"""Dynamic water detection using current Earth Engine surface-water inputs.

Primary method: Dynamic World water probability / class. Fallback: Sentinel-1 VV
threshold when optical observations are insufficient. No manually drawn water masks.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


@dataclass
class WaterPeriodResult:
    period_start: str
    period_end: str
    images_used: int
    method: str
    water_fraction_mean: Optional[float]
    water_area_ha_mean: Optional[float]
    water_area_ha_max: Optional[float]
    water_area_ha_min: Optional[float]

    def to_dict(self):
        return asdict(self)


class WaterDetector:
    def __init__(self, config):
        self.config = config

    def _dw(self, geometry, start: str, end: str):
        import ee
        return (
            ee.ImageCollection(self.config.water.primary_dataset)
            .filterBounds(geometry)
            .filterDate(start, end)
        )

    def _s1(self, geometry, start: str, end: str):
        import ee
        return (
            ee.ImageCollection(self.config.water.fallback_dataset)
            .filterBounds(geometry)
            .filterDate(start, end)
            .filter(ee.Filter.eq("instrumentMode", "IW"))
            .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
            .select("VV")
        )

    def water_mask_for_period(self, geometry, start: str, end: str):
        import ee
        dw = self._dw(geometry, start, end)
        n = int(dw.size().getInfo())
        if n >= self.config.water.min_primary_images:
            # Dynamic World: class 0 is water. Mean probability gives a stable composite.
            p = dw.select("water").mean()
            return p.gte(self.config.water.primary_probability_threshold).rename("water"), "dynamic_world", n
        if not self.config.water.fallback_enabled:
            return ee.Image(0).selfMask().rename("water"), "none", n
        s1 = self._s1(geometry, start, end)
        n1 = int(s1.size().getInfo())
        if n1 < 1:
            return ee.Image(0).selfMask().rename("water"), "none", n
        vv = s1.mean()
        return vv.lt(self.config.water.fallback_vv_threshold_db).rename("water"), "sentinel1_vv", n1

    def area_summary(self, geometry, start: str, end: str) -> Dict[str, Any]:
        import ee
        boundary_area = ee.Image.pixelArea().reduceRegion(
            reducer=ee.Reducer.sum(), geometry=geometry, scale=10, maxPixels=1e8, bestEffort=True
        ).get("area")
        boundary_area_ha = ee.Number(boundary_area).divide(1e4)

        mask, method, n = self.water_mask_for_period(geometry, start, end)
        water_area = ee.Image.pixelArea().updateMask(mask)
        stats = water_area.reduceRegion(
            reducer=ee.Reducer.sum(), geometry=geometry, scale=10, maxPixels=1e8, bestEffort=True
        ).get("area")
        water_ha = ee.Number(stats).divide(1e4)
        fraction = water_ha.divide(boundary_area_ha).multiply(100.0)
        return {
            "period_start": start,
            "period_end": end,
            "images_used": n,
            "method": method,
            "water_area_ha": water_ha.getInfo(),
            "boundary_area_ha": boundary_area_ha.getInfo(),
            "water_fraction_pct": fraction.getInfo(),
        }

    def observation_occurrence(self, geometry, start: str, end: str):
        """Pixel-wise occurrence of Dynamic World water class over valid observations."""
        import ee
        dw = self._dw(geometry, start, end)
        n = int(dw.size().getInfo())
        if n >= 1:
            occ = dw.select("label").map(lambda img: img.eq(0).rename("water")).mean()
            return occ.rename("water_occurrence"), "dynamic_world", n
        return ee.Image(0).rename("water_occurrence").updateMask(ee.Image(0)), "none", 0

    def persistence(self, geometry, start: str, end: str) -> Dict[str, Any]:
        import ee
        occ, method, n = self.observation_occurrence(geometry, start, end)
        value = occ.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=geometry, scale=10, maxPixels=1e8, bestEffort=True
        ).get("water_occurrence")
        return {
            "period_start": start,
            "period_end": end,
            "method": method,
            "n_images": n,
            "water_occurrence_fraction": value.getInfo() if value is not None else None,
        }

    def period_metrics(self, geometry, periods: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        return [self.area_summary(geometry, p["start"], p["end"]) for p in periods]
