"""
darukaa_reference indicators — v6.1 (Aligned with State of Nature Module PRD v2.0)
=============================================================

25 ex-situ biodiversity indicators organized under the TNFD Annex 2
measurement tree:
    Dim 1 — Ecosystem Extent        (5 indicators)
    Dim 2 — Ecosystem Condition     (10 indicators, includes EII + components + BII)
    Dim 3 — Species Population Size (2 indicators)
    Dim 4 — Species Extinction Risk (3 indicators)
    Threats — Pressures / context   (5 indicators, tier2_eligible=False, not in SoN score)

Key design decisions:
    - tier2_eligible=False for all threat/pressure indicators (ghm, light_pollution,
      hdi, lst_day, lst_night) — Tier 2 HMI selection is circular for pressure metrics
    - flii: reference_radius_km=150 (forest-only indicator needs wider search)
    - ceri: ee.Filter.notNull([cat_col]) applied before bird .map() to prevent null crash
    - Scoring: Protocol B v1.0 thresholds (>=85/70/50/30%) applied in SoN scoring layer
"""

from __future__ import annotations
import logging, math
from typing import Any, Dict
import numpy as np
from darukaa_reference.config import Config
from darukaa_reference.registry import IndicatorRegistry

logger = logging.getLogger(__name__)

_EII_ASSET = "projects/landler-open-data/assets/eii/global/eii_global_v1"
_MAMMALS = "projects/darukaa-earth130226/assets/RedList_Mammals_Terrestrial"
_BIRDS = "projects/darukaa-earth130226/assets/RedList_Bird_IUCN_Category"
_KBA = "projects/darukaa-earth130226/assets/KBA_Global_POL_SEP25"
_PV = "projects/darukaa-earth-product/assets/biodiversity_India_PV_Binary_2025_Full_Mosaic"
_MSA = "projects/ee-jayankandir/assets/TerrestrialMSA_2015_World"


# ── Helpers ───────────────────────────────────────────────────────────

def _to_ee(geometry):
    import ee
    if isinstance(geometry, ee.Geometry): return geometry
    from shapely.geometry import mapping
    from shapely.ops import transform as st
    if hasattr(geometry, "has_z") and geometry.has_z:
        geometry = st(lambda x, y, z=None: (x, y), geometry)
    return ee.Geometry(mapping(geometry))

def _reduce(image, geometry, scale=100):
    import ee
    g = _to_ee(geometry)
    stats = image.reduceRegion(
        reducer=ee.Reducer.mean().combine(ee.Reducer.median(), sharedInputs=True),
        geometry=g, scale=scale, maxPixels=1e8, bestEffort=True).getInfo()
    v = None
    for k, val in (stats or {}).items():
        if "mean" in k.lower() and val is not None: v = val; break
    if v is None:
        for val in (stats or {}).values():
            if val is not None: v = val; break
    return {"value": v, "pixels": None}

def _local_raster(path, geometry, band=1, sf=1.0):
    import rasterio
    from rasterio.mask import mask as rio_mask
    from shapely.geometry import mapping
    with rasterio.open(path) as src:
        pw, ph = abs(src.transform[0]), abs(src.transform[4])
        if geometry.area < pw * ph * 4:
            c = geometry.centroid; r, col = src.index(c.x, c.y)
            if 0 <= r < src.height and 0 <= col < src.width:
                val = float(src.read(band)[r, col])
                if not np.isfinite(val): return {"value": None, "pixels": None}
                return {"value": val * sf, "pixels": np.array([val * sf])}
            return {"value": None, "pixels": None}
        try:
            out, _ = rio_mask(src, [mapping(geometry)], crop=True, nodata=src.nodata)
            arr = out[band-1].flatten(); arr = arr[np.isfinite(arr)]
            if src.nodata is not None and not np.isnan(src.nodata): arr = arr[arr != src.nodata]
            if len(arr) == 0: return {"value": None, "pixels": None}
            return {"value": float(np.nanmean(arr * sf)), "pixels": arr * sf}
        except Exception as e:
            logger.warning(f"Raster extract failed: {e}"); return {"value": None, "pixels": None}

