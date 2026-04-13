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
                result.tier1_intactness = self._intactness_ratio(
                    result.site_value, result.tier1_median, indicator_spec.higher_is_better
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
                    result.tier2_intactness = self._intactness_ratio(
                        result.site_value, result.tier2_median, indicator_spec.higher_is_better
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

        Priority: local raster (if available) > GEE.
        This ensures indicators like BII that have both a local raster AND
        a GEE fallback always use the authoritative local source for
        reference computation.
        """
        radius_km = spec.reference_radius_km or self.config.reference_buffer_km

        # Priority 1: Local raster (regardless of source_type)
        # An indicator like BII may be registered as source_type="gee" for
        # site extraction (which tries GEE then falls back to local), but
        # if a local raster exists, Tier 1 reference should use it for
        # methodological consistency.
        raster_path = self._get_local_raster_path(spec)
        if raster_path:
            result = self._tier1_from_local_raster(
                raster_path, site_geometry, radius_km, spec
            )
            if result:
                return result

        # Route: GEE-based indicators
        self._ensure_gee()
        import ee

        if not isinstance(site_geometry, ee.Geometry):
            site_geometry = self._shapely_to_ee(site_geometry)

        buffer_m = radius_km * 1000
        region = site_geometry.centroid().buffer(buffer_m)

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

    def _tier1_from_local_raster(
        self, raster_path: str, site_geometry, radius_km: float, spec: IndicatorSpec
    ) -> Dict[str, Any]:
        """
        Compute Tier 1 reference from a local raster by reading a circular
        buffer region.

        This is the preferred approach for coarse global rasters (BII ~10km,
        GLOBIO4 MSA ~300m, SEED ~1km) because:
        1. Methodological consistency — same data source for site and reference
        2. Self-contained — no GEE access needed for the indicator itself
        3. Works regardless of GEE asset availability

        Reference: Uses the same "regional buffer" approach as the GEE path,
        but reads directly from the authoritative raster (e.g., PREDICTS-based
        BII from NHM, GLOBIO4 MSA from PBL).
        """
        import rasterio
        from rasterio.mask import mask as rio_mask
        from shapely.geometry import mapping
        from shapely.ops import transform as shapely_transform
        import pyproj

        # Ensure 2D geometry
        if hasattr(site_geometry, 'has_z') and site_geometry.has_z:
            site_geometry = shapely_transform(lambda x, y, z=None: (x, y), site_geometry)

        centroid = site_geometry.centroid

        # Create circular buffer in metres, then reproject to WGS84
        # Use UTM zone for accurate buffering
        utm_zone = int((centroid.x + 180) / 6) + 1
        hemisphere = 'north' if centroid.y >= 0 else 'south'
        utm_crs = pyproj.CRS(f"+proj=utm +zone={utm_zone} +{hemisphere} +datum=WGS84")
        wgs84 = pyproj.CRS("EPSG:4326")

        project_to_utm = pyproj.Transformer.from_crs(wgs84, utm_crs, always_xy=True).transform
        project_to_wgs = pyproj.Transformer.from_crs(utm_crs, wgs84, always_xy=True).transform

        centroid_utm = shapely_transform(project_to_utm, centroid)
        buffer_utm = centroid_utm.buffer(radius_km * 1000)
        buffer_wgs = shapely_transform(project_to_wgs, buffer_utm)

        # Determine scale factor for this indicator
        scale_factor = 1.0
        if spec.name == "bii":
            scale_factor = 0.01  # NHM BII stores 0–100, we need 0–1

        with rasterio.open(raster_path) as src:
            geom_json = [mapping(buffer_wgs)]
            try:
                out_image, _ = rio_mask(src, geom_json, crop=True, nodata=src.nodata)
                arr = out_image[0].flatten()
                arr = arr[np.isfinite(arr)]
                if src.nodata is not None and not np.isnan(src.nodata):
                    arr = arr[arr != src.nodata]
                if len(arr) == 0:
                    return {}
                arr = arr * scale_factor
                logger.info(
                    f"  Tier 1 (local raster): {len(arr)} pixels in "
                    f"{radius_km}km buffer, median={np.median(arr):.4f}"
                )
                return self._array_stats(arr)
            except Exception as e:
                logger.warning(f"Tier 1 local raster extraction failed: {e}")
                return {}

    def _get_local_raster_path(self, spec: IndicatorSpec) -> str:
        """Resolve the local raster path for an indicator."""
        # Map indicator names to config raster_paths keys
        name_to_key = {
            "bii": "bii",
            "msa_globio4": "globio4_msa",
            "seed": "seed_biocomplexity",
        }
        key = name_to_key.get(spec.name)
        if key:
            path = self.config.raster_paths.get(key)
            if path and __import__("os").path.exists(path):
                return path
        return None

    # ------------------------------------------------------------------
    # Tier 2: Contemporary reference (SEED-style least-disturbed patches)
    # ------------------------------------------------------------------

    def _compute_tier2(
        self, spec: IndicatorSpec, site_geometry, eco_id: int
    ) -> Dict[str, Any]:
        """
        Tier 2: Select the least-disturbed reference pixels using a
        SEED-adapted dynamic threshold with three-way stratification.

        Adapted from McElderry et al. (2024) SEED biocomplexity framework
        Supplement S1.1, with elevation stratification added:

        1. Buffer the site centroid by per-indicator reference_radius_km
        2. Get land cover class and elevation at site location
        3. Within the buffer, mask to pixels with:
           a) Same land cover class (Copernicus LC, 100m)
           b) Within ±elevation_band_m of site elevation (SRTM 30m)
        4. Compute DYNAMIC HMI threshold (SEED Equation S1):
           - P5 = 5th percentile, P3 = 3rd percentile of HMI in zone
           - If P5 ≤ ceiling (0.05) → threshold = P5
           - If P5 > ceiling but P3 ≤ ceiling → threshold = P3
           - If both > ceiling → threshold = ceiling
           This ensures truly minimal disturbance in reference areas.
        5. Select pixels with HMI ≤ threshold
        6. If fewer than min_reference_pixels (default 5, per SEED):
           → Fallback 1: Drop land cover mask, keep elevation + buffer
           → Fallback 2: Expand to full ecoregion geometry
        7. Extract indicator statistics from reference pixels

        References:
            McElderry, R.M. et al. (2024). SEED framework. EcoEvoRxiv.
                DOI:10.32942/X2689N. Supplement S1.1.
            McNellie, M.J. et al. (2020). Contemporary reference states.
                GCB, 26(12). DOI:10.1111/gcb.15383
            Farr, T.G. et al. (2007). SRTM. DOI:10.1029/2005RG000183
        """
        self._ensure_gee()
        import ee

        if not isinstance(site_geometry, ee.Geometry):
            site_geometry = self._shapely_to_ee(site_geometry)

        # Step 1: Reference zone = buffer around site centroid
        radius_km = spec.reference_radius_km or self.config.reference_buffer_km
        buffer_m = radius_km * 1000
        reference_zone = site_geometry.centroid().buffer(buffer_m)

        # Step 2a: Get land cover at site
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

        # Step 2b: Get elevation at site (SRTM 30m DEM)
        srtm = ee.Image(self.config.srtm_gee_asset).select("elevation")
        site_elev = srtm.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=site_geometry,
            scale=30,
            maxPixels=1e6,
        ).getInfo()

        elev_value = None
        for v in (site_elev or {}).values():
            if v is not None:
                elev_value = v
                break

        # Step 3: Build stratification masks (kept separate for fallback)
        ghm_raw = ee.ImageCollection(self.GHM_ASSET).first().select("gHM")
        masks_applied = []

        lc_mask = None
        if lc_value is not None:
            lc_mask = lc.eq(ee.Number(lc_value))
            masks_applied.append(f"LC={lc_value}")

        elev_mask = None
        if elev_value is not None:
            elev_band = self.config.elevation_band_m
            elev_min = elev_value - elev_band
            elev_max = elev_value + elev_band
            elev_mask = srtm.gte(ee.Number(elev_min)).And(srtm.lte(ee.Number(elev_max)))
            masks_applied.append(f"elev={elev_value:.0f}m±{elev_band:.0f}m")
        else:
            logger.warning("  Could not determine site elevation; skipping elevation filter")

        # Apply all masks
        ghm = ghm_raw
        if lc_mask is not None:
            ghm = ghm.updateMask(lc_mask)
        if elev_mask is not None:
            ghm = ghm.updateMask(elev_mask)
        ghm_in_zone = ghm.clip(reference_zone)
        logger.info(f"  Tier 2 stratification: {', '.join(masks_applied) or 'none'}")

        # Step 4: SEED-adapted dynamic HMI threshold
        hmi_ceiling = getattr(self.config, "hmi_hard_ceiling", 0.05)
        indicator_image = self._get_indicator_image(spec)
        if indicator_image is None:
            return {}

        # Try primary zone (full stratification)
        hmi_threshold = self._dynamic_hmi_threshold(ghm_in_zone, reference_zone, hmi_ceiling)
        if hmi_threshold is not None:
            result = self._extract_tier2_stats(
                ghm_in_zone, hmi_threshold, indicator_image, reference_zone
            )
            n_ref = result.get("n", 0)
            if n_ref >= self.config.min_reference_pixels:
                logger.info(
                    f"  Tier 2: {n_ref} ref pixels, HMI ≤ {hmi_threshold:.4f} "
                    f"(ceiling={hmi_ceiling})"
                )
                return result
            logger.info(f"  Tier 2: {n_ref} pixels < {self.config.min_reference_pixels}, "
                        f"trying fallbacks...")

        # Fallback 1: Drop land cover, keep elevation + buffer
        if lc_value is not None:
            logger.info("  Tier 2 fallback 1: dropping land cover mask...")
            ghm_fb1 = ghm_raw
            if elev_mask is not None:
                ghm_fb1 = ghm_fb1.updateMask(elev_mask)
            ghm_fb1 = ghm_fb1.clip(reference_zone)
            t_fb1 = self._dynamic_hmi_threshold(ghm_fb1, reference_zone, hmi_ceiling)
            if t_fb1 is not None:
                result = self._extract_tier2_stats(
                    ghm_fb1, t_fb1, indicator_image, reference_zone
                )
                if result.get("n", 0) >= self.config.min_reference_pixels:
                    logger.info(f"  Tier 2 fallback 1: {result['n']} pixels (no LC mask)")
                    return result

        # Fallback 2: Progressive buffer widening (more reliable than ecoregion geometry)
        for multiplier in [2.0, 3.0, 4.0]:
            wider_km = radius_km * multiplier
            if wider_km > 200:
                break
            logger.info(f"  Tier 2 fallback 2: widening buffer to {wider_km}km...")
            wider_zone = site_geometry.centroid().buffer(wider_km * 1000)
            ghm_wider = ghm_raw
            if elev_mask is not None:
                ghm_wider = ghm_wider.updateMask(elev_mask)
            if lc_mask is not None:
                ghm_wider = ghm_wider.updateMask(lc_mask)
            ghm_wider = ghm_wider.clip(wider_zone)
            t_wider = self._dynamic_hmi_threshold(ghm_wider, wider_zone, hmi_ceiling)
            if t_wider is not None:
                result = self._extract_tier2_stats(
                    ghm_wider, t_wider, indicator_image, wider_zone
                )
                if result.get("n", 0) >= self.config.min_reference_pixels:
                    logger.info(f"  Tier 2 fallback 2: {result['n']} pixels at {wider_km}km")
                    return result

    def _dynamic_hmi_threshold(self, ghm_image, geometry, ceiling: float) -> float:
        """
        SEED Equation S1 — dynamic HMI threshold.

        For each zone, compute P5 and P3 of HMI:
          If P5 ≤ ceiling → use P5 (restrictive, pristine ecoregion)
          If P5 > ceiling but P3 ≤ ceiling → use P3 (step down)
          If both > ceiling → use ceiling (degraded ecoregion, hard cap)

        Returns threshold or None if computation fails.
        """
        import ee
        try:
            stats = ghm_image.reduceRegion(
                reducer=ee.Reducer.percentile([3, 5]),
                geometry=geometry,
                scale=1000,
                maxPixels=1e8,
                bestEffort=True,
            ).getInfo()
        except Exception:
            return None

        if not stats:
            return None

        # Parse P5 and P3 from GEE stats dict
        p5 = p3 = None
        for k, v in stats.items():
            if v is None:
                continue
            kl = k.lower()
            if "p5" in kl or kl.endswith("_5"):
                p5 = v
            elif "p3" in kl or kl.endswith("_3"):
                p3 = v

        # If both None, try any value
        if p5 is None and p3 is None:
            for v in stats.values():
                if v is not None:
                    return min(v, ceiling)
            return None

        # SEED decision tree
        if p5 is not None and p5 <= ceiling:
            return p5
        if p3 is not None and p3 <= ceiling:
            return p3
        return ceiling

    def _extract_tier2_stats(
        self, ghm_in_zone, hmi_threshold, indicator_image, geometry
    ) -> Dict[str, Any]:
        """Extract indicator stats from reference pixels (HMI ≤ threshold)."""
        import ee
        ref_mask = ghm_in_zone.lte(ee.Number(hmi_threshold))
        indicator_ref = indicator_image.updateMask(ref_mask).clip(geometry)

        stats = indicator_ref.reduceRegion(
            reducer=(
                ee.Reducer.mean()
                .combine(ee.Reducer.median(), sharedInputs=True)
                .combine(ee.Reducer.stdDev(), sharedInputs=True)
                .combine(ee.Reducer.percentile([25, 75, 90]), sharedInputs=True)
                .combine(ee.Reducer.count(), sharedInputs=True)
            ),
            geometry=geometry,
            scale=1000,
            maxPixels=1e8,
            bestEffort=True,
        ).getInfo()

        return self._parse_gee_stats(stats)


    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _intactness_ratio(
        site_value: float, reference_value: float, higher_is_better: bool
    ) -> float:
        """
        Compute intactness ratio, accounting for indicator directionality.

        For STATE indicators (NDVI, BII, EII — higher_is_better=True):
            intactness = site / reference, capped at 1.0
            A site at 0.6 with reference 0.8 → 75% intactness

        For PRESSURE indicators (gHM, LST, noise — higher_is_better=False):
            intactness = reference / site, capped at 1.0
            A site at 0.34 gHM with reference 0.23 → 68% intactness
            (site has more human modification = lower intactness)

        Both return 0–1 where 1.0 = equivalent to reference condition.
        """
        if reference_value == 0 or site_value == 0:
            return None

        if higher_is_better:
            return min(site_value / reference_value, 1.0)
        else:
            return min(reference_value / site_value, 1.0)

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
