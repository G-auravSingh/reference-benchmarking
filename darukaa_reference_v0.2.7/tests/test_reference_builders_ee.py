"""
Structure tests for the Earth Engine reference builders (fakes only): the selection RULE, the call chains, the derived tile margin,
the explicit extent rule, and the exposed population / reference_n. The orchestration LOGIC (tiling, ownership, ladder, interior rule)
is tested against a numpy world in test_water_body_ee_logic.py. None of this proves Earth Engine's own behaviour: the live smoke test
and its synthetic parity check do.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from darukaa_reference import constructs as K
from darukaa_reference import indicator_contract as IC
from darukaa_reference import reference_builders_ee as RE


def rec(uid, area, pure=100, value=0.1, perm=0.9, extent=200.0):
    return {"uid": uid, "area_m2": area, "pure_px": pure, "value": value, "permanence": perm, "bbox": (0.0, 0.0, extent, extent)}


def test_selection_rule_applies_size_permanence_pixel_and_extent_criteria():
    t = rec("T", 40000.0, value=0.5)
    recs = [t, rec("a", 40000 * 3.0), rec("b", 40000 * 3.01), rec("c", 40000 / 3.0), rec("d", 40000 / 3.1),
            rec("e", 40000.0, perm=0.65), rec("f", 40000.0, perm=0.64), rec("g", 40000.0, pure=9), rec("h", 40000.0, value=None),
            rec("i", 40000.0, extent=2500.0)]
    final, f = RE.select_reference_records(recs, "T", max_extent_m=2000.0)
    assert sorted(r["uid"] for r in final) == ["a", "c", "e"]                    # ratio bounds and |dperm| <= 0.25 are inclusive
    assert f["n_rejected_size"] == 2 and f["n_rejected_permanence"] == 1 and f["n_rejected_extent"] == 1
    final2, _ = RE.select_reference_records(recs, "T", use_permanence=False, max_extent_m=2000.0)
    assert sorted(r["uid"] for r in final2) == ["a", "c", "e", "f"]
    final3, f3 = RE.select_reference_records(recs, "T")                          # no extent rule: the long body is eligible
    assert "i" in [r["uid"] for r in final3] and f3["n_rejected_extent"] == 0


def test_the_target_is_never_rejected_by_the_extent_rule_inside_selection():
    t = rec("T", 40000.0, extent=5000.0)
    final, f = RE.select_reference_records([t, rec("a", 40000.0)], "T", max_extent_m=2000.0)
    assert [r["uid"] for r in final] == ["a"]                                    # the orchestrator rejects an over-long TARGET explicitly


def test_the_tile_margin_is_derived_from_the_extent_rule_so_tiling_cannot_drop_an_eligible_body():
    assert K.MAX_WATER_BODY_EXTENT_M == 2000.0
    from darukaa_reference.config import Config
    assert Config().water_body_max_extent_m == K.MAX_WATER_BODY_EXTENT_M
    # margin = max extent + interior margin + 1 px: water (erode + 1 px) and ring (ring width + 2 px)
    water = 2000.0 + (K.PURE_WATER_ERODE_PX + 1) * 10.0 + 10.0
    ring = 2000.0 + 100.0 + 2 * 10.0 + 10.0
    assert water == 2030.0 and ring == 2130.0


def test_unit_records_builds_a_pixel_count_area_an_interior_flag_and_reads_features():
    ee = MagicMock()
    counts = MagicMock(); counts.getInfo.return_value = {"features": [
        {"properties": {"uid": "u1", "n": 458.0, "p": 340.0, "clon": 75.00103960971117, "clat": 18.08974837431718, "lon0": 75.00000000000001, "lat0": 18.088708943127365,
                        "lon1": 75.0020792316692, "lat1": 18.090787799792878, "geodesic_area_m2": 45962.0, "touches_site": 1}},
        {"properties": {"uid": "u2", "n": 20.0, "p": 0.0, "clon": 75.00103960971117, "clat": 18.08974837431718, "lon0": 75.00000000000001, "lat0": 18.088708943127365, "lon1": 75.00000000000001, "lat1": 18.088708943127365}}]}
    vals = MagicMock(); vals.getInfo.return_value = {"features": [{"properties": {"uid": "u1", "v": 0.1467, "perm": 0.8}}]}
    img = MagicMock()
    img.select.return_value.rename.return_value.updateMask.return_value.addBands.return_value.reduceRegions.return_value = vals
    water = MagicMock()
    water.focal_min.return_value = MagicMock()
    ee.Image.cat.return_value.reduceRegions.return_value = counts
    out = RE.unit_records_ee(ee, region=MagicMock(), region_bounds=(499000.0, 1999000.0, 501000.0, 2001000.0), water_mask=water,
                             metric_image=img, kind="water", native_scale_m=10.0, permanence_image=MagicMock(),
                             min_area_m2=3000.0, crs="EPSG:32643", site_geometry=MagicMock())
    assert [r["uid"] for r in out] == ["u1"]                                     # 2,000 m2 < min area 3,000 m2: dropped by the exact filter
    r = out[0]
    assert r["area_m2"] == 45800.0 and r["n_px"] == 458 and r["pure_px"] == 340 and r["geodesic_area_m2"] == 45962.0
    assert abs(r["cx"] - 500110.0) < 5 and abs(r["cy"] - 2000115.0) < 5 and abs(r["bbox"][0] - 500000.0) < 5 and abs(r["bbox"][3] - 2000230.0) < 5   # lon/lat -> UTM
    assert r["interior"] is True and r["touches_site"] is True and r["value"] == 0.1467 and r["permanence"] == 0.8
    water.focal_min.assert_called_with(radius=K.PURE_WATER_ERODE_PX, kernelType="square", units="pixels")
    edge = RE.unit_records_ee(ee, region=MagicMock(), region_bounds=(500000.0, 2000000.0, 500240.0, 2000250.0), water_mask=water,
                              metric_image=img, kind="water", native_scale_m=10.0, min_area_m2=3000.0, crs="EPSG:32643")
    assert edge[0]["interior"] is False                                          # touches the erosion margin of a tight region


def test_cell_reference_exposes_population_cell_size_and_reference_n():
    ee = MagicMock()
    fake = MagicMock(); fake.getInfo.return_value = [0.1, 0.2, None, 0.3]
    fc = MagicMock(); fc.aggregate_array.return_value = fake
    import darukaa_reference.support as S
    orig = S.ee_sample_cells
    S.ee_sample_cells = lambda *a, **k: fc
    try:
        ref = RE.cell_reference_ee(ee, cell_image="IMG", region="Z", native_scale_m=10.0, site_area_m2=4.01e5,
                                   crs="EPSG:32643", n=5000, seed=12345, support="site_window_mean", construct="c",
                                   unit="u", temporal="t", population="regional_ecoregion", tier="tier1",
                                   population_definition="ecoregion cells")
    finally:
        S.ee_sample_cells = orig
    assert ref.reference_n == 3 and ref.population_definition == "ecoregion cells"           # the None is dropped
    assert ref.spec.window_area_m2 == 630.0 ** 2 and ref.diagnostics["cell_px"] == 63 and ref.diagnostics["crs"] == "EPSG:32643"
    assert ref.diagnostics["seed"] == 12345 and ref.diagnostics["sample_requested"] == 5000


def test_shared_water_definition_is_mndwi_and_pure_water_is_eroded():
    comp = MagicMock()
    RE.water_mask_s2(comp)
    comp.normalizedDifference.assert_called_with(["B3", "B11"])
    wm = MagicMock()
    RE.pure_water_mask(wm)
    wm.focal_min.assert_called_with(radius=1, kernelType="square", units="pixels")


# ================================================================== memory-safe tiled cell reference
from darukaa_reference import tiling as T


class Zone2D:
    """Eligible cells scattered over a 100 km circle: density varies by location so allocation must be proportional."""
    def __init__(self, cell_m=630.0, seed=0):
        self.cell_m = cell_m
        rng = np.random.default_rng(seed)
        self.density = lambda x, y: 0.9 if x < 0 else 0.2                    # west 90 % eligible, east 20 % eligible

    def n_eligible(self, tile):
        nx = int(round((tile[2] - tile[0]) / self.cell_m)); ny = int(round((tile[3] - tile[1]) / self.cell_m))
        return int(round(nx * ny * self.density((tile[0] + tile[2]) / 2, 0)))


def run_tiled(zone, n=5000, fail=None, tile_native_px=3072, radius_m=50000.0, native=10.0, site_area=4.01e5):
    ee = MagicMock()
    cell_m = S_.cell_size_px(site_area, native) * native
    counts_log, samples_log, ids = [], [], {}
    zone.ids = ids                                                       # tile -> numeric id, so sampled VALUES identify their tile

    def count_fn(tile):
        counts_log.append(tile)
        if fail and fail(tile):
            raise RuntimeError("User memory limit exceeded.")
        return zone.n_eligible(tile)

    def sample_fn(tile, m):
        samples_log.append((tile, m))
        if fail and fail(tile):
            raise RuntimeError("Image.stratifiedSample: Reprojection output too large (10017x10017 pixels).")
        tid = ids.setdefault(tile, len(ids) + 1)
        return [float(tid * 1e6 + i) for i in range(min(m, zone.n_eligible(tile)))]
    ref = RE.cell_reference_tiled_ee(ee, cell_image=MagicMock(), mask=None, centre_xy=(500000.0, 2000000.0), radius_m=radius_m,
                                     native_scale_m=native, site_area_m2=site_area, crs="EPSG:32643", n=n, seed=1,
                                     support="site_window_mean", construct="c", unit="u", temporal="t", population="p", tier="tier1",
                                     population_definition="pop", tile_native_px=tile_native_px, count_fn=count_fn, sample_fn=sample_fn)
    return ref, counts_log, samples_log


import darukaa_reference.support as S_


def test_tiled_reference_returns_n_cells_with_proportional_allocation_and_no_tile_larger_than_the_budget():
    zone = Zone2D()
    ref, counts_log, samples_log = run_tiled(zone)
    assert ref.reference_n == 5000 and len(set(ref.values.tolist())) == 5000                      # n cells, no duplicates
    cell_m = S_.cell_size_px(4.01e5, 10.0) * 10.0
    side = T.tile_side_m(3072, 10.0, cell_m)
    assert all(abs((t[2] - t[0]) - side) < 1e-6 for t in counts_log)                              # every request is one bounded tile
    assert (side / 10.0) <= 3072 + cell_m / 10.0                                                  # ~3,072 native px per side, never 10,017
    total = ref.diagnostics["eligible_cells_total"]
    by_tile = {}
    for v in ref.values:
        by_tile[int(v // 1e6)] = by_tile.get(int(v // 1e6), 0) + 1
    tile_of = {i: t for t, i in zone.ids.items()}
    for tid, got in by_tile.items():                                                              # inclusion probability n/N in every tile
        assert abs(got - 5000 * zone.n_eligible(tile_of[tid]) / total) <= 1.0
    assert ref.diagnostics["population_taken"] == f"5000 of {total} eligible cells"
    assert ref.diagnostics["n_tiles"] == len(counts_log) and ref.diagnostics["n_tile_splits"] == 0


def test_a_memory_failure_splits_tiles_and_keeps_n_and_the_population():
    plain, _, _ = run_tiled(Zone2D())
    cell_m = S_.cell_size_px(4.01e5, 10.0) * 10.0
    limit = 30 * cell_m                                                                            # the "server" only does <= 30 cells across
    ref, counts_log, samples_log = run_tiled(Zone2D(), fail=lambda t: (t[2] - t[0]) > limit)
    assert ref.diagnostics["n_tile_splits"] >= 1 and ref.diagnostics["split_errors"]
    assert ref.reference_n == 5000 and len(set(ref.values.tolist())) == 5000
    assert ref.diagnostics["eligible_cells_total"] == plain.diagnostics["eligible_cells_total"] or \
        abs(ref.diagnostics["eligible_cells_total"] - plain.diagnostics["eligible_cells_total"]) < 0.02 * plain.diagnostics["eligible_cells_total"]
    assert all((t[2] - t[0]) <= limit + 1e-6 for t, m in samples_log if m > 0)                     # after splitting every sampled tile fits


def test_a_small_population_is_taken_whole_and_below_30_is_reported_not_padded():
    z = Zone2D(); z.density = lambda x, y: 0.0002                                                  # almost nothing eligible
    ref, _, _ = run_tiled(z, n=5000)
    assert ref.reference_n == ref.diagnostics["eligible_cells_total"] < 5000 and ref.diagnostics["population_taken"] == "all cells"
    z.density = lambda x, y: 0.0                                                                   # nothing eligible at all
    empty, _, _ = run_tiled(z)
    assert empty.reference_n == 0


def test_tiled_reference_is_deterministic_and_exposes_its_construction():
    a, _, _ = run_tiled(Zone2D()); b, _, _ = run_tiled(Zone2D())
    assert a.values.tolist() == b.values.tolist()
    d = a.diagnostics
    for k in ("tile_side_m", "tile_native_px", "n_tiles", "n_leaf_tiles", "eligible_cells_total", "allocation_min", "allocation_max",
              "n_returned", "seed", "cell_side_m", "sampling"):
        assert k in d, k
    assert a.spec.window_area_m2 == d["cell_area_m2"] and a.spec.native_scale_m == 10.0 and "self-weighting" in d["sampling"]


def test_tiled_default_count_and_sample_functions_call_earth_engine_with_bounded_regions():
    ee = MagicMock()
    fc = MagicMock(); fc.aggregate_array.return_value.getInfo.return_value = [1.0, 2.0]
    img = MagicMock()
    S_orig = S_.ee_sample_cells
    seen = []
    S_.ee_sample_cells = lambda ee_, image, region, native, area, crs, m, seed, ts: (seen.append((region, m)) or fc)
    ee.Image.constant.return_value.reduceRegion.return_value.getInfo.return_value = {"constant": 7}
    try:
        ref = RE.cell_reference_tiled_ee(ee, cell_image=img, mask=None, centre_xy=(500000.0, 2000000.0), radius_m=3000.0,
                                         native_scale_m=10.0, site_area_m2=4.01e5, crs="EPSG:32643", n=10, seed=1,
                                         support="site_window_mean", construct="c", unit="u", temporal="t", population="p",
                                         tier="tier1", population_definition="pop", tile_native_px=3072)
    finally:
        S_.ee_sample_cells = S_orig
    kw = ee.Image.constant.return_value.reduceRegion.call_args.kwargs
    assert kw["scale"] == 630.0 and kw["crs"] == "EPSG:32643"                                      # counted on the cell grid
    assert ee.Reducer.count.return_value.unweighted.called                                          # pixel centres, not fractional weights
    assert ref.reference_n >= 2 and seen


def test_uid_is_precise_and_coordinates_are_requested_in_lonlat_not_assumed_utm():
    """Live bug: bbox came back in degrees (73.8, 18.6) and every uid was '73.8,18.6'. The uid keeps 1e-7 degrees and the transform is explicit."""
    import inspect
    src = inspect.getsource(RE._unit_geometry_properties)
    assert '"EPSG:4326"' in src and "%.7f" in src and "%.1f" not in src
    tr = RE._xy_transformer("EPSG:32643")
    x, y, bb = RE._to_xy(tr, {"clon": 73.81, "clat": 18.643, "lon0": 73.8096, "lat0": 18.6417, "lon1": 73.8121, "lat1": 18.6448})
    assert 300000 < x < 700000 and 2.0e6 < y < 2.1e6 and bb[0] < x < bb[2] and bb[1] < y < bb[3] and 200 < bb[2] - bb[0] < 400   # metres, a ~250 m body