def _load_fc(asset, config=None):
    import ee
    if config and hasattr(config, 'raster_paths'):
        overrides = {_MAMMALS: "iucn_mammals", _BIRDS: "iucn_birds", _KBA: "kba_global"}
        key = overrides.get(asset)
        if key and config.raster_paths.get(key): asset = config.raster_paths[key]
    try: return ee.FeatureCollection(asset)
    except Exception as e:
        logger.warning(f"Cannot load {asset}: {e}"); return None


# ── Registry ──────────────────────────────────────────────────────────

def create_default_registry() -> IndicatorRegistry:
    r = IndicatorRegistry()

    # ═══ DIM 1 — ECOSYSTEM EXTENT ═══
    r.register(name="natural_habitat", display_name="Natural Habitat Extent", source_type="gee",
        extract_fn=extract_natural_habitat, unit="%", value_range=(0,100),
        citation="Brown et al. (2022). Dynamic World. DOI:10.1038/s41597-022-01307-4",
        tier2_eligible=True, reference_radius_km=50.0, pillar=1,
        metadata={"gee_image_fn": _img_natural_habitat, "tnfd_dim": 1})

    r.register(name="natural_landcover", display_name="Natural Land Cover Proportion", source_type="gee",
        extract_fn=extract_natural_landcover, unit="%", value_range=(0,100),
        citation="Friedl et al. (2019). MCD12Q1. DOI:10.5067/MODIS/MCD12Q1.061",
        tier2_eligible=True, reference_radius_km=50.0, pillar=1,
        metadata={"gee_image_fn": _img_natural_landcover, "tnfd_dim": 1})

    r.register(name="cpland", display_name="Landscape Connectivity (CPLAND)", source_type="gee",
        extract_fn=extract_cpland, unit="%", value_range=(0,100),
        citation="McGarigal & Marks (1995). Darukaa PV binary.",
        tier2_eligible=False, reference_radius_km=30.0, pillar=1,
        metadata={"tnfd_dim": 1, "note": "India-only PV binary asset"})

    r.register(name="forest_loss_rate", display_name="Habitat Loss Rate", source_type="gee",
        extract_fn=extract_forest_loss_rate, unit="% per year", value_range=(0,100),
        citation="Hansen et al. (2013). Science. DOI:10.1126/science.1244693. v1.12.",
        tier2_eligible=True, higher_is_better=False, reference_radius_km=50.0, pillar=1,
        metadata={"gee_image_fn": _img_forest_loss, "tnfd_dim": 1})

    r.register(name="kba_overlap", display_name="KBA/IBA Overlap", source_type="gee",
        extract_fn=extract_kba_overlap, unit="%", value_range=(0,100),
        citation="IUCN (2022). KBA Standards. DOI:10.2305/IUCN.CH.2022.24.en",
        tier2_eligible=False, reference_radius_km=50.0, pillar=1,
        metadata={"tnfd_dim": 1, "note": "Requires KBA asset"})

    # ═══ DIM 2 — ECOSYSTEM CONDITION ═══
    r.register(name="ndvi", display_name="Vegetation Structure (NDVI)", source_type="gee",
        extract_fn=extract_ndvi, unit="index", value_range=(-1,1),
        citation="Sentinel-2 SCL. Drusch et al. (2012). DOI:10.1016/j.rse.2011.11.026",
        tier2_eligible=True, reference_radius_km=50.0, pillar=2,
        metadata={"gee_image_fn": _img_ndvi, "tnfd_dim": 2})

    r.register(name="habitat_health", display_name="Habitat Health Index (HHI)", source_type="gee",
        extract_fn=extract_habitat_health, unit="z5/σ", value_range=(0,50),
        citation="Darukaa greenness stability = mean(z5/σ) from S2 NDVI.",
        tier2_eligible=True, reference_radius_km=50.0, pillar=2,
        metadata={"gee_image_fn": _img_hhi, "tnfd_dim": 2})

    r.register(name="flii", display_name="Forest Landscape Integrity Index", source_type="gee",
        extract_fn=extract_flii, unit="0–10", value_range=(0,10),
        citation="Approx MODIS LC(1-10)+VIIRS. Grantham et al. (2020). DOI:10.1038/s41467-020-19493-3",
        tier2_eligible=True, reference_radius_km=150.0, pillar=2,
        metadata={"gee_image_fn": _img_flii, "tnfd_dim": 2})

    r.register(name="eii", display_name="Ecosystem Integrity Index", source_type="gee",
        extract_fn=extract_eii, unit="index", value_range=(0,1),
        citation="Hill et al. (2022). bioRxiv. DOI:10.1101/2022.08.21.504707. Landbanking 300m.",
        tier2_eligible=True, reference_radius_km=75.0, pillar=2,
        metadata={"gee_image_fn": _img_eii, "tnfd_dim": 2})

    r.register(name="eii_structural", display_name="EII: Structural Integrity", source_type="gee",
        extract_fn=extract_eii_s, unit="index", value_range=(0,1),
        citation="Hill et al. (2022). Core area. Kennedy et al. (2019). DOI:10.1111/gcb.14549",
        tier2_eligible=True, reference_radius_km=75.0, pillar=2,
        metadata={"gee_image_fn": _img_eii_s, "tnfd_dim": 2})

    r.register(name="eii_compositional", display_name="EII: Compositional Integrity", source_type="gee",
        extract_fn=extract_eii_c, unit="index", value_range=(0,1),
        citation="IO BII 300m. Newbold et al. (2016). DOI:10.1126/science.aaf2201",
        tier2_eligible=True, reference_radius_km=75.0, pillar=2,
        metadata={"gee_image_fn": _img_eii_c, "tnfd_dim": 2})

    r.register(name="eii_functional", display_name="EII: Functional Integrity", source_type="gee",
        extract_fn=extract_eii_f, unit="index", value_range=(0,1),
        citation="Actual/potential NPP. Hill et al. (2022).",
        tier2_eligible=True, reference_radius_km=75.0, pillar=2,
        metadata={"gee_image_fn": _img_eii_f, "tnfd_dim": 2})

    r.register(name="bii", display_name="Biodiversity Intactness Index", source_type="gee",
        extract_fn=extract_bii, unit="index", value_range=(0,1),
        citation="Newbold et al. (2016). Science. DOI:10.1126/science.aaf2201. IO 300m / PREDICTS fallback.",
        tier2_eligible=True, reference_radius_km=75.0, pillar=2,
        metadata={"gee_image_fn": _img_bii, "tnfd_dim": 2})

    r.register(name="pdf", display_name="Potentially Disappeared Fraction", source_type="gee",
        extract_fn=extract_pdf, unit="fraction", value_range=(0,1),
        citation="Huijbregts et al. (2017). ReCiPe2016. DOI:10.1007/s11367-016-1246-y",
        tier2_eligible=True, higher_is_better=False, reference_radius_km=50.0, pillar=2,
        metadata={"gee_image_fn": _img_pdf, "tnfd_dim": 2})

    r.register(name="aridity_index", display_name="Aridity Index", source_type="gee",
        extract_fn=extract_aridity, unit="P/PET", value_range=(0,5),
        citation="Zomer et al. (2022). DOI:10.1038/s41597-022-01493-1. CHIRPS+TerraClimate.",
        tier2_eligible=True, higher_is_better=True, reference_radius_km=50.0, pillar=2,
        metadata={"gee_image_fn": _img_aridity, "tnfd_dim": 2})

    # ═══ DIM 3 — SPECIES POPULATION SIZE ═══
    r.register(name="endemic_richness", display_name="Endemic Species Richness", source_type="gee",
        extract_fn=extract_endemic_richness, unit="count", value_range=(0,500),
        citation="IUCN mammal ranges. Range < 100,000 km².",
        tier2_eligible=False, reference_radius_km=100.0, pillar=3,
        metadata={"tnfd_dim": 3, "note": "Requires mammal asset"})

    r.register(name="flagship_habitat", display_name="Flagship Habitat Viability", source_type="gee",
        extract_fn=extract_flagship_habitat, unit="index", value_range=(0,1),
        citation="Forest × elevation_suit × inverse_pressure. Bird threatened overlay.",
        tier2_eligible=False, reference_radius_km=50.0, pillar=3,
        metadata={"tnfd_dim": 3, "note": "Requires bird asset"})

    # ═══ DIM 4 — SPECIES EXTINCTION RISK ═══
    r.register(name="threatened_richness", display_name="Threatened Species Richness", source_type="gee",
        extract_fn=extract_threatened_richness, unit="count", value_range=(0,500),
        citation="IUCN Red List. CR/EN/VU mammals + birds.",
        tier2_eligible=False, reference_radius_km=100.0, pillar=4,
        metadata={"tnfd_dim": 4})

    r.register(name="ceri", display_name="Composite Extinction-Risk Index", source_type="gee",
        extract_fn=extract_ceri, unit="index", value_range=(0,1),
        citation="Butchart et al. (2007). PLoS ONE. DOI:10.1371/journal.pone.0000140",
        tier2_eligible=False, higher_is_better=False, reference_radius_km=100.0, pillar=4,
        metadata={"tnfd_dim": 4})

    r.register(name="star_t", display_name="STAR_T (Threat Abatement)", source_type="gee",
        extract_fn=extract_star_t, unit="score", value_range=(0,10),
        citation="Mair et al. (2021). Nat Ecol Evol. DOI:10.1038/s41559-021-01432-0",
        tier2_eligible=False, higher_is_better=False, reference_radius_km=100.0, pillar=4,
        metadata={"tnfd_dim": 4, "note": "Bird-based. Requires bird+DW+VIIRS."})

    # ═══ THREATS & PRESSURES ═══
    r.register(name="ghm", display_name="Global Human Modification", source_type="gee",
        extract_fn=extract_ghm, unit="index", value_range=(0,1),
        citation="Kennedy et al. (2019). DOI:10.1111/gcb.14549",
        tier2_eligible=False, higher_is_better=False, reference_radius_km=50.0, pillar=5,
        metadata={"gee_image_fn": _img_ghm, "tnfd_dim": "threats"})

    r.register(name="light_pollution", display_name="Light Pollution (VIIRS)", source_type="gee",
        extract_fn=extract_light_pollution, unit="nW/cm²/sr", value_range=(0,500),
        citation="Elvidge et al. (2017). DOI:10.1080/01431161.2017.1342050",
        tier2_eligible=False, higher_is_better=False, reference_radius_km=25.0, pillar=5,
        metadata={"gee_image_fn": _img_viirs, "tnfd_dim": "threats"})

    r.register(name="hdi", display_name="Human Disturbance Index", source_type="gee",
        extract_fn=extract_hdi, unit="index", value_range=(0,1),
        citation="ESA WorldCover v200. DOI:10.5281/zenodo.7254221",
        tier2_eligible=False, higher_is_better=False, reference_radius_km=25.0, pillar=5,
        metadata={"gee_image_fn": _img_hdi, "tnfd_dim": "threats"})

    r.register(name="lst_day", display_name="Daytime Surface Temperature", source_type="gee",
        extract_fn=extract_lst_day, unit="°C", value_range=(-40,70),
        citation="Wan et al. (2021). MOD11A1. DOI:10.5067/MODIS/MOD11A1.061",
        tier2_eligible=False, higher_is_better=False, reference_radius_km=25.0, pillar=5,
        metadata={"gee_image_fn": _img_lst_day, "tnfd_dim": "threats"})

    r.register(name="lst_night", display_name="Nighttime Surface Temperature", source_type="gee",
        extract_fn=extract_lst_night, unit="°C", value_range=(-40,50),
        citation="Wan et al. (2021). MOD11A1 Night. DOI:10.5067/MODIS/MOD11A1.061",
        tier2_eligible=False, higher_is_better=False, reference_radius_km=25.0, pillar=5,
        metadata={"gee_image_fn": _img_lst_night, "tnfd_dim": "threats"})

    return r


