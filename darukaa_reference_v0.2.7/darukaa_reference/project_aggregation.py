"""
Multi-Tile Project Aggregation (agroforestry / large multi-parcel AOIs)
=========================================================================

WHY THIS EXISTS
----------------
darukaa_reference's Tier-2 reference selection buffers around a site's CENTROID. That is
geographically meaningless for an AOI that spans hundreds of kilometres and hundreds of
scattered smallholder parcels (agroforestry is the canonical case) — one centroid over a
200 km scatter corresponds to no real landscape near any actual parcel, and Pipeline.run()
would otherwise treat every placemark as its own separate mini-site (see
_dissolve_tile_to_geojson below for why that matters).

Such an AOI must be TILED FIRST — grouped into a manageable number of ecologically-local
assessment units (e.g. via DBSCAN on parcel centroids) — with darukaa_reference run once
per tile. Tiling itself is upstream of this module (it depends on parcel geometry only,
not on anything ecological darukaa_reference computes, so it can live wherever is most
convenient — see the README section "Multi-tile / agroforestry projects"). What THIS
module owns, self-contained, with no dependency on any other repository:

  1. Running each tile through the exact same single-site Pipeline used for a
     conservation project (every placemark within a tile's KML is dissolved into one
     geometry first — a tile IS one assessment unit).
  2. Combining tile-level results into ONE project-level profile, NON-COMPENSATORILY.

THE AGGREGATION RULE (the crucial part)
-----------------------------------------
For every SCORED indicator, the project-level signal is the WORST TILE'S signed
benchmark — literally the minimum across tiles (after each indicator's own
higher_is_better orientation is already applied upstream in estimators.py, so "more
negative = worse" is a uniform convention across every indicator, state or pressure).
This is the exact same limiting-factor principle scoring.py already applies across
subdimensions within a component and across components within a site — applied one
level further, across tiles. A project cannot look good by averaging over a cluster of
degraded parcels; the worst parcel sets the ceiling on the honest answer, and that tile
is named.

The combined worst-tile-per-indicator values are then fed into scoring.build_site_profile
— the SAME profile-first, non-compensatory engine a single site uses — so the project
"is" a site profile in every downstream sense: same limiting-factor components, same
condition x pressure matrix, same sensitivity flag, same framing block. No parallel
aggregation logic is invented at this level; only the INPUT to the existing engine
differs (worst-tile benchmarks instead of one tile's own benchmarks).

Two secondary, clearly-labelled, non-primary numbers are also reported per indicator for
transparency: an area-weighted GEOMETRIC mean of the tiles' normalised scores (still
penalises low tiles, just less severely than the worst-tile headline), and a plain
area-weighted MEAN of the raw indicator VALUE (a physically additive quantity — e.g.
"average canopy cover across the project" — genuinely different in kind from the
condition-relative-to-reference score, and reported separately so the two are never
conflated).

WORKS FOR ANY ARCHETYPE: a single-tile "project" (i.e. a conservation site) is the
trivial case here and produces the same numbers as calling Pipeline.run() directly.
"""
from __future__ import annotations

import json
import logging
import tempfile
import dataclasses
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import geopandas as gpd
import numpy as np

from darukaa_reference.config import Config
from darukaa_reference.registry import IndicatorRegistry
from darukaa_reference.pipeline import Pipeline
from darukaa_reference.site_loader import SiteLoader
from darukaa_reference import scoring, html_report

logger = logging.getLogger(__name__)

# Global equal-area projection for area computation — deliberately NOT a UTM zone (which
# would need per-project selection) so this works identically for any project, anywhere.
_EQUAL_AREA_CRS = "EPSG:6933"  # NSIDC EASE-Grid 2.0 Global


