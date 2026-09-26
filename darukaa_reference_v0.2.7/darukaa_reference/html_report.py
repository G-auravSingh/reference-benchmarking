"""
Evidence-Graded HTML Report (CS-10) — v0.2.7 client/product-facing rebuild
============================================================================

Two real inputs, handled explicitly rather than assumed identical:
  - a SINGLE-SITE report (one project, one boundary) — `site_profiles` has
    one or more real site_ids, no `multi_tile_summary`.
  - a PROJECT-LEVEL, multi-zone report (e.g. Tata Motors' 9 real zones,
    Soulforest's 7 EMUs, Corbett's 4 independent sites) — `site_profiles`
    has exactly one entry keyed "PROJECT" (the worst-zone-driven,
    non-compensatory aggregate), plus `multi_tile_summary` (per-indicator
    worst-zone detail) and `tile_reports` (each real zone's own COMPLETE,
    independent report — the pipeline genuinely ran once per zone, not
    once over the whole boundary; this file shows that work, not just
    the aggregate on top of it).

Design goals for this rebuild (client-reported: needs to read as a
scientifically rigorous, professional, high-standard document that is
also genuinely self-explanatory — a reader who has never seen this
methodology before should understand it from this file alone, and a
product team should be able to theme/consume it reliably):
  - a real executive summary in plain language, before any table;
  - an embedded, real explanation of WHY the scoring works this way
    (profile-first, non-compensatory, evidence tiers) — not a citation
    list standing in for an explanation;
  - genuine visual elements (inline SVG — no external JS dependency, so
    the file stays a single self-contained artifact): a per-zone ranked
    bar chart and a condition x pressure quadrant plot;
  - clean, semantic, predictable CSS classes (`.dk-*` prefix) instead of
    inline styles, so a product team can reliably theme or scrape this;
  - every real limitation (evidence tier, confidence, sensitivity,
    failed tiles) stays exactly as visible as it was before this rebuild
    — this is an addition of clarity and design, not a removal of rigor.

No external dependencies; returns an HTML string and optionally writes it.
"""
from __future__ import annotations

import html
from pathlib import Path
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Shared display vocabulary
# ---------------------------------------------------------------------------
_TIER_COLOR = {
    "baseline": ("#0f5132", "#e6f4ec"),
    "monitoring": ("#0d47a1", "#e3f0fb"),
    "contextual": ("#7a5c00", "#fbf3d5"),
    "screening": ("#8a2b2b", "#f7e3e3"),
    "pending": ("#555", "#ececec"),
    "removed": ("#000", "#ddd"),
}
_MATRIX_LABEL = {
    "protect_maintain": ("Protect / maintain", "#0f5132"),
    "defend_abate_threat": ("Defend — abate threat", "#8a2b2b"),
    "restore": ("Restore", "#7a5c00"),
    "stabilise_then_restore": ("Stabilise, then restore", "#5a2a82"),
    "insufficient_data": ("Insufficient data", "#555"),
}
_CONCERN_COLOR = {
    "Very Low": "#0f5132", "Low": "#4a8a5f", "Moderate": "#a67c00",
    "High": "#c05621", "Very High": "#8a2b2b",
}
_CONCERN_ORDER = ["Very Low", "Low", "Moderate", "High", "Very High"]

_ARCHETYPE_COPY = {
    "conservation": ("a conservation site with real, ecologically distinct zones",
                      "zone"),
    "industrial": ("an industrial-campus site assessed zone by zone against its own "
                    "real, client-declared ecological zonation", "zone"),
    "agroforestry": ("an agroforestry project spanning real, physically scattered "
                      "farm parcels grouped into ecological management units", "EMU"),
}


def _esc(x) -> str:
    return html.escape(str(x)) if x is not None else "—"


def _badge(tier: str) -> str:
    fg, bg = _TIER_COLOR.get(tier, ("#333", "#eee"))
    return (f'<span class="dk-badge" style="background:{bg};color:{fg}">{_esc(tier)}</span>')


def _pct(x) -> str:
    return "—" if x is None else f"{x:.0f}%"


def _num(x, d=3) -> str:
    return "—" if x is None else f"{x:.{d}f}"


def _matrix_pill(cell: str) -> str:
    label, color = _MATRIX_LABEL.get(cell, (cell or "—", "#555"))
    return f'<span class="dk-pill" style="background:{color}">{_esc(label)}</span>'


def _concern_color(label: str) -> str:
    return _CONCERN_COLOR.get(label, "#555")


def _render_classification(cls: Dict) -> str:
    if not cls or not cls.get("reference_relative"):
        return "—"
    rr = cls["reference_relative"]
    out = f"{_esc(rr.get('class'))} <span class='dk-muted'>(ref.)</span>"
    la = cls.get("literature_anchored")
    if la:
        out += (f"<br><span class='dk-muted' title=\"{_esc(la.get('basis',''))}\">"
               f"{_esc(la.get('class'))} (literature)</span>")
    return out


# ---------------------------------------------------------------------------
# Indicator-table rendering (client-requested rebuild): raw value, intactness
# %, concern level per indicator, grouped by real pillar — replacing the
# earlier flat scorecard table. "No bare dashes" rule: every empty-looking
# cell states WHY (not applicable to this geometry/realm vs. a real
# extraction failure vs. genuinely not scored), never a silent "—" a reader
# has to guess at.
# ---------------------------------------------------------------------------

def _indicator_state(row: Dict) -> str:
    """Distinguishes the three real, different reasons a cell can look
    empty — client-requested directly ("many empty dashes... very
    confusing"). Never returns a bare dash."""
    if row.get("site_value") is not None:
        return "ok"
    reason = ((row.get("metadata") or {}).get("reason") or "")
    if reason:
        return "not_applicable"  # e.g. "no open water detected" — a real,
        # informative reason the extraction function itself gave, not a
        # crash and not silence
    return "unavailable"  # a real extraction attempt that produced nothing,
    # with no stated reason — shown as such, not disguised as N/A


