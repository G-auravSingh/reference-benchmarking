"""Auditable report and manifest writer for adaptive assessments."""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from .benchmark import benchmark_dataframe
from .registry import indicator_table, legacy_crosswalk


def _git_commit_for(path: Path) -> Optional[str]:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=path, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def write_assessment(
    output_dir,
    config,
    site_path,
    boundary_area_ha,
    domains,
    metrics,
    water_periods,
    readiness,
    benchmarks=None,
    scored_df=None,
    pillar_df=None,
    overall=None,
    landcover=None,
    extra_manifest: Optional[dict] = None,
):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    metric_df = pd.DataFrame([m.to_dict() for m in metrics])
    metric_df.to_csv(out / "metric_scorecard.csv", index=False)

    if benchmarks is not None:
        benchmark_dataframe(benchmarks).to_csv(out / "benchmark_scorecard.csv", index=False)
    else:
        pd.DataFrame().to_csv(out / "benchmark_scorecard.csv", index=False)

    if scored_df is not None:
        scored_df.to_csv(out / "metric_concern_scorecard.csv", index=False)
    else:
        pd.DataFrame().to_csv(out / "metric_concern_scorecard.csv", index=False)

    if pillar_df is not None:
        pillar_df.to_csv(out / "pillar_scorecard.csv", index=False)
    else:
        pd.DataFrame().to_csv(out / "pillar_scorecard.csv", index=False)

    pd.DataFrame(water_periods).to_csv(out / "water_periods.csv", index=False)

    if landcover is not None:
        pd.DataFrame([{"dynamic_world_class": k, "fraction": v} for k, v in landcover.items()]).to_csv(
            out / "landcover_composition.csv", index=False
        )

    (out / "readiness.json").write_text(json.dumps(readiness, indent=2, default=str), encoding="utf-8")
    (out / "overall_scorecard.json").write_text(json.dumps(overall or {}, indent=2, default=str), encoding="utf-8")
    pd.DataFrame(indicator_table()).to_csv(out / "indicator_registry.csv", index=False)
    pd.DataFrame(legacy_crosswalk()).to_csv(out / "legacy_metric_crosswalk.csv", index=False)

    manifest = {
        "package": "darukaa_adaptive",
        "version": config.profile.version,
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": platform.python_version(),
        "site_file": str(site_path),
        "site_sha256": hashlib.sha256(Path(site_path).read_bytes()).hexdigest(),
        "git_commit": _git_commit_for(Path.cwd()),
        "boundary_area_ha": boundary_area_ha,
        "config": config.to_dict(),
        "readiness": readiness,
        "overall_scorecard": overall or {},
        "spatial_domains": {
            "master_boundary": True,
            "fixed_riparian_buffer_m": config.spatial.riparian_buffer_m,
            "context_buffer_km": config.spatial.context_buffer_km,
            "dynamic_water_generated_per_period": True,
        },
        "metrics": [m.to_dict() for m in metrics],
    }
    if extra_manifest:
        manifest.update(extra_manifest)

    (out / "assessment_manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")

    (out / "README_OUTPUTS.md").write_text(
        "# Assessment outputs\n\n"
        "`metric_scorecard.csv` contains the raw metric measurements and provenance.\n\n"
        "`benchmark_scorecard.csv` contains Tier-1/Tier-2 reference values and direction-aware relative comparison where applicable.\n\n"
        "`metric_concern_scorecard.csv` contains 1-5 concern scores only where approved thresholds or explicitly enabled reference-relative bands exist.\n\n"
        "`pillar_scorecard.csv` aggregates only scored metrics with a minimum-evidence rule.\n\n"
        "`overall_scorecard.json` reports the 0-10 composite only when the required pillar coverage is met.\n\n"
        "`water_periods.csv` contains dynamic surface-water summaries.\n\n"
        "`readiness.json` records baseline, reference and field-validation readiness.\n\n"
        "`assessment_manifest.json` captures configuration and input SHA-256 provenance.\n",
        encoding="utf-8",
    )

    return {
        "metric_scorecard": str(out / "metric_scorecard.csv"),
        "benchmark_scorecard": str(out / "benchmark_scorecard.csv"),
        "metric_concern_scorecard": str(out / "metric_concern_scorecard.csv"),
        "pillar_scorecard": str(out / "pillar_scorecard.csv"),
        "water_periods": str(out / "water_periods.csv"),
        "readiness": str(out / "readiness.json"),
        "overall_scorecard": str(out / "overall_scorecard.json"),
        "manifest": str(out / "assessment_manifest.json"),
    }
