"""
01_ingestion / kml_ingest.py
============================

Stage 1 of the unified pipeline. Turns raw client KML(s) into a normalized,
attributed, classified set of candidate polygons — the single input every
downstream stage (02_covariates onward) depends on.

What this stage does, in order:
  1. Parse every KML in projects/<NAME>/raw/ (common/kml_utils.py handles
     the schema differences between clients — see that module's docstring).
  2. Resolve a projected CRS from the data itself (common/crs.py).
  3. Repair invalid geometries (buffer(0)); drop zero-area / unparseable ones,
     but COUNT and REPORT every drop — never silent.
  4. Classify every placemark into exactly one of:
       - "aoi_boundary"          the overall site outline (conservation/
                                  industrial archetypes only — agroforestry
                                  has no such placemark, see below)
       - "ecological_anchor"     client-identified real ecological feature
                                  (e.g. Soulforest's Fruit Forest, Wetland)
       - "exclusion_hard"        infrastructure, dropped from candidate set
       - "exclusion_soft"        provisionally excluded, pixel-level review
                                  deferred to 02_covariates
       - "candidate"             a normal stratification/EMU input tile
  5. Apply the project's attribute crosswalk (raw KML field name -> our
     canonical name), so downstream stages never touch a client's raw
     column names. Reports crosswalk COVERAGE — which canonical fields were
     actually found — since this varies a lot by client (see CHANGELOG:
     GV has no `admin_block`; Soova has no analogue of GV's `Submission`).
  6. Cross-check any client-reported area_ha against geometry-computed area;
     flag mismatches > 5% rather than silently trusting either source.
  7. Write: candidates.geojson, exclusion_zones.geojson, aoi_boundary.geojson
     (if any), ingestion_report.json.

AOI-boundary auto-detection (step 4) is a heuristic, not a certainty: the
largest candidate polygon is checked for whether it geometrically contains
the centroids of most other candidate polygons. If so, it's almost
certainly a project-outline placemark, not a stratification tile, and is
pulled out. This only fires for single/few-polygon archetypes — with
hundreds of small farm parcels (agroforestry) there is no such placemark and
the check correctly finds nothing. A project can also force this via
`aoi_boundary_placemark_names` in config.yaml if the heuristic ever picks
wrong — this is logged clearly in the ingestion report either way.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

from shapely.geometry import mapping, shape
from shapely.validation import make_valid

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for candidate_grid.py (same dir)
import config_schema  # noqa: E402
import crs             # noqa: E402
import kml_utils        # noqa: E402

logger = logging.getLogger(__name__)


def _match_canonical(raw_attrs: Dict[str, str], crosswalk: Dict[str, List[str]]) -> Dict[str, Any]:
    """Case-insensitive match of raw KML field names against the crosswalk.
    Returns {canonical_name: value} for every canonical field actually found."""
    lower_raw = {k.lower(): v for k, v in raw_attrs.items()}
    out = {}
    for canonical, aliases in crosswalk.items():
        for alias in aliases:
            if alias.lower() in lower_raw:
                out[canonical] = lower_raw[alias.lower()]
                break
    return out


def _classify_exclusion(name: str, cfg: Dict[str, Any]) -> str | None:
    name_lower = name.lower()
    if name in cfg["exclusion_placemark_names"]:
        return "exclusion_hard"
    for term in cfg["hard_exclusion_terms"]:
        if term in name_lower:
            return "exclusion_hard"
    for term in cfg["soft_exclusion_terms"]:
        if term in name_lower:
            return "exclusion_soft"
    return None


def _repair_geometry(geom):
    """Returns (repaired_geom, was_invalid: bool, is_usable: bool)."""
    if geom is None:
        return None, False, False
    if geom.is_valid:
        area = getattr(geom, "area", 0.0)
        return geom, False, area > 0
    try:
        fixed = make_valid(geom)
        area = getattr(fixed, "area", 0.0)
        return fixed, True, area > 0
    except Exception as e:
        logger.warning("Geometry repair failed for a placemark: %s", e)
        return geom, True, False


def detect_aoi_boundary(candidates: List[Dict[str, Any]], projected_crs: str) -> int | None:
    """Returns the list-index of the placemark judged to be the overall AOI
    boundary, or None if no candidate qualifies. Heuristic: largest polygon
    whose area exceeds the combined area of ALL other candidates, and which
    contains the centroids of at least 80% of them. Both conditions must
    hold — this is deliberately conservative so it does not fire on
    agroforestry's many same-scale farm parcels."""
    if len(candidates) < 2:
        return None
    polys = [(i, c) for i, c in enumerate(candidates) if c["geometry"] is not None
             and c["geometry"].geom_type in ("Polygon", "MultiPolygon")]
    if len(polys) < 2:
        return None

    areas = [(i, crs.to_m(c["geometry"], projected_crs).area) for i, c in polys]
    areas.sort(key=lambda t: t[1], reverse=True)
    biggest_idx, biggest_area = areas[0]
    other_area_sum = sum(a for i, a in areas[1:])
    if other_area_sum == 0 or biggest_area < other_area_sum:
        return None

    biggest_geom_m = crs.to_m(candidates[biggest_idx]["geometry"], projected_crs)
    contained = 0
    for i, c in polys:
        if i == biggest_idx:
            continue
        centroid_m = crs.to_m(c["geometry"], projected_crs).centroid
        if biggest_geom_m.contains(centroid_m):
            contained += 1
    frac_contained = contained / (len(polys) - 1)
    if frac_contained >= 0.8:
        return biggest_idx
    return None


