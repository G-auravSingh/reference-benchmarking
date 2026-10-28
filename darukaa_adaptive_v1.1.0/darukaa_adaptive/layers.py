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
    qa: Optional[Callable[[Any], Any]] = None   # Measurement -> Measurement, after the contract gates


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


def chm_source(options=None):
    """(asset, band, label) of the 1 m canopy-height source (P-27-1).

    Default is Meta/WRI v1 (band "cover_code", EE probe 24 Oct). CHMv2 is switched on by
    setting all three options ``chm_asset``, ``chm_band`` and ``chm_label`` once the probe
    has confirmed its Earth Engine asset and band; a partial setting is an error, never a
    silent fallback to v1.
    """
    o = options or {}
    keys = ("chm_asset", "chm_band", "chm_label")
    given = [k for k in keys if o.get(k)]
    if not given:
        return META_CHM_ASSET, "cover_code", "Meta/WRI CHM v1 (imagery 2009-2020, mostly 2018-2020)"
    if len(given) != len(keys):
        raise ValueError(f"canopy-height source half configured: set all of {keys}, got {given}")
    return o["chm_asset"], o["chm_band"], o["chm_label"]


def chm_image(options=None):
    ee = ee_module()
    asset, band, _ = chm_source(options)
    return ee.ImageCollection(asset).mosaic().select([band]).rename("v")


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


def fire_frequency_image(first_year: int, last_year: int, min_valid_months: int = 6):
    """Share of observed years with a MODIS burned-area detection (D-26-2).

    A pixel-year is *observed* if any month records a burn, or if at least
    ``min_valid_months`` months carry the MCD64A1 valid-data QA flag (bit 1).
    Unobserved pixel-years are masked, never counted as "not burned". Requiring all
    12 months (R2 run 2) removed most monsoon-region years.
    """
    ee = ee_module()
    col = ee.ImageCollection(MCD64_ASSET)
    years, counts = [], {}
    for y in range(first_year, last_year + 1):
        yc = col.filterDate(f"{y}-01-01", f"{y + 1}-01-01")
        n_valid = yc.map(lambda i: ee.Image(i).select("QA").bitwiseAnd(2).neq(0).unmask(0)).sum()
        burned = yc.map(lambda i: ee.Image(i).select("BurnDate").gt(0).unmask(0)).max()
        observed = burned.Or(n_valid.gte(min_valid_months))
        years.append(burned.updateMask(observed).rename("v").toFloat())
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
    elif kind == "canopy_eligible":
        w = canopy_eligible(ctx)
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
                     extras=_loss_by_type(m))


GAIN_TYPES = ("trees", "shrub_and_scrub", "grass", "flooded_vegetation", "water")


def _loss_by_type(m):
    """Gross loss split by 2020 type (ForTy natural forest vs other natural) and by what replaced it.

    Nature Positive rule: gross loss by ecosystem type, never netted against gain.
    """
    loss = m.select("loss")
    lab = m.select("dw_label")
    return {"gross_loss_ha": (loss, "ha"),
            "loss_from_natural_forest_ha": (loss.And(m.select("forest_2020")), "ha"),
            "loss_from_other_natural_ha": (loss.And(m.select("forest_2020").Not()), "ha"),
            "loss_to_crops_ha": (loss.And(lab.eq(nm.DW["crops"])), "ha"),
            "loss_to_built_ha": (loss.And(lab.eq(nm.DW["built"])), "ha")}


def b_gross_gain(ctx):
    m = ctx.mask
    lab = m.select("dw_label")
    extras = {f"gain_{t}_ha": (m.select("gain_candidate").And(lab.eq(nm.DW[t])), "ha") for t in GAIN_TYPES}
    return RatioSpec(m.select("gain_candidate"), lab.gte(0), 10, factor=None,
                     period=f"2020 -> {ctx.start}..{ctx.end_exclusive}", na_status="no_valid_pixels", extras=extras)


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


def _vegetated(ctx):
    return "strata:" + ",".join(str(c) for c in nm.VEGETATED_STRATA)


