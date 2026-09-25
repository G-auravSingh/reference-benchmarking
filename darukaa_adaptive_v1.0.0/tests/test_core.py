import json
import tempfile
from pathlib import Path

import pandas as pd
from shapely.geometry import Polygon

from darukaa_adaptive.benchmark import benchmark_metric, intactness_ratio, percent_change
from darukaa_adaptive.config import AssessmentConfig
from darukaa_adaptive.periods import annual_periods, month_periods
from darukaa_adaptive.registry import AQUATIC_INDICATORS, LEGACY_METRIC_SPECS, indicator_table
from darukaa_adaptive.site import area_ha, make_shapely_domains, read_kml, validate_site_geometry
from darukaa_adaptive.scoring import (
    aggregate_overall,
    aggregate_pillars,
    concern_label,
    overall_concern_label,
    score_from_intactness,
    score_with_thresholds,
)
from darukaa_adaptive.trajectory import compare


def test_ratio_and_percent_change():
    assert intactness_ratio(80, 100, True) == 0.8
    assert intactness_ratio(80, 100, False) == 1.0
    assert round(percent_change(110, 100), 6) == 10.0


def test_benchmark_tier1_priority():
    result = benchmark_metric("ndci_proxy", 0.05, 0.10, 0.20)
    assert result.selected_reference_level == "tier1"
    assert result.selected_reference == 0.10
    assert result.intactness_ratio == 1.0


def test_contextual_metric_is_not_referenceable():
    result = benchmark_metric("water_extent", 40, 50, 60)
    assert result.benchmark_status == "not_referenceable"
    assert result.selected_reference is None


def test_threshold_scoring():
    th = {"t1": 0.1, "t2": 0.2, "t3": 0.3, "t4": 0.4}
    assert score_with_thresholds(0.05, th, True) == 1
    assert score_with_thresholds(0.5, th, True) == 5
    assert score_with_thresholds(0.05, th, False) == 5


def test_reference_relative_scoring():
    assert score_from_intactness(0.2, {"r1": 0.5, "r2": 0.7, "r3": 0.85, "r4": 0.95}) == 5
    assert score_from_intactness(0.98, {"r1": 0.5, "r2": 0.7, "r3": 0.85, "r4": 0.95}) == 1


def test_labels():
    assert concern_label(1.0) == "Very Low"
    assert concern_label(3.0) == "Moderate"
    assert concern_label(5.0) == "Very High"
    assert overall_concern_label(4.5) == "Low"
    assert overall_concern_label(6.0) == "Moderate"


def test_pillar_and_overall_gating():
    cfg = AssessmentConfig()
    cfg.scoring.composite_son_enabled = True
    df = pd.DataFrame([
        {"metric": "a", "pillar": "P1_ecosystem_condition", "concern_score_1_to_5": 2, "score_eligible": True},
        {"metric": "b", "pillar": "P2_species_assemblage", "concern_score_1_to_5": 3, "score_eligible": True},
        {"metric": "c", "pillar": "P3_species_status", "concern_score_1_to_5": 4, "score_eligible": True},
        {"metric": "d", "pillar": "P4_threats", "concern_score_1_to_5": 5, "score_eligible": True},
    ])
    pillars = aggregate_pillars(df, cfg)
    overall = aggregate_overall(pillars, cfg)
    assert overall["status"] == "scored"
    assert round(overall["score_0_to_10"], 6) == 6.25

    incomplete = pillars[pillars["pillar"] != "P4_threats"].copy()
    gated = aggregate_overall(incomplete, cfg)
    assert gated["score_0_to_10"] is None
    assert gated["status"] in {"insufficient_pillar_coverage", "incomplete_pillar_coverage"}


def test_geometry():
    poly = Polygon([(74, 17.5), (74.001, 17.5), (74.001, 17.501), (74, 17.501)])
    assert area_ha(poly) > 0
    qa = validate_site_geometry(poly)
    assert qa["valid"]
    domains = make_shapely_domains(poly, 100, 1)
    assert domains["riparian_fixed"].area > 0
    assert domains["context"].area > domains["riparian_fixed"].area


def test_kml_reader():
    text = '''<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark><name>Nandoshi</name><Polygon><outerBoundaryIs><LinearRing><coordinates>74,17,0 74.001,17,0 74.001,17.001,0 74,17.001,0 74,17,0</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></Document></kml>'''
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.kml"
        p.write_text(text)
        geom, parts = read_kml(p)
        assert geom.area > 0
        assert parts


def test_config_baseline_dates_and_yaml():
    cfg = AssessmentConfig()
    start, exclusive_end = cfg.temporal.baseline_dates()
    assert start == "2025-08-01"
    assert exclusive_end == "2026-09-01"
    assert cfg.validate() == []

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "profile.yaml"
        p.write_text("gEE:\n  project_id: abc\ntemporal:\n  baseline_start_date: 2025-08-01\n  baseline_end_date: 2026-08-31\n")
        loaded = AssessmentConfig.from_yaml(p)
        assert loaded.gee.project_id == "abc"
        assert loaded.temporal.baseline_dates()[1] == "2026-09-01"


def test_period_helpers():
    months = month_periods("2025-08-01", "2026-08-31")
    assert len(months) == 13
    assert months[0]["label"] == "2025-08"
    assert months[-1]["label"] == "2026-08"
    years = annual_periods(2018, 2026)
    assert len(years) == 9
    assert years[0]["start"] == "2018-01-01"
    assert years[-1]["end"] == "2027-01-01"


def test_registry_has_aquatic_contracts_and_legacy_crosswalk():
    names = {x.name for x in AQUATIC_INDICATORS}
    assert {"water_extent", "ndci_proxy", "shoreline_disturbance_fraction"}.issubset(names)
    assert len(LEGACY_METRIC_SPECS) == 44
    assert len(indicator_table()) == len(AQUATIC_INDICATORS)


def test_trajectory_same_window_semantics(tmp_path):
    base = pd.DataFrame([
        {"metric": "x", "value": 10, "units": "u", "direction": "higher_is_better", "temporal_window": "2025-08-01:2026-09-01", "status": "ok"}
    ])
    cur = pd.DataFrame([
        {"metric": "x", "value": 12, "units": "u", "direction": "higher_is_better", "temporal_window": "2025-08-01:2026-09-01", "status": "ok"}
    ])
    bp = tmp_path / "base.csv"
    cp = tmp_path / "cur.csv"
    base.to_csv(bp, index=False)
    cur.to_csv(cp, index=False)
    result = compare(cp, bp)
    assert result.loc[0, "delta"] == 2
    assert result.loc[0, "change_flag"] == "changed_same_window"
