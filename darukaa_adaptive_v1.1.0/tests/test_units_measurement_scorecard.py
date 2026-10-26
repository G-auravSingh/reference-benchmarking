import math

import numpy as np
import pytest
from shapely.geometry import Polygon, box

from darukaa_adaptive import catalogue as cat
from darukaa_adaptive.inputs import EMU, ProjectInput, load_boundary, load_project_inputs
from darukaa_adaptive.measurement import Measurement, check_measurement, failed, status_layers
from darukaa_adaptive.scorecard import (ReferenceSample, aggregate_pillar, area_weighted, bounded_regional,
                                        concern_0_10, concern_label, headline, reference_attainment, score_metric)
from darukaa_adaptive.site import area_ha, read_kml
from darukaa_adaptive.units import build_units, context_window

D = 0.009  # ~1 km in degrees at 18N


def _emu(i, x, y, size=0.002):
    g = box(x, y, x + size, y + size)
    return EMU(f"E{i}", g, area_ha=area_ha(g))


def _project(emus):
    return ProjectInput("p", "p", "<test>", emus)


# ------------------------------------------------------------------ units
def test_adjacent_emus_form_one_site_and_separated_polygons_form_separate_sites():
    adjacent = _project([_emu(1, 73.8, 18.6), _emu(2, 73.802, 18.6), _emu(3, 73.8, 18.602)])
    assert len(build_units(adjacent).sites) == 1
    separated = _project([_emu(1, 73.8, 18.6), _emu(2, 73.8 + 3 * D, 18.6), _emu(3, 73.8 + 30 * D, 18.6)])
    u = build_units(separated, site_cluster_distance_m=1000)
    assert len(u.sites) == 3
    assert "no_boundary_supplied" in u.flags[0]


def test_supplied_boundary_is_the_site_and_emu_share_is_reported():
    emus = [_emu(1, 73.8, 18.6), _emu(2, 73.803, 18.6)]
    boundary = box(73.799, 18.599, 73.806, 18.603)
    u = build_units(_project(emus), boundary)
    s = u.sites[0]
    assert s.boundary_source == "supplied_boundary"
    assert s.area_ha > s.emu_area_ha
    assert 0 < s.to_dict()["emu_share_of_site_pct"] < 100


def test_emu_outside_boundary_fails_loudly():
    with pytest.raises(ValueError):
        build_units(_project([_emu(1, 75.0, 18.6)]), box(73.799, 18.599, 73.806, 18.603))


def test_context_window_holds_four_native_pixels():
    small = box(73.8, 18.6, 73.8005, 18.6005)  # ~0.3 ha
    g, buf = context_window(small, 300.0, 4)
    assert buf > 0
    assert area_ha(g) >= 4 * 9.0 - 0.01
    big = box(73.8, 18.6, 73.83, 18.63)
    assert context_window(big, 300.0, 4)[1] == 0.0


def test_kml_keeps_holes_and_multiple_placemarks(tmp_path):
    kml = """<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
    <Placemark><name>a</name><Polygon><outerBoundaryIs><LinearRing><coordinates>
    73.80,18.60 73.81,18.60 73.81,18.61 73.80,18.61 73.80,18.60</coordinates></LinearRing></outerBoundaryIs>
    <innerBoundaryIs><LinearRing><coordinates>73.802,18.602 73.804,18.602 73.804,18.604 73.802,18.604 73.802,18.602
    </coordinates></LinearRing></innerBoundaryIs></Polygon></Placemark>
    <Placemark><name>b</name><MultiGeometry><Polygon><outerBoundaryIs><LinearRing><coordinates>
    73.82,18.60 73.83,18.60 73.83,18.61 73.82,18.60</coordinates></LinearRing></outerBoundaryIs></Polygon>
    <Polygon><outerBoundaryIs><LinearRing><coordinates>
    73.84,18.60 73.85,18.60 73.85,18.61 73.84,18.60</coordinates></LinearRing></outerBoundaryIs></Polygon></MultiGeometry></Placemark>
    </Document></kml>"""
    p = tmp_path / "two.kml"
    p.write_text(kml)
    _, parts = read_kml(p)
    assert len(parts["a"].interiors) == 1
    assert parts["b"].geom_type == "MultiPolygon"


