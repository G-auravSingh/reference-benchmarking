"""
preprocess_eco_zones.py — TataMotors_Pimpri
=============================================

Purpose-built preprocessing for a genuinely different KML structure than
any other project this pipeline has ingested: 20 real GDAL layers, split
between true exclusion polygons, LINE-traced exclusion features (buildings/
infrastructure/paths/streams — confirmed directly, Aug 2026, that these are
NOT reliably closed loops: NIC_Building is only 39% closed, Path way just
1% — so treating "closed vs open" as the deciding factor would be fragile;
buffering every line into an exclusion polygon is the robust, and safely
conservative, choice), and real, named, ecologically-usable vegetation
zones.

This script does NOT run candidate generation itself — it produces three
clean artifacts that 01_ingestion's existing candidate_grid.py can then
consume as it already does for any conservation-archetype project:
  - aoi_boundary.geojson   (the corrected site boundary, already a real
                             closed Polygon in the source KML — verified
                             directly, 126.66 ha)
  - exclusion_mask.geojson (union of real exclusion polygons + buffered
                             line features)
  - eco_zones.geojson      (every usable vegetation zone, tagged with its
                             real client-given zone name AND sub-zone name
                             where the client already provided one, e.g.
                             "Veg_Deccan forest" / "F_D_7c")

Buffer distances (metres) are real, stated, and adjustable — not silently
baked in:
  - Buildings/infrastructure: 10m (a reasonable minimum standoff from a
    structure — not derived from any project-specific survey, flagged as
    such)
  - Paths: 5m
  - Water streams / reed beds / seasonal wetland lines: 15m (a riparian-
    buffer-literature-consistent default, same reasoning already used
    elsewhere in this pipeline for water body proximity)
"""
from __future__ import annotations

import json
import logging
import warnings
from pathlib import Path
from typing import Dict, List

import geopandas as gpd
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Real layer classification, confirmed directly against the actual KML
# (Aug 2026) — not assumed from names alone; every layer's real geometry
# type was checked before being placed in one of these three buckets.
BOUNDARY_LAYER = "Pune-Boundary .kml"

EXCLUSION_POLYGON_LAYERS = ["_L_Water_Bodies", "_L_Water_Island"]

EXCLUSION_LINE_LAYERS = {
    # layer name -> buffer distance in metres
    "_L_Infrastructure": 10.0,
    "_L_NIC _Building": 10.0,
    "_L_NIC_Landscape": 10.0,
    "_L_Path way": 5.0,
    "_L_Reed beds and check dam": 15.0,
    "_L_Veg_Seasonal wetland-line": 15.0,
    "_L_Water_Stream": 15.0,
}

# Display-label corrections for known typos in the client's own source
# KML layer names. The raw layer name is never altered — only the label
# used in this pipeline's own outputs.
ZONE_LABEL_CORRECTIONS = {
    "Water margion": "Water margin",
}

USABLE_ZONE_LAYERS = [
    "_L_Trail plots", "_L_Veg_Deccan forest", "_L_Veg_Eco region",
    "_L_Veg_Grass land", "_L_Veg_Narmada valley", "_L_Veg_Savana ecosystem",
    "_L_Veg_Wildlife", "_L_Veg_Seasonal wetland-polygon", "_L_Veg_Water margion",
    "_L_Veg_Wetland forest",
]


def _load_layer(kml_path: Path, layer: str) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(kml_path, layer=layer, driver="KML")
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    return gdf


