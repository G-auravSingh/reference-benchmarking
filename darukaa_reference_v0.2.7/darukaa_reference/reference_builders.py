"""
reference_builders.py -- numpy definitions of the corrected v0.2.8 constructs (Phase 3)
=======================================================================================

Each builder returns a ReferenceData that EXPOSES its reference population definition and
reference_n, and each site-side function computes the SAME construct with the SAME rule,
so that the compatibility check in benchmarking.py can be passed for the right reasons.

These are the executable definitions the Earth Engine code mirrors (they share constants
via constructs.py). Synthetic fixtures with known answers test them in
tests/test_phase3_indicators.py.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Optional

import numpy as np
from scipy import ndimage

from darukaa_reference import constructs as K
from darukaa_reference import indicator_contract as IC
from darukaa_reference import support as S
from darukaa_reference.benchmarking import MetricSpec, ReferenceData


# ----------------------------------------------------------------------------------------
# Site-sized cell references (proportions, means, rates): TESSELLATION CELLS (see support.py)
# ----------------------------------------------------------------------------------------
def _thin(values: np.ndarray, max_n: Optional[int], seed: int) -> np.ndarray:
    if max_n and values.size > max_n:
        return np.random.default_rng(seed).choice(values, max_n, replace=False)
    return values


def _cell_ref(cells: np.ndarray, cell_px: int, site_area_m2: float, native_scale_m: float, support: str,
              construct: str, unit: str, temporal: str, population: str, tier: str, population_definition: str,
              eligible_cells: Optional[np.ndarray], max_n: Optional[int], seed: int,
              extra: Optional[Dict] = None) -> ReferenceData:
    c = cells if eligible_cells is None else np.where(np.asarray(eligible_cells, bool), cells, np.nan)
    vals = c[np.isfinite(c)]
    n_before = int(vals.size)
    vals = _thin(vals, max_n, seed)
    spec = MetricSpec(construct, unit, temporal, support, population,
                      window_area_m2=float(cell_px * native_scale_m) ** 2, native_scale_m=native_scale_m)
    diag = {"cell_px": cell_px, "cell_side_m": cell_px * native_scale_m,
            "cell_area_m2": float(cell_px * native_scale_m) ** 2, "site_area_m2": site_area_m2,
            "n_cells_before_thinning": n_before,
            "cells_centred_on": "eligible cells only" if eligible_cells is not None else "all valid cells"}
    diag.update(extra or {})
    return ReferenceData(vals, spec, tier, population_definition, diag)


def window_proportion_reference(binary, valid, site_area_m2, native_scale_m, *, construct, unit, temporal,
                                population, tier, population_definition, eligible=None, max_n=None, seed=0,
                                scale_to_percent=False, offset=(0, 0)):
    k = S.cell_size_px(site_area_m2, native_scale_m)
    cells = S.block_mean(np.asarray(binary, float), valid, k, offset)
    if scale_to_percent:
        cells = cells * 100.0
    el = None if eligible is None else S.block_centres(eligible, k, offset)
    return _cell_ref(cells, k, site_area_m2, native_scale_m, "site_window_proportion", construct, unit, temporal,
                     population, tier, population_definition, el, max_n, seed)


def window_mean_reference(values, valid, site_area_m2, native_scale_m, *, construct, unit, temporal,
                          population, tier, population_definition, eligible=None, max_n=None, seed=0, offset=(0, 0)):
    k = S.cell_size_px(site_area_m2, native_scale_m)
    cells = S.block_mean(np.asarray(values, float), valid, k, offset)
    el = None if eligible is None else S.block_centres(eligible, k, offset)
    return _cell_ref(cells, k, site_area_m2, native_scale_m, "site_window_mean", construct, unit, temporal,
                     population, tier, population_definition, el, max_n, seed)


def window_rate_reference(numerator, denominator, site_area_m2, native_scale_m, years, *, construct, unit,
                          temporal, population, tier, population_definition, pixel_area_m2,
                          min_denominator_area_m2=0.0, eligible=None, max_n=None, seed=0, offset=(0, 0)):
    k = S.cell_size_px(site_area_m2, native_scale_m)
    cells = S.block_rate(numerator, denominator, k, years, pixel_area_m2, min_denominator_area_m2, offset)
    el = None if eligible is None else S.block_centres(eligible, k, offset)
    return _cell_ref(cells, k, site_area_m2, native_scale_m, "site_window_rate", construct, unit, temporal,
                     population, tier, population_definition, el, max_n, seed,
                     {"min_cell_denominator_area_m2": min_denominator_area_m2})


def site_mean(values, polygon, valid=None) -> Optional[float]:
    v = np.asarray(values, float)
    m = np.asarray(polygon, bool) & np.isfinite(v)
    if valid is not None:
        m &= np.asarray(valid, bool)
    return float(v[m].mean()) if m.any() else None


@dataclass
class Case:
    """Site value + its spec + the matched reference, ready for benchmarking.evaluate_indicator."""
    site_value: Optional[float]
    site_spec: MetricSpec
    reference: ReferenceData
    site_area_m2: float
    extras: Dict = field(default_factory=dict)


# ----------------------------------------------------------------------------------------
# forest_loss_rate  (E1)
# ----------------------------------------------------------------------------------------
def forest_loss_terms(lossyear, treecover2000, first_code, last_code):
    """Numerator = loss INSIDE the >=30 % canopy baseline; denominator = that baseline.

    v0.2.7 counted loss on any pixel with canopy > 0 % against a >=30 % baseline: the
    numerator was not a subset of the denominator."""
    forest = np.asarray(treecover2000) >= K.HANSEN_CANOPY_THRESHOLD_PCT
    ly = np.asarray(lossyear)
    loss = (ly >= first_code) & (ly <= last_code) & (ly > 0) & forest
    return loss.astype(float), forest.astype(float), K.years_in_window(first_code, last_code)


def forest_loss_case(lossyear, treecover2000, polygon, *, pixel_size_m=30.0, first_code=1, last_code=25,
                     eligible=None, max_n=None, seed=0, offset=(0, 0), tier="tier2",
                     population_definition="least-disturbed stratum cells (centre pixel eligible)") -> Case:
    num, den, years = forest_loss_terms(lossyear, treecover2000, first_code, last_code)
    px_area = pixel_size_m ** 2
    poly = np.asarray(polygon, bool)
    site_area = float(poly.sum()) * px_area
    floor = IC.FOREST_BASELINE_MIN_M2
    temporal = f"hansen_v1.13_lossyear:{first_code}-{last_code}({years}y)"
    site = S.polygon_rate(num, den, poly, years, px_area, floor)
    site_spec = MetricSpec("gross_forest_loss_rate", "percent_per_year", temporal, "polygon_rate", "site",
                           native_scale_m=pixel_size_m)
    ref = window_rate_reference(num, den, site_area, pixel_size_m, years, construct="gross_forest_loss_rate",
                                unit="percent_per_year", temporal=temporal, population="least_disturbed_stratum",
                                tier=tier, population_definition=population_definition, pixel_area_m2=px_area,
                                min_denominator_area_m2=floor, eligible=eligible, max_n=max_n, seed=seed, offset=offset)
    return Case(site, site_spec, ref, site_area, {"years": years, "baseline_forest_m2": float(den[poly].sum() * px_area)})


# ----------------------------------------------------------------------------------------
# net_tree_cover_change_rate  (D5)
# ----------------------------------------------------------------------------------------
def dw_tree_indicator(dw_label):
    """1 where Dynamic World says trees, 0 elsewhere, NaN where there is no classification."""
    d = np.asarray(dw_label, float)
    return np.where(np.isfinite(d), (d == K.DW_TREES).astype(float), np.nan)


def tree_share_change_pp_per_year(dw_early, dw_recent, dt_years):
    """Per-pixel change in tree-cover share, percentage points per year, ONE product, ONE
    classifier, identical compositing at both endpoints (the same dw_tree_indicator). Its polygon
    mean and its window mean are both the change in tree-cover share (linear)."""
    if dt_years <= 0:
        raise ValueError("the two periods must be separated in time")
    return (dw_tree_indicator(dw_recent) - dw_tree_indicator(dw_early)) * 100.0 / dt_years


def net_change_case(dw_early, dw_recent, polygon, *, dt_years, pixel_size_m=10.0, eligible=None, max_n=None,
                    seed=0, offset=(0, 0), tier="tier1",
                    population_definition="all valid site-sized cells of the ecoregion (no land-cover stratum)") -> Case:
    diff = tree_share_change_pp_per_year(dw_early, dw_recent, dt_years)
    valid = np.isfinite(diff)
    poly = np.asarray(polygon, bool)
    site_area = float(poly.sum()) * pixel_size_m ** 2
    temporal = f"dw_tree_share:early{K.NET_CHANGE_EARLY_YEARS}->recent;dt={dt_years:g}y"
    site = site_mean(diff, poly, valid)
    site_spec = MetricSpec("net_tree_cover_change", "percentage_points_per_year", temporal, "polygon_mean", "site",
                           native_scale_m=pixel_size_m)
    ref = window_mean_reference(diff, valid, site_area, pixel_size_m, construct="net_tree_cover_change",
                                unit="percentage_points_per_year", temporal=temporal, population="regional_ecoregion",
                                tier=tier, population_definition=population_definition, eligible=eligible,
                                max_n=max_n, seed=seed, offset=offset)
    return Case(site, site_spec, ref, site_area)


# ----------------------------------------------------------------------------------------
# natural_habitat  (D2)
# ----------------------------------------------------------------------------------------
def natural_binary(dw_label):
    d = np.asarray(dw_label, float)
    return np.where(np.isfinite(d), np.isin(d, K.NATURAL_CLASSES).astype(float), np.nan)


def natural_habitat_case(dw_label, polygon, *, pixel_size_m=10.0, eligible=None, max_n=None, seed=0, offset=(0, 0),
                         population_definition="all valid site-sized cells of the ecoregion (no land-cover stratum)") -> Case:
    nat = natural_binary(dw_label)
    valid = np.isfinite(nat)
    poly = np.asarray(polygon, bool)
    site_area = float(poly.sum()) * pixel_size_m ** 2
    site = site_mean(nat, poly, valid)
    site = None if site is None else site * 100.0
    site_spec = MetricSpec("natural_habitat_share", "percent", "dw_annual_mode", "polygon_proportion", "site",
                           native_scale_m=pixel_size_m)
    ref = window_proportion_reference(nat, valid, site_area, pixel_size_m, construct="natural_habitat_share",
                                      unit="percent", temporal="dw_annual_mode", population="regional_ecoregion",
                                      tier="tier1", population_definition=population_definition, eligible=eligible,
                                      max_n=max_n, seed=seed, scale_to_percent=True, offset=offset)
    return Case(site, site_spec, ref, site_area)


# ----------------------------------------------------------------------------------------
# ghm  (site read at native resolution, regional unfiltered stratum)
# ----------------------------------------------------------------------------------------
def ghm_case(hmi, polygon, *, pixel_size_m=K.GHM_NATIVE_M, eligible=None, max_n=None, seed=0, offset=(0, 0),
             population_definition="regional stratum cells, NO pressure filter (item 3, option B)") -> Case:
    h = np.asarray(hmi, float)
    valid = np.isfinite(h)
    poly = np.asarray(polygon, bool)
    site_area = float(poly.sum()) * pixel_size_m ** 2
    site_spec = MetricSpec("human_modification", "index_0_1", "static_2022", "polygon_mean", "site",
                           native_scale_m=pixel_size_m)
    ref = window_mean_reference(h, valid, site_area, pixel_size_m, construct="human_modification", unit="index_0_1",
                                temporal="static_2022", population="regional_stratum_unfiltered", tier="tier2",
                                population_definition=population_definition, eligible=eligible, max_n=max_n, seed=seed, offset=offset)
    return Case(site_mean(h, poly, valid), site_spec, ref, site_area)


# ----------------------------------------------------------------------------------------
# Aquatic pixel metrics (numpy definitions of the corrected constructs)
# ----------------------------------------------------------------------------------------
def sabf_pixel_frequency(fai_stack, threshold=K.FAI_BLOOM_THRESHOLD):
    """Per-pixel share of valid dates with FAI > threshold. fai_stack: (T, H, W), NaN = masked."""
    f = np.asarray(fai_stack, float)
    valid = np.isfinite(f)
    cnt = valid.sum(axis=0)
    bloom = ((f > threshold) & valid).sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = bloom / cnt
    out[cnt == 0] = np.nan
    return out


def tsm_nechad(red):
    r = np.asarray(red, float)
    with np.errstate(invalid="ignore", divide="ignore"):
        tsm = K.TSM_NECHAD_A * r / (1.0 - r / K.TSM_NECHAD_C)
    return np.where((tsm > 0) & (tsm < K.TSM_MAX), tsm, np.nan)


def wcpi_pixel(red):
    """RAW water clarity 1/(TSM+1). No normalisation by the site's own range (X3)."""
    return 1.0 / (tsm_nechad(red) + 1.0)


