"""
Configuration
=============

Loads pipeline configuration from a YAML file specifying file paths,
GEE project ID, buffer radius, HMI threshold, and indicator toggles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import yaml


@dataclass
class Config:
    """Pipeline configuration."""

    # Google Earth Engine
    gee_project: str = ""
    gee_service_account: Optional[str] = None
    gee_key_path: Optional[str] = None

    # Local raster paths
    raster_paths: Dict[str, str] = field(default_factory=dict)
    # Expected keys: "globio4_msa", "seed_biocomplexity", "ecoregions", "ghm", etc.

    # Ecoregion shapefile or GEE asset
    ecoregion_source: str = "gee"  # "gee" or path to local shapefile
    ecoregion_gee_asset: str = "RESOLVE/ECOREGIONS/2017"

    # BII GEE asset — upload NHM PREDICTS BII to your GEE project
    # NHM v2.1.1: https://data.nhm.ac.uk/dataset/bii-developed-by-nhm-v2-1-1-limited-release
    # Values stored as 0–100; pipeline divides by 100 automatically.
    bii_gee_asset: Optional[str] = None  # e.g., "projects/your-gee-project-id/assets/bii-2020_v2-1-1"

    # Tier 2 reference selection parameters
    reference_buffer_km: float = 100.0  # search radius for reference patches
    hmi_percentile_threshold: float = 5.0  # percentile of HMI distribution for threshold
    hmi_hard_ceiling: float = 0.05  # SEED MAXIMUM allowable HMI for reference pixels.
    # RESTORED to 0.05 (v0.2.0). The SEED source (McElderry et al. 2024) defines the
    # maximum allowable upper-limit HMI for the counterfactual reference as < 0.05.
    # A prior build had raised this to 0.10 to make references easier to find; that
    # admits land twice as modified as SEED permits and inflates apparent intactness.
    # The dynamic threshold is min(P5(HMI), hmi_hard_ceiling) and the REALISED value
    # is now reported per run (reference_hmi_realised) for transparency.
    min_reference_pixels: int = 12  # representativeness floor for a stable reference.
    # NOTE (v0.2.0): a fixed pixel floor is a provisional stand-in. SEED expands the
    # search until the area is statistically representative; a mean±SD from ~5 pixels
    # is noise. 12 is a conservative interim floor pending a variance-stability
    # criterion (OPEN_DECISIONS OD-3). The config.py default and the YAML loader
    # default are now identical (previously 5 vs 20 — a silent inconsistency bug).

    # HMI asset (v0.2.0 audit): the original CSP/HM/GlobalHumanModification is 1 km,
    # frozen at ~2016. Replaced with the same authors' updated, finer, current successor:
    # TNC Global Human Modification v3, 90 m, 2022 static snapshot (RMSE 0.178 at 90 m;
    # Theobald et al. 2025, Scientific Data). Verified as a live GEE catalog asset.
    hmi_gee_asset: str = "TNC/HM/v3/90m_s"
    hmi_gee_band: str = "All_threats_combined"
    # Legacy asset, kept only for exact reproduction of pre-audit runs:
    hmi_gee_asset_legacy: str = "CSP/HM/GlobalHumanModification"
    hmi_gee_band_legacy: str = "gHM"
    use_legacy_hmi_asset: bool = False

    # FLII proxy (v0.2.5) — edge-effect / focal radius for the Q (inferred pressure) and
    # LFC (lost forest connectivity) terms. Declared, not silently fixed: edge-effect
    # distances documented in the literature vary widely (metres to several km
    # depending on taxon and pressure type) — 300 m is a documented default pending
    # project-specific literature review, not a claim of universal validity.
    flii_edge_effect_radius_m: float = 300.0

    landcover_gee_asset: str = "COPERNICUS/Landcover/100m/Proba-V-C3/Global/2019"
    # NOTE: retained only for reference_stratification="legacy_landcover_elevation" (see
    # below). The SEED-faithful default path uses Dynamic World (10 m, current) instead —
    # this 100 m/2019 asset is coarse and stale next to it (v0.2.0 audit).
    elevation_band_m: float = 300.0  # ±m elevation band — LEGACY MODE ONLY, not in SEED.
    # Filters reference pixels to within ±elevation_band_m of the site's
    # elevation, preventing ecologically incomparable high/low altitude
    # pixels from contaminating the reference distribution.
    # Uses SRTM 30m DEM (Farr et al. 2007, DOI:10.1029/2005RG000183).
    # GEE asset: USGS/SRTMGL1_003
    srtm_gee_asset: str = "USGS/SRTMGL1_003"

    # Remote sensing parameters
    ndvi_year: int = 2025
    ndvi_cloud_threshold: float = 20.0  # max cloud cover %
    lst_year: int = 2025

    # forest_loss_rate windows (v0.2.1: made configurable — was hardcoded). Each tuple is
    # (label, hansen_lossyear_start, hansen_lossyear_end, n_years) where start/end are
    # Hansen GFC lossyear codes (1=2001 ... 25=2025 in the 2025 v1.13 release). Add or
    # remove windows freely (e.g. a "last_10_years" window) for REPORTING/NARRATIVE.
    #
    # forest_loss_primary_window MUST match one label in the list below and is the ONLY
    # window whose rate feeds the actual SCORE. This is deliberate, not an oversight:
    # letting the scored window be freely swapped per-run would let a project pick
    # whichever window looks best and call that "the" loss rate — the same hidden-
    # cherry-picking problem this whole methodology redesign removes elsewhere. Changing
    # which window is primary is a methodology decision, not a per-run config tweak;
    # do it deliberately and document why if you do.
    forest_loss_windows: List[Tuple[str, int, int, int]] = field(default_factory=lambda: [
        ("loss_longterm_2001_2025", 1, 25, 24),   # full Hansen record
        ("loss_recent_2020_2025",  20, 25,  5),   # last 5 years
        ("loss_current_2023_2025", 23, 25,  2),   # last 2 years
    ])
    forest_loss_primary_window: str = "loss_longterm_2001_2025"

    # Statistical parameters
    bootstrap_iterations: int = 10000
    permutation_iterations: int = 10000
    confidence_level: float = 0.95
    random_seed: int = 42

    # Output
    output_dir: str = "./output"
    output_format: str = "json"  # "json", "csv", or "both"

    # Indicator selection (empty = all registered)
    enabled_indicators: List[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Project context (v0.2.0). Drives reference type + which modules activate,
    # WITHOUT changing the fixed core constructs (keeps cross-project comparability).
    # ------------------------------------------------------------------
    realm: str = "terrestrial"          # terrestrial | aquatic | mixed
    archetype: str = "conservation"     # conservation | agroforestry | aquatic |
                                        # corporate | solar | mining | materials
    assessment_mode: str = "baseline"   # baseline (Year-0) | monitoring (Year-N: change vs baseline)
    reference_estimator_default: str = "auto"  # auto (by scale) | log_response_ratio | robust_z

    # OD-3 — variance-stability reference floor. When enabled, a reference is accepted
    # only if it also passes estimators.reference_is_stable (bootstrap median SE within
    # tolerance); otherwise the score is suppressed rather than computed on noise.
    use_variance_stability_floor: bool = True
    reference_stability_rel_tol: float = 0.15   # max bootstrap median SE / |median|
    reference_stability_min_n: int = 8          # absolute minimum finite pixels

    # OD-4 — SEED similarity-to-reference kernel (Eq. 1 in McElderry et al. 2024):
    # K = exp[-delta (x-x_r)^T C_r^-1 (x-x_r)] — a genuine Mahalanobis-distance kernel
    # using the REFERENCE SAMPLE'S COVARIANCE, not a weighted-magnitude approximation.
    # An OPTIONAL per-construct similarity view; complements, never replaces, the
    # direction-aware per-indicator responsive benchmarks used for scoring.
    #   "diagonal" (default): treats indicators within a construct as uncorrelated —
    #     a real, named special case of Eq. 1 (C_r^-1 = diag(1/var)), and the numerically
    #     STABLE choice given reference samples are typically small (~12-30 pixels,
    #     OD-3) — a full covariance estimated from that few points is unstable/singular.
    #   "full": estimates the full reference covariance (with shrinkage regularisation)
    #     from co-located, multi-band-sampled reference pixels — closer to Eq. 1 as
    #     written, but requires a larger reference sample to invert reliably; falls back
    #     to "diagonal" and reports the fallback when the sample is too small.
    use_seed_kernel: bool = False
    seed_kernel_mode: str = "diagonal"        # "diagonal" | "full"
    seed_kernel_delta: float = 0.5            # provisional; NOT yet calibrated (see below)
    seed_kernel_shrinkage: float = 0.2        # "full" mode only: covariance shrinkage toward diagonal
    seed_kernel_min_n_full: int = 30          # "full" mode requires at least this many co-located pixels

    # delta calibration (SEED optimises delta per land-cover x ecoregion stratum to
    # maximise the correlation between K and (1-HMI), Section 3.1). We cannot fit this
    # without real reference-adjacent pixel data (indicator values + HMI at the same
    # points) from a live GEE run. estimators.fit_delta_diagonal() implements the
    # fitting routine and is unit-tested on synthetic data; the DEFAULT above stays an
    # explicit, undisguised placeholder until fitted against real project data.

    # ------------------------------------------------------------------------------
    # OD-5 — reference stratification. TWO modes:
    #
    # "ecoregion_landcover" (DEFAULT, SEED-faithful): ecoregion x land-cover are BOTH the
    #   stratum (not one "primary" and the other secondary). Land cover is a Dynamic
    #   World (10 m, current) modal composite. PNV is used ONLY to relabel pixels whose
    #   Dynamic World class is "artificial" (crops, built) with their PNV-predicted
    #   natural class — exactly SEED's stated role for PNV — via a class crosswalk that
    #   MUST be verified against the live PNV asset's legend before first use (see
    #   PNV_TO_DW_CROSSWALK below and ASSUMPTIONS_AND_LIMITATIONS.md). No elevation.
    #
    # "legacy_landcover_elevation": the pre-audit Darukaa addition (Copernicus land cover
    #   + elevation band, no PNV correction). NOT SEED. Kept as an optional refinement
    #   for users who want elevation-narrowed references; off by default.
    # ------------------------------------------------------------------------------
    reference_stratification: str = "ecoregion_landcover"

    ecoregion_gee_asset: str = "RESOLVE/ECOREGIONS/2017"  # verified: FeatureCollection, ECO_ID/REALM

    # Dynamic World (current, 10 m) as the land-cover class source for the SEED-faithful
    # path. Modal (most-frequent) class over the lookback window, per pixel.
    seed_landcover_gee_asset: str = "GOOGLE/DYNAMICWORLD/V1"
    seed_landcover_lookback_days: int = 730  # ~2 years; adjust for project cadence
    # Dynamic World "label" class indices treated as artificial (PNV-correctable):
    #   0 water, 1 trees, 2 grass, 3 flooded_vegetation, 4 crops, 5 shrub_and_scrub,
    #   6 built, 7 bare, 8 snow_and_ice. Default = crops(4) + built(6), the two
    #   unambiguous conversions. KNOWN GAP: pasture/grazing land has no distinct DW
    #   class and is NOT reliably captured by this default — see ASSUMPTIONS §1.
    seed_artificial_dw_classes: List[int] = field(default_factory=lambda: [4, 6])

    pnv_gee_asset: str = "OpenLandMap/PNV/PNV_BIOME-TYPE_BIOME00K_C/v01"
    # NOTE: 1 km / biome-level — coarse vs the 10 m land-cover/indicator layers, and may
    # be near-constant within a single ecoregion. Not confirmed to be the exact PNV
    # product SEED used (SEED-spirit, not SEED-identical). See ASSUMPTIONS §1.
    #
    # VERIFIED (2026-08-22, against the live asset's actual band/class metadata — 20
    # biome_type classes, band 'biome_type'). The class CODES and NAMES below are
    # confirmed correct. The mapping of each biome to a Dynamic World class is a
    # documented judgement call for a handful of ambiguous classes (flagged inline);
    # not every biome has an unambiguous DW equivalent, since DW's 9 classes are far
    # coarser than PNV's 20 biomes. Re-check the flagged ones if results look off for
    # a project heavy in savanna, sclerophyll woodland, or open-woodland biomes.
    pnv_to_dw_crosswalk_verified: bool = True
    pnv_to_dw_crosswalk: Dict[int, int] = field(default_factory=lambda: {
        # code: name                                                  -> DW class
        1:  1,   # tropical evergreen broadleaf forest                -> trees
        2:  1,   # tropical semi-evergreen broadleaf forest           -> trees
        3:  1,   # tropical deciduous broadleaf forest and woodland   -> trees
        4:  1,   # warm-temperate evergreen broadleaf and mixed forest-> trees
        7:  1,   # cool-temperate rainforest                          -> trees
        8:  1,   # cool evergreen needleleaf forest                   -> trees
        9:  1,   # cool mixed forest                                  -> trees
        13: 1,   # temperate deciduous broadleaf forest               -> trees
        14: 1,   # cold deciduous forest                              -> trees
        15: 1,   # cold evergreen needleleaf forest                   -> trees
        16: 5,   # temperate sclerophyll woodland and shrubland       -> shrub_and_scrub
                 #   JUDGEMENT CALL: "woodland and shrubland" straddles trees/shrub_and_scrub;
                 #   mapped to shrub_and_scrub since these (e.g. Mediterranean chaparral-type
                 #   systems) are typically open/shrub-dominated, not closed canopy.
        17: 1,   # temperate evergreen needleleaf open woodland       -> trees
                 #   JUDGEMENT CALL: "open" woodland could arguably be shrub_and_scrub;
                 #   mapped to trees since needleleaf woodland is still forest-structured.
        18: 2,   # tropical savanna                                   -> grass
                 #   JUDGEMENT CALL: savanna is mixed grass + scattered trees; DW has no
                 #   savanna class. Mapped to grass (the dominant cover) — this is a real
                 #   simplification, most consequential for savanna-heavy projects.
        20: 5,   # xerophytic woods/scrub                             -> shrub_and_scrub
        22: 2,   # steppe                                             -> grass
        27: 7,   # desert                                             -> bare
        28: 2,   # graminoid and forb tundra                          -> grass
        30: 5,   # erect dwarf shrub tundra                           -> shrub_and_scrub
        31: 5,   # low and high shrub tundra                          -> shrub_and_scrub
        32: 5,   # prostrate dwarf shrub tundra                       -> shrub_and_scrub
        # No PNV biome maps to water(0), flooded_vegetation(3), crops(4), built(6), or
        # snow_and_ice(8) — expected: PNV is POTENTIAL NATURAL vegetation, so "what would
        # this artificial pixel naturally be" can never resolve to another artificial
        # class, and this product has no permanent-ice biome. A crops/built pixel whose
        # PNV falls outside this table simply keeps its Dynamic World label uncorrected
        # (the correction is a best-effort relabelling, not a guarantee for every pixel).
    })

    # Dynamic World class reference (for the table above): 0 water, 1 trees, 2 grass,
    # 3 flooded_vegetation, 4 crops, 5 shrub_and_scrub, 6 built, 7 bare, 8 snow_and_ice.

    @classmethod
    def from_yaml(cls, path: str) -> "Config":
        """Load configuration from a YAML file."""
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}

        # Flatten nested sections
        flat = {}
        for section in data.values() if isinstance(data, dict) else []:
            if isinstance(section, dict):
                flat.update(section)
            else:
                flat.update(data)
                break

        # If the YAML is already flat, use directly
        if not any(isinstance(v, dict) for v in data.values()):
            flat = data

        # Merge nested structure
        if "gee" in data and isinstance(data["gee"], dict):
            flat["gee_project"] = data["gee"].get("project", "")
            flat["gee_service_account"] = data["gee"].get("service_account")
            flat["gee_key_path"] = data["gee"].get("key_path")

        if "rasters" in data and isinstance(data["rasters"], dict):
            flat["raster_paths"] = data["rasters"]

        if "tier2" in data and isinstance(data["tier2"], dict):
            t2 = data["tier2"]
            flat["reference_buffer_km"] = t2.get("buffer_km", 100.0)
            flat["hmi_percentile_threshold"] = t2.get("hmi_percentile", 5.0)
            flat["hmi_hard_ceiling"] = t2.get("hmi_hard_ceiling", 0.05)  # SEED max (now loadable)
            flat["min_reference_pixels"] = t2.get("min_pixels", 12)  # matches dataclass default (was 20 — bug)
            flat["elevation_band_m"] = t2.get("elevation_band_m", 300.0)

        if "statistics" in data and isinstance(data["statistics"], dict):
            st = data["statistics"]
            flat["bootstrap_iterations"] = st.get("bootstrap_n", 10000)
            flat["permutation_iterations"] = st.get("permutation_n", 10000)
            flat["confidence_level"] = st.get("confidence", 0.95)
            flat["random_seed"] = st.get("seed", 42)

        if "output" in data and isinstance(data["output"], dict):
            flat["output_dir"] = data["output"].get("dir", "./output")
            flat["output_format"] = data["output"].get("format", "json")

        if "indicators" in data and isinstance(data["indicators"], list):
            flat["enabled_indicators"] = data["indicators"]

        if "project" in data and isinstance(data["project"], dict):
            pr = data["project"]
            flat["realm"] = pr.get("realm", "terrestrial")
            flat["archetype"] = pr.get("archetype", "conservation")
            flat["assessment_mode"] = pr.get("assessment_mode", "baseline")
            flat["reference_estimator_default"] = pr.get("reference_estimator_default", "auto")

        # Build config, ignoring unknown keys
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in flat.items() if k in valid_fields}
        return cls(**filtered)

    @classmethod
    def default(cls) -> "Config":
        """Return default configuration."""
        return cls()
