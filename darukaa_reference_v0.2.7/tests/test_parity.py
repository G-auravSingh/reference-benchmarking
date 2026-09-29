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
    return P.PixelGrid(x, y, res, {k: np.asarray(v, float).ravel() for k, v in values.items()})


class FakeBackend:
    """bug in {None, 'natural_class', 'years24', 'loss_any_canopy', 'cell_shift', 'wcpi_normalised', 'no_erosion',
    'duplicate_sample', 'ee_error'}"""

    def __init__(self, bug=None):
        self.bug = bug
        rng = np.random.default_rng(5)
        self.dw = rng.choice([0, 1, 2, 3, 4, 5, 6, 7], (60, 60), p=[.05, .3, .15, .05, .2, .1, .1, .05]).astype(float)
        self.early = rng.choice([1, 2, 4], (60, 60)).astype(float)
        self.recent = np.where(rng.random((60, 60)) < .1, 1, self.early)
        self.red = np.where(rng.random((60, 60)) < .05, 0.2, rng.uniform(.02, .12, (60, 60)))
        self.ly = rng.integers(0, 26, (20, 20)).astype(float); self.tc = rng.uniform(0, 100, (20, 20))

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
            return grid(20, 20, 30.0, {"lossyear": self.ly, "treecover2000": self.tc, "ee_loss": num, "ee_baseline": den,
                                       "ee_years": np.full((20, 20), 24.0 if self.bug == "years24" else 25.0)})
        if key == "water_bundle":
            water = np.zeros((60, 60)); water[10:30, 10:30] = 1; water[36:50, 36:50] = 1          # both clear of the window edge
            metric = np.where(water > 0, 0.2, 0.01)
            self._water, self._metric = water, metric
            return grid(60, 60, 10.0, {"water": water, "metric": metric})
        raise KeyError(key)

    def pull_polygon(self, name, zone):
        vals = np.random.default_rng(8).uniform(0, 100, (60, 60))
        self._poly_vals = vals
        return grid(60, 60, 10.0, {"v": vals})

    def site_value_ee(self, name, zone):
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
        self.pull("water_bundle", region)
        units = S.label_units(self._water > 0, 100.0, min_area_m2=3000.0)
        pure = S.unit_masks(units, pure=(self.bug != "no_erosion"))
        vals = S.unit_values(self._metric, pure)
        return [{"area_m2": units.areas_m2[i], "pure_px": int(pure[i].sum()), "value": vals.get(i), "interior": True} for i in units.areas_m2]


ZONE = MagicMock()


def statuses(results, check=None):
    return {(r.check, r.item): r.status for r in results if check is None or r.check == check}


def test_consistent_ee_and_numpy_give_only_match_and_info():
    res = P.run_checks(FakeBackend(), ZONE, ZONE, parity_area_m2=1e4, site_value_names=("ndvi", "ghm"))
    bad = [(r.check, r.item, r.status, r.note) for r in res if r.status in (P.DISCREPANCY, P.HARNESS_ERROR)]
    assert bad == [], bad
    assert {r.check for r in res} >= {"pixel_construct", "block_cell_A1", "sampling_A2", "site_value", "boundary_weighting", "water_body"}
    assert sum(r.status == P.MATCH for r in res) >= 15


def test_boundary_weighting_is_quantified_not_hidden():
    res = P.run_checks(FakeBackend(), ZONE, None, site_value_names=("ndvi",))
    info = [r for r in res if r.check == "boundary_weighting"][0]
    assert info.status == P.INFO and info.abs_diff > 0 and "coverage-weighted" in info.note
    sv = [r for r in res if r.check == "site_value"][0]
    assert sv.status == P.MATCH                                                 # EE's coverage weighting IS the comparison target


@pytest.mark.parametrize("bug, check, fragment", [
    ("natural_class", "pixel_construct", "natural_habitat"),
    ("years24", "pixel_construct", "forest_loss years"),
    ("loss_any_canopy", "pixel_construct", "numerator"),
    ("wcpi_normalised", "pixel_construct", "wcpi"),
    ("cell_shift", "block_cell_A1", "natural_habitat"),
    ("duplicate_sample", "sampling_A2", "cells sampled"),
    ("no_erosion", "water_body", "pure-water"),
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
