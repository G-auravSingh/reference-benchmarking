"""Offline tests of the Earth Engine layer using a recording mock (no EE calls)."""
import sys
from unittest import mock

import pytest
from shapely.geometry import box

from darukaa_adaptive import catalogue as cat
from darukaa_adaptive import layers as L
from darukaa_adaptive.ee_utils import parse_stats
from darukaa_adaptive.extraction import Unit, month_starts, pick_peak_window, plan_unit
from darukaa_adaptive.reference_pool import PoolConfig, regional_blocks
from darukaa_adaptive.site import area_ha


@pytest.fixture
def fake_ee(monkeypatch):
    ee = mock.MagicMock(name="ee")
    monkeypatch.setitem(sys.modules, "ee", ee)
    return ee


def _ctx_base():
    return {"crs": "EPSG:32643", "start": "2025-08-01", "end_exclusive": "2026-09-01", "mask": mock.MagicMock(),
            "peak_window": ("2025-09-01", "2025-12-01"), "raster_paths": {}, "options": {}}


def test_every_catalogue_metric_has_a_builder():
    missing = [c.id for c in cat.CATALOGUE if c.status == "approved" and c.id not in L.BUILDERS]
    assert missing == []


def test_reduce_stats_sets_scale_and_crs_and_never_best_effort(fake_ee):
    from darukaa_adaptive.ee_utils import reduce_stats
    img = mock.MagicMock()
    reduce_stats(img, "REGION", 300, "EPSG:32643")
    calls = [c for c in img.mock_calls if c[0].endswith("reduceRegion")]
    calls += [c for c in fake_ee.mock_calls if c[0].endswith("reduceRegion")]
    assert calls, "reduceRegion was not called"
    for c in calls:
        kw = c.kwargs
        assert kw["scale"] == 300 and kw["crs"] == "EPSG:32643"
        assert "bestEffort" not in kw


def test_parse_stats_uses_exact_keys():
    raw = {"v_mean": 0.5, "v_p5": 0.1, "v_p50": 0.45, "v_p95": 0.9, "v_stdDev": 0.2, "w_sum": 12.5, "w_count": 13,
           "v_p55": 999}
    st = parse_stats(raw)
    assert st["p5"] == 0.1 and st["p50"] == 0.45 and st["covered_pixel_equivalent"] == 12.5 and st["centre_pixels"] == 13
    assert parse_stats({"v_mean": float("nan")})["mean"] is None


def test_small_unit_gets_context_window_for_coarse_layer_but_not_for_fine(fake_ee):
    tiny = Unit("E1", "emu", box(73.8, 18.6, 73.8005, 18.6005))  # ~0.3 ha
    plans = {p.metric: p for p in plan_unit(tiny, ["eii_functional", "ndvi_peak_season", "natural_extent_pct"], _ctx_base())}
    assert plans["eii_functional"].context_buffer_m > 0
    assert area_ha(plans["eii_functional"].region_geom) >= 4 * 9 - 0.01
    assert plans["ndvi_peak_season"].context_buffer_m == 0
    assert plans["natural_extent_pct"].context_buffer_m == 0


def test_road_and_population_use_one_km_buffer(fake_ee):
    u = Unit("S", "site", box(73.8, 18.6, 73.81, 18.61))
    plans = {p.metric: p for p in plan_unit(u, ["road_density", "population_density"], _ctx_base())}
    for p in plans.values():
        assert area_ha(p.region_geom) > area_ha(u.geometry) * 2


def test_pending_metrics_never_carry_values(fake_ee):
    from darukaa_adaptive.extraction import _measure
    u = Unit("S", "site", box(73.8, 18.6, 73.81, 18.61))
    p = {pl.metric: pl for pl in plan_unit(u, ["msa", "lai_s2"], _ctx_base())}
    m = _measure(p["msa"], u, {})
    assert m.status == "pending_input" and m.value is None and m.ran
    m = _measure(p["lai_s2"], u, {})
    assert m.status == "not_run" and m.value is None and not m.ran


def test_ratio_measure_handles_baseline_floor(fake_ee):
    from darukaa_adaptive.extraction import _measure
    u = Unit("S", "site", box(73.8, 18.6, 73.81, 18.61))
    p = {pl.metric: pl for pl in plan_unit(u, ["tree_cover_loss_rate"], _ctx_base())}["tree_cover_loss_rate"]
    # 0.5 ha baseline -> not applicable (decision 3), never 100
    m = _measure(p, u, {"sums": {"num": 0.0, "den": 5000.0, "x_baseline_forest_ha": 5000.0, "x_loss_ha": 0.0}})
    assert m.status == "not_applicable_no_forest_baseline" and m.value is None
    # 20 ha baseline, 1 ha lost over 5 years -> 1 %/yr
    m = _measure(p, u, {"sums": {"num": 1e4, "den": 2e5, "x_baseline_forest_ha": 2e5, "x_loss_ha": 1e4}})
    assert m.value == pytest.approx(1.0) and m.extras["baseline_forest_ha"] == pytest.approx(20.0)


def test_error_in_one_layer_is_recorded_not_hidden(fake_ee):
    from darukaa_adaptive.extraction import _measure
    u = Unit("S", "site", box(73.8, 18.6, 73.81, 18.61))
    p = {pl.metric: pl for pl in plan_unit(u, ["ghm"], _ctx_base())}["ghm"]
    m = _measure(p, u, {"stats": RuntimeError("asset not found")})
    assert m.status == "error" and not m.ran and "asset not found" in m.error


