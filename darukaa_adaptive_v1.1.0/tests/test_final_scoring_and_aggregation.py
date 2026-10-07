import math
import pandas as pd
from darukaa_adaptive.config import AssessmentConfig
from darukaa_adaptive.scoring import aggregate_subdimensions, aggregate_pillars, aggregate_overall, geometric_mean
from darukaa_adaptive.aggregation import aggregate_project_metric_scores, aggregate_project_pillars, build_emu_comparison_table


def test_subdimension_geometric_mean_then_pillar_limiting_factor():
    cfg=AssessmentConfig()
    df=pd.DataFrame([
        {"metric":"natural_landcover_fraction","pillar":"P1_extent_configuration","subdimension":"natural_cover","intactness_score_0_100":80,"score_eligible":True},
        {"metric":"terrestrial_ndvi","pillar":"P2_ecosystem_condition","subdimension":"greenness","intactness_score_0_100":90,"score_eligible":True},
        {"metric":"riparian_ndvi","pillar":"P2_ecosystem_condition","subdimension":"greenness","intactness_score_0_100":40,"score_eligible":True},
        {"metric":"water_persistence","pillar":"P2_ecosystem_condition","subdimension":"hydrology","intactness_score_0_100":20,"score_eligible":True},
        {"metric":"edna_fish_richness","pillar":"P3_biodiversity_integrity","subdimension":"fish_richness","intactness_score_0_100":70,"score_eligible":True},
        {"metric":"built_fraction","pillar":"P4_pressure","subdimension":"built_up","intactness_score_0_100":60,"score_eligible":True},
    ])
    sub=aggregate_subdimensions(df,cfg)
    green=math.sqrt(90*40)
    assert abs(float(sub.query("subdimension=='greenness'").score_0_to_100.iloc[0])-green)<1e-9
    pillars=aggregate_pillars(df,cfg)
    p2=float(pillars.query("pillar=='P2_ecosystem_condition'").score_0_to_100.iloc[0])
    assert abs(p2-20.0)<1e-9
    assert pillars.query("pillar=='P2_ecosystem_condition'").limiting_subdimension.iloc[0]=='hydrology'


def test_project_aggregation_preserves_distribution_and_area_weighting():
    rows=[
        {"emu_id":"A","area_ha":10,"metric":"m","score_0_to_100":90,"score_eligible":True},
        {"emu_id":"B","area_ha":30,"metric":"m","score_0_to_100":50,"score_eligible":True},
    ]
    out=aggregate_project_metric_scores(rows).iloc[0]
    assert abs(out.project_score_0_to_100-60.0)<1e-9
    assert out.emu_n==2 and out.emu_min==50.0 and out.emu_max==90.0


def test_project_pillar_comparison_keeps_limiting_emu():
    rows=[
        {"emu_id":"A","area_ha":10,"pillar":"P1_extent_configuration","pillar_name":"Ecosystem Extent & Configuration","score_0_to_100":90,"concern_label":"Very Low"},
        {"emu_id":"B","area_ha":30,"pillar":"P1_extent_configuration","pillar_name":"Ecosystem Extent & Configuration","score_0_to_100":40,"concern_label":"Moderate"},
    ]
    out=aggregate_project_pillars(rows).iloc[0]
    assert abs(out.project_score_0_to_100-52.5)<1e-9
    assert out.limiting_emu=='B'


def test_emu_comparison_is_not_reduced_to_one_hidden_rank():
    pillars=[
        {"emu_id":"A","area_ha":10,"domain":"terrestrial","pillar":"P1_extent_configuration","pillar_name":"Ecosystem Extent & Configuration","score_0_to_100":90,"concern_label":"Very Low","limiting_metric":"natural_landcover_fraction"},
        {"emu_id":"A","area_ha":10,"domain":"terrestrial","pillar":"P2_ecosystem_condition","pillar_name":"Ecosystem Condition","score_0_to_100":60,"concern_label":"Low","limiting_metric":"terrestrial_ndvi"},
    ]
    metrics=[{"emu_id":"A","metric":"natural_landcover_fraction","score_0_to_100":90},{"emu_id":"A","metric":"terrestrial_ndvi","score_0_to_100":60}]
    out=build_emu_comparison_table(pillars,metrics)
    assert set(['emu_id','area_ha','P1_extent_configuration_score_0_to_100','P2_ecosystem_condition_score_0_to_100','limiting_metric']).issubset(out.columns)


def test_calculated_metric_status_is_scoreable_when_other_gates_pass():
    from types import SimpleNamespace
    from darukaa_adaptive.config import AssessmentConfig
    from darukaa_adaptive.benchmark import benchmark_metric
    from darukaa_adaptive.scoring import score_metric
    cfg = AssessmentConfig()
    metric = SimpleNamespace(metric="bii", value=0.5, units="index", direction="higher_is_better",
                             reference_allowed=True, status="calculated", notes="", domain="terrestrial", evidence_type="EO")
    b = benchmark_metric("bii", 0.5, 0.8, None, tier1_approved=True, reference_level="auto", reference_n=100,
                         reference_state="least_disturbed_contemporary", reference_approval_basis="qa")
    out = score_metric(metric, b, cfg)
    assert out["score_eligible"] is True
    assert out["score_status"] == "scored"
