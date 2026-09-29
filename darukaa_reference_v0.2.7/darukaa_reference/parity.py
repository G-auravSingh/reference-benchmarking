"""
parity.py -- Earth Engine vs numpy parity harness (v0.2.8 smoke test)
=====================================================================

Question answered: does the Earth Engine code compute the SAME thing as the numpy definitions that the
synthetic tests verify? It pulls small real rasters out of Earth Engine, recomputes each construct with the
numpy definition on those exact pixels, and reports every difference.

Statuses (never confused):
  MATCH          EE and numpy agree within the stated tolerance
  DISCREPANCY    they disagree: a real finding, to be reported before any further zone is run
  INFO           a quantified, expected difference (e.g. boundary-pixel weighting), reported not judged
  HARNESS_ERROR  the check itself failed to run (an exception): NOT evidence about the indicators

The numpy layer (PixelGrid, comparisons) is unit-tested offline, including that it DETECTS injected bugs.
The Earth Engine pulls (EEBackend) are structure-tested only: running them is the point of the smoke test.
"""
from __future__ import annotations

import json
import math
import os
import traceback
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from darukaa_reference import constructs as K
from darukaa_reference import reference_builders as R
from darukaa_reference import support as S

MATCH, DISCREPANCY, INFO, HARNESS_ERROR = "MATCH", "DISCREPANCY", "INFO", "HARNESS_ERROR"
MAX_PX_PER_CALL = 4000            # Earth Engine getInfo aborts above 5,000 elements


@dataclass
class ParityResult:
    check: str
    item: str
    status: str
    ee: Any = None
    numpy: Any = None
    abs_diff: Optional[float] = None
    rel_diff: Optional[float] = None
    tolerance: Optional[float] = None
    n: Optional[int] = None
    note: str = ""


# ----------------------------------------------------------------------------------------
# Comparison primitives (pure numpy, tested)
# ----------------------------------------------------------------------------------------
def compare_scalar(check, item, ee_value, np_value, rel_tol=1e-6, abs_tol=1e-9, note="") -> ParityResult:
    if ee_value is None or np_value is None:
        both = ee_value is None and np_value is None
        return ParityResult(check, item, MATCH if both else DISCREPANCY, ee_value, np_value, note=note or ("both undefined" if both else "one side undefined"))
    d = abs(float(ee_value) - float(np_value))
    rel = d / max(abs(float(np_value)), 1e-300)
    ok = d <= abs_tol or rel <= rel_tol
    return ParityResult(check, item, MATCH if ok else DISCREPANCY, float(ee_value), float(np_value), d, rel, rel_tol, note=note)


def compare_pixel_arrays(check, item, ee_vals, np_vals, tol=1e-9, note="") -> ParityResult:
    """Element-wise on aligned arrays; masked (NaN) must be masked on both sides."""
    a, b = np.asarray(ee_vals, float), np.asarray(np_vals, float)
    if a.shape != b.shape:
        return ParityResult(check, item, DISCREPANCY, a.shape, b.shape, note="shape differs: " + note)
    nan_a, nan_b = np.isnan(a), np.isnan(b)
    mask_mismatch = int((nan_a != nan_b).sum())
    both = ~nan_a & ~nan_b
    diff = np.abs(a[both] - b[both]) if both.any() else np.array([0.0])
    n_bad = int((diff > tol).sum()) + mask_mismatch
    return ParityResult(check, item, MATCH if n_bad == 0 else DISCREPANCY, float(np.nansum(a)), float(np.nansum(b)),
                        float(diff.max()), None, tol, int(a.size),
                        note=f"{n_bad} of {a.size} pixels differ ({mask_mismatch} mask mismatches). {note}".strip())


def compare_cell_dicts(check, item, ee_cells: Dict, np_cells: Dict, tol=1e-6, note="") -> ParityResult:
    """Cell id -> value; a cell present (unmasked) on one side only is a mismatch."""
    keys = set(ee_cells) | set(np_cells)
    bad, worst = 0, 0.0
    for k in keys:
        a, b = ee_cells.get(k), np_cells.get(k)
        if a is None or b is None or (isinstance(b, float) and math.isnan(b)) and not (isinstance(a, float) and math.isnan(a)):
            if not (a is None and b is None):
                bad += 1
            continue
        d = abs(a - b)
        worst = max(worst, d)
        bad += d > tol
    return ParityResult(check, item, MATCH if bad == 0 else DISCREPANCY, len(ee_cells), len(np_cells), worst, None, tol, len(keys),
                        note=f"{bad} of {len(keys)} cells differ or are present on one side only. {note}".strip())


