"""Dynamic water detection and period summaries for aquatic assessments."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass
class WaterPeriodResult:
    period_start: str
    period_end: str
    period_end_inclusive: Optional[str]
    images_used: int
    method: str
    water_area_ha: Optional[float]
    boundary_area_ha: Optional[float]
    water_fraction_pct: Optional[float]
    occurrence_fraction: Optional[float] = None
    water_present: Optional[bool] = None
    status: str = "ok"
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class WaterDetector:
    """Primary Dynamic World detection with Sentinel-1 majority fallback."""

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
            .filter(
                ee.Filter.listContains(
                    "transmitterReceiverPolarisation",
                    "VV",
                )
            )
            .select("VV")
        )

    @staticmethod
    def _size(collection) -> int:
        return int(collection.size().getInfo())

    def water_mask_for_period(self, geometry, start: str, end: str):
        import ee

        dw = self._dw(geometry, start, end)
        n = self._size(dw)

        if n >= self.config.water.min_primary_images:
            probability = dw.select("water").mean()

            mask = probability.gte(
                self.config.water.primary_probability_threshold
            ).rename("water")

            return mask, "dynamic_world_probability", n

        if not self.config.water.fallback_enabled:
            return (
                ee.Image(0).selfMask().rename("water"),
                "none",
                n,
            )

        s1 = self._s1(geometry, start, end)
        n1 = self._size(s1)

        if n1 < 1:
            return (
                ee.Image(0).selfMask().rename("water"),
                "none",
                0,
            )

        detections = s1.map(
            lambda img: ee.Image(img).lt(
                self.config.water.fallback_vv_threshold_db
            ).rename("water")
        )

        occurrence = detections.mean()

        mask = occurrence.gte(
            self.config.water.fallback_majority_fraction
        ).rename("water")

        return mask, "sentinel1_vv_majority", n1

    def occurrence_image(self, geometry, start: str, end: str):
        """Return per-pixel water occurrence from the best available sensor."""
        import ee

        dw = self._dw(geometry, start, end)
        n = self._size(dw)

        if n >= 1:
            occurrence = (
                dw.select("label")
                .map(
                    lambda img: ee.Image(img).eq(0).rename("water")
                )
                .mean()
                .rename("water_occurrence")
            )

            return occurrence, "dynamic_world_label", n

        if self.config.water.fallback_enabled:
            s1 = self._s1(geometry, start, end)
            n1 = self._size(s1)

            if n1 >= 1:
                occurrence = (
                    s1.map(
                        lambda img: ee.Image(img).lt(
                            self.config.water.fallback_vv_threshold_db
                        ).rename("water")
                    )
                    .mean()
                    .rename("water_occurrence")
                )

                return occurrence, "sentinel1_vv", n1

        return (
            ee.Image(0)
            .selfMask()
            .rename("water_occurrence"),
            "none",
            0,
        )

    def _area(self, geometry, mask, scale=10) -> Optional[float]:
        import ee

        value = (
            ee.Image.pixelArea()
            .updateMask(mask)
            .reduceRegion(
                reducer=ee.Reducer.sum(),
                geometry=geometry,
                scale=scale,
                maxPixels=1e8,
                bestEffort=True,
            )
            .get("area")
        )

        # Earth Engine can return a computed null value when
        # there are no valid pixels.
        if value is None:
            return None

        value = value.getInfo()

        if value is None:
            return None

        return float(value / 1e4)

    @staticmethod
    def _evaluate_number(value) -> Optional[float]:
        """
        Safely evaluate an Earth Engine scalar.

        Returns None when Earth Engine returns no valid value.
        """
        if value is None:
            return None

        result = value.getInfo()

        if result is None:
            return None

        return float(result)

    def area_summary(
        self,
        geometry,
        start: str,
        end: str,
    ) -> Dict[str, Any]:
        import ee
        from datetime import date, timedelta

        boundary_area = self._area(
            geometry,
            ee.Image(1).selfMask(),
            10,
        )

        mask, method, n = self.water_mask_for_period(
            geometry,
            start,
            end,
        )

        water_ha = self._area(
            geometry,
            mask,
            10,
        )

        fraction = (
            None
            if water_ha is None
            or boundary_area is None
            or boundary_area == 0
            else water_ha / boundary_area * 100.0
        )

        occurrence, _, _ = self.occurrence_image(
            geometry,
            start,
            end,
        )

        occurrence_value = occurrence.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geometry,
            scale=10,
            maxPixels=1e8,
            bestEffort=True,
        ).get("water_occurrence")

        occurrence_value = self._evaluate_number(
            occurrence_value
        )

        status = (
            "ok"
            if water_ha is not None
            else "insufficient_data"
        )

        period_end_inclusive = None

        if end:
            period_end_inclusive = (
                date.fromisoformat(end) - timedelta(days=1)
            ).isoformat()

        return WaterPeriodResult(
            period_start=start,
            period_end=end,
            period_end_inclusive=period_end_inclusive,
            images_used=n,
            method=method,
            water_area_ha=water_ha,
            boundary_area_ha=boundary_area,
            water_fraction_pct=fraction,
            occurrence_fraction=occurrence_value,
            water_present=(
                fraction is not None
                and fraction
                >= self.config.water.water_presence_area_fraction_threshold
            ),
            status=status,
            notes=(
                "Water extent is descriptive and must be compared "
                "using the same seasonal/temporal window."
            ),
        ).to_dict()

    def persistence(
        self,
        geometry,
        start: str,
        end: str,
    ) -> Dict[str, Any]:
        import ee

        occurrence, method, n = self.occurrence_image(
            geometry,
            start,
            end,
        )

        value = occurrence.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geometry,
            scale=10,
            maxPixels=1e8,
            bestEffort=True,
        ).get("water_occurrence")

        value = self._evaluate_number(value)

        return {
            "period_start": start,
            "period_end": end,
            "method": method,
            "n_images": n,
            "water_occurrence_fraction": value,
            "status": (
                "ok"
                if value is not None
                else "insufficient_data"
            ),
        }

    def period_metrics(
        self,
        geometry,
        periods: List[Dict[str, str]],
    ) -> List[Dict[str, Any]]:
        return [
            self.area_summary(
                geometry,
                p["start"],
                p["end"],
            )
            for p in periods
        ]
