from pathlib import Path

def test_required_files_exist():
    root=Path(__file__).resolve().parents[1]
    for rel in ['README.md','CHANGELOG.md','VALIDATION.md','requirements.txt','setup.py','profiles/aquatic_lake.yaml','profiles/terrestrial.yaml','profiles/mixed.yaml','notebooks/Nandoshi_Lake_Aquatic_Assessment_Colab.ipynb','darukaa_adaptive/evidence.py','darukaa_adaptive/reference_engine.py','darukaa_adaptive/report.py','examples/nandoshi_edna_context_example.csv']:
        assert (root/rel).exists(), rel

def test_no_nested_release_folder():
    root=Path(__file__).resolve().parents[1]
    assert not (root/'darukaa_adaptive_v1.0.0').exists()
