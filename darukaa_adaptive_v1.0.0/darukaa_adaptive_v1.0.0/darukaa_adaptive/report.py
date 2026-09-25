"""Auditable report/manifest writer."""
from __future__ import annotations

import hashlib, json, platform
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def write_assessment(output_dir, config, site_path, boundary_area_ha, domains, metrics, water_periods, readiness):
    out=Path(output_dir); out.mkdir(parents=True,exist_ok=True)
    metric_df=pd.DataFrame([m.to_dict() for m in metrics])
    metric_df.to_csv(out/"metric_scorecard.csv",index=False)
    pd.DataFrame(water_periods).to_csv(out/"water_periods.csv",index=False)
    manifest={
        "package":"darukaa_adaptive", "version":"1.0.0", "run_timestamp_utc":datetime.now(timezone.utc).isoformat(),
        "python_version":platform.python_version(), "site_file":str(site_path),
        "site_sha256":hashlib.sha256(Path(site_path).read_bytes()).hexdigest(),
        "boundary_area_ha":boundary_area_ha, "config":config.to_dict(), "readiness":readiness,
        "domains":{"fixed":"master boundary + standardized riparian/context domains", "dynamic":"water masks are generated per observation period"},
        "metrics": [m.to_dict() for m in metrics],
    }
    (out/"assessment_manifest.json").write_text(json.dumps(manifest,indent=2,default=str),encoding="utf-8")
    (out/"README_OUTPUTS.md").write_text(
        "# Assessment outputs\n\n"
        "- `metric_scorecard.csv`: raw metric values, domain, dates, datasets, status and scoring eligibility.\n"
        "- `water_periods.csv`: dynamic water extent summaries for requested periods.\n"
        "- `assessment_manifest.json`: configuration and provenance record, including SHA-256 hash of the input KML.\n"
        "- Composite aquatic SoN scoring is disabled unless explicitly configured with reviewed thresholds.\n",
        encoding="utf-8")
    return {"metric_scorecard":str(out/"metric_scorecard.csv"),"water_periods":str(out/"water_periods.csv"),"manifest":str(out/"assessment_manifest.json")}
