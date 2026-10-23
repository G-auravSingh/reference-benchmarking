"""Earth Engine layer definitions: one builder per catalogue metric.

A builder receives an :class:`ExtractionContext` and returns a spec describing how
to measure the metric over one assessment unit. The same image builders feed the
reference pools, so site and reference are always measured with the same image
construction and scale (audit H4).

Spec kinds
  StatsSpec   - coverage-weighted statistics of a single band ``v``
  RatioSpec   - ratio of two coverage-weighted areas (extent-type metrics)
  CustomSpec  - vector or multi-step metrics returning a parsed value
  PendingSpec - metric not runnable yet (missing input or unverified access); recorded
                as ``pending_input`` or ``not_run``, never as a value

Coarse layers (native scale >= 100 m) cannot be masked pixel-by-pixel with the 10 m
natural mask, so they are weighted by the natural fraction of each coarse pixel
(EE treats fractional masks as weights). Fine layers use the binary mask directly.
Nothing here evaluates Earth Engine; evaluation happens in :mod:`extraction`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Tuple

from . import natural_mask as nm
from .ee_utils import ee_module

S2_ASSET = "COPERNICUS/S2_SR_HARMONIZED"
S2_CLOUD_ASSET = "COPERNICUS/S2_CLOUD_PROBABILITY"
HANSEN_ASSET = "UMD/hansen/global_forest_change_2025_v1_13"
META_CHM_ASSET = "projects/sat-io/open-datasets/facebook/meta-canopy-height"
GLAD_HEIGHT_ASSET = "projects/sat-io/open-datasets/GLAD/GEDI_V27"
GEDI_L2A_ASSET = "LARSE/GEDI/GEDI02_A_002_MONTHLY"
BII_ASSET = "projects/ebx-data/assets/earthblox/IO/BII_V1_1"
EII_ASSET = "projects/landler-open-data/assets/eii/global/eii_global_v1"
FLII_ASSET = "projects/darukaa-earth-product/assets/flii_global_2019"
GHM_ASSET = "TNC/HM/v3/90m_s"
GHM_BAND = "All_threats_combined"
MCD64_ASSET = "MODIS/061/MCD64A1"
VIIRS_ASSET = "NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG"
WORLDPOP_ASSET = "WorldPop/GP/100m/pop"
MOD11_ASSET = "MODIS/061/MOD11A1"
CHIRPS_ASSET = "UCSB-CHG/CHIRPS/DAILY"
TERRACLIMATE_ASSET = "IDAHO_EPSCOR/TERRACLIMATE"
JRC_GFC_ASSET = "JRC/GFC2020/V2"
JRC_GSW_ASSET = "JRC/GSW1_4/GlobalSurfaceWater"
WDPA_ASSET = "WCMC/WDPA/current/polygons"
KBA_ASSET = "projects/darukaa-earth-product/assets/Biodiversity/KBA_Global_POL_SEP25"
MAMMALS_ASSET = "projects/darukaa-earth-product/assets/Biodiversity/RedList_Mammals_Terrestrial"
BIRDS_ASSET = "projects/darukaa-earth-product/assets/Biodiversity/RedList_Bird_IUCN_Category"
PLANTS_ASSET = "projects/darukaa-earth-product/assets/Biodiversity/IUCN_Plant_Redlist"
LANDSAT_L2 = ("LANDSAT/LC08/C02/T1_L2", "LANDSAT/LC09/C02/T1_L2")


@dataclass
class ExtractionContext:
    region: Any                 # ee.Geometry of the unit (or its context window)
    unit_region: Any            # ee.Geometry of the unit itself
    crs: str                    # local UTM, e.g. "EPSG:32643"
    start: str                  # assessment window start (inclusive)
    end_exclusive: str          # assessment window end (exclusive)
    mask: Any                   # natural_mask.build_mask image
    peak_window: Tuple[str, str]  # 3-month peak-greenness window (start, end_exclusive)
    raster_paths: Dict[str, str] = field(default_factory=dict)
    options: Dict[str, Any] = field(default_factory=dict)

    @property
    def window_end_year(self) -> int:
        return int(self.end_exclusive[:4]) if self.end_exclusive[5:] != "01-01" else int(self.end_exclusive[:4]) - 1

    def opt(self, key: str, default):
        return self.options.get(key, default)


@dataclass
class StatsSpec:
    image: Any
    scale: float
    crs: Any = None              # None -> context UTM crs
    weight: str = "natural"      # natural | managed | none | strata:<codes>
    period: str = ""
    extras: Dict[str, Any] = field(default_factory=dict)
    post: Optional[Callable[[Dict[str, Optional[float]]], Optional[float]]] = None
    by_stratum: bool = False


@dataclass
class RatioSpec:
    numerator: Any
    denominator: Any
    scale: float
    factor: float = 100.0
    crs: Any = None
    period: str = ""
    min_denominator_ha: float = 0.0
    na_status: str = "not_applicable_no_natural_baseline"
    extras: Dict[str, Any] = field(default_factory=dict)
    region_key: str = "unit"     # unit | buffer_1km | ring_5km


@dataclass
class CustomSpec:
    lazy: Dict[str, Any]
    parse: Callable[[Dict[str, Any]], Tuple[Optional[float], str, Dict[str, Any]]]
    period: str = ""
    native_scale_m: Optional[float] = None


@dataclass
class PendingSpec:
    status: str   # pending_input | not_run
    reason: str


# --------------------------------------------------------------------- image builders
def s2_ndvi_collection(region, start: str, end_exclusive: str, cloud_prob_max: float = 50.0, scene_cloud_max: float = 60.0):
    """Cloud-masked Sentinel-2 NDVI (s2cloudless probability + SCL shadow/cloud classes)."""
    ee = ee_module()
    s2 = (ee.ImageCollection(S2_ASSET).filterBounds(region).filterDate(start, end_exclusive)
          .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", scene_cloud_max)))
    cp = ee.ImageCollection(S2_CLOUD_ASSET).filterBounds(region).filterDate(start, end_exclusive)
    joined = ee.ImageCollection(ee.Join.saveFirst("cloud").apply(
        s2, cp, ee.Filter.equals(leftField="system:index", rightField="system:index")))

    def one(img):
        img = ee.Image(img)
        prob = ee.Image(img.get("cloud")).select("probability")
        scl = img.select("SCL")
        ok = prob.lt(cloud_prob_max).And(scl.neq(3)).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10))
        return img.updateMask(ok).normalizedDifference(["B8", "B4"]).rename("v")

    return joined.map(one)


def ndvi_peak(ctx: ExtractionContext, region=None):
    a, b = ctx.peak_window
    col = s2_ndvi_collection(region or ctx.region, a, b, ctx.opt("s2_cloud_prob_max", 50.0), ctx.opt("s2_scene_cloud_max", 60.0))
    return col.median().rename("v"), col.size()


def monthly_ndvi_means(region, months, crs: str, cloud_prob_max: float = 50.0):
    """Lazy dict month -> mean NDVI over ``region`` (used once per project to pick the peak window)."""
    ee = ee_module()
    out = {}
    for m_start, m_end in months:
        img = s2_ndvi_collection(region, m_start, m_end, cloud_prob_max).median()
        out[m_start] = img.reduceRegion(reducer=ee.Reducer.mean(), geometry=region, scale=30, crs=crs,
                                        maxPixels=1e13, tileScale=4).get("v")
    return out


def chm_image():
    ee = ee_module()
    return ee.ImageCollection(META_CHM_ASSET).mosaic().select([0]).rename("v")


def bii_image(end_exclusive: str):
    ee = ee_module()
    col = ee.ImageCollection(BII_ASSET).filterDate("2017-01-01", end_exclusive).sort("system:time_start", False)
    img = ee.Image(col.first())
    return img.select([0]).rename("v"), ee.Date(img.get("system:time_start")).get("year")


def eii_band(band: str):
    ee = ee_module()
    return ee.Image(EII_ASSET).select([band]).rename("v")


def ghm_image(region):
    ee = ee_module()
    col = ee.ImageCollection(GHM_ASSET).filterBounds(region)
    first = ee.Image(col.first()).select(GHM_BAND)
    return col.select(GHM_BAND).mosaic().rename("v").setDefaultProjection(first.projection()), first.projection()


def fire_frequency_image(first_year: int, last_year: int):
    """Share of years with a MODIS burned-area detection, valid-data pixels only.

    A month counts only where QA bit 1 (valid data) is set; a year is masked at a
    pixel if any of its months lacks valid data there, so missing data never reads
    as "not burned". Per-year image counts are returned for the record.
    """
    ee = ee_module()
    col = ee.ImageCollection(MCD64_ASSET)
    years, counts = [], {}
    for y in range(first_year, last_year + 1):
        yc = col.filterDate(f"{y}-01-01", f"{y + 1}-01-01")
        valid_all = yc.map(lambda i: ee.Image(i).select("QA").bitwiseAnd(2).neq(0)).min()
        burned = yc.map(lambda i: ee.Image(i).select("BurnDate").gt(0).unmask(0)).max()
        years.append(burned.updateMask(valid_all).rename("v").toFloat())
        counts[str(y)] = yc.size()
    proj = ee.Image(col.first()).projection()
    return ee.ImageCollection(years).mean().rename("v").setDefaultProjection(proj), proj, counts


def viirs_image(start: str, end_exclusive: str):
    ee = ee_module()
    col = ee.ImageCollection(VIIRS_ASSET).filterDate(start, end_exclusive)
    proj = ee.Image(col.first()).select("avg_rad").projection()
    img = col.map(lambda i: ee.Image(i).select("avg_rad").updateMask(ee.Image(i).select("cf_cvg").gt(0))).median()
    return img.rename("v").setDefaultProjection(proj), proj, col.size()


def landsat_lst(region, start: str, end_exclusive: str):
    ee = ee_module()
    col = ee.ImageCollection(LANDSAT_L2[0]).merge(ee.ImageCollection(LANDSAT_L2[1])).filterBounds(region).filterDate(start, end_exclusive)

    def one(img):
        img = ee.Image(img)
        qa = img.select("QA_PIXEL")
        clear = (qa.bitwiseAnd(1 << 1).eq(0).And(qa.bitwiseAnd(1 << 2).eq(0))
                 .And(qa.bitwiseAnd(1 << 3).eq(0)).And(qa.bitwiseAnd(1 << 4).eq(0)))
        return img.select("ST_B10").multiply(0.00341802).add(149.0).subtract(273.15).updateMask(clear).rename("v")

    return col.map(one).median(), col.size()


def weight_image(ctx: ExtractionContext, kind: str, scale: float):
    """Fractional weight (0-1) of each analysis pixel that belongs to the target class."""
    ee = ee_module()
    m = ctx.mask
    if kind == "none":
        return None
    if kind == "natural":
        w = m.select("natural_now")
    elif kind == "managed":
        w = m.select("managed")
    elif kind.startswith("strata:"):
        codes = [int(x) for x in kind.split(":", 1)[1].split(",")]
        s = m.select("stratum")
        w = s.eq(codes[0])
        for code in codes[1:]:
            w = w.Or(s.eq(code))
    else:
        raise ValueError(f"Unknown weight kind {kind}")
    w = w.unmask(0).toFloat().setDefaultProjection(crs=ctx.crs, scale=10)
    if scale <= 10:
        return w
    return (w.reduceResolution(reducer=ee.Reducer.mean(), bestEffort=False, maxPixels=65535)
             .reproject(crs=ctx.crs, scale=scale))


# --------------------------------------------------------------------- builders
def _woody(ctx):
    return "strata:" + ",".join(str(c) for c in nm.WOODY_STRATA)


def b_natural_extent(ctx):
    m = ctx.mask
    return RatioSpec(m.select("natural_now"), m.select("dw_label").gte(0), 10, 100.0, period=f"natural 2020 (ForTy/SBTN); DW {ctx.start}..{ctx.end_exclusive}",
                     extras={"uncertain_pct": (m.select("uncertain"), "pct"), "managed_pct": (m.select("managed"), "pct"),
                             "natural_2020_pct": (m.select("natural_2020").And(m.select("uncertain").eq(0)), "pct")},
                     na_status="no_valid_pixels")


def b_gross_loss(ctx):
    m = ctx.mask
    base = m.select("natural_2020").And(m.select("uncertain").eq(0))
    return RatioSpec(m.select("loss"), base, 10, 100.0, period=f"2020 -> {ctx.start}..{ctx.end_exclusive}",
                     min_denominator_ha=0.01, na_status="not_applicable_no_natural_baseline",
                     extras={"gross_loss_ha": (m.select("loss"), "ha")})


def b_gross_gain(ctx):
    m = ctx.mask
    return RatioSpec(m.select("gain_candidate"), m.select("dw_label").gte(0), 10, factor=None,
                     period=f"2020 -> {ctx.start}..{ctx.end_exclusive}", na_status="no_valid_pixels")


def b_core_area(ctx):
    m = ctx.mask
    nat = m.select("natural_now").unmask(0)
    core = nat.focalMin(radius=ctx.opt("core_edge_depth_m", 30.0), kernelType="circle", units="meters").And(nat)
    return RatioSpec(core, m.select("dw_label").gte(0), 10, 100.0, period=f"DW {ctx.start}..{ctx.end_exclusive}",
                     na_status="no_valid_pixels", extras={"edge_depth_m": ctx.opt("core_edge_depth_m", 30.0)})


def b_extent_by_type(ctx):
    ee = ee_module()
    m = ctx.mask
    area = ee.Image.pixelArea().addBands(m.select("stratum"))
    lazy = {"by_stratum": area.updateMask(m.select("natural_now").Or(m.select("managed"))).reduceRegion(
        reducer=ee.Reducer.sum().group(groupField=1, groupName="stratum"), geometry=ctx.unit_region, scale=10,
        crs=ctx.crs, maxPixels=1e13, tileScale=4)}

    def parse(raw):
        groups = (raw.get("by_stratum") or {}).get("groups", [])
        ha = {nm.STRATA.get(int(g["stratum"]), str(g["stratum"])): round(g["sum"] / 1e4, 4) for g in groups if int(g["stratum"]) in nm.STRATA}
        natural = sum(v for k, v in ha.items() if k in {nm.STRATA[c] for c in nm.NATURAL_STRATA})
        return natural, "ok", {"area_ha_by_type": ha}
    return CustomSpec(lazy, parse, period=f"DW {ctx.start}..{ctx.end_exclusive}", native_scale_m=10)


def b_tree_loss_rate(ctx):
    ee = ee_module()
    h = ee.Image(HANSEN_ASSET)
    thr = ctx.opt("tree_cover_threshold_pct", 10)
    last = ctx.opt("hansen_last_year", 2025)
    n = ctx.opt("tree_loss_years", 5)
    base = h.select("treecover2000").gte(thr)
    ly = h.select("lossyear")
    loss = base.And(ly.gte(last - 2000 - n + 1)).And(ly.lte(last - 2000))
    return RatioSpec(loss, base, None, 100.0 / n, crs=h.projection(), period=f"Hansen v1.13 loss {last - n + 1}-{last}; baseline 2000, canopy >= {thr}%",
                     min_denominator_ha=ctx.opt("min_forest_baseline_ha", 1.0), na_status="not_applicable_no_forest_baseline",
                     extras={"baseline_forest_ha": (base, "ha"), "loss_ha": (loss, "ha")})


def b_jrc_forest(ctx):
    ee = ee_module()
    img = ee.ImageCollection(JRC_GFC_ASSET).mosaic().select([0]).eq(1)
    return RatioSpec(img, ee.Image.constant(1), 10, 100.0, period="2020", na_status="no_valid_pixels")


def b_surface_water(ctx):
    ee = ee_module()
    occ = ee.Image(JRC_GSW_ASSET).select("occurrence")
    return RatioSpec(occ.gte(50), ee.Image.constant(1), 30, factor=None, period="JRC GSW 1984-2021 occurrence >= 50%",
                     na_status="no_valid_pixels", extras={"max_extent_ha": (ee.Image(JRC_GSW_ASSET).select("max_extent"), "ha")})


def b_landscape_extent(ctx):
    m = ctx.mask
    return RatioSpec(m.select("natural_now"), m.select("dw_label").gte(0), 30, 100.0, region_key="ring_5km",
                     period=f"DW {ctx.start}..{ctx.end_exclusive}", na_status="no_valid_pixels")


def _overlap_spec(ctx, fc, label):
    ee = ee_module()
    near = fc.filterBounds(ctx.unit_region.buffer(50000))
    # Dissolve first so nested designations (e.g. a park inside a sanctuary) are not counted twice.
    inter = (near.filterBounds(ctx.unit_region).union(ee.ErrorMargin(10)).geometry()
             .intersection(ctx.unit_region, ee.ErrorMargin(10)))
    lazy = {"overlap_m2": inter.area(ee.ErrorMargin(10)), "unit_m2": ctx.unit_region.area(ee.ErrorMargin(10)),
            "n_near": near.size(),
            "distance_m": ee.Algorithms.If(near.size().gt(0), ctx.unit_region.distance(near.geometry(), ee.ErrorMargin(10)), None)}

    def parse(raw):
        unit = raw.get("unit_m2") or 0
        if unit <= 0:
            return None, "no_valid_pixels", {}
        extras = {"distance_to_nearest_m": raw.get("distance_m") if (raw.get("n_near") or 0) > 0 else None,
                  "n_within_50km": raw.get("n_near"), "layer": label}
        pct = 100.0 * (raw.get("overlap_m2") or 0) / unit
        if pct > 100.5:
            return None, "out_of_range_review", extras
        return min(pct, 100.0), "ok", extras
    return CustomSpec(lazy, parse, period="current release")


def b_kba(ctx):
    ee = ee_module()
    return _overlap_spec(ctx, ee.FeatureCollection(ctx.raster_paths.get("kba", KBA_ASSET)), "KBA")


def b_wdpa(ctx):
    ee = ee_module()
    fc = (ee.FeatureCollection(WDPA_ASSET)
          .filter(ee.Filter.inList("STATUS", ["Designated", "Inscribed", "Established"]))
          .filter(ee.Filter.neq("DESIG_ENG", "UNESCO-MAB Biosphere Reserve")))
    return _overlap_spec(ctx, fc, "WDPA")


def b_ndvi(ctx):
    img, n = ndvi_peak(ctx)
    return StatsSpec(img, 10, weight="natural", by_stratum=True, period=f"S2 peak window {ctx.peak_window[0]}..{ctx.peak_window[1]}",
                     extras={"n_scenes": n})


def b_managed_ndvi(ctx):
    img, n = ndvi_peak(ctx)
    return StatsSpec(img, 10, weight="managed", by_stratum=True, period=f"S2 peak window {ctx.peak_window[0]}..{ctx.peak_window[1]}",
                     extras={"n_scenes": n})


def b_sbi(ctx):
    img, n = ndvi_peak(ctx)

    def sbi(stats):
        sd, p95 = stats.get("stdDev"), stats.get("p95")
        if sd is None or p95 is None or p95 <= 0:
            return None
        return sd / p95
    return StatsSpec(img, 10, weight="none", period=f"S2 peak window {ctx.peak_window[0]}..{ctx.peak_window[1]}",
                     post=sbi, extras={"n_scenes": n})


def b_chm(ctx):
    return StatsSpec(chm_image(), 1, weight=_woody(ctx), by_stratum=True, period="Meta/WRI imagery 2009-2020 (mostly 2018-2020)")


def b_managed_chm(ctx):
    return StatsSpec(chm_image(), 1, weight="managed", by_stratum=True, period="Meta/WRI imagery 2009-2020 (mostly 2018-2020)")


def b_glad_height(ctx):
    ee = ee_module()
    raw = ee.ImageCollection(GLAD_HEIGHT_ASSET).mosaic().select([0])
    img = raw.updateMask(raw.lte(60)).rename("v")   # 101 water, 102 snow/ice, 103 no data are codes, not heights
    return StatsSpec(img, 30, weight="strata:10", period="2019/2020")


def b_gedi(ctx):
    ee = ee_module()
    col = ee.ImageCollection(GEDI_L2A_ASSET).filterBounds(ctx.region)

    def q(i):
        i = ee.Image(i)
        return i.select("rh98").updateMask(i.select("quality_flag").eq(1).And(i.select("degrade_flag").eq(0)))
    img = col.map(q).mean().rename("v")
    return StatsSpec(img, 25, weight=_woody(ctx), period="GEDI L2A 2019-2025")


def b_bii(ctx):
    img, year = bii_image(ctx.end_exclusive)
    return StatsSpec(img, 100, weight="natural", period="latest BII year <= window end", extras={"bii_year": year})


def b_eii(band):
    def _b(ctx):
        return StatsSpec(eii_band(band), 300, weight="natural", period="EII v1 (inputs 2020-2022)")
    return _b


def b_flii(ctx):
    ee = ee_module()
    asset = ctx.raster_paths.get("flii_gee_asset", FLII_ASSET)
    return StatsSpec(ee.Image(asset).select([0]).rename("v"), 300, weight="strata:10", period="FLII 2019")


def b_msa(ctx):
    asset = ctx.raster_paths.get("msa_gee_asset")
    if not asset:
        return PendingSpec("pending_input", "GLOBIO4 MSA 2015 is not in Earth Engine; upload it and set raster_paths['msa_gee_asset']")
    ee = ee_module()
    return StatsSpec(ee.Image(asset).select([0]).rename("v"), 300, weight="natural", period="GLOBIO4 2015")


def b_built_fraction(ctx):
    m = ctx.mask
    return RatioSpec(m.select("dw_label").eq(nm.DW["built"]), m.select("dw_label").gte(0), 10, 1.0,
                     period=f"DW {ctx.start}..{ctx.end_exclusive}", na_status="no_valid_pixels")


def b_ghm(ctx):
    img, proj = ghm_image(ctx.region)
    return StatsSpec(img, None, crs=proj, weight="none", period="gHM v3 2022")


def b_fire(ctx):
    first, last = ctx.opt("fire_first_year", 2016), ctx.opt("fire_last_year", 2025)
    img, proj, counts = fire_frequency_image(first, last)
    return StatsSpec(img, None, crs=proj, weight="none", period=f"MCD64A1 {first}-{last}",
                     extras={"images_per_year": counts})


def b_night_lights(ctx):
    img, proj, n = viirs_image(ctx.start, ctx.end_exclusive)
    return StatsSpec(img, None, crs=proj, weight="none", period=f"VIIRS monthly {ctx.start}..{ctx.end_exclusive}", extras={"n_months": n})


def b_population(ctx):
    ee = ee_module()
    col = ee.ImageCollection(WORLDPOP_ASSET).filter(ee.Filter.eq("year", 2020)).filterBounds(ctx.region)
    proj = ee.Image(col.first()).select("population").projection()
    pop = col.mosaic().select("population")
    # Counts are summed on WorldPop's own grid; resampling to a metric grid would
    # sample each native cell about cos(latitude) times and under-count.
    lazy = {"people": pop.reduceRegion(reducer=ee.Reducer.sum(), geometry=ctx.region, crs=proj, scale=None,
                                        maxPixels=1e13, tileScale=4).get("population"),
            "area_m2": ctx.region.area(ee.ErrorMargin(1))}

    def parse(raw):
        a = raw.get("area_m2") or 0
        if raw.get("people") is None or a <= 0:
            return None, "no_valid_pixels", {}
        return raw["people"] / (a / 1e6), "ok", {"people": raw["people"]}
    return CustomSpec(lazy, parse, period="WorldPop 2020", native_scale_m=92.77)


def b_road_density(ctx):
    ee = ee_module()
    asset = ctx.raster_paths.get("grip4_asset")
    if not asset:
        return PendingSpec("pending_input", "GRIP4 regional asset path not set (raster_paths['grip4_asset']); confirm in the EE probe")
    region = ctx.region
    roads = ee.FeatureCollection(asset).filterBounds(region)
    length_m = roads.map(lambda f: f.set("len", f.geometry().intersection(region, ee.ErrorMargin(1)).length(ee.ErrorMargin(1)))).aggregate_sum("len")
    lazy = {"length_m": length_m, "area_m2": region.area(ee.ErrorMargin(1)),
            "n_within_10km": ee.FeatureCollection(asset).filterBounds(region.buffer(10000)).limit(1).size()}

    def parse(raw):
        a = raw.get("area_m2") or 0
        if a <= 0 or raw.get("length_m") is None:
            return None, "no_valid_pixels", {}
        if not raw.get("n_within_10km"):
            # No road at all within 10 km usually means the regional asset does not cover
            # this area; an empty query must not read as a genuine zero density.
            return None, "source_unavailable", {"note": "no GRIP4 road within 10 km; check asset coverage"}
        return (raw["length_m"] / 1000.0) / (a / 1e6), "ok", {"road_km": raw["length_m"] / 1000.0}
    return CustomSpec(lazy, parse, period="GRIP4 (~2018)")


def b_lst_day(ctx):
    img, n = landsat_lst(ctx.region, ctx.start, ctx.end_exclusive)
    return StatsSpec(img.rename("v"), 30, weight="none", period=f"Landsat 8/9 {ctx.start}..{ctx.end_exclusive}", extras={"n_scenes": n})


def b_lst_night(ctx):
    ee = ee_module()
    col = ee.ImageCollection(MOD11_ASSET).filterDate(ctx.start, ctx.end_exclusive)
    proj = ee.Image(col.first()).select("LST_Night_1km").projection()
    img = col.select("LST_Night_1km").mean().multiply(0.02).subtract(273.15).rename("v").setDefaultProjection(proj)
    return StatsSpec(img, None, crs=proj, weight="none", period=f"MOD11A1 {ctx.start}..{ctx.end_exclusive}")


def b_aridity(ctx):
    ee = ee_module()
    y = ctx.window_end_year - 1
    p = ee.ImageCollection(CHIRPS_ASSET).filterDate(f"{y}-01-01", f"{y + 1}-01-01").select("precipitation").sum()
    pet = ee.ImageCollection(TERRACLIMATE_ASSET).filterDate(f"{y}-01-01", f"{y + 1}-01-01").select("pet").sum().multiply(0.1)
    return StatsSpec(p.divide(pet).rename("v"), 4638.3, weight="none", period=f"{y} (CHIRPS / TerraClimate PET)")


def b_managed_area(ctx):
    m = ctx.mask
    return RatioSpec(m.select("managed"), m.select("dw_label").gte(0), 10, 100.0, period=f"DW {ctx.start}..{ctx.end_exclusive}",
                     na_status="no_valid_pixels")


def _range_count(ctx, assets, filt=None, required_fields=("sci_name",)):
    """Count species from Darukaa-held IUCN range snapshots overlapping the unit.

    Each asset is checked lazily for the fields the filter needs; a missing field is
    an error, never an empty (zero) count.
    """
    ee = ee_module()
    lazy = {}
    for name, asset in assets:
        full = ee.FeatureCollection(ctx.raster_paths.get(name, asset))
        fc = full.filterBounds(ctx.unit_region)
        if filt is not None:
            fc = filt(fc, full)
        lazy[name] = fc.aggregate_array("sci_name").distinct().size()
        lazy[f"fields_{name}"] = full.first().propertyNames().containsAll(list(required_fields))

    def parse(raw):
        missing = [k[7:] for k, v in raw.items() if k.startswith("fields_") and not v]
        if missing:
            raise ValueError(f"range asset(s) {missing} lack required fields {list(required_fields)}")
        counts = {k: int(v) for k, v in raw.items() if not k.startswith("fields_") and v is not None}
        return float(sum(counts.values())), "ok", counts
    return CustomSpec(lazy, parse, period="Darukaa-held IUCN range snapshots")


def b_threatened_range(ctx):
    ee = ee_module()
    field = ctx.opt("iucn_category_field", "category")
    return _range_count(ctx, [("mammals", MAMMALS_ASSET), ("birds", BIRDS_ASSET)],
                        lambda fc, full: fc.filter(ee.Filter.inList(field, ["CR", "EN", "VU"])),
                        required_fields=("sci_name", field))


def b_restricted_range(ctx):
    """Species whose WHOLE range (all features of the species) is < 100,000 km2."""
    ee = ee_module()

    def small(fc, full):
        names = fc.aggregate_array("sci_name").distinct()
        parts = full.filter(ee.Filter.inList("sci_name", names)).map(
            lambda f: f.set("rk2", f.geometry().area(ee.ErrorMargin(1000)).divide(1e6)))
        groups = ee.List(parts.reduceColumns(ee.Reducer.sum().group(groupField=1, groupName="sci_name"),
                                             ["rk2", "sci_name"]).get("groups"))
        small_names = groups.filter(ee.Filter.lt("sum", 100000)).map(lambda g: ee.Dictionary(g).get("sci_name"))
        return fc.filter(ee.Filter.inList("sci_name", small_names))
    return _range_count(ctx, [("mammals", MAMMALS_ASSET), ("birds", BIRDS_ASSET), ("plants", PLANTS_ASSET)], small)


def b_star(ctx):
    asset = ctx.raster_paths.get("star_t")
    if not asset:
        return PendingSpec("pending_input", "No IBAT STAR-t raster supplied")
    ee = ee_module()
    img = ee.Image(asset).select([0])
    lazy = {"sum": img.reduceRegion(reducer=ee.Reducer.sum(), geometry=ctx.unit_region, crs=img.projection(), scale=None,
                                     maxPixels=1e13).values().get(0)}
    return CustomSpec(lazy, lambda raw: (raw.get("sum"), "ok" if raw.get("sum") is not None else "no_valid_pixels", {}),
                      period="IBAT STAR-t", native_scale_m=1000)


BUILDERS: Dict[str, Callable[[ExtractionContext], Any]] = {
    "natural_extent_pct": b_natural_extent,
    "natural_gross_loss_pct": b_gross_loss,
    "tree_cover_loss_rate": b_tree_loss_rate,
    "natural_core_area_pct": b_core_area,
    "natural_gross_gain_ha": b_gross_gain,
    "natural_extent_by_type_ha": b_extent_by_type,
    "forest_cover_2020_jrc_pct": b_jrc_forest,
    "surface_water_extent_ha": b_surface_water,
    "landscape_natural_extent_pct": b_landscape_extent,
    "kba_overlap_pct": b_kba,
    "protected_area_overlap_pct": b_wdpa,
    "ndvi_peak_season": b_ndvi,
    "lai_s2": lambda ctx: PendingSpec("not_run", "SL2P LAI implementation in EE not yet verified (catalogue v1 note)"),
    "canopy_height_m": b_chm,
    "bii": b_bii,
    "eii_functional": b_eii("functional_integrity"),
    "flii": b_flii,
    "gedi_rh98_m": b_gedi,
    "canopy_height_glad_m": b_glad_height,
    "pv_habitat_health_sbi": b_sbi,
    "eii": b_eii("eii"),
    "eii_structural": b_eii("structural_integrity"),
    "eii_compositional": b_eii("compositional_integrity"),
    "msa": b_msa,
    "landscape_connectivity": lambda ctx: PendingSpec("not_run", "Connectance implementation pending"),
    "species_records_screen": lambda ctx: PendingSpec("not_run", "Computed outside EE by darukaa_adaptive.gbif"),
    "scheduled_species_records": lambda ctx: PendingSpec("pending_input", "Needs the WPA 2022 Schedule species list (CSV)"),
    "threatened_species_range_count": b_threatened_range,
    "restricted_range_species_count": b_restricted_range,
    "star_t": b_star,
    "built_fraction": b_built_fraction,
    "ghm": b_ghm,
    "road_density": b_road_density,
    "fire_frequency": b_fire,
    "night_lights": b_night_lights,
    "forest_disturbance_alerts": lambda ctx: PendingSpec("not_run", "GFW integrated alerts EE access to be confirmed in the probe"),
    "population_density": b_population,
    "lst_day": b_lst_day,
    "lst_night": b_lst_night,
    "aridity_index": b_aridity,
    "managed_area_pct": b_managed_area,
    "managed_ndvi": b_managed_ndvi,
    "managed_canopy_height_m": b_managed_chm,
}

# Metrics whose regional reference is built from block-level values with the same
# areal support as the site (Approach 4), rather than from a pixel sample.
AREAL_METRICS = {"natural_gross_loss_pct", "tree_cover_loss_rate", "built_fraction", "road_density",
                 "population_density", "natural_core_area_pct", "natural_extent_pct"}
