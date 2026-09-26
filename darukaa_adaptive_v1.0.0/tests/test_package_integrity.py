from pathlib import Path
import hashlib
import nbformat

ROOT=Path(__file__).resolve().parents[1]


def test_notebook_compiles_and_final_cell_is_report():
    path=ROOT/"notebooks"/"Nandoshi_Lake_Aquatic_Assessment_Colab.ipynb"
    nb=nbformat.read(path,as_version=4)
    code=[c.source for c in nb.cells if c.cell_type=="code"]
    for c in code:
        cleaned="\n".join((line if not line.lstrip().startswith("!") else line[:len(line)-len(line.lstrip())]+"pass") for line in c.splitlines())
        compile(cleaned, str(path), "exec")
    assert "git pull --ff-only" in "\n".join(code)
    assert "build_html_report" in code[-1]


def test_required_files():
    required=[
        "README.md","CHANGELOG.md","setup.py","requirements.txt",
        "darukaa_adaptive/config.py","darukaa_adaptive/registry.py","darukaa_adaptive/benchmark.py",
        "darukaa_adaptive/scoring.py","darukaa_adaptive/site.py","darukaa_adaptive/water.py",
        "darukaa_adaptive/metrics.py","darukaa_adaptive/terrestrial_metrics.py","darukaa_adaptive/observations.py",
        "darukaa_adaptive/edna.py","darukaa_adaptive/pipeline.py","darukaa_adaptive/html_report.py",
        "darukaa_adaptive/report.py","profiles/mixed_lake.yaml","profiles/aquatic_lake.yaml","profiles/terrestrial.yaml",
        "templates/external_observations_template.csv","templates/edna_observations_template.csv",
    ]
    missing=[x for x in required if not (ROOT/x).exists()]
    assert not missing, missing


def test_legacy_hashes_unchanged():
    manifest=ROOT/"docs"/"LEGACY_SHA256.txt"
    for line in manifest.read_text().splitlines():
        if not line.strip(): continue
        expected, rel=line.split(maxsplit=1)
        p=ROOT/"legacy"/"darukaa_reference_v0.1.0"/rel
        assert hashlib.sha256(p.read_bytes()).hexdigest()==expected, rel


def test_no_provisional_context_ring_reference_config():
    cfg=(ROOT/"profiles"/"mixed_lake.yaml").read_text()
    assert "tier1_reference_kml" not in cfg
    assert "tier1_reference_csv" not in cfg
    assert "tier2_min_water_occurrence" not in cfg
    assert "context ring" not in cfg.lower()


def test_html_report_synthetic(tmp_path):
    from darukaa_adaptive.html_report import build_html_report
    out=tmp_path/"report.html"
    result={
        "config":{"profile":{"name":"test","version":"1.2.0"},"temporal":{"baseline_label":"Year-0"},"reference":{"strategy":"auto"}},
        "parts":{"Test Site":object()},"boundary_area_ha":10,
        "metrics":[],"metric_concern":[],"pillars":[],"overall":{},"readiness":{},"reference_diagnostics":{},"observations":[],"edna":[],
        "outputs":{"attachments":{}},"water_periods":[],
    }
    build_html_report(result,out)
    text=out.read_text()
    assert "Year-0 Biodiversity Baseline" in text
    assert "C1" in text or "Pillar results" in text


def test_edna_template_schema():
    import pandas as pd
    path=ROOT/"templates"/"edna_observations_template.csv"
    df=pd.read_csv(path)
    required={"metric","value","units","pillar","evidence_class","reference_approved"}
    assert required.issubset(df.columns)
    assert set(df["metric"]).issuperset({"edna_cyanobacterial_fraction","edna_fauna_taxonomic_richness"})
