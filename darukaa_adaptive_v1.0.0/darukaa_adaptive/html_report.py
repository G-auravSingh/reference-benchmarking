"""Client-facing HTML report generator.

The report is deterministic from the pipeline result and is intended to be the final
Colab deliverable. It uses a restrained dark editorial visual language inspired by the
supplied Nandoshi eDNA web report: evidence chips, strong typographic hierarchy, compact
metric cards, and an explicit measured/indicated/inferred/unresolved distinction.
"""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Dict, Iterable

import pandas as pd

from .registry import PILLARS, get_indicator_spec
from .scoring import concern_label


CSS = r"""
:root{--bg:#08141a;--panel:#0d1f27;--panel2:#10252e;--line:#24414a;--text:#e9e4d9;--muted:#9aa8ac;--faint:#5d7076;--blue:#7fb3c8;--amber:#d99a3c;--rust:#c05a4a;--green:#6d9d84;--violet:#8f7fa8;--slate:#7b8c8f;--max:1280px;--serif:Georgia,'Times New Roman',serif;--mono:'IBM Plex Mono',ui-monospace,SFMono-Regular,Menlo,monospace}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--text);font-family:var(--serif);font-size:16px;line-height:1.6}a{color:var(--blue)}.wrap{max-width:var(--max);margin:auto;padding:0 34px}.mono{font-family:var(--mono);font-variant-numeric:tabular-nums}.top{position:sticky;top:0;z-index:8;background:rgba(8,20,26,.94);backdrop-filter:blur(12px);border-bottom:1px solid var(--line);padding:13px 0}.topin{display:flex;justify-content:space-between;align-items:center;gap:20px}.brand{font:600 11px var(--mono);letter-spacing:.18em;text-transform:uppercase}.nav{display:flex;gap:20px;flex-wrap:wrap}.nav a{text-decoration:none;color:var(--muted);font:10px var(--mono);text-transform:uppercase;letter-spacing:.11em}.hero{padding:74px 0 60px;border-bottom:1px solid var(--line)}.eyebrow{font:10px var(--mono);letter-spacing:.22em;text-transform:uppercase;color:var(--faint);margin-bottom:18px}.hero h1{font-size:clamp(42px,6vw,78px);line-height:1.02;font-weight:400;max-width:15ch;margin:0 0 22px;letter-spacing:-.03em}.hero p{max-width:70ch;color:var(--muted);font-size:19px}.facts{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:var(--line);margin-top:36px}.fact{background:var(--bg);padding:18px}.fact .k{font:9px var(--mono);text-transform:uppercase;letter-spacing:.14em;color:var(--faint)}.fact .v{font:600 16px var(--mono);margin-top:6px}.section{padding:72px 0;border-bottom:1px solid var(--line)}.section h2{font-size:37px;line-height:1.1;font-weight:400;margin:0 0 12px}.section .lead{color:var(--muted);max-width:75ch;margin-bottom:36px}.grid2{display:grid;grid-template-columns:1.05fr .95fr;gap:34px}.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.grid4{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:var(--line)}.card{background:var(--panel);border:1px solid var(--line);padding:22px}.grid4 .card{border:0}.small{font:10px var(--mono);letter-spacing:.11em;text-transform:uppercase;color:var(--faint)}.big{font:46px var(--mono);font-weight:300;line-height:1.1;margin:8px 0}.muted{color:var(--muted)}.callout{border-left:2px solid var(--blue);background:rgba(127,179,200,.05);padding:20px 22px}.warning{border-left-color:var(--amber);background:rgba(217,154,60,.06)}.pressure{border-left-color:var(--rust);background:rgba(192,90,74,.06)}.evidence{display:inline-flex;align-items:center;gap:7px;font:9px var(--mono);text-transform:uppercase;letter-spacing:.13em;padding:4px 9px;border:1px solid;border-radius:2px;margin-right:7px}.evidence:before{content:'';width:6px;height:6px;border-radius:50%;background:currentColor}.measured{color:var(--blue)}.indicated{color:var(--amber)}.inferred{color:var(--violet)}.unresolved{color:var(--slate)}table{width:100%;border-collapse:collapse;font-size:14px}th,td{padding:11px 10px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left}th{font:9px var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--faint)}.scorebar{height:8px;background:var(--line);overflow:hidden;border-radius:2px}.scorebar i{display:block;height:100%;background:var(--blue)}.pillars{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:var(--line)}.pillar{background:var(--panel);padding:24px}.pillar h3{margin:0 0 7px;font-size:17px}.pillar .score{font:35px var(--mono);font-weight:300}.tag{display:inline-block;padding:4px 8px;border:1px solid var(--line);font:9px var(--mono);letter-spacing:.09em;text-transform:uppercase;color:var(--muted);margin-top:9px}.metric-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:15px}.metric{background:var(--panel);border:1px solid var(--line);padding:20px}.metric-head{display:flex;justify-content:space-between;gap:12px}.metric h4{font-size:18px;margin:0}.metric .raw{font:27px var(--mono);margin:10px 0}.meta{font:10px var(--mono);color:var(--faint);line-height:1.5}.chain{font-family:var(--mono);font-size:12px;color:var(--muted);padding:18px;border:1px dashed var(--line);background:#0a1920}.chain b{color:var(--text)}.waterchart{padding:10px 0}.waterrow{display:grid;grid-template-columns:95px 1fr 88px;gap:12px;align-items:center;margin:8px 0}.watertrack{height:8px;background:var(--line)}.waterfill{height:8px;background:var(--blue)}.waterval{font:10px var(--mono);text-align:right}.footer{padding:52px 0;color:var(--faint);font:10px var(--mono);line-height:1.7}.two-col-list{columns:2;column-gap:44px}.two-col-list li{break-inside:avoid;margin:0 0 9px}.hidden-note{color:var(--faint);font-size:13px}.success{color:var(--green)}.danger{color:var(--rust)}@media(max-width:900px){.facts,.pillars{grid-template-columns:repeat(2,1fr)}.grid2,.grid3,.metric-grid{grid-template-columns:1fr}}@media(max-width:620px){.wrap{padding:0 18px}.facts,.pillars{grid-template-columns:1fr}.nav{display:none}.hero h1{font-size:46px}}
"""


