"""
crs.py — projected CRS resolution                              [NEW, v6.0]

Replaces the hard-coded `config.PROJECTED_CRS = "EPSG:32644"`.

Zone 44N spans 78-84 E. Pimpri sits at 73.81 E, which is zone 43N. Measured
effect of using the wrong zone on a real 189.93 m separation at Pimpri:
191.21 m -> +0.67% on every distance and ~+1.3% on every area. That bias
propagates into MIN_SPACING_M tests, virtual-parcel radii, DBSCAN eps, all
hectare figures and all logistics distances, for every project west of 78 E
(Gujarat, Maharashtra, western MP). North Shahdol at ~81.4 E is correctly 44N
and unaffected.

WHY resolve() TAKES A KML FOLDER, NOT JUST A POLYGON
-----------------------------------------------------
PHASE_0's Pattern-A parser buffers raw points into polygons using
`cfg.PROJECTED_CRS` *while parsing* (see the `.to_crs(cfg.PROJECTED_CRS)`
calls in `parse_pattern_a` / `parse_pattern_c`) — i.e. it needs a projected
CRS before a finished AOI geometry exists to derive one from. Deriving the
zone from a full centroid is therefore circular for those patterns.

The zone only needs to be correct to within a 6-degree longitude band, so a
cheap peek at the first coordinate anywhere in the KML file(s) is sufficient
— no need to wait for the parse to finish. `resolve_from_kml_folder()` does
that peek and is called once, at the very top of `run_phase_0()`, before any
pattern-specific parsing begins.

Usage
-----
    import crs
    # at the top of run_phase_0(), before parse_pattern_*() runs:
    cfg.PROJECTED_CRS = crs.resolve_from_kml_folder(kml_files, cfg.PROJECTED_CRS_OVERRIDE)

    # anywhere a finished AOI polygon already exists (v6.0 aquatic/frame code):
    PROJECTED_CRS = crs.resolve(aoi_polygon_wgs84)
"""
from __future__ import annotations

import re
from pathlib import Path

import pyproj
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as _shp_transform

GEOGRAPHIC_CRS = "EPSG:4326"

_COORD_RE = re.compile(
    r"<coordinates>\s*([\-\d\.]+)\s*,\s*([\-\d\.]+)", re.IGNORECASE)


def utm_epsg(lon: float, lat: float) -> str:
    """UTM EPSG code for a lon/lat. 326xx northern hemisphere, 327xx southern."""
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError(f"lon/lat out of range: {lon}, {lat}")
    zone = int((lon + 180) // 6) + 1
    return f"EPSG:{(32600 if lat >= 0 else 32700) + zone}"


def resolve(aoi_wgs84: BaseGeometry, override: str | None = None) -> str:
    """Projected CRS for a finished AOI geometry. `override` forces a zone
    deliberately (e.g. to keep an older project's outputs byte-comparable)."""
    if override:
        return override
    c = aoi_wgs84.centroid
    return utm_epsg(c.x, c.y)


def resolve_from_kml_folder(kml_paths: list[Path], override: str | None = None) -> str:
    """Projected CRS derived from the first coordinate found in any of the
    given KML files. Used at the top of PHASE_0, before geometries exist,
    because Pattern A/C need PROJECTED_CRS set before they can buffer points
    into polygons. Only the 6-degree longitude band matters, so the first
    coordinate anywhere in the file(s) is sufficient — precision to the
    metre is not required here."""
    if override:
        return override
    for p in kml_paths:
        m = _COORD_RE.search(Path(p).read_text(errors="ignore"))
        if m:
            lon, lat = float(m.group(1)), float(m.group(2))
            return utm_epsg(lon, lat)
    raise ValueError(
        "resolve_from_kml_folder: no <coordinates> found in any KML file — "
        "cannot derive a projected CRS. Set config.PROJECTED_CRS_OVERRIDE "
        "explicitly.")


def transformers(projected_crs: str):
    """Return (to_metres, to_lonlat) shapely-ready transform functions."""
    fwd = pyproj.Transformer.from_crs(GEOGRAPHIC_CRS, projected_crs, always_xy=True).transform
    inv = pyproj.Transformer.from_crs(projected_crs, GEOGRAPHIC_CRS, always_xy=True).transform
    return fwd, inv


def to_m(geom: BaseGeometry, projected_crs: str) -> BaseGeometry:
    fwd, _ = transformers(projected_crs)
    return _shp_transform(fwd, geom)


def to_ll(geom: BaseGeometry, projected_crs: str) -> BaseGeometry:
    _, inv = transformers(projected_crs)
    return _shp_transform(inv, geom)


def provenance(a, b=None) -> dict:
    """Audit record — logged by run_phase_0()/PHASE_0b and written into the
    outputs manifest, so the resolved zone is never a silent guess.

    Accepts either argument order, since two call sites in this codebase use
    it differently: PHASE_0_KMLIngestion.py (no finished polygon yet) calls
    provenance(projected_crs); PHASE_0b_SiteFrame.py (polygon already built)
    calls provenance(aoi_wgs84, projected_crs). Both resolve to the same
    output shape."""
    if isinstance(a, str):
        projected_crs, aoi_wgs84 = a, b
    else:
        aoi_wgs84, projected_crs = a, b
    rec = {"projected_crs": projected_crs,
           "utm_zone": int(projected_crs[-2:]),
           "basis": "derived_from_first_kml_coordinate"}
    if aoi_wgs84 is not None:
        c = aoi_wgs84.centroid
        rec["aoi_centroid_lon"] = round(c.x, 6)
        rec["aoi_centroid_lat"] = round(c.y, 6)
        rec["basis"] = "derived_from_aoi_centroid"
    return rec
