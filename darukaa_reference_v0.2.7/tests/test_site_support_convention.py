"""
Frozen production convention for polygon site metrics: COVERAGE-WEIGHTED mean over the native pixels the polygon touches.
Known answers are derived by hand; the one-native-pixel-cell path is structure-tested (it was the live 'Bad maxPixels arg' bug).
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from darukaa_reference import constructs as K
from darukaa_reference import reference_builders as R
from darukaa_reference import support as S

X0, Y_TOP = 500000.0, 2000000.0


def test_the_convention_is_named_once_and_agrees_across_modules():
    assert S.SITE_SUPPORT_CONVENTION == K.SITE_SUPPORT_CONVENTION == "polygon_coverage_weighted"


def test_polygon_coverage_known_fractions():
    poly = box(X0 + 5.0, Y_TOP - 35.0, X0 + 25.0, Y_TOP - 5.0)                    # x: 5..25 -> columns 50 %, 100 %, 50 %, 0 ; y: rows 50 %, 100 %, 100 %, 50 %
    w = S.polygon_coverage(poly, X0, Y_TOP, 10.0, (4, 4))
    col, row = np.array([0.5, 1.0, 0.5, 0.0]), np.array([0.5, 1.0, 1.0, 0.5])
    assert np.allclose(w, np.outer(row, col))
    assert w.sum() * 100.0 == pytest.approx(poly.area)                            # the weights add up to the polygon's own area


def test_polygon_coverage_of_a_pixel_aligned_polygon_is_0_or_1_and_clips_to_the_raster():
    w = S.polygon_coverage(box(X0 + 10.0, Y_TOP - 30.0, X0 + 30.0, Y_TOP - 10.0), X0, Y_TOP, 10.0, (4, 4))
    assert set(np.unique(w)) == {0.0, 1.0} and w.sum() == 4
    partly_outside = S.polygon_coverage(box(X0 - 100.0, Y_TOP - 20.0, X0 + 20.0, Y_TOP + 100.0), X0, Y_TOP, 10.0, (4, 4))
    assert partly_outside.sum() == 4 and partly_outside[0, 0] == 1.0             # only the part inside the raster counts


def test_weighted_mean_known_answer_and_masked_pixels_are_excluded_from_both_sums():
    v = np.zeros((4, 4)); v[:, :2] = 10.0
    w = np.outer([0.5, 1.0, 1.0, 0.5], [0.5, 1.0, 0.5, 0.0])
    assert S.weighted_mean(v, w) == pytest.approx((0.5 * 10 + 1.0 * 10 + 0.5 * 0) / 2.0)          # 7.5
    v2 = v.copy(); v2[1, 1] = np.nan                                              # a masked pixel drops its weight from the denominator too
    ww = w.copy()
    expect = (w * v).sum() - w[1, 1] * 10.0
    assert S.weighted_mean(v2, ww) == pytest.approx(expect / (w.sum() - w[1, 1]))
    assert S.weighted_mean(np.full((2, 2), np.nan), np.ones((2, 2))) is None
    assert S.weighted_mean(v, np.zeros((4, 4))) is None


def test_weights_of_one_reduce_to_the_plain_mean_and_scaling_weights_changes_nothing():
    rng = np.random.default_rng(3)
    v = rng.uniform(0, 1, (5, 5))
    assert S.weighted_mean(v, np.ones((5, 5))) == pytest.approx(v.mean())
    w = rng.uniform(0, 1, (5, 5))
    assert S.weighted_mean(v, 7.0 * w) == pytest.approx(S.weighted_mean(v, w))


def test_site_mean_accepts_boolean_masks_and_fractional_coverage_identically_when_weights_are_binary():
    rng = np.random.default_rng(4)
    v = rng.uniform(0, 100, (6, 6)); mask = np.zeros((6, 6), bool); mask[1:4, 2:5] = True
    assert R.site_mean(v, mask) == pytest.approx(v[mask].mean())
    assert R.site_mean(v, mask.astype(float)) == pytest.approx(v[mask].mean())
    valid = np.ones((6, 6), bool); valid[2, 3] = False
    m2 = mask & valid
    assert R.site_mean(v, mask, valid) == pytest.approx(v[m2].mean())
    w = mask * 0.5; w[2, 3] = 1.0
    assert R.site_mean(v, w) == pytest.approx((w * v).sum() / w.sum())


def test_polygon_rate_uses_coverage_weights_in_numerator_and_denominator():
    num = np.array([[1.0, 0.0], [0.0, 1.0]]); den = np.array([[1.0, 1.0], [1.0, 1.0]])
    w = np.array([[1.0, 0.5], [0.5, 0.0]])
    # numerator 1*1 + 0 + 0 + 0 = 1 ; denominator 1 + .5 + .5 + 0 = 2 -> 50 % over 25 years = 2 %/yr
    assert S.polygon_rate(num, den, w, 25, 1.0, 0.0) == pytest.approx(0.5 / 25 * 100.0)
    assert S.polygon_rate(num, den, w > 0, 25, 1.0, 0.0) == pytest.approx((1.0 / 3.0) / 25 * 100.0)   # boolean mask (weights 1/0): num 1, den 3
    assert S.polygon_rate(num, den, np.zeros((2, 2)), 25, 1.0, 0.0) is None


def test_the_rejected_centre_inclusion_convention_really_differs_on_a_coarse_pixel_gradient():
    """Why the convention matters: a 90 m product and a small polygon straddling pixel boundaries (the live ghm case in miniature)."""
    v = np.array([[0.2, 0.9, 0.9], [0.2, 0.9, 0.9], [0.2, 0.2, 0.9]])
    poly = box(X0 + 45.0, Y_TOP - 225.0, X0 + 135.0, Y_TOP - 45.0)               # 90 m x 180 m at 90 m pixels: touches many pixels partly
    w = S.polygon_coverage(poly, X0, Y_TOP, 90.0, (3, 3))
    cov = S.weighted_mean(v, w)
    centre = float(v[w >= 0.5].mean())
    assert cov != pytest.approx(centre) and abs(cov - centre) > 0.05


# ---------------------------------------------------------------- one-native-pixel cells: no aggregation, no maxPixels=1
def _ee():
    ee = MagicMock()
    ee.Projection.return_value.atScale.side_effect = lambda m: f"proj@{m}"
    return ee


def test_a_one_pixel_cell_skips_reduceResolution_entirely():
    ee = _ee()
    img = MagicMock()
    v = img.select.return_value.rename.return_value.reproject.return_value
    out = S.ee_block_mean_image(ee, img, 463.83, 4.0e5, "EPSG:32643")             # VIIRS-like: cell_px = round(632/463.83) = 1
    assert S.cell_size_px(4.0e5, 463.83) == 1
    v.reduceResolution.assert_not_called()                                         # 'Bad maxPixels arg' cannot occur
    assert out is v.rename.return_value


def test_a_multi_pixel_cell_still_aggregates_with_max_pixels_equal_to_the_cell_area():
    ee = _ee()
    img = MagicMock()
    v = img.select.return_value.rename.return_value.reproject.return_value
    S.ee_block_mean_image(ee, img, 10.0, 4.01e5, "EPSG:32643")
    assert v.reduceResolution.call_args_list[0].kwargs["maxPixels"] == 63 * 63


def test_a_one_pixel_rate_cell_never_passes_max_pixels_below_two():
    ee = _ee()
    num, den = MagicMock(), MagicMock()
    S.ee_block_rate_image(ee, num, den, 463.83, 4.0e5, 25, "EPSG:32643", 1.0)
    for m in (num, den):
        chain = m.select.return_value.unmask.return_value.reproject.return_value
        chain.reduceResolution.assert_not_called()


def test_contract_constants_agree_with_constructs_and_support():
    from darukaa_reference import indicator_contract as IC
    assert IC.SITE_SUPPORT_CONVENTION == S.SITE_SUPPORT_CONVENTION == K.SITE_SUPPORT_CONVENTION
    assert IC.MAX_WATER_BODY_EXTENT_M == K.MAX_WATER_BODY_EXTENT_M == 2000.0
