import math

from darukaa_adaptive.benchmark import benchmark_metric
from darukaa_adaptive.config import AssessmentConfig
from darukaa_adaptive.metrics import MetricResult
from darukaa_adaptive.qa import normalize_measurement_status
from darukaa_adaptive.registry import get_indicator_spec, effective_scoring_role


def test_ndvi_is_default_scoreable_with_distribution_response():
    cfg = AssessmentConfig()
    spec = get_indicator_spec("ndvi")
    assert spec.reference_allowed is True
    assert effective_scoring_role(spec, cfg) == "SCORED"
    result = benchmark_metric(
        "ndvi", observed=0.45, tier1=None, tier2=0.61,
        tier2_approved=True, reference_n=100,
        reference_diagnostics={"p05": 0.25, "p50": 0.61, "p95": 0.79},
    )
    assert result.benchmark_status == "ok"
    assert result.comparison_method == "reference_distribution_p05_to_p50"
    assert math.isclose(result.reference_attainment_0_100, 100 * (0.45 - 0.25) / (0.61 - 0.25))
    assert "not a ratio" in result.notes
    assert result.raw_relative_ratio is None
    assert result.relative_departure_pct is None


def test_context_disposition_is_not_promoted_by_global_score_default():
    cfg = AssessmentConfig()
    assert effective_scoring_role(get_indicator_spec("habitat_health"), cfg) == "CONTEXTUAL"
    assert effective_scoring_role(get_indicator_spec("eii"), cfg) == "SCORED"
    for name in ("eii_structural", "eii_compositional", "eii_functional", "star_t"):
        assert effective_scoring_role(get_indicator_spec(name), cfg) == "CONTEXTUAL"


def test_zero_pixel_calculated_placeholder_becomes_missing_observation():
    m = MetricResult(metric="flii", pillar="P2_ecosystem_condition", construct="C2_vegetation",
                     subdimension="forest_integrity", domain="terrestrial", value=0.0, units="0-10",
                     status="calculated", temporal_window="baseline", dataset="canonical FLII",
                     scale_m=300, direction="higher_is_better", evidence_tier="baseline",
                     reference_type="regional_distribution", reference_allowed=True,
                     valid_observations=0, valid_pixels=0)
    m = normalize_measurement_status(m)
    assert m.status == "no_valid_observation"
    assert m.value is None


def test_eii_parent_and_lai_are_default_scoring_candidates():
    cfg = AssessmentConfig()
    assert effective_scoring_role(get_indicator_spec("eii"), cfg) == "SCORED"
    assert effective_scoring_role(get_indicator_spec("lai"), cfg) == "SCORED"
    for name in ("eii_structural", "eii_compositional", "eii_functional"):
        assert effective_scoring_role(get_indicator_spec(name), cfg) == "CONTEXTUAL"
    # BII is kept out of the same headline composite when EII parent is selected.


def test_coarse_metric_with_three_valid_pixels_is_not_scored():
    m = MetricResult(metric="ghm", pillar="P4_pressure", construct="C4_pressure",
                     subdimension="land_use_pressure", domain="terrestrial", value=0.6, units="index",
                     status="calculated", temporal_window="baseline", dataset="GHM", scale_m=1000,
                     direction="lower_is_better", evidence_tier="baseline",
                     reference_type="regional_distribution", reference_allowed=True,
                     valid_observations=3, valid_pixels=3)
    m = normalize_measurement_status(m)
    assert m.status == "no_valid_observation"
    assert m.value is None
    assert "minimum support" in m.notes


def test_default_headline_requires_two_metrics_per_pillar_and_all_condition_pillars():
    cfg = AssessmentConfig()
    assert cfg.scoring.min_valid_metrics_per_pillar == 3
    assert cfg.scoring.min_valid_subdimensions_per_pillar == 3
    assert cfg.scoring.min_condition_pillars == 3
    assert cfg.scoring.require_complete_pillars is True
    assert cfg.scoring.require_fauna_for_condition is True


def test_pillar_with_two_metrics_does_not_produce_headline_score_by_default():
    import pandas as pd
    from darukaa_adaptive.scoring import aggregate_pillars
    cfg = AssessmentConfig()
    frame = pd.DataFrame([
        {"metric": "natural_habitat", "pillar": "P1_extent_configuration", "subdimension": "extent",
         "intactness_score_0_100": 70.0, "score_eligible": True},
        {"metric": "cpland", "pillar": "P1_extent_configuration", "subdimension": "configuration",
         "intactness_score_0_100": 75.0, "score_eligible": True},
    ])
    pillar = aggregate_pillars(frame, cfg).query("pillar == 'P1_extent_configuration'").iloc[0]
    assert pd.isna(pillar.score_0_to_100)
    assert pillar.status == "insufficient_metric_coverage"
    assert pillar.n_scored_metrics == 2
    assert pillar.minimum_metrics_required == 3
    assert pillar.minimum_subdimensions_required == 3


def test_star_t_registered_calculator_has_no_dynamic_world_viirs_proxy():
    import inspect
    from darukaa_adaptive.registry import _LEGACY_REGISTRY
    source = inspect.getsource(_LEGACY_REGISTRY.get("star_t").extract_fn)
    assert "Canonical STAR-T raster not supplied" in source
    assert "GOOGLE/DYNAMICWORLD/V1" not in source
    assert "NOAA/VIIRS" not in source


def test_ndvi_reference_distribution_response_is_bounded():
    low = benchmark_metric("ndvi", observed=0.1, tier1=None, tier2=0.6, tier2_approved=True,
                           reference_diagnostics={"p05": 0.2, "p50": 0.6})
    high = benchmark_metric("ndvi", observed=0.8, tier1=None, tier2=0.6, tier2_approved=True,
                            reference_diagnostics={"p05": 0.2, "p50": 0.6})
    assert low.reference_attainment_0_100 == 0.0
    assert high.reference_attainment_0_100 == 100.0
