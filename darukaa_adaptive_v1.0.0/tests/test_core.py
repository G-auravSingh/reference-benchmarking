import tempfile
from pathlib import Path

from shapely.geometry import Polygon

from darukaa_adaptive.benchmark import intactness_ratio, percent_change
from darukaa_adaptive.config import AssessmentConfig
from darukaa_adaptive.site import area_ha, read_kml
from darukaa_adaptive.scoring import score_with_thresholds


def test_ratio_and_percent_change():
    assert intactness_ratio(80, 100, True) == 0.8
    assert intactness_ratio(80, 100, False) == 1.0
    assert round(percent_change(110, 100), 6) == 10.0


def test_threshold_scoring():
    th = {"t1":0.1,"t2":0.2,"t3":0.3,"t4":0.4}
    assert score_with_thresholds(0.05, th, True) == 1
    assert score_with_thresholds(0.5, th, True) == 5
    assert score_with_thresholds(0.05, th, False) == 5


def test_area():
    poly=Polygon([(74,17.5),(74.001,17.5),(74.001,17.501),(74,17.501)])
    assert area_ha(poly) > 0


def test_kml_reader():
    text='''<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark><name>Nandoshi</name><Polygon><outerBoundaryIs><LinearRing><coordinates>74,17,0 74.001,17,0 74.001,17.001,0 74,17.001,0 74,17,0</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></Document></kml>'''
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/'x.kml'; p.write_text(text)
        geom,parts=read_kml(p)
        assert geom.area > 0
        assert parts


def test_config_default_validates():
    cfg=AssessmentConfig()
    assert cfg.validate()==[]