def test_multiple_kml_files_get_unique_ids(tmp_path):
    for name, x in (("Site_1", 73.80), ("Site_2", 73.90)):
        (tmp_path / f"{name}.kml").write_text(f"""<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark><name>x</name>
        <Polygon><outerBoundaryIs><LinearRing><coordinates>{x},18.6 {x+0.01},18.6 {x+0.01},18.61 {x},18.6</coordinates>
        </LinearRing></outerBoundaryIs></Polygon></Placemark></Document></kml>""")
    proj = load_project_inputs(sorted(tmp_path.glob("*.kml")), project_id="corbett")
    assert [e.emu_id for e in proj.emus] == ["Site_1", "Site_2"]
    assert load_boundary(tmp_path / "Site_1.kml").geom_type == "Polygon"


# ------------------------------------------------------------------ measurement
def test_failed_or_invalid_measurement_never_carries_a_value():
    m = Measurement("ndvi_peak_season", "u", "site", 0.0, "no_valid_pixels")
    assert m.value is None and not m.measured_valid
    m = Measurement("ndvi_peak_season", "u", "site", float("nan"), "ok")
    assert m.value is None and m.status == "no_valid_pixels"
    f = failed("ndvi_peak_season", "u", "site", RuntimeError("boom"))
    assert not f.ran and f.value is None


def test_support_and_range_gates():
    m = check_measurement(Measurement("bii", "u", "site", 0.4, "ok", covered_pixel_equivalent=2.5))
    assert m.status == "below_min_support" and m.value is None
    m = check_measurement(Measurement("bii", "u", "site", 1.4, "ok", covered_pixel_equivalent=50))
    assert m.status == "out_of_range_review" and m.value is None
    m = check_measurement(Measurement("bii", "u", "site", 0.4, "ok", covered_pixel_equivalent=50))
    assert m.measured_valid


def test_four_status_layers_are_separate():
    ok = Measurement("bii", "u", "site", 0.4, "ok", covered_pixel_equivalent=50)
    assert status_layers(ok, "contextual", None, None, True).measured_valid
    assert not status_layers(ok, "contextual", None, None, True).sufficient_to_score
    l = status_layers(ok, "scored", 80.0, "Low", True)
    assert l.sufficient_to_score and not l.interpretable
    assert not status_layers(failed("bii", "u", "site", ValueError()), "scored", None, None, True).ran


# ------------------------------------------------------------------ response functions
def test_reference_attainment_caps_at_reference_and_rejects_bad_reference():
    assert reference_attainment(0.3, 0.6, "higher_is_better") == 50.0
    assert reference_attainment(0.9, 0.6, "higher_is_better") == 100.0
    assert reference_attainment(0.3, 0.0, "higher_is_better") is None


def test_bounded_pressure_response_decision_4():
    # ref 0.2, worst 0.6 -> obs 0.4 halfway -> 50
    assert bounded_regional(0.4, 0.2, 0.6, "lower_is_better")[0] == pytest.approx(50.0)
    assert bounded_regional(0.1, 0.2, 0.6, "lower_is_better")[0] == 100.0
    assert bounded_regional(0.9, 0.2, 0.6, "lower_is_better")[0] == 0.0
    # zero reference no longer collapses to 0 (the old ratio gave 0 for ref 0 / obs 0.15)
    s, basis = bounded_regional(0.15, 0.0, 0.6, "lower_is_better")
    assert s == pytest.approx(75.0) and basis == "regional_p95"
    # degenerate distribution falls back to the contract maximum, then refuses
    assert bounded_regional(0.5, 0.0, 0.0, "lower_is_better", fallback_worst=1.0) == (50.0, "contract_value_range_max")
    assert bounded_regional(0.5, 0.0, 0.0, "lower_is_better", fallback_worst=None) == (None, "degenerate_reference")