def b_ndvi(ctx):
    # Natural *vegetated* pixels only: NDVI over natural water or bare ground is not a
    # vegetation-condition signal (R2 run 2: Pune's only natural pixels were water).
    img, n = ndvi_peak(ctx)
    return StatsSpec(img, 10, weight=_vegetated(ctx), by_stratum=True, period=f"S2 peak window {ctx.peak_window[0]}..{ctx.peak_window[1]}",
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


def _chm_period(ctx):
    asset, band, label = chm_source(ctx.options)
    return f"{label}; {asset} band {band}"


# ---------------------------------------------------------------- canopy height (D-28-1)
# Detection floors below which a reading is "below detection", never a measured 0.
META_FLOOR_M = 2.0     # Darukaa: Meta v1 is weak on low vegetation (CHMv2 paper); same 2 m used for canopy cover
GEDI_FLOOR_M = 5.0     # Darukaa, empirical: rh98 read 4.9 m over Ludhiana cropland and 15.3 m over Pune buildings (probe 27 Oct)
DISAGREEMENT_SHARE = 0.5   # P-27-4 A: like-for-like sources more than 50% apart
CANOPY_EPOCH = ("2018-01-01", "2021-01-01")   # Meta v1 imagery mostly 2018-2020
CANOPY_CAVEATS = (
    "Meta/WRI v1: single-date imagery 2009-2020 (mostly 2018-2020); no field validation for trees taller than 25 m "
    "(WRI); trained and validated on a limited set of regions; slope and shadow bias; weak on vegetation below about 2 m. "
    "GLAD 2019: 30 m, saturates above 30 m; 0 = no forest canopy detected. GEDI rh98: tallest return in a ~25 m "
    "footprint; reads up to ~5 m over non-tree surfaces. No India-specific validation of any source was found.")


def canopy_eligible(ctx):
    """Natural woody pixels whose woody class already existed in the canopy-height source epoch (P-27-4 B).

    Natural forest (ForTy) and woodland need Dynamic World 'trees' as the 2018-2020 mode;
    shrub needs 'shrub_and_scrub'. Pixels that became woody later are excluded and reported.
    """
    ee = ee_module()
    s = ctx.mask.select("stratum")
    epoch, _ = nm.dw_mode(ctx.region, *CANOPY_EPOCH)
    trees, shrub = nm.DW["trees"], nm.DW["shrub_and_scrub"]
    ok = (s.eq(10).Or(s.eq(11)).And(epoch.eq(trees))).Or(s.eq(12).And(epoch.eq(shrub)))
    return ok.unmask(0).setDefaultProjection(crs=ctx.crs, scale=10)


def _woody_mask(ctx):
    s = ctx.mask.select("stratum")
    return s.eq(10).Or(s.eq(11)).Or(s.eq(12)).unmask(0)


def _canopy_evidence_lazies(ctx):
    """Like-for-like evidence over the same eligible pixels (P-27-5)."""
    ee = ee_module()
    elig = canopy_eligible(ctx)
    chm = chm_image(ctx.options).setDefaultProjection(crs=ctx.crs, scale=1)
    reg, crs = ctx.region, ctx.crs
    p95 = (chm.reduceResolution(reducer=ee.Reducer.percentile([95]), bestEffort=False, maxPixels=1024)
              .reproject(crs=crs, scale=30).rename("v"))
    w30 = elig.toFloat().reduceResolution(ee.Reducer.mean(), False, 65535).reproject(crs=crs, scale=30)
    glad = ee.ImageCollection(GLAD_HEIGHT_ASSET).mosaic().select([0])
    glad = glad.updateMask(glad.lte(60)).rename("v")
    col = ee.ImageCollection(GEDI_L2A_ASSET).filterBounds(reg)
    gedi = col.map(lambda i: ee.Image(i).select("rh98").updateMask(ee.Image(i).select("quality_flag").eq(1)
                                                                    .And(ee.Image(i).select("degrade_flag").eq(0)))).median().rename("v")
    w25 = elig.toFloat().reduceResolution(ee.Reducer.mean(), False, 65535).reproject(crs=crs, scale=25)
    mc = ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True)
    areas = ee.Image.cat([_woody_mask(ctx).rename("woody"), elig.rename("eligible")]).toFloat().multiply(ee.Image.pixelArea())
    return {
        "meta_p95_30m": p95.updateMask(w30.gte(0.5)).reduceRegion(ee.Reducer.mean(), reg, 30, crs, maxPixels=1e13, tileScale=4),
        "meta_cover_2m": chm.gt(META_FLOOR_M).rename("v").updateMask(elig).reduceRegion(ee.Reducer.mean(), reg, 1, crs, maxPixels=1e13, tileScale=4),
        "glad": glad.updateMask(w30.gte(0.5)).reduceRegion(mc, reg, 30, crs, maxPixels=1e13, tileScale=4),
        "gedi": gedi.updateMask(w25.gte(0.5)).reduceRegion(ee.Reducer.median().combine(ee.Reducer.count(), sharedInputs=True),
                                                          reg, 25, crs, maxPixels=1e13, tileScale=4),
        "areas": areas.reduceRegion(ee.Reducer.sum(), reg, 10, crs, maxPixels=1e13, tileScale=4),
    }


