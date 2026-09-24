"""
run_pipeline.py — single-command driver for the whole pipeline
==================================================================

Runs 01_ingestion -> 02_covariates -> 03_emu_delineation (archetype-routed
automatically: ecological_clustering for agroforestry, segmentation_
reconciliation for conservation/industrial) for one project in one call.

CACHING — the actual point of this file. Every stage writes its outputs
under outputs/<NN_stage>/. Before running a stage, this driver checks
whether ALL of that stage's declared inputs are OLDER than ALL of its
declared outputs; if so, the stage is skipped with a one-line note instead
of re-run. This is the "never regenerate files that already exist and are
unchanged" operating rule, made automatic instead of relying on a human to
remember which stages need re-running after e.g. only config.yaml changed.

Use `--force` to bypass caching entirely (e.g. after a code change to a
stage itself, which this driver has no way to detect via mtimes alone).
Use `--from STAGE` to force-rerun from a given stage onward regardless of
staleness (e.g. "--from 03" after a real GEE CSV finally lands, since that
only touches 02's output file, not 02's own script mtime).

Usage:
    python run_pipeline.py ../projects/FCF_Soova
    python run_pipeline.py ../projects/FCF_Soova --force
    python run_pipeline.py ../projects/FCF_Soova --from 03
"""
from __future__ import annotations

import argparse
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Callable, List, Optional

PIPELINE_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PIPELINE_ROOT / "common"))
import config_schema  # noqa: E402

logger = logging.getLogger(__name__)


