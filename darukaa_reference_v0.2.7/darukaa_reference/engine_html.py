"""
engine_html.py -- HTML for engine-based project reports (v0.2.9 Phase 5)
========================================================================

Renders the report built by engine_report.build_project_report, reusing html_report's visual system. Reached through html_report.write_html (dispatch on
meta.report_kind), so it is part of the one existing HTML generation entry point.

Display rules (enforced by tests):
  * a benchmark SCORE is shown as a 0-1 number under a column titled "Benchmark score", never as a percentage; the raw MEASUREMENT (value + unit) and the
    reference median are separate columns;
  * the score explainer (a score of 1.00 is not "100 % ecological condition") is shown at the top and with every realm headline;
  * the coverage caveat is shown WITH the headline, not below the fold;
  * a missing value is "n/a" (an em dash), never 0; every excluded row shows its status and reason;
  * terrestrial and aquatic realms are separate sections; there is no blended headline.
"""
from __future__ import annotations

from typing import Any, Dict, List

from darukaa_reference import engine_report as ER
from darukaa_reference.html_report import _CONCERN_COLOR, _CSS, _MATRIX_LABEL, _esc, _matrix_pill

_SHORT = {"domain_mismatch": "n/a: domain", "target_feature_absent": "n/a: no feature", "ecosystem_type_mismatch": "n/a: ecosystem",
          "site_below_product_resolution": "n/a: below resolution", "insufficient_pure_water": "n/a: pure water"}
_ROLE_TITLE = {"aggregate": "Scored (aggregated)", "context": "Context only (not aggregated)", "screening": "Screening only (not aggregated)",
               "excluded": "Excluded from aggregation (status and reason kept)"}
_ROLE_BG = {"aggregate": "#e6f4ec", "context": "#fbf3d5", "screening": "#f7e3e3", "excluded": "#ececec"}


def _score(x) -> str:
    return "n/a" if x is None else f"{float(x):.2f}"


def _val(x, unit=None) -> str:
    if x is None:
        return "n/a"
    s = f"{float(x):.4g}"
    return f"{s} {_esc(unit)}" if unit else s


def short_status(r: Dict[str, Any]) -> str:
    s = r["status"]
    if s == "scored":
        return _score(r["score"])
    if s == "not_applicable":
        return _SHORT.get(r["reason"], "n/a: " + (r["reason"] or ""))
    return {"contextual_only": "context", "screening_only": "screening", "pending_methodology": "pending", "suppressed_for_stability": "suppressed",
            "applicable_but_no_site_value": "n/a: no site value", "applicable_but_no_reference": "n/a: no reference",
            "reference_available_but_not_scoreable": "n/a: not scoreable"}[s]


def _headline_cards(h: Dict[str, Any]) -> str:
    if not h["available"]:
        return f'<div class="dk-framing dk-warn">{_esc(h["no_headline_reason"])}</div>'
    oc, op = h["condition"], h["pressure"]

    def card(label, d, extra):
        colour = _CONCERN_COLOR.get(d.get("concern_class"), "#555")
        sc = _score(d.get("score"))
        return (f'<div class="dk-badge-card" style="background:{colour}"><div class="dk-badge-label">{label}</div>'
                f'<div class="dk-badge-score">{sc}</div><div class="dk-badge-class">concern class: {_esc(d.get("concern_class"))}</div>'
                f'<div class="dk-muted" style="color:#fff">{extra}</div></div>')
    conf = oc.get("confidence", {})
    cond = card("Condition: benchmark score (0-1)", oc,
                f"pillar confidence {_esc(conf.get('level'))} ({_esc(conf.get('n_pillars_assessed'))} of {_esc(conf.get('n_pillars_total'))} pillars with a scored indicator)")
    pres = card("Pressure: benchmark score (0-1)", op, "kept separate from condition; never blended") if h.get("pressure_available") else \
        '<div class="dk-badge-card" style="background:#555"><div class="dk-badge-label">Pressure</div><div class="dk-badge-score">n/a</div><div class="dk-badge-class">no scored pressure indicator</div></div>'
    return f'<div class="dk-scorebadges">{cond}{pres}</div>'


def _coverage_table(pzc: Dict[str, Any]) -> str:
    def area(v):
        return "n/a" if v["area_fraction"] is None else "%.0f%% of realm area" % (v["area_fraction"] * 100)
    rows = "".join("<tr><td>%s</td><td>%d of %d</td><td>%s</td><td>%s</td></tr>"
                   % (_esc(p), v["zones_scored"], v["zones_total"], area(v), _esc(", ".join(v["zones"]) or "—")) for p, v in pzc.items())
    return ('<table class="dk-table"><tr><th>Pillar</th><th>Zones with a scored indicator</th><th>Area covered</th><th>Which zones</th></tr>' + rows + "</table>")


