"""
darukaa_reference indicators — v3.0 (Aquatic + eDNA + Terrestrial extension)
=============================================================

44 ex-situ biodiversity indicators organized under the TNFD Annex 2
measurement tree:
    Dim 1 — Ecosystem Extent        (5 indicators)
    Dim 2 — Ecosystem Condition     (23 indicators)
    Dim 3 — Species Population Size (3 indicators)
    Dim 4 — Species Extinction Risk (4 indicators)
    Threats — Pressures / context   (9 indicators, tier2_eligible=False, not in SoN score)

v3.0 additions — Aquatic & eDNA suite (lake/reservoir monitoring):
    Condition: tspi, sabf, wcpi, wsdi, hsas, edpp, mspl, rci
    Threats:   sdi, stsi, iri

v3.0 additions — Terrestrial vegetation + plant species:
    Condition: riparian_ndvi_trend, jrc_water_persistence, shdi, lai, chm
    Pillar 3:  endemic_plant_richness
    Pillar 4:  threatened_plant_richness
    Threats:   ivsi

REJECTED (redundancy):
    EVI               — redundant with ndvi; used internally in rci
    Native Veg Cover  — redundant with natural_habitat + natural_landcover
    PSI               — redundant with habitat_health (same NDVI stability concept)
    Veg Drought Stress — deferred for later

Key design decisions:
    - tier2_eligible=False for all aquatic/eDNA/plant/scalar/change indicators (revist)
    - tspi: raw NDCI (-1 to 1), higher_is_better=False (more chlorophyll = more stress)
    - wsdi: higher_is_better=False (peak at 0.5 occurrence = maximally unstable)
    - hsas: requires config.raster_paths['edna_points_asset']; falls back to suitability only
    - shdi: scalar-only metric (≥1.0); no spatial map; pillar=2
    - stsi: site-relative normalization only; not cross-site comparable
    - ivsi: detects NDVI expansion (not taxonomic invasion); use alongside iri
    - RCI citation corrected: Naiman & Decamps (1997), not MacArthur/Wilson
    - flii: reference_radius_km=150
    - ceri: ee.Filter.notNull([cat_col]) before .map() to prevent null crash
    - Scoring: Protocol B v1.0 thresholds applied in SoN scoring layer
"""

from __future__ import annotations
import logging, math
from typing import Any, Dict
import numpy as np
from darukaa_reference.config import Config
from darukaa_reference.registry import IndicatorRegistry

logger = logging.getLogger(__name__)

_EII_ASSET = "projects/landler-open-data/assets/eii/global/eii_global_v1"
_MAMMALS   = "projects/darukaa-earth-product/assets/Biodiversity/RedList_Mammals_Terrestrial"
_BIRDS     = "projects/darukaa-earth-product/assets/Biodiversity/RedList_Bird_IUCN_Category"
_KBA       = "projects/darukaa-earth-product/assets/Biodiversity/KBA_Global_POL_SEP25"
_PV        = "projects/darukaa-earth-product/assets/biodiversity_India_PV_Binary_2025_Full_Mosaic"
_MSA       = "projects/ee-jayankandir/assets/TerrestrialMSA_2015_World"
_PLANT_REDLIST = "projects/darukaa-earth-product/assets/Biodiversity/IUCN_Plant_Redlist"


# ── Helpers ───────────────────────────────────────────────────────────────────

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


# ═══════════════════════════════════════════════════════════════════════════════
# IMAGE BUILDERS — TERRESTRIAL CORE
# ═══════════════════════════════════════════════════════════════════════════════

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
    gfc=ee.Image("UMD/hansen/global_forest_change_2025_v1_13")
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
    forest=modis.gte(1).And(modis.lte(10)).Or(modis.eq(14))
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
    f=npp.divide(2.0).min(1).max(0); b=_img_bii(c)
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
    cf=lc.expression(
        "b('LC_Type1')<=5?0.10:b('LC_Type1')==7?0.20:b('LC_Type1')==8?0.20:"
        "b('LC_Type1')==9?0.20:b('LC_Type1')==10?0.05:b('LC_Type1')==12?0.30:"
        "b('LC_Type1')==13?0.50:0.0").rename("PDF")
    return cf

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

def _img_flagship_hsi(c):
    import ee; y=c.ndvi_year
    dw=ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterDate(f"{y}-01-01",f"{y}-12-31").select("label").mode()
    forest=dw.eq(1); dem=ee.Image("USGS/SRTMGL1_003")
    es=dem.unitScale(0,2000).multiply(-1).add(1)
    viirs=ee.ImageCollection("NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG").filterDate(f"{y}-01-01",f"{y}-12-31").select("avg_rad").mean()
    hs=viirs.unitScale(0,50).multiply(-1).add(1)
    return forest.multiply(es).multiply(hs).rename("HSI")

def _img_cpland_binary(c):
    import ee
    pa=c.raster_paths.get("pv_binary",_PV)
    try: return ee.Image(pa).select(0).rename("cpland")
    except Exception as e:
        logger.warning(f"CPLAND binary image: {e}"); return None


# ═══════════════════════════════════════════════════════════════════════════════
# IMAGE BUILDERS — AQUATIC & eDNA 
# ═══════════════════════════════════════════════════════════════════════════════

def _s2_masked(c, use_qa60=True):
    """Return annual cloud-masked S2 SR collection."""
    import ee; y=c.ndvi_year
    if use_qa60:
        def msk(img):
            qa=img.select('QA60'); mask=qa.bitwiseAnd(1<<10).eq(0).And(qa.bitwiseAnd(1<<11).eq(0))
            return img.updateMask(mask).divide(10000).copyProperties(img,['system:time_start'])
    else:
        def msk(img):
            scl=img.select('SCL')
            mask=scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))
            return img.updateMask(mask).divide(10000).copyProperties(img,['system:time_start'])
    return (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
            .filterDate(f"{y}-01-01",f"{y}-12-31")
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE',20))
            .map(msk))

def _ls8_masked(c):
    """Return annual cloud-masked Landsat 8 collection."""
    import ee; y=c.ndvi_year
    def msk(img):
        qa=img.select('QA_PIXEL')
        mask=qa.bitwiseAnd(1<<4).eq(0).And(qa.bitwiseAnd(1<<3).eq(0))
        return img.updateMask(mask)
    return (ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
            .filterDate(f"{y}-01-01",f"{y}-12-31")
            .map(msk))

def _img_tspi(c):
    """NDCI = (B5-B4)/(B5+B4). Mishra & Mishra (2012). Higher = more eutrophication."""
    composite=_s2_masked(c).median()
    return composite.normalizedDifference(['B5','B4']).rename('TSPI')

def _img_sabf(c):
    """Surface Algal Bloom Frequency via FAI (Hu 2009). Returns bloom occurrence 0-1."""
    import ee
    def calc_fai(img):
        red=img.select('B4'); nir=img.select('B8'); swir=img.select('B11')
        baseline=red.add(swir.subtract(red).multiply((842-665)/(1610-665)))
        return nir.subtract(baseline).rename('FAI').copyProperties(img,['system:time_start'])
    s2=_s2_masked(c); fai_col=s2.map(calc_fai)
    bloom_col=fai_col.map(lambda img: img.select('FAI').gt(0.005).rename('Bloom')
                          .copyProperties(img,['system:time_start']))
    return bloom_col.sum().divide(bloom_col.count()).rename('SABF')

