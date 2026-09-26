"""Deterministic output writer for the adaptive biodiversity assessment."""
from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .benchmark import benchmark_dataframe
from .registry import indicator_table


def _git_commit_for(path: Path):
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=path, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def _copy_input(src, attachments):
    if not src:
        return None
    p = Path(src)
    if not p.exists():
        return None
    dest = attachments / p.name
    shutil.copy2(p, dest)
    return str(dest.relative_to(attachments.parent))


def write_assessment(output_dir, config, site_path, result):
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    attachments = out / "attachments"; attachments.mkdir(exist_ok=True)
    metrics = result.get("metrics", []); scored_df = result.get("metric_concern", pd.DataFrame()); pillars = result.get("pillars", pd.DataFrame())
    benchmarks = list(result.get("benchmarks", {}).values())

    pd.DataFrame([m.to_dict() for m in metrics]).to_csv(out / "metric_scorecard.csv", index=False)
    benchmark_dataframe(benchmarks).to_csv(out / "benchmark_scorecard.csv", index=False)
    scored_df.to_csv(out / "metric_concern_scorecard.csv", index=False)
    pillars.to_csv(out / "pillar_scorecard.csv", index=False)
    pd.DataFrame(result.get("water_periods", [])).to_csv(out / "water_periods.csv", index=False)
    pd.DataFrame(result.get("qa", [])).to_csv(out / "metric_qa_scorecard.csv", index=False)
    pd.DataFrame(result.get("observations", []), columns=["metric","pillar","raw_value","units","direction","source_type","evidence_class","temporal_window","reference_value","reference_level","reference_approved","uncertainty","sample_n","status","interpretation","notes"]).to_csv(out / "external_evidence.csv", index=False)
    if result.get("landcover"):
        pd.DataFrame([{"dynamic_world_class": k, "fraction": v} for k,v in result["landcover"].items()]).to_csv(out / "landcover_composition.csv", index=False)
    if result.get("edna"):
        pd.DataFrame([e.to_dict() for e in result["edna"]]).to_csv(out / "edna_evidence.csv", index=False)

    attachments_map = {}
    for key in ["edna_pdf","edna_html","krona_html"]:
        rel = _copy_input((result.get("inputs") or {}).get(key), attachments)
        if rel: attachments_map[key] = rel

    (out / "readiness.json").write_text(json.dumps(result.get("readiness", {}), indent=2, default=str), encoding="utf-8")
    (out / "overall_scorecard.json").write_text(json.dumps(result.get("overall", {}), indent=2, default=str), encoding="utf-8")
    (out / "reference_diagnostics.json").write_text(json.dumps(result.get("reference_diagnostics", {}), indent=2, default=str), encoding="utf-8")
    manifest = {
        "package": "darukaa_adaptive", "version": config.profile.version, "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": platform.python_version(), "site_file": str(site_path), "site_sha256": hashlib.sha256(Path(site_path).read_bytes()).hexdigest(),
        "git_commit": _git_commit_for(Path.cwd()), "boundary_area_ha": result.get("boundary_area_ha"), "config": config.to_dict(),
        "reference_diagnostics": result.get("reference_diagnostics", {}), "overall_scorecard": result.get("overall", {}), "attachments": attachments_map,
        "architecture": {"pillars": ["C1_extent","C2_vegetation","C3_fauna","C4_pressure"], "reference_strategy": config.reference.strategy, "condition_pillars": config.scoring.condition_pillars, "pressure_pillar": config.scoring.pressure_pillar},
    }
    (out / "assessment_manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")

    return {
        "output_dir": str(out), "metric_scorecard": str(out / "metric_scorecard.csv"), "benchmark_scorecard": str(out / "benchmark_scorecard.csv"),
        "metric_concern_scorecard": str(out / "metric_concern_scorecard.csv"), "pillar_scorecard": str(out / "pillar_scorecard.csv"),
        "water_periods": str(out / "water_periods.csv"), "metric_qa": str(out / "metric_qa_scorecard.csv"), "readiness": str(out / "readiness.json"),
        "overall_scorecard": str(out / "overall_scorecard.json"), "reference_diagnostics": str(out / "reference_diagnostics.json"), "manifest": str(out / "assessment_manifest.json"),
        "attachments": attachments_map,
    }
