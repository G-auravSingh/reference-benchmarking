from __future__ import annotations
from pathlib import Path
from typing import List
import zipfile
from shapely.geometry import shape, mapping
from shapely.ops import unary_union


def _read_kml_text(path: str) -> str:
    p = Path(path)
    if p.suffix.lower() == ".kmz":
        with zipfile.ZipFile(p) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".kml")]
            if not names:
                raise ValueError("KMZ contains no KML file")
            return z.read(names[0]).decode("utf-8", errors="replace")
    return p.read_text(encoding="utf-8", errors="replace")


def load_kml(path: str):
    """Load all polygon geometries from KML/KMZ and return their unary union."""
    text = _read_kml_text(path)
    geoms = []
    try:
        from fastkml import kml as fkml
        k = fkml.KML()
        k.from_string(text.encode())
        def walk(features):
            for f in features:
                if getattr(f, "geometry", None) is not None:
                    g = f.geometry
                    if g.geom_type in {"Polygon", "MultiPolygon"}:
                        geoms.append(g)
                children = getattr(f, "features", None)
                if children:
                    walk(list(children()))
        walk(list(k.features()))
    except Exception:
        from lxml import etree
        from shapely.geometry import Polygon
        root = etree.fromstring(text.encode())
        ns = {"kml": "http://www.opengis.net/kml/2.2"}
        for pm in root.findall(".//kml:Placemark", ns):
            el = pm.find(".//kml:coordinates", ns)
            if el is None or not el.text:
                continue
            coords=[]
            for token in el.text.strip().split():
                vals=token.split(",")
                if len(vals)>=2:
                    coords.append((float(vals[0]), float(vals[1])))
            if len(coords)>=3:
                geoms.append(Polygon(coords))
    if not geoms:
        raise ValueError(f"No polygon geometry found in {path}")
    geom = unary_union(geoms)
    if not geom.is_valid:
        geom = geom.buffer(0)
    return geom


def area_ha(geom) -> float:
    """Approximate geodesic area using pyproj.Geod when available."""
    try:
        from pyproj import Geod
        geod = Geod(ellps="WGS84")
        if geom.geom_type == "Polygon":
            a, _ = geod.geometry_area_perimeter(geom)
            return abs(a) / 10000.0
        return sum(abs(geod.geometry_area_perimeter(g)[0]) for g in geom.geoms) / 10000.0
    except Exception:
        # Fallback is only for environments without pyproj; do not use for final reporting.
        return float("nan")


def to_ee_geometry(geom):
    import ee
    return ee.Geometry(mapping(geom))
