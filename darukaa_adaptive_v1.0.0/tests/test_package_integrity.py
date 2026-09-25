from pathlib import Path
import json
import zipfile

import nbformat

ROOT = Path(__file__).resolve().parents[1]


def test_notebook_is_valid_and_cell_by_cell():
    path = ROOT / "notebooks" / "Nandoshi_Lake_Aquatic_Assessment_Colab.ipynb"
    nb = nbformat.read(path, as_version=4)
    assert len(nb.cells) >= 30
    code = "\n".join("".join(c.get("source", [])) for c in nb.cells if c.cell_type == "code")
    compile(code, str(path), "exec")
    assert "pull" in code and "--ff-only" in code
    assert "darukaa_adaptive_v1.0.0" in code


def test_required_project_files_present():
    required = [
        "README.md", "CHANGELOG.md", "VALIDATION.md",
        "setup.py", "requirements.txt",
        "darukaa_adaptive/config.py", "darukaa_adaptive/site.py", "darukaa_adaptive/water.py",
        "darukaa_adaptive/metrics.py", "darukaa_adaptive/benchmark.py", "darukaa_adaptive/scoring.py",
        "darukaa_adaptive/trajectory.py", "darukaa_adaptive/readiness.py", "darukaa_adaptive/report.py", "darukaa_adaptive/qa.py",
        "darukaa_adaptive/pipeline.py", "darukaa_adaptive/registry.py", "darukaa_adaptive/periods.py",
        "profiles/aquatic_lake.yaml", "profiles/terrestrial_legacy.yaml",
        "profiles/aquatic_lake_thresholds.template.yaml",
        "docs/METHOD_NOTES.md", "docs/REFERENCE_PIPELINE_AUDIT.md", "docs/REFERENCE_AND_SCORING_MODEL.md",
        "docs/NOTEBOOK_RUNBOOK.md", "tests/test_core.py", "tests/test_package_integrity.py",
    ]
    missing = [p for p in required if not (ROOT / p).exists()]
    assert not missing, missing


def test_no_changes_under_legacy_from_adaptive_release_files():
    # Guardrail: the adaptive package must retain the supplied legacy directory.
    legacy = ROOT / "legacy" / "darukaa_reference_v0.1.0"
    assert legacy.exists()
    assert (legacy / "darukaa_reference" / "pipeline.py").exists()


def test_legacy_hashes_match_recorded_manifest():
    import hashlib
    manifest = ROOT / "docs" / "LEGACY_SHA256.txt"
    for line in manifest.read_text().splitlines():
        if not line.strip():
            continue
        expected, relative = line.split(maxsplit=1)
        actual = hashlib.sha256((ROOT / "legacy" / "darukaa_reference_v0.1.0" / relative).read_bytes()).hexdigest()
        assert actual == expected, relative
