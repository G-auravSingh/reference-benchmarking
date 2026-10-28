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
    for k in ("P1", "P2", "P3", "P4", "son", "pressure"):
        r = res.project[k]
        proj.append({"item": k, "value_0_100": r["value"], "low": r["interval"][0], "high": r["interval"][1],
                     "concern": concern_label(r["value"]), "confidence": r.get("confidence"),
                     "weakest_pillar": r.get("weakest_pillar"), "coverage_label": r.get("coverage_label"),
                     "divergence_flag": r.get("divergence_flag"),
                     "limiting_metrics": ", ".join(r.get("limiting_metrics") or []), "label": r["label"]})
    return {
        "metrics": pd.DataFrame(mrows), "scores": pd.DataFrame(srows), "pillars": pd.DataFrame(prow),
        "site_headlines": pd.DataFrame(hrow), "project_summary": pd.DataFrame(proj), "metric_roles": roles,
        "units": units, "restoration_and_change": pd.DataFrame(res.project["restoration"]["sites"]),
        "canopy_height_evidence": pd.DataFrame(canopy_evidence_rows(res)),
        "priority_species": pd.DataFrame(priority_species_rows(res)),
        "nature_positive_coverage": pd.DataFrame(res.project["nature_positive_coverage"]),
        "reference_condition_pool": pd.DataFrame(res.references.get("condition_pool") or []),
        "flags": pd.DataFrame(res.flags),
    }


def canopy_evidence_rows(res: AssessmentResult) -> List[Dict[str, Any]]:
    """One row per unit and source for canopy height (D-28-1): what is measured, the reading, caveats."""
    rows = []
    for m in res.measurements:
        if m.metric != "canopy_height_m":
            continue
        ex = m.extras or {}
        base = {"unit_id": m.unit_id, "level": m.level, "metric_status": m.status, "scored_value_m": m.value,
                "woody_natural_ha": ex.get("woody_ha"), "eligible_ha": ex.get("eligible_ha"),
                "excluded_post_epoch_ha": ex.get("excluded_post_epoch_ha"),
                "by_type": "; ".join(f"{nm_strata(k)}: {v.get('mean'):.2f} m" for k, v in (ex.get("by_stratum") or {}).items()
                                     if isinstance(v, dict) and v.get("mean") is not None),
                "disagreement": json.dumps(ex.get("disagreement") or []), "caveats": ex.get("caveats")}
        for src, d in (ex.get("sources") or {}).items():
            rows.append({**base, "source": src, "quantity": d.get("quantity"), "reading": d.get("reading"),
                         "support": d.get("n_pixels") or d.get("n_footprints")})
        if not ex.get("sources"):
            rows.append({**base, "source": "meta_mean", "quantity": "mean of 1 m heights (gaps included)",
                         "reading": m.status, "support": None})
    return rows


def nm_strata(code) -> str:
    from . import natural_mask as nm
    try:
        return nm.STRATA.get(int(code), str(code))
    except (TypeError, ValueError):
        return str(code)


def priority_species_rows(res: AssessmentResult) -> List[Dict[str, Any]]:
    rows = []
    for m in res.measurements:
        if m.metric == "priority_species_habitat_trend" and m.level == "site":
            for r in (m.extras or {}).get("species") or []:
                rows.append({"unit_id": m.unit_id, **r})
    return rows


def _species_section(res: AssessmentResult) -> str:
    out = []
    for m in res.measurements:
        if m.level != "site" or m.metric not in ("star_t_estimated", "rarity_weighted_richness", "priority_species_habitat_trend"):
            continue
        c = cat.get(m.metric)
        ex = m.extras or {}
        detail = ""
        if m.metric == "star_t_estimated" and ex.get("top_contributors"):
            detail = "top: " + ", ".join(f"{t['sci_name']} ({t['category']}, {t['contribution']:.3g})" for t in ex["top_contributors"][:5])
        if m.metric == "priority_species_habitat_trend" and ex.get("counts"):
            k = ex["counts"]
            detail = (f"{ex.get('n_priority')} priority species: declining {k['declining']}, stable {k['stable']}, "
                      f"increasing (candidate) {k['increasing_candidate']}; slowing in decline not assessable")
        out.append(f"<tr><td>{html.escape(m.unit_id)}</td><td>{html.escape(c.name)}</td><td>{_fmt(m.value, 3)}</td>"
                   f"<td>{html.escape(c.unit)}</td><td>{html.escape(m.status)}</td><td>{html.escape(detail)}</td></tr>")
    if not out:
        return "<p class='muted'>Not measured in this run.</p>"
    return ("<table><thead><tr><th>unit</th><th>metric</th><th>value</th><th>unit</th><th>status</th><th>detail</th></tr></thead>"
            f"<tbody>{''.join(out)}</tbody></table>")


def _fmt(x, nd=1):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "–"
    if isinstance(x, (int, float)):
        return f"{x:.{nd}f}"
    return html.escape(str(x))