def compare_multisets(check, item, ee_vals, np_vals, tol=1e-6, note="") -> ParityResult:
    a, b = np.sort(np.asarray(ee_vals, float)), np.sort(np.asarray(np_vals, float))
    if a.size != b.size:
        return ParityResult(check, item, DISCREPANCY, int(a.size), int(b.size), n=max(a.size, b.size),
                            note=f"different number of values: EE {a.size} vs numpy {b.size}. {note}".strip())
    d = float(np.abs(a - b).max()) if a.size else 0.0
    return ParityResult(check, item, MATCH if d <= tol else DISCREPANCY, float(a.sum()), float(b.sum()), d, None, tol, int(a.size), note=note)


# ----------------------------------------------------------------------------------------
# Pixel grid rebuilt from pulled pixel centres
# ----------------------------------------------------------------------------------------
@dataclass
class PixelGrid:
    x: np.ndarray                      # pixel-centre easting (m, in the site's UTM zone)
    y: np.ndarray
    res: float
    values: Dict[str, np.ndarray]      # band -> values, NaN where masked

    @property
    def n(self) -> int:
        return int(self.x.size)

    def cell_ids(self, cell_m: float) -> Tuple[np.ndarray, np.ndarray]:
        return np.floor(self.x / cell_m).astype(int), np.floor(self.y / cell_m).astype(int)

    def raster(self, band: str) -> Tuple[np.ndarray, float, float]:
        """(2-D array north-up, x0 = west centre, y0 = north centre). Requires a regular grid."""
        ix = np.round((self.x - self.x.min()) / self.res).astype(int)
        iy = np.round((self.y.max() - self.y) / self.res).astype(int)
        if np.abs(self.x - (self.x.min() + ix * self.res)).max() > 0.01 * self.res or \
                np.abs(self.y - (self.y.max() - iy * self.res)).max() > 0.01 * self.res:
            raise ValueError("pulled pixel centres do not form a regular grid of the stated resolution")
        arr = np.full((iy.max() + 1, ix.max() + 1), np.nan)
        arr[iy, ix] = self.values[band]
        return arr, float(self.x.min()), float(self.y.max())


def numpy_cell_means(grid: PixelGrid, band: str, cell_m: float, min_coverage: float = 0.9, sum_instead: bool = False) -> Dict:
    """The numpy definition of a cell value, grouped by cell id from pixel-centre coordinates (no offset guesswork).
    Only cells whose every pixel was pulled are returned (edge cells are incomplete in a pulled window)."""
    k = int(round(cell_m / grid.res))
    cx, cy = grid.cell_ids(cell_m)
    v = grid.values[band]
    acc: Dict[Tuple[int, int], List[float]] = {}
    tot: Dict[Tuple[int, int], int] = {}
    for i in range(grid.n):
        key = (int(cx[i]), int(cy[i]))
        tot[key] = tot.get(key, 0) + 1
        if np.isfinite(v[i]):
            acc.setdefault(key, []).append(float(v[i]))
    out = {}
    for key, n_all in tot.items():
        if n_all < k * k:
            continue                                           # incomplete cell in the pulled window
        vals = acc.get(key, [])
        if sum_instead:
            out[key] = float(np.sum(vals))
        elif vals and len(vals) / (k * k) >= min_coverage:
            out[key] = float(np.mean(vals))
    return out


