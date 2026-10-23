from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_required_files_exist():
    for rel in ["README.md", "CHANGELOG.md", "requirements.txt", "setup.py", "pytest.ini", "profiles/terrestrial.yaml",
                "docs/methodology/metric_catalogue_v1.md", "docs/decisions/README.md",
                "notebooks/Darukaa_Adaptive_Biodiversity_Assessment_Colab.ipynb", "validation/R2_controls.geojson",
                "validation/R2_expected.json"]:
        assert (ROOT / rel).exists(), rel


def test_package_imports_without_earth_engine():
    import importlib
    for mod in ("catalogue", "config", "inputs", "units", "measurement", "scorecard", "layers", "extraction",
                "reference_pool", "assessment", "outputs", "probe", "natural_mask", "ee_utils"):
        importlib.import_module(f"darukaa_adaptive.{mod}")


def test_version_is_1_1_0():
    import darukaa_adaptive
    assert darukaa_adaptive.__version__ == "1.1.0"