def esc(x: Any) -> str:
    return html.escape("" if x is None else str(x))


def pct(x):
    return "—" if x is None or pd.isna(x) else f"{float(x):.1f}%"


def fmt(x):
    if x is None or pd.isna(x): return "—"
    x=float(x)
    return f"{x:.4f}" if abs(x) < 1 else f"{x:,.2f}"


def evidence_chip(kind):
    k = str(kind or "measured").lower()
    cls = k if k in {"measured","indicated","inferred","unresolved"} else "measured"
    return f'<span class="evidence {cls}">{esc(cls)}</span>'


def score_cell(score):
    label = concern_label(score)
    return f"{pct(score)} <span class='tag'>{esc(label or 'Not scored')}</span>"


def water_section(periods):
    if not periods:
        return '<div class="callout"><b>No monthly water series was generated.</b><div class="muted">Run the aquatic module to populate this section.</div></div>'
    rows=[]
    for r in periods:
        frac=r.get("water_fraction_pct")
        width=max(0,min(100,float(frac))) if frac is not None else 0
        rows.append('<div class="waterrow"><div class="mono">{}</div><div class="watertrack"><div class="waterfill" style="width:{}%"></div></div><div class="waterval">{}%</div></div>'.format(esc(r.get("period_start",""))[:7], f"{width:.2f}", f"{float(frac):.1f}" if frac is not None else "—"))
    return '<div class="waterchart">' + ''.join(rows) + '</div><p class="hidden-note">Water extent is a descriptive hydroperiod indicator. Monthly values should be compared using equivalent seasonal windows and with the detection method shown in the underlying CSV.</p>'


