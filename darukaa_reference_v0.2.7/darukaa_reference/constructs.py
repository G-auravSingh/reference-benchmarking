"""
constructs.py -- shared construct constants (v0.2.8 Phase 3)
============================================================
No imports, so both the numpy reference definitions (reference_builders.py) and the Earth
Engine code (indicators/__init__.py) can import the SAME numbers. A test asserts these equal
the legacy module-level constants, so the two implementations cannot drift apart.
"""

# Dynamic World label ids
DW_WATER, DW_TREES, DW_GRASS, DW_FLOODED_VEG, DW_CROPS = 0, 1, 2, 3, 4
DW_SHRUB_SCRUB, DW_BUILT, DW_BARE, DW_SNOW_ICE = 5, 6, 7, 8
NATURAL_CLASSES = (DW_TREES, DW_GRASS, DW_FLOODED_VEG, DW_SHRUB_SCRUB)
DISTURBED_CLASSES = (DW_CROPS, DW_BUILT, DW_BARE)

# Hansen Global Forest Change v1.13
HANSEN_CANOPY_THRESHOLD_PCT = 30
HANSEN_LOSSYEAR_FIRST, HANSEN_LOSSYEAR_LAST = 1, 25          # 2001 .. 2025 inclusive
# (label, first lossyear code, last lossyear code). Years in a window = last - first + 1.
FOREST_LOSS_WINDOWS = (
    ("loss_longterm_2001_2025", 1, 25),     # 25 years
    ("loss_recent_2020_2025", 20, 25),      # 6 years
    ("loss_current_2023_2025", 23, 25),     # 3 years
)
FOREST_LOSS_PRIMARY_WINDOW = "loss_longterm_2001_2025"


def years_in_window(first_code: int, last_code: int) -> int:
    """Inclusive year count. v0.2.7 divided the 2001-2025 window by 24 (and 2020-2025 by 5,
    2023-2025 by 2): an off-by-one in every window."""
    return int(last_code) - int(first_code) + 1


# Net forest change (D5): same product, same compositing, two periods
NET_CHANGE_EARLY_YEARS = (2017, 2018)     # decision 8: current configurable early comparison period

# Aquatic constructs
FAI_BLOOM_THRESHOLD = 0.005            # Darukaa choice (audit item 14)
TSM_NECHAD_A, TSM_NECHAD_C = 228.1, 0.1641
TSM_MAX = 1000.0
PURE_WATER_ERODE_PX = 1                # one-pixel erosion removes mixed shoreline pixels
# Explicit POPULATION rule shared by the numpy definition and the tiled Earth Engine builder: a water body (target or reference)
# is eligible only if its bounding-box extent is <= this. It is what lets every Earth Engine request stay bounded WITHOUT silently
# changing the population near tile edges (a body owned by a tile is then always fully inside that tile's region). A very
# elongated body (channel / river reach) is not a comparable "water body" for these indicators. Darukaa choice; configurable.
MAX_WATER_BODY_EXTENT_M = 2000.0
# CANONICAL water-body PERMANENCE (used to match comparable bodies, decision E2): the mean of the continuous Sentinel-1 water OCCURRENCE
# (share of dates classified water, indicators._s1_water_occurrence) over the water BODY'S OWN pixels, reduced on the S1 native 10 m grid.
# ONE definition for every aquatic indicator, whatever the indicator's own native grid (sabf 20 m) or unit (water body / riparian ring):
# a ring is matched on the permanence of the BODY it surrounds, never on the ring's land pixels (run 2: ring 0.031 vs body 0.91).
PERMANENCE_SCALE_M = 10.0
PERMANENCE_CONSISTENCY_TOL = 0.05     # a CHECK, not methodology: the same body's permanence measured on 10 m and 20 m grids must agree within this
RIPARIAN_RING_WIDTH_M = 100.0          # decision 7: current configurable methodology parameter (Darukaa choice)
WOODY_MIN_TREE_FRACTION = 0.10         # site counts as a woody ecosystem when >= 10 % of it is DW trees (FLII precedent)

# EDPP / MSPL thermal term (decision 6): NO ecological temperature bound is adopted.
# v0.2.7 scaled LST by the SITE's own min/max (X3). v0.2.8 first tried 20-40 degC, an unsupported
# ecological guess, and that is withdrawn. The thermal term is now scaled over the SOURCE PRODUCT's
# documented physical valid range, which is a numerical / QC bound only:
#   Landsat Collection 2 Level-2 surface temperature: valid DN 293-65535, scale 0.00341802, offset 149.0
#   (USGS "How do I use a scale factor with Landsat Level-2 science products?") -> 150.0 K to 373.0 K.
# Values outside it are masked as invalid. Within that range the scaling is absolute (site-independent) but
# NOT ecologically calibrated: EDPP / MSPL are screening / context and are not scored.
LST_SCALE_FACTOR, LST_OFFSET_K = 0.00341802, 149.0
LST_VALID_DN_MIN, LST_VALID_DN_MAX = 293, 65535
KELVIN_TO_CELSIUS = 273.15
LST_QC_MIN_C = LST_VALID_DN_MIN * LST_SCALE_FACTOR + LST_OFFSET_K - KELVIN_TO_CELSIUS     # -123.15 degC
LST_QC_MAX_C = LST_VALID_DN_MAX * LST_SCALE_FACTOR + LST_OFFSET_K - KELVIN_TO_CELSIUS     #   99.85 degC
MSPL_WEIGHTS = {"nutrient": 0.35, "thermal": 0.30, "turbidity": 0.20, "water_persistence": 0.15}

# Native scales (verified where noted in the audit)
GHM_NATIVE_M = 90.0                    # TNC HM v3, verified


# Polygon site-support convention (frozen at the smoke-test review): see support.SITE_SUPPORT_CONVENTION.
SITE_SUPPORT_CONVENTION = "polygon_coverage_weighted"
