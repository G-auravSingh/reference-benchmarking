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
# P-27-1: no public Earth Engine asset ID for Meta/WRI CHMv2 was found on 27 Oct 2026
# (Meta blog, AWS registry, Zenodo, GEE community catalogue). These folders are listed
# read-only to find it; any ID the user pastes is checked too.
CHMV2_SEARCH_FOLDERS = ("projects/meta-forest-monitoring-okw37/assets", "projects/sat-io/open-datasets/facebook")
CHMV2_KEYWORDS = ("v2", "chm", "canopy")


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


def chmv2_search(candidates: Sequence[str] = ()) -> Dict[str, Any]:
    """List likely CHMv2 assets and describe each candidate (bands, scale, size). Read-only."""
    ee = ee_module()
    out: Dict[str, Any] = {"folders": {}, "candidates": {}}
    for folder in CHMV2_SEARCH_FOLDERS:
        out["folders"][folder] = _try(lambda folder=folder: [
            {"id": a.get("id") or a.get("name"), "type": a.get("type")}
            for a in ee.data.listAssets({"parent": folder}).get("assets", [])
            if any(k in (a.get("id") or a.get("name") or "").lower() for k in CHMV2_KEYWORDS)])
    found = [a["id"] for v in out["folders"].values() if isinstance(v, list) for a in v if a.get("id")]
    for cid in dict.fromkeys(list(candidates) + found):
        if cid == L.META_CHM_ASSET:
            continue
        def describe(cid=cid):
            try:
                n = ee.ImageCollection(cid).limit(100000).size().getInfo()
                img, kind = ee.Image(ee.ImageCollection(cid).first()), "ImageCollection"
            except Exception:  # noqa: BLE001 - may be a single Image, not a collection
                img, n, kind = ee.Image(cid), None, "Image"
            props = img.toDictionary().getInfo()
            return {"kind": kind, "collection_size": n, **_image_info(ee, img),
                    "properties_sample": dict(list(props.items())[:15])}
        out["candidates"][cid] = _try(describe)
    return out


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
            "bii": L.BII_ASSET, "ghm": L.GHM_ASSET, "jrc_gfc2020": L.JRC_GFC_ASSET, "jrc_gfc2020_v4": "JRC/GFC2020/V4", "gedi_l2a": L.GEDI_L2A_ASSET,
            "mcd64a1": L.MCD64_ASSET, "viirs": L.VIIRS_ASSET, "worldpop": L.WORLDPOP_ASSET, "dynamic_world": nm.DW_ASSET}
    for k, a in cols.items():
        out[k] = _try(lambda a=a: {"size": col(a).limit(5000).size().getInfo(), **_image_info(ee, ee.Image(col(a).first()))})
    out["bii_years"] = _try(lambda: sorted(set(ee.ImageCollection(L.BII_ASSET).aggregate_array("system:time_start")
                                               .map(lambda t: ee.Date(t).get("year")).getInfo())))
    out["grip4_south_east_asia_fields"] = _try(lambda: ee.FeatureCollection(f"{GRIP4_FOLDER}/South-East-Asia").first().propertyNames().getInfo())
    for k, a in {"kba": L.KBA_ASSET, "wdpa": L.WDPA_ASSET, "mammals": L.MAMMALS_ASSET, "birds": L.BIRDS_ASSET, "plants": L.PLANTS_ASSET}.items():
        out[f"{k}_fields"] = _try(lambda a=a: ee.FeatureCollection(a).first().propertyNames().getInfo())
    out["mammals_category_values"] = _try(lambda: ee.FeatureCollection(L.MAMMALS_ASSET).aggregate_histogram("category").getInfo())
    out["birds_redlist_values"] = _try(lambda: {f: ee.FeatureCollection(L.BIRDS_ASSET).limit(5000).aggregate_histogram(f).getInfo()
                                                for f in ("RedList_IU", "RedList__1", "RedList__5")})
    out["terraclimate_last"] = _try(lambda: ee.Date(ee.ImageCollection(L.TERRACLIMATE_ASSET).sort("system:time_start", False)
                                                    .first().get("system:time_start")).format("YYYY-MM").getInfo())
    return out


