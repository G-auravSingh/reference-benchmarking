"""Earth Engine helpers shared by every extractor.

Rules enforced here (metric catalogue v1, "Small-parcel and scale rules"):
* every reduction sets ``scale`` and ``crs`` explicitly; ``bestEffort`` is never used;
* the value is the coverage-weighted mean (EE weights pixels by covered fraction);
* support is recorded as ``covered_pixel_equivalent`` (sum of coverage weights of
  valid pixels) and ``centre_pixels`` (unweighted count of valid pixel centres);
* outputs are parsed by exact key, never by substring (audit M1).

``ee`` is imported lazily so the package and its tests run without Earth Engine.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Optional, Sequence

from shapely.geometry.base import BaseGeometry

from .site import _utm_epsg

STAT_KEYS = ("mean", "stdDev", "p5", "p50", "p95")
MAX_PIXELS = 1e13
TILE_SCALE = 4


def ee_module():
    import ee  # noqa: WPS433 - deliberate lazy import
    return ee


def to_ee(geom: BaseGeometry):
    ee = ee_module()
    return ee.Geometry(geom.__geo_interface__, None, False)


def utm_crs(geom: BaseGeometry) -> str:
    return f"EPSG:{_utm_epsg(geom)}"


def stats_reducer():
    ee = ee_module()
    return (ee.Reducer.mean()
            .combine(ee.Reducer.stdDev(), sharedInputs=True)
            .combine(ee.Reducer.percentile([5, 50, 95]), sharedInputs=True))


def reduce_stats(image, region, scale: float, crs) -> Any:
    """Lazy ee.Dictionary with the value statistics and support of band ``v``.

    ``image`` must have a single band named ``v`` whose mask marks valid pixels.
    """
    ee = ee_module()
    v = image.select(["v"])
    stats = v.reduceRegion(reducer=stats_reducer(), geometry=region, scale=scale, crs=crs,
                           maxPixels=MAX_PIXELS, tileScale=TILE_SCALE)
    one = ee.Image.constant(1).rename("w").updateMask(v.mask())
    support = one.reduceRegion(
        reducer=ee.Reducer.sum().combine(ee.Reducer.count().unweighted(), sharedInputs=True),
        geometry=region, scale=scale, crs=crs, maxPixels=MAX_PIXELS, tileScale=TILE_SCALE)
    return ee.Dictionary(stats).combine(support)


def reduce_sums(image, region, scale: float, crs) -> Any:
    """Lazy ee.Dictionary of coverage-weighted pixel-area sums (m2) for every band."""
    ee = ee_module()
    area = image.multiply(ee.Image.pixelArea())
    return area.reduceRegion(reducer=ee.Reducer.sum(), geometry=region, scale=scale, crs=crs,
                             maxPixels=MAX_PIXELS, tileScale=TILE_SCALE)


def _num(x) -> Optional[float]:
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def parse_stats(raw: Mapping[str, Any]) -> Dict[str, Optional[float]]:
    """Parse ``reduce_stats`` output by exact keys (``v_mean`` ...; ``w_sum``, ``w_count``)."""
    def pick(prefixed: str, bare: str):
        # Exact keys only: EE prefixes outputs with the band name when a reducer has
        # several outputs; the bare form is accepted only as the exact same output.
        return raw[prefixed] if prefixed in raw else raw.get(bare)

    out = {k: _num(pick(f"v_{k}", k)) for k in STAT_KEYS}
    out["covered_pixel_equivalent"] = _num(pick("w_sum", "sum"))
    cnt = _num(pick("w_count", "count"))
    out["centre_pixels"] = int(cnt) if cnt is not None else None
    return out


def evaluate(lazy: Mapping[str, Any]) -> Dict[str, Any]:
    """Evaluate a dict of lazy EE objects in one call; on failure, isolate per key.

    Returns ``{key: value}`` for successes and ``{key: Exception}`` for failures, so one
    broken layer never hides the others and never turns into a value.
    """
    ee = ee_module()
    if not lazy:
        return {}
    try:
        return dict(ee.Dictionary(dict(lazy)).getInfo())
    except Exception:  # noqa: BLE001 - re-evaluated per key below; errors are kept as values
        out: Dict[str, Any] = {}
        for k, v in lazy.items():
            try:
                out[k] = ee.Dictionary({"x": v}).getInfo()["x"]
            except Exception as exc:  # noqa: BLE001 - the exception itself is the recorded result
                out[k] = exc
        return out
