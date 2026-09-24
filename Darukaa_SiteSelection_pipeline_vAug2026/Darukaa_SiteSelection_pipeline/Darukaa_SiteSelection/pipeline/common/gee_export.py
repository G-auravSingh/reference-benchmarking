"""
common/gee_export.py — produces the file GEE's Assets manager actually accepts
==================================================================================

GEE's Cloud Assets
manager UI does not accept raw .geojson/.json uploads — only Shapefile
(.shp/.shx/.dbf/.prj, zipped) or CSV. Every earlier GEE_RUN_INSTRUCTIONS.md
in this repo said "Table Upload -> GeoJSON", which is wrong and was never
actually tested against the real GEE UI — caught only when the person doing
the manual step hit the real error. This module is the fix: it converts
01_ingestion's candidates.geojson (or candidate_grid.geojson, for contiguous
archetypes) into a zipped ESRI Shapefile containing ONLY a `name` column —
short enough (4 characters) to survive Shapefile's 10-character field-name
truncation with no mapping needed, which is also why the GEE script's
CANDIDATE_SCHEMA="unified" reads `name` directly rather than a truncated
alias.

Also generates a per-project, READY-TO-PASTE .js file with CANDIDATE_SCHEMA
and RUN_SEGMENTATION already baked in correctly for the project's archetype
— this was flagged directly as a second real problem: requiring a human to
manually comment/uncomment a code block per project, every run, is
error-prone busywork. ASSET_PATH still can't be pre-filled (it doesn't
exist until after the manual upload step creates it), so that one line
still needs a human to paste in — everything else does not.
"""
from __future__ import annotations

import logging
import sys
import zipfile
from pathlib import Path
from typing import Dict

import geopandas as gpd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config_schema  # noqa: E402

logger = logging.getLogger(__name__)

GEE_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "gee" / "covariates_and_segmentation.js"


def export_shapefile_for_gee(source_geojson: Path, out_dir: Path, base_name: str) -> Path:
    """Reads source_geojson, keeps ONLY `name` + geometry (everything else
    is irrelevant to GEE and risks Shapefile's field-name/type limits for
    no benefit — the pipeline re-joins its own full attribute set locally
    afterward, by `name`, once the covariate CSV comes back), writes a
    zipped ESRI Shapefile. Returns the zip path."""
    gdf = gpd.read_file(source_geojson)
    if "name" not in gdf.columns:
        raise ValueError(f"{source_geojson} has no 'name' column to use as the GEE join key.")
    slim = gdf[["name", "geometry"]].copy()

    out_dir.mkdir(parents=True, exist_ok=True)
    shp_stem = out_dir / base_name
    shp_path = shp_stem.with_suffix(".shp")
    slim.to_file(shp_path, driver="ESRI Shapefile")

    zip_path = out_dir / f"{base_name}.zip"
    sidecar_exts = [".shp", ".shx", ".dbf", ".prj", ".cpg"]
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for ext in sidecar_exts:
            f = shp_stem.with_suffix(ext)
            if f.exists():
                zf.write(f, arcname=f.name)

    # Verify round-trip readability before declaring success — a shapefile
    # that geopandas wrote but can't itself read back is worse than no file.
    check = gpd.read_file(zip_path)
    if len(check) != len(slim):
        raise RuntimeError(
            f"Shapefile round-trip check failed: wrote {len(slim)} features, "
            f"read back {len(check)} from {zip_path}.")

    logger.info("Wrote %s (%d features, verified readable)", zip_path, len(check))
    return zip_path