# ═══════════════════════════════════════════════════════════════════════
# IMAGE BUILDERS (for reference engine)
# ═══════════════════════════════════════════════════════════════════════

def _img_natural_habitat(c):
    import ee; y=c.ndvi_year
    dw=ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterDate(f"{y}-01-01",f"{y}-12-31").select("label").mode()
    return dw.remap([1,2,3,5],[1,1,1,1],0).multiply(100).rename("natural_habitat")

def _img_natural_landcover(c):
    import ee
    lc=ee.ImageCollection("MODIS/061/MCD12Q1").sort("system:time_start",False).first().select("LC_Type1")
    return lc.remap(list(range(1,12)),[1]*11,0).multiply(100).rename("natural_landcover")

def _img_forest_loss(c):
    import ee
    gfc=ee.Image("UMD/hansen/global_forest_change_2024_v1_12")
    f=gfc.select("treecover2000").gte(30); l=gfc.select("lossyear").gt(0)
    return l.divide(f.max(1)).multiply(100).divide(24).updateMask(f).rename("forest_loss_rate")

def _img_ndvi(c):
    import ee; y=c.ndvi_year
    def m(img):
        scl=img.select('SCL'); g=scl.eq(2).Or(scl.eq(4)).Or(scl.eq(5)).Or(scl.eq(6)).Or(scl.eq(7))
        return img.updateMask(g).divide(10000)
    s2=ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterDate(f"{y}-01-01",f"{y}-12-31").filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE",c.ndvi_cloud_threshold)).map(m)
    return s2.map(lambda i:i.normalizedDifference(["B8","B4"]).rename("NDVI")).median().select("NDVI")

