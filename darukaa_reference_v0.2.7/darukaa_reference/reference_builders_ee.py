"""
reference_builders_ee.py -- Earth Engine reference builders (v0.2.8 Phase 3)
===========================================================================

Mirrors reference_builders.py (the executable numpy definition) on Earth Engine.

STATUS: structure-tested offline (fake ee objects). NOT yet run against live Earth Engine;
that is the Phase 5 / Phase 6 acceptance test. Unverified EE assumptions (also listed in
SCORING_ARCHITECTURE_v0.2.8.md): A1 reproject-to-native focal sums, A2 point-sampling of a
reprojected window image, and the cost of vectorising water bodies over 10-50 km zones.

Design rule: every DECISION (which bodies are comparable, which are rejected, what is
reported) is made by pure-Python functions that the numpy definition also uses, so the same
rule is tested offline and executed live.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from darukaa_reference import constructs as K
from darukaa_reference import indicator_contract as IC
from darukaa_reference import support as S
from darukaa_reference.benchmarking import MetricSpec, ReferenceData


# ----------------------------------------------------------------------------------------
# Pure-Python decision logic (shared, tested)
# ----------------------------------------------------------------------------------------
def select_reference_records(records: Sequence[Dict], target_uid, *, area_ratio=IC.WATER_BODY_AREA_RATIO,
                             permanence_tol=IC.WATER_BODY_PERMANENCE_TOL, min_pure_px=IC.MIN_PURE_WATER_PIXELS,
                             use_permanence=True) -> Tuple[List[Dict], Dict]:
    """Comparable water bodies (E2). Each record: {uid, area_m2, pure_px, value, permanence}.

    A reference body must (a) have >= min_pure_px pure-water pixels and a finite metric value,
    (b) have area within [target/ratio, target*ratio], (c) if use_permanence, be within
    +/- permanence_tol of the target's permanence, (d) not be the target."""
    by_uid = {r["uid"]: r for r in records}
    tgt = by_uid[target_uid]
    ok = [r for r in records if r["pure_px"] >= min_pure_px and r.get("value") is not None
          and np.isfinite(r["value"])]
    lo, hi = tgt["area_m2"] / area_ratio, tgt["area_m2"] * area_ratio
    by_size = [r for r in ok if r["uid"] != target_uid and lo <= r["area_m2"] <= hi]
    if use_permanence and tgt.get("permanence") is not None:
        final = [r for r in by_size if r.get("permanence") is not None
                 and abs(r["permanence"] - tgt["permanence"]) <= permanence_tol]
    else:
        final = by_size
    funnel = {"n_water_bodies_total": len(records), "n_bodies_with_enough_pixels": len(ok),
              "n_rejected_size": len(ok) - (1 if any(r["uid"] == target_uid for r in ok) else 0) - len(by_size),
              "n_rejected_permanence": len(by_size) - len(final), "n_reference_bodies": len(final)}
    return final, funnel


def reference_from_records(final: Sequence[Dict], target: Dict, funnel: Dict, *, kind: str, construct: str,
                           unit: str, temporal: str, population: str, tier: str, native_scale_m: float,
                           area_ratio: float, permanence_tol: float, min_pure_px: int, use_permanence: bool,
                           radius_km: Optional[float], ring_width_m: Optional[float]) -> ReferenceData:
    vals = np.array([r["value"] for r in final], dtype=float)
    what = "water bodies" if kind == "water" else "riparian rings of water bodies"
    pdef = (f"comparable {what} within {radius_km:g} km of the site: area within [1/{area_ratio:g}, {area_ratio:g}] x "
            f"target ({target['area_m2']:.0f} m2)"
            + (f", |permanence difference| <= {permanence_tol:g}" if use_permanence else "")
            + f", >= {min_pure_px} pure-water px each; {len(final)} of {funnel['n_water_bodies_total'] - 1} other bodies"
            if radius_km is not None else "comparable water bodies")
    support = "water_body_unit" if kind == "water" else "riparian_ring_unit"
    return ReferenceData(vals, MetricSpec(construct, unit, temporal, support, population, native_scale_m=native_scale_m),
                         tier, pdef, {"reference_body_uids": [r["uid"] for r in final], "funnel": dict(funnel),
                                      "radius_used_km": radius_km, "ring_width_m": ring_width_m,
                                      "erode_px": K.PURE_WATER_ERODE_PX})


