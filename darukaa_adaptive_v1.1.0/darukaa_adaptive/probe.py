"""Read-only Earth Engine probe (Colab run CR1).

Answers the open questions in metric catalogue v1 before scores are read:
asset reachability, band names, native scales, years, and true pixel support for
the test units. Every check is isolated; a failure is recorded, never hidden.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Sequence, Tuple

from shapely.geometry.base import BaseGeometry

from . import layers as L
from . import natural_mask as nm
from .ee_utils import ee_module, to_ee, utm_crs

GRIP4_FOLDER = "projects/sat-io/open-datasets/GRIP4"


def _try(fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - the error text is the probe result
        return {"error": f"{type(exc).__name__}: {exc}"}


def _image_info(ee, img) -> Dict[str, Any]:
    info = img.getInfo()
    bands = info.get("bands", [])
    return {"bands": [b["id"] for b in bands],
            "crs": bands[0].get("crs") if bands else None,
            "scale_m": img.select(0).projection().nominalScale().getInfo() if bands else None}


def asset_checks() -> Dict[str, Any]:
    ee = ee_module()
    col = lambda a: ee.ImageCollection(a)  # noqa: E731
    out: Dict[str, Any] = {}
    images = {
        "hansen": lambda: ee.Image(L.HANSEN_ASSET), "sbtn": lambda: ee.Image(nm.SBTN_ASSET),
        "eii": lambda: ee.Image(L.EII_ASSET), "flii": lambda: ee.Image(L.FLII_ASSET),
        "jrc_gsw": lambda: ee.Image(L.JRC_GSW_ASSET),
    }
    for k, f in images.items():
        out[k] = _try(lambda f=f: _image_info(ee, f()))
    cols = {"forty": nm.FORTY_ASSET, "meta_chm": L.META_CHM_ASSET, "glad_height": L.GLAD_HEIGHT_ASSET,
            "bii": L.BII_ASSET, "ghm": L.GHM_ASSET, "jrc_gfc2020": L.JRC_GFC_ASSET, "gedi_l2a": L.GEDI_L2A_ASSET,
            "mcd64a1": L.MCD64_ASSET, "viirs": L.VIIRS_ASSET, "worldpop": L.WORLDPOP_ASSET, "dynamic_world": nm.DW_ASSET}
    for k, a in cols.items():
        out[k] = _try(lambda a=a: {"size": col(a).limit(5000).size().getInfo(), **_image_info(ee, ee.Image(col(a).first()))})
    out["bii_years"] = _try(lambda: sorted(set(ee.ImageCollection(L.BII_ASSET).aggregate_array("system:time_start")
                                               .map(lambda t: ee.Date(t).get("year")).getInfo())))
    out["grip4_assets"] = _try(lambda: [a["id"] for a in ee.data.listAssets({"parent": GRIP4_FOLDER}).get("assets", [])])
    for k, a in {"kba": L.KBA_ASSET, "wdpa": L.WDPA_ASSET, "mammals": L.MAMMALS_ASSET, "birds": L.BIRDS_ASSET, "plants": L.PLANTS_ASSET}.items():
        out[f"{k}_fields"] = _try(lambda a=a: ee.FeatureCollection(a).first().propertyNames().getInfo())
    out["mammals_category_values"] = _try(lambda: ee.FeatureCollection(L.MAMMALS_ASSET).aggregate_histogram("category").getInfo())
    return out


def unit_checks(units: Sequence[Tuple[str, BaseGeometry]], window: Tuple[str, str]) -> Dict[str, Any]:
    ee = ee_module()
    out: Dict[str, Any] = {}
    for uid, geom in units:
        g = to_ee(geom)
        crs = utm_crs(geom)
        r: Dict[str, Any] = {"area_ha": geom.area and None}
        from .site import area_ha
        r["area_ha"] = area_ha(geom)

        def px(img, scale, crs_=crs):
            v = img.select([0]).rename("v")
            one = ee.Image.constant(1).updateMask(v.mask())
            d = one.reduceRegion(ee.Reducer.sum().combine(ee.Reducer.count().unweighted(), sharedInputs=True), g, scale, crs_, maxPixels=1e13)
            m = v.reduceRegion(ee.Reducer.mean(), g, scale, crs_, maxPixels=1e13)
            return {"covered_pixel_equivalent": d.get("constant_sum"), "centre_pixels": d.get("constant_count"), "mean": m.get("v")}

        h = ee.Image(L.HANSEN_ASSET)
        r["hansen_baseline_ha"] = _try(lambda: {t: h.select("treecover2000").gte(t).multiply(ee.Image.pixelArea()).divide(1e4).reduceRegion(
            ee.Reducer.sum(), g, None, h.projection(), maxPixels=1e13).getInfo() for t in (10, 30)})
        r["eii_bands"] = _try(lambda: {b: ee.Dictionary(px(ee.Image(L.EII_ASSET).select(b), 300)).getInfo()
                                       for b in ("eii", "functional_integrity", "structural_integrity", "compositional_integrity")})
        r["flii"] = _try(lambda: ee.Dictionary(px(ee.Image(L.FLII_ASSET), 300)).getInfo())
        r["bii"] = _try(lambda: ee.Dictionary(px(L.bii_image(window[1])[0], 100)).getInfo())
        ghm, proj = L.ghm_image(g)
        r["ghm_90m"] = _try(lambda: ee.Dictionary(px(ghm, 90, proj)).getInfo())
        r["ghm_1000m_old_scale"] = _try(lambda: ee.Dictionary(px(ghm, 1000, proj)).getInfo())
        mask, dwn = nm.build_mask(g, window[0], window[1], crs=crs)
        r["natural_mask"] = _try(lambda: {"dw_images": dwn.getInfo(), "means": mask.select(
            ["natural_2020", "natural_now", "loss", "gain_candidate", "managed", "uncertain"]).reduceRegion(
            ee.Reducer.mean(), g, 10, crs, maxPixels=1e13).getInfo(),
            "strata": mask.select("stratum").reduceRegion(ee.Reducer.frequencyHistogram(), g, 10, crs, maxPixels=1e13).getInfo()})
        r["meta_chm_mean_10m"] = _try(lambda: ee.Dictionary(px(L.chm_image(), 10)).getInfo())
        # Weight-path check (review finding 1): the 300 m natural fraction must match the 10 m mean.
        r["weight_check"] = _try(lambda: {
            "natural_now_mean_10m": mask.select("natural_now").reduceRegion(ee.Reducer.mean(), g, 10, crs, maxPixels=1e13).get("natural_now").getInfo(),
            "natural_weight_mean_300m": mask.select("natural_now").unmask(0).toFloat().setDefaultProjection(crs=crs, scale=10)
                .reduceResolution(ee.Reducer.mean(), False, 65535).reproject(crs=crs, scale=300)
                .reduceRegion(ee.Reducer.mean(), g, 300, crs, maxPixels=1e13).get("natural_now").getInfo()})
        r["glad_height_codes"] = _try(lambda: ee.ImageCollection(L.GLAD_HEIGHT_ASSET).mosaic().select([0]).reduceRegion(
            ee.Reducer.frequencyHistogram(), g, 30, crs, maxPixels=1e13).getInfo())
        r["fire_images_per_year"] = _try(lambda: {y: ee.ImageCollection(L.MCD64_ASSET).filterDate(f"{y}-01-01", f"{y+1}-01-01").size().getInfo()
                                                  for y in (2016, 2020, 2024, 2025)})
        out[uid] = r
    return out


def run_probe(units: Sequence[Tuple[str, BaseGeometry]], window: Tuple[str, str], path: str = "probe_results.json") -> Dict[str, Any]:
    result = {"assets": asset_checks(), "units": unit_checks(units, window), "window": list(window)}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    return result