def _img_hhi(c):
    import ee; y=c.ndvi_year
    def m(img):
        scl=img.select("SCL"); g=scl.eq(2).Or(scl.eq(4)).Or(scl.eq(5)).Or(scl.eq(6)).Or(scl.eq(7))
        return img.updateMask(g).divide(10000)
    ic=ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterDate(f"{y}-01-01",f"{y}-12-31").filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE",c.ndvi_cloud_threshold)).map(m).map(lambda i:i.normalizedDifference(["B8","B4"]).rename("NDVI"))
    z5=ic.reduce(ee.Reducer.percentile([5])).rename("p5")
    sig=ic.reduce(ee.Reducer.stdDev()).rename("sd")
    cnt=ic.count().rename("n")
    return z5.divide(sig).updateMask(cnt.gte(6).And(sig.neq(0))).rename("HHI")

def _img_flii(c):
    import ee
    modis=ee.ImageCollection("MODIS/061/MCD12Q1").sort("system:time_start",False).first().select("LC_Type1")
    forest=modis.gte(1).And(modis.lte(10))
    y=c.ndvi_year
    night=ee.ImageCollection("NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG").filterDate(f"{y}-01-01",f"{y}-12-31").select("avg_rad")
    night=ee.ImageCollection(ee.Algorithms.If(night.size().gt(0),night,ee.ImageCollection("NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG").sort("system:time_start",False).limit(12).select("avg_rad"))).mean()
    nn=night.unitScale(0,60).clamp(0,1)
    conn=forest.focal_min(2); frag=forest.subtract(conn).selfMask().unmask(0).unitScale(0,1)
    p=nn.add(frag).unitScale(0,2).clamp(0,1)
    return ee.Image(10).subtract(p.multiply(10)).updateMask(forest).rename("FLII")

