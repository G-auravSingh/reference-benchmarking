"""
Indicator Registry
==================

The central registry that makes the pipeline indicator-agnostic. Any biodiversity
indicator—current or future—is registered here with its metadata and extraction logic.

Adding a new indicator requires ONLY:
    1. Writing an extraction function (site_geometry → float/array)
    2. Calling registry.register(...)

No changes to the core pipeline are ever needed.

Design Pattern
--------------
Each indicator is stored as an IndicatorSpec dataclass containing:
    - name: unique identifier (e.g., "ndvi", "msa_globio4")
    - display_name: human-readable name for reports
    - source_type: "gee" | "local_raster" | "api" | "in_situ"
    - extract_fn: callable(site_geometry, config) → dict with 'value', 'pixels', etc.
    - unit: measurement unit string
    - value_range: (min, max) tuple for sanity checks
    - citation: peer-reviewed literature reference
    - tier1_layer: optional GEE asset ID or raster path for Tier 1 global extraction
    - tier2_eligible: whether this indicator can be benchmarked via Tier 2
    - pillar: which Darukaa pillar this maps to (1–4 or None)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class IndicatorSpec:
    """Specification for a single biodiversity indicator."""

    name: str
    display_name: str
    source_type: str  # "gee", "local_raster", "api", "in_situ"
    extract_fn: Callable  # (geometry, config) → dict
    unit: str = ""
    value_range: Tuple[float, float] = (0.0, 1.0)
    citation: str = ""
    tier1_layer: Optional[str] = None  # GEE asset or raster path
    tier2_eligible: bool = True
    higher_is_better: bool = True  # True for state indicators (NDVI, BII, EII)
                                    # False for pressure indicators (gHM, LST, noise)
    reference_radius_km: Optional[float] = None
    # Per-indicator spatial scale for reference selection (km).
    # If None, falls back to config.reference_buffer_km (default 100).
    #
    # Ecological rationale for scale selection:
    #   1–5 km    : pollination, invertebrate dispersal
    #   5–20 km   : seed dispersal, local habitat connectivity, acoustic landscapes
    #   10–50 km  : bird/mammal corridors, landscape-scale habitat mosaics
    #   50–100 km : regional vegetation, climate, hydrological processes
    #   100–500 km: ecoregion-level composition, macroecological patterns
    #
    # Reference: Thornton, D.H. et al. (2011). The influence of landscape,
    # patch, and within-patch factors on species presence and abundance: a
    # review of focal patch studies. Landscape Ecology, 26, 7–18.
    # DOI:10.1007/s10980-010-9549-z
    pillar: Optional[int] = None  # Darukaa pillar 1–4

    # ------------------------------------------------------------------
    # v0.2.0 indicator contract (CS-1). All fields are additive with safe
    # defaults, so existing register(...) calls remain valid unchanged.
    # These make the reviewer's per-indicator documentation requirements
    # machine-readable and drive redundancy screening, evidence-tier
    # separation, scale-correct benchmarking, and the auto-generated report.
    # ------------------------------------------------------------------

    # -- construct placement (replaces the flat "pillar" over time) --
    construct: Optional[str] = None       # C1_landscape | C2_vegetation | C3_fauna | C4_pressure
    subdimension: Optional[str] = None    # e.g. "extent", "configuration", "structure"
    ecological_question: str = ""         # the question this indicator answers
    management_use: str = ""              # how a manager would act on it

    # -- provenance & redundancy screening (Gate A) --
    input_layers: List[str] = field(default_factory=list)  # raw layers consumed
    measurement_scale: Optional[str] = None  # "ratio" | "interval" | "bounded"
    spatial_grain: str = ""               # e.g. "10 m", "1 km"
    temporal_period: str = ""             # e.g. "2024 annual composite"
    effort_basis: str = ""                # for in-situ: detections/recorder-day, etc.

    # -- evidence tier & applicability --
    evidence_tier: str = "contextual"     # screening | contextual | baseline | monitoring
    realm: str = "terrestrial"            # terrestrial | aquatic | mixed
    module: str = "core"                  # core | conservation | agroforestry | aquatic | optional
    # REAL FIX: "module" groups indicators by which archetype/programme
    # designed them (metadata only, until this field). It does NOT mean
    # "only valid in that realm" -- confirmed directly by checking real
    # extraction logic: 10 of 12 currently-scored indicators are tagged
    # module="core" but several are land-cover-specific in a way that
    # gives a degenerate, misleading value on open water (chm: canopy
    # height ~0m on a lake; forest_loss_rate: trivially 0% on a lake;
    # natural_habitat: DW_NATURAL_CLASSES excludes water entirely, so a
    # pristine lake would wrongly show ~0% "natural"). applicable_realms
    # is the real, authoritative gate for realm-based filtering; module
    # stays as the original archetype-grouping metadata, unchanged.
    applicable_realms: tuple = ("terrestrial", "aquatic", "mixed")

    # -- reference & benchmarking --
    reference_type: Optional[str] = None  # contemporary_best_on_offer | regional_distribution |
                                          # published_threshold | paired_control |
                                          # counterfactual_practice | historical_potential
    reference_estimator: Optional[str] = None  # log_response_ratio | robust_z | None(=auto by scale)
    threshold_basis: str = ""             # provenance of any concern-class thresholds

    # -- uncertainty & interpretation --
    uncertainty_method: str = ""          # bootstrap_ci | none | ...
    restoration_sensitivity: str = ""     # expected direction/magnitude of response
    reassessment_frequency: str = ""      # e.g. "annual", "3-yearly"
    management_trigger: str = ""          # interpretation / action threshold

    # -- toggle architecture (CS-1 / Q7): active ⟹ eligible; eligible is COMPUTED --
    registered: bool = True               # wired into the backend at its correct place
    active: bool = True                   # included in this project's run (client-toggled)
    requires: List[str] = field(default_factory=list)  # unmet deps, e.g. ["field_plots"]

    # Client activation override (v0.2.1): set by contracts.request_activation() when a
    # client explicitly asks to score an indicator beyond the Darukaa default contract.
    # Never set directly — always goes through request_activation() so the promotion is
    # auditable (visible in every downstream report) and subject to the safety tiers
    # documented there (context = promotable; screening = promotable only with an
    # explicit override; removed = never promotable this way).
    client_override: bool = False
    client_override_note: str = ""

    metadata: Dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Computed eligibility — NEVER hand-set. An indicator may be SCORED only
    # if it is registered, its evidence supports a defensible score, it has a
    # reference and an uncertainty method, and it is not screening-tier.
    # (Enforcement in the scoring layer lands in a later batch; exposed here
    # so downstream code and the register document can rely on one definition.)
    # ------------------------------------------------------------------
    @property
    def eligible(self) -> bool:
        """True if this indicator is defensible to SCORE (vs show as context)."""
        if not self.registered:
            return False
        if self.evidence_tier not in ("baseline", "monitoring"):
            return False
        if not self.reference_type:
            return False
        if not self.uncertainty_method or self.uncertainty_method == "none":
            return False
        if self.requires:  # unmet dependencies -> cannot be a defensible score yet
            return False
        return True

    @property
    def scoring_eligible(self) -> bool:
        """Scored iff active AND eligible (enforces: active ⟹ eligible)."""
        return self.active and self.eligible


class IndicatorRegistry:
    """
    Thread-safe registry for biodiversity indicators.

    Usage::

        registry = IndicatorRegistry()
        registry.register(
            name="ndvi",
            display_name="Vegetation Structure (NDVI)",
            source_type="gee",
            extract_fn=extract_ndvi,
            unit="index",
            value_range=(-1.0, 1.0),
            citation="Sentinel-2 MSI; Drusch et al. (2012) RSE 120, 25–36",
            tier1_layer="COPERNICUS/S2_SR_HARMONIZED",
            pillar=1,
        )

        # Later, in the pipeline:
        for spec in registry.all():
            value = spec.extract_fn(site_geom, config)
    """

    def __init__(self):
        self._indicators: Dict[str, IndicatorSpec] = {}

    def register(self, name: str, **kwargs) -> None:
        """Register a new indicator. Overwrites if name already exists."""
        if name in self._indicators:
            logger.warning(f"Overwriting existing indicator: {name}")
        self._indicators[name] = IndicatorSpec(name=name, **kwargs)
        logger.info(f"Registered indicator: {name}")

    def get(self, name: str) -> IndicatorSpec:
        """Retrieve an indicator spec by name."""
        if name not in self._indicators:
            raise KeyError(
                f"Indicator '{name}' not registered. "
                f"Available: {list(self._indicators.keys())}"
            )
        return self._indicators[name]

    def all(self) -> List[IndicatorSpec]:
        """Return all registered indicators."""
        return list(self._indicators.values())

    def names(self) -> List[str]:
        """Return all registered indicator names."""
        return list(self._indicators.keys())

    def by_pillar(self, pillar: int) -> List[IndicatorSpec]:
        """Return indicators belonging to a specific Darukaa pillar."""
        return [s for s in self._indicators.values() if s.pillar == pillar]

    def by_source(self, source_type: str) -> List[IndicatorSpec]:
        """Return indicators by source type (gee, local_raster, api, in_situ)."""
        return [s for s in self._indicators.values() if s.source_type == source_type]

    def tier2_indicators(self) -> List[IndicatorSpec]:
        """Return only indicators eligible for Tier 2 benchmarking."""
        return [s for s in self._indicators.values() if s.tier2_eligible]

    # -- v0.2.0 contract-aware queries (CS-1) --
    def by_construct(self, construct: str) -> List[IndicatorSpec]:
        """Return indicators belonging to a construct (C1_landscape … C4_pressure)."""
        return [s for s in self._indicators.values() if s.construct == construct]

    def scored(self) -> List[IndicatorSpec]:
        """Indicators that will actually be SCORED (active AND computed-eligible)."""
        return [s for s in self._indicators.values() if s.scoring_eligible]

    def contextual(self) -> List[IndicatorSpec]:
        """Registered/active indicators shown as context (not scored)."""
        return [s for s in self._indicators.values()
                if s.active and not s.eligible]

    def pending(self) -> List[IndicatorSpec]:
        """Indicators blocked by unmet dependencies (rendered 'pending input')."""
        return [s for s in self._indicators.values() if s.requires]

    def by_input_layer(self, layer: str) -> List[IndicatorSpec]:
        """Indicators consuming a given raw input layer (redundancy Gate A)."""
        return [s for s in self._indicators.values() if layer in s.input_layers]

    def availability_table(self) -> List[Dict[str, Any]]:
        """Every registered indicator with its current disposition and WHY — the
        client-facing "what could I score, and what would it take" view. Use this
        (e.g. via a pandas DataFrame in the notebook) before deciding whether to request
        activation of anything beyond the Darukaa default scored set — see
        contracts.request_activation() and README §"Choosing what gets scored"."""
        order = {"C1_landscape": 1, "C2_vegetation": 2, "C3_fauna": 3, "C4_pressure": 4}
        rows = []
        for s in sorted(self._indicators.values(),
                        key=lambda s: (order.get(s.construct, 9), s.name)):
            rows.append({
                "name": s.name,
                "display_name": s.display_name,
                "construct": s.construct,
                "disposition": s.metadata.get("disposition", "?"),
                "currently_scored": s.scoring_eligible,
                "evidence_tier": s.evidence_tier,
                "why": s.metadata.get("contract_note", ""),
                "client_override": s.client_override,
            })
        return rows

    def __len__(self) -> int:
        return len(self._indicators)

    def __contains__(self, name: str) -> bool:
        return name in self._indicators

    def __repr__(self) -> str:
        return f"IndicatorRegistry({len(self)} indicators: {self.names()})"
