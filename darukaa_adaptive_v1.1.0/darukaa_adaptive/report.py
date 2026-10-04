"""Auditable outputs plus a self-contained professional Year-0 HTML report."""
from __future__ import annotations
import hashlib, html, json, platform, subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import pandas as pd
from .benchmark import benchmark_dataframe
from .registry import indicator_table, legacy_crosswalk


def _git_commit_for(path):
    # Prefer an explicit release identity supplied by the execution environment;
    # otherwise walk upward from the working directory. This prevents the manifest
    # from silently losing provenance in Colab where the notebook runs outside the
    # cloned repository.
    import os
    explicit = os.environ.get("DARUKAA_GIT_COMMIT")
    if explicit:
        return explicit
    p = Path(path).resolve()
    candidates = [p] + list(p.parents)
    for candidate in candidates:
        try:
            return subprocess.check_output(["git","rev-parse","HEAD"],cwd=candidate,text=True,stderr=subprocess.DEVNULL).strip()
        except Exception:
            continue
    return None

def _table(df, max_rows=200):
    if df is None or df.empty: return '<div class="empty">No data available.</div>'
    return df.head(max_rows).to_html(index=False, classes="data", border=0, na_rep="—")

def _bar(label, value, status=None):
    if value is None or status not in (None, 'scored'):
        text = 'Not assessed' if status and status != 'scored' else '—'
        return f'<div class="barrow"><span>{html.escape(label)}</span><span>{text}</span></div>'
    v=max(0,min(100,float(value)))
    return f'<div class="barrow"><span>{html.escape(label)}</span><div class="track"><div class="fill" style="width:{v:.1f}%"></div></div><b>{v:.1f}</b></div>'

