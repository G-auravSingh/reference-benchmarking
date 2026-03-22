"""
Reference Selector
==================

Implements two tiers of ecoregion-specific reference benchmarking:

Tier 1 — Global Modelled Reference
    Extract indicator values from pre-computed global raster layers (GLOBIO4,
    BII, EII, SEED, etc.) at the site and across its ecoregion.
    Reference = ecoregion-wide statistics (mean, median, percentiles).

Tier 2 — Contemporary Reference (SEED-style)
    Identify the top 5% least-disturbed pixels within the same ecoregion ×
    land-cover combination using the Global Human Modification Index.
    Extract indicator values from those reference pixels and compute
    reference statistics.

    This follows the methodology of:
    - McElderry et al. (2024). EcoEvoRxiv. DOI:10.32942/X2689N
      "Reference areas representing the 5% least disturbed areas within each
      combination of ecoregion and land cover type."
    - McNellie et al. (2020). Global Change Biology, 26(12), 6702–6714.
      DOI:10.1111/gcb.15383  (Contemporary reference state framework)
    - Yen et al. (2019). Ecological Applications, 29(7), e01970.
      DOI:10.1002/eap.1970  (Upper-quantile benchmarks in variable environments)

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

    # Tier 1: global modelled reference (ecoregion-wide)
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
    tier1_intactness: Optional[float] = None  # site / tier1_reference
    tier2_intactness: Optional[float] = None  # site / tier2_reference

    metadata: Dict[str, Any] = field(default_factory=dict)


class ReferenceSelector:
    """
    Compute Tier 1 and Tier 2 reference benchmarks for any indicator.

    Usage::

        selector = ReferenceSelector(config)
        result = selector.compute(
            indicator_spec=registry.get("ndvi"),
            site_geometry=site_geom,
            site_id="dumka_0001",
            eco_id=60401,
            eco_geometry=eco_geom,
        )
    """

    # GEE asset IDs for key layers
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
        site_geometry,  # shapely geometry or ee.Geometry
        site_id: str,
        eco_id: int,
        eco_geometry=None,  # ee.Geometry or shapely geometry
    ) -> ReferenceResult:
        """
        Compute site value + Tier 1 + Tier 2 references for one indicator at one site.

        Parameters
        ----------
        indicator_spec : IndicatorSpec
            The indicator to compute.
        site_geometry : shapely.geometry or ee.Geometry
            The project site boundary.
        site_id : str
            Unique site identifier.
        eco_id : int
            WWF Ecoregion ECO_ID for this site.
        eco_geometry : ee.Geometry or shapely.geometry, optional
            Ecoregion boundary (needed for Tier 1/2 regional extraction).

        Returns
        -------
        ReferenceResult
        """
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
            logger.debug(
                f"  {indicator_spec.name} @ {site_id}: site_value={result.site_value}"
            )
        except Exception as e:
            logger.error(
                f"Failed to extract {indicator_spec.name} for {site_id}: {e}"
            )
            return result

        # --- Step 2: Tier 1 - Ecoregion-wide reference ---
        if eco_geometry is not None:
            try:
                tier1 = self._compute_tier1(indicator_spec, eco_geometry)
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

        # --- Step 3: Tier 2 - Contemporary reference ---
        if indicator_spec.tier2_eligible and eco_geometry is not None:
            try:
                tier2 = self._compute_tier2(
                    indicator_spec, site_geometry, eco_id, eco_geometry
                )
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

    def _compute_tier1(
        self, spec: IndicatorSpec, eco_geometry
    ) -> Dict[str, Any]:
        """
        Extract ecoregion-wide statistics for Tier 1 reference.

        For GEE-based indicators: reduce across ecoregion geometry.
        For local rasters: use rasterio zonal stats.
        """
        if spec.source_type == "gee" and spec.tier1_layer:
            return self._tier1_gee(spec, eco_geometry)
        elif spec.source_type == "local_raster" and spec.tier1_layer:
            return self._tier1_local(spec, eco_geometry)
        else:
            # Use the extract_fn on the ecoregion geometry for a sample
            extraction = spec.extract_fn(eco_geometry, self.config)
            if isinstance(extraction, dict) and "pixels" in extraction:
                arr = np.array(extraction["pixels"])
                return self._array_stats(arr)
            return {}

    def _tier1_gee(self, spec: IndicatorSpec, eco_geometry) -> Dict[str, Any]:
        """Extract Tier 1 stats from a GEE image across the ecoregion."""
        self._ensure_gee()
        import ee

        # Convert shapely to ee.Geometry if needed
        if not isinstance(eco_geometry, ee.Geometry):
            eco_geometry = self._shapely_to_ee(eco_geometry)

        # Get image from the indicator's tier1_layer
        image = self._get_gee_image(spec)
        if image is None:
            return {}

        # Compute percentile reducer
        stats = image.reduceRegion(
            reducer=(
                ee.Reducer.mean()
                .combine(ee.Reducer.median(), sharedInputs=True)
                .combine(ee.Reducer.stdDev(), sharedInputs=True)
                .combine(ee.Reducer.percentile([25, 75, 90]), sharedInputs=True)
                .combine(ee.Reducer.count(), sharedInputs=True)
            ),
            geometry=eco_geometry,
            scale=1000,  # 1km for efficiency on large ecoregions
            maxPixels=1e9,
            bestEffort=True,
        ).getInfo()

        # Parse the flat dict from GEE (band_reducer format)
        return self._parse_gee_stats(stats)

    def _tier1_local(self, spec: IndicatorSpec, eco_geometry) -> Dict[str, Any]:
        """Extract Tier 1 stats from a local raster using rasterio."""
        import rasterio
        from rasterio.mask import mask as rio_mask
        from shapely.geometry import mapping

        with rasterio.open(spec.tier1_layer) as src:
            # Mask raster to ecoregion
            geom_json = [mapping(eco_geometry)]
            try:
                out_image, _ = rio_mask(src, geom_json, crop=True, nodata=src.nodata)
                arr = out_image[0]  # first band
                if src.nodata is not None:
                    arr = arr[arr != src.nodata]
                arr = arr[np.isfinite(arr)]
                return self._array_stats(arr)
            except Exception as e:
                logger.warning(f"Local raster extraction failed: {e}")
                return {}

    def _compute_tier2(
        self,
        spec: IndicatorSpec,
        site_geometry,
        eco_id: int,
        eco_geometry,
    ) -> Dict[str, Any]:
        """
        Tier 2: Contemporary reference from least-disturbed patches.

        Algorithm (following SEED framework, McElderry et al. 2024):
        1. Buffer the site centroid by config.reference_buffer_km
        2. Intersect buffer with ecoregion boundary
        3. Get land cover class at site location
        4. Within the intersection, find pixels with the same land cover class
        5. Rank by HMI; select bottom config.hmi_percentile_threshold %
        6. Extract indicator values from those reference pixels
        7. Return statistics
        """
        self._ensure_gee()
        import ee

        # Convert geometries
        if not isinstance(eco_geometry, ee.Geometry):
            eco_geometry = self._shapely_to_ee(eco_geometry)
        if not isinstance(site_geometry, ee.Geometry):
            site_geometry = self._shapely_to_ee(site_geometry)

        # Step 1: Buffer around site centroid
        buffer_m = self.config.reference_buffer_km * 1000
        site_centroid = site_geometry.centroid()
        search_area = site_centroid.buffer(buffer_m)

        # Step 2: Intersect with ecoregion
        reference_zone = search_area.intersection(eco_geometry)

        # Step 3: Get land cover at site
        lc = ee.Image(self.config.landcover_gee_asset).select("discrete_classification")
        site_lc = lc.reduceRegion(
            reducer=ee.Reducer.mode(),
            geometry=site_geometry,
            scale=100,
            maxPixels=1e6,
        ).getInfo()

        lc_value = None
        for v in site_lc.values():
            if v is not None:
                lc_value = v
                break

        # Step 4-5: Mask to same land cover + select least disturbed
        ghm = ee.ImageCollection(self.GHM_ASSET).first().select("gHM")

        # Create combined mask: same ecoregion region + same land cover
        if lc_value is not None:
            lc_mask = lc.eq(ee.Number(lc_value))
        else:
            # If we can't determine land cover, skip LC stratification
            lc_mask = ee.Image.constant(1)
            logger.warning(
                f"Could not determine land cover for site; "
                f"using ecoregion-only reference"
            )

        # Get HMI within reference zone, masked to same land cover
        ghm_masked = ghm.updateMask(lc_mask).clip(reference_zone)

        # Compute the HMI percentile threshold
        threshold_stats = ghm_masked.reduceRegion(
            reducer=ee.Reducer.percentile([self.config.hmi_percentile_threshold]),
            geometry=reference_zone,
            scale=1000,
            maxPixels=1e9,
            bestEffort=True,
        ).getInfo()

        hmi_threshold = None
        for v in threshold_stats.values():
            if v is not None:
                hmi_threshold = v
                break

        if hmi_threshold is None:
            logger.warning("Could not compute HMI threshold for Tier 2")
            return {}

        # Step 6: Create reference mask (pixels below HMI threshold)
        ref_mask = ghm_masked.lte(ee.Number(hmi_threshold))

        # Get the indicator image
        indicator_image = self._get_gee_image(spec)
        if indicator_image is None:
            # Try extracting via the extract function with the reference zone
            return {}

        # Mask indicator to reference pixels only
        indicator_ref = indicator_image.updateMask(ref_mask).clip(reference_zone)

        # Extract statistics
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
            maxPixels=1e9,
            bestEffort=True,
        ).getInfo()

        result = self._parse_gee_stats(stats)

        if result.get("n", 0) < self.config.min_reference_pixels:
            logger.warning(
                f"Tier 2: Only {result.get('n', 0)} reference pixels found "
                f"(min={self.config.min_reference_pixels}). "
                f"Consider increasing buffer or HMI threshold."
            )

        return result

    # --- Helpers ---

    def _get_gee_image(self, spec: IndicatorSpec):
        """Get or construct the GEE image for an indicator."""
        import ee

        layer = spec.tier1_layer
        if layer is None:
            return None

        # Check if there's a custom builder function (preferred)
        if "gee_image_fn" in spec.metadata:
            return spec.metadata["gee_image_fn"](self.config)

        # Try as ImageCollection first (most GEE assets are collections),
        # then fall back to single Image
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

        # Strip Z coordinates — GEE rejects 3D geometries
        if geom.has_z:
            geom = shapely_transform(lambda x, y, z=None: (x, y), geom)

        geojson = mapping(geom)

        # GEE needs coordinates as 'type' + 'coordinates'; remove extra keys
        return ee.Geometry(geojson)

    @staticmethod
    def _array_stats(arr: np.ndarray) -> Dict[str, Any]:
        """Compute standard statistics from a numpy array."""
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
