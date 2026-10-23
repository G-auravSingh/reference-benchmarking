"""Site geometry ingestion, validation and canonical spatial domains."""
from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path
from typing import Dict, Tuple

from shapely.geometry import Polygon, shape
from shapely.geometry.base import BaseGeometry
import shapely
from shapely.ops import unary_union


def _strip_z(geom: BaseGeometry) -> BaseGeometry:
    return shapely.force_2d(geom)


def _reproject(geom: BaseGeometry, transformer) -> BaseGeometry:
    return shapely.transform(geom, lambda x, y: transformer.transform(x, y), interleaved=False)


def _normalise_geometry(geom: BaseGeometry) -> BaseGeometry:
    geom = _strip_z(geom)
    if geom.is_empty:
        return geom
    if not geom.is_valid:
        geom = geom.buffer(0)
    if geom.is_empty:
        return geom
    return geom


def _parse_coords(text: str):
    coords = []
    for token in (text or "").strip().split():
        vals = token.split(",")
        if len(vals) >= 2:
            coords.append((float(vals[0]), float(vals[1])))
    return coords


def _iter_lxml_placemarks(root):
    """Yield (name, geometry) for every Placemark, keeping holes and all parts.

    Each kml:Polygon contributes its outer ring and every inner ring; a Placemark
    holding several polygons (MultiGeometry) becomes a MultiPolygon. Nothing is
    silently reduced to the first coordinate list.
    """
    from shapely.geometry import MultiPolygon
    ns = {"kml": "http://www.opengis.net/kml/2.2"}
    for pm in root.findall(".//kml:Placemark", ns):
        name_el = pm.find("kml:name", ns)
        name = (name_el.text or "").strip() if name_el is not None else ""
        polys = []
        for poly_el in pm.findall(".//kml:Polygon", ns):
            outer = poly_el.find("kml:outerBoundaryIs//kml:coordinates", ns)
            if outer is None:
                continue
            shell = _parse_coords(outer.text)
            if len(shell) < 3:
                continue
            holes = [_parse_coords(h.text) for h in poly_el.findall("kml:innerBoundaryIs//kml:coordinates", ns)]
            polys.append(Polygon(shell, [h for h in holes if len(h) >= 3]))
        if not polys:
            continue
        yield name or "site", (polys[0] if len(polys) == 1 else MultiPolygon(polys))


def _extract_with_fastkml(data: bytes) -> Dict[str, BaseGeometry]:
    from fastkml import kml

    doc = kml.KML()
    doc.from_string(data)

    geoms: Dict[str, BaseGeometry] = {}

    def walk(items):
        for item in items:
            children = []
            features = getattr(item, "features", None)
            if callable(features):
                try:
                    children = list(features())
                except TypeError:
                    children = list(features)
            if children:
                yield from walk(children)
            geom = getattr(item, "geometry", None)
            if geom is not None:
                try:
                    yield str(getattr(item, "name", None) or "site"), shape(geom.__geo_interface__)
                except Exception:
                    continue

    root_features = getattr(doc, "features", None)
    if callable(root_features):
        containers = list(root_features())
    else:
        containers = list(root_features or [])

    for name, geom in walk(containers):
        geom = _normalise_geometry(geom)
        if not geom.is_empty:
            geoms[name] = geom
    return geoms


def read_kml(path: str | Path) -> Tuple[BaseGeometry, Dict[str, BaseGeometry]]:
    """Read KML/KMZ and return union geometry plus individual named geometries."""
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
        raise ValueError("Expected a .kml or .kmz file")

    # The namespace-aware XML parser is used first: it is deterministic and keeps
    # holes and multi-part placemarks. fastkml is only a fallback for documents the
    # XML parser cannot read (for example a non-standard namespace).
    from lxml import etree
    geoms: Dict[str, BaseGeometry] = {}
    root = etree.fromstring(data)
    used = {}
    for name, geom in _iter_lxml_placemarks(root):
        geom = _normalise_geometry(geom)
        if geom.is_empty:
            continue
        used[name] = used.get(name, 0) + 1
        key = name if used[name] == 1 else f"{name}_{used[name]}"
        geoms[key] = geom
    if not geoms:
        geoms = _extract_with_fastkml(data)

    if not geoms:
        raise ValueError(f"No usable polygon geometries found in {path}")

    union = _normalise_geometry(unary_union(list(geoms.values())))
    if union.is_empty or not union.is_valid:
        raise ValueError("The unioned site geometry is empty or invalid")
    return union, geoms


def geometry_hash(path: str | Path) -> str:
    """SHA-256 of the exact input file bytes."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _utm_epsg(geom: BaseGeometry) -> int:
    c = geom.centroid
    zone = int((c.x + 180) // 6) + 1
    return 32600 + zone if c.y >= 0 else 32700 + zone


def area_ha(geom: BaseGeometry) -> float:
    """Area in hectares using an auto-selected local UTM projection."""
    from pyproj import Transformer

    epsg = _utm_epsg(geom)
    transformer = Transformer.from_crs("EPSG:4326", epsg, always_xy=True)
    projected = _reproject(geom, transformer)
    return float(projected.area / 10_000.0)


def projected_buffer(geom: BaseGeometry, distance_m: float) -> BaseGeometry:
    """Buffer a WGS84 geometry in metres using its local UTM zone."""
    from pyproj import Transformer

    epsg = _utm_epsg(geom)
    fwd = Transformer.from_crs("EPSG:4326", epsg, always_xy=True)
    inv = Transformer.from_crs(epsg, "EPSG:4326", always_xy=True)
    projected = _reproject(geom, fwd)
    return _normalise_geometry(_reproject(projected.buffer(distance_m), inv))


def make_shapely_domains(geom: BaseGeometry, riparian_buffer_m: float, context_buffer_km: float) -> Dict[str, BaseGeometry]:
    """Create deterministic fixed spatial domains without requiring Earth Engine."""
    riparian_outer = projected_buffer(geom, riparian_buffer_m)
    context_outer = projected_buffer(geom, context_buffer_km * 1000.0)
    return {
        "master": geom,
        "riparian_fixed": _normalise_geometry(riparian_outer.difference(geom)),
        "context": _normalise_geometry(context_outer.difference(geom)),
    }


def make_domains(geom: BaseGeometry, riparian_buffer_m: float, context_buffer_km: float):
    """Return EE fixed domains; dynamic water is generated separately."""
    from .site import ee_geometry  # local import keeps this module testable without EE

    shp = make_shapely_domains(geom, riparian_buffer_m, context_buffer_km)
    return {
        "boundary": ee_geometry(shp["master"]),
        "riparian_fixed": ee_geometry(shp["riparian_fixed"]),
        "context": ee_geometry(shp["context"]),
        "water_dynamic": None,
        "littoral_dynamic": None,
        "shapely": shp,
    }


def ee_geometry(geom: BaseGeometry):
    import ee
    return ee.Geometry(geom.__geo_interface__)


def validate_site_geometry(geom: BaseGeometry) -> Dict[str, object]:
    """Return deterministic geometry QA information."""
    return {
        "valid": bool(geom.is_valid and not geom.is_empty),
        "geometry_type": geom.geom_type,
        "part_count": len(geom.geoms) if hasattr(geom, "geoms") else 1,
        "area_ha": area_ha(geom),
        "bounds": tuple(float(x) for x in geom.bounds),
    }