def build_html_report(result: Dict[str, Any], output_path: str | Path | None = None) -> str:
    cfg = result.get("config") or {}
    metrics_df = pd.DataFrame([m.to_dict() if hasattr(m,"to_dict") else m for m in result.get("metrics",[])])
    scored = result.get("metric_concern", pd.DataFrame()); scored = pd.DataFrame(scored)
    pillars = pd.DataFrame(result.get("pillars", pd.DataFrame())); overall=result.get("overall",{}) or {}
    readiness=result.get("readiness",{}) or {}; ref_diag=result.get("reference_diagnostics",{}) or {}
    site_area=result.get("boundary_area_ha"); profile=cfg.get("profile",{}) if isinstance(cfg,dict) else {}
    baseline=(cfg.get("temporal",{}).get("baseline_label") if isinstance(cfg,dict) else None) or "Year-0 baseline"
    site_name=(result.get("parts") or {}).keys(); site_name=next(iter(site_name),"Assessment site")

    scored_n=int(scored.get("score_eligible",pd.Series(dtype=bool)).sum()) if not scored.empty else 0
    usable_n=int((metrics_df.get("status",pd.Series(dtype=str)).isin(["ok","usable"])).sum()) if not metrics_df.empty else 0
    obs=result.get("observations",[])
    edna=result.get("edna",[])
    cond=overall.get("condition_score_0_to_100"); press=overall.get("pressure_score_0_to_100"); son=overall.get("overall_son_score_0_to_100")
    lim_p=overall.get("overall_son_limiting_pillar"); lim_ps=overall.get("overall_son_limiting_pillar_score")
    if son is not None:
        summary_sentence=f"The four-pillar State of Nature score is {float(son):.1f}/100 ({concern_label(son)} concern)."
    elif cond is not None:
        summary_sentence=f"A condition score of {float(cond):.1f}/100 ({concern_label(cond)} concern) is available for C1–C3; a complete four-pillar State of Nature score is not yet available."
    else:
        summary_sentence="The Year-0 evidence record has been generated, but a complete four-pillar State of Nature score is not yet available because one or more pillar references/data streams remain pending."

    ref_site = ref_diag.get("site_ecoregion",{})
    cand = ref_diag.get("aquatic_reference_candidates",[]) or []
    cand_rows = []
    for c in cand:
        cand_rows.append(
            "<tr>"
            f"<td class='mono'>{esc(c.get('hylak_id') or '—')}</td>"
            f"<td class='mono'>{fmt(c.get('area_km2'))}</td>"
            f"<td class='mono'>{fmt(c.get('hmi_mean'))}</td>"
            "</tr>"
        )
    candidate_table = ''.join(cand_rows) or '<tr><td colspan="3">No automatic aquatic reference candidates passed the current screening rules.</td></tr>'

    metric_rows=[]
    if not scored.empty:
        for _, r in scored.iterrows():
            score = r.get("intactness_score_0_100")
            metric_rows.append(
                "<tr>"
                f"<td><b>{esc(r.get("metric"))}</b><br><span class='meta'>{esc(r.get("domain") or "")}</span></td>"
                f"<td class='mono'>{esc(r.get("source_type") or "")}</td>"
                f"<td class='mono'>{fmt(r.get("raw_value"))}</td>"
                f"<td class='mono'>{fmt(r.get("reference_value"))}</td>"
                f"<td>{pct(score)}</td>"
                f"<td>{esc(r.get("concern_label") or "Not scored")}</td>"
                "</tr>"
            )
    metric_table=''.join(metric_rows) or '<tr><td colspan="6">No benchmarked metric records available.</td></tr>'

    pillar_cards=[]
    for _,r in pillars.iterrows() if not pillars.empty else []:
        sc=r.get("score_0_to_100"); lim=r.get("limiting_metric")
        pillar_cards.append('<div class="pillar"><div class="small">{}</div><h3>{}</h3><div class="score">{}</div><div>{}</div><div class="scorebar" style="margin:12px 0 8px"><i style="width:{}%"></i></div><div class="meta">{} scored metrics · limiting indicator: {}</div></div>'.format(
            esc(r.get("pillar")), esc(r.get("pillar_name")), pct(sc), esc(r.get("concern_label") or "Not scored"), float(sc or 0), int(r.get("n_scored_metrics") or 0), esc(lim or "—")
        ))
    if not pillar_cards:
        pillar_cards=['<div class="pillar"><h3>Coverage pending</h3><div class="muted">Pillar results appear here after reference benchmarking.</div></div>']*4

    edna_html=[]
    for e in edna:
        d=e.to_dict() if hasattr(e,"to_dict") else e
        edna_html.append('<div class="card"><div>{}</div><h3 style="margin:9px 0 4px">{}</h3><div class="big">{}</div><div class="meta">{} · {}</div><p class="muted">{}</p>{}</div>'.format(
            evidence_chip(d.get("evidence_class")), esc(d.get("metric")), fmt(d.get("raw_value")), esc(d.get("units")), esc(d.get("temporal_window")), esc(d.get("interpretation") or d.get("notes") or ""),
            ('<div class="callout warning"><b>Validation:</b> '+esc(d.get("validation_required"))+"</div>") if d.get("validation_required") else ""
        ))
    edna_block=''.join(edna_html)
    attachments=result.get("outputs",{}).get("attachments",{}) or {}
    attach_links=''.join([f'<li><a href="{esc(v)}">{esc(k)}</a></li>' for k,v in attachments.items()]) if attachments else '<li>No eDNA HTML/PDF/Krona attachment was supplied in this run.</li>'

    exec_points=[]
    if usable_n: exec_points.append(f"{usable_n} Earth-observation indicator calculations returned usable values.")
    if scored_n: exec_points.append(f"{scored_n} indicators have approved reference benchmarks and entered scoring.")
    if edna: exec_points.append(f"{len(edna)} eDNA evidence records are integrated as a separate evidence stream with conservative evidence grades.")
    if not scored_n: exec_points.append("No indicator is presented as scored until the automatic reference engine confirms an adequate reference population and uncertainty stability.")
    if lim_p: exec_points.append(f"The current limiting four-pillar component is {lim_p} at {pct(lim_ps)}.")

    recommendation_items=[]
    if not scored.empty:
        eligible = scored[scored.get("score_eligible", pd.Series(dtype=bool)) == True].copy()
        if not eligible.empty:
            eligible["_score"] = pd.to_numeric(eligible["intactness_score_0_100"], errors="coerce")
            for _, r in eligible.dropna(subset=["_score"]).sort_values("_score").head(5).iterrows():
                try:
                    spec = get_indicator_spec(str(r.get("metric")))
                    action = spec.management_use
                except Exception:
                    action = str(r.get("notes") or "Review the indicator and maintain its measurement protocol.")
                recommendation_items.append(f"<li><b>{esc(r.get('metric'))}</b> ({pct(r.get('_score'))}): {esc(action)}</li>")
    for e in edna:
        d=e.to_dict() if hasattr(e,"to_dict") else e
        if d.get("validation_required"):
            recommendation_items.append(f"<li><b>{esc(d.get('metric'))}</b> eDNA validation: {esc(d.get('validation_required'))}</li>")
    if not recommendation_items:
        recommendation_items = [
            "<li>Retain the Year-0 spatial and temporal definitions for reproducibility.</li>",
            "<li>Populate additional comparable field, acoustic and molecular observations as they become available.</li>",
            "<li>Use subsequent monitoring cycles to test change against Year-0 with uncertainty and consistent effort.</li>",
        ]

    html_doc = "<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>"+esc(site_name)+" — Year-0 Biodiversity Baseline</title><style>"+CSS+"</style></head><body>"
    html_doc += "<div class='top'><div class='wrap topin'><div class='brand'>DARUKAA · BIODIVERSITY BASELINE</div><div class='nav'><a href='#summary'>Summary</a><a href='#method'>Method</a><a href='#pillars'>Pillars</a><a href='#metrics'>Indicators</a><a href='#edna'>eDNA</a><a href='#appendix'>Appendix</a></div></div></div>"
    html_doc += "<header class='hero'><div class='wrap'><div class='eyebrow'>Year-0 assessment · " + esc(profile.get("version","1.2.0")) + "</div><h1>"+esc(site_name)+"</h1><p>Integrated biodiversity baseline for aquatic and terrestrial ecological domains, combining Earth observation with structured field, acoustic and environmental-DNA evidence as those inputs become available.</p><div class='facts'><div class='fact'><div class='k'>Baseline</div><div class='v'>"+esc(baseline)+"</div></div><div class='fact'><div class='k'>Boundary area</div><div class='v'>"+fmt(site_area)+" ha</div></div><div class='fact'><div class='k'>Usable indicators</div><div class='v'>"+str(usable_n)+"</div></div><div class='fact'><div class='k'>Scored indicators</div><div class='v'>"+str(scored_n)+"</div></div></div></div></header>"
    html_doc += "<main>"
    html_doc += "<section id='summary' class='section'><div class='wrap'><h2>Executive summary</h2><p class='lead'>"+esc(summary_sentence)+" The report separates measurement, reference benchmarking and ecological interpretation so that a valid observation is not mistaken for a validated score.</p><div class='grid3'>"
    for title,value,sub,cls in [("Overall State of Nature",pct(son),overall.get("overall_son_concern") or "Four-pillar score pending",""),("Overall condition",pct(cond),overall.get("condition_concern") or "C1–C3 coverage pending",""),("Pressure axis",pct(press),overall.get("pressure_concern") or "C4 coverage pending","pressure")]:
        html_doc += f"<div class='card {'pressure' if cls else ''}'><div class='small'>{esc(title)}</div><div class='big'>{value}</div><div>{esc(sub)}</div></div>"
    html_doc += "</div><div class='callout' style='margin-top:24px'><b>Key assessment points</b><ul class='two-col-list'>"+''.join("<li>"+esc(x)+"</li>" for x in exec_points)+"</ul></div></div></section>"

    html_doc += "<section id='method' class='section'><div class='wrap'><h2>Assessment architecture & methodology</h2><p class='lead'>The framework is profile-driven: the same benchmark and scoring engine can accept terrestrial, aquatic, field, acoustic and eDNA evidence. The supplied site boundary is the master spatial frame; ecological subdomains are derived deterministically.</p><div class='grid4'>"
    steps=[("01","Boundary","Master KML/KMZ is ingested, validated and retained as the project boundary."),("02","Domains","Dynamic water, littoral, fixed riparian and broader terrestrial-context domains are derived automatically."),("03","Reference","References are constructed automatically from comparable least-modified regional strata; no reference KML is required."),("04","Scoring","Raw value → reference comparison → 0–100 intactness → concern → pillar geometric mean → four-pillar SoN." )]
    for n,t,d in steps: html_doc += f"<div class='card'><div class='small'>{n}</div><h3>{esc(t)}</h3><p class='muted'>{esc(d)}</p></div>"
    html_doc += "</div><div class='callout' style='margin-top:24px'><b>Declared concern convention</b><br><span class='mono'>80–100 Very Low · 60–&lt;80 Low · 40–&lt;60 Moderate · 20–&lt;40 High · 0–&lt;20 Very High</span><p class='muted' style='margin:9px 0 0'>These equal-width bands are a Darukaa product convention on the normalized scale, not universal ecological thresholds.</p></div></div></section>"

    html_doc += "<section class='section'><div class='wrap'><h2>Reference framework</h2><p class='lead'>The standard workflow does not require client-supplied reference geometry. The engine first characterizes the site, then constructs an automatic reference population appropriate to the indicator's realm and measurement scale.</p><div class='grid2'><div class='card'><div class='small'>Site ecological context</div><div class='big'>"+esc(ref_site.get("eco_name") or "Unresolved")+"</div><div class='muted'>ECO_ID: "+esc(ref_site.get("eco_id"))+" · Biome: "+esc(ref_site.get("biome_name"))+" · Realm: "+esc(ref_site.get("realm"))+"<br>Dominant terrestrial stratum: "+esc(ref_site.get("dominant_terrestrial_landcover_label") or "Not resolved")+"</div></div><div class='card'><div class='small'>Automatic aquatic reference pool</div><div class='big'>"+str(len(cand))+" candidates</div><div class='muted'>Comparable waterbodies are screened using ecoregion, approximate area similarity, spatial exclusion and near-shore human-modification context. Candidate selection is not itself a score.</div></div></div><div class='card' style='margin-top:18px;overflow:auto'><table><thead><tr><th>HydroLAKES ID</th><th>Area (km²)</th><th>Near-shore HMI mean</th></tr></thead><tbody>"+candidate_table+"</tbody></table></div><div class='callout warning' style='margin-top:18px'><b>Reference acceptance:</b> an indicator is benchmarked only when its reference population passes the minimum sample-size, estimator-validity and uncertainty-stability checks. The selected reference median, uncertainty and percentiles are retained in the benchmark scorecard.</div></div></section>"

    html_doc += "<section class='section'><div class='wrap'><h2>What the indicators mean</h2><p class='lead'>Each indicator keeps its ecological question and management use alongside the numerical result. Proxy indicators are labelled as proxies rather than presented as direct field measurements.</p><div class='metric-grid'>"
    definition_rows = scored if not scored.empty else metrics_df
    definition_cards=[]
    for _, r in definition_rows.iterrows() if not definition_rows.empty else []:
        name = str(r.get('metric') or '')
        try:
            spec = get_indicator_spec(name)
            question = spec.ecological_question
            use = spec.management_use
        except Exception:
            question = r.get('notes') or 'Definition supplied in the observation metadata.'
            use = 'Use according to the registered metric definition.'
        definition_cards.append(f"<div class='metric'><div class='metric-head'><h4>{esc(name)}</h4><span class='tag'>{esc(r.get('pillar') or '')}</span></div><p class='muted' style='margin:12px 0 8px'>{esc(question)}</p><div class='meta'>Management use</div><p class='muted' style='margin:5px 0 0'>{esc(use)}</p></div>")
    html_doc += ''.join(definition_cards) if definition_cards else "<div class='callout'>Indicator definitions will populate when metrics or external observations are supplied.</div>"
    html_doc += "</div></div></section>"

    html_doc += "<section id='pillars' class='section'><div class='wrap'><h2>Pillar results</h2><p class='lead'>Continuous normalized scores are aggregated first. Concern labels are assigned only after aggregation. The limiting indicator is shown for traceability.</p><div class='pillars'>"+''.join(pillar_cards)+"</div></div></section>"

    html_doc += "<section id='metrics' class='section'><div class='wrap'><h2>Indicator scorecard</h2><p class='lead'>Every calculated indicator retains its native value, source, reference comparison, normalized score and scoring eligibility.</p><div class='card'><div style='overflow:auto'><table><thead><tr><th>Indicator</th><th>Source</th><th>Raw value</th><th>Reference</th><th>Intactness</th><th>Concern</th></tr></thead><tbody>"+metric_table+"</tbody></table></div></div></div></section>"

    html_doc += "<section class='section'><div class='wrap'><h2>Seasonal water dynamics</h2><p class='lead'>The dynamic-water record is retained as a time series rather than collapsing seasonal hydrology into a single month. Detection method is preserved in the CSV output.</p><div class='card'>"+water_section(result.get("water_periods",[]))+"</div></div></section>"

    edna_lead = (
        "eDNA is integrated as a distinct evidence layer. When a structured eDNA table is supplied, "
        "the records retain their evidence class and can enter the shared scorer only when an appropriate "
        "matched reference is explicitly approved. Source PDF/HTML/Krona artefacts remain linked in the report."
    )
    if edna:
        edna_lead += " The evidence record is not treated as a live census: taxonomic assignments are interpreted according to the sampling and bioinformatics method supplied by the project."
    html_doc += "<section id='edna' class='section'><div class='wrap'><h2>Environmental DNA / metagenomic evidence</h2><p class='lead'>" + esc(edna_lead) + "</p>"
    if edna_block:
        html_doc += "<div class='grid3'>"+edna_block+"</div>"
    else:
        html_doc += "<div class='callout'><b>No structured eDNA CSV was supplied to the pipeline run.</b><div class='muted'>The notebook supports later integration of the structured eDNA evidence table while preserving the source PDF/HTML/Krona artefacts as linked evidence.</div></div>"
    html_doc += "<div class='callout warning' style='margin-top:22px'><b>Evidence discipline.</b> eDNA detections can indicate recent biological material or environmental signals, but do not by themselves prove that a detected organism was alive, locally established or active at sampling. Cyanobacterial, human-associated and oxygen-limitation signals should be confirmed with targeted chemistry, microscopy, qPCR/source-tracking or direct dissolved oxygen measurements where appropriate.</div>"
    html_doc += "<div class='card' style='margin-top:18px'><div class='small'>Source artefacts</div><ul>"+attach_links+"</ul></div></div></section>"

    limiting_metric = overall.get("overall_son_limiting_metric") or (
        overall.get("condition_limiting_pillar") and next((r.get("limiting_metric") for r in (result.get("pillars") if isinstance(result.get("pillars"), list) else []) if r.get("pillar") == overall.get("condition_limiting_pillar")), None)
    )
    chain_metric = limiting_metric or "metric-level driver"
    html_doc += "<section class='section'><div class='wrap'><h2>Interpretation & management use</h2><p class='lead'>Interpretation is tied to the evidence basis of each metric. EO proxies can support spatial/temporal screening; field and acoustic metrics require comparable effort; eDNA signals require matched sampling protocols and targeted confirmation before they are treated as direct ecological measurements.</p><div class='grid2'><div class='card'><div class='small'>Limiting-chain logic</div><div class='chain'><b>"+esc(overall.get("overall_son_limiting_pillar") or overall.get("condition_limiting_pillar") or "Not available")+"</b> <span>→</span> <b>"+esc(chain_metric)+"</b></div><p class='muted'>The geometric mean is the published aggregate. The limiting component/metric is an explanatory diagnostic and is never a second competing score.</p></div><div class='card'><div class='small'>Recommendations</div><ul>"+''.join(recommendation_items)+"</ul></div></div></div></section>"

    readiness_json = esc(json.dumps(readiness, indent=2, default=str)) if readiness else "No readiness diagnostics were generated."
    html_doc += "<section class='section'><div class='wrap'><h2>Assessment readiness & data gaps</h2><p class='lead'>Readiness separates what was measured from what is benchmark-ready. Missing reference evidence, incomplete pillar coverage and contextual-only indicators remain visible rather than being converted into unsupported scores.</p><div class='grid2'><div class='card'><div class='small'>Current readiness status</div><div class='big'>"+esc(readiness.get('overall_status') or '—')+"</div><div class='muted'>Approved benchmarks: "+str((readiness.get('references') or {}).get('approved_benchmarks',0))+" · usable EO metrics: "+str((readiness.get('metrics') or {}).get('usable',0))+" · scored metrics: "+str((readiness.get('metrics') or {}).get('scored',0))+"</div></div><div class='card'><div class='small'>Diagnostics</div><pre class='mono' style='white-space:pre-wrap;color:var(--muted);font-size:11px;max-height:260px;overflow:auto'>"+readiness_json+"</pre></div></div></div></section>"

    html_doc += "<section id='appendix' class='section'><div class='wrap'><h2>Technical appendix</h2><div class='grid2'><div class='card'><div class='small'>Data and QA</div><ul><li>Usable EO metrics: "+str(usable_n)+"</li><li>Scored metrics: "+str(scored_n)+"</li><li>External records: "+str(len(obs))+"</li><li>eDNA records: "+str(len(edna))+"</li></ul></div><div class='card'><div class='small'>Reproducibility</div><pre class='mono' style='white-space:pre-wrap;color:var(--muted);font-size:11px'>"+esc(json.dumps({"profile":profile,"baseline":baseline,"reference_strategy":((cfg.get("reference") or {}).get("strategy") if isinstance(cfg,dict) else None)},indent=2)) + "</pre></div></div></div></section>"
    html_doc += "</main><footer class='footer'><div class='wrap'>Generated by the Darukaa adaptive biodiversity baseline engine · score bands are declared product conventions · scores are decision-support summaries, not direct measurements of biodiversity · read the profile and evidence basis before interpreting the roll-up.</div></footer></body></html>"

    if output_path is not None:
        p=Path(output_path); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(html_doc, encoding="utf-8")
    return html_doc
