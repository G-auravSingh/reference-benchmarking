import tempfile
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from shapely.geometry import Polygon

from darukaa_adaptive.benchmark import benchmark_metric, benchmark_observation, intactness_ratio, percent_change
from darukaa_adaptive.config import AssessmentConfig
from darukaa_adaptive.periods import annual_periods, month_periods
from darukaa_adaptive.registry import AQUATIC_INDICATORS, LEGACY_METRIC_SPECS, PILLARS, indicator_table
from darukaa_adaptive.site import area_ha, make_shapely_domains, read_kml, validate_site_geometry
from darukaa_adaptive.scoring import aggregate_overall, aggregate_pillars, concern_label, geometric_mean, build_scorecard, score_external_observations
from darukaa_adaptive.trajectory import compare


def test_ratio_and_percent_change():
    assert intactness_ratio(80, 100, True) == 0.8
    assert intactness_ratio(80, 100, False) == 1.0
    assert round(percent_change(110, 100), 6) == 10.0


def test_benchmark_tier1_priority_and_intactness():
    result = benchmark_metric("ndci_proxy", 0.05, 0.10, 0.20, tier1_approved=True)
    assert result.selected_reference_level == "tier1"
    assert result.selected_reference == 0.10
    assert result.intactness_ratio == 1.0
    assert result.intactness_score_0_100 == 100.0
    assert result.reference_approved_for_scoring is True


def test_contextual_metric_is_not_referenceable():
    result = benchmark_metric("riparian_ndvi_sen_slope", -0.01, -0.01, None)
    assert result.benchmark_status == "not_referenceable"
    assert result.selected_reference is None


def test_fixed_concern_bands():
    assert concern_label(0) == "Very High"
    assert concern_label(19.999) == "Very High"
    assert concern_label(20) == "High"
    assert concern_label(40) == "Moderate"
    assert concern_label(60) == "Low"
    assert concern_label(80) == "Very Low"
    assert concern_label(100) == "Very Low"


def test_geometric_mean_and_target_reference():
    assert round(geometric_mean([25, 100]), 6) == 50.0
    result = benchmark_observation("water_extent", 40, 50, "reference_target")
    assert result.intactness_score_0_100 == 80.0
    assert result.comparison_method == "distance_from_reference"


def test_pillar_and_overall_geometric_mean():
    cfg = AssessmentConfig()
    scored = pd.DataFrame([
        {"metric": "a", "pillar": "C1_extent", "intactness_score_0_100": 90, "score_eligible": True},
        {"metric": "b", "pillar": "C1_extent", "intactness_score_0_100": 50, "score_eligible": True},
        {"metric": "c", "pillar": "C2_vegetation", "intactness_score_0_100": 80, "score_eligible": True},
        {"metric": "d", "pillar": "C3_fauna", "intactness_score_0_100": 60, "score_eligible": True},
        {"metric": "e", "pillar": "C4_pressure", "intactness_score_0_100": 20, "score_eligible": True},
    ])
    pillars = aggregate_pillars(scored, cfg)
    c1 = float(pillars.loc[pillars.pillar == "C1_extent", "score_0_to_100"].iloc[0])
    assert round(c1, 6) == round(geometric_mean([90, 50]), 6)
    assert pillars.loc[pillars.pillar == "C1_extent", "limiting_metric"].iloc[0] == "b"
    overall = aggregate_overall(pillars, cfg)
    expected = geometric_mean([geometric_mean([90, 50]), 80, 60, 20])
    assert round(overall["score_0_to_100"], 6) == round(expected, 6)
    assert overall["limiting_pillar"] == "C4_pressure"
    assert overall["limiting_metric"] == "e"


