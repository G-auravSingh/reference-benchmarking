"""End-to-end assessment: units -> measurements -> references -> scores -> outputs.

This replaces the earlier ``AdaptivePipeline`` orchestration (decisions D-23-1 to
D-23-14). Earth Engine must be initialised by the caller (the Colab notebook).
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from . import catalogue as cat
from . import natural_mask as nm
from .config import VERSION, AssessmentConfig
from .ee_utils import evaluate, to_ee, utm_crs
from .extraction import Unit, measure_units, month_starts, pick_peak_window
from .inputs import ProjectInput
from .layers import AREAL_METRICS, monthly_ndvi_means
from .measurement import Measurement, status_layers
from .reference_pool import (ConditionPool, build_condition_pool, regional_blocks, regional_sample,
                             same_ecoregion, select_low_pressure_blocks)
from .scorecard import (SON_DIVERGENCE_POINTS, SON_LABEL, Headline, MetricScore, PillarResult, ReferenceSample,
                        aggregate_pillar, area_weighted, coverage_label, headline, lowest_confidence, score_metric, _interval)
from .site import projected_buffer
from .units import AssessmentUnits, Site, build_units

log = logging.getLogger(__name__)
FINE_SCALE_M = 30.0


@dataclass
class AssessmentResult:
    project_id: str
    config: AssessmentConfig
    units: AssessmentUnits
    roles: Dict[str, cat.RoleDecision]
    peak_window: Tuple[str, str]
    peak_basis: str
    measurements: List[Measurement]
    scores: List[MetricScore]
    pillars: List[PillarResult]
    headlines: List[Headline]
    project: Dict[str, Any]
    references: Dict[str, Any]
    flags: List[Dict[str, str]] = field(default_factory=list)


# --------------------------------------------------------------------- scoring helpers
def score_with_strata(m: Measurement, role: str, pool: Optional[ConditionPool], cfg: AssessmentConfig) -> MetricScore:
    """Benchmark each natural type against its own reference stratum, then area-weight.

    Fine metrics (<= 30 m) carry per-stratum means; coarse metrics are benchmarked
    against the pooled least-disturbed natural sample (their pixels mix types).
    """
    c = cat.get(m.metric)
    n, seed = cfg.scoring.n_bootstrap, cfg.scoring.bootstrap_seed
    by = m.extras.get("by_stratum") if m.measured_valid else None
    if pool is None or not by or (c.native_scale_m or 0) > FINE_SCALE_M:
        ref = pool.get(m.metric, "natural_all") if pool is not None else None
        return score_metric(m, role, ref, n, seed)
    parts, total_w, scored_w = [], 0.0, 0.0
    for code, d in by.items():
        if code not in nm.NATURAL_STRATA or d.get("weight") in (None, 0):
            continue
        total_w += d["weight"]
        ref = pool.get(m.metric, code)
        if ref is None or not ref.usable:
            continue
        sub = Measurement(m.metric, m.unit_id, m.level, d["mean"], m.status, covered_pixel_equivalent=m.covered_pixel_equivalent,
                          context_buffer_m=m.context_buffer_m, period_gap_years=m.period_gap_years)
        s = score_metric(sub, role, ref, n, seed)
        if s.score is not None:
            parts.append((d["weight"], s))
            scored_w += d["weight"]
    base = score_metric(m, role, None, n, seed)  # carries the role / validity outcome
    if role != "scored" or not m.measured_valid:
        return base
    if not parts or total_w <= 0 or scored_w / total_w < cfg.scoring.min_stratum_weight_share:
        base.reference_status = "reference_insufficient_for_unit_types"
        base.basis = f"usable reference for {100 * scored_w / total_w if total_w else 0:.0f}% of the unit's natural area"
        return base
    w = np.array([p[0] for p in parts])
    score = float(np.sum(w * np.array([p[1].score for p in parts])) / w.sum())
    draws = np.sum(w[:, None] * np.vstack([p[1].draws for p in parts]), axis=0) / w.sum()
    first = parts[0][1]
    worst_conf = sorted((p[1].confidence for p in parts), key=["High", "Medium", "Low"].index)[-1]
    reasons = sorted({r for p in parts for r in p[1].confidence_reasons})
    return MetricScore(m.metric, m.unit_id, c.pillar, c.component, role, m.value, score, _interval(draws), draws, "ok",
                       None, None, sum(p[1].reference_n or 0 for p in parts), None,
                       f"type-matched attainment over {len(parts)} type(s), {100 * scored_w / total_w:.0f}% of natural area",
                       worst_conf, reasons)


def period_gap(m: Measurement, window_end_year: int) -> float:
    """Years between the data used and the assessment window, from the recorded period."""
    import re
    years = [int(y) for y in re.findall(r"(?<!\d)(20\d\d|19\d\d)(?!\d)", m.effective_period or "")]
    extras = m.extras if isinstance(m.extras, dict) else {}
    extra_year = extras.get("bii_year")
    if isinstance(extra_year, (int, float)):
        years.append(int(extra_year))
    end = extras.get("period_end")          # exclusive "YYYY-MM" end of the data actually used
    if isinstance(end, str) and re.fullmatch(r"\d{4}-\d{2}", end):
        y, mo = int(end[:4]), int(end[5:])
        years.append(y - 1 if mo == 1 else y)
    if not years:
        return 0.0
    return float(max(0, window_end_year - max(years)))


# --------------------------------------------------------------------- main entry
def run_assessment(project: ProjectInput, config: AssessmentConfig, boundary: Optional[BaseGeometry] = None,
                   progress=print) -> AssessmentResult:
    errors = config.validate()
    if errors:
        raise ValueError("Invalid configuration: " + "; ".join(errors))
    start, end_excl = config.window_exclusive()
    window_end_year = int(config.window_end[:4])
    units = build_units(project, boundary, config.site_cluster_distance_m)
    roles = cat.resolve_roles(config.scoring.role_mode, config.scoring.metric_overrides, config.scoring.include_proposed)
    active = [c for c in cat.active(config.scoring.include_proposed)]
    site_metrics = [c.id for c in active if c.level in ("site", "site_and_emu")]
    emu_metrics = [c.id for c in active if c.level in ("emu", "site_and_emu")]
    flags: List[Dict[str, str]] = [{"severity": "INFO", "code": f, "message": f} for f in units.flags]

    footprint = units.footprint()
    crs = utm_crs(footprint)
    progress(f"[1/6] Units: {len(units.sites)} site(s), {sum(len(s.emus) for s in units.sites)} EMU(s); CRS {crs}")

    # Peak-greenness window (Plan Vivo Pillar 4 convention), one per project so that
    # every site and its reference use the same window.
    months = month_starts(start, end_excl)
    # Window chosen over the sites plus 1 km (D-25-2): small or patchy sites (agroforestry,
    # fragments) otherwise pick a window from too few clear pixels.
    peak_region = to_ee(projected_buffer(footprint, config.options.get("peak_window_buffer_m", 1000.0)))
    raw = evaluate(monthly_ndvi_means(peak_region, months, crs, config.options.get("s2_cloud_prob_max", 50.0)))
    monthly = {k: (v if isinstance(v, (int, float)) else None) for k, v in raw.items()}
    peak, peak_basis = pick_peak_window(monthly, months)
    progress(f"[2/6] Peak window {peak[0]}..{peak[1]} ({peak_basis})")

    from .natural_mask import build_mask
    # The collections behind the mask are filtered to an area that covers the sites,
    # their context windows and the whole reference ring.
    filter_region = to_ee(projected_buffer(footprint, config.pool.radius_km * 1000.0 + 2000.0))
    mask, dw_count = build_mask(filter_region, start, end_excl, config.natural_mask_min_probability, crs=crs)
    ctx_base = {"crs": crs, "start": start, "end_exclusive": end_excl, "mask": mask, "peak_window": peak,
                "raster_paths": dict(config.raster_paths), "options": dict(config.options)}

    measurements: List[Measurement] = []
    for s in units.sites:
        progress(f"[3/6] Measuring {s.site_id} ({s.area_ha:.1f} ha, {len(s.emus)} EMU)")
        measurements += measure_units([Unit(s.site_id, "site", s.geometry)], site_metrics, ctx_base, config.min_support_px)
        single = len(s.emus) == 1 and s.boundary_source == "emu_union"
        if not single:
            measurements += measure_units([Unit(e.emu_id, "emu", e.geometry) for e in s.emus], emu_metrics, ctx_base,
                                          config.min_support_px)
    for m in measurements:
        m.period_gap_years = period_gap(m, window_end_year)
        if m.metric == "tree_cover_loss_rate" and m.extras.get("baseline_forest_ha") is not None:
            m.extras["low_baseline_flag"] = m.extras["baseline_forest_ha"] < config.options.get("low_forest_baseline_ha", 5.0)

    # Condition reference (Approach 2), one pool per project footprint.
    scored_now = {mid for mid, d in roles.items() if d.applied_role == "scored"}
    progress("[4/6] Building the condition reference pool")
    pool: Optional[ConditionPool] = None
    if any(cat.get(m).reference_type == "reference_condition" for m in scored_now):
        try:
            pool = build_condition_pool(footprint, ctx_base, config.pool)
        except Exception as exc:  # noqa: BLE001 - recorded; condition metrics then cannot be scored
            flags.append({"severity": "REVIEW", "code": "condition_reference_failed", "message": str(exc)})

    # Regional blocks (Approach 4) feed two references:
    #  * regional_context metrics (P1 loss rates, managed land): all ring blocks;
    #  * low_pressure metrics (P4, option B, D-25-1): reference = blocks selected by 2020
    #    natural share (not by any pressure metric); worst = p95 of all ring blocks.
    progress("[5/6] Measuring regional reference blocks")
    regional: Dict[Tuple[str, str], ReferenceSample] = {}
    low_ref: Dict[Tuple[str, str], ReferenceSample] = {}
    regional_ids = sorted(m for m in scored_now if cat.get(m).reference_type in ("regional_context", "low_pressure"))
    block_ids = sorted(set(regional_ids) | {"natural_extent_pct"})
    block_info: Dict[str, Any] = {}
    for s in units.sites:
        if not regional_ids:
            break
        try:
            blocks = same_ecoregion(regional_blocks(s.geometry, footprint, config.pool), footprint)
        except Exception as exc:  # noqa: BLE001
            flags.append({"severity": "REVIEW", "code": "regional_blocks_failed", "message": f"{s.site_id}: {exc}"})
            continue
        bms = measure_units([Unit(b, "reference_block", g) for b, g, _ in blocks], block_ids, ctx_base, config.min_support_px)
        cells = {b: cell for b, _, cell in blocks}
        nat2020 = {m.unit_id: m.extras.get("natural_2020_pct") for m in bms
                   if m.metric == "natural_extent_pct" and m.measured_valid}
        low_ids, stage = select_low_pressure_blocks(nat2020, config.pool)
        radius_used = config.pool.radius_km
        low_values = {(m.unit_id, m.metric): m for m in bms}
        # D-26-1: too few qualifying blocks -> widen the search (same ecoregion), measuring
        # natural share first and pressure metrics only on the blocks that qualify.
        prev_km = config.pool.radius_km
        lp_ids = sorted(m for m in regional_ids if cat.get(m).reference_type == "low_pressure")
        for outer_km in config.pool.low_pressure_search_radii_km:
            if low_ids or not lp_ids:
                break
            try:
                extra = same_ecoregion(regional_blocks(s.geometry, footprint, config.pool, inner_m=prev_km * 1000.0,
                                                       outer_km=outer_km, prefix=f"W{int(outer_km)}_"), footprint)
            except Exception as exc:  # noqa: BLE001
                flags.append({"severity": "REVIEW", "code": "low_pressure_widening_failed", "message": f"{s.site_id}: {exc}"})
                break
            nat_ms = measure_units([Unit(b, "reference_block", g) for b, g, _ in extra], ["natural_extent_pct"], ctx_base,
                                   config.min_support_px)
            nat2020.update({m.unit_id: m.extras.get("natural_2020_pct") for m in nat_ms if m.measured_valid})
            cells.update({b: cell for b, _, cell in extra})
            low_ids, stage = select_low_pressure_blocks(nat2020, config.pool)
            new = [(b, g) for b, g, _ in extra if b in set(low_ids)]
            if new:
                for m in measure_units([Unit(b, "reference_block", g) for b, g in new], lp_ids, ctx_base, config.min_support_px):
                    low_values[(m.unit_id, m.metric)] = m
            radius_used, prev_km = outer_km, outer_km
        block_info[s.site_id] = {"n_blocks": len(blocks), "low_pressure_blocks": len(low_ids), "low_pressure_stage": stage,
                                 "low_pressure_radius_km": radius_used}
        for mid in regional_ids:
            vals = {m.unit_id: (m.value if m.measured_valid else None) for m in bms if m.metric == mid}
            regional[(s.site_id, mid)] = regional_sample(mid, vals, cells, config.pool)
            if cat.get(mid).reference_type == "low_pressure":
                sub = {b: (low_values[(b, mid)].value if (b, mid) in low_values and low_values[(b, mid)].measured_valid else None)
                       for b in low_ids}
                rs = regional_sample(mid, sub, cells, config.pool)
                rs.method = f"low-pressure blocks ({stage}; search radius {radius_used:g} km)"
                rs.min_n = min(config.pool.min_n, config.pool.low_pressure_min_blocks)
                low_ref[(s.site_id, mid)] = rs

    # Scores
    progress("[6/6] Scoring")
    site_of_emu = {e.emu_id: s.site_id for s in units.sites for e in s.emus}
    scores: List[MetricScore] = []
    nb, seed = config.scoring.n_bootstrap, config.scoring.bootstrap_seed
    for m in measurements:
        c = cat.get(m.metric)
        role = roles[m.metric].applied_role
        sid = m.unit_id if m.level == "site" else site_of_emu.get(m.unit_id)
        if c.reference_type == "regional_context":
            scores.append(score_metric(m, role, regional.get((sid, m.metric)), nb, seed))
        elif c.reference_type == "low_pressure":
            sc = score_metric(m, role, low_ref.get((sid, m.metric)), nb, seed, worst_ref=regional.get((sid, m.metric)))
            ctx = regional.get((sid, m.metric))
            if role == "scored" and m.measured_valid and ctx is not None and ctx.usable:
                a = ReferenceSample(m.metric, "regional_context", ctx.values, ctx.blocks, min_n=ctx.min_n, min_blocks=ctx.min_blocks)
                med, p95 = float(np.median(a.values)), float(np.percentile(a.values, 95))
                from .scorecard import bounded_regional, ghm_class
                sc.context_score = bounded_regional(float(m.value), med, p95, c.direction, c.value_range[1])[0]
            if m.metric == "ghm" and m.measured_valid:
                from .scorecard import ghm_class
                sc.absolute_class = ghm_class(float(m.value))
            scores.append(sc)
        elif c.reference_type == "reference_condition":
            scores.append(score_with_strata(m, role, pool, config))
        else:
            scores.append(score_metric(m, role, None, nb, seed))

    pillars: List[PillarResult] = []
    headlines: List[Headline] = []
    unit_ids = [(s.site_id, "site") for s in units.sites] + [(e.emu_id, "emu") for s in units.sites for e in s.emus]
    for uid, level in unit_ids:
        us = [s for s in scores if s.unit_id == uid]
        if not us:
            continue
        pills = {p: aggregate_pillar(us, uid, p, config.scoring.min_metrics_per_pillar, config.scoring.min_components_per_pillar)
                 for p in ("P1", "P2", "P3", "P4", "M")}
        pillars += list(pills.values())
        if level == "site":
            headlines.append(headline(pills, uid))

    # Project roll-up across sites (D-23-6)
    site_area = {s.site_id: s.area_ha for s in units.sites}
    project: Dict[str, Any] = {"n_sites": len(units.sites), "total_site_area_ha": units.total_site_area_ha}
    son = area_weighted([(h.unit_id, site_area[h.unit_id], h.son_score, h.son_draws) for h in headlines])
    pres = area_weighted([(h.unit_id, site_area[h.unit_id], h.pressure_score, h.pressure_draws) for h in headlines])
    project["pressure"] = pres.__dict__
    project["pressure"]["confidence"] = lowest_confidence([h.pressure_confidence for h in headlines if h.pressure_score is not None])
    for p in ("P1", "P2", "P3", "P4"):
        rows = [pr for pr in pillars if pr.pillar == p and pr.unit_id in site_area]
        project[p] = area_weighted([(pr.unit_id, site_area[pr.unit_id], pr.score, pr.draws) for pr in rows]).__dict__
        project[p]["confidence"] = lowest_confidence([pr.limiting_confidence for pr in rows if pr.score is not None])
        lim = [pr for pr in rows if pr.score is not None]
        project[p]["limiting_metrics"] = sorted({pr.limiting_metric for pr in lim if pr.limiting_metric})
    project["son"] = son_rollup(son, headlines, project)
    project["restoration"] = restoration_summary(measurements, units)
    project["nature_positive_coverage"] = nature_positive_coverage(scores, roles)

    refs = {"condition_pool": (pool.summary() if pool else []), "ecoregion": (pool.ecoregion if pool else None),
            "condition_points": (pool.n_points if pool else 0), "regional_blocks": block_info,
            "peak_window": list(peak), "peak_basis": peak_basis}
    for s in scores:
        if s.role == "scored" and s.score is None and s.reference_status not in {"no_valid_measurement", "not_scored_role"}:
            flags.append({"severity": "REVIEW", "code": "scored_metric_without_score",
                          "message": f"{s.unit_id}/{s.metric}: {s.reference_status}"})
    return AssessmentResult(project.get("project_id", units.project_id), config, units, roles, peak, peak_basis,
                            measurements, scores, pillars, headlines, project, refs, flags)


def son_rollup(son, headlines: Sequence[Headline], project: Dict[str, Any]) -> Dict[str, Any]:
    """Project SoN score (area-weighted over sites) with the same companions as the site score (P-27-2)."""
    out = dict(son.__dict__)
    scored = [h for h in headlines if h.son_score is not None]
    pillars = sorted({p for h in scored for p in h.son_pillars})
    state = {p: project[p]["value"] for p in ("P1", "P2", "P3") if p in pillars and project[p]["value"] is not None}
    weakest = min(state, key=state.get) if state else None
    out.update({
        "label": f"{SON_LABEL}; {son.label}",
        "pillars": pillars, "coverage_label": coverage_label(pillars) if pillars else "",
        "confidence": lowest_confidence([h.son_confidence for h in scored]) if scored else None,
        "weakest_pillar": weakest, "weakest_pillar_score": state.get(weakest) if weakest else None,
        "divergence_flag": None})
    if out["value"] is not None and weakest and out["value"] - state[weakest] > SON_DIVERGENCE_POINTS:
        out["divergence_flag"] = (f"SoN score {out['value']:.1f} exceeds the weakest pillar {weakest} ({state[weakest]:.1f}) "
                                  f"by more than {SON_DIVERGENCE_POINTS:.0f} points: the composite hides a weak pillar")
    return out


GAIN_KEYS = ("gain_trees_ha", "gain_shrub_and_scrub_ha", "gain_grass_ha", "gain_flooded_vegetation_ha", "gain_water_ha")
LOSS_KEYS = ("loss_from_natural_forest_ha", "loss_from_other_natural_ha", "loss_to_crops_ha", "loss_to_built_ha")


def restoration_summary(measurements: Sequence[Measurement], units: AssessmentUnits) -> Dict[str, Any]:
    """Gross loss and candidate gross gain by type per site, never netted (Nature Positive rule).

    A site whose loss or gain measurement is not valid contributes no number; the total
    then says it is partial instead of treating the site as zero.
    """
    by = {(m.unit_id, m.metric): m for m in measurements if m.level == "site"}
    rows = []
    for s in units.sites:
        g = by.get((s.site_id, "natural_gross_gain_ha"))
        l = by.get((s.site_id, "natural_gross_loss_pct"))
        g_ok = g is not None and g.status == "ok" and g.value is not None
        l_ok = l is not None and l.status == "ok"
        row = {"site_id": s.site_id, "area_ha": s.area_ha,
               "candidate_gain_ha": g.value if g_ok else None, "gain_status": g.status if g else "not_run",
               "gross_loss_ha": (l.extras or {}).get("gross_loss_ha") if l_ok else None,
               "loss_status": l.status if l else "not_run"}
        for k in GAIN_KEYS:
            row[k] = (g.extras or {}).get(k) if g_ok else None
        for k in LOSS_KEYS:
            row[k] = (l.extras or {}).get(k) if l_ok else None
        rows.append(row)

    def total(key):
        vals = [r[key] for r in rows]
        known = [v for v in vals if v is not None]
        return {"value": sum(known) if known else None, "sites_with_value": len(known), "sites": len(vals),
                "partial": len(known) < len(vals)}
    return {"sites": rows, "totals": {k: total(k) for k in ("candidate_gain_ha", "gross_loss_ha") + GAIN_KEYS + LOSS_KEYS},
            "note": "Gross figures by type; never netted. Gain is a candidate: Dynamic World cannot confirm natural status."}


def nature_positive_coverage(scores: Sequence[MetricScore], roles: Dict[str, cat.RoleDecision]) -> List[Dict[str, str]]:
    """Comply-or-explain table for the four Nature Positive indicators (TOR p.83)."""
    def any_scored(pillar):
        return any(s.pillar == pillar and s.score is not None for s in scores)
    return [
        {"indicator": "Ecosystem extent", "covered": "yes (preparatory)" if any_scored("P1") else "no",
         "how": "ForTy 2020 + SBTN v1.1 natural mask; gross loss and candidate gain since 2020 by type"},
        {"indicator": "Ecosystem condition", "covered": "yes (preparatory)" if any_scored("P2") else "no",
         "how": "remote-sensing condition metrics on natural pixels against least-disturbed reference; landscape connectivity pending"},
        {"indicator": "Species extinction risk", "covered": "no",
         "how": "IUCN/STAR/LIFE data need a commercial licence Darukaa does not hold; range-overlap counts shown as diagnostics only"},
        {"indicator": "Species populations", "covered": "no",
         "how": "needs repeated in-situ surveys; open occurrence records shown as screening only"},
    ]
