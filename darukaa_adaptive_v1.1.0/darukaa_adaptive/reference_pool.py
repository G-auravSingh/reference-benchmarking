"""Reference pools (approved design, D-23-14; metric catalogue v1 "Reference design").

Approach 2 - condition reference (``reference_condition`` metrics)
  One pool per project and ecoregion: inside the site's RESOLVE ecoregion and within
  ``radius_km``, outside every project site plus ``exclusion_m``. Natural pixels are
  stratified by natural-mask type; within each stratum the least-disturbed pixels are
  kept by the human-modification ladder on gHM v3 (90 m):
    stage 1 strict  : gHM <= strict_hmi (default 0.05)
    stage 2 quantile: gHM <= the stratum's ``least_quantile`` (default 10th percentile)
    stage 3 manual  : gHM <= manual_hmi, only if the analyst set it
  A stratified pixel sample is drawn and every condition metric is read at the same
  pixels; layers finer than the 30 m sampling grid are averaged to it first. Too few pixels -> ``reference_insufficient``; there is no silent fallback.

Approach 4 - regional context (``regional_context`` metrics; 3Bee-style control ring
  [VENDOR precedent]): square blocks of the same areal support as the site are placed
  in the same ring (no disturbance filter) and measured with exactly the same code
  path as the site. Blocks are grouped into larger spatial cells for the bootstrap.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from . import catalogue as cat
from . import layers as L
from . import natural_mask as nm
from .ee_utils import ee_module, evaluate, to_ee
from .scorecard import ReferenceSample
from .site import _reproject, _utm_epsg, area_ha, projected_buffer

ECOREGIONS = "RESOLVE/ECOREGIONS/2017"


@dataclass
class PoolConfig:
    radius_km: float = 25.0
    exclusion_m: float = 1000.0
    strict_hmi: float = 0.05
    least_quantile: float = 0.10
    manual_hmi: Optional[float] = None
    n_per_stratum: int = 300
    min_stratum_pixels: int = 200
    sample_scale_m: float = 30.0
    bootstrap_cell_m: float = 5000.0
    min_n: int = 30
    min_blocks: int = 5
    n_regional_blocks: int = 120
    block_min_m: float = 300.0
    block_max_m: float = 3000.0
    seed: int = 20261023


def ring(footprint: BaseGeometry, cfg: PoolConfig) -> BaseGeometry:
    outer = projected_buffer(footprint, cfg.radius_km * 1000.0)
    inner = projected_buffer(footprint, cfg.exclusion_m)
    return outer.difference(inner)


def condition_metric_images(ctx: L.ExtractionContext, sample_scale_m: float = 30.0) -> Dict[str, Any]:
    """Images for every reference_condition metric, built exactly as for the site."""
    ee = ee_module()
    imgs: Dict[str, Any] = {}
    for c in cat.CATALOGUE:
        if c.reference_type != "reference_condition" or c.pillar != "P2":
            continue
        try:
            spec = L.BUILDERS[c.id](ctx)
        except Exception:  # noqa: BLE001 - a missing layer simply has no reference
            continue
        if isinstance(spec, L.StatsSpec):
            img = spec.image.select(["v"])
            native = c.native_scale_m or 30
            if native < sample_scale_m:
                # Point samples read one pixel. Layers finer than the sampling grid are first
                # averaged to that grid so a reference value is a local mean, as a site value is,
                # not a single 1 m or 10 m pixel (review finding 8).
                img = (img.setDefaultProjection(crs=ctx.crs, scale=native)
                       .reduceResolution(reducer=ee.Reducer.mean(), bestEffort=False, maxPixels=65535)
                       .reproject(crs=ctx.crs, scale=sample_scale_m))
            imgs[c.id] = img.rename(c.id)
    return imgs


@dataclass
class ConditionPool:
    ecoregion: Dict[str, Any]
    stages: Dict[int, Dict[str, Any]]
    samples: Dict[Tuple[str, Any], ReferenceSample]
    n_points: int
    notes: List[str] = field(default_factory=list)

    def get(self, metric: str, stratum) -> Optional[ReferenceSample]:
        return self.samples.get((metric, stratum))

    def summary(self) -> List[Dict[str, Any]]:
        rows = []
        for code, st in sorted(self.stages.items()):
            rows.append({"stratum": nm.STRATA.get(code, code), "stage": st.get("stage"), "hmi_threshold": st.get("threshold"),
                         "pixels_total": st.get("total"), "pixels_least_disturbed": st.get("eligible")})
        return rows


def build_condition_pool(footprint: BaseGeometry, ctx_base: Dict[str, Any], cfg: PoolConfig) -> ConditionPool:
    ee = ee_module()
    rg = ring(footprint, cfg)
    centroid = footprint.centroid
    eco_fc = ee.FeatureCollection(ECOREGIONS).filterBounds(ee.Geometry.Point([centroid.x, centroid.y]))
    eco = ee.Feature(eco_fc.first())
    region = to_ee(rg).intersection(eco.geometry(), ee.ErrorMargin(30))
    ctx = L.ExtractionContext(region=region, unit_region=region, **ctx_base)
    mask, _ = nm.build_mask(region, ctx_base["start"], ctx_base["end_exclusive"],
                            ctx_base.get("options", {}).get("min_probability", 0.5), crs=ctx_base["crs"])
    ctx.mask = mask
    ghm, _ = L.ghm_image(region)
    stratum = mask.select("stratum")
    natural = mask.select("natural_now")
    s30 = cfg.sample_scale_m
    crs = ctx_base["crs"]
    nat_strat = stratum.updateMask(natural)
    hist_total = nat_strat.reduceRegion(ee.Reducer.frequencyHistogram(), region, s30, crs, maxPixels=1e13, tileScale=8).get("stratum")
    hist_strict = nat_strat.updateMask(ghm.lte(cfg.strict_hmi)).reduceRegion(ee.Reducer.frequencyHistogram(), region, s30, crs,
                                                                             maxPixels=1e13, tileScale=8).get("stratum")
    q = ghm.addBands(nat_strat).reduceRegion(
        ee.Reducer.percentile([cfg.least_quantile * 100]).group(groupField=1, groupName="stratum"),
        region, s30, crs, maxPixels=1e13, tileScale=8).get("groups")
    raw = evaluate({"eco": eco.toDictionary(["ECO_ID", "ECO_NAME", "BIOME_NAME"]), "total": hist_total, "strict": hist_strict, "q": q})
    for k, v in raw.items():
        if isinstance(v, Exception):
            raise RuntimeError(f"Condition reference pool failed at '{k}': {v}")
    total = {int(float(k)): int(v) for k, v in (raw["total"] or {}).items()}
    strict = {int(float(k)): int(v) for k, v in (raw["strict"] or {}).items()}
    qmap = {int(g["stratum"]): next(iter(v for kk, v in g.items() if kk != "stratum"), None) for g in (raw["q"] or [])}
    stages: Dict[int, Dict[str, Any]] = {}
    ld = ee.Image(0)
    for code in nm.NATURAL_STRATA:
        tot = total.get(code, 0)
        if strict.get(code, 0) >= cfg.min_stratum_pixels:
            stage, thr, elig = "strict_hmi", cfg.strict_hmi, strict[code]
        elif qmap.get(code) is not None and tot * cfg.least_quantile >= cfg.min_stratum_pixels:
            stage, thr, elig = "least_disturbed_quantile", float(qmap[code]), int(tot * cfg.least_quantile)
        elif cfg.manual_hmi is not None:
            stage, thr, elig = "manual_hmi", float(cfg.manual_hmi), None
        else:
            stages[code] = {"stage": "reference_insufficient", "threshold": None, "total": tot, "eligible": strict.get(code, 0)}
            continue
        stages[code] = {"stage": stage, "threshold": thr, "total": tot, "eligible": elig}
        ld = ld.where(nat_strat.eq(code).And(ghm.lte(thr)), 1)
    usable = [c for c, s in stages.items() if s["stage"] != "reference_insufficient"]
    samples: Dict[Tuple[str, Any], ReferenceSample] = {}
    notes = []
    if not usable:
        return ConditionPool(raw["eco"], stages, samples, 0, ["no natural stratum with enough least-disturbed pixels"])
    imgs = condition_metric_images(ctx, cfg.sample_scale_m)
    coords = ee.Image.pixelCoordinates(ee.Projection(crs))
    cell = coords.select("x").divide(cfg.bootstrap_cell_m).floor().multiply(100000).add(
        coords.select("y").divide(cfg.bootstrap_cell_m).floor()).rename("cell")
    stack = ee.Image.cat(list(imgs.values()) + [nat_strat.rename("stratum"), cell]).updateMask(ld.eq(1))
    fc = stack.stratifiedSample(numPoints=cfg.n_per_stratum, classBand="stratum", region=region, scale=s30,
                                projection=crs, seed=cfg.seed, classValues=usable,
                                classPoints=[cfg.n_per_stratum] * len(usable), dropNulls=False, tileScale=8, geometries=False)
    # A FeatureCollection is fetched on its own: nested inside an ee.Dictionary it does
    # not come back with a "features" list (R2 run, 24 Oct: KeyError 'features').
    try:
        got = fc.getInfo()
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller with context
        raise RuntimeError(f"Reference sampling failed: {exc}") from exc
    feats = [f["properties"] for f in got.get("features", [])]
    for mid in imgs:
        for code in usable:
            rows = [p for p in feats if int(p["stratum"]) == code and p.get(mid) is not None]
            if rows:
                samples[(mid, code)] = ReferenceSample(mid, "reference_condition", np.array([r[mid] for r in rows]),
                                                       np.array([r["cell"] for r in rows]), stratum=nm.STRATA[code],
                                                       method=stages[code]["stage"], min_n=cfg.min_n, min_blocks=cfg.min_blocks)
        rows = [p for p in feats if p.get(mid) is not None]
        if rows:
            samples[(mid, "natural_all")] = ReferenceSample(mid, "reference_condition", np.array([r[mid] for r in rows]),
                                                            np.array([r["cell"] for r in rows]), stratum="natural_all",
                                                            method="pooled least-disturbed natural strata",
                                                            min_n=cfg.min_n, min_blocks=cfg.min_blocks)
    return ConditionPool(raw["eco"], stages, samples, len(feats), notes)


def regional_blocks(site: BaseGeometry, footprint: BaseGeometry, cfg: PoolConfig) -> List[Tuple[str, BaseGeometry, int]]:
    """Client-side square blocks with the site's areal support, inside the ring.

    Returns (block_id, geometry, bootstrap cell id). Block side = sqrt(site area),
    clamped to [block_min_m, block_max_m].
    """
    from pyproj import Transformer
    rg = ring(footprint, cfg)
    epsg = _utm_epsg(footprint)
    fwd = Transformer.from_crs("EPSG:4326", epsg, always_xy=True)
    inv = Transformer.from_crs(epsg, "EPSG:4326", always_xy=True)
    rg_p = _reproject(rg, fwd)
    side = min(max(math.sqrt(area_ha(site) * 1e4), cfg.block_min_m), cfg.block_max_m)
    minx, miny, maxx, maxy = rg_p.bounds
    cands = []
    y = miny
    while y + side <= maxy:
        x = minx
        while x + side <= maxx:
            b = box(x, y, x + side, y + side)
            if rg_p.contains(b):
                cands.append(b)
            x += side
        y += side
    rnd = random.Random(cfg.seed)
    rnd.shuffle(cands)
    out = []
    for i, b in enumerate(cands[: cfg.n_regional_blocks]):
        cx, cy = b.centroid.x, b.centroid.y
        cell = int(cx // cfg.bootstrap_cell_m) * 100000 + int(cy // cfg.bootstrap_cell_m)
        out.append((f"RB{i:03d}", _reproject(b, inv), cell))
    return out


def same_ecoregion(blocks: Sequence[Tuple[str, BaseGeometry, int]], footprint: BaseGeometry) -> List[Tuple[str, BaseGeometry, int]]:
    """Keep blocks whose centroid lies in the site's RESOLVE ecoregion."""
    ee = ee_module()
    c = footprint.centroid
    eco = ee.Feature(ee.FeatureCollection(ECOREGIONS).filterBounds(ee.Geometry.Point([c.x, c.y])).first())
    pts = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([g.centroid.x, g.centroid.y]), {"id": bid}) for bid, g, _ in blocks])
    raw = evaluate({"ids": pts.filterBounds(eco.geometry()).aggregate_array("id")})
    if isinstance(raw["ids"], Exception):
        raise RuntimeError(f"Ecoregion filter failed: {raw['ids']}")
    keep = set(raw["ids"] or [])
    return [b for b in blocks if b[0] in keep]


def regional_sample(metric: str, block_values: Dict[str, Optional[float]], cells: Dict[str, int], cfg: PoolConfig) -> ReferenceSample:
    ids = [b for b, v in block_values.items() if v is not None]
    return ReferenceSample(metric, "regional_context", np.array([block_values[b] for b in ids], dtype=float),
                           np.array([cells[b] for b in ids]), stratum="regional_blocks",
                           method="same-ecoregion ring blocks, no disturbance filter", min_n=cfg.min_n, min_blocks=cfg.min_blocks)