def _img_eii(c):
    import ee
    try: return ee.Image(_EII_ASSET).select("eii").rename("EII")
    except: pass
    s=ee.ImageCollection("CSP/HM/GlobalHumanModification").first().select("gHM")
    s=ee.Image.constant(1).subtract(s)
    npp=ee.ImageCollection("MODIS/061/MOD17A3HGF").sort("system:time_start",False).first().select("Npp").multiply(0.0001)
    f=npp.divide(2.0).min(1).max(0)
    b=_img_bii(c)
    if b: return s.min(b).min(f).rename("EII")
    return s.min(f).rename("EII")

def _img_eii_s(c):
    import ee
    try: return ee.Image(_EII_ASSET).select("structural_integrity").rename("EII_Structural")
    except:
        g=ee.ImageCollection("CSP/HM/GlobalHumanModification").first().select("gHM")
        return ee.Image.constant(1).subtract(g).rename("EII_Structural")

def _img_eii_c(c):
    import ee
    try: return ee.Image(_EII_ASSET).select("compositional_integrity").rename("EII_Compositional")
    except:
        b=_img_bii(c); return b.rename("EII_Compositional") if b else None

def _img_eii_f(c):
    import ee
    try: return ee.Image(_EII_ASSET).select("functional_integrity").rename("EII_Functional")
    except:
        npp=ee.ImageCollection("MODIS/061/MOD17A3HGF").sort("system:time_start",False).first().select("Npp").multiply(0.0001)
        return npp.divide(2.0).min(1).max(0).rename("EII_Functional")

