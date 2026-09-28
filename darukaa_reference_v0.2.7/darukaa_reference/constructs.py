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
NET_CHANGE_EARLY_YEARS = (2017, 2018)

# Aquatic constructs
FAI_BLOOM_THRESHOLD = 0.005            # Darukaa choice (audit item 14)
TSM_NECHAD_A, TSM_NECHAD_C = 228.1, 0.1641
TSM_MAX = 1000.0
PURE_WATER_ERODE_PX = 1                # one-pixel erosion removes mixed shoreline pixels
RIPARIAN_RING_WIDTH_M = 100.0          # E3 (Darukaa choice)

# EDPP / MSPL: ABSOLUTE thermal scaling (v0.2.7 scaled by the site's own LST min/max, X3).
# 20-40 degC is a Darukaa choice, unvalidated; both indicators are screening/context.
THERMAL_MIN_C, THERMAL_MAX_C = 20.0, 40.0
MSPL_WEIGHTS = {"nutrient": 0.35, "thermal": 0.30, "turbidity": 0.20, "water_persistence": 0.15}

# Native scales (verified where noted in the audit)
GHM_NATIVE_M = 90.0                    # TNC HM v3, verified
