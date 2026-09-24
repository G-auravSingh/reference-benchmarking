"""
build_crosswalk.py — TataMotors_Pimpri
=========================================

Real, direct spatial join of every already-deployed Phase 01 position
(13-27 Aug 2026, under the OLD SEG01-10 segmentation) against the NEW,
corrected boundary/exclusion/eco-zone structure — so the already-collected
one-time-per-season data (hydro, camera, water/soil chemistry) stays
correctly geo-attributed going forward, and so the audiomoth history is
readable against real zone names, not just an old-scheme label with no
current meaning.

This does NOT resume or extend the old SEG-based deployment — confirmed
directly (Aug 2026) that SEG01-10 has zero relationship to any real
ecological concept. It is a real, honest accounting of where past data
physically sits relative to the new design, nothing more.
"""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point
import warnings
warnings.filterwarnings("ignore")


def run_crosswalk(project_dir: str | Path) -> dict:
    project_dir = Path(project_dir)
    hist_path = project_dir / "historical" / "field_recee_phase01.json"
    pre_dir = project_dir / "outputs_preprocess"

    with open(hist_path) as f:
        hist = json.load(f)
    with open(pre_dir / "aoi_boundary.geojson") as f:
        boundary_fc = json.load(f)
    with open(pre_dir / "exclusion_mask.geojson") as f:
        exclusion_fc = json.load(f)
    with open(pre_dir / "eco_zones_eligible.geojson") as f:
        zones_fc = json.load(f)

    boundary_gdf = gpd.GeoDataFrame.from_features(boundary_fc["features"], crs="EPSG:4326")
    exclusion_gdf = gpd.GeoDataFrame.from_features(exclusion_fc["features"], crs="EPSG:4326")
    zones_gdf = gpd.GeoDataFrame.from_features(zones_fc["features"], crs="EPSG:4326")
    projected_crs = boundary_gdf.estimate_utm_crs()
    boundary_m = boundary_gdf.to_crs(projected_crs).geometry.iloc[0]
    exclusion_m = exclusion_gdf.to_crs(projected_crs).geometry.union_all() if len(exclusion_gdf) else None
    zones_m = zones_gdf.to_crs(projected_crs)

    def classify(lat: float, lng: float) -> dict:
        pt_ll = gpd.GeoSeries([Point(lng, lat)], crs="EPSG:4326")
        pt_m = pt_ll.to_crs(projected_crs).iloc[0]
        inside_boundary = boundary_m.contains(pt_m)
        inside_exclusion = bool(exclusion_m and exclusion_m.contains(pt_m))
        matched_zone = None
        for _, row in zones_m.iterrows():
            if row.geometry.contains(pt_m):
                matched_zone = row["eco_zone"]
                break
        return {
            "inside_corrected_boundary": inside_boundary,
            "inside_exclusion_mask": inside_exclusion,
            "new_eco_zone": matched_zone,
            "status": (
                "OUTSIDE corrected boundary" if not inside_boundary else
                "inside exclusion zone (buildings/infrastructure/water buffer)" if inside_exclusion else
                f"real zone: {matched_zone}" if matched_zone else
                "inside boundary but unmatched to any usable zone (gap area)"
            ),
        }

    result = {"streams": {}}
    for stream_name, points in hist.items():
        rows = []
        for p in points:
            info = classify(p["lat"], p["lng"])
            rows.append({**p, **info})
        result["streams"][stream_name] = rows

    n_outside = sum(1 for s in result["streams"].values() for r in s if not r["inside_corrected_boundary"])
    n_in_exclusion = sum(1 for s in result["streams"].values() for r in s if r["inside_exclusion_mask"])
    n_unmatched = sum(1 for s in result["streams"].values() for r in s
                      if r["inside_corrected_boundary"] and not r["inside_exclusion_mask"]
                      and not r["new_eco_zone"])
    result["summary"] = {
        "n_total_positions": sum(len(s) for s in result["streams"].values()),
        "n_outside_corrected_boundary": n_outside,
        "n_inside_exclusion_mask": n_in_exclusion,
        "n_inside_boundary_but_unmatched_zone": n_unmatched,
    }

    out_path = project_dir / "historical" / "crosswalk_report.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    return result


if __name__ == "__main__":
    import sys
    r = run_crosswalk(sys.argv[1] if len(sys.argv) > 1 else ".")
    print(json.dumps(r["summary"], indent=2))