def _img_bii(c):
    import ee
    try: return ee.Image(_EII_ASSET).select("compositional_integrity").rename("BII")
    except: pass
    a=getattr(c,"bii_gee_asset",None)
    if a:
        try: return ee.Image(a).select(0).divide(100).rename("BII")
        except: pass
    return None

def _img_pdf(c):
    import ee
    lc=ee.ImageCollection("MODIS/061/MCD12Q1").sort("system:time_start",False).first().select("LC_Type1")
    cf=lc.expression("b('LC_Type1')==12?0.30:b('LC_Type1')==13?0.50:b('LC_Type1')==10?0.05:b('LC_Type1')==7?0.20:b('LC_Type1')<=5?0.10:0").rename("PDF")
    return cf.updateMask(cf)

def _img_aridity(c):
    import ee; y=c.ndvi_year
    for yr in [y,y-1]:
        pc=ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").filterDate(f"{yr}-01-01",f"{yr}-12-31")
        pe=ee.ImageCollection("IDAHO_EPSCOR/TERRACLIMATE").filterDate(f"{yr}-01-01",f"{yr}-12-31").select("pet")
        try:
            if pc.size().gt(0).And(pe.size().gt(0)).getInfo():
                return pc.sum().rename("p").divide(pe.sum().multiply(0.1).rename("e").max(1)).rename("Aridity_Index")
        except: continue
    return None

def _img_ghm(c):
    import ee; return ee.ImageCollection("CSP/HM/GlobalHumanModification").first().select("gHM").rename("gHM")

def _img_viirs(c):
    import ee; y=c.ndvi_year
    return ee.ImageCollection("NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG").filterDate(f"{y}-01-01",f"{y}-12-31").select("avg_rad").mean().rename("light_pollution")

def _img_hdi(c):
    import ee
    wc=ee.Image("ESA/WorldCover/v200/2021").select("Map")
    u=wc.eq(50).selfMask()
    d=u.fastDistanceTransform(300,"pixels","squared_euclidean").sqrt().multiply(10)
    return ee.Image.constant(1).subtract(d.divide(1500).min(1.0)).rename("HDI")

def _img_lst_day(c):
    import ee; y=c.lst_year
    return ee.ImageCollection("MODIS/061/MOD11A1").filterDate(f"{y}-01-01",f"{y}-12-31").select("LST_Day_1km").mean().multiply(0.02).subtract(273.15).rename("LST_Day")

def _img_lst_night(c):
    import ee; y=c.lst_year
    return ee.ImageCollection("MODIS/061/MOD11A1").filterDate(f"{y}-01-01",f"{y}-12-31").select("LST_Night_1km").mean().multiply(0.02).subtract(273.15).rename("LST_Night")


# ═══════════════════════════════════════════════════════════════════════
# EXTRACTION FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════

# Dim 1
def extract_natural_habitat(g,c): return _reduce(_img_natural_habitat(c),g,10)
def extract_natural_landcover(g,c): return _reduce(_img_natural_landcover(c),g,500)

def extract_cpland(g,c):
    import ee; eg=_to_ee(g); pa=c.raster_paths.get("pv_binary",_PV)
    try:
        img=ee.Image(pa).select(0); sm=img.projection().nominalScale().getInfo()
        if sm<=0: return {"value":None,"pixels":None}
        rp=int(math.ceil((10+0.5*sm)/sm))
        core=img.eq(1).unmask(0).rename("b").reduceNeighborhood(reducer=ee.Reducer.min(),kernel=ee.Kernel.circle(rp,units="pixels")).rename("c")
        ca=core.multiply(ee.Image.pixelArea()).reduceRegion(reducer=ee.Reducer.sum(),geometry=eg,scale=sm,maxPixels=1e13)
        pa_m2=float(eg.area().getInfo())
        if pa_m2==0: return {"value":None,"pixels":None}
        return {"value":max(0,min(100,100*float(ee.Number(ca.get("c")).getInfo())/pa_m2)),"pixels":None}
    except Exception as e: logger.warning(f"CPLAND: {e}"); return {"value":None,"pixels":None}

