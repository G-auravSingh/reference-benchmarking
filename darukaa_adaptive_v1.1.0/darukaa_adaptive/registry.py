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
    direction = "higher_is_better" if legacy_spec.higher_is_better else "lower_is_better"
    # A contextual metric may have a direction in the legacy registry, but that
    # does not make it score-eligible.
    if legacy_spec.name in {"wsdi"}:
        direction = "lower_is_better"
    return IndicatorSpec(
        name=legacy_spec.name,
        pillar=pillar_map.get(legacy_spec.pillar, "P2_ecosystem_condition"),
        construct=legacy_spec.construct or "",
        subdimension=legacy_spec.subdimension or "",
        domain=legacy_spec.realm,
        units=legacy_spec.unit,
        direction=direction,
        evidence_tier=legacy_spec.evidence_tier,
        reference_type=legacy_spec.reference_type or "none",
        reference_allowed=bool(legacy_spec.reference_type),
        default_scoring="reference_relative" if role == "SCORED" else "context_only",
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
