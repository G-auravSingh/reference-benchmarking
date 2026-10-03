"""Indicator contracts for the generalized adaptive biodiversity framework.

The registry is metadata, not the metric calculator. It defines applicability, pillar,
direction, referenceability, evidence, and the preferred scoring pathway.

The adaptive pillar structure is intentionally shared across ecosystem realms:
C1 = Extent
C2 = Vegetation
C3 = Fauna
C4 = Pressure

External/field observations do not need to be hard-coded here: the generic scoring API
accepts observation metadata directly (metric, pillar, direction, reference, etc.).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List, Optional


PILLARS = {
    "C1_extent": "Extent",
    "C2_vegetation": "Vegetation",
    "C3_fauna": "Fauna",
    "C4_pressure": "Pressure",
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

    @property
    def higher_is_better(self) -> Optional[bool]:
        if self.direction == "higher_is_better":
            return True
        if self.direction == "lower_is_better":
            return False
        return None


AQUATIC_INDICATORS: List[IndicatorSpec] = [
    IndicatorSpec(
        "water_extent",
        "C1_extent",
        "extent",
        "surface_water",
        "dynamic_water",
        "% of master boundary",
        "reference_target",
        "baseline",
        "regional_or_matched",
        True,
        "reference_relative",
        "How much of the master boundary is mapped as surface water during the assessment window?",
        "Track hydroperiod and lake-footprint departure relative to a matched reference window.",
        "Reference-target metric: equality with the comparable reference is the intactness optimum; not intrinsically higher-is-better.",
    ),
    IndicatorSpec(
        "water_persistence",
        "C1_extent",
        "hydrology",
        "water_occurrence",
        "dynamic_water",
        "fraction",
        "reference_target",
        "baseline",
        "regional_or_matched",
        True,
        "reference_relative",
        "How consistently is water observed across the assessment window?",
        "Track persistent-water habitat availability relative to a comparable reference.",
        "Reference-target metric; direct monotonic interpretation is avoided.",
    ),
    IndicatorSpec(
        "ndci_proxy",
        "C1_extent",
        "water_quality",
        "chlorophyll_proxy",
        "dynamic_water",
        "NDCI",
        "lower_is_better",
        "baseline",
        "geometry_or_table",
        True,
        "reference_relative",
        "What is the water-masked spectral signal associated with chlorophyll/trophic condition?",
        "Flag periods for field water-quality validation and relative monitoring.",
        "Remote-sensing proxy; reference comparison is allowed only when the reference is scientifically comparable.",
    ),
    IndicatorSpec(
        "red_reflectance_turbidity_proxy",
        "C1_extent",
        "water_quality",
        "turbidity_proxy",
        "dynamic_water",
        "surface reflectance",
        "lower_is_better",
        "baseline",
        "geometry_or_table",
        True,
        "reference_relative",
        "What is the water-masked red-band reflectance associated with suspended material?",
        "Track relative clarity/turbidity patterns and prioritize field verification.",
        "Proxy only; do not label as calibrated turbidity without independent validation.",
    ),
    IndicatorSpec(
        "surface_algal_bloom_frequency",
        "C1_extent",
        "water_quality",
        "bloom_proxy",
        "dynamic_water",
        "fraction",
        "lower_is_better",
        "baseline",
        "geometry_or_table",
        True,
        "reference_relative",
        "How often do water-masked optical observations exceed the configured FAI bloom-proxy threshold?",
        "Monitor recurring surface-bloom signals and trigger targeted field checks.",
        "Surface optical screening proxy, not a confirmed harmful algal-bloom observation.",
    ),
    IndicatorSpec(
        "riparian_ndvi",
        "C2_vegetation",
        "vegetation",
        "riparian_greenness",
        "fixed_riparian_100m",
        "NDVI",
        "higher_is_better",
        "baseline",
        "geometry_or_table",
        True,
        "reference_relative",
        "What is the baseline greenness of the standardized riparian vegetation domain?",
        "Compare vegetation condition with a matched reference and monitor change.",
        "Greenness is a vegetation-condition proxy; it is not a direct biodiversity measure.",
    ),
    IndicatorSpec(
        "riparian_ndvi_sen_slope",
        "C2_vegetation",
        "vegetation",
        "riparian_trend",
        "fixed_riparian_100m",
        "NDVI/year",
        "context_dependent",
        "monitoring",
        "none",
        False,
        "contextual",
        "How has standardized riparian vegetation greenness changed over the historical trend window?",
        "Monitor directional change and pair with land-use and field observations.",
        "Descriptive trend metric; not converted directly to intactness.",
    ),
    IndicatorSpec(
        "shoreline_disturbance_fraction",
        "C4_pressure",
        "pressure",
        "anthropogenic_shoreline_pressure",
        "fixed_riparian_100m",
        "fraction",
        "lower_is_better",
        "baseline",
        "geometry_or_table",
        True,
        "reference_relative",
        "What fraction of the standardized riparian ring is mapped as crops, built or bare land?",
        "Identify shoreline pressure hotspots and prioritize management attention.",
        "EO land-use pressure proxy; bare ground can include natural exposed substrate.",
    ),
    IndicatorSpec(
        "landcover_composition",
        "C2_vegetation",
        "vegetation_landcover",
        "class_fractions",
        "master_boundary",
        "fraction by class",
        "context_dependent",
        "baseline",
        "none",
        False,
        "contextual",
        "What land-cover classes occur within the master boundary?",
        "Contextualize littoral and vegetation structure.",
        "Reported by class rather than collapsed into a single ecological score.",
    ),

    IndicatorSpec("edna_taxon_richness", "C3_fauna", "fauna", "eDNA_taxon_richness", "eDNA_sampling", "taxa", "higher_is_better", "field", "field_or_matched", True, "reference_relative", "How many taxa are detected by the eDNA assay under the defined sampling design?", "Track aquatic/faunal representation when sampling effort and laboratory QC are comparable.", "eDNA detection is evidence of DNA presence/detection, not automatically confirmed local population size."),
    IndicatorSpec("edna_detection_rate", "C3_fauna", "fauna", "eDNA_detection", "eDNA_sampling", "fraction", "higher_is_better", "field", "field_or_matched", True, "reference_relative", "What proportion of defined eDNA targets/samples produced validated detections?", "Track detection consistency under a standardized sampling design.", "Requires explicit sampling effort, extraction controls and assay/QC metadata."),
    IndicatorSpec("edna_fish_richness", "C3_fauna", "fauna", "fish_richness", "eDNA_sampling", "taxa", "higher_is_better", "field", "field_or_matched", True, "reference_relative", "How many validated fish taxa were detected by eDNA?", "Track fish assemblage representation when the assay and effort are comparable.", "Taxonomic assignments require laboratory/database QC and should not be treated as abundance without validation."),
    IndicatorSpec("edna_persistence_potential", "C3_fauna", "eDNA_persistence", "eDNA_persistence", "eDNA_context", "index", "context_dependent", "modelled", "none", False, "contextual", "Do environmental conditions favour persistence of extracellular DNA?", "Interpret eDNA detectability and sampling design limitations.", "Contextual proxy; the Nandoshi report presents this as persistence potential, not a direct eDNA detection metric."),
    IndicatorSpec("natural_landcover_fraction", "C1_extent", "extent", "natural_cover", "master_boundary", "fraction", "higher_is_better", "baseline", "regional_or_matched", True, "reference_relative", "What proportion of the assessment boundary remains in natural/semi-natural land-cover classes?", "Track habitat extent and conversion.", "EO land-cover classification is a screening proxy."),
    IndicatorSpec("terrestrial_ndvi", "C2_vegetation", "vegetation", "greenness", "master_boundary", "NDVI", "higher_is_better", "baseline", "regional_or_matched", True, "reference_relative", "What is the baseline vegetation greenness?", "Track vegetation condition and change.", "NDVI is a condition proxy, not a biodiversity observation."),
    IndicatorSpec("built_fraction", "C4_pressure", "pressure", "built_up", "master_boundary", "fraction", "lower_is_better", "baseline", "regional_or_matched", True, "reference_relative", "What fraction of the assessment boundary is mapped as built surface?", "Track direct land-use pressure.", "EO built-up fraction is a pressure proxy."),
]

@dataclass(frozen=True)
class MetricSpec:
    legacy_name: str
    aquatic_status: str
    aquatic_domain: str
    scoring_default: str
    pillar: str
    rationale: str


_LEGACY_PILLAR = {
    # Extent / ecosystem footprint
    "natural_habitat": "C1_extent",
    "natural_landcover": "C1_extent",
    "cpland": "C1_extent",
    "kba_overlap": "C1_extent",
    "flii": "C1_extent",
    "eii": "C1_extent",
    "eii_structural": "C1_extent",
    "eii_compositional": "C1_extent",
    "eii_functional": "C1_extent",
    "pdf": "C3_fauna",
    "aridity_index": "C1_extent",
    "tspi": "C1_extent",
    "sabf": "C1_extent",
    "wcpi": "C1_extent",
    "wsdi": "C1_extent",
    "hsas": "C1_extent",
    "edpp": "C1_extent",
    "mspl": "C1_extent",
    "jrc_water_persistence": "C1_extent",
    "shdi": "C1_extent",
    # Vegetation
    "ndvi": "C2_vegetation",
    "habitat_health": "C2_vegetation",
    "rci": "C2_vegetation",
    "riparian_ndvi_trend": "C2_vegetation",
    "lai": "C2_vegetation",
    "chm": "C2_vegetation",
    # Fauna / biodiversity
    "bii": "C3_fauna",
    "endemic_richness": "C3_fauna",
    "endemic_plant_richness": "C3_fauna",
    "threatened_richness": "C3_fauna",
    "ceri": "C3_fauna",
    "threatened_plant_richness": "C3_fauna",
    "flagship_habitat": "C3_fauna",
    # Pressure
    "forest_loss_rate": "C4_pressure",
    "star_t": "C4_pressure",
    "ghm": "C4_pressure",
    "light_pollution": "C4_pressure",
    "hdi": "C4_pressure",
    "lst_day": "C4_pressure",
    "lst_night": "C4_pressure",
    "sdi": "C4_pressure",
    "stsi": "C4_pressure",
    "iri": "C4_pressure",
    "ivsi": "C4_pressure",
}


# Frozen 44-indicator legacy crosswalk; the legacy implementation itself remains untouched.
_LEGACY_ROWS = [
    ("natural_habitat", "modify", "land_context", "disabled", "Terrestrial habitat classes cannot treat lake water as habitat loss."),
    ("natural_landcover", "modify", "land_context", "disabled", "Recompute on non-water land domain only."),
    ("cpland", "context", "context", "disabled", "Landscape connectivity is a context metric and needs a surrounding landscape."),
    ("forest_loss_rate", "context", "land_context", "disabled", "Forest-specific change is contextual for a lake."),
    ("kba_overlap", "context", "master_boundary", "contextual", "Conservation designation, not ecosystem condition."),
    ("ndvi", "modify", "fixed_riparian_or_land_context", "contextual", "NDVI is meaningful on vegetated domains, not open water."),
    ("habitat_health", "modify", "fixed_riparian_or_land_context", "disabled", "Legacy formulation is terrestrial."),
    ("flii", "exclude", "none", "disabled", "Forest landscape integrity is not a general lake metric."),
    ("eii", "exclude", "none", "disabled", "Legacy ecosystem-integrity composite is terrestrial and overlaps other indicators."),
    ("eii_structural", "exclude", "none", "disabled", "Terrestrial structural component."),
    ("eii_compositional", "exclude", "none", "disabled", "Terrestrial compositional component."),
    ("eii_functional", "exclude", "none", "disabled", "Terrestrial functional component."),
    ("bii", "context", "broader_reference", "contextual", "Global biodiversity intactness context is not a local lake population observation."),
    ("pdf", "exclude", "none", "disabled", "GLOBIO/PDF formulation is not directly interpretable inside open-water footprint."),
    ("aridity_index", "context", "broader_reference", "contextual", "Climate context, not lake condition."),
    ("tspi", "modify", "dynamic_water", "disabled", "Use NDCI only as a water-masked proxy with no automatic universal threshold."),
    ("sabf", "modify", "dynamic_water", "disabled", "FAI bloom-proxy frequency is sensor/threshold dependent."),
    ("wcpi", "modify", "dynamic_water", "disabled", "Water clarity/turbidity proxy must remain water-masked and uncalibrated unless validated."),
    ("wsdi", "modify", "dynamic_water_time_series", "disabled", "Replace non-monotonic legacy score with explicit water-area dynamics/persistence series."),
    ("hsas", "exclude", "none", "disabled", "Legacy habitat suitability surface is not a validated aquatic habitat model."),
    ("edpp", "context", "dynamic_water", "disabled", "Heuristic environmental proxy; not a direct eDNA persistence measure."),
    ("mspl", "context", "dynamic_water", "disabled", "Heuristic composite; not a validated microbial-stress probability."),
    ("rci", "modify", "fixed_riparian_100m", "disabled", "Riparian complexity can be reported on a fixed standardized vegetation domain."),
    ("riparian_ndvi_trend", "modify", "fixed_riparian_100m", "disabled", "Use multi-year seasonal composites and robust trend statistics."),
    ("jrc_water_persistence", "context", "historical_context", "contextual", "Useful through 2021 only; current monitoring should use current EO observations."),
    ("shdi", "context", "dynamic_water_boundary", "contextual", "Morphometry/shape statistic; scale-dependent and not a generic condition score."),
    ("lai", "context", "fixed_riparian_100m", "contextual", "Vegetation structure context outside open water."),
    ("chm", "context", "fixed_riparian_100m", "contextual", "Canopy-height context only where woody vegetation exists."),
    ("endemic_richness", "context", "master_boundary_or_context", "contextual", "Range-overlap screening does not confirm local occurrence."),
    ("flagship_habitat", "exclude", "none", "disabled", "Legacy model is forest/elevation-oriented and not a lake model."),
    ("endemic_plant_richness", "context", "master_boundary_or_context", "contextual", "Range-overlap screening does not confirm local plant occurrence."),
    ("threatened_richness", "context", "master_boundary_or_context", "contextual", "Range overlap is conservation context, not confirmed population size."),
    ("ceri", "context", "master_boundary_or_context", "contextual", "Range-overlap weighted conservation sensitivity, not local extinction probability."),
    ("star_t", "exclude", "none", "disabled", "Legacy threat-abatement proxy is not direct extinction risk and needs redesign before aquatic use."),
    ("threatened_plant_richness", "context", "master_boundary_or_context", "contextual", "Range-overlap screening does not confirm local plant occurrence."),
    ("ghm", "context", "broader_reference", "contextual", "Human-modification context, not lake condition."),
    ("light_pollution", "context", "broader_reference", "contextual", "External pressure context, particularly nocturnal ecology."),
    ("hdi", "context", "broader_reference", "contextual", "Human-development context rather than direct lake condition."),
    ("lst_day", "context", "riparian_or_context", "contextual", "Thermal context; interpretation needs land/water separation."),
    ("lst_night", "context", "riparian_or_context", "contextual", "Thermal context; interpretation needs land/water separation."),
    ("sdi", "modify", "fixed_riparian_100m", "disabled", "Use a transparent disturbed-land fraction around the shoreline/riparian domain."),
    ("stsi", "context", "dynamic_water", "disabled", "Legacy site-normalized thermal stress proxy needs calibration before scoring."),
    ("iri", "context", "dynamic_water_and_context", "disabled", "Heuristic invasion-risk proxy; should not be treated as observed invasive pressure."),
    ("ivsi", "exclude", "none", "disabled", "NDVI expansion signal is not taxonomic invasive-species evidence."),
]

LEGACY_METRIC_SPECS: List[MetricSpec] = [
    MetricSpec(name, status, domain, scoring, _LEGACY_PILLAR.get(name, "C1_extent"), rationale)
    for name, status, domain, scoring, rationale in _LEGACY_ROWS
]


def get_indicator_spec(name: str) -> IndicatorSpec:
    for spec in AQUATIC_INDICATORS:
        if spec.name == name:
            return spec
    raise KeyError(name)


def indicator_table() -> List[Dict]:
    return [asdict(x) for x in AQUATIC_INDICATORS]


def legacy_crosswalk() -> List[Dict]:
    return [asdict(x) for x in LEGACY_METRIC_SPECS]


def get_metric_spec(name: str) -> MetricSpec:
    for spec in LEGACY_METRIC_SPECS:
        if spec.legacy_name == name:
            return spec
    raise KeyError(name)


def names() -> List[str]:
    return [x.legacy_name for x in LEGACY_METRIC_SPECS]

# --- Generalized extensibility API -------------------------------------------------
# The built-in indicators remain immutable metadata, while future EO, acoustic,
# eDNA, camera-trap, field and model-derived indicators can register through the
# same contract. Registration is process-local and intentionally explicit.

INDICATOR_REGISTRY: Dict[str, IndicatorSpec] = {x.name: x for x in AQUATIC_INDICATORS}


def validate_indicator_spec(spec: IndicatorSpec) -> None:
    if not spec.name or any(c.isspace() for c in spec.name):
        raise ValueError("Indicator name must be a non-empty machine-readable identifier")
    if spec.pillar not in PILLARS:
        raise ValueError(f"Unknown pillar: {spec.pillar}")
    if spec.direction not in {"higher_is_better", "lower_is_better", "reference_target", "context_dependent"}:
        raise ValueError(f"Unsupported direction: {spec.direction}")
    if spec.default_scoring not in {"reference_relative", "contextual", "raw", "none"}:
        raise ValueError(f"Unsupported scoring pathway: {spec.default_scoring}")
    if spec.reference_allowed and spec.reference_type == "none":
        raise ValueError("reference_allowed=True requires a reference_type")


def register_indicator(spec: IndicatorSpec, *, overwrite: bool = False) -> IndicatorSpec:
    """Register an indicator using the production metadata contract."""
    validate_indicator_spec(spec)
    if spec.name in INDICATOR_REGISTRY and not overwrite:
        raise KeyError(f"Indicator already registered: {spec.name}")
    INDICATOR_REGISTRY[spec.name] = spec
    return spec


def get_registered_indicator(name: str) -> IndicatorSpec:
    try:
        return INDICATOR_REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"Unknown registered indicator: {name}") from exc


def registered_indicator_table() -> List[Dict]:
    return [asdict(x) for x in INDICATOR_REGISTRY.values()]