def extract_forest_loss_rate(g,c):
    import ee; eg=_to_ee(g)
    gfc=ee.Image("UMD/hansen/global_forest_change_2024_v1_12").clip(eg)
    f=gfc.select("treecover2000").gte(30); l=gfc.select("lossyear").gt(0); pa=ee.Image.pixelArea()
    a0=pa.updateMask(f).reduceRegion(reducer=ee.Reducer.sum(),geometry=eg,scale=30,maxPixels=1e13)
    al=pa.updateMask(l).reduceRegion(reducer=ee.Reducer.sum(),geometry=eg,scale=30,maxPixels=1e13)
    try: return {"value":ee.Number(al.get("area")).divide(ee.Number(a0.get("area"))).multiply(100).divide(24).getInfo(),"pixels":None}
    except: return {"value":None,"pixels":None}

def extract_kba_overlap(g,c):
    import ee; eg=_to_ee(g); kba=_load_fc(_KBA,c)
    if not kba: return {"value":None,"pixels":None}
    try:
        sa=eg.area(1).divide(1e6); kf=kba.filterBounds(eg)
        ov=kf.map(lambda f:f.intersection(eg,ee.ErrorMargin(100)))
        oa=ov.geometry().area(100).divide(1e6)
        return {"value":min(100,oa.divide(sa).multiply(100).getInfo()),"pixels":None}
    except Exception as e: logger.warning(f"KBA: {e}"); return {"value":None,"pixels":None}

# Dim 2
def extract_ndvi(g,c): return _reduce(_img_ndvi(c),g,10)

def extract_habitat_health(g,c):
    img=_img_hhi(c)
    return _reduce(img,g,10) if img else {"value":None,"pixels":None}

def extract_flii(g,c):
    img=_img_flii(c)
    return _reduce(img,g,500) if img else {"value":None,"pixels":None}

def extract_eii(g,c):
    img=_img_eii(c)
    return _reduce(img,g,300) if img else {"value":None,"pixels":None}

def extract_eii_s(g,c): return _reduce(_img_eii_s(c),g,300)
def extract_eii_c(g,c): return _reduce(_img_eii_c(c),g,300)
def extract_eii_f(g,c): return _reduce(_img_eii_f(c),g,300)

def extract_bii(g,c):
    import ee; img=_img_bii(c)
    if img:
        r=_reduce(img,g,300)
        if r.get("value") is not None: return r
    rp=c.raster_paths.get("bii")
    if rp:
        try: return _local_raster(rp,g,1,0.01)
        except: pass
    return {"value":None,"pixels":None}

def extract_pdf(g,c): return _reduce(_img_pdf(c),g,500)

def extract_aridity(g,c):
    img=_img_aridity(c)
    return _reduce(img,g,5000) if img else {"value":None,"pixels":None}

# Dim 3
def extract_endemic_richness(g,c):
    import ee; eg=_to_ee(g); fc=_load_fc(_MAMMALS,c)
    if not fc: return {"value":None,"pixels":None}
    try:
        wa=fc.map(lambda f:f.set("rk2",f.geometry().area().divide(1e6)))
        sr=wa.filter(ee.Filter.lt("rk2",100000)).filterBounds(eg).distinct("sci_name")
        return {"value":sr.size().getInfo(),"pixels":None}
    except Exception as e: logger.warning(f"Endemic: {e}"); return {"value":None,"pixels":None}

def extract_flagship_habitat(g,c):
    import ee; eg=_to_ee(g); birds=_load_fc(_BIRDS,c)
    if not birds: return {"value":None,"pixels":None}
    try:
        y=c.ndvi_year
        dw=ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterDate(f"{y}-01-01",f"{y}-12-31").filterBounds(eg).select("label").mode()
        forest=dw.eq(1); dem=ee.Image("USGS/SRTMGL1_003")
        es=dem.unitScale(0,2000).multiply(-1).add(1)
        viirs=ee.ImageCollection("NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG").filterDate(f"{y}-01-01",f"{y}-12-31").select("avg_rad").mean()
        hs=viirs.unitScale(0,50).multiply(-1).add(1)
        hsi=forest.multiply(es).multiply(hs).rename("HSI")
        val=hsi.reduceRegion(reducer=ee.Reducer.mean(),geometry=eg,scale=1000,maxPixels=1e13).get("HSI").getInfo()
        return {"value":val,"pixels":None}
    except Exception as e: logger.warning(f"Flagship: {e}"); return {"value":None,"pixels":None}

