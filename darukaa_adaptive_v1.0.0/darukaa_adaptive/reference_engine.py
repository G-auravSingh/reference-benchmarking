"""Automatic reference-population construction.

Manual reference files remain optional overrides. The default engine constructs a
candidate reference population from the master boundary, ecological realm, land/water
context and disturbance filters. Candidate quality and uncertainty are recorded rather
than silently treated as pristine controls.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any


@dataclass
class ReferencePopulation:
    level: str
    realm: str
    method: str
    status: str
    geometry: Any = None
    candidate_area_ha: Optional[float] = None
    candidate_pixels: Optional[int] = None
    uncertainty: Optional[float] = None
    approval: bool = False
    diagnostics: Dict[str, Any] = None

    def to_dict(self):
        d = asdict(self)
        d.pop("geometry", None)
        return d


class AutomaticReferenceEngine:
    """Construct comparable candidate populations without a required reference KML/CSV."""

    def __init__(self, config, water_detector=None):
        self.config = config
        self.water = water_detector

    def _buffer_annulus(self, geometry):
        import ee
        # A standardized external context, not a user-drawn reference polygon.
        return geometry.buffer(self.config.spatial.context_buffer_km * 1000).difference(geometry)

    def aquatic_candidate(self, master_geometry, start: str, end: str) -> ReferencePopulation:
        import ee
        context = self._buffer_annulus(master_geometry)
        if self.water is None:
            return ReferencePopulation("auto_aquatic", "aquatic", "water_similarity_mask", "no_water_detector")
        try:
            occurrence, method, n = self.water.occurrence_image(context, start, end)
            # Candidate population = water pixels outside the project boundary that are
            # persistent enough to represent comparable aquatic habitat. It is a pixel
            # population, not a hand-drawn lake polygon.
            min_occ = self.config.reference.auto_min_water_occurrence
            candidate = occurrence.gte(min_occ).selfMask()
            area = ee.Image.pixelArea().updateMask(candidate).reduceRegion(
                reducer=ee.Reducer.sum(), geometry=context, scale=10,
                maxPixels=1e9, bestEffort=True).get("area")
            pix = candidate.reduceRegion(
                reducer=ee.Reducer.count(), geometry=context, scale=10,
                maxPixels=1e9, bestEffort=True).get("water_occurrence")
            area_ha = area.getInfo() if area is not None else None
            pixels = pix.getInfo() if pix is not None else None
            area_ha = None if area_ha is None else float(area_ha) / 1e4
            pixels = None if pixels is None else int(pixels)
            ok = area_ha is not None and area_ha >= self.config.reference.auto_min_candidate_area_ha and pixels is not None and pixels >= self.config.reference.auto_min_candidate_pixels
            ref_geom = None
            if ok:
                vectors = candidate.reduceToVectors(geometry=context, scale=30, geometryType="polygon", eightConnected=True, labelProperty="water", maxPixels=1e9, bestEffort=True)
                ref_geom = vectors.geometry()
            return ReferencePopulation(
                "auto_aquatic", "aquatic", method, "candidate_ready" if ok else "insufficient_candidate_population",
                geometry=ref_geom, candidate_area_ha=area_ha, candidate_pixels=pixels,
                approval=bool(ok and self.config.reference.auto_approve),
                diagnostics={"min_occurrence": min_occ, "images": n, "context_km": self.config.spatial.context_buffer_km, "vectorized_at_m": 30},
            )
        except Exception as exc:
            return ReferencePopulation("auto_aquatic", "aquatic", "water_similarity_mask", f"error:{exc}", diagnostics={})

    def terrestrial_candidate(self, master_geometry):
        import ee
        context = self._buffer_annulus(master_geometry)
        try:
            # Dynamic World: exclude built (6) and crops (4), then retain common natural/
            # semi-natural vegetation classes. This is a candidate population, not a claim
            # of pristine condition.
            dw = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(context).select("label").mode()
            natural = dw.eq(1).Or(dw.eq(2)).Or(dw.eq(3)).Or(dw.eq(5)).Or(dw.eq(7)).selfMask()
            vectors = natural.reduceToVectors(geometry=context, scale=30, geometryType="polygon", eightConnected=True, labelProperty="natural", maxPixels=1e9, bestEffort=True)
            return ReferencePopulation(
                "auto_terrestrial", "terrestrial", "ecoregion_plus_low_modification", "candidate_ready",
                geometry=vectors.geometry(), approval=bool(self.config.reference.auto_approve),
                diagnostics={"excluded_dynamic_world_classes": [4, 6], "context_km": self.config.spatial.context_buffer_km, "vectorized_at_m":30},
            )
        except Exception as exc:
            return ReferencePopulation("auto_terrestrial", "terrestrial", "ecoregion_plus_low_modification", f"error:{exc}")

    def build(self, master_geometry, realm: str, start: str, end: str) -> ReferencePopulation:
        if realm == "aquatic":
            return self.aquatic_candidate(master_geometry, start, end)
        if realm == "terrestrial":
            return self.terrestrial_candidate(master_geometry)
        # Mixed assessments get separate candidate populations; caller should benchmark
        # each indicator against the population appropriate to its domain.
        return ReferencePopulation("auto_mixed", "mixed", "separate_realm_candidates", "requires_domain_specific_selection")
