"""
Evidence-Graded HTML Report (CS-10)
===================================

Deterministic projection of the report dict (ReportGenerator.generate output) into a
standalone, self-contained HTML "Evidence Record", modelled on the Nandoshi Year-0
reference report. The report is GENERATED from the registry + results, not hand-built:

    - every claim carries its EVIDENCE GRADE (baseline / contextual / screening / pending);
    - SCORED, CONTEXTUAL, SCREENING-ONLY, PENDING and REMOVED indicators are shown
      separately and honestly (nothing hidden);
    - the profile-first output leads: per-component limiting factor, the condition x
      pressure matrix, then the roll-up (secondary) with its stability flag and the
      mandatory framing block;
    - the signed, uncapped benchmark is shown, never the capped ratio.

No external dependencies; returns an HTML string and optionally writes it.
"""
from __future__ import annotations

import html
from pathlib import Path
from typing import Dict

# Evidence-tier badge colours (declared display choice [X]).
_TIER_COLOR = {
    "baseline": ("#1b5e3f", "#e6f4ec"),
    "monitoring": ("#0d47a1", "#e3f0fb"),
    "contextual": ("#7a5c00", "#fbf3d5"),
    "screening": ("#8a2b2b", "#f7e3e3"),
    "pending": ("#555", "#ececec"),
    "removed": ("#000", "#ddd"),
}
_MATRIX_LABEL = {
    "protect_maintain": ("Protect / maintain", "#1b5e3f"),
    "defend_abate_threat": ("Defend — abate threat", "#8a2b2b"),
    "restore": ("Restore", "#7a5c00"),
    "stabilise_then_restore": ("Stabilise, then restore", "#5a2a82"),
    "insufficient_data": ("Insufficient data", "#555"),
}


def _esc(x) -> str:
    return html.escape(str(x)) if x is not None else "—"


def _badge(tier: str) -> str:
    fg, bg = _TIER_COLOR.get(tier, ("#333", "#eee"))
    return (f'<span style="background:{bg};color:{fg};padding:1px 7px;border-radius:10px;'
            f'font-size:11px;font-weight:600;white-space:nowrap">{_esc(tier)}</span>')


def _pct(x) -> str:
    return "—" if x is None else f"{x:.0f}%"


def _num(x, d=3) -> str:
    return "—" if x is None else f"{x:.{d}f}"


def _render_classification(cls: Dict) -> str:
    """Render the dual-mode classification cell: reference-relative always; the
    literature-anchored view alongside it, titled with its source, only where it
    exists — never one silently replacing the other."""
    if not cls or not cls.get("reference_relative"):
        return "—"
    rr = cls["reference_relative"]
    out = f"{_esc(rr.get('class'))} <span class='muted'>(ref.)</span>"
    la = cls.get("literature_anchored")
    if la:
        out += (f"<br><span class='muted' title=\"{_esc(la.get('basis',''))}\">"
               f"{_esc(la.get('class'))} (literature)</span>")
    return out