# Dim 4
def extract_threatened_richness(g,c):
    import ee; eg=_to_ee(g); total=0
    for asset,nc,cc in [(_MAMMALS,"sci_name","category"),(_BIRDS,"sci_name","RedList_5")]:
        fc=_load_fc(asset,c)
        if not fc: continue
        try: total+=fc.filter(ee.Filter.inList(cc,["CR","EN","VU"])).filterBounds(eg).distinct(nc).size().getInfo()
        except Exception as e: logger.warning(f"Threatened({asset}): {e}")
    return {"value":total if total>0 else None,"pixels":None}

def extract_ceri(g,c):
    import ee; eg=_to_ee(g); tn=0; tw=0
    for asset,nc,cc in [(_MAMMALS,"sci_name","category"),(_BIRDS,"sci_name","RedList_5")]:
        fc=_load_fc(asset,c)
        if not fc: continue
        try:
            def aw(f):
                cat=ee.String(f.get(cc))
                w=ee.Number(ee.Algorithms.If(cat.compareTo("EX").eq(0),5,ee.Algorithms.If(cat.compareTo("EW").eq(0),5,ee.Algorithms.If(cat.compareTo("CR").eq(0),4,ee.Algorithms.If(cat.compareTo("EN").eq(0),3,ee.Algorithms.If(cat.compareTo("VU").eq(0),2,ee.Algorithms.If(cat.compareTo("NT").eq(0),1,ee.Algorithms.If(cat.compareTo("LC").eq(0),0,0))))))))
                return f.set("weight",w)
            wf=fc.filterBounds(eg).filter(ee.Filter.notNull([cc])).map(aw).distinct(nc)
            tn+=wf.size().getInfo(); tw+=wf.aggregate_sum("weight").getInfo()
        except Exception as e: logger.warning(f"CERI({asset}): {e}")
    if tn==0: return {"value":None,"pixels":None}
    return {"value":tw/(tn*5),"pixels":None}

def extract_star_t(g,c):
    import ee; eg=_to_ee(g); birds=_load_fc(_BIRDS,c)
    if not birds: return {"value":None,"pixels":None}
    try:
        y=c.ndvi_year
        filt=birds.filter(ee.Filter.eq("presence",1)).filter(ee.Filter.eq("origin",1)).filter(ee.Filter.inList("RedList_5",["CR","EN","VU"]))
        def aw(f):
            cat=ee.String(f.get("RedList_5"))
            w=ee.Number(ee.Algorithms.If(cat.equals("CR"),4,ee.Algorithms.If(cat.equals("EN"),3,ee.Algorithms.If(cat.equals("VU"),2,1))))
            return f.set("weight",w)
        wr=filt.map(aw); sr=ee.Image().float().paint(featureCollection=wr,color="weight")
        dw=ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterDate(f"{y}-01-01",f"{y}-12-31").filterBounds(eg).select("label").mode()
        hm=dw.remap([1,2,3,5],[1,1,1,1],0); bm=dw.eq(6)
        bd=bm.reduceNeighborhood(reducer=ee.Reducer.mean(),kernel=ee.Kernel.circle(radius=1000,units="meters"))
        viirs=ee.ImageCollection("NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG").filterDate(f"{y}-01-01",f"{y}-12-31").select("avg_rad").mean()
        nn=viirs.unitScale(0,50); tp=bd.add(nn).divide(2)
        st=sr.multiply(tp).multiply(hm).rename("STAR_T")
        val=st.reduceRegion(reducer=ee.Reducer.mean(),geometry=eg,scale=1000,maxPixels=1e13).get("STAR_T").getInfo()
        return {"value":val,"pixels":None}
    except Exception as e: logger.warning(f"STAR_T: {e}"); return {"value":None,"pixels":None}

# Threats
def extract_ghm(g,c): return _reduce(_img_ghm(c),g,1000)
def extract_light_pollution(g,c): return _reduce(_img_viirs(c),g,500)
def extract_hdi(g,c): return _reduce(_img_hdi(c),g,10)
def extract_lst_day(g,c): return _reduce(_img_lst_day(c),g,1000)
def extract_lst_night(g,c): return _reduce(_img_lst_night(c),g,1000)