def write_html_report(out, config, site_path, area_ha, domains, metrics_df, benchmark_df, scored_df, pillar_df, overall, water_df, readiness, evidence_df=None):
    out=Path(out); evidence_df=evidence_df if evidence_df is not None else pd.DataFrame()
    cond=overall.get("condition_score_0_to_100"); press=overall.get("pressure_score_0_to_100")
    title=config.profile.name.replace('_',' ').title()
    gaps=[]
    c3_scored = False
    if not scored_df.empty and "pillar" in scored_df.columns and "score_eligible" in scored_df.columns:
        c3_scored = bool(scored_df.loc[scored_df["pillar"].eq("C3_fauna"), "score_eligible"].fillna(False).any())
    if not c3_scored:
        gaps.append("Fauna evidence (field/acoustic/eDNA) is not currently score-eligible; C3 cannot be treated as a completed condition pillar.")
    if overall.get("status") == "insufficient_fauna_coverage":
        gaps.append("Overall condition scoring is gated because the configured profile requires a scored C3 Fauna pillar.")
    if benchmark_df.empty: gaps.append("No reference benchmark was generated.")
    elif not benchmark_df.empty and (benchmark_df.get("selected_reference").isna().all()): gaps.append("No defensible reference value was available for the scoreable indicators.")
    if evidence_df.empty: gaps.append("No optional external/eDNA evidence file was supplied.")
    generated=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    pillar_html=''.join(_bar(str(r.pillar_name),r.score_0_to_100,r.status) for _,r in pillar_df.iterrows()) if not pillar_df.empty else '<div class="empty">No pillar scores.</div>'
    metric_display=scored_df.copy()
    if not metric_display.empty:
        cols=[c for c in ["metric","pillar","raw_value","units","reference_value","reference_attainment_0_100","relative_departure_pct","concern_label","score_status","evidence_type"] if c in metric_display.columns]
        metric_display=metric_display[cols]
    html_doc=f'''<!doctype html><html><head><meta charset="utf-8"><title>Biodiversity Baseline — {html.escape(title)}</title>
<style>
body{{font-family:Inter,Arial,sans-serif;margin:0;background:#f4f6f8;color:#17202a}} .wrap{{max-width:1180px;margin:auto;padding:28px}}
.hero{{background:#13202b;color:white;padding:42px;border-radius:18px;margin-bottom:22px}} h1{{font-size:34px;margin:0 0 8px}} h2{{margin-top:34px;border-bottom:1px solid #d8dee4;padding-bottom:8px}} h3{{margin-top:24px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px}} .card{{background:white;border:1px solid #e0e5ea;border-radius:12px;padding:18px}} .big{{font-size:30px;font-weight:700}} .muted{{color:#65727e}}
.data{{width:100%;border-collapse:collapse;background:white;font-size:13px}} .data th,.data td{{padding:8px;border-bottom:1px solid #e6eaee;text-align:left}} .data th{{background:#eef2f5}} .barrow{{display:grid;grid-template-columns:180px 1fr 55px;gap:10px;align-items:center;margin:10px 0}} .track{{height:12px;background:#e5e9ed;border-radius:8px;overflow:hidden}} .fill{{height:100%;background:#3d667c}}
.notice{{background:#fff8e6;border-left:4px solid #c58a18;padding:12px 15px;margin:12px 0}} .good{{background:#edf7f0;border-left:4px solid #3f7d54;padding:12px 15px}} .empty{{padding:18px;background:#fff;border:1px dashed #b8c1ca;color:#697681}} code{{background:#eef2f5;padding:2px 4px;border-radius:4px}}
footer{{margin-top:40px;color:#697681;font-size:12px}}
</style></head><body><div class="wrap">
<div class="hero"><h1>Biodiversity Baseline Assessment</h1><div>{html.escape(title)}</div><div class="muted" style="color:#cbd4da;margin-top:12px">Year-0 • {html.escape(config.temporal.baseline_label)} • Framework v{html.escape(config.profile.version)} • Generated {generated}</div></div>
<div class="grid"><div class="card"><div class="muted">Master boundary</div><div class="big">{area_ha:.2f} ha</div></div><div class="card"><div class="muted">Profile</div><div class="big" style="font-size:20px">{html.escape(config.profile.name)}</div></div><div class="card"><div class="muted">Condition</div><div class="big">{('%.1f' % cond) if cond is not None else 'Pending'}</div></div><div class="card"><div class="muted">Pressure</div><div class="big">{('%.1f' % press) if press is not None else 'Pending'}</div></div></div>
<h2>Executive Summary</h2><p>This Year-0 assessment establishes a reproducible baseline from the supplied project boundary and available evidence. The framework separates measured indicators, reference-condition construction, reference QA/approval, reference-relative departure and interpretation. Aquatic and terrestrial domains are handled separately where applicable; optional field, acoustic and eDNA evidence can be added without changing the scoring architecture.</p>
<div class="notice"><b>Scoring guardrail:</b> a valid measurement is not automatically a scored ecological indicator. Reference comparability, uncertainty and evidence provenance are retained explicitly.</div>
<h2>1. Assessment Overview</h2><div class="grid"><div class="card"><b>Boundary</b><br>Master assessment boundary supplied by the project.</div><div class="card"><b>Baseline</b><br>{html.escape(str(config.temporal.baseline_start_date))} to {html.escape(str(config.temporal.baseline_end_date))}</div><div class="card"><b>Historical context</b><br>{config.temporal.start_year}–{config.temporal.end_year}</div><div class="card"><b>Domains</b><br>Aquatic • littoral/shoreline • riparian • landscape context</div></div>
<h2>2. Assessment Architecture</h2><p><b>Project boundary → ecological domains → multi-source indicators → automatic reference population → reference comparison → reference attainment (0–100) → C1/C2/C3 condition + C4 pressure → transparent management interpretation.</b></p>
<h2>3. Reference Framework</h2><p>The default workflow constructs an ecologically matched reference candidate automatically. The candidate is screened by ecosystem comparability, pressure, temporal compatibility and population quality before it can be approved for scoring. The production workflow does not use manual reference files. If both automatic stages fail, an analyst may enter a single manual HMI threshold in Colab after reviewing the reference diagnostics. The reference state, method, QA diagnostics and approval basis are retained in the assessment manifest.</p>{_table(benchmark_df[[c for c in ["metric","selected_reference","selected_reference_level","reference_n","reference_uncertainty","relative_departure_pct","reference_attainment_0_100","reference_method","reference_state","reference_approval_basis","benchmark_status","reference_approved_for_scoring"] if c in benchmark_df.columns]])}
<h2>4. Indicator Results</h2>{_table(metric_display)}
<h2>5. Pillar Results</h2>{pillar_html}<div style="margin-top:18px">C1 Extent, C2 Vegetation/Habitat and C3 Fauna are treated as condition components. C4 Pressure is reported separately.</div>
<h2>6. State of Nature</h2><div class="grid"><div class="card"><div class="muted">Overall condition</div><div class="big">{('%.1f / 100' % cond) if cond is not None else 'Not scoreable'}</div><div>{html.escape(str(overall.get('condition_concern_label') or ''))}</div></div><div class="card"><div class="muted">Overall pressure</div><div class="big">{('%.1f / 100' % press) if press is not None else 'Not scoreable'}</div><div>{html.escape(str(overall.get('pressure_concern_label') or ''))}</div></div><div class="card"><div class="muted">Limiting condition component</div><div class="big" style="font-size:20px">{html.escape(str(overall.get('limiting_pillar') or 'Pending'))}</div><div>{html.escape(str(overall.get('limiting_metric') or ''))}</div></div></div>
<h2>7. Spatial & Temporal Results</h2>{_table(water_df)}
<h2>8. Multi-source Evidence & eDNA</h2><p>eDNA is an optional evidence stream. When supplied as validated observations, eDNA metrics use the same raw value → reference → intactness → pillar pathway as other evidence. The Nandoshi source report describes <b>eDNA Persistence Potential</b> as an environmental persistence proxy; that type of proxy is retained as contextual unless a defensible reference and validation pathway are supplied.</p>{_table(evidence_df)}
<h2>9. Interpretation & Management Use</h2><p>Interpretations should be tied to the indicator definition, reference comparison, spatial domain and uncertainty. Proxy indicators such as spectral bloom/turbidity signals should not be relabelled as laboratory water-quality measurements without independent validation. Management actions should therefore be linked to the specific limiting indicator and a measurable next-cycle monitoring variable.</p>
<h2>10. Data Gaps & Next-Cycle Improvements</h2>{''.join('<div class="notice">'+html.escape(g)+'</div>' for g in gaps) if gaps else '<div class="good">Current evidence and reference diagnostics are represented in the scorecard.</div>'}
<h2>11. Technical Appendix</h2><p><b>Indicator registry:</b> {len(indicator_table())} active/current registry entries. <b>Evidence model:</b> EO, field, acoustic, eDNA and modelled evidence share one downstream scoring contract. <b>QA/QC:</b> structural metric QA and provenance are exported separately from ecological interpretation.</p><pre>{html.escape(json.dumps(readiness,indent=2,default=str))}</pre>
<footer>Darukaa Adaptive Biodiversity Assessment Framework v{html.escape(config.profile.version)} • This report is generated from the assessment outputs and configuration; it is not a substitute for field/laboratory validation where required.</footer></div></body></html>'''
    path=out/'Year0_Biodiversity_Baseline_Report.html'; path.write_text(html_doc,encoding='utf-8'); return path


