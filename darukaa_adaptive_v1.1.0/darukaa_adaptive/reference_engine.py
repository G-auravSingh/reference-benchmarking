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
from .reference_profiles import (AQUATIC_LAKE_PROFILE, TERRESTRIAL_PROFILE,
                                 ReferenceSelectionPolicy)


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
    """Construct comparable candidate populations for the finite automatic reference workflow; no reference-file upload is required."""

    def __init__(self, config, water_detector=None):
        self.config = config
        self.water = water_detector
        self.policy = ReferenceSelectionPolicy(config)

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

    def _hmi_context_filter(self, water_mask, context, start=None, end=None, threshold=None):
        """Apply an HMI threshold to a candidate water population.

        ``threshold`` is supplied by the caller so the same implementation can
        support the strict minimally-disturbed screen and the finite
        least-disturbed contemporary fallback without silently changing the policy.
        """
        import ee
        hmi, hmi_n, hmi_diag = self._hmi_image(context)
        if hmi is None:
            return ee.Image(0).selfMask().rename("reference_water"), False, {**hmi_diag, "pressure_screen_status":"unavailable"}
        land_mask = None; dw_n = None
        if start and end:
            dw=(ee.ImageCollection(self.config.reference.landcover_asset).filterBounds(context).filterDate(start,end).select("label"))
            dw_n=int(dw.size().getInfo())
            if dw_n>0: land_mask=dw.mode().neq(0)
        contextual=hmi
        if land_mask is not None: contextual=contextual.updateMask(land_mask)
        contextual=contextual.focal_mean(radius=float(self.config.reference.hmi_context_radius_m),units="meters")
        threshold=float(self.config.reference.hmi_max_for_reference if threshold is None else threshold)
        screened=water_mask.And(contextual.lte(threshold)).selfMask().rename("reference_water")
        pre_area=ee.Image.pixelArea().updateMask(water_mask).reduceRegion(reducer=ee.Reducer.sum(),geometry=context,scale=10,maxPixels=1e9,bestEffort=True).get("area")
        post_area=ee.Image.pixelArea().updateMask(screened).reduceRegion(reducer=ee.Reducer.sum(),geometry=context,scale=10,maxPixels=1e9,bestEffort=True).get("area")
        def get_number(v):
            try: return None if v is None else v.getInfo()
            except Exception: return None
        pre_m2=get_number(pre_area); post_m2=get_number(post_area)
        hmi_mean=get_number(contextual.updateMask(water_mask).reduceRegion(reducer=ee.Reducer.mean(),geometry=context,scale=90,maxPixels=1e9,bestEffort=True).values().get(0))
        retention=None if pre_m2 in (None,0) or post_m2 is None else float(post_m2)/float(pre_m2)
        pressure_pass=bool(post_m2 is not None and float(post_m2)>0)
        diagnostics={**hmi_diag,"hmi_context_radius_m":float(self.config.reference.hmi_context_radius_m),
                     "hmi_max_for_reference":threshold,"land_context_dataset":self.config.reference.landcover_asset,
                     "land_context_images":dw_n,"hmi_mean_over_prepressure_candidate":hmi_mean,
                     "pressure_retention_fraction":retention,"pressure_screen_status":"passed" if pressure_pass else "failed",
                     **self._hmi_diagnostics(contextual,water_mask,context)}
        return screened,pressure_pass,diagnostics

    def _hmi_diagnostics(self, contextual, water_mask, geometry):
        """Return pre-pressure HMI distribution and threshold-retention diagnostics.

        HMI pixels are spatial observations, not independent ecological replicates.
        These diagnostics are therefore descriptive and are never treated as site n.
        """
        import ee
        stats = contextual.updateMask(water_mask).reduceRegion(
            reducer=ee.Reducer.percentile([0,5,10,25,50,75,90,95,100]).combine(
                ee.Reducer.count(), sharedInputs=True
            ), geometry=geometry, scale=90, maxPixels=1e9, bestEffort=True
        )
        info = stats.getInfo() or {}
        # Earth Engine percentile/count keys depend on the band name; normalize them.
        band = self.config.reference.hmi_gee_band
        def pick(p):
            for k in (f"{band}_p{p}", f"{band}_percentile_{p}", f"p{p}"):
                if k in info: return info[k]
            return None
        count = info.get(f"{band}_count", info.get("count"))
        dist = {"hmi_min": pick(0), "hmi_p05": pick(5), "hmi_p10": pick(10),
                "hmi_p25": pick(25), "hmi_p50": pick(50), "hmi_p75": pick(75),
                "hmi_p90": pick(90), "hmi_p95": pick(95), "hmi_max": pick(100),
                "hmi_valid_pixels": count}
        dist["hmi_diagnostic_note"] = "Distribution percentiles are computed once per reference stage; threshold-area sensitivity sweeps are not part of the production run. Candidate area at each selected stage is the governing retention diagnostic."
        return dist

    @staticmethod
    def _as_float(value):
        return None if value is None else float(value)

    def _aquatic_candidate_once(self, master_geometry, start, end, threshold, state, method):
        import ee
        context=self._buffer_annulus(master_geometry)
        occurrence,method_occ,n=self.water.occurrence_image(context,start,end)
        site_occurrence,site_method,site_n=self.water.occurrence_image(master_geometry,start,end)
        site_mean=self._site_mean(site_occurrence,master_geometry,scale=10)
        if site_mean is None:
            return ReferencePopulation("auto_aquatic","aquatic",method,"site_hydroperiod_unavailable",reference_state=state,diagnostics={"occurrence_method":site_method,"occurrence_images":n,"site_occurrence_images":site_n})
        min_occ=float(self.config.reference.auto_min_water_occurrence); tol=float(self.config.reference.water_occurrence_tolerance)
        water_similar=occurrence.gte(min_occ).And(occurrence.subtract(float(site_mean)).abs().lte(tol)).And(occurrence.lte(1.0))
        eco_context,eco_ok,eco_diag=self._ecoregion_geometry(master_geometry,context)
        pre=water_similar.clip(eco_context).selfMask()
        candidate,pressure_ok,hmi_diag=self._hmi_context_filter(pre,eco_context,start=start,end=end,threshold=threshold)
        candidate=candidate.selfMask()
        area=ee.Image.pixelArea().updateMask(candidate).reduceRegion(reducer=ee.Reducer.sum(),geometry=eco_context,scale=10,maxPixels=1e9,bestEffort=True).get("area")
        area_m2 = self._as_float(area.getInfo() if area is not None else None)
        area_ha = None if area_m2 is None else area_m2/1e4
        # Candidate pixel count is a nominal 10-m equivalent derived from area;
        # do not use a bestEffort reducer count as if it were a fixed-scale count.
        pixels = None if area_m2 is None else int(round(area_m2/100.0))
        candidate_occ=occurrence.updateMask(candidate).reduceRegion(reducer=ee.Reducer.mean(),geometry=eco_context,scale=10,maxPixels=1e9,bestEffort=True).values().get(0)
        candidate_occ=self._as_float(candidate_occ.getInfo() if candidate_occ is not None else None)
        # Ecological similarity is a hard eligibility gate, not a score that can
        # be traded against HMI. Pixel-level occurrence tolerance already defines
        # the eligible aquatic population; therefore no second aggregate match
        # score is used to reject the resulting population.
        ecological_gate = bool(eco_ok and candidate_occ is not None)
        temporal_ok=n>=self.config.reference.min_reference_observations and site_n>=self.config.reference.min_reference_observations
        eco_rule=("RESOLVE ecoregion + pixel-level water-occurrence regime: occurrence >= "
                  f"{min_occ} and abs(candidate_occurrence - site_occurrence) <= {tol}")
        eco_policy_diag=self.policy.ecological_gate_diagnostics(
            profile=AQUATIC_LAKE_PROFILE, passed=ecological_gate, rule=eco_rule,
            components={"site_water_occurrence":float(site_mean),"candidate_mean_water_occurrence":candidate_occ,
                        "minimum_water_occurrence":min_occ,"water_occurrence_tolerance":tol,
                        "ecoregion_ok":bool(eco_ok)})
        qa=evaluate_reference_candidate(candidate_area_ha=area_ha,candidate_pixels=pixels,min_area_ha=self.config.reference.auto_min_candidate_area_ha,min_pixels=self.config.reference.auto_min_candidate_pixels,ecological_match_score=1.0 if ecological_gate else 0.0,min_ecological_match_score=1.0,pressure_screen_pass=pressure_ok,temporal_match_pass=temporal_ok,spatial_quality_pass=ecological_gate,reference_state=state,auto_approve=self.config.reference.auto_approve,extra={"site_water_occurrence":float(site_mean),"candidate_mean_water_occurrence":candidate_occ,"water_occurrence_tolerance":tol,"minimum_water_occurrence":min_occ,"occurrence_method":method_occ,"site_occurrence_method":site_method,"occurrence_images":int(n),"site_occurrence_images":int(site_n),"reference_hmi_threshold":float(threshold),**eco_policy_diag,**eco_diag,**hmi_diag})
        ref_geom=None
        if qa.approval_recommendation:
            vectors=candidate.reduceToVectors(geometry=eco_context,scale=30,geometryType="polygon",eightConnected=True,labelProperty="reference_water",maxPixels=1e9,bestEffort=True)
            ref_geom=vectors.geometry()
        status="validated_candidate" if qa.approval_recommendation else ("candidate_rejected" if area_ha is not None else "candidate_unresolved")
        return ReferencePopulation("auto_aquatic","aquatic",method,status,geometry=ref_geom,candidate_area_ha=area_ha,candidate_pixels=pixels,approval=qa.approval_recommendation,reference_state=state,diagnostics=qa.diagnostics)

    def _aquatic_ecological_population(self, master_geometry, start, end):
        import ee
        context=self._buffer_annulus(master_geometry)
        occurrence,method_occ,n=self.water.occurrence_image(context,start,end)
        site_occurrence,site_method,site_n=self.water.occurrence_image(master_geometry,start,end)
        site_mean=self._site_mean(site_occurrence,master_geometry,scale=10)
        if site_mean is None:
            return None, None, None, None, {"status":"site_hydroperiod_unavailable","occurrence_method":site_method,
                                             "occurrence_images":n,"site_occurrence_images":site_n}
        eco_context,eco_ok,eco_diag=self._ecoregion_geometry(master_geometry,context)
        min_occ=float(self.config.reference.auto_min_water_occurrence)
        tol=float(self.config.reference.water_occurrence_tolerance)
        pre=occurrence.gte(min_occ).And(occurrence.subtract(float(site_mean)).abs().lte(tol)).And(occurrence.lte(1.0)).clip(eco_context).selfMask()
        temporal_ok=n>=self.config.reference.min_reference_observations and site_n>=self.config.reference.min_reference_observations
        rule=("RESOLVE ecoregion + pixel-level water-occurrence regime: occurrence >= "
              f"{min_occ} and abs(candidate_occurrence - site_occurrence) <= {tol}")
        diagnostics={**self.policy.ecological_gate_diagnostics(
            profile=AQUATIC_LAKE_PROFILE, passed=bool(eco_ok), rule=rule,
            components={"site_water_occurrence":float(site_mean),"minimum_water_occurrence":min_occ,
                        "water_occurrence_tolerance":tol,"ecoregion_ok":bool(eco_ok)}),
            "site_water_occurrence":float(site_mean),"occurrence_method":method_occ,
            "site_occurrence_method":site_method,"occurrence_images":int(n),"site_occurrence_images":int(site_n),
            **eco_diag}
        return pre, eco_context, site_mean, temporal_ok, diagnostics

    def _aquatic_candidate_once(self, master_geometry, start, end, threshold, state, method):
        import ee
        pre, eco_context, site_mean, temporal_ok, base_diag=self._aquatic_ecological_population(master_geometry,start,end)
        if pre is None:
            return ReferencePopulation("auto_aquatic","aquatic",method,base_diag.get("status","candidate_unresolved"),reference_state=state,diagnostics=base_diag)
        candidate,pressure_ok,hmi_diag=self._hmi_context_filter(pre,eco_context,start=start,end=end,threshold=threshold)
        area=ee.Image.pixelArea().updateMask(candidate).reduceRegion(reducer=ee.Reducer.sum(),geometry=eco_context,scale=10,maxPixels=1e9,bestEffort=True).get("area")
        area_m2=self._as_float(area.getInfo() if area is not None else None)
        area_ha=None if area_m2 is None else area_m2/1e4
        pixels=None if area_m2 is None else int(round(area_m2/100.0))
        candidate_occ=occurrence=None
        # Reconstruct the candidate occurrence from the pre-mask to document the
        # realized population; no new ecological score is computed.
        water_occ,_,_=self.water.occurrence_image(eco_context,start,end)
        co=water_occ.updateMask(candidate).reduceRegion(reducer=ee.Reducer.mean(),geometry=eco_context,scale=10,maxPixels=1e9,bestEffort=True).values().get(0)
        candidate_occ=self._as_float(co.getInfo() if co is not None else None)
        ecological_gate=bool(base_diag.get("ecological_eligibility_pass") and candidate_occ is not None)
        qa=evaluate_reference_candidate(candidate_area_ha=area_ha,candidate_pixels=pixels,
            min_area_ha=self.config.reference.auto_min_candidate_area_ha,min_pixels=self.config.reference.auto_min_candidate_pixels,
            ecological_match_score=1.0 if ecological_gate else 0.0,min_ecological_match_score=1.0,
            pressure_screen_pass=pressure_ok,temporal_match_pass=temporal_ok,spatial_quality_pass=ecological_gate,
            reference_state=state,auto_approve=self.config.reference.auto_approve,
            extra={**base_diag,"candidate_mean_water_occurrence":candidate_occ,
                   "reference_hmi_threshold":float(threshold),**hmi_diag})
        ref_geom=None
        if qa.approval_recommendation:
            vectors=candidate.reduceToVectors(geometry=eco_context,scale=30,geometryType="polygon",eightConnected=True,labelProperty="reference_water",maxPixels=1e9,bestEffort=True)
            ref_geom=vectors.geometry()
        status="validated_candidate" if qa.approval_recommendation else ("candidate_rejected" if area_ha is not None else "candidate_unresolved")
        return ReferencePopulation("auto_aquatic","aquatic",method,status,geometry=ref_geom,candidate_area_ha=area_ha,candidate_pixels=pixels,approval=qa.approval_recommendation,reference_state=state,diagnostics=qa.diagnostics)

    def aquatic_candidate(self, master_geometry, start: Optional[str] = None, end: Optional[str] = None):
        """Finite aquatic reference selection using ecological gates then HMI ordering."""
        if self.water is None:
            return ReferencePopulation("auto_aquatic","aquatic","aquatic_reference_policy","no_water_detector",reference_state="least_disturbed_contemporary",diagnostics={"error":"Water detector is required for automatic aquatic references."})
        try:
            strict=self._aquatic_candidate_once(master_geometry,start,end,float(self.config.reference.hmi_max_for_reference),"least_disturbed_contemporary","aquatic_ecological_gate_strict_hmi")
            if strict.approval or not self.config.reference.least_disturbed_enabled:
                return strict

            pre,eco_context,site_mean,temporal_ok,base_diag=self._aquatic_ecological_population(master_geometry,start,end)
            least=None; qval=None
            if pre is not None:
                import ee
                hmi,_,hmi_diag=self._hmi_image(eco_context)
                if hmi is not None:
                    dw=ee.ImageCollection(self.config.reference.landcover_asset).filterBounds(eco_context).filterDate(start,end).select("label")
                    land=dw.mode().neq(0) if int(dw.size().getInfo())>0 else None
                    contextual=hmi.updateMask(land) if land is not None else hmi
                    contextual=contextual.focal_mean(radius=float(self.config.reference.hmi_context_radius_m),units="meters")
                    q=float(self.config.reference.least_disturbed_quantile)*100.0
                    qdict=contextual.updateMask(pre).reduceRegion(reducer=ee.Reducer.percentile([q]),geometry=eco_context,scale=90,maxPixels=1e9,bestEffort=True).getInfo() or {}
                    qval=float(next(iter(qdict.values()))) if qdict else None
                    if qval is not None:
                        least=self._aquatic_candidate_once(master_geometry,start,end,qval,"least_disturbed_contemporary","aquatic_ecological_gate_least_disturbed_quantile")
                        least.diagnostics=(least.diagnostics or {}) | {"least_disturbed_quantile":float(self.config.reference.least_disturbed_quantile),"least_disturbed_hmi_threshold":qval,"strict_candidate_status":strict.status,"strict_candidate_area_ha":strict.candidate_area_ha,"strict_candidate_pixels":strict.candidate_pixels,**hmi_diag}
                        if least.approval:
                            return least
            if least is None:
                least=strict

            manual_hmi=self.config.reference.manual_hmi_threshold
            if self.config.reference.manual_hmi_fallback_enabled and manual_hmi is not None:
                manual=self._aquatic_candidate_once(master_geometry,start,end,float(manual_hmi),self.config.reference.manual_hmi_reference_state,"aquatic_ecological_gate_manual_hmi")
                manual.diagnostics=(manual.diagnostics or {}) | {"manual_hmi_threshold":float(manual_hmi),"strict_hmi_threshold":float(self.config.reference.hmi_max_for_reference),"least_disturbed_quantile":float(self.config.reference.least_disturbed_quantile),"least_disturbed_hmi_threshold":qval,"strict_candidate_status":strict.status,"least_disturbed_candidate_status":least.status,"manual_threshold_requires_explicit_colab_configuration":True}
                if manual.approval:
                    return manual
                return self.policy.terminal_status(manual,strict,least,manual)

            return self.policy.terminal_status(least,strict,least)
        except Exception as exc:
            return ReferencePopulation("auto_aquatic","aquatic","aquatic_reference_policy","error:"+type(exc).__name__,reference_state="least_disturbed_contemporary",diagnostics={"error":str(exc),"exception_type":type(exc).__name__})

    def _terrestrial_candidate_once(self, master_geometry, start, end, threshold, state, method):
        import ee
        context=self._buffer_annulus(master_geometry)
        eco_context,eco_ok,eco_diag=self._ecoregion_geometry(master_geometry,context)
        dw_collection=ee.ImageCollection(self.config.reference.landcover_asset).filterBounds(eco_context).select("label")
        if start and end: dw_collection=dw_collection.filterDate(start,end)
        dw_n=int(dw_collection.size().getInfo())
        if dw_n<1:
            return ReferencePopulation("auto_terrestrial","terrestrial",method,"landcover_unavailable",reference_state=state,diagnostics={**eco_diag,"landcover_images":dw_n})
        dw=dw_collection.mode()
        site_class_value=dw.reduceRegion(reducer=ee.Reducer.mode(),geometry=master_geometry,scale=10,maxPixels=1e9,bestEffort=True).get("label")
        site_class=site_class_value.getInfo() if site_class_value is not None else None
        if site_class is None:
            return ReferencePopulation("auto_terrestrial","terrestrial",method,"site_landcover_unavailable",reference_state=state,diagnostics={**eco_diag,"landcover_images":dw_n})
        if int(site_class)==0:
            return ReferencePopulation("auto_terrestrial","terrestrial",method,"site_is_water_class",reference_state=state,diagnostics={**eco_diag,"site_dynamic_world_class":0,"landcover_images":dw_n})
        hmi,_,hmi_diag=self._hmi_image(eco_context)
        if hmi is None:
            return ReferencePopulation("auto_terrestrial","terrestrial",method,"hmi_unavailable",reference_state=state,diagnostics={**eco_diag,**hmi_diag})
        candidate=dw.eq(int(site_class)).And(hmi.lte(float(threshold))).selfMask()
        area=ee.Image.pixelArea().updateMask(candidate).reduceRegion(reducer=ee.Reducer.sum(),geometry=eco_context,scale=10,maxPixels=1e9,bestEffort=True).get("area")
        area_m2=self._as_float(area.getInfo() if area is not None else None); area_ha=None if area_m2 is None else area_m2/1e4
        pixels=None if area_m2 is None else int(round(area_m2/100.0))
        hmi_mean=hmi.updateMask(candidate).reduceRegion(reducer=ee.Reducer.mean(),geometry=eco_context,scale=90,maxPixels=1e9,bestEffort=True).values().get(0)
        hmi_mean=self._as_float(hmi_mean.getInfo() if hmi_mean is not None else None)
        ecological_gate=bool(eco_ok and site_class is not None)
        rule="RESOLVE ecoregion + contemporary Dynamic World habitat stratum matching focal modal class"
        eco_policy_diag=self.policy.ecological_gate_diagnostics(profile=TERRESTRIAL_PROFILE,passed=ecological_gate,rule=rule,components={"site_dynamic_world_class":int(site_class),"ecoregion_ok":bool(eco_ok)})
        pressure_ok=hmi_mean is not None and hmi_mean<=float(threshold)
        qa=evaluate_reference_candidate(candidate_area_ha=area_ha,candidate_pixels=pixels,min_area_ha=self.config.reference.auto_min_candidate_area_ha,min_pixels=self.config.reference.auto_min_candidate_pixels,ecological_match_score=1.0 if ecological_gate else 0.0,min_ecological_match_score=1.0,pressure_screen_pass=pressure_ok,temporal_match_pass=True,spatial_quality_pass=ecological_gate,reference_state=state,auto_approve=self.config.reference.auto_approve,extra={**eco_policy_diag,"site_dynamic_world_class":int(site_class),"landcover_asset":self.config.reference.landcover_asset,"landcover_images":dw_n,"hmi_mean_over_candidate":hmi_mean,"reference_hmi_threshold":float(threshold),**hmi_diag,**eco_diag})
        ref_geom=None
        if qa.approval_recommendation:
            vectors=candidate.reduceToVectors(geometry=eco_context,scale=30,geometryType="polygon",eightConnected=True,labelProperty="reference_habitat",maxPixels=1e9,bestEffort=True); ref_geom=vectors.geometry()
        status="validated_candidate" if qa.approval_recommendation else ("candidate_rejected" if area_ha is not None else "candidate_unresolved")
        return ReferencePopulation("auto_terrestrial","terrestrial",method,status,geometry=ref_geom,candidate_area_ha=area_ha,candidate_pixels=pixels,approval=qa.approval_recommendation,reference_state=state,diagnostics=qa.diagnostics)

    def terrestrial_candidate(self, master_geometry, start: Optional[str] = None, end: Optional[str] = None):
        """Finite terrestrial reference selection using habitat eligibility then HMI ordering."""
        try:
            strict=self._terrestrial_candidate_once(master_geometry,start,end,float(self.config.reference.hmi_max_for_reference),"least_disturbed_contemporary","terrestrial_ecological_gate_strict_hmi")
            if strict.approval or not self.config.reference.least_disturbed_enabled:
                return strict
            # Empirical HMI quantile is computed only inside the ecologically eligible habitat population.
            import ee
            context=self._buffer_annulus(master_geometry); eco_context,eco_ok,eco_diag=self._ecoregion_geometry(master_geometry,context)
            dw=ee.ImageCollection(self.config.reference.landcover_asset).filterBounds(eco_context).select("label")
            if start and end: dw=dw.filterDate(start,end)
            dw_n=int(dw.size().getInfo()); least=None; qval=None
            if dw_n>0:
                dwi=dw.mode(); site_class_value=dwi.reduceRegion(reducer=ee.Reducer.mode(),geometry=master_geometry,scale=10,maxPixels=1e9,bestEffort=True).get("label")
                site_class=site_class_value.getInfo() if site_class_value is not None else None
                hmi,_,hmi_diag=self._hmi_image(eco_context)
                if site_class is not None and hmi is not None:
                    pre=dwi.eq(int(site_class)).selfMask()
                    contextual=hmi.focal_mean(radius=float(self.config.reference.hmi_context_radius_m),units="meters")
                    q=float(self.config.reference.least_disturbed_quantile)*100.0
                    qdict=contextual.updateMask(pre).reduceRegion(reducer=ee.Reducer.percentile([q]),geometry=eco_context,scale=90,maxPixels=1e9,bestEffort=True).getInfo() or {}
                    qval=float(next(iter(qdict.values()))) if qdict else None
                    if qval is not None:
                        least=self._terrestrial_candidate_once(master_geometry,start,end,qval,"least_disturbed_contemporary","terrestrial_ecological_gate_least_disturbed_quantile")
                        least.diagnostics=(least.diagnostics or {}) | {"least_disturbed_quantile":float(self.config.reference.least_disturbed_quantile),"least_disturbed_hmi_threshold":qval,"strict_candidate_status":strict.status,"strict_candidate_area_ha":strict.candidate_area_ha,"strict_candidate_pixels":strict.candidate_pixels,**hmi_diag}
                        if least.approval: return least
            if least is None: least=strict
            manual_hmi=self.config.reference.manual_hmi_threshold
            if self.config.reference.manual_hmi_fallback_enabled and manual_hmi is not None:
                manual=self._terrestrial_candidate_once(master_geometry,start,end,float(manual_hmi),self.config.reference.manual_hmi_reference_state,"terrestrial_ecological_gate_manual_hmi")
                manual.diagnostics=(manual.diagnostics or {}) | {"manual_hmi_threshold":float(manual_hmi),"strict_hmi_threshold":float(self.config.reference.hmi_max_for_reference),"least_disturbed_quantile":float(self.config.reference.least_disturbed_quantile),"least_disturbed_hmi_threshold":qval,"strict_candidate_status":strict.status,"least_disturbed_candidate_status":least.status,"manual_threshold_requires_explicit_colab_configuration":True}
                if manual.approval: return manual
                return self.policy.terminal_status(manual,strict,least,manual)
            return self.policy.terminal_status(least,strict,least)
        except Exception as exc:
            return ReferencePopulation("auto_terrestrial","terrestrial","terrestrial_reference_policy","error:"+type(exc).__name__,reference_state="least_disturbed_contemporary",diagnostics={"error":str(exc),"exception_type":type(exc).__name__})

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
