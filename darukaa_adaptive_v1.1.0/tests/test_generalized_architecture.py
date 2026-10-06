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


def test_site_selection_tile_paths_manifest_is_native_contract(tmp_path):
    tiles_dir = tmp_path / 'tiles'
    tiles_dir.mkdir()
    paths = []
    for emu_id, x0 in [('EMU_01', 77.0), ('EMU_02', 77.002)]:
        tile = tiles_dir / f'TataMotors_Pimpri_{emu_id}.geojson'
        tile.write_text(json.dumps({
            'type': 'FeatureCollection',
            'features': [{
                'type': 'Feature',
                'properties': {'site_id': emu_id, 'name': emu_id},
                'geometry': mapping(Polygon([(x0,30),(x0+0.001,30),(x0+0.001,30.001),(x0,30.001),(x0,30)]))
            }]
        }))
        # Match the real Site Selection contract: absolute tile_paths.
        paths.append(str(tile))
    manifest = tmp_path / 'tile_manifest.json'
    manifest.write_text(json.dumps({
        'project_name': 'TataMotors_Pimpri',
        'n_tiles': 2,
        'tile_paths': paths,
        'tile_labels': ['EMU_01', 'EMU_02']
    }))
    project = load_project_input(manifest, domain='terrestrial')
    assert project.project_name == 'TataMotors_Pimpri'
    assert [e.emu_id for e in project.emus] == ['EMU_01', 'EMU_02']
    assert project.project_domain == 'terrestrial'


def test_zipped_site_selection_manifest_rebases_absolute_tile_paths(tmp_path):
    import zipfile
    source_root = tmp_path / 'source'
    tiles_dir = source_root / 'outputs' / '07_reference_handoff' / 'tiles'
    tiles_dir.mkdir(parents=True)
    tile = tiles_dir / 'TataMotors_Pimpri_EMU_01.geojson'
    tile.write_text(json.dumps({
        'type': 'FeatureCollection',
        'features': [{
            'type': 'Feature',
            'properties': {'site_id': 'EMU_01'},
            'geometry': mapping(Polygon([(77,30),(77.001,30),(77.001,30.001),(77,30.001),(77,30)]))
        }]
    }))
    manifest = source_root / 'outputs' / '07_reference_handoff' / 'tile_manifest.json'
    manifest.write_text(json.dumps({
        'project_name': 'TataMotors_Pimpri',
        'n_tiles': 1,
        'tile_paths': [str(tile)],
        'tile_labels': ['EMU_01']
    }))
    archive = tmp_path / 'handoff.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.write(manifest, 'tile_manifest.json')
        z.write(tile, 'tiles/TataMotors_Pimpri_EMU_01.geojson')
    project = load_project_input(archive, domain='terrestrial')
    assert [e.emu_id for e in project.emus] == ['EMU_01']