def _f(x):
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


def _normalise_evidence(extras):
    if "evidence" in extras:
        return extras["evidence"]
    def one(d, key):
        return _f((d or {}).get(key)) if isinstance(d, dict) else _f(d)
    ar = extras.pop("areas", None) or {}
    ev = {"meta_p95_30m": one(extras.pop("meta_p95_30m", None), "v"),
          "meta_cover_2m": one(extras.pop("meta_cover_2m", None), "v"),
          "glad": {"mean": one(extras.get("glad"), "v_mean"), "count": one(extras.get("glad"), "v_count")},
          "gedi": {"median": one(extras.get("gedi"), "v_median"), "count": one(extras.get("gedi"), "v_count")},
          "areas": {"woody_ha": (_f(ar.get("woody")) or 0.0) / 1e4, "eligible_ha": (_f(ar.get("eligible")) or 0.0) / 1e4}}
    extras.pop("glad", None)
    extras.pop("gedi", None)
    return ev


def _reading(v, floor, unit="m"):
    if v is None:
        return "no reading"
    return f"below detection (< {floor:g} {unit})" if v < floor else f"{v:.1f} {unit}"


def canopy_qa(m):
    """Apply the approved canopy-height evidence rules (D-28-1) and label every source.

    Order: epoch (source predates the woody state) -> like-for-like disagreement ->
    below detection. Each sets an explicit status and removes the value; none is a zero.
    """
    ex = dict(m.extras or {})
    ev = _normalise_evidence(ex)
    glad, gedi, areas = ev.get("glad") or {}, ev.get("gedi") or {}, ev.get("areas") or {}
    woody, elig = _f(areas.get("woody_ha")) or 0.0, _f(areas.get("eligible_ha")) or 0.0
    raw_mean = m.value
    ex.update({"evidence": ev, "raw_mean_m": raw_mean, "excluded_post_epoch_ha": max(0.0, woody - elig),
               "woody_ha": woody, "eligible_ha": elig, "caveats": CANOPY_CAVEATS,
               "quantity": "mean 1 m top-of-canopy height incl. gaps, natural woody pixels woody since 2018-2020"})
    p95 = _f(ev.get("meta_p95_30m"))
    ex["sources"] = {
        "meta_mean": {"quantity": "mean of 1 m heights (gaps included)", "reading": _reading(raw_mean, META_FLOOR_M)},
        "meta_p95_30m": {"quantity": "95th percentile of 1 m heights per 30 m cell, averaged", "reading": _reading(p95, META_FLOOR_M)},
        "meta_cover_2m": {"quantity": "share of 1 m pixels taller than 2 m",
                          "reading": None if ev.get("meta_cover_2m") is None else f"{100 * _f(ev['meta_cover_2m']):.1f} %"},
        "glad_2019": {"quantity": "30 m forest canopy height (GEDI-calibrated)", "n_pixels": glad.get("count"),
                      "reading": "no reading" if glad.get("mean") is None else
                      ("0 = no forest canopy detected" if _f(glad["mean"]) == 0 else f"{_f(glad['mean']):.1f} m")},
        "gedi_rh98": {"quantity": "median rh98 of quality-filtered footprints (tallest return per ~25 m)",
                      "n_footprints": gedi.get("count"), "reading": _reading(_f(gedi.get("median")), GEDI_FLOOR_M)},
    }
    m.extras = ex
    if m.status in ("no_valid_pixels", "below_min_support") and woody > elig:
        m.status, m.value = "source_predates_state", None
        m.notes = (m.notes + f" {woody - elig:.2f} ha became woody after the 2018-2020 source epoch").strip()
        return m
    dis = []
    if p95 is not None and p95 >= META_FLOOR_M:
        g, n = _f(glad.get("mean")), _f(glad.get("count")) or 0
        if g is not None and g > 0 and n >= 4 and abs(p95 - g) / max(p95, g) > DISAGREEMENT_SHARE:
            dis.append({"against": "glad", "meta_p95_30m": p95, "other": g})
        d, n = _f(gedi.get("median")), _f(gedi.get("count")) or 0
        if d is not None and d >= GEDI_FLOOR_M and n >= 10 and abs(p95 - d) / max(p95, d) > DISAGREEMENT_SHARE:
            dis.append({"against": "gedi", "meta_p95_30m": p95, "other": d})
    ex["disagreement"] = dis
    if dis and m.value is not None:
        m.status, m.value = "source_disagreement", None
        return m
    if raw_mean is not None and raw_mean < META_FLOOR_M and m.status in ("ok", "scored_context_scale"):
        m.status, m.value = "below_detection", None
    return m