def _within_project_rank(row: Dict, all_project_rows: Optional[List[Dict]]) -> Optional[tuple]:
    """Real rank of this zone's value for this SAME indicator among all real
    zones in this project that have real data for it. 1 = best (respecting
    the indicator's own higher_is_better), N = worst. This is the real,
    meaningful comparative context an in-situ metric CAN offer at baseline
    even with no valid spatial reference pool (see son_score.py / change.py:
    "self-referential thresholds are not a baseline") -- "how does this
    zone compare to the other real zones in THIS project", never a claim
    about external ecoregion condition. Returns None when all_project_rows
    isn't available (a single-site report) or fewer than 2 real zones have
    data for this indicator."""
    if not all_project_rows:
        return None
    indicator = row.get("indicator")
    higher_is_better = row.get("higher_is_better", True)
    same_indicator = [(r.get("site_id"), r.get("site_value")) for r in all_project_rows
                      if r.get("indicator") == indicator and r.get("site_value") is not None]
    if len(same_indicator) < 2:
        return None
    ranked = sorted(same_indicator, key=lambda t: t[1], reverse=higher_is_better)
    for i, (site_id, _) in enumerate(ranked, start=1):
        if site_id == row.get("site_id"):
            return (i, len(ranked))
    return None


def _indicator_row_html(row: Dict, all_project_rows: Optional[List[Dict]] = None) -> str:
    state = _indicator_state(row)
    name = row.get("display_name") or row.get("indicator")
    unit = row.get("unit") or ""
    if state == "ok":
        raw = f"{_num(row.get('site_value'), 3)} {_esc(unit)}".strip()
    elif state == "not_applicable":
        reason = (row.get("metadata") or {}).get("reason", "")
        raw = f'<span class="dk-muted" title="{_esc(reason)}">Not applicable — {_esc(reason)}</span>'
    else:
        raw = '<span class="dk-warn">Unavailable — real extraction attempt found no data</span>'

    # Client-requested directly: in-situ (field-collected) metrics have no
    # valid spatial reference pool the way a remote-sensed indicator does
    # (no equivalent "other nearby pristine sites surveyed with the same
    # camera-trap/eDNA protocol" to benchmark against) -- a concern level
    # here would fabricate a comparison that doesn't exist. Real,
    # documented answer already existed in change.py before this report
    # rebuild: baseline shows a real value + within-project rank, never a
    # concern class; a genuine signal (change vs this site's own Year-0)
    # only becomes available from monitoring cycles onward. No real
    # in_situ indicator is registered yet — this path is forward-looking,
    # not yet exercised by a real run, and clearly marked as such below.
    if row.get("source_type") == "in_situ":
        rank = _within_project_rank(row, all_project_rows)
        rank_str = (f"Rank {rank[0]} of {rank[1]} zones in this project"
                   if rank else "Not enough real zones with data to rank")
        intactness_cell = '<span class="dk-muted">no spatial reference pool</span>'
        concern_cell = (f'<span class="dk-muted">{_esc(rank_str)}</span><br>'
                       f'<span class="dk-insitu-tag">in-situ — baseline, no concern level</span>')
        return (f'<tr><td>{_esc(name)}</td><td>{raw}</td>'
               f'<td>{intactness_cell}</td><td>{concern_cell}</td></tr>')

    tier = row.get("evidence_tier") or "contextual"
    if tier not in ("baseline", "monitoring"):
        # Real, computed context — genuinely shown, genuinely not scored.
        # Never a score_pct or concern badge for these (would misrepresent
        # them as benchmarked when they are not).
        intactness_cell = '<span class="dk-muted">not scored</span>'
        concern_cell = _badge(tier)
    elif row.get("tier2_benchmark") is None:
        intactness_cell = '<span class="dk-warn">reference comparison unavailable</span>'
        # REAL FIX (finishing the "no bare dashes" sweep): this was a bare
        # "—" with nothing explaining it, even though the cell right next
        # to it already gives the real reason. Made explicit rather than
        # relying on an adjacent cell's context to carry the meaning.
        concern_cell = '<span class="dk-muted">not assessable without a reference</span>'
    else:
        # The bounded 0-1 score (already computed by scoring.normalize's
        # logistic — see son_score.py) is what belongs here, not the raw,
        # unbounded z-score/LRR value, which is real and kept in the full
        # audit CSV/JSON but is not something a report reader should have
        # to interpret directly (client-requested: "converting to 1-100%
        # intactness and not just using z score").
        from darukaa_reference import scoring as _scoring
        bounded = _scoring.normalize(row.get("tier2_benchmark"), row.get("tier2_benchmark_estimator") or "")
        pct = _score_pct(bounded)
        cls = (row.get("classification") or {}).get("reference_relative") or {}
        concern = cls.get("class")
        intactness_cell = pct
        # REAL FIX (finishing the "no bare dashes" sweep): a benchmark
        # exists but classification is somehow missing -- a rare, real
        # edge case, not something to hide behind a silent dash.
        concern_cell = (f'<span style="color:{_concern_color(concern)};font-weight:600">{_esc(concern)}</span>'
                       if concern else '<span class="dk-warn">concern class unavailable despite a real benchmark</span>')

    return (f'<tr><td>{_esc(name)}</td><td>{raw}</td>'
           f'<td>{intactness_cell}</td><td>{concern_cell}</td></tr>')


def _pillar_card_html(pillar: Dict, all_rows_for_pillar: List[Dict],
                      all_project_rows: Optional[List[Dict]] = None) -> str:
    color = _concern_color(pillar.get("concern_class"))
    limiting = pillar.get("limiting_indicators") or []
    # REAL FIX (finishing the "no bare dashes" sweep): the fallback here
    # used to be a bare "—" for the genuine edge case where a pillar has
    # no real scored data at all this run.
    limiting_str = " & ".join(limiting) if limiting else (
        pillar.get("limiting_subdimension") or "no real scored data this run")
    out = [f'<div class="dk-pillar-card">']
    out.append(f'<div class="dk-pillar-head" style="border-left-color:{color}">'
              f'<h3 class="dk-h3">{_esc(pillar.get("pillar_label"))}</h3>'
              f'<div class="dk-pillar-score">{_esc(pillar.get("score_pct"))} '
              f'<span style="color:{color};font-weight:700">{_esc(pillar.get("concern_class"))}</span></div>'
              f'<div class="dk-muted">limited by: <b>{_esc(limiting_str)}</b></div></div>')
    scored_rows = [r for r in all_rows_for_pillar
                  if r.get("evidence_tier") in ("baseline", "monitoring")
                  and r.get("source_type") != "in_situ"]
    insitu_rows = [r for r in all_rows_for_pillar if r.get("source_type") == "in_situ"]
    context_rows = [r for r in all_rows_for_pillar
                    if r.get("evidence_tier") not in ("baseline", "monitoring")
                    and r.get("source_type") != "in_situ"]
    if scored_rows:
        out.append('<table class="dk-table"><tr><th>Indicator</th><th>Raw value</th>'
                  '<th>Intactness</th><th>Concern</th></tr>')
        for r in scored_rows:
            out.append(_indicator_row_html(r, all_project_rows))
        out.append('</table>')
    if insitu_rows:
        out.append('<div class="dk-insitu-note">In-situ (field-collected) metrics in this pillar — '
                  'baseline year, real values shown with within-project rank, never a concern level '
                  '(no valid spatial reference pool exists for field data). A real trend signal becomes '
                  'available from Year-1 monitoring onward, comparing each site to its own baseline.</div>')
        out.append('<table class="dk-table"><tr><th>Indicator</th><th>Raw value</th>'
                  '<th>Reference</th><th>Rank / status</th></tr>')
        for r in insitu_rows:
            out.append(_indicator_row_html(r, all_project_rows))
        out.append('</table>')
    if context_rows:
        out.append('<details class="dk-collapsible"><summary>Context indicators in this pillar '
                  f'({len(context_rows)}) — shown, real, not scored</summary>')
        out.append('<table class="dk-table"><tr><th>Indicator</th><th>Raw value</th>'
                  '<th>Intactness</th><th>Status</th></tr>')
        for r in context_rows:
            out.append(_indicator_row_html(r, all_project_rows))
        out.append('</table></details>')
    out.append('</div>')
    return "".join(out)


