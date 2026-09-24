from pathlib import Path
from darukaa_adaptive.geometry import load_kml, area_ha

def test_nandoshi_kml_loads():
    p=Path(__file__).parents[1]/'input'/'Nandoshi lake.kml'
    g=load_kml(str(p))
    a=area_ha(g)
    assert a > 0
    assert 8.0 < a < 10.0