def _dissolve_tile_to_geojson(tile_path: str, tile_label: str,
                              tmp_dir: str) -> Tuple[str, float]:
    """Merge every placemark in a tile's KML/GeoJSON/shapefile into ONE geometry.

    Why this is necessary: Pipeline.run() treats every row in the loaded GeoDataFrame as
    its own separate site (this is correct and desired for a conservation KML with one
    or a few real, distinct sites — it is NOT what you want for a tile containing dozens
    or hundreds of parcels that together constitute ONE assessment unit). Without this
    dissolve step, running Pipeline.run() on a raw multi-parcel tile KML would silently
    produce N tiny per-parcel results instead of one tile-level result.

    Returns (path to a 1-feature GeoJSON usable as a Pipeline site_path, area in hectares
    — the SUM of individual parcel areas, which equals the union's area for the normal
    case of non-overlapping farm/forest parcels, and is simpler and more robust than
    computing area from a unioned, possibly-multi-part geometry).
    """
    gdf = SiteLoader().load(tile_path)
    if gdf.empty:
        raise ValueError(f"Tile '{tile_label}' ({tile_path}) contains no geometries.")

    area_ha = float(gdf.to_crs(_EQUAL_AREA_CRS).area.sum() / 10_000.0)

    dissolved_geom = gdf.geometry.unary_union
    out = gpd.GeoDataFrame({"site_id": [tile_label], "name": [tile_label]},
                           geometry=[dissolved_geom], crs="EPSG:4326")
    out_path = str(Path(tmp_dir) / f"{tile_label}.geojson")
    out.to_file(out_path, driver="GeoJSON")
    return out_path, area_ha


def _normalize_value(value: Optional[float], estimator: str) -> Optional[float]:
    return scoring.normalize(value, estimator)


def aggregate_tiles_noncompensatory(tile_reports: Dict[str, Dict],
                                    tile_areas_ha: Dict[str, float],
                                    registry: IndicatorRegistry,
                                    seed_kernel: bool = False,
                                    seed_delta: float = 0.5) -> Dict:
    """Combine N tile-level report dicts into ONE project-level profile.

    tile_reports  : {tile_label: report_dict}, each as returned by Pipeline.run() /
                    ReportGenerator.generate() for that tile.
    tile_areas_ha : {tile_label: area_ha}.

    Returns {"project_profile", "multi_tile_summary", "combined_benchmarks"}.
    See module docstring for the aggregation rule.
    """
    scored_specs = {s.name: s for s in registry.scored()}
    per_indicator_summary: Dict[str, Dict] = {}
    combined_benchmarks: List[Dict] = []

    for ind_name, spec in scored_specs.items():
        tile_values = []   # (tile_label, benchmark, estimator, site_value)
        for tile_label, rep in tile_reports.items():
            row = next((r for r in rep.get("scorecard", []) if r.get("indicator") == ind_name), None)
            if row is None or row.get("tier2_benchmark") is None:
                continue
            tile_values.append((tile_label, row["tier2_benchmark"],
                               row.get("tier2_benchmark_estimator") or "robust_z",
                               row.get("site_value")))

        if not tile_values:
            per_indicator_summary[ind_name] = {
                "status": "no_tile_had_data",
                "n_tiles_with_data": 0,
            }
            continue

        # --- PRIMARY: worst tile (limiting factor, applied across tiles) ---
        worst_label, worst_value, worst_estimator, _ = min(tile_values, key=lambda t: t[1])

        # --- SECONDARY: area-weighted geometric mean of normalised scores (context) ---
        norm_vals, weights = [], []
        raw_vals, raw_weights = [], []
        for label, bench, est, site_val in tile_values:
            area = tile_areas_ha.get(label, 0.0) or 1e-6  # avoid zero-weight collapse
            nv = _normalize_value(bench, est)
            if nv is not None:
                norm_vals.append(nv); weights.append(area)
            if site_val is not None:
                raw_vals.append(site_val); raw_weights.append(area)

        geomean = scoring.geometric_mean(norm_vals) if norm_vals else None
        # weighted arithmetic mean (context only, never the headline)
        area_weighted_mean_norm = (
            float(np.average(norm_vals, weights=weights)) if norm_vals else None)
        area_weighted_mean_site_value = (
            float(np.average(raw_vals, weights=raw_weights)) if raw_vals else None)

        per_indicator_summary[ind_name] = {
            "status": "ok",
            "construct": spec.construct,
            "subdimension": spec.subdimension,
            "worst_tile": worst_label,
            "worst_tile_benchmark": round(worst_value, 4),
            "area_weighted_geomean_normalised": (round(geomean, 4) if geomean is not None else None),
            "area_weighted_mean_normalised_context": (
                round(area_weighted_mean_norm, 4) if area_weighted_mean_norm is not None else None),
            "area_weighted_mean_site_value_context": (
                round(area_weighted_mean_site_value, 4)
                if area_weighted_mean_site_value is not None else None),
            "n_tiles_with_data": len(tile_values),
            "n_tiles_total": len(tile_reports),
        }

        combined_benchmarks.append({
            "name": ind_name, "construct": spec.construct, "subdimension": spec.subdimension,
            "value": worst_value, "estimator": worst_estimator,
        })

    project_profile = scoring.build_site_profile(
        combined_benchmarks, seed_kernel=seed_kernel, seed_delta=seed_delta)

    return {
        "project_profile": project_profile,
        "multi_tile_summary": {
            "per_indicator": per_indicator_summary,
            "n_tiles": len(tile_reports),
            "tile_areas_ha": dict(tile_areas_ha),
            "total_area_ha": round(sum(tile_areas_ha.values()), 2),
            "aggregation_rule": (
                "Project-level signal per indicator = WORST TILE's signed benchmark "
                "(non-compensatory, limiting-factor principle applied across tiles). "
                "Area-weighted geometric mean and area-weighted mean of the raw value "
                "are reported as secondary/context only, never as the headline."
            ),
        },
        "combined_benchmarks": combined_benchmarks,
    }


