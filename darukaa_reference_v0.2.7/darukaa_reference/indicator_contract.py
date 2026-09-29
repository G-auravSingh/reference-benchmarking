"""
indicator_contract.py -- v0.2.8 scientific indicator contract (Phase 1: FROZEN SPEC)
===================================================================================

This module is the machine-readable form of SCORING_ARCHITECTURE_v0.2.8.md. It is a
SPECIFICATION: nothing in the running pipeline reads it yet, so it changes no behaviour.
It is wired into scoring indicator-by-indicator in Phase 3+, and an indicator can only be
marked `validated=True` when its current_defects are empty and it has validation evidence
(synthetic fixture + live tile).

KEY SEPARATIONS (each is its own field; none is inferred from another)
  reference_tier       -- only a CLASSIFICATION of the reference population
                          (tier1 = regional, tier2 = stratified / least-disturbed,
                           absolute = fixed reference level). NOT scoreability.
  proposed_scoreability-- the audited target status (scoreable / contextual / screening /
                          pending_methodology / removed). PROPOSED, not active.
  validated            -- True only after Phases 3-6 evidence exists.
  site_support vs reference_support -- must be the matched pair (support.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from darukaa_reference.support import MATCHED_REFERENCE_SUPPORT, SITE_SUPPORTS

# ------------------------------------------------------------------------------ vocabulary
DOMAINS = ("terrestrial", "aquatic", "mixed")
CONSTRUCTS = ("C1_landscape", "C2_vegetation", "C3_fauna", "C4_pressure")
PRESSURE_CONSTRUCTS = ("C4_pressure",)

REFERENCE_POPULATIONS = (
    "regional_all",                 # all valid units in the reference zone (tier1)
    "regional_ecoregion",           # all valid site-sized windows in the ecoregion within the reference radius;
                                    #   NO land-cover stratification and NO pressure filter (tier1)
    "least_disturbed_stratum",      # ecoregion + ecosystem stratum + low-HMI selection (tier2)
    "regional_stratum_unfiltered",  # ecoregion + ecosystem stratum, NO pressure filter (ghm, item 3)
    "absolute_level",               # a fixed reference level (e.g. 100 % natural)
    "comparable_water_bodies",      # water bodies matched on size / permanence / basin
    "comparable_riparian_rings",    # rings of those comparable water bodies
    "none",
)
REFERENCE_TIERS = ("tier1", "tier2", "absolute", None)
SCOREABILITY = ("scoreable", "contextual", "screening", "pending_methodology", "removed")
ESTIMATORS = ("log_response_ratio", "robust_z", "reference_percentile", None)
DIRECTIONS = ("higher_is_better", "lower_is_better", "none")
ECOSYSTEMS = ("any", "woody", "open_water")

# Per-site-per-indicator status (Phase 8). Every non-scored indicator carries one + a reason.
INDICATOR_STATUSES = (
    "not_applicable",
    "applicable_but_no_site_value",
    "applicable_but_no_reference",
    "reference_available_but_not_scoreable",
    "scored",
    "contextual_only",
    "screening_only",
    "suppressed_for_stability",
    "pending_methodology",
)
NOT_APPLICABLE_REASONS = (
    "domain_mismatch",              # e.g. aquatic indicator on a terrestrial tile
    "ecosystem_type_mismatch",      # e.g. canopy height on grassland
    "target_feature_absent",        # e.g. no water body / forest baseline < 5 ha
    "site_below_product_resolution",# site support rule (audit X6)
    "insufficient_pure_water",      # fewer pure-water pixels than required
)

# ---- Explicit, documented thresholds (v0.2.8 decisions D3, E2; the values are configurable per contract)
GENERIC_MIN_NATIVE_PIXELS = 10        # hard applicability floor (D3). NOT a statistical-sufficiency claim.
MIN_PURE_WATER_PIXELS = 10            # aquatic: >= 10 pure-water pixels AND a valid water-body geometry (D3)
FOREST_BASELINE_MIN_M2 = 50_000.0     # 5 ha of >=30 % canopy baseline forest (forest_loss_rate applicability)
MIN_REFERENCE_WINDOWS = 30            # documented minimum reference windows (proposal; configurable)
MIN_COMPARABLE_WATER_BODIES = 10      # documented minimum comparable reference water bodies (E2; proposal)
WATER_BODY_AREA_RATIO = 3.0           # comparable if area within [1/3, 3] x target (E2)
WATER_BODY_PERMANENCE_TOL = 0.25      # comparable if |permanence difference| <= 0.25 (E2)
MAX_WATER_BODY_EXTENT_M = 2000.0      # POPULATION RULE (Darukaa choice, needs confirmation): a target or comparable water body has a bounding-box
                                      # extent <= this. It is what lets Earth Engine tile the region without changing the population (see constructs).
SITE_SUPPORT_CONVENTION = "polygon_coverage_weighted"   # frozen at the smoke-test review: every polygon site metric is the coverage-weighted mean
# Decision 5: the percentile convention is defined ONCE, here, and implemented in benchmarking.percentile_benchmark.
PERCENTILE_CONVENTION = ("mid-rank empirical CDF of the reference units, oriented so that a HIGHER score is always "
                         "BETTER: score = P(reference worse than site) + 0.5 * P(reference tied with site); "
                         "'worse' means lower for higher_is_better indicators and higher for lower_is_better ones; "
                         "ties are within isclose(rtol=1e-9, atol=1e-12); score is already in [0, 1], no logistic")
# Decision 2: the pressure-indicator support rule, stated once and referenced by every exempt contract.
PRESSURE_SUPPORT_RULE = ("Pressure-indicator support rule: ghm, hdi and light_pollution are LANDSCAPE-PRESSURE "
                         "indicators. Their value describes the landscape around a site at the product's own "
                         "resolution, so they are exempt from the generic condition-polygon floor (10 native "
                         "pixels): a site smaller than the product pixel reports the covering pixel(s) and is "
                         "flagged below_generic_floor_landscape_pressure_exempt. Condition indicators are NOT exempt.")
FLOOR_BASES = ("polygon_native_pixels", "pure_water_pixels", "exempt_landscape_pressure")
IMPLEMENTATION_STATUSES = ("v0.2.7_legacy", "v0.2.8_synthetic_tested", "blocked", "v0.2.8_live_validated")

# Reference populations appropriate to each construct type (audit X8).
CONDITION_POPULATIONS = {"least_disturbed_stratum", "absolute_level", "regional_ecoregion",
                         "comparable_water_bodies", "comparable_riparian_rings"}
PRESSURE_POPULATIONS = {"regional_all", "regional_ecoregion", "regional_stratum_unfiltered",
                        "comparable_water_bodies", "comparable_riparian_rings"}
# Variables used to SELECT each reference population (audit X2: an indicator may not use them
# as inputs when benchmarked against that population).
POPULATION_SELECTORS = {"least_disturbed_stratum": {"hmi", "dw_label"},
                        "regional_stratum_unfiltered": {"dw_label"}}

REDUNDANCY_GROUPS = {   # Phase 7: aggregation rules still to be defined
    "R1_vegetation_signal": "NDVI / habitat health / LAI / CHM",
    "R2_human_modification": "gHM / EII-structural / FLII",
    "R3_compositional_intactness": "BII / EII-compositional",
    "R4_trophic_signal": "TSPI / IRI / MSPL",
    "R5_built_up": "HDI / IRI",
}


@dataclass(frozen=True)
class Applicability:
    """Applicability rules, all explicit.

    min_native_pixels          generic HARD floor (D3): the site must contain at least this many
                               native pixels. It is an applicability floor, not a claim that 10
                               pixels are statistically sufficient.
    indicator_min_native_pixels  stricter, indicator-specific floor where scientifically justified
                               (must be >= the generic floor; rationale in min_support_rationale).
    floor_basis                'polygon_native_pixels' (default), 'pure_water_pixels' (aquatic:
                               >= min_pure_water_pixels pure-water pixels + valid water-body
                               geometry) or 'exempt_landscape_pressure' (a landscape-level pressure
                               whose value describes the surrounding landscape at the product's
                               resolution; exempt from the polygon floor, flagged in the report).
    """
    domains: Tuple[str, ...]
    ecosystem: str = "any"
    requires_feature: Optional[str] = None      # "water_body" | "forest_baseline_5ha" | None
    min_native_pixels: Optional[int] = GENERIC_MIN_NATIVE_PIXELS
    min_pure_water_pixels: Optional[int] = None
    indicator_min_native_pixels: Optional[int] = None
    floor_basis: str = "polygon_native_pixels"


def effective_min_native_pixels(c: "IndicatorContract") -> Optional[int]:
    """The polygon-pixel floor that actually applies (None when the basis is not the polygon)."""
    ap = c.applicability
    if ap.floor_basis != "polygon_native_pixels":
        return None
    return max(ap.min_native_pixels or 0, ap.indicator_min_native_pixels or 0)


@dataclass(frozen=True)
class IndicatorContract:
    name: str
    definition: str
    construct: str
    subdimension: str
    site_support: str
    reference_support: str
    reference_population: str
    reference_tier: Optional[str]
    proposed_scoreability: str
    scoreability_reason: str
    estimator: Optional[str]
    direction: str
    temporal: str
    native_resolution_m: Optional[float]
    resolution_verified: bool
    applicability: Applicability
    inputs: Tuple[str, ...] = ()
    redundancy_groups: Tuple[str, ...] = ()
    requires_sensitivity_check: bool = False
    image_is_single_band: bool = True
    site_relative_normalisation: bool = False
    limitations: Tuple[str, ...] = ()
    current_defects: Tuple[str, ...] = ()        # gap between v0.2.7 code and this contract
    validated: bool = False
    validation_evidence: Tuple[str, ...] = ()
    # ---- v0.2.8 Phase 3 additions
    min_reference_n: Optional[int] = None        # documented minimum reference units (windows / water bodies)
    min_support_rationale: str = ""              # why an indicator-specific floor / exemption applies
    expects_tied_reference: bool = False         # zero-inflated or tie-heavy reference: percentile estimator only
    diagnostics: Tuple[str, ...] = ()            # contextual diagnostics reported beside (never inside) the score
    implementation_status: str = "v0.2.7_legacy"
    synthetic_tests: Tuple[str, ...] = ()        # names of the synthetic fixtures with known answers
    parameters: Tuple[Tuple[str, object], ...] = ()   # explicit, configurable methodology parameters (decisions 7, 8)


# ------------------------------------------------------------------------------ validator
def validate_contract(c: IndicatorContract) -> List[str]:
    """Rules every contract must satisfy. Returns human-readable violations (empty = ok)."""
    v: List[str] = []
    if c.site_support not in SITE_SUPPORTS:
        v.append(f"unknown site_support {c.site_support!r}")
    if c.reference_population not in REFERENCE_POPULATIONS:
        v.append(f"unknown reference_population {c.reference_population!r}")
    if c.reference_tier not in REFERENCE_TIERS:
        v.append(f"unknown reference_tier {c.reference_tier!r}")
    if c.proposed_scoreability not in SCOREABILITY:
        v.append(f"unknown scoreability {c.proposed_scoreability!r}")
    if c.estimator not in ESTIMATORS:
        v.append(f"unknown estimator {c.estimator!r}")
    if c.direction not in DIRECTIONS:
        v.append(f"unknown direction {c.direction!r}")
    if c.construct not in CONSTRUCTS:
        v.append(f"unknown construct {c.construct!r}")
    if c.applicability.ecosystem not in ECOSYSTEMS:
        v.append(f"unknown ecosystem {c.applicability.ecosystem!r}")
    if not set(c.applicability.domains) <= set(DOMAINS) or not c.applicability.domains:
        v.append("applicability.domains must be a non-empty subset of DOMAINS")
    for g in c.redundancy_groups:
        if g not in REDUNDANCY_GROUPS:
            v.append(f"unknown redundancy group {g!r}")
    if c.implementation_status not in IMPLEMENTATION_STATUSES:
        v.append(f"unknown implementation_status {c.implementation_status!r}")
    ap = c.applicability
    if ap.floor_basis not in FLOOR_BASES:
        v.append(f"unknown floor_basis {ap.floor_basis!r}")
    if ap.indicator_min_native_pixels is not None:
        if ap.indicator_min_native_pixels < GENERIC_MIN_NATIVE_PIXELS:
            v.append("indicator_min_native_pixels must not be below the generic floor")
        if not c.min_support_rationale:
            v.append("an indicator-specific support floor needs a min_support_rationale")
    if c.estimator in ("robust_z", "log_response_ratio") and c.expects_tied_reference:
        v.append("a zero-inflated / tied reference must use the reference_percentile estimator, "
                 "never robust_z / log_response_ratio")

    # Support: the reference unit must be the site unit's matched counterpart
    expected = "absolute_level" if c.reference_population == "absolute_level" \
        else MATCHED_REFERENCE_SUPPORT.get(c.site_support)
    if c.reference_population != "none" and c.reference_support != expected:
        v.append(f"support mismatch: site {c.site_support} requires reference {expected}, "
                 f"contract says {c.reference_support}")

    if c.proposed_scoreability == "scoreable":
        if c.reference_population == "none":
            v.append("scoreable indicator needs a reference population")
        if c.estimator is None:
            v.append("scoreable indicator needs an estimator (benchmark formula)")
        if c.direction == "none":
            v.append("scoreable indicator needs a direction")
        if not c.temporal:
            v.append("scoreable indicator needs a temporal specification")
        if c.native_resolution_m is None:
            v.append("scoreable indicator needs a known native resolution")
        if c.site_relative_normalisation:
            v.append("site-relative normalisation is not comparable with any reference (X3)")
        if not c.image_is_single_band:
            v.append("reference image must be single-band and the site construct (X4)")
        pressure = c.construct in PRESSURE_CONSTRUCTS
        allowed = PRESSURE_POPULATIONS if pressure else CONDITION_POPULATIONS
        if c.reference_population not in allowed:
            kind = "pressure" if pressure else "condition"
            v.append(f"{kind} indicator cannot be scored against {c.reference_population} (X8)")
        clash = POPULATION_SELECTORS.get(c.reference_population, set()) & set(c.inputs)
        if clash:
            v.append(f"circular reference: inputs {sorted(clash)} also select the population (X2)")
        if c.min_reference_n is None or c.min_reference_n < 2:
            v.append("scoreable indicator needs a documented minimum reference n (min_reference_n)")
        if ap.floor_basis == "polygon_native_pixels":
            if (ap.min_native_pixels or 0) < GENERIC_MIN_NATIVE_PIXELS:
                v.append("polygon-based indicator needs the hard floor min_native_pixels >= 10 (D3)")
        elif ap.floor_basis == "pure_water_pixels":
            if ap.requires_feature != "water_body" or (ap.min_pure_water_pixels or 0) < MIN_PURE_WATER_PIXELS:
                v.append("pure-water floor needs requires_feature='water_body' and >= 10 pure-water pixels (D3)")
        elif ap.floor_basis == "exempt_landscape_pressure":
            if not pressure or not c.min_support_rationale:
                v.append("only a pressure indicator with a rationale may be exempt from the polygon floor")
        if ap.requires_feature == "water_body":
            if (ap.min_pure_water_pixels or 0) < MIN_PURE_WATER_PIXELS:
                v.append("water-body indicator needs the minimum pure-water pixel rule (>= 10)")
            if c.reference_population in ("comparable_water_bodies", "comparable_riparian_rings") \
                    and (c.min_reference_n or 0) < 5:
                v.append("comparable-water-body reference needs a documented minimum number of comparable bodies")
        if "water_body" == c.applicability.requires_feature and c.applicability.min_pure_water_pixels is None:
            v.append("water-body indicator needs a minimum pure-water pixel rule")

    if c.validated:
        if c.current_defects:
            v.append("cannot be validated while current_defects remain")
        if not c.validation_evidence:
            v.append("validated requires validation_evidence")
        if not c.resolution_verified:
            v.append("validated requires a verified native resolution")
    return v


def redundancy_conflicts(contracts: Dict[str, IndicatorContract]) -> Dict[str, List[str]]:
    """Groups with more than one proposed-scoreable member. Phase 7 must define an
    aggregation rule for each before the headline is computed."""
    out: Dict[str, List[str]] = {}
    for g in REDUNDANCY_GROUPS:
        members = sorted(n for n, c in contracts.items()
                         if g in c.redundancy_groups and c.proposed_scoreability == "scoreable")
        if len(members) > 1:
            out[g] = members
    return out


# ------------------------------------------------------------------------------ the frozen table
T, A, M = "terrestrial", "aquatic", "mixed"
TM, AM, TAM = (T, M), (A, M), (T, A, M)


def _ctx(name, definition, construct, subdim, site_support, reason, native, verified, domains,
         inputs=(), groups=(), defects=(), limits=(), status="contextual", **kw):
    """Shorthand for a non-scored contract (contextual / screening / pending / removed)."""
    ref_support = MATCHED_REFERENCE_SUPPORT.get(site_support, "none")
    pop = kw.pop("population", "none" if ref_support == "none" else "regional_all")
    return IndicatorContract(
        name=name, definition=definition, construct=construct, subdimension=subdim,
        site_support=site_support, reference_support=ref_support if pop != "none" else "none",
        reference_population=pop, reference_tier=kw.pop("tier", "tier1" if pop != "none" else None),
        proposed_scoreability=status, scoreability_reason=reason, estimator=kw.pop("estimator", None),
        direction=kw.pop("direction", "none"), temporal=kw.pop("temporal", ""),
        native_resolution_m=native, resolution_verified=verified,
        applicability=Applicability(domains=domains, **kw.pop("app", {})),
        inputs=inputs, redundancy_groups=groups, current_defects=defects, limitations=limits, **kw)


CONTRACTS: Dict[str, IndicatorContract] = {c.name: c for c in [
    # ---------------------------------------------------------------- C1 landscape
IndicatorContract(
        "natural_habitat", "Share of the site in natural Dynamic World classes (trees, grass, flooded veg, shrub).",
        "C1_landscape", "extent", "polygon_proportion", "site_window_proportion", "regional_ecoregion", "tier1",
        "scoreable", "D2: departure from REGIONAL condition = percentile of the site among site-sized windows "
        "of the ecoregion. Departure from an ideal (100 % natural) is reported separately as a diagnostic.",
        "reference_percentile", "higher_is_better", "annual:ndvi_year (DW mode)", 10.0, False,
        Applicability(TM, "any", None, 10), inputs=("dw_label",),
        min_reference_n=MIN_REFERENCE_WINDOWS, expects_tied_reference=True,
        diagnostics=("absolute_natural_reference",),
        limitations=("Generic 10-native-pixel floor (decision 1): a share from 10-99 pixels is coarse (resolution "
                     "1/n); the reference cells are the same size, so the comparison stays like-for-like.","Windows are centred on ecoregion pixels of any land cover (no class stratification) so the "
                     "reference is the regional condition, not a like-for-like habitat comparison.",
                     "Reference is tie-heavy where much of the ecoregion is 100 % natural: percentile, not z-score."),
        implementation_status="v0.2.8_synthetic_tested",
        synthetic_tests=("test_natural_habitat_regional_window_reference_and_absolute_diagnostic",
                         "test_binary_proportion_reference_recovers_regional_proportion_and_has_spread")),
    _ctx("natural_landcover", "Naturalness-weighted DW cover (1 / 0.5 mixed / 0).", "C1_landscape", "extent",
         "polygon_proportion", "Redundant with natural_habitat (same DW input and subdimension).", 10.0, False, TM,
         inputs=("dw_label",), defects=("X1", "X2a")),
    IndicatorContract(
        "cpland", "Share of the site that is core habitat (PV binary eroded by the edge depth).",
        "C1_landscape", "configuration", "polygon_proportion", "site_window_proportion",
        "least_disturbed_stratum", "tier2", "pending_methodology",
        "Blocked until the Darukaa PV_Binary_2025 asset provenance is documented.",
        "robust_z", "higher_is_better", "static:PV_Binary_2025", None, False,
        Applicability(TM, "any", None, 10), inputs=("pv_binary",),
        current_defects=("reference is the raw binary, site is eroded core area (live T1 ref = 0)",
                         "PV binary provenance undocumented")),
IndicatorContract(
        "forest_loss_rate", "Gross tree-cover loss rate: Hansen loss area in window / 2000 forest (>=30 % canopy) area / years.",
        "C1_landscape", "disturbance_regime", "polygon_rate", "site_window_rate", "least_disturbed_stratum",
        "tier2", "scoreable", "E1: same rate for site and site-sized reference windows; empirical percentile "
        "because the reference is strongly zero-inflated.",
        "reference_percentile", "lower_is_better", "window:Hansen v1.13 lossyear 1-25 (2001-2025), 25 years", 30.0, True,
        Applicability(TM, "woody", "forest_baseline_5ha", 10), inputs=("hansen_gfc",),
        min_reference_n=MIN_REFERENCE_WINDOWS, expects_tied_reference=True,
        limitations=("Zero-loss reference windows are common: ties get mid-rank, tie fraction is reported.",
                     "Reference windows need >= 5 ha baseline forest, like the site.",
                     "Windows are centred on pixels satisfying the stratum / HMI criteria."),
        implementation_status="v0.2.8_synthetic_tested",
        synthetic_tests=("test_forest_loss_site_and_reference_are_the_same_rate",
                         "test_forest_loss_windows_use_correct_year_counts",
                         "test_percentile_lower_is_better_with_zero_inflated_reference")),
IndicatorContract(
        "net_tree_cover_change_rate", "Change in Dynamic World tree-cover share between an early and a recent period, percentage "
        "points per year (one product, identical compositing at both endpoints): a remote-sensing "
        "tree-cover proxy, not direct forest-area gain/loss.",
        "C1_landscape", "restoration_trajectory", "polygon_mean", "site_window_mean", "regional_ecoregion",
        "tier1", "scoreable", "Single-product change; site and reference windows use the same difference image. "
        "Population is NOT land-cover stratified (the stratum is chosen from the same DW classes the change is "
        "measured on: selection on the outcome, X2).",
        "reference_percentile", "higher_is_better",
        "early:2017-2018 vs recent:(ndvi_year-1)-ndvi_year, DW annual-mode composites, full calendar years", 10.0, False,
        Applicability(TM, "any", None, 10), inputs=("dw_label",),
        min_reference_n=MIN_REFERENCE_WINDOWS, expects_tied_reference=True,
        parameters=(("early_years", (2017, 2018)),),
        limitations=("Generic 10-native-pixel floor (decision 1).",
                     "REMOTE-SENSING TREE-COVER PROXY, not direct forest-area gain/loss (decision 9): DW 'trees' can "
                     "include plantations and tall tree crops; equivalence with forest change is not demonstrated.","DW classifier noise between periods produces spurious +/- change; the reference distribution "
                     "of windows carries that noise, which is why the site is placed by percentile.",
                     "Does not use Hansen: no cross-product comparison. Absolute area change is a separate diagnostic.",
                     "Early period start is limited by DW availability (2015-06 onward)."),
        implementation_status="v0.2.8_synthetic_tested",
        synthetic_tests=("test_net_change_identical_endpoints_gives_zero",
                         "test_net_change_planting_gives_positive_pp_per_year",
                         "test_net_change_reference_is_not_fixed_by_the_stratum")),
    _ctx("kba_overlap", "Share of the site inside a Key Biodiversity Area.", "C1_landscape", "extent",
         "polygon_scalar", "Designation, not condition.", None, False, TAM, status="screening"),
    # ---------------------------------------------------------------- C2 vegetation / water
IndicatorContract(
        "ndvi", "Annual median Sentinel-2 NDVI over the site.", "C2_vegetation", "greenness",
        "polygon_mean", "site_window_mean", "least_disturbed_stratum", "tier2", "scoreable",
        "Observed vegetation condition vs least-disturbed windows of the same ecosystem.",
        "robust_z", "higher_is_better", "annual:ndvi_year", 10.0, False,
        Applicability(TM, "any", None, 10), inputs=("s2",), redundancy_groups=("R1_vegetation_signal",),
        min_reference_n=MIN_REFERENCE_WINDOWS,
        current_defects=("X1 polygon mean vs pixel reference", "subdimension 'structure' shared with chm/lai/habitat_health")),
    _ctx("habitat_health", "p5(NDVI) / SD(NDVI) over the year (Darukaa index).", "C2_vegetation", "stability",
         "polygon_mean", "Unvalidated; penalises natural seasonality of deciduous systems.", 10.0, False, TM,
         groups=("R1_vegetation_signal",)),
    _ctx("flii", "Darukaa forest-integrity proxy from HMI, HMI edge and forest density.", "C1_landscape",
         "forest_integrity", "polygon_mean", "HMI is both an input and the Tier-2 selector; duplicates ghm + natural_habitat.",
         None, False, TM, inputs=("hmi", "dw_label"), groups=("R2_human_modification",),
         defects=("X2b circular with HMI selection",)),
    _ctx("eii", "Landler Ecosystem Integrity Index (min of structural/compositional/functional).",
         "C2_vegetation", "integrity", "polygon_mean", "Too coarse for zone-level condition; landscape context.",
         None, False, TM, defects=("X6", "X7")),
    _ctx("eii_structural", "Landler EII structural integrity.", "C2_vegetation", "eii_structure", "polygon_mean",
         "Human-modification based (overlaps ghm); too coarse.", None, False, TM,
         groups=("R2_human_modification",), defects=("X6", "X7", "X2c")),
    _ctx("eii_compositional", "Landler EII compositional integrity.", "C2_vegetation", "composition",
         "polygon_mean", "BII-based (overlaps bii); too coarse.", None, False, TM,
         groups=("R3_compositional_intactness",), defects=("X6", "X7")),
    _ctx("eii_functional", "Landler EII functional integrity (NPP-based).", "C2_vegetation", "function",
         "polygon_mean", "Too coarse for zone-level condition unless the site support rule is met.", None, False, TM,
         defects=("X6", "X7")),
IndicatorContract(
        "bii", "Biodiversity Intactness Index (modelled mean species abundance vs intact).", "C3_fauna",
        "abundance_intactness", "polygon_mean", "site_window_mean", "least_disturbed_stratum", "tier2",
        "scoreable", "Only fauna-pillar evidence; modelled product with disclosed caveat.",
        "robust_z", "higher_is_better", "annual:ndvi_year (BII v1.1, 2017-2025)", 100.0, True,
        Applicability(TM, "any", None, 10), inputs=("bii_v1_1",),
        redundancy_groups=("R3_compositional_intactness",), requires_sensitivity_check=True,
        min_reference_n=MIN_REFERENCE_WINDOWS,
        limitations=("Modelled from land use and pressure: a low-HMI pool partly restates pressure (X2c); "
                     "report a sensitivity benchmark using an ecoregion + PNV pool.",
                     "100 m product: at the generic 10-pixel floor only sites >= 10 ha are applicable "
                     "(Tata: only Deccan forest). Decision pending on a landscape-product exemption."),
        current_defects=("X1 polygon mean vs pixel reference",)),
    _ctx("pdf", "Land-use biodiversity loss proxy (DW class coefficient).", "C2_vegetation", "composition",
         "polygon_mean", "DW-label lookup; degenerate under DW stratification (live: 96 % of pool = 0.1).",
         10.0, False, TM, inputs=("dw_label",), defects=("X2a",)),
    _ctx("aridity_index", "Annual P / PET (CHIRPS / TerraClimate).", "C4_pressure", "climate_exposure",
         "polygon_mean", "Climate exposure, not site condition or a manageable pressure.", 4638.3, True, TAM,
         defects=("X7 sampled at 100 m",)),
IndicatorContract(
        "tspi", "Trophic state (Carlson TSI) from Sentinel-2 NDCI-derived chlorophyll-a, pure-water pixels.",
        "C2_vegetation", "water_quality", "water_body_unit", "water_body_unit", "comparable_water_bodies",
        "tier2", "scoreable", "Water quality vs comparable water bodies (size / permanence / basin).",
        "robust_z", "lower_is_better", "annual:ndvi_year (S2 median composite)", 20.0, False,
        Applicability(AM, "open_water", "water_body", None, MIN_PURE_WATER_PIXELS, None, "pure_water_pixels"),
        inputs=("s2",), redundancy_groups=("R4_trophic_signal",), min_reference_n=MIN_COMPARABLE_WATER_BODIES,
        limitations=("Empirical NDCI -> chl-a coefficients not validated for Indian water bodies.",
                     "NDCI uses B5 (20 m): effective native resolution 20 m.",
                     "Naturally eutrophic shallow ponds: direction needs ecological review."),
        current_defects=("reference = all regional water pixels, not comparable water bodies (Phase 4)",
                         "no pure-water / minimum-pixel guard (Phase 4)")),
IndicatorContract(
        "sabf", "Share of dates with a floating-algae bloom (FAI > 0.005), averaged over the pure-water pixels of one water body.",
        "C2_vegetation", "algal_bloom_frequency", "water_body_unit", "water_body_unit", "comparable_water_bodies",
        "tier2", "scoreable", "Bloom frequency vs comparable water bodies (E2 matching, documented minimum n).",
        "reference_percentile", "lower_is_better", "annual:ndvi_year (all S2 dates, QA60-masked)", 20.0, False,
        Applicability(AM, "open_water", "water_body", None, MIN_PURE_WATER_PIXELS, None, "pure_water_pixels"),
        inputs=("s2",), min_reference_n=MIN_COMPARABLE_WATER_BODIES, expects_tied_reference=True,
        limitations=("FAI threshold 0.005 is a Darukaa choice (item 14).",
                     "Most clear water bodies have zero blooms: the reference is zero-inflated, so percentile.",
                     "Unit value is the mean of per-pixel bloom frequencies over pure water only (no land, no mixed shore pixels)."),
        implementation_status="v0.2.8_synthetic_tested",
        synthetic_tests=("test_sabf_uses_pure_water_only_and_land_never_counts_as_bloom",
                         "test_water_body_reference_matches_e2_and_requires_min_n")),
IndicatorContract(
        "wcpi", "Water clarity 1/(TSM+1), TSM from Sentinel-2 red (Nechad-type), mean over pure-water pixels of one water body.",
        "C2_vegetation", "water_clarity", "water_body_unit", "water_body_unit", "comparable_water_bodies",
        "tier2", "scoreable", "Clarity vs comparable water bodies; RAW physical quantity for site and reference.",
        "robust_z", "higher_is_better", "annual:ndvi_year (S2 median composite)", 10.0, False,
        Applicability(AM, "open_water", "water_body", None, MIN_PURE_WATER_PIXELS, None, "pure_water_pixels"),
        inputs=("s2",), min_reference_n=MIN_COMPARABLE_WATER_BODIES,
        limitations=("TSM coefficients not locally validated.",),
        implementation_status="v0.2.8_synthetic_tested",
        synthetic_tests=("test_wcpi_is_raw_and_independent_of_site_relative_range",
                         "test_water_body_reference_matches_e2_and_requires_min_n")),
    _ctx("wsdi", "Sentinel-1 water-surface dynamism.", "C2_vegetation", "water_surface_dynamics",
         "water_body_unit", "Seasonal dynamism is natural for many wetlands (item 15 decision).", 10.0, False, AM),
    _ctx("hsas", "Habitat suitability aligned with eDNA detections.", "C2_vegetation", "habitat_suitability",
         "polygon_mean", "Needs eDNA; suitability layer is land-weighted (50 % NDVI).", 10.0, False, AM,
         status="pending_methodology", defects=("reference is suitability, site may be eDNA alignment",)),
_ctx("edpp", "eDNA preservation potential (survey design aid): single-band index; thermal term scaled over the source "
         "product's valid range (a numerical / QC bound, NOT an ecological threshold).",
         "C2_vegetation", "edna_persistence", "polygon_mean",
         "Operational survey-design aid, not biodiversity condition.", 30.0, False, AM,
         status="screening", image_is_single_band=True, site_relative_normalisation=False,
         implementation_status="v0.2.8_synthetic_tested",
         synthetic_tests=("test_edpp_mspl_use_absolute_thermal_scaling_and_a_single_band",)),
_ctx("mspl", "Microbial stress proxy (Darukaa composite): single-band; thermal term scaled over the source product's "
         "valid range (a numerical / QC bound, NOT an ecological threshold).",
         "C2_vegetation", "microbial_stress", "polygon_mean",
         "Unvalidated composite; overlaps tspi and wcpi.", 20.0, False, AM,
         groups=("R4_trophic_signal",), image_is_single_band=True, site_relative_normalisation=False,
         implementation_status="v0.2.8_synthetic_tested",
         synthetic_tests=("test_edpp_mspl_use_absolute_thermal_scaling_and_a_single_band",)),
IndicatorContract(
        "riparian_natural_veg_share", "E3: share of natural-vegetation pixels (Dynamic World trees, grass, flooded "
        "vegetation, shrub) in the 100 m riparian ring around the water body; land only, all water excluded. "
        "Replaces the retired 'Riparian Complexity Index' (rci), which measured no actual complexity.",
        "C1_landscape", "riparian_condition", "riparian_ring_unit", "riparian_ring_unit",
        "comparable_riparian_rings", "tier2", "scoreable",
        "Riparian natural cover vs rings of comparable water bodies; same ring, vegetation definition and support "
        "for target and reference.", "reference_percentile", "higher_is_better",
        "annual:ndvi_year (DW mode)", 10.0, False,
        Applicability(TAM, "any", "water_body", None, MIN_PURE_WATER_PIXELS, None, "pure_water_pixels"),
        inputs=("dw_label",), min_reference_n=MIN_COMPARABLE_WATER_BODIES, expects_tied_reference=True,
        parameters=(("ring_width_m", 100.0),),
        limitations=("Natural = DW trees / grass / flooded vegetation / shrub (same class set as natural_habitat).",
                     "Ring width 100 m is the current configurable methodology parameter (config.riparian_ring_width_m).",
                     "Fully vegetated rings give ties at 1.0: percentile, not z-score."),
        implementation_status="v0.2.8_synthetic_tested",
        synthetic_tests=("test_ring_metric_uses_the_same_ring_for_target_and_reference",
                         "test_water_body_reference_matches_e2_and_requires_min_n")),
    _ctx("riparian_ndvi_trend", "NDVI trend in the riparian ring.", "C1_landscape", "hydrology",
         "riparian_ring_unit", "Context; needs the ring-unit reference if ever scored.", 10.0, False, TAM,
         population="comparable_riparian_rings", tier="tier2", defects=("X5",)),
    _ctx("jrc_water_persistence", "Share of the site that is persistent water (S1, occurrence > 0.75).",
         "C1_landscape", "hydrology", "polygon_proportion",
         "Low persistence is natural for seasonal ponds (consistent with the WSDI decision).", 10.0, False, TAM,
         defects=("X1 binary pixel reference",)),
    _ctx("shdi", "Shoreline development index of the main water body.", "C2_vegetation", "morphometry",
         "polygon_scalar", "Morphometric descriptor, not condition.", 10.0, False, AM),
    _ctx("lai", "MODIS leaf area index.", "C2_vegetation", "structure", "polygon_mean",
         "500 m pixels: landscape context for these zones; overlaps chm / ndvi.", 500.0, False, TM,
         groups=("R1_vegetation_signal",), defects=("X6", "X7")),
IndicatorContract(
        "chm", "Canopy height (ETH Global Canopy Height 2020).", "C2_vegetation", "structure",
        "polygon_mean", "site_window_mean", "least_disturbed_stratum", "tier2", "scoreable",
        "Vegetation structure vs least-disturbed windows of woody ecosystems.",
        "log_response_ratio", "higher_is_better", "static:2020", 10.0, False,
        Applicability(TM, "woody", None, 10), inputs=("eth_chm_2020",),
        redundancy_groups=("R1_vegetation_signal",), min_reference_n=MIN_REFERENCE_WINDOWS,
        limitations=("Static 2020 snapshot: baseline only, not a monitoring signal.",),
        current_defects=("site read at 25 m, reference at 10 m", "X1", "no woody-ecosystem applicability check")),
    # ---------------------------------------------------------------- C3 representation (screening)
    _ctx("endemic_richness", "Endemic species richness from range maps.", "C3_fauna", "representation",
         "polygon_scalar", "Representation / importance, not condition.", None, False, TAM, status="screening"),
    _ctx("shi", "Species habitat index.", "C3_fauna", "habitat_intactness", "not_computed",
         "No image registered; not computed.", None, False, TAM, status="screening"),
    _ctx("flagship_habitat", "Flagship-species habitat suitability.", "C3_fauna", "habitat_suitability",
         "polygon_scalar", "Representation, not condition.", None, False, TM, status="screening"),
    _ctx("endemic_plant_richness", "Endemic plant richness.", "C3_fauna", "representation", "polygon_scalar",
         "Representation, not condition.", None, False, TAM, status="screening"),
    _ctx("threatened_richness", "Threatened species richness from range maps.", "C3_fauna", "representation",
         "polygon_scalar", "Representation, not condition.", None, False, TAM, status="screening"),
    _ctx("ceri", "Removed indicator.", "C3_fauna", "representation", "not_computed", "Removed.",
         None, False, TAM, status="removed"),
    _ctx("star_t", "STAR threat-abatement score.", "C3_fauna", "representation", "polygon_scalar",
         "Opportunity metric, not condition.", None, False, TM, status="screening"),
    _ctx("threatened_plant_richness", "Threatened plant richness.", "C3_fauna", "representation",
         "polygon_scalar", "Representation, not condition.", None, False, TAM, status="screening"),
    # ---------------------------------------------------------------- C4 pressure
IndicatorContract(
        "ghm", "Human modification (TNC HM v3, all threats combined, 2022).", "C4_pressure", "land_use_pressure",
        "polygon_mean", "site_window_mean", "regional_stratum_unfiltered", "tier2", "scoreable",
        "Pressure relative to the regional stratum, no pressure filter (item 3, option B).",
        "robust_z", "lower_is_better", "static:2022", 90.0, True,
        Applicability(TAM, "any", None, None, None, None, "exempt_landscape_pressure"),
        inputs=("hmi",), redundancy_groups=("R2_human_modification",), min_reference_n=MIN_REFERENCE_WINDOWS,
        min_support_rationale=PRESSURE_SUPPORT_RULE,
        implementation_status="v0.2.8_synthetic_tested",
        synthetic_tests=("test_ghm_site_is_read_at_native_90m",)),
IndicatorContract(
        "light_pollution", "Mean VIIRS night-time radiance.", "C4_pressure", "direct_pressure",
        "polygon_mean", "site_window_mean", "regional_all", "tier1", "scoreable",
        "Pressure relative to the regional distribution (X8: Tier 1 is correct for pressures).",
        "robust_z", "lower_is_better", "annual:ndvi_year", 463.83, False,
        Applicability(TAM, "any", None, None, None, None, "exempt_landscape_pressure"),
        inputs=("viirs",), min_reference_n=MIN_REFERENCE_WINDOWS,
        min_support_rationale=PRESSURE_SUPPORT_RULE,
        current_defects=("X1",)),
IndicatorContract(
        "hdi", "Built-up / settlement proximity pressure (Dynamic World built-up distance).", "C4_pressure",
        "built_up_pressure", "polygon_mean", "site_window_mean", "regional_all", "tier1", "scoreable",
        "Pressure relative to the regional distribution.", "robust_z", "lower_is_better",
        "annual:ndvi_year (DW mode)", 10.0, False,
        Applicability(TAM, "any", None, None, None, None, "exempt_landscape_pressure"),
        inputs=("dw_label",), redundancy_groups=("R5_built_up",), min_reference_n=MIN_REFERENCE_WINDOWS,
        min_support_rationale=PRESSURE_SUPPORT_RULE,
        current_defects=("X1",)),
    _ctx("lst_day", "MODIS day land-surface temperature.", "C4_pressure", "climate_exposure", "polygon_mean",
         "Climate exposure, not condition.", 1000.0, False, TAM, defects=("X7",)),
    _ctx("lst_night", "MODIS night land-surface temperature.", "C4_pressure", "climate_exposure", "polygon_mean",
         "Climate exposure, not condition.", 1000.0, False, TAM, defects=("X7",)),
IndicatorContract(
        "sdi", "Share of the 100 m riparian ring (land only) that is disturbed (crops, built, bare, road proxy).", "C4_pressure",
        "shoreline_disturbance", "riparian_ring_unit", "riparian_ring_unit", "comparable_riparian_rings",
        "tier2", "scoreable", "Shoreline pressure vs rings of comparable water bodies; same ring and disturbance definition.",
        "reference_percentile", "lower_is_better", "annual:ndvi_year (DW mode)", 10.0, False,
        Applicability(AM, "open_water", "water_body", None, MIN_PURE_WATER_PIXELS, None, "pure_water_pixels"),
        inputs=("dw_label",), min_reference_n=MIN_COMPARABLE_WATER_BODIES, expects_tied_reference=True,
        parameters=(("ring_width_m", 100.0),),
        limitations=("Road proxy = built-up edge, not a road dataset.",
                     "Undisturbed shorelines give many zero shares: percentile, not z-score."),
        implementation_status="v0.2.8_synthetic_tested",
        synthetic_tests=("test_ring_metric_uses_the_same_ring_for_target_and_reference",
                         "test_water_body_reference_matches_e2_and_requires_min_n")),
    _ctx("stsi", "Surface thermal stress (Landsat LST).", "C4_pressure", "direct_pressure", "polygon_mean",
         "Site-relative normalisation; context.", 30.0, False, TAM, site_relative_normalisation=True,
         defects=("X3",)),
    _ctx("iri", "Invasion risk index (Darukaa composite).", "C4_pressure", "invasive_risk", "polygon_mean",
         "Unvalidated composite; double counts tspi's NDCI and hdi's built-up signal.", 10.0, False, TAM,
         groups=("R4_trophic_signal", "R5_built_up")),
    _ctx("ivsi", "Share of the site with NDVI expansion > 0.2 vs 5 years earlier.", "C4_pressure",
         "direct_pressure", "polygon_proportion", "Not taxonomic; context.", 10.0, False, TM, defects=("X1",)),
]}
