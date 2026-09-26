"""Site geometry ingestion, domain derivation and QA."""
from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path
from typing import Dict, Tuple

from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union


def _strip_z(geom: BaseGeometry) -> BaseGeometry:
    return transform(lambda x, y, z=None: (x, y), geom)


def _normalise_geometry(geom: BaseGeometry) -> BaseGeometry:
    geom = _strip_z(geom)
    if geom.is_empty:
        return geom
    if not geom.is_valid:
        geom = geom.buffer(0)
    return geom


def _iter_lxml_placemarks(root):
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


def _extract_with_fastkml(data: bytes) -> Dict[str, BaseGeometry]:
    from fastkml import kml
    from shapely.geometry import shape

    doc = kml.KML()
    doc.from_string(data)
    geoms: Dict[str, BaseGeometry] = {}

    def walk(items):
        for item in items:
            features = getattr(item, "features", None)
            try:
                children = list(features()) if callable(features) else list(features or [])
            except Exception:
                children = []
            if children:
                yield from walk(children)
            geom = getattr(item, "geometry", None)
            if geom is not None:
                try:
                    yield str(getattr(item, "name", None) or "site"), shape(geom.__geo_interface__)
                except Exception:
                    pass

    features = getattr(doc, "features", None)
    roots = list(features()) if callable(features) else list(features or [])
    for name, geom in walk(roots):
        geom = _normalise_geometry(geom)
        if not geom.is_empty and geom.geom_type in {"Polygon", "MultiPolygon"}:
            geoms[name] = geom
    return geoms


def read_kml(path: str | Path) -> Tuple[BaseGeometry, Dict[str, BaseGeometry]]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() == ".kmz":
        with zipfile.ZipFile(path, "r") as z:
            names = [n for n in z.namelist() if n.lower().endswith(".kml")]
            if not names:
                raise ValueError("KMZ contains no KML file")
            data = z.read(names[0])
    elif path.suffix.lower() == ".kml":
        data = path.read_bytes()
    else:
        raise ValueError("Expected .kml or .kmz")

    geoms: Dict[str, BaseGeometry] = {}
    try:
        geoms = _extract_with_fastkml(data)
    except Exception:
        geoms = {}
    if not geoms:
        from lxml import etree
        root = etree.fromstring(data)
        for name, geom in _iter_lxml_placemarks(root):
            geom = _normalise_geometry(geom)
            if not geom.is_empty:
                geoms[name] = geom
    if not geoms:
        raise ValueError(f"No usable polygon geometries found in {path}")
    union = _normalise_geometry(unary_union(list(geoms.values())))
    if union.is_empty or not union.is_valid:
        raise ValueError("Unioned site geometry is empty or invalid")
    return union, geoms


def geometry_hash(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _utm_epsg(geom: BaseGeometry) -> int:
    c = geom.centroid
    zone = int((c.x + 180) // 6) + 1
    return 32600 + zone if c.y >= 0 else 32700 + zone


def area_ha(geom: BaseGeometry) -> float:
    from pyproj import Transformer
    epsg = _utm_epsg(geom)
    transformer = Transformer.from_crs("EPSG:4326", epsg, always_xy=True)
    return float(transform(transformer.transform, geom).area / 10_000.0)


def projected_buffer(geom: BaseGeometry, distance_m: float) -> BaseGeometry:
    from pyproj import Transformer
    epsg = _utm_epsg(geom)
    fwd = Transformer.from_crs("EPSG:4326", epsg, always_xy=True).transform
    inv = Transformer.from_crs(epsg, "EPSG:4326", always_xy=True).transform
    projected = transform(fwd, geom)
    return _normalise_geometry(transform(inv, projected.buffer(distance_m)))


def make_shapely_domains(geom: BaseGeometry, riparian_buffer_m: float, context_buffer_km: float, littoral_band_m: float = 50.0) -> Dict[str, BaseGeometry]:
    riparian_outer = projected_buffer(geom, riparian_buffer_m)
    context_outer = projected_buffer(geom, context_buffer_km * 1000.0)
    littoral_outer = projected_buffer(geom, littoral_band_m)
    return {
        "master": geom,
        "riparian_fixed": _normalise_geometry(riparian_outer.difference(geom)),
        "littoral_band": _normalise_geometry(littoral_outer.difference(geom)),
        "context": _normalise_geometry(context_outer.difference(geom)),
        "terrestrial_context": _normalise_geometry(context_outer.difference(geom)),
    }


def make_domains(geom: BaseGeometry, riparian_buffer_m: float, context_buffer_km: float, littoral_band_m: float = 50.0):
    shp = make_shapely_domains(geom, riparian_buffer_m, context_buffer_km, littoral_band_m)
    return {
        "boundary": ee_geometry(shp["master"]),
        "riparian_fixed": ee_geometry(shp["riparian_fixed"]),
        "littoral_band": ee_geometry(shp["littoral_band"]),
        "context": ee_geometry(shp["context"]),
        "terrestrial_context": ee_geometry(shp["terrestrial_context"]),
        "shapely": shp,
    }


def ee_geometry(geom: BaseGeometry):
    import ee
    return ee.Geometry(geom.__geo_interface__)


def validate_site_geometry(geom: BaseGeometry) -> Dict[str, object]:
    return {
        "valid": bool(geom.is_valid and not geom.is_empty),
        "geometry_type": geom.geom_type,
        "part_count": len(geom.geoms) if hasattr(geom, "geoms") else 1,
        "area_ha": area_ha(geom),
        "bounds": tuple(float(x) for x in geom.bounds),
    }