def test_concern_mappings():
    assert concern_label(85) == "Very Low" and concern_label(10) == "Very High"
    assert concern_0_10(100) == 0.0 and concern_0_10(0) == 10.0 and concern_0_10(None) is None


# ------------------------------------------------------------------ scoring with references
def _ref(metric, rtype, values, nblocks=12):
    vals = np.asarray(values, dtype=float)
    return ReferenceSample(metric, rtype, vals, np.arange(vals.size) % nblocks)


def test_score_metric_gives_interval_and_confidence():
    rng = np.random.default_rng(1)
    ref = _ref("ndvi_peak_season", "reference_condition", rng.normal(0.6, 0.05, 400))
    m = Measurement("ndvi_peak_season", "SITE_01", "site", 0.45, "ok", covered_pixel_equivalent=500)
    s = score_metric(m, "scored", ref)
    assert 70 < s.score < 80
    assert s.interval[0] <= s.score <= s.interval[1]
    assert s.confidence == "High"


def test_small_reference_is_not_scored_and_context_scale_downgrades_confidence():
    small = _ref("ndvi_peak_season", "reference_condition", [0.6] * 10, nblocks=2)
    m = Measurement("ndvi_peak_season", "u", "site", 0.45, "ok", covered_pixel_equivalent=500)
    assert score_metric(m, "scored", small).reference_status == "reference_insufficient"
    rng = np.random.default_rng(2)
    ref = _ref("bii", "reference_condition", rng.normal(0.7, 0.03, 300))
    m = Measurement("bii", "u", "site", 0.5, "scored_context_scale", covered_pixel_equivalent=5, context_buffer_m=150)
    s = score_metric(m, "scored", ref)
    assert s.confidence == "Low"  # context scale + pressure-modelled
    assert any("pressure-modelled" in r for r in s.confidence_reasons)


def test_unscored_role_and_invalid_measurement_produce_no_score():
    ref = _ref("ghm", "regional_context", np.linspace(0, 1, 200))
    assert score_metric(Measurement("ghm", "u", "site", 0.3, "ok"), "contextual", ref).score is None
    assert score_metric(Measurement("ghm", "u", "site", None, "no_valid_pixels"), "scored", ref).score is None


def test_natural_scale_metric_has_no_reference_and_zero_width_interval():
    s = score_metric(Measurement("natural_extent_pct", "u", "site", 64.0, "ok", covered_pixel_equivalent=1e4), "scored", None)
    assert s.score == 64.0 and s.interval == (64.0, 64.0) and s.reference_status == "natural_scale"


def _ms(metric, score, n=50):
    c = cat.get(metric)
    from darukaa_adaptive.scorecard import MetricScore
    return MetricScore(metric, "u", c.pillar, c.component, "scored", 1.0, score, (score, score), np.full(n, score),
                       "ok", None, None, None, None, "", "High")


def test_pillar_is_limited_by_weakest_component_and_gated():
    ps = [_ms("natural_extent_pct", 80), _ms("natural_gross_loss_pct", 90), _ms("tree_cover_loss_rate", 40),
          _ms("natural_core_area_pct", 70)]
    p = aggregate_pillar(ps, "u", "P1")
    assert p.status == "scored"
    assert p.limiting_component == "change" and p.score == pytest.approx(math.sqrt(90 * 40))
    p2 = aggregate_pillar(ps[:2], "u", "P1")
    assert p2.score is None and p2.status == "insufficient_evidence"


def test_zero_component_is_flagged():
    ps = [_ms("natural_extent_pct", 0.0), _ms("tree_cover_loss_rate", 60), _ms("natural_core_area_pct", 70)]
    p = aggregate_pillar(ps, "u", "P1")
    assert p.score == 0.0 and any("scored 0" in f for f in p.flags)


