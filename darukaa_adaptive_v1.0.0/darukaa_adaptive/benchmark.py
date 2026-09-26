"""Automatic reference selection and responsive, direction-aware benchmarking.

The normal workflow does not require a reference KML/CSV. The engine constructs a
least-modified reference population automatically from ecoregion + comparable habitat
or waterbody strata. A supplied reference can still be used later as an explicit override.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import exp, log
from typing import Dict, Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd

from .registry import get_indicator_spec
from .site import ee_geometry, make_shapely_domains


@dataclass
class BenchmarkResult:
    metric: str
    observed_value: Optional[float]
    reference_value: Optional[float]
    reference_level: str
    reference_source: str
    reference_n: Optional[int]
    reference_se: Optional[float]
    reference_p05: Optional[float]
    reference_p95: Optional[float]
    raw_relative_ratio: Optional[float]
    signed_benchmark: Optional[float]
    percentile_in_reference: Optional[float]
    intactness_ratio: Optional[float]
    intactness_score_0_100: Optional[float]
    comparison_method: str
    benchmark_status: str
    reference_approved_for_scoring: bool = False
    quality_flag: str = ""
    notes: str = ""

    def to_dict(self):
        return asdict(self)


def _finite(values: Sequence[float]) -> np.ndarray:
    return np.asarray([float(v) for v in values if v is not None and np.isfinite(float(v))], dtype=float)


def _robust_mad(values: Sequence[float]) -> float:
    arr = _finite(values)
    if arr.size == 0:
        return 0.0
    med = np.median(arr)
    return float(np.median(np.abs(arr - med)))


def _bootstrap_median_se(values: Sequence[float], n_boot: int = 500, seed: int = 0) -> Optional[float]:
    arr = _finite(values)
    if arr.size < 2:
        return None
    rng = np.random.default_rng(seed)
    samples = rng.choice(arr, size=(int(n_boot), arr.size), replace=True)
    medians = np.median(samples, axis=1)
    return float(np.std(medians, ddof=1))


def _logistic(x: float, scale: float) -> float:
    if scale <= 0:
        scale = np.log(2.0)
    z = np.clip(float(x) / scale, -40.0, 40.0)
    return 1.0 / (1.0 + exp(-z))


def reference_relative_intactness(observed: Optional[float], reference: Optional[float], direction: str) -> Optional[float]:
    """Backward-compatible directional ratio in 0-1.

    The ratio is retained as a transparent diagnostic. The actual responsive score used
    for aggregation is computed from the signed benchmark in ``benchmark_from_values``.
    """
    if observed is None or reference is None:
        return None
    observed = float(observed); reference = float(reference)
    if direction == "higher_is_better":
        return None if reference == 0 else max(0.0, min(1.0, observed / reference))
    if direction == "lower_is_better":
        if observed == 0:
            return 1.0 if reference >= 0 else None
        return max(0.0, min(1.0, reference / observed))
    if direction == "reference_target":
        if reference == 0:
            return 1.0 if observed == 0 else 0.0
        return max(0.0, min(1.0, 1.0 - abs(observed - reference) / abs(reference)))
    return None


def intactness_ratio(observed: float, reference: float, higher_is_better: bool) -> Optional[float]:
    return reference_relative_intactness(observed, reference, "higher_is_better" if higher_is_better else "lower_is_better")


def raw_relative_ratio(observed: Optional[float], reference: Optional[float], direction: str) -> Optional[float]:
    if observed is None or reference is None or reference == 0:
        return None
    if direction == "higher_is_better":
        return float(observed / reference)
    if direction == "lower_is_better":
        if observed == 0:
            return None
        return float(reference / observed)
    return float(observed / reference)


def _benchmark_scale(metric_name: str, reference_values: Sequence[float]) -> str:
    """Choose v0.2.7-style scale-aware estimator for native metrics.

    Ratio scale is appropriate for true-zero quantities such as cover fractions and counts;
    NDVI and dimensionless spectral/pressure indices use robust standardized deviation.
    """
    ratio_names = {
        "water_persistence", "natural_habitat_fraction", "habitat_connectivity_proxy",
        "built_up_fraction", "species_richness", "species_diversity", "edna_taxonomic_richness",
        "edna_cyanobacterial_fraction", "edna_human_associated_fraction", "edna_reducing_microbe_fraction",
    }
    return "ratio" if metric_name in ratio_names else "bounded"


def _signed_benchmark(observed: float, ref_values: Sequence[float], direction: str, scale_type: str) -> tuple[Optional[float], str, Optional[float], Optional[float]]:
    arr = _finite(ref_values)
    if arr.size == 0:
        return None, "none", None, None
    med = float(np.median(arr))
    if scale_type == "ratio":
        if observed <= 0 or med <= 0:
            return None, "log_response_ratio_undefined", med, None
        raw = log(observed / med)
        signed = raw if direction == "higher_is_better" else (-raw if direction == "lower_is_better" else None)
        return signed, "log_response_ratio", med, None
    mad = _robust_mad(arr)
    robust_sd = 1.4826 * mad
    if robust_sd <= 0:
        sd = float(np.std(arr, ddof=1)) if arr.size > 1 else 0.0
        robust_sd = sd
    if robust_sd <= 0:
        return None, "robust_z_undefined", med, None
    z = (float(observed) - med) / robust_sd
    signed = z if direction == "higher_is_better" else (-z if direction == "lower_is_better" else None)
    if direction == "reference_target":
        signed = -(abs(float(observed) - med) / robust_sd)
    return signed, "robust_z", med, robust_sd


def benchmark_from_values(metric_name: str, observed: Optional[float], reference_values: Sequence[float], config, reference_level: str, reference_source: str, notes: str = "") -> BenchmarkResult:
    spec = get_indicator_spec(metric_name)
    arr = _finite(reference_values)
    if not spec.reference_allowed:
        return BenchmarkResult(metric_name, observed, None, "none", reference_source, int(arr.size) if arr.size else None, None, None, None, None, None, None, None, None, None, "not_referenceable", "not_referenceable", False, "context_only", notes or "Indicator is contextual and is not referenceable.")
    if observed is None or arr.size == 0:
        return BenchmarkResult(metric_name, observed, None, "none", reference_source, int(arr.size) if arr.size else None, None, None, None, None, None, None, None, None, None, "reference_unavailable", "reference_unavailable", False, "missing_reference", notes or "No automatic reference values were available.")

    med = float(np.median(arr))
    se = _bootstrap_median_se(arr, n_boot=config.reference.bootstrap_iterations, seed=0)
    rel_se = None if se is None or med == 0 else abs(se / med)
    p05, p95 = float(np.percentile(arr, 5)), float(np.percentile(arr, 95))
    raw_ratio = raw_relative_ratio(observed, med, spec.direction)
    signed, estimator, _, scale = _signed_benchmark(float(observed), arr, spec.direction, _benchmark_scale(metric_name, arr))
    score = None if signed is None else _logistic(signed, config.scoring.logistic_ratio_scale) * 100.0
    percentile = None
    if arr.size:
        percentile = float(np.mean(arr <= float(observed)) * 100.0)
        if spec.direction == "lower_is_better":
            percentile = 100.0 - percentile

    approved = bool(
        config.reference.auto_approve and
        arr.size >= config.reference.minimum_reference_n and
        rel_se is not None and rel_se <= config.reference.maximum_reference_relative_se and
        signed is not None
    )
    qflag = "pass" if approved else (f"n={arr.size}" if arr.size < config.reference.minimum_reference_n else f"relative_se={rel_se:.3f}" if rel_se is not None else "estimator_undefined")
    status = "ok" if signed is not None else "reference_unusable"
    rel_se_text = "NA" if rel_se is None else f"{rel_se:.3f}"
    return BenchmarkResult(metric_name, float(observed), med, reference_level, reference_source, int(arr.size), se, p05, p95,
                           raw_ratio, signed, percentile, None if signed is None else score / 100.0, score,
                           estimator, status, approved, qflag,
                           notes + f" Reference median; n={arr.size}; bootstrap median SE={se:.6g} if defined; relative SE={rel_se_text}. Intactness uses a declared logistic transform centred at 50% at the reference condition; the raw signed benchmark remains in outputs.")


def benchmark_observation(record, config) -> BenchmarkResult:
    values = [record.reference_value] if record.reference_value is not None else []
    if record.reference_value is None:
        return BenchmarkResult(record.metric, record.raw_value, None, "none", "external", None, None, None, None, None, None, None, None, None,
                               "reference_unavailable", "reference_unavailable", False, "missing_reference", record.notes)
    spec_direction = record.direction
    # External references are often supplied as a single benchmark value. Use a stable
    # ratio for true-zero quantities and a direct reference-target distance for indices.
    if record.metric in {"species_richness", "species_diversity", "edna_taxonomic_richness"}:
        pseudo_scale = "ratio"
    else:
        pseudo_scale = "bounded"
    arr = _finite(values)
    obs = record.raw_value
    ref = float(arr[0])
    raw = raw_relative_ratio(obs, ref, spec_direction)
    if obs is None:
        signed = None
    elif pseudo_scale == "ratio" and obs > 0 and ref > 0:
        lr = log(obs / ref); signed = lr if spec_direction == "higher_is_better" else -lr
    else:
        # A single bounded reference is a point benchmark. Its oriented proportional
        # departure is centred at zero at the reference condition and then normalized
        # by the shared logistic transform. It is deliberately not treated as a raw
        # ecological threshold.
        if ref == 0:
            signed = None
        elif spec_direction == "higher_is_better":
            signed = (obs - ref) / abs(ref)
        elif spec_direction == "lower_is_better":
            signed = (ref - obs) / abs(ref)
        else:
            signed = -(abs(obs - ref) / abs(ref))
    score = None if signed is None else _logistic(float(signed), config.scoring.logistic_ratio_scale) * 100
    approved = bool(record.reference_approved and score is not None)
    return BenchmarkResult(record.metric, obs, ref, record.reference_level, "external", 1, record.uncertainty, None, None, raw, signed, None, None if score is None else score/100, score,
                           "external_reference", "ok" if score is not None else "reference_unusable", approved, "pass" if approved else "reference_not_approved", record.notes)


class ReferenceEngine:
    """Automatically construct comparable reference populations from GEE."""

    def __init__(self, config, metrics):
        self.config = config
        self.metrics = metrics
        self.diagnostics: Dict[str, object] = {}
        self._ecoregion = None
        self._candidate_features: List[dict] = []

    def characterize_site(self, master_geometry):
        import ee
        center = master_geometry.centroid(maxError=100)
        eco_fc = ee.FeatureCollection(self.config.reference.ecoregion_dataset)
        feature = eco_fc.filterBounds(center).first()
        info = feature.getInfo() or {}
        props = info.get("properties", {}) if info else {}
        self._ecoregion = props

        # Resolve the dominant non-water Dynamic World class in the assessment boundary.
        # This is a stratum descriptor for terrestrial reference selection; the raw site
        # water extent is never used as a terrestrial land-cover class.
        dominant_class = None
        dominant_label = None
        try:
            dw = (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
                  .filterBounds(master_geometry)
                  .filterDate(*self.config.temporal.baseline_dates())
                  .select("label"))
            mode = dw.mode()
            class_hist = mode.reduceRegion(
                reducer=ee.Reducer.frequencyHistogram(),
                geometry=master_geometry,
                scale=10,
                maxPixels=1e8,
                bestEffort=True,
            ).get("label")
            hist = class_hist.getInfo() if class_hist is not None else {}
            if hist:
                water_labels = {0, 9, 8}  # water, mangroves, snow/ice are not terrestrial reference strata here
                items = [(int(k), float(v)) for k, v in hist.items() if int(k) not in water_labels]
                if items:
                    dominant_class = max(items, key=lambda x: x[1])[0]
                    labels = {1:"trees",2:"grass",3:"flooded_vegetation",4:"crops",5:"shrub_scrub",6:"built",7:"bare"}
                    dominant_label = labels.get(dominant_class, str(dominant_class))
        except Exception:
            pass

        self.diagnostics["site_ecoregion"] = {
            "eco_id": props.get("ECO_ID"), "eco_name": props.get("ECO_NAME"),
            "biome_name": props.get("BIOME_NAME"), "realm": props.get("REALM"),
            "dominant_terrestrial_landcover_class": dominant_class,
            "dominant_terrestrial_landcover_label": dominant_label,
        }
        return self._ecoregion

    def _candidate_lakes(self, master_geometry):
        import ee
        if not self.config.reference.use_hydrolakes_for_aquatic:
            return [], "hydrolakes_disabled"
        if not self._ecoregion:
            self.characterize_site(master_geometry)
        eco_id = self._ecoregion.get("ECO_ID")
        if eco_id is None:
            return [], "ecoregion_unresolved"
        from .site import area_ha
        site_area_km2 = area_ha(master_geometry) / 100.0
        eco = ee.FeatureCollection(self.config.reference.ecoregion_dataset).filter(ee.Filter.eq("ECO_ID", eco_id)).geometry()
        fc = (ee.FeatureCollection(self.config.reference.hydrolakes_asset)
              .filter(ee.Filter.notNull(["Hylak_id", "Lake_area"]))
              .filterBounds(eco)
              .sort("Lake_area")
              .limit(max(100, self.config.reference.aquatic_max_candidates * 12)))
        feats = fc.getInfo().get("features", [])
        try:
            from shapely.geometry import shape
            site_shape = shape(master_geometry.getInfo())
            filtered=[]
            for f in feats:
                prop=f.get("properties", {})
                a=float(prop.get("Lake_area", 0) or 0)
                if a <= 0 or not (site_area_km2 * self.config.reference.aquatic_area_ratio_min <= a <= site_area_km2 * self.config.reference.aquatic_area_ratio_max):
                    continue
                try:
                    g=shape(f["geometry"]); dist_m=site_shape.centroid.distance(g.centroid)*111320.0
                except Exception:
                    dist_m=1e9
                if dist_m < self.config.spatial.reference_exclusion_buffer_m:
                    continue
                f["_distance_m"] = dist_m
                filtered.append(f)
            filtered.sort(key=lambda x: abs(np.log(max(float(x["properties"].get("Lake_area",1e-9)),1e-9)/site_area_km2)))
            feats=filtered
        except Exception:
            feats=feats

        # Apply the least-modified reference screen at lake level using the HMI mean of
        # each candidate polygon. This is a reference-selection filter, not a score.
        hmi=ee.Image(self.config.reference.human_modification_dataset)
        hmi_results=[]
        if feats:
            candidate_list = feats[:max(30,self.config.reference.aquatic_max_candidates*2)]
            score_features=[]
            for f in candidate_list:
                geom = ee.Feature(f).geometry()
                # HMI describes terrestrial human modification, so score a near-shore
                # land context rather than the water-body interior.
                ring = geom.buffer(self.config.spatial.riparian_buffer_m, maxError=100).difference(geom, maxError=100)
                score_features.append(ee.Feature(ring).copyProperties(ee.Feature(f)))
            cfc=ee.FeatureCollection(score_features)
            reduced=hmi.reduceRegions(collection=cfc, reducer=ee.Reducer.mean(), scale=100)
            hmi_results=reduced.getInfo().get("features", [])
        kept=[]
        for f in hmi_results:
            hm=f.get("properties",{}).get("mean")
            if hm is None or float(hm) <= self.config.reference.human_modification_threshold:
                kept.append(f)
        self._candidate_features=kept[:self.config.reference.aquatic_max_candidates]
        self.diagnostics["aquatic_reference_candidates"]=[
            {"hylak_id": f.get("properties",{}).get("Hylak_id"), "area_km2": f.get("properties",{}).get("Lake_area"), "hmi_mean": f.get("properties",{}).get("mean")}
            for f in self._candidate_features
        ]
        return self._candidate_features, "ok" if self._candidate_features else "no_eligible_aquatic_candidates"

    def _candidate_geometry(self, feature_dict):
        import ee
        return ee.Feature(feature_dict).geometry()

    def _aquatic_values(self, metric_name, candidates, start, end):
        values = []
        for f in candidates:
            geom = self._candidate_geometry(f)
            try:
                if metric_name == "water_persistence":
                    v = self.metrics.water.persistence(geom, start, end)["water_occurrence_fraction"]
                elif metric_name == "ndci_proxy":
                    v = self.metrics.ndci(geom, start, end).value
                elif metric_name == "red_reflectance_turbidity_proxy":
                    v = self.metrics.turbidity_proxy(geom, start, end).value
                elif metric_name == "surface_algal_bloom_frequency":
                    v = self.metrics.bloom_frequency(geom, start, end).value
                elif metric_name == "riparian_ndvi":
                    from shapely.geometry import shape
                    candidate_shape = shape(self._candidate_geometry(f).getInfo())
                    r = make_shapely_domains(candidate_shape, self.config.spatial.riparian_buffer_m, self.config.spatial.context_buffer_km)
                    v = self.metrics.riparian_ndvi(ee_geometry(r["riparian_fixed"]), start, end).value
                elif metric_name == "shoreline_disturbance_fraction":
                    from shapely.geometry import shape
                    candidate_shape = shape(self._candidate_geometry(f).getInfo())
                    r = make_shapely_domains(candidate_shape, self.config.spatial.riparian_buffer_m, self.config.spatial.context_buffer_km)
                    v = self.metrics.shoreline_disturbance(ee_geometry(r["riparian_fixed"]), start, end).value
                else:
                    continue
                if v is not None and np.isfinite(float(v)):
                    values.append(float(v))
            except Exception:
                continue
        return values

    def _terrestrial_values(self, metric_name, master_geometry, start, end):
        import ee
        eco_id = (self._ecoregion or {}).get("ECO_ID")
        if eco_id is None:
            self.characterize_site(master_geometry); eco_id = self._ecoregion.get("ECO_ID")
        if eco_id is None:
            return []
        eco = ee.FeatureCollection(self.config.reference.ecoregion_dataset).filter(ee.Filter.eq("ECO_ID", eco_id)).geometry()
        exclude = master_geometry.buffer(self.config.spatial.reference_exclusion_buffer_m, maxError=100)
        region = eco.difference(exclude, maxError=100)
        hmi = ee.Image(self.config.reference.human_modification_dataset)
        hmi_mask = hmi.lte(self.config.reference.human_modification_threshold)
        if metric_name in {"natural_habitat_fraction", "built_up_fraction", "habitat_connectivity_proxy"}:
            dw = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(region).filterDate(start, end).select("label").mode()
            natural = dw.eq(1).Or(dw.eq(2)).Or(dw.eq(3)).Or(dw.eq(5))
            land = dw.neq(0)
            if metric_name == "natural_habitat_fraction":
                image = natural.updateMask(land).updateMask(hmi_mask).rename("value")
            elif metric_name == "built_up_fraction":
                image = dw.eq(6).updateMask(land).updateMask(hmi_mask).rename("value")
            else:
                image = natural.focal_mean(100, "circle", "meters").updateMask(land).updateMask(hmi_mask).rename("value")
                dominant = (self.diagnostics.get("site_ecoregion", {}) or {}).get("dominant_terrestrial_landcover_class")
                # Match the site's dominant terrestrial land-cover stratum where doing so
                # is meaningful for a local condition metric. This is not applied to the
                # natural-habitat/built-fraction pressure/extent metrics themselves.
                if metric_name == "habitat_connectivity_proxy" and dominant is not None and dominant not in {0, 8, 9}:
                    image = image.updateMask(dw.eq(int(dominant)))
        elif metric_name == "vegetation_ndvi":
            col = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(region).filterDate(start, end).filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", self.config.temporal.max_cloud_pct))
            def mask(img):
                img = ee.Image(img); scl = img.select("SCL")
                good = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))
                return img.updateMask(good).divide(10000)
            ndvi = col.map(mask).map(lambda img: ee.Image(img).normalizedDifference(["B8", "B4"]).rename("NDVI")).median()
            dw = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(region).filterDate(start, end).select("label").mode()
            natural = dw.eq(1).Or(dw.eq(2)).Or(dw.eq(3)).Or(dw.eq(5))
            image = ndvi.updateMask(natural).updateMask(hmi_mask).rename("value")
        elif metric_name == "human_modification":
            image = hmi.updateMask(hmi_mask).rename("value")
        else:
            return []
        fc = image.sample(region=region, scale=10 if metric_name != "human_modification" else 100, numPixels=5000, seed=123, geometries=False)
        return [float(v) for v in (fc.aggregate_array("value").getInfo() or []) if v is not None]

    def reference_values(self, metric_name, master_geometry, start, end):
        spec = get_indicator_spec(metric_name)
        if spec.reference_type == "automatic_aquatic_reference":
            candidates, status = self._candidate_lakes(master_geometry)
            if status != "ok":
                return [], "automatic_aquatic_reference", status
            vals = self._aquatic_values(metric_name, candidates, start, end)
            return vals, "automatic_aquatic_reference", f"{status}; n_candidate_values={len(vals)}"
        if spec.reference_type == "automatic_terrestrial_reference":
            vals = self._terrestrial_values(metric_name, master_geometry, start, end)
            return vals, "automatic_terrestrial_reference", f"ecoregion={self.diagnostics.get('site_ecoregion', {})}; n_pixels={len(vals)}"
        return [], spec.reference_type, "external reference required"

    def build(self, metric_results, master_geometry, baseline_start=None, baseline_end=None, external_records=None):
        if baseline_start is None or baseline_end is None:
            baseline_start, baseline_end = self.config.temporal.baseline_dates()
        external_records = external_records or []
        external = {r.metric: r for r in external_records}
        results = []
        for m in metric_results:
            spec = get_indicator_spec(m.metric)
            if not self.config.reference.enabled or not spec.reference_allowed:
                results.append(benchmark_from_values(m.metric, m.value, [], self.config, "none", "none", "Contextual/not referenceable.")); continue
            if spec.reference_type == "external_reference":
                r = external.get(m.metric)
                if r is None:
                    results.append(benchmark_from_values(m.metric, m.value, [], self.config, "external", "external", "External reference value not supplied."))
                else:
                    results.append(benchmark_observation(r, self.config))
                continue
            vals, level, source_note = self.reference_values(m.metric, master_geometry, baseline_start, baseline_end)
            results.append(benchmark_from_values(m.metric, m.value, vals, self.config, level, level, source_note))
        self.diagnostics["reference_strategy"] = {
            "name": self.config.reference.strategy,
            "automated": True,
            "manual_reference_inputs_required": False,
            "terrestrial": "ecoregion + least-modified HMI + contextual land-cover stratification where applicable",
            "aquatic": "ecoregion + comparable HydroLAKES waterbodies + area similarity + near-shore HMI screen",
            "reference_uncertainty": "bootstrap median standard error",
        }
        return results


def benchmark_dataframe(results: Iterable[BenchmarkResult]) -> pd.DataFrame:
    return pd.DataFrame([r.to_dict() for r in results])
