"""Site geometry ingestion and canonical spatial domains."""
from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path
from typing import Dict, Iterable, Tuple

from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, shape
from shapely.ops import transform, unary_union


def _strip_z(geom):
    return transform(lambda x, y, z=None: (x, y), geom)


def _iter_placemarks(root):
    ns = {"kml": "http://www.opengis.net/kml/2.2"}
    for pm in root.findall(".//kml:Placemark", ns):
        name_el = pm.find("kml:name", ns)
        name = (name_el.text or "").strip() if name_el is not None else ""
        coords_el = pm.find(".//kml:coordinates", ns)
        if coords_el is None or not coords_el.text:
            continue
        coords = []
        for token in coords_el.text.strip().split():
            vals = token.split(",")
            if len(vals) >= 2:
                coords.append((float(vals[0]), float(vals[1])))
        if len(coords) >= 3:
            yield name or "site", Polygon(coords)


def read_kml(path: str | Path) -> Tuple[object, Dict[str, object]]:
    """Read KML/KMZ and return union geometry plus individual named geometries."""
    path = Path(path)
    if path.suffix.lower() == ".kmz":
        with zipfile.ZipFile(path, "r") as z:
            names = [n for n in z.namelist() if n.lower().endswith(".kml")]
            if not names:
                raise ValueError("KMZ contains no KML file")
            data = z.read(names[0])
    else:
        data = path.read_bytes()

    geoms: Dict[str, object] = {}
    try:
        from fastkml import kml
        doc = kml.KML()
        doc.from_string(data)
        containers = list(doc.features())
        def walk(items):
            for item in items:
                if hasattr(item, "features"):
                    children = list(item.features())
                    if children:
                        yield from walk(children)
                geom = getattr(item, "geometry", None)
                if geom is not None:
                    yield getattr(item, "name", None) or "site", geom
        for name, geom in walk(containers):
            if not geom.is_empty:
                geoms[str(name)] = _strip_z(geom)
    except Exception:
        from lxml import etree
        root = etree.fromstring(data)
        for name, geom in _iter_placemarks(root):
            geoms[name] = _strip_z(geom)

    if not geoms:
        raise ValueError(f"No usable polygon geometries found in {path}")
    union = unary_union(list(geoms.values()))
    return union, geoms


def geometry_hash(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def area_ha(geom) -> float:
    """Approximate area in hectares using an auto-selected UTM projection."""
    from pyproj import CRS, Transformer
    c = geom.centroid
    zone = int((c.x + 180) // 6) + 1
    epsg = 32600 + zone if c.y >= 0 else 32700 + zone
    transformer = Transformer.from_crs("EPSG:4326", epsg, always_xy=True)
    projected = transform(transformer.transform, geom)
    return float(projected.area / 10_000.0)


def ee_geometry(geom):
    import ee
    return ee.Geometry(geom.__geo_interface__)


def make_domains(geom, riparian_buffer_m: float, context_buffer_km: float):
    """Return fixed domains; dynamic domains are produced by WaterDetector per period."""
    import ee
    boundary = ee_geometry(geom)
    # Buffer in a local UTM projection for metric-safe distance, then convert back.
    from pyproj import Transformer
    from shapely.ops import transform as shp_transform
    c = geom.centroid
    zone = int((c.x + 180) // 6) + 1
    epsg = 32600 + zone if c.y >= 0 else 32700 + zone
    fwd = Transformer.from_crs("EPSG:4326", epsg, always_xy=True).transform
    inv = Transformer.from_crs(epsg, "EPSG:4326", always_xy=True).transform
    p = shp_transform(fwd, geom)
    riparian = shp_transform(inv, p.buffer(riparian_buffer_m).difference(p))
    context = shp_transform(inv, p.buffer(context_buffer_km * 1000).difference(p))
    return {
        "boundary": boundary,
        "riparian_fixed": ee_geometry(riparian),
        "context": ee_geometry(context),
    }