def _load_height(ee, asset: str, band: str, kind: str):
    src = ee.ImageCollection(asset).mosaic() if kind == "ImageCollection" else ee.Image(asset)
    return src.select([band])


def unit_checks(units: Sequence[Tuple[str, BaseGeometry]], window: Tuple[str, str],
                chm_candidates: Sequence[Tuple[str, str, str]] = ()) -> Dict[str, Any]:
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
        # Canopy-height cross-check (Karpa run 26 Oct: Meta 1 m read ~0 m on DW woodland).
        r["canopy_height_sources"] = _try(lambda: {
            "meta_hist_m": L.chm_image().reduceRegion(ee.Reducer.fixedHistogram(0, 30, 15), g, 10, crs, maxPixels=1e13).getInfo(),
            "glad_mean_m": ee.Dictionary(px(ee.ImageCollection(L.GLAD_HEIGHT_ASSET).mosaic().select([0]).updateMask(
                ee.ImageCollection(L.GLAD_HEIGHT_ASSET).mosaic().select([0]).lte(60)), 30)).getInfo(),
            "gedi_rh98": ee.ImageCollection(L.GEDI_L2A_ASSET).filterBounds(g).map(
                lambda i: ee.Image(i).select("rh98").updateMask(ee.Image(i).select("quality_flag").eq(1).And(
                    ee.Image(i).select("degrade_flag").eq(0)))).mean().reduceRegion(
                ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True), g, 25, crs, maxPixels=1e13).getInfo(),
            "dw_trees_prob_window": ee.ImageCollection(nm.DW_ASSET).filterBounds(g).filterDate(window[0], window[1])
                .select("trees").mean().reduceRegion(ee.Reducer.mean(), g, 10, crs, maxPixels=1e13).getInfo(),
            "forty_class_hist": nm.forty_class(g)[0].reduceRegion(ee.Reducer.frequencyHistogram(), g, 10, crs, maxPixels=1e13).getInfo(),
            "sbtn_class_hist": ee.Image(nm.SBTN_ASSET).select("classification").reduceRegion(
                ee.Reducer.frequencyHistogram(), g, 30, crs, maxPixels=1e13).getInfo()})
        # P-27-1: CHMv2 beside v1 on the same units (asset, band) pairs confirmed by chmv2_search.
        r["chmv2_vs_v1"] = {f"{a}:{b}": _try(lambda a=a, b=b, k=k: {
            "hist_m": _load_height(ee, a, b, k).reduceRegion(
                ee.Reducer.fixedHistogram(0, 30, 15), g, 10, crs, maxPixels=1e13).getInfo(),
            **ee.Dictionary(px(_load_height(ee, a, b, k), 10)).getInfo()}) for a, b, k in chm_candidates}
        r["glad_height_codes"] = _try(lambda: ee.ImageCollection(L.GLAD_HEIGHT_ASSET).mosaic().select([0]).reduceRegion(
            ee.Reducer.frequencyHistogram(), g, 30, crs, maxPixels=1e13).getInfo())
        r["fire_images_per_year"] = _try(lambda: {y: ee.ImageCollection(L.MCD64_ASSET).filterDate(f"{y}-01-01", f"{y+1}-01-01").size().getInfo()
                                                  for y in (2016, 2020, 2024, 2025)})
        out[uid] = r
    return out


def run_probe(units: Sequence[Tuple[str, BaseGeometry]], window: Tuple[str, str], path: str = "probe_results.json",
              chmv2_candidates: Sequence[str] = (), chmv2_band: str = "") -> Dict[str, Any]:
    """``chmv2_candidates``: CHMv2 asset IDs to check; ``chmv2_band``: band to compare on the units
    (left empty, the first band of each candidate is used)."""
    search = _try(lambda: chmv2_search(chmv2_candidates))
    pairs = []
    if isinstance(search, dict):
        for cid, info in search.get("candidates", {}).items():
            if isinstance(info, dict) and info.get("bands"):
                pairs.append((cid, chmv2_band or info["bands"][0], info.get("kind", "ImageCollection")))
    result = {"assets": asset_checks(), "chmv2_search": search,
              "units": unit_checks(units, window, pairs), "window": list(window)}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    return result