def write_assessment(output_dir, config, site_path, boundary_area_ha, domains, metrics, water_periods, readiness,
                     benchmarks=None, scored_df=None, pillar_df=None, overall=None, landcover=None, metric_qa=None,
                     extra_manifest=None, evidence_df=None):
    out=Path(output_dir); out.mkdir(parents=True,exist_ok=True)
    metric_df=pd.DataFrame([m.to_dict() for m in metrics]); metric_df.to_csv(out/'metric_scorecard.csv',index=False)
    bdf=benchmark_dataframe(benchmarks or []); bdf.to_csv(out/'benchmark_scorecard.csv',index=False)
    sdf=scored_df if scored_df is not None else pd.DataFrame(); sdf.to_csv(out/'metric_concern_scorecard.csv',index=False)
    pdf=pillar_df if pillar_df is not None else pd.DataFrame(); pdf.to_csv(out/'pillar_scorecard.csv',index=False)
    pd.DataFrame(water_periods).to_csv(out/'water_periods.csv',index=False)
    if landcover is not None: pd.DataFrame([{"dynamic_world_class":k,"fraction":v} for k,v in landcover.items()]).to_csv(out/'landcover_composition.csv',index=False)
    qdf=metric_qa if metric_qa is not None else pd.DataFrame(); qdf.to_csv(out/'metric_qa_scorecard.csv',index=False)
    edf=evidence_df if evidence_df is not None else pd.DataFrame(); edf.to_csv(out/'external_evidence.csv',index=False)
    ref_cols=[c for c in ['metric','selected_reference','selected_reference_level','reference_n','reference_uncertainty','relative_departure_pct','reference_attainment_0_100','reference_method','reference_state','reference_approval_basis','reference_approved_for_scoring','benchmark_status','interpretation_status','reference_diagnostics'] if c in bdf.columns]
    bdf[ref_cols].to_csv(out/'reference_governance.csv',index=False) if ref_cols else pd.DataFrame().to_csv(out/'reference_governance.csv',index=False)
    (out/'readiness.json').write_text(json.dumps(readiness,indent=2,default=str),encoding='utf-8')
    (out/'overall_scorecard.json').write_text(json.dumps(overall or {},indent=2,default=str),encoding='utf-8')
    pd.DataFrame(indicator_table()).to_csv(out/'indicator_registry.csv',index=False); pd.DataFrame(legacy_crosswalk()).to_csv(out/'legacy_metric_crosswalk.csv',index=False)
    manifest={
        "package":"darukaa_adaptive",
        "version":config.profile.version,
        "run_timestamp_utc":datetime.now(timezone.utc).isoformat(),
        "python_version":platform.python_version(),
        "site_file":str(site_path),
        "site_sha256":hashlib.sha256(Path(site_path).read_bytes()).hexdigest(),
        "git_commit":_git_commit_for(Path.cwd()),
        "boundary_area_ha":boundary_area_ha,
        "config":config.to_dict(),
        "readiness":readiness,
        "overall_scorecard":overall or {},
        "pillar_scorecard":pdf.to_dict(orient='records'),
        "metric_concern_scorecard":sdf.to_dict(orient='records'),
        "benchmark_scorecard":bdf.to_dict(orient='records'),
        "spatial_domains":{"master_boundary":True,"dynamic_water_generated_per_period":True,
                           "fixed_riparian_buffer_m":config.spatial.riparian_buffer_m,
                           "context_buffer_km":config.spatial.context_buffer_km,
                           "reference_search_radius_km":config.reference.search_radius_km},
        "metrics":[m.to_dict() for m in metrics],
        "metric_qa":qdf.to_dict(orient='records'),
        "external_evidence":edf.to_dict(orient='records'),
    }
    if extra_manifest: manifest.update(extra_manifest)
    (out/'assessment_manifest.json').write_text(json.dumps(manifest,indent=2,default=str),encoding='utf-8')
    html_path=write_html_report(out,config,site_path,boundary_area_ha,domains,metric_df,bdf,sdf,pdf,overall or {},pd.DataFrame(water_periods),readiness,edf)
    (out/'README_OUTPUTS.md').write_text('# Assessment outputs\n\nThis directory is the auditable output bundle for the Darukaa Adaptive assessment. It contains raw measurements, measurement QA, reference governance, reference-relative benchmarking, score eligibility, pillar/overall scoring, water-period diagnostics, optional external/eDNA evidence, provenance, and the self-contained Year-0 HTML report. Contextual indicators remain visible but are not silently converted into composite scores.\n\n## Key files\n- `metric_scorecard.csv`: raw metric measurements and data-quality fields.\n- `metric_qa_scorecard.csv`: structural QA/QC.\n- `reference_governance.csv`: reference selection, approval and reference-relative interpretation.\n- `benchmark_scorecard.csv`: complete benchmark records including diagnostics.\n- `metric_concern_scorecard.csv`: score eligibility and concern bands.\n- `pillar_scorecard.csv` / `overall_scorecard.json`: aggregation.\n- `assessment_manifest.json`: exact input hash, configuration, package version and Git commit.\n- `Year0_Biodiversity_Baseline_Report.html`: client-facing report.\n',encoding='utf-8')
    return {"metric_scorecard":str(out/'metric_scorecard.csv'),"benchmark_scorecard":str(out/'benchmark_scorecard.csv'),"reference_governance":str(out/'reference_governance.csv'),"metric_concern_scorecard":str(out/'metric_concern_scorecard.csv'),"pillar_scorecard":str(out/'pillar_scorecard.csv'),"water_periods":str(out/'water_periods.csv'),"readiness":str(out/'readiness.json'),"overall_scorecard":str(out/'overall_scorecard.json'),"manifest":str(out/'assessment_manifest.json'),"html_report":str(html_path),"external_evidence":str(out/'external_evidence.csv')}


