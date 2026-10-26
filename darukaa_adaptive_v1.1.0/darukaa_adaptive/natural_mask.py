"""Natural / managed classification shared by P1, P2 and the managed-land result.

Order of evidence (metric catalogue v1, "Natural mask"):

1. Nature Trace Forest Typology 2020 (10 m) decides tree cover: argmax class 1
   (primary) or 2 (naturally regenerating) is natural forest; 3-5 (planted,
   plantation, tree crops) is managed. Primary and naturally regenerating are
   merged because the split is unreliable in Asia (preprint Tables 23-24).
2. Where ForTy's argmax is 6 ("other land"), SBTN Natural Lands v1.1 2020 (30 m)
   ``natural`` decides.
3. Dynamic World (10 m) modal label in the assessment window records conversion of
   2020-natural land to crops or built (gross loss) and candidate gain; it never
   promotes a pixel to natural on its own.
4. A pixel is ``uncertain`` (excluded from natural and managed areas, reported
   separately) when ForTy's winning probability is below ``min_probability`` or when
   ForTy and SBTN disagree.

Stratum codes (reference stratification and per-type reporting)
  natural: 10 natural_forest, 11 woodland, 12 shrub, 13 grass, 14 wetland,
           15 water, 16 bare, 17 other_natural
  managed: 21 planted_or_tree_crops, 22 cropland, 23 built, 24 other_managed
"""
from __future__ import annotations

from typing import Dict

from .ee_utils import ee_module

FORTY_ASSET = "projects/nature-trace/assets/forest_typology/forest_typology_2020_v1_0_collection"
FORTY_BANDS = ["PrimaryForest", "NaturallyRegeneratingForest", "PlantedForest", "PlantationForest", "TreeCropsAndAgroforestry"]
SBTN_ASSET = "WRI/SBTN/naturalLands/v1_1/2020"
DW_ASSET = "GOOGLE/DYNAMICWORLD/V1"

DW = {"water": 0, "trees": 1, "grass": 2, "flooded_vegetation": 3, "crops": 4, "shrub_and_scrub": 5, "built": 6, "bare": 7, "snow_and_ice": 8}

STRATA: Dict[int, str] = {
    10: "natural_forest", 11: "woodland", 12: "shrub", 13: "grass", 14: "wetland", 15: "water", 16: "bare", 17: "other_natural",
    21: "planted_or_tree_crops", 22: "cropland", 23: "built", 24: "other_managed",
}
NATURAL_STRATA = (10, 11, 12, 13, 14, 15, 16, 17)
MANAGED_STRATA = (21, 22, 23, 24)
WOODY_STRATA = (10, 11, 12)
VEGETATED_STRATA = (10, 11, 12, 13, 14)   # vegetation-condition metrics do not apply to water, bare or other
TYPE_TO_STRATA = {"natural_forest": (10,), "woodland": (11,), "shrub": (12,), "grass": (13,), "wetland": (14,),
                  "water": (15,), "bare": (16,)}


def dw_mode(region, start: str, end_exclusive: str):
    ee = ee_module()
    col = ee.ImageCollection(DW_ASSET).filterBounds(region).filterDate(start, end_exclusive).select("label")
    return col.mode().rename("dw_label"), col.size()


def forty_class(region):
    """(class 1-6, winning probability 0-1) from the ForTy probability bands."""
    ee = ee_module()
    col = ee.ImageCollection(FORTY_ASSET).filterBounds(region)
    img = col.mosaic().select(FORTY_BANDS)
    valid = img.reduce(ee.Reducer.max()).lt(255)
    other = ee.Image.constant(250).subtract(img.reduce(ee.Reducer.sum())).max(0).rename("Other")
    probs = img.addBands(other)
    cls = probs.toArray().arrayArgmax().arrayGet([0]).add(1).rename("forty_class")
    maxp = probs.reduce(ee.Reducer.max()).divide(250).rename("forty_maxp")
    return cls.updateMask(valid), maxp.updateMask(valid)


