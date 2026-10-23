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
                             same_ecoregion)
from .scorecard import (Headline, MetricScore, PillarResult, ReferenceSample, aggregate_pillar, area_weighted,
                        headline, score_metric, _interval)
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
    extra_year = m.extras.get("bii_year") if isinstance(m.extras, dict) else None
    if isinstance(extra_year, (int, float)):
        years.append(int(extra_year))
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
    raw = evaluate(monthly_ndvi_means(to_ee(footprint), months, crs, config.options.get("s2_cloud_prob_max", 50.0)))
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

    # Regional context (Approach 4): blocks with each site's areal support.
    progress("[5/6] Measuring regional reference blocks")
    regional: Dict[Tuple[str, str], ReferenceSample] = {}
    regional_ids = sorted(m for m in scored_now if cat.get(m).reference_type == "regional_context")
    block_info: Dict[str, Any] = {}
    for s in units.sites:
        if not regional_ids:
            break
        try:
            blocks = same_ecoregion(regional_blocks(s.geometry, footprint, config.pool), footprint)
        except Exception as exc:  # noqa: BLE001
            flags.append({"severity": "REVIEW", "code": "regional_blocks_failed", "message": f"{s.site_id}: {exc}"})
            continue
        block_info[s.site_id] = {"n_blocks": len(blocks)}
        bms = measure_units([Unit(b, "reference_block", g) for b, g, _ in blocks], regional_ids, ctx_base, config.min_support_px)
        cells = {b: cell for b, _, cell in blocks}
        for mid in regional_ids:
            vals = {m.unit_id: (m.value if m.measured_valid else None) for m in bms if m.metric == mid}
            regional[(s.site_id, mid)] = regional_sample(mid, vals, cells, config.pool)

    # Scores
    progress("[6/6] Scoring")
    site_of_emu = {e.emu_id: s.site_id for s in units.sites for e in s.emus}
    scores: List[MetricScore] = []
    for m in measurements:
        c = cat.get(m.metric)
        role = roles[m.metric].applied_role
        if c.reference_type == "regional_context":
            sid = m.unit_id if m.level == "site" else site_of_emu.get(m.unit_id)
            scores.append(score_metric(m, role, regional.get((sid, m.metric)), config.scoring.n_bootstrap, config.scoring.bootstrap_seed))
        elif c.reference_type == "reference_condition":
            scores.append(score_with_strata(m, role, pool, config))
        else:
            scores.append(score_metric(m, role, None, config.scoring.n_bootstrap, config.scoring.bootstrap_seed))

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
    cond = area_weighted([(h.unit_id, site_area[h.unit_id], h.condition_score, h.condition_draws) for h in headlines])
    pres = area_weighted([(h.unit_id, site_area[h.unit_id], h.pressure_score, h.pressure_draws) for h in headlines])
    project["condition"] = cond.__dict__
    project["pressure"] = pres.__dict__
    for p in ("P1", "P2", "P3", "P4"):
        rows = [pr for pr in pillars if pr.pillar == p and pr.unit_id in site_area]
        project[p] = area_weighted([(pr.unit_id, site_area[pr.unit_id], pr.score, pr.draws) for pr in rows]).__dict__
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
