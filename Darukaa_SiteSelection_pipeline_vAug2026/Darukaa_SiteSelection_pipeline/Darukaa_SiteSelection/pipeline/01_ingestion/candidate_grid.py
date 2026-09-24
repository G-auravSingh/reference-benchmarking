"""
01_ingestion / candidate_grid.py
==================================

Fixes the real gap found while building 03_emu_delineation's
segmentation_reconciliation.py: for CONTIGUOUS archetypes (conservation/
industrial) whose KML only gives a few large hand-drawn zone polygons (e.g.
Soulforest's single "Island"), reducing SEGMENT_ID over the whole polygon
throws away exactly the internal sub-structure SNIC finds. This module
tessellates the unmasked terrestrial matrix — AOI minus ecological anchors
minus exclusion zones — into small square cells BEFORE the GEE run, so
SEGMENT_ID can be computed per-cell instead of per-huge-polygon.

Ecological anchors are deliberately NOT gridded — they're already treated
as fixed, whole EMUs (client-declared ecological identity outranks an
algorithmic sub-split here, per the architecture decision on Soulforest).
Only the genuinely unclassified residual matrix gets tessellated.

Only runs for conservation/industrial archetypes — agroforestry's scattered
parcels already ARE the candidate set; a grid over empty land between farms
would be the same "fill the gap" mistake flagged elsewhere in this project.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
import crs  # noqa: E402

logger = logging.getLogger(__name__)


def _load_geoms(path: Path, projected_crs: str, role_filter: Optional[str] = None):
    """role_filter, when given, keeps only features whose `role` property
    matches — used so soft-exclusion zones (e.g. a zone that's only
    PARTIALLY built-up) are NOT removed from the tessellated grid
    entirely, only the hard-excluded portion within it. Soft
    zones now get tessellated like anywhere else; the real BuiltUp_Pct
    value each cell gets back from GEE (already a hard filter in
    02_covariates) is what actually decides, pixel by pixel, which cells
    in a soft-exclusion zone survive — not a blanket polygon-level guess."""
    if not path.exists():
        return []
    with open(path) as f:
        fc = json.load(f)
    geoms = []
    for feat in fc["features"]:
        if role_filter and feat["properties"].get("role") != role_filter:
            continue
        geoms.append(crs.to_m(shape(feat["geometry"]), projected_crs))
    return geoms


def generate_grid(
    aoi_geom_m, exclude_geoms_m: List, cell_size_m: float,
    min_coverage_frac: float = 0.5,
) -> List[Dict[str, Any]]:
    """Returns a list of {geometry (shapely, metres), area_m2} cells
    covering aoi_geom_m minus the union of exclude_geoms_m.

    Each cell is clipped against the valid (non-excluded) region. If
    clipping splits a cell into multiple disconnected pieces — an
    exclusion zone or eco-zone boundary cutting through its middle — only
    the largest connected piece is kept, and its own area (not the
    combined area of all pieces) is checked against min_coverage_frac.
    Every candidate this function returns is guaranteed to be a single,
    genuinely connected polygon representing one coherent deployable
    location, never a MultiPolygon assembled from unrelated slivers.

    A cell is dropped entirely if its surviving area (after the above)
    falls below min_coverage_frac of its nominal size — this avoids
    keeping near-degenerate slivers at the AOI/exclusion boundary that
    would be meaningless for GEE mode-reduction anyway."""
    excluded_union = unary_union(exclude_geoms_m) if exclude_geoms_m else None
    valid_region = aoi_geom_m.difference(excluded_union) if excluded_union else aoi_geom_m

    minx, miny, maxx, maxy = aoi_geom_m.bounds
    nominal_area = cell_size_m * cell_size_m
    cells = []
    x = minx
    while x < maxx:
        y = miny
        while y < maxy:
            cell = box(x, y, x + cell_size_m, y + cell_size_m)
            if cell.intersects(valid_region):
                clipped = cell.intersection(valid_region)
                # A cell clipped against an exclusion zone or eco-zone
                # boundary that cuts through its middle can survive as a
                # MultiPolygon — two or more disconnected slivers whose
                # areas sum above the coverage threshold even though
                # neither individually represents one coherent, deployable
                # spot. Keep only the largest connected piece, and check
                # THAT piece's own area against the threshold, not the
                # combined total — every stored candidate must be a
                # single, genuinely connected polygon.
                if clipped.geom_type == "MultiPolygon":
                    clipped = max(clipped.geoms, key=lambda g: g.area)
                if clipped.area >= min_coverage_frac * nominal_area:
                    cells.append({"geometry": clipped, "area_m2": clipped.area})
            y += cell_size_m
        x += cell_size_m
    return cells


def run_grid_generation(project_dir: str | Path, cfg: Dict[str, Any]) -> Dict[str, Any]:
    project_dir = Path(project_dir)
    ing_dir = project_dir / "outputs" / "01_ingestion"
    aoi_path = ing_dir / "aoi_boundary.geojson"

    if not aoi_path.exists():
        logger.warning(
            "No aoi_boundary.geojson — cannot generate a candidate grid "
            "without a known AOI extent. Set aoi_boundary_placemark_names "
            "in config.yaml or check the detect_aoi_boundary heuristic.")
        return {"status": "skipped_no_aoi", "n_cells": 0}

    with open(aoi_path) as f:
        aoi_fc = json.load(f)
    aoi_geom_ll = shape(aoi_fc["features"][0]["geometry"])
    projected_crs = crs.resolve(aoi_geom_ll)
    aoi_geom_m = crs.to_m(aoi_geom_ll, projected_crs)

    anchor_geoms_m = _load_geoms(ing_dir / "ecological_anchors.geojson", projected_crs)
    hard_exclusion_geoms_m = _load_geoms(ing_dir / "exclusion_zones.geojson", projected_crs,
                                          role_filter="exclusion_hard")
    # Anchors are tessellated too, even though they're already fixed EMUs
    # that never get split into multiple EMUs — "don't split this" and
    # "don't tessellate it at all" are different things, and skipping
    # tessellation entirely would mean an anchor never gets real per-cell
    # covariate data
    # or an actual deployable candidate position, even though they're real
    # habitat that will need a device in it. Anchors are now tessellated
    # like anywhere else; segmentation_reconciliation.py assigns every
    # resulting tile inside an anchor DIRECTLY to that anchor's EMU
    # (skipping SEGMENT_ID grouping for those tiles), so the anchor still
    # never gets split into multiple EMUs — it just also gets real
    # candidate points now.
    all_excluded_m = hard_exclusion_geoms_m

    cell_size = cfg["contiguous_grid_cell_size_m"]
    cells = generate_grid(aoi_geom_m, all_excluded_m, cell_size)

    features = []
    id_prefix = cfg.get("id_prefix", "T")
    for i, c in enumerate(cells):
        geom_ll = crs.to_ll(c["geometry"], projected_crs)
        internal_name = f"grid_{i:05d}"
        features.append({
            "type": "Feature",
            "geometry": mapping(geom_ll),
            "properties": {
                # "name" MUST stay as the internal grid_XXXXX form — it's
                # the join key already baked into any GEE asset/CSV a
                # project has already uploaded/run against. Renaming it
                # here would silently break that match for every existing
                # project. "display_name" is the client-facing form
                # (matching the Tata Motors "PMP-T060" convention) — used
                # only in map popups / reports, never for joining.
                "name": internal_name,
                "display_name": f"{id_prefix}{i + 1:04d}",
                "role": "candidate_grid_cell",
                "area_ha": round(c["area_m2"] / 10_000.0, 5),
            },
        })

    out_path = ing_dir / "candidate_grid.geojson"
    with open(out_path, "w") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f)

    soft_exclusion_geoms_m = _load_geoms(ing_dir / "exclusion_zones.geojson", projected_crs,
                                          role_filter="exclusion_soft")
    aoi_area_ha = aoi_geom_m.area / 10_000.0
    hard_exclusion_area_ha = sum(g.area for g in hard_exclusion_geoms_m) / 10_000.0
    soft_exclusion_area_ha = sum(g.area for g in soft_exclusion_geoms_m) / 10_000.0
    anchor_area_ha = sum(g.area for g in anchor_geoms_m) / 10_000.0
    grid_area_ha = sum(c["area_m2"] for c in cells) / 10_000.0
    # Matrix = AOI minus HARD exclusions only. Anchors are no longer
    # subtracted — they're tessellated too now (see the fix note above);
    # anchor_area_ha is still reported below purely for transparency about
    # how much of the tessellated area falls inside an anchor vs. the
    # general matrix, not because it's excluded from tessellation.
    matrix_area_ha = aoi_area_ha - hard_exclusion_area_ha

    report = {
        "status": "ok",
        "n_cells": len(cells),
        "cell_size_m": cell_size,
        "aoi_area_ha": round(aoi_area_ha, 3),
        "anchor_area_ha": round(anchor_area_ha, 3),
        "hard_exclusion_area_ha": round(hard_exclusion_area_ha, 3),
        "soft_exclusion_area_ha_included_in_matrix": round(soft_exclusion_area_ha, 3),
        "matrix_area_ha_to_tessellate": round(matrix_area_ha, 3),
        "grid_area_ha_covered": round(grid_area_ha, 3),
        "coverage_of_matrix_pct": round(100 * grid_area_ha / matrix_area_ha, 1) if matrix_area_ha > 0 else 0.0,
    }
    with open(ing_dir / "candidate_grid_report.json", "w") as f:
        json.dump(report, f, indent=2)

    logger.info("Candidate grid: %d cells @ %dm, covering %.1f/%.1f ha of matrix (%.1f%%)",
                report["n_cells"], cell_size, grid_area_ha, matrix_area_ha,
                report["coverage_of_matrix_pct"])
    return report


if __name__ == "__main__":
    import argparse
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
    import config_schema
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    args = parser.parse_args()
    cfg = config_schema.load_config(Path(args.project_dir) / "config.yaml")
    run_grid_generation(args.project_dir, cfg)