def run_ingestion(project_dir: str | Path) -> Dict[str, Any]:
    project_dir = Path(project_dir)
    cfg = config_schema.load_config(project_dir / "config.yaml")

    raw_dir = project_dir / "raw"
    kml_files = sorted(raw_dir.glob("*.kml"))
    if not kml_files:
        raise FileNotFoundError(f"No .kml files found in {raw_dir}")

    projected_crs = crs.resolve_from_kml_folder(kml_files, cfg.get("projected_crs_override"))
    logger.info("Resolved projected CRS: %s", projected_crs)

    all_records = []
    for kf in kml_files:
        all_records.extend(kml_utils.parse_kml(kf))

    report = {
        "project_name": cfg["project_name"],
        "client_name": cfg["client_name"],
        "archetype": cfg["archetype"],
        "projected_crs": projected_crs,
        "kml_files": [str(f.name) for f in kml_files],
        "n_placemarks_total": len(all_records),
        "n_geometry_repaired": 0,
        "n_geometry_dropped_unusable": 0,
        "n_exclusion_hard": 0,
        "n_exclusion_soft": 0,
        "n_ecological_anchor": 0,
        "n_aoi_boundary": 0,
        "n_candidates": 0,
        "attribute_coverage": {},   # canonical_name -> count of candidates having it
        "area_mismatches_gt_5pct": [],
        "warnings": [],
    }

    classified = []
    for rec in all_records:
        geom, was_invalid, usable = _repair_geometry(rec["geometry"])
        if was_invalid:
            report["n_geometry_repaired"] += 1
        if not usable:
            report["n_geometry_dropped_unusable"] += 1
            report["warnings"].append(
                f"Dropped unusable geometry: placemark '{rec['name']}' "
                f"(index {rec['placemark_index']}, source geometry_type={rec['geometry_type']})")
            continue

        name = rec["name"]
        exclusion_status = _classify_exclusion(name, cfg)
        is_anchor = name in cfg["ecological_anchor_placemark_names"]

        canonical_attrs = _match_canonical(rec["attrs"], cfg["attribute_crosswalk"])

        # District corrections use a k-nearest-neighbour geographic vote
        # against every other confidently-tagged parcel, not a
        # bounding-box heuristic, since a district's own real coordinate
        # range can overlap a neighbouring district's. Only applied where the evidence was
        # unambiguous (6+ of 8 nearest real neighbours agreeing, all under
        # ~1.5km) — a client-reported batch of "28 mistagged parcels" was
        # checked the same way and found NOT supported by the data, so
        # deliberately left untouched.
        district_corrections = cfg.get("district_corrections") or {}
        if name in district_corrections:
            # REAL BUG FIXED HERE, caught by checking actual output rather
            # than trusting the logic: canonical_attrs' own internal keys
            # are unprefixed ("admin_district") — the "attr_" prefix is
            # only added later, by _write_geojson's f"attr_{k}" step. Using
            # "attr_admin_district" here created a spurious NEW key that
            # got double-prefixed to "attr_attr_admin_district" downstream,
            # leaving the real "attr_admin_district" field untouched and
            # still empty.
            canonical_attrs["admin_district"] = district_corrections[name]

        classified.append({
            "name": name,
            "geometry": geom,
            "geometry_type": geom.geom_type,
            "raw_attrs": rec["attrs"],
            "attrs": canonical_attrs,
            "attr_source": rec["attr_source"],
            "exclusion_status": exclusion_status,
            "is_ecological_anchor": is_anchor,
            "role": None,  # filled in below
        })

    # AOI boundary detection runs only among placemarks not already
    # classified as exclusion/anchor (an anchor or exclusion zone is never
    # mistaken for the outer boundary).
    boundary_pool = [c for c in classified
                      if c["exclusion_status"] is None and not c["is_ecological_anchor"]]
    forced_boundary_names = set(cfg["aoi_boundary_placemark_names"])
    aoi_idx_in_pool = None
    if forced_boundary_names:
        for i, c in enumerate(boundary_pool):
            if c["name"] in forced_boundary_names:
                aoi_idx_in_pool = i
                break
    else:
        aoi_idx_in_pool = detect_aoi_boundary(boundary_pool, projected_crs)

    aoi_boundary_name = boundary_pool[aoi_idx_in_pool]["name"] if aoi_idx_in_pool is not None else None

    for c in classified:
        if c["exclusion_status"] == "exclusion_hard":
            c["role"] = "exclusion_hard"
            report["n_exclusion_hard"] += 1
        elif c["exclusion_status"] == "exclusion_soft":
            c["role"] = "exclusion_soft"
            report["n_exclusion_soft"] += 1
        elif c["is_ecological_anchor"]:
            c["role"] = "ecological_anchor"
            report["n_ecological_anchor"] += 1
        elif aoi_boundary_name is not None and c["name"] == aoi_boundary_name:
            c["role"] = "aoi_boundary"
            report["n_aoi_boundary"] += 1
        else:
            c["role"] = "candidate"
            report["n_candidates"] += 1

    # Attribute coverage + area cross-check, computed only over candidates
    # (the population that actually feeds 03_emu_delineation).
    candidate_records = [c for c in classified if c["role"] == "candidate"]
    for canonical in cfg["attribute_crosswalk"]:
        n_found = sum(1 for c in candidate_records if canonical in c["attrs"])
        report["attribute_coverage"][canonical] = {
            "n_found": n_found,
            "n_candidates": len(candidate_records),
            "pct": round(100 * n_found / len(candidate_records), 1) if candidate_records else 0.0,
        }

    for c in candidate_records:
        reported = c["attrs"].get("area_ha_reported")
        if reported is None:
            continue
        try:
            reported_ha = float(reported)
        except ValueError:
            continue
        computed_ha = crs.to_m(c["geometry"], projected_crs).area / 10_000.0
        if reported_ha > 0:
            pct_diff = abs(computed_ha - reported_ha) / reported_ha * 100
            if pct_diff > 5.0:
                report["area_mismatches_gt_5pct"].append({
                    "name": c["name"],
                    "reported_ha": round(reported_ha, 4),
                    "computed_ha": round(computed_ha, 4),
                    "pct_diff": round(pct_diff, 1),
                })
        c["attrs"]["area_ha_computed"] = round(computed_ha, 4)

    # Which stratification_attributes were REQUESTED in config but are not
    # actually present in this project's data — flagged plainly rather than
    # silently ignored, per the new instruction to use plantation
    # type/block/year when available.
    requested = cfg.get("stratification_attributes") or []
    unavailable = [a for a in requested
                   if report["attribute_coverage"].get(a, {}).get("n_found", 0) == 0]
    if unavailable:
        report["warnings"].append(
            f"stratification_attributes requested but not found in any candidate: "
            f"{unavailable}. They will not be used as clustering features in 03.")

    # --- write outputs ------------------------------------------------
    out_dir = project_dir / "outputs" / "01_ingestion"
    out_dir.mkdir(parents=True, exist_ok=True)

    _write_geojson(out_dir / "candidates.geojson", candidate_records, projected_crs)
    _write_geojson(out_dir / "exclusion_zones.geojson",
                    [c for c in classified if c["role"] in ("exclusion_hard", "exclusion_soft")],
                    projected_crs)
    _write_geojson(out_dir / "ecological_anchors.geojson",
                    [c for c in classified if c["role"] == "ecological_anchor"],
                    projected_crs)
    aoi_records = [c for c in classified if c["role"] == "aoi_boundary"]
    if aoi_records:
        _write_geojson(out_dir / "aoi_boundary.geojson", aoi_records, projected_crs)

    with open(out_dir / "ingestion_report.json", "w") as f:
        json.dump(report, f, indent=2)

    logger.info(
        "Ingestion complete: %d candidates, %d exclusion(hard), %d exclusion(soft), "
        "%d anchors, %s boundary, %d geometry issues",
        report["n_candidates"], report["n_exclusion_hard"], report["n_exclusion_soft"],
        report["n_ecological_anchor"],
        "1" if aoi_boundary_name else "0",
        report["n_geometry_repaired"] + report["n_geometry_dropped_unusable"])

    # Contiguous archetypes need a dense candidate grid for meaningful
    # per-cell SEGMENT_ID resolution downstream (see candidate_grid.py
    # docstring for why coarse KML zone polygons alone aren't enough).
    # Runs automatically here so a project never needs a separate manual
    # step — one call to run_ingestion() produces everything 02_covariates
    # needs to build its GEE run instructions correctly. Written into the
    # SAME report file (re-dumped below) rather than a second file, so
    # there's one authoritative ingestion report per project, not two.
    if cfg["archetype"] in ("conservation", "industrial"):
        import candidate_grid
        report["candidate_grid"] = candidate_grid.run_grid_generation(project_dir, cfg)

        # Real, client-declared sub-area position bias (e.g. Soulforest's
        # Wetland/Island: one of two audiomoth devices should be on the
        # more accessible island) — tags
        # every candidate cell with which named sub-area polygon (if any)
        # it falls within, so 03b_position_scoring can bias its real
        # spacing-verified selection toward it later. A no-op for every
        # project that doesn't declare position_pool_named_subarea_bias.
        subarea_bias_cfg = cfg.get("position_pool_named_subarea_bias") or {}
        if subarea_bias_cfg:
            _tag_named_subareas(project_dir, cfg, subarea_bias_cfg, projected_crs)

        with open(out_dir / "ingestion_report.json", "w") as f:
            json.dump(report, f, indent=2)

    return report


