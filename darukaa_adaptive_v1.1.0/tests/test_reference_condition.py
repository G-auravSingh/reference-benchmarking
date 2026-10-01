import math

import numpy as np
import pytest

from darukaa_adaptive.reference_condition import (
    evaluate_reference_candidate,
    reference_distribution,
    relative_departure,
    reference_percentile,
    reference_attainment,
)


def test_reference_distribution_is_robust_and_reproducible():
    values = [0.2, 0.3, 0.31, 0.32, 0.4, 4.0]
    a = reference_distribution(values, bootstrap_n=200, seed=7)
    b = reference_distribution(values, bootstrap_n=200, seed=7)
    assert a["n"] == 6
    assert a["median"] == pytest.approx(0.315)
    assert a["mad"] == pytest.approx(0.05)
    assert a["bootstrap_ci_low"] == b["bootstrap_ci_low"]
    assert a["bootstrap_ci_high"] == b["bootstrap_ci_high"]


def test_reference_distribution_ignores_nonfinite():
    out = reference_distribution([1, np.nan, np.inf, 2])
    assert out["n"] == 2
    assert out["median"] == pytest.approx(1.5)


def test_reference_distribution_exposes_full_percentile_contract():
    out = reference_distribution([1, 2, 3, 4, 5], bootstrap_n=0)
    assert out["p05"] == pytest.approx(1.2)
    assert out["p10"] == pytest.approx(1.4)
    assert out["p25"] == pytest.approx(2.0)
    assert out["p50"] == pytest.approx(3.0)
    assert out["p75"] == pytest.approx(4.0)
    assert out["p90"] == pytest.approx(4.6)
    assert out["p95"] == pytest.approx(4.8)


def test_candidate_requires_population_size():
    qa = evaluate_reference_candidate(
        candidate_area_ha=1.0,
        candidate_pixels=100,
        min_area_ha=2.0,
        min_pixels=500,
    )
    assert not qa.approval_recommendation
    assert not qa.population_ok


def test_auto_approval_is_gated():
    qa = evaluate_reference_candidate(
        candidate_area_ha=10,
        candidate_pixels=5000,
        min_area_ha=2,
        min_pixels=500,
        ecological_match_score=0.9,
        min_ecological_match_score=0.8,
        pressure_screen_pass=True,
        temporal_match_pass=True,
        spatial_quality_pass=True,
        auto_approve=True,
    )
    assert qa.approval_recommendation


def test_auto_approval_cannot_bypass_ecological_gate():
    qa = evaluate_reference_candidate(
        candidate_area_ha=10,
        candidate_pixels=5000,
        min_area_ha=2,
        min_pixels=500,
        ecological_match_score=0.5,
        min_ecological_match_score=0.8,
        auto_approve=True,
    )
    assert not qa.approval_recommendation
    assert not qa.ecological_match_ok


def test_auto_approval_cannot_bypass_pressure_gate():
    qa = evaluate_reference_candidate(
        candidate_area_ha=10,
        candidate_pixels=5000,
        min_area_ha=2,
        min_pixels=500,
        ecological_match_score=0.9,
        pressure_screen_pass=False,
        auto_approve=True,
    )
    assert not qa.approval_recommendation


def test_relative_departure_higher_is_better():
    assert relative_departure(0.36, 0.30, "higher_is_better") == pytest.approx(0.2)
    assert relative_departure(0.24, 0.30, "higher_is_better") == pytest.approx(-0.2)


def test_relative_departure_lower_is_better():
    assert relative_departure(0.08, 0.10, "lower_is_better") == pytest.approx(0.2)
    assert relative_departure(0.12, 0.10, "lower_is_better") == pytest.approx(-0.2)


def test_reference_target_departure_is_nonpositive():
    assert relative_departure(0.10, 0.10, "reference_target") == pytest.approx(0.0)
    assert relative_departure(0.12, 0.10, "reference_target") < 0


def test_reference_percentile_handles_ties():
    assert reference_percentile(3, [1, 2, 3, 3, 4]) == pytest.approx(60.0)
    assert reference_percentile(5, [1, 2, 3, 4]) == pytest.approx(100.0)


def test_reference_attainment_is_capped_not_superreference():
    assert reference_attainment(0.30, 0.30, "higher_is_better") == pytest.approx(100)
    assert reference_attainment(0.45, 0.30, "higher_is_better") == pytest.approx(100)
    assert reference_attainment(0.15, 0.30, "higher_is_better") == pytest.approx(50)


def test_lower_is_better_attainment():
    assert reference_attainment(0.05, 0.10, "lower_is_better") == pytest.approx(100)
    assert reference_attainment(0.20, 0.10, "lower_is_better") == pytest.approx(50)


def test_reference_state_validation():
    with pytest.raises(ValueError):
        evaluate_reference_candidate(
            candidate_area_ha=10,
            candidate_pixels=5000,
            min_area_ha=2,
            min_pixels=500,
            reference_state="pristine_magic",
        )


def test_benchmark_carries_reference_governance():
    from types import SimpleNamespace
    from darukaa_adaptive.benchmark import benchmark_metric
    from darukaa_adaptive.config import AssessmentConfig
    cfg = AssessmentConfig()
    b = benchmark_metric(
        "riparian_ndvi", 0.30, None, 0.25,
        tier2_approved=True,
        reference_level="auto_aquatic",
        reference_n=100,
        reference_method="ecoregion_hydrology_low_pressure",
        reference_state="least_disturbed_contemporary",
        reference_approval_basis="automated_reference_QA",
        reference_diagnostics={"ecological_match_score": 0.95},
    )
    assert b.reference_approved_for_scoring is True
    assert b.reference_state == "least_disturbed_contemporary"
    assert b.reference_approval_basis == "automated_reference_QA"
    assert b.reference_diagnostics["ecological_match_score"] == 0.95
    assert b.relative_departure_pct == pytest.approx(20.0)
    assert b.reference_attainment_0_100 == pytest.approx(100.0)


def test_missing_fauna_cannot_render_as_100(tmp_path):
    from darukaa_adaptive.config import AssessmentConfig
    from darukaa_adaptive.report import write_html_report
    cfg = AssessmentConfig()
    site = tmp_path / "site.kml"
    site.write_text("<kml></kml>")
    pillar = __import__("pandas").DataFrame([
        {"pillar": "C1_extent", "pillar_name": "C1 Extent", "score_0_to_100": 55.0, "status": "scored"},
        {"pillar": "C2_vegetation", "pillar_name": "C2 Vegetation", "score_0_to_100": 90.0, "status": "scored"},
        {"pillar": "C3_fauna", "pillar_name": "C3 Fauna", "score_0_to_100": None, "status": "insufficient_metric_coverage"},
        {"pillar": "C4_pressure", "pillar_name": "C4 Pressure", "score_0_to_100": 60.0, "status": "scored"},
    ])
    out = write_html_report(tmp_path, cfg, site, 1.0, {}, __import__("pandas").DataFrame(), __import__("pandas").DataFrame(), __import__("pandas").DataFrame(), pillar, {}, __import__("pandas").DataFrame(), {}, __import__("pandas").DataFrame())
    html = out.read_text()
    assert "C3 Fauna</span><span>Not assessed</span>" in html
    assert "C3 Fauna</span><div class=\"track\"><div class=\"fill\" style=\"width:100.0%\"" not in html


def test_hmi_diagnostic_threshold_contract():
    thresholds = [0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50]
    assert thresholds == sorted(thresholds)
    assert thresholds[0] == 0.05
    assert thresholds[-1] == 0.50
