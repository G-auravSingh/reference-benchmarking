from darukaa_adaptive.registry import FULL_INDICATORS
from darukaa_adaptive.legacy_reference.indicators import _annualized_rate_pct


def _spec(name):
    return next(x for x in FULL_INDICATORS if x.name == name)


def test_forest_loss_windows_use_inclusive_year_counts():
    # 2001-2025 inclusive = 25 annual observations; the package must not divide by 24.
    assert round(_annualized_rate_pct(25.0, 100.0, 25), 6) == 1.0
    assert round(_annualized_rate_pct(6.0, 100.0, 6), 6) == 1.0
    assert round(_annualized_rate_pct(3.0, 100.0, 3), 6) == 1.0


def test_pressure_metrics_are_separate_from_condition_axis():
    for name in ("ghm", "light_pollution", "hdi"):
        assert _spec(name).pillar == "P4_pressure"


def test_scoreable_aquatic_metrics_are_runtime_score_selectable():
    from darukaa_adaptive.registry import metric_scoreability
    for name in ("sabf", "wcpi", "edpp", "mspl", "rci"):
        assert metric_scoreability(_spec(name)) == "default_scored"
    for name in ("hsas", "sdi", "iri"):
        assert metric_scoreability(_spec(name)) in {"default_scored", "context_only"}


def test_bii_and_flii_have_explicit_scientific_gates():
    assert _spec("bii").scoring_role == "SCORED"
    assert _spec("bii").reference_estimator == "robust_z"
    assert _spec("flii").scoring_role == "SCORED"
    assert _spec("flii").reference_estimator == "robust_z"


def test_chm_uses_meta_wri_primary_product_contract():
    spec = _spec("chm")
    assert spec.scoring_role == "SCORED"
    assert spec.native_scale_m == 1.0
    assert "meta_wri_canopy_height" in spec.input_layers
    assert "meta-forest-monitoring-okw37/assets/CanopyHeight" in spec.source_type


def test_eii_parent_and_components_are_mutually_exclusive():
    from darukaa_adaptive.config import AssessmentConfig
    from darukaa_adaptive.registry import effective_scoring_role
    cfg = AssessmentConfig()
    cfg.scoring.eii_mode = "components"
    assert effective_scoring_role(_spec("eii"), cfg) == "CONTEXTUAL"
    for name in ("eii_structural", "eii_compositional", "eii_functional"):
        assert effective_scoring_role(_spec(name), cfg) == "SCORED"

    cfg.scoring.eii_mode = "parent"
    assert effective_scoring_role(_spec("eii"), cfg) == "SCORED"
    for name in ("eii_structural", "eii_compositional", "eii_functional"):
        assert effective_scoring_role(_spec(name), cfg) == "CONTEXTUAL"

    cfg.scoring.eii_mode = "none"
    for name in ("eii","eii_structural","eii_compositional","eii_functional"):
        assert effective_scoring_role(_spec(name), cfg) == "CONTEXTUAL"


def test_bii_is_independent_of_eii_compositional_source():
    spec = _spec("bii")
    assert "BII_V1_1" in spec.source_type
    assert "landbanking_eii" not in spec.input_layers


def test_eii_override_cannot_bypass_hierarchy_gate():
    from darukaa_adaptive.config import AssessmentConfig
    from darukaa_adaptive.registry import effective_scoring_role
    cfg = AssessmentConfig()
    cfg.scoring.eii_mode = "components"
    cfg.scoring.metric_overrides = {"eii": "scored"}
    assert effective_scoring_role(_spec("eii"), cfg) == "CONTEXTUAL"

    cfg.scoring.eii_mode = "parent"
    cfg.scoring.metric_overrides = {"eii_structural": "scored"}
    assert effective_scoring_role(_spec("eii_structural"), cfg) == "CONTEXTUAL"


def test_full_legacy_inventory_is_unique_and_complete():
    names = [x.name for x in __import__("darukaa_adaptive.registry", fromlist=["FULL_INDICATORS"]).FULL_INDICATORS]
    assert len(names) == 46
    assert len(set(names)) == 46


def test_net_tree_cover_change_is_contextual_absolute_area_metric():
    spec = _spec("net_forest_change_rate")
    assert spec.scoring_role == "CONTEXTUAL"
    assert spec.default_scoring == "context_only"
    assert spec.units == "ha per year"
    assert "Net Tree Cover Change Proxy" in spec.display_name
    assert spec.name in __import__("darukaa_adaptive.registry", fromlist=["HARD_CONTEXT_ONLY"]).HARD_CONTEXT_ONLY


def test_pipeline_pressure_filter_uses_explicit_boolean_parentheses():
    from pathlib import Path
    source = Path(__file__).resolve().parents[1] / "darukaa_adaptive" / "pipeline.py"
    text = source.read_text()
    assert '(pillar_agg["pillar"] == "P4_pressure") & (pillar_agg["project_score_0_to_100"].notna())' in text