# ----------------------------------------------------------------------------------------
# Earth Engine pieces
# ----------------------------------------------------------------------------------------
def water_mask_s2(composite):
    """ONE shared water definition for every v0.2.8 aquatic construct: MNDWI (B3, B11) > 0."""
    return composite.normalizedDifference(["B3", "B11"]).gt(0)


def pure_water_mask(water_mask, erode_px: int = K.PURE_WATER_ERODE_PX):
    """Erode the water mask so mixed shoreline pixels are excluded."""
    return water_mask.focal_min(radius=erode_px, kernelType="square", units="pixels")


def _add_uid(ee, fc):
    return fc.map(lambda f: f.set("uid", ee.String(f.geometry().centroid(1).coordinates().join(","))))


def unit_records_ee(ee, *, region, water_mask, metric_image, kind: str, native_scale_m: float,
                    permanence_image=None, ring_width_m: float = K.RIPARIAN_RING_WIDTH_M,
                    min_area_m2: float = 0.0, tile_scale: int = 4) -> List[Dict]:
    """One record per water body in `region`: uid, area_m2, pure_px, value, permanence.

    kind='water': value = mean of `metric_image` over the body's PURE-water pixels.
    kind='ring' : value = mean over the land ring of width ring_width_m (ALL water excluded)."""
    pure = pure_water_mask(water_mask)
    units = _add_uid(ee, S.ee_water_body_units(ee, water_mask, region, native_scale_m, min_area_m2))
    v = metric_image.select(0).rename("v")
    if kind == "water":
        val_fc = units
        v = v.updateMask(pure)
    else:
        val_fc = units.map(lambda f: S.ee_ring(ee, f, ring_width_m))
        v = v.updateMask(water_mask.Not())
    perm = (permanence_image.select(0).rename("perm") if permanence_image is not None
            else ee.Image.constant(0).rename("perm"))
    vals = v.addBands(perm).reduceRegions(collection=val_fc, reducer=ee.Reducer.mean(),
                                          scale=native_scale_m, tileScale=tile_scale)
    pure_px = pure.rename("p").reduceRegions(collection=units, reducer=ee.Reducer.sum(),
                                             scale=native_scale_m, tileScale=tile_scale)
    vf = {f["properties"]["uid"]: f["properties"] for f in vals.getInfo()["features"]}
    pf = {f["properties"]["uid"]: f["properties"] for f in pure_px.getInfo()["features"]}
    out = []
    for uid, p in pf.items():
        q = vf.get(uid, {})
        out.append({"uid": uid, "area_m2": p.get("area_m2"), "pure_px": int(p.get("sum") or 0),
                    "value": q.get("v"), "permanence": (q.get("perm") if permanence_image is not None else None)})
    return out