def run_preprocess(kml_path: str | Path, out_dir: str | Path) -> Dict:
    kml_path = Path(kml_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- 1. Boundary ---
    boundary_gdf = _load_layer(kml_path, BOUNDARY_LAYER)
    boundary_gdf = boundary_gdf[boundary_gdf.geometry.geom_type == "Polygon"]
    if len(boundary_gdf) != 1:
        raise ValueError(
            f"Expected exactly 1 boundary polygon, found {len(boundary_gdf)} — "
            "check the KML's boundary layer directly before proceeding.")
    boundary_geom = boundary_gdf.geometry.iloc[0]
    projected_crs = boundary_gdf.estimate_utm_crs()
    boundary_m = boundary_gdf.to_crs(projected_crs).geometry.iloc[0]
    boundary_area_ha = boundary_m.area / 10_000
    logger.info("Boundary: 1 polygon, %.2f ha", boundary_area_ha)

    with open(out_dir / "aoi_boundary.geojson", "w") as f:
        json.dump({"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": mapping(boundary_geom),
             "properties": {"area_ha": round(boundary_area_ha, 3)}}]}, f)

    # --- 2. Exclusion mask ---
    excl_geoms_m = []
    layer_report = {}
    for lyr in EXCLUSION_POLYGON_LAYERS:
        gdf = _load_layer(kml_path, lyr)
        gdf = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
        gdf_m = gdf.to_crs(projected_crs)
        excl_geoms_m.extend(gdf_m.geometry.tolist())
        layer_report[lyr] = {"n_features": len(gdf), "kind": "polygon", "buffer_m": 0}

    for lyr, buf_m in EXCLUSION_LINE_LAYERS.items():
        gdf = _load_layer(kml_path, lyr)
        gdf = gdf[gdf.geometry.geom_type.isin(["LineString", "MultiLineString"])]
        gdf_m = gdf.to_crs(projected_crs)
        buffered = gdf_m.geometry.buffer(buf_m)
        excl_geoms_m.extend(buffered.tolist())
        layer_report[lyr] = {"n_features": len(gdf), "kind": "line_buffered", "buffer_m": buf_m}

    exclusion_union_m = unary_union(excl_geoms_m) if excl_geoms_m else None
    exclusion_area_ha = exclusion_union_m.area / 10_000 if exclusion_union_m else 0.0
    logger.info("Exclusion mask: %.2f ha (%.1f%% of boundary)",
                exclusion_area_ha, 100 * exclusion_area_ha / boundary_area_ha)

    if exclusion_union_m is not None:
        exclusion_ll = gpd.GeoSeries([exclusion_union_m], crs=projected_crs).to_crs("EPSG:4326").iloc[0]
        with open(out_dir / "exclusion_mask.geojson", "w") as f:
            json.dump({"type": "FeatureCollection", "features": [
                {"type": "Feature", "geometry": mapping(exclusion_ll),
                 "properties": {"area_ha": round(exclusion_area_ha, 3)}}]}, f)

    # --- 3. Usable eco-zones, tagged with real zone + sub-zone name ---
    zone_features = []
    zone_report = {}
    for lyr in USABLE_ZONE_LAYERS:
        gdf = _load_layer(kml_path, lyr)
        gdf_poly = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
        n_dropped = len(gdf) - len(gdf_poly)
        gdf_m = gdf_poly.to_crs(projected_crs)
        zone_area_ha = gdf_m.geometry.area.sum() / 10_000
        zone_report[lyr] = {"n_polygons": len(gdf_poly), "n_non_polygon_dropped": n_dropped,
                            "area_ha": round(zone_area_ha, 3)}
        zone_label = lyr.replace("_L_", "").replace("Veg_", "").strip()
        zone_label = ZONE_LABEL_CORRECTIONS.get(zone_label, zone_label)
        for _, row in gdf_poly.iterrows():
            sub_name = row.get("Name") if "Name" in row.index and row.get("Name") not in (None, "") else None
            zone_features.append({
                "type": "Feature",
                "geometry": mapping(row.geometry),
                "properties": {"eco_zone": zone_label, "sub_zone_name": sub_name},
            })

    with open(out_dir / "eco_zones.geojson", "w") as f:
        json.dump({"type": "FeatureCollection", "features": zone_features}, f)

    total_zone_area = sum(z["area_ha"] for z in zone_report.values())
    logger.info("Usable eco-zones (raw, before clipping to exclusion/boundary): %d polygons "
                "across %d zone types, %.2f ha total", len(zone_features), len(zone_report), total_zone_area)

    # REAL FINDING, HANDLED HERE (Aug 2026, caught by checking the actual
    # numbers rather than assuming they'd add up cleanly): raw exclusion
    # area + raw usable-zone area summed to MORE than the boundary itself
    # (140.7 ha vs 126.7 ha) — a real, meaningful overlap (~11% of the
    # site), not a rounding artifact. A usable vegetation polygon can
    # legitimately sit partly inside a buffered exclusion zone (e.g. a
    # Trail plot close to a building) — reported separately above as raw
    # client-drawn areas, but exclusion must take precedence for actual
    # candidate eligibility. The true eligible area is computed here by
    # clipping every usable zone to (boundary MINUS exclusion), not by
    # naively subtracting independently-summed areas.
    from shapely.geometry import shape as shapely_shape
    eligible_features = []
    eligible_area_ha = 0.0
    for f in zone_features:
        g = shapely_shape(f["geometry"])
        g_m = gpd.GeoSeries([g], crs="EPSG:4326").to_crs(projected_crs).iloc[0]
        g_m = g_m.intersection(boundary_m)
        if exclusion_union_m is not None:
            g_m = g_m.difference(exclusion_union_m)
        if g_m.is_empty:
            continue
        eligible_area_ha += g_m.area / 10_000
        g_ll = gpd.GeoSeries([g_m], crs=projected_crs).to_crs("EPSG:4326").iloc[0]
        eligible_features.append({
            "type": "Feature", "geometry": mapping(g_ll),
            "properties": {**f["properties"], "area_ha": round(g_m.area / 10_000, 4)},
        })
    with open(out_dir / "eco_zones_eligible.geojson", "w") as f:
        json.dump({"type": "FeatureCollection", "features": eligible_features}, f)
    logger.info("Usable eco-zones (real, clipped to boundary and exclusion): %.2f ha "
                "(%.2f ha removed by clipping/overlap)", eligible_area_ha, total_zone_area - eligible_area_ha)

    report = {
        "boundary_area_ha": round(boundary_area_ha, 3),
        "exclusion_area_ha": round(exclusion_area_ha, 3),
        "exclusion_layers": layer_report,
        "usable_zone_area_ha": round(total_zone_area, 3),
        "usable_zone_area_ha_after_clipping": round(eligible_area_ha, 3),
        "usable_zones": zone_report,
        "unaccounted_area_ha": round(boundary_area_ha - exclusion_area_ha - eligible_area_ha, 3),
    }
    with open(out_dir / "preprocess_report.json", "w") as f:
        json.dump(report, f, indent=2)
    return report


