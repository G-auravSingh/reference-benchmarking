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

import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from darukaa_reference import constructs as K
from darukaa_reference import indicator_contract as IC
from darukaa_reference import support as S
from darukaa_reference.benchmarking import MetricSpec, ReferenceData


# ----------------------------------------------------------------------------------------
# Pure-Python decision logic (shared, tested)
# ----------------------------------------------------------------------------------------
def body_extent_m(r: Dict) -> float:
    """Bounding-box extent (the larger side) of a water body record."""
    b = r["bbox"]
    return max(b[2] - b[0], b[3] - b[1])


def select_reference_records(records: Sequence[Dict], target_uid, *, area_ratio=IC.WATER_BODY_AREA_RATIO,
                             permanence_tol=IC.WATER_BODY_PERMANENCE_TOL, min_pure_px=IC.MIN_PURE_WATER_PIXELS,
                             use_permanence=True, max_extent_m: Optional[float] = None) -> Tuple[List[Dict], Dict]:
    """Comparable water bodies (E2). Each record: {uid, area_m2, pure_px, value, permanence}.

    A reference body must (a) have >= min_pure_px pure-water pixels and a finite metric value,
    (b) have area within [target/ratio, target*ratio], (c) if use_permanence, be within
    +/- permanence_tol of the target's permanence, (d) not be the target."""
    by_uid = {r["uid"]: r for r in records}
    tgt = by_uid[target_uid]
    ok = [r for r in records if r["pure_px"] >= min_pure_px and r.get("value") is not None
          and np.isfinite(r["value"])]
    n_ext = 0
    if max_extent_m is not None:                                       # explicit population rule (see constructs.MAX_WATER_BODY_EXTENT_M)
        keep = [r for r in ok if r["uid"] == target_uid or body_extent_m(r) <= max_extent_m]
        n_ext, ok = len(ok) - len(keep), keep
    lo, hi = tgt["area_m2"] / area_ratio, tgt["area_m2"] * area_ratio
    by_size = [r for r in ok if r["uid"] != target_uid and lo <= r["area_m2"] <= hi]
    if use_permanence and tgt.get("permanence") is not None:
        final = [r for r in by_size if r.get("permanence") is not None
                 and abs(r["permanence"] - tgt["permanence"]) <= permanence_tol]
    else:
        final = by_size
    funnel = {"n_water_bodies_total": len(records), "n_bodies_with_enough_pixels": len(ok) + n_ext, "n_rejected_extent": n_ext,
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


def rect_geometry(ee, bounds, crs: str):
    x0, y0, x1, y1 = bounds
    return ee.Geometry.Rectangle([x0, y0, x1, y1], proj=crs, geodesic=False)


def _unit_geometry_properties(ee, site_geometry=None):
    """Server-side: lon/lat centroid and bounding box of each unit, a PRECISE uid, and whether it touches the site.
    Earth Engine's coordinates() are ALWAYS lon/lat (the live run returned degrees even after transform(UTM)), so they are
    requested explicitly in EPSG:4326 and converted to the UTM grid CLIENT-side (see _to_xy). uid = lon/lat to 1e-7 deg (~1 cm)."""
    def add(f):
        g = f.geometry().transform("EPSG:4326", 1)
        ring = ee.List(g.bounds(1).coordinates().get(0))                 # min / max over the ring: no assumption about vertex order
        xs, ys = ring.map(lambda p: ee.List(p).get(0)), ring.map(lambda p: ee.List(p).get(1))
        c = ee.List(g.centroid(1).coordinates())
        lon, lat = ee.Number(c.get(0)), ee.Number(c.get(1))
        f = f.set({"clon": lon, "clat": lat, "lon0": ee.List(xs).reduce(ee.Reducer.min()), "lat0": ee.List(ys).reduce(ee.Reducer.min()),
                   "lon1": ee.List(xs).reduce(ee.Reducer.max()), "lat1": ee.List(ys).reduce(ee.Reducer.max()),
                   "geodesic_area_m2": f.geometry().area(1),
                   "uid": ee.String(lon.format("%.7f")).cat(",").cat(lat.format("%.7f"))})
        if site_geometry is not None:
            f = f.set("touches_site", f.geometry().intersects(site_geometry, 1))
        return f
    return add


def _xy_transformer(crs: str):
    import pyproj
    return pyproj.Transformer.from_crs("EPSG:4326", crs, always_xy=True)


def _to_xy(tr, p: Dict) -> Tuple[float, float, Tuple[float, float, float, float]]:
    """lon/lat centroid + bbox (from Earth Engine) -> UTM centroid + bbox (bbox of the four transformed corners; the grid convergence
    makes this larger than the true pixel bbox by a few metres at most, far below the interior margin)."""
    cx, cy = tr.transform(p["clon"], p["clat"])
    pts = [tr.transform(lo, la) for lo in (p["lon0"], p["lon1"]) for la in (p["lat0"], p["lat1"])]
    xs, ys = [q[0] for q in pts], [q[1] for q in pts]
    return cx, cy, (min(xs), min(ys), max(xs), max(ys))


def unit_records_ee(ee, *, region, region_bounds, water_mask, metric_image, kind: str, native_scale_m: float,
                    permanence_image=None, ring_width_m: float = K.RIPARIAN_RING_WIDTH_M, min_area_m2: float = 0.0,
                    tile_scale: int = 4, crs: str, site_geometry=None) -> List[Dict]:
    """One record per water body in `region`, on the native UTM grid (the SAME grid the numpy definition uses).

    Area is n_px * native^2 (a pixel COUNT, as in the numpy definition), not the geodesic polygon area, which is
    0.35 % larger at the live site. `interior` says whether the body lies clear of the region edge (bounding box
    inside the region shrunk by the erosion / ring margin): a body at the edge is clipped by the region, so its area,
    erosion and ring are wrong and it must not be used. kind='water': value = mean over the body's PURE-water pixels.
    kind='ring': value = mean over the land ring (all water excluded)."""
    from darukaa_reference import tiling as T
    proj = S.ee_native_projection(ee, native_scale_m, crs)
    pure = pure_water_mask(water_mask)
    loose = 0.9 * float(min_area_m2)                                    # geodesic pre-filter; the exact filter is below
    units = S.ee_water_body_units(ee, water_mask, region, native_scale_m, loose, crs=crs)
    units = units.map(_unit_geometry_properties(ee, site_geometry))
    v = metric_image.select(0).rename("v")
    if kind == "water":
        val_fc, v = units, v.updateMask(pure)
        margin = (K.PURE_WATER_ERODE_PX + 1) * native_scale_m
    else:
        val_fc, v = units.map(lambda f: S.ee_ring(ee, f, ring_width_m)), v.updateMask(water_mask.Not())
        margin = ring_width_m + 2 * native_scale_m
    perm = (permanence_image.select(0).rename("perm") if permanence_image is not None
            else ee.Image.constant(0).rename("perm"))
    extra = {"crs": proj}
    counts = ee.Image.cat([water_mask.rename("n"), pure.rename("p")]).reduceRegions(
        collection=units, reducer=ee.Reducer.sum(), scale=native_scale_m, tileScale=tile_scale, **extra)
    vals = v.addBands(perm).reduceRegions(collection=val_fc, reducer=ee.Reducer.mean(), scale=native_scale_m,
                                          tileScale=tile_scale, **extra)
    vf = {f["properties"]["uid"]: f["properties"] for f in vals.getInfo()["features"]}
    tr = _xy_transformer(crs)
    out = []
    for f in counts.getInfo()["features"]:
        p = f["properties"]
        n_px = int(round(p.get("n") or 0))
        if n_px * native_scale_m ** 2 < min_area_m2:
            continue
        q = vf.get(p["uid"], {})
        cx, cy, bbox = _to_xy(tr, p)
        out.append({"uid": p["uid"], "cx": cx, "cy": cy, "bbox": bbox, "n_px": n_px,
                    "area_m2": n_px * native_scale_m ** 2, "geodesic_area_m2": p.get("geodesic_area_m2"),
                    "pure_px": int(round(p.get("p") or 0)), "value": q.get("v"),
                    "permanence": (q.get("perm") if permanence_image is not None else None),
                    "interior": T.is_interior(bbox, region_bounds, margin), "touches_site": bool(p.get("touches_site", False))})
    return out


def _dist(a, b) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def water_body_reference_ee(ee, *, site_geometry, site_bounds_utm, centre_xy, water_mask, metric_image, kind: str,
                            native_scale_m: float, construct: str, unit: str, temporal: str, population: str,
                            tier: str = "tier2", radii_km: Sequence[float] = (10.0, 25.0, 50.0),
                            min_reference_n: int = IC.MIN_COMPARABLE_WATER_BODIES, permanence_image=None,
                            ring_width_m: float = K.RIPARIAN_RING_WIDTH_M, min_pure_px: int = IC.MIN_PURE_WATER_PIXELS,
                            area_ratio: float = IC.WATER_BODY_AREA_RATIO, permanence_tol: float = IC.WATER_BODY_PERMANENCE_TOL,
                            want_reference: bool = True, crs: str, tile_core_m: float = 10000.0,
                            max_extent_m: float = K.MAX_WATER_BODY_EXTENT_M, margin_m: Optional[float] = None,
                            probe_margin_m: float = 500.0, max_probe_margin_m: float = 8000.0, log=None) -> Dict:
    """Target water body + comparable-water-body reference, with every Earth Engine request bounded in size.

    1. TARGET: vectorise a small region around the site (site bbox + margin), doubling the margin until the target is
       INTERIOR (not clipped by the region edge).
    2. REFERENCES (want_reference): tile the reference circle into cores of `tile_core_m`, vectorise each core plus a
       `margin_m` border, keep bodies that (a) are interior to that region and (b) have their centroid in the core
       (each body belongs to exactly one tile), splitting a tile in four on a memory error. The radius ladder widens
       incrementally, re-using tiles, until the documented minimum number of comparable bodies is reached (never
       fabricating one).
    Population = bodies with centroid within the radius, interior, >= min_pure_px pure-water px, area within
    [1/ratio, ratio] x target and |permanence difference| <= tolerance."""
    from darukaa_reference import tiling as T
    log = log or (lambda *a, **k: None)
    interior_margin = (K.PURE_WATER_ERODE_PX + 1) * native_scale_m if kind == "water" else ring_width_m + 2 * native_scale_m
    # A body owned by a tile (centroid in its core) with extent <= max_extent lies wholly within core + max_extent, so a region
    # margin of max_extent + interior margin + 1 px guarantees it is interior: tiling can never drop an eligible body.
    margin_m = margin_m if margin_m is not None else max_extent_m + interior_margin + native_scale_m
    support = "water_body_unit" if kind == "water" else "riparian_ring_unit"
    site_spec = MetricSpec(construct, unit, temporal, support, "site", native_scale_m=native_scale_m)
    use_perm = permanence_image is not None
    out: Dict = {"valid": False, "invalid_reason": "no_water_body_in_site", "target": None, "site_spec": site_spec,
                 "reference": None, "radius_used_km": None, "diagnostics": {"probe": []}}
    common = dict(water_mask=water_mask, metric_image=metric_image, kind=kind, native_scale_m=native_scale_m,
                  permanence_image=permanence_image, ring_width_m=ring_width_m, crs=crs)
    snap = lambda v, up=False: (math.ceil(v / native_scale_m) if up else math.floor(v / native_scale_m)) * native_scale_m

    # ---------------- 1. target
    m, target = probe_margin_m, None
    sx0, sy0, sx1, sy1 = site_bounds_utm
    while True:
        b = (snap(sx0 - m), snap(sy0 - m), snap(sx1 + m, True), snap(sy1 + m, True))
        recs = unit_records_ee(ee, region=rect_geometry(ee, b, crs), region_bounds=b, site_geometry=site_geometry,
                               min_area_m2=0.0, **common)
        touching = [r for r in recs if r["touches_site"]]
        out["diagnostics"]["probe"].append({"margin_m": m, "n_bodies_in_region": len(recs), "n_touching_site": len(touching),
                                            "touching": [{k: r[k] for k in ("uid", "n_px", "pure_px", "interior", "bbox")} for r in touching]})
        if not touching:
            out["invalid_reason"] = "no_water_body_in_site"
            return out
        inner = [r for r in touching if r["interior"]]
        if inner:
            target = max(inner, key=lambda r: r["n_px"])
            break
        if m >= max_probe_margin_m:
            out["invalid_reason"] = "target_truncated_at_region_edge"
            return out
        m *= 2.0
    out["target"] = target
    out["n_pure_water_px"] = target["pure_px"]
    out["diagnostics"]["max_extent_m"], out["diagnostics"]["tile_margin_m"] = max_extent_m, margin_m
    if body_extent_m(target) > max_extent_m:
        out["invalid_reason"] = "target_exceeds_max_extent"
        return out
    if target["pure_px"] < min_pure_px:
        out["invalid_reason"] = "insufficient_pure_water"
        return out
    if target.get("value") is None:
        out["invalid_reason"] = "no_valid_metric_pixels"
        return out
    out.update(valid=True, invalid_reason="")
    if not want_reference:
        return out

    # ---------------- 2. references
    cx, cy = centre_xy
    cache: Dict[Tuple, Tuple[List[Dict], int]] = {}
    stats: Dict = {"splits": 0}
    ntiles = 0

    def tile_records(core):
        nonlocal ntiles
        ntiles += 1
        rb = (core[0] - margin_m, core[1] - margin_m, core[2] + margin_m, core[3] + margin_m)
        try:
            recs = unit_records_ee(ee, region=rect_geometry(ee, rb, crs), region_bounds=rb, min_area_m2=0.0, **common)
        except Exception as e:
            subs = T.split_tile(core, native_scale_m)
            if not T.is_retryable(e) or len(subs) == 1:
                raise
            stats["splits"] += 1
            recs_all, trunc = [], 0
            for s in subs:
                r_, t_ = tile_records(s)
                recs_all += r_; trunc += t_
            return recs_all, trunc
        owned = [r for r in recs if T.owns(r["cx"], r["cy"], core)]
        return [r for r in owned if r["interior"]], sum(1 for r in owned if not r["interior"])

    last = None
    for r_km in radii_km:
        rr = r_km * 1000.0
        for core in T.tiles_for_circle(cx, cy, rr, tile_core_m, native_scale_m):
            if core not in cache:
                cache[core] = tile_records(core)
                log(f"    water-body tile {ntiles} ({r_km:g} km ladder): {len(cache[core][0])} bodies")
        allrecs = [r for recs, _t in cache.values() for r in recs]
        in_circle = [r for r in allrecs if _dist((r["cx"], r["cy"]), (cx, cy)) <= rr]
        within = [r for r in in_circle if _dist((r["cx"], r["cy"]), (target["cx"], target["cy"])) > 1.5 * native_scale_m]
        pool = within + [target]
        final, funnel = select_reference_records(pool, target["uid"], area_ratio=area_ratio, permanence_tol=permanence_tol,
                                                 min_pure_px=min_pure_px, use_permanence=use_perm, max_extent_m=max_extent_m)
        funnel.update({"n_excluded_truncated_at_tile_edge": sum(t for _r, t in cache.values()),
                       "n_outside_radius": len(allrecs) - len(in_circle),
                       "n_tiles": len(cache), "n_tile_splits": stats["splits"], "radius_km": r_km})
        last = (final, funnel, r_km)
        if len(final) >= min_reference_n:
            break
    if last is not None:
        final, funnel, r_km = last
        out["reference"] = reference_from_records(
            final, target, funnel, kind=kind, construct=construct, unit=unit, temporal=temporal, population=population,
            tier=tier, native_scale_m=native_scale_m, area_ratio=area_ratio, permanence_tol=permanence_tol,
            min_pure_px=min_pure_px, use_permanence=use_perm, radius_km=r_km, ring_width_m=ring_width_m if kind == "ring" else None)
        out["radius_used_km"] = r_km
    out["diagnostics"]["tiles"] = {"n_tiles": len(cache), "splits": stats["splits"], "split_errors": stats.get("split_errors", [])}
    return out


# ---------------------------------------------------------------- cell (site-sized window) references
def cell_reference_ee(ee, *, cell_image, region, native_scale_m: float, site_area_m2: float, crs: str, n: int,
                      seed: int, support: str, construct: str, unit: str, temporal: str, population: str,
                      tier: str, population_definition: str, tile_scale: int = 4,
                      extra: Optional[Dict] = None) -> ReferenceData:
    """Sample site-sized cells (each at most once) of an already-built cell image over ONE region.
    Only safe for a region of bounded native pixel count; use cell_reference_tiled_ee for a reference zone."""
    fc = S.ee_sample_cells(ee, cell_image, region, native_scale_m, site_area_m2, crs, n, seed, tile_scale)
    vals = fc.aggregate_array("v").getInfo()
    vals = np.array([v for v in (vals or []) if v is not None], dtype=float)
    k = S.cell_size_px(site_area_m2, native_scale_m)
    spec = MetricSpec(construct, unit, temporal, support, population,
                      window_area_m2=float(k * native_scale_m) ** 2, native_scale_m=native_scale_m)
    diag = {"cell_px": k, "cell_side_m": k * native_scale_m, "cell_area_m2": float(k * native_scale_m) ** 2,
            "site_area_m2": site_area_m2, "crs": crs, "sample_requested": n, "seed": seed,
            "sampling": "stratifiedSample on validity band in the cell projection, numPoints=0"}
    diag.update(extra or {})
    return ReferenceData(vals, spec, tier, population_definition, diag)


def circle_polygon(ee, cx: float, cy: float, radius_m: float, crs: str, n_vertices: int = 256):
    """The reference zone as a polygon in the site's UTM CRS (identical for the count and the sample of every tile)."""
    pts = [[cx + radius_m * math.cos(2 * math.pi * k / n_vertices), cy + radius_m * math.sin(2 * math.pi * k / n_vertices)]
           for k in range(n_vertices)]
    return ee.Geometry.Polygon([pts], proj=crs, geodesic=False)


def cell_reference_tiled_ee(ee, *, cell_image, mask, centre_xy, radius_m: float, native_scale_m: float, site_area_m2: float,
                            crs: str, n: int, seed: int, support: str, construct: str, unit: str, temporal: str,
                            population: str, tier: str, population_definition: str, tile_native_px: int = 3072,
                            tile_scale: int = 4, extra: Optional[Dict] = None, count_fn=None, sample_fn=None,
                            log=None) -> ReferenceData:
    """A reference sample of site-sized cells over the whole reference circle, with every Earth Engine request bounded.

    The first live run failed ("User memory limit exceeded", "Reprojection output too large (10017x10017 pixels)") because one
    request covered a 100 km box of 10 m pixels. The resolution, the cell size, the non-overlap and the population are unchanged;
    only the REQUEST is confined:
      1. tile the circle with tiles of ~tile_native_px native pixels per side, edges on the cell grid (no cell is cut);
      2. COUNT the eligible cells of each tile (cheap: the eligibility mask on the cell grid only);
      3. allocate the n draws over the tiles in proportion to those counts (largest remainder): every eligible cell then has the
         same inclusion probability n/N, so the pooled sample is a simple random sample and needs no weights;
      4. SAMPLE each tile for its allocation. A tile that hits a memory / size error is split in four and retried.
    If the whole population has <= n cells every cell is taken. reference_n = the cells actually returned."""
    from darukaa_reference import tiling as T
    log = log or (lambda *a, **k: None)
    k = S.cell_size_px(site_area_m2, native_scale_m)
    cell_m = k * native_scale_m
    tile_m = T.tile_side_m(tile_native_px, native_scale_m, cell_m)
    cx, cy = centre_xy
    tiles = T.tiles_for_circle(cx, cy, radius_m, tile_m, cell_m)
    circle = circle_polygon(ee, cx, cy, radius_m, crs)
    elig = ee.Image.constant(1) if mask is None else ee.Image.constant(1).updateMask(mask)
    sampled_image = cell_image if mask is None else cell_image.updateMask(mask)

    def region(tile):
        rect = rect_geometry(ee, tile, crs)
        inside = all((x - cx) ** 2 + (y - cy) ** 2 <= radius_m ** 2 for x in (tile[0], tile[2]) for y in (tile[1], tile[3]))
        return rect if inside else rect.intersection(circle, 1)

    if count_fn is None:
        def count_fn(tile):
            r = elig.reduceRegion(reducer=ee.Reducer.count().unweighted(), geometry=region(tile), scale=cell_m, crs=crs,
                                  maxPixels=1e9, tileScale=tile_scale).getInfo()
            return int(next((v for v in (r or {}).values() if v is not None), 0))
    if sample_fn is None:
        def sample_fn(tile, m):
            fc = S.ee_sample_cells(ee, sampled_image, region(tile), native_scale_m, site_area_m2, crs, m, seed, tile_scale)
            return fc.aggregate_array("v").getInfo() or []

    stats: Dict = {"splits": 0}
    leaves: List[Tuple] = []
    for i, t in enumerate(tiles):
        got = T.count_adaptive(t, count_fn, cell_m, stats)
        leaves += [(lt, c) for lt, c in got if c > 0]
        log(f"    cell count tile {i + 1}/{len(tiles)}: {sum(c for _, c in got)} eligible cells")
    counts = {lt: c for lt, c in leaves}
    total = sum(counts.values())
    alloc = T.allocate(counts, n)
    values: List[float] = []
    for i, (lt, _c) in enumerate(leaves):
        vals = T.sample_adaptive(lt, alloc.get(lt, 0), sample_fn, count_fn, cell_m, stats)
        values += [v for v in vals if v is not None]
        log(f"    cell sample leaf {i + 1}/{len(leaves)}: asked {alloc.get(lt, 0)}, got {len(vals)}")
    arr = np.array(values, dtype=float)
    spec = MetricSpec(construct, unit, temporal, support, population,
                      window_area_m2=float(cell_m) ** 2, native_scale_m=native_scale_m)
    diag = {"cell_px": k, "cell_side_m": cell_m, "cell_area_m2": float(cell_m) ** 2, "site_area_m2": site_area_m2, "crs": crs,
            "sample_requested": n, "seed": seed, "reference_radius_m": radius_m, "eligible_cells_total": total,
            "sampling": "tiled proportional allocation (self-weighting simple random sample); stratifiedSample numPoints=0 per tile",
            "tile_native_px": tile_native_px, "tile_side_m": tile_m, "n_tiles": len(tiles), "n_leaf_tiles": len(leaves),
            "n_tile_splits": stats["splits"], "split_errors": stats.get("split_errors", [])[:5],
            "allocation_min": min(alloc.values()) if alloc else 0, "allocation_max": max(alloc.values()) if alloc else 0,
            "n_returned": int(arr.size), "population_taken": "all cells" if total <= n else f"{n} of {total} eligible cells"}
    diag.update(extra or {})
    return ReferenceData(arr, spec, tier, f"{population_definition}; {diag['population_taken']}", diag)