def _img_wcpi(c):
    """Water Clarity Proxy Index via Nechad turbidity inversion. Site-normalized 0-1."""
    import ee
    composite=_s2_masked(c).median()
    ndwi=composite.normalizedDifference(['B3','B8']); water_mask=ndwi.gt(0)
    red=composite.select('B4').updateMask(water_mask)
    tsm=red.expression('(A * r) / (1 - (r / C))',{'r':red,'A':228.1,'C':0.1641}).rename('TSM')
    tsm=tsm.updateMask(tsm.gt(0)).updateMask(tsm.lt(1000))
    return ee.Image(1).divide(tsm.add(1)).rename('WCPI')

def _img_wsdi(c):
    """Water Surface Dynamics Index via S1 SAR VV. Peaks at 0.5 occurrence (most dynamic)."""
    import ee; y=c.ndvi_year
    s1=(ee.ImageCollection('COPERNICUS/S1_GRD')
        .filterDate(f"{y}-01-01",f"{y}-12-31")
        .filter(ee.Filter.eq('instrumentMode','IW'))
        .filter(ee.Filter.listContains('transmitterReceiverPolarisation','VV'))
        .select('VV'))
    def detect_water(img):
        smooth=img.focal_mean(radius=30,units='meters')
        return smooth.lt(-16).rename('water').copyProperties(img,['system:time_start'])
    wc=s1.map(detect_water)
    occurrence=wc.sum().divide(wc.count()).rename('Occurrence')
    return ee.Image(1).subtract(occurrence.subtract(0.5).abs().multiply(2)).rename('WSDI')

def _img_stsi_raw(c):
    """Raw LST from Landsat 8 for STSI — normalization applied in extract_fn."""
    import ee
    composite=_ls8_masked(c).median()
    return composite.select('ST_B10').multiply(0.00341802).add(149.0).subtract(273.15).rename('STSI')

def _img_sdi(c):
    """Disturbed land cover mask (DW classes 4+6+7) for SDI computation."""
    import ee; y=c.ndvi_year
    dw=(ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1')
        .filterDate(f"{y}-01-01",f"{y}-12-31").select('label').mode())
    disturbed=dw.eq(4).Or(dw.eq(6)).Or(dw.eq(7))
    roads_proxy=dw.eq(6).focalMax(1).subtract(dw.eq(6)).gt(0)
    return disturbed.Or(roads_proxy).rename('Disturbed')

def _img_hsas(c):
    """Habitat suitability surface: NDVI*0.5 + water proximity*0.3 + (1-disturbance)*0.2."""
    import ee; y=c.ndvi_year
    composite=_s2_masked(c).median()
    ndvi=composite.normalizedDifference(['B8','B4']).unmask(0)
    ndwi=composite.normalizedDifference(['B3','B8']); water_mask=ndwi.gt(0)
    water_dist=water_mask.selfMask().distance(ee.Kernel.euclidean(500,'meters'))
    water_suit=ee.Image(1).subtract(water_dist.divide(500)).clamp(0,1).unmask(0)
    dw=(ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1')
        .filterDate(f"{y}-01-01",f"{y}-12-31").select('label').mode())
    builtup=dw.eq(6)
    built_dist=builtup.selfMask().distance(ee.Kernel.euclidean(500,'meters'))
    disturbance=ee.Image(1).subtract(built_dist.divide(500)).clamp(0,1).unmask(0)
    return (ndvi.multiply(0.5).add(water_suit.multiply(0.3))
            .add(ee.Image(1).subtract(disturbance).multiply(0.2))
            .rename('Suitability').clamp(0,1))

def _img_edpp_bands(c):
    """Multi-band image for EDPP: LST, turbidity protection, moisture, UV exposure."""
    import ee; y=c.ndvi_year
    composite=_s2_masked(c).median(); lsc=_ls8_masked(c).median()
    lst=lsc.select('ST_B10').multiply(0.00341802).add(149.0).subtract(273.15).rename('LST')
    turbidity=composite.select('B4').unitScale(0,0.3).clamp(0,1)
    turbidity_prot=ee.Image(1).subtract(turbidity.subtract(0.5).abs().multiply(2)).clamp(0,1)
    ndwi=composite.normalizedDifference(['B3','B8'])
    moisture=ndwi.unitScale(-1,1).clamp(0,1).unmask(0)
    dw=(ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1')
        .filterDate(f"{y}-01-01",f"{y}-12-31").select('label').mode())
    bare=dw.eq(7)
    exposure=ee.Image(1).subtract(
        bare.selfMask().distance(ee.Kernel.euclidean(300,'meters')).divide(300)
    ).clamp(0,1).unmask(0)
    return lst.addBands(turbidity_prot.rename('TurbProt')).addBands(
        moisture.rename('Moisture')).addBands(exposure.rename('Exposure'))

def _img_iri(c):
    """Invasive Risk Index: connectivity*0.30+nutrient*0.25+human*0.20+disturbance*0.15+access*0.10."""
    import ee; y=c.ndvi_year
    composite=_s2_masked(c).median()
    ndwi=composite.normalizedDifference(['B3','B8']); water_mask=ndwi.gt(0)
    water_dist=water_mask.selfMask().distance(ee.Kernel.euclidean(200,'meters'))
    connectivity=ee.Image(1).subtract(water_dist.divide(200)).clamp(0,1).unmask(0)
    ndci=composite.normalizedDifference(['B5','B4'])
    nutrient=ndci.unitScale(-0.2,0.5).clamp(0,1)
    dw=(ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1')
        .filterDate(f"{y}-01-01",f"{y}-12-31").select('label').mode())
    builtup=dw.eq(6)
    built_dist=builtup.selfMask().distance(ee.Kernel.euclidean(200,'meters'))
    human_pressure=ee.Image(1).subtract(built_dist.divide(200)).clamp(0,1).unmask(0)
    disturb_mask=dw.eq(4).Or(dw.eq(7))
    disturb_dist=disturb_mask.selfMask().distance(ee.Kernel.euclidean(200,'meters'))
    disturbance=ee.Image(1).subtract(disturb_dist.divide(200)).clamp(0,1).unmask(0)
    roads_proxy=builtup.focalMax(1).subtract(builtup).gt(0)
    road_dist=roads_proxy.selfMask().distance(ee.Kernel.euclidean(100,'meters'))
    accessibility=ee.Image(1).subtract(road_dist.divide(100)).clamp(0,1).unmask(0)
    return (connectivity.multiply(0.30).add(nutrient.multiply(0.25))
            .add(human_pressure.multiply(0.20)).add(disturbance.multiply(0.15))
            .add(accessibility.multiply(0.10)).rename('IRI').clamp(0,1))

def _img_mspl_bands(c):
    """Multi-band image for MSPL: nutrient, LST, turbidity, water persistence."""
    import ee; y=c.ndvi_year
    composite=_s2_masked(c).median(); lsc=_ls8_masked(c).median()
    ndci=composite.normalizedDifference(['B5','B4'])
    nutrient=ndci.unitScale(-0.2,0.5).clamp(0,1).unmask(0)
    lst=lsc.select('ST_B10').multiply(0.00341802).add(149.0).subtract(273.15).rename('LST')
    turbidity=composite.select('B4').unitScale(0,0.3).clamp(0,1).unmask(0)
    ndwi=composite.normalizedDifference(['B3','B8'])
    water_persist=ndwi.gt(0).focal_mean(radius=100,units='meters').clamp(0,1).unmask(0)
    return lst.addBands(nutrient.rename('NutrientStress')).addBands(
        turbidity.rename('TurbidityStress')).addBands(water_persist.rename('WaterPersist'))

