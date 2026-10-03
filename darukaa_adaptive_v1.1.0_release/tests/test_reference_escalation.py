from darukaa_adaptive.config import AssessmentConfig


def test_reference_escalation_is_finite_and_configurable():
    cfg = AssessmentConfig()
    assert cfg.reference.least_disturbed_enabled is True
    assert cfg.reference.least_disturbed_quantile == 0.10
    assert cfg.reference.hmi_max_for_reference == 0.05
    assert cfg.reference.manual_hmi_fallback_enabled is True
    assert cfg.reference.manual_hmi_threshold is None
    assert cfg.reference.manual_hmi_reference_state == "best_attainable"
    assert cfg.validate() == []


def test_manual_hmi_threshold_is_validated():
    cfg = AssessmentConfig()
    cfg.reference.manual_hmi_threshold = 0.30
    assert cfg.validate() == []
    cfg.reference.manual_hmi_threshold = 1.01
    assert any("manual_hmi_threshold" in e for e in cfg.validate())


def test_manual_hmi_state_is_restricted():
    cfg = AssessmentConfig()
    cfg.reference.manual_hmi_reference_state = "historical"
    assert any("manual_hmi_reference_state" in e for e in cfg.validate())
