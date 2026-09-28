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

import time
from contextlib import contextmanager

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import numpy as np

from darukaa_reference.config import Config
from darukaa_reference.registry import IndicatorSpec
from darukaa_reference import estimators

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
    tier1_mad: Optional[float] = None  # real median(|x-median|), NOT std -- see benchmark() fix
    tier1_p25: Optional[float] = None
    tier1_p75: Optional[float] = None
    tier1_p90: Optional[float] = None
    tier1_n_pixels: int = 0

    # Tier 2: contemporary reference (least-disturbed patches)
    tier2_mean: Optional[float] = None
    tier2_median: Optional[float] = None
    tier2_std: Optional[float] = None
    tier2_mad: Optional[float] = None  # real median(|x-median|), NOT std -- see benchmark() fix
    tier2_p25: Optional[float] = None
    tier2_p75: Optional[float] = None
    tier2_p90: Optional[float] = None
    tier2_n_pixels: int = 0
    tier2_pixels: Optional[np.ndarray] = None

    # Intactness ratios (LEGACY, capped at 1.0 — DEPRECATED, display/back-compat only;
    # scoring should consume the responsive benchmark fields below).
    tier1_intactness: Optional[float] = None
    tier2_intactness: Optional[float] = None

    # Responsive benchmark (v0.2.0, CS-3) — signed & UNCAPPED so restoration
    # gains above reference remain visible. Estimator chosen by measurement scale.
    tier1_benchmark: Optional[float] = None        # signed value (>0 = better than ref)
    tier2_benchmark: Optional[float] = None
    tier1_benchmark_estimator: Optional[str] = None
    tier2_benchmark_estimator: Optional[str] = None
    tier2_percentile_in_reference: Optional[float] = None
    tier2_display_pct_of_reference: Optional[float] = None  # UNCAPPED, display only
    tier2_low_dispersion_warning: bool = False  # real audit-requested flag -- see estimators.benchmark()
    reference_type: Optional[str] = None            # honesty label (see IndicatorSpec)
    reference_hmi_realised: Optional[float] = None   # realised HMI threshold used (SEED transparency)
    # v0.2.0 (post-audit): stratification diagnostics — which mode ran, which masks
    # applied, land-cover class before/after PNV correction, stability check outcome.
    # This is what makes a live run's JSON report self-sufficient for validation: no
    # separate diagnostic export is needed, everything is in the standard report.
    stratification_diagnostics: Dict[str, Any] = field(default_factory=dict)
    # Tier 1 reference-sampling diagnostics (Tier 2's live in stratification_diagnostics).
    tier1_sampling_diagnostics: Dict[str, Any] = field(default_factory=dict)

    metadata: Dict[str, Any] = field(default_factory=dict)
    extraction_metadata: Dict[str, Any] = field(default_factory=dict)
    # extraction_metadata: populated from extract_fn return dict["metadata"]
    # Contains species lists for biodiversity indicators (threatened_richness,
    # ceri, endemic_richness). Not all indicators populate this field.


# Process-wide timing log (every ReferenceSelector appends here) so a notebook can summarise
# a whole run without needing a handle on each per-tile selector.
TIMING_LOG: list = []


def reference_stats_from_values(values) -> Dict[str, Any]:
    """Reference statistics computed from SAMPLED native-resolution values (pure numpy --
    no GEE, directly unit-testable). MAD is the true median(|x - median|) of the sampled
    values (NOT SD, NOT a coarsened image). Returns {} when there are no finite values."""
    x = np.asarray([v for v in np.atleast_1d(values).ravel() if v is not None], dtype=float)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return {}
    med = float(np.median(x))
    return {
        "mean": float(np.mean(x)),
        "median": med,
        "std": float(np.std(x, ddof=1)) if x.size > 1 else 0.0,
        "mad": float(np.median(np.abs(x - med))),
        "p25": float(np.percentile(x, 25)),
        "p75": float(np.percentile(x, 75)),
        "p90": float(np.percentile(x, 90)),
        "n": int(x.size),
        "pixels": x,
    }


