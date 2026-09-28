"""
Synthetic tests for the comparison-unit framework (v0.2.8 Phase 2).

Every test constructs a landscape where the TRUE answer is known analytically and checks
that the framework recovers it -- and, where instructive, that the v0.2.7 single-pixel
reference does NOT (audit defect X1).
"""
import math
import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from darukaa_reference import support as S

RNG = np.random.default_rng(20260928)


# ------------------------------------------------------------------ geometry & spacing
def test_window_radius_gives_site_equal_area():
    for a in (1e4, 4.01e5, 7.3e7):
        r = S.site_window_radius_m(a)
        assert math.isclose(math.pi * r * r, a, rel_tol=1e-12)


def test_sampling_spacing_prevents_overlap_and_pixel_reuse():
    # fine product, large site: spacing = window diameter
    assert S.sampling_spacing_m(10, 4.01e5) == pytest.approx(2 * S.site_window_radius_m(4.01e5))
    # coarse product, small site: spacing = native pixel (a coarse cell is never sampled twice)
    assert S.sampling_spacing_m(4638.3, 1e4) == 4638.3
    assert S.sampling_spacing_m(300, 1e4) == 300


def test_site_support_rule():
    assert S.site_support_ok(4.01e5, 10, 10) is True           # 4,010 S2 pixels
    assert S.site_support_ok(4.01e5, 300, 10) is False         # 4.5 EII pixels
    assert S.site_support_ok(1e4, 4638.3, 10) is False         # fraction of one TerraClimate cell
    assert S.site_support_ok(1e4, 4638.3, None) is True        # rule not applied (pressures)


def test_disk_kernel_area_matches_circle():
    for r in (5, 12.5, 30):
        k = S.disk_kernel(r)
        assert abs(k.sum() - math.pi * r * r) / (math.pi * r * r) < 0.05


# ------------------------------------------------------------- proportions (binary input)
def test_binary_proportion_reference_recovers_regional_proportion_and_has_spread():
    p = 0.3
    land = (RNG.random((600, 600)) < p).astype(float)
    win = S.window_mean(land, None, radius_px=10)
    vals = S.grid_sample(win, spacing_px=21)
    assert vals.size > 500
    assert abs(vals.mean() - p) < 0.01                       # unbiased for the regional proportion
    k = S.disk_kernel(10).sum()
    assert abs(vals.std() - math.sqrt(p * (1 - p) / k)) < 0.006   # binomial window SD
    # v0.2.7 pixel reference: median is 0 and MAD is 0 -> no usable distribution
    pix = land.ravel()
    assert np.median(pix) == 0.0 and np.median(np.abs(pix - np.median(pix))) == 0.0


def test_site_proportion_is_placed_correctly_in_window_distribution():
    p = 0.5
    land = (RNG.random((500, 500)) < p).astype(float)
    vals = S.grid_sample(S.window_mean(land, None, radius_px=8), spacing_px=17)
    # a site at the regional proportion sits near the 50th percentile, not at the 0th/100th
    pct = (vals < 0.5).mean() * 100
    assert 35 < pct < 65


# ------------------------------------------------------------- continuous input
def test_continuous_window_sd_matches_theory_and_pixel_sd_is_wrong_support():
    mu, sd = 0.45, 0.12
    ndvi = RNG.normal(mu, sd, (600, 600))
    r = 10
    k = S.disk_kernel(r).sum()
    vals = S.grid_sample(S.window_mean(ndvi, None, r), spacing_px=21)
    assert abs(vals.mean() - mu) < 0.005
    assert abs(vals.std() - sd / math.sqrt(k)) < 0.0015        # SD of site-sized means
    assert ndvi.std() / vals.std() > 10                        # pixel SD overstates spread >10x


def test_window_uses_valid_pixels_only_and_drops_low_coverage_windows():
    img = np.full((100, 100), 5.0)
    valid = np.ones((100, 100), bool)
    valid[:, :50] = False                                     # left half masked
    img[~valid] = 999.0                                       # masked values must never leak
    win = S.window_mean(img, valid, radius_px=5, min_coverage=0.9)
    finite = win[np.isfinite(win)]
    assert np.allclose(finite, 5.0)
    assert np.isnan(win[50, 48]) and np.isnan(win[50, 52])     # straddling windows dropped
    assert np.isfinite(win[50, 60])


