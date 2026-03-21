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
    pillar: Optional[int] = None  # Darukaa pillar 1–4
    metadata: Dict[str, Any] = field(default_factory=dict)


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

    def __len__(self) -> int:
        return len(self._indicators)

    def __contains__(self, name: str) -> bool:
        return name in self._indicators

    def __repr__(self) -> str:
        return f"IndicatorRegistry({len(self)} indicators: {self.names()})"
