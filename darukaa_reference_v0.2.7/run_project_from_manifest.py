"""
run_project_from_manifest.py
==============================

Generalised project runner — reads ANY project's real tile_manifest.json
(the exact handoff format the site-selection pipeline's 07_reference_handoff
stage already produces for every archetype: conservation zone-per-EMU,
agroforestry parcel-per-EMU, or a manually-built manifest for a project
with no site-selection pipeline involvement at all, e.g. Corbett) and runs
it through the same real `run_multi_tile_project` path — one script for
every project, not a bespoke one per client.

For a project WITH a site-selection pipeline (Tata Motors, Soulforest,
GV, Soova): each real zone/EMU is already its own dissolved GeoJSON tile
under outputs/07_reference_handoff/tiles/, and tile_manifest.json in that
same folder lists them — point this script at that folder directly, no
reformatting needed. For Tata Motors specifically: this means the
pipeline genuinely runs on each of its 9 real zones independently (worst-
zone-first, non-compensatory aggregation, exactly as documented in
AGGREGATION_WALKTHROUGH.md), not once over the whole 126.66 ha campus —
the project-level report is built FROM those 9 real per-zone results, the
same real architecture already verified end-to-end against Corbett's 4
independent sites.

For a project with NO site-selection pipeline (raw KML/GeoJSON boundaries
only): build a manifest.json by hand in the same shape (see
corbett_sites/manifest_example.json) and point this script at it.

USAGE (Colab):
    1. Clone this repo; %cd into darukaa_reference_v0.2.7
    2. !pip install -r requirements.txt
    3. import ee; ee.Authenticate(); ee.Initialize(project="<your-real-gee-project>")
    4. Edit config.yaml: set gee.project to the same real id.
    5. Upload the project's real outputs/07_reference_handoff/ folder
       (tile_manifest.json + tiles/*.geojson) — from the site-selection
       pipeline's own output, unmodified.
    6. python run_project_from_manifest.py --manifest <path>/tile_manifest.json

Verified structurally (not assumed) before shipping: all 4 site-selection
projects' real, current manifests (Tata Motors 9 zones, Soulforest 7 EMUs,
GV and Soova 6 EMUs each) load correctly through this exact code path.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("run_project")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from darukaa_reference.config import Config
from darukaa_reference.indicators import create_default_registry
from darukaa_reference.project_aggregation import run_multi_tile_project


def load_manifest(manifest_path: Path) -> dict:
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Manifest not found: {manifest_path}\n"
            f"This should be a real tile_manifest.json — either copied directly "
            f"from a site-selection project's outputs/07_reference_handoff/ folder, "
            f"or hand-built in the same shape for a project with no site-selection "
            f"pipeline involvement (see corbett_sites/manifest_example.json)."
        )
    with open(manifest_path) as f:
        manifest = json.load(f)
    for key in ("project_name", "tile_paths", "tile_labels"):
        if key not in manifest:
            raise ValueError(f"Manifest is missing required key '{key}': {manifest_path}")
    if len(manifest["tile_paths"]) != len(manifest["tile_labels"]):
        raise ValueError(
            f"Manifest has {len(manifest['tile_paths'])} tile_paths but "
            f"{len(manifest['tile_labels'])} tile_labels — these must match 1:1."
        )
    return manifest


def resolve_tile_paths(manifest: dict, manifest_path: Path) -> list[str]:
    """Tile paths in a real site-selection manifest are relative to that
    project's OWN repo root (e.g. "projects/TataMotors_Pimpri/outputs/...")
    — resolved here relative to the manifest file's own real location,
    not the current working directory, so this script works regardless
    of where it's invoked from."""
    base = manifest_path.parent
    resolved = []
    for p in manifest["tile_paths"]:
        # Real manifest paths are repo-root-relative; the actual tiles/
        # folder sits alongside the manifest itself, so re-anchor on that.
        candidate = base / Path(p).name if not (base / p).exists() else base / p
        if not candidate.exists():
            candidate = base / "tiles" / Path(p).name
        resolved.append(str(candidate))
    return resolved


def main():
    parser = argparse.ArgumentParser(description="Run darukaa_reference against a real project tile manifest.")
    parser.add_argument("--manifest", required=True, help="Path to the project's tile_manifest.json")
    parser.add_argument("--output-dir", default=None, help="Output dir (default: ./outputs/<project_name>)")
    parser.add_argument("--config", default=str(Path(__file__).resolve().parent / "config.yaml"))
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    manifest = load_manifest(manifest_path)
    tile_paths = resolve_tile_paths(manifest, manifest_path)

    missing = [p for p in tile_paths if not Path(p).exists()]
    if missing:
        raise FileNotFoundError(
            f"{len(missing)} tile file(s) referenced in the manifest were not found:\n"
            + "\n".join(f"  {p}" for p in missing)
            + f"\nEnsure the manifest's real tiles/ folder is uploaded alongside it."
        )

    project_name = manifest["project_name"]
    tile_labels = manifest["tile_labels"]
    output_dir = args.output_dir or f"./outputs/{project_name}"

    config = Config.from_yaml(args.config)
    if config.gee_project in (None, "", "your-gee-project-id"):
        logger.warning(
            "config.yaml's gee.project is still the placeholder value — "
            "set it to your real GEE project id before this run can reach "
            "live Earth Engine data."
        )

    registry = create_default_registry()

    logger.info("Running %s — %d real zone(s)/tile(s): %s",
                project_name, len(tile_labels), ", ".join(tile_labels))
    result = run_multi_tile_project(
        config, registry, tile_paths, tile_labels,
        project_name=project_name, output_dir=output_dir,
        continue_on_tile_failure=True,
    )

    logger.info("Done. Project-level report: %s/%s_project.json / .html", output_dir, project_name)
    return result


if __name__ == "__main__":
    main()