def test_build_scorecard_keeps_unscored_metrics():
    cfg = AssessmentConfig()
    metric = next(x for x in AQUATIC_INDICATORS if x.name == "ndci_proxy")
    result = SimpleNamespace(
        metric=metric.name, pillar=metric.pillar, construct=metric.construct,
        subdimension=metric.subdimension, domain=metric.domain, value=0.05,
        units=metric.units, status="ok", temporal_window="x", dataset="x",
        scale_m=10, direction=metric.direction, evidence_tier="baseline",
        reference_type=metric.reference_type, reference_allowed=True,
        score_eligible=False, valid_observations=1, valid_pixels=1,
        std_dev=None, p05=None, p95=None, notes=""
    )
    bench = benchmark_metric("ndci_proxy", 0.05, 0.10, None, tier1_approved=False)
    metric_df, pillar_df, overall = build_scorecard([result], [bench], cfg)
    assert len(metric_df) == 1
    assert bool(metric_df.iloc[0]["score_eligible"]) is False
    assert metric_df.iloc[0]["score_status"] == "reference_not_approved_for_scoring"


def test_external_field_observations_use_same_scoring():
    cfg = AssessmentConfig()
    df = pd.DataFrame([{
        "metric": "species_richness", "pillar": "C3_fauna", "raw_value": 40,
        "direction": "higher_is_better", "reference_value": 50,
        "reference_type": "field_reference", "reference_level": "tier1",
        "reference_approved_for_scoring": True,
    }])
    metric_df, pillar_df, overall = score_external_observations(df, cfg)
    assert metric_df.loc[0, "intactness_score_0_100"] == 80
    assert metric_df.loc[0, "concern_label"] == "Very Low"
    assert bool(metric_df.loc[0, "score_eligible"]) is True
    assert round(float(pillar_df.loc[pillar_df.pillar == "C3_fauna", "score_0_to_100"].iloc[0]), 6) == 80.0


def test_geometry():
    poly = Polygon([(74, 17.5), (74.001, 17.5), (74.001, 17.501), (74, 17.501)])
    assert area_ha(poly) > 0
    qa = validate_site_geometry(poly)
    assert qa["valid"]
    domains = make_shapely_domains(poly, 100, 1)
    assert domains["riparian_fixed"].area > 0
    assert domains["context"].area > domains["riparian_fixed"].area


def test_kml_reader():
    text = '<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark><name>Nandoshi</name><Polygon><outerBoundaryIs><LinearRing><coordinates>74,17,0 74.001,17,0 74.001,17.001,0 74,17,0 74,17,0</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></Document></kml>'
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


def test_registry_has_four_pillars_and_legacy_crosswalk():
    assert PILLARS == {"C1_extent": "Extent", "C2_vegetation": "Vegetation", "C3_fauna": "Fauna", "C4_pressure": "Pressure"}
    names = {x.name for x in AQUATIC_INDICATORS}
    assert {"water_extent", "ndci_proxy", "shoreline_disturbance_fraction"}.issubset(names)
    assert "riparian_ndvi" in names
    assert len(LEGACY_METRIC_SPECS) == 44
    assert len(indicator_table()) == len(AQUATIC_INDICATORS)


def test_trajectory_same_window_semantics(tmp_path):
    base = pd.DataFrame([{"metric": "x", "value": 10, "units": "u", "direction": "higher_is_better", "temporal_window": "2025-08-01:2026-09-01", "status": "ok"}])
    cur = pd.DataFrame([{"metric": "x", "value": 12, "units": "u", "direction": "higher_is_better", "temporal_window": "2025-08-01:2026-09-01", "status": "ok"}])
    bp = tmp_path / "base.csv"
    cp = tmp_path / "cur.csv"
    base.to_csv(bp, index=False)
    cur.to_csv(cp, index=False)
    result = compare(cp, bp)
    assert result.loc[0, "delta"] == 2
    assert result.loc[0, "change_flag"] == "changed_same_window"


def test_metric_qa_flags_only_data_quality_issues():
    from darukaa_adaptive.qa import qa_metrics
    good = SimpleNamespace(metric="x", pillar="C3_fauna", value=10, status="ok", valid_observations=5, valid_pixels=20, p05=1, p95=20)
    bad = SimpleNamespace(metric="y", pillar="C2_vegetation", value=None, status="ok", valid_observations=0, valid_pixels=0, p05=None, p95=None)
    qa = qa_metrics([good, bad]).set_index("metric")
    assert bool(qa.loc["x", "qa_pass"]) is True
    assert bool(qa.loc["y", "qa_pass"]) is False
    assert "missing_value" in qa.loc["y", "qa_flags"]