def _indicator_table(agg: Dict[str, Any]) -> str:
    out = ['<table class="dk-table"><tr><th>Indicator</th><th>Pillar / subdimension</th><th>Worst zone</th><th>Benchmark score (0-1)</th>'
           '<th>Raw measurement at the worst zone</th><th>Reference median (n)</th><th>Scoring method</th><th>Zones scored</th></tr>']
    for i in agg["per_indicator"].values():
        if i["status"] != "ok":
            continue
        out.append(f"<tr><td>{_esc(i['display_name'])}</td><td>{_esc(i['construct'])} / {_esc(i['subdimension'])}</td><td>{_esc(i['worst_zone'])}</td>"
                   f"<td><b>{_score(i['worst_zone_score'])}</b></td><td>{_val(i['worst_zone_site_value'], i['worst_zone_site_unit'])}</td>"
                   f"<td>{_val(i['worst_zone_reference_median'])} (n={_esc(i['worst_zone_reference_n'])})</td><td>{_esc(i['worst_zone_scoring_method'])}</td>"
                   f"<td>{i['n_zones_scored']} of {i['n_zones_in_realm']}</td></tr>")
    out.append("</table>")
    return "".join(out)


def _unscored_table(agg: Dict[str, Any]) -> str:
    rows = []
    for i in agg["per_indicator"].values():
        if i["status"] == "ok" and i["n_zones_scored"] == i["n_zones_in_realm"]:
            continue
        why = "; ".join(f"{e['zone']}: {e['status']}" + (f" / {e['reason']}" if e["reason"] else "") for e in i["excluded_zones"][:12]) or \
              ("context only" if i["context_zones"] else "screening only" if i["screening_zones"] else "—")
        rows.append(f"<tr><td>{_esc(i['display_name'])}</td><td>{i['n_zones_scored']} of {i['n_zones_in_realm']}</td><td>{_esc(why)}</td></tr>")
    if not rows:
        return '<p class="dk-muted">Every in-domain indicator was scored in every zone.</p>'
    return ('<table class="dk-table"><tr><th>Indicator</th><th>Zones scored</th><th>Where it was NOT scored, and why (status / reason)</th></tr>' + "".join(rows) + "</table>")


def _matrix(zones: List[Dict[str, Any]], agg: Dict[str, Any]) -> str:
    inds = [i for i in agg["per_indicator"].values()]
    head = "".join(f"<th>{_esc(z['label'])}</th>" for z in zones)
    lines = [f'<table class="dk-table"><tr><th>Indicator</th>{head}</tr>']
    for i in inds:
        cells = []
        for z in zones:
            r = next((r for r in z["rows"] if r["indicator"] == i["indicator"]), None)
            if r is None:
                cells.append("<td>—</td>")
                continue
            bg = _ROLE_BG[r["aggregation_role"]]
            cells.append(f'<td style="background:{bg}">{_esc(short_status(r))}</td>')
        lines.append(f"<tr><td>{_esc(i['display_name'])}</td>{''.join(cells)}</tr>")
    lines.append("</table>")
    lines.append('<p class="dk-muted">Cell = benchmark score (0-1) where scored, otherwise the status; every status and reason is in the zone sections below. '
                 'Green = scored, yellow = context, red = screening, grey = excluded.</p>')
    return "".join(lines)


def _zone_section(z: Dict[str, Any]) -> str:
    cov, h = z["coverage"], z["headline"]
    area_txt = "n/a" if z["area_ha"] is None else "%.2f ha" % z["area_ha"]
    parts = ['<details class="dk-collapsible"><summary>%s (%s, %s) &mdash; scored %d, condition pillars with evidence %d of %d</summary>'
             % (_esc(z["label"]), _esc(z["realm"]), area_txt, cov["n_scored"], cov["n_condition_pillars_covered"], cov["n_condition_pillars_total"])]
    parts.append(f'<p class="dk-muted">realm declared by: {_esc(z["realm_source"])}; status counts: {_esc(cov["status_counts"])}</p>')
    parts.append(_headline_cards(h))
    for role in ("aggregate", "context", "screening", "excluded"):
        rs = [r for r in z["rows"] if r["aggregation_role"] == role]
        if not rs:
            continue
        parts.append(f'<h3 class="dk-h3">{_ROLE_TITLE[role]} &mdash; {len(rs)}</h3>')
        if role == "aggregate":
            parts.append('<table class="dk-table"><tr><th>Indicator</th><th>Raw measurement</th><th>Reference median (n)</th><th>Benchmark score (0-1)</th>'
                         '<th>Scoring method</th><th>Applicability / flags</th></tr>')
            for r in rs:
                flag = r["applicability_reason"] if r["applicability_reason"] not in (None, "applicable") else ""
                parts.append(f"<tr><td>{_esc(r['display_name'])}</td><td>{_val(r['site_value'], r['site_unit'])}</td>"
                             f"<td>{_val(r['reference_median'])} (n={_esc(r['reference_n'])})</td><td><b>{_score(r['score'])}</b></td>"
                             f"<td>{_esc(r['scoring_method'])}</td><td>{_esc(flag or r['flags'] or '')}</td></tr>")
        else:
            parts.append('<table class="dk-table"><tr><th>Indicator</th><th>Status</th><th>Reason</th><th>Detail</th><th>Raw measurement (if any)</th></tr>')
            for r in rs:
                parts.append(f"<tr><td>{_esc(r['display_name'])}</td><td>{_esc(r['status'])}</td><td>{_esc(r['reason'] or '—')}</td><td>{_esc(r['detail'] or '—')}</td>"
                             f"<td>{_val(r['site_value'], r['site_unit'])}</td></tr>")
        parts.append("</table>")
    parts.append("</details>")
    return "".join(parts)


