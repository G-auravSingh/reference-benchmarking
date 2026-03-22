"""
Reference Selector
==================

Implements two tiers of ecoregion-specific reference benchmarking:

Tier 1 — Global Modelled Reference
    Extract indicator values from pre-computed global raster layers (GLOBIO4,
    BII, EII, SEED, etc.) within a regional buffer around the site.
    Reference = regional statistics (mean, median, percentiles).

Tier 2 — Contemporary Reference (SEED-style)
    Identify the top 5% least-disturbed pixels within the same land-cover type
    in a buffer around the site, using the Global Human Modification Index.

    This follows the methodology of:
    - McElderry et al. (2024). EcoEvoRxiv. DOI:10.32942/X2689N
    - McNellie et al. (2020). Global Change Biology, 26(12), 6702–6714.
      DOI:10.1111/gcb.15383
    - Yen et al. (2019). Ecological Applications, 29(7), e01970.
      DOI:10.1002/eap.1970

Human Modification Index
    Kennedy, C.M., Oakleaf, J.R., Theobald, D.M., et al. (2019).
    Global Change Biology, 25(3), 811–826. DOI:10.1111/gcb.14549
    GEE: CSP/HM/GlobalHumanModification (1 km, 0–1 scale)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from darukaa_reference.config import Config
from darukaa_reference.registry import IndicatorSpec

logger = logging.getLogger(__name__)


@dataclass
class ReferenceResult:
    """Reference statistics for a single indicator at a single site."""

    indicator_name: str
    site_id: str
    eco_id: Optional[int] = None

    # Site value
    site_value: Optional[float] = None
    site_pixels: Optional[np.ndarray] = None

    # Tier 1: global modelled reference (regional buffer)
    tier1_mean: Optional[float] = None
    tier1_median: Optional[float] = None
    tier1_std: Optional[float] = None
    tier1_p25: Optional[float] = None
    tier1_p75: Optional[float] = None
    tier1_p90: Optional[float] = None
    tier1_n_pixels: int = 0

    # Tier 2: contemporary reference (least-disturbed patches)
    tier2_mean: Optional[float] = None
    tier2_median: Optional[float] = None
    tier2_std: Optional[float] = None
    tier2_p25: Optional[float] = None
    tier2_p75: Optional[float] = None
    tier2_p90: Optional[float] = None
    tier2_n_pixels: int = 0
    tier2_pixels: Optional[np.ndarray] = None

    # Intactness ratios
    tier1_intactness: Optional[float] = None
    tier2_intactness: Optional[float] = None

    metadata: Dict[str, Any] = field(default_factory=dict)


class ReferenceSelector:
    """
    Compute Tier 1 and Tier 2 reference benchmarks for any indicator.
    """

    GHM_ASSET = "CSP/HM/GlobalHumanModification"
    LANDCOVER_ASSET = "COPERNICUS/Landcover/100m/Proba-V-C3/Global/2019"

    def __init__(self, config: Config):
        self.config = config
        self._gee_initialised = False

    def _ensure_gee(self):
        """Lazy-init GEE only when needed."""
        if not self._gee_initialised:
            import ee
            if self.config.gee_service_account and self.config.gee_key_path:
                credentials = ee.ServiceAccountCredentials(
                    self.config.gee_service_account, self.config.gee_key_path
                )
                ee.Initialize(credentials, project=self.config.gee_project)
            else:
                ee.Initialize(project=self.config.gee_project or None)
            self._gee_initialised = True

    def compute(
        self,
        indicator_spec: IndicatorSpec,
        site_geometry,
        site_id: str,
        eco_id: int,
        eco_geometry=None,
    ) -> ReferenceResult:
        """Compute site value + Tier 1 + Tier 2 references for one indicator."""
        result = ReferenceResult(
            indicator_name=indicator_spec.name,
            site_id=site_id,
            eco_id=eco_id,
        )

        # --- Step 1: Extract site value ---
        try:
            extraction = indicator_spec.extract_fn(site_geometry, self.config)
            if isinstance(extraction, dict):
                result.site_value = extraction.get("value")
                result.site_pixels = extraction.get("pixels")
            else:
                result.site_value = float(extraction)
        except Exception as e:
            logger.error(f"Failed to extract {indicator_spec.name} for {site_id}: {e}")
            return result

        # --- Step 2: Tier 1 — Regional reference (buffer around site) ---
        try:
            tier1 = self._compute_tier1(indicator_spec, site_geometry)
            result.tier1_mean = tier1.get("mean")
            result.tier1_median = tier1.get("median")
            result.tier1_std = tier1.get("std")
            result.tier1_p25 = tier1.get("p25")
            result.tier1_p75 = tier1.get("p75")
            result.tier1_p90 = tier1.get("p90")
            result.tier1_n_pixels = tier1.get("n", 0)

            if result.site_value is not None and result.tier1_median:
                result.tier1_intactness = min(
                    result.site_value / result.tier1_median, 1.0
                )
        except Exception as e:
            logger.warning(f"Tier 1 failed for {indicator_spec.name}: {e}")

        # --- Step 3: Tier 2 — Contemporary reference ---
        if indicator_spec.tier2_eligible:
            try:
                tier2 = self._compute_tier2(indicator_spec, site_geometry, eco_id)
                result.tier2_mean = tier2.get("mean")
                result.tier2_median = tier2.get("median")
                result.tier2_std = tier2.get("std")
                result.tier2_p25 = tier2.get("p25")
                result.tier2_p75 = tier2.get("p75")
                result.tier2_p90 = tier2.get("p90")
                result.tier2_n_pixels = tier2.get("n", 0)
                result.tier2_pixels = tier2.get("pixels")

                if result.site_value is not None and result.tier2_median:
                    result.tier2_intactness = min(
                        result.site_value / result.tier2_median, 1.0
                    )
            except Exception as e:
                logger.warning(f"Tier 2 failed for {indicator_spec.name}: {e}")

        return result

    # ------------------------------------------------------------------
    # Tier 1: Regional reference within buffer
    # ------------------------------------------------------------------

    def _compute_tier1(self, spec: IndicatorSpec, site_geometry) -> Dict[str, Any]:
        """
        Extract Tier 1 reference stats within a buffer around the site.

        Uses config.reference_buffer_km as the radius. This avoids the
        problem of reducing over entire ecoregions which timeout in GEE.
        """
        self._ensure_gee()
        import ee

        if not isinstance(site_geometry, ee.Geometry):
            site_geometry = self._shapely_to_ee(site_geometry)

        buffer_m = self.config.reference_buffer_km * 1000
        region = site_geometry.centroid().buffer(buffer_m)

        # Get indicator image — try gee_image_fn first, then tier1_layer
        image = self._get_indicator_image(spec)
        if image is None:
            return {}

        stats = image.reduceRegion(
            reducer=(
                ee.Reducer.mean()
                .combine(ee.Reducer.median(), sharedInputs=True)
                .combine(ee.Reducer.stdDev(), sharedInputs=True)
                .combine(ee.Reducer.percentile([25, 75, 90]), sharedInputs=True)
                .combine(ee.Reducer.count(), sharedInputs=True)
            ),
            geometry=region,
            scale=1000,
            maxPixels=1e9,
            bestEffort=True,
        ).getInfo()

        return self._parse_gee_stats(stats)

    # ------------------------------------------------------------------
    # Tier 2: Contemporary reference (SEED-style least-disturbed patches)
    # ------------------------------------------------------------------

    def _compute_tier2(
        self, spec: IndicatorSpec, site_geometry, eco_id: int
    ) -> Dict[str, Any]:
        """
        Tier 2: Select the top 5% least-disturbed pixels within the
        same land-cover class in a buffer around the site.

        KEY DESIGN: We use the buffer directly — NOT the full ecoregion
        geometry. GEE ecoregion polygons can have millions of vertices
        and cause computation timeouts. Since the site is already within
        its ecoregion, the buffer is a valid proxy for the local landscape.
        """
        self._ensure_gee()
        import ee

        if not isinstance(site_geometry, ee.Geometry):
            site_geometry = self._shapely_to_ee(site_geometry)

        # Step 1: Reference zone = buffer around site centroid
        buffer_m = self.config.reference_buffer_km * 1000
        reference_zone = site_geometry.centroid().buffer(buffer_m)

        # Step 2: Get land cover at site
        lc = ee.Image(self.config.landcover_gee_asset).select("discrete_classification")
        site_lc = lc.reduceRegion(
            reducer=ee.Reducer.mode(),
            geometry=site_geometry,
            scale=100,
            maxPixels=1e6,
        ).getInfo()

        lc_value = None
        for v in (site_lc or {}).values():
            if v is not None:
                lc_value = v
                break

        # Step 3: Load gHM within reference zone
        ghm = ee.ImageCollection(self.GHM_ASSET).first().select("gHM")

        if lc_value is not None:
            lc_mask = lc.eq(ee.Number(lc_value))
            ghm_in_zone = ghm.updateMask(lc_mask).clip(reference_zone)
            logger.debug(f"  Tier 2: land cover = {lc_value}")
        else:
            logger.warning("Could not determine land cover; using buffer-only reference")
            ghm_in_zone = ghm.clip(reference_zone)

        # Step 4: Compute HMI percentile threshold
        threshold_stats = ghm_in_zone.reduceRegion(
            reducer=ee.Reducer.percentile([self.config.hmi_percentile_threshold]),
            geometry=reference_zone,
            scale=1000,
            maxPixels=1e8,
            bestEffort=True,
        ).getInfo()

        hmi_threshold = None
        for v in (threshold_stats or {}).values():
            if v is not None:
                hmi_threshold = v
                break

        # Fallback: retry without land cover mask
        if hmi_threshold is None and lc_value is not None:
            logger.info("  Tier 2: retrying without land cover mask...")
            ghm_in_zone = ghm.clip(reference_zone)
            threshold_stats = ghm_in_zone.reduceRegion(
                reducer=ee.Reducer.percentile([self.config.hmi_percentile_threshold]),
                geometry=reference_zone,
                scale=1000,
                maxPixels=1e8,
                bestEffort=True,
            ).getInfo()
            for v in (threshold_stats or {}).values():
                if v is not None:
                    hmi_threshold = v
                    break

        if hmi_threshold is None:
            logger.warning("Could not compute HMI threshold for Tier 2")
            return {}

        logger.info(
            f"  Tier 2 HMI threshold (p{self.config.hmi_percentile_threshold}): "
            f"{hmi_threshold:.4f}"
        )

        # Step 5: Mask to reference pixels (HMI <= threshold)
        ref_mask = ghm_in_zone.lte(ee.Number(hmi_threshold))

        # Get indicator image
        indicator_image = self._get_indicator_image(spec)
        if indicator_image is None:
            return {}

        indicator_ref = indicator_image.updateMask(ref_mask).clip(reference_zone)

        # Step 6: Extract statistics from reference pixels
        stats = indicator_ref.reduceRegion(
            reducer=(
                ee.Reducer.mean()
                .combine(ee.Reducer.median(), sharedInputs=True)
                .combine(ee.Reducer.stdDev(), sharedInputs=True)
                .combine(ee.Reducer.percentile([25, 75, 90]), sharedInputs=True)
                .combine(ee.Reducer.count(), sharedInputs=True)
            ),
            geometry=reference_zone,
            scale=1000,
            maxPixels=1e8,
            bestEffort=True,
        ).getInfo()

        result = self._parse_gee_stats(stats)

        n_ref = result.get("n", 0)
        if n_ref < self.config.min_reference_pixels:
            logger.warning(
                f"Tier 2: Only {n_ref} reference pixels "
                f"(min={self.config.min_reference_pixels})"
            )
        else:
            logger.info(f"  Tier 2: {n_ref} reference pixels selected")

        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_indicator_image(self, spec: IndicatorSpec):
        """
        Get the GEE image for an indicator.

        Priority: gee_image_fn (custom builder) > tier1_layer (asset ID).
        """
        import ee

        # 1. Custom builder function (preferred — handles composite indicators)
        if "gee_image_fn" in spec.metadata:
            return spec.metadata["gee_image_fn"](self.config)

        # 2. Tier 1 layer asset ID
        layer = spec.tier1_layer
        if layer is None:
            return None

        try:
            return ee.ImageCollection(layer).mosaic()
        except Exception:
            try:
                return ee.Image(layer)
            except Exception:
                return None

    def _shapely_to_ee(self, geom) -> "ee.Geometry":
        """Convert a shapely geometry to ee.Geometry, stripping Z coords."""
        import ee
        from shapely.geometry import mapping
        from shapely.ops import transform as shapely_transform

        if geom.has_z:
            geom = shapely_transform(lambda x, y, z=None: (x, y), geom)
        geojson = mapping(geom)
        return ee.Geometry(geojson)

    @staticmethod
    def _array_stats(arr: np.ndarray) -> Dict[str, Any]:
        """Compute standard statistics from a numpy array."""
        if arr is None:
            return {}
        arr = np.atleast_1d(arr)
        if len(arr) == 0:
            return {}
        return {
            "mean": float(np.nanmean(arr)),
            "median": float(np.nanmedian(arr)),
            "std": float(np.nanstd(arr)),
            "p25": float(np.nanpercentile(arr, 25)),
            "p75": float(np.nanpercentile(arr, 75)),
            "p90": float(np.nanpercentile(arr, 90)),
            "n": int(np.sum(np.isfinite(arr))),
            "pixels": arr,
        }

    @staticmethod
    def _parse_gee_stats(stats: Dict) -> Dict[str, Any]:
        """Parse the flat dict returned by GEE multi-reducer."""
        if not stats:
            return {}

        result = {}
        for key, val in stats.items():
            if val is None:
                continue
            key_lower = key.lower()
            if "mean" in key_lower:
                result["mean"] = val
            elif "median" in key_lower:
                result["median"] = val
            elif "stddev" in key_lower or "stdDev" in key:
                result["std"] = val
            elif "p25" in key_lower or "_25" in key:
                result["p25"] = val
            elif "p75" in key_lower or "_75" in key:
                result["p75"] = val
            elif "p90" in key_lower or "_90" in key:
                result["p90"] = val
            elif "count" in key_lower:
                result["n"] = int(val)

        return result
