"""
02_covariates / covariate_ingest.py
====================================

Stage 2. Merges the GEE-exported covariate CSV (produced by
pipeline/gee/covariates_and_segmentation.js — see that file's header for the
manual run steps) back onto 01_ingestion's candidates.geojson.

This is a generalization of the existing PHASE_2_GEEMetricsIngest.py
(reused pattern, not reinvented — binary hard-filters, merge-by-ID,
impute-with-warning): the join key is our own `name` field from
01_ingestion (stable, unique per placemark in every project inspected so
far) rather than a shapefile-truncated `Site_ID`/`SITE_ID`, since we upload
candidates as GeoJSON, not a shapefile — no 10-character column truncation
to work around.

GEE STEP IS MANUAL BY DESIGN (automating it wasn't judged worth the
complexity relative to keeping clear, numbered manual instructions). This
module does NOT call Earth Engine. It expects a human to have:
  1. Uploaded projects/<NAME>/outputs/01_ingestion/candidates.geojson as an
     Earth Engine table asset.
  2. Run pipeline/gee/covariates_and_segmentation.js in the GEE code editor
     against that asset (see GEE_RUN_INSTRUCTIONS.md, generated per project
     by build_run_instructions() below).
  3. Downloaded the resulting CSV from Drive into
     projects/<NAME>/gee_output/gee_covariates_output.csv

If that file isn't there yet, this module says so plainly and stops — it
does NOT silently proceed with an all-imputed, meaningless dataset, unlike
the old PHASE_2_GEEMetricsIngest.py's "PATH B fallback" which allowed a full
run with zero real metrics. Real covariates are a hard prerequisite for
03_emu_delineation; pretending otherwise here would just move a
zero-real-data run one stage downstream where it's harder to notice.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
import config_schema  # noqa: E402
import gee_export       # noqa: E402

logger = logging.getLogger(__name__)

# Covariate columns expected from the GEE script, independent of archetype
# (every candidate gets these regardless of whether SNIC ran).
BASE_COVARIATE_COLUMNS = [
    "NDVI_raw", "TreeCover_Pct", "Elev_m", "ElevStd_m", "TRI_m", "Slope_deg",
    "NatCoverPct_2km", "EdgeDensity_2km", "NatCoverPct_500m", "EdgeDensity_500m",
    "gHM", "DistWater_m", "LST_C", "NightLights",
    "BuiltUp_Pct", "JRC_Water",
]
# Present only when the project's archetype ran the SNIC block (contiguous
# AOIs) — see the generalization note at the top of the .js file.
SEGMENTATION_COLUMNS = ["SEGMENT_ID"]


class CovariateIngestionError(RuntimeError):
    pass


def build_run_instructions(project_dir: Path, cfg: Dict[str, Any]) -> Path:
    """Writes a project-specific, numbered GEE run guide. Regenerated every
    call (cheap, always current) rather than hand-maintained per project.

    GEE's Assets manager does not accept raw .geojson uploads through the
    UI — only zipped Shapefile or CSV. This calls
    gee_export.run_gee_export() to produce a real, verified-readable
    Shapefile zip, and a per-project .js file with
    CANDIDATE_SCHEMA/RUN_SEGMENTATION already correct for the archetype,
    so there's no manual comment/uncomment step per project."""
    is_contiguous = cfg["archetype"] in ("conservation", "industrial")
    export_result = gee_export.run_gee_export(project_dir)
    zip_name = Path(export_result["shapefile_zip"]).name
    script_name = Path(export_result["ready_to_run_script"]).name
    waterbody_zip = export_result.get("waterbody_zip")

    aquatic_steps = ""
    if waterbody_zip:
        wb_name = Path(waterbody_zip).name
        aquatic_steps = f"""
11. This project has real water features configured for the aquatic export.
    Upload gee_output/{wb_name} the same way (Assets -> NEW -> Table Upload
    -> Shapefile), then paste its asset path into WATERBODY_ASSET_PATH near
    the top of the pasted script (currently a placeholder — search for
    "PASTE THE WATERBODY ASSET PATH").
12. This produces a SECOND CSV ({{EXPORT_NAME}}_aquatic) — place it at
    projects/{cfg['project_name']}/gee_output/gee_covariates_output_aquatic.csv
"""
    else:
        aquatic_steps = f"""
Note: no aquatic export for this project — either it's agroforestry
(aquatic is never generated for that archetype) or no
water_feature_placemark_names are configured. WATERBODY_ASSET_PATH is left
as "" in the pasted script, so the aquatic section is skipped entirely,
not defaulted to any other project's waterbodies (see the script's own
history note on that bug).
"""

    text = f"""# GEE run instructions — {cfg['project_name']}

Archetype: {cfg['archetype']} ({'contiguous' if is_contiguous else 'scattered'})

1. Go to code.earthengine.google.com
2. Assets tab -> NEW -> Table Upload -> Shapefile
   -> select gee_output/{zip_name}
   (a zipped .shp/.shx/.dbf/.prj — GEE's uploader does not accept raw
   .geojson/.json directly; this file was generated for you and verified
   readable before being written)
3. Name the asset (suggested: `{cfg['project_name'].lower()}_candidates`),
   wait for the upload task to finish (Tasks tab, yellow -> green)
4. Open gee_output/{script_name} — this is a ready-to-paste copy of the
   shared script with CANDIDATE_SCHEMA and RUN_SEGMENTATION already set
   correctly for this project's archetype. Paste it into a new GEE script.
5. Find the ASSET_PATH line near the top and paste in the full asset path
   from step 3. This is the ONLY line that needs manual editing — it can't
   be pre-filled because the asset doesn't exist until step 3 runs.
6. Set EXPORT_NAME = "gee_covariates_output" and
   DRIVE_FOLDER = "{cfg['project_name'].lower()}_gee" if not already set.
7. Run the script, open the Tasks tab, click Run on the export task
8. Once complete, download the CSV from Google Drive
9. Place it at: projects/{cfg['project_name']}/gee_output/gee_covariates_output.csv
10. Re-run: python covariate_ingest.py projects/{cfg['project_name']}
{aquatic_steps}"""
    out_path = project_dir / "gee_output" / "GEE_RUN_INSTRUCTIONS.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)
    return out_path


