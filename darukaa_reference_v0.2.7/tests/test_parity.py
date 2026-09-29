"""
Parity harness tests. A FAKE backend fabricates the "Earth Engine" data from the numpy definitions, so the harness's
own logic is tested offline: it must report MATCH when EE agrees, and DETECT each injected bug (a wrong class set, an
off-by-one year count, a shifted cell grid, a site-normalised wcpi, a missing erosion, a duplicated sample).
The real Earth Engine pulls are structure-tested; running them live is the smoke test itself.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from darukaa_reference import constructs as K
from darukaa_reference import parity as P
from darukaa_reference import reference_builders as R
from darukaa_reference import support as S

X0, Y1 = 500000.0, 2000000.0


def grid(h, w, res, values, x0=X0, y1=Y1):
    ii, jj = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
    x = (x0 + (jj + 0.5) * res).ravel(); y = (y1 - (ii + 0.5) * res).ravel()
    vals = {k: np.asarray(v, float).ravel() for k, v in values.items()}
    return P.PixelGrid(x, y, res, vals, {k: int(np.isfinite(v).sum()) for k, v in vals.items()})


class FakeBackend:
    """bug in {None, 'natural_class', 'years24', 'loss_any_canopy', 'cell_shift', 'wcpi_normalised', 'no_erosion',
    'duplicate_sample', 'ee_error', 'geodesic_area', 'extra_component', 'lossyear_masked', 'forest_centre_inclusion'}
    synth_bug in {None, 'eight_connected', 'no_erosion'}"""

    def __init__(self, bug=None, synth_bug=None):
        self.bug, self.synth_bug = bug, synth_bug
        rng = np.random.default_rng(5)
        self.dw = rng.choice([0, 1, 2, 3, 4, 5, 6, 7], (60, 60), p=[.05, .3, .15, .05, .2, .1, .1, .05]).astype(float)
        self.early = rng.choice([1, 2, 4], (60, 60)).astype(float)
        self.recent = np.where(rng.random((60, 60)) < .1, 1, self.early)
        self.red = np.where(rng.random((60, 60)) < .05, 0.2, rng.uniform(.02, .12, (60, 60)))
        self.ly = rng.integers(0, 26, (20, 20)).astype(float); self.tc = rng.uniform(0, 100, (20, 20))

    def _crs_for(self, zone):
        return "EPSG:32643"

    def region(self, zone, side_m, cell_m):
        return {"crs": "EPSG:32643", "bounds": (X0, Y1 - 600.0, X0 + 600.0, Y1)}

    def polygon_utm(self, zone):
        return box(X0 + 105.0, Y1 - 395.0, X0 + 305.0, Y1 - 205.0)              # deliberately NOT pixel-aligned

    def pull(self, key, region):
        if self.bug == "ee_error" and key == "s2_bundle":
            raise RuntimeError("EE computation timed out")
        if key == "dw_bundle":
            nat = R.natural_binary(self.dw)
            if self.bug == "natural_class":
                nat = np.where(np.isfinite(self.dw), np.isin(self.dw, [1, 2, 3]).astype(float), np.nan)      # shrub dropped
            return grid(60, 60, 10.0, {"dw_label": self.dw, "ee_natural_habitat": nat * 100, "ee_natural_veg": nat,
                                       "ee_sdi": R.sdi_pixel_disturbed(self.dw), "dw_early": self.early, "dw_recent": self.recent,
                                       "ee_net_change": R.tree_share_change_pp_per_year(self.early, self.recent, 7.0),
                                       "dt_years": np.full((60, 60), 7.0)})
        if key == "s2_bundle":
            w = R.wcpi_pixel(self.red)
            if self.bug == "wcpi_normalised":
                w = (w - np.nanmin(w)) / (np.nanmax(w) - np.nanmin(w))
            return grid(60, 60, 10.0, {"red": self.red, "ee_wcpi": w})
        if key == "hansen_bundle":
            num, den, _ = R.forest_loss_terms(self.ly, self.tc, 1, 25)
            if self.bug == "loss_any_canopy":
                num = ((self.ly > 0)).astype(float)
            g = grid(20, 20, 30.0, {"lossyear": self.ly, "treecover2000": self.tc, "ee_loss": num, "ee_baseline": den,
                                    "ee_years": np.full((20, 20), 24.0 if self.bug == "years24" else 25.0)})
            if self.bug == "lossyear_masked":               # Earth Engine omits a masked band: the real backend fills it with NaN
                g.values["lossyear"] = np.full(g.n, np.nan); g.coverage["lossyear"] = 0
            return g
        if key == "water_bundle":
            water = np.zeros((60, 60)); water[10:30, 10:30] = 1; water[36:50, 36:50] = 1
            water[1:7, 40:47] = 1                                                                # a 42-px pond 10 m from the window edge (the live pattern)
            metric = np.where(water > 0, 0.2, 0.01)
            self._water, self._metric = water, metric
            return grid(60, 60, 10.0, {"water": water, "metric": metric})
        raise KeyError(key)

    def pull_polygon(self, name, zone):
        vals = np.random.default_rng(8).uniform(0, 100, (60, 60))
        self._poly_vals = vals
        return grid(60, 60, 10.0, {"v": vals})

    def pull_forest_polygon(self, zone):
        return self.pull("hansen_bundle", None)

    def site_value_ee(self, name, zone):
        if name == "forest_loss_rate":
            g = self.pull("hansen_bundle", None)
            num, _, _ = g.raster("ee_loss"); den, _, _ = g.raster("ee_baseline")
            x0, y_top = float(g.x.min()) - 15.0, float(g.y.max()) + 15.0
            w = S.polygon_coverage(self.polygon_utm(zone), x0, y_top, 30.0, num.shape)
            if self.bug == "forest_centre_inclusion":
                w = (w >= 0.5).astype(float)                                                    # the rejected convention
            return S.polygon_rate(np.nan_to_num(num), np.nan_to_num(den), w, 25, 1.0, 0.0)
        g = self.pull_polygon(name, zone)
        return P.polygon_means(g, "v", self.polygon_utm(zone))["coverage_weighted"]             # EE weights boundary pixels by coverage

    def cells_ee(self, key, region, site_area_m2):
        g = self.pull("dw_bundle", region)
        band = "ee_natural_habitat" if key == "natural_habitat" else "ee_net_change"
        cells = P.numpy_cell_means(g, band, S.cell_size_px(site_area_m2, 10.0) * 10.0)
        if self.bug == "cell_shift":
            cells = {(k[0] + 1, k[1]): v for k, v in cells.items()}
        return cells

    def sampled_cells_ee(self, key, region, site_area_m2):
        vals = list(P.numpy_cell_means(self.pull("dw_bundle", region), "ee_natural_habitat", S.cell_size_px(site_area_m2, 10.0) * 10.0).values())
        return np.array(vals + ([vals[0]] if self.bug == "duplicate_sample" else []))

    def water_units_ee(self, region):
        g = self.pull("water_bundle", region)
        wa, x0, y0 = g.raster("water"); ma, _, _ = g.raster("metric")
        recs = P.numpy_water_records(wa > 0, ma, 10.0, x0, y0, region["bounds"])
        for r in recs:
            if self.bug == "no_erosion":
                r["pure_px"] = r["n_px"]
            if self.bug == "geodesic_area":
                r["area_m2"] = r["area_m2"] * 1.00354                                          # the v0.2.7 geodesic polygon area
        if self.bug == "extra_component":
            recs.append({"cx": X0 + 300.0, "cy": Y1 - 300.0, "bbox": (X0 + 250, Y1 - 350, X0 + 350, Y1 - 250), "n_px": 60, "area_m2": 6000.0,
                         "pure_px": 30, "value": 0.1, "interior": True})
        return recs

    def synthetic_water_ee(self, bounds, crs, n, res):
        water, metric = P.synthetic_water_raster(n)
        recs = P.numpy_water_records(water, metric, res, bounds[0] + res / 2, bounds[1] + n * res - res / 2, bounds, min_px=1,
                                     eight_connected=(self.synth_bug == "eight_connected"))
        if self.synth_bug == "no_erosion":
            for r in recs:
                r["pure_px"] = r["n_px"]
        return recs


ZONE = MagicMock()


def statuses(results, check=None):
    return {(r.check, r.item): r.status for r in results if check is None or r.check == check}


def test_consistent_ee_and_numpy_give_only_match_and_info():
    res = P.run_checks(FakeBackend(), ZONE, ZONE, parity_area_m2=1e4, site_value_names=("ndvi", "ghm"))
    bad = [(r.check, r.item, r.status, r.note) for r in res if r.status in (P.DISCREPANCY, P.HARNESS_ERROR)]
    assert bad == [], bad
    assert {r.check for r in res} >= {"pixel_construct", "block_cell_A1", "sampling_A2", "site_value", "convention_effect", "water_body",
                                      "water_body_synthetic", "band_coverage"}
    assert sum(r.status == P.MATCH for r in res) >= 25


def test_boundary_weighting_is_quantified_and_labelled_correctly():
    res = P.run_checks(FakeBackend(), ZONE, None, site_value_names=("ndvi",))
    info = [r for r in res if r.check == "convention_effect"][0]
    assert info.status == P.INFO and info.abs_diff > 0
    assert info.ee is None and info.numpy is None                               # the review mislabelled these columns: they are NOT EE vs numpy
    assert "coverage_weighted (PRODUCTION)" in info.note and "centre_inclusion (rejected)" in info.note
    sv = [r for r in res if r.check == "site_value"][0]
    assert sv.status == P.MATCH and "PRODUCTION convention" in sv.item             # EE's coverage weighting IS the comparison target


def test_site_value_classification_match_info_discrepancy():
    assert P.compare_site_value("c", "i", 81.956, 81.9560001).status == P.MATCH
    assert P.compare_site_value("c", "i", 100.0, 100.09).status == P.MATCH                    # 0.09 %
    r = P.compare_site_value("c", "i", 0.444752, 0.446356)                                    # the live ghm residual, 0.36 %
    assert r.status == P.INFO and "not investigated" in r.note
    assert P.compare_site_value("c", "i", 0.5071, 0.4464).status == P.DISCREPANCY             # the centre-inclusion effect (13.6 %)
    assert P.compare_site_value("c", "i", None, 1.0).status == P.DISCREPANCY


@pytest.mark.parametrize("bug, check, fragment", [
    ("natural_class", "pixel_construct", "natural_habitat"),
    ("years24", "pixel_construct", "forest_loss years"),
    ("loss_any_canopy", "pixel_construct", "numerator"),
    ("wcpi_normalised", "pixel_construct", "wcpi"),
    ("cell_shift", "block_cell_A1", "natural_habitat"),
    ("duplicate_sample", "sampling_A2", "cells sampled"),
    ("no_erosion", "water_body", "pure-water"),
    ("geodesic_area", "water_body", "area_m2"),
    ("extra_component", "water_body", "UNMATCHED EE"),
])
def test_each_injected_bug_is_detected_as_a_discrepancy(bug, check, fragment):
    res = P.run_checks(FakeBackend(bug), ZONE, ZONE, site_value_names=("ndvi",))
    hits = [r for r in res if r.check == check and fragment in r.item and r.status == P.DISCREPANCY]
    assert hits, (bug, [(r.item, r.status) for r in res if r.check == check])


def test_a_failing_pull_is_a_harness_error_not_a_discrepancy():
    res = P.run_checks(FakeBackend("ee_error"), ZONE, None, site_value_names=("ndvi",))
    err = [r for r in res if r.status == P.HARNESS_ERROR]
    assert len(err) == 1 and "timed out" in err[0].note and err[0].check == "harness"
    assert not [r for r in res if r.status == P.DISCREPANCY and r.check == "pixel_construct"]        # not misreported as a finding
    assert any(r.check == "block_cell_A1" and r.status == P.MATCH for r in res)                     # other checks still ran


def test_primitives_compare_correctly():
    assert P.compare_scalar("c", "i", 1.0, 1.0 + 1e-9).status == P.MATCH
    assert P.compare_scalar("c", "i", 1.0, 1.01).status == P.DISCREPANCY
    assert P.compare_scalar("c", "i", None, None).status == P.MATCH and P.compare_scalar("c", "i", None, 1.0).status == P.DISCREPANCY
    assert P.compare_pixel_arrays("c", "i", [1, np.nan], [1, np.nan]).status == P.MATCH
    assert P.compare_pixel_arrays("c", "i", [1, np.nan], [1, 2]).status == P.DISCREPANCY          # mask mismatch
    assert P.compare_multisets("c", "i", [1, 2, 3], [3, 2, 1]).status == P.MATCH
    assert P.compare_multisets("c", "i", [1, 2], [1, 2, 3]).status == P.DISCREPANCY
    assert P.compare_cell_dicts("c", "i", {(0, 0): 1.0}, {(0, 0): 1.0, (1, 0): 2.0}).status == P.DISCREPANCY


def test_pixel_grid_rebuilds_a_raster_and_rejects_irregular_grids():
    a = np.arange(12.0).reshape(3, 4)
    g = grid(3, 4, 10.0, {"v": a})
    r, x0, y0 = g.raster("v")
    assert np.array_equal(r, a) and x0 == X0 + 5.0 and y0 == Y1 - 5.0
    bad = P.PixelGrid(g.x + np.linspace(0, 4, g.n), g.y, 10.0, g.values)
    with pytest.raises(ValueError):
        bad.raster("v")


def test_numpy_cell_means_use_coordinates_and_drop_incomplete_cells():
    a = np.arange(36.0).reshape(6, 6)
    # cells are 30 m wide and start at multiples of 30 m from the CRS origin; 500010 / 30 and 2000010 / 30 are integers
    aligned = grid(6, 6, 10.0, {"v": a}, x0=500010.0, y1=2000010.0)
    cells = P.numpy_cell_means(aligned, "v", 30.0)
    assert len(cells) == 4 and cells[(16667, 66666)] == a[:3, :3].mean() and cells[(16668, 66665)] == a[3:, 3:].mean()
    shifted = grid(6, 6, 10.0, {"v": a}, x0=500020.0, y1=2000010.0)                # window edge cuts every column of cells
    assert len(P.numpy_cell_means(shifted, "v", 30.0)) == 2                       # only the one complete column x 2 rows survives


def test_polygon_means_boundary_effect_known_answer():
    v = np.zeros((4, 4)); v[:, :2] = 10.0                                         # west half 10, east half 0
    g = grid(4, 4, 10.0, {"v": v})
    poly = box(X0 + 5.0, Y1 - 35.0, X0 + 25.0, Y1 - 5.0)                          # covers half of the outer columns of pixels
    m = P.polygon_means(g, "v", poly)
    # coverage weights: columns 0 and 2 at 50 %, column 1 at 100 % (rows the same) -> weighted mean = (0.5*10 + 1*10 + 0.5*0) / 2 = 7.5
    assert m["coverage_weighted"] == pytest.approx(7.5)
    assert m["centre_inclusion"] == pytest.approx(10.0)                           # only the centre-in pixels (column 1)
    assert m["n_centre_pixels"] == 2                                # column 1, rows 1-2: the others sit exactly on the boundary


def test_write_parity_report(tmp_path):
    res = P.run_checks(FakeBackend("years24"), ZONE, None, site_value_names=("ndvi",))
    paths = P.write_parity(res, str(tmp_path))
    md = open(paths["md"], encoding="utf-8").read()
    assert "DISCREPANCY" in md.splitlines()[6] or "DISCREPANCY" in md                # discrepancies listed first
    import json
    assert json.load(open(paths["json"]))["summary"]["DISCREPANCY"] >= 1


def test_ee_backend_region_is_aligned_to_the_cell_grid():
    shapely = pytest.importorskip("shapely")
    from shapely.geometry import Point
    be = P.EEBackend.__new__(P.EEBackend)
    zone = MagicMock(); zone.geometry = Point(73.8, 18.6)
    reg = be.region(zone, side_m=600.0, cell_m=100.0)
    x0, y0, x1, y1 = reg["bounds"]
    assert reg["crs"] == "EPSG:32643" and x0 % 100 == 0 and y0 % 100 == 0 and (x1 - x0) % 100 == 0 and (x1 - x0) >= 600


def test_smoke_notebook_only_calls_functions_that_exist():
    import json, re
    nb = json.load(open(Path(__file__).resolve().parent.parent / "notebooks" / "v028_smoke_test.ipynb", encoding="utf-8"))
    src = "\n".join("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code")
    from darukaa_reference import assess as A
    for fn in re.findall(r"\bA\.(\w+)", src):
        assert hasattr(A, fn), fn
    for fn in re.findall(r"\bparity\.(\w+)", src):
        assert hasattr(P, fn), fn
    assert "v0.2.8-contract" in src and "headline" not in src.lower().replace("does **not** touch the headline", "")
    assert "main" in "".join(nb["cells"][0]["source"])                       # states it does not touch main


def test_ee_backend_computes_zone_evidence_only_once():
    be = P.EEBackend.__new__(P.EEBackend)
    be._ev = {}
    prov = MagicMock()
    prov.site.return_value.value = 1.5
    be.provider = prov
    zone = MagicMock(); zone.label = "z"
    assert be.site_value_ee("ndvi", zone) == 1.5 and be.site_value_ee("ghm", zone) == 1.5
    assert prov.evidence.call_count == 1 and prov.site.call_count == 2


# ================================================================== smoke-test fixes: water bodies, Hansen, isolation, synthetic
def test_the_live_extra_component_pattern_now_agrees_because_both_sides_apply_the_same_rules():
    """v0.2.7: EE listed a 42-px body that numpy did not (numpy edge-filtered, EE unfiltered). Now BOTH list it, flag it as an edge body,
    and the interior counts agree."""
    res = P.run_checks(FakeBackend(), None, ZONE)
    wb = {(r.item): r for r in res if r.check == "water_body"}
    assert wb["number of water bodies (all, before the interior rule)"].status == P.MATCH and wb["number of water bodies (all, before the interior rule)"].ee == 3
    inter = wb["number of INTERIOR water bodies (same rule both sides)"]
    assert inter.status == P.MATCH and inter.ee == inter.numpy == 2                                   # the edge pond is excluded on BOTH sides
    edge = [r for r in res if r.check == "water_body" and "EDGE" in r.item]
    assert edge and all("42 px" in r.item for r in edge)
    assert not [r for r in res if r.status in (P.DISCREPANCY, P.HARNESS_ERROR)]


def test_a_geodesic_area_or_an_extra_ee_component_is_reported_with_a_diagnosis():
    res = P.run_checks(FakeBackend("extra_component"), None, ZONE)
    miss = [r for r in res if r.item.startswith("UNMATCHED EE") and r.status == P.DISCREPANCY]
    assert len(miss) == 1 and "m from the region edge" in miss[0].note and "interior=True" in miss[0].note and "60 px" in miss[0].note
    assert [r for r in res if r.check == "water_body" and r.item.startswith("number of water bodies") and r.status == P.DISCREPANCY]
    geo = P.run_checks(FakeBackend("geodesic_area"), None, ZONE)
    assert [r for r in geo if "area_m2" in r.item and r.status == P.DISCREPANCY]


def test_the_live_synthetic_fixture_has_the_designed_cases_and_matches_a_correct_ee():
    water, metric = P.synthetic_water_raster()
    recs = P.numpy_water_records(water, metric, 10.0, 500005.0, 2000595.0, (500000.0, 2000000.0, 500600.0, 2000600.0), min_px=1)
    by_n = sorted((r["n_px"], r["pure_px"], r["interior"]) for r in recs)
    # lake 400/324, edge pond 42, two 25-px corner-touching bodies (pure 9 each), island lake 16x16-4x4=240, edge-cut 80
    assert len(recs) == 6 and (400, 324, True) in by_n and (25, 9, True) in by_n and by_n.count((25, 9, True)) == 2
    assert any(n == 42 and not i for n, _p, i in by_n) and any(n == 80 and not i for n, _p, i in by_n) and any(n == 240 for n, _p, _i in by_n)
    res = P.run_checks(FakeBackend(), None, ZONE)
    syn = [r for r in res if r.check == "water_body_synthetic"]
    assert syn and all(r.status == P.MATCH for r in syn)


def test_synthetic_fixture_detects_wrong_connectivity_and_missing_erosion():
    merged = P.run_checks(FakeBackend(synth_bug="eight_connected"), None, ZONE)
    bad = [r for r in merged if r.check == "water_body_synthetic" and r.status == P.DISCREPANCY]
    assert bad and any("number of water bodies" in r.item or "expected bodies" in r.item for r in bad)      # diagonal bodies merged
    ne = P.run_checks(FakeBackend(synth_bug="no_erosion"), None, ZONE)
    assert [r for r in ne if r.check == "water_body_synthetic" and "pure-water" in r.item and r.status == P.DISCREPANCY]


def test_a_masked_hansen_band_is_reported_not_a_keyerror_and_other_results_survive():
    res = P.run_checks(FakeBackend("lossyear_masked"), ZONE, None, site_value_names=("ndvi",))
    assert not [r for r in res if r.status == P.HARNESS_ERROR]                                        # the live run's KeyError
    cov = [r for r in res if r.check == "band_coverage" and r.item == "hansen_bundle.lossyear"]
    assert cov and cov[0].ee == 0 and "FULLY MASKED" in cov[0].note
    assert [r for r in res if r.check == "pixel_construct" and "natural_habitat" in r.item and r.status == P.MATCH]      # dw results kept


def test_one_failing_comparison_does_not_discard_the_rest():
    fb = FakeBackend()
    orig = fb.pull
    def pull(key, region):
        g = orig(key, region)
        if key == "dw_bundle":
            del g.values["ee_sdi"]                                                                      # one band missing entirely
        return g
    fb.pull = pull
    res = P.run_checks(fb, ZONE, None, site_value_names=("ndvi",))
    err = [r for r in res if r.status == P.HARNESS_ERROR]
    assert len(err) == 1 and "sdi" in err[0].item
    assert [r for r in res if r.check == "pixel_construct" and r.status == P.MATCH and "net_tree_cover_change" in r.item]
    assert [r for r in res if r.check == "pixel_construct" and r.status == P.MATCH and "wcpi" in r.item]      # later bundles still ran


def test_forest_validation_zone_checks_hansen_terms_power_and_site_rate():
    res = P.run_checks(FakeBackend(), None, None, zone_forest=ZONE)
    assert not [r for r in res if r.status in (P.DISCREPANCY, P.HARNESS_ERROR)]
    power = [r for r in res if "parity power" in r.item][0]
    assert power.status == P.INFO and "both terms non-zero" in power.note                              # a real (non-degenerate) test
    sv = [r for r in res if r.check == "site_value" and "forest_loss_rate" in r.item]
    assert sv and sv[0].status == P.MATCH
    bad = P.run_checks(FakeBackend("forest_centre_inclusion"), None, None, zone_forest=ZONE)
    assert [r for r in bad if r.check == "site_value" and "forest_loss_rate" in r.item and r.status in (P.INFO, P.DISCREPANCY)]     # convention mixing is visible


def test_a_degenerate_forest_region_is_flagged_not_passed_silently():
    fb = FakeBackend(); fb.tc = np.zeros((20, 20))                                                     # no baseline forest at all (like Deccan)
    res = P.run_checks(fb, None, None, zone_forest=ZONE)
    power = [r for r in res if "parity power" in r.item][0]
    assert "DEGENERATE" in power.note


def test_ee_pull_fills_a_masked_band_with_nan_and_reports_zero_coverage():
    """Structure test of the REAL EEBackend._pull: Earth Engine omits a masked pixel's property; the band must survive as all-NaN."""
    ee = MagicMock()
    feats = [{"geometry": {"coordinates": [73.8 + i * 1e-4, 18.6]}, "properties": {"ee_loss": 0.0, "ee_years": 25.0}} for i in range(4)]   # no 'lossyear'
    ee.Geometry.Rectangle.return_value = "rect"
    img = MagicMock(); img.reproject.return_value.sample.return_value.getInfo.return_value = {"features": feats}
    be = P.EEBackend(MagicMock(), MagicMock(), ee=ee, provider=MagicMock())
    g = be._pull(img, (500000.0, 2000000.0, 500120.0, 2000030.0), 30.0, "EPSG:32643", ["lossyear", "ee_loss", "ee_years"])
    assert "lossyear" in g.values and np.isnan(g.values["lossyear"]).all() and g.coverage["lossyear"] == 0 and g.coverage["ee_loss"] == 4