def test_month_starts_and_peak_window():
    months = month_starts("2025-08-01", "2026-09-01")
    assert len(months) == 13 and months[0] == ("2025-08-01", "2025-09-01") and months[-1][1] == "2026-09-01"
    vals = {m[0]: 0.3 for m in months}
    vals.update({"2025-09-01": 0.6, "2025-10-01": 0.7, "2025-11-01": 0.65})
    (a, b), basis = pick_peak_window(vals, months)
    assert (a, b) == ("2025-09-01", "2025-12-01") and "peak" in basis
    (a, b), basis = pick_peak_window({}, months)
    assert (a, b) == ("2025-08-01", "2026-09-01") and "full window" in basis


def test_regional_blocks_are_outside_exclusion_and_match_site_support():
    site = box(73.80, 18.60, 73.81, 18.61)  # ~117 ha -> ~1.08 km side
    cfg = PoolConfig(radius_km=10, n_regional_blocks=40)
    blocks = regional_blocks(site, site, cfg)
    assert 0 < len(blocks) <= 40
    from darukaa_adaptive.site import projected_buffer
    excl = projected_buffer(site, cfg.exclusion_m)
    for _, g, _ in blocks:
        assert not g.intersects(excl)
        assert area_ha(g) == pytest.approx(area_ha(site), rel=0.05)


# ---------------------------------------------------------------- review findings (23 Oct red-team pass)
def _plan(metric, ctx_extra=None):
    u = Unit("S", "site", box(73.8, 18.6, 73.81, 18.61))
    base = _ctx_base()
    base["raster_paths"] = {"grip4_asset": "projects/x/GRIP4/South-East-Asia"}
    return u, {pl.metric: pl for pl in plan_unit(u, [metric], base)}[metric]


def test_empty_road_query_is_not_a_zero_density(fake_ee):
    from darukaa_adaptive.extraction import _measure
    u, p = _plan("road_density")
    m = _measure(p, u, {"length_m": 0.0, "area_m2": 4e6, "n_within_10km": 0})
    assert m.value is None and m.status == "source_unavailable"
    m = _measure(p, u, {"length_m": 2000.0, "area_m2": 4e6, "n_within_10km": 1})
    assert m.value == pytest.approx(0.5)


def test_overlap_above_100_percent_is_flagged_not_reported(fake_ee):
    from darukaa_adaptive.extraction import _measure
    u, p = _plan("protected_area_overlap_pct")
    m = _measure(p, u, {"overlap_m2": 3e6, "unit_m2": 1e6, "n_near": 2, "distance_m": 0})
    assert m.value is None and m.status == "out_of_range_review"


def test_missing_range_fields_raise_instead_of_counting_zero(fake_ee):
    from darukaa_adaptive.extraction import _measure
    u, p = _plan("threatened_species_range_count")
    m = _measure(p, u, {"mammals": 0, "fields_mammals": False, "birds": 3, "fields_birds": True})
    assert m.status == "error" and m.value is None


def test_natural_mask_requires_metric_crs(fake_ee):
    from darukaa_adaptive.natural_mask import build_mask
    with pytest.raises(ValueError):
        build_mask("REGION", "2025-08-01", "2026-09-01")


def test_fire_spec_records_images_per_year(fake_ee):
    u, p = _plan("fire_frequency")
    spec, _ = p.spec
    assert set(spec.extras["images_per_year"]) == {str(y) for y in range(2016, 2026)}


def test_context_window_grows_when_support_falls_short(monkeypatch):
    """R2 run 24 Oct: a 4-pixel window held 3.x natural pixel-equivalents for EII."""
    import darukaa_adaptive.extraction as X
    calls = []

    def fake_once(unit, ids, ctx_base, min_px, factors):
        calls.append(dict(factors))
        out = {}
        for mid in ids:
            f = factors.get(mid, 1.0)
            st, v = ("below_min_support", None) if f < 2 else ("scored_context_scale", 0.7)
            out[mid] = Measurement(mid, unit.unit_id, unit.level, v, st, covered_pixel_equivalent=3.8 * f, context_buffer_m=150 * f)
        return out
    from darukaa_adaptive.measurement import Measurement
    monkeypatch.setattr(X, "_measure_once", fake_once)
    res = X.measure_units([Unit("S", "site", box(73.8, 18.6, 73.8005, 18.6005))], ["eii_functional", "ndvi_peak_season"], _ctx_base())
    by = {m.metric: m for m in res}
    assert by["eii_functional"].status == "scored_context_scale" and by["eii_functional"].value == 0.7
    assert calls[1] == {"eii_functional": 2.0}       # only the coarse metric is retried
    assert by["ndvi_peak_season"].status == "below_min_support"  # fine metric: no window, stays unsupported


def test_threatened_count_excludes_asset_without_confirmed_category_field(fake_ee):
    """Karpa run 26 Oct: the birds snapshot has no 'category' field."""
    from darukaa_adaptive.extraction import _measure
    u, p = _plan("threatened_species_range_count")
    spec, _ = p.spec
    assert set(spec.lazy) == {"mammals", "fields_mammals"}          # birds not queried
    m = _measure(p, u, {"mammals": 4, "fields_mammals": True})
    assert m.value == 4 and m.extras["excluded_unconfirmed_field"] == ["birds"]