# ------------------------------------------------------------- rates (num/den aggregation)
def test_rate_is_ratio_of_sums_not_mean_of_pixel_rates():
    # two halves: dense forest with little loss, sparse forest with heavy loss
    den = np.zeros((40, 40)); num = np.zeros((40, 40))
    den[:, :20] = 1.0; num[:2, :20] = 1.0        # 800 forest px, 40 lost
    den[:4, 20:] = 1.0; num[:2, 20:] = 1.0       # 80 forest px, 40 lost
    poly = np.ones((40, 40), bool)
    years = 5.0
    true_rate = (40 + 40) / (800 + 80) * 100 / years
    assert S.polygon_rate(num, den, poly, years) == pytest.approx(true_rate)
    # mean of the two halves' rates is a different (wrong) number
    mean_of_rates = ((40 / 800) + (40 / 80)) / 2 * 100 / years
    assert abs(mean_of_rates - true_rate) > 1.0


def test_window_rate_matches_polygon_rate_for_identical_support_and_floor_applies():
    den = (RNG.random((300, 300)) < 0.6).astype(float)
    num = den * (RNG.random((300, 300)) < 0.1)
    r = 12
    k = S.disk_kernel(r)
    c = (150, 150)
    n = k.shape[0] // 2
    poly = np.zeros_like(den, bool)
    poly[c[0] - n:c[0] + n + 1, c[1] - n:c[1] + n + 1] = k.astype(bool)
    site = S.polygon_rate(num, den, poly, years=24)
    ref = S.window_rate(num, den, r, years=24)
    assert ref[c] == pytest.approx(site, rel=1e-9)             # identical unit -> identical value
    # 5 ha floor with 30 m pixels: windows with < 5 ha of baseline forest are excluded
    sparse = np.zeros((300, 300)); sparse[150, 150] = 1.0
    out = S.window_rate(sparse * 0, sparse, r, years=24, pixel_area_m2=900, min_denominator_area_m2=5e4)
    assert np.isnan(out[150, 150])
    assert S.polygon_rate(sparse * 0, sparse, poly, 24, 900, 5e4) is None


def test_rate_reference_has_rate_units_not_year_codes():
    den = np.ones((300, 300))
    num = (RNG.random((300, 300)) < 0.10).astype(float)      # 10 % of forest lost over 24 years
    rate = S.window_rate(num, den, radius_px=20, years=24)
    vals = S.grid_sample(rate, spacing_px=41)
    assert vals.size > 20 and np.all((vals >= 0) & (vals <= 100 / 24))   # %/yr, never a year code
    assert vals.mean() == pytest.approx(10 / 24, rel=0.05)


def test_windows_extending_past_the_region_edge_are_dropped():
    rate = S.window_rate(np.zeros((200, 200)), np.ones((200, 200)), radius_px=200, years=24)
    assert np.isnan(rate).all()                                # never a partial-area "site window"


# ------------------------------------------------------------- water bodies & rings
def _lakes():
    w = np.zeros((120, 120), bool)
    w[10:20, 10:20] = True        # 100 px
    w[40:60, 40:60] = True        # 400 px
    w[90:94, 90:94] = True        # 16 px
    return w


def test_water_bodies_identified_with_exact_areas_and_min_area():
    u = S.label_units(_lakes(), pixel_area_m2=100.0)
    assert sorted(u.areas_m2.values()) == [1600.0, 10000.0, 40000.0]
    u2 = S.label_units(_lakes(), pixel_area_m2=100.0, min_area_m2=5000.0)
    assert sorted(u2.areas_m2.values()) == [10000.0, 40000.0]


def test_pure_water_removes_mixed_shoreline_pixels():
    body = np.zeros((30, 30), bool); body[5:15, 5:15] = True
    assert S.pure_water(body, 1).sum() == 8 * 8
    tiny = np.zeros((10, 10), bool); tiny[4:6, 4:6] = True
    assert S.pure_water(tiny, 1).sum() == 0                    # a 2x2 pond has no pure water


def test_water_metric_is_computed_over_the_unit_mask_only():
    w = _lakes()
    vals = np.where(w, 0.02, 0.9)                             # land "blooms" (0.9), water is 0.02
    u = S.label_units(w)
    out = S.unit_values(vals, S.unit_masks(u, pure=True))
    assert all(v == pytest.approx(0.02) for v in out.values())  # no land contamination (sabf fix)


