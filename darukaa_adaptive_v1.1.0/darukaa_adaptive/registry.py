"""Evidence-aware indicator registry for the generalized adaptive framework.

The registry is the scientific contract for every indicator. Calculators should
obtain direction, applicability, scoring role and aggregation semantics here rather
than hard-coding those decisions in notebooks or reports.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass, replace
from typing import Dict, List, Optional

PILLARS = {
    "P1_extent_configuration": "Ecosystem Extent & Configuration",
    "P2_ecosystem_condition": "Ecosystem Condition",
    "P3_biodiversity_integrity": "Biodiversity Integrity",
    "P4_pressure": "Anthropogenic Pressure",
}

@dataclass(frozen=True)
class IndicatorSpec:
    name: str
    pillar: str
    construct: str
    subdimension: str
    domain: str
    units: str
    direction: str
    evidence_tier: str
    reference_type: str
    reference_allowed: bool
    default_scoring: str
    ecological_question: str
    management_use: str
    notes: str = ""
    active: bool = True
    scoring_role: str = "SCORED"
    aggregation_method: str = "area_weighted_mean"
    uncertainty_method: str = "reference_distribution"
    proxy_status: str = "proxy"
    display_name: str = ""
    source_type: str = ""
    value_range: Optional[tuple] = None
    citation: str = ""
    tier2_eligible: bool = False
    reference_radius_km: Optional[float] = None
    applicable_realms: tuple = ("terrestrial", "aquatic", "mixed")
    module: str = "core"
    input_layers: tuple = ()
    measurement_scale: Optional[str] = None
    spatial_grain: str = ""
    native_scale_m: Optional[float] = None
    dataset_asset: str = ""
    spatial_resolution: str = ""
    temporal_resolution: str = ""
    temporal_period: str = ""
    effort_basis: str = ""
    reference_estimator: Optional[str] = None
    threshold_basis: str = ""
    restoration_sensitivity: str = ""
    reassessment_frequency: str = ""
    management_trigger: str = ""
    registered: bool = True
    requires: tuple = ()
    disposition: str = ""
    contract_note: str = ""

    @property
    def higher_is_better(self) -> Optional[bool]:
        if self.direction == "higher_is_better": return True
        if self.direction == "lower_is_better": return False
        return None

# Only indicators with a defensible calculation already implemented in this package
# are activated. Additional 0.2.7 indicators are not silently promoted here.
AQUATIC_INDICATORS: List[IndicatorSpec] = [
    IndicatorSpec("water_extent","P1_extent_configuration","extent","surface_water","dynamic_water","% of master boundary","reference_target","baseline","regional_or_matched",True,"reference_relative","How much of the assessment boundary is mapped as surface water during the assessment window?","Track hydroperiod and lake-footprint departure relative to a matched reference window.","Target metric; equality with the comparable reference is the optimum.",scoring_role="SCORED",proxy_status="EO_proxy"),
    IndicatorSpec("water_persistence","P2_ecosystem_condition","hydrology","water_occurrence","dynamic_water","fraction","reference_target","baseline","regional_or_matched",True,"reference_relative","How consistently is water observed across the assessment window?","Track persistent aquatic habitat availability relative to a comparable reference.","Reference-target metric; direct monotonic interpretation is avoided.",scoring_role="SCORED",proxy_status="EO_proxy"),
    IndicatorSpec("ndci_proxy","P2_ecosystem_condition","water_quality","chlorophyll_proxy","dynamic_water","NDCI","lower_is_better","baseline","geometry_or_table",True,"reference_relative","What is the water-masked spectral signal associated with chlorophyll/trophic condition?","Flag periods for field water-quality validation and relative monitoring.","Uncalibrated spectral proxy; do not label as chlorophyll concentration.",scoring_role="SCORED",proxy_status="uncalibrated_proxy"),
    IndicatorSpec("red_reflectance_turbidity_proxy","P2_ecosystem_condition","water_quality","turbidity_proxy","dynamic_water","surface reflectance","lower_is_better","baseline","geometry_or_table",True,"reference_relative","What is the water-masked red-band reflectance associated with suspended material?","Track relative clarity/turbidity patterns and prioritize field verification.","Uncalibrated proxy; not laboratory turbidity.",scoring_role="SCORED",proxy_status="uncalibrated_proxy"),
    IndicatorSpec("surface_algal_bloom_frequency","P2_ecosystem_condition","water_quality","bloom_proxy","dynamic_water","fraction","lower_is_better","baseline","geometry_or_table",True,"reference_relative","How often do optical observations exceed the configured FAI bloom-proxy threshold?","Monitor recurring surface-bloom signals and trigger targeted field checks.","Optical screening proxy, not confirmed harmful algal bloom.",scoring_role="SCORED",proxy_status="uncalibrated_proxy"),
    IndicatorSpec("riparian_ndvi","P2_ecosystem_condition","vegetation","riparian_greenness","fixed_riparian_100m","NDVI","higher_is_better","baseline","geometry_or_table",True,"reference_relative","What is baseline greenness of the standardized riparian vegetation domain?","Compare vegetation condition with a matched reference and monitor change.","Vegetation-condition proxy.",scoring_role="SCORED",proxy_status="EO_proxy"),
    IndicatorSpec("riparian_ndvi_sen_slope","P2_ecosystem_condition","vegetation","riparian_trend","fixed_riparian_100m","NDVI/year","context_dependent","monitoring","none",False,"contextual","How has standardized riparian vegetation greenness changed over the historical trend window?","Monitor directional change and pair with land-use and field observations.","Descriptive trend; not collapsed into condition score.",scoring_role="CONTEXTUAL",proxy_status="EO_proxy"),
    IndicatorSpec("shoreline_disturbance_fraction","P4_pressure","pressure","anthropogenic_shoreline_pressure","fixed_riparian_100m","fraction","lower_is_better","baseline","geometry_or_table",True,"reference_relative","What fraction of the standardized riparian ring is mapped as anthropogenic land cover?","Identify shoreline pressure hotspots.","Pressure proxy; bare ground can include natural exposed substrate.",scoring_role="PRESSURE",proxy_status="EO_proxy"),
    IndicatorSpec("landcover_composition","P2_ecosystem_condition","vegetation_landcover","class_fractions","master_boundary","fraction by class","context_dependent","baseline","none",False,"contextual","What land-cover classes occur within the assessment boundary?","Contextualize littoral and vegetation structure.","Reported by class; not collapsed into a single score.",scoring_role="CONTEXTUAL",proxy_status="EO_classification"),
    IndicatorSpec("edna_taxon_richness","P3_biodiversity_integrity","fauna","eDNA_taxon_richness","eDNA_sampling","taxa","higher_is_better","field","field_or_matched",True,"reference_relative","How many taxa are detected by the eDNA assay under the defined sampling design?","Track faunal representation when sampling effort and laboratory QC are comparable.","Requires explicit effort and laboratory QC.",scoring_role="SCORED",proxy_status="measured_field"),
    IndicatorSpec("edna_detection_rate","P3_biodiversity_integrity","fauna","eDNA_detection","eDNA_sampling","fraction","higher_is_better","field","field_or_matched",True,"reference_relative","What proportion of defined targets/samples produced validated detections?","Track detection consistency under standardized design.","Requires sampling effort, extraction controls and assay QC.",scoring_role="SCORED",proxy_status="measured_field"),
    IndicatorSpec("edna_fish_richness","P3_biodiversity_integrity","fauna","fish_richness","eDNA_sampling","taxa","higher_is_better","field","field_or_matched",True,"reference_relative","How many validated fish taxa were detected by eDNA?","Track fish assemblage representation under comparable effort.","Taxonomic assignments require laboratory/database QC.",scoring_role="SCORED",proxy_status="measured_field"),
    IndicatorSpec("edna_persistence_potential","P3_biodiversity_integrity","eDNA_context","eDNA_persistence","eDNA_context","index","context_dependent","modelled","none",False,"contextual","Do environmental conditions favour persistence of extracellular DNA?","Interpret eDNA detectability limitations.","Contextual proxy only.",scoring_role="CONTEXTUAL",proxy_status="modelled_proxy"),
]

_AQUATIC_META = {
    "water_extent": ("GOOGLE/DYNAMICWORLD/V1", 10.0, "10 m", "near-daily / configured assessment window", "Dynamic Surface Water Extent"),
    "water_persistence": ("GOOGLE/DYNAMICWORLD/V1", 10.0, "10 m", "near-daily / configured assessment window", "Water Occurrence / Persistence"),
    "ndci_proxy": ("COPERNICUS/S2_SR_HARMONIZED", 20.0, "20 m", "configured assessment window", "NDCI Water-Quality Proxy"),
    "red_reflectance_turbidity_proxy": ("COPERNICUS/S2_SR_HARMONIZED", 20.0, "20 m", "configured assessment window", "Red Reflectance Turbidity Proxy"),
    "surface_algal_bloom_frequency": ("COPERNICUS/S2_SR_HARMONIZED", 20.0, "20 m", "configured assessment window", "Surface Algal Bloom Frequency"),
    "riparian_ndvi": ("COPERNICUS/S2_SR_HARMONIZED", 10.0, "10 m", "configured assessment window", "Riparian NDVI"),
    "riparian_ndvi_sen_slope": ("COPERNICUS/S2_SR_HARMONIZED", 10.0, "10 m", "multi-year trend window", "Riparian NDVI Trend"),
    "shoreline_disturbance_fraction": ("GOOGLE/DYNAMICWORLD/V1", 10.0, "10 m", "configured assessment window", "Shoreline/Riparian Disturbance Fraction"),
    "landcover_composition": ("GOOGLE/DYNAMICWORLD/V1", 10.0, "10 m", "configured assessment window", "Land-cover Composition"),
    "edna_taxon_richness": ("client-supplied eDNA observations", None, "field sampling", "survey-specific", "eDNA Taxon Richness"),
    "edna_detection_rate": ("client-supplied eDNA observations", None, "field sampling", "survey-specific", "eDNA Detection Rate"),
    "edna_fish_richness": ("client-supplied eDNA observations", None, "field sampling", "survey-specific", "eDNA Fish Richness"),
    "edna_persistence_potential": ("modelled/contextual eDNA input", None, "model-dependent", "survey-specific", "eDNA Persistence Potential"),
}
_AQUATIC_REALM_ONLY = {
    "water_extent", "water_persistence", "ndci_proxy", "red_reflectance_turbidity_proxy",
    "surface_algal_bloom_frequency", "riparian_ndvi", "riparian_ndvi_sen_slope",
    "shoreline_disturbance_fraction", "landcover_composition", "edna_taxon_richness",
    "edna_detection_rate", "edna_fish_richness", "edna_persistence_potential"
}
AQUATIC_INDICATORS = [
    replace(s,
            applicable_realms=("aquatic", "mixed"),
            dataset_asset=_AQUATIC_META[s.name][0],
            native_scale_m=_AQUATIC_META[s.name][1],
            spatial_resolution=_AQUATIC_META[s.name][2],
            temporal_resolution=_AQUATIC_META[s.name][3],
            display_name=_AQUATIC_META[s.name][4])
    for s in AQUATIC_INDICATORS
]

TERRESTRIAL_INDICATORS: List[IndicatorSpec] = [
    IndicatorSpec("natural_landcover_fraction","P1_extent_configuration","extent","natural_cover","master_boundary","fraction","higher_is_better","baseline","regional_or_matched",True,"reference_relative","What proportion of the assessment boundary remains in natural/semi-natural land cover?","Track habitat extent and conversion.","EO land-cover classification is a screening proxy.",scoring_role="SCORED",proxy_status="EO_proxy"),
    IndicatorSpec("terrestrial_ndvi","P2_ecosystem_condition","vegetation","greenness","master_boundary","NDVI","higher_is_better","baseline","regional_or_matched",True,"reference_relative","What is baseline vegetation greenness?","Track vegetation condition and change.","NDVI is a condition proxy, not a biodiversity observation.",scoring_role="SCORED",proxy_status="EO_proxy"),
    IndicatorSpec("built_fraction","P4_pressure","pressure","built_up","master_boundary","fraction","lower_is_better","baseline","regional_or_matched",True,"reference_relative","What fraction of the assessment boundary is mapped as built surface?","Track direct land-use pressure.","EO pressure proxy.",scoring_role="PRESSURE",proxy_status="EO_proxy"),
]


# ---------------------------------------------------------------------------
# Full legacy metric inventory (v0.2.7 authoritative calculator source)
# ---------------------------------------------------------------------------
#
# v0.2.7's live registry contains 46 registered calculators.  The legacy
# calculator implementation is vendored under legacy_reference solely as an
# implementation dependency; v1.1.0 owns applicability, status, reference
# routing, benchmarking, scoring and aggregation.
#
# Metrics that are intrinsically unsuitable for a headline reference-relative score
# in the current implementation. They remain visible and calculated, but cannot be
# promoted by a client override. This list is intentionally short. Everything else
# with a quantitative, monotonic calculation is score-selectable by default.
HARD_CONTEXT_ONLY = {
    "landcover_composition", "riparian_ndvi_trend", "net_forest_change_rate",
    "kba_overlap", "endemic_richness", "endemic_plant_richness",
    "threatened_richness", "threatened_plant_richness", "ceri",
    "flagship_habitat", "star_t", "aridity_index", "lst_day", "lst_night",
    "stsi", "iri", "ivsi", "sdi", "wsdi", "jrc_water_persistence",
}

HARD_DIAGNOSTIC = {
    "kba_overlap", "endemic_richness", "endemic_plant_richness",
    "threatened_richness", "threatened_plant_richness",
}

def metric_scoreability(spec: IndicatorSpec) -> str:
    """Return the registry-level scoring option for a metric.

    ``default_scored`` means it is included by default but can be demoted.
    ``context_only`` means it is intentionally not scoreable in this release.
    ``diagnostic`` and ``removed`` are hard-gated.
    """
    if spec.name in {"ceri"}:
        return "removed"
    if spec.name in HARD_DIAGNOSTIC or spec.disposition == "screening":
        return "diagnostic"
    if spec.name in HARD_CONTEXT_ONLY:
        return "context_only"
    return "default_scored"

def effective_scoring_role(spec: IndicatorSpec, config=None) -> str:
    """Resolve the runtime role without modifying the scientific registry.

    EII is a hierarchical construct: the provider's parent EII and its three
    component dimensions must never enter the same headline condition score.
    ``config.scoring.eii_mode`` therefore acts as a hard scientific gate:

    * ``components`` (default): structural/compositional/functional components
      are score-eligible; the parent EII is diagnostic/contextual.
    * ``parent``: the parent EII is score-eligible; all three components are
      diagnostic/contextual.
    * ``none``: all EII layers are diagnostic/contextual.

    User metric overrides may demote a scoreable metric, but cannot promote an
    EII layer that is excluded by the selected hierarchy mode.
    """
    cls = metric_scoreability(spec)
    if cls in {"removed", "diagnostic", "context_only"}:
        return {"removed":"REMOVED", "diagnostic":"DIAGNOSTIC", "context_only":"CONTEXTUAL"}[cls]

    scoring_cfg = getattr(config, "scoring", None)
    eii_mode = str(getattr(scoring_cfg, "eii_mode", "components")).lower()
    eii_parent = {"eii"}
    eii_components = {"eii_structural", "eii_compositional", "eii_functional"}

    if spec.name in eii_parent and eii_mode != "parent":
        return "CONTEXTUAL"
    if spec.name in eii_components and eii_mode != "components":
        return "CONTEXTUAL"

    overrides = getattr(scoring_cfg, "metric_overrides", {}) or {}
    if spec.name in overrides:
        return "SCORED" if overrides[spec.name] == "scored" else "CONTEXTUAL"
    return "SCORED" if getattr(scoring_cfg, "score_all_scoreable_metrics", True) else spec.scoring_role

def metric_selection_table(config=None) -> List[Dict]:
    """Return the unified metric registry, optionally overlaid with the run period.

    The static registry cannot know the actual assessment dates. When a runtime
    config is supplied, empty ``temporal_period`` fields are populated with the
    configured baseline/trend window so the audit table is operationally useful.
    """
    rows=[]
    for spec in INDICATORS:
        rows.append({
            "metric": spec.name, "display_name": spec.display_name or spec.name,
            "pillar": spec.pillar, "construct": spec.construct,
            "domain": spec.domain, "direction": spec.direction,
            "scoreability": metric_scoreability(spec),
            "registry_role": spec.scoring_role,
            "reference_type": spec.reference_type,
            "source": spec.source_type, "dataset_asset": spec.dataset_asset,
            "native_scale_m": spec.native_scale_m, "spatial_resolution": spec.spatial_resolution,
            "temporal_resolution": spec.temporal_resolution,
            "temporal_period": spec.temporal_period,
            "notes": spec.contract_note or spec.notes,
        })
    if config is not None:
        temporal = getattr(config, "temporal", None)
        baseline_label = getattr(temporal, "baseline_label", "configured baseline window") if temporal else "configured baseline window"
        if temporal and hasattr(temporal, "baseline_inclusive_window"):
            try:
                bs, be = temporal.baseline_inclusive_window()
                baseline_label = f"{baseline_label} [{bs} to {be}]"
            except Exception:
                pass
        trend_label = None
        if temporal and hasattr(temporal, "start_year") and hasattr(temporal, "end_year"):
            trend_label = f"trend window [{temporal.start_year}-01-01 to {temporal.end_year}-12-31]"
        trend_metrics = {"riparian_ndvi_sen_slope", "riparian_ndvi_trend", "net_forest_change_rate"}
        for row in rows:
            if not row.get("temporal_period"):
                row["temporal_period"] = trend_label if row["metric"] in trend_metrics and trend_label else baseline_label
    return rows


def _legacy_to_adaptive_spec(legacy_spec) -> IndicatorSpec:
    disposition = str((legacy_spec.metadata or {}).get("disposition", ""))
    if disposition in {"retain", "redefine"} and legacy_spec.eligible:
        role = "SCORED"
    elif disposition == "screening":
        role = "DIAGNOSTIC"
    elif disposition == "remove":
        role = "REMOVED"
    else:
        role = "CONTEXTUAL"
    pillar_map = {1: "P1_extent_configuration", 2: "P2_ecosystem_condition",
                  3: "P3_biodiversity_integrity", 4: "P4_pressure"}
    # Contract construct placement is authoritative. Legacy numeric pillar values
    # predate the generalized P1-P4 separation and can be stale for pressure metrics.
    construct_to_pillar = {
        "C1_landscape": "P1_extent_configuration",
        "C2_vegetation": "P2_ecosystem_condition",
        "C3_fauna": "P3_biodiversity_integrity",
        "C4_pressure": "P4_pressure",
    }
    direction = "higher_is_better" if legacy_spec.higher_is_better else "lower_is_better"
    # A contextual metric may have a direction in the legacy registry, but that
    # does not make it score-eligible.
    if legacy_spec.name in {"wsdi"}:
        direction = "lower_is_better"
    return IndicatorSpec(
        name=legacy_spec.name,
        pillar=construct_to_pillar.get(legacy_spec.construct, pillar_map.get(legacy_spec.pillar, "P2_ecosystem_condition")),
        construct=legacy_spec.construct or "",
        subdimension=legacy_spec.subdimension or "",
        domain=legacy_spec.realm,
        units=legacy_spec.unit,
        direction=direction,
        evidence_tier=legacy_spec.evidence_tier,
        reference_type=legacy_spec.reference_type or "none",
        reference_allowed=bool(legacy_spec.reference_type),
        default_scoring="reference_relative" if (disposition not in {"screening","remove"} and legacy_spec.name not in HARD_CONTEXT_ONLY) else "context_only",
        ecological_question=legacy_spec.ecological_question or "",
        management_use=legacy_spec.management_use or "",
        notes=str((legacy_spec.metadata or {}).get("contract_note", "")),
        active=bool(legacy_spec.active),
        scoring_role=role,
        aggregation_method="geometric_mean" if role == "SCORED" else "none",
        uncertainty_method=legacy_spec.uncertainty_method or "none",
        proxy_status="EO_proxy" if legacy_spec.source_type == "gee" else legacy_spec.source_type,
        display_name=legacy_spec.display_name,
        source_type=legacy_spec.source_type,
        value_range=legacy_spec.value_range,
        citation=legacy_spec.citation,
        tier2_eligible=legacy_spec.tier2_eligible,
        reference_radius_km=legacy_spec.reference_radius_km,
        applicable_realms=tuple(legacy_spec.applicable_realms),
        module=legacy_spec.module,
        input_layers=tuple(legacy_spec.input_layers),
        measurement_scale=legacy_spec.measurement_scale,
        spatial_grain=legacy_spec.spatial_grain,
        native_scale_m=legacy_spec.native_scale_m,
        temporal_period=legacy_spec.temporal_period,
        effort_basis=legacy_spec.effort_basis,
        reference_estimator=legacy_spec.reference_estimator,
        threshold_basis=legacy_spec.threshold_basis,
        restoration_sensitivity=legacy_spec.restoration_sensitivity,
        reassessment_frequency=legacy_spec.reassessment_frequency,
        management_trigger=legacy_spec.management_trigger,
        registered=legacy_spec.registered,
        requires=tuple(legacy_spec.requires),
        disposition=disposition,
        contract_note=str((legacy_spec.metadata or {}).get("contract_note", "")),
    )

try:
    from .legacy_reference.indicators import create_default_registry as _create_legacy_registry
    _LEGACY_REGISTRY = _create_legacy_registry()
    LEGACY_INDICATORS = [_legacy_to_adaptive_spec(x) for x in _LEGACY_REGISTRY.all()]

    # Source/provenance overrides are maintained here because several legacy
    # metadata fields predate the v1.1.0 scientific audit. These values describe
    # the calculators actually shipped in the current package.
    _SOURCE_OVERRIDES = {
        "eii": ("landler-open-data/assets/eii/global/eii_global_v1", 300.0, ("landbanking_eii",)),
        "eii_structural": ("landler-open-data/assets/eii/global/eii_global_v1", 300.0, ("landbanking_eii",)),
        "eii_compositional": ("landler-open-data/assets/eii/global/eii_global_v1", 300.0, ("landbanking_eii",)),
        "eii_functional": ("landler-open-data/assets/eii/global/eii_global_v1", 300.0, ("landbanking_eii",)),
        "bii": ("ebx-data/assets/earthblox/IO/BII_V1_1", 100.0, ("predicts_bii",)),
        "chm": ("meta-forest-monitoring-okw37/assets/CanopyHeight", 1.0, ("meta_wri_canopy_height",)),
    }
    for _name, (_source, _scale, _layers) in _SOURCE_OVERRIDES.items():
        for _i, _spec in enumerate(LEGACY_INDICATORS):
            if _spec.name == _name:
                LEGACY_INDICATORS[_i] = replace(_spec, source_type=_source, native_scale_m=_scale, input_layers=_layers)
                break
    _DATASET_META = {
        "dynamic_world": ("GOOGLE/DYNAMICWORLD/V1", 10.0, "10 m", "near-daily / configured assessment window"),
        "hansen_gfc": ("UMD/hansen/global_forest_change_2025_v1_13", 30.0, "30 m", "annual loss-year; 2000 baseline"),
        "sentinel2": ("COPERNICUS/S2_SR_HARMONIZED", 10.0, "10 m", "configured assessment window"),
        "sentinel2_ndvi": ("COPERNICUS/S2_SR_HARMONIZED", 10.0, "10 m", "configured assessment/trend window"),
        "landbanking_eii": ("landler-open-data/assets/eii/global/eii_global_v1", 300.0, "300 m", "annual"),
        "predicts_bii": ("ebx-data/assets/earthblox/IO/BII_V1_1", 100.0, "100 m", "annual / available year"),
        "meta_wri_canopy_height": ("projects/meta-forest-monitoring-okw37/assets/CanopyHeight", 1.0, "~1 m", "static canopy-height product"),
        "chirps_terraclimate": ("CHIRPS + TerraClimate", None, "source-dependent", "annual aggregation"),
        "modis_lai": ("MODIS/061/MCD15A3H", 500.0, "500 m", "4-day"),
        "modis_lst": ("MODIS/061/MOD11A1", 1000.0, "1 km", "daily"),
        "viirs_ntl": ("NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG", 500.0, "~500 m", "monthly"),
        "csp_ghm": ("TNC Global Human Modification v3", 90.0, "90 m", "static"),
        "dw_builtup": ("GOOGLE/DYNAMICWORLD/V1", 10.0, "10 m", "near-daily / configured assessment window"),
        "jrc_water": ("COPERNICUS/S1_GRD", 10.0, "10 m", "configured annual window"),
    }
    _KNOWN_SCALES = {
        "natural_habitat":10.0, "hdi":10.0, "forest_loss_rate":30.0,
        "chm":1.0, "ghm":90.0, "light_pollution":500.0,
        "tspi":10.0, "sabf":10.0, "wcpi":10.0, "edpp":10.0,
        "mspl":10.0, "rci":10.0, "wsdi":10.0, "sdi":10.0, "iri":10.0,
        "net_forest_change_rate":30.0,
    }
    _KNOWN_ASSET_FALLBACK = {
        "kba_overlap":"KBA/IBAT source; exact asset configured/verified at runtime", "flii_asset":"FLII source asset configured in legacy calculator",
        "india_pv_binary":"India PV binary habitat source configured in legacy calculator", "iucn_range_maps":"IUCN species-range source configured in legacy calculator",
        "mol_api":"Map of Life API (external; requires credentials/access)", "edna_points":"client-supplied eDNA point asset/input", "lc_impact_pdf":"land-cover biodiversity-impact source configured in legacy calculator",
    }
    for _i,_spec in enumerate(LEGACY_INDICATORS):
        _layers=list(_spec.input_layers); _key=_layers[0] if _layers else ""; _meta=_DATASET_META.get(_key)
        _asset=_spec.source_type if _spec.source_type and _spec.source_type != "gee" else (_meta[0] if _meta else _KNOWN_ASSET_FALLBACK.get(_key, "not_individually_confirmed"))
        _scale=_spec.native_scale_m or _KNOWN_SCALES.get(_spec.name) or (_meta[1] if _meta else None)
        _sres=(_meta[2] if _meta else (f"{int(_scale)} m" if _scale else "not_individually_confirmed"))
        _tres=(_meta[3] if _meta else ("configured assessment window" if _spec.temporal_period=="" else _spec.temporal_period))
        LEGACY_INDICATORS[_i]=replace(_spec,dataset_asset=_asset,native_scale_m=_scale,spatial_resolution=_sres,temporal_resolution=_tres)
    # Calculator-specific provenance corrections. These override generic input-layer
    # labels where the implementation uses a different source than the legacy key suggests.
    for _i,_spec in enumerate(LEGACY_INDICATORS):
        if _spec.name == "wsdi":
            LEGACY_INDICATORS[_i]=replace(_spec,dataset_asset="COPERNICUS/S1_GRD", spatial_resolution="10 m", temporal_resolution="configured assessment window")
        elif _spec.name == "jrc_water_persistence":
            LEGACY_INDICATORS[_i]=replace(_spec,dataset_asset="COPERNICUS/S1_GRD", spatial_resolution="10 m", temporal_resolution="configured annual window", display_name="Persistent Water Fraction (Sentinel-1 SAR)")
        elif _spec.name == "net_forest_change_rate":
            LEGACY_INDICATORS[_i]=replace(_spec,dataset_asset="Hansen GFC + GOOGLE/DYNAMICWORLD/V1", spatial_resolution="30 m loss layer + 10 m DW", temporal_resolution="annual loss + current DW tree expansion")
except Exception:
    # Registry import must remain usable even in environments where optional
    # legacy dependencies are unavailable. The calculator engine will report
    # the dependency failure at execution time.
    _LEGACY_REGISTRY = None
    LEGACY_INDICATORS = []

# Full 0.2.7 inventory.  Existing v1 compatibility indicators remain available;
# names are distinct, so no concept is silently overwritten.
FULL_INDICATORS = LEGACY_INDICATORS

# Backwards-compatible aliases for code that imported the older constants.
INDICATORS = AQUATIC_INDICATORS + TERRESTRIAL_INDICATORS + FULL_INDICATORS
_DYNAMIC_REGISTRY: Dict[str, IndicatorSpec] = {}
PILLAR_ALIASES = {
    "C1_extent": "P1_extent_configuration",
    "C2_vegetation": "P2_ecosystem_condition",
    "C3_fauna": "P3_biodiversity_integrity",
    "C4_pressure": "P4_pressure",
}


def register_indicator(spec: IndicatorSpec, overwrite: bool = False) -> IndicatorSpec:
    if spec.name in {x.name for x in INDICATORS} and not overwrite:
        raise ValueError(f"Indicator already registered: {spec.name}")
    pillar = PILLAR_ALIASES.get(spec.pillar, spec.pillar)
    if pillar not in PILLARS:
        raise ValueError(f"Unknown pillar: {spec.pillar}")
    normalized = replace(spec, pillar=pillar)
    _DYNAMIC_REGISTRY[normalized.name] = normalized
    return normalized

def get_registered_indicator(name: str) -> IndicatorSpec:
    return get_indicator_spec(name)

def indicator_table() -> List[Dict]:
    return [asdict(x) for x in INDICATORS] + [asdict(x) for x in _DYNAMIC_REGISTRY.values()]

def get_indicator_spec(name: str) -> IndicatorSpec:
    if name in _DYNAMIC_REGISTRY:
        return _DYNAMIC_REGISTRY[name]
    for spec in INDICATORS:
        if spec.name == name:
            return spec
    raise KeyError(f"Unknown indicator: {name}")

def legacy_crosswalk() -> List[Dict]:
    return [{"metric": s.name, "pillar": s.pillar, "subdimension": s.subdimension,
             "scoring_role": s.scoring_role, "status": "active" if s.active else "inactive"} for s in INDICATORS]
