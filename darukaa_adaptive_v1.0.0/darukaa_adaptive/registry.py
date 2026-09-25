"""Indicator contracts for the adaptive framework.

The native registry controls applicability, evidence tier, reference eligibility and
whether a metric is allowed into ecological scoring. The legacy crosswalk is retained
for compatibility and does not activate legacy terrestrial calculations.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List, Optional


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

    @property
    def higher_is_better(self) -> Optional[bool]:
        if self.direction == "higher_is_better":
            return True
        if self.direction == "lower_is_better":
            return False
        return None


AQUATIC_INDICATORS: List[IndicatorSpec] = [
    IndicatorSpec(
        "water_extent", "P1_ecosystem_condition", "extent", "surface_water", "dynamic_water",
        "% of master boundary", "context_dependent", "baseline", "none", False, "contextual",
        "How much of the master boundary is mapped as surface water during the assessment window?",
        "Hydroperiod and lake-footprint tracking; interpret only against a consistent seasonal window.",
        "Not intrinsically better or worse because lake extent is hydroclimatically driven.",
    ),
    IndicatorSpec(
        "water_persistence", "P1_ecosystem_condition", "hydrology", "water_occurrence", "dynamic_water",
        "fraction", "context_dependent", "baseline", "none", False, "contextual",
        "How consistently is water observed at pixels within the master boundary?",
        "Track hydroperiod shifts and persistent-water habitat availability.",
        "Legacy WSDI-style interpretations are not reused because occurrence is not a monotonic condition score.",
    ),
    IndicatorSpec(
        "ndci_proxy", "P1_ecosystem_condition", "water_quality", "chlorophyll_proxy", "dynamic_water",
        "NDCI", "lower_is_better", "baseline", "geometry_or_table", True, "eligible_if_thresholded",
        "What is the water-masked spectral signal associated with chlorophyll/trophic condition?",
        "Flag periods for field water-quality validation and trend monitoring.",
        "Proxy only; calibration is required before ecological thresholds are used.",
    ),
    IndicatorSpec(
        "red_reflectance_turbidity_proxy", "P1_ecosystem_condition", "water_quality", "turbidity_proxy", "dynamic_water",
        "surface reflectance", "lower_is_better", "baseline", "geometry_or_table", True, "eligible_if_thresholded",
        "What is the water-masked red-band reflectance associated with suspended material?",
        "Track relative clarity/turbidity patterns and prioritize field verification.",
        "Proxy only; do not report as calibrated turbidity without validation.",
    ),
    IndicatorSpec(
        "surface_algal_bloom_frequency", "P1_ecosystem_condition", "water_quality", "bloom_proxy", "dynamic_water",
        "fraction", "lower_is_better", "baseline", "geometry_or_table", True, "eligible_if_thresholded",
        "How often do water-masked optical observations exceed the configured FAI bloom-proxy threshold?",
        "Monitor recurring surface-bloom signals and trigger targeted field checks.",
        "Surface signal is a screening proxy, not a confirmed harmful algal bloom observation.",
    ),
    IndicatorSpec(
        "shoreline_disturbance_fraction", "P4_threats", "pressure", "anthropogenic_shoreline_pressure", "fixed_riparian_100m",
        "fraction", "lower_is_better", "baseline", "geometry_or_table", True, "eligible_if_thresholded",
        "What fraction of the standardized riparian ring is mapped as crops, built or bare land?",
        "Identify shoreline pressure hotspots and prioritize management attention.",
        "This is an EO land-use pressure proxy; bare ground can include natural exposed substrate.",
    ),
    IndicatorSpec(
        "riparian_ndvi_sen_slope", "P1_ecosystem_condition", "vegetation", "riparian_trend", "fixed_riparian_100m",
        "NDVI/year", "context_dependent", "monitoring", "none", False, "contextual",
        "How has standardized riparian vegetation greenness changed over the historical trend window?",
        "Monitor directional change; pair with land-use and field observations.",
        "Trend is descriptive. Higher NDVI is not universally synonymous with higher native biodiversity.",
    ),
    IndicatorSpec(
        "landcover_composition", "P4_threats", "land_use", "class_fractions", "master_boundary",
        "fraction by class", "context_dependent", "baseline", "none", False, "contextual",
        "What land-cover classes occur within the master boundary?",
        "Contextualize exposed shoreline/littoral and land-use change.",
        "Reported by class rather than collapsed into a single ecological score.",
    ),
]


@dataclass(frozen=True)
class MetricSpec:
    legacy_name: str
    aquatic_status: str
    aquatic_domain: str
    scoring_default: str
    rationale: str


# Frozen 44-indicator legacy crosswalk.
LEGACY_METRIC_SPECS: List[MetricSpec] = [
    MetricSpec("natural_habitat", "modify", "land_context", "disabled", "Terrestrial habitat classes cannot treat lake water as habitat loss."),
    MetricSpec("natural_landcover", "modify", "land_context", "disabled", "Recompute on non-water land domain only."),
    MetricSpec("cpland", "context", "context", "disabled", "Landscape connectivity is a context metric and needs a surrounding landscape."),
    MetricSpec("forest_loss_rate", "context", "land_context", "disabled", "Forest-specific change is contextual for a lake."),
    MetricSpec("kba_overlap", "context", "master_boundary", "contextual", "Conservation designation, not ecosystem condition."),
    MetricSpec("ndvi", "modify", "fixed_riparian_or_land_context", "contextual", "NDVI is meaningful on vegetated domains, not open water."),
    MetricSpec("habitat_health", "modify", "fixed_riparian_or_land_context", "disabled", "Legacy formulation is terrestrial."),
    MetricSpec("flii", "exclude", "none", "disabled", "Forest landscape integrity is not a general lake metric."),
    MetricSpec("eii", "exclude", "none", "disabled", "Legacy ecosystem-integrity composite is terrestrial and overlaps other indicators."),
    MetricSpec("eii_structural", "exclude", "none", "disabled", "Terrestrial structural component."),
    MetricSpec("eii_compositional", "exclude", "none", "disabled", "Terrestrial compositional component."),
    MetricSpec("eii_functional", "exclude", "none", "disabled", "Terrestrial functional component."),
    MetricSpec("bii", "context", "broader_reference", "contextual", "Global biodiversity intactness context is not a local lake population observation."),
    MetricSpec("pdf", "exclude", "none", "disabled", "GLOBIO/PDF formulation is not directly interpretable inside open-water footprint."),
    MetricSpec("aridity_index", "context", "broader_reference", "contextual", "Climate context, not lake condition."),
    MetricSpec("tspi", "modify", "dynamic_water", "disabled", "Use NDCI only as a water-masked proxy with no automatic universal threshold."),
    MetricSpec("sabf", "modify", "dynamic_water", "disabled", "FAI bloom-proxy frequency is sensor/threshold dependent."),
    MetricSpec("wcpi", "modify", "dynamic_water", "disabled", "Water clarity/turbidity proxy must remain water-masked and uncalibrated unless validated."),
    MetricSpec("wsdi", "modify", "dynamic_water_time_series", "disabled", "Replace non-monotonic legacy score with explicit water-area dynamics/persistence series."),
    MetricSpec("hsas", "exclude", "none", "disabled", "Legacy habitat suitability surface is not a validated aquatic habitat model."),
    MetricSpec("edpp", "context", "dynamic_water", "disabled", "Heuristic environmental proxy; not a direct eDNA persistence measure."),
    MetricSpec("mspl", "context", "dynamic_water", "disabled", "Heuristic composite; not a validated microbial-stress probability."),
    MetricSpec("rci", "modify", "fixed_riparian_100m", "disabled", "Riparian complexity can be reported on a fixed standardized vegetation domain."),
    MetricSpec("riparian_ndvi_trend", "modify", "fixed_riparian_100m", "disabled", "Use multi-year seasonal composites and robust trend statistics."),
    MetricSpec("jrc_water_persistence", "context", "historical_context", "contextual", "Useful through 2021 only; current monitoring should use current EO observations."),
    MetricSpec("shdi", "context", "dynamic_water_boundary", "contextual", "Morphometry/shape statistic; scale-dependent and not a generic condition score."),
    MetricSpec("lai", "context", "fixed_riparian_100m", "contextual", "Vegetation structure context outside open water."),
    MetricSpec("chm", "context", "fixed_riparian_100m", "contextual", "Canopy-height context only where woody vegetation exists."),
    MetricSpec("endemic_richness", "context", "master_boundary_or_context", "contextual", "Range-overlap screening does not confirm local occurrence."),
    MetricSpec("flagship_habitat", "exclude", "none", "disabled", "Legacy model is forest/elevation-oriented and not a lake model."),
    MetricSpec("endemic_plant_richness", "context", "master_boundary_or_context", "contextual", "Range-overlap screening does not confirm local plant occurrence."),
    MetricSpec("threatened_richness", "context", "master_boundary_or_context", "contextual", "Range overlap is conservation context, not confirmed population size."),
    MetricSpec("ceri", "context", "master_boundary_or_context", "contextual", "Range-overlap weighted conservation sensitivity, not local extinction probability."),
    MetricSpec("star_t", "exclude", "none", "disabled", "Legacy threat-abatement proxy is not direct extinction risk and needs redesign before aquatic use."),
    MetricSpec("threatened_plant_richness", "context", "master_boundary_or_context", "contextual", "Range-overlap screening does not confirm local occurrence."),
    MetricSpec("ghm", "context", "broader_reference", "contextual", "Human-modification context, not lake condition."),
    MetricSpec("light_pollution", "context", "broader_reference", "contextual", "External pressure context, particularly nocturnal ecology."),
    MetricSpec("hdi", "context", "broader_reference", "contextual", "Human-development context rather than direct lake condition."),
    MetricSpec("lst_day", "context", "riparian_or_context", "contextual", "Thermal context; interpretation needs land/water separation."),
    MetricSpec("lst_night", "context", "riparian_or_context", "contextual", "Thermal context; interpretation needs land/water separation."),
    MetricSpec("sdi", "modify", "fixed_riparian_100m", "disabled", "Use a transparent disturbed-land fraction around the shoreline/riparian domain."),
    MetricSpec("stsi", "context", "dynamic_water", "disabled", "Legacy site-normalized thermal stress proxy needs calibration before scoring."),
    MetricSpec("iri", "context", "dynamic_water_and_context", "disabled", "Heuristic invasion-risk proxy; should not be treated as observed invasive pressure."),
    MetricSpec("ivsi", "exclude", "none", "disabled", "NDVI expansion signal is not taxonomic invasive-species evidence."),
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