def test_units_matched_on_size_and_permanence():
    w = _lakes()
    u = S.label_units(w, pixel_area_m2=1.0)
    ids = {int(a): i for i, a in u.areas_m2.items()}
    assert S.match_units(u, target_area_m2=120, size_factor=3.0) == [ids[100]]
    perm = np.where(w, 1.0, 0.0)
    perm[40:60, 40:60] = 0.3                                   # the 400-px body is seasonal
    got = S.match_units(u, target_area_m2=200, size_factor=3.0, permanence=perm, target_permanence=1.0)
    assert got == [ids[100]]
    assert S.match_units(u, 200, 3.0, exclude_ids=[ids[100]]) == [ids[400]]


def test_riparian_ring_geometry_and_excludes_water():
    w = np.zeros((60, 60), bool); w[20:30, 20:30] = True
    u = S.label_units(w)
    ring = S.ring_masks(u, width_px=3)[1]
    assert ring.sum() == 16 * 16 - 10 * 10                     # square dilation, analytic count
    assert not (ring & w).any()


def test_ring_excludes_neighbouring_water_body():
    w = np.zeros((60, 60), bool); w[20:30, 20:30] = True; w[20:30, 31:34] = True
    u = S.label_units(w)
    for m in S.ring_masks(u, width_px=3).values():
        assert not (m & w).any()


def test_ring_metric_matches_between_site_and_reference_units():
    w = np.zeros((80, 80), bool); w[10:20, 10:20] = True; w[50:60, 50:60] = True
    veg = np.where(w, np.nan, 0.6)
    veg[45:65, 45:65] = np.where(w[45:65, 45:65], np.nan, 0.2)  # degraded ring around lake 2
    u = S.label_units(w)
    vals = S.unit_values(veg, S.ring_masks(u, width_px=3))
    assert sorted(round(v, 6) for v in vals.values()) == [0.2, 0.6]


# ------------------------------------------------------------- no pseudo-replication
def test_grid_sampling_of_coarse_product_never_repeats_a_cell():
    coarse = RNG.random((10, 10))
    fine = np.kron(coarse, np.ones((46, 46)))               # 4.6 km cells seen on a 100 m grid
    naive = fine.ravel()                                    # v0.2.7-style: each cell counted 2,116 times
    assert np.unique(naive).size == 100 and naive.size == 211600
    spacing_px = int(S.sampling_spacing_m(4638.3, 1e4) / 100.0)   # -> 46
    vals = S.grid_sample(fine, spacing_px)
    assert vals.size == 100 and np.unique(vals).size == 100       # each cell once


# ------------------------------------------------------------- EE layer (structure only)
def _fake_ee():
    ee = MagicMock()
    img = MagicMock(name="img")
    for m in ("select", "mask", "gt", "unmask", "multiply", "reduceNeighborhood", "divide",
              "updateMask", "gte", "rename", "reproject", "addBands", "toInt", "And"):
        getattr(img, m).return_value = img
    ee.Image.constant.return_value = img
    ee.Image.pixelArea.return_value = img
    return ee, img


def test_ee_window_image_reprojects_to_native_and_uses_site_radius():
    ee, img = _fake_ee()
    S.ee_window_image(ee, img, native_scale_m=10, site_area_m2=4.01e5)
    kw = ee.Kernel.circle.call_args.kwargs
    assert kw["units"] == "meters" and kw["radius"] == pytest.approx(S.site_window_radius_m(4.01e5))
    assert kw["normalize"] is False
    ee.Projection.return_value.atScale.assert_called_with(10)
    assert img.reproject.called


def test_ee_sample_windows_uses_nonoverlapping_spacing_and_valid_only():
    ee, img = _fake_ee()
    S.ee_sample_windows(ee, img, "REGION", native_scale_m=10, site_area_m2=4.01e5, n=5000, seed=1)
    kw = img.stratifiedSample.call_args.kwargs
    assert kw["scale"] == pytest.approx(S.sampling_spacing_m(10, 4.01e5))
    assert kw["numPoints"] == 0 and kw["classValues"] == [1] and kw["classPoints"] == [5000]