def polygon_means(grid: PixelGrid, band: str, polygon_utm) -> Dict[str, Optional[float]]:
    """Site aggregation two ways: pixel-centre inclusion (the numpy definition) and coverage-weighted (how an Earth
    Engine reduceRegion(mean) weights boundary pixels). Their difference is the boundary-weighting effect."""
    from shapely.geometry import box
    v = grid.values[band]
    h = grid.res / 2.0
    w_num = w_den = c_num = c_den = 0.0
    for i in range(grid.n):
        if not np.isfinite(v[i]):
            continue
        cell = box(grid.x[i] - h, grid.y[i] - h, grid.x[i] + h, grid.y[i] + h)
        frac = cell.intersection(polygon_utm).area / cell.area if cell.intersects(polygon_utm) else 0.0
        if frac > 0:
            w_num += frac * v[i]; w_den += frac
        if polygon_utm.contains(cell.centroid):
            c_num += v[i]; c_den += 1
    return {"coverage_weighted": (w_num / w_den) if w_den else None, "centre_inclusion": (c_num / c_den) if c_den else None,
            "n_centre_pixels": int(c_den)}


# ----------------------------------------------------------------------------------------
# Checks (each takes a Backend; the numpy side is computed HERE, from pixels the backend pulled)
# ----------------------------------------------------------------------------------------
def check_pixel_constructs(be, region) -> List[ParityResult]:
    """EE per-pixel construct vs the numpy formula applied to the raw inputs pulled with it."""
    out: List[ParityResult] = []
    g = be.pull("dw_bundle", region)                                     # 10 m
    dw = g.values["dw_label"]
    out.append(compare_pixel_arrays("pixel_construct", "natural_habitat", g.values["ee_natural_habitat"], R.natural_binary(dw) * 100.0, 1e-9))
    out.append(compare_pixel_arrays("pixel_construct", "riparian_natural_veg (natural cover)", g.values["ee_natural_veg"], R.natural_binary(dw), 1e-9))
    arr, _, _ = g.raster("dw_label")
    sdi_np = R.sdi_pixel_disturbed(arr)
    ee_sdi, _, _ = g.raster("ee_sdi")
    out.append(compare_pixel_arrays("pixel_construct", "sdi disturbed (interior; shore-edge proxy uses neighbours)",
                                    ee_sdi[1:-1, 1:-1], sdi_np[1:-1, 1:-1], 1e-9))
    dt = float(g.values["dt_years"][0])
    net_np = R.tree_share_change_pp_per_year(g.values["dw_early"], g.values["dw_recent"], dt)
    out.append(compare_pixel_arrays("pixel_construct", "net_tree_cover_change (pp/yr)", g.values["ee_net_change"], net_np, 1e-9))
    s2 = be.pull("s2_bundle", region)
    out.append(compare_pixel_arrays("pixel_construct", "wcpi raw 1/(TSM+1)", s2.values["ee_wcpi"], R.wcpi_pixel(s2.values["red"]), 1e-9,
                                    "numpy Nechad formula on the pulled B4 composite"))
    h = be.pull("hansen_bundle", region)                                 # 30 m
    num_np, den_np, years = R.forest_loss_terms(np.nan_to_num(h.values["lossyear"]), np.nan_to_num(h.values["treecover2000"]), 1, 25)
    out.append(compare_pixel_arrays("pixel_construct", "forest_loss numerator (loss inside >=30% baseline)", np.nan_to_num(h.values["ee_loss"]), num_np, 1e-9))
    out.append(compare_pixel_arrays("pixel_construct", "forest_loss denominator (>=30% baseline)", np.nan_to_num(h.values["ee_baseline"]), den_np, 1e-9))
    out.append(ParityResult("pixel_construct", "forest_loss years", MATCH if int(h.values["ee_years"][0]) == years == 25 else DISCREPANCY,
                            int(h.values["ee_years"][0]), years, note="inclusive 2001-2025 window"))
    return out


def check_block_cells(be, region, site_area_m2: float) -> List[ParityResult]:
    """A1: EE reduceResolution+reproject cells vs numpy block means of the very pixels EE reports."""
    out: List[ParityResult] = []
    cell_m = S.cell_size_px(site_area_m2, 10.0) * 10.0
    g = be.pull("dw_bundle", region)
    for key, band, ee_key in (("natural_habitat (cell proportion, %)", "ee_natural_habitat", "natural_habitat"),
                              ("net_tree_cover_change (cell mean, pp/yr)", "ee_net_change", "net_tree_cover_change_rate")):
        ee_cells = be.cells_ee(ee_key, region, site_area_m2)
        np_cells = numpy_cell_means(g, band, cell_m)
        common = {k: v for k, v in ee_cells.items() if k in np_cells}
        r = compare_cell_dicts("block_cell_A1", key, {k: ee_cells.get(k) for k in np_cells}, np_cells, 1e-6,
                               f"cell {cell_m:g} m ({int(cell_m / 10)}x{int(cell_m / 10)} px); numpy = mean of the EE-reported native pixels")
        out.append(r)
    return out


