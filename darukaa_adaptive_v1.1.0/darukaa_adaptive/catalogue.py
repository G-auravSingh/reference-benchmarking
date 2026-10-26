"""Metric catalogue v1: one contract per metric.

The catalogue is the single source of truth for what each metric means, how it is
measured, which reference it is compared against and which role it should play.
It implements docs/methodology/metric_catalogue_v1.md (approved 23 Oct 2026,
decisions D-23-3 to D-23-14). Nothing here touches Earth Engine.

Roles
-----
``recommended_role`` is the scientific recommendation. ``can_score`` says whether a
metric can be scored at all (it needs a defined reference and a valid scale).
Colab runs default to scoring every metric with ``can_score=True`` (amendment A2);
any departure from the recommendation is recorded by :func:`resolve_roles`.

Source labels: STD = standard/framework, VENDOR = vendor/tool approach,
ACAD = academic dataset, DARUKAA = Darukaa's own construct or evidence.
Framework tags are provisional until the standards crosswalk pass.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

PILLARS = {
    "P1": "Ecosystem extent",
    "P2": "Ecosystem condition",
    "P3": "Species",
    "P4": "Pressure",
    "M": "Managed land (outside the Nature Positive panel)",
}
CONDITION_PILLARS = ("P1", "P2", "P3")
ROLES = ("scored", "contextual", "screening", "diagnostic")
REFERENCE_TYPES = ("reference_condition", "regional_context", "low_pressure", "natural_scale", "none")
DIRECTIONS = ("higher_is_better", "lower_is_better", "descriptive")
LEVELS = ("site", "emu", "site_and_emu")
GRANULARITY = ("preparatory", "medium", "high")


@dataclass(frozen=True)
class Dataset:
    asset_id: str
    version: str
    native_scale_m: Optional[float]
    licence: str
    source_label: str  # STD | ACAD | VENDOR | DARUKAA
    citation: str = ""
    verified: str = "catalogue page 23 Oct 2026; probe pending"


@dataclass(frozen=True)
class MapSpec:
    palette: Tuple[str, ...] = ("#f7fcf5", "#74c476", "#00441b")
    vmin: Optional[float] = None
    vmax: Optional[float] = None
    legend: str = ""
    kind: str = "raster"  # raster | vector | none


@dataclass(frozen=True)
class MetricContract:
    id: str
    name: str
    pillar: str
    component: str
    definition: str
    unit: str
    direction: str
    level: str
    datasets: Tuple[Dataset, ...]
    reference_type: str
    recommended_role: str
    role_reason: str
    can_score: bool
    natural_only: bool = False
    min_support_px: float = 4.0
    granularity: str = "preparatory"
    pressure_modelled: bool = False
    landscape_context: bool = False
    applicable_realms: Tuple[str, ...] = ("terrestrial", "mixed")
    applicable_types: Tuple[str, ...] = ()  # empty = all natural types
    value_range: Tuple[Optional[float], Optional[float]] = (None, None)
    exclusive_group: Optional[str] = None
    group_priority: int = 0
    framework_tags: Tuple[str, ...] = ()
    failure_modes: Tuple[str, ...] = ()
    map_spec: MapSpec = field(default_factory=MapSpec)
    status: str = "approved"  # approved | proposed
    notes: str = ""

    @property
    def native_scale_m(self) -> Optional[float]:
        scales = [d.native_scale_m for d in self.datasets if d.native_scale_m]
        return min(scales) if scales else None

    def to_row(self) -> Dict[str, object]:
        row = asdict(self)
        row["datasets"] = "; ".join(f"{d.asset_id} ({d.version}, {d.native_scale_m} m, {d.licence}, {d.source_label})" for d in self.datasets)
        row["framework_tags"] = ", ".join(self.framework_tags)
        row["failure_modes"] = ", ".join(self.failure_modes)
        row["applicable_realms"] = ", ".join(self.applicable_realms)
        row["applicable_types"] = ", ".join(self.applicable_types)
        row["native_scale_m"] = self.native_scale_m
        row.pop("map_spec", None)
        return row


COMMON_FAILURES = ("not_run", "source_unavailable", "no_valid_pixels", "below_min_support",
                   "out_of_range_review")

# --------------------------------------------------------------------------- datasets
FORTY = Dataset("projects/nature-trace/assets/forest_typology/forest_typology_2020_v1_0_collection", "v1.0 (2020)", 10.0, "CC-BY-4.0", "ACAD",
                "Nature Trace Forest Typology 2020 (Google DeepMind et al.); EarthArXiv 10.31223/X58R27")
SBTN = Dataset("WRI/SBTN/naturalLands/v1_1/2020", "v1.1 (2020)", 30.0, "CC-BY-SA-4.0", "STD",
               "SBTN Natural Lands Map v1.1 (Mazur et al. 2025)")
DW = Dataset("GOOGLE/DYNAMICWORLD/V1", "V1", 10.0, "CC-BY-4.0", "ACAD", "Brown et al. 2022, Sci Data 9:251")
HANSEN = Dataset("UMD/hansen/global_forest_change_2025_v1_13", "v1.13 (2000-2025)", 30.0, "CC-BY-4.0", "ACAD", "Hansen et al. 2013, Science 342:850")
JRC_GFC = Dataset("JRC/GFC2020/V2", "V2 (2020)", 10.0, "licence to confirm", "ACAD", "JRC Global Forest Cover 2020")
JRC_GSW = Dataset("JRC/GSW1_4/GlobalSurfaceWater", "1.4", 30.0, "open with attribution", "ACAD", "Pekel et al. 2016, Nature 540:418")
S2 = Dataset("COPERNICUS/S2_SR_HARMONIZED", "L2A", 10.0, "Copernicus open", "ACAD", "ESA Sentinel-2")
S2CP = Dataset("COPERNICUS/S2_CLOUD_PROBABILITY", "s2cloudless", 10.0, "Copernicus open", "ACAD", "Sentinel Hub s2cloudless")
META_CHM = Dataset("projects/sat-io/open-datasets/facebook/meta-canopy-height", "forests/v1 (imagery 2009-2020)", 1.0, "CC-BY-4.0", "ACAD", "Tolan et al. 2024, RSE 300:113888")
GLAD_CH = Dataset("projects/sat-io/open-datasets/GLAD/GEDI_V27", "2019/2020 (ID to probe)", 30.0, "CC-BY-4.0", "ACAD", "Potapov et al. 2021, RSE 253:112165")
GEDI_L2A = Dataset("LARSE/GEDI/GEDI02_A_002_MONTHLY", "002", 25.0, "public domain", "ACAD", "Dubayah et al., GEDI L2A")
BII = Dataset("projects/ebx-data/assets/earthblox/IO/BII_V1_1", "v1.1 (2017-2025)", 100.0, "CC-BY-4.0", "ACAD", "Gassert, Mazzarello & Hyde 2026 (Vizzuality / Impact Observatory)")
EII = Dataset("projects/landler-open-data/assets/eii/global/eii_global_v1", "v1 (beta)", 300.0, "data licence unverified", "VENDOR", "Landbanking Group EII v1 (Leutner 2025)")
FLII = Dataset("projects/darukaa-earth-product/assets/flii_global_2019", "2019 (official WCS download, uploaded by Darukaa)", 300.0, "licence unverified", "ACAD", "Grantham et al. 2020, Nat Commun 11:5978")
MSA = Dataset("raster_paths['msa_gee_asset'] (GLOBIO4 2015 upload)", "GLOBIO4 2015", 300.0, "CC-BY-4.0 (globio.info)", "ACAD", "Schipper et al. 2020, Glob Change Biol 26:760")
KBA = Dataset("projects/darukaa-earth-product/assets/Biodiversity/KBA_Global_POL_SEP25", "Sep 2025", None, "commercial use restricted (BirdLife/KBA terms); held for review", "STD", "World Database of KBAs")
WDPA = Dataset("WCMC/WDPA/current/polygons", "monthly", None, "commercial use restricted (UNEP-WCMC terms); held for review", "STD", "UNEP-WCMC & IUCN, Protected Planet")
IUCN_RANGES = Dataset("projects/darukaa-earth-product/assets/Biodiversity/RedList_* and IUCN_Plant_Redlist", "Darukaa-held", None, "IUCN terms: non-commercial; held for review", "STD", "IUCN Red List spatial data")
STAR = Dataset("raster_paths['star_t'] (IBAT STAR-t raster, if supplied)", "IBAT", 1000.0, "IBAT licence required", "STD", "Mair et al. 2021")
GBIF = Dataset("GBIF occurrence API (CC0 and CC-BY records only)", "live", None, "CC0 / CC-BY-4.0 per record", "ACAD", "GBIF.org")
TNC_HM = Dataset("TNC/HM/v3/90m_s", "v3 2022", 90.0, "CC-BY-4.0", "ACAD", "Theobald et al. 2025, Sci Data 12:489")
GRIP = Dataset("projects/sat-io/open-datasets/GRIP4/*", "GRIP4 (~2018)", None, "CC-BY-4.0", "ACAD", "Meijer et al. 2018, ERL 13:064006")
MCD64 = Dataset("MODIS/061/MCD64A1", "061", 500.0, "LP DAAC, no restrictions", "ACAD", "doi:10.5067/MODIS/MCD64A1.061")
VIIRS = Dataset("NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG", "V1", 464.0, "no restrictions", "ACAD", "Earth Observation Group, Colorado School of Mines")
GFW_ALERTS = Dataset("GFW integrated deforestation alerts (EE access to probe)", "live", 10.0, "CC-BY-4.0", "ACAD", "Global Forest Watch")
WORLDPOP = Dataset("WorldPop/GP/100m/pop", "2020", 93.0, "CC-BY-4.0", "ACAD", "WorldPop")
LANDSAT_ST = Dataset("LANDSAT/LC09/C02/T1_L2 + LANDSAT/LC08/C02/T1_L2 (ST_B10)", "C2 L2", 30.0, "public domain", "ACAD", "USGS Landsat Collection 2")
MOD11 = Dataset("MODIS/061/MOD11A1", "061", 1000.0, "LP DAAC, no restrictions", "ACAD", "doi:10.5067/MODIS/MOD11A1.061")
ARIDITY = Dataset("UCSB-CHG/CHIRPS/DAILY / IDAHO_EPSCOR/TERRACLIMATE pet", "annual", 4600.0, "public domain / CC0", "ACAD", "Funk et al. 2015; Abatzoglou et al. 2018")
SL2P = Dataset("COPERNICUS/S2_SR_HARMONIZED + SL2P (CCRS LEAF toolbox)", "SL2P", 20.0, "Copernicus open; algorithm open source", "ACAD", "Weiss & Baret, SL2P; Fernandes et al., LEAF toolbox")
MODIS_LAI = Dataset("MODIS/061/MCD15A3H", "061", 500.0, "LP DAAC, no restrictions", "ACAD", "doi:10.5067/MODIS/MCD15A3H.061")

NATURAL_MASK = (FORTY, SBTN, DW)


def _m(**kw) -> MetricContract:
    kw.setdefault("failure_modes", COMMON_FAILURES)
    return MetricContract(**kw)


CATALOGUE: Tuple[MetricContract, ...] = (
    # ------------------------------------------------------------------ P1 extent
    _m(id="natural_extent_pct", name="Natural ecosystem extent", pillar="P1", component="extent",
       definition="Share of the site that is natural or semi-natural now (natural mask: ForTy 2020 for tree cover, SBTN 2020 otherwise, Dynamic World current-window conversion removes lost pixels).",
       unit="%", direction="higher_is_better", level="site", datasets=NATURAL_MASK, reference_type="natural_scale",
       recommended_role="scored", role_reason="Nature Positive extent indicator [STD]; SBTN map is the named preparatory classification layer (Guidance p.15).",
       can_score=True, value_range=(0, 100), framework_tags=("NPI:extent", "TNFD:C1.0", "ESRS:E4-5", "SBTN:Land", "GRI:101-7"),
       map_spec=MapSpec(("#d9d9d9", "#1b7837"), 0, 1, "natural (green) / non-natural (grey)")),
    _m(id="natural_gross_loss_pct", name="Gross loss of natural ecosystems since 2020", pillar="P1", component="change",
       definition="Natural area in 2020 that is non-natural in the assessment window, as % of 2020 natural area. Gross only; never netted against gain.",
       unit="%", direction="lower_is_better", level="site", datasets=NATURAL_MASK, reference_type="regional_context",
       recommended_role="scored", role_reason="Nature Positive extent losses [STD]; gross-only rule [DARUKAA].", can_score=True,
       value_range=(0, 100), framework_tags=("NPI:extent", "TNFD:C1.1", "ESRS:E4-5", "SBTN:Land"),
       failure_modes=COMMON_FAILURES + ("not_applicable_no_natural_baseline",),
       map_spec=MapSpec(("#ffffff", "#b2182b"), 0, 1, "lost since 2020")),
    _m(id="tree_cover_loss_rate", name="Tree cover loss rate", pillar="P1", component="change",
       definition="Percent of year-2000 tree cover (canopy >= 10%) lost per year, mean over the last 5 full years of the Hansen version; same function on site and reference.",
       unit="%/yr", direction="lower_is_better", level="site", datasets=(HANSEN,), reference_type="regional_context",
       recommended_role="scored", role_reason="Decision 3 (16 Oct): normalised rate replaces cumulative ha.", can_score=True,
       value_range=(0, 100), framework_tags=("TNFD:C1.1", "ESRS:E4-5"),
       failure_modes=COMMON_FAILURES + ("not_applicable_no_forest_baseline",),
       map_spec=MapSpec(("#ffffff", "#e31a1c"), 0, 1, "loss year in window")),
    _m(id="natural_core_area_pct", name="Natural core area (CPLAND)", pillar="P1", component="configuration",
       definition="Natural pixels more than 30 m from any non-natural pixel, as % of site area (within-site configuration).",
       unit="%", direction="higher_is_better", level="site", datasets=NATURAL_MASK, reference_type="natural_scale",
       recommended_role="scored", role_reason="Configuration; Plan Vivo PV Nature Pillar 5 uses CPLAND (V1.2 p.28) [STD].", can_score=True,
       value_range=(0, 100), framework_tags=("PV:P5", "TNFD:C1.0"), map_spec=MapSpec(("#d9d9d9", "#006837"), 0, 1, "core natural")),
    _m(id="natural_gross_gain_ha", name="Candidate gross gain of natural vegetation since 2020", pillar="P1", component="change",
       definition="Area non-natural in 2020 that carries natural-class Dynamic World vegetation in the window, by type. Candidate only: DW cannot confirm natural status.",
       unit="ha", direction="descriptive", level="site", datasets=NATURAL_MASK, reference_type="none",
       recommended_role="contextual", role_reason="No defensible reference; restoration progress is shown, not scored.", can_score=False,
       framework_tags=("NPI:extent", "TNFD:C1.1")),
    _m(id="natural_extent_by_type_ha", name="Natural extent by ecosystem type", pillar="P1", component="extent",
       definition="Natural area by type (ForTy forest classes; SBTN classification; DW class for the current window).",
       unit="ha", direction="descriptive", level="site", datasets=NATURAL_MASK, reference_type="none",
       recommended_role="contextual", role_reason="Breakdown by type required [STD]; descriptive.", can_score=False,
       framework_tags=("NPI:extent",)),
    _m(id="forest_cover_2020_jrc_pct", name="Forest cover 2020 (JRC cross-check)", pillar="P1", component="extent",
       definition="Share of site mapped as forest in JRC GFC2020; QA cross-check of the natural mask.",
       unit="%", direction="descriptive", level="site", datasets=(JRC_GFC,), reference_type="none",
       recommended_role="contextual", role_reason="QA cross-check only.", can_score=False),
    _m(id="surface_water_extent_ha", name="Surface water extent", pillar="P1", component="extent",
       definition="Permanent and seasonal water area (JRC occurrence >= 50% / seasonality) inside the site.",
       unit="ha", direction="descriptive", level="site", datasets=(JRC_GSW,), reference_type="none",
       recommended_role="contextual", role_reason="Terrestrial context; scored in the aquatic track later.", can_score=False,
       applicable_realms=("terrestrial", "aquatic", "mixed")),
    _m(id="landscape_natural_extent_pct", name="Landscape natural extent (context)", pillar="P1", component="extent",
       definition="Natural extent in 5 km and 10 km rings around the site, site excluded.",
       unit="%", direction="descriptive", level="site", datasets=NATURAL_MASK, reference_type="none",
       recommended_role="contextual", role_reason="Landscape context, not attributable to the project (TOR p.132).", can_score=False,
       landscape_context=True, framework_tags=("NPI:extent-landscape",)),
    _m(id="kba_overlap_pct", name="Key Biodiversity Area overlap", pillar="P1", component="significance",
       definition="Share of site inside a KBA polygon, plus distance to nearest KBA.",
       unit="%", direction="descriptive", level="site", datasets=(KBA,), reference_type="none",
       recommended_role="screening", role_reason="Significance screen, not a state metric; licence terms held for review.", can_score=False,
       framework_tags=("ESRS:E4-5", "TNFD:location", "IFC:PS6"), map_spec=MapSpec(kind="vector", legend="KBA")),
    _m(id="protected_area_overlap_pct", name="Protected area overlap", pillar="P1", component="significance",
       definition="Share of site inside a WDPA protected area, plus distance to nearest protected area.",
       unit="%", direction="descriptive", level="site", datasets=(WDPA,), reference_type="none",
       recommended_role="screening", role_reason="Significance screen; licence terms held for review.", can_score=False,
       framework_tags=("ESRS:E4-5", "TNFD:location", "IFC:PS6"), map_spec=MapSpec(kind="vector", legend="WDPA")),

    # ------------------------------------------------------------------ P2 condition
    _m(id="ndvi_peak_season", name="Peak-season NDVI", pillar="P2", component="function",
       definition="Median NDVI of cloud-masked Sentinel-2 scenes in the 3-month peak-greenness window inside the assessment period, natural vegetated pixels only (forest, woodland, shrub, grass, wetland).",
       applicable_types=("natural_forest", "woodland", "shrub", "grass", "wetland"),
       unit="NDVI", direction="higher_is_better", level="site_and_emu", datasets=(S2, S2CP), reference_type="reference_condition",
       recommended_role="scored", role_reason="Sentinel-2 indices used for preparatory condition (TOR pp.102, 116) [STD pilots].", can_score=True,
       natural_only=True, value_range=(-1, 1), framework_tags=("NPI:condition", "TNFD:C5.0", "ESRS:E4-5", "PV:P4"),
       map_spec=MapSpec(("#a50026", "#ffffbf", "#006837"), 0, 0.9, "NDVI")),
    _m(id="lai_s2", name="Leaf area index (Sentinel-2 SL2P)", pillar="P2", component="structure",
       definition="Median SL2P LAI (20 m) in the peak-greenness window, natural vegetated pixels only.",
       applicable_types=("natural_forest", "woodland", "shrub", "grass", "wetland"),
       unit="m2/m2", direction="higher_is_better", level="site_and_emu", datasets=(SL2P,), reference_type="reference_condition",
       recommended_role="scored", role_reason="Finest open LAI; replaces MODIS 500 m (C6).", can_score=True, natural_only=True,
       value_range=(0, 10), framework_tags=("NPI:condition", "TNFD:C5.0"), notes="EE implementation of SL2P to be verified before scoring.",
       map_spec=MapSpec(("#ffffe5", "#78c679", "#004529"), 0, 6, "LAI")),
    _m(id="canopy_height_m", name="Canopy height", pillar="P2", component="structure",
       definition="Mean 1 m canopy height over natural forest and shrub pixels.",
       unit="m", direction="higher_is_better", level="site_and_emu", datasets=(META_CHM,), reference_type="reference_condition",
       recommended_role="scored", role_reason="Structure component [STD]; finest open source (1 m).", can_score=True, natural_only=True,
       applicable_types=("natural_forest", "shrub"), value_range=(0, 80), framework_tags=("NPI:condition", "TNFD:C5.0"),
       failure_modes=COMMON_FAILURES + ("not_applicable_no_woody_type",), map_spec=MapSpec(("#ffffcc", "#41ab5d", "#00441b"), 0, 30, "m")),
    _m(id="bii", name="Biodiversity Intactness Index", pillar="P2", component="composition",
       definition="Mean BII over natural pixels for the latest year at or before the window end (year recorded).",
       unit="index 0-1", direction="higher_is_better", level="site_and_emu", datasets=(BII,), reference_type="reference_condition",
       recommended_role="scored", role_reason="Composition; pressure-modelled, so preparatory only (Guidance p.20).", can_score=True,
       natural_only=True, pressure_modelled=True, value_range=(0, 1), exclusive_group="modelled_intactness", group_priority=1,
       framework_tags=("NPI:condition", "TNFD:C5.0", "ESRS:E4-5"), failure_modes=COMMON_FAILURES + ("year_unavailable",),
       map_spec=MapSpec(("#fde0dd", "#c51b8a", "#49006a"), 0, 1, "BII")),
    _m(id="eii_functional", name="EII functional integrity", pillar="P2", component="function",
       definition="Landbanking EII v1 functional_integrity band (observed vs potential NPP).",
       unit="index 0-1", direction="higher_is_better", level="site", datasets=(EII,), reference_type="reference_condition",
       recommended_role="scored", role_reason="Most observation-based EII component [VENDOR product].", can_score=True, natural_only=True,
       value_range=(0, 1), exclusive_group="eii", group_priority=1, framework_tags=("NPI:condition", "TNFD:C5.0")),
    _m(id="flii", name="Forest Landscape Integrity Index", pillar="P2", component="integrity",
       definition="FLII 2019 (0-10) over forest pixels; context window when fewer than 4 forest pixel-equivalents.",
       unit="index 0-10", direction="higher_is_better", level="site", datasets=(FLII,), reference_type="reference_condition",
       recommended_role="scored", role_reason="Forest integrity [ACAD]; forest pixels only.", can_score=True, natural_only=True,
       applicable_types=("natural_forest",), value_range=(0, 10), framework_tags=("NPI:condition", "TNFD:C5.0"),
       failure_modes=COMMON_FAILURES + ("not_applicable_non_forest",)),
    _m(id="gedi_rh98_m", name="GEDI canopy height (rh98)", pillar="P2", component="structure",
       definition="Mean rh98 of quality-filtered GEDI L2A footprints over natural pixels; scored only with >= 10 footprints.",
       unit="m", direction="higher_is_better", level="site", datasets=(GEDI_L2A,), reference_type="reference_condition",
       recommended_role="contextual", role_reason="Sparse footprints on small sites; cross-check of canopy height.", can_score=True,
       natural_only=True, min_support_px=10, applicable_types=("natural_forest", "shrub"), value_range=(0, 100)),
    _m(id="canopy_height_glad_m", name="GLAD forest height 2020", pillar="P2", component="structure",
       definition="Mean GLAD 30 m forest height over natural forest pixels.", unit="m", direction="higher_is_better", level="site",
       datasets=(GLAD_CH,), reference_type="reference_condition", recommended_role="contextual",
       role_reason="Cross-check of 1 m canopy height.", can_score=True, natural_only=True, applicable_types=("natural_forest",), value_range=(0, 80)),
    _m(id="pv_habitat_health_sbi", name="Habitat health (Plan Vivo Pillar 4 SBI)", pillar="P2", component="function",
       definition="Surface bearing index Sq / z05 of the peak-season 3-month median NDVI surface across the unit (PV Nature V1.2 Sec. 1.5.4; geodiv sbi).",
       unit="index", direction="descriptive", level="site_and_emu", datasets=(S2, S2CP), reference_type="none",
       recommended_role="contextual", role_reason="Plan Vivo scores year-on-year change, not an absolute level; baseline is descriptive [STD].",
       can_score=False, framework_tags=("PV:P4",), notes="Direction and mean-plane handling to be confirmed against PV p.26 before monitoring-year use."),
    _m(id="eii", name="Ecosystem Integrity Index (parent)", pillar="P2", component="integrity",
       definition="Landbanking EII v1 parent band (min component x fuzzy sum of the other two).",
       unit="index 0-1", direction="higher_is_better", level="site", datasets=(EII,), reference_type="reference_condition",
       recommended_role="contextual", role_reason="Structural component is built from gHM (pressure), double-counting P4 and limited by Guidance p.20.",
       can_score=True, natural_only=True, pressure_modelled=True, value_range=(0, 1), exclusive_group="eii", group_priority=2),
    _m(id="eii_structural", name="EII structural integrity", pillar="P2", component="structure",
       definition="Landbanking EII v1 structural_integrity band (gHM-based core habitat, 5 km).", unit="index 0-1",
       direction="higher_is_better", level="site", datasets=(EII,), reference_type="reference_condition",
       recommended_role="contextual", role_reason="Pressure-derived (gHM) landscape measure.", can_score=True, natural_only=True,
       pressure_modelled=True, value_range=(0, 1), exclusive_group="eii", group_priority=3),
    _m(id="eii_compositional", name="EII compositional integrity", pillar="P2", component="composition",
       definition="Landbanking EII v1 compositional_integrity band (BII aggregated to 300 m).", unit="index 0-1",
       direction="higher_is_better", level="site", datasets=(EII,), reference_type="none", recommended_role="diagnostic",
       role_reason="Duplicates BII.", can_score=False, value_range=(0, 1)),
    _m(id="msa", name="Mean Species Abundance (GLOBIO4)", pillar="P2", component="composition",
       definition="GLOBIO4 2015 total MSA over natural pixels.", unit="index 0-1", direction="higher_is_better", level="site",
       datasets=(MSA,), reference_type="reference_condition", recommended_role="contextual",
       role_reason="Fully pressure-modelled; overlaps BII and P4.", can_score=True, natural_only=True, pressure_modelled=True,
       value_range=(0, 1), exclusive_group="modelled_intactness", group_priority=2),
    _m(id="landscape_connectivity", name="Landscape connectivity (context)", pillar="P2", component="landscape",
       definition="Connectance of natural patches in 5 km and 10 km rings (share of natural patch pairs within 500 m).",
       unit="%", direction="descriptive", level="site", datasets=NATURAL_MASK, reference_type="none",
       recommended_role="contextual", role_reason="Nature Positive landscape condition metric (Framework p.13); context, not attributable.",
       can_score=False, landscape_context=True, framework_tags=("NPI:condition-landscape",)),

    # ------------------------------------------------------------------ P3 species
    _m(id="species_records_screen", name="Recorded species (open records)", pillar="P3", component="records",
       definition="Distinct species in CC0/CC-BY GBIF records (incl. eBird) since 2015 within the site and 5/10 km rings.",
       unit="count", direction="descriptive", level="site", datasets=(GBIF,), reference_type="none", recommended_role="screening",
       role_reason="Presence-only, effort-biased; never read as absence.", can_score=False, landscape_context=True),
    _m(id="scheduled_species_records", name="Recorded scheduled species (India WPA 2022)", pillar="P3", component="records",
       definition="Recorded species listed in Schedules I/II of the Wildlife (Protection) Amendment Act 2022.", unit="count",
       direction="descriptive", level="site", datasets=(GBIF,), reference_type="none", recommended_role="screening",
       role_reason="National protection status, not IUCN extinction risk.", can_score=False),
    _m(id="threatened_species_range_count", name="Threatened species with overlapping ranges", pillar="P3", component="extinction_risk",
       definition="Count of IUCN CR/EN/VU mammals and birds whose range polygons overlap the site.", unit="count",
       direction="descriptive", level="site", datasets=(IUCN_RANGES,), reference_type="none", recommended_role="diagnostic",
       role_reason="Range overlap is not presence; licence held for review.", can_score=False),
    _m(id="restricted_range_species_count", name="Restricted-range species with overlapping ranges", pillar="P3", component="extinction_risk",
       definition="Count of mammals, birds and plants with range < 100,000 km2 whose range overlaps the site.", unit="count",
       direction="descriptive", level="site", datasets=(IUCN_RANGES,), reference_type="none", recommended_role="diagnostic",
       role_reason="Range overlap is not presence; licence held for review.", can_score=False),
    _m(id="star_t", name="STAR threat-abatement score", pillar="P3", component="extinction_risk",
       definition="Sum of STAR-t over the site from a supplied IBAT raster.", unit="STAR units", direction="descriptive",
       level="site", datasets=(STAR,), reference_type="none", recommended_role="contextual",
       role_reason="Needs an IBAT raster; pending input.", can_score=False, failure_modes=COMMON_FAILURES + ("pending_input",)),

    # ------------------------------------------------------------------ P4 pressure
    _m(id="built_fraction", name="Built-up share", pillar="P4", component="land_use",
       definition="Share of site pixels whose modal Dynamic World class in the window is built.", unit="fraction",
       direction="lower_is_better", level="site", datasets=(DW,), reference_type="low_pressure", recommended_role="scored",
       role_reason="Direct land-use pressure.", can_score=True, value_range=(0, 1), framework_tags=("TNFD:C1.0", "ESRS:E4-5")),
    _m(id="ghm", name="Human modification (gHM v3)", pillar="P4", component="land_use",
       definition="Coverage-weighted mean of All_threats_combined, 2022, at 90 m.", unit="index 0-1",
       direction="lower_is_better", level="site", datasets=(TNC_HM,), reference_type="low_pressure", recommended_role="scored",
       role_reason="Integrated pressure layer; native-scale rebuild (H4).", can_score=True, value_range=(0, 1),
       framework_tags=("TNFD:pressure", "ESRS:E4-5")),
    _m(id="road_density", name="Road density", pillar="P4", component="access",
       definition="Road length per area in the site plus 1 km (GRIP4).", unit="km/km2", direction="lower_is_better",
       level="site", datasets=(GRIP,), reference_type="low_pressure", recommended_role="scored",
       role_reason="Access pressure; vector source has no scale limit.", can_score=True, value_range=(0, None),
       map_spec=MapSpec(kind="vector", legend="roads")),
    _m(id="fire_frequency", name="Fire frequency", pillar="P4", component="disturbance",
       definition="Share of years 2016-2025 with a MODIS burned-area detection (coverage-weighted).", unit="fraction of years",
       direction="lower_is_better", level="site", datasets=(MCD64,), reference_type="low_pressure", recommended_role="scored",
       role_reason="Common disturbance in Indian dry forests; Vale used fire (TOR p.119).", can_score=True, value_range=(0, 1)),
    _m(id="night_lights", name="Night-time lights", pillar="P4", component="light",
       definition="Median monthly VIIRS avg_rad in the window (cf_cvg > 0).", unit="nW/cm2/sr", direction="lower_is_better",
       level="site", datasets=(VIIRS,), reference_type="low_pressure", recommended_role="scored",
       role_reason="Light pressure; no finer open source.", can_score=True, value_range=(0, None)),
    _m(id="forest_disturbance_alerts", name="Forest disturbance alerts", pillar="P4", component="disturbance",
       definition="Area of integrated deforestation alerts in the window.", unit="ha", direction="descriptive", level="site",
       datasets=(GFW_ALERTS,), reference_type="none", recommended_role="contextual", role_reason="30N-30S only; EE access to probe.",
       can_score=False),
    _m(id="population_density", name="Population density", pillar="P4", component="access",
       definition="WorldPop 2020 people per km2 in the site plus 1 km.", unit="people/km2", direction="lower_is_better",
       level="site", datasets=(WORLDPOP,), reference_type="low_pressure", recommended_role="contextual",
       role_reason="Modelled; overlaps gHM.", can_score=True, value_range=(0, None)),
    _m(id="lst_day", name="Land surface temperature (day)", pillar="P4", component="climate",
       definition="Median Landsat C2 surface temperature in the window.", unit="degC", direction="descriptive", level="site",
       datasets=(LANDSAT_ST,), reference_type="none", recommended_role="contextual",
       role_reason="Climate exposure, not anthropogenic pressure.", can_score=False),
    _m(id="lst_night", name="Land surface temperature (night)", pillar="P4", component="climate",
       definition="Mean MODIS night LST in the window.", unit="degC", direction="descriptive", level="site",
       datasets=(MOD11,), reference_type="none", recommended_role="contextual", role_reason="Climate exposure.", can_score=False),
    _m(id="aridity_index", name="Aridity index", pillar="P4", component="climate",
       definition="Annual precipitation / potential evapotranspiration for the latest full year.", unit="ratio",
       direction="descriptive", level="site", datasets=(ARIDITY,), reference_type="none", recommended_role="contextual",
       role_reason="Climate exposure.", can_score=False),
    _m(id="built_up_within_1km_pct", name="Built-up land within 1 km", pillar="P4", component="land_use",
       definition="Share of built land (DW, window) in a 1 km ring around the site; successor to the retired HDI proximity index.",
       unit="%", direction="lower_is_better", level="site", datasets=(DW,), reference_type="low_pressure",
       recommended_role="contextual", role_reason="Edge pressure from nearby settlement; overlaps gHM.", can_score=True,
       value_range=(0, 100), status="proposed"),

    # ------------------------------------------------------------------ managed land
    _m(id="managed_area_pct", name="Managed land share", pillar="M", component="extent",
       definition="Share of the unit that is non-natural (ForTy planted/plantation/tree crops, SBTN non-natural).", unit="%",
       direction="descriptive", level="site_and_emu", datasets=NATURAL_MASK, reference_type="none", recommended_role="contextual",
       role_reason="Managed-land result [DARUKAA], outside the Nature Positive panel (D-22-2).", can_score=False),
    _m(id="managed_ndvi", name="Managed-land vegetation (NDVI)", pillar="M", component="vegetation",
       definition="Peak-season NDVI on managed pixels, against the same managed class in the region.", unit="NDVI",
       direction="higher_is_better", level="site_and_emu", datasets=(S2, S2CP), reference_type="regional_context",
       recommended_role="contextual", role_reason="Managed-land vegetation score [DARUKAA]; never feeds condition.", can_score=True,
       value_range=(-1, 1)),
    _m(id="managed_canopy_height_m", name="Managed-land canopy height", pillar="M", component="vegetation",
       definition="Mean 1 m canopy height on managed pixels.", unit="m", direction="higher_is_better", level="site_and_emu",
       datasets=(META_CHM,), reference_type="regional_context", recommended_role="contextual",
       role_reason="Managed-land vegetation [DARUKAA].", can_score=True, value_range=(0, 80)),
)

_BY_ID = {c.id: c for c in CATALOGUE}
if len(_BY_ID) != len(CATALOGUE):  # pragma: no cover - guarded by tests
    raise RuntimeError("Duplicate metric id in catalogue")


def get(metric_id: str) -> MetricContract:
    try:
        return _BY_ID[metric_id]
    except KeyError as exc:
        raise KeyError(f"Unknown metric: {metric_id}") from exc


def active(include_proposed: bool = False) -> List[MetricContract]:
    return [c for c in CATALOGUE if include_proposed or c.status == "approved"]


def validate_catalogue() -> List[str]:
    """Return contract errors; an empty list means every contract is complete."""
    errors: List[str] = []
    for c in CATALOGUE:
        if c.pillar not in PILLARS: errors.append(f"{c.id}: unknown pillar {c.pillar}")
        if c.recommended_role not in ROLES: errors.append(f"{c.id}: unknown role {c.recommended_role}")
        if c.reference_type not in REFERENCE_TYPES: errors.append(f"{c.id}: unknown reference type {c.reference_type}")
        if c.direction not in DIRECTIONS: errors.append(f"{c.id}: unknown direction {c.direction}")
        if c.level not in LEVELS: errors.append(f"{c.id}: unknown level {c.level}")
        if c.granularity not in GRANULARITY: errors.append(f"{c.id}: unknown granularity {c.granularity}")
        if not c.datasets: errors.append(f"{c.id}: no dataset")
        if not c.definition or not c.unit or not c.role_reason: errors.append(f"{c.id}: incomplete contract text")
        if c.can_score:
            if c.reference_type == "none": errors.append(f"{c.id}: scoreable metric needs a reference type")
            if c.direction == "descriptive": errors.append(f"{c.id}: scoreable metric needs a direction")
        if c.recommended_role == "scored" and not c.can_score: errors.append(f"{c.id}: recommended scored but cannot score")
        if c.pillar == "P2" and c.can_score and not c.natural_only: errors.append(f"{c.id}: condition metric must be natural-only")
        if c.pillar == "M" and c.recommended_role == "scored": errors.append(f"{c.id}: managed land never feeds the headline")
    return errors


@dataclass(frozen=True)
class RoleDecision:
    metric: str
    recommended_role: str
    applied_role: str
    deviates: bool
    reason: str


def resolve_roles(mode: str = "recommended", overrides: Optional[Mapping[str, str]] = None,
                  include_proposed: bool = False) -> Dict[str, RoleDecision]:
    """Resolve the role every metric plays in a run.

    ``mode='recommended'`` applies the catalogue recommendation. ``mode='all_scoreable'``
    (the Colab default, amendment A2) scores every metric with ``can_score=True``.
    ``overrides`` set a single metric to ``scored`` or ``contextual``; metrics that
    cannot be scored are never promoted. Within an exclusive group (for example EII
    parent vs its components) only the highest-priority scored member stays scored,
    so the same construct is never counted twice.
    """
    if mode not in {"recommended", "all_scoreable"}:
        raise ValueError("mode must be 'recommended' or 'all_scoreable'")
    overrides = dict(overrides or {})
    unknown = sorted(set(overrides) - set(_BY_ID))
    if unknown:
        raise KeyError(f"Unknown metric override(s): {unknown}")
    out: Dict[str, RoleDecision] = {}
    for c in active(include_proposed):
        role = c.recommended_role
        reason = "catalogue recommendation"
        if mode == "all_scoreable" and c.can_score:
            role, reason = "scored", "all_scoreable mode (A2)"
        if c.id in overrides:
            want = overrides[c.id]
            if want not in {"scored", "contextual"}:
                raise ValueError(f"Override for {c.id} must be 'scored' or 'contextual'")
            if want == "scored" and not c.can_score:
                reason = f"override to scored refused: {c.role_reason}"
            else:
                role, reason = want, "user override"
        out[c.id] = RoleDecision(c.id, c.recommended_role, role, role != c.recommended_role, reason)
    groups: Dict[str, List[MetricContract]] = {}
    for c in active(include_proposed):
        if c.exclusive_group and out[c.id].applied_role == "scored":
            groups.setdefault(c.exclusive_group, []).append(c)
    for group, members in groups.items():
        members.sort(key=lambda c: c.group_priority)
        for c in members[1:]:
            d = out[c.id]
            out[c.id] = RoleDecision(c.id, d.recommended_role, "contextual", d.recommended_role != "contextual",
                                     f"exclusive group '{group}': {members[0].id} already scored")
    return out


def catalogue_table(roles: Optional[Mapping[str, RoleDecision]] = None) -> List[Dict[str, object]]:
    rows = []
    for c in CATALOGUE:
        row = c.to_row()
        if roles and c.id in roles:
            row["applied_role"] = roles[c.id].applied_role
            row["role_deviates"] = roles[c.id].deviates
            row["role_reason_applied"] = roles[c.id].reason
        rows.append(row)
    return rows


def scored_ids(roles: Mapping[str, RoleDecision], pillar: Optional[str] = None) -> List[str]:
    return [m for m, d in roles.items() if d.applied_role == "scored" and (pillar is None or get(m).pillar == pillar)]
