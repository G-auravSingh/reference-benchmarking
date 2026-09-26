"""Generalized indicator registry for terrestrial, aquatic and mixed assessments."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Iterable, List, Optional


PILLARS = {
    "C1_extent": "C1 — Extent",
    "C2_vegetation": "C2 — Vegetation / ecosystem condition",
    "C3_fauna": "C3 — Fauna",
    "C4_pressure": "C4 — Pressure",
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
    source_type: str = "eo"
    evidence_class: str = "measured"
    notes: str = ""

    @property
    def higher_is_better(self) -> Optional[bool]:
        if self.direction == "higher_is_better":
            return True
        if self.direction == "lower_is_better":
            return False
        return None


REGISTRY: List[IndicatorSpec] = [
    IndicatorSpec("water_extent", "C1_extent", "extent", "surface_water", "dynamic_water", "% of master boundary", "context_dependent", "baseline", "context_only", False, "contextual", "How much of the master boundary is surface water during the window?", "Hydroperiod tracking; compare only across equivalent seasonal windows.", notes="Not intrinsically better or worse across different lakes."),
    IndicatorSpec("water_persistence", "C1_extent", "hydrology", "surface_water_persistence", "dynamic_water", "fraction", "higher_is_better", "baseline", "automatic_aquatic_reference", True, "reference", "How consistently is surface water available?", "Track aquatic habitat permanence and seasonal availability."),
    IndicatorSpec("ndci_proxy", "C2_vegetation", "aquatic_condition", "water_quality", "dynamic_water", "NDCI", "lower_is_better", "baseline", "automatic_aquatic_reference", True, "reference", "How elevated is the red-edge chlorophyll/trophic proxy relative to comparable lakes?", "Screen aquatic productivity/eutrophication pressure; validate with field water chemistry."),
    IndicatorSpec("red_reflectance_turbidity_proxy", "C2_vegetation", "aquatic_condition", "water_quality", "dynamic_water", "surface reflectance", "lower_is_better", "baseline", "automatic_aquatic_reference", True, "reference", "How elevated is the red-band reflectance proxy relative to comparable lakes?", "Screen relative suspended-material/turbidity condition; validate with direct measurements."),
    IndicatorSpec("surface_algal_bloom_frequency", "C2_vegetation", "aquatic_condition", "water_quality", "dynamic_water", "fraction", "lower_is_better", "baseline", "automatic_aquatic_reference", True, "reference", "How frequently are surface bloom-like FAI conditions observed?", "Track recurring bloom pressure; validate with chlorophyll-a/phycocyanin and microscopy."),
    IndicatorSpec("riparian_ndvi", "C2_vegetation", "vegetation_condition", "riparian_condition", "fixed_riparian_100m", "NDVI", "higher_is_better", "baseline", "automatic_aquatic_reference", True, "reference", "How does riparian greenness compare with comparable lake margins?", "Monitor riparian vegetation condition and restoration response."),
    IndicatorSpec("riparian_ndvi_sen_slope", "C2_vegetation", "vegetation_change", "riparian_trend", "fixed_riparian_100m", "NDVI/year", "contextual_trend", "baseline", "context_only", False, "contextual", "Is riparian vegetation changing over time?", "Provide historical context; do not convert a Cycle-1 trend into an intactness score.", source_type="eo", evidence_class="measured"),
    IndicatorSpec("shoreline_disturbance_fraction", "C4_pressure", "direct_pressure", "shoreline_disturbance", "fixed_riparian_100m", "fraction", "lower_is_better", "baseline", "automatic_aquatic_reference", True, "reference", "How much shoreline context is occupied by disturbance classes?", "Identify shoreline pressure and restoration opportunities."),
    IndicatorSpec("natural_habitat_fraction", "C1_extent", "habitat_extent", "natural_habitat", "terrestrial_context", "fraction", "higher_is_better", "baseline", "automatic_terrestrial_reference", True, "reference", "How much comparable terrestrial context remains natural habitat?", "Track habitat retention and land-cover conversion."),
    IndicatorSpec("vegetation_ndvi", "C2_vegetation", "vegetation_condition", "greenness", "terrestrial_context", "NDVI", "higher_is_better", "baseline", "automatic_terrestrial_reference", True, "reference", "How does terrestrial vegetation condition compare with least-modified comparable pixels?", "Monitor vegetation condition and restoration response."),
    IndicatorSpec("habitat_connectivity_proxy", "C1_extent", "configuration", "connectivity", "terrestrial_context", "fraction", "higher_is_better", "baseline", "automatic_terrestrial_reference", True, "reference", "How connected are natural-habitat pixels in the surrounding landscape?", "Screen habitat fragmentation/connectivity."),
    IndicatorSpec("built_up_fraction", "C4_pressure", "land_use_pressure", "built_environment", "terrestrial_context", "fraction", "lower_is_better", "baseline", "automatic_terrestrial_reference", True, "reference", "How much built cover occurs in the terrestrial context?", "Track urbanization/land-use pressure."),
    IndicatorSpec("human_modification", "C4_pressure", "land_use_pressure", "human_modification", "terrestrial_context", "index", "lower_is_better", "baseline", "automatic_terrestrial_reference", True, "reference", "How modified is the terrestrial context?", "Track cumulative land-use pressure."),
    IndicatorSpec("species_richness", "C3_fauna", "community_condition", "richness", "field", "count", "higher_is_better", "baseline", "external_reference", True, "reference", "How many taxa were observed under the survey protocol?", "Track biological richness; reference must use comparable sampling effort." , source_type="field"),
    IndicatorSpec("species_diversity", "C3_fauna", "community_condition", "diversity", "field", "index", "higher_is_better", "baseline", "external_reference", True, "reference", "How diverse and balanced is the observed assemblage?", "Track community composition using comparable survey effort.", source_type="field"),
    IndicatorSpec("acoustic_health_index", "C3_fauna", "community_condition", "acoustic_activity", "acoustic", "index", "higher_is_better", "baseline", "external_reference", True, "reference", "How does the soundscape compare with an appropriate acoustic reference?", "Track acoustic biological activity and disturbance.", source_type="acoustic"),
    IndicatorSpec("ndsi", "C4_pressure", "direct_pressure", "acoustic_disturbance", "acoustic", "index", "higher_is_better", "baseline", "external_reference", True, "reference", "How balanced is biological versus anthropogenic acoustic energy?", "Track acoustic disturbance using standardized recording effort.", source_type="acoustic"),
    IndicatorSpec("edna_taxonomic_richness", "C2_vegetation", "molecular_biodiversity", "taxonomic_richness", "aquatic", "taxonomic assignments", "higher_is_better", "baseline", "external_reference", True, "reference", "How taxonomically rich is the broad environmental molecular signal under the same lab/bioinformatics protocol?", "Establish a molecular Year-0 baseline only under matched sampling, laboratory and classification protocols; it is not a direct fauna census.", source_type="edna", evidence_class="measured", notes="Shotgun metagenomic assignments can include bacteria, archaea, viruses, plants, algae and fungi; do not interpret this as confirmed fauna richness."),
    IndicatorSpec("edna_fauna_taxonomic_richness", "C3_fauna", "molecular_biodiversity", "faunal_richness", "aquatic", "taxa", "higher_is_better", "baseline", "external_reference", True, "reference", "How taxonomically rich is the faunal molecular signal under a targeted or taxonomically filtered protocol?", "Potential C3 input once a fauna-specific eDNA workflow and matched reference are available.", source_type="edna", evidence_class="measured", notes="Future fauna-specific eDNA metric; not populated from the current broad Nandoshi metagenomic assignment count."),
    IndicatorSpec("edna_cyanobacterial_fraction", "C2_vegetation", "aquatic_condition", "microbial_stress", "aquatic", "fraction of assigned reads", "lower_is_better", "baseline", "external_reference", True, "reference", "How prominent is the cyanobacterial molecular signal?", "Screen bloom-risk pressure; confirm with toxin, cell-count and chemistry testing.", source_type="edna", evidence_class="indicated"),
    IndicatorSpec("edna_human_associated_fraction", "C4_pressure", "contamination_pressure", "human_derived_signal", "aquatic", "fraction of assigned reads", "lower_is_better", "baseline", "external_reference", True, "reference", "How prominent is human-associated molecular material?", "Screen possible human-derived inputs; source attribution requires targeted testing.", source_type="edna", evidence_class="indicated"),
    IndicatorSpec("edna_reducing_microbe_fraction", "C2_vegetation", "aquatic_condition", "oxygen_limitation_signal", "aquatic", "fraction of genetic material", "lower_is_better", "baseline", "external_reference", True, "reference", "How prominent are microbial groups associated with reducing/oxygen-limited conditions?", "Screen oxygen-limited microenvironments; validate with direct dissolved oxygen measurements.", source_type="edna", evidence_class="indicated"),
    IndicatorSpec("edna_functional_capacity", "C2_vegetation", "ecosystem_function", "functional_potential", "aquatic", "qualitative", "contextual", "baseline", "context_only", False, "contextual", "What functional genes/taxa suggest nutrient cycling or pollutant-degradation potential?", "Recovery-potential context; do not score without a validated quantitative reference.", source_type="edna", evidence_class="inferred"),
    IndicatorSpec("edna_assignment_count", "C2_vegetation", "molecular_biodiversity", "assignment_volume", "aquatic", "count", "contextual", "baseline", "context_only", False, "contextual", "How many taxonomic assignments were returned?", "Describe sequencing output only; not an independent biodiversity measure.", source_type="edna", evidence_class="measured"),
    IndicatorSpec("bii", "C3_fauna", "biodiversity_intactness", "abundance_intactness", "terrestrial", "index", "higher_is_better", "baseline", "external_reference", True, "reference", "How intact is modelled biological abundance relative to an appropriate reference?", "Track biodiversity intactness as a fauna/community signal; retain known coverage caveats.", source_type="eo", evidence_class="measured"),
    IndicatorSpec("mean_species_abundance", "C3_fauna", "community_condition", "abundance", "field", "index", "higher_is_better", "baseline", "external_reference", True, "reference", "How does mean species abundance compare with the reference community?", "Track population/community condition where the sampling design supports abundance inference.", source_type="field"),
    IndicatorSpec("taxonomic_dissimilarity", "C3_fauna", "community_composition", "turnover", "field", "index", "contextual", "baseline", "context_only", False, "contextual", "How different are communities in taxonomic composition?", "Use as a community-composition context metric unless a directional condition question and reference are explicitly defined.", source_type="field", evidence_class="measured"),
    IndicatorSpec("iucn_conservation_value", "C3_fauna", "conservation_significance", "representation", "screening", "index", "contextual", "screening", "context_only", False, "contextual", "What is the conservation significance of records/ranges intersecting the site?", "Conservation-priority context; not a direct site-condition measure.", source_type="field", evidence_class="measured"),
    IndicatorSpec("cpland", "C1_extent", "configuration", "connectivity", "terrestrial_context", "fraction", "higher_is_better", "baseline", "external_reference", True, "reference", "How connected is natural habitat in the landscape?", "Landscape-context connectivity metric.", source_type="eo"),
    IndicatorSpec("forest_loss_rate", "C4_pressure", "disturbance_regime", "habitat_loss", "terrestrial_context", "% per year", "lower_is_better", "baseline", "external_reference", True, "reference", "What is the recent rate of forest-cover loss?", "Track habitat-loss pressure; accuracy assessment required.", source_type="eo"),
    IndicatorSpec("chm", "C2_vegetation", "vegetation_condition", "structure", "terrestrial_context", "m", "higher_is_better", "baseline", "external_reference", True, "reference", "How does vegetation structural height compare with a suitable reference?", "Track habitat structure where GEDI or comparable canopy-height data are available.", source_type="eo"),
    IndicatorSpec("eii", "C2_vegetation", "vegetation_condition", "integrity", "terrestrial_context", "index", "higher_is_better", "baseline", "external_reference", True, "reference", "How intact is ecosystem structure/function under the selected EII definition?", "Use only when the underlying EII components and independence controls are available.", source_type="eo"),

]

# Compatibility crosswalk for old names; not a legacy scoring engine.
LEGACY_METRIC_SPECS = {x.name: x for x in REGISTRY}


def indicator_specs() -> List[IndicatorSpec]:
    return list(REGISTRY)


def indicator_table() -> List[Dict]:
    return [asdict(x) for x in REGISTRY]


def legacy_crosswalk() -> List[Dict]:
    return [
        {"legacy_metric": "jrc_water_persistence", "adaptive_metric": "water_persistence", "status": "conceptual crosswalk"},
        {"legacy_metric": "riparian_ndvi_trend", "adaptive_metric": "riparian_ndvi_sen_slope", "status": "contextual in Cycle 1"},
        {"legacy_metric": "sabf", "adaptive_metric": "surface_algal_bloom_frequency", "status": "aquatic proxy; reference method updated"},
        {"legacy_metric": "wcpi", "adaptive_metric": "red_reflectance_turbidity_proxy", "status": "proxy retained with explicit validation caveat"},
    ]


def get_indicator_spec(name: str) -> IndicatorSpec:
    for spec in REGISTRY:
        if spec.name == name:
            return spec
    raise KeyError(f"Unknown indicator: {name}. Register external metrics with explicit metadata before scoring.")
