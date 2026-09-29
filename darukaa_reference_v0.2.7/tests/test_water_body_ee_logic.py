"""
Water-body construction: the tiled / edge-safe Earth Engine ORCHESTRATION is run against a numpy world through a fake
`unit_records_ee` that reproduces Earth Engine's semantics (region-clipped 4-connected components, area = pixel count,
erosion that can see pixels outside the region). What this proves: tile ownership, margins, the interior rule, the radius
ladder and target selection give exactly the numpy definition's answer, including the live "extra component" case.
What it does NOT prove: Earth Engine's own primitives -- the live synthetic parity check does that.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from darukaa_reference import reference_builders_ee as RE
from darukaa_reference import support as S
from darukaa_reference import tiling as T

RES, X0, YTOP = 10.0, 500000.0, 2004000.0
MAX_EXT = 700.0                                     # population rule for the fixture (production default 2,000 m)


class World:
    def __init__(self, h=400, w=400):
        self.mask = np.zeros((h, w), bool); self.metric = np.full((h, w), 0.5); self.perm = np.zeros((h, w))
        self.h, self.w = h, w

    def add(self, i, j, hh, ww, value, perm=0.9):
        self.mask[i:i + hh, j:j + ww] = True; self.metric[i:i + hh, j:j + ww] = value; self.perm[i:i + hh, j:j + ww] = perm

    def px_to_xy(self, i, j):
        return X0 + (j + 0.5) * RES, YTOP - (i + 0.5) * RES


def fake_unit_records(world, calls=None, fail=None):
    def fn(ee, *, region, region_bounds, water_mask, metric_image, kind, native_scale_m, permanence_image=None,
           ring_width_m=100.0, min_area_m2=0.0, tile_scale=4, crs=None, site_geometry=None):
        if calls is not None:
            calls.append(region_bounds)
        if fail is not None and fail(region_bounds):
            raise RuntimeError("User memory limit exceeded.")
        bx0, by0, bx1, by1 = region_bounds
        j0, j1 = max(0, int(round((bx0 - X0) / RES))), min(world.w, int(round((bx1 - X0) / RES)))
        i0, i1 = max(0, int(round((YTOP - by1) / RES))), min(world.h, int(round((YTOP - by0) / RES)))
        window = np.zeros_like(world.mask); window[i0:i1, j0:j1] = world.mask[i0:i1, j0:j1]          # clipped to the region
        units = S.label_units(window, RES * RES)
        pure_full = S.pure_water(world.mask, 1)                                                     # EE sees pixels outside the region
        ring_px = int(round(ring_width_m / RES))
        margin = (2 * RES) if kind == "water" else ring_width_m + 2 * RES
        out = []
        for lab in units.areas_m2:
            body = units.labels == lab
            ii, jj = np.nonzero(body)
            xs, ys = X0 + (jj + 0.5) * RES, YTOP - (ii + 0.5) * RES
            bbox = (xs.min() - RES / 2, ys.min() - RES / 2, xs.max() + RES / 2, ys.max() + RES / 2)
            pure = body & pure_full
            if kind == "water":
                mask_v = pure
            else:
                mask_v = S.ring_masks(S.WaterUnits(body.astype(int), {1: 1.0}), ring_px, all_water=world.mask)[1]
            n_px = int(body.sum())
            if n_px * RES * RES < min_area_m2:
                continue
            val = float(world.metric[mask_v].mean()) if mask_v.any() else None
            touches = bool(site_geometry is not None and (site_geometry & body).any())
            cx, cy = float(xs.mean()), float(ys.mean())
            out.append({"uid": f"{cx:.1f},{cy:.1f}", "cx": cx, "cy": cy, "bbox": bbox, "n_px": n_px, "area_m2": n_px * RES * RES,
                        "geodesic_area_m2": n_px * RES * RES * 1.00354, "pure_px": int(pure.sum()), "value": val,
                        "permanence": float(world.perm[body].mean()) if permanence_image is not None else None,
                        "interior": T.is_interior(bbox, region_bounds, margin), "touches_site": touches})
        return out
    return fn


def numpy_expected(world, site, centre, radius_m, kind="water", ring_px=10, use_perm=True):
    """The numpy DEFINITION over the whole world: no tiles, no regions."""
    units = S.label_units(world.mask, RES * RES)
    pure_full = S.pure_water(world.mask, 1)
    recs = []
    for lab in units.areas_m2:
        body = units.labels == lab
        ii, jj = np.nonzero(body)
        xs, ys = X0 + (jj + 0.5) * RES, YTOP - (ii + 0.5) * RES
        mask_v = (body & pure_full) if kind == "water" else S.ring_masks(S.WaterUnits(body.astype(int), {1: 1.0}), ring_px, all_water=world.mask)[1]
        cx, cy = float(xs.mean()), float(ys.mean())
        bbox = (xs.min() - RES / 2, ys.min() - RES / 2, xs.max() + RES / 2, ys.max() + RES / 2)
        recs.append({"uid": f"{cx:.1f},{cy:.1f}", "cx": cx, "cy": cy, "bbox": bbox, "n_px": int(body.sum()), "area_m2": int(body.sum()) * RES * RES,
                     "pure_px": int((body & pure_full).sum()), "value": float(world.metric[mask_v].mean()) if mask_v.any() else None,
                     "permanence": float(world.perm[body].mean()), "touches": bool((site & body).any())})
    target = max([r for r in recs if r["touches"]], key=lambda r: r["n_px"])
    pool = [r for r in recs if RE._dist((r["cx"], r["cy"]), centre) <= radius_m and r["uid"] != target["uid"]] + [target]
    final, funnel = RE.select_reference_records(pool, target["uid"], use_permanence=use_perm, max_extent_m=MAX_EXT)
    return target, final, funnel


def build_world():
    w = World()
    w.add(190, 190, 20, 20, 0.20, 0.9)                                    # TARGET lake (400 px) at the centre
    cores = [(60, 60), (60, 300), (300, 60), (300, 300), (120, 120), (250, 250), (100, 250), (250, 100), (30, 180), (330, 190),
             (190, 40), (190, 340)]
    sizes = [(15, 15), (18, 18), (22, 22), (16, 16), (25, 25), (20, 20), (14, 14), (28, 28), (19, 19), (24, 24), (17, 17), (21, 21)]
    for k, ((i, j), (h, ww)) in enumerate(zip(cores, sizes)):
        w.add(i, j, h, ww, 0.10 + 0.01 * k, 0.85)                        # 12 comparable lakes, spread over several tiles
    w.add(60, 130, 3, 3, 0.9, 0.9)                                        # 3x3: no pure water
    w.add(330, 330, 4, 4, 0.9, 0.9)                                       # too small (16 px < 133 px)
    w.add(20, 20, 60, 60, 0.9, 0.9)                                       # too big (3600 px > 1200 px)
    w.add(150, 300, 20, 20, 0.7, 0.3)                                     # right size, wrong permanence
    w.add(380, 10, 6, 350, 0.9, 0.9)                                      # long channel: exceeds any margin, never comparable
    site = np.zeros_like(w.mask); site[185:215, 185:215] = True
    return w, site


def run_reference(world, site, tile_core_m=1000.0, radii=(1200.0, 2500.0), fail=None, calls=None, kind="water", **kw):
    ee = MagicMock()
    cx, cy = world.px_to_xy(200, 200)
    RE_unit = RE.unit_records_ee
    RE.unit_records_ee = fake_unit_records(world, calls, fail)
    try:
        return RE.water_body_reference_ee(
            ee, site_geometry=site, site_bounds_utm=(X0 + 1850, YTOP - 2150, X0 + 2150, YTOP - 1850), centre_xy=(cx, cy),
            water_mask=None, metric_image=MagicMock(), kind=kind, native_scale_m=RES, construct="c", unit="u", temporal="t",
            population="comparable_water_bodies", radii_km=tuple(r / 1000 for r in radii), min_reference_n=10,
            permanence_image=MagicMock(), crs="EPSG:32643", tile_core_m=tile_core_m, max_extent_m=MAX_EXT, probe_margin_m=200.0, **kw)
    finally:
        RE.unit_records_ee = RE_unit


def test_tiled_orchestration_equals_the_numpy_definition_over_the_whole_world():
    w, site = build_world()
    out = run_reference(w, site)
    cx, cy = w.px_to_xy(200, 200)
    target, final, funnel = numpy_expected(w, site, (cx, cy), out["radius_used_km"] * 1000)
    assert out["valid"] and out["target"]["uid"] == target["uid"]
    assert out["target"]["n_px"] == 400 and out["target"]["pure_px"] == 18 * 18
    ref = out["reference"]
    assert sorted(ref.diagnostics["reference_body_uids"]) == sorted(r["uid"] for r in final)
    assert np.allclose(sorted(ref.values), sorted(r["value"] for r in final))
    assert ref.reference_n == len(final) >= 10
    for k in ("n_rejected_size", "n_rejected_permanence", "n_reference_bodies"):
        assert ref.diagnostics["funnel"][k] == funnel[k], k
    # the 3.5 km channel violates the explicit extent rule: numpy rejects it by rule, the tiled EE region cannot contain it, so it
    # is reported as truncated -- either way it is not in the population
    assert funnel["n_rejected_extent"] + ref.diagnostics["funnel"]["n_rejected_extent"] + \
        ref.diagnostics["funnel"]["n_excluded_truncated_at_tile_edge"] >= 1


def test_a_body_straddling_a_tile_boundary_is_counted_exactly_once():
    w, site = build_world()
    cx, cy = w.px_to_xy(200, 200)
    core = 1000.0
    edge_x = np.floor(cx / core) * core                                                              # a tile-core boundary
    j = int(round((edge_x - X0) / RES)) - 9                                                          # straddle it: 9 px left, 9 px right
    w.add(100, j, 18, 18, 0.33, 0.9)
    out = run_reference(w, site)
    uids = out["reference"].diagnostics["reference_body_uids"]
    assert len(uids) == len(set(uids))                                                                # no duplicates
    straddler = [r for r in uids if abs(float(r.split(",")[0]) - (X0 + (j + 9) * RES)) < RES]
    assert len(straddler) == 1


def test_the_extra_component_case_is_reproduced_and_then_agrees():
    """The live discrepancy: EE listed a 42-px body that numpy did not. Same pixels on both sides, so the body exists in
    both; the harness applied the 'interior' filter to numpy only. Reproduce it, then show the corrected rule agrees."""
    w = World(70, 70)                                                                                # a 700 m parity window
    w.add(20, 20, 24, 24, 0.147, 0.9)                                                                # main lake: 576 px
    w.add(1, 60, 6, 7, 0.134, 0.9)                                                                   # 42-px pond 10 m from the window edge
    ee = MagicMock()
    fn = fake_unit_records(w)
    bounds = (X0, YTOP - 700.0, X0 + 700.0, YTOP)
    ee_recs = fn(ee, region=None, region_bounds=bounds, water_mask=None, metric_image=None, kind="water", native_scale_m=RES, min_area_m2=3000.0)
    assert sorted(r["n_px"] for r in ee_recs) == [42, 576]                                           # EE sees both components
    assert abs(ee_recs[0]["geodesic_area_m2"] / ee_recs[0]["area_m2"] - 1.00354) < 1e-9             # geodesic area is NOT the pixel-count area
    units = S.label_units(w.mask, 100.0, min_area_m2=3000.0)
    edge = np.zeros_like(w.mask); edge[:2, :] = edge[-2:, :] = True; edge[:, :2] = edge[:, -2:] = True
    numpy_inner = [i for i in units.areas_m2 if not (units.labels == i)[edge].any()]
    # OLD harness: EE list unfiltered (all 'interior' by default) vs numpy edge-filtered -> 2 vs 2?  the pond is 30 m from the edge
    pond = [r for r in ee_recs if r["n_px"] == 42][0]
    assert pond["bbox"][3] >= bounds[3] - 2 * RES and not pond["interior"]                          # it sits inside the edge margin
    # CORRECTED: both apply the same interior rule and the same pixel-count area
    ee_interior = [r for r in ee_recs if r["interior"]]
    assert [r["n_px"] for r in ee_interior] == [576] and len(numpy_inner) == 1
    assert ee_interior[0]["area_m2"] == units.areas_m2[numpy_inner[0]] == 57600.0                    # identical area definition
    pure = S.unit_masks(units, pure=True)
    assert ee_interior[0]["pure_px"] == int(pure[numpy_inner[0]].sum()) == 22 * 22


def test_a_target_at_the_region_edge_doubles_the_margin_until_it_is_interior():
    w, site = build_world()
    out = run_reference(w, site, want_reference=False)
    probes = out["diagnostics"]["probe"]
    assert out["valid"] and probes[0]["margin_m"] == 200.0
    w2, site2 = build_world()
    out2 = None
    ee = MagicMock(); cx, cy = w2.px_to_xy(200, 200)
    RE_unit = RE.unit_records_ee; RE.unit_records_ee = fake_unit_records(w2)
    try:
        out2 = RE.water_body_reference_ee(ee, site_geometry=site2, site_bounds_utm=(X0 + 1900, YTOP - 2100, X0 + 2100, YTOP - 1900),
                                          centre_xy=(cx, cy), water_mask=None, metric_image=MagicMock(), kind="water", native_scale_m=RES,
                                          construct="c", unit="u", temporal="t", population="p", want_reference=False, crs="EPSG:32643",
                                          probe_margin_m=10.0)
    finally:
        RE.unit_records_ee = RE_unit
    m = [p["margin_m"] for p in out2["diagnostics"]["probe"]]
    assert m[0] == 10.0 and m == sorted(m) and len(m) >= 2 and out2["valid"]                        # 10 m margin clips the lake: doubled
    assert not out2["diagnostics"]["probe"][0]["touching"][0]["interior"] and out2["diagnostics"]["probe"][-1]["touching"][0]["interior"]


def test_no_water_body_in_site_and_insufficient_pure_water_are_explicit():
    w, site = build_world()
    empty = np.zeros_like(site); empty[5:8, 5:8] = True                                             # a site with no water
    out = run_reference(w, empty, want_reference=False)
    assert not out["valid"] and out["invalid_reason"] == "no_water_body_in_site"
    w2 = World(); w2.add(195, 195, 4, 4, 0.2)                                                       # a 4x4 pond: 4 pure px
    site2 = np.zeros_like(w2.mask); site2[190:205, 190:205] = True
    out2 = run_reference(w2, site2, want_reference=False)
    assert not out2["valid"] and out2["invalid_reason"] == "insufficient_pure_water" and out2["n_pure_water_px"] == 4


def test_too_few_comparable_bodies_returns_the_honest_short_reference_and_uses_the_whole_ladder():
    w = World(); w.add(190, 190, 20, 20, 0.2)
    for k, (i, j) in enumerate([(60, 60), (60, 300), (300, 60)]):
        w.add(i, j, 18, 18, 0.1 + k * .01)
    site = np.zeros_like(w.mask); site[185:215, 185:215] = True
    out = run_reference(w, site)
    assert out["valid"] and out["reference"].reference_n == 3 < 10 and out["radius_used_km"] == 2.5


def test_radius_ladder_stops_as_soon_as_the_minimum_is_reached_and_reuses_tiles():
    w, site = build_world()
    calls = []
    out = run_reference(w, site, radii=(3000.0, 6000.0), calls=calls)
    assert out["radius_used_km"] == 3.0                                                            # 12 comparables exist within 3 km
    assert len(set(calls)) == len(calls)                                                           # no tile computed twice


def test_a_memory_error_splits_the_tile_and_gives_the_same_reference():
    w, site = build_world()
    plain = run_reference(w, site)
    calls = []
    big = lambda b: (b[2] - b[0]) > 2000.0                                                          # the "server" cannot do a 1 km core + margins
    split = run_reference(w, site, fail=big, calls=calls)
    assert split["diagnostics"]["tiles"]["splits"] >= 1
    assert sorted(split["reference"].diagnostics["reference_body_uids"]) == sorted(plain["reference"].diagnostics["reference_body_uids"])


def test_ring_kind_excludes_bodies_whose_ring_would_be_truncated():
    w, site = build_world()
    out = run_reference(w, site, kind="ring", ring_width_m=100.0)
    assert out["valid"] and out["reference"].spec.support == "riparian_ring_unit"
    assert out["reference"].diagnostics["ring_width_m"] == 100.0
    cx, cy = w.px_to_xy(200, 200)
    target, final, _ = numpy_expected(w, site, (cx, cy), out["radius_used_km"] * 1000, kind="ring", ring_px=10)
    assert sorted(out["reference"].diagnostics["reference_body_uids"]) == sorted(r["uid"] for r in final)
