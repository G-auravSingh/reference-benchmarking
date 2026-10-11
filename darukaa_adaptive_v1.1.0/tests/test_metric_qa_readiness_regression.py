from types import SimpleNamespace

from darukaa_adaptive.config import AssessmentConfig
from darukaa_adaptive.qa import qa_metric_record, normalize_measurement_status
from darukaa_adaptive.readiness import assess_readiness


def _metric(**overrides):
    values = dict(
        metric="test_metric",
        pillar="P2_ecosystem_condition",
        status="calculated",
        value=0.42,
        score_eligible=True,
        reference_allowed=True,
        valid_observations=12,
        valid_pixels=12,
        p05=0.1,
        p95=0.8,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_calculated_is_a_successful_measurement_status():
    row = qa_metric_record(_metric())
    assert row["qa_pass"] is True
    assert row["qa_status"] == "pass"
    assert row["qa_flags"] == ""


def test_calculated_metric_with_zero_valid_pixels_still_fails_qa():
    row = qa_metric_record(_metric(valid_pixels=0))
    assert row["qa_pass"] is False
    assert row["qa_status"] == "review"
    assert "no_valid_pixels" in row["qa_flags"]


def test_not_applicable_is_not_mislabeled_as_missing_measurement_failure():
    row = qa_metric_record(_metric(status="not_applicable", value=None, valid_observations=None, valid_pixels=None))
    assert row["qa_pass"] is None
    assert row["qa_status"] == "not_applicable"
    assert "missing_value" not in row["qa_flags"]


def test_readiness_counts_calculated_metrics_but_excludes_zero_support_and_non_scored_states():
    cfg = AssessmentConfig()
    metrics = [
        _metric(metric="valid"),
        _metric(metric="zero_pixels", valid_pixels=0),
        _metric(metric="no_observation", status="no_valid_observation", value=None, valid_observations=0, valid_pixels=0),
        _metric(metric="not_applicable", status="not_applicable", value=None, valid_observations=None, valid_pixels=None),
        _metric(metric="pending", status="context_only_pending_provenance", value=0.0, valid_observations=None, valid_pixels=None),
    ]
    result = assess_readiness(cfg, 1.0, metrics, benchmarks=[], scoring={})
    assert result["metric_coverage"]["total_metrics"] == 5
    assert result["metric_coverage"]["usable_metrics"] == 1
    assert result["metric_coverage"]["not_applicable_metrics"] == 1
    assert result["metric_coverage"]["pending_or_contextual_metrics"] == 1
    assert result["metric_coverage"]["no_valid_observation_metrics"] == 2


def test_project_report_surfaces_metric_qa_gaps_and_aggregation_basis(tmp_path):
    import pandas as pd
    from types import SimpleNamespace
    from darukaa_adaptive.report import write_project_report

    cfg = AssessmentConfig()
    project = SimpleNamespace(project_name="QA regression project")
    comparison = pd.DataFrame([{
        "emu_id": "EMU_1", "area_ha": 1.0, "domain": "terrestrial",
        "P1_extent_configuration_score_0_to_100": 60.0,
        "P2_ecosystem_condition_score_0_to_100": 40.0,
        "P3_biodiversity_integrity_score_0_to_100": 50.0,
        "condition_concern_label": "High",
        "condition_score_0_to_100": 49.3,
        "condition_coverage_status": "complete_three_pillar_condition",
        "limiting_metric": "chm",
    }])
    metric_qa = pd.DataFrame([{
        "metric": "chm", "pillar": "P2_ecosystem_condition", "status": "calculated",
        "score_eligible": True, "valid_observations": 0, "valid_pixels": 0,
        "qa_pass": False, "qa_status": "review", "qa_flags": "no_valid_pixels",
    }])
    emu_results = [{
        "emu_id": "EMU_1", "emu_domain": "terrestrial", "emu_area_ha": 1.0,
        "reference_populations": {}, "outputs": {}, "metric_qa": metric_qa,
    }]
    overall = {
        "status": "condition_scored", "condition_score_0_to_100": 49.3,
        "condition_concern_label": "High", "condition_coverage": "complete",
        "condition_pillar_count": 3, "condition_pillars": [
            "P1_extent_configuration", "P2_ecosystem_condition", "P3_biodiversity_integrity"
        ],
        "pressure_intactness_score_0_to_100": 30.0, "pressure_concern_label": "High",
    }
    qa = {"status": "review_required", "flags": [{
        "severity": "REVIEW", "code": "metric_measurement_qa",
        "message": "Metric-level QA requires review.", "metrics": ["chm"],
    }]}
    out = write_project_report(
        tmp_path, project, overall, pd.DataFrame(), pd.DataFrame(), comparison,
        emu_results, cfg, qa,
    )
    report = out.read_text()
    assert "Metric-level measurement QA requires review" in report
    assert "the geometric mean of the available project-level P1–P3 pillar scores" in report
    assert "not that every registered metric was scored" in report


def test_zero_support_placeholder_is_normalized_before_benchmarking():
    metric = _metric(metric="flii", value=0.0, valid_observations=0, valid_pixels=0)
    normalized = normalize_measurement_status(metric)
    assert normalized.status == "no_valid_observation"
    assert normalized.value is None
    row = qa_metric_record(normalized)
    assert row["qa_status"] == "review"
    assert "missing_value" in row["qa_flags"]
    assert "no_valid_pixels" in row["qa_flags"]