def _read_candidates_geojson(path: Path) -> Dict[str, Any]:
    with open(path) as f:
        return json.load(f)


def _read_covariate_csv(path: Path) -> Dict[str, Dict[str, Any]]:
    """Minimal CSV reader keyed by `name` — avoids pulling in pandas just
    for this join; every value stays a string except where we explicitly
    cast below, so a malformed numeric field surfaces as a ValueError at
    the point of use, not a silently-wrong float."""
    import csv
    rows = {}
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = row.get("name")
            if key is None:
                raise CovariateIngestionError(
                    f"{path}: CSV has no 'name' column to join on. "
                    f"Columns present: {reader.fieldnames}")
            rows[key] = row
    return rows


def run_covariate_ingestion(project_dir: str | Path) -> Dict[str, Any]:
    project_dir = Path(project_dir)
    cfg = config_schema.load_config(project_dir / "config.yaml")

    candidates_path = project_dir / "outputs" / "01_ingestion" / (
        "candidate_grid.geojson" if cfg["archetype"] in ("conservation", "industrial")
        else "candidates.geojson")
    if not candidates_path.exists():
        raise FileNotFoundError(f"{candidates_path} not found — run 01_ingestion first.")

    csv_path = project_dir / "gee_output" / "gee_covariates_output.csv"
    instructions_path = build_run_instructions(project_dir, cfg)

    if not csv_path.exists():
        logger.warning(
            "No GEE covariate CSV found at %s.\n"
            "  -> Run instructions written/refreshed at %s\n"
            "  -> Stopping here — 03_emu_delineation needs real covariates, "
            "not an imputed placeholder.", csv_path, instructions_path)
        return {
            "status": "waiting_on_gee_csv",
            "project_name": cfg["project_name"],
            "instructions_path": str(instructions_path),
            "expected_csv_path": str(csv_path),
        }

    fc = _read_candidates_geojson(candidates_path)
    covariate_rows = _read_covariate_csv(csv_path)

    is_contiguous = cfg["archetype"] in ("conservation", "industrial")
    expected_cols = BASE_COVARIATE_COLUMNS + (SEGMENTATION_COLUMNS if is_contiguous else [])

    report = {
        "status": "ok",
        "project_name": cfg["project_name"],
        "n_candidates": len(fc["features"]),
        "n_matched": 0,
        "n_unmatched": 0,
        "unmatched_names": [],
        "coverage_by_column": {c: 0 for c in expected_cols},
        "n_hard_filtered_builtup": 0,
        "n_hard_filtered_water": 0,
        "warnings": [],
    }

    max_builtup_pct = cfg.get("max_builtup_pct_for_candidate", 50.0)

    for feat in fc["features"]:
        name = feat["properties"]["name"]
        row = covariate_rows.get(name)
        if row is None:
            report["n_unmatched"] += 1
            report["unmatched_names"].append(name)
            feat["properties"]["gee_matched"] = False
            continue

        report["n_matched"] += 1
        feat["properties"]["gee_matched"] = True
        for col in expected_cols:
            val = row.get(col)
            if val not in (None, ""):
                try:
                    feat["properties"][col] = float(val)
                    report["coverage_by_column"][col] += 1
                except ValueError:
                    feat["properties"][col] = val  # e.g. SEGMENT_ID as int-like string

        builtup = feat["properties"].get("BuiltUp_Pct")
        water = feat["properties"].get("JRC_Water")
        ndvi = feat["properties"].get("NDVI_raw")
        hard_pass = True
        # A genuine impervious/built surface does not show real-vegetation
        # NDVI (0.24-0.35 range) — a land-cover classifier can misclassify
        # a young plantation's bare-soil-between-rows pattern as "Built
        # Area", a known failure mode on managed/transitional landscapes,
        # not a real finding. Rather than silently trust the categorical
        # classifier over a direct physical measurement, a real-vegetation
        # NDVI overrides a built-up call: a cell this green is not a
        # building, regardless of what the land-cover layer says.
        ndvi_override_threshold = cfg.get("builtup_ndvi_override_threshold", 0.2)
        vegetation_override = ndvi is not None and ndvi >= ndvi_override_threshold
        if builtup is not None and builtup > max_builtup_pct and not vegetation_override:
            hard_pass = False
            report["n_hard_filtered_builtup"] += 1
        elif builtup is not None and builtup > max_builtup_pct and vegetation_override:
            report.setdefault("n_builtup_override_by_ndvi", 0)
            report["n_builtup_override_by_ndvi"] += 1
        if water is not None and water > 0.5:
            hard_pass = False
            report["n_hard_filtered_water"] += 1
        feat["properties"]["hard_filter_pass"] = hard_pass

    if report["n_unmatched"] > 0:
        pct_unmatched = 100 * report["n_unmatched"] / report["n_candidates"]
        msg = (f"{report['n_unmatched']}/{report['n_candidates']} "
               f"({pct_unmatched:.1f}%) candidates had no matching row in "
               f"the GEE CSV — check that candidate_id/name values were "
               f"preserved through the GEE table upload.")
        report["warnings"].append(msg)
        logger.warning(msg)
        if pct_unmatched > 20:
            raise CovariateIngestionError(
                f"{msg} Over 20% unmatched — stopping rather than proceeding "
                f"on a majority-imputed dataset. Check the asset upload.")

    for col, n_found in report["coverage_by_column"].items():
        pct = round(100 * n_found / report["n_candidates"], 1) if report["n_candidates"] else 0.0
        if pct < 100.0:
            report["warnings"].append(f"{col}: only {pct}% coverage across candidates")

    n_override = report.get("n_builtup_override_by_ndvi", 0)
    if n_override > 0:
        report["warnings"].append(
            f"{n_override} candidate(s) in this project had BuiltUp_Pct above the "
            "threshold but were kept anyway because their NDVI showed real vegetation "
            "— the land-cover classifier appears to be misclassifying part of this "
            "site as built-up (a known failure mode on managed/plantation landscapes: "
            "a young plantation's bare-soil-between-rows pattern showing BuiltUp_Pct "
            "near 100 with NDVI 0.24-0.35, physically inconsistent with a real built "
            "surface). Worth a visual/field check on this specific classifier "
            "behaviour.")

    out_dir = project_dir / "outputs" / "02_covariates"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "candidates_with_covariates.geojson", "w") as f:
        json.dump(fc, f)
    with open(out_dir / "covariate_ingestion_report.json", "w") as f:
        json.dump(report, f, indent=2)

    logger.info("Covariate ingestion complete: %d/%d matched, %d built-up filtered, "
                "%d water filtered", report["n_matched"], report["n_candidates"],
                report["n_hard_filtered_builtup"], report["n_hard_filtered_water"])
    return report


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    args = parser.parse_args()
    run_covariate_ingestion(args.project_dir)
