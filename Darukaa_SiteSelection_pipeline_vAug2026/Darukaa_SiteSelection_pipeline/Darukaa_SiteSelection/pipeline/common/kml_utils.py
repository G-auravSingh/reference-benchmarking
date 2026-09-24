"""
kml_utils.py — generic KML placemark parser
============================================

Why this exists rather than a straight `geopandas.read_file(kml)`: real
client KMLs in this project are NOT one consistent schema. Confirmed by
direct inspection of the KMLs on file:

  - Project_GV_Biodiversity.kml   -> standard KML 2.2 <ExtendedData><SchemaData>
                                      <SimpleData name="...">value</SimpleData>
                                      structure. Fields seen: Farmer_s_n,
                                      District, Grampancha, Village,
                                      Year_of_pl, Submission, area_ha.
                                      No `block` field at all.

  - Project_Soova_Biodiversity.kml -> LEGACY Google-Earth-Pro export: no
                                      ExtendedData at all. Attributes are
                                      buried in a <description> CDATA block
                                      containing an HTML <table> of
                                      alternating <td>key</td><td>value</td>
                                      pairs (the "BalloonStyle" table you get
                                      from exporting a shapefile/CSV import
                                      in Earth Pro). Fields seen: farmername,
                                      state, district, block, grampanchayat,
                                      village, _id, latitude, longitude,
                                      area_ha, LP_id, Plantation_year,
                                      SHAPE_Length, SHAPE_Area.

  - SoulForest_Veltoor.kml         -> plain named Polygon placemarks, no
                                      attribute table at all (zone identity
                                      IS the placemark name).

`geopandas.read_file` only handles the first cleanly and drops the
description-table attributes of the second entirely (they'd load as one
opaque HTML blob under a `description` column). This module normalizes all
three into one flat attribute dict per placemark, which
01_ingestion/kml_ingest.py then runs through the config's attribute
crosswalk.

geometry handling: <Polygon> and <MultiGeometry> (of polygons) are parsed
into shapely Polygon/MultiPolygon. <Point> placemarks are kept for
completeness (some project KMLs carry point markers, e.g. individual trees
or sample locations) but flagged as `geometry_type="Point"` so downstream
code can decide whether they're candidates or reference markers.
"""
from __future__ import annotations

import logging
import html
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from shapely.geometry import MultiPolygon, Point, Polygon

logger = logging.getLogger(__name__)

_NS_STRIP_RE = re.compile(r"\sxmlns(:\w+)?=\"[^\"]*\"")
_PLACEMARK_RE = re.compile(r"<Placemark[^>]*>.*?</Placemark>", re.S)
_NAME_RE = re.compile(r"<name>(.*?)</name>", re.S)
_SIMPLEDATA_RE = re.compile(
    r'<SimpleData\s+name="([^"]+)">(.*?)</SimpleData>', re.S)
_TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_COORDS_BLOCK_RE = re.compile(r"<coordinates>(.*?)</coordinates>", re.S)
_POLYGON_RE = re.compile(r"<Polygon>.*?</Polygon>", re.S)
_POINT_RE = re.compile(r"<Point>.*?</Point>", re.S)


def _clean_text(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s)  # strip any nested tags (e.g. <![CDATA[ )
    return s.replace("<![CDATA[", "").replace("]]>", "").strip()


def _parse_coords(coord_text: str) -> List[tuple]:
    coord_text = coord_text.strip()
    pts = []
    for chunk in coord_text.split():
        parts = chunk.split(",")
        if len(parts) >= 2:
            lon, lat = float(parts[0]), float(parts[1])
            pts.append((lon, lat))
    return pts


def _parse_polygon_block(block: str) -> Optional[Polygon]:
    """Parse one <Polygon>...</Polygon> block (outer ring + optional inner
    rings) into a shapely Polygon."""
    rings = re.findall(
        r"<(outerBoundaryIs|innerBoundaryIs)>.*?<coordinates>(.*?)</coordinates>.*?</\1>",
        block, re.S)
    outer = None
    inners = []
    for tag, coord_text in rings:
        pts = _parse_coords(coord_text)
        if len(pts) < 3:
            continue
        if tag == "outerBoundaryIs":
            outer = pts
        else:
            inners.append(pts)
    if outer is None:
        return None
    try:
        return Polygon(outer, inners if inners else None)
    except Exception as e:
        logger.warning("Failed to build polygon from parsed rings: %s", e)
        return None


def _parse_geometry(placemark_xml: str):
    """Returns (geometry, geometry_type_str) or (None, None)."""
    polys = [p for blk in _POLYGON_RE.findall(placemark_xml)
             if (p := _parse_polygon_block(blk)) is not None]
    if len(polys) == 1:
        return polys[0], "Polygon"
    if len(polys) > 1:
        return MultiPolygon(polys), "MultiPolygon"

    pt_match = _POINT_RE.search(placemark_xml)
    if pt_match:
        coord_match = _COORDS_BLOCK_RE.search(pt_match.group(0))
        if coord_match:
            pts = _parse_coords(coord_match.group(1))
            if pts:
                return Point(pts[0]), "Point"

    return None, None


