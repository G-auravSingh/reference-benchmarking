"""Automatic, ecologically matched reference-population construction.

Reference construction is deliberately separated from reference approval. A spatial
candidate is not a reference merely because it is nearby or has low human
modification. The production pathway requires ecological comparability, pressure
screening, temporal compatibility, spatial quality and minimum population size.

The engine is Earth-Engine aware, but the approval contract itself lives in
``reference_condition.py`` so it can be tested without Earth Engine.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

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
    diagnostics: Optional[Dict[str, Any]] = None

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
    def _scalar(image, geometry, reducer, band=None, scale=30):
        import ee

        img = ee.Image(image)
        if band:
            img = img.select(band)
        result = img.reduceRegion(
            reducer=reducer,
            geometry=geometry,
            scale=scale,
            maxPixels=1e9,
            bestEffort=True,
        )
        if band:
            value = result.get(band)
        else:
            value = result.values().get(0)
        try:
            return value.getInfo() if value is not None else None
        except Exception:
            return None

    def _site_mean(self, image, geometry, scale=30):
        import ee
        return self._scalar(image, geometry, ee.Reducer.mean(), scale=scale)

    def _ecoregion_geometry(self, master_geometry, context):
        """Restrict the search context to the site's dominant RESOLVE ecoregion.

        RESOLVE Ecoregions 2017 is a terrestrial biogeographic layer. For aquatic
        sites it is used only as a surrounding biogeographic comparability stratum,
        not as an aquatic ecosystem typology.
        """
        import ee

        fc = ee.FeatureCollection(self.config.reference.ecoregion_gee_asset)
        hits = fc.filterBounds(master_geometry)
        try:
            n = int(hits.size().getInfo())
            if n == 0:
                return context, False, {"ecoregion_filter": "no_site_match"}

            def add_overlap(feature):
                overlap = feature.geometry().intersection(master_geometry, ee.ErrorMargin(30)).area(1)
                return feature.set("_site_overlap_m2", overlap)

            ranked = hits.map(add_overlap).sort("_site_overlap_m2", False).limit(1)
            selected = ee.Feature(ranked.first())
            selected_info = selected.toDictionary(["ECO_ID", "ECO_NAME", "REALM"]).getInfo() or {}
            eco_geom = selected.geometry().intersection(context, ee.ErrorMargin(30))
            return eco_geom, True, {
                "ecoregion_filter": "RESOLVE_2017_dominant_site_ecoregion",
                "site_ecoregion_feature_count": n,
                "selected_ecoregion_id": selected_info.get("ECO_ID"),
                "selected_ecoregion_name": selected_info.get("ECO_NAME"),
                "selected_ecoregion_realm": selected_info.get("REALM"),
            }
        except Exception as exc:
            return context, False, {"ecoregion_filter": f"error:{exc}"}

    def _hmi_image(self, geometry):
        """Load the TNC HM v3 90 m static snapshot correctly as an ImageCollection."""
        import ee

        asset = self.config.reference.hmi_gee_asset
        band = self.config.reference.hmi_gee_band
        collection = ee.ImageCollection(asset).filterBounds(geometry).select(band)
        n = int(collection.size().getInfo())
        if n < 1:
            return None, n, {
                "hmi_asset": asset,
                "hmi_band": band,
                "hmi_image_count": n,
                "hmi_status": "no_image_in_context",
            }
        # The configured v3 90m_s asset is a static 2022 snapshot represented as
        # an ImageCollection in Earth Engine. Median is robust if the catalog later
        # contains more than one matching image.
        image = collection.median().select(band)
        return image, n, {
            "hmi_asset": asset,
            "hmi_band": band,
            "hmi_image_count": n,
            "hmi_status": "ok",
            "hmi_aggregation": "median",
            "hmi_resolution_m": 90,
        }

    def _hmi_context_filter(self, water_mask, context, start=None, end=None):
        """Screen aquatic candidates using low human modification in surrounding land.

        HMI is a terrestrial pressure surface. It is therefore sampled through a
        local focal mean of land pixels surrounding candidate water, rather than
        interpreted as a water-quality variable or as a direct measure of lake
        condition.

        The diagnostics deliberately retain the *pre-pressure* HMI distribution and
        progressive retention at several thresholds. This is essential for auditing
        whether a strict absolute HMI gate is genuinely excluding the regional
        candidate population or whether another reference-selection gate is
        responsible.
        """
        import ee

        hmi, hmi_n, hmi_diag = self._hmi_image(context)
        if hmi is None:
            return ee.Image(0).selfMask().rename("reference_water"), False, {
                **hmi_diag,
                "pressure_screen_status": "unavailable",
            }

        land_mask = None
        dw_n = None
        if start and end:
            dw = (ee.ImageCollection(self.config.reference.landcover_asset)
                  .filterBounds(context).filterDate(start, end).select("label"))
            dw_n = int(dw.size().getInfo())
            if dw_n > 0:
                # Dynamic World label 0 is water. Other classes are treated as
                # surrounding land context for the pressure screen only.
                land_mask = dw.mode().neq(0)

        contextual = hmi
        if land_mask is not None:
            contextual = contextual.updateMask(land_mask)
        contextual = contextual.focal_mean(
            radius=float(self.config.reference.hmi_context_radius_m),
            units="meters",
        )

        # Diagnostics before the HMI threshold. These describe the HMI exposure of
        # the entire ecologically/hydrologically matched candidate population.
        pre_stats = contextual.updateMask(water_mask).reduceRegion(
            reducer=ee.Reducer.percentile([0, 5, 10, 25, 50, 75, 90, 95, 100])
                    .combine(ee.Reducer.count(), sharedInputs=True),
            geometry=context, scale=90, maxPixels=1e9, bestEffort=True,
        )

        def get_info_dict(obj):
            try:
                value = obj.getInfo()
                return {} if value is None else value
            except Exception:
                return {}

        pre_stats_raw = get_info_dict(pre_stats)
        # Earth Engine reducer output keys are band-prefixed for percentile
        # reducers and '<band>_count' for the combined count.
        hmi_band = self.config.reference.hmi_gee_band

        def first_key(prefixes):
            for prefix in prefixes:
                if prefix in pre_stats_raw:
                    return pre_stats_raw[prefix]
            return None

        hmi_distribution = {
            "n_hmi_pixels": first_key([f"{hmi_band}_count", "count"]),
            "min": first_key([f"{hmi_band}_p0", f"{hmi_band}_p0.0"]),
            "p05": first_key([f"{hmi_band}_p5", f"{hmi_band}_p5.0"]),
            "p10": first_key([f"{hmi_band}_p10", f"{hmi_band}_p10.0"]),
            "p25": first_key([f"{hmi_band}_p25", f"{hmi_band}_p25.0"]),
            "p50": first_key([f"{hmi_band}_p50", f"{hmi_band}_p50.0"]),
            "p75": first_key([f"{hmi_band}_p75", f"{hmi_band}_p75.0"]),
            "p90": first_key([f"{hmi_band}_p90", f"{hmi_band}_p90.0"]),
            "p95": first_key([f"{hmi_band}_p95", f"{hmi_band}_p95.0"]),
            "max": first_key([f"{hmi_band}_p100", f"{hmi_band}_p100.0"]),
        }

        thresholds = [0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50]
        retention_by_threshold = {}
        for threshold_value in thresholds:
            retained = water_mask.And(contextual.lte(threshold_value)).selfMask()
            retained_area = ee.Image.pixelArea().updateMask(retained).reduceRegion(
                reducer=ee.Reducer.sum(), geometry=context, scale=10,
                maxPixels=1e9, bestEffort=True).get("area")
            retained_pixels = retained.reduceRegion(
                reducer=ee.Reducer.count(), geometry=context, scale=10,
                maxPixels=1e9, bestEffort=True).values().get(0)
            area_m2 = get_info_dict(retained_area)
            pixels_value = get_info_dict(retained_pixels)
            # getInfo() on scalar EE objects returns a scalar rather than a dict;
            # normalize both forms.
            if isinstance(area_m2, dict):
                area_m2 = area_m2.get("area")
            if isinstance(pixels_value, dict):
                pixels_value = next(iter(pixels_value.values()), None)
            retention_by_threshold[str(threshold_value)] = {
                "area_ha": None if area_m2 is None else float(area_m2) / 1e4,
                "pixels_10m": None if pixels_value is None else int(pixels_value),
            }

        threshold = float(self.config.reference.hmi_max_for_reference)
        pre_area = ee.Image.pixelArea().updateMask(water_mask).reduceRegion(
            reducer=ee.Reducer.sum(), geometry=context, scale=10,
            maxPixels=1e9, bestEffort=True).get("area")
        screened = water_mask.And(contextual.lte(threshold)).selfMask().rename("reference_water")
        post_area = ee.Image.pixelArea().updateMask(screened).reduceRegion(
            reducer=ee.Reducer.sum(), geometry=context, scale=10,
            maxPixels=1e9, bestEffort=True).get("area")
        hmi_mean = contextual.updateMask(water_mask).reduceRegion(
            reducer=ee.Reducer.mean(), geometry=context, scale=90,
            maxPixels=1e9, bestEffort=True).values().get(0)

        def get_number(value):
            try:
                return None if value is None else value.getInfo()
            except Exception:
                return None

        pre_m2 = get_number(pre_area)
        post_m2 = get_number(post_area)
        hmi_mean_value = get_number(hmi_mean)
        retention = None
        if pre_m2 not in (None, 0) and post_m2 is not None:
            retention = float(post_m2) / float(pre_m2)

        diagnostics = {
            **hmi_diag,
            "hmi_context_radius_m": float(self.config.reference.hmi_context_radius_m),
            "hmi_max_for_reference": threshold,
            "land_context_dataset": self.config.reference.landcover_asset,
            "land_context_images": dw_n,
            "prepressure_candidate_area_ha": None if pre_m2 is None else float(pre_m2) / 1e4,
            "postpressure_candidate_area_ha": None if post_m2 is None else float(post_m2) / 1e4,
            "hmi_mean_over_prepressure_candidate": hmi_mean_value,
            "hmi_distribution_prepressure": hmi_distribution,
            "hmi_retention_by_threshold": retention_by_threshold,
            "pressure_retention_fraction": retention,
            "pressure_screen_status": "passed" if (
                post_m2 is not None and float(post_m2) > 0
            ) else "failed",
        }

        # The thresholded image itself is the pressure-screened population.
        # Approval still requires the downstream population-size QA gate. Do not
        # require the *mean of the unfiltered population* to be below the threshold:
        # that would reject a candidate even when a sufficient low-HMI subset exists.
        pressure_pass = bool(post_m2 is not None and float(post_m2) > 0)
        return screened, pressure_pass, diagnostics

    @staticmethod
    def _as_float(value):
        return None if value is None else float(value)

    def aquatic_candidate(self, master_geometry, start: str, end: str) -> ReferencePopulation:
        import ee

        context = self._buffer_annulus(master_geometry)
        if self.water is None:
            return ReferencePopulation(
                "auto_aquatic", "aquatic", "ecologically_matched_water_population",
                "no_water_detector", reference_state="least_disturbed_contemporary",
                diagnostics={"error": "Water detector is required for automatic aquatic references."},
            )
        try:
            occurrence, method, n = self.water.occurrence_image(context, start, end)
            site_occurrence, site_method, site_n = self.water.occurrence_image(master_geometry, start, end)
            site_mean = self._site_mean(site_occurrence, master_geometry, scale=10)
            if site_mean is None:
                return ReferencePopulation(
                    "auto_aquatic", "aquatic", "ecoregion_hydrology_low_pressure",
                    "site_hydroperiod_unavailable", reference_state="least_disturbed_contemporary",
                    diagnostics={"occurrence_method": site_method, "occurrence_images": n, "site_occurrence_images": site_n},
                )

            min_occ = float(self.config.reference.auto_min_water_occurrence)
            tol = float(self.config.reference.water_occurrence_tolerance)
            water_similar = (
                occurrence.gte(min_occ)
                .And(occurrence.subtract(float(site_mean)).abs().lte(tol))
                .And(occurrence.lte(1.0))
            )
            eco_context, eco_ok, eco_diag = self._ecoregion_geometry(master_geometry, context)
            prepressure_candidate = water_similar.clip(eco_context).selfMask()

            def _mask_area_pixels(mask):
                area_obj = ee.Image.pixelArea().updateMask(mask).reduceRegion(
                    reducer=ee.Reducer.sum(), geometry=eco_context, scale=10,
                    maxPixels=1e9, bestEffort=True).get("area")
                pix_obj = mask.reduceRegion(
                    reducer=ee.Reducer.count(), geometry=eco_context, scale=10,
                    maxPixels=1e9, bestEffort=True).values().get(0)
                try:
                    area_value = area_obj.getInfo() if area_obj is not None else None
                except Exception:
                    area_value = None
                try:
                    pix_value = pix_obj.getInfo() if pix_obj is not None else None
                except Exception:
                    pix_value = None
                return {
                    "area_ha": None if area_value is None else float(area_value) / 1e4,
                    "pixels_10m": None if pix_value is None else int(pix_value),
                }

            progressive = {
                "hydrology_and_water_occurrence": _mask_area_pixels(water_similar),
                "ecoregion_hydrology_candidate": _mask_area_pixels(prepressure_candidate),
            }

            candidate, pressure_ok, hmi_diag = self._hmi_context_filter(
                prepressure_candidate, eco_context, start=start, end=end
            )
            progressive["hmi_screened_candidate"] = {
                "area_ha": hmi_diag.get("postpressure_candidate_area_ha"),
                "pixels_10m": (
                    hmi_diag.get("hmi_retention_by_threshold", {})
                    .get(str(float(self.config.reference.hmi_max_for_reference)), {})
                    .get("pixels_10m")
                ),
            }
            candidate = candidate.selfMask()

            area = ee.Image.pixelArea().updateMask(candidate).reduceRegion(
                reducer=ee.Reducer.sum(), geometry=eco_context, scale=10,
                maxPixels=1e9, bestEffort=True).get("area")
            pix = candidate.reduceRegion(
                reducer=ee.Reducer.count(), geometry=eco_context, scale=10,
                maxPixels=1e9, bestEffort=True).values().get(0)
            area_ha = self._as_float(area.getInfo() if area is not None else None)
            pixels_raw = pix.getInfo() if pix is not None else None
            pixels = None if pixels_raw is None else int(pixels_raw)
            area_ha = None if area_ha is None else area_ha / 1e4

            candidate_occ = occurrence.updateMask(candidate).reduceRegion(
                reducer=ee.Reducer.mean(), geometry=eco_context, scale=10,
                maxPixels=1e9, bestEffort=True).values().get(0)
            candidate_occ = self._as_float(candidate_occ.getInfo() if candidate_occ is not None else None)
            match_score = (
                max(0.0, 1.0 - abs(candidate_occ - float(site_mean)) / max(tol, 1e-6))
                if candidate_occ is not None else 0.0
            )

            temporal_ok = n >= self.config.reference.min_reference_observations and site_n >= self.config.reference.min_reference_observations
            qa = evaluate_reference_candidate(
                candidate_area_ha=area_ha,
                candidate_pixels=pixels,
                min_area_ha=self.config.reference.auto_min_candidate_area_ha,
                min_pixels=self.config.reference.auto_min_candidate_pixels,
                ecological_match_score=match_score if eco_ok else 0.0,
                min_ecological_match_score=self.config.reference.min_ecological_match_score,
                pressure_screen_pass=pressure_ok,
                temporal_match_pass=temporal_ok,
                spatial_quality_pass=eco_ok,
                reference_state="least_disturbed_contemporary",
                auto_approve=self.config.reference.auto_approve,
                extra={
                    "site_water_occurrence": float(site_mean),
                    "candidate_mean_water_occurrence": candidate_occ,
                    "water_occurrence_tolerance": tol,
                    "minimum_water_occurrence": min_occ,
                    "occurrence_method": method,
                    "site_occurrence_method": site_method,
                    "occurrence_images": int(n),
                    "site_occurrence_images": int(site_n),
                    "progressive_candidate_gates": progressive,
                    **eco_diag,
                    **hmi_diag,
                },
            )

            ref_geom = None
            if qa.approval_recommendation:
                vectors = candidate.reduceToVectors(
                    geometry=eco_context, scale=30, geometryType="polygon",
                    eightConnected=True, labelProperty="reference_water",
                    maxPixels=1e9, bestEffort=True,
                )
                ref_geom = vectors.geometry()

            status = "validated_candidate" if qa.approval_recommendation else (
                "candidate_rejected" if area_ha is not None else "candidate_unresolved"
            )
            return ReferencePopulation(
                "auto_aquatic", "aquatic", "ecoregion_hydrology_low_pressure", status,
                geometry=ref_geom, candidate_area_ha=area_ha, candidate_pixels=pixels,
                approval=qa.approval_recommendation, reference_state="least_disturbed_contemporary",
                diagnostics=qa.diagnostics,
            )
        except Exception as exc:
            return ReferencePopulation(
                "auto_aquatic", "aquatic", "ecoregion_hydrology_low_pressure",
                f"error:{type(exc).__name__}",
                reference_state="least_disturbed_contemporary",
                diagnostics={"error": str(exc), "exception_type": type(exc).__name__},
            )

    def terrestrial_candidate(self, master_geometry, start: Optional[str] = None, end: Optional[str] = None):
        import ee

        context = self._buffer_annulus(master_geometry)
        try:
            eco_context, eco_ok, eco_diag = self._ecoregion_geometry(master_geometry, context)
            dw_collection = (ee.ImageCollection(self.config.reference.landcover_asset)
                             .filterBounds(eco_context).select("label"))
            if start and end:
                dw_collection = dw_collection.filterDate(start, end)
            dw_n = int(dw_collection.size().getInfo())
            if dw_n < 1:
                return ReferencePopulation(
                    "auto_terrestrial", "terrestrial", "ecoregion_landcover_low_pressure",
                    "landcover_unavailable", reference_state="least_disturbed_contemporary",
                    diagnostics={**eco_diag, "landcover_images": dw_n},
                )
            dw = dw_collection.mode()
            site_class_value = dw.reduceRegion(
                reducer=ee.Reducer.mode(), geometry=master_geometry, scale=10,
                maxPixels=1e9, bestEffort=True).get("label")
            site_class = site_class_value.getInfo() if site_class_value is not None else None
            if site_class is None:
                return ReferencePopulation(
                    "auto_terrestrial", "terrestrial", "ecoregion_landcover_low_pressure",
                    "site_landcover_unavailable", reference_state="least_disturbed_contemporary",
                    diagnostics={**eco_diag, "landcover_images": dw_n},
                )
            if int(site_class) == 0:
                return ReferencePopulation(
                    "auto_terrestrial", "terrestrial", "ecoregion_landcover_low_pressure",
                    "site_is_water_class", reference_state="least_disturbed_contemporary",
                    diagnostics={**eco_diag, "site_dynamic_world_class": 0, "landcover_images": dw_n},
                )

            hmi, hmi_n, hmi_diag = self._hmi_image(eco_context)
            if hmi is None:
                return ReferencePopulation(
                    "auto_terrestrial", "terrestrial", "ecoregion_landcover_low_pressure",
                    "hmi_unavailable", reference_state="least_disturbed_contemporary",
                    diagnostics={**eco_diag, **hmi_diag},
                )

            # Same Dynamic World habitat class + low contemporary human modification.
            # The land-cover class is a comparability stratum, not proof of naturalness.
            candidate = dw.eq(int(site_class)).And(hmi.lte(self.config.reference.hmi_max_for_reference)).selfMask()
            area = ee.Image.pixelArea().updateMask(candidate).reduceRegion(
                reducer=ee.Reducer.sum(), geometry=eco_context, scale=10,
                maxPixels=1e9, bestEffort=True).get("area")
            pix = candidate.reduceRegion(
                reducer=ee.Reducer.count(), geometry=eco_context, scale=10,
                maxPixels=1e9, bestEffort=True).values().get(0)
            area_ha = self._as_float(area.getInfo() if area is not None else None)
            pixels_raw = pix.getInfo() if pix is not None else None
            pixels = None if pixels_raw is None else int(pixels_raw)
            area_ha = None if area_ha is None else area_ha / 1e4

            hmi_mean = hmi.updateMask(candidate).reduceRegion(
                reducer=ee.Reducer.mean(), geometry=eco_context, scale=90,
                maxPixels=1e9, bestEffort=True).values().get(0)
            hmi_mean = self._as_float(hmi_mean.getInfo() if hmi_mean is not None else None)
            pressure_ok = hmi_mean is not None and hmi_mean <= float(self.config.reference.hmi_max_for_reference)
            qa = evaluate_reference_candidate(
                candidate_area_ha=area_ha,
                candidate_pixels=pixels,
                min_area_ha=self.config.reference.auto_min_candidate_area_ha,
                min_pixels=self.config.reference.auto_min_candidate_pixels,
                ecological_match_score=1.0 if eco_ok else 0.0,
                min_ecological_match_score=self.config.reference.min_ecological_match_score,
                pressure_screen_pass=pressure_ok,
                temporal_match_pass=True,
                spatial_quality_pass=eco_ok,
                reference_state="least_disturbed_contemporary",
                auto_approve=self.config.reference.auto_approve,
                extra={
                    "site_dynamic_world_class": int(site_class),
                    "landcover_asset": self.config.reference.landcover_asset,
                    "landcover_images": dw_n,
                    "hmi_mean_over_candidate": hmi_mean,
                    **hmi_diag,
                    **eco_diag,
                },
            )
            ref_geom = None
            if qa.approval_recommendation:
                vectors = candidate.reduceToVectors(
                    geometry=eco_context, scale=30, geometryType="polygon",
                    eightConnected=True, labelProperty="reference_habitat",
                    maxPixels=1e9, bestEffort=True,
                )
                ref_geom = vectors.geometry()
            status = "validated_candidate" if qa.approval_recommendation else "candidate_rejected"
            return ReferencePopulation(
                "auto_terrestrial", "terrestrial", "ecoregion_landcover_low_pressure", status,
                geometry=ref_geom, candidate_area_ha=area_ha,
                candidate_pixels=pixels, approval=qa.approval_recommendation,
                reference_state="least_disturbed_contemporary", diagnostics=qa.diagnostics,
            )
        except Exception as exc:
            return ReferencePopulation(
                "auto_terrestrial", "terrestrial", "ecoregion_landcover_low_pressure",
                f"error:{type(exc).__name__}", reference_state="least_disturbed_contemporary",
                diagnostics={"error": str(exc), "exception_type": type(exc).__name__},
            )

    def build(self, master_geometry, realm: str, start: str, end: str) -> ReferencePopulation:
        if realm == "aquatic":
            return self.aquatic_candidate(master_geometry, start, end)
        if realm == "terrestrial":
            return self.terrestrial_candidate(master_geometry, start, end)
        return ReferencePopulation(
            "auto_mixed", "mixed", "separate_realm_candidates",
            "requires_domain_specific_selection", reference_state="least_disturbed_contemporary",
            diagnostics={"note": "Mixed assessments require separate aquatic and terrestrial reference populations."},
        )
