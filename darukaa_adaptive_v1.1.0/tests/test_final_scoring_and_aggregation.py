import math
import pandas as pd
from darukaa_adaptive.config import AssessmentConfig
from darukaa_adaptive.scoring import aggregate_subdimensions, aggregate_pillars, aggregate_overall, geometric_mean
from darukaa_adaptive.aggregation import aggregate_project_metric_scores, aggregate_project_pillars, build_emu_comparison_table


def test_subdimension_geometric_mean_then_pillar_limiting_factor():
    cfg=AssessmentConfig()
    df=pd.DataFrame([
        {"metric":"natural_habitat","pillar":"P1_extent_configuration","subdimension":"natural_cover","intactness_score_0_100":80,"score_eligible":True},
        {"metric":"ndvi","pillar":"P2_ecosystem_condition","subdimension":"greenness","intactness_score_0_100":90,"score_eligible":True},
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
        {"emu_id":"A","area_ha":10,"domain":"terrestrial","pillar":"P1_extent_configuration","pillar_name":"Ecosystem Extent & Configuration","score_0_to_100":90,"concern_label":"Very Low","limiting_metric":"natural_habitat"},
        {"emu_id":"A","area_ha":10,"domain":"terrestrial","pillar":"P2_ecosystem_condition","pillar_name":"Ecosystem Condition","score_0_to_100":60,"concern_label":"Low","limiting_metric":"ndvi"},
    ]
    metrics=[{"emu_id":"A","metric":"natural_habitat","score_0_to_100":90},{"emu_id":"A","metric":"ndvi","score_0_to_100":60}]
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


def test_emu_condition_distribution_uses_existing_bands_and_keeps_incomplete_area():
    from darukaa_adaptive.aggregation import summarize_emu_condition_distribution
    comparison = pd.DataFrame([
        {"emu_id":"A","area_ha":10,"P1_extent_configuration_score_0_to_100":80,"P2_ecosystem_condition_score_0_to_100":60,"P3_biodiversity_integrity_score_0_to_100":40,"condition_concern_label":"Moderate"},
        {"emu_id":"B","area_ha":30,"P1_extent_configuration_score_0_to_100":20,"P2_ecosystem_condition_score_0_to_100":20,"P3_biodiversity_integrity_score_0_to_100":20,"condition_concern_label":"Very High"},
        {"emu_id":"C","area_ha":20,"P1_extent_configuration_score_0_to_100":40,"P2_ecosystem_condition_score_0_to_100":None,"P3_biodiversity_integrity_score_0_to_100":None,"condition_concern_label":None},
        {"emu_id":"D","area_ha":40,"P1_extent_configuration_score_0_to_100":None,"P2_ecosystem_condition_score_0_to_100":None,"P3_biodiversity_integrity_score_0_to_100":None,"condition_concern_label":None},
    ])
    out = summarize_emu_condition_distribution(comparison)
    very_high = out.query("concern_band == 'Very High'").iloc[0]
    moderate = out.query("concern_band == 'Moderate'").iloc[0]
    partial = out.query("category == 'partial_condition_evidence'").iloc[0]
    insufficient = out.query("category == 'insufficient_condition_evidence'").iloc[0]
    assert very_high.n_emus == 1 and very_high.area_ha == 30 and very_high.area_share_pct == 30
    assert moderate.n_emus == 1 and moderate.area_ha == 10 and moderate.area_share_pct == 10
    assert partial.n_emus == 1 and partial.area_ha == 20 and partial.area_share_pct == 20
    assert insufficient.n_emus == 1 and insufficient.area_ha == 40 and insufficient.area_share_pct == 40


def test_project_report_includes_distribution_qa_and_output_index(tmp_path):
    from types import SimpleNamespace
    from darukaa_adaptive.config import AssessmentConfig
    from darukaa_adaptive.report import write_project_report
    cfg = AssessmentConfig()
    project = SimpleNamespace(project_name="Report Test")
    comparison = pd.DataFrame([
        {"emu_id":"A","area_ha":10,"domain":"terrestrial",
         "P1_extent_configuration_score_0_to_100":80,"P2_ecosystem_condition_score_0_to_100":70,"P3_biodiversity_integrity_score_0_to_100":60,
         "condition_score_0_to_100":69.6,"condition_concern_label":"Low","condition_coverage_status":"complete_three_pillar_condition"}
    ])
    path = write_project_report(tmp_path, project, {"condition_score_0_to_100":69.6,"condition_concern_label":"Low","condition_coverage":"complete","pressure_intactness_score_0_to_100":None},
        pd.DataFrame(), pd.DataFrame(), comparison, [{"emu_id":"A","emu_domain":"terrestrial","emu_area_ha":10,"reference_populations":{},"outputs":"emu_A"}], cfg,
        {"status":"review_required","flags":[{"severity":"REVIEW","code":"test_flag","message":"review this"}]})
    html = path.read_text(encoding="utf-8")
    assert "EMU Condition Concern Distribution" in html
    assert "Automated Output QA" in html and "test_flag" in html
    assert "EMU Output &amp; Reference Index" in html or "EMU Output & Reference Index" in html
    assert (tmp_path / "emu_condition_concern_distribution.csv").exists()


def test_project_output_bundle_audit_accepts_complete_report(tmp_path):
    from types import SimpleNamespace
    from darukaa_adaptive.config import AssessmentConfig
    from darukaa_adaptive.report import write_project_report, audit_project_output_bundle
    cfg = AssessmentConfig()
    project = SimpleNamespace(project_name="Bundle Audit")
    comparison = pd.DataFrame([
        {"emu_id":"A","area_ha":10,"domain":"terrestrial",
         "P1_extent_configuration_score_0_to_100":80,"P2_ecosystem_condition_score_0_to_100":70,"P3_biodiversity_integrity_score_0_to_100":60,
         "condition_score_0_to_100":69.6,"condition_concern_label":"Low","condition_coverage_status":"complete_three_pillar_condition"}
    ])
    write_project_report(tmp_path, project, {"condition_score_0_to_100":69.6,"condition_concern_label":"Low","condition_coverage":"complete","condition_pillar_count":3},
        pd.DataFrame(), pd.DataFrame(), comparison, [{"emu_id":"A","emu_domain":"terrestrial","emu_area_ha":10,"reference_populations":{},"outputs":"emu_A"}], cfg, {"status":"pass","flags":[]})
    for name in ["project_assessment_manifest.json","project_overall_scorecard.json","project_pillar_aggregation.csv","project_metric_raw_aggregation.csv","project_metric_score_aggregation.csv","emu_ecological_comparison.csv","project_output_qa.json"]:
        (tmp_path/name).write_text("{}",encoding="utf-8")
    flags = audit_project_output_bundle(tmp_path, comparison, 1)
    assert flags == []


def test_project_output_bundle_audit_flags_missing_report(tmp_path):
    from darukaa_adaptive.report import audit_project_output_bundle
    flags = audit_project_output_bundle(tmp_path, pd.DataFrame(), 0)
    assert any(f["code"] == "required_output_missing" for f in flags)


def test_emu_comparison_includes_emu_with_no_scored_pillars():
    from darukaa_adaptive.aggregation import complete_emu_comparison
    comparison = pd.DataFrame([{"emu_id":"A","area_ha":10,"domain":"terrestrial","condition_score_0_to_100":70}])
    emus = [
        {"emu_id":"A","emu_area_ha":10,"emu_domain":"terrestrial"},
        {"emu_id":"B","emu_area_ha":25,"emu_domain":"aquatic"},
    ]
    out = complete_emu_comparison(comparison, emus)
    assert set(out.emu_id) == {"A", "B"}
    row = out.query("emu_id == 'B'").iloc[0]
    assert row.condition_coverage_status == "insufficient_condition_evidence"
    assert row.area_ha == 25 and row.condition_score_0_to_100 is None