def _load_module(stage_dir: str, module_file: str):
    path = PIPELINE_ROOT / stage_dir / module_file
    spec = importlib.util.spec_from_file_location(module_file[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _newest_mtime(paths: List[Path]) -> Optional[float]:
    existing = [p.stat().st_mtime for p in paths if p.exists()]
    return max(existing) if existing else None


def _oldest_mtime(paths: List[Path]) -> Optional[float]:
    existing = [p.stat().st_mtime for p in paths if p.exists()]
    return min(existing) if existing else None


def _all_exist(paths: List[Path]) -> bool:
    return all(p.exists() for p in paths)


class Stage:
    def __init__(self, key: str, inputs: List[Path], outputs: List[Path],
                 run_fn: Callable[[], dict]):
        self.key = key
        self.inputs = inputs
        self.outputs = outputs
        self.run_fn = run_fn

    def is_stale(self) -> bool:
        if not _all_exist(self.outputs):
            return True
        newest_input = _newest_mtime(self.inputs)
        oldest_output = _oldest_mtime(self.outputs)
        if newest_input is None or oldest_output is None:
            return True
        return newest_input > oldest_output

    def run(self, force: bool) -> dict:
        if not force and not self.is_stale():
            logger.info("[%s] up to date — skipping (use --force to override)", self.key)
            return {"status": "skipped_up_to_date"}
        logger.info("[%s] running...", self.key)
        return self.run_fn()


def build_stages(project_dir: Path, cfg: dict) -> List[Stage]:
    raw_kmls = sorted((project_dir / "raw").glob("*.kml"))
    config_path = project_dir / "config.yaml"
    ing_dir = project_dir / "outputs" / "01_ingestion"
    cov_dir = project_dir / "outputs" / "02_covariates"
    emu_dir = project_dir / "outputs" / "03_emu_delineation"
    is_contiguous = cfg["archetype"] in ("conservation", "industrial")

    kml_ingest = _load_module("01_ingestion", "kml_ingest.py")
    # A project whose source KML doesn't fit the standard placemark-
    # classification model (e.g. many real thematic layers rather than a
    # small number of named anchor/exclusion/candidate placemarks) can
    # provide its own project_dir/custom_ingestion.py exposing
    # run_ingestion(project_dir). When present, it replaces
    # kml_ingest.run_ingestion for stage 01 entirely, so a full pipeline
    # run — including --force — never silently falls back to logic that
    # was never designed for that project's KML structure.
    custom_ingestion_path = project_dir / "custom_ingestion.py"
    ingestion_run_fn = kml_ingest.run_ingestion
    if custom_ingestion_path.exists():
        import importlib.util
        spec = importlib.util.spec_from_file_location("custom_ingestion", custom_ingestion_path)
        custom_ingestion = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(custom_ingestion)
        ingestion_run_fn = custom_ingestion.run_ingestion

    covariate_ingest = _load_module("02_covariates", "covariate_ingest.py")
    position_scoring = _load_module("03b_position_scoring", "position_scoring.py")
    panel_scheduler = _load_module("04_deployment_planning", "panel_scheduler.py")
    schedule_export = _load_module("04_deployment_planning", "schedule_export.py")
    rollup = _load_module("05_metrics_rollup", "rollup.py")
    report_builder = _load_module("06_reporting", "report_builder.py")
    field_map_builder = _load_module("06_reporting", "field_map_builder.py")
    export_tiles = _load_module("07_reference_handoff", "export_tiles.py")

    ingestion_outputs = [ing_dir / "candidates.geojson", ing_dir / "ingestion_report.json"]
    if is_contiguous:
        ingestion_outputs.append(ing_dir / "candidate_grid.geojson")

    covariate_outputs = [cov_dir / "candidates_with_covariates.geojson",
                          cov_dir / "covariate_ingestion_report.json"]
    gee_csv = project_dir / "gee_output" / "gee_covariates_output.csv"

    emu_module_file = "segmentation_reconciliation.py" if is_contiguous else "ecological_clustering.py"
    emu_module = _load_module("03_emu_delineation", emu_module_file)
    emu_run_fn = (emu_module.run_segmentation_reconciliation if is_contiguous
                  else emu_module.run_ecological_clustering)
    # Both archetypes now write candidates_with_emu.geojson (per-member-tile,
    # carries covariate properties) — segmentation_reconciliation.py was
    # produces this alongside its dissolved
    # emus.geojson; previously the contiguous path only wrote the dissolved
    # file, which silently broke 05_metrics_rollup for every conservation/
    # industrial project (see rollup.py's _tiles_by_emu docstring).
    emu_outputs = [emu_dir / "candidates_with_emu.geojson", emu_dir / "emu_delineation_report.json"]
    if is_contiguous:
        emu_outputs.append(emu_dir / "emus.geojson")

    return [
        Stage("01_ingestion", inputs=raw_kmls + [config_path], outputs=ingestion_outputs,
              run_fn=lambda: ingestion_run_fn(project_dir)),
        Stage("02_covariates", inputs=[config_path] + ingestion_outputs + ([gee_csv] if gee_csv.exists() else []),
              outputs=covariate_outputs,
              run_fn=lambda: covariate_ingest.run_covariate_ingestion(project_dir)),
        Stage("03_emu_delineation",
              inputs=[config_path] + ingestion_outputs + (covariate_outputs if cov_dir.exists() else []),
              outputs=emu_outputs,
              run_fn=lambda: emu_run_fn(project_dir)),
        Stage("03b_position_scoring",
              inputs=[config_path] + emu_outputs,
              outputs=[project_dir / "outputs" / "03b_position_scoring" / "position_pool.geojson",
                       project_dir / "outputs" / "03b_position_scoring" / "position_scoring_report.json"],
              run_fn=lambda: position_scoring.run_position_scoring(project_dir)),
        Stage("04_deployment_planning",
              inputs=[config_path] + emu_outputs +
                      [project_dir / "outputs" / "03b_position_scoring" / "position_pool.geojson"],
              outputs=[project_dir / "outputs" / "04_deployment_planning" / "deployment_schedule.json"],
              run_fn=lambda: panel_scheduler.run_panel_scheduling(project_dir)),
        Stage("04b_schedule_export",
              inputs=[config_path, project_dir / "outputs" / "04_deployment_planning" / "deployment_schedule.json"],
              outputs=[project_dir / "outputs" / "04_deployment_planning" / "deployment_schedule.csv"],
              run_fn=lambda: schedule_export.run_schedule_export(project_dir)),
        Stage("05_metrics_rollup",
              inputs=[config_path] + emu_outputs,
              outputs=[project_dir / "outputs" / "05_metrics_rollup" / "metrics_rollup_report.json",
                       project_dir / "outputs" / "05_metrics_rollup" / "emu_reference_handoff.geojson"],
              run_fn=lambda: rollup.run_rollup(project_dir)),
        Stage("06_reporting",
              inputs=[config_path,
                      project_dir / "outputs" / "01_ingestion" / "ingestion_report.json",
                      project_dir / "outputs" / "04_deployment_planning" / "deployment_schedule.json",
                      project_dir / "outputs" / "05_metrics_rollup" / "metrics_rollup_report.json"],
              outputs=[project_dir / "outputs" / "06_reporting" /
                       f"{cfg['project_name']}_site_selection_report.html"],
              run_fn=lambda: report_builder.run_report_build(project_dir)),
        Stage("06b_field_map",
              inputs=[config_path,
                      project_dir / "outputs" / "01_ingestion" / "ingestion_report.json",
                      project_dir / "outputs" / "03b_position_scoring" / "position_pool.geojson",
                      project_dir / "outputs" / "04_deployment_planning" / "deployment_schedule.json"],
              outputs=[project_dir / "outputs" / "06_reporting" / "field_map.html"],
              run_fn=lambda: field_map_builder.run_field_map_build(project_dir)),
        Stage("07_reference_handoff",
              # Real, independent stage — see export_tiles.py's own
              # docstring: nothing downstream in THIS pipeline reads its
              # output. It exists purely to produce the per-EMU tile files
              # darukaa_reference's project_aggregation.run_multi_tile_project
              # expects as input.
              inputs=[config_path, project_dir / "outputs" / "03_emu_delineation" / "candidates_with_emu.geojson"],
              outputs=[project_dir / "outputs" / "07_reference_handoff" / "tile_manifest.json"],
              run_fn=lambda: export_tiles.run_export_tiles(project_dir)),
    ]


def run_pipeline(project_dir: str | Path, force: bool = False, from_stage: Optional[str] = None) -> dict:
    project_dir = Path(project_dir)
    cfg = config_schema.load_config(project_dir / "config.yaml")
    stages = build_stages(project_dir, cfg)

    results = {}
    force_from_here = False  # BUG FIX: was `from_stage is None`, which made
    # this True by default (the common case, no --from given) — meaning
    # every stage force-ran regardless of staleness, exactly the repeated-
    # effort problem this file exists to solve. Caught by actually running
    # the same project twice in a row and checking for "skipping" in the
    # log, which is the only way this class of bug shows up — mtime logic
    # looks right on paper and silently does nothing useful.
    for stage in stages:
        if from_stage and stage.key.startswith(from_stage):
            force_from_here = True
        results[stage.key] = stage.run(force=force or force_from_here)
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    parser.add_argument("--force", action="store_true", help="Re-run every stage regardless of staleness")
    parser.add_argument("--from", dest="from_stage", default=None,
                        help="Force re-run from this stage onward, e.g. --from 03")
    args = parser.parse_args()
    run_pipeline(args.project_dir, force=args.force, from_stage=args.from_stage)