def _pillar_tile(key: str, r: Dict) -> str:
    if r["value"] is None:
        body = f"<div class='big'>–</div><div class='muted'>not scored: {html.escape(r['label'])}</div>"
    else:
        lim = ", ".join(r.get("limiting_metrics") or []) or "–"
        body = (f"<div class='big'>{_fmt(r['value'])}</div><div>90% interval {_fmt(r['interval'][0])}–{_fmt(r['interval'][1])}"
                f" · confidence {_fmt(r.get('confidence'))}</div><div class='muted'>set by: {html.escape(lim)}; {html.escape(r['label'])}</div>")
    return f"<div class='tile'><div class='muted'>{html.escape(cat.PILLARS[key])}</div>{body}</div>"


def _restoration_table(rest: Dict) -> str:
    tot = rest["totals"]
    rows = [("Candidate gross gain, all types", "candidate_gain_ha")] + [(f"  gain as {k[5:-3].replace('_', ' ')}", k) for k in
            ("gain_trees_ha", "gain_shrub_and_scrub_ha", "gain_grass_ha", "gain_flooded_vegetation_ha", "gain_water_ha")]
    rows += [("Gross loss, all types", "gross_loss_ha"), ("  loss from natural forest (2020)", "loss_from_natural_forest_ha"),
             ("  loss from other natural (2020)", "loss_from_other_natural_ha"), ("  converted to cropland", "loss_to_crops_ha"),
             ("  converted to built-up", "loss_to_built_ha")]
    body = "".join(f"<tr><td>{html.escape(lab)}</td><td>{_fmt(tot[k]['value'], 2)}</td><td>{tot[k]['sites_with_value']} of {tot[k]['sites']}"
                   f"{' (partial)' if tot[k]['partial'] else ''}</td></tr>" for lab, k in rows)
    return f"<table><thead><tr><th>Item</th><th>ha</th><th>sites with a valid value</th></tr></thead><tbody>{body}</tbody></table>"


def html_report(res: AssessmentResult, t: Dict[str, pd.DataFrame]) -> str:
    p = res.project
    cov = t["nature_positive_coverage"]
    def table(df, cols):
        if df.empty:
            return "<p class='muted'>None.</p>"
        head = "".join(f"<th>{html.escape(c)}</th>" for c in cols)
        body = "".join("<tr>" + "".join(f"<td>{_fmt(r.get(c), 2)}</td>" for c in cols) + "</tr>" for r in df.to_dict("records"))
        return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
    son, pres = p["son"], p["pressure"]
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
<h2>State of nature profile (by pillar)</h2>
<p class='muted'>Primary view (D-27-2). Each pillar takes its weakest component, so a strong component never hides a weak one. Area-weighted across sites. Condition covers natural and semi-natural land only.</p>
{''.join(_pillar_tile(k, p[k]) for k in ('P1','P2','P3'))}
<div class='tile'><div class='muted'>{cat.PILLARS['P4']} (reported separately, not part of the state of nature)</div><div class='big'>{_fmt(pres['value'])}</div><div>90% interval {_fmt(pres['interval'][0])}–{_fmt(pres['interval'][1])} · confidence {_fmt(pres.get('confidence'))}</div><div class='muted'>{html.escape(pres['label'])}; 100 = at or below the low-pressure reference of the same ecoregion</div></div>
<h2>Restoration and change since 2020 (gross, by type)</h2>
<p class='muted'>{html.escape(p['restoration']['note'])} Losses and gains are never netted.</p>
{_restoration_table(p['restoration'])}
<h2>SoN composite score (secondary)</h2>
<div class='tile'><div class='muted'>{html.escape(son['label'])}</div><div class='big'>{_fmt(son['value'])}</div><div>90% interval {_fmt(son['interval'][0])}–{_fmt(son['interval'][1])} · confidence {_fmt(son.get('confidence'))} · coverage: {html.escape(son.get('coverage_label') or '–')}</div><div>Weakest pillar: {_fmt(son.get('weakest_pillar'))} ({_fmt(son.get('weakest_pillar_score'))})</div>{f"<div class='note'>{html.escape(son['divergence_flag'])}</div>" if son.get('divergence_flag') else ''}</div>
<p class='muted'>Equal-weight geometric mean of the scored state pillars (P1, P2, plus P3 when covered); withheld unless P1 and P2 are both scored; pressure is never included. The Nature Positive State of Nature indicators define no composite number; read the pillar profile first.</p>
<h2>Canopy height evidence</h2>
<p class='muted'>{html.escape(cat.get('canopy_height_m').definition)} It is not tree height. {html.escape(cat.get('canopy_height_m').notes)}</p>
{table(t['canopy_height_evidence'], ['unit_id','source','quantity','reading','support','metric_status','scored_value_m','eligible_ha','excluded_post_epoch_ha','by_type'])}
<h2>Species (preparatory, reported not scored)</h2>
<p class='muted'>Range maps, not observations: a range overlapping the site does not mean the species is present. Estimated STAR-t and rarity-weighted richness show the site's share of global (threat-weighted) range; they are importance, not condition. The habitat trend uses natural habitat within each priority species' range as the population proxy (Nature Positive preparatory granularity).</p>
{_species_section(res)}
<h2>Sites: headline</h2>{table(t['site_headlines'], ['unit_id','son_score_0_100','son_low','son_high','son_confidence','coverage_label','weakest_pillar','weakest_pillar_score','weakest_pillar_metric','son_divergence_flag','pressure_score_0_100','pressure_confidence','son_status'])}
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
