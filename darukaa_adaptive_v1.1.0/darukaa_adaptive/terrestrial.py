"""Terrestrial EO core sharing the adaptive scoring contract."""
from __future__ import annotations
from .metrics import MetricResult

class TerrestrialMetrics:
    def __init__(self, config): self.config=config
    def _s2(self, geometry,start,end):
        import ee
        def mask(img):
            img=ee.Image(img); scl=img.select("SCL")
            good=scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))
            return img.updateMask(good).divide(10000).copyProperties(img,["system:time_start"])
        return ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(geometry).filterDate(start,end).filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE",self.config.temporal.max_cloud_pct)).map(mask)
    def _make(self,name,value,status,window,dataset,scale,direction,pillar,construct,subdimension,domain,reference_type,notes=""):
        return MetricResult(name,pillar,construct,subdimension,domain,value,
            {"natural_landcover_fraction":"fraction","terrestrial_ndvi":"NDVI","built_fraction":"fraction"}[name],status,window,dataset,scale,direction,"baseline",reference_type,True,False,
            1 if value is not None else 0,None,None,None,notes)
    def run(self,geometry,start,end):
        import ee
        s2=self._s2(geometry,start,end); n=int(s2.size().getInfo()); window=f"{start}:{end}"
        dw=ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(geometry).filterDate(start,end).select("label").mode()
        if n<1:
            vals=(None,None,None); status="insufficient_data"
        else:
            ndvi=s2.median().normalizedDifference(["B8","B4"]).rename("ndvi")
            v=ndvi.reduceRegion(ee.Reducer.mean(),geometry,scale=10,maxPixels=1e9,bestEffort=True).get("ndvi"); vals=(None if v is None else v.getInfo(),None,None); status="ok"
            natural=dw.eq(1).Or(dw.eq(2)).Or(dw.eq(3)).Or(dw.eq(5)).Or(dw.eq(7)).rename("fraction")
            built=dw.eq(6).rename("fraction")
            def mean(img):
                x=img.reduceRegion(ee.Reducer.mean(),geometry,scale=10,maxPixels=1e9,bestEffort=True).get("fraction"); return None if x is None else x.getInfo()
            vals=(mean(natural),vals[0],mean(built))
        return [
            self._make("natural_landcover_fraction",vals[0],status,window,"Dynamic World",10,"higher_is_better","C1_extent","habitat_extent","natural_cover","master_boundary","regional_or_matched","Natural/semi-natural land-cover fraction; EO screening proxy."),
            self._make("terrestrial_ndvi",vals[1],status,window,"Sentinel-2 SR Harmonized",10,"higher_is_better","C2_vegetation","vegetation","greenness","master_boundary","regional_or_matched","NDVI is a vegetation-condition proxy, not a biodiversity observation."),
            self._make("built_fraction",vals[2],status,window,"Dynamic World",10,"lower_is_better","C4_pressure","pressure","built_up","master_boundary","regional_or_matched","Built-up fraction is a land-use pressure proxy.")
        ]