def _tag_named_subareas(
    project_dir: Path, cfg: Dict[str, Any], subarea_bias_cfg: Dict[str, Any], projected_crs: str,
) -> None:
    """Spatial-joins candidate_grid.geojson against the raw KML's own named
    sub-area placemarks (e.g. "Island" within the "Wetland" anchor) —
    tags each candidate with in_named_subarea=True/False. Reads the raw
    KML directly rather than any already-processed ingestion output,
    since a sub-area like Island is deliberately not an anchor or
    exclusion zone in its own right (see this project's config comment) —
    it only matters for this one, narrow purpose."""
    raw_kml = next((project_dir / "raw").glob("*.kml"), None)
    if raw_kml is None:
        return
    import geopandas as gpd
    import warnings
    warnings.filterwarnings("ignore")
    gdf = gpd.read_file(raw_kml, driver="KML")
    name_col = "Name" if "Name" in gdf.columns else "name"

    subarea_geoms_m: Dict[str, Any] = {}
    for cfg_entry in subarea_bias_cfg.values():
        subarea_name = cfg_entry["subarea_placemark_name"]
        if subarea_name in subarea_geoms_m:
            continue
        match = gdf[gdf[name_col] == subarea_name]
        if len(match) == 0:
            logger.warning("position_pool_named_subarea_bias declares %r but no matching "
                           "placemark was found in the raw KML — skipped.", subarea_name)
            continue
        subarea_geoms_m[subarea_name] = crs.to_m(match.geometry.iloc[0], projected_crs)

    if not subarea_geoms_m:
        return

    grid_path = project_dir / "outputs" / "01_ingestion" / "candidate_grid.geojson"
    with open(grid_path) as f:
        grid_fc = json.load(f)
    for feat in grid_fc["features"]:
        c = crs.to_m(shape(feat["geometry"]), projected_crs).centroid
        matched = next((name for name, geom in subarea_geoms_m.items() if geom.contains(c)), None)
        feat["properties"]["named_subarea"] = matched
    with open(grid_path, "w") as f:
        json.dump(grid_fc, f)
    n_tagged = sum(1 for f in grid_fc["features"] if f["properties"].get("named_subarea"))
    logger.info("Named sub-area tagging: %d candidate(s) tagged across %d sub-area(s) (%s)",
                n_tagged, len(subarea_geoms_m), list(subarea_geoms_m.keys()))



def _write_geojson(path: Path, records: List[Dict[str, Any]], projected_crs: str) -> None:
    features = []
    for r in records:
        geom = r["geometry"]
        area_ha = round(crs.to_m(geom, projected_crs).area / 10_000.0, 4) if geom else None
        props = {
            "name": r["name"],
            "role": r["role"],
            "attr_source": r["attr_source"],
            "area_ha": area_ha,
            **{f"attr_{k}": v for k, v in r["attrs"].items()},
        }
        features.append({
            "type": "Feature",
            "geometry": mapping(geom) if geom else None,
            "properties": props,
        })
    fc = {"type": "FeatureCollection", "features": features}
    with open(path, "w") as f:
        json.dump(fc, f)


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    args = parser.parse_args()
    run_ingestion(args.project_dir)