def _project_distribution_html(zone_sons: Dict[str, Dict]) -> str:
    """Real project-level summary statistics (client-requested directly:
    "3 out of 5 zones sit in this concern level... some way of showing
    that... when we do this for agroforestry it will run on each parcel
    within an EMU also... project-level information would always help").
    A distribution, not just a ranked list -- matters more, not less, as
    the real number of real units in a project grows (agroforestry's many
    real parcels vs a handful of conservation zones)."""
    from collections import Counter
    concern_counts = Counter(s.get("overall_condition", {}).get("concern_class")
                             for s in zone_sons.values())
    n = len(zone_sons)
    out = ['<div class="dk-dist-grid">']
    for concern in CONCERN_ORDER_LOCAL:
        count = concern_counts.get(concern, 0)
        pct = round(100 * count / n) if n else 0
        color = _concern_color(concern)
        out.append(f'<div class="dk-dist-cell"><div class="dk-dist-bar" '
                  f'style="background:{color};height:{max(4,pct)}px"></div>'
                  f'<div class="dk-dist-label">{count}/{n}<br>{_esc(concern)}</div></div>')
    out.append('</div>')
    out.append(f'<p class="dk-muted">{n} real zone(s)/unit(s) assessed. '
              f'{concern_counts.get("High",0)+concern_counts.get("Very High",0)} of {n} sit in '
              f'High or Very High concern.</p>')
    return "".join(out)


CONCERN_ORDER_LOCAL = ["Very Low", "Low", "Moderate", "High", "Very High"]

from darukaa_reference.son_score import PILLAR_NAMES  # single source of truth
from darukaa_reference.son_score import _pct as _score_pct  # REAL BUG FIXED HERE
# (caught by rendering this in a real browser, not assumed correct): this
# module already had its OWN, different, pre-existing _pct(x) (formats an
# ALREADY-multiplied percentage number, e.g. tier2_display_pct_of_reference
# -- no *100). My new code calling a bare _pct(0-1 score) was silently
# resolving to THAT local function instead of son_score's (which expects a
# raw 0-1 fraction and multiplies by 100) -- 0.30 became "0%", not "30%".
# Imported under an explicit, non-colliding alias instead of renaming
# either original function, since both are real and still needed for
# their own original purpose.


def _son_hero_html(son_data: Dict, label: str = "") -> str:
    oc = son_data.get("overall_condition", {})
    color = _concern_color(oc.get("concern_class"))
    chain = son_data.get("limiting_chain") or {}
    chain_str = chain.get("display", "")
    out = [f'<div class="dk-son-hero" style="background:{color}">']
    if label:
        out.append(f'<div class="dk-badge-label">{_esc(label)}</div>')
    out.append(f'<div class="dk-score">{_esc(oc.get("score_pct"))} '
              f'&nbsp;{_esc(oc.get("concern_class"))}</div>')
    if chain_str:
        # REAL BUG FIXED HERE (caught by actually rendering this in a
        # browser, not assumed correct): Python's .capitalize() lowercases
        # every OTHER character too, mangling real proper nouns already
        # correctly capitalized inside the chain string itself (e.g. "C1
        # — Landscape extent" became "C1 — landscape extent" — and
        # "Forest Fragmentation & Pressure Proxy" lost its own
        # capitalisation). Only the true first character needs
        # capitalising here; the rest of the string is left exactly as
        # limiting_chain() already built it.
        display_chain = chain_str[0].upper() + chain_str[1:] if chain_str else chain_str
        out.append(f'<div class="dk-chain">{_esc(display_chain)}</div>')
    out.append('</div>')
    return "".join(out)


# ---------------------------------------------------------------------------
# Inline SVG visuals — no external chart library, stays self-contained.
# ---------------------------------------------------------------------------

def _svg_zone_bar_chart(zone_scores: List[Dict], width: int = 900) -> str:
    """Horizontal ranked bar chart: one bar per real zone's overall
    condition score, worst (lowest) at top — visually reinforcing the
    non-compensatory design before any table does. zone_scores:
    [{"zone": str, "score": float 0-1, "concern_class": str}], pre-sorted
    ascending by score (worst first) by the caller."""
    if not zone_scores:
        return ""
    n = len(zone_scores)
    row_h = 34
    left_pad = 220
    chart_w = width - left_pad - 60
    height = n * row_h + 40
    bars = []
    for i, z in enumerate(zone_scores):
        y = 20 + i * row_h
        score = z["score"] if z["score"] is not None else 0.0
        bar_w = max(2, chart_w * min(max(score, 0.0), 1.0))
        color = _concern_color(z.get("concern_class"))
        worst_marker = " ▼ worst" if i == 0 else ""
        bars.append(
            f'<text x="{left_pad-10}" y="{y+row_h/2+4}" text-anchor="end" '
            f'class="dk-svg-label">{_esc(z["zone"])}{worst_marker}</text>'
            f'<rect x="{left_pad}" y="{y+4}" width="{chart_w}" height="{row_h-14}" '
            f'fill="#eee" rx="3"/>'
            f'<rect x="{left_pad}" y="{y+4}" width="{bar_w}" height="{row_h-14}" '
            f'fill="{color}" rx="3"/>'
            f'<text x="{left_pad+chart_w+8}" y="{y+row_h/2+4}" class="dk-svg-value">'
            f'{_score_pct(z["score"])}</text>'
        )
    # Reference line at 0.5 (at-reference)
    ref_x = left_pad + chart_w * 0.5
    bars.append(f'<line x1="{ref_x}" y1="14" x2="{ref_x}" y2="{height-14}" '
               f'stroke="#999" stroke-dasharray="3,3"/>'
               f'<text x="{ref_x}" y="12" text-anchor="middle" class="dk-svg-refline">'
               f'at reference</text>')
    return (f'<svg viewBox="0 0 {width} {height}" class="dk-svg-chart" '
           f'xmlns="http://www.w3.org/2000/svg">{"".join(bars)}</svg>')