def export_waterbody_shapefile_for_gee(project_dir: Path, cfg: Dict) -> Path | None:
    """Builds a REAL, per-project waterbody shapefile for the optional GEE
    aquatic export — fixes the bug where WATERBODY_ASSET_PATH was a single
    hardcoded path shared (and never varied) across every project. Returns
    None if this project has nothing real to export, in which case the
    aquatic section stays off (WATERBODY_ASSET_PATH = "") rather than
    falling back to someone else's waterbodies.

    HARD RULE: agroforestry NEVER gets an aquatic asset, regardless of
    config: "it should not generate anything
    for agroforestry". Not a default that could be overridden by an
    unrelated config value; checked first, unconditionally."""
    if cfg["archetype"] == "agroforestry":
        return None

    names = set(cfg.get("water_feature_placemark_names") or [])
    if not names:
        return None

    exclusions_path = project_dir / "outputs" / "01_ingestion" / "exclusion_zones.geojson"
    if not exclusions_path.exists():
        return None
    gdf = gpd.read_file(exclusions_path)
    water_gdf = gdf[gdf["name"].isin(names)][["name", "geometry"]].copy()
    if water_gdf.empty:
        logger.warning("water_feature_placemark_names=%s configured but none matched "
                        "any exclusion-zone placemark — check the names against the "
                        "real KML.", names)
        return None

    out_dir = project_dir / "gee_output"
    out_dir.mkdir(parents=True, exist_ok=True)
    shp_stem = out_dir / f"{cfg['project_name']}_waterbodies"
    water_gdf.to_file(shp_stem.with_suffix(".shp"), driver="ESRI Shapefile")
    zip_path = out_dir / f"{cfg['project_name']}_waterbodies.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for ext in [".shp", ".shx", ".dbf", ".prj", ".cpg"]:
            f = shp_stem.with_suffix(ext)
            if f.exists():
                zf.write(f, arcname=f.name)

    check = gpd.read_file(zip_path)
    if len(check) != len(water_gdf):
        raise RuntimeError(f"Waterbody shapefile round-trip check failed for {zip_path}.")
    logger.info("Wrote %s (%d real waterbody features, verified readable)", zip_path, len(check))
    return zip_path


def build_ready_to_run_script(cfg: Dict, out_dir: Path, waterbody_zip: Path | None) -> Path:
    """Generates a per-project .js file with CANDIDATE_SCHEMA and
    RUN_SEGMENTATION already correct — the only manual edit left is pasting
    in ASSET_PATH after the upload step (that value doesn't exist until
    then, so it genuinely can't be pre-filled)."""
    is_contiguous = cfg["archetype"] in ("conservation", "industrial")
    base_script = GEE_SCRIPT_PATH.read_text()

    script = base_script.replace(
        'var CANDIDATE_SCHEMA = "unified";',
        'var CANDIDATE_SCHEMA = "unified";  // pre-set for '
        f'{cfg["project_name"]} ({cfg["archetype"]}) — do not change',
    ).replace(
        "var RUN_SEGMENTATION = true;",
        f'var RUN_SEGMENTATION = {"true" if is_contiguous else "false"};  // pre-set for '
        f'{cfg["project_name"]} ({"contiguous" if is_contiguous else "scattered"} archetype) — do not change',
    )

    if waterbody_zip is not None:
        script = script.replace(
            'var WATERBODY_ASSET_PATH = "";',
            'var WATERBODY_ASSET_PATH = "<< PASTE THE WATERBODY ASSET PATH HERE, '
            f'AFTER UPLOADING {waterbody_zip.name} >>";  // real per-project waterbodies '
            f'({cfg["project_name"]}) — see GEE_RUN_INSTRUCTIONS.md step for uploading it',
        )
    # else: leave WATERBODY_ASSET_PATH = "" — aquatic export stays off,
    # not defaulted to anyone else's waterbodies.

    out_path = out_dir / f"{cfg['project_name']}_ready_to_run.js"
    out_path.write_text(script)
    return out_path


def run_gee_export(project_dir: str | Path) -> Dict:
    project_dir = Path(project_dir)
    cfg = config_schema.load_config(project_dir / "config.yaml")
    is_contiguous = cfg["archetype"] in ("conservation", "industrial")

    ing_dir = project_dir / "outputs" / "01_ingestion"
    source = ing_dir / ("candidate_grid.geojson" if is_contiguous else "candidates.geojson")
    if not source.exists():
        raise FileNotFoundError(f"{source} not found — run 01_ingestion first.")

    gee_dir = project_dir / "gee_output"
    zip_path = export_shapefile_for_gee(source, gee_dir, f"{cfg['project_name']}_gee_upload")
    waterbody_zip = export_waterbody_shapefile_for_gee(project_dir, cfg)
    script_path = build_ready_to_run_script(cfg, gee_dir, waterbody_zip)

    return {"shapefile_zip": str(zip_path), "ready_to_run_script": str(script_path),
            "waterbody_zip": str(waterbody_zip) if waterbody_zip else None}


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    args = parser.parse_args()
    result = run_gee_export(args.project_dir)
    print(result)
