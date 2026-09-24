from __future__ import annotations
import ee
from .water import dw_collection, annual_water_occurrence, jrc_historical_occurrence


def characterize(geom, cfg):
    area_img=ee.Image.pixelArea()
    area_m2=area_img.reduceRegion(ee.Reducer.sum(),geom,10,maxPixels=1e9).get('area')
    dw=dw_collection(geom,cfg.assessment_year)
    # Annual modal land-cover composition from Dynamic World labels.
    mode=dw.select('label').mode()
    hist=jrc_historical_occurrence(geom)
    hist_occ=hist.reduceRegion(ee.Reducer.mean(),geom,30,maxPixels=1e9).get('occurrence')
    water_occ=annual_water_occurrence(geom,cfg.assessment_year,cfg.dw_water_probability)
    water_mean=water_occ.reduceRegion(ee.Reducer.mean(),geom,10,maxPixels=1e9).get('water_occurrence')
    water_max=dw.select('water').max().reduceRegion(ee.Reducer.mean(),geom,10,maxPixels=1e9).get('water')
    label_stats=mode.reduceRegion(ee.Reducer.frequencyHistogram(),geom,10,maxPixels=1e9).get('label')
    return {
        'site_area_ha': ee.Number(area_m2).divide(10000).getInfo(),
        'historical_jrc_mean_occurrence_pct': hist_occ.getInfo() if hist_occ else None,
        'annual_mean_water_occurrence': water_mean.getInfo() if water_mean else None,
        'annual_max_water_probability_fraction': water_max.getInfo() if water_max else None,
        'dynamic_world_modal_class_histogram': label_stats.getInfo() if label_stats else {},
    }


def infer_project_type(ch, aquatic_water_occurrence_threshold=0.10, aquatic_hist_occurrence_threshold=10.0):
    current=ch.get('annual_max_water_probability_fraction') or 0
    hist=ch.get('historical_jrc_mean_occurrence_pct') or 0
    if current >= aquatic_water_occurrence_threshold or hist >= aquatic_hist_occurrence_threshold:
        return 'aquatic_lake'
    return 'terrestrial'