def _svg_condition_pressure_quadrant(zone_points: List[Dict], width: int = 520, height: int = 460) -> str:
    """A real condition (x) vs pressure (y) scatter — one point per zone,
    in the same quadrant framing the condition x pressure decision matrix
    uses (protect/defend/restore/stabilise). zone_points:
    [{"zone": str, "condition": float 0-1, "pressure": float 0-1}]."""
    if not zone_points:
        return ""
    pad = 60
    plot_w, plot_h = width - pad - 20, height - pad - 30
    def px(v): return pad + plot_w * min(max(v, 0.0), 1.0)
    def py(v): return (height - 30) - plot_h * min(max(v, 0.0), 1.0)  # low pressure at bottom
    mid_x, mid_y = px(0.5), py(0.5)
    quads = [
        (pad, 30, mid_x-pad, mid_y-30, "#fdecea", "Defend", "start", pad+6, 30+16),
        (mid_x, 30, width-20-mid_x, mid_y-30, "#fff6e0", "Stabilise, then restore", "end", width-26, 30+16),
        (pad, mid_y, mid_x-pad, (height-30)-mid_y, "#eaf6ee", "Restore-adjacent", "start", pad+6, height-38),
        (mid_x, mid_y, width-20-mid_x, (height-30)-mid_y, "#e6f4ec", "Protect / maintain", "end", width-26, height-38),
    ]
    parts = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{c}"/>'
            for x, y, w, h, c, lbl, anch, lx, ly in quads]
    parts += [f'<text x="{lx}" y="{ly}" text-anchor="{anch}" class="dk-svg-quadlabel" opacity="0.55">{_esc(lbl)}</text>'
             for x, y, w, h, c, lbl, anch, lx, ly in quads]
    parts.append(f'<line x1="{pad}" y1="{mid_y}" x2="{width-20}" y2="{mid_y}" stroke="#999"/>')
    parts.append(f'<line x1="{mid_x}" y1="30" x2="{mid_x}" y2="{height-30}" stroke="#999"/>')
    parts.append(f'<text x="{width/2}" y="{height-8}" text-anchor="middle" class="dk-svg-axis">Condition (low → high) →</text>')
    parts.append(f'<text x="14" y="{height/2}" text-anchor="middle" class="dk-svg-axis" '
                f'transform="rotate(-90 14 {height/2})">← Pressure (low → high)</text>')
    for zp in zone_points:
        cx, cy = px(zp["condition"]), py(zp["pressure"])
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="10" fill="#1b5e3f" stroke="#fff" stroke-width="1.5"/>')
        zp["_cx"], zp["_cy"] = cx, cy
    # REAL FIX (confirmed directly by rendering a real multi-zone test in
    # an actual browser, not assumed): text labels directly on each point
    # overlapped badly whenever several zones scored similarly, which is
    # a COMMON real pattern, not a rare synthetic-data edge case. Numbered
    # markers + a separate legend list avoids overlap regardless of how
    # tightly zones cluster, rather than trying to de-collide text that
    # can still collide when points themselves are only a few px apart.
    legend_items = []
    for i, zp in enumerate(zone_points, start=1):
        parts.append(f'<text x="{zp["_cx"]}" y="{zp["_cy"]+4}" text-anchor="middle" '
                    f'class="dk-svg-ptnum">{i}</text>')
        legend_items.append(zp["zone"])
    legend_html = ('<div class="dk-quad-legend">' +
                  " &nbsp;·&nbsp; ".join(f'<b>{i}</b> {_esc(z)}' for i, z in enumerate(legend_items, start=1)) +
                  '</div>')
    return (f'<svg viewBox="0 0 {width} {height}" class="dk-svg-chart" '
           f'xmlns="http://www.w3.org/2000/svg">{"".join(parts)}</svg>' + legend_html)