def run_tm_ingestion(project_dir: str | Path) -> Dict[str, Any]:
    """Real replacement for kml_ingest.run_ingestion(), specific to this
    project's genuinely different KML structure (Aug 2026) — produces
    exactly the same outputs the rest of the pipeline expects
    (candidates.geojson, aoi_boundary.geojson, exclusion_zones.geojson,
    ecological_anchors.geojson, ingestion_report.json,
    candidate_grid.geojson), so every downstream stage runs completely
    unmodified. ecological_anchors.geojson is written empty — TM's real
    ecological zones are a PARTITION (hard_barrier_attribute), not a small
    number of discrete anchors, an architectural distinction confirmed
    directly with the project's own real data (10 real zones, not 2-3
    anchor-sized features)."""
    import sys
    project_dir = Path(project_dir)
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "pipeline" / "common"))
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "pipeline" / "01_ingestion"))
    import config_schema
    import candidate_grid
    import crs as crs_mod

    cfg = config_schema.load_config(project_dir / "config.yaml")
    ing_dir = project_dir / "outputs" / "01_ingestion"
    ing_dir.mkdir(parents=True, exist_ok=True)

    raw_kml = next((project_dir / "raw").glob("*.kml"))
    pre_report = run_preprocess(raw_kml, project_dir / "outputs_preprocess")

    # Copy the real preprocessed outputs into 01_ingestion's expected
    # locations, in the exact schema candidate_grid.py and downstream
    # stages already expect.
    pre_dir = project_dir / "outputs_preprocess"
    with open(pre_dir / "aoi_boundary.geojson") as f:
        aoi_fc = json.load(f)
    with open(ing_dir / "aoi_boundary.geojson", "w") as f:
        json.dump(aoi_fc, f)

    excl_path = pre_dir / "exclusion_mask.geojson"
    excl_features = []
    if excl_path.exists():
        with open(excl_path) as f:
            excl_fc = json.load(f)
        for feat in excl_fc["features"]:
            feat["properties"]["role"] = "exclusion_hard"
            excl_features.append(feat)
    with open(ing_dir / "exclusion_zones.geojson", "w") as f:
        json.dump({"type": "FeatureCollection", "features": excl_features}, f)

    # No discrete anchors for this project — see docstring above.
    with open(ing_dir / "ecological_anchors.geojson", "w") as f:
        json.dump({"type": "FeatureCollection", "features": []}, f)

    with open(ing_dir / "candidates.geojson", "w") as f:
        json.dump({"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": aoi_fc["features"][0]["geometry"],
             "properties": {"name": "aoi", "role": "candidate", "attr_source": raw_kml.name,
                            "area_ha": pre_report["boundary_area_ha"]}}]}, f)

    grid_report = candidate_grid.run_grid_generation(project_dir, cfg)

    # --- Real spatial join: tag every tessellated cell with its real
    # client-given eco-zone, before anything downstream ever sees it. ---
    with open(ing_dir / "candidate_grid.geojson") as f:
        grid_fc = json.load(f)
    with open(pre_dir / "eco_zones_eligible.geojson") as f:
        zones_fc = json.load(f)

    grid_geoms = [shape(f["geometry"]) for f in grid_fc["features"]]
    projected_crs = crs_mod.resolve(grid_geoms[0]) if grid_geoms else None
    zone_geoms_m = []
    for zf in zones_fc["features"]:
        zone_geoms_m.append((crs_mod.to_m(shape(zf["geometry"]), projected_crs),
                             zf["properties"]["eco_zone"], zf["properties"].get("sub_zone_name")))

    n_unmatched = 0
    for cell_feat, cell_geom in zip(grid_fc["features"], grid_geoms):
        cell_m = crs_mod.to_m(cell_geom, projected_crs).centroid
        matched_zone, matched_sub = None, None
        for zg_m, zone_name, sub_name in zone_geoms_m:
            if zg_m.contains(cell_m):
                matched_zone, matched_sub = zone_name, sub_name
                break
        if matched_zone is None:
            n_unmatched += 1
        cell_feat["properties"]["eco_zone"] = matched_zone
        cell_feat["properties"]["sub_zone_name"] = matched_sub

    with open(ing_dir / "candidate_grid.geojson", "w") as f:
        json.dump(grid_fc, f)

    report = {
        "status": "ok", "preprocess": pre_report, "grid_generation": grid_report,
        "n_grid_cells": len(grid_fc["features"]), "n_cells_unmatched_to_any_zone": n_unmatched,
        "hard_exclusion_area_ha": grid_report.get("hard_exclusion_area_ha"),
        "warnings": ([f"{n_unmatched} of {len(grid_fc['features'])} candidate cells did not fall "
                     "within any real eco-zone polygon (likely the 4.08ha unaccounted-for gap area "
                     "found during preprocessing) — these cells have eco_zone=None and will not "
                     "be assigned to any EMU."] if n_unmatched else []),
    }
    with open(ing_dir / "ingestion_report.json", "w") as f:
        json.dump(report, f, indent=2)
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("kml_path")
    parser.add_argument("out_dir")
    args = parser.parse_args()
    r = run_preprocess(args.kml_path, args.out_dir)
    print(json.dumps(r, indent=2))
