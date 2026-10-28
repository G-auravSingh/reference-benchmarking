"""Canopy-height evidence rules (D-28-1: P-27-4 + P-27-5) and preparatory P3 metrics (D-28-2)."""
import sys
from unittest import mock

import pytest
from shapely.geometry import box

from darukaa_adaptive import catalogue as cat
from darukaa_adaptive import layers as L
from darukaa_adaptive.extraction import Unit, plan_unit, _measure
from darukaa_adaptive.measurement import Measurement


@pytest.fixture
def fake_ee(monkeypatch):
    ee = mock.MagicMock(name="ee")
    monkeypatch.setitem(sys.modules, "ee", ee)
    return ee


def _ctx_base(options=None):
    return {"crs": "EPSG:32643", "start": "2025-08-01", "end_exclusive": "2026-09-01", "mask": mock.MagicMock(),
            "peak_window": ("2025-09-01", "2025-12-01"), "raster_paths": {}, "options": options or {}}


def _plan(metric, options=None):
    u = Unit("S", "site", box(79.0, 29.5, 79.01, 29.51))
    return u, {p.metric: p for p in plan_unit(u, [metric], _ctx_base(options))}[metric]


# ---------------------------------------------------------------- canopy height
def _chm(value, **ev):
    extras = {"evidence": ev}
    return Measurement("canopy_height_m", "S", "site", value, "ok", covered_pixel_equivalent=5000.0, extras=extras)


def test_canopy_contract_says_what_is_measured_and_its_caveats():
    c = cat.get("canopy_height_m")
    for text in ("1 m", "gaps", "natural forest", "woodland", "shrub", "2018", "25 m"):
        assert text in c.definition + " " + c.notes, text


def test_canopy_spec_uses_epoch_consistent_woody_pixels_and_collects_evidence(fake_ee):
    u, p = _plan("canopy_height_m")
    spec, _ = p.spec
    assert spec.weight == "canopy_eligible"
    assert {"meta_p95_30m", "meta_cover_2m", "glad", "gedi", "areas"} <= set(spec.extras)
    assert spec.qa is not None


def test_below_detection_is_not_a_zero():
    m = L.canopy_qa(_chm(0.002, areas={"woody_ha": 14.6, "eligible_ha": 14.6}))
    assert m.status == "below_detection" and m.value is None
    assert m.extras["raw_mean_m"] == pytest.approx(0.002)
    assert "below" in m.extras["sources"]["meta_mean"]["reading"]


def test_like_for_like_disagreement_withholds_the_value():
    # Meta p95 at 30 m 5 m against GLAD 14.6 m over the same pixels: 66% apart
    m = L.canopy_qa(_chm(4.8, meta_p95_30m=5.0, glad={"mean": 14.6, "count": 12},
                         areas={"woody_ha": 0.5, "eligible_ha": 0.5}))
    assert m.status == "source_disagreement" and m.value is None
    assert m.extras["disagreement"][0]["against"] == "glad"


def test_mean_against_top_height_is_not_used_for_disagreement():
    # Gap-inclusive mean 4.8 m vs GLAD 14.6 m is not like-for-like; p95 at 30 m (12 m) is within 50%
    m = L.canopy_qa(_chm(4.8, meta_p95_30m=12.0, glad={"mean": 14.6, "count": 12},
                         areas={"woody_ha": 0.5, "eligible_ha": 0.5}))
    assert m.status == "ok" and m.value == pytest.approx(4.8)


def test_gedi_below_its_floor_is_not_evidence_of_disagreement():
    m = L.canopy_qa(_chm(6.0, meta_p95_30m=9.0, gedi={"median": 3.3, "count": 95},
                         areas={"woody_ha": 10, "eligible_ha": 10}))
    assert m.status == "ok"
    assert "below" in m.extras["sources"]["gedi_rh98"]["reading"]


def test_canopy_newer_than_the_source_is_reported_not_scored():
    m = Measurement("canopy_height_m", "S", "site", None, "no_valid_pixels", extras={"evidence": {
        "areas": {"woody_ha": 14.6, "eligible_ha": 0.0}}})
    m = L.canopy_qa(m)
    assert m.status == "source_predates_state" and m.value is None
    assert m.extras["excluded_post_epoch_ha"] == pytest.approx(14.6)


def test_agreeing_sources_keep_the_value():
    m = L.canopy_qa(_chm(15.7, meta_p95_30m=20.0, glad={"mean": 17.0, "count": 500}, gedi={"median": 23.0, "count": 400},
                         areas={"woody_ha": 470, "eligible_ha": 465}))
    assert m.status == "ok" and m.value == pytest.approx(15.7)
    assert m.extras["excluded_post_epoch_ha"] == pytest.approx(5.0)