def sdi_pixel_disturbed(dw_label):
    """1 where crops / built / bare or the built-up edge ('road proxy'), 0 elsewhere."""
    d = np.asarray(dw_label, float)
    built = d == K.DW_BUILT
    edge = ndimage.binary_dilation(built, structure=ndimage.generate_binary_structure(2, 1)) & ~built
    dist = np.isin(d, K.DISTURBED_CLASSES) | edge
    return np.where(np.isfinite(d), dist.astype(float), np.nan)


def thermal_term(lst_c):
    """Thermal term 0-1 over the SOURCE PRODUCT's valid range (numerical / QC scaling, no ecological threshold);
    values outside the product's valid range are invalid (NaN)."""
    t = np.asarray(lst_c, float)
    span = K.LST_QC_MAX_C - K.LST_QC_MIN_C
    ok = (t >= K.LST_QC_MIN_C) & (t <= K.LST_QC_MAX_C)
    return np.where(ok, np.clip((t - K.LST_QC_MIN_C) / span, 0, 1), np.nan)


def edpp_index(lst_c, turbidity_protection, moisture, exposure):
    """Single-band EDPP; thermal term = 1 - product-range-scaled LST."""
    return np.clip((1 - thermal_term(lst_c)) * turbidity_protection * moisture * (1 - exposure), 0, 1)


