from __future__ import annotations
import ee

DW = "GOOGLE/DYNAMICWORLD/V1"
S2 = "COPERNICUS/S2_SR_HARMONIZED"
JRC = "JRC/GSW1_4/GlobalSurfaceWater"


def dw_collection(geometry, year):
    return (ee.ImageCollection(DW)
            .filterBounds(geometry)
            .filterDate(f"{year}-01-01", f"{year+1}-01-01"))


def water_mask_from_dw(img, probability=0.5):
    # Dynamic World water probability is preferred over a hard label alone.
    return img.select("water").gte(probability).rename("water")


def annual_water_occurrence(geometry, year, probability=0.5):
    col = dw_collection(geometry, year).map(
        lambda i: water_mask_from_dw(i, probability).copyProperties(i, ["system:time_start"])
    )
    return col.mean().rename("water_occurrence")


def annual_water_fraction(geometry, year, probability=0.5):
    occ = annual_water_occurrence(geometry, year, probability)
    stats = occ.gte(0).multiply(ee.Image.pixelArea()).reduceRegion(
        reducer=ee.Reducer.sum(), geometry=geometry, scale=10, maxPixels=1e9
    )
    # The numerator is the mean water fraction integrated over the fixed site.
    val = occ.multiply(ee.Image.pixelArea()).reduceRegion(
        reducer=ee.Reducer.sum(), geometry=geometry, scale=10, maxPixels=1e9
    ).get("water_occurrence")
    area = ee.Image.pixelArea().reduceRegion(
        reducer=ee.Reducer.sum(), geometry=geometry, scale=10, maxPixels=1e9
    ).get("area")
    return ee.Number(val).divide(ee.Number(area).max(1))


def per_image_water_s2_join(geometry, year, probability=0.5):
    """Join S2 SR images to matching Dynamic World images by system:index."""
    s2 = (ee.ImageCollection(S2).filterBounds(geometry)
          .filterDate(f"{year}-01-01", f"{year+1}-01-01")
          .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", 35)))
    dw = dw_collection(geometry, year)
    joined = ee.Join.inner().apply(
        primary=s2, secondary=dw,
        condition=ee.Filter.equals(leftField="system:index", rightField="system:index")
    )
    def merge(pair):
        s = ee.Image(pair.get("primary"))
        d = ee.Image(pair.get("secondary"))
        return s.addBands(d.select(["water"], ["DW_water_prob"]))
    return ee.ImageCollection(joined.map(merge))


def jrc_historical_occurrence(geometry):
    """Static 1984-2021 JRC surface-water occurrence, when coverage exists."""
    return ee.Image(JRC).select("occurrence").clip(geometry)