def _floor_qa(floor, use_p95=False):
    def qa(m):
        if m.value is None:
            return m
        p95 = (m.spread or {}).get("p95")
        low = (p95 is not None and p95 == 0) if use_p95 else m.value < floor
        if low:
            m.extras = {**(m.extras or {}), "raw_mean_m": m.value, "caveats": CANOPY_CAVEATS}
            m.status, m.value = "below_detection", None
        return m
    return qa


def b_chm(ctx):
    return StatsSpec(chm_image(ctx.options), 1, weight="canopy_eligible", by_stratum=True, period=_chm_period(ctx),
                     extras=_canopy_evidence_lazies(ctx), qa=canopy_qa)


def b_managed_chm(ctx):
    return StatsSpec(chm_image(ctx.options), 1, weight="managed", by_stratum=True, period=_chm_period(ctx))


def b_glad_height(ctx):
    ee = ee_module()
    raw = ee.ImageCollection(GLAD_HEIGHT_ASSET).mosaic().select([0])
    img = raw.updateMask(raw.lte(60)).rename("v")   # 101 water, 102 snow/ice, 103 no data are codes, not heights
    return StatsSpec(img, 30, weight="strata:10", period="2019", qa=_floor_qa(0, use_p95=True))


def b_gedi(ctx):
    ee = ee_module()
    col = ee.ImageCollection(GEDI_L2A_ASSET).filterBounds(ctx.region)

    def q(i):
        i = ee.Image(i)
        return i.select("rh98").updateMask(i.select("quality_flag").eq(1).And(i.select("degrade_flag").eq(0)))
    img = col.map(q).mean().rename("v")
    return StatsSpec(img, 25, weight=_woody(ctx), period="GEDI L2A 2019-2025", qa=_floor_qa(GEDI_FLOOR_M))


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
    # The FLII raster stores the 0-10 index multiplied by 1000 (EE probe 24 Oct: forest
    # control mean 9085). The factor is applied here and the 0-10 range check still guards it.
    scale_factor = ctx.opt("flii_scale_factor", 0.001)
    img = ee.Image(asset).select([0]).multiply(scale_factor).rename("v")
    return StatsSpec(img, 300, weight="strata:10", period="FLII 2019", extras={"scale_factor": scale_factor})


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
    img, proj, counts = fire_frequency_image(first, last, ctx.opt("fire_min_valid_months", 6))
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
    """P / PET over the latest 12 months that TerraClimate covers, up to the window end.

    TerraClimate is released with a lag of about a year (Karpa run 26 Oct: no 2025 PET),
    so the period is anchored on its latest month instead of a fixed calendar year.
    """
    ee = ee_module()
    terra = ee.ImageCollection(TERRACLIMATE_ASSET).filterDate("2000-01-01", ctx.end_exclusive)
    last = ee.Date(terra.sort("system:time_start", False).first().get("system:time_start"))
    start, end = last.advance(-11, "month"), last.advance(1, "month")
    p = ee.ImageCollection(CHIRPS_ASSET).filterDate(start, end).select("precipitation").sum()
    pet = terra.filterDate(start, end).select("pet").sum().multiply(0.1)
    return StatsSpec(p.divide(pet).rename("v"), 4638.3, weight="none",
                     period="12 months to latest TerraClimate month (CHIRPS / TerraClimate PET)",
                     extras={"period_end": end.format("YYYY-MM")})


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
    """Threatened (CR/EN/VU) species per asset. The Red List category field differs between
    the Darukaa-held snapshots (probes 26-27 Oct: mammals 'category'; birds 'RedList__5'),
    so it is configured per asset and checked lazily; a missing field is an error and an
    unconfigured asset is excluded and reported."""
    ee = ee_module()
    fields = ctx.opt("iucn_category_fields", {"mammals": "category", "birds": "RedList__5"})
    lazy, parts = {}, []
    skipped = [n for n in ("mammals", "birds") if not fields.get(n)]
    for name, asset in (("mammals", MAMMALS_ASSET), ("birds", BIRDS_ASSET)):
        field = fields.get(name)
        if not field:   # category field not confirmed for this asset: excluded and reported, never guessed
            continue
        full = ee.FeatureCollection(ctx.raster_paths.get(name, asset))
        fc = full.filterBounds(ctx.unit_region).filter(ee.Filter.inList(field, ["CR", "EN", "VU"]))
        lazy[name] = fc.aggregate_array("sci_name").distinct().size()
        lazy[f"fields_{name}"] = full.first().propertyNames().containsAll(["sci_name", field])

    def parse(raw):
        missing = [k[7:] for k, v in raw.items() if k.startswith("fields_") and not v]
        if missing:
            raise ValueError(f"range asset(s) {missing} lack the configured category field ({fields})")
        counts = {k: int(v) for k, v in raw.items() if not k.startswith("fields_") and v is not None}
        if not counts:
            raise ValueError("no range asset has a confirmed category field")
        counts["excluded_unconfirmed_field"] = skipped
        return float(sum(v for v in counts.values() if isinstance(v, int))), "ok", counts
    return CustomSpec(lazy, parse, period="Darukaa-held IUCN range snapshots")


