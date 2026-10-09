"""Auditable outputs plus a self-contained professional Year-0 HTML report."""
from __future__ import annotations
import hashlib, html, json, platform, subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import pandas as pd
from .benchmark import benchmark_dataframe
from .registry import indicator_table


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
    cond=overall.get("condition_score_0_to_100"); press=overall.get("pressure_intactness_score_0_to_100", overall.get("pressure_score_0_to_100"))
    title=config.profile.name.replace('_',' ').title()
    gaps=[]
    c3_scored = False
    if not scored_df.empty and "pillar" in scored_df.columns and "score_eligible" in scored_df.columns:
        c3_scored = bool(scored_df.loc[scored_df["pillar"].eq("P3_biodiversity_integrity"), "score_eligible"].fillna(False).any())
    if not c3_scored:
        gaps.append("Fauna evidence (field/acoustic/eDNA) is not currently score-eligible; P3 Biodiversity Integrity cannot be treated as a completed condition pillar.")
    if overall.get("status") == "condition_scored_partial":
        gaps.append(f"Overall condition is a partial State of Nature assessment based on {overall.get('condition_pillar_count', len(overall.get('condition_pillars', [])))}/3 condition pillars. Missing pillars are excluded, not assigned zero; P3 Biodiversity Integrity is the key evidence gap when absent.")
    elif overall.get("status") == "insufficient_fauna_coverage":
        gaps.append("Overall condition scoring is gated because the configured profile requires a scored P3 Biodiversity Integrity pillar.")
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
<h2>2. Assessment Architecture</h2><p><b>Project boundary → ecological domains → multi-source indicators → automatic reference population → reference comparison → reference attainment (0–100) → P1/P2/P3 condition + P4 pressure → transparent management interpretation.</b></p>
<h2>3. Reference Framework</h2><p>The default workflow constructs an ecologically matched reference candidate automatically. The candidate is screened by ecosystem comparability, pressure, temporal compatibility and population quality before it can be approved for scoring. The production workflow does not use manual reference files. If both automatic stages fail, an analyst may enter a single manual HMI threshold in Colab after reviewing the reference diagnostics. The reference state, method, QA diagnostics and approval basis are retained in the assessment manifest.</p>{_table(benchmark_df[[c for c in ["metric","selected_reference","selected_reference_level","reference_n","reference_uncertainty","relative_departure_pct","reference_attainment_0_100","reference_method","reference_state","reference_approval_basis","benchmark_status","reference_approved_for_scoring"] if c in benchmark_df.columns]])}
<h2>4. Indicator Results</h2>{_table(metric_display)}
<h2>5. Pillar Results</h2>{pillar_html}<div style="margin-top:18px">P1 Ecosystem Extent & Configuration, P2 Ecosystem Condition and P3 Biodiversity Integrity are condition components. P4 Anthropogenic Pressure is reported separately.</div>
<h2>6. State of Nature</h2><div class="grid"><div class="card"><div class="muted">Overall condition</div><div class="big">{('%.1f / 100' % cond) if cond is not None else 'Not scoreable'}</div><div>{html.escape(str(overall.get('condition_concern_label') or ''))}</div></div><div class="card"><div class="muted">Pressure intactness</div><div class="big">{('%.1f / 100' % press) if press is not None else 'Not scoreable'}</div><div>{html.escape(str(overall.get('pressure_concern_label') or ''))}</div><div class="muted">Higher = lower pressure / better condition</div></div><div class="card"><div class="muted">Limiting condition component</div><div class="big" style="font-size:20px">{html.escape(str(overall.get('limiting_pillar') or 'Pending'))}</div><div>{html.escape(str(overall.get('limiting_metric') or ''))}</div></div></div>
<h2>7. Spatial & Temporal Results</h2>{_table(water_df)}
<h2>8. Multi-source Evidence & eDNA</h2><p>eDNA is an optional evidence stream. When supplied as validated observations, eDNA metrics use the same raw value → reference → intactness → pillar pathway as other evidence. Modelled eDNA-persistence proxies are retained as contextual unless a defensible reference and validation pathway are supplied.</p>{_table(evidence_df)}
<h2>9. Interpretation & Management Use</h2><p>Interpretations should be tied to the indicator definition, reference comparison, spatial domain and uncertainty. Proxy indicators such as spectral bloom/turbidity signals should not be relabelled as laboratory water-quality measurements without independent validation. Management actions should therefore be linked to the specific limiting indicator and a measurable next-cycle monitoring variable.</p>
<h2>10. Data Gaps & Next-Cycle Improvements</h2>{''.join('<div class="notice">'+html.escape(g)+'</div>' for g in gaps) if gaps else '<div class="good">Current evidence and reference diagnostics are represented in the scorecard.</div>'}
<h2>11. Technical Appendix</h2><p><b>Indicator registry:</b> {len(indicator_table(config))} active/current registry entries. <b>Evidence model:</b> EO, field, acoustic, eDNA and modelled evidence share one downstream scoring contract. <b>QA/QC:</b> structural metric QA and provenance are exported separately from ecological interpretation.</p><pre>{html.escape(json.dumps(readiness,indent=2,default=str))}</pre>
<footer>Darukaa Adaptive Biodiversity Assessment Framework v{html.escape(config.profile.version)} • This report is generated from the assessment outputs and configuration; it is not a substitute for field/laboratory validation where required.</footer></div></body></html>'''
    path=out/'Year0_Biodiversity_Baseline_Report.html'; path.write_text(html_doc,encoding='utf-8'); return path



def write_project_report(out, project, project_overall, pillar_agg, metric_agg, comparison, emu_results, config, project_output_qa=None):
    'Write a client-facing project report with explicit coverage and QA limitations.'
    from .aggregation import summarize_emu_condition_distribution
    out=Path(out)
    cond=project_overall.get("condition_score_0_to_100")
    press=project_overall.get("pressure_intactness_score_0_to_100", project_overall.get("pressure_score_0_to_100"))
    pillar_html=_table(pillar_agg) if pillar_agg is not None and not pillar_agg.empty else '<div class="empty">No project-level pillar score is currently defensible.</div>'
    metric_html=_table(metric_agg) if metric_agg is not None and not metric_agg.empty else '<div class="empty">No project-level metric score is currently defensible.</div>'
    comp_html=_table(comparison) if comparison is not None and not comparison.empty else '<div class="empty">No EMU comparison table available.</div>'
    distribution=summarize_emu_condition_distribution(comparison)
    distribution.to_csv(out/'emu_condition_concern_distribution.csv', index=False)
    distribution_html=_table(distribution) if not distribution.empty else '<div class="empty">EMU condition concern distribution is unavailable.</div>'
    total_area=float(pd.to_numeric(comparison['area_ha'],errors='coerce').fillna(0).clip(lower=0).sum()) if comparison is not None and not comparison.empty and 'area_ha' in comparison else sum(float(r.get('emu_area_ha') or 0) for r in emu_results)
    generated=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    emu_index=[]
    comp_lookup = {str(row.get("emu_id")): row for _, row in comparison.iterrows()} if comparison is not None and not comparison.empty else {}
    for r in emu_results:
        cr = comp_lookup.get(str(r.get("emu_id")), {})
        emu_index.append({"emu_id":r.get("emu_id"),"domain":r.get("emu_domain"),"area_ha":r.get("emu_area_ha"),
                          "condition_score_0_to_100":cr.get("condition_score_0_to_100"),
                          "condition_concern":cr.get("condition_concern_label"),
                          "condition_coverage":cr.get("condition_coverage_status", "not available"),
                          "limiting_metric":cr.get("limiting_metric"),
                          "reference_populations":", ".join(sorted((r.get("reference_populations") or {}).keys())) or "None generated",
                          "output_directory":str(r.get("outputs") or "Not recorded")})
    emu_index_df=pd.DataFrame(emu_index)
    emu_index_html=_table(emu_index_df) if emu_index else '<div class="empty">No completed EMU records.</div>'
    domain_summary=(emu_index_df.groupby("domain",dropna=False).agg(n_emus=("emu_id","count"),area_ha=("area_ha","sum")).reset_index() if not emu_index_df.empty else pd.DataFrame())
    domain_html=_table(domain_summary) if not domain_summary.empty else '<div class="empty">Domain coverage unavailable.</div>'
    baseline_start=getattr(config.temporal,"baseline_start_date",None)
    baseline_end=getattr(config.temporal,"baseline_end_date",None)
    historical_start=getattr(config.temporal,"start_year",None)
    historical_end=getattr(config.temporal,"end_year",None)
    qa=project_output_qa or {"status":"not_run","flags":[]}
    qa_rows=qa.get("flags",[])
    qa_html=_table(pd.DataFrame(qa_rows)) if qa_rows else '<div class="good">No automated output-QA flags were raised. This does not replace analyst review.</div>'
    gaps=[]
    if project_overall.get("status") == "condition_scored_partial":
        gaps.append(f"Project condition is a partial State of Nature assessment based on {project_overall.get('condition_pillar_count', len(project_overall.get('condition_pillars', [])))}/3 condition pillars. Missing pillars are excluded, not assigned zero.")
    elif cond is None:
        gaps.append("A project-level condition score was not generated because no condition pillar was score-eligible.")
    if press is None:
        gaps.append("A project-level pressure score was not generated because pressure evidence was not score-eligible.")
    html_doc=f'''<!doctype html><html><head><meta charset="utf-8"><title>Project Biodiversity Baseline — {html.escape(project.project_name)}</title>
