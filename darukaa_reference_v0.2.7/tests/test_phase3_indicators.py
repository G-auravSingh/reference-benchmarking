"""
Phase 3 synthetic fixtures (v0.2.8): one landscape with a KNOWN answer for every changed indicator,
driven through reference_builders (numpy definitions) and benchmarking.evaluate_indicator.
"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from darukaa_reference import benchmarking as B
from darukaa_reference import constructs as K
from darukaa_reference import indicator_contract as IC
from darukaa_reference import reference_builders as R
from darukaa_reference import reference_builders_ee as RE
from darukaa_reference import support as S
from darukaa_reference.config import Config

C = IC.CONTRACTS


def disk(shape, centre, r):
    k = S.disk_kernel(r).astype(bool)
    m = np.zeros(shape, bool)
    h = k.shape[0] // 2
    m[centre[0] - h:centre[0] + h + 1, centre[1] - h:centre[1] + h + 1] = k
    return m


# ==================================================================== forest_loss_rate (E1)
def _forest(n=480, p_loss=0.10, seed=1):
    rng = np.random.default_rng(seed)
    tc = np.full((n, n), 80.0)
    ly = np.where(rng.random((n, n)) < p_loss, rng.integers(1, 26, (n, n)), 0)
    return ly, tc


def test_forest_loss_site_and_reference_are_the_same_rate():
    ly, tc = _forest()
    poly = disk(ly.shape, (240, 240), 15)
    case = R.forest_loss_case(ly, tc, poly, pixel_size_m=30.0)
    # the discretised disc and the window kernel are the same footprint for this site
    assert S.disk_kernel(15).sum() == S.disk_kernel(S.window_radius_px(case.site_area_m2, 30.0)).sum() == poly.sum()
    num, den, years = R.forest_loss_terms(ly, tc, 1, 25)
    expected = num[poly].sum() / den[poly].sum() * 100.0 / 25.0                       # by hand
    assert case.site_value == pytest.approx(expected) and years == 25
    ref_at_site = S.window_rate(num, den, 15, 25, 900.0, IC.FOREST_BASELINE_MIN_M2)[240, 240]
    assert ref_at_site == pytest.approx(case.site_value, rel=1e-12)                    # identical unit -> identical value
    assert case.reference.spec.unit == case.site_spec.unit == "percent_per_year"
    v = case.reference.finite()
    assert v.size >= IC.MIN_REFERENCE_WINDOWS and np.all((v >= 0) & (v <= 100 / 25))  # %/yr, never a year code (v0.2.7: 16/17)
    assert v.mean() == pytest.approx(0.10 * 100 / 25, rel=0.05)                         # 10 % loss over 25 y = 0.4 %/yr
    assert case.reference.population_definition and case.reference.reference_n == v.size
    # end to end
    ev = B.SiteEvidence("terrestrial", case.site_area_m2, frozenset({"woody"}), forest_baseline_m2=case.extras["baseline_forest_m2"])
    a = B.evaluate_indicator(C["forest_loss_rate"], ev, case.site_value, case.site_spec, {"tier2": case.reference})
    assert a.status == "scored" and a.estimator == "reference_percentile" and a.direction == "lower_is_better"
    assert a.reference_n == v.size and 0.0 <= a.score <= 1.0


def test_forest_loss_numerator_is_a_subset_of_the_baseline_and_the_5ha_floor_applies():
    n = 60
    tc = np.full((n, n), 80.0); tc[:, :30] = 15.0                       # left half: 15 % canopy, NOT baseline forest
    ly = np.full((n, n), 5)                                              # loss everywhere in 2005
    num, den, _ = R.forest_loss_terms(ly, tc, 1, 25)
    assert num[:, :30].sum() == 0 and den[:, :30].sum() == 0             # loss on non-baseline pixels never counts
    assert num[:, 30:].sum() == den[:, 30:].sum() == n * 30
    small = np.zeros((n, n), bool); small[10:17, 40:47] = True           # 49 px * 900 m2 = 4.4 ha < 5 ha
    assert R.forest_loss_case(ly, tc, small).site_value is None
    big = np.zeros((n, n), bool); big[10:20, 35:45] = True               # 100 px = 9 ha
    assert R.forest_loss_case(ly, tc, big).site_value == pytest.approx(100.0 / 25.0)   # all baseline forest lost in 25 y


def test_forest_loss_windows_use_correct_year_counts():
    assert K.years_in_window(1, 25) == 25 and K.years_in_window(20, 25) == 6 and K.years_in_window(23, 25) == 3
    cfg = Config()
    assert [w[3] for w in cfg.forest_loss_windows] == [25, 6, 3]           # v0.2.7: 24 / 5 / 2 (off by one)
    assert all(w[3] == w[2] - w[1] + 1 for w in cfg.forest_loss_windows)
    import darukaa_reference.indicators as I
    src = inspect.getsource(I._forest_baseline_and_loss)
    assert "_K.years_in_window" in src and ".And(f)" in src                # default windows + numerator inside baseline
    assert "24)" not in src and ", 5)" not in src


def test_percentile_lower_is_better_with_zero_inflated_reference():
    n = 480
    rng = np.random.default_rng(2)
    tc = np.full((n, n), 80.0)
    ly = np.zeros((n, n), int)
    ly[:180, :180] = np.where(rng.random((180, 180)) < 0.30, rng.integers(1, 26, (180, 180)), 0)   # loss only in one corner
    hot = disk((n, n), (90, 90), 15)                                        # site inside the loss corner
    clean = disk((n, n), (400, 400), 15)                                    # site far from any loss
    hot_case, clean_case = R.forest_loss_case(ly, tc, hot), R.forest_loss_case(ly, tc, clean)
    ref = hot_case.reference.finite()
    assert (ref == 0).mean() > 0.6                                          # strongly zero-inflated
    assert B.scale_estimator_guard(ref) == "reference_zero_inflated_or_tie_heavy"
    ev = lambda case: B.SiteEvidence("terrestrial", case.site_area_m2, frozenset({"woody"}), forest_baseline_m2=case.extras["baseline_forest_m2"])
    a_hot = B.evaluate_indicator(C["forest_loss_rate"], ev(hot_case), hot_case.site_value, hot_case.site_spec, {"tier2": hot_case.reference})
    a_clean = B.evaluate_indicator(C["forest_loss_rate"], ev(clean_case), clean_case.site_value, clean_case.site_spec, {"tier2": clean_case.reference})
    assert a_hot.status == a_clean.status == "scored"
    assert clean_case.site_value == 0.0 and hot_case.site_value > 1.0
    assert a_clean.score > 0.5 > a_hot.score                                 # lower loss = better benchmark
    assert a_clean.score == pytest.approx(B.percentile_benchmark(0.0, ref, "lower_is_better")["score"])
    assert a_clean.benchmark_details["fraction_reference_zero"] > 0.6 and a_clean.benchmark_details["p_reference_tied"] > 0.6
    assert a_hot.benchmark_details["reference_n"] == a_hot.reference_n


# ==================================================================== net_forest_change_rate (D5)
def _dw(shape, fill):
    return np.full(shape, float(fill))


def test_net_change_identical_endpoints_gives_zero():
    dw = np.random.default_rng(5).choice([1.0, 2.0, 4.0, 6.0], (300, 300))
    poly = disk(dw.shape, (150, 150), 15)
    case = R.net_change_case(dw, dw.copy(), poly, dt_years=7.0)
    assert case.site_value == 0.0 and np.all(case.reference.finite() == 0.0)
    a = B.evaluate_indicator(C["net_forest_change_rate"], B.SiteEvidence("terrestrial", case.site_area_m2), case.site_value,
                             case.site_spec, {"tier1": case.reference})
    assert a.status == "scored" and a.score == pytest.approx(0.5)            # equal to an all-tied reference: mid-rank


def test_net_change_planting_gives_positive_pp_per_year():
    early = _dw((300, 300), K.DW_GRASS)
    recent = early.copy()
    poly = disk(early.shape, (150, 150), 15)
    recent[poly] = K.DW_TREES                                                # the whole site is planted with trees
    case = R.net_change_case(early, recent, poly, dt_years=7.0)
    assert case.site_value == pytest.approx(100.0 / 7.0)                     # 100 pp over 7 years, by hand
    half = recent.copy(); half[poly & (np.arange(300)[None, :] < 150)] = K.DW_GRASS
    case_half = R.net_change_case(early, half, poly, dt_years=7.0)
    assert case_half.site_value == pytest.approx((poly & (np.arange(300)[None, :] >= 150)).sum() / poly.sum() * 100 / 7.0)
    a = B.evaluate_indicator(C["net_forest_change_rate"], B.SiteEvidence("terrestrial", case.site_area_m2), case.site_value,
                             case.site_spec, {"tier1": case.reference})
    assert a.status == "scored" and a.score > 0.95 and a.direction == "higher_is_better"
    # tree LOSS is negative and scores below the regional reference
    loss = _dw((300, 300), K.DW_TREES); loss_recent = loss.copy(); loss_recent[poly] = K.DW_CROPS
    cl = R.net_change_case(loss, loss_recent, poly, dt_years=7.0)
    assert cl.site_value == pytest.approx(-100.0 / 7.0)
    assert B.evaluate_indicator(C["net_forest_change_rate"], B.SiteEvidence("terrestrial", cl.site_area_m2), cl.site_value,
                                cl.site_spec, {"tier1": cl.reference}).score < 0.05


def test_net_change_reference_is_not_fixed_by_the_stratum():
    rng = np.random.default_rng(9)
    early = np.where(rng.random((300, 300)) < 0.3, K.DW_TREES, K.DW_GRASS)
    recent = np.where(rng.random((300, 300)) < 0.03, K.DW_TREES + K.DW_GRASS - early, early)   # 3 % of pixels flip
    poly = disk(early.shape, (150, 150), 15)
    case = R.net_change_case(early, recent, poly, dt_years=7.0)
    v = case.reference.finite()
    assert v.std() > 0 and len(np.unique(np.round(v, 9))) > 10               # a real distribution, not a constant
    assert case.reference.spec.population == "regional_ecoregion"
    assert case.reference.diagnostics["windows_centred_on"] == "all valid pixels"      # no DW-class stratum
    assert IC.CONTRACTS["net_forest_change_rate"].reference_population not in IC.POPULATION_SELECTORS
    # v0.2.7 reference: +/-1 proxy conditioned on the tree stratum had median exactly 1
    proxy_pool = np.where(early == K.DW_TREES, 1.0, np.nan)
    assert np.nanmedian(proxy_pool) == 1.0
    # classification gaps are excluded, never treated as change
    gap = early.astype(float); gap[:, :100] = np.nan
    cg = R.net_change_case(gap, recent, poly, dt_years=7.0)
    assert cg.reference.finite().size < case.reference.finite().size


def test_net_change_single_product_no_hansen_in_the_ee_definition():
    import darukaa_reference.indicators as I
    src = inspect.getsource(I._img_net_forest_change) + inspect.getsource(I._dw_tree_binary_period) + inspect.getsource(I.extract_net_forest_change_rate)
    assert "UMD/hansen" not in src and "global_forest_change" not in src and "treecover2000" not in src
    assert "GOOGLE/DYNAMICWORLD" in src
    class Cfg: ndvi_year = 2025
    early, recent, dt = I._net_change_periods(Cfg)
    assert early == (2017, 2018) and recent == (2024, 2025) and dt == 7.0


# ==================================================================== natural_habitat (D2)
def test_natural_habitat_regional_window_reference_and_absolute_diagnostic():
    n = 400
    rng = np.random.default_rng(11)
    dw = np.where(rng.random((n, n)) < 0.6, K.DW_TREES, K.DW_CROPS).astype(float)         # regional condition: 60 % natural
    poly = disk(dw.shape, (200, 200), 15)
    idx = np.flatnonzero(poly)
    rng.shuffle(idx)
    nat = idx[:round(0.8 * idx.size)]
    dw[poly] = K.DW_CROPS
    dw.flat[nat] = K.DW_GRASS                                                             # 80 % natural inside the site
    case = R.natural_habitat_case(dw, poly, pixel_size_m=10.0)
    assert case.site_value == pytest.approx(100.0 * round(0.8 * idx.size) / idx.size)      # by hand
    v = case.reference.finite()
    assert abs(v.mean() - 60.0) < 1.5 and v.std() > 1.0                                    # regional windows: spread, centred on 60 %
    pix = R.natural_binary(dw).ravel() * 100
    assert np.median(np.abs(pix - np.median(pix))) == 0.0 and np.median(np.abs(v - np.median(v))) > 0.5   # v0.2.7 pixel MAD = 0
    ev = B.SiteEvidence("terrestrial", case.site_area_m2)
    a = B.evaluate_indicator(C["natural_habitat"], ev, case.site_value, case.site_spec, {"tier1": case.reference})
    assert a.status == "scored" and a.score > 0.99                                          # far above the regional windows
    assert a.reference_population.startswith("all valid site-sized windows of the ecoregion")
    assert a.reference_n == v.size >= IC.MIN_REFERENCE_WINDOWS
    d = a.diagnostics["absolute_natural_reference"]                                        # SEPARATE from the score
    assert d["departure_percentage_points"] == pytest.approx(100.0 - case.site_value)
    assert d["reference_condition"] == "100 % natural cover"
    # site exactly at the regional condition sits mid-distribution, not at an extreme
    typical = B.percentile_benchmark(float(np.median(v)), v, "higher_is_better")["score"]
    assert 0.4 < typical < 0.6


# ==================================================================== ghm
def test_ghm_site_is_read_at_native_90m(monkeypatch):
    import darukaa_reference.indicators as I
    seen = {}
    monkeypatch.setattr(I, "_img_ghm", lambda c: "IMG")
    monkeypatch.setattr(I, "_reduce", lambda img, g, scale: seen.update(scale=scale) or {"value": 0.5, "pixels": None})
    I.extract_ghm("GEOM", object())
    assert seen["scale"] == 90.0 == K.GHM_NATIVE_M == C["ghm"].native_resolution_m      # v0.2.7 read it at 1,000 m
    # window reference in the regional UNFILTERED stratum, site-sized, native 90 m
    rng = np.random.default_rng(4)
    hmi = np.clip(rng.normal(0.5, 0.12, (200, 200)), 0, 1)
    poly = disk(hmi.shape, (100, 100), 3)
    case = R.ghm_case(hmi, poly)
    assert case.reference.spec.support == "site_window_mean" and case.reference.spec.native_scale_m == 90.0
    assert case.reference.spec.population == "regional_stratum_unfiltered"
    assert case.reference.finite().std() < hmi.std() / 2                                    # site-sized means, not pixels
    a = B.evaluate_indicator(C["ghm"], B.SiteEvidence("terrestrial", case.site_area_m2), case.site_value, case.site_spec, {"tier2": case.reference})
    assert a.status == "scored" and a.estimator == "robust_z" and a.direction == "lower_is_better"


# ==================================================================== aquatic: water bodies (E2)
def _lake_world(sides_perm, target_side=20, shape=(360, 360), cell=40):
    """Lakes on a grid. Cell 0 = target (permanence 0.9). Returns water, permanence, per-lake metric and bookkeeping."""
    water = np.zeros(shape, bool)
    perm = np.zeros(shape, float)
    metric = np.full(shape, 9.99)
    sides = [(target_side, 0.9)] + list(sides_perm)
    ids = []
    for k, (side, p) in enumerate(sides):
        r, c = divmod(k, shape[1] // cell)
        r0, c0 = r * cell + 5, c * cell + 5
        water[r0:r0 + side, c0:c0 + side] = True
        perm[r0:r0 + side, c0:c0 + side] = p
        metric[r0:r0 + side, c0:c0 + side] = 0.10 + 0.01 * k                 # distinct per-lake value
        ids.append((r0, c0, side, p))
    return water, perm, metric, ids


MATCH_SIDES = [(12, .9), (15, .9), (18, .8), (22, .9), (26, .85), (30, .9), (34, .9), (16, .8), (20, .95), (24, .9), (28, .75), (14, .9)]
# 12 comparable lakes (area 144..1156 within [133, 1200], |perm - 0.9| <= 0.25)
REJECT = [(10, .9), (36, .9), (20, .5), (24, .3), (3, .9)]     # too small / too big / too impermanent / 1 pure pixel


def _case(sides):
    water, perm, metric, ids = _lake_world(sides)
    site = np.zeros(water.shape, bool); site[5:25, 5:25] = True
    return R.water_body_case(water=water, metric=metric, kind="water", site_mask=site, pixel_area_m2=100.0,
                             native_scale_m=10.0, construct="x", unit="u", temporal="t",
                             population="comparable_water_bodies", permanence=perm), ids


def test_water_body_reference_matches_e2_and_requires_min_n():
    case, ids = _case(MATCH_SIDES + REJECT)
    assert case.valid and case.n_pure_water_px == 18 * 18                          # target 20x20 eroded by one pixel
    f = case.funnel
    assert f["n_water_bodies_total"] == 1 + len(MATCH_SIDES) + len(REJECT)
    assert f["n_bodies_with_enough_pixels"] == 1 + len(MATCH_SIDES) + len(REJECT) - 1     # the 3x3 lake has 1 pure px
    assert f["n_rejected_size"] == 2 and f["n_rejected_permanence"] == 2                   # 10 & 36 ; perm 0.5 & 0.3
    assert f["n_reference_bodies"] == case.reference.reference_n == len(MATCH_SIDES)
    for r0, c0, side, p in [ids[i + 1] for i in range(len(MATCH_SIDES))]:
        assert 20 * 20 / 3 <= side * side <= 20 * 20 * 3 and abs(p - 0.9) <= 0.25          # every reference obeys E2
    assert "area within [1/3, 3]" in case.reference.population_definition and "permanence" in case.reference.population_definition
    ev = B.SiteEvidence("aquatic", 4e4, frozenset({"open_water"}), water_body_valid=True, n_pure_water_px=case.n_pure_water_px)
    a = B.evaluate_indicator(C["sabf"], ev, case.target_value, case.site_spec, {"tier2": case.reference})
    assert a.status == "scored" and a.reference_n == 12 and a.reference_population.startswith("comparable water bodies")
    # too few comparable bodies -> explicit status, never a fabricated score
    few, _ = _case(MATCH_SIDES[:5] + REJECT)
    assert few.reference.reference_n == 5
    ev5 = B.SiteEvidence("aquatic", 4e4, frozenset({"open_water"}), water_body_valid=True, n_pure_water_px=few.n_pure_water_px)
    a5 = B.evaluate_indicator(C["sabf"], ev5, few.target_value, few.site_spec, {"tier2": few.reference})
    assert a5.status == "reference_available_but_not_scoreable" and a5.reason == "insufficient_reference_n"
    assert a5.reference_n == 5 and a5.score is None and "documented minimum 10" in a5.detail


def test_earth_engine_selection_rule_matches_the_numpy_definition():
    case, ids = _case(MATCH_SIDES + REJECT)
    water, perm, metric, _ = _lake_world(MATCH_SIDES + REJECT)
    units = S.label_units(water, 100.0)
    pure = S.unit_masks(units, pure=True)
    vals = S.unit_values(metric, S.unit_masks(units, pure=True))
    recs = [{"uid": i, "area_m2": units.areas_m2[i], "pure_px": int(pure[i].sum()), "value": vals.get(i),
             "permanence": float(perm[units.labels == i].mean())} for i in units.areas_m2]
    final, funnel = RE.select_reference_records(recs, case.target_id)
    assert sorted(r["uid"] for r in final) == sorted(case.reference.diagnostics["reference_body_ids"])
    for k in ("n_rejected_size", "n_rejected_permanence", "n_reference_bodies", "n_bodies_with_enough_pixels", "n_water_bodies_total"):
        assert funnel[k] == case.funnel[k], k


def test_sabf_uses_pure_water_only_and_land_never_counts_as_bloom():
    shape = (100, 100)
    water = np.zeros(shape, bool); water[35:65, 35:65] = True                       # 30x30 lake
    T = 10
    fai = np.full((T,) + shape, 0.05)                                               # land: vegetation always > 0.005 -> "bloom"
    fai[:, water] = 0.001                                                           # open water: clear
    shore = water & ~S.pure_water(water, 1)
    fai[:, shore] = 0.05                                                            # mixed shoreline pixels look like bloom
    freq = R.sabf_pixel_frequency(fai)
    site = np.zeros(shape, bool); site[40:60, 40:60] = True
    kw = dict(kind="water", site_mask=site, pixel_area_m2=100.0, native_scale_m=10.0, construct="sabf", unit="f",
              temporal="t", population="comparable_water_bodies")
    case = R.water_body_case(water=water, metric=freq, **kw)
    assert case.valid and case.target_value == 0.0 and case.n_pure_water_px == 28 * 28
    naive_lake = float(freq[water].mean())
    assert naive_lake == pytest.approx((900 - 784) / 900) and naive_lake > 0.1     # including shore pixels would be wrong
    assert float(freq[~water].mean()) == 1.0                                       # land reads as permanent bloom (v0.2.7 reference pool)
    blooming = fai.copy(); blooming[:3][:, S.pure_water(water, 1)] = 0.02          # 3 of 10 dates bloom on pure water
    assert R.water_body_case(water=water, metric=R.sabf_pixel_frequency(blooming), **kw).target_value == pytest.approx(0.3)
    nowater = R.water_body_case(water=np.zeros(shape, bool), metric=freq, **kw)
    assert not nowater.valid and nowater.invalid_reason == "no_water_body"          # land-only zone: no value at all
    tiny = np.zeros(shape, bool); tiny[10:13, 10:13] = True
    t = R.water_body_case(water=tiny, metric=freq, **{**kw, "site_mask": tiny})
    assert not t.valid and t.invalid_reason == "insufficient_pure_water"            # a 3x3 pond has 1 pure pixel


def test_wcpi_is_raw_and_independent_of_site_relative_range():
    A, Cc = K.TSM_NECHAD_A, K.TSM_NECHAD_C
    def expected(r):
        return 1.0 / (A * r / (1 - r / Cc) + 1.0)
    assert expected(0.03) == pytest.approx(1 / (228.1 * 0.03 / (1 - 0.03 / 0.1641) + 1))
    shape = (100, 200)
    water = np.zeros(shape, bool); water[30:70, 20:60] = True; water[30:70, 120:160] = True    # two lakes
    red = np.full(shape, 0.05)
    red[30:70, 20:60] = 0.03; red[30:70, 120:160] = 0.06
    kw = dict(kind="water", pixel_area_m2=100.0, native_scale_m=10.0, construct="wcpi", unit="i", temporal="t",
              population="comparable_water_bodies")
    site = np.zeros(shape, bool); site[40:60, 30:50] = True
    a = R.water_body_case(water=water, metric=R.wcpi_pixel(red), site_mask=site, **kw)
    assert a.target_value == pytest.approx(expected(0.03), abs=1e-12) and a.target_value > 0.05
    # the value does not depend on any range within the site or on the other lake
    red2 = red.copy(); red2[30:70, 120:160] = 0.12; red2[45, 30:50] = 0.05             # change the other lake and add within-site range
    b = R.water_body_case(water=water, metric=R.wcpi_pixel(red2), site_mask=site, **kw)
    unif = R.water_body_case(water=water, metric=R.wcpi_pixel(red), site_mask=site, **kw)
    assert unif.target_value == a.target_value
    # v0.2.7 min-max normalisation of a uniform lake collapses to 0 (span floored at 1e-6)
    px = R.wcpi_pixel(red)[40:60, 30:50]
    old = (px - px.min()) / max(px.max() - px.min(), 1e-6)
    assert old.mean() == 0.0 and a.target_value != old.mean()
    # out-of-range reflectance (>= 0.1641 makes TSM undefined) is masked, not turned into a value
    assert np.isnan(R.wcpi_pixel(np.array([0.2, 0.3]))).all()
    assert not R.water_body_case(water=water, metric=R.wcpi_pixel(np.full(shape, 0.2)), site_mask=site, **kw).valid


# ==================================================================== aquatic: riparian rings (E3)
def _ring_world():
    shape = (200, 320)
    water = np.zeros(shape, bool)
    lakes = [(60, 20)] + [(60, 80 + 40 * k) for k in range(6)]                       # target + 6 comparable lakes
    for r0, c0 in lakes:
        water[r0:r0 + 20, c0:c0 + 20] = True
    return water, lakes


def test_ring_metric_uses_the_same_ring_for_target_and_reference():
    W = 3
    water, lakes = _ring_world()
    r0, c0 = lakes[0]
    water[r0 + 5:r0 + 9, c0 + 22:c0 + 26] = True                                       # a small pond touching the target's ring
    disturbed = np.zeros(water.shape)
    disturbed[:, :c0 + 10] = 1.0                                                       # disturbed everywhere left of the lake centre
    disturbed[water] = 1.0                                                             # water pixels must never count
    outside = np.zeros(water.shape, bool); outside[r0 - 30:r0 - 10, c0 + 5] = True     # a disturbed patch > 3 px from the lake
    disturbed[outside] = 1.0
    rr0, rc0 = lakes[1]
    disturbed[rr0 - W:rr0 + 20 + W, rc0 - 3:rc0 + 8] = 1.0                             # part of ONE reference ring is disturbed
    site = np.zeros(water.shape, bool); site[r0:r0 + 20, c0:c0 + 20] = True
    kw = dict(water=water, kind="ring", site_mask=site, pixel_area_m2=100.0, native_scale_m=10.0, construct="sdi", unit="f",
              temporal="t", population="comparable_riparian_rings", ring_width_px=W, min_pure_px=10)
    case = R.water_body_case(metric=disturbed, **kw)
    # independent, hand-built ring of the target: square dilation by W minus the lake and minus ALL water
    big = np.zeros(water.shape, bool); big[r0 - W:r0 + 20 + W, c0 - W:c0 + 20 + W] = True
    ring = big & ~water
    assert ring.sum() == 26 * 26 - 20 * 20 - 4                                         # only one 4-px column of the pond lies inside the ring
    assert not (ring & outside).any()                                                  # the far patch is outside the ring
    assert case.valid and case.target_value == pytest.approx(disturbed[ring].mean())
    without_far_patch = disturbed.copy(); without_far_patch[outside] = 0.0
    assert R.water_body_case(metric=without_far_patch, **kw).target_value == pytest.approx(case.target_value)   # it never counted
    with_water_zeroed = disturbed.copy(); with_water_zeroed[water] = 0.0
    assert R.water_body_case(metric=with_water_zeroed, **kw).target_value == pytest.approx(case.target_value)   # water pixels never counted
    # the very same ring width, water exclusion and metric build every reference ring
    assert case.reference.diagnostics["ring_width_px"] == W and case.reference.spec.support == "riparian_ring_unit"
    assert case.site_spec.support == "riparian_ring_unit"
    bigr = np.zeros(water.shape, bool); bigr[rr0 - W:rr0 + 20 + W, rc0 - W:rc0 + 20 + W] = True
    ringr = bigr & ~water
    expected_ref = float(disturbed[ringr].mean())
    assert 0.0 < expected_ref < 1.0
    assert any(abs(v - expected_ref) < 1e-12 for v in case.reference.values)              # a reference ring built identically
    ref_ids = case.reference.diagnostics["reference_body_ids"]
    assert len(ref_ids) == 6 == case.reference.reference_n
    # riparian_natural_veg_share is the same construction with the natural-vegetation metric
    dw = np.where(disturbed > 0, K.DW_CROPS, K.DW_TREES).astype(float)
    share = R.water_body_case(metric=R.natural_binary(dw), **{**kw, "construct": "rnvs"})
    assert share.target_value == pytest.approx(1.0 - case.target_value)                 # natural share = 1 - disturbed share
    for n in ("sdi", "riparian_natural_veg_share"):
        assert C[n].site_support == "riparian_ring_unit" and C[n].reference_support == "riparian_ring_unit"
        assert C[n].reference_population == "comparable_riparian_rings"
    assert K.RIPARIAN_RING_WIDTH_M == 100.0
    ev = B.SiteEvidence("aquatic", 4e4, frozenset({"open_water"}), water_body_valid=True, n_pure_water_px=case.n_pure_water_px)
    sdi = B.evaluate_indicator(C["sdi"], ev, case.target_value, case.site_spec, {"tier2": case.reference})
    assert sdi.status == "reference_available_but_not_scoreable" and sdi.reason == "insufficient_reference_n"
    assert sdi.reference_n == 6 and "documented minimum 10" in sdi.detail              # 6 comparable rings < 10: no fabricated score


# ==================================================================== EDPP / MSPL
def test_edpp_mspl_use_absolute_thermal_scaling_and_a_single_band():
    # two sites with the SAME absolute temperature (30 degC) but different local ranges
    site_a = np.array([30.0, 30.2, 30.5]); site_b = np.array([29.0, 30.0, 31.0])
    old = lambda lst, x: (x - lst.min()) / max(lst.max() - lst.min(), 1e-6)
    assert old(site_a, 30.0) == 0.0 and old(site_b, 30.0) == 0.5                        # v0.2.7: range-dependent
    thermal = (30.0 - K.THERMAL_MIN_C) / (K.THERMAL_MAX_C - K.THERMAL_MIN_C)
    assert thermal == 0.5
    assert R.edpp_index(30.0, 1.0, 1.0, 0.0) == pytest.approx(1 - 0.5)                  # absolute: identical for both sites
    assert R.edpp_index(20.0, 1.0, 1.0, 0.0) == 1.0 and R.edpp_index(40.0, 1.0, 1.0, 0.0) == 0.0
    assert R.mspl_index(30.0, 0.0, 0.0, 0.0) == pytest.approx(K.MSPL_WEIGHTS["thermal"] * 0.5)
    assert R.mspl_index(45.0, 1, 1, 1) == pytest.approx(1.0) and sum(K.MSPL_WEIGHTS.values()) == pytest.approx(1.0)
    # code structure: one image function per indicator is BOTH the site value and the reference
    import darukaa_reference.indicators as I
    from darukaa_reference.indicators import create_default_registry
    reg = create_default_registry()
    assert reg.get("edpp").metadata["gee_image_fn"] is I._img_edpp and reg.get("mspl").metadata["gee_image_fn"] is I._img_mspl
    for extract, img in ((I.extract_edpp, "_img_edpp(c)"), (I.extract_mspl, "_img_mspl(c)")):
        s = inspect.getsource(extract)
        assert img in s and "minMax" not in s and "reduceRegion" not in s
    for fn in (I._img_edpp, I._img_mspl, I._thermal_absolute):
        s = inspect.getsource(fn)
        assert "minMax" not in s and "reduceRegion" not in s                            # no site-derived statistic
    assert 'rename("EDPP")' in inspect.getsource(I._img_edpp) and 'rename("MSPL")' in inspect.getsource(I._img_mspl)
    assert "_K.THERMAL_MIN_C" in inspect.getsource(I._thermal_absolute)
    for n in ("edpp", "mspl"):
        assert C[n].image_is_single_band and not C[n].site_relative_normalisation


# ==================================================================== blocked / retired
def test_cpland_stays_blocked_until_the_pv_binary_provenance_is_documented():
    c = C["cpland"]
    assert c.proposed_scoreability == "pending_methodology" and c.implementation_status != "v0.2.8_synthetic_tested"
    assert "provenance" in " ".join(c.current_defects).lower()
    a = B.evaluate_indicator(c, B.SiteEvidence("terrestrial", 4e5), 60.0, None, {})
    assert a.status == "pending_methodology"


def test_rci_is_retired_and_its_replacement_has_no_complexity_wording():
    from darukaa_reference.indicators import create_default_registry
    reg = create_default_registry()
    assert "rci" not in reg and "rci" not in C
    r = reg.get("riparian_natural_veg_share")
    assert "complexity" not in r.display_name.lower() and r.unit == "fraction (0-1)"
    import darukaa_reference.indicators as I
    assert not hasattr(I, "_img_rci") and hasattr(I, "_img_natural_veg")