def b_restricted_range(ctx):
    """Species whose WHOLE range (all features of the species) is < 100,000 km2."""
    ee = ee_module()

    def small(fc, full):
        names = fc.aggregate_array("sci_name").distinct()
        parts = full.filter(ee.Filter.inList("sci_name", names)).map(
            lambda f: f.set("rk2", f.geometry().area(ee.ErrorMargin(1000)).divide(1e6)))
        groups = ee.List(parts.reduceColumns(ee.Reducer.sum().group(groupField=1, groupName="sci_name"),
                                             ["rk2", "sci_name"]).get("groups"))
        # ee.List.filter only accepts filters on 'item'; map to names (or null) and drop nulls.
        small_names = groups.map(lambda g: ee.Algorithms.If(ee.Number(ee.Dictionary(g).get("sum")).lt(100000),
                                                            ee.Dictionary(g).get("sci_name"), None), True)
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


# ---------------------------------------------------------------- P3 preparatory (D-28-2)
STAR_WEIGHTS = {"CR": 4, "EN": 3, "VU": 2, "NT": 1, "LC": 0}   # Mair et al. 2021 (STAR threat weights)
PRIORITY_CATEGORIES = ("CR", "EN", "VU")
RANGE_FILTERS = {"presence": [1, "1"], "origin": [1, 2, "1", "2"], "seasonal": [1, 2, "1", "2"]}  # extant; native/reintroduced; resident/breeding
SPECIES_PERIOD = "Darukaa-held IUCN/BirdLife range snapshots; habitat = natural mask 2020 vs assessment window"