def mspl_index(lst_c, nutrient, turbidity, water_persistence):
    """Single-band MSPL; thermal term over the product's valid range."""
    w = K.MSPL_WEIGHTS
    return np.clip(w["nutrient"] * nutrient + w["thermal"] * np.nan_to_num(thermal_term(lst_c), nan=0.0)
                   + w["turbidity"] * turbidity + w["water_persistence"] * water_persistence, 0, 1)


# ----------------------------------------------------------------------------------------
# Water-body and riparian-ring references (E2, E3)
# ----------------------------------------------------------------------------------------
@dataclass
class WaterBodyCase:
    valid: bool
    invalid_reason: str
    target_id: Optional[int]
    target_value: Optional[float]
    target_area_m2: Optional[float]
    n_pure_water_px: int
    reference: Optional[ReferenceData]
    site_spec: Optional[MetricSpec]
    funnel: Dict = field(default_factory=dict)


def water_body_case(*, water, metric, kind, site_mask, pixel_area_m2, native_scale_m, construct, unit, temporal,
                    population, permanence=None, ring_width_px=10, min_pure_px=IC.MIN_PURE_WATER_PIXELS,
                    area_ratio=IC.WATER_BODY_AREA_RATIO, permanence_tol=IC.WATER_BODY_PERMANENCE_TOL,
                    erode_px=K.PURE_WATER_ERODE_PX, tier="tier2", region_definition="the reference zone") -> WaterBodyCase:
    """Target water body + comparable-water-body reference (E2).

    kind = 'water': unit metric = mean of `metric` over the body's PURE-water pixels.
    kind = 'ring' : unit metric = mean of `metric` over the land ring of width ring_width_px
                    around the body (all water excluded).
    The SAME masks, erosion, ring width and metric are applied to the target and to every
    reference body. A reference body must itself have >= min_pure_px pure-water pixels."""
    water = np.asarray(water, bool)
    units = S.label_units(water, pixel_area_m2)
    funnel = {"n_water_bodies_total": len(units.areas_m2)}
    if not units.areas_m2:
        return WaterBodyCase(False, "no_water_body", None, None, None, 0, None, None, funnel)
    site_mask = np.asarray(site_mask, bool)
    overlaps = {i: int(((units.labels == i) & site_mask).sum()) for i in units.areas_m2}
    target = max(overlaps, key=overlaps.get)
    if overlaps[target] == 0:
        return WaterBodyCase(False, "no_water_body_in_site", None, None, None, 0, None, None, funnel)

    pure = S.unit_masks(units, pure=True, erode_px=erode_px)
    pure_px = {i: int(m.sum()) for i, m in pure.items()}
    masks = pure if kind == "water" else S.ring_masks(units, ring_width_px, all_water=water)
    n_pure = pure_px[target]
    if n_pure < min_pure_px:
        return WaterBodyCase(False, "insufficient_pure_water", target, None, units.areas_m2[target], n_pure, None, None, funnel)
    vals = S.unit_values(metric, masks, min_pixels=1)
    if target not in vals:
        return WaterBodyCase(False, "no_valid_metric_pixels", target, None, units.areas_m2[target], n_pure, None, None, funnel)

    ok = {i for i in units.areas_m2 if pure_px[i] >= min_pure_px and i in vals
          and (kind == "water" or int(masks[i].sum()) >= min_pure_px)}
    funnel["n_bodies_with_enough_pixels"] = len(ok)
    cand = S.WaterUnits(units.labels, {i: units.areas_m2[i] for i in ok})
    tgt_area = units.areas_m2[target]
    by_size = S.match_units(cand, tgt_area, size_factor=area_ratio, exclude_ids=[target])
    tperm = None
    if permanence is not None:
        tperm = float(np.nanmean(np.asarray(permanence, float)[units.labels == target]))
        final = S.match_units(cand, tgt_area, size_factor=area_ratio, permanence=permanence,
                              target_permanence=tperm, permanence_tolerance=permanence_tol, exclude_ids=[target])
    else:
        final = by_size
    funnel.update({"n_rejected_size": len(ok) - 1 - len(by_size),
                   "n_rejected_permanence": len(by_size) - len(final), "n_reference_bodies": len(final)})
    ref_vals = np.array([vals[i] for i in final], float)
    pdef = (f"comparable {'water bodies' if kind == 'water' else 'riparian rings of water bodies'} in {region_definition}: "
            f"area within [1/{area_ratio:g}, {area_ratio:g}] x target ({tgt_area:.0f} m2)"
            + (f", |permanence difference| <= {permanence_tol:g}" if permanence is not None else "")
            + f", >= {min_pure_px} pure-water px each; {len(final)} of {len(units.areas_m2) - 1} other bodies")
    unit_support = "water_body_unit" if kind == "water" else "riparian_ring_unit"
    ref = ReferenceData(ref_vals, MetricSpec(construct, unit, temporal, unit_support, population, native_scale_m=native_scale_m),
                        tier, pdef, {"reference_body_ids": list(final), "funnel": dict(funnel),
                                     "target_permanence": tperm, "erode_px": erode_px,
                                     "ring_width_px": ring_width_px if kind == "ring" else None})
    site_spec = MetricSpec(construct, unit, temporal, unit_support, "site", native_scale_m=native_scale_m)
    return WaterBodyCase(True, "", target, float(vals[target]), tgt_area, n_pure, ref, site_spec, funnel)