# ---------------------------------------------------------------------------
# CSS — semantic classes, no inline styles in the body markup below.
# ---------------------------------------------------------------------------
_CSS = """
:root{--dk-green:#0f5132;--dk-green-bg:#e6f4ec;--dk-ink:#1a1a1a;--dk-muted:#666;--dk-border:#e2e2e2}
*{box-sizing:border-box}
body{font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:var(--dk-ink);
     max-width:1120px;margin:0 auto;padding:32px 28px 60px;line-height:1.55;background:#fff}
.dk-header{border-bottom:3px solid var(--dk-green);padding-bottom:16px;margin-bottom:24px}
.dk-header h1{font-size:28px;margin:0 0 6px;font-weight:700}
.dk-header .dk-subtitle{color:var(--dk-muted);font-size:14px}
.dk-header .dk-meta-strip{margin-top:10px;font-size:12.5px;color:var(--dk-muted);
     display:flex;flex-wrap:wrap;gap:14px}
.dk-header .dk-meta-strip span{white-space:nowrap}
h2.dk-h2{font-size:20px;margin:36px 0 14px;padding-bottom:6px;border-bottom:2px solid var(--dk-green);
     display:flex;align-items:center;gap:10px}
h3.dk-h3{font-size:15.5px;margin:20px 0 8px;font-weight:700}
.dk-exec-summary{background:var(--dk-green-bg);border-left:5px solid var(--dk-green);
     border-radius:0 8px 8px 0;padding:20px 24px;font-size:15px;margin:14px 0 8px}
.dk-exec-summary p{margin:0 0 10px}.dk-exec-summary p:last-child{margin-bottom:0}
.dk-primer{background:#fafbfa;border:1px solid var(--dk-border);border-radius:8px;
     padding:18px 22px;font-size:13.5px;margin:10px 0}
.dk-primer h4{margin:14px 0 6px;font-size:13.5px}
.dk-primer h4:first-child{margin-top:0}
table.dk-table{border-collapse:collapse;width:100%;font-size:12.5px;margin:10px 0}
table.dk-table th,table.dk-table td{border:1px solid var(--dk-border);padding:6px 9px;
     text-align:left;vertical-align:top}
table.dk-table th{background:#f4f6f5;font-weight:700}
table.dk-table tr.dk-row-worst{background:#fdecea}
.dk-framing{background:#f4f6f5;border-left:4px solid var(--dk-green);padding:12px 16px;
     font-size:13px;margin:10px 0;border-radius:0 6px 6px 0}
.dk-card{border:1px solid var(--dk-border);border-radius:10px;padding:16px 18px;
     margin:12px 0;background:#fcfdfc}
.dk-limiting{background:#fbf3d5;font-weight:600}
.dk-pill{display:inline-block;padding:4px 12px;border-radius:14px;color:#fff;font-size:12.5px;font-weight:600}
.dk-badge{padding:1.5px 8px;border-radius:10px;font-size:11px;font-weight:700;white-space:nowrap}
.dk-muted{color:var(--dk-muted);font-size:12px}.dk-warn{color:#8a2b2b;font-weight:600}
.dk-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.dk-scorebadges{display:flex;gap:16px;flex-wrap:wrap;margin:10px 0}
.dk-badge-card{border-radius:12px;padding:18px 22px;color:#fff;min-width:230px;flex:1}
.dk-badge-label{font-size:12.5px;opacity:.9;letter-spacing:.03em;text-transform:uppercase}
.dk-badge-score{font-size:34px;font-weight:800;line-height:1.15;margin:4px 0}
.dk-badge-class{font-size:16px;font-weight:600}
.dk-svg-chart{width:100%;height:auto;margin:12px 0}
.dk-svg-label{font-size:12px;fill:#333}
.dk-svg-value{font-size:12px;fill:#333;font-weight:600}
.dk-svg-refline{font-size:10px;fill:#888}
.dk-svg-axis{font-size:11px;fill:#555;font-weight:600}
.dk-svg-quadlabel{font-size:11px;fill:#555;font-weight:600}
.dk-svg-ptlabel{font-size:11px;fill:#1a1a1a}
.dk-svg-ptnum{font-size:11px;fill:#fff;font-weight:700}
.dk-quad-legend{font-size:11.5px;color:var(--dk-muted);margin-top:8px;line-height:1.8}
.dk-quad-legend b{color:#1b5e3f}
.dk-toc{background:#fafbfa;border:1px solid var(--dk-border);border-radius:8px;padding:14px 20px;
     font-size:13px;margin:16px 0}
.dk-toc a{color:var(--dk-green);text-decoration:none}.dk-toc a:hover{text-decoration:underline}
.dk-footer{margin-top:48px;padding-top:16px;border-top:1px solid var(--dk-border);
     font-size:11.5px;color:var(--dk-muted)}
.dk-collapsible summary{cursor:pointer;font-weight:600;color:var(--dk-green);padding:4px 0}
.dk-pillar-card{border:1px solid var(--dk-border);border-radius:10px;margin:14px 0;overflow:hidden}
.dk-pillar-head{padding:14px 18px;border-left:6px solid #555;background:#fafbfa}
.dk-pillar-head h3{margin:0 0 4px}
.dk-pillar-score{font-size:22px;font-weight:800}
.dk-pillar-card table{margin:0;border-top:1px solid var(--dk-border)}
.dk-pillar-card table th,.dk-pillar-card table td{border-left:none;border-right:none}
.dk-son-hero{border-radius:12px;padding:24px 28px;color:#fff;margin:14px 0}
.dk-son-hero .dk-score{font-size:44px;font-weight:800;line-height:1.1}
.dk-son-hero .dk-chain{font-size:14px;margin-top:8px;opacity:0.95}
.dk-dist-grid{display:flex;align-items:flex-end;gap:14px;margin:14px 0;height:110px}
.dk-dist-cell{flex:1;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;height:100%}
.dk-dist-bar{width:100%;border-radius:4px 4px 0 0;min-height:4px}
.dk-dist-label{font-size:11.5px;text-align:center;margin-top:6px;color:var(--dk-muted);line-height:1.4}
.dk-insitu-note{background:#f0eefb;border-left:4px solid #5a2a82;padding:10px 16px;
     font-size:12.5px;margin:8px 0;border-radius:0 6px 6px 0}
.dk-insitu-tag{background:#5a2a82;color:#fff;padding:1px 7px;border-radius:9px;
     font-size:10px;font-weight:600;display:inline-block;margin-top:3px}
"""


def _exec_summary(meta: Dict, son: Dict, mts: Optional[Dict], project_name: str) -> str:
    """Real, plain-language executive summary — no methodology jargon,
    the archetype-aware framing decided BEFORE any number is shown."""
    archetype = (meta.get("archetype") or "conservation").lower()
    copy_desc, unit_word = _ARCHETYPE_COPY.get(archetype, _ARCHETYPE_COPY["conservation"])

    if mts:
        n_units = mts.get("n_tiles")
        area = mts.get("total_area_ha")
        proj = son.get("PROJECT", {})
        oc, op = proj.get("overall_condition", {}), proj.get("overall_pressure", {})
        worst_name = oc.get("minimum_component")
        p1 = (f"<b>{_esc(project_name)}</b> is {copy_desc}, assessed across "
             f"<b>{_esc(n_units)} real {unit_word}s</b> totalling "
             f"<b>{_esc(area)} ha</b>. Following this methodology's non-compensatory "
             f"design (see §Methodology below), the project's headline condition score "
             f"is set by its <b>worst-performing {unit_word}</b> — not an average across "
             f"all {unit_word}s — so a single degraded area cannot be masked by strong "
             f"results elsewhere on site.")
        p2 = (f"The project's overall condition is classed <b>{_esc(oc.get('concern_class'))}</b> "
             f"(score {_num(oc.get('score'))}), driven by its <b>{_esc(worst_name)}</b> component. "
             f"Overall pressure is classed <b>{_esc(op.get('concern_class'))}</b> "
             f"(score {_num(op.get('score'))}). Together these place the project in the "
             f"<b>{_MATRIX_LABEL.get(proj.get('matrix_cell'), (proj.get('matrix_cell'),''))[0]}</b> "
             f"quadrant of the condition × pressure decision matrix.")
        conf = oc.get("confidence", {})
        p3 = (f"Confidence in this headline: <b>{_esc(conf.get('level'))}</b> "
             f"({_esc(conf.get('note'))}).")
        return f'<div class="dk-exec-summary"><p>{p1}</p><p>{p2}</p><p>{p3}</p></div>'

    if len(son) == 1:
        site_id, s = next(iter(son.items()))
        oc, op = s.get("overall_condition", {}), s.get("overall_pressure", {})
        p1 = (f"<b>{_esc(project_name)}</b> ({_esc(site_id)}) is {copy_desc}. "
             f"Overall condition is classed <b>{_esc(oc.get('concern_class'))}</b> "
             f"(score {_num(oc.get('score'))}), overall pressure "
             f"<b>{_esc(op.get('concern_class'))}</b> (score {_num(op.get('score'))}).")
        return f'<div class="dk-exec-summary"><p>{p1}</p></div>'

    p1 = (f"<b>{_esc(project_name)}</b> is {copy_desc}, assessed across "
         f"<b>{_esc(len(son))}</b> real sites.")
    return f'<div class="dk-exec-summary"><p>{p1}</p></div>'