def check_sampling(be, region, site_area_m2: float) -> List[ParityResult]:
    """A2: the REAL cell_reference_ee sampler returns each valid cell once (multiset equals the numpy cells)."""
    out: List[ParityResult] = []
    g = be.pull("dw_bundle", region)
    cell_m = S.cell_size_px(site_area_m2, 10.0) * 10.0
    np_cells = numpy_cell_means(g, "ee_natural_habitat", cell_m)
    ee_vals = be.sampled_cells_ee("natural_habitat", region, site_area_m2)
    out.append(compare_multisets("sampling_A2", "natural_habitat cells sampled by cell_reference_ee", ee_vals, list(np_cells.values()), 1e-6,
                                 "every valid cell exactly once, none masked, none twice"))
    return out


def check_site_values(be, zone, names: Sequence[str]) -> List[ParityResult]:
    """Site value: the provider's EE number vs numpy aggregations of pixels pulled over the polygon."""
    out: List[ParityResult] = []
    poly = be.polygon_utm(zone)
    for name in names:
        ee_val = be.site_value_ee(name, zone)
        g = be.pull_polygon(name, zone)
        m = polygon_means(g, "v", poly)
        out.append(compare_scalar("site_value", f"{name} (EE reduceRegion vs numpy coverage-weighted mean)", ee_val, m["coverage_weighted"],
                                  rel_tol=1e-4, abs_tol=1e-9, note=f"{m['n_centre_pixels']} centre pixels"))
        if m["centre_inclusion"] is not None and m["coverage_weighted"] is not None:
            d = abs(m["centre_inclusion"] - m["coverage_weighted"])
            out.append(ParityResult("boundary_weighting", name, INFO, m["coverage_weighted"], m["centre_inclusion"], d,
                                    d / max(abs(m["centre_inclusion"]), 1e-300), None, m["n_centre_pixels"],
                                    "pixel-centre inclusion (numpy definition) vs coverage-weighted (EE): the effect of boundary pixels"))
    return out


def check_water_bodies(be, region) -> List[ParityResult]:
    """EE per-water-body records vs numpy label_units / pure water / unit_values on the same pulled pixels."""
    out: List[ParityResult] = []
    g = be.pull("water_bundle", region)
    water_arr, _, _ = g.raster("water")
    metric_arr, _, _ = g.raster("metric")
    res = g.res
    water = np.nan_to_num(water_arr) > 0
    units = S.label_units(water, res * res, min_area_m2=30 * res * res)
    pure = S.unit_masks(units, pure=True)
    vals = S.unit_values(metric_arr, pure)
    edge = np.zeros_like(water); edge[:2, :] = edge[-2:, :] = True; edge[:, :2] = edge[:, -2:] = True
    inner = [i for i in units.areas_m2 if not (units.labels == i)[edge].any()]      # bodies clear of the pulled window's edge
    np_recs = sorted((round(units.areas_m2[i]), int(pure[i].sum()), round(vals.get(i, float("nan")), 6)) for i in inner)
    ee_recs = be.water_units_ee(region)
    ee_inner = sorted((round(r["area_m2"]), int(r["pure_px"]), round(r["value"], 6) if r["value"] is not None else float("nan")) for r in ee_recs
                      if r.get("interior", True))
    out.append(ParityResult("water_body", "number of interior water bodies", MATCH if len(np_recs) == len(ee_inner) else DISCREPANCY,
                            len(ee_inner), len(np_recs), note=f"numpy {np_recs} vs EE {ee_inner}"))
    if len(np_recs) == len(ee_inner) and np_recs:
        a = np.array([[r[0], r[1], r[2]] for r in ee_inner], float)
        b = np.array([[r[0], r[1], r[2]] for r in np_recs], float)
        for j, nm, tol in ((0, "area_m2 (within 1 pixel)", res * res), (1, "pure-water pixel count", 0.5), (2, "unit metric value", 1e-5)):
            out.append(compare_pixel_arrays("water_body", nm, a[:, j], b[:, j], tol))
    return out


