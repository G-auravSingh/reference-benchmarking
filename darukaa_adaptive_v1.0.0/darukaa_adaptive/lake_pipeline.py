from __future__ import annotations
import json, os, logging
from pathlib import Path
import pandas as pd
import ee
from .config import LakeConfig
from .geometry import load_kml, to_ee_geometry, area_ha
from .characterize import characterize, infer_project_type
from . import lake_metrics
from .water import annual_water_occurrence
from .scoring import protocol_a, LABELS, son_score

log=logging.getLogger(__name__)

class LakePipeline:
    """Automated lake profile: KML is the only spatial input; secondary domains are derived in GEE."""
    def __init__(self, config: LakeConfig):
        self.config=config

    def run(self, site_path: str, output_dir: str|None=None):
        out=Path(output_dir or self.config.output_dir); out.mkdir(parents=True,exist_ok=True)
        geom=load_kml(site_path); ee_geom=to_ee_geometry(geom)
        local_area=area_ha(geom)
        ch=characterize(ee_geom,self.config)
        inferred=infer_project_type(ch)
        if inferred!='aquatic_lake':
            raise ValueError('Lake profile did not detect an aquatic signal in the supplied KML. Use the generic/terrestrial profile or inspect characterization.json.')
        metrics=[]
        def add(name, display, value, unit='', domain='', status='computed', notes=''):
            score=protocol_a(name,value)
            metrics.append({'indicator_name':name,'display_name':display,'site_value':value,'unit':unit,'spatial_domain':domain,'status':status,'concern_numeric':score,'concern_label':LABELS.get(score,'—'),'notes':notes})
        # Water extent
        try:
            r=lake_metrics.water_extent(ee_geom,self.config)
            add('water_extent','Mean annual water extent',r.get('value'),'fraction','dynamic water','computed','Mean fraction of fixed KML classified as water across valid S2/DW observations.')
        except Exception as e: add('water_extent','Mean annual water extent',None,'fraction','dynamic water','failed',str(e))
        for name,func,display,unit,domain in [
            ('tspi',lake_metrics.tspi,'Trophic State Proxy Index (NDCI)','index','dynamic water'),
            ('sabf',lake_metrics.sabf,'Surface Algal Bloom Frequency','fraction','dynamic water'),
            ('wcpi',lake_metrics.wcpi,'Water Clarity Proxy Index','index','dynamic water'),
            ('wsdi',lake_metrics.wsdi,'Water Surface Dynamics Index','index','fixed KML + dynamic water'),
            ('rci',lake_metrics.rci,'Riparian Complexity Index','index','fixed external riparian buffer'),
        ]:
            try:
                value,pixels=func(ee_geom,self.config)
                add(name,display,value,unit,domain,'computed',f'Valid pixels: {pixels}')
            except Exception as e: add(name,display,None,unit,domain,'failed',str(e))
        try:
            value,n=lake_metrics.riparian_ndvi_trend(ee_geom,self.config)
            add('riparian_ndvi_trend','Riparian NDVI temporal trend',value,'NDVI/year','fixed external riparian buffer','computed',f'Annual observations used: {n}')
        except Exception as e: add('riparian_ndvi_trend','Riparian NDVI temporal trend',None,'NDVI/year','fixed external riparian buffer','failed',str(e))
        try:
            value,meta=lake_metrics.shdi(ee_geom,self.config)
            add('shdi','Shoreline Development Index',value,'index','derived water shoreline','descriptive_only',meta.get('note',''))
        except Exception as e: add('shdi','Shoreline Development Index',None,'index','derived water shoreline','failed',str(e))
        # Water persistence is intentionally separated from JRC because JRC v1.4 ends in 2021.
        try:
            occ=lake_metrics.annual_water_occurrence(ee_geom,self.config.assessment_year,self.config.dw_water_probability) if hasattr(lake_metrics,'annual_water_occurrence') else None
            if occ:
                value=occ.gt(0.75).reduceRegion(ee.Reducer.mean(),ee_geom,10,maxPixels=1e9).get('water_occurrence').getInfo()
                add('water_persistence','Current-year high-persistence water fraction',value,'fraction','fixed KML + dynamic water','computed','Derived from Dynamic World; not the historical JRC product.')
        except Exception as e: add('water_persistence','Current-year high-persistence water fraction',None,'fraction','fixed KML + dynamic water','failed',str(e))
        # Species context uses the supplied legacy package only when explicitly enabled; no local presence is inferred.
        if self.config.include_species_context:
            for name in ('threatened_richness','endemic_richness','ceri','star_t'):
                metrics.append({'indicator_name':name,'display_name':name.replace('_',' ').title(),'site_value':None,'unit':'','spatial_domain':'species range context','status':'not_run','concern_numeric':None,'concern_label':'—','notes':'Not inferred from EO alone; retain as optional contextual indicators using the legacy species-range assets.'})
        df=pd.DataFrame(metrics)
        # Only condition metrics with explicit compatibility thresholds contribute to the provisional lake SoN.
        son_names=['tspi','sabf','wcpi','wsdi','rci','riparian_ndvi_trend']
        scores=[row.concern_numeric for row in df.itertuples() if row.indicator_name in son_names and row.concern_numeric is not None]
        score=son_score(scores)
        result={
            'framework_version':'Darukaa Adaptive Ecosystem Assessment v1.0.0',
            'profile':'aquatic_lake',
            'site_file':str(site_path),
            'site_area_ha_local':local_area,
            'characterization':ch,
            'inferred_project_type':inferred,
            'riparian_buffer_m':self.config.riparian_buffer_m,
            'assessment_year':self.config.assessment_year,
            'metrics':metrics,
            'son':{'score':score,'n_metrics_used':len(scores),'status':'PROVISIONAL — uses compatibility thresholds inherited from the supplied Nandoshi methodology; aquatic benchmark validation is a separate QA step.'},
            'limitations':[
                'No manual water polygon is required; water is derived automatically from Dynamic World probability and Sentinel-2 joins.',
                'The supplied KML remains the fixed assessment boundary.',
                'Exposed lakebed is not automatically treated as terrestrial habitat.',
                'SHDI is descriptive and excluded from SoN by default.',
                'Species range-overlap indicators are not treated as confirmed local occurrence.',
                'JRC Global Surface Water v1.4 is historical through 2021; current-year water persistence uses Dynamic World instead.'
            ]
        }
        df.to_csv(out/'lake_scorecard.csv',index=False)
        (out/'characterization.json').write_text(json.dumps(ch,indent=2,default=str))
        (out/'lake_run_manifest.json').write_text(json.dumps(result,indent=2,default=str))
        return result
