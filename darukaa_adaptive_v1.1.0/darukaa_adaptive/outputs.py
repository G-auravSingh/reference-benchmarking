"""Write the run bundle: tables, JSON manifest, HTML report and a ZIP archive."""
from __future__ import annotations

import html
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from . import catalogue as cat
from .assessment import AssessmentResult
from .config import VERSION
from .measurement import status_layers
from .scorecard import concern_label

SOURCE_LABELS = {"STD": "Standard / framework", "ACAD": "Academic dataset", "VENDOR": "Vendor / tool approach",
                 "DARUKAA": "Darukaa evidence"}


def _git_commit() -> str:
    env = os.environ.get("DARUKAA_GIT_COMMIT")
    if env:
        return env
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=Path(__file__).parent).stdout.strip()
    except Exception:  # noqa: BLE001 - commit is informational only
        return "unknown"


def tables(res: AssessmentResult) -> Dict[str, pd.DataFrame]:
    score_by = {(s.unit_id, s.metric): s for s in res.scores}
    mrows = []
    for m in res.measurements:
        c = cat.get(m.metric)
        s = score_by.get((m.unit_id, m.metric))
        role = res.roles[m.metric].applied_role
        layers = status_layers(m, role, s.score if s else None, s.confidence if s else None,
                               bool(s and s.reference_status in {"ok", "natural_scale"}))
        mrows.append({
            "unit_id": m.unit_id, "level": m.level, "metric": m.metric, "name": c.name, "pillar": c.pillar,
            "component": c.component, "value": m.value, "unit": c.unit, "status": m.status,
            "ran": layers.ran, "measured_valid": layers.measured_valid, "sufficient_to_score": layers.sufficient_to_score,
            "interpretable": layers.interpretable, "status_reason": layers.reason,
            "recommended_role": c.recommended_role, "applied_role": role, "role_deviates": res.roles[m.metric].deviates,
            "granularity": c.granularity, "pressure_modelled": c.pressure_modelled, "landscape_context": c.landscape_context,
            "native_scale_m": m.native_scale_m, "analysis_scale_m": m.analysis_scale_m,
            "covered_pixel_equivalent": m.covered_pixel_equivalent, "centre_pixels": m.touched_pixels,
            "context_buffer_m": m.context_buffer_m, "effective_period": m.effective_period,
            "period_gap_years": m.period_gap_years, "datasets": "; ".join(d.asset_id for d in c.datasets),
            "source_labels": ", ".join(sorted({SOURCE_LABELS[d.source_label] for d in c.datasets})),
            "framework_tags": ", ".join(c.framework_tags), "notes": m.notes, "error": m.error,
            "extras": json.dumps(m.extras, default=str),
        })
    srows = [s.row() for s in res.scores if s.role == "scored"]
    prow = [p.row() for p in res.pillars]
    hrow = [h.row() for h in res.headlines]
    roles = pd.DataFrame(cat.catalogue_table(res.roles))
    units = pd.DataFrame([s.to_dict() for s in res.units.sites])
    proj = []
    for k in ("condition", "pressure", "P1", "P2", "P3", "P4"):
        r = res.project[k]
        proj.append({"item": k, "value_0_100": r["value"], "low": r["interval"][0], "high": r["interval"][1],
                     "concern": concern_label(r["value"]), "label": r["label"]})
    return {
        "metrics": pd.DataFrame(mrows), "scores": pd.DataFrame(srows), "pillars": pd.DataFrame(prow),
        "site_headlines": pd.DataFrame(hrow), "project_summary": pd.DataFrame(proj), "metric_roles": roles,
        "units": units, "nature_positive_coverage": pd.DataFrame(res.project["nature_positive_coverage"]),
        "reference_condition_pool": pd.DataFrame(res.references.get("condition_pool") or []),
        "flags": pd.DataFrame(res.flags),
    }


def _fmt(x, nd=1):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "–"
    if isinstance(x, (int, float)):
        return f"{x:.{nd}f}"
    return html.escape(str(x))