# ----------------------------------------------------------------------------------------
# Runner
# ----------------------------------------------------------------------------------------
def _safe(name: str, fn: Callable[[], List[ParityResult]]) -> List[ParityResult]:
    try:
        return fn()
    except Exception as e:                                             # a failing harness is NOT a finding about the indicators
        return [ParityResult("harness", name, HARNESS_ERROR, note=f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}")]


def run_checks(be, zone_terrestrial=None, zone_aquatic=None, parity_area_m2: float = 1.0e4,
               site_value_names: Sequence[str] = ("natural_habitat", "net_tree_cover_change_rate", "ndvi", "ghm", "hdi")) -> List[ParityResult]:
    res: List[ParityResult] = []
    if zone_terrestrial is not None:
        region = be.region(zone_terrestrial, side_m=600.0, cell_m=S.cell_size_px(parity_area_m2, 10.0) * 10.0)
        res += _safe("pixel constructs", lambda: check_pixel_constructs(be, region))
        res += _safe("block cells (A1)", lambda: check_block_cells(be, region, parity_area_m2))
        res += _safe("cell sampling (A2)", lambda: check_sampling(be, region, parity_area_m2))
        res += _safe("site values (terrestrial)", lambda: check_site_values(be, zone_terrestrial, site_value_names))
    if zone_aquatic is not None:
        region = be.region(zone_aquatic, side_m=700.0, cell_m=10.0)
        res += _safe("water bodies", lambda: check_water_bodies(be, region))
    return res


def write_parity(results: Sequence[ParityResult], out_dir: str, stem: str = "parity") -> Dict[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    cnt = {s: sum(r.status == s for r in results) for s in (MATCH, DISCREPANCY, INFO, HARNESS_ERROR)}
    pj, pm = os.path.join(out_dir, f"{stem}.json"), os.path.join(out_dir, f"{stem}.md")
    with open(pj, "w", encoding="utf-8") as f:
        json.dump({"summary": cnt, "results": [asdict(r) for r in results]}, f, indent=1, default=str)
    with open(pm, "w", encoding="utf-8") as f:
        f.write(f"# EE vs numpy parity\n\nSummary: {cnt}\n\n| status | check | item | EE | numpy | max abs diff | note |\n|---|---|---|---|---|---|---|\n")
        for r in sorted(results, key=lambda r: (r.status != DISCREPANCY, r.status != HARNESS_ERROR, r.check)):
            f.write(f"| {r.status} | {r.check} | {r.item} | {r.ee if not isinstance(r.ee, float) else f'{r.ee:.6g}'} | "
                    f"{r.numpy if not isinstance(r.numpy, float) else f'{r.numpy:.6g}'} | "
                    f"{'' if r.abs_diff is None else f'{r.abs_diff:.3g}'} | {r.note.splitlines()[0][:160] if r.note else ''} |\n")
    return {"json": pj, "md": pm}


# ----------------------------------------------------------------------------------------
# Earth Engine backend (structure-tested only; running it IS the live parity test)
# ----------------------------------------------------------------------------------------
class EEBackend:
    def __init__(self, config, registry, ee=None, provider=None, log=print):
        if ee is None:
            import ee as _ee
            ee = _ee
        from darukaa_reference import assess as A
        self.ee, self.config, self.registry, self.log = ee, config, registry, log
        self.provider = provider or A.EEProvider(config, registry, ee=ee, log=log)
        self._ev: Dict[str, Any] = {}

    # ---- geometry helpers
    def _crs_for(self, zone) -> str:
        c = zone.geometry.centroid
        return S.utm_crs_for(c.x, c.y)

    def polygon_utm(self, zone):
        import pyproj
        from shapely.ops import transform
        t = pyproj.Transformer.from_crs("EPSG:4326", self._crs_for(zone), always_xy=True)
        return transform(t.transform, zone.geometry)

    def region(self, zone, side_m: float, cell_m: float):
        import pyproj
        crs = self._crs_for(zone)
        t = pyproj.Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        c = zone.geometry.centroid
        x, y = t.transform(c.x, c.y)
        half = math.floor(side_m / cell_m / 2.0) * cell_m
        x0, y0 = math.floor(x / cell_m) * cell_m - half, math.floor(y / cell_m) * cell_m - half
        return {"crs": crs, "bounds": (x0, y0, x0 + 2 * half + cell_m, y0 + 2 * half + cell_m)}

    # ---- pixel pulls
    def _pull(self, image, bounds, native: float, crs: str) -> PixelGrid:
        import pyproj
        ee = self.ee
        proj = S.ee_native_projection(ee, native, crs)
        img = image.reproject(proj)
        x0, y0, x1, y1 = bounds
        ncols = max(1, int(round((x1 - x0) / native)))
        rows = max(1, MAX_PX_PER_CALL // ncols)
        t = pyproj.Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        xs, ys, cols = [], [], {}
        yy = y0
        while yy < y1 - 1e-6:
            yt = min(y1, yy + rows * native)
            rect = ee.Geometry.Rectangle([x0, yy, x1, yt], proj=crs, geodesic=False)
            feats = img.sample(region=rect, projection=proj, dropNulls=False, geometries=True).getInfo()["features"]
            for f in feats:
                lon, lat = f["geometry"]["coordinates"]
                x, y = t.transform(lon, lat)
                xs.append(x); ys.append(y)
                for k, v in f["properties"].items():
                    cols.setdefault(k, {})[len(xs) - 1] = v
            yy = yt
        n = len(xs)
        vals = {k: np.array([d.get(i, np.nan) if d.get(i) is not None else np.nan for i in range(n)], float) for k, d in cols.items()}
        return PixelGrid(np.array(xs), np.array(ys), native, vals)

    def pull(self, key: str, region) -> PixelGrid:
        import darukaa_reference.indicators as I
        from darukaa_reference import reference_builders_ee as RB
        ee, cfg = self.ee, self.config
        crs, bounds = region["crs"], region["bounds"]
        if key == "dw_bundle":
            early, recent, dt = I._net_change_periods(cfg)
            bands = [I._dw_mode(cfg).rename("dw_label"), I._img_natural_habitat(cfg).rename("ee_natural_habitat"),
                     I._img_natural_veg(cfg).rename("ee_natural_veg"), I._img_sdi(cfg).rename("ee_sdi"),
                     I._dw_period_label(*early).rename("dw_early"), I._dw_period_label(*recent).rename("dw_recent"),
                     I._img_net_tree_cover_change(cfg).rename("ee_net_change"), ee.Image.constant(dt).rename("dt_years")]
            return self._pull(ee.Image.cat(bands), bounds, 10.0, crs)
        if key == "s2_bundle":
            comp = I._s2_masked(cfg).median()
            return self._pull(ee.Image.cat([comp.select("B4").rename("red"), I._img_wcpi(cfg).rename("ee_wcpi")]), bounds, 10.0, crs)
        if key == "hansen_bundle":
            num, den, years = I._forest_loss_terms_image(cfg)
            gfc = ee.Image("UMD/hansen/global_forest_change_2025_v1_13")
            img = ee.Image.cat([gfc.select("lossyear").rename("lossyear"), gfc.select("treecover2000").rename("treecover2000"),
                                num.rename("ee_loss"), den.rename("ee_baseline"), ee.Image.constant(years).rename("ee_years")])
            return self._pull(img, bounds, 30.0, crs)
        if key == "water_bundle":
            wm = RB.water_mask_s2(I._s2_masked(cfg).median()).rename("water")
            return self._pull(ee.Image.cat([wm, I._img_wcpi(cfg).rename("metric")]), bounds, 10.0, crs)
        raise KeyError(key)

    def pull_polygon(self, name: str, zone) -> PixelGrid:
        c = __import__("darukaa_reference.indicator_contract", fromlist=["CONTRACTS"]).CONTRACTS[name]
        native, crs = float(c.native_resolution_m), self._crs_for(zone)
        poly = self.polygon_utm(zone)
        x0, y0, x1, y1 = poly.bounds
        b = (math.floor(x0 / native) * native - native, math.floor(y0 / native) * native - native,
             math.ceil(x1 / native) * native + native, math.ceil(y1 / native) * native + native)
        img = self.provider._img(name).select(0).rename("v")
        return self._pull(img, b, native, crs)

    # ---- EE values
    def site_value_ee(self, name: str, zone):
        if zone.label not in self._ev:                     # evidence (incl. the water-body probe) once per zone
            self._ev[zone.label] = self.provider.evidence(zone)
        r = self.provider.site(name, zone, self._ev[zone.label])
        return None if r is None else r.value

    def _cell_image(self, key: str, site_area_m2: float, crs: str):
        import darukaa_reference.indicators as I
        ee = self.ee
        img = I._img_natural_habitat(self.config) if key == "natural_habitat" else I._img_net_tree_cover_change(self.config)
        return S.ee_block_mean_image(ee, img, 10.0, site_area_m2, crs)

    def cells_ee(self, key: str, region, site_area_m2: float) -> Dict:
        import pyproj
        ee, crs = self.ee, region["crs"]
        cell_px = S.cell_size_px(site_area_m2, 10.0)
        cell_m = cell_px * 10.0
        cell_proj = S.ee_native_projection(ee, cell_m, crs)
        img = self._cell_image(key, site_area_m2, crs)
        x0, y0, x1, y1 = region["bounds"]
        rect = ee.Geometry.Rectangle([x0, y0, x1, y1], proj=crs, geodesic=False)
        feats = img.sample(region=rect, projection=cell_proj, dropNulls=True, geometries=True).getInfo()["features"]
        t = pyproj.Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        out = {}
        for f in feats:
            x, y = t.transform(*f["geometry"]["coordinates"])
            v = next(iter(f["properties"].values()))
            if v is not None:
                out[(int(math.floor(x / cell_m)), int(math.floor(y / cell_m)))] = float(v)
        return out

    def sampled_cells_ee(self, key: str, region, site_area_m2: float) -> np.ndarray:
        from darukaa_reference import reference_builders_ee as RB
        ee, crs = self.ee, region["crs"]
        x0, y0, x1, y1 = region["bounds"]
        rect = ee.Geometry.Rectangle([x0, y0, x1, y1], proj=crs, geodesic=False)
        ref = RB.cell_reference_ee(ee, cell_image=self._cell_image(key, site_area_m2, crs), region=rect, native_scale_m=10.0,
                                   site_area_m2=site_area_m2, crs=crs, n=5000, seed=int(getattr(self.config, "reference_sample_seed", 12345)),
                                   support="site_window_proportion", construct=key, unit="u", temporal="t",
                                   population="regional_ecoregion", tier="tier1", population_definition="parity region")
        return ref.values

    def water_units_ee(self, region) -> List[Dict]:
        import darukaa_reference.indicators as I
        from darukaa_reference import reference_builders_ee as RB
        ee, cfg, crs = self.ee, self.config, region["crs"]
        x0, y0, x1, y1 = region["bounds"]
        rect = ee.Geometry.Rectangle([x0, y0, x1, y1], proj=crs, geodesic=False)
        wm = RB.water_mask_s2(I._s2_masked(cfg).median())
        recs = RB.unit_records_ee(ee, region=rect, water_mask=wm, metric_image=I._img_wcpi(cfg), kind="water", native_scale_m=10.0,
                                  permanence_image=None, min_area_m2=30 * 100.0, crs=crs)
        return recs


def run_parity(config, registry, zone_terrestrial, zone_aquatic=None, out_dir: str = "outputs/smoke", parity_area_m2: float = 1.0e4,
               backend=None, log=print) -> List[ParityResult]:
    be = backend or EEBackend(config, registry, log=log)
    results = run_checks(be, zone_terrestrial, zone_aquatic, parity_area_m2)
    paths = write_parity(results, out_dir)
    cnt = {s: sum(r.status == s for r in results) for s in (MATCH, DISCREPANCY, INFO, HARNESS_ERROR)}
    log(f"Parity summary: {cnt}\nWritten: {paths}")
    for r in results:
        if r.status in (DISCREPANCY, HARNESS_ERROR):
            log(f"  {r.status}: {r.check} / {r.item}: {r.note.splitlines()[0] if r.note else ''}")
    return results