def _img_rci(c):
    """Riparian Complexity Index from 2-year S2 window."""
    import ee; y=c.ndvi_year
    start=f"{y-1}-01-01"; end=f"{y}-12-31"
    def msk(img):
        qa=img.select('QA60'); mask=qa.bitwiseAnd(1<<10).eq(0).And(qa.bitwiseAnd(1<<11).eq(0))
        return img.updateMask(mask).divide(10000).copyProperties(img,['system:time_start'])
    s2=(ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
        .filterDate(start,end).filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE',20)).map(msk))
    composite=s2.median()
    ndvi=composite.normalizedDifference(['B8','B4']).rename('NDVI')
    evi=composite.expression('2.5*((NIR-RED)/(NIR+6*RED-7.5*BLUE+1))',
        {'NIR':composite.select('B8'),'RED':composite.select('B4'),'BLUE':composite.select('B2')}).rename('EVI')
    ndvi_std=s2.map(lambda img: img.normalizedDifference(['B8','B4']).rename('NDVI')
                    ).reduce(ee.Reducer.stdDev()).rename('NDVI_std')
    veg_var=ndvi_std.unitScale(0,0.2).clamp(0,1)
    veg_complex=evi.unitScale(0,1).clamp(0,1)
    veg_prod=ndvi.unitScale(0,1).clamp(0,1)
    edge_complex=ndvi.reduceNeighborhood(
        reducer=ee.Reducer.stdDev(),
        kernel=ee.Kernel.circle(radius=30,units='meters')).unitScale(0,0.15).clamp(0,1)
    return (veg_var.multiply(0.30).add(veg_complex.multiply(0.30))
            .add(veg_prod.multiply(0.20)).add(edge_complex.multiply(0.20))
            .rename('RCI').clamp(0,1))


# ═══════════════════════════════════════════════════════════════════════════════
# IMAGE BUILDERS — TERRESTRIAL VEGETATION + PLANT SPECIES 
# ═══════════════════════════════════════════════════════════════════════════════

def _img_riparian_ndvi_trend(c):
    """Linear NDVI slope (NDVI/year) from 2-year S2 time series."""
    import ee; y=c.ndvi_year; start_str=f"{y-1}-01-01"; end_str=f"{y}-12-31"
    def msk(img):
        qa=img.select('QA60'); mask=qa.bitwiseAnd(1<<10).eq(0).And(qa.bitwiseAnd(1<<11).eq(0))
        return img.updateMask(mask).divide(10000).copyProperties(img,['system:time_start'])
    s2=(ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
        .filterDate(start_str,end_str).filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE',20)).map(msk))
    start_ee=ee.Date(start_str)
    def with_time(img):
        t=ee.Image.constant(img.date().difference(start_ee,'year')).toFloat()
        ndvi=img.normalizedDifference(['B8','B4']).toFloat().rename('NDVI')
        return ndvi.addBands(t.rename('time'))
    return s2.map(with_time).select(['time','NDVI']).reduce(ee.Reducer.linearFit()).select('scale').rename('NDVI_Trend')

def _img_lai(c):
    """MODIS MCD15A3H LAI. Scale 0.1. Valid 0-8 m2/m2."""
    import ee; y=c.ndvi_year
    lai=(ee.ImageCollection('MODIS/061/MCD15A3H')
         .filterDate(f"{y}-01-01",f"{y}-12-31").select('Lai'))
    mean_lai=lai.map(lambda img: img.multiply(0.1).rename('LAI')).mean()
    return mean_lai.updateMask(mean_lai.gte(0).And(mean_lai.lte(8))).rename('LAI')

def _img_chm(c):
    """GEDI L2A rh98 canopy height. 2-year window, quality-masked 0-80m."""
    import ee; y=c.ndvi_year
    gedi=(ee.ImageCollection('LARSE/GEDI/GEDI02_A_002_MONTHLY')
          .filterDate(f"{y-1}-01-01",f"{y}-12-31").select('rh98'))
    return gedi.map(lambda img: img.updateMask(img.gte(0).And(img.lte(80)))).mean().rename('CHM')

def _img_ivsi(c):
    """IVSI: fraction of pixels with NDVI increase >0.2 vs 5-year prior."""
    import ee; y=c.ndvi_year; old_year=y-5
    def msk(img):
        scl=img.select('SCL')
        mask=scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))
        return img.updateMask(mask).divide(10000).copyProperties(img,['system:time_start'])
    def add_ndvi(img):
        return img.addBands(img.normalizedDifference(['B8','B4']).rename('NDVI'))
    s2_old=(ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
            .filterDate(f"{old_year}-01-01",f"{old_year}-12-31")
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE',20)).map(msk).map(add_ndvi))
    s2_new=(ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
            .filterDate(f"{y}-01-01",f"{y}-12-31")
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE',20)).map(msk).map(add_ndvi))
    old_ndvi=s2_old.select('NDVI').median(); new_ndvi=s2_new.select('NDVI').median()
    return new_ndvi.subtract(old_ndvi).gt(0.2).rename('IVSI')


# ═══════════════════════════════════════════════════════════════════════════════
# FC TIER 1 HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _fc_tier1_endemic_richness(site_geom, region, config):
    import ee
    region_ee = region if isinstance(region, ee.Geometry) else _to_ee(region)
    total = 0
    for asset in [_MAMMALS, _BIRDS]:
        fc = _load_fc(asset, config)
        if not fc: continue
        try:
            wa = fc.map(lambda f: f.set("rk2", f.geometry().area().divide(1e6)))
            n = wa.filter(ee.Filter.lt("rk2", 100000)).filterBounds(region_ee).distinct("sci_name").size().getInfo()
            total += n
        except Exception as e:
            logger.warning(f"FC Tier1 endemic: {e}")
    if total == 0: return {}
    return {"mean": float(total), "median": float(total), "n": 1}

def _fc_tier1_threatened_richness(site_geom, region, config):
    import ee
    region_ee = region if isinstance(region, ee.Geometry) else _to_ee(region)
    total = 0
    for asset, nc, cc in [(_MAMMALS, "sci_name", "category"), (_BIRDS, "sci_name", "RedList__5")]:
        fc = _load_fc(asset, config)
        if not fc: continue
        try:
            total += fc.filter(ee.Filter.inList(cc, ["CR","EN","VU"])).filterBounds(region_ee).distinct(nc).size().getInfo()
        except Exception as e:
            logger.warning(f"FC Tier1 threatened({asset}): {e}")
    if total == 0: return {}
    return {"mean": float(total), "median": float(total), "n": 1}


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════

def create_default_registry() -> IndicatorRegistry:
    r = IndicatorRegistry()

    # ── DIM 1: ECOSYSTEM EXTENT ───────────────────────────────────────────────
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
        metadata={"tnfd_dim": 1, "note": "India-only PV binary asset",
                  "gee_image_fn": _img_cpland_binary})

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

    # ── DIM 2: ECOSYSTEM CONDITION — Terrestrial core ────────────────────────
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
        citation="Hill et al. (2022). Kennedy et al. (2019). DOI:10.1111/gcb.14549",
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

    # ── DIM 2: ECOSYSTEM CONDITION — Aquatic & eDNA (v6.4) ───────────────────
    r.register(name="tspi", display_name="Trophic State Proxy Index (NDCI)", source_type="gee",
        extract_fn=extract_tspi, unit="index", value_range=(-1,1),
        citation="Mishra S & Mishra DR (2012) RSE 117:394-405. DOI:10.1016/j.rse.2011.10.016",
        tier2_eligible=False, higher_is_better=False, reference_radius_km=10.0, pillar=2,
        metadata={"gee_image_fn": _img_tspi, "tnfd_dim": 2,
                  "note": "Raw NDCI. Higher = more chlorophyll-a / eutrophication. Aquatic only."})

    r.register(name="sabf", display_name="Surface Algal Bloom Frequency", source_type="gee",
        extract_fn=extract_sabf, unit="frequency (0-1)", value_range=(0,1),
        citation="Hu C (2009) RSE 113:2118-2129. DOI:10.1016/j.rse.2009.05.012",
        tier2_eligible=False, higher_is_better=False, reference_radius_km=10.0, pillar=2,
        metadata={"gee_image_fn": _img_sabf, "tnfd_dim": 2,
                  "note": "FAI bloom threshold=0.005 (S2 inland water). Higher = more bloom events."})

    r.register(name="wcpi", display_name="Water Clarity Proxy Index", source_type="gee",
        extract_fn=extract_wcpi, unit="index (0-1, site-relative)", value_range=(0,1),
        citation=("Nechad et al. (2010) RSE 114:1167. DOI:10.1016/j.rse.2009.11.022; "
                  "Binding et al. (2018) L&O 63:1616. DOI:10.1002/lno.10940"),
        tier2_eligible=False, higher_is_better=True, reference_radius_km=10.0, pillar=2,
        metadata={"gee_image_fn": _img_wcpi, "tnfd_dim": 2,
                  "note": "Site-normalized. Not comparable across sites. Water pixels only."})

    r.register(name="wsdi", display_name="Water Surface Dynamics Index", source_type="gee",
        extract_fn=extract_wsdi, unit="index (0-1)", value_range=(0,1),
        citation="Pekel et al. (2016) Nature 540:418-422. DOI:10.1038/nature20584",
        tier2_eligible=False, higher_is_better=False, reference_radius_km=10.0, pillar=2,
        metadata={"gee_image_fn": _img_wsdi, "tnfd_dim": 2,
                  "note": "Peaks at 0.5 occurrence = most dynamic/unstable. Lower = more stable."})

    r.register(name="hsas", display_name="Habitat Suitability Alignment Score", source_type="gee",
        extract_fn=extract_hsas, unit="index (0-1)", value_range=(0,1),
        citation="Elith J & Leathwick JR (2009) Annu Rev Ecol Evol Syst 40:677. DOI:10.1146/annurev.ecolsys.110308.120159",
        tier2_eligible=False, higher_is_better=True, reference_radius_km=10.0, pillar=2,
        metadata={"gee_image_fn": _img_hsas, "tnfd_dim": 2,
                  "note": "Requires config.raster_paths['edna_points_asset']. Without eDNA points returns habitat suitability only."})

    r.register(name="edpp", display_name="eDNA Persistence Potential", source_type="gee",
        extract_fn=extract_edpp, unit="index (0-1)", value_range=(0,1),
        citation=("Strickler KM et al. (2015) EST 49:4209. DOI:10.1021/es404734p; "
                  "Roussel JM et al. (2015) Biol Conserv 183:50. DOI:10.1016/j.biocon.2014.11.038"),
        tier2_eligible=False, higher_is_better=True, reference_radius_km=10.0, pillar=2,
        metadata={"gee_image_fn": _img_edpp_bands, "tnfd_dim": 2,
                  "note": "Higher = better eDNA preservation conditions."})

    r.register(name="mspl", display_name="Microbial Stress Probability Layer", source_type="gee",
        extract_fn=extract_mspl, unit="probability (0-1)", value_range=(0,1),
        citation="Shade A et al. (2012) Microb Ecol 63:795. DOI:10.1007/s00248-012-0159-y",
        tier2_eligible=False, higher_is_better=False, reference_radius_km=10.0, pillar=2,
        metadata={"gee_image_fn": _img_mspl_bands, "tnfd_dim": 2,
                  "note": "Proxy for eutrophic/microbial imbalance. Complements 16S eDNA."})

    r.register(name="rci", display_name="Riparian Complexity Index", source_type="gee",
        extract_fn=extract_rci, unit="index (0-1)", value_range=(0,1),
        citation="Naiman RJ & Decamps H (1997) Annu Rev Ecol Syst 28:621. DOI:10.1146/annurev.ecolsys.28.1.621",
        tier2_eligible=False, higher_is_better=True, reference_radius_km=25.0, pillar=2,
        metadata={"gee_image_fn": _img_rci, "tnfd_dim": 2,
                  "note": "100m riparian buffer. 2-year S2 window."})

    # ── DIM 2: ECOSYSTEM CONDITION — Terrestrial vegetation  ───────────
    r.register(name="riparian_ndvi_trend", display_name="Riparian NDVI Temporal Trend", source_type="gee",
        extract_fn=extract_riparian_ndvi_trend, unit="NDVI/year", value_range=(-0.5,0.5),
        citation="Naiman RJ et al. (2005) TREE 20:312. DOI:10.1016/j.tree.2005.05.011",
        tier2_eligible=False, higher_is_better=True, reference_radius_km=25.0, pillar=2,
        metadata={"gee_image_fn": _img_riparian_ndvi_trend, "tnfd_dim": 2,
                  "note": "Linear slope NDVI/year in riparian zone. Negative = degradation trend."})

    r.register(name="jrc_water_persistence", display_name="JRC Water Persistence (Permanent Fraction)", source_type="gee",
        extract_fn=extract_jrc_water_persistence, unit="fraction (0-1)", value_range=(0,1),
        citation="Pekel JF et al. (2016) Nature 540:418. DOI:10.1038/nature20584",
        tier2_eligible=False, higher_is_better=True, reference_radius_km=10.0, pillar=2,
        metadata={"tnfd_dim": 2,
                  "note": "Fraction of site with water >75% of months. Complements WSDI (SAR-based)."})

    r.register(name="shdi", display_name="Shoreline Development Index (Morphometric)", source_type="gee",
        extract_fn=extract_shdi, unit="dimensionless (≥1.0)", value_range=(1.0,20.0),
        citation="Jennings E et al. (2003) Freshwater Biology 48:301. DOI:10.1046/j.1365-2427.2003.00988.x",
        tier2_eligible=False, higher_is_better=True, reference_radius_km=10.0, pillar=2,
        metadata={"tnfd_dim": 2,
                  "note": "SCALAR metric only — no spatial map. Min=1.0 (circle). DO NOT confuse with sdi (disturbance)."})

    r.register(name="lai", display_name="Leaf Area Index (MODIS MCD15A3H)", source_type="gee",
        extract_fn=extract_lai, unit="m²/m²", value_range=(0,8),
        citation="Myneni RB et al. (2002) RSE 83:214. DOI:10.1016/S0034-4257(02)00074-3",
        tier2_eligible=True, higher_is_better=True, reference_radius_km=50.0, pillar=2,
        metadata={"gee_image_fn": _img_lai, "tnfd_dim": 2,
                  "note": "MODIS 500m. Scale factor 0.1 applied."})

    r.register(name="chm", display_name="Canopy Height Model (GEDI L2A rh98)", source_type="gee",
        extract_fn=extract_chm, unit="metres", value_range=(0,80),
        citation="Dubayah R et al. (2020) Sci Remote Sens 1:100002. DOI:10.1016/j.srs.2020.100002",
        tier2_eligible=True, higher_is_better=True, reference_radius_km=50.0, pillar=2,
        metadata={"gee_image_fn": _img_chm, "tnfd_dim": 2,
                  "note": "GEDI L2A rh98. 2-year window. Quality-masked 0-80m."})

    # ── DIM 3: SPECIES POPULATION SIZE ───────────────────────────────────────
    r.register(name="endemic_richness", display_name="Endemic Species Richness", source_type="gee",
        extract_fn=extract_endemic_richness, unit="count", value_range=(0,500),
        citation="IUCN mammal ranges. Range < 100,000 km².",
        tier2_eligible=False, reference_radius_km=100.0, pillar=3,
        metadata={"tnfd_dim": 3, "note": "Mammals + birds. Species list in metadata.",
                  "fc_tier1_fn": _fc_tier1_endemic_richness})

    r.register(name="flagship_habitat", display_name="Flagship Habitat Viability", source_type="gee",
        extract_fn=extract_flagship_habitat, unit="index", value_range=(0,1),
        citation="Forest × elevation_suit × inverse_pressure. Bird threatened overlay.",
        tier2_eligible=False, reference_radius_km=50.0, pillar=3,
        metadata={"tnfd_dim": 3, "note": "Requires bird asset.",
                  "gee_image_fn": _img_flagship_hsi})

    r.register(name="endemic_plant_richness", display_name="Endemic Plant Species Richness", source_type="gee",
        extract_fn=extract_endemic_plant_richness, unit="count", value_range=(0,1000),
        citation="IUCN Standards and Petitions Committee (2022) Guidelines v15.1. DOI:10.2305/IUCN.CH.2022.24.en",
        tier2_eligible=False, higher_is_better=True, reference_radius_km=100.0, pillar=3,
        metadata={"tnfd_dim": 3,
                  "note": "IUCN_Plant_Redlist. Range < 100,000 km². Distinct by sci_name."})

    # ── DIM 4: SPECIES EXTINCTION RISK ───────────────────────────────────────
    r.register(name="threatened_richness", display_name="Threatened Species Richness", source_type="gee",
        extract_fn=extract_threatened_richness, unit="count", value_range=(0,500),
        citation="IUCN Red List. CR/EN/VU mammals + birds.",
        tier2_eligible=False, higher_is_better=False, reference_radius_km=100.0, pillar=4,
        metadata={"tnfd_dim": 4, "fc_tier1_fn": _fc_tier1_threatened_richness})

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

    r.register(name="threatened_plant_richness", display_name="Threatened Plant Species Richness", source_type="gee",
        extract_fn=extract_threatened_plant_richness, unit="count", value_range=(0,1000),
        citation="IUCN Standards and Petitions Committee (2022) Guidelines v15.1. DOI:10.2305/IUCN.CH.2022.24.en",
        tier2_eligible=False, higher_is_better=False, reference_radius_km=100.0, pillar=4,
        metadata={"tnfd_dim": 4,
                  "note": "IUCN_Plant_Redlist. CR/EN/VU. Returns n_CR/n_EN/n_VU counts."})

    # ── THREATS & PRESSURES (pillar=5) ───────────────────────────────────────
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

    r.register(name="sdi", display_name="Shoreline Disturbance Index", source_type="gee",
        extract_fn=extract_sdi, unit="fraction (0-1)", value_range=(0,1),
        citation="Allan JD et al. (2002) BioScience 52:883. DOI:10.1641/0006-3568(2002)052[0883:UBAC]2.0.CO;2",
        tier2_eligible=False, higher_is_better=False, reference_radius_km=10.0, pillar=5,
        metadata={"gee_image_fn": _img_sdi, "tnfd_dim": "threats",
                  "note": "Disturbed fraction in 100m shore buffer. DW classes: crops(4), built(6), bare(7)."})

    r.register(name="stsi", display_name="Surface Temperature Stress Index", source_type="gee",
        extract_fn=extract_stsi, unit="index (0-1, site-relative)", value_range=(0,1),
        citation="Jimenez-Munoz JC et al. (2014) RSE 155:11. DOI:10.1016/j.rse.2013.08.027",
        tier2_eligible=False, higher_is_better=False, reference_radius_km=25.0, pillar=5,
        metadata={"gee_image_fn": _img_stsi_raw, "tnfd_dim": "threats",
                  "note": "Site-relative normalization only. Not cross-site comparable."})

    r.register(name="iri", display_name="Invasive Risk Index", source_type="gee",
        extract_fn=extract_iri, unit="index (0-1)", value_range=(0,1),
        citation=("Bellard C et al. (2016) Glob Change Biol 22:1869. DOI:10.1111/gcb.13004; "
                  "Mandrak NE & Cudmore B (2009) Can J Fish Aquat Sci 67:1135. DOI:10.1139/F08-099"),
        tier2_eligible=False, higher_is_better=False, reference_radius_km=10.0, pillar=5,
        metadata={"gee_image_fn": _img_iri, "tnfd_dim": "threats",
                  "note": "Road proxy = built-up edge (not true road dataset)."})

    r.register(name="ivsi", display_name="Invasive Vegetation Spread Index", source_type="gee",
        extract_fn=extract_ivsi, unit="fraction (0-1)", value_range=(0,1),
        citation="Paz-Kagan T et al. (2019) RSE 233:111396. DOI:10.1016/j.rse.2019.111396",
        tier2_eligible=False, higher_is_better=False, reference_radius_km=25.0, pillar=5,
        metadata={"gee_image_fn": _img_ivsi, "tnfd_dim": "threats",
                  "note": "NDVI expansion >0.2 vs 5-year prior. Detects expansion broadly, not taxonomic invasion."})

    return r


# ═══════════════════════════════════════════════════════════════════════════════
# EXTRACTION FUNCTIONS — TERRESTRIAL CORE
# ═══════════════════════════════════════════════════════════════════════════════

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
    gfc=ee.Image("UMD/hansen/global_forest_change_2025_v1_13").clip(eg)
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

def extract_ghm(g,c): return _reduce(_img_ghm(c),g,1000)
def extract_light_pollution(g,c): return _reduce(_img_viirs(c),g,500)
def extract_hdi(g,c): return _reduce(_img_hdi(c),g,10)
def extract_lst_day(g,c): return _reduce(_img_lst_day(c),g,1000)
def extract_lst_night(g,c): return _reduce(_img_lst_night(c),g,1000)

def extract_endemic_richness(g,c):
    import ee; eg=_to_ee(g); total=0; species_list=[]
    for asset,nc,group in [(_MAMMALS,"sci_name","mammal"),(_BIRDS,"sci_name","bird")]:
        fc=_load_fc(asset,c)
        if not fc: continue
        try:
            wa=fc.map(lambda f:f.set("rk2",f.geometry().area().divide(1e6)))
            filtered=wa.filter(ee.Filter.lt("rk2",100000)).filterBounds(eg).distinct(nc)
            n=filtered.size().getInfo(); total+=n
            names=filtered.reduceColumns(ee.Reducer.toList(),[nc]).get("list").getInfo()
            for name in (names or []):
                species_list.append({"name":name,"group":group})
        except Exception as e: logger.warning(f"Endemic {group}: {e}")
    return {"value":total if total>0 else None,"pixels":None,
            "metadata":{"species_list":species_list,
                        "n_mammals":sum(1 for s in species_list if s["group"]=="mammal"),
                        "n_birds":sum(1 for s in species_list if s["group"]=="bird"),
                        "range_threshold_km2":100000}}

def extract_flagship_habitat(g,c):
    import ee; eg=_to_ee(g)
    try:
        y=c.ndvi_year
        dw=ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterDate(f"{y}-01-01",f"{y}-12-31").filterBounds(eg).select("label").mode()
        forest=dw.eq(1); dem=ee.Image("USGS/SRTMGL1_003")
        es=dem.unitScale(0,2000).multiply(-1).add(1)
        viirs=ee.ImageCollection("NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG").filterDate(f"{y}-01-01",f"{y}-12-31").select("avg_rad").mean()
        hs=viirs.unitScale(0,50).multiply(-1).add(1)
        hsi=forest.multiply(es).multiply(hs).rename("HSI")
        hsi_val=hsi.reduceRegion(reducer=ee.Reducer.mean(),geometry=eg,scale=1000,maxPixels=1e13).get("HSI").getInfo()
        if hsi_val is None: return {"value":None,"pixels":None}
        n_species=0
        birds=_load_fc(_BIRDS,c)
        if birds:
            n_species+=birds.filter(ee.Filter.inList("RedList__5",["CR","EN","VU"])).filterBounds(eg).distinct("sci_name").size().getInfo()
        mammals=_load_fc(_MAMMALS,c)
        if mammals:
            n_species+=mammals.filter(ee.Filter.inList("category",["CR","EN","VU"])).filterBounds(eg).distinct("sci_name").size().getInfo()
        species_suit=min(n_species/50.0,1.0)
        return {"value":float(hsi_val)*0.6+species_suit*0.4,"pixels":None}
    except Exception as e: logger.warning(f"Flagship: {e}"); return {"value":None,"pixels":None}

def extract_threatened_richness(g,c):
    import ee; eg=_to_ee(g); total=0; species_list=[]
    for asset,nc,cc in [(_MAMMALS,"sci_name","category"),(_BIRDS,"sci_name","RedList__5")]:
        fc=_load_fc(asset,c)
        if not fc: continue
        try:
            filtered=fc.filter(ee.Filter.inList(cc,["CR","EN","VU"])).filterBounds(eg).distinct(nc)
            n=filtered.size().getInfo(); total+=n
            props=filtered.reduceColumns(ee.Reducer.toList(2),[nc,cc]).get("list").getInfo()
            for row in (props or []):
                if len(row)>=2: species_list.append({"name":row[0],"category":row[1],"group":"mammal" if asset==_MAMMALS else "bird"})
        except Exception as e: logger.warning(f"Threatened({asset}): {e}")
    return {"value":total if total>0 else None,"pixels":None,
            "metadata":{"species_list":species_list,
                        "n_mammals":sum(1 for s in species_list if s["group"]=="mammal"),
                        "n_birds":sum(1 for s in species_list if s["group"]=="bird")}}

def extract_ceri(g,c):
    import ee; eg=_to_ee(g); tn=0; tw=0; species_list=[]
    for asset,nc,cc in [(_MAMMALS,"sci_name","category"),(_BIRDS,"sci_name","RedList__5")]:
        fc=_load_fc(asset,c)
        if not fc: continue
        try:
            def aw(f):
                cat=ee.String(f.get(cc))
                w=ee.Number(ee.Algorithms.If(cat.compareTo("EX").eq(0),5,ee.Algorithms.If(cat.compareTo("EW").eq(0),5,ee.Algorithms.If(cat.compareTo("CR").eq(0),4,ee.Algorithms.If(cat.compareTo("EN").eq(0),3,ee.Algorithms.If(cat.compareTo("VU").eq(0),2,ee.Algorithms.If(cat.compareTo("NT").eq(0),1,ee.Algorithms.If(cat.compareTo("LC").eq(0),0,0))))))))
                return f.set("weight",w)
            wf=fc.filterBounds(eg).filter(ee.Filter.notNull([cc])).map(aw).distinct(nc)
            n=wf.size().getInfo(); tw_local=wf.aggregate_sum("weight").getInfo()
            tn+=n; tw+=tw_local
            props=wf.reduceColumns(ee.Reducer.toList(2),[nc,cc]).get("list").getInfo()
            for row in (props or []):
                if len(row)>=2: species_list.append({"name":row[0],"category":row[1],"group":"mammal" if asset==_MAMMALS else "bird"})
        except Exception as e: logger.warning(f"CERI({asset}): {e}")
    if tn==0: return {"value":None,"pixels":None}
    return {"value":tw/(tn*5),"pixels":None,
            "metadata":{"species_list":species_list,"n_species":tn,
                        "categories_included":"EX/EW=5,CR=4,EN=3,VU=2,NT=1,LC=0"}}

def extract_star_t(g,c):
    import ee; eg=_to_ee(g); y=c.ndvi_year
    try:
        dw=ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterDate(f"{y}-01-01",f"{y}-12-31").filterBounds(eg).select("label").mode()
        hm=dw.remap([1,2,3,5],[1,1,1,1],0); bm=dw.eq(6)
        bd=bm.reduceNeighborhood(reducer=ee.Reducer.mean(),kernel=ee.Kernel.circle(radius=1000,units="meters"))
        viirs=ee.ImageCollection("NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG").filterDate(f"{y}-01-01",f"{y}-12-31").select("avg_rad").mean()
        nn=viirs.unitScale(0,50); tp=bd.add(nn).divide(2)
        combined_raster=ee.Image(0).float()
        birds=_load_fc(_BIRDS,c)
        if birds:
            filt_b=birds.filter(ee.Filter.eq("presence",1)).filter(ee.Filter.eq("origin",1)).filter(ee.Filter.inList("RedList__5",["CR","EN","VU"]))
            def aw_b(f):
                cat=ee.String(f.get("RedList__5"))
                w=ee.Number(ee.Algorithms.If(cat.equals("CR"),4,ee.Algorithms.If(cat.equals("EN"),3,ee.Algorithms.If(cat.equals("VU"),2,1))))
                return f.set("weight",w)
            wr_b=filt_b.map(aw_b)
            sr_b=ee.Image().float().paint(featureCollection=wr_b,color="weight")
            combined_raster=combined_raster.add(sr_b.unmask(0))
        mammals=_load_fc(_MAMMALS,c)
        if mammals:
            filt_m=mammals.filter(ee.Filter.inList("category",["CR","EN","VU"]))
            def aw_m(f):
                cat=ee.String(f.get("category"))
                w=ee.Number(ee.Algorithms.If(cat.equals("CR"),4,ee.Algorithms.If(cat.equals("EN"),3,ee.Algorithms.If(cat.equals("VU"),2,1))))
                return f.set("weight",w)
            wr_m=filt_m.map(aw_m)
            sr_m=ee.Image().float().paint(featureCollection=wr_m,color="weight")
            combined_raster=combined_raster.add(sr_m.unmask(0))
        st=combined_raster.multiply(tp).multiply(hm).rename("STAR_T")
        val=st.reduceRegion(reducer=ee.Reducer.mean(),geometry=eg,scale=1000,maxPixels=1e13).get("STAR_T").getInfo()
        return {"value":val,"pixels":None}
    except Exception as e: logger.warning(f"STAR_T: {e}"); return {"value":None,"pixels":None}


# ═══════════════════════════════════════════════════════════════════════════════
# EXTRACTION FUNCTIONS — AQUATIC & eDNA
# ═══════════════════════════════════════════════════════════════════════════════

def extract_tspi(g,c): return _reduce(_img_tspi(c),g,10)
def extract_sabf(g,c): return _reduce(_img_sabf(c),g,10)

def extract_wcpi(g,c):
    import ee
    eg=_to_ee(g); wcpi_raw=_img_wcpi(c)
    if wcpi_raw is None: return {"value":None,"pixels":None}
    stats=wcpi_raw.reduceRegion(reducer=ee.Reducer.minMax(),geometry=eg,scale=10,maxPixels=1e13)
    mn=ee.Number(stats.get('WCPI_min')); mx=ee.Number(stats.get('WCPI_max'))
    span=mx.subtract(mn).max(1e-6)
    wcpi_norm=wcpi_raw.subtract(mn).divide(span).clamp(0,1)
    return _reduce(wcpi_norm,g,10)

def extract_wsdi(g,c):
    import ee; eg=_to_ee(g)
    img=_img_wsdi(c)
    if img is None: return {"value":None,"pixels":None}
    return _reduce(img.clip(eg),g,10)

def extract_sdi(g,c):
    import ee; eg=_to_ee(g)
    try:
        y=c.ndvi_year
        def msk(img):
            qa=img.select('QA60'); mask=qa.bitwiseAnd(1<<10).eq(0).And(qa.bitwiseAnd(1<<11).eq(0))
            return img.updateMask(mask).divide(10000)
        s2=(ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
            .filterDate(f"{y}-01-01",f"{y}-12-31").filterBounds(eg)
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE',20)).map(msk))
        composite=s2.median().clip(eg)
        ndwi=composite.normalizedDifference(['B3','B8'])
        water_vec=ndwi.gt(0).selfMask().reduceToVectors(
            geometry=eg,scale=10,geometryType='polygon',eightConnected=True,maxPixels=1e13)
        water_geom=water_vec.geometry(1); shore_buf=water_geom.buffer(100)
        disturbed=_img_sdi(c)
        pa=ee.Image.pixelArea()
        dist_area=pa.updateMask(disturbed.clip(shore_buf)).reduceRegion(
            reducer=ee.Reducer.sum(),geometry=shore_buf,scale=10,maxPixels=1e13)
        total_area=pa.reduceRegion(reducer=ee.Reducer.sum(),geometry=shore_buf,scale=10,maxPixels=1e13)
        sdi_val=ee.Number(dist_area.get('area')).divide(ee.Number(total_area.get('area')).max(1)).getInfo()
        return {"value":float(sdi_val),"pixels":None}
    except Exception as e: logger.warning(f"SDI: {e}"); return {"value":None,"pixels":None}

def extract_stsi(g,c):
    import ee; eg=_to_ee(g)
    try:
        lst_img=_img_stsi_raw(c).clip(eg)
        stats=lst_img.reduceRegion(reducer=ee.Reducer.minMax(),geometry=eg,scale=30,maxPixels=1e13)
        mn=ee.Number(ee.Algorithms.If(stats.get('STSI_min'),stats.get('STSI_min'),0))
        mx=ee.Number(ee.Algorithms.If(stats.get('STSI_max'),stats.get('STSI_max'),1))
        span=mx.subtract(mn).max(1e-6)
        stsi=lst_img.subtract(mn).divide(span).clamp(0,1).rename('STSI')
        return _reduce(stsi,g,30)
    except Exception as e: logger.warning(f"STSI: {e}"); return {"value":None,"pixels":None}

def extract_hsas(g,c):
    import ee; eg=_to_ee(g)
    suitability=_img_hsas(c).clip(eg)
    edna_asset=getattr(c,'raster_paths',{}).get('edna_points_asset',None)
    try:
        if edna_asset:
            edna_fc=ee.FeatureCollection(edna_asset)
            biodiversity=(ee.Image().byte().paint(edna_fc,1)
                          .focal_max(radius=100,units='meters').unmask(0).clip(eg))
            hsas=ee.Image(1).subtract(suitability.subtract(biodiversity).abs()).clamp(0,1)
            val=_reduce(hsas,g,10)
            val['metadata']={'edna_points_used':True,'edna_asset':edna_asset}
            return val
        else:
            val=_reduce(suitability,g,10)
            val['metadata']={'edna_points_used':False,
                             'note':'No eDNA asset provided. Value = habitat suitability only, NOT true HSAS.'}
            return val
    except Exception as e: logger.warning(f"HSAS: {e}"); return {"value":None,"pixels":None}

def extract_edpp(g,c):
    import ee; eg=_to_ee(g)
    try:
        bands=_img_edpp_bands(c).clip(eg)
        lst=bands.select('LST'); tprot=bands.select('TurbProt')
        moisture=bands.select('Moisture'); exposure=bands.select('Exposure')
        stats=lst.reduceRegion(reducer=ee.Reducer.minMax(),geometry=eg,scale=30,maxPixels=1e13)
        mn=ee.Number(ee.Algorithms.If(stats.get('LST_min'),stats.get('LST_min'),0))
        mx=ee.Number(ee.Algorithms.If(stats.get('LST_max'),stats.get('LST_max'),1))
        thermal_stress=lst.subtract(mn).divide(mx.subtract(mn).max(1e-6)).clamp(0,1)
        edpp=(ee.Image(1).subtract(thermal_stress)
              .multiply(tprot).multiply(moisture)
              .multiply(ee.Image(1).subtract(exposure))
              .rename('EDPP').clamp(0,1))
        return _reduce(edpp,g,30)
    except Exception as e: logger.warning(f"EDPP: {e}"); return {"value":None,"pixels":None}

def extract_iri(g,c): return _reduce(_img_iri(c),g,10)

def extract_mspl(g,c):
    import ee; eg=_to_ee(g)
    try:
        bands=_img_mspl_bands(c).clip(eg)
        lst=bands.select('LST'); nutrient=bands.select('NutrientStress')
        turbidity=bands.select('TurbidityStress'); water_persist=bands.select('WaterPersist')
        stats=lst.reduceRegion(reducer=ee.Reducer.minMax(),geometry=eg,scale=30,maxPixels=1e13)
        mn=ee.Number(ee.Algorithms.If(stats.get('LST_min'),stats.get('LST_min'),0))
        mx=ee.Number(ee.Algorithms.If(stats.get('LST_max'),stats.get('LST_max'),1))
        thermal=lst.subtract(mn).divide(mx.subtract(mn).max(1e-6)).clamp(0,1).unmask(0)
        mspl=(nutrient.multiply(0.35).add(thermal.multiply(0.30))
              .add(turbidity.multiply(0.20)).add(water_persist.multiply(0.15))
              .rename('MSPL').clamp(0,1))
        return _reduce(mspl,g,20)
    except Exception as e: logger.warning(f"MSPL: {e}"); return {"value":None,"pixels":None}

def extract_rci(g,c):
    import ee; eg=_to_ee(g)
    try:
        y=c.ndvi_year; start=f"{y-1}-01-01"; end=f"{y}-12-31"
        def msk(img):
            qa=img.select('QA60'); mask=qa.bitwiseAnd(1<<10).eq(0).And(qa.bitwiseAnd(1<<11).eq(0))
            return img.updateMask(mask).divide(10000)
        s2=(ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
            .filterDate(start,end).filterBounds(eg).filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE',20)).map(msk))
        composite=s2.median().clip(eg)
        ndwi=composite.normalizedDifference(['B3','B8'])
        water_vec=ndwi.gt(0).selfMask().reduceToVectors(
            geometry=eg,scale=10,geometryType='polygon',eightConnected=True,maxPixels=1e13)
        water_geom=water_vec.geometry(1)
        outer=water_geom.buffer(100,1); riparian=outer.difference(water_geom.buffer(0,1),1)
        rci=_img_rci(c).clip(riparian)
        return _reduce(rci,riparian,10)
    except Exception as e: logger.warning(f"RCI: {e}"); return {"value":None,"pixels":None}


# ═══════════════════════════════════════════════════════════════════════════════
# EXTRACTION FUNCTIONS — TERRESTRIAL VEGETATION + PLANT SPECIES 
# ═══════════════════════════════════════════════════════════════════════════════

def extract_riparian_ndvi_trend(g,c):
    import ee; eg=_to_ee(g)
    try:
        y=c.ndvi_year
        def msk(img):
            qa=img.select('QA60'); mask=qa.bitwiseAnd(1<<10).eq(0).And(qa.bitwiseAnd(1<<11).eq(0))
            return img.updateMask(mask).divide(10000)
        s2=(ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
            .filterDate(f"{y-1}-01-01",f"{y}-12-31").filterBounds(eg)
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE',20)).map(msk))
        composite=s2.median().clip(eg)
        ndwi=composite.normalizedDifference(['B3','B8'])
        water_vec=ndwi.gt(0).selfMask().reduceToVectors(
            geometry=eg,scale=10,geometryType='polygon',maxPixels=1e13)
        water_geom=water_vec.geometry(1)
        outer=water_geom.buffer(100,1); riparian=outer.difference(water_geom.buffer(0,1),1)
        trend_img=_img_riparian_ndvi_trend(c).clip(riparian)
        return _reduce(trend_img,riparian,10)
    except Exception as e: logger.warning(f"riparian_ndvi_trend: {e}"); return {"value":None,"pixels":None}

def extract_jrc_water_persistence(g,c):
    import ee; eg=_to_ee(g)
    try:
        y=c.ndvi_year
        jrc=(ee.ImageCollection('JRC/GSW1_4/MonthlyHistory')
             .filterDate(f"{y-1}-01-01",f"{y}-12-31").filterBounds(eg))
        monthly_water=jrc.map(lambda img: img.select('water').eq(2).rename('Water')
                              .copyProperties(img,['system:time_start']))
        occurrence=monthly_water.mean().clip(eg)
        persistent=occurrence.gt(0.75)
        pa=ee.Image.pixelArea()
        persist_area=pa.updateMask(persistent).reduceRegion(
            reducer=ee.Reducer.sum(),geometry=eg,scale=30,maxPixels=1e13)
        total_area=pa.reduceRegion(reducer=ee.Reducer.sum(),geometry=eg,scale=30,maxPixels=1e13)
        val=ee.Number(persist_area.get('area')).divide(ee.Number(total_area.get('area')).max(1)).getInfo()
        return {"value":float(val),"pixels":None}
    except Exception as e: logger.warning(f"jrc_water_persistence: {e}"); return {"value":None,"pixels":None}

def extract_shdi(g,c):
    import ee; eg=_to_ee(g)
    try:
        y=c.ndvi_year
        def msk(img):
            qa=img.select('QA60'); mask=qa.bitwiseAnd(1<<10).eq(0).And(qa.bitwiseAnd(1<<11).eq(0))
            return img.updateMask(mask).divide(10000)
        s2=(ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
            .filterDate(f"{y}-01-01",f"{y}-12-31").filterBounds(eg)
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE',20)).map(msk))
        composite=s2.median().clip(eg)
        ndwi=composite.normalizedDifference(['B3','B8'])
        water_vec=ndwi.gt(0).selfMask().reduceToVectors(
            geometry=eg,scale=10,geometryType='polygon',eightConnected=True,maxPixels=1e13)
        with_area=water_vec.map(lambda f: f.set('area',f.geometry().area(1)))
        lake=ee.Feature(with_area.sort('area',False).first())
        lake_geom=lake.geometry()
        area=lake_geom.area(1); perim=lake_geom.perimeter(1)
        shdi=perim.divide(ee.Number(2).multiply(ee.Number(math.pi).multiply(area).sqrt()))
        return {"value":float(shdi.getInfo()),"pixels":None,
                "metadata":{"type":"scalar","note":"No spatial map for SHDI"}}
    except Exception as e: logger.warning(f"shdi: {e}"); return {"value":None,"pixels":None}

def extract_lai(g,c): return _reduce(_img_lai(c),g,500)
def extract_chm(g,c): return _reduce(_img_chm(c),g,25)

def extract_ivsi(g,c):
    import ee; eg=_to_ee(g)
    try:
        ivsi_img=_img_ivsi(c).clip(eg)
        pa=ee.Image.pixelArea()
        spread_area=pa.updateMask(ivsi_img).reduceRegion(
            reducer=ee.Reducer.sum(),geometry=eg,scale=10,maxPixels=1e13)
        total_area=pa.reduceRegion(reducer=ee.Reducer.sum(),geometry=eg,scale=10,maxPixels=1e13)
        val=ee.Number(spread_area.get('area')).divide(ee.Number(total_area.get('area')).max(1)).getInfo()
        return {"value":float(val),"pixels":None,
                "metadata":{"unit":"fraction of site with NDVI expansion > 0.2"}}
    except Exception as e: logger.warning(f"ivsi: {e}"); return {"value":None,"pixels":None}

def extract_endemic_plant_richness(g,c):
    import ee; eg=_to_ee(g); plants=None
    try: plants=ee.FeatureCollection(_PLANT_REDLIST)
    except Exception as e:
        logger.warning(f"endemic_plant_richness: cannot load asset: {e}")
        return {"value":None,"pixels":None}
    try:
        with_area=plants.map(lambda f: f.set('rk2',f.geometry().area().divide(1e6)))
        filtered=with_area.filter(ee.Filter.lt('rk2',100000)).filterBounds(eg).distinct('sci_name')
        n=filtered.size().getInfo()
        names=filtered.reduceColumns(ee.Reducer.toList(),['sci_name']).get('list').getInfo()
        return {"value":int(n) if n>0 else None,"pixels":None,
                "metadata":{"species_list":names or [],"range_threshold_km2":100000}}
    except Exception as e: logger.warning(f"endemic_plant_richness: {e}"); return {"value":None,"pixels":None}

def extract_threatened_plant_richness(g,c):
    import ee; eg=_to_ee(g); plants=None
    try: plants=ee.FeatureCollection(_PLANT_REDLIST)
    except Exception as e:
        logger.warning(f"threatened_plant_richness: cannot load asset: {e}")
        return {"value":None,"pixels":None}
    try:
        filtered=(plants.filter(ee.Filter.inList('category',['CR','EN','VU']))
                  .filter(ee.Filter.notNull(['sci_name'])).filterBounds(eg).distinct('sci_name'))
        n=filtered.size().getInfo()
        props=filtered.reduceColumns(ee.Reducer.toList(2),['sci_name','category']).get('list').getInfo()
        species_list=[{"name":row[0],"category":row[1]} for row in (props or []) if len(row)>=2]
        n_cr=sum(1 for s in species_list if s['category']=='CR')
        n_en=sum(1 for s in species_list if s['category']=='EN')
        n_vu=sum(1 for s in species_list if s['category']=='VU')
        return {"value":int(n) if n>0 else None,"pixels":None,
                "metadata":{"species_list":species_list,"n_CR":n_cr,"n_EN":n_en,"n_VU":n_vu}}
    except Exception as e: logger.warning(f"threatened_plant_richness: {e}"); return {"value":None,"pixels":None}
