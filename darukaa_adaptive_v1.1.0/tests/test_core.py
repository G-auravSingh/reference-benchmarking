import tempfile
from pathlib import Path
from types import SimpleNamespace
import pandas as pd
from shapely.geometry import Polygon
from darukaa_adaptive.benchmark import benchmark_metric, benchmark_observation, intactness_ratio, percent_change
from darukaa_adaptive.config import AssessmentConfig
from darukaa_adaptive.evidence import load_evidence_csv
from darukaa_adaptive.periods import annual_periods, month_periods
from darukaa_adaptive.registry import AQUATIC_INDICATORS, TERRESTRIAL_INDICATORS, PILLARS, indicator_table
from darukaa_adaptive.site import area_ha, make_shapely_domains, read_kml, validate_site_geometry
from darukaa_adaptive.scoring import aggregate_overall, aggregate_pillars, concern_label, geometric_mean, build_scorecard, score_external_observations
from darukaa_adaptive.trajectory import compare

def test_ratio_and_percent_change():
    assert intactness_ratio(80,100,True)==0.8
    assert round(percent_change(110,100),6)==10.0

def test_reference_target():
    r=benchmark_observation('water_extent',40,50,'reference_target'); assert r.intactness_score_0_100==80

def test_fixed_bands():
    assert concern_label(0)=='Very High'; assert concern_label(20)=='High'; assert concern_label(40)=='Moderate'; assert concern_label(60)=='Low'; assert concern_label(80)=='Very Low'

def test_geomean(): assert abs(geometric_mean([25,100])-50.0)<1e-9

def test_condition_pressure_are_separate():
    cfg=AssessmentConfig(); scored=pd.DataFrame([
      {'metric':'a','pillar':'P1_extent_configuration','intactness_score_0_100':90,'score_eligible':True},
      {'metric':'b','pillar':'P2_ecosystem_condition','intactness_score_0_100':80,'score_eligible':True},
      {'metric':'c','pillar':'P3_biodiversity_integrity','intactness_score_0_100':70,'score_eligible':True},
      {'metric':'p','pillar':'P4_pressure','intactness_score_0_100':20,'score_eligible':True}])
    p=aggregate_pillars(scored,cfg); o=aggregate_overall(p,cfg)
    assert abs(o['condition_score_0_to_100']-geometric_mean([90,80,70]))<1e-9; assert abs(o['pressure_score_0_to_100']-20)<1e-9
    assert o['son_score_0_to_100'] is None

def test_condition_requires_fauna_when_profile_requires_it():
    cfg=AssessmentConfig()
    cfg.scoring.require_fauna_for_condition=True
    scored=pd.DataFrame([
      {'metric':'a','pillar':'P1_extent_configuration','intactness_score_0_100':90,'score_eligible':True},
      {'metric':'b','pillar':'P2_ecosystem_condition','intactness_score_0_100':80,'score_eligible':True},
      {'metric':'p','pillar':'P4_pressure','intactness_score_0_100':70,'score_eligible':True}])
    p=aggregate_pillars(scored,cfg); o=aggregate_overall(p,cfg)
    assert o['condition_score_0_to_100'] is None
    assert o['status']=='insufficient_fauna_coverage'


def test_external_evidence_same_path():
    cfg=AssessmentConfig(); df=pd.DataFrame([{'metric':'edna_fish_richness','pillar':'P3_biodiversity_integrity','raw_value':8,'direction':'higher_is_better','reference_value':10,'reference_approved_for_scoring':True,'evidence_type':'eDNA'}])
    m,p,o=score_external_observations(df,cfg); assert float(m.iloc[0].intactness_score_0_100)==80; assert m.iloc[0].evidence_type=='eDNA'

def test_geometry_and_kml():
    poly=Polygon([(74,17.5),(74.001,17.5),(74.001,17.501),(74,17.501)])
    assert area_ha(poly)>0; assert validate_site_geometry(poly)['valid']; d=make_shapely_domains(poly,100,1); assert d['context'].area>d['riparian_fixed'].area
    text='<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark><name>N</name><Polygon><outerBoundaryIs><LinearRing><coordinates>74,17,0 74.001,17,0 74.001,17.001,0 74,17,0 74,17,0</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></Document></kml>'
    with tempfile.TemporaryDirectory() as td:
      p=Path(td)/'x.kml'; p.write_text(text); g,parts=read_kml(p); assert g.area>0 and parts

def test_config_dates_and_validation():
    c=AssessmentConfig(); assert c.temporal.baseline_dates()==('2025-08-01','2026-09-01'); assert c.validate()==[]

def test_periods():
    assert len(month_periods('2025-08-01','2026-08-31'))==13; assert len(annual_periods(2018,2026))==9

def test_registry_count():
    assert set(PILLARS)=={'P1_extent_configuration','P2_ecosystem_condition','P3_biodiversity_integrity','P4_pressure'}; assert {'water_extent','edna_fish_richness'}.issubset({x.name for x in AQUATIC_INDICATORS}) and 'built_fraction' in {x.name for x in TERRESTRIAL_INDICATORS}; assert len(indicator_table())>=len(AQUATIC_INDICATORS)+len(TERRESTRIAL_INDICATORS)

def test_evidence_csv(tmp_path):
    p=tmp_path/'e.csv'; pd.DataFrame([{'metric':'edna_fish_richness','raw_value':8,'pillar':'P3_biodiversity_integrity','direction':'higher_is_better'}]).to_csv(p,index=False); d=load_evidence_csv(p); assert d.iloc[0]['evidence_type']=='external'

def test_trajectory(tmp_path):
    base=pd.DataFrame([{'metric':'x','value':10,'units':'u','direction':'higher_is_better','temporal_window':'same','status':'ok'}]); cur=base.copy(); cur.loc[0,'value']=12
    bp=tmp_path/'b.csv'; cp=tmp_path/'c.csv'; base.to_csv(bp,index=False); cur.to_csv(cp,index=False); r=compare(cp,bp); assert r.loc[0,'delta']==2