def run_multi_tile_project(config: Config,
                           registry: IndicatorRegistry,
                           tile_paths: List[str],
                           tile_labels: Optional[List[str]] = None,
                           project_name: str = "project",
                           output_dir: Optional[str] = None,
                           continue_on_tile_failure: bool = True,
                           tile_realms: Optional[List[str]] = None) -> Dict:
    """Run darukaa_reference once per tile and combine the results project-wide.

    tile_paths   : one KML/GeoJSON/shapefile per tile (each may contain many parcels —
                   they are dissolved into one geometry per tile automatically).
    tile_labels  : optional; defaults to tile_01, tile_02, ... in input order.
    tile_realms  : REAL FEATURE (client-requested directly: "if any project
                   involves both aquatic + terrestrial the report can't be
                   separate one"). Optional; one realm per tile, same
                   length/order as tile_paths, e.g. 9x "terrestrial" +
                   6x "aquatic" for a combined Tata Motors run (9 real
                   zones + 6 real water bodies as ONE project). Each
                   tile gets its own real config.realm override (via
                   dataclasses.replace — never mutates the shared config
                   object other tiles still use) before its own Pipeline
                   runs, so a terrestrial zone correctly gets terrestrial-
                   applicable indicators and an aquatic tile correctly
                   gets aquatic-applicable ones (see registry.py's
                   applicable_realms) — never the same, single project-
                   wide indicator set blindly applied to every tile
                   regardless of what it actually is. None (the default)
                   uses config.realm for every tile unchanged, exactly
                   the prior behaviour for every existing single-realm
                   project.
    output_dir   : defaults to config.output_dir. Writes:
                     <output_dir>/<project_name>_project.{json,csv,html}
                     <output_dir>/<project_name>_tiles/<tile_label>.{json,csv,html}
    continue_on_tile_failure : if a tile's run raises (e.g. GEE error, empty geometry),
                   log it and continue with the remaining tiles rather than aborting the
                   whole project — a broken tile is recorded explicitly in the output,
                   never silently dropped.

    Returns the full project-level report dict (see module docstring for its shape).
    """
    if tile_labels is None:
        tile_labels = [f"tile_{i+1:02d}" for i in range(len(tile_paths))]
    if len(tile_labels) != len(tile_paths):
        raise ValueError("tile_labels must match tile_paths in length if provided.")
    if tile_realms is not None and len(tile_realms) != len(tile_paths):
        raise ValueError("tile_realms must match tile_paths in length if provided.")

    out_dir = Path(output_dir or config.output_dir)
    tiles_dir = out_dir / f"{project_name}_tiles"
    tiles_dir.mkdir(parents=True, exist_ok=True)

    tile_reports: Dict[str, Dict] = {}
    tile_areas_ha: Dict[str, float] = {}
    failed_tiles: Dict[str, str] = {}

    with tempfile.TemporaryDirectory() as tmp_dir:
        for i, (path, label) in enumerate(zip(tile_paths, tile_labels)):
            logger.info(f"\n{'='*60}\nTILE: {label} ({path})\n{'='*60}")
            try:
                geojson_path, area_ha = _dissolve_tile_to_geojson(path, label, tmp_dir)
                tile_areas_ha[label] = area_ha
                logger.info(f"  Dissolved to one geometry, area={area_ha:.2f} ha")

                tile_config = config
                if tile_realms is not None:
                    tile_config = dataclasses.replace(config, realm=tile_realms[i])
                    logger.info(f"  Realm for this tile: {tile_config.realm}")
                pipe = Pipeline(tile_config, registry)
                rep = pipe.run(site_path=geojson_path,
                              output_path=str(tiles_dir / label))
                tile_reports[label] = rep
            except Exception as e:
                logger.error(f"  Tile '{label}' FAILED: {e}")
                failed_tiles[label] = str(e)
                if not continue_on_tile_failure:
                    raise

    if not tile_reports:
        raise RuntimeError(
            f"All {len(tile_paths)} tile(s) failed; no project-level result can be "
            f"computed. Failures: {failed_tiles}")

    agg = aggregate_tiles_noncompensatory(
        tile_reports, tile_areas_ha, registry,
        seed_kernel=getattr(config, "use_seed_kernel", False),
        seed_delta=getattr(config, "seed_kernel_delta", 0.5))

    # Representative indicator_status: identical across tiles (same registry/config) —
    # taken from any one successful tile's report, not recomputed.
    any_report = next(iter(tile_reports.values()))

    from datetime import datetime
    project_report = {
        "meta": {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "pipeline_version": any_report["meta"]["pipeline_version"],
            "project_name": project_name,
            "n_tiles": len(tile_paths),
            "n_tiles_succeeded": len(tile_reports),
            "n_tiles_failed": len(failed_tiles),
            "failed_tiles": failed_tiles,
            "total_area_ha": agg["multi_tile_summary"]["total_area_ha"],
            "archetype": getattr(config, "archetype", None),
            "assessment_mode": getattr(config, "assessment_mode", None),
            "aggregation": "non-compensatory: project signal = worst tile per indicator "
                          "(see multi_tile_summary.aggregation_rule); reuses the same "
                          "profile-first scoring engine as a single site.",
        },
        "indicator_status": any_report.get("indicator_status", {}),
        "site_profiles": {"PROJECT": agg["project_profile"]},
        "multi_tile_summary": agg["multi_tile_summary"],
        "scorecard": [
            {"indicator": name, **summary}
            for name, summary in agg["multi_tile_summary"]["per_indicator"].items()
        ],
        "tile_reports": tile_reports,
    }

    # Write project-level outputs
    json_path = out_dir / f"{project_name}_project.json"
    with open(json_path, "w") as f:
        json.dump(project_report, f, indent=2, default=str)

    import csv as csv_mod
    csv_path = out_dir / f"{project_name}_project.csv"
    if project_report["scorecard"]:
        with open(csv_path, "w", newline="") as f:
            writer = csv_mod.DictWriter(f, fieldnames=project_report["scorecard"][0].keys())
            writer.writeheader()
            writer.writerows(project_report["scorecard"])

    html_path = out_dir / f"{project_name}_project.html"
    html_report.write_html(project_report, str(html_path),
                           project_name=f"{project_name} (project-level, {len(tile_reports)} tiles)")

    logger.info(f"\n{'='*60}\nPROJECT COMPLETE: {len(tile_reports)}/{len(tile_paths)} tiles | "
               f"total area {agg['multi_tile_summary']['total_area_ha']:.1f} ha")
    logger.info(f"Project reports: {json_path.name} / {csv_path.name} / {html_path.name}")
    if failed_tiles:
        logger.warning(f"FAILED TILES (excluded from aggregation, recorded in meta): {failed_tiles}")

    return project_report
