"""
config_schema.py — loads and validates a project's config.yaml
================================================================

Design decision (locked): ONE declarative config.yaml per project, no
embedded logic. A project that wants
non-standard behaviour gets a new config KEY (added here, with a default so
older configs keep working), never a per-project Python override file.

Validation is intentionally hand-written rather than via a schema library —
the project has few enough config keys that a manual check gives clearer,
more actionable error messages ("EMU_MIN_TILES must be >= 1, got 0" beats a
generic jsonschema trace) and avoids adding a dependency for this alone.

Every field has an explicit default declared in DEFAULTS below. A project's
config.yaml only needs to set what differs from the default — this is what
keeps configs short and non-confusing across very different archetypes
(a 4-parcel Soulforest zone vs. a 1,893-parcel GV run).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults. Every one of these can be overridden by a project's config.yaml.
# Grouped by the pipeline stage that consumes them (01..06) for readability.
# ---------------------------------------------------------------------------
DEFAULTS: Dict[str, Any] = {
    # --- identity ---------------------------------------------------------
    "client_name": None,                 # REQUIRED, no default
    "project_name": None,                # REQUIRED, no default
    "realm": "terrestrial",              # terrestrial | aquatic | mixed
    "archetype": None,                   # REQUIRED: agroforestry | conservation | industrial

    # --- 01_ingestion -------------------------------------------------------
    # Attribute crosswalk: canonical_name -> [possible raw KML field names].
    # Matching is case-insensitive and tried in list order. A project's
    # config.yaml should extend/override this per its own client's KML
    # schema (every client names columns differently — see CHANGELOG note
    # on Soova vs GV using entirely different field names for the same
    # underlying attributes).
    # Explicit, auditable per-parcel data-quality overrides — keyed on
    # placemark name, applied AFTER the crosswalk. Empty by default; a
    # project's own config.yaml is where real, verified corrections go,
    # each with its own justification comment.
    "district_corrections": {},
    "attribute_crosswalk": {
        "farmer_id":        ["farmername", "Farmer_s_n", "farmer_name"],
        "admin_state":      ["state", "State"],
        "admin_district":   ["district", "District"],
        "admin_block":      ["block", "Block", "Block_Name"],
        "admin_grampanchayat": ["grampanchayat", "Grampancha", "gram_panchayat"],
        "admin_village":    ["village", "Village"],
        "plantation_year":  ["Plantation_year", "Year_of_pl", "plantation_year", "year_of_planting"],
        "plantation_type":  ["plantation_type", "Plantation_Type", "species_mix", "crop_type", "Crop_Type"],
        "parcel_block_id":  ["LP_id", "block_id", "Block_ID", "parcel_block"],
        "area_ha_reported": ["area_ha", "Area_ha", "AREA_HA"],
    },
    # Placemark-name lexicon, split by confidence — this split exists because
    # a name like "Admin Area" is not reliably 100% built-up (Soulforest:
    # Aura confirmed a genuinely green sub-patch in the middle of its Admin
    # Area polygon). Two different actions follow:
    #   hard_exclusion_terms   -> whole placemark dropped now, in 01_ingestion.
    #                              Reserved for names that are unambiguously
    #                              infrastructure at any resolution (a road is
    #                              a road end to end).
    #   soft_exclusion_terms   -> placemark is NOT dropped here. It's tagged
    #                              exclusion_status="provisional_pixel_review"
    #                              and passed through to 02_covariates, where
    #                              the actual land-cover/segmentation raster
    #                              inside the polygon decides pixel-by-pixel
    #                              what's really built vs. green. Prevents
    #                              silently losing real candidate space.
    "hard_exclusion_terms": [
        "building", "parking", "shed", "structure", "road", "office", "warehouse",
    ],
    "soft_exclusion_terms": [
        "guest area", "admin area", "nursery", "speciality zone",
    ],
    "exclusion_placemark_names": [],     # exact-name overrides, project-specific
    "ecological_anchor_placemark_names": [],  # e.g. ["Fruit Forest", "Wetland"] — see 03
    "aoi_boundary_placemark_names": [],  # exact override if auto-detection (see kml_ingest.classify_aoi_boundary) picks the wrong placemark

    # --- 02_covariates ----------------------------------------------------
    "max_builtup_pct_for_candidate": 50.0,  # hard-filter: candidate footprint > this % built-up is dropped
    # NDVI override threshold (see covariate_ingest.py): a cell with NDVI
    # at or above this is treated as
    # genuinely vegetated regardless of what the land-cover classifier's
    # built-up percentage says, since a real impervious surface does not
    # show meaningful photosynthetic reflectance. 0.2 is a conservative
    # floor (well below typical healthy-canopy NDVI of 0.4+), chosen to
    # only override clear classifier errors, not to broadly disable the
    # built-up filter.
    "builtup_ndvi_override_threshold": 0.2,

    # --- 03_emu_delineation ---------------------------------------------
    "emu_delineation_method": "auto",    # auto | segmentation | ecological_clustering | client_zones
    "emu_min_tiles": 3,                  # matches Darukaa's existing EII limiting-factor minimum-replication convention
    "emu_min_area_ha": None,             # None = no floor; else sub-threshold tiles flagged low-confidence
    "stratification_attributes": [],     # canonical attribute names usable as clustering features
                                          # e.g. ["plantation_year", "plantation_type", "admin_block"]
                                          # ONLY used if present in the parsed data — see CHANGELOG
    "n_devices": None,                   # REQUIRED for K_max auto-tune
    "project_duration_weeks": None,      # REQUIRED for K_max auto-tune
    # For a project spanning multiple discrete seasons (e.g. 24 weeks =
    # 3x8-week seasons), the weekly position rotation resets at each
    # season boundary instead of running as one continuous cycle — needed
    # for valid season-to-season comparison at a fixed point (see
    # build_weekly_rotation's docstring for the real reasoning and the
    # mistake this corrected). None (default) = no reset, single
    # continuous rotation for the whole project_duration_weeks.
    "season_length_weeks": None,
    # When True, each real value of hard_barrier_attribute becomes exactly
    # one EMU directly — no further segmentation-based sub-clustering
    # within it. Default False preserves the existing behaviour (a real
    # zone/partition may still be split into multiple EMUs by SNIC
    # segmentation or K-means clustering) for every project that hasn't
    # opted into this simpler model.
    "zone_is_emu": False,
    # When True, an EMU whose real capacity at the standard
    # min_device_spacing_m is below 3 positions gets a second attempt at
    # a relaxed (min 50m) spacing floor — real trade-off (some acoustic
    # overlap risk) only taken for genuinely small EMUs, and always
    # reported explicitly. Default False — every project keeps the full
    # spacing guarantee everywhere unless it opts in.
    "allow_small_emu_spacing_relaxation": False,
    # A real, client-declared preference that camera trap should never be
    # assigned to specific EMUs (e.g. a small biodiversity-value anchor
    # the client wants sampled by audiomoth only). Empty by default —
    # every existing project's camera trap logic is unaffected.
    "camera_trap_excluded_emus": [],
    # A real, client-declared preference that at least N of an EMU's
    # position pool should fall within a specific named sub-area polygon
    # (e.g. an island within a wetland, more accessible for the field
    # team than the wetland's other real candidates). Empty by default.
    # Structure: {emu_id: {"subarea_placemark_name": str, "min_positions_in_subarea": int}}
    "position_pool_named_subarea_bias": {},

    # A one-time baseline-survey design is a genuinely different goal from
    # a long-term, same-position, season-long comparison regime — a
    # project may only need each EMU sampled ONCE, not every week.
    # "continuous_multi_week" = the season-long comparison regime.
    # "stratified_single_pass" = each EMU gets exactly one
    # assigned week; multiple devices may be assigned to it that week,
    # proportional to its size/capacity; EMUs sharing a week split that
    # week's devices proportionally.
    "sampling_design": "continuous_multi_week",

    # Minimum real-world spacing between two simultaneous device positions
    # in the SAME EMU in the SAME week. Value and derivation confirmed
    # directly against the real Tata Motors methodology document (P5:
    # "Independence is derived, not assumed — minimum spacing comes from
    # the instrument detection distance"): effective acoustic detection
    # radius is 25-50m in vegetated habitat; the upper bound (50m) is used
    # and DOUBLED, so two recorders' detection zones cannot overlap even
    # under favourable conditions. Not a site-specific acoustic model of
    # THIS site — reused from the validated TM derivation as the same
    # instrument class (passive acoustic monitors) is used here.
    "min_device_spacing_m": 100.0,
    # Day 1 = deployment, days 2-6 = 5 recording days, Day 7 = retrieval +
    # data transfer, Day 8 = buffer, Day 9 = next deployment. That's
    # cycle_length=7 (day 1 through day 7 inclusive: deploy+record+retrieve)
    # and logistics_buffer=1 (day 8 only) — an 8-day turnover.
    "cycle_length_days": 7,
    "logistics_buffer_days": 1,
    # Proxy for "real ecological discontinuity" used to hard-partition
    # candidates before clustering (declared approximation — see
    # ecological_clustering.py docstring; no real river/mountain GIS layer
    # available yet). Must be a canonical attribute name prefixed `attr_`
    # as it appears in 01_ingestion's output properties.
    "hard_barrier_attribute": "attr_admin_district",

    # HARD cap: neither a spatial connectivity constraint nor adding x/y
    # as Gower features is enough on its own to stop clustering
    # "chaining" (every consecutive pair of members close, but the overall
    # span still enormous). Any final EMU whose member centroids span more
    # than this
    # many km gets split into spatially-compact sub-groups as a
    # post-processing step — see ecological_clustering.py's
    # _enforce_spatial_compactness().
    "max_emu_spatial_diameter_km": 5.0,

    # Names of exclusion-zone placemarks that are actual WATER FEATURES
    # (ponds, lakes, artificial waterbodies)
    # rather than infrastructure — used ONLY to build a real, per-project
    # waterbody asset for the optional GEE aquatic export. Distinct from
    # exclusion_placemark_names (which controls terrestrial candidate
    # exclusion) — a feature can be both: excluded from terrestrial
    # tessellation AND exported as a real waterbody for aquatic covariates.
    "water_feature_placemark_names": [],

    # --- contiguous-archetype grid generation (see candidate_grid.py) ----
    # Cell size for the dense tessellation used ONLY for conservation/
    # industrial archetypes — smaller than SNIC's ~100m default seed
    # spacing (SNIC_SIZE_PIXELS=10 @ 10m) so several cells fall inside one
    # expected segment, giving segmentation_reconciliation.py real
    # sub-structure to work with instead of one mode-reduced value per
    # huge hand-drawn zone polygon.
    "contiguous_grid_cell_size_m": 25,

    # Short, clean prefix for candidate/position display names — e.g. "SFV"
    # produces "SFV-T0001" instead of the internal "grid_00001", the
    # convention used in client-facing popups and exports. Defaults to
    # "T" (generic "Terrestrial") if a project doesn't set its own —
    # explicit per-project is better than a clever auto-derivation from
    # project_name, since this is genuinely a naming-convention choice.
    "id_prefix": "T",

    # --- 04_deployment_planning ------------------------------------------
    "deployment_regime": "sequential_cluster",  # continuous_proportional | sequential_cluster
    "max_panel_travel_hours": 4.0,       # auto-tune target: max single-day field travel per panel
    "avg_travel_speed_kmh": 25.0,        # declared approximation for panel travel-time estimate — see panel_scheduler.py

    # Calendar anchor for the deployment schedule export (CSV/Excel) — real
    # dates, not just day-offsets. None means "not yet decided"; the export
    # then falls back to relative day-offset labels instead of guessing a
    # date.
    "project_start_date": None,  # e.g. "2026-09-06" — set per project
    # Policy: devices can NEVER be added to
    # solve an infeasible schedule. Duration may extend by at most this
    # many weeks, and only as a last resort when nothing else closes the
    # gap — never silently, always reported as an explicit trade-off.
    "max_duration_extension_weeks": 1,
    "streams_active": ["audiomoth"],     # subset of common/streams.py registry

    # Camera trap gets its own small, project-wide (not per-EMU) position
    # pool and weekly rotation. Only used if "camera_trap" is in
    # streams_active.
    "camera_trap_n_devices": 2,
    "camera_trap_pool_size": 4,

    # --- 05_metrics_rollup -------------------------------------------------
    "small_tile_area_ha_floor": 0.25,    # below this, parcel-intrinsic metrics flagged low-confidence
    "landscape_buffer_m": {              # per-indicator-family buffer radius, metres
        "connectivity": 1000,
        "natural_habitat_pct": 1000,
        "fragmentation": 1000,
    },
    "aggregation_rule": "profile_first_noncompensatory",  # locked Darukaa standard (son_score.py pattern)

    # --- 06_reporting --------------------------------------------------
    "report_format": "html",
}

REQUIRED_KEYS = ["client_name", "project_name", "archetype"]
VALID_ARCHETYPES = {"agroforestry", "conservation", "industrial"}
VALID_EMU_METHODS = {"auto", "segmentation", "ecological_clustering", "client_zones"}
VALID_REGIMES = {"continuous_proportional", "sequential_cluster"}


class ConfigError(ValueError):
    pass


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str | Path) -> Dict[str, Any]:
    """Load a project's config.yaml, merge over DEFAULTS, validate, return
    the resolved dict. Raises ConfigError with a specific, actionable
    message on any problem — never silently falls back on a bad value."""
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"config.yaml not found at {path}")

    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    cfg = _deep_merge(DEFAULTS, raw)
    _validate(cfg, path)
    logger.info("Loaded config for %s / %s (archetype=%s)",
                cfg["client_name"], cfg["project_name"], cfg["archetype"])
    return cfg


def _validate(cfg: Dict[str, Any], path: Path) -> None:
    missing = [k for k in REQUIRED_KEYS if not cfg.get(k)]
    if missing:
        raise ConfigError(f"{path}: missing required config key(s): {missing}")

    if cfg["archetype"] not in VALID_ARCHETYPES:
        raise ConfigError(
            f"{path}: archetype={cfg['archetype']!r} not in {VALID_ARCHETYPES}")

    if cfg["emu_delineation_method"] not in VALID_EMU_METHODS:
        raise ConfigError(
            f"{path}: emu_delineation_method={cfg['emu_delineation_method']!r} "
            f"not in {VALID_EMU_METHODS}")

    if cfg["deployment_regime"] not in VALID_REGIMES:
        raise ConfigError(
            f"{path}: deployment_regime={cfg['deployment_regime']!r} "
            f"not in {VALID_REGIMES}")

    if cfg["n_devices"] is not None and cfg["n_devices"] < 1:
        raise ConfigError(f"{path}: n_devices must be >= 1")

    if cfg["emu_min_tiles"] < 1:
        raise ConfigError(f"{path}: emu_min_tiles must be >= 1")

    strat_attrs = cfg.get("stratification_attributes") or []
    known_canonical = set(cfg["attribute_crosswalk"].keys())
    unknown = [a for a in strat_attrs if a not in known_canonical]
    if unknown:
        raise ConfigError(
            f"{path}: stratification_attributes {unknown} are not canonical "
            f"names declared in attribute_crosswalk. Known: {sorted(known_canonical)}")