def _species_lazies(ctx):
    """Per-species range areas and on-site habitat areas for every group with a confirmed category field."""
    ee = ee_module()
    site = ctx.unit_region
    fields = {"plants": "category", **ctx.opt("iucn_category_fields", {"mammals": "category", "birds": "RedList__5"})}
    m = ctx.mask
    hab = ee.Image.cat([ee.Image.constant(1).rename("site"),
                        m.select("natural_2020").And(m.select("uncertain").eq(0)).rename("h2020"),
                        m.select("natural_now").rename("hnow"), m.select("gain_candidate").rename("gain")]
                       ).unmask(0).toFloat().multiply(ee.Image.pixelArea()).divide(1e6)
    lazy = {"site_km2": ee.Image.pixelArea().divide(1e6).rename("a").reduceRegion(
        ee.Reducer.sum(), site, 10, ctx.crs, maxPixels=1e13, tileScale=4).get("a")}
    excluded = []
    for g, asset in (("mammals", MAMMALS_ASSET), ("birds", BIRDS_ASSET), ("plants", PLANTS_ASSET)):
        cf = fields.get(g)
        if not cf:
            excluded.append(g)
            continue
        full = ee.FeatureCollection(ctx.raster_paths.get(g, asset))
        filt = full
        for k, vals in RANGE_FILTERS.items():
            filt = filt.filter(ee.Filter.inList(k, vals))
        local = filt.filterBounds(site)
        names = local.aggregate_array("sci_name").distinct()
        glob = filt.filter(ee.Filter.inList("sci_name", names)).map(
            lambda f: f.set("a_km2", f.geometry().area(ee.ErrorMargin(1000)).divide(1e6)))
        per = ee.FeatureCollection(names.map(lambda n: ee.Feature(
            local.filter(ee.Filter.eq("sci_name", n)).geometry().intersection(site, ee.ErrorMargin(1)), {"sci_name": n})))
        red = hab.reduceRegions(collection=per, reducer=ee.Reducer.sum(), scale=10, crs=ctx.crs, tileScale=4)
        lazy[g] = ee.Dictionary({
            "global": glob.reduceColumns(ee.Reducer.sum().group(groupField=1, groupName="sci_name"), ["a_km2", "sci_name"]).get("groups"),
            "cats": local.reduceColumns(ee.Reducer.first().group(groupField=1, groupName="sci_name"), [cf, "sci_name"]).get("groups"),
            "areas": red.reduceColumns(ee.Reducer.toList(5), ["sci_name", "site", "h2020", "hnow", "gain"]).get("list"),
            "n_local_unfiltered": full.filterBounds(site).size(), "n_local": local.size()})
        lazy[f"fields_{g}"] = full.first().propertyNames().containsAll(["sci_name", cf, *RANGE_FILTERS])
    return lazy, excluded


def species_rows(raw):
    """Turn the evaluated lazies into rows: (sci_name, group, category, global_km2, site_km2, h2020, hnow, gain)."""
    missing = [k[7:] for k, v in raw.items() if k.startswith("fields_") and not v]
    if missing:
        raise ValueError(f"range asset(s) {missing} lack sci_name, the category field or presence/origin/seasonal")
    rows, diag = [], {}
    for g in ("mammals", "birds", "plants"):
        d = raw.get(g)
        if not isinstance(d, dict):
            continue
        if (d.get("n_local_unfiltered") or 0) > 0 and (d.get("n_local") or 0) == 0:
            raise ValueError(f"{g}: presence/origin/seasonal filter removed every overlapping feature (field type?)")
        glob = {x["sci_name"]: _f(x.get("sum")) for x in d.get("global") or []}
        cats = {x["sci_name"]: x.get("first") for x in d.get("cats") or []}
        for name, site, h20, hn, gn in d.get("areas") or []:
            rows.append((name, g, str(cats.get(name) or "").strip().upper(), glob.get(name), _f(site) or 0.0,
                         _f(h20) or 0.0, _f(hn) or 0.0, _f(gn) or 0.0))
        diag[g] = {"species": len(d.get("areas") or []), "features_overlapping": d.get("n_local_unfiltered")}
    return rows, diag


def _share(row, site_km2):
    glob = row[3]
    if not glob or glob <= 0:
        return None
    return min(row[4], site_km2) / glob


