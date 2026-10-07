from pathlib import Path

def test_required_files_exist():
    root=Path(__file__).resolve().parents[1]
    for rel in ['README.md','CHANGELOG.md','VALIDATION.md','requirements.txt','setup.py','pytest.ini','docs/METHODOLOGY.md','docs/REFERENCE_CONDITION_METHODOLOGY.md','profiles/aquatic_lake.yaml','profiles/terrestrial.yaml','profiles/mixed.yaml','docs/VALIDATION_SCIENTIFIC_SOURCES.md','darukaa_adaptive/evidence.py','darukaa_adaptive/reference_engine.py','darukaa_adaptive/inputs.py','darukaa_adaptive/aggregation.py','darukaa_adaptive/handoff.py','docs/EMU_AND_HANDOFF_SPECIFICATION.md','docs/METRIC_REGISTRY_AND_EXTENSIBILITY.md','notebooks/Darukaa_Adaptive_Biodiversity_Assessment_Colab.ipynb','darukaa_adaptive/report.py']:
        assert (root/rel).exists(), rel

def test_no_nested_release_folder():
    root=Path(__file__).resolve().parents[1]
    assert not (root/'darukaa_adaptive_v1.1.0').exists()
