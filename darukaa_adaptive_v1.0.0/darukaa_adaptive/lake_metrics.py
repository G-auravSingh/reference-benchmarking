from __future__ import annotations
import ee
from .water import per_image_water_s2_join, annual_water_occurrence


def _reduce_mean(img, geom, scale=10):
    d = img.reduceRegion(ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True), geom, scale, maxPixels=1e9)
    info = d.getInfo()
    return {"value": info.get(img.bandNames().getInfo()[0]), "pixels": info.get("count")}


def _mean(img, geom, scale=10):
    band = img.bandNames().get(0).getInfo()
    d = img.reduceRegion(ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True), geom, scale, maxPixels=1e9).getInfo()
    return d.get(band), d.get("count")


def water_extent(geom, cfg):
    occ = annual_water_occurrence(geom, cfg.assessment_year, cfg.dw_water_probability)
    # Water extent is reported for each valid observation and summarized as mean/max/min fraction.
    col = per_image_water_s2_join(geom, cfg.assessment_year, cfg.dw_water_probability)
    def frac(i):
        w = i.select("DW_water_prob").gte(cfg.dw_water_probability)
        return ee.Image.pixelArea().updateMask(w).reduceRegion(
            ee.Reducer.sum(), geom, 10, maxPixels=1e9
        ).get("area")
    vals = col.map(lambda i: ee.Feature(None, {"area": frac(i)})).aggregate_array("area")
    total = ee.Image.pixelArea().reduceRegion(ee.Reducer.sum(), geom, 10, maxPixels=1e9).get("area")
    arr = ee.List(vals).removeAll([None])
    return {
        "value": ee.Number(arr.reduce(ee.Reducer.mean())).divide(total).getInfo() if arr.size().getInfo() else None,
        "metadata": {"mean_water_fraction": "see water_extent_timeseries.csv", "n_valid_images": arr.size().getInfo()}
    }


def tspi(geom, cfg):
    col = per_image_water_s2_join(geom, cfg.assessment_year, cfg.dw_water_probability)
    def f(i):
        water = i.select("DW_water_prob").gte(cfg.dw_water_probability)
        ndci = i.normalizedDifference(["B5", "B4"]).rename("TSPI").updateMask(water)
        return ndci
    img = col.map(f).median().clip(geom)
    return _mean(img, geom, 10)


def sabf(geom, cfg):
    col = per_image_water_s2_join(geom, cfg.assessment_year, cfg.dw_water_probability)
    def bloom(i):
        w = i.select("DW_water_prob").gte(cfg.dw_water_probability)
        red=i.select("B4"); nir=i.select("B8"); swir=i.select("B11")
        baseline=red.add(swir.subtract(red).multiply((842-665)/(1610-665)))
        fai=nir.subtract(baseline)
        return fai.gt(0.005).updateMask(w).rename("Bloom")
    b = col.map(bloom)
    freq = b.sum().divide(b.count()).rename("SABF")
    return _mean(freq, geom, 10)


def wcpi(geom, cfg):
    col = per_image_water_s2_join(geom, cfg.assessment_year, cfg.dw_water_probability)
    def f(i):
        w=i.select("DW_water_prob").gte(cfg.dw_water_probability)
        red=i.select("B4")
        tsm=red.expression('(228.1*r)/(1-(r/0.1641))', {'r':red}).rename('TSM')
        return ee.Image(1).divide(tsm.add(1)).updateMask(w).rename('WCPI')
    img=col.map(f).median().clip(geom)
    return _mean(img, geom, 10)


def wsdi(geom, cfg):
    occ=annual_water_occurrence(geom, cfg.assessment_year, cfg.dw_water_probability)
    wsdi=ee.Image(1).subtract(occ.subtract(0.5).abs().multiply(2)).rename("WSDI")
    return _mean(wsdi, geom, 10)


def riparian_geometry(geom, buffer_m):
    return geom.buffer(buffer_m, 1).difference(geom.buffer(0,1), 1)


def riparian_ndvi_trend(geom, cfg):
    years=list(range(cfg.baseline_start_year, cfg.baseline_end_year+1))
    rip=riparian_geometry(geom, cfg.riparian_buffer_m)
    vals=[]
    for y in years:
        s2=(ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(rip)
            .filterDate(f"{y}-01-01",f"{y+1}-01-01")
            .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", cfg.s2_cloud_pct)))
        def nd(i):
            scl=i.select("SCL")
            mask=scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))
            return i.updateMask(mask).normalizedDifference(["B8","B4"]).rename("NDVI")
        med=s2.map(nd).median()
        v=med.reduceRegion(ee.Reducer.mean(), rip, 10, maxPixels=1e9).get("NDVI")
        vals.append(ee.Feature(None, {"year": y, "ndvi": v}))
    fc=ee.FeatureCollection(vals).filter(ee.Filter.notNull(["ndvi"]))
    fit=fc.reduceColumns(ee.Reducer.linearFit(), ["year","ndvi"]).getInfo()
    return fit.get("scale"), fc.size().getInfo()


def rci(geom, cfg):
    rip=riparian_geometry(geom, cfg.riparian_buffer_m)
    y=cfg.assessment_year
    s2=(ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(rip)
        .filterDate(f"{y-1}-01-01",f"{y+1}-01-01")
        .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE",cfg.s2_cloud_pct)))
    def clean(i):
        scl=i.select("SCL")
        m=scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))
        return i.updateMask(m).divide(10000)
    c=s2.map(clean).median()
    ndvi=c.normalizedDifference(["B8","B4"])
    evi=c.expression('2.5*((NIR-RED)/(NIR+6*RED-7.5*BLUE+1))',{'NIR':c.select('B8'),'RED':c.select('B4'),'BLUE':c.select('B2')})
    ndvi_std=s2.map(lambda i: i.normalizedDifference(['B8','B4']).rename('NDVI')).reduce(ee.Reducer.stdDev())
    score=(ndvi_std.unitScale(0,0.2).clamp(0,1).multiply(0.30)
           .add(evi.unitScale(0,1).clamp(0,1).multiply(0.30))
           .add(ndvi.unitScale(0,1).clamp(0,1).multiply(0.20))
           .add(ndvi.reduceNeighborhood(ee.Reducer.stdDev(), ee.Kernel.circle(30,'meters')).unitScale(0,0.15).clamp(0,1).multiply(0.20))
           .rename('RCI'))
    return _mean(score, rip, 10)


def shdi(geom, cfg):
    # Descriptive only. Uses the largest water component from the annual high-water composite.
    occ=annual_water_occurrence(geom, cfg.assessment_year, cfg.dw_water_probability)
    water=occ.gte(0.25).selfMask()
    vec=water.reduceToVectors(geometry=geom,scale=10,geometryType='polygon',eightConnected=True,maxPixels=1e9)
    largest=ee.Feature(vec.sort('system:area',False).first()).geometry()
    area=largest.area(1); per=largest.perimeter(1)
    val=per.divide(2*3.141592653589793*ee.Number(area).sqrt()).getInfo()
    return val, {"note":"Descriptive shoreline geometry metric; excluded from SoN by default."}