def test_headline_uses_p1_p2_and_keeps_pressure_separate():
    p1 = aggregate_pillar([_ms("natural_extent_pct", 81), _ms("tree_cover_loss_rate", 81), _ms("natural_core_area_pct", 81)], "u", "P1")
    p2 = aggregate_pillar([_ms("ndvi_peak_season", 64), _ms("lai_s2", 64), _ms("bii", 64)], "u", "P2")
    p4 = aggregate_pillar([_ms("built_fraction", 10), _ms("road_density", 10), _ms("fire_frequency", 10)], "u", "P4")
    h = headline({"P1": p1, "P2": p2, "P4": p4}, "u")
    assert h.son_score == pytest.approx(72.0)
    assert h.son_pillars == ["P1", "P2"] and h.son_status == "scored_without_P3"
    assert h.pressure_score == pytest.approx(10.0)
    h2 = headline({"P1": p1, "P4": p4}, "u")
    assert h2.son_score is None and "P2" in h2.son_status and h2.weakest_pillar is None


def _ms_c(metric, score, conf):
    m = _ms(metric, score)
    m.confidence = conf
    return m


def test_son_score_carries_weakest_pillar_confidence_coverage_and_label():
    """P-27-2 (approved 27 Oct): equal-weight geometric mean, always with its companions."""
    p1 = aggregate_pillar([_ms("natural_extent_pct", 90), _ms("tree_cover_loss_rate", 90), _ms("natural_core_area_pct", 90)], "u", "P1")
    p2 = aggregate_pillar([_ms_c("ndvi_peak_season", 40, "Medium"), _ms("lai_s2", 60), _ms("bii", 60)], "u", "P2")
    h = headline({"P1": p1, "P2": p2}, "u")
    assert h.son_score == pytest.approx((90 * 40) ** 0.5)
    assert h.weakest_pillar == "P2" and h.weakest_pillar_score == pytest.approx(40)
    assert h.son_confidence == "Medium"                      # lowest of the contributing pillars
    assert "species" in h.coverage_label and "not covered" in h.coverage_label
    assert "Darukaa composite" in h.label and "not a Nature Positive standard metric" in h.label
    assert h.son_divergence_flag is None                    # 60 - 40 = 20, not more than 20
    p1b = aggregate_pillar([_ms("natural_extent_pct", 95), _ms("tree_cover_loss_rate", 95), _ms("natural_core_area_pct", 95)], "u", "P1")
    p2b = aggregate_pillar([_ms("ndvi_peak_season", 20), _ms("lai_s2", 60), _ms("bii", 60)], "u", "P2")
    hb = headline({"P1": p1b, "P2": p2b}, "u")
    assert hb.son_divergence_flag and "P2" in hb.son_divergence_flag
    row = hb.row()
    for k in ("son_score_0_100", "weakest_pillar", "weakest_pillar_score", "son_confidence", "coverage_label", "son_divergence_flag"):
        assert k in row


def test_son_score_never_includes_pressure():
    p1 = aggregate_pillar([_ms("natural_extent_pct", 80), _ms("tree_cover_loss_rate", 80), _ms("natural_core_area_pct", 80)], "u", "P1")
    p2 = aggregate_pillar([_ms("ndvi_peak_season", 80), _ms("lai_s2", 80), _ms("bii", 80)], "u", "P2")
    p4 = aggregate_pillar([_ms("built_fraction", 1), _ms("road_density", 1), _ms("fire_frequency", 1)], "u", "P4")
    assert headline({"P1": p1, "P2": p2, "P4": p4}, "u").son_score == pytest.approx(80)