def html_report(res: AssessmentResult, t: Dict[str, pd.DataFrame]) -> str:
    p = res.project
    cov = t["nature_positive_coverage"]
    def table(df, cols):
        if df.empty:
            return "<p class='muted'>None.</p>"
        head = "".join(f"<th>{html.escape(c)}</th>" for c in cols)
        body = "".join("<tr>" + "".join(f"<td>{_fmt(r.get(c), 2)}</td>" for c in cols) + "</tr>" for r in df.to_dict("records"))
        return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
    cond, pres = p["condition"], p["pressure"]
    mt = t["metrics"]
    site_rows = mt[mt["level"] == "site"]
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>Darukaa Adaptive assessment: {html.escape(res.units.project_id)}</title>
<style>body{{font-family:system-ui,Arial,sans-serif;margin:24px;color:#1d2a24;max-width:1200px}}h1{{font-size:22px}}h2{{font-size:17px;margin-top:28px;border-bottom:1px solid #ccc}}
table{{border-collapse:collapse;font-size:12px;width:100%;margin:8px 0}}th,td{{border:1px solid #ddd;padding:4px 6px;text-align:left;vertical-align:top}}th{{background:#f2f5f3}}
.tile{{display:inline-block;border:1px solid #cfd8d3;border-radius:6px;padding:10px 14px;margin:6px 8px 6px 0;min-width:200px}}.big{{font-size:24px;font-weight:600}}.muted{{color:#667}}.note{{background:#fff8e1;padding:8px;border-left:3px solid #e0a800}}</style></head><body>
<h1>Biodiversity baseline (ex-situ, preparatory): {html.escape(res.units.project_id)}</h1>
<p class='muted'>Darukaa Adaptive v{VERSION} · commit {_git_commit()[:10]} · assessment window {res.config.window_start} to {res.config.window_end} · baseline year {res.config.baseline_year} · generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC</p>
<p class='note'>All results are <b>preparatory</b> under the Nature Positive Initiative measurement guidance (satellite data, natural/non-natural classification, no ground-truthing). They support screening and baseline description; they do not support nature-positive claims. Landscape results are context and are not attributable to the project.</p>
<h2>Nature Positive State of Nature indicators [standard]</h2>{table(cov, ['indicator','covered','how'])}
<h2>Headline (Darukaa 0–100 index [Darukaa])</h2>
<div class='tile'><div class='muted'>Ecosystem condition (P1+P2{'+P3' if any('P3' in str(h) for h in t['site_headlines'].get('condition_pillars', [])) else ''})</div><div class='big'>{_fmt(cond['value'])}</div><div>90% interval {_fmt(cond['interval'][0])}–{_fmt(cond['interval'][1])} · concern {concern_label(cond['value']) or '–'}</div><div class='muted'>{html.escape(cond['label'])}</div></div>
<div class='tile'><div class='muted'>Pressure (P4, reported separately)</div><div class='big'>{_fmt(pres['value'])}</div><div>90% interval {_fmt(pres['interval'][0])}–{_fmt(pres['interval'][1])}</div><div class='muted'>{html.escape(pres['label'])}; 100 = at or below the low-pressure reference of the same ecoregion</div></div>
<h2>Sites</h2>{table(t['units'], ['site_id','boundary_source','area_ha','emu_ids','emu_share_of_site_pct','flags'])}
<h2>Pillars by unit</h2>{table(t['pillars'][t['pillars']['status']!='insufficient_evidence'] if not t['pillars'].empty else t['pillars'], ['unit_id','pillar_name','score_0_100','score_low','score_high','concern','limiting_component','n_metrics','component_scores','flags'])}
<p class='muted'>Pillars without enough scored evidence are listed in pillars.csv with status insufficient_evidence; they are not shown as numbers.</p>
<h2>Site metrics</h2>{table(site_rows, ['unit_id','pillar','name','value','unit','status','applied_role','sufficient_to_score','interpretable','context_buffer_m','effective_period','source_labels'])}
<h2>Scored metrics with references and confidence</h2>{table(t['scores'], ['unit_id','metric','value','score_0_100','score_low','score_high','confidence','confidence_reasons','reference_status','reference_n','basis','score_vs_surroundings','absolute_class'])}
<h2>Condition reference pool</h2><p>Ecoregion: {html.escape(str(res.references.get('ecoregion')))} · sample points {res.references.get('condition_points')}</p>{table(t['reference_condition_pool'], ['stratum','stage','hmi_threshold','pixels_total','pixels_least_disturbed'])}
<h2>Metric roles</h2><p class='muted'>Role mode: {res.config.scoring.role_mode}. Departures from the recommended role are marked.</p>{table(t['metric_roles'], ['id','pillar','recommended_role','applied_role','role_deviates','role_reason_applied','reference_type','framework_tags'])}
<h2>Review flags</h2>{table(t['flags'], ['severity','code','message'])}
<h2>Method disclosure</h2><p>Scope: {len(res.units.sites)} site(s); EMUs nested inside sites. Natural mask: Nature Trace Forest Typology 2020 (10 m, CC-BY-4.0) for tree cover, SBTN Natural Lands v1.1 2020 (30 m, CC-BY-SA-4.0) otherwise, Dynamic World for change. Reference: least-disturbed pixels of the same natural type in the same RESOLVE ecoregion within {res.config.pool.radius_km} km, outside all sites plus {res.config.pool.exclusion_m:.0f} m (condition); same-size blocks in the same ring: pressure is scored against the blocks with the highest 2020 natural share (selected without any pressure metric) and the worst 5% of all blocks; the all-ring comparison is shown as context. Intervals: spatial-block bootstrap ({res.config.scoring.n_bootstrap} draws). Peak-greenness window: {res.peak_window[0]} to {res.peak_window[1]} ({html.escape(res.peak_basis)}). Full contracts: docs/methodology/metric_catalogue_v1.md.</p>
</body></html>"""


def write_bundle(res: AssessmentResult, output_dir: str | Path) -> Dict[str, str]:
    out = Path(output_dir) / res.units.project_id
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    t = tables(res)
    paths = {}
    for name, df in t.items():
        p = out / f"{name}.csv"
        df.to_csv(p, index=False)
        paths[name] = str(p)
    manifest = {"package_version": VERSION, "git_commit": _git_commit(), "generated_utc": datetime.now(timezone.utc).isoformat(),
                "project_id": res.units.project_id, "config": res.config.to_dict(), "units": res.units.to_dict(),
                "peak_window": list(res.peak_window), "peak_basis": res.peak_basis, "references": res.references,
                "project": {k: v for k, v in res.project.items()}, "flags": res.flags}
    (out / "run_manifest.json").write_text(json.dumps(manifest, indent=2, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)), encoding="utf-8")
    (out / "report.html").write_text(html_report(res, t), encoding="utf-8")
    archive = shutil.make_archive(str(out), "zip", root_dir=out.parent, base_dir=out.name)
    paths.update({"manifest": str(out / "run_manifest.json"), "report": str(out / "report.html"), "archive": archive})
    return paths