def _safe_filename(value: str) -> str:
    import re
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "project"))
    return text.strip("._") or "project"


def write_project_html_report(out, project, emu_results, metric_agg, pillar_agg, manifest):
    """Write a self-contained project-level HTML report for multi-EMU assessments."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    project_name = str(getattr(project, "project_name", None) or manifest.get("project", {}).get("project_name") or "Darukaa Project")
    project_id = str(getattr(project, "project_id", None) or manifest.get("project", {}).get("project_id") or "project")
    total_area = float(sum(float(r.get("emu_area_ha") or 0) for r in emu_results))
    domains = [str(r.get("emu_domain") or "unknown") for r in emu_results]
    domain_text = ", ".join(sorted(set(domains)))

    ref_rows = []
    for r in emu_results:
        refs = r.get("reference_populations") or {}
        if refs:
            for domain, pop in refs.items():
                ref_rows.append({
                    "EMU": r.get("emu_id"),
                    "Domain": domain,
                    "Area (ha)": round(float(r.get("emu_area_ha") or 0), 3),
                    "Reference status": pop.get("status"),
                    "Approved": pop.get("approval"),
                    "Reference state": pop.get("reference_state"),
                    "Method": pop.get("method"),
                    "Candidate area (ha)": pop.get("candidate_area_ha"),
                    "Candidate pixels": pop.get("candidate_pixels"),
                })
        else:
            ref_rows.append({"EMU": r.get("emu_id"), "Domain": r.get("emu_domain"), "Area (ha)": round(float(r.get("emu_area_ha") or 0), 3), "Reference status": "not available", "Approved": False, "Reference state": "", "Method": "", "Candidate area (ha)": None, "Candidate pixels": None})
    ref_df = pd.DataFrame(ref_rows)
    emu_df = pd.DataFrame([{
        "EMU": r.get("emu_id"),
        "Domain": r.get("emu_domain"),
        "Area (ha)": round(float(r.get("emu_area_ha") or 0), 3),
        "Reference approved": any(bool(v.get("approval")) for v in (r.get("reference_populations") or {}).values()),
        "Reference state": ", ".join(sorted({str(v.get("reference_state")) for v in (r.get("reference_populations") or {}).values() if v.get("reference_state")})) or "—",
        "Assessment report": "Year-0 HTML available in EMU output folder",
    } for r in emu_results])
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    metric_df = metric_agg.copy() if isinstance(metric_agg, pd.DataFrame) else pd.DataFrame(metric_agg)
    pillar_df = pillar_agg.copy() if isinstance(pillar_agg, pd.DataFrame) else pd.DataFrame(pillar_agg)
    approved = int(emu_df["Reference approved"].sum()) if not emu_df.empty else 0
    coverage = metric_df["coverage_weight"].mean() * 100 if not metric_df.empty and "coverage_weight" in metric_df.columns else None
    report_name = f"{_safe_filename(project_name)}_Biodiversity_Baseline_Report.html"
    coverage_text = f"{coverage:.1f}%" if coverage is not None else "Not available"

    html_doc = f'''<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(project_name)} — Biodiversity Baseline Assessment</title>
<style>
body{{font-family:Inter,Arial,sans-serif;margin:0;background:#f4f6f8;color:#17202a}} .wrap{{max-width:1240px;margin:auto;padding:30px}}
.hero{{background:#13202b;color:white;padding:42px;border-radius:18px;margin-bottom:22px}} h1{{font-size:34px;margin:0 0 8px}} h2{{margin-top:34px;border-bottom:1px solid #d8dee4;padding-bottom:8px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px}} .card{{background:white;border:1px solid #e0e5ea;border-radius:12px;padding:18px}} .big{{font-size:29px;font-weight:700}} .muted{{color:#65727e}}
.data{{width:100%;border-collapse:collapse;background:white;font-size:13px}} .data th,.data td{{padding:8px;border-bottom:1px solid #e6eaee;text-align:left}} .data th{{background:#eef2f5}}
.notice{{background:#fff8e6;border-left:4px solid #c58a18;padding:12px 15px;margin:12px 0}} .empty{{padding:18px;background:#fff;border:1px dashed #b8c1ca;color:#697681}}
footer{{margin-top:40px;color:#697681;font-size:12px}} code{{background:#eef2f5;padding:2px 4px;border-radius:4px}}
</style></head><body><div class="wrap">
<div class="hero"><h1>Biodiversity Baseline Assessment</h1><div>{html.escape(project_name)}</div><div class="muted" style="color:#cbd4da;margin-top:12px">Year-0 • Generalized EMU Framework v1.1.0 • Generated {generated}</div></div>
<div class="grid"><div class="card"><div class="muted">Assessment area</div><div class="big">{total_area:.2f} ha</div></div><div class="card"><div class="muted">EMUs assessed</div><div class="big">{len(emu_results)}</div></div><div class="card"><div class="muted">Reference-approved EMUs</div><div class="big">{approved} / {len(emu_results)}</div></div><div class="card"><div class="muted">Domains</div><div class="big" style="font-size:20px">{html.escape(domain_text)}</div></div></div>
<h2>Executive Summary</h2><p>This project-level report consolidates the completed EMU assessments while preserving each EMU as an auditable ecological management unit. Metrics are aggregated only after EMU-level measurement, QA/QC and reference-condition processing. Incompatible ecological domains are not pooled into a common reference population.</p>
<div class="notice"><b>Interpretation guardrail:</b> project-level aggregation describes the coverage and weighted state of the assessed EMUs. It does not convert incomplete evidence into zero, and it does not create a project-wide condition score unless that score is explicitly supported by the configured scoring architecture.</div>
<h2>1. Project &amp; Assessment Architecture</h2><div class="grid"><div class="card"><b>Project ID</b><br>{html.escape(project_id)}</div><div class="card"><b>Project domain</b><br>{html.escape(str(getattr(project, 'project_domain', 'auto')))}</div><div class="card"><b>Assessment unit</b><br>EMU; multipart/disconnected geometry retained</div><div class="card"><b>Metric aggregation</b><br>Area-weighted across valid EMU observations</div></div>
<h2>2. EMU Coverage</h2>{_table(emu_df)}
<h2>3. Reference-Condition Governance</h2><p>Reference populations are constructed and approved at EMU/domain level. Approval is QA-gated and does not mean ecological perfection; it means the candidate satisfied the configured reference-selection and quality criteria for benchmarking.</p>{_table(ref_df)}
<h2>4. Project-Level Metric Aggregation</h2>{_table(metric_df)}
<h2>5. Project-Level Pillar Aggregation</h2>{_table(pillar_df)}
<h2>6. Coverage &amp; Data Quality</h2><div class="grid"><div class="card"><div class="muted">Mean metric coverage</div><div class="big">{coverage_text}</div></div><div class="card"><div class="muted">Reference governance</div><div class="big">{approved}/{len(emu_results)} approved</div></div></div>
<p>Coverage weights are retained per metric and pillar. A project value is not interpreted independently of its <code>n_emus</code>, <code>n_emus_total</code> and <code>coverage_weight</code>.</p>
<h2>7. Deliverables</h2><ul><li>Per-EMU output folders with metric, QA, benchmark, reference governance and Year-0 reports.</li><li><code>project_metric_aggregation.csv</code> and <code>project_pillar_aggregation.csv</code>.</li><li><code>project_assessment_manifest.json</code> containing the normalized EMU model, outputs and aggregation coverage.</li><li>This project-level HTML report.</li></ul>
<footer>Darukaa Adaptive Biodiversity Assessment • Project ID: {html.escape(project_id)} • Package v1.1.0</footer>
</div></body></html>'''
    path = out / report_name
    path.write_text(html_doc, encoding="utf-8")
    return str(path)