def test_area_weighted_rollup_labels_contribution():
    r = area_weighted([("a", 10.0, 50.0, np.full(5, 50.0)), ("b", 30.0, 90.0, np.full(5, 90.0)), ("c", 60.0, None, None)])
    assert r.value == pytest.approx(80.0)
    assert r.n_contributing == 2 and r.area_share_pct == pytest.approx(40.0)
    assert "2 of 3 units, 40.0% of area" in r.label


# ------------------------------------------------------------------ option B pressure reference (D-25-1)
def test_low_pressure_blocks_are_selected_by_natural_share_with_ladder():
    from darukaa_adaptive.reference_pool import PoolConfig, select_low_pressure_blocks
    cfg = PoolConfig()
    strict = {f"b{i}": 95.0 for i in range(25)} | {f"c{i}": 10.0 for i in range(50)}
    ids, stage = select_low_pressure_blocks(strict, cfg)
    assert len(ids) == 25 and stage.startswith("strict")
    partly = {f"b{i}": 0.7 * i for i in range(120)}          # max 83 % natural, 48 blocks >= 50 %
    ids, stage = select_low_pressure_blocks(partly, cfg)
    assert len(ids) == 24 and stage.startswith("quantile") and min(partly[b] for b in ids) >= 50
    converted = {f"b{i}": 0.3 + 0.01 * i for i in range(120)}  # Ludhiana-like: nothing near natural
    ids, stage = select_low_pressure_blocks(converted, cfg)
    assert ids == [] and stage == "reference_insufficient"     # floor (D-26-1): never compare with cropland
    ids, stage = select_low_pressure_blocks({"a": 99.0, "b": None}, cfg)
    assert ids == [] and stage == "reference_insufficient"


def test_intensive_region_no_longer_flatters_pressure():
    """R2 run 1: Ludhiana cropland scored P4 = 100 against an all-cropland ring (option A)."""
    rng = np.random.default_rng(3)
    ring_all = _ref("ghm", "regional_context", rng.uniform(0.45, 0.75, 120))
    low = _ref("ghm", "regional_context", rng.uniform(0.02, 0.08, 25), nblocks=10)
    low.min_n = 20
    m = Measurement("ghm", "u", "site", 0.61, "ok", covered_pixel_equivalent=700)
    s = score_metric(m, "scored", low, worst_ref=ring_all)
    assert s.score < 30 and s.reference_status == "ok" and "low-pressure" in s.basis
    a = score_metric(Measurement("built_fraction", "u", "site", 0.04, "ok"), "scored", None)
    assert a.score is None and a.reference_status == "reference_missing"
    missing_worst = score_metric(m, "scored", low, worst_ref=None)
    assert missing_worst.score is None and missing_worst.reference_status == "regional_distribution_missing"


def test_ghm_absolute_class():
    from darukaa_adaptive.scorecard import ghm_class
    assert ghm_class(0.01).startswith("low") and ghm_class(0.61).startswith("high") and ghm_class(0.98).startswith("very high")


def test_no_pressure_metric_selects_its_own_reference():
    for c in cat.CATALOGUE:
        if c.pillar == "P4" and c.can_score:
            assert c.reference_type == "low_pressure"


def test_pillar_reports_the_metric_that_sets_it():
    """Karpa run 26 Oct: one Medium-confidence metric (canopy height) set P2 to 0.3."""
    from darukaa_adaptive.scorecard import MetricScore
    def ms(metric, score, conf, reasons=()):
        c = cat.get(metric)
        return MetricScore(metric, "u", c.pillar, c.component, "scored", 1.0, score, (score, score), np.full(10, score),
                           "ok", None, None, None, None, "", conf, list(reasons))
    p = aggregate_pillar([ms("ndvi_peak_season", 95, "High"), ms("canopy_height_m", 0.3, "Medium", ["data 6 years from assessment window"]),
                          ms("bii", 86, "Medium")], "u", "P2")
    assert p.limiting_metric == "canopy_height_m" and p.limiting_confidence == "Medium"
    assert any("pillar set by canopy_height_m" in f for f in p.flags)