def test_qa_hook_runs_inside_measure(fake_ee):
    u, p = _plan("canopy_height_m")
    raw = {"stats": {"v_mean": 0.003, "w_sum": 15000.0, "w_count": 15100}, "x_meta_p95_30m": {"v": 0.0},
           "x_meta_cover_2m": {"v": 0.0}, "x_glad": {"v_mean": 0.0, "v_count": 160}, "x_gedi": {"v_median": 3.3, "v_count": 95},
           "x_areas": {"woody": 146000.0, "eligible": 146000.0}}
    m = _measure(p, u, raw)
    assert m.status == "below_detection" and m.value is None


def test_glad_and_gedi_contextual_readings_below_floor_are_flagged(fake_ee):
    u, p = _plan("gedi_rh98_m")
    m = _measure(p, u, {"stats": {"v_mean": 3.3, "w_sum": 95.0, "w_count": 95}})
    assert m.status == "below_detection" and m.value is None
    u, p = _plan("canopy_height_glad_m")
    m = _measure(p, u, {"stats": {"v_mean": 0.0, "v_p95": 0.0, "w_sum": 160.0, "w_count": 160}})
    assert m.status == "below_detection"


# ---------------------------------------------------------------- P3 preparatory
def _rows():
    return [  # sci_name, group, category, global_km2, site_km2, h2020_km2, hnow_km2, gain_km2
        ("Panthera tigris", "mammals", "EN", 1_000_000, 1.5, 0.15, 0.149, 1.28),
        ("Gyps bengalensis", "birds", "CR", 2_000_000, 1.5, 0.15, 0.15, 0.0),
        ("Rare plant", "plants", "VU", 50, 0.5, 0.05, 0.02, 0.0),
        ("Common bird", "birds", "LC", 5_000_000, 1.5, 0.15, 0.15, 0.0),
        ("Near bird", "birds", "NT", 3_000_000, 1.5, 0.0, 0.0, 0.0),
    ]


def test_star_t_estimate_uses_standard_threat_weights_and_range_share():
    rows = _rows()
    value, ex = L.star_t_from_rows(rows, site_km2=1.5)
    expected = 100 * (3 * 1.5 / 1e6 + 4 * 1.5 / 2e6 + 2 * 0.5 / 50 + 1 * 1.5 / 3e6)
    assert value == pytest.approx(expected)
    assert ex["n_species"] == 5 and ex["weights"] == {"CR": 4, "EN": 3, "VU": 2, "NT": 1, "LC": 0}
    assert ex["top_contributors"][0]["sci_name"] == "Rare plant"


def test_rarity_weighted_richness_counts_all_categories():
    value, ex = L.rarity_from_rows(_rows(), site_km2=1.5)
    assert value == pytest.approx(1.5 / 1e6 + 1.5 / 2e6 + 0.5 / 50 + 1.5 / 5e6 + 1.5 / 3e6)


def test_site_share_never_exceeds_site_area():
    rows = [("X", "mammals", "EN", 10.0, 3.0, 0, 0, 0)]       # overlapping seasonal polygons summed to 3 km2
    value, ex = L.star_t_from_rows(rows, site_km2=1.5)
    assert value == pytest.approx(100 * 3 * 1.5 / 10.0)


def test_habitat_trend_classes_follow_the_npi_metric():
    pct, ex = L.habitat_trend_from_rows(_rows(), threshold=0.05)
    # priority = CR/EN/VU: tiger (stable, candidate gain -> increasing_candidate), vulture (stable), plant (declining)
    assert ex["counts"] == {"declining": 1, "stable": 1, "increasing_candidate": 1, "slowing_in_decline": None}
    assert pct == pytest.approx(100 / 3)
    assert ex["n_priority"] == 3


def test_no_priority_species_is_not_a_zero_percent():
    rows = [("Common bird", "birds", "LC", 5e6, 1.5, 0.15, 0.15, 0.0)]
    pct, ex = L.habitat_trend_from_rows(rows, threshold=0.05)
    assert pct is None and ex["reason"] == "no priority (CR/EN/VU) species on site"


def test_no_species_at_all_is_an_error_not_zero():
    with pytest.raises(ValueError):
        L.star_t_from_rows([], site_km2=1.5)


def test_new_p3_metrics_have_full_contracts():
    for mid in ("star_t_estimated", "rarity_weighted_richness", "priority_species_habitat_trend"):
        c = cat.get(mid)
        assert c.pillar == "P3" and c.granularity == "preparatory" and c.framework_tags and c.failure_modes
        assert c.recommended_role in {"contextual", "diagnostic"} and not c.can_score
        assert "range" in c.definition.lower()
        assert mid in L.BUILDERS


def test_species_builder_filters_extant_native_resident_breeding_and_checks_fields(fake_ee):
    u, p = _plan("star_t_estimated")
    spec, _ = p.spec
    assert {"mammals", "birds", "plants", "fields_mammals", "fields_birds", "fields_plants", "site_km2"} <= set(spec.lazy)