def star_t_from_rows(rows, site_km2):
    """Estimated STAR-t (range-based): 100 x sum over species of threat weight x share of global range on site."""
    if not rows:
        raise ValueError("no species ranges overlap the unit; check the range assets")
    total, contrib, skipped = 0.0, [], []
    for r in rows:
        w, sh = STAR_WEIGHTS.get(r[2]), _share(r, site_km2)
        if w is None or sh is None:
            skipped.append(r[0])
            continue
        c = 100.0 * w * sh
        total += c
        if c > 0:
            contrib.append({"sci_name": r[0], "group": r[1], "category": r[2], "contribution": c})
    contrib.sort(key=lambda x: -x["contribution"])
    return total, {"n_species": len(rows), "weights": dict(STAR_WEIGHTS), "top_contributors": contrib[:10],
                   "skipped_no_weight_or_area": skipped,
                   "by_category": {k: sum(1 for r in rows if r[2] == k) for k in ("CR", "EN", "VU", "NT", "LC", "DD")}}


def rarity_from_rows(rows, site_km2):
    """Range-size rarity-weighted richness: sum over species of the share of each global range on site."""
    if not rows:
        raise ValueError("no species ranges overlap the unit; check the range assets")
    shares = [(r[0], _share(r, site_km2)) for r in rows]
    return sum(sh for _, sh in shares if sh is not None), {"n_species": len(rows),
                                                            "skipped_no_area": [n for n, sh in shares if sh is None]}


def habitat_trend_from_rows(rows, threshold=0.05):
    """Priority-species population proxy (area of natural habitat within range on site), 2020 vs now.

    NPI species populations metric at preparatory granularity with area of habitat as the
    proxy (TOR p.74; Guidance p.28). 'Increasing' can only come from candidate gain,
    because the natural mask never adds natural area after 2020.
    """
    pri = [r for r in rows if r[2] in PRIORITY_CATEGORIES]
    counts = {"declining": 0, "stable": 0, "increasing_candidate": 0}
    per, no_hab = [], []
    for name, g, cat_, _, _, h20, hn, gn in pri:
        if h20 <= 0 and gn <= 0:
            no_hab.append(name)
            continue
        if h20 > 0 and (hn - h20) / h20 <= -threshold:
            cls = "declining"
        elif gn > 0 and (h20 <= 0 or gn / h20 >= threshold):
            cls = "increasing_candidate"
        else:
            cls = "stable"
        counts[cls] += 1
        per.append({"sci_name": name, "group": g, "category": cat_, "habitat_2020_ha": 100 * h20,
                    "habitat_now_ha": 100 * hn, "candidate_gain_ha": 100 * gn, "trend": cls})
    n = sum(counts.values())
    ex = {"counts": {**counts, "slowing_in_decline": None}, "n_priority": n, "no_habitat_on_site": no_hab,
          "threshold_relative_change": threshold, "species": per[:200],
          "note": "slowing in decline needs three or more time points; not assessable at baseline"}
    if n == 0:
        ex["reason"] = "no priority (CR/EN/VU) species on site"
        return None, ex
    ex["pct_by_trend"] = {k: 100.0 * v / n for k, v in counts.items()}
    return 100.0 * counts["declining"] / n, ex


def _species_spec(ctx, kind):
    lazy, excluded = _species_lazies(ctx)
    thr = ctx.opt("species_trend_threshold", 0.05)

    def parse(raw):
        rows, diag = species_rows(raw)
        site_km2 = _f(raw.get("site_km2")) or 0.0
        if kind == "star":
            v, ex = star_t_from_rows(rows, site_km2)
        elif kind == "rarity":
            v, ex = rarity_from_rows(rows, site_km2)
        else:
            if not rows:
                raise ValueError("no species ranges overlap the unit; check the range assets")
            v, ex = habitat_trend_from_rows(rows, thr)
            if v is None:
                return None, "not_applicable_no_priority_species", {**ex, "groups": diag, "excluded_groups": excluded}
        return v, "ok", {**ex, "groups": diag, "excluded_groups": excluded, "site_km2": site_km2}
    return CustomSpec(lazy, parse, period=SPECIES_PERIOD)


def b_star_estimated(ctx):
    return _species_spec(ctx, "star")


def b_rarity(ctx):
    return _species_spec(ctx, "rarity")


def b_habitat_trend(ctx):
    return _species_spec(ctx, "trend")


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
    "star_t_estimated": b_star_estimated,
    "rarity_weighted_richness": b_rarity,
    "priority_species_habitat_trend": b_habitat_trend,
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