def water_body_reference_ee(ee, *, site_geometry, water_mask, metric_image, kind: str, native_scale_m: float,
                            construct: str, unit: str, temporal: str, population: str, tier: str = "tier2",
                            radii_km: Sequence[float] = (10.0, 25.0, 50.0), min_reference_n: int = IC.MIN_COMPARABLE_WATER_BODIES,
                            permanence_image=None, ring_width_m: float = K.RIPARIAN_RING_WIDTH_M,
                            min_pure_px: int = IC.MIN_PURE_WATER_PIXELS, area_ratio: float = IC.WATER_BODY_AREA_RATIO,
                            permanence_tol: float = IC.WATER_BODY_PERMANENCE_TOL, want_reference: bool = True) -> Dict:
    """Target water body + comparable-water-body reference, widening the radius until the
    documented minimum number of comparable bodies is reached (never fabricating one).

    Returns dict(valid, invalid_reason, target, site_spec, reference (ReferenceData|None), radius_used_km)."""
    centre = site_geometry.centroid(1)
    result: Dict = {"valid": False, "invalid_reason": "no_water_body_in_site", "target": None,
                    "site_spec": None, "reference": None, "radius_used_km": None}
    support = "water_body_unit" if kind == "water" else "riparian_ring_unit"
    site_spec = MetricSpec(construct, unit, temporal, support, "site", native_scale_m=native_scale_m)
    use_perm = permanence_image is not None
    last = None
    for r_km in radii_km:
        zone = centre.buffer(r_km * 1000.0)
        recs = unit_records_ee(ee, region=zone, water_mask=water_mask, metric_image=metric_image, kind=kind,
                               native_scale_m=native_scale_m, permanence_image=permanence_image,
                               ring_width_m=ring_width_m)
        hits = _bodies_touching_site(ee, zone, site_geometry, water_mask, native_scale_m)
        target = next((r for r in recs if r["uid"] in hits), None)
        if target is None:
            continue
        if target["pure_px"] < min_pure_px:
            return {**result, "invalid_reason": "insufficient_pure_water", "target": target, "site_spec": site_spec,
                    "n_pure_water_px": target["pure_px"]}
        if target.get("value") is None:
            return {**result, "invalid_reason": "no_valid_metric_pixels", "target": target, "site_spec": site_spec}
        result.update(valid=True, invalid_reason="", target=target, site_spec=site_spec,
                      n_pure_water_px=target["pure_px"], radius_used_km=r_km)
        if not want_reference:
            return result
        final, funnel = select_reference_records(recs, target["uid"], area_ratio=area_ratio,
                                                 permanence_tol=permanence_tol, min_pure_px=min_pure_px,
                                                 use_permanence=use_perm)
        last = (final, funnel, target, r_km)
        if len(final) >= min_reference_n:
            break
    if last is not None:
        final, funnel, target, r_km = last
        result["reference"] = reference_from_records(
            final, target, funnel, kind=kind, construct=construct, unit=unit, temporal=temporal,
            population=population, tier=tier, native_scale_m=native_scale_m, area_ratio=area_ratio,
            permanence_tol=permanence_tol, min_pure_px=min_pure_px, use_permanence=use_perm,
            radius_km=r_km, ring_width_m=ring_width_m if kind == "ring" else None)
        result["radius_used_km"] = r_km
    return result


def _bodies_touching_site(ee, zone, site_geometry, water_mask, native_scale_m) -> set:
    """uids of the water bodies (vectorised in `zone`) that intersect the site."""
    units = _add_uid(ee, S.ee_water_body_units(ee, water_mask, zone, native_scale_m, 0.0))
    hits = units.filterBounds(site_geometry)
    return {f["properties"]["uid"] for f in hits.getInfo()["features"]}


# ---------------------------------------------------------------- window references
def window_reference_ee(ee, *, window_image, region, native_scale_m: float, site_area_m2: float, n: int, seed: int,
                        support: str, construct: str, unit: str, temporal: str, population: str, tier: str,
                        population_definition: str, tile_scale: int = 4, extra: Optional[Dict] = None) -> ReferenceData:
    """Sample non-overlapping site-sized windows of an already-built window image."""
    vals = S.ee_sample_windows(ee, window_image, region, native_scale_m, site_area_m2, n, seed, tile_scale).getInfo()
    vals = np.array([v for v in (vals or []) if v is not None], dtype=float)
    spec = MetricSpec(construct, unit, temporal, support, population,
                      window_area_m2=float(site_area_m2), native_scale_m=native_scale_m)
    diag = {"window_radius_m": S.site_window_radius_m(site_area_m2),
            "sampling_spacing_m": S.sampling_spacing_m(native_scale_m, site_area_m2),
            "sample_requested": n, "seed": seed, "sampling": "stratifiedSample on validity band, numPoints=0"}
    diag.update(extra or {})
    return ReferenceData(vals, spec, tier, population_definition, diag)
