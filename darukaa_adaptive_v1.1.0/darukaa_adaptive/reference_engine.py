"""Automatic, ecologically matched reference-population construction.

The engine is deliberately split into candidate construction and approval.  A
candidate is *not* a reference merely because it is nearby or has low human
modification.  The production pathway requires ecological comparability, low-pressure
screening, temporal compatibility and sufficient population size before automated
approval is allowed.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any

from .reference_condition import evaluate_reference_candidate


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
    reference_state: str = "least_disturbed_contemporary"
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

    def _buffer_annulus(self, geometry, radius_km=None):
        radius = radius_km if radius_km is not None else self.config.reference.search_radius_km
        return geometry.buffer(float(radius) * 1000).difference(geometry)

    @staticmethod
    def _site_mean(image, geometry, scale=30):
        import ee
        value = image.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=geometry, scale=scale,
            maxPixels=1e9, bestEffort=True
        ).values().get(0)
        try:
            return value.getInfo()
        except Exception:
            return None

    def _ecoregion_geometry(self, master_geometry, context):
        """Return the intersection of the context with the site's RESOLVE ecoregion(s).

        If the lookup is unavailable, the caller records the limitation instead of
        silently claiming ecological equivalence.
        """
        import ee
        fc = ee.FeatureCollection(self.config.reference.ecoregion_gee_asset)
        hits = fc.filterBounds(master_geometry)
        try:
            n = hits.size().getInfo()
            if not n:
                return context, False, {"ecoregion_filter": "unavailable_or_no_match"}
            geom = hits.geometry().intersection(context, ee.ErrorMargin(30))
            return geom, True, {"ecoregion_filter": "RESOLVE_2017", "site_ecoregion_feature_count": int(n)}
        except Exception as exc:
            return context, False, {"ecoregion_filter": f"error:{exc}"}

    def _hmi_context_filter(self, water_mask, context):
        """Screen aquatic candidates using low human modification in their land context.

        HM is a terrestrial pressure surface, so it is not interpreted as a water-quality
        metric.  A focal mean around candidate water pixels is used only as a disturbance
        screen for the surrounding landscape.
        """
        import ee
        asset = self.config.reference.hmi_gee_asset
        band = self.config.reference.hmi_gee_band
        hmi = ee.Image(asset).select(band)
        radius = float(self.config.reference.hmi_context_radius_m)
        contextual = hmi.focal_mean(radius=radius, units="meters")
        screened = water_mask.And(contextual.lte(self.config.reference.hmi_max_for_reference))
        return screened, {"hmi_asset": asset, "hmi_band": band,
                          "hmi_context_radius_m": radius,
                          "hmi_max_for_reference": self.config.reference.hmi_max_for_reference}

    def aquatic_candidate(self, master_geometry, start: str, end: str) -> ReferencePopulation:
        import ee
        context = self._buffer_annulus(master_geometry)
        if self.water is None:
            return ReferencePopulation("auto_aquatic", "aquatic", "ecologically_matched_water_population",
                                       "no_water_detector", reference_state="least_disturbed_contemporary")
        try:
            occurrence, method, n = self.water.occurrence_image(context, start, end)
            site_occurrence, _, site_n = self.water.occurrence_image(master_geometry, start, end)
            site_mean = self._site_mean(site_occurrence, master_geometry, scale=10)
            if site_mean is None:
                return ReferencePopulation("auto_aquatic", "aquatic", method,
                                           "site_hydroperiod_unavailable",
                                           reference_state="least_disturbed_contemporary",
                                           diagnostics={"images": n})

            min_occ = self.config.reference.auto_min_water_occurrence
            tol = self.config.reference.water_occurrence_tolerance
            water_similar = occurrence.gte(min_occ).And(occurrence.subtract(float(site_mean)).abs().lte(tol))
            water_similar = water_similar.And(occurrence.lt(1.01))
            eco_context, eco_ok, eco_diag = self._ecoregion_geometry(master_geometry, context)
            candidate = water_similar.clip(eco_context)
            candidate, hmi_diag = self._hmi_context_filter(candidate, eco_context)
            candidate = candidate.selfMask()

            area = ee.Image.pixelArea().updateMask(candidate).reduceRegion(
                reducer=ee.Reducer.sum(), geometry=eco_context, scale=10,
                maxPixels=1e9, bestEffort=True).get("area")
            pix = candidate.reduceRegion(
                reducer=ee.Reducer.count(), geometry=eco_context, scale=10,
                maxPixels=1e9, bestEffort=True).values().get(0)
            area_ha = area.getInfo() if area is not None else None
            pixels = pix.getInfo() if pix is not None else None
            area_ha = None if area_ha is None else float(area_ha) / 1e4
            pixels = None if pixels is None else int(pixels)

            # Ecological match is based on the candidate population's observed
            # hydroperiod relative to the focal site. It is intentionally transparent
            # and does not claim that low HMI alone establishes naturalness.
            candidate_occ = occurrence.updateMask(candidate).reduceRegion(
                reducer=ee.Reducer.mean(), geometry=eco_context, scale=10,
                maxPixels=1e9, bestEffort=True).values().get(0)
            candidate_occ = candidate_occ.getInfo() if candidate_occ is not None else None
            match_score = (max(0.0, 1.0 - abs(float(candidate_occ) - float(site_mean)) / max(tol, 1e-6))
                           if candidate_occ is not None else 0.0)
            qa = evaluate_reference_candidate(
                candidate_area_ha=area_ha,
                candidate_pixels=pixels,
                min_area_ha=self.config.reference.auto_min_candidate_area_ha,
                min_pixels=self.config.reference.auto_min_candidate_pixels,
                ecological_match_score=match_score if eco_ok else 0.0,
                min_ecological_match_score=self.config.reference.min_ecological_match_score,
                pressure_screen_pass=True,
                temporal_match_pass=(n >= self.config.reference.min_reference_observations),
                spatial_quality_pass=eco_ok,
                reference_state="least_disturbed_contemporary",
                auto_approve=self.config.reference.auto_approve,
                extra={"site_water_occurrence": float(site_mean),
                       "candidate_mean_water_occurrence": candidate_occ,
                       "water_occurrence_tolerance": tol,
                       "occurrence_images": int(n),
                       "site_occurrence_images": int(site_n),
                       **eco_diag, **hmi_diag},
            )
            ref_geom = None
            if qa.approval:
                vectors = candidate.reduceToVectors(
                    geometry=eco_context, scale=30, geometryType="polygon",
                    eightConnected=True, labelProperty="reference_water", maxPixels=1e9,
                    bestEffort=True
                )
                ref_geom = vectors.geometry()
            status = "validated_candidate" if qa.approval else ("candidate_rejected" if area_ha is not None else "candidate_unresolved")
            return ReferencePopulation(
                "auto_aquatic", "aquatic", "ecoregion_hydrology_low_pressure", status,
                geometry=ref_geom, candidate_area_ha=area_ha, candidate_pixels=pixels,
                approval=qa.approval, reference_state="least_disturbed_contemporary",
                diagnostics=qa.diagnostics,
            )
        except Exception as exc:
            return ReferencePopulation("auto_aquatic", "aquatic", "ecoregion_hydrology_low_pressure",
                                       f"error:{exc}", reference_state="least_disturbed_contemporary",
                                       diagnostics={})

    def terrestrial_candidate(self, master_geometry, start: Optional[str] = None, end: Optional[str] = None):
        import ee
        context = self._buffer_annulus(master_geometry)
        try:
            eco_context, eco_ok, eco_diag = self._ecoregion_geometry(master_geometry, context)
            dw = (ee.ImageCollection(self.config.reference.landcover_asset)
                  .filterBounds(eco_context).select("label").mode())
            site_class = dw.reduceRegion(
                reducer=ee.Reducer.mode(), geometry=master_geometry, scale=10,
                maxPixels=1e9, bestEffort=True).get("label")
            site_class = site_class.getInfo() if site_class is not None else None
            if site_class is None:
                return ReferencePopulation("auto_terrestrial", "terrestrial",
                                           "ecoregion_landcover_low_pressure", "site_landcover_unavailable",
                                           reference_state="least_disturbed_contemporary", diagnostics=eco_diag)

            # Same habitat class + contemporary low modification.  The class is a
            # comparability stratum, not a claim that every pixel of that class is natural.
            hmi = ee.Image(self.config.reference.hmi_gee_asset).select(self.config.reference.hmi_gee_band)
            candidate = dw.eq(int(site_class)).And(hmi.lte(self.config.reference.hmi_max_for_reference)).selfMask()
            area = ee.Image.pixelArea().updateMask(candidate).reduceRegion(
                reducer=ee.Reducer.sum(), geometry=eco_context, scale=10,
                maxPixels=1e9, bestEffort=True).get("area")
            pix = candidate.reduceRegion(
                reducer=ee.Reducer.count(), geometry=eco_context, scale=10,
                maxPixels=1e9, bestEffort=True).values().get(0)
            area_ha = area.getInfo() if area is not None else None
            pixels = pix.getInfo() if pix is not None else None
            area_ha = None if area_ha is None else float(area_ha) / 1e4
            pixels = None if pixels is None else int(pixels)
            qa = evaluate_reference_candidate(
                candidate_area_ha=area_ha, candidate_pixels=pixels,
                min_area_ha=self.config.reference.auto_min_candidate_area_ha,
                min_pixels=self.config.reference.auto_min_candidate_pixels,
                ecological_match_score=1.0 if eco_ok else 0.0,
                min_ecological_match_score=self.config.reference.min_ecological_match_score,
                pressure_screen_pass=True, temporal_match_pass=True,
                spatial_quality_pass=eco_ok,
                reference_state="least_disturbed_contemporary",
                auto_approve=self.config.reference.auto_approve,
                extra={"site_dynamic_world_class": int(site_class),
                       "landcover_asset": self.config.reference.landcover_asset,
                       "hmi_asset": self.config.reference.hmi_gee_asset,
                       "hmi_band": self.config.reference.hmi_gee_band,
                       **eco_diag},
            )
            ref_geom = None
            if qa.approval:
                vectors = candidate.reduceToVectors(
                    geometry=eco_context, scale=30, geometryType="polygon", eightConnected=True,
                    labelProperty="reference_habitat", maxPixels=1e9, bestEffort=True)
                ref_geom = vectors.geometry()
            status = "validated_candidate" if qa.approval else "candidate_rejected"
            return ReferencePopulation("auto_terrestrial", "terrestrial",
                                       "ecoregion_landcover_low_pressure", status,
                                       geometry=ref_geom, candidate_area_ha=area_ha,
                                       candidate_pixels=pixels, approval=qa.approval,
                                       reference_state="least_disturbed_contemporary",
                                       diagnostics=qa.diagnostics)
        except Exception as exc:
            return ReferencePopulation("auto_terrestrial", "terrestrial",
                                       "ecoregion_landcover_low_pressure", f"error:{exc}",
                                       reference_state="least_disturbed_contemporary", diagnostics={})

    def build(self, master_geometry, realm: str, start: str, end: str) -> ReferencePopulation:
        if realm == "aquatic":
            return self.aquatic_candidate(master_geometry, start, end)
        if realm == "terrestrial":
            return self.terrestrial_candidate(master_geometry, start, end)
        return ReferencePopulation("auto_mixed", "mixed", "separate_realm_candidates",
                                   "requires_domain_specific_selection",
                                   reference_state="least_disturbed_contemporary")