class ReferenceSelector:
    """
    Compute Tier 1 and Tier 2 reference benchmarks for any indicator.
    """

    GHM_ASSET = "CSP/HM/GlobalHumanModification"  # DEPRECATED default; see config.hmi_gee_asset
    LANDCOVER_ASSET = "COPERNICUS/Landcover/100m/Proba-V-C3/Global/2019"  # legacy-mode only
    # NOTE (v0.2.0): both constants are retained only as historical markers. The actual
    # assets used at runtime come from Config (hmi_gee_asset, seed_landcover_gee_asset,
    # landcover_gee_asset) — see config.py for the current defaults and rationale.

    def __init__(self, config: Config):
        self.config = config
        self._gee_initialised = False
        self.timing_log: list = []          # one dict per timed stage (see _log_timing)
        self._timing_ctx = ("?", "?")       # (site_id, indicator) for the current compute()

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

        self._timing_ctx = (site_id, indicator_spec.name)
        # --- Step 1: Extract site value ---
        try:
            with self._timed("site_extraction"):
                extraction = indicator_spec.extract_fn(site_geometry, self.config)
            if isinstance(extraction, dict):
                result.site_value = extraction.get("value")
                result.site_pixels = extraction.get("pixels")
                # Capture species lists and other indicator-level metadata
                if "metadata" in extraction and isinstance(extraction["metadata"], dict):
                    result.extraction_metadata = extraction["metadata"]
            else:
                result.site_value = float(extraction)
        except Exception as e:
            logger.error(f"Failed to extract {indicator_spec.name} for {site_id}: {e}")
            return result

        # --- Step 2: Tier 1 — Regional reference (buffer around site) ---
        try:
            with self._timed("tier1_reference") as _t1:
                tier1 = self._compute_tier1(indicator_spec, site_geometry)
                _t1["n"] = tier1.get("n")
            result.tier1_sampling_diagnostics = tier1.get("sampling_diagnostics") or {}
            result.tier1_mean = tier1.get("mean")
            result.tier1_median = tier1.get("median")
            result.tier1_std = tier1.get("std")
            result.tier1_mad = tier1.get("mad")
            result.tier1_p25 = tier1.get("p25")
            result.tier1_p75 = tier1.get("p75")
            result.tier1_p90 = tier1.get("p90")
            result.tier1_n_pixels = tier1.get("n", 0)

            if result.site_value is not None and result.tier1_median:
                # Legacy capped ratio (deprecated) retained for back-compat/display.
                result.tier1_intactness = self._intactness_ratio(
                    result.site_value, result.tier1_median, indicator_spec.higher_is_better
                )
                # Responsive, scale-aware benchmark (CS-3) — the value scoring should use.
                _tb1 = time.perf_counter()
                _b1 = estimators.benchmark(
                    site_value=result.site_value,
                    reference_median=result.tier1_median,
                    reference_mad=result.tier1_mad,
                    measurement_scale=getattr(indicator_spec, "measurement_scale", None),
                    reference_estimator=getattr(indicator_spec, "reference_estimator", None),
                    higher_is_better=indicator_spec.higher_is_better,
                )
                self._log_timing("benchmark_calculation_tier1", time.perf_counter() - _tb1, None)
                result.tier1_benchmark = _b1["value"]
                result.tier1_benchmark_estimator = _b1["estimator"]
        except Exception as e:
            logger.warning(f"Tier 1 failed for {indicator_spec.name}: {e}")

        # --- Step 3: Tier 2 — Contemporary reference ---
        if indicator_spec.tier2_eligible:
            try:
                with self._timed("tier2_reference") as _t2:
                    tier2 = self._compute_tier2(indicator_spec, site_geometry, eco_id)
                    _t2["n"] = tier2.get("n")
                result.tier2_mean = tier2.get("mean")
                result.tier2_median = tier2.get("median")
                result.tier2_std = tier2.get("std")
                result.tier2_mad = tier2.get("mad")
                result.tier2_p25 = tier2.get("p25")
                result.tier2_p75 = tier2.get("p75")
                result.tier2_p90 = tier2.get("p90")
                result.tier2_n_pixels = tier2.get("n", 0)
                result.tier2_pixels = tier2.get("pixels")
                result.reference_hmi_realised = tier2.get("hmi_realised")
                result.stratification_diagnostics = tier2.get("stratification_diagnostics", {})
                _sd = tier2.get("sampling_diagnostics")
                if _sd:
                    result.stratification_diagnostics = {
                        **(result.stratification_diagnostics or {}), **_sd,
                        "reference_population_definition": self._tier2_population_definition(
                            result.stratification_diagnostics or {}, tier2.get("hmi_realised")),
                    }
                if tier2.get("stability"):
                    result.stratification_diagnostics = {
                        **(result.stratification_diagnostics or {}), "reference_stability": tier2["stability"]}
                if tier2.get("suppressed_reason"):
                    result.stratification_diagnostics = {
                        **result.stratification_diagnostics, "suppressed_reason": tier2["suppressed_reason"]}
                # Real, audit-requested technical metadata: the actual reduceRegion
                # scale used for this indicator's reference, so a reviewer can see
                # whether a coarse fallback scale was used rather than the real
                # native resolution.
                if tier2.get("effective_scale_m") is not None:
                    result.stratification_diagnostics = {
                        **result.stratification_diagnostics, "effective_scale_m": tier2["effective_scale_m"]}

                if result.site_value is not None and result.tier2_median:
                    # Legacy capped ratio (deprecated) retained for back-compat/display.
                    result.tier2_intactness = self._intactness_ratio(
                        result.site_value, result.tier2_median, indicator_spec.higher_is_better
                    )
                    # Responsive, scale-aware benchmark (CS-3).
                    _ref_vals = None
                    if result.tier2_pixels is not None:
                        _ref_vals = np.atleast_1d(result.tier2_pixels).ravel().tolist()
                    _tb2 = time.perf_counter()
                    _b2 = estimators.benchmark(
                        site_value=result.site_value,
                        reference_median=result.tier2_median,
                        reference_mad=result.tier2_mad,
                        reference_values=_ref_vals,
                        measurement_scale=getattr(indicator_spec, "measurement_scale", None),
                        reference_estimator=getattr(indicator_spec, "reference_estimator", None),
                        higher_is_better=indicator_spec.higher_is_better,
                    )
                    self._log_timing("benchmark_calculation_tier2", time.perf_counter() - _tb2, None)
                    result.tier2_benchmark = _b2["value"]
                    result.tier2_benchmark_estimator = _b2["estimator"]
                    result.tier2_percentile_in_reference = _b2["percentile_in_reference"]
                    result.tier2_display_pct_of_reference = _b2["display_pct_of_reference"]
                    result.tier2_low_dispersion_warning = _b2.get("low_dispersion_warning", False)
                    # Honesty label: Tier-2 is the contemporary best-available in a
                    # possibly-modified landscape, NOT a natural/historical baseline.
                    result.reference_type = (
                        getattr(indicator_spec, "reference_type", None)
                        or "contemporary_best_on_offer"
                    )
            except Exception as e:
                logger.warning(f"Tier 2 failed for {indicator_spec.name}: {e}")

        if result.tier1_sampling_diagnostics:
            result.stratification_diagnostics = {
                **(result.stratification_diagnostics or {}),
                "tier1_reference_sampling": result.tier1_sampling_diagnostics}
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

        # FeatureCollection-based indicators (CERI, endemic richness, threatened
        # richness, KBA, flagship) have no raster image but may provide a custom
        # Tier 1 function via metadata["fc_tier1_fn"]. This function takes
        # (site_geometry_ee, region_ee, config) and returns a stats dict directly.
        if image is None:
            fc_tier1_fn = spec.metadata.get("fc_tier1_fn")
            if fc_tier1_fn is not None:
                try:
                    return fc_tier1_fn(site_geometry, region, self.config)
                except Exception as e:
                    logger.warning(f"FC Tier 1 failed for {spec.name}: {e}")
            return {}

        # PERFORMANCE FIX (2026-09-28): the previous full-region native-scale reduceRegion
        # plus a second full pass for MAD cost ~1.5 h/tile at 10-30 m over 50-150 km. Now a
        # deterministic, bounded NATIVE-SCALE random sample of valid pixels; every statistic
        # (incl. the true MAD) is computed from the sampled values -- never a coarsened image.
        scale = self._effective_scale(spec)
        parsed = self._sample_reference_stats(
            ee, image, region, scale, label="tier1",
            population=f"all valid pixels of the indicator image within {radius_km:g} km of the site centroid")
        return parsed

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

    def _reference_accepted(self, result: Dict[str, Any]) -> bool:
        """Reference acceptance gate. Always requires the pixel floor; when OD-3 is
        enabled, ALSO requires the reference to be statistically stable (bootstrap median
        SE within tolerance) so scores are never computed on a noisy reference."""
        n_ref = result.get("n", 0)
        if n_ref < self.config.min_reference_pixels:
            return False
        if getattr(self.config, "use_variance_stability_floor", False):
            pixels = result.get("pixels")
            if pixels is not None:
                stable, diag = estimators.reference_is_stable(
                    pixels,
                    min_n=getattr(self.config, "reference_stability_min_n", 8),
                    rel_tol=getattr(self.config, "reference_stability_rel_tol", 0.15),
                    abs_tol=getattr(self.config, "reference_stability_abs_tol", None))
                result["stability"] = diag
                if not stable:
                    logger.info(f"  Tier 2: reference rejected as unstable "
                                f"(n={diag.get('n')}, rel_se={diag.get('rel_se')}); score suppressed")
                    return False
        return True

    # ------------------------------------------------------------------------
    # Land-cover class construction for the SEED-faithful path (v0.2.0 rewrite).
    # ------------------------------------------------------------------------
    def _build_ecoregion_landcover_image(self, ee, reference_zone):
        """Build the current (Dynamic World) land-cover class image with SEED's PNV
        correction applied ONLY to artificial-class pixels (crops/built by default).

        Returns (corrected_lc_image, diagnostics). This is the class image used for
        BOTH the site's own lookup and the reference pool — SEED applies the same
        correction to focal and reference areas alike (see METHODOLOGY_MASTER §5).
        """
        cfg = self.config
        diag = {"mode": "ecoregion_landcover", "artificial_classes": list(cfg.seed_artificial_dw_classes)}

        dw = (ee.ImageCollection(cfg.seed_landcover_gee_asset)
              .filterBounds(reference_zone)
              .filterDate(ee.Date(ee.Date(self._today_str())).advance(-cfg.seed_landcover_lookback_days, "day"),
                          ee.Date(self._today_str()))
              .select("label"))
        dw_modal = dw.mode()  # most-frequent class per pixel over the lookback window

        artificial_mask = ee.Image.constant(0)
        for cls in cfg.seed_artificial_dw_classes:
            artificial_mask = artificial_mask.Or(dw_modal.eq(ee.Number(cls)))

        if getattr(cfg, "pnv_gee_asset", ""):
            pnv = ee.Image(cfg.pnv_gee_asset)
            # REAL BUG FIXED HERE (found directly from the client's real run
            # log: "Image.select, argument 'bandSelectors': Invalid type.
            # Expected type: List<Object>. Actual type: String. Actual
            # value: biome_type" -- failing for EVERY indicator's Tier2
            # computation, not just some, because this function runs once
            # per Tier2 attempt regardless of which indicator). Passing a
            # bare server-side computed object (pnv.bandNames().get(0)) to
            # .select() -- instead of wrapping it in a list -- trips this
            # exact error in this client library version: the argument
            # type-checker only recognises a literal Python str/list at
            # this call site, not an unwrapped ee.ComputedObject, so it
            # gets treated as an invalid single value instead of a
            # one-element band selector list. Wrapping in [...] is the
            # real, standard fix for this exact, well-known GEE gotcha.
            pnv = pnv.select([pnv.bandNames().get(0)])
            crosswalk = getattr(cfg, "pnv_to_dw_crosswalk", {}) or {}
            if crosswalk:
                pnv_as_dw = ee.Image.constant(-1)  # sentinel; stays -1 for unmapped PNV codes
                for pnv_code, dw_code in crosswalk.items():
                    pnv_as_dw = pnv_as_dw.where(pnv.eq(ee.Number(int(pnv_code))), ee.Number(int(dw_code)))
                # relabel ONLY artificial pixels with their PNV-predicted natural class;
                # everything else keeps its actual Dynamic World class, per SEED.
                corrected = dw_modal.where(artificial_mask.And(pnv_as_dw.gte(0)), pnv_as_dw)
                diag["pnv_correction_applied"] = True
                if not getattr(cfg, "pnv_to_dw_crosswalk_verified", False):
                    diag["warning"] = ("pnv_to_dw_crosswalk has NOT been marked verified against "
                                       "the live PNV asset legend — correction may be mislabelled. "
                                       "See ASSUMPTIONS_AND_LIMITATIONS.md S-4b.")
                    logger.warning("  " + diag["warning"])
            else:
                corrected = dw_modal
                diag["pnv_correction_applied"] = False
                diag["warning"] = "pnv_to_dw_crosswalk is empty — artificial pixels NOT corrected."
                logger.warning("  " + diag["warning"])
        else:
            corrected = dw_modal
            diag["pnv_correction_applied"] = False

        return corrected, diag

    @staticmethod
    def _today_str():
        from datetime import date
        return date.today().isoformat()

    def _compute_tier2(
        self, spec: IndicatorSpec, site_geometry, eco_id: int
    ) -> Dict[str, Any]:
        """
        Tier 2: Select the least-disturbed pixels within the site's ecoregion and
        land-cover stratum, ranked by HMI.

        v0.2.0 CORRECTED algorithm (McElderry et al. 2024, Sec. 3.2 — the earlier build
        had diverged from this; see CHANGELOG and ASSUMPTIONS §1 for the audit trail):

        DEFAULT mode ("ecoregion_landcover", SEED-faithful):
          1. Buffer the site centroid by per-indicator reference_radius_km.
          2. Stratum = SAME ECOREGION (RESOLVE/ECOREGIONS/2017, via eco_id) AND SAME
             LAND-COVER CLASS (Dynamic World, 10 m, current — modal over the lookback
             window). Land cover is NOT secondary to ecoregion; both jointly define the
             stratum, exactly as SEED specifies.
          3. Pixels whose Dynamic World class is "artificial" (crops/built by default)
             are relabelled with their Potential-Natural-Vegetation class BEFORE
             stratum lookup — SEED's actual, narrow use of PNV (not a parallel or
             primary classifier for all pixels, which a prior build incorrectly did).
          4. Within that stratum, rank by HMI (TNC HM v3, 90 m, 2022 — see config);
             reference = pixels at/below min(P5, hmi_hard_ceiling).
          5. Extract indicator values from those reference pixels; return statistics.
          No elevation banding — not part of SEED.

        LEGACY mode ("legacy_landcover_elevation"): the pre-audit Darukaa refinement —
          same ecoregion constraint (now added; previously silently absent), contemporary
          Copernicus land cover, PLUS an elevation band. Not SEED; off by default.
        """
        self._ensure_gee()
        import ee

        # RESOLVED (independent audit, item 3) — DECISION MADE by the project owner,
        # 2026-09-27: Option B (benchmark ghm against an INDEPENDENTLY defined regional
        # reference distribution — the ecoregion+land-cover-matched stratum used by
        # every other indicator, but WITHOUT the low-HMI filtering step that made this
        # circular for ghm specifically). Chosen over Option A (suppress ghm's Tier2
        # entirely, report only absolute/percentile pressure) because ghm is THE
        # headline land-use pressure metric (pillar 5) -- losing its benchmark
        # entirely is a bigger real information loss than the extra branching Option B
        # needs, and Option B keeps ghm's benchmark conceptually consistent with every
        # other indicator's (a real reference-relative comparison), not a different
        # kind of number.
        #
        # How this removes the circularity: normal Tier2 selects reference pixels BY
        # ranking on HMI and keeping only the least-disturbed (P5/ceiling) -- for any
        # OTHER indicator this is fine (the pool is selected by ghm, but the value
        # being compared is a genuinely different measurement). For ghm itself, that
        # selection step picks the pool FOR having low ghm, then compares ghm to it --
        # circular by construction. Fixed by a dedicated ghm-only path (below, at the
        # primary/fallback_1/fallback_2 stages) that uses the SAME ecoregion+land-cover
        # stratification as every other indicator (a real, independent selection
        # criterion -- not derived from ghm/HMI at all) but skips the low-HMI
        # narrowing step entirely (threshold fixed at 1.0, HMI's real max, i.e. no
        # filter): ghm's value is benchmarked against the FULL regional distribution
        # of HMI in its own ecoregion+land-cover stratum, not a pool pre-selected for
        # already resembling it.
        #
        # ghm's Tier 1 (ecoregion-wide) and raw site value were never affected by this
        # (not circular there either); only the Tier 2 path changes.
        _ghm_independent_reference = (spec.name == "ghm")

        if not isinstance(site_geometry, ee.Geometry):
            site_geometry = self._shapely_to_ee(site_geometry)

        cfg = self.config
        strat_mode = getattr(cfg, "reference_stratification", "ecoregion_landcover")

        # Step 1: Reference zone = buffer around site centroid
        radius_km = spec.reference_radius_km or cfg.reference_buffer_km
        buffer_m = radius_km * 1000
        reference_zone = site_geometry.centroid().buffer(buffer_m)

        # Step 2: ECOREGION mask — used in BOTH modes (this constraint was previously
        # threaded through as `eco_id` but never actually applied; fixed here).
        masks_applied = []
        eco_mask = None
        if eco_id is not None and getattr(cfg, "ecoregion_gee_asset", ""):
            try:
                eco_fc = ee.FeatureCollection(cfg.ecoregion_gee_asset).filter(
                    ee.Filter.eq("ECO_ID", int(eco_id)))
                eco_mask = ee.Image.constant(0).paint(eco_fc, 1).selfMask()
                masks_applied.append(f"ecoregion(ECO_ID={eco_id})")
            except Exception as e:
                logger.warning(f"  Ecoregion mask failed ({e}); continuing without it")
        else:
            logger.warning("  No eco_id available; reference pool NOT ecoregion-constrained "
                           "(weaker match — see ASSUMPTIONS_AND_LIMITATIONS.md).")

        # Step 3: LAND-COVER class mask (mode-dependent)
        lc_diag: Dict[str, Any] = {}
        if strat_mode == "ecoregion_landcover":
            lc_image, lc_diag = self._build_ecoregion_landcover_image(ee, reference_zone)
            lc_scale = 10  # Dynamic World native resolution
        else:  # legacy_landcover_elevation
            lc_image = ee.Image(cfg.landcover_gee_asset).select("discrete_classification")
            lc_scale = 100
            lc_diag = {"mode": "legacy_landcover_elevation"}

        site_lc = lc_image.reduceRegion(
            reducer=ee.Reducer.mode(), geometry=site_geometry, scale=lc_scale, maxPixels=1e6
        ).getInfo()
        lc_value = next((v for v in (site_lc or {}).values() if v is not None), None)

        # REAL DEAD CODE REMOVED HERE (Aug 2026, found by an automated
        # unused-variable check): a "Step 4: HMI image" block here fetched
        # the exact same HMI asset via ee.ImageCollection(...).first()
        # .select(...) into a variable ("hmi") that was never used
        # anywhere afterward — the actual HMI fetch that IS used
        # throughout the rest of this function happens again, a few lines
        # below, as "ghm_raw". This was a genuine, wasteful duplicate GEE
        # fetch with no purpose, not a stratification step that got
        # silently skipped — ghm_raw's own masking logic (ecoregion +
        # land-cover + elevation) is the real, complete implementation.

        # Step 5: Build the combined stratification mask (masks kept as named variables
        # so the fallback ladder below can selectively relax them).
        lc_mask = None
        elev_mask = None
        if lc_value is not None:
            lc_mask = lc_image.eq(ee.Number(lc_value))
            masks_applied.append(f"landcover(class={lc_value}, {strat_mode})")

        # Legacy-only: additional elevation band
        if strat_mode == "legacy_landcover_elevation":
            srtm = ee.Image(cfg.srtm_gee_asset).select("elevation")
            site_elev = srtm.reduceRegion(reducer=ee.Reducer.mean(), geometry=site_geometry,
                                          scale=30, maxPixels=1e6).getInfo()
            elev_value = next((v for v in (site_elev or {}).values() if v is not None), None)
            if elev_value is not None:
                elev_band = cfg.elevation_band_m
                elev_mask = srtm.gte(ee.Number(elev_value - elev_band)).And(
                    srtm.lte(ee.Number(elev_value + elev_band)))
                masks_applied.append(f"elev={elev_value:.0f}m±{elev_band:.0f}m")

        # HMI image, masked to ecoregion (always, when available) + land-cover + elevation.
        # Ecoregion is the constraint that should NEVER be dropped in the fallback ladder
        # below (SEED stratifies within-ecoregion always); land-cover/elevation are
        # progressively relaxed if the primary stratum is too small.
        if getattr(cfg, "use_legacy_hmi_asset", False):
            ghm_raw = ee.ImageCollection(cfg.hmi_gee_asset_legacy).first().select(cfg.hmi_gee_band_legacy)
        else:
            ghm_raw = ee.ImageCollection(cfg.hmi_gee_asset).first().select(cfg.hmi_gee_band)
        if eco_mask is not None:
            ghm_raw = ghm_raw.updateMask(eco_mask)

        ghm = ghm_raw
        if lc_mask is not None:
            ghm = ghm.updateMask(lc_mask)
        if elev_mask is not None:
            ghm = ghm.updateMask(elev_mask)

        ghm_in_zone = ghm.clip(reference_zone)
        logger.info(f"  Tier 2 stratification [{strat_mode}]: {', '.join(masks_applied) or 'none'}")
        if lc_diag.get("warning"):
            logger.info(f"  PNV correction note: {lc_diag['warning']}")

        strat_diag = {
            "mode": strat_mode, "masks_applied": list(masks_applied),
            "eco_id": eco_id, "landcover_class": lc_value,
            "landcover_source": (self.config.seed_landcover_gee_asset
                                 if strat_mode == "ecoregion_landcover" else self.config.landcover_gee_asset),
            "hmi_source": (self.config.hmi_gee_asset if not getattr(self.config, "use_legacy_hmi_asset", False)
                          else self.config.hmi_gee_asset_legacy),
            **lc_diag,
        }

        # Step 6: SEED-adapted dynamic HMI threshold
        # P5 capped at ceiling (default 0.05 per McElderry et al. 2024 Eq. S1)
        hmi_ceiling = getattr(self.config, "hmi_hard_ceiling", 0.05)

        # Get indicator image
        indicator_image = self._get_indicator_image(spec)
        if indicator_image is None:
            # REAL GAP FIXED HERE (found while investigating a real Tata
            # Motors run): this returned {} completely silently -- no log
            # message at all, a genuinely different, harder-to-diagnose
            # failure mode than the "insufficient reference pixels"
            # warning below. This is exactly what jrc_water_persistence
            # hit before its real fix (neither gee_image_fn nor
            # tier1_layer registered) -- confirmed directly: it produced
            # zero log output anywhere, not even a warning, for every one
            # of 15 real tiles in that run.
            logger.warning(f"Tier 2: {spec.name} has no gee_image_fn or tier1_layer registered -- "
                          f"_get_indicator_image() returned None, so no reference comparison is "
                          f"structurally possible for this indicator regardless of real data availability.")
            return {}

        # Try primary zone first
        # ghm (independent audit item 3, resolved): skip the low-HMI percentile filter
        # entirely -- threshold fixed at 1.0 (HMI's real max, i.e. no filter) so the
        # reference pool is the FULL ecoregion+land-cover stratum, not one pre-selected
        # for already having low ghm. Every other indicator keeps the normal dynamic
        # P5/ceiling threshold.
        if _ghm_independent_reference:
            hmi_threshold = 1.0
        else:
            hmi_threshold = self._dynamic_hmi_threshold(ghm_in_zone, reference_zone, hmi_ceiling)
        if hmi_threshold is not None:
            result = self._extract_tier2_stats(
                ghm_in_zone, hmi_threshold, indicator_image, reference_zone, spec=spec)
            n_ref = result.get("n", 0)
            if self._reference_accepted(result):
                # SEED transparency: report the realised HMI threshold actually used,
                # so the reader can see how disturbed the "reference" really is.
                result["hmi_realised"] = hmi_threshold
                result["stratification_diagnostics"] = {
                    **strat_diag, "fallback_level": "primary",
                    **({"ghm_independent_reference": True,
                        "ghm_reference_note": ("Independently-selected regional distribution "
                            "(ecoregion+land-cover stratum, NOT filtered by HMI itself) -- "
                            "see independent audit item 3 resolution, reference.py's "
                            "_compute_tier2 docstring.")}
                       if _ghm_independent_reference else {}),
                }
                logger.info(f"  Tier 2: {n_ref} ref pixels, HMI ≤ {hmi_threshold:.4f}")
                return result

        # Fallback 1: drop land-cover (+elevation) constraint, keep ecoregion (never dropped)
        if lc_mask is not None or elev_mask is not None:
            logger.info("  Tier 2 fallback 1: dropping land-cover/elevation mask, keeping ecoregion...")
            ghm_fb = ghm_raw  # already ecoregion-masked above
            ghm_fb = ghm_fb.clip(reference_zone)
            t = 1.0 if _ghm_independent_reference else self._dynamic_hmi_threshold(ghm_fb, reference_zone, hmi_ceiling)
            if t is not None:
                result = self._extract_tier2_stats(ghm_fb, t, indicator_image, reference_zone, spec=spec)
                if self._reference_accepted(result):
                    result["stratification_diagnostics"] = {
                        **strat_diag, "fallback_level": "fallback_1_dropped_landcover",
                        **({"ghm_independent_reference": True} if _ghm_independent_reference else {}),
                    }
                    logger.info(f"  Tier 2 fallback 1: {result['n']} pixels (ecoregion only)")
                    return result

        # Fallback 2: progressively widen the buffer (ecoregion + land-cover kept where set)
        for multiplier in [2.0, 3.0, 4.0]:
            wider_km = radius_km * multiplier
            if wider_km > 200:
                break
            logger.info(f"  Tier 2 fallback 2: widening buffer to {wider_km}km...")
            wider_zone = site_geometry.centroid().buffer(wider_km * 1000)
            ghm_wider = ghm_raw
            if lc_mask is not None:
                ghm_wider = ghm_wider.updateMask(lc_mask)
            if elev_mask is not None:
                ghm_wider = ghm_wider.updateMask(elev_mask)
            ghm_wider = ghm_wider.clip(wider_zone)
            t = 1.0 if _ghm_independent_reference else self._dynamic_hmi_threshold(ghm_wider, wider_zone, hmi_ceiling)
            if t is not None:
                result = self._extract_tier2_stats(
                    ghm_wider, t, indicator_image, wider_zone, spec=spec)
                if self._reference_accepted(result):
                    result["stratification_diagnostics"] = {
                        **strat_diag, "fallback_level": f"fallback_2_widened_{wider_km}km",
                        **({"ghm_independent_reference": True} if _ghm_independent_reference else {}),
                    }
                    logger.info(f"  Tier 2 fallback 2: {result['n']} pixels at {wider_km}km")
                    return result

        logger.warning(
            f"Tier 2: insufficient reference pixels for {spec.name}. "
            f"Buffer={radius_km}km, ceiling={hmi_ceiling}.")
        # REAL DIAGNOSTIC ADDED HERE (found while investigating a real Tata
        # Motors run where 4+ indicators failed this way across every real
        # zone, with no way to tell WHY from the log alone -- ruled out
        # several real hypotheses via static code inspection, none fully
        # confirmed without this). Reports the actual HMI threshold and
        # the real count of stratified (ecoregion+landcover) pixels
        # available at 200km, even before HMI-ranking -- distinguishes
        # "the stratum itself is essentially empty at this location" from
        # "the stratum has pixels but none pass the HMI ceiling" from
        # "this indicator's own asset has no valid data at the stratified
        # pixel locations", which look identical without this.
        try:
            widest_zone = site_geometry.centroid().buffer(200 * 1000)
            diag_lc = lc_image.clip(widest_zone)
            strat_count = ee.Image.constant(1).updateMask(diag_lc.mask()).reduceRegion(
                reducer=ee.Reducer.count(), geometry=widest_zone, scale=1000,
                maxPixels=1e8, bestEffort=True).getInfo()
            ind_count = indicator_image.clip(widest_zone).reduceRegion(
                reducer=ee.Reducer.count(), geometry=widest_zone, scale=1000,
                maxPixels=1e8, bestEffort=True).getInfo()
            logger.warning(f"  Diagnostic: stratified (ecoregion+landcover) pixel count at 200km = "
                          f"{strat_count}; this indicator's OWN valid-pixel count at 200km = {ind_count}. "
                          f"If the indicator count is ~0 while the stratum count is real, the indicator's "
                          f"own asset likely has no valid data here (a real, external data-coverage gap, "
                          f"not a stratification problem). If both are ~0, the stratification itself is "
                          f"the constraint.")
        except Exception as diag_e:
            logger.warning(f"  Diagnostic query itself failed ({diag_e}) -- cannot narrow this down further "
                          f"without live GEE access to test directly.")
        return {}

    def _dynamic_hmi_threshold(self, ghm_image, geometry, ceiling):
        """SEED Eq. S1: P5 capped at ceiling, with P3 step-down."""
        import ee
        try:
            stats = ghm_image.reduceRegion(
                reducer=ee.Reducer.percentile([3, 5]),
                geometry=geometry, scale=1000, maxPixels=1e8, bestEffort=True
            ).getInfo()
        except Exception:
            return None
        if not stats:
            return None
        p5 = p3 = None
        for k, v in stats.items():
            if v is None: continue
            kl = k.lower()
            if "p5" in kl or kl.endswith("_5"): p5 = v
            elif "p3" in kl or kl.endswith("_3"): p3 = v
        if p5 is not None and p5 <= ceiling: return p5
        if p3 is not None and p3 <= ceiling: return p3
        if p5 is not None or p3 is not None: return ceiling
        for v in stats.values():
            if v is not None: return min(v, ceiling)
        return None

    def _extract_tier2_stats(self, ghm_zone, threshold, indicator_image, geometry, spec=None):
        """Extract indicator stats from reference pixels (HMI ≤ threshold)."""
        import ee
        # All existing masks (ecoregion + land-cover stratum are already baked into ghm_zone;
        # the HMI threshold mask is applied here) are applied BEFORE sampling, so the sample
        # is drawn from exactly the selected reference population -- selection logic unchanged.
        ref_mask = ghm_zone.lte(ee.Number(threshold))
        ind_ref = indicator_image.updateMask(ref_mask).clip(geometry)
        scale = self._effective_scale(spec)
        return self._sample_reference_stats(ee, ind_ref, geometry, scale, label="tier2")

    # Independent audit item 4, real known native resolutions confirmed
    # directly this session (not guessed): every reference reduceRegion
    # previously hardcoded scale=1000 regardless of the indicator's own real
    # dataset resolution -- indefensible for 10-30m indicators, especially
    # against Tata's real <1ha zones. Honest limitation: only the indicators
    # actually investigated this session have a confirmed value below; the
    # rest fall back to a documented, more conservative default (100m, not
    # the old 1000m) rather than a guessed per-indicator number.
    _KNOWN_NATIVE_SCALE_M = {
        "natural_habitat": 10,      # Dynamic World
        "hdi": 10,                  # Dynamic World built-up class
        "forest_loss_rate": 30,     # Hansen GFC
        "chm": 10,                  # ETH Global Canopy Height 2020 (confirmed this session)
        "ghm": 90,                  # TNC HM v3 (confirmed this session)
        "light_pollution": 500,     # VIIRS DNB (confirmed this session)
        "jrc_water_persistence": 30,  # JRC GSW MonthlyHistory
        "tspi": 10, "sabf": 10, "wcpi": 10, "edpp": 10, "mspl": 10,
        "sdi": 10, "rci": 10, "iri": 10,  # Sentinel-2-based
        "wsdi": 10,                 # Sentinel-1 GRD
        "net_forest_change_rate": 30,  # Hansen GFC + DW proxy; declared 30 m reference scale
    }
    _DEFAULT_FALLBACK_SCALE_M = 100  # was 1000 -- still a real placeholder for
    # indicators not yet individually confirmed, but an order of magnitude
    # closer to reality than the old blanket 1km for what are mostly 10-90m
    # products; not a substitute for confirming the remaining indicators
    # individually as real follow-up work.

    def _effective_scale(self, spec) -> float:
        """Real, indicator-aware reduceRegion scale in metres. Returns the
        confirmed native resolution when known; otherwise a documented,
        honest fallback -- never a silent, unconditional 1000m regardless of
        what the indicator actually is."""
        if spec is not None:
            explicit = getattr(spec, "native_scale_m", None)
            if explicit:
                return explicit
            known = self._KNOWN_NATIVE_SCALE_M.get(getattr(spec, "name", None))
            if known:
                return known
        return self._DEFAULT_FALLBACK_SCALE_M

    # ------------------------------------------------------------------
    # Bounded native-scale reference sampling + timing
    # ------------------------------------------------------------------
    def _log_timing(self, stage: str, elapsed: float, n_ref) -> None:
        site, ind = getattr(self, "_timing_ctx", ("?", "?"))
        rec = {"site_id": site, "indicator": ind, "stage": stage,
               "elapsed_seconds": round(float(elapsed), 2), "n_reference_pixels": n_ref}
        self.timing_log.append(rec)
        TIMING_LOG.append(rec)
        msg = (f"TIMING site_id={site} indicator={ind} stage={stage} "
               f"elapsed_seconds={rec['elapsed_seconds']:.2f} n_reference_pixels={n_ref}")
        logger.debug(msg)
        print(msg, flush=True)   # printed (not only logged) so it is visible at any log level

    @contextmanager
    def _timed(self, stage: str):
        info = {"n": None}
        t0 = time.perf_counter()
        try:
            yield info
        finally:
            self._log_timing(stage, time.perf_counter() - t0, info.get("n"))

    def _sample_reference_stats(self, ee, image, region, scale, label: str,
                                population: str | None = None) -> Dict[str, Any]:
        """Deterministic native-resolution reference sample -> statistics.

        image  : ALREADY-MASKED reference image (sampling happens after every mask).
        Draws ee.Image.sample(numPixels=N, seed=S, dropNulls=True, tileScale=T) at the
        indicator's native `scale`, then computes mean/median/SD/MAD/p25/p75/p90/n from the
        sampled values in numpy. If a heavily-masked pool returns far fewer valid pixels than
        requested, the request is enlarged (bounded by reference_sample_max_pixels) and the
        final requested/valid counts are recorded -- never silently coarsened."""
        cfg = self.config
        n_cfg = int(getattr(cfg, "reference_sample_pixels", 5000))
        seed = int(getattr(cfg, "reference_sample_seed", 12345))
        tile_scale = int(getattr(cfg, "reference_sample_tilescale", 4))
        max_px = int(getattr(cfg, "reference_sample_max_pixels", 40000))
        factor = max(2, int(getattr(cfg, "reference_sample_oversample_factor", 4)))
        min_frac = float(getattr(cfg, "reference_sample_min_fraction", 0.5))

        n_req, attempts, values = n_cfg, 0, []
        t0 = time.perf_counter()
        while True:
            attempts += 1
            fc = (image.select(0).rename("v")
                  .sample(region=region, scale=scale, numPixels=n_req, seed=seed,
                          dropNulls=True, geometries=False, tileScale=tile_scale))
            values = [v for v in (fc.aggregate_array("v").getInfo() or []) if v is not None]
            if len(values) >= min_frac * n_req or n_req >= max_px:
                break
            n_req = min(n_req * factor, max_px)
        self._log_timing(f"reference_sampling_{label}", time.perf_counter() - t0, len(values))

        parsed = reference_stats_from_values(values)
        parsed["effective_scale_m"] = scale
        parsed["sampling_diagnostics"] = {
            "reference_sampling_method": "deterministic_native_scale_random_sample",
            "reference_sample_requested": n_req,
            "reference_sample_requested_initial": n_cfg,
            "reference_sample_attempts": attempts,
            "reference_sample_n": len(values),
            "reference_sample_seed": seed,
            "reference_sample_tilescale": tile_scale,
            "reference_sample_max_pixels": max_px,
            "reference_sample_retry_min_fraction": min_frac,
            "reference_sample_oversample_factor": factor,
            "effective_scale_m": scale,
            "reference_population_definition": population,
            "reference_stat_source": "sampled native-scale pixel values (not a coarsened image)",
        }
        return parsed

    @staticmethod
    def _tier2_population_definition(strat_diag: Dict[str, Any], hmi_realised) -> str:
        level = (strat_diag or {}).get("fallback_level", "primary")
        if (strat_diag or {}).get("ghm_independent_reference"):
            sel = "NO HMI filter (independent regional reference for ghm; see audit item 3)"
        else:
            sel = (f"HMI <= {hmi_realised:.4f} (least-modified pixels)"
                   if hmi_realised is not None else "HMI-threshold-selected least-modified pixels")
        strat = {"primary": "ecoregion + Dynamic World land-cover stratum",
                 "fallback_1_dropped_landcover": "ecoregion only (land-cover constraint dropped)"
                 }.get(level, f"ecoregion + land-cover stratum, buffer widened ({level})")
        return f"{strat}; {sel}"

    @staticmethod
    def _compute_true_mad(ee, image, region, median_value, scale=1000):
        """DEPRECATED / UNUSED since 2026-09-28 (no callers): reference MAD is now computed
        from the sampled values in reference_stats_from_values. Kept only for reference; it
        performs a FULL-region reduceRegion and must not be reintroduced into the Tier 1/2 path.

        Real, GEE-native two-pass Median Absolute Deviation: median(|x -
        median(x)|), computed over the exact same region/mask the median itself
        came from. Not an approximation from SD or percentiles -- an independent
        audit found this pipeline was silently using SD where its own documented
        formula calls for MAD; this is the real fix, not a client-side shortcut.
        Returns None if the reduction yields nothing (e.g. the reference pool is
        empty), rather than raising."""
        try:
            abs_dev = image.subtract(ee.Number(median_value)).abs()
            mad_stats = abs_dev.reduceRegion(
                reducer=ee.Reducer.median(), geometry=region, scale=scale,
                maxPixels=1e9, bestEffort=True).getInfo()
            for v in (mad_stats or {}).values():
                if v is not None:
                    return v
            return None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _intactness_ratio(
        site_value: float, reference_value: float, higher_is_better: bool
    ) -> float:
        """
        DEPRECATED (v0.2.0). Legacy capped intactness ratio, retained only for
        backward compatibility and intuitive display. Do NOT use for scoring:
        the 1.0 cap censors above-reference improvement (non-responsive) and the
        ratio is invalid for non-ratio-scale indicators. Use estimators.benchmark
        (tier*_benchmark fields) instead. See estimators.py and the HMI/SEED audit.

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
        # reference = 0: regional landscape has no signal — ratio undefined
        if reference_value == 0:
            return None

        # site_value = 0 for lower-is-better indicators (e.g. forest_loss_rate=0):
        # zero loss/pressure is the best possible outcome → intactness = 100%
        if site_value == 0:
            if not higher_is_better:
                return 1.0   # zero pressure = fully intact relative to reference
            else:
                return None  # zero value for higher-is-better is genuinely missing

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
