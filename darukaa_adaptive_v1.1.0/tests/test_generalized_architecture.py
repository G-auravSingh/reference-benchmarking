import json
from pathlib import Path
from shapely.geometry import Polygon, mapping

from darukaa_adaptive.inputs import load_project_input
from darukaa_adaptive.handoff import handoff_manifest_template
from darukaa_adaptive.registry import IndicatorSpec, register_indicator, get_registered_indicator
from darukaa_adaptive.aggregation import aggregate_emu_scorecards


def test_geojson_featurecollection_becomes_multiple_emus(tmp_path):
    data={"type":"FeatureCollection","metadata":{"project_id":"P1"},"features":[
        {"type":"Feature","properties":{"emu_id":"EMU_A","domain":"terrestrial"},"geometry":mapping(Polygon([(77,30),(77.001,30),(77.001,30.001),(77,30.001),(77,30)]))},
        {"type":"Feature","properties":{"emu_id":"EMU_B","domain":"terrestrial"},"geometry":mapping(Polygon([(77.002,30),(77.003,30),(77.003,30.001),(77.002,30.001),(77.002,30)]))},
    ]}
    p=tmp_path/'project.geojson'; p.write_text(json.dumps(data))
    project=load_project_input(p)
    assert [e.emu_id for e in project.emus]==['EMU_A','EMU_B']
    assert project.validate()==[]


def test_handoff_manifest_requires_contract_fields(tmp_path):
    tile=tmp_path/'tile.geojson'
    tile.write_text(json.dumps({"type":"FeatureCollection","features":[{"type":"Feature","properties":{"emu_id":"EMU_1","domain":"terrestrial"},"geometry":mapping(Polygon([(77,30),(77.001,30),(77.001,30.001),(77,30.001),(77,30)]))}]}))
    manifest=handoff_manifest_template('P1',[{"emu_id":"EMU_1","path":"tile.geojson","domain":"terrestrial"}])
    p=tmp_path/'tile_manifest.json'; p.write_text(json.dumps(manifest))
    project=load_project_input(p)
    assert project.project_id=='P1'
    assert project.emus[0].emu_id=='EMU_1'


def test_indicator_registry_accepts_future_field_indicator():
    spec=IndicatorSpec('camera_trap_occupancy','C3_fauna','fauna','occupancy','camera_trap','probability','higher_is_better','field','field_or_matched',True,'reference_relative','Occupancy estimate','Track occupancy under standardized effort','Requires detection/non-detection effort metadata.')
    register_indicator(spec, overwrite=True)
    assert get_registered_indicator('camera_trap_occupancy').evidence_tier=='field'


def test_project_aggregation_preserves_missing_coverage():
    out=aggregate_emu_scorecards([
        {"emu_id":"A","area_ha":10,"metric":"x","value":80},
        {"emu_id":"B","area_ha":10,"metric":"x","value":None},
    ])
    row=out.iloc[0]
    assert row.project_value==80
    assert row.n_emus==1 and row.n_emus_total==2
    assert row.coverage_weight==0.5


def test_multi_emu_external_evidence_requires_emu_id(tmp_path):
    p=tmp_path/'evidence.csv'; p.write_text('metric,raw_value,pillar,direction\nx,1,C3_fauna,higher_is_better\n')
    from darukaa_adaptive.pipeline import AdaptivePipeline
    from darukaa_adaptive.config import AssessmentConfig
    from shapely.geometry import Polygon
    cfg=AssessmentConfig(); cfg.output_dir=str(tmp_path/'out')
    runner=AdaptivePipeline(cfg)
    poly=Polygon([(77,30),(77.001,30),(77.001,30.001),(77,30.001),(77,30)])
    import json
    g=tmp_path/'g.geojson'; g.write_text(json.dumps({"type":"Feature","properties":{"emu_id":"E1","domain":"terrestrial"},"geometry":mapping(poly)}))
    try:
        runner.run(g,external_evidence_file=p)
    except ValueError as e:
        assert 'emu_id' in str(e)
    else:
        raise AssertionError('Expected explicit emu_id requirement')
