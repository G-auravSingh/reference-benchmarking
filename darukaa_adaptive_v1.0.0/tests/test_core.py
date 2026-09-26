import tempfile
from pathlib import Path

import pandas as pd
from shapely.geometry import Polygon

from darukaa_adaptive.benchmark import benchmark_from_values
from darukaa_adaptive.config import AssessmentConfig
from darukaa_adaptive.metrics import MetricResult
from darukaa_adaptive.periods import month_periods
from darukaa_adaptive.registry import PILLARS, get_indicator_spec
from darukaa_adaptive.scoring import aggregate_overall, aggregate_pillars, concern_label, geometric_mean
from darukaa_adaptive.site import area_ha, make_shapely_domains, read_kml, validate_site_geometry


def test_four_pillars():
    assert list(PILLARS) == ["C1_extent", "C2_vegetation", "C3_fauna", "C4_pressure"]


def test_concern_bands_and_geomean():
    assert concern_label(80) == "Very Low"
    assert concern_label(60) == "Low"
    assert concern_label(40) == "Moderate"
    assert concern_label(20) == "High"
    assert concern_label(19.999) == "Very High"
    assert round(geometric_mean([25, 50, 100]), 6) == round(50, 6)


def test_reference_benchmark_is_centered_at_50():
    cfg=AssessmentConfig()
    b=benchmark_from_values("water_persistence", 0.5, [0.5]*8, cfg, "regional_aquatic", "test")
    # Zero dispersion makes robust estimator undefined for bounded metrics, but ratio scale is valid.
    assert b.intactness_score_0_100 is not None
    assert abs(b.intactness_score_0_100 - 50) < 1e-9
    assert b.reference_approved_for_scoring is False or b.reference_n == 8


def test_bounded_reference_can_score_with_dispersion():
    cfg=AssessmentConfig()
    vals=[0.03,0.04,0.05,0.06,0.07,0.08,0.09,0.10]
    b=benchmark_from_values("ndci_proxy", 0.05, vals, cfg, "regional_aquatic", "test")
    assert b.signed_benchmark is not None
    assert 0 <= b.intactness_score_0_100 <= 100


def test_pillar_and_overall_geomean():
    cfg=AssessmentConfig()
    df=pd.DataFrame([
        {"metric":"a","pillar":"C1_extent","intactness_score_0_100":60,"score_eligible":True},
        {"metric":"b","pillar":"C2_vegetation","intactness_score_0_100":60,"score_eligible":True},
        {"metric":"c","pillar":"C3_fauna","intactness_score_0_100":60,"score_eligible":True},
        {"metric":"d","pillar":"C4_pressure","intactness_score_0_100":60,"score_eligible":True},
    ])
    p=aggregate_pillars(df,cfg)
    o=aggregate_overall(p,cfg)
    assert (p["score_0_to_100"].sub(60).abs() < 1e-9).all()
    assert abs(o["overall_son_score_0_to_100"]-60)<1e-9
    assert o["overall_son_concern"]=="Low"


def test_config_and_periods():
    cfg=AssessmentConfig.from_yaml("profiles/mixed_lake.yaml")
    assert cfg.validate()==[]
    assert cfg.reference.strategy=="auto_ecoregion_stratum"
    assert cfg.profile.aquatic_enabled and cfg.profile.terrestrial_enabled
    assert len(month_periods(*cfg.temporal.baseline_inclusive_window()))==13


def test_domains():
    poly=Polygon([(74,17.5),(74.001,17.5),(74.001,17.501),(74,17.501)])
    assert validate_site_geometry(poly)["valid"]
    d=make_shapely_domains(poly,100,5,50)
    assert d["riparian_fixed"].area>0 and d["littoral_band"].area>0 and d["context"].area>d["riparian_fixed"].area
    assert area_ha(poly)>0


def test_kml_fallback():
    text='''<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark><name>Nandoshi</name><Polygon><outerBoundaryIs><LinearRing><coordinates>74,17,0 74.001,17,0 74.001,17.001,0 74,17.001,0 74,17,0</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></Document></kml>'''
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/"x.kml"; p.write_text(text)
        geom,parts=read_kml(p)
        assert geom.area>0 and parts


def test_registry_assignment():
    assert get_indicator_spec("water_extent").pillar=="C1_extent"
    assert get_indicator_spec("ndci_proxy").pillar=="C2_vegetation"
    assert get_indicator_spec("red_reflectance_turbidity_proxy").pillar=="C2_vegetation"
    assert get_indicator_spec("surface_algal_bloom_frequency").pillar=="C2_vegetation"
    assert get_indicator_spec("shoreline_disturbance_fraction").pillar=="C4_pressure"
    assert get_indicator_spec("species_richness").pillar=="C3_fauna"


def test_external_boolean_parsing(tmp_path):
    from darukaa_adaptive.observations import load_observations
    f=tmp_path/"obs.csv"
    f.write_text("metric,value,pillar,direction,reference_approved\nspecies_richness,10,C3_fauna,higher_is_better,False\n")
    rec=load_observations(f,"field")[0]
    assert rec.reference_approved is False


def test_edna_broad_assignment_is_not_fauna_pillar():
    assert get_indicator_spec("edna_taxonomic_richness").pillar == "C2_vegetation"
    assert get_indicator_spec("edna_fauna_taxonomic_richness").pillar == "C3_fauna"