def render_engine_html(report: Dict[str, Any], project_name: str = "Darukaa Assessment") -> str:
    meta = report["meta"]
    eng = meta.get("engine", {})
    prov = meta.get("provenance", {})
    out = [f'<!doctype html><html><head><meta charset="utf-8"><title>{_esc(project_name)} - engine assessment</title><style>{_CSS}</style></head><body>']
    out.append(f'<div class="dk-header"><h1>{_esc(project_name)}</h1><div class="dk-subtitle">Reference benchmarking: frozen v0.2.8 engine, general pipeline</div>'
               f'<div class="dk-meta-strip"><span>{_esc(meta.get("n_zones"))} zones assessed ({_esc(meta.get("n_zones_failed"))} failed)</span>'
               f'<span>realms: {_esc(", ".join(f"{k} {len(v)}" for k, v in meta.get("zones_by_realm", {}).items()))}</span>'
               f'<span>contract {_esc(eng.get("contract_version"))}</span><span>engine {_esc(str(eng.get("engine_sha256_at_import", ""))[:12])}'
               f'{" (frozen)" if eng.get("engine_matches_frozen") else " (NOT FROZEN)"}</span><span>commit {_esc(prov.get("git_commit_short"))}</span></div></div>')
    out.append(f'<div class="dk-framing"><b>How to read the numbers.</b> {_esc(ER.SCORE_EXPLAINER)}</div>')
    if meta.get("failed_zones"):
        out.append('<div class="dk-framing dk-warn">Zones that failed and are NOT in this report: ' + _esc(meta["failed_zones"]) + "</div>")
    out.append('<div class="dk-framing"><b>No blended headline.</b> ' + _esc(report["headline_policy"].split("Each realm")[0]) + "</div>")
    for realm, r in report["realms"].items():
        h = r["headline"]
        zones = [report["zones"][k] for k in r["zones"]]
        out.append(f'<h2 class="dk-h2">{_esc(realm.title())} realm &mdash; {r["n_zones"]} zones, {r["total_area_ha"]} ha</h2>')
        out.append(_headline_cards(h))
        if h["available"]:
            out.append(f'<p>{_matrix_pill(h.get("matrix_cell"))} <span class="dk-muted">condition x pressure decision cell</span></p>')
            if h["limiting_chain"].get("available"):
                out.append(f'<p class="dk-muted">Condition is {_esc(h["limiting_chain"]["display"])}.</p>')
        if h.get("coverage_caveat"):
            out.append(f'<div class="dk-framing dk-warn">{_esc(h["coverage_caveat"])}</div>')
        out.append('<h3 class="dk-h3">Pillar coverage by zone</h3>' + _coverage_table(h["pillar_zone_coverage"]))
        out.append('<h3 class="dk-h3">Realm signal per indicator (worst scored zone)</h3>' + _indicator_table(r["aggregation"]))
        out.append('<h3 class="dk-h3">Where evidence is absent (never imputed, never 0)</h3>' + _unscored_table(r["aggregation"]))
        out.append('<h3 class="dk-h3">Zone x indicator matrix</h3>' + _matrix(zones, r["aggregation"]))
        out.append(f'<p class="dk-muted">Indicators outside this realm\'s domain ({len(r["aggregation"]["indicators_out_of_domain"])}) are not applicable by the '
                   f'frozen contract and are listed per zone as n/a: domain.</p>')
        out.append('<h3 class="dk-h3">Zones</h3>' + "".join(_zone_section(z) for z in zones))
    out.append('<h2 class="dk-h2">Status policy</h2><table class="dk-table"><tr><th>Engine status</th><th>Used as</th></tr>' +
               "".join(f"<tr><td>{_esc(k)}</td><td>{_esc(v)}</td></tr>" for k, v in report["status_policy"].items()) + "</table>")
    out.append(f'<div class="dk-footer">pipeline {_esc(meta.get("pipeline_version"))} &middot; engine code {_esc(eng.get("code_version"))} &middot; engine sha256 '
               f'{_esc(eng.get("engine_sha256_at_import"))} &middot; engine config matches the frozen configuration: {_esc(eng.get("engine_config_matches_frozen"))} '
               f'&middot; source sha256 {_esc(str(prov.get("source_sha256_at_import", ""))[:16])} &middot; generated {_esc(meta.get("generated_at"))}</div></body></html>')
    return "".join(out)