def build_mask(region, start: str, end_exclusive: str, min_probability: float = 0.5, crs: str = None):
    """Return (image with mask bands, lazy DW image count).

    The mask is built from composites, which have no fixed projection (EE treats
    them as WGS84 at 1 degree). It is therefore pinned to ``crs`` at 10 m so that
    later aggregation (reduceResolution) works on 10 m pixels, not 1-degree ones.
    """
    ee = ee_module()
    fcls_m, fmaxp_m = forty_class(region)
    # Masked inputs are made explicit (0 / -1) so every logical test below is defined
    # everywhere; "no data" is then handled as its own case, never as a class.
    fcls = fcls_m.unmask(0)
    fmaxp = fmaxp_m.unmask(0)
    sbtn = ee.Image(SBTN_ASSET)
    sbtn_nat = sbtn.select("natural").unmask(-1)
    sbtn_cls = sbtn.select("classification")
    label, dw_count = dw_mode(region, start, end_exclusive)

    has_forty = fcls.gt(0)
    forty_nat = fcls.gte(1).And(fcls.lte(2))
    forty_man = fcls.gte(3).And(fcls.lte(5))
    forty_other = fcls.eq(6)
    nat2020 = (ee.Image(0)
               .where(has_forty.And(forty_nat), 1)
               .where(has_forty.And(forty_other).And(sbtn_nat.eq(1)), 1)
               .where(has_forty.Not().And(sbtn_nat.eq(1)), 1))
    uncertain = (ee.Image(0)
                 .where(has_forty.And(fmaxp.lt(min_probability)), 1)
                 .where(has_forty.And(forty_nat).And(sbtn_nat.eq(0)), 1)
                 .where(has_forty.And(forty_man).And(sbtn_nat.eq(1)), 1)
                 .where(has_forty.Not().And(sbtn_nat.eq(-1)), 1)
                 .where(forty_other.And(sbtn_nat.eq(-1)), 1))
    certain = uncertain.eq(0)
    converted = label.eq(DW["crops"]).Or(label.eq(DW["built"]))
    natural_now = nat2020.And(certain).And(converted.Not())
    loss = nat2020.And(certain).And(converted)
    gain_candidate = (nat2020.eq(0).And(certain).And(forty_man.Not())
                      .And(label.eq(DW["water"]).Or(label.eq(DW["trees"])).Or(label.eq(DW["grass"]))
                           .Or(label.eq(DW["flooded_vegetation"])).Or(label.eq(DW["shrub_and_scrub"]))))
    managed = certain.And(natural_now.Not())

    nat_stratum = (ee.Image(17)
                   .where(label.eq(DW["trees"]), 11).where(label.eq(DW["shrub_and_scrub"]), 12)
                   .where(label.eq(DW["grass"]), 13).where(label.eq(DW["flooded_vegetation"]), 14)
                   .where(label.eq(DW["water"]), 15).where(label.eq(DW["bare"]), 16)
                   .where(has_forty.And(forty_nat), 10))
    man_stratum = (ee.Image(24).where(label.eq(DW["crops"]), 22).where(label.eq(DW["built"]), 23)
                   .where(has_forty.And(forty_man), 21))
    stratum = ee.Image(0).where(natural_now, nat_stratum).where(managed, man_stratum)

    bands = ee.Image.cat([
        nat2020.rename("natural_2020"), natural_now.rename("natural_now"), loss.rename("loss"),
        gain_candidate.rename("gain_candidate"), managed.rename("managed"), uncertain.rename("uncertain"),
        stratum.rename("stratum"), label.rename("dw_label"), sbtn_cls.rename("sbtn_class"),
    ]).updateMask(label.mask())
    if crs is None:
        raise ValueError("build_mask needs a metric CRS (e.g. the site's UTM zone)")
    return bands.setDefaultProjection(crs=crs, scale=10), dw_count