<style>body{{font-family:Inter,Arial,sans-serif;margin:0;background:#f4f6f8;color:#17202a}}.wrap{{max-width:1220px;margin:auto;padding:28px}}.hero{{background:#13202b;color:white;padding:42px;border-radius:18px;margin-bottom:22px}}h1{{font-size:34px;margin:0 0 8px}}h2{{margin-top:34px;border-bottom:1px solid #d8dee4;padding-bottom:8px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px}}.card{{background:white;border:1px solid #e0e5ea;border-radius:12px;padding:18px}}.big{{font-size:30px;font-weight:700}}.muted{{color:#65727e}}.data{{width:100%;border-collapse:collapse;background:white;font-size:13px}}.data th,.data td{{padding:8px;border-bottom:1px solid #e6eaee;text-align:left;vertical-align:top}}.data th{{background:#eef2f5}}.notice{{background:#fff8e6;border-left:4px solid #c58a18;padding:12px 15px;margin:12px 0}}.good{{background:#edf7f0;border-left:4px solid #3f7d54;padding:12px 15px}}.empty{{padding:18px;background:#fff;border:1px dashed #b8c1ca;color:#697681}}footer{{margin-top:40px;color:#697681;font-size:12px}}code{{background:#eef2f5;padding:2px 4px;border-radius:4px}}@media print{{body{{background:white}}.wrap{{max-width:none;padding:0}}.hero{{border-radius:0;print-color-adjust:exact}}h2{{break-after:avoid}}table{{break-inside:auto}}tr{{break-inside:avoid}}}}</style></head><body><div class="wrap">
<div class="hero"><h1>Project Biodiversity Baseline</h1><div>{html.escape(project.project_name)}</div><div style="color:#cbd4da;margin-top:12px">{len(emu_results)} EMUs • Framework v{html.escape(config.profile.version)} • Generated {generated}</div></div>
<div class="grid"><div class="card"><div class="muted">Summed EMU area</div><div class="big">{total_area:.2f} ha</div></div><div class="card"><div class="muted">EMUs assessed</div><div class="big">{len(emu_results)}</div></div><div class="card"><div class="muted">Project condition</div><div class="big">{('%.1f / 100' % cond) if cond is not None else 'Pending'}</div><div>{html.escape(str(project_overall.get('condition_concern_label') or ''))}</div><div class="muted">{html.escape(str(project_overall.get('condition_coverage') or 'not assessed'))} coverage</div></div><div class="card"><div class="muted">Pressure intactness</div><div class="big">{('%.1f / 100' % press) if press is not None else 'Pending'}</div><div>{html.escape(str(project_overall.get('pressure_concern_label') or ''))}</div><div class="muted">Higher = lower pressure / better condition</div></div><div class="card"><div class="muted">Limiting pillar</div><div class="big" style="font-size:20px">{html.escape(str(project_overall.get('limiting_pillar') or 'Pending'))}</div><div>Limiting EMU: {html.escape(str(project_overall.get('limiting_emu') or '—'))}</div></div></div>
<h2>1. Executive Summary</h2><p>The project is assessed as a set of ecological management units (EMUs). Each EMU is independently characterized, benchmarked against an ecologically appropriate reference population where defensible, and scored only when evidence and reference QA permit. Project-level values summarize the EMU results; the EMU comparison table is retained so spatial ecological differences are not hidden by the project headline. Condition represents ecosystem condition; anthropogenic pressure is reported separately and must not be interpreted as the inverse of biodiversity condition.</p>
<div class="notice"><b>Aggregation limitation:</b> area shares use the sum of EMU areas as denominator and assume EMUs do not overlap. Where EMUs overlap, partition them or use a validated non-overlapping area basis before interpreting area shares. Area-weighted means do not replace the EMU-level distribution.</div>
<h2>2. Assessment Overview &amp; Domain Coverage</h2><div class="grid"><div class="card"><b>Profile</b><br>{html.escape(str(config.profile.name))}</div><div class="card"><b>Baseline window</b><br>{html.escape(str(baseline_start or 'Not specified'))} to {html.escape(str(baseline_end or 'Not specified'))}</div><div class="card"><b>Historical context</b><br>{html.escape(str(historical_start or 'Not specified'))}–{html.escape(str(historical_end or 'Not specified'))}</div><div class="card"><b>Condition coverage</b><br>{html.escape(str(project_overall.get('condition_pillar_count', 0)))} of 3 pillars available at project level</div></div>{domain_html}
<h2>3. Project-level Pillars</h2>{pillar_html}
<h2>4. Project-level Metric Summary</h2>{metric_html}
<h2>5. EMU Condition Concern Distribution</h2><p>Existing score concern bands are used without introducing new thresholds. An overall EMU condition band is assigned only when P1, P2 and P3 are all scored for that EMU. EMUs with partial or insufficient condition evidence are counted and their area retained separately rather than assigned a synthetic band. This distribution is a condition summary, not a standalone risk score.</p>{distribution_html}
<h2>6. EMU Ecological Comparison</h2>{comp_html}
<h2>7. Interpretation &amp; Management Priorities</h2><p><b>Project condition is not a substitute for spatial diagnosis.</b> Review the weakest pillar, limiting metric and EMUs with the lowest condition scores. Keep pressure indicators separate from condition, and distinguish low ecological condition from exposure to anthropogenic pressure. Priorities should be linked to metric definitions, reference quality, spatial domain, confidence and a measurable next-cycle monitoring variable. EMUs with different ecological domains are not forced into a shared reference population.</p>
<h2>8. Evidence Gaps</h2>{''.join('<div class="notice">'+html.escape(x)+'</div>' for x in gaps) if gaps else '<div class="good">No project-level condition/pressure gap was detected by the current score gates; inspect detailed QA and reference outputs before release.</div>'}
<h2>9. Automated Output QA</h2><p>These are review flags, not automatic corrections. A PASS means only that no currently configured review flag was triggered; it is not a certification of ecological validity.</p><p><b>QA status:</b> {html.escape(str(qa.get('status','not_run')))}</p>{qa_html}
<h2>10. EMU Output &amp; Reference Index</h2>{emu_index_html}
<h2>11. Assessment Traceability &amp; Deliverables</h2><p>The project manifest retains each EMU output directory, input routing, reference population diagnostics, metric-level benchmark records, score eligibility, project aggregation and configuration. Review each EMU folder for raw metric measurements, metric QA/QC, reference governance, benchmark scorecard, metric concern scorecard, pillar and overall scorecards, readiness diagnostics and the Year-0 HTML report where applicable.</p><ul><li><code>project_assessment_manifest.json</code> — project identity, EMU inventory and aggregation trace.</li><li><code>project_overall_scorecard.json</code> — project condition/pressure headline and coverage status.</li><li><code>project_metric_raw_aggregation.csv</code> and <code>project_metric_score_aggregation.csv</code> — raw and scored summaries with coverage/distribution statistics.</li><li><code>project_pillar_aggregation.csv</code> — project pillar summaries and limiting EMUs.</li><li><code>emu_ecological_comparison.csv</code> — EMU-level pillar, condition and limiting-indicator comparison.</li><li><code>emu_condition_concern_distribution.csv</code> — concern-band counts and area shares including partial/unscored categories.</li><li><code>project_output_qa.json</code> — automated post-run review flags.</li></ul>
<footer>Darukaa Adaptive Biodiversity Assessment Framework v{html.escape(config.profile.version)} • Generated {generated} • Project aggregation does not replace field/laboratory validation where required.</footer></div></body></html>'''
    path=out/'Project_Biodiversity_Baseline_Report.html'
    path.write_text(html_doc,encoding='utf-8')
    return path

def audit_project_output_bundle(output_dir, comparison, expected_emu_count):
    """Validate report deliverables and reconcile EMU concern distribution totals."""
    out = Path(output_dir)
    flags = []
    required = [
        "project_assessment_manifest.json", "project_overall_scorecard.json",
        "project_pillar_aggregation.csv", "project_metric_raw_aggregation.csv",
        "project_metric_score_aggregation.csv", "emu_ecological_comparison.csv",
        "emu_condition_concern_distribution.csv", "project_output_qa.json",
        "Project_Biodiversity_Baseline_Report.html",
    ]
    missing = [name for name in required if not (out / name).exists()]
    if missing:
        flags.append({"severity":"REVIEW", "code":"required_output_missing", "message":"Required project deliverables are missing.", "files":missing})
    report_path = out / "Project_Biodiversity_Baseline_Report.html"
    if report_path.exists():
        report = report_path.read_text(encoding="utf-8")
        required_sections = [
            "Executive Summary", "Assessment Overview &amp; Domain Coverage", "Project-level Pillars",
            "Project-level Metric Summary", "EMU Condition Concern Distribution", "EMU Ecological Comparison",
            "Interpretation &amp; Management Priorities", "Evidence Gaps", "Automated Output QA",
            "EMU Output &amp; Reference Index", "Assessment Traceability &amp; Deliverables",
        ]
        absent = [section for section in required_sections if section not in report]
        if absent:
            flags.append({"severity":"REVIEW", "code":"report_section_missing", "message":"Project report failed required-section checks.", "sections":absent})
    if comparison is not None and not comparison.empty:
        dist_path = out / "emu_condition_concern_distribution.csv"
        if dist_path.exists():
            try:
                dist = pd.read_csv(dist_path)
                observed_n = int(pd.to_numeric(dist["n_emus"], errors="coerce").fillna(0).sum())
                if observed_n != int(expected_emu_count):
                    flags.append({"severity":"REVIEW", "code":"condition_distribution_count_mismatch", "message":f"Concern distribution counts sum to {observed_n}; expected {int(expected_emu_count)} EMUs."})
                expected_area = float(pd.to_numeric(comparison["area_ha"], errors="coerce").fillna(0).clip(lower=0).sum())
                observed_area = float(pd.to_numeric(dist["area_ha"], errors="coerce").fillna(0).sum())
                if abs(observed_area - expected_area) > max(1e-6, expected_area * 1e-6):
                    flags.append({"severity":"REVIEW", "code":"condition_distribution_area_mismatch", "message":f"Concern distribution area sums to {observed_area}; expected {expected_area} ha from EMU comparison."})
                if expected_area > 0 and "area_share_pct" in dist.columns:
                    share_total = float(pd.to_numeric(dist["area_share_pct"], errors="coerce").fillna(0).sum())
                    if abs(share_total - 100.0) > 1e-4:
                        flags.append({"severity":"REVIEW", "code":"condition_distribution_share_mismatch", "message":f"Concern distribution area shares sum to {share_total}%, expected 100%."})
            except Exception as exc:
                flags.append({"severity":"REVIEW", "code":"condition_distribution_unreadable", "message":f"Could not validate concern distribution: {exc}"})
    return flags


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
    pd.DataFrame(indicator_table(config)).to_csv(out/'indicator_registry.csv',index=False)
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