def _parse_schemadata_attrs(placemark_xml: str) -> Dict[str, str]:
    return {k: _clean_text(v) for k, v in _SIMPLEDATA_RE.findall(placemark_xml)}


def _parse_description_table_attrs(placemark_xml: str) -> Dict[str, str]:
    """Legacy Earth-Pro export: <description><![CDATA[<html>...<table> of
    <td>key</td><td>value</td> pairs.

    Real layout, confirmed against the actual Soova KML cell-by-cell:
        [id_header, <nested-table-junk>, 'SHAPE', 'Polygon', 'Name', id,
         'farmername', 'Chidiram Majhi', 'state', 'Odisha', ...]

    The reliable anchor is the literal cell 'Name' (exact case-insensitive
    match, not a substring/structural-word check) — the key/value run
    starts EXACTLY there: ('Name', id_value) is itself the first valid pair,
    followed by ('farmername', value), ('state', value), etc.

    An earlier version of this parser searched for the first cell whose
    lowercased text was outside a structural-word set, intending to skip
    past 'Name' to the id value beyond it — that landed one cell too late
    and paired every key with the WRONG value (confirmed by running against
    real Soova data: e.g. {'763493190': 'latitude', 'Jagala Majhi': 'state'}
    instead of {'farmername': 'Jagala Majhi', 'state': 'Odisha', ...}).
    Anchoring on 'Name' itself, not the cell after it, fixes this."""
    desc_match = re.search(r"<description>(.*?)</description>", placemark_xml, re.S)
    if not desc_match:
        return {}
    desc_content = desc_match.group(1)
    # Found directly against a real client KML that
    # failed to parse at all — attr_source came back "none" for every
    # single placemark, not a partial/degraded parse): the description
    # table markup can be embedded either wrapped in <![CDATA[...]]>
    # (literal <td> tags, what this parser originally assumed) OR as
    # HTML-entity-escaped text (&lt;td&gt;...&lt;/td&gt;) with no CDATA
    # wrapper at all — a real, valid difference in how different export
    # tool versions serialise the same underlying Earth-Pro description
    # table, not a data quality issue. Un-escaping entities first makes
    # this parser work identically regardless of which form the source
    # KML used, rather than silently returning nothing for one of them.
    if "&lt;td" in desc_content.lower() or "&lt;table" in desc_content.lower():
        desc_content = html.unescape(desc_content)
    cells = [_clean_text(c) for c in _TD_RE.findall(desc_content)]

    start = None
    for i, cell in enumerate(cells):
        if cell.strip().lower() == "name":
            start = i
            break
    if start is None:
        return {}

    kv_cells = cells[start:]
    attrs = {}
    for i in range(0, len(kv_cells) - 1, 2):
        key, val = kv_cells[i].strip(), kv_cells[i + 1]
        if key:
            attrs[key] = val
    return attrs


def parse_kml(path: str | Path) -> List[Dict[str, Any]]:
    """Parse a KML file into a list of normalized placemark dicts:
        {
          "name": str,
          "geometry": shapely geometry or None,
          "geometry_type": "Polygon" | "MultiPolygon" | "Point" | None,
          "attrs": {raw_field_name: value, ...},
          "attr_source": "schemadata" | "description_table" | "none",
        }
    Never raises on a single malformed placemark — logs and skips it,
    since one bad placemark in a 1,893-parcel KML should not abort the run.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="ignore")
    placemarks_xml = _PLACEMARK_RE.findall(text)
    logger.info("%s: found %d <Placemark> elements", path.name, len(placemarks_xml))

    records = []
    n_failed = 0
    for i, pm_xml in enumerate(placemarks_xml):
        try:
            name_match = _NAME_RE.search(pm_xml)
            name = _clean_text(name_match.group(1)) if name_match else f"unnamed_{i}"

            geometry, geom_type = _parse_geometry(pm_xml)

            schemadata_attrs = _parse_schemadata_attrs(pm_xml)
            if schemadata_attrs:
                attrs, source = schemadata_attrs, "schemadata"
            else:
                desc_attrs = _parse_description_table_attrs(pm_xml)
                attrs, source = (desc_attrs, "description_table") if desc_attrs else ({}, "none")

            records.append({
                "name": name,
                "geometry": geometry,
                "geometry_type": geom_type,
                "attrs": attrs,
                "attr_source": source,
                "placemark_index": i,
            })
        except Exception as e:
            n_failed += 1
            logger.warning("%s: failed to parse placemark %d (%s), skipping", path.name, i, e)

    if n_failed:
        logger.warning("%s: %d/%d placemarks failed to parse and were skipped",
                        path.name, n_failed, len(placemarks_xml))

    n_no_geom = sum(1 for r in records if r["geometry"] is None)
    if n_no_geom:
        logger.warning("%s: %d placemarks have no parseable geometry", path.name, n_no_geom)

    return records