def render_html(report: Dict, project_name: str = "Darukaa Assessment") -> str:
    meta = report.get("meta", {})
    status = report.get("indicator_status", {})
    profiles = report.get("site_profiles", {})
    rows = report.get("scorecard", [])

    css = """
    body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1a1a1a;
         max-width:1080px;margin:0 auto;padding:28px;line-height:1.5;background:#fff}
    h1{font-size:26px;margin:0 0 4px} h2{font-size:19px;margin:30px 0 10px;border-bottom:2px solid #1b5e3f;padding-bottom:4px}
    h3{font-size:15px;margin:18px 0 6px} .sub{color:#666;font-size:13px;margin-bottom:18px}
    table{border-collapse:collapse;width:100%;font-size:12.5px;margin:8px 0}
    th,td{border:1px solid #ddd;padding:5px 8px;text-align:left;vertical-align:top}
    th{background:#f4f6f5;font-weight:600}
    .framing{background:#f4f6f5;border-left:4px solid #1b5e3f;padding:12px 16px;font-size:13px;margin:10px 0}
    .card{border:1px solid #e2e2e2;border-radius:8px;padding:14px 16px;margin:12px 0;background:#fcfdfc}
    .limiting{background:#fbf3d5;font-weight:600}
    .pill{display:inline-block;padding:3px 10px;border-radius:12px;color:#fff;font-size:12px;font-weight:600}
    .muted{color:#777;font-size:12px} .warn{color:#8a2b2b;font-weight:600}
    .grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
    .badge-card{border-radius:10px;padding:16px 20px;color:#fff;display:inline-block;margin:6px 12px 6px 0;min-width:220px}
    .badge-score{font-size:32px;font-weight:700;line-height:1.1}
    .badge-label{font-size:13px;opacity:0.9} .badge-class{font-size:16px;font-weight:600;margin-top:4px}
    """
    _CONCERN_COLOR = {"Very Low": "#1b5e3f", "Low": "#4a8a5f", "Moderate": "#7a5c00",
                      "High": "#a04a1f", "Very High": "#8a2b2b"}

    def matrix_pill(cell):
        label, color = _MATRIX_LABEL.get(cell, (cell, "#555"))
        return f'<span class="pill" style="background:{color}">{_esc(label)}</span>'

    out = [f"<!doctype html><html><head><meta charset='utf-8'><title>{_esc(project_name)} — Evidence Record</title>",
           f"<style>{css}</style></head><body>"]
    out.append(f"<h1>{_esc(project_name)} — Year-0 Evidence Record</h1>")
    out.append(f"<div class='sub'>Generated {_esc(meta.get('generated_at'))} · pipeline "
               f"v{_esc(meta.get('pipeline_version'))} · {_esc(meta.get('n_sites'))} site(s) · "
               f"HMI ceiling {_esc(meta.get('tier2_hmi_ceiling'))} · "
               f"<b>Every claim below carries its evidence grade.</b></div>")

    # --- SoN summary badges (v0.2.4) — the dashboard-facing headline numbers ---
    son = report.get("son_summary", {})
    if son:
        out.append("<h2>State of Nature summary</h2>")
        for site_id, s in son.items():
            oc, op = s.get("overall_condition", {}), s.get("overall_pressure", {})
            cc = _CONCERN_COLOR.get(oc.get("concern_class"), "#555")
            pc = _CONCERN_COLOR.get(op.get("concern_class"), "#555")
            conf = oc.get("confidence", {})
            out.append(f"<div><b>{_esc(site_id)}</b> &nbsp; {matrix_pill(s.get('matrix_cell'))}</div>")
            out.append(f"<div class='badge-card' style='background:{cc}'>"
                       f"<div class='badge-label'>OVERALL CONDITION</div>"
                       f"<div class='badge-score'>{_num(oc.get('score'))}</div>"
                       f"<div class='badge-class'>{_esc(oc.get('concern_class'))}</div></div>")
            out.append(f"<div class='badge-card' style='background:{pc}'>"
                       f"<div class='badge-label'>OVERALL PRESSURE</div>"
                       f"<div class='badge-score'>{_num(op.get('score'))}</div>"
                       f"<div class='badge-class'>{_esc(op.get('concern_class'))}</div></div>")
            out.append(f"<p class='muted'>Confidence: <b>{_esc(conf.get('level'))}</b> "
                       f"({_esc(conf.get('note'))}) · limiting component: "
                       f"<b>{_esc(oc.get('minimum_component'))}</b> "
                       f"({_num(oc.get('minimum_component_score'))}) · "
                       f"sensitivity: {'stable' if oc.get('stable') else 'UNSTABLE — see profile below'}</p>")
        out.append(f"<div class='framing'>{_esc(next(iter(son.values()))['overall_condition'].get('framing',''))}</div>")

    # --- Scoring transparency ---
    out.append("<h2>What is scored, and what is not</h2>")
    out.append("<div class='grid'>")
    for key, tier, title in [
        ("scored", "baseline", "Scored (defensible: active &amp; eligible)"),
        ("contextual", "contextual", "Contextual (shown, not scored)"),
        ("screening_only", "screening", "Screening-only (e.g. range overlap)"),
        ("pending_inputs", "pending", "Pending input (dependency unmet)"),
        ("removed", "removed", "Removed (de-scoped)"),
    ]:
        items = status.get(key, [])
        out.append(f"<div class='card'><h3>{_badge(tier)} &nbsp;{title} "
                   f"<span class='muted'>({len(items)})</span></h3>"
                   f"<div class='muted'>{', '.join(_esc(i) for i in items) or '—'}</div></div>")
    out.append("</div>")

    # --- Per-site profile-first ---
    # --- Multi-tile summary (agroforestry / large multi-parcel projects only) ---
    mts = report.get("multi_tile_summary")
    if mts:
        out.append("<h2>Multi-tile aggregation (why the project profile looks like this)</h2>")
        out.append(f"<p class='muted'>{_esc(mts.get('aggregation_rule'))}</p>")
        out.append(f"<p><b>{_esc(mts.get('n_tiles'))} tiles</b>, "
                   f"total area <b>{_esc(mts.get('total_area_ha'))} ha</b></p>")
        out.append("<table><tr><th>Indicator</th><th>Worst tile (project headline)</th>"
                   "<th>Worst-tile value</th><th>Area-wtd geomean (context)</th>"
                   "<th>Area-wtd mean value (context)</th><th>Tiles with data</th></tr>")
        for name, s in mts.get("per_indicator", {}).items():
            if s.get("status") != "ok":
                out.append(f"<tr><td>{_esc(name)}</td><td colspan='5' class='muted'>"
                          f"no tile had data</td></tr>")
                continue
            out.append(f"<tr><td>{_esc(name)}</td><td><b>{_esc(s.get('worst_tile'))}</b></td>"
                      f"<td>{_num(s.get('worst_tile_benchmark'))}</td>"
                      f"<td class='muted'>{_num(s.get('area_weighted_geomean_normalised'))}</td>"
                      f"<td class='muted'>{_num(s.get('area_weighted_mean_site_value_context'))}</td>"
                      f"<td>{_esc(s.get('n_tiles_with_data'))}/{_esc(s.get('n_tiles_total'))}</td></tr>")
        out.append("</table>")

    out.append("<h2>Site profiles (profile-first)</h2>")
    if not profiles:
        out.append("<p class='warn'>No sites carry a propagated benchmark yet — profiles pending "
                   "upstream computation. (This is honest: nothing is scored on the deprecated ratio.)</p>")
    for site_id, prof in profiles.items():
        cond = prof.get("condition", {})
        press = prof.get("pressure", {})
        sens = cond.get("sensitivity", {})
        out.append(f"<div class='card'><h3>Site: {_esc(site_id)} &nbsp; {matrix_pill(prof.get('matrix_cell'))}</h3>")

        # components + limiting factor
        out.append("<table><tr><th>Component</th><th>Limiting subdimension</th>"
                   "<th>Component score (limiting factor)</th><th>Subdimension profile</th></tr>")
        for comp, cs in prof.get("components", {}).items():
            profile_str = ", ".join(f"{_esc(k)}={_num(v,2)}" for k, v in cs.get("profile", {}).items())
            out.append(f"<tr><td>{_esc(comp)}</td><td class='limiting'>{_esc(cs.get('limiting_subdimension'))}</td>"
                       f"<td><b>{_num(cs.get('headline'),3)}</b> <span class='muted'>(mean {_num(cs.get('mean'),2)})</span></td>"
                       f"<td class='muted'>{profile_str}</td></tr>")
        out.append("</table>")

        # roll-up (secondary) + stability + minimum
        stab = "STABLE" if sens.get("stable") else "UNSTABLE"
        stab_cls = "" if sens.get("stable") else "warn"
        out.append(f"<p><b>Condition roll-up (secondary):</b> {_num(cond.get('rollup'),3)} "
                   f"&nbsp;|&nbsp; <b>minimum component:</b> {_num(cond.get('minimum'),3)} "
                   f"({_esc(cond.get('minimum_component'))}) "
                   f"&nbsp;|&nbsp; <b>pressure axis:</b> {_num(press.get('headline'),3)} "
                   f"&nbsp;|&nbsp; <span class='{stab_cls}'>sensitivity: {stab}</span> "
                   f"<span class='muted'>[{_num(sens.get('rollup_min'),2)}–{_num(sens.get('rollup_max'),2)}]</span></p>")
        if not sens.get("stable"):
            out.append(f"<p class='warn'>⚠ {_esc(sens.get('note'))}</p>")
        out.append(f"<div class='framing'>{_esc(cond.get('framing'))}</div>")
        out.append("</div>")

    # --- Scorecard (evidence-graded) ---
    out.append("<h2>Indicator scorecard (evidence-graded)</h2>")
    out.append("<table><tr><th>Indicator</th><th>Construct</th><th>Grade</th><th>Site value</th>"
               "<th>Benchmark (signed)</th><th>% of ref (uncapped)</th><th>Reference type</th><th>Class</th></tr>")
    for r in rows:
        tier = r.get("evidence_tier") or "—"
        override_flag = ""
        if r.get("client_override"):
            override_flag = (' <span style="background:#5a2a82;color:#fff;padding:1px 6px;'
                            'border-radius:10px;font-size:10px;font-weight:600" '
                            f'title="{_esc(r.get("client_override_note",""))}">CLIENT-ACTIVATED</span>')
        out.append(f"<tr><td>{_esc(r.get('display_name') or r.get('indicator'))}{override_flag}</td>"
                   f"<td>{_esc(r.get('construct'))}</td><td>{_badge(tier)}</td>"
                   f"<td>{_num(r.get('site_value'))}</td>"
                   f"<td>{_num(r.get('tier2_benchmark'))} <span class='muted'>{_esc(r.get('tier2_benchmark_estimator') or '')}</span></td>"
                   f"<td>{_pct(r.get('tier2_display_pct_of_reference'))}</td>"
                   f"<td class='muted'>{_esc(r.get('reference_type'))}</td>"
                   f"<td>{_render_classification(r.get('classification'))}</td></tr>")
    out.append("</table>")
    if any(r.get("client_override") for r in rows):
        out.append("<p class='muted'>Indicators marked <b>CLIENT-ACTIVATED</b> were scored by "
                   "explicit request beyond the Darukaa default set — hover for the original "
                   "disposition and caveat.</p>")

    out.append("<h2>Methodology</h2><ul class='muted'>")
    for ref in meta.get("methodology_references", []):
        out.append(f"<li>{_esc(ref)}</li>")
    out.append("</ul>")
    out.append(f"<p class='muted'>Scoring: {_esc(meta.get('scoring'))}</p>")
    out.append("</body></html>")
    return "\n".join(out)


def write_html(report: Dict, output_path: str, project_name: str = "Darukaa Assessment") -> str:
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    html_str = render_html(report, project_name)
    p.write_text(html_str, encoding="utf-8")
    return str(p)