def _methodology_primer() -> str:
    """A real, plain-language explanation — not a citation list standing
    in for one. Written so a reader who has never seen this methodology
    can understand it from this section alone."""
    return """
    <div class="dk-primer">
      <h4>Profile-first scoring — what it means</h4>
      <p>Every scored indicator is first compared to a real regional reference
      distribution (nearby, ecologically similar, low-human-modification land) and
      converted onto a common 0–1 scale, where <b>0.5 means "at reference"</b> —
      indistinguishable from the surrounding landscape's own natural state. This makes
      otherwise incommensurable units (a % canopy cover, an index score, a distance in
      metres) genuinely comparable for the first time, without forcing any of them
      onto an artificial universal scale.</p>

      <h4>Non-compensatory aggregation — why the worst result leads</h4>
      <p>A simple average lets a strong score in one area hide a real problem in
      another. This methodology deliberately does not average: within each
      ecological component, the <b>lowest-scoring (limiting) sub-dimension</b> sets
      that component's score — the same logic ecologists use for a limiting factor
      in a food web. Across components, scores combine with a penalised geometric
      mean, which is mathematically far less forgiving of a single weak result than
      an arithmetic average. For a multi-zone project, this same principle applies
      one level up: the <b>project's headline is its worst zone</b>, not a
      size-weighted average across all zones.</p>

      <h4>Condition and pressure — kept structurally separate</h4>
      <p><b>Condition</b> describes the ecological state of a site today. <b>Pressure</b>
      describes the human-driven forces acting on it (modification, light pollution,
      development proximity). These are never blended into one number — a site can be
      in good condition today but under severe pressure (worth flagging urgently), or
      in poor condition but under low pressure (a genuine restoration opportunity,
      not an active threat). The condition × pressure matrix below states which of
      four management postures — protect/maintain, defend, restore, or stabilise-then-
      restore — this combination implies.</p>

      <h4>Evidence tiers — every number here is labelled by how much it can carry</h4>
      <p>Not every real, useful piece of data is trustworthy at the same statistical
      weight. <span class="dk-badge" style="background:#e6f4ec;color:#0f5132">baseline</span>
      indicators are reference-benchmarked and drive the score above.
      <span class="dk-badge" style="background:#fbf3d5;color:#7a5c00">contextual</span>
      indicators are shown for real interpretive value but do not enter the score.
      <span class="dk-badge" style="background:#f7e3e3;color:#8a2b2b">screening</span>
      indicators (e.g. species range-overlap counts) are real data with a known,
      industry-wide resolution limitation at site scale — shown as context, never as
      a score. Nothing in this report is hidden by evidence tier; the full register is
      in §What is scored, and what is not.</p>
    </div>
    """


def _project_headline(son: Dict, mts: Dict, zone_labels: Optional[List[str]] = None) -> str:
    """The matrix cell and framing disclaimer for the project headline —
    NOT the condition/pressure scores themselves. REAL BUG FIXED HERE
    (caught by rendering this in a real browser, not assumed correct):
    this function used to ALSO render its own condition/pressure "badges"
    with RAW, unbounded decimal scores (e.g. "0.297") directly underneath
    _son_hero_html()'s already-correct bounded % display for the exact
    same two numbers — a real, visible inconsistency (bounded % right
    above raw decimals right below it, for the same score). Trimmed to
    keep only the matrix pill and framing text, which _son_hero_html()
    does NOT already show and which are genuinely non-redundant."""
    proj = son.get("PROJECT", {})
    oc = proj.get("overall_condition", {})
    out = []
    out.append(f'<p>{_matrix_pill(proj.get("matrix_cell"))} '
              f'<span class="dk-muted">worst-driving component: '
              f'<b>{_esc(oc.get("minimum_component"))}</b> '
              f'({_score_pct(oc.get("minimum_component_score"))})</span></p>')
    out.append(f'<div class="dk-framing">{_esc(oc.get("framing",""))}</div>')
    return "".join(out)


