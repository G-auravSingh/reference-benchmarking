"""Measure catalogue metrics over assessment units (sites, EMUs, reference blocks).

One code path measures sites, EMUs and regional reference blocks, so a value and
its regional reference are always built the same way (audit H4). Every metric is
evaluated lazily and all metrics for a unit are fetched in one Earth Engine call;
a failing layer is isolated and recorded as ``error`` without hiding the others.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from shapely.geometry.base import BaseGeometry

from . import catalogue as cat
from . import layers as L
from .ee_utils import ee_module, evaluate, parse_stats, reduce_stats, to_ee, utm_crs
from .measurement import Measurement, check_measurement, failed
from .site import area_ha, projected_buffer
from .units import context_window

# Regions other than the unit itself, fixed by the metric definitions.
REGION_RULES = {"road_density": ("buffer", 1000.0), "population_density": ("buffer", 1000.0),
                "landscape_natural_extent_pct": ("ring", 5000.0)}


@dataclass
class Unit:
    unit_id: str
    level: str          # site | emu | reference_block
    geometry: BaseGeometry


@dataclass
class Planned:
    metric: str
    spec: Any
    region_geom: BaseGeometry
    context_buffer_m: float
    native_scale_m: Optional[float]


def month_starts(start: str, end_exclusive: str) -> List[Tuple[str, str]]:
    s = date.fromisoformat(start).replace(day=1)
    e = date.fromisoformat(end_exclusive)
    out = []
    while s < e:
        nxt = date(s.year + (s.month // 12), s.month % 12 + 1, 1)
        out.append((s.isoformat(), min(nxt, e).isoformat()))
        s = nxt
    return out


def pick_peak_window(monthly: Dict[str, Optional[float]], months: Sequence[Tuple[str, str]], length: int = 3) -> Tuple[Tuple[str, str], str]:
    """Choose the ``length`` consecutive months with the highest mean NDVI.

    Plan Vivo Pillar 4 uses a 3-month peak-vegetation window (PV Nature V1.2 p.25).
    Months with no clear observation are skipped; if no complete run exists the whole
    assessment window is used and the basis says so.
    """
    best, best_val = None, None
    for i in range(len(months) - length + 1):
        vals = [monthly.get(months[i + k][0]) for k in range(length)]
        if any(v is None for v in vals):
            continue
        m = sum(vals) / length
        if best_val is None or m > best_val:
            best, best_val = i, m
    if best is None:
        return (months[0][0], months[-1][1]), "no complete 3-month run with clear scenes; full window used"
    return (months[best][0], months[best + length - 1][1]), f"peak 3-month mean NDVI {best_val:.3f}"


def plan_unit(unit: Unit, metric_ids: Iterable[str], ctx_base: Dict[str, Any], min_px: float = 4.0) -> List[Planned]:
    """Choose the measurement region for each metric and build its spec (lazy)."""
    plans: List[Planned] = []
    for mid in metric_ids:
        c = cat.get(mid)
        native = c.native_scale_m
        region, buf = unit.geometry, 0.0
        rule = REGION_RULES.get(mid)
        if rule and unit.level != "reference_block":
            kind, dist = rule
            outer = projected_buffer(unit.geometry, dist)
            region = outer if kind == "buffer" else outer.difference(unit.geometry)
        spec, ctx = _build(mid, region, unit, ctx_base)
        if isinstance(spec, L.StatsSpec) and native and native >= 30:
            # Decision 5: a raster layer whose native pixels the unit cannot hold
            # min_px times is measured over the smallest window that can, and is
            # labelled context scale (never presented as site-resolved).
            win, buf = context_window(unit.geometry, native, max(min_px, c.min_support_px))
            if buf > 0:
                region = win
                spec, ctx = _build(mid, region, unit, ctx_base)
        plans.append(Planned(mid, (spec, ctx), region, buf, native))
    return plans


def _build(mid: str, region: BaseGeometry, unit: Unit, ctx_base: Dict[str, Any]):
    ctx = L.ExtractionContext(region=to_ee(region), unit_region=to_ee(unit.geometry), **ctx_base)
    try:
        return L.BUILDERS[mid](ctx), ctx
    except Exception as exc:  # noqa: BLE001 - recorded as an error measurement, never a value
        return exc, ctx


def _lazy_for(plan: Planned) -> Dict[str, Any]:
    ee = ee_module()
    spec, ctx = plan.spec
    if isinstance(spec, Exception) or isinstance(spec, L.PendingSpec):
        return {}
    region = ctx.region
    if isinstance(spec, L.StatsSpec):
        crs = spec.crs if spec.crs is not None else ctx.crs
        img = spec.image.select(["v"])
        w = L.weight_image(ctx, spec.weight, spec.scale)
        if w is not None:
            img = img.updateMask(w)
        out = {"stats": reduce_stats(img, region, spec.scale, crs)}
        if spec.by_stratum:
            out["strata"] = img.addBands(ctx.mask.select("stratum")).reduceRegion(
                reducer=ee.Reducer.mean().combine(ee.Reducer.sum(), sharedInputs=True).group(groupField=1, groupName="stratum"),
                geometry=region, scale=spec.scale, crs=crs, maxPixels=1e13, tileScale=4)
        for k, v in spec.extras.items():
            out[f"x_{k}"] = v
        return out
    if isinstance(spec, L.RatioSpec):
        crs = spec.crs if spec.crs is not None else ctx.crs
        bands = [spec.numerator.unmask(0).rename("num"), spec.denominator.unmask(0).rename("den")]
        names = []
        for k, v in spec.extras.items():
            if isinstance(v, tuple):
                bands.append(v[0].unmask(0).rename(f"x_{k}"))
                names.append(k)
        img = ee.Image.cat(bands).toFloat().multiply(ee.Image.pixelArea())
        return {"sums": img.reduceRegion(reducer=ee.Reducer.sum(), geometry=region, scale=spec.scale, crs=crs,
                                         maxPixels=1e13, tileScale=4)}
    if isinstance(spec, L.CustomSpec):
        return dict(spec.lazy)
    raise TypeError(f"Unknown spec {type(spec)}")


def _measure(plan: Planned, unit: Unit, raw: Dict[str, Any]) -> Measurement:
    spec, ctx = plan.spec
    mid = plan.metric
    if isinstance(spec, Exception):
        return failed(mid, unit.unit_id, unit.level, spec)
    if isinstance(spec, L.PendingSpec):
        return Measurement(mid, unit.unit_id, unit.level, None, spec.status, ran=spec.status != "not_run", notes=spec.reason)
    errors = [v for v in raw.values() if isinstance(v, Exception)]
    if errors:
        return failed(mid, unit.unit_id, unit.level, errors[0])
    common = dict(native_scale_m=plan.native_scale_m, context_buffer_m=plan.context_buffer_m,
                  effective_period=getattr(spec, "period", ""))
    status_ok = "scored_context_scale" if plan.context_buffer_m > 0 else "ok"
    if isinstance(spec, L.StatsSpec):
        st = parse_stats(raw.get("stats") or {})
        value = spec.post(st) if spec.post else st.get("mean")
        extras = {k[2:]: v for k, v in raw.items() if k.startswith("x_")}
        if "strata" in raw:
            groups = (raw.get("strata") or {}).get("groups", [])
            extras["by_stratum"] = {int(g["stratum"]): {"mean": g.get("mean"), "weight": g.get("sum")} for g in groups
                                    if g.get("mean") is not None}
        m = Measurement(mid, unit.unit_id, unit.level, value, status_ok if value is not None else "no_valid_pixels",
                        covered_pixel_equivalent=st.get("covered_pixel_equivalent"), touched_pixels=st.get("centre_pixels"),
                        analysis_scale_m=spec.scale, spread={k: st.get(k) for k in ("stdDev", "p5", "p50", "p95")},
                        extras=extras, **common)
        return check_measurement(m)
    if isinstance(spec, L.RatioSpec):
        sums = raw.get("sums") or {}
        num, den = sums.get("num"), sums.get("den")
        extras = {}
        for k, v in spec.extras.items():
            if isinstance(v, tuple):
                x = sums.get(f"x_{k}")
                if x is None:
                    extras[k] = None
                elif v[1] == "ha":
                    extras[k] = x / 1e4
                else:
                    extras[k] = 100.0 * x / den if den else None
            else:
                extras[k] = v
        extras["denominator_ha"] = den / 1e4 if den is not None else None
        if num is None or den is None or den <= 0:
            return Measurement(mid, unit.unit_id, unit.level, None, spec.na_status if den == 0 else "no_valid_pixels", extras=extras, **common)
        if den / 1e4 < spec.min_denominator_ha:
            return Measurement(mid, unit.unit_id, unit.level, None, spec.na_status, extras=extras,
                               notes=f"denominator {den / 1e4:.3f} ha < {spec.min_denominator_ha} ha", **common)
        value = num / 1e4 if spec.factor is None else spec.factor * num / den
        m = Measurement(mid, unit.unit_id, unit.level, value, "ok", analysis_scale_m=spec.scale, extras=extras, **common)
        return check_measurement(m)
    value, status, extras = spec.parse(raw)
    m = Measurement(mid, unit.unit_id, unit.level, value, status if value is not None else ("no_valid_pixels" if status == "ok" else status),
                    extras=extras, **common)
    return check_measurement(m)


def measure_units(units: Sequence[Unit], metric_ids: Sequence[str], ctx_base: Dict[str, Any], min_px: float = 4.0) -> List[Measurement]:
    """Measure every metric on every unit; one EE evaluation per unit."""
    out: List[Measurement] = []
    for unit in units:
        plans = plan_unit(unit, metric_ids, ctx_base, min_px)
        lazy: Dict[str, Any] = {}
        for p in plans:
            for k, v in _lazy_for(p).items():
                lazy[f"{p.metric}|{k}"] = v
        raw = evaluate(lazy) if lazy else {}
        for p in plans:
            prefix = f"{p.metric}|"
            part = {k[len(prefix):]: v for k, v in raw.items() if k.startswith(prefix)}
            try:
                out.append(_measure(p, unit, part))
            except Exception as exc:  # noqa: BLE001 - parsing failure is recorded, not hidden
                out.append(failed(p.metric, unit.unit_id, unit.level, exc))
    return out
