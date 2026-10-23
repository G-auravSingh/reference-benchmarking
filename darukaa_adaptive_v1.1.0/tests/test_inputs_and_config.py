import json
import zipfile
from pathlib import Path

import pandas as pd
from shapely.geometry import Polygon, mapping

from darukaa_adaptive.config import AssessmentConfig
from darukaa_adaptive.evidence import load_evidence_csv
from darukaa_adaptive.inputs import load_project_input


def test_geojson_featurecollection_becomes_multiple_emus(tmp_path):
    data={"type":"FeatureCollection","metadata":{"project_id":"P1"},"features":[
        {"type":"Feature","properties":{"emu_id":"EMU_A","domain":"terrestrial"},"geometry":mapping(Polygon([(77,30),(77.001,30),(77.001,30.001),(77,30.001),(77,30)]))},
        {"type":"Feature","properties":{"emu_id":"EMU_B","domain":"terrestrial"},"geometry":mapping(Polygon([(77.002,30),(77.003,30),(77.003,30.001),(77.002,30.001),(77.002,30)]))},
    ]}
    p=tmp_path/'project.geojson'; p.write_text(json.dumps(data))
    project=load_project_input(p)
    assert [e.emu_id for e in project.emus]==['EMU_A','EMU_B']
    assert project.validate()==[]


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

def test_site_selection_project_id_comes_from_manifest_and_boundary_is_found(tmp_path):
    tiles = tmp_path / "tiles"; tiles.mkdir()
    t = tiles / "A.geojson"
    t.write_text(json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {},
        "geometry": mapping(Polygon([(77, 30), (77.001, 30), (77.001, 30.001), (77, 30.001), (77, 30)]))}]}))
    (tmp_path / "aoi_boundary.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {},
        "geometry": mapping(Polygon([(76.99, 29.99), (77.01, 29.99), (77.01, 30.01), (76.99, 30.01), (76.99, 29.99)]))}]}))
    m = tmp_path / "tile_manifest.json"
    m.write_text(json.dumps({"project_name": "Demo_Project", "tile_paths": ["tiles/A.geojson"], "tile_labels": ["EMU_A"]}))
    p = load_project_input(m)
    assert p.project_id == "Demo_Project"          # not "tile_manifest" (audit M5)
    assert p.metadata["boundary_file"].endswith("aoi_boundary.geojson")


def test_evidence_csv(tmp_path):
    p = tmp_path / "e.csv"
    pd.DataFrame([{"metric": "edna_fish_richness", "raw_value": 8, "pillar": "P3", "direction": "higher_is_better"}]).to_csv(p, index=False)
    assert load_evidence_csv(p).iloc[0]["evidence_type"] == "external"


def test_config_defaults_and_yaml_profile():
    c = AssessmentConfig()
    assert c.window_exclusive() == ("2025-08-01", "2026-09-01") and c.validate() == []
    prof = AssessmentConfig.from_yaml(Path(__file__).resolve().parents[1] / "profiles" / "terrestrial.yaml")
    assert prof.validate() == [] and prof.pool.radius_km == 25 and prof.options["tree_cover_threshold_pct"] == 10


def test_config_rejects_unknown_keys_and_small_exclusion():
    import pytest
    with pytest.raises(ValueError):
        AssessmentConfig.from_dict({"not_a_key": 1})
    c = AssessmentConfig.from_dict({"pool": {"exclusion_m": 200}})
    assert any("exclusion" in e for e in c.validate())