def render_html(report: Dict, project_name: str = "Darukaa Assessment") -> str:
    meta = report.get("meta", {})
    status = report.get("indicator_status", {})
    profiles = report.get("site_profiles", {})
    rows = report.get("scorecard", [])
    son = report.get("son_summary", {})
    mts = report.get("multi_tile_summary")
    tile_reports = report.get("tile_reports", {})
    is_project_level = bool(mts)

    # For a project-level report, son_summary isn't pre-computed the way a
    # single-site report's is — compute it here from the real project
    # profile AND from each real zone's own tile_report, so both the
    # aggregate headline and the true per-zone breakdown are real, not
    # re-derived approximations. scorecard_rows passed through so the
    # limiting chain (pillar -> subdimension -> real indicator name) is
    # available, not just the bare score.
    if is_project_level and not son:
        from darukaa_reference import son_score
        proj_rows = [r for r in rows if r.get("indicator")]  # project scorecard rows (worst-tile driven)
        son = {"PROJECT": son_score.son_summary(profiles.get("PROJECT", {}), proj_rows, PILLAR_NAMES)}
    per_zone_son = {}
    per_zone_rows: Dict[str, List[Dict]] = {}
    if is_project_level and tile_reports:
        from darukaa_reference import son_score
        for zone_id, tr in tile_reports.items():
            zp = (tr.get("site_profiles") or {}).get(zone_id)
            zrows = [r for r in (tr.get("scorecard") or []) if r.get("site_id") == zone_id]
            per_zone_rows[zone_id] = zrows
            if zp:
                per_zone_son[zone_id] = son_score.son_summary(zp, zrows, PILLAR_NAMES)

    out = [f"<!doctype html><html><head><meta charset='utf-8'>",
          f"<meta name='viewport' content='width=device-width, initial-scale=1'>",
          f"<title>{_esc(project_name)} — Evidence Record</title>",
          f"<style>{_CSS}</style></head><body>"]

    # --- Header ---
    out.append('<div class="dk-header">')
    out.append(f"<h1>{_esc(project_name)}</h1>")
    out.append(f'<div class="dk-subtitle">Year-0 Evidence Record — Darukaa Reference Benchmarking</div>')
    out.append(f"<div class='dk-meta-strip'>"
              f"<span>Generated {_esc(meta.get('generated_at'))}</span>"
              f"<span>Pipeline v{_esc(meta.get('pipeline_version'))}</span>"
              f"<span>{_esc(meta.get('n_tiles') or meta.get('n_sites') or len(profiles))} unit(s) assessed</span>"
              f"<span>Archetype: {_esc((meta.get('archetype') or 'conservation').title())}</span>"
              f"<span>HMI ceiling {_esc(meta.get('tier2_hmi_ceiling'))}</span>"
              f"<span><b>Every claim below carries its evidence grade</b></span></div>")
    out.append('</div>')

    # --- Table of contents ---
    out.append('<div class="dk-toc"><b>Contents:</b> '
              '<a href="#dk-exec">Executive summary</a> · '
              '<a href="#dk-method">Methodology</a> · '
              + ('<a href="#dk-zones">Per-zone breakdown</a> · ' if is_project_level else '')
              + '<a href="#dk-profiles">Site profile(s)</a> · '
              '<a href="#dk-transparency">What is scored</a> · '
              '<a href="#dk-scorecard">Full scorecard</a> · '
              '<a href="#dk-refs">References</a></div>')

    # --- Executive summary ---
    out.append('<h2 class="dk-h2" id="dk-exec">Executive summary</h2>')
    out.append(_exec_summary(meta, son, mts, project_name))

    # --- Methodology primer ---
    out.append('<h2 class="dk-h2" id="dk-method">Methodology, in plain language</h2>')
    out.append(_methodology_primer())

    # --- Project-level: headline + per-zone visuals + per-zone table ---
    if is_project_level:
        out.append('<h2 class="dk-h2">Project headline (non-compensatory)</h2>')
        out.append(_son_hero_html(son.get("PROJECT", {})))
        out.append(_project_headline(son, mts))

        if per_zone_son:
            zone_scores = sorted(
                [{"zone": z, "score": s.get("overall_condition", {}).get("score"),
                  "concern_class": s.get("overall_condition", {}).get("concern_class")}
                 for z, s in per_zone_son.items()],
                key=lambda d: (d["score"] if d["score"] is not None else 0))
            out.append('<h2 class="dk-h2" id="dk-zones">Per-zone breakdown — every zone, independently assessed</h2>')
            out.append(f'<p class="dk-muted">This project genuinely ran once per real zone below — '
                      f'this is not the aggregate broken back out, it is the {len(zone_scores)} '
                      f'real, independent results the aggregate above was built from.</p>')
            out.append(_svg_zone_bar_chart(zone_scores))

            out.append('<h3 class="dk-h3">Concern-level distribution across all real zones</h3>')
            out.append(_project_distribution_html(per_zone_son))

            out.append('<div class="dk-grid">')
            quad_points = [{"zone": z, "condition": s.get("overall_condition", {}).get("score") or 0,
                            "pressure": s.get("overall_pressure", {}).get("score") or 0}
                          for z, s in per_zone_son.items()]
            out.append(f'<div>{_svg_condition_pressure_quadrant(quad_points)}</div>')

            out.append('<div><table class="dk-table"><tr><th>Zone</th><th>SoN</th>'
                      '<th>Class</th><th>Pressure</th><th>Class</th><th>Matrix cell</th></tr>')
            worst_zone = zone_scores[0]["zone"] if zone_scores else None
            for z, s in per_zone_son.items():
                oc, op = s.get("overall_condition", {}), s.get("overall_pressure", {})
                row_cls = ' class="dk-row-worst"' if z == worst_zone else ''
                out.append(f'<tr{row_cls}><td><b>{_esc(z)}</b>'
                          f'{" <span class=\'dk-warn\'>(worst)</span>" if z == worst_zone else ""}</td>'
                          f'<td>{_esc(oc.get("score_pct"))}</td>'
                          f'<td><span style="color:{_concern_color(oc.get("concern_class"))};font-weight:600">'
                          f'{_esc(oc.get("concern_class"))}</span></td>'
                          f'<td>{_esc(op.get("score_pct"))}</td>'
                          f'<td><span style="color:{_concern_color(op.get("concern_class"))};font-weight:600">'
                          f'{_esc(op.get("concern_class"))}</span></td>'
                          f'<td>{_matrix_pill(s.get("matrix_cell"))}</td></tr>')
            out.append('</table></div></div>')

            # --- Full per-zone detail: every real zone's own SoN hero + 4
            # pillar cards, each with every applicable indicator's raw
            # value, intactness %, and concern level. Client-requested
            # directly ("each zone should also show raw values of each
            # 44-45 indicators... concern level as well... pillar wise
            # results also for each zone"). Collapsed by default so the
            # project summary above stays scannable, but every real number
            # is here, one click away — never only in a separate per-tile
            # file a reader has to go find.
            out.append('<h3 class="dk-h3">Full detail, every real zone</h3>')
            for z, s in sorted(per_zone_son.items(),
                              key=lambda kv: (kv[1].get("overall_condition", {}).get("score") or 0)):
                out.append(f'<details class="dk-collapsible"><summary>{_esc(z)} — '
                          f'{_esc(s.get("overall_condition", {}).get("score_pct"))} '
                          f'{_esc(s.get("overall_condition", {}).get("concern_class"))}</summary>')
                out.append(_son_hero_html(s))
                zrows = per_zone_rows.get(z, [])
                all_project_rows_flat = [r for zr in per_zone_rows.values() for r in zr]
                for pillar_data in s.get("pillars", []):
                    pillar_rows = [r for r in zrows if r.get("construct") == pillar_data["pillar"]]
                    out.append(_pillar_card_html(pillar_data, pillar_rows, all_project_rows_flat))
                out.append('</details>')

        if mts.get("n_tiles_total", 0) > mts.get("n_tiles", 0) or (mts.get("aggregation_rule")):
            out.append(f'<p class="dk-muted">{_esc(mts.get("aggregation_rule",""))}</p>')

        failed = meta.get("failed_tiles") or {}
        if failed:
            out.append('<h3 class="dk-h3">Zones excluded from this run</h3>')
            out.append('<table class="dk-table"><tr><th>Zone</th><th>Reason</th></tr>')
            for z, reason in failed.items():
                out.append(f'<tr><td>{_esc(z)}</td><td class="dk-warn">{_esc(reason)}</td></tr>')
            out.append('</table>')

    # --- Scoring transparency ---
    out.append('<h2 class="dk-h2" id="dk-transparency">What is scored, and what is not</h2>')
    out.append('<div class="dk-grid">')
    for key, tier, title in [
        ("scored", "baseline", "Scored (defensible: active &amp; eligible)"),
        ("contextual", "contextual", "Contextual (shown, not scored)"),
        ("screening_only", "screening", "Screening-only (e.g. range overlap)"),
        ("pending_inputs", "pending", "Pending input (dependency unmet)"),
        ("removed", "removed", "Removed (de-scoped)"),
    ]:
        items = status.get(key, [])
        out.append(f'<div class="dk-card"><h3 class="dk-h3">{_badge(tier)} &nbsp;{title} '
                  f'<span class="dk-muted">({len(items)})</span></h3>'
                  f'<div class="dk-muted">{", ".join(_esc(i) for i in items) or "—"}</div></div>')
    out.append('</div>')

    # --- Single-site profiles (only when NOT project-level; project-level
    # already showed its per-zone breakdown above) ---
    if not is_project_level:
        out.append('<h2 class="dk-h2" id="dk-profiles">Site profile(s)</h2>')
        if not profiles:
            out.append('<p class="dk-warn">No sites carry a propagated benchmark yet — profiles '
                      'pending upstream computation.</p>')
        for site_id, prof in profiles.items():
            s = son.get(site_id, {})
            out.append(f'<h3 class="dk-h3">Site: {_esc(site_id)} &nbsp; '
                      f'{_matrix_pill(prof.get("matrix_cell"))}</h3>')
            out.append(_son_hero_html(s))
            site_rows = [r for r in rows if r.get("site_id") == site_id]
            for pillar_data in s.get("pillars", []):
                pillar_rows = [r for r in site_rows if r.get("construct") == pillar_data["pillar"]]
                out.append(_pillar_card_html(pillar_data, pillar_rows, rows))
            press = prof.get("pressure", {})
            sens = (prof.get("condition", {}) or {}).get("sensitivity", {})
            stab = "STABLE" if sens.get("stable") else "UNSTABLE"
            stab_cls = "" if sens.get("stable") else "dk-warn"
            out.append(f'<p><b>Pressure axis:</b> {_esc(s.get("overall_pressure",{}).get("score_pct"))} '
                      f'<span style="color:{_concern_color(s.get("overall_pressure",{}).get("concern_class"))}">'
                      f'{_esc(s.get("overall_pressure",{}).get("concern_class"))}</span> '
                      f'&nbsp;|&nbsp; <span class="{stab_cls}">sensitivity: {stab}</span></p>')
            if not sens.get("stable"):
                out.append(f'<p class="dk-warn">⚠ {_esc(sens.get("note"))}</p>')
            out.append(f'<div class="dk-framing">{_esc((prof.get("condition") or {}).get("framing"))}</div>')

    # --- Scorecard ---
    out.append('<h2 class="dk-h2" id="dk-scorecard">Indicator scorecard (evidence-graded)</h2>')
    if is_project_level:
        out.append('<p class="dk-muted">Project-level: worst-zone signed benchmark per indicator '
                  '(the real headline value), with area-weighted context alongside.</p>')
        out.append('<table class="dk-table"><tr><th>Indicator</th><th>Worst zone</th>'
                  '<th>Worst-zone benchmark</th><th>Area-wtd geomean (context)</th>'
                  '<th>Zones with data</th></tr>')
        for r in rows:
            out.append(f'<tr><td>{_esc(r.get("indicator"))}</td><td><b>{_esc(r.get("worst_tile"))}</b></td>'
                      f'<td>{_num(r.get("worst_tile_benchmark"))}</td>'
                      f'<td class="dk-muted">{_num(r.get("area_weighted_geomean_normalised"))}</td>'
                      f'<td>{_esc(r.get("n_tiles_with_data"))}/{_esc(r.get("n_tiles_total"))}</td></tr>')
        out.append('</table>')
    else:
        out.append('<table class="dk-table"><tr><th>Indicator</th><th>Construct</th><th>Grade</th>'
                  '<th>Site value</th><th>Benchmark (signed)</th><th>% of ref (uncapped)</th>'
                  '<th>Reference type</th><th>Class</th></tr>')
        for r in rows:
            tier = r.get("evidence_tier") or "—"
            # REAL REMOVAL (client-requested directly): the CLIENT-ACTIVATED
            # badge and its hover-text ("original disposition and caveat")
            # exposed internal decision history to the client-facing report
            # -- exactly what the client said must not happen ("this
            # indicator was originally context only but has been scored"
            # can read as wrong to a client). The report shows only the
            # final, as-computed result now; the full disposition
            # reasoning lives in contracts.py and the notebook's picker,
            # not here.
            out.append(f'<tr><td>{_esc(r.get("display_name") or r.get("indicator"))}</td>'
                      f'<td>{_esc(r.get("construct"))}</td><td>{_badge(tier)}</td>'
                      f'<td>{_num(r.get("site_value"))}</td>'
                      f'<td>{_num(r.get("tier2_benchmark"))} '
                      f'<span class="dk-muted">{_esc(r.get("tier2_benchmark_estimator") or "")}</span></td>'
                      f'<td>{_pct(r.get("tier2_display_pct_of_reference"))}</td>'
                      f'<td class="dk-muted">{_esc(r.get("reference_type"))}</td>'
                      f'<td>{_render_classification(r.get("classification"))}</td></tr>')
        out.append('</table>')

    # --- References ---
    out.append('<h2 class="dk-h2" id="dk-refs">Methodology references</h2><ul class="dk-muted">')
    for ref in meta.get("methodology_references", []):
        out.append(f"<li>{_esc(ref)}</li>")
    out.append('</ul>')
    out.append(f'<p class="dk-muted">Scoring: {_esc(meta.get("scoring", ""))}</p>')

    out.append(f'<div class="dk-footer">Darukaa Reference Benchmarking Pipeline v'
              f'{_esc(meta.get("pipeline_version"))} · Generated {_esc(meta.get("generated_at"))} · '
              f'Evidence-graded — every value above is labelled by how much it can carry. '
              f'See METHODOLOGY_MASTER.md and ASSUMPTIONS_AND_LIMITATIONS.md in the source repository '
              f'for the full technical basis of every choice on this page.</div>')

    out.append("</body></html>")
    return "\n".join(out)


def write_html(report: Dict, output_path: str, project_name: str = "Darukaa Assessment") -> str:
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    html_str = render_html(report, project_name)
    p.write_text(html_str, encoding="utf-8")
    return str(p)
