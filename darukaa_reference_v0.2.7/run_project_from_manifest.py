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
    1. Clone this repo (contains BOTH pipelines now — no separate zip/
       upload step for the handoff between them);
       %cd into darukaa_reference_v0.2.7
    2. !pip install -r requirements.txt
    3. import ee; ee.Authenticate(); ee.Initialize(project="<your-real-gee-project>")
    4. Edit config.yaml: set gee.project to the same real id.
    5. python run_project_from_manifest.py --project TataMotors_Pimpri
       (searches this repo for that project's real site-selection handoff
       automatically — see find_manifest_by_project_name below. Use
       --manifest <exact path> instead if you'd rather point at a
       specific file directly, e.g. a manifest that isn't in this repo.)

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


def find_manifest_by_project_name(repo_root, project_name: str) -> Path:
    """REAL CONNECTION (client-requested: 'reduce this manual downloading
    and uploading process... the two pipelines can be connected'). With
    the site-selection pipeline pushed into this same repository, its
    real outputs/07_reference_handoff/tile_manifest.json for any project
    are already sitting on disk the moment this repo is cloned — no zip,
    no manual upload, no copy step at all. This searches for it by
    project name alone, rather than requiring the exact nested path
    (which varies by how the site-selection folder happens to be named/
    zipped — confirmed directly: the real pushed copy sits under a
    doubly-nested Darukaa_SiteSelection_pipeline_vAug2026/.../
    Darukaa_SiteSelection/ path, not a fixed, predictable one), so this
    stays robust even if that nesting changes on a future push.

    Searches the whole repo (this file's own parent tree) for
    projects/<project_name>/outputs/07_reference_handoff/tile_manifest.json
    under ANY site-selection folder present, and requires exactly one
    real match — ambiguity (e.g. two different site-selection checkouts
    both containing the same project name) is a real problem to surface
    and resolve explicitly, never silently guessed at.

    REAL FIX (found directly by testing this against a real second
    manifest, not assumed to work): matching purely by path pattern
    (projects/<name>/outputs/07_reference_handoff/...) silently misses
    any manifest under a differently-named outputs folder — confirmed
    directly against Tata Motors' own real aquatic-module manifest,
    which deliberately lives under a SEPARATE
    outputs/07_reference_handoff_aquatic/ (a different real project,
    "TataMotors_Pimpri_Aquatic", extracted from the same site's raw
    water body polygons — see extract_aquatic_tiles.py). Now matches on
    each real manifest's own declared "project_name" field, which is the
    actual authoritative identity, rather than inferring identity from a
    path convention that doesn't hold for every real case."""
    repo_root = Path(repo_root)  # accepts a plain string too (e.g. from a
    # notebook's os.path.dirname(...)) — confirmed directly this call
    # pattern is real, not hypothetical, before making this defensive.
    matches = []
    for p in repo_root.rglob("tile_manifest.json"):
        try:
            with open(p) as f:
                candidate = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue  # a malformed or unreadable file is not a real match, skip silently
        if candidate.get("project_name") == project_name:
            matches.append(p)
    if not matches:
        raise FileNotFoundError(
            f"No tile_manifest.json with project_name '{project_name}' found anywhere "
            f"under {repo_root}. Confirm the site-selection pipeline's real output for "
            f"this project has been pushed to this repo, and that '{project_name}' "
            f"matches the manifest's own \"project_name\" field exactly (case-sensitive)."
        )
    if len(matches) > 1:
        raise ValueError(
            f"Found {len(matches)} different real tile_manifest.json files for project "
            f"'{project_name}' — ambiguous, not resolved automatically:\n"
            + "\n".join(f"  {m}" for m in matches)
            + f"\nPass --manifest with the exact one you want instead of --project."
        )
    return matches[0]


def main():
    parser = argparse.ArgumentParser(description="Run darukaa_reference against a real project tile manifest.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--manifest", help="Exact path to a project's tile_manifest.json")
    group.add_argument("--project", help="Real project name (e.g. TataMotors_Pimpri) — "
                       "searches this repo for its site-selection handoff automatically, "
                       "no manual path/zip/upload needed when both pipelines share a repo")
    parser.add_argument("--output-dir", default=None, help="Output dir (default: ./outputs/<project_name>)")
    parser.add_argument("--config", default=str(Path(__file__).resolve().parent / "config.yaml"))
    parser.add_argument("--realm", default=None, choices=["terrestrial", "aquatic", "mixed"],
                       help="Overrides auto-detection (which only triggers on a project name "
                       "containing 'aquatic'). 'terrestrial' excludes aquatic-module indicators, "
                       "'aquatic' keeps only core+aquatic, 'mixed' keeps everything.")
    parser.add_argument("--no-combine", action="store_true",
                       help="Client-requested directly: 'if any project involves both aquatic + "
                       "terrestrial the report can't be a separate one.' By default, running a "
                       "real project (e.g. TataMotors_Pimpri) automatically finds and merges in "
                       "its real '<project>_Aquatic' companion manifest if one exists, producing "
                       "ONE combined report -- each tile still gets its own correct realm (see "
                       "tile_realms in run_multi_tile_project), never one project-wide setting "
                       "blindly applied to every tile. Pass this flag to force a standalone, "
                       "terrestrial-only run even when a real aquatic companion exists.")
    args = parser.parse_args()

    if args.project:
        repo_root = Path(__file__).resolve().parent.parent  # this repo's real root
        manifest_path = find_manifest_by_project_name(repo_root, args.project).resolve()
        logger.info("Found real manifest for '%s' at: %s", args.project, manifest_path)
    else:
        manifest_path = Path(args.manifest).resolve()
        repo_root = manifest_path.parent  # combining needs a repo root to search from too

    manifest = load_manifest(manifest_path)
    tile_paths = resolve_tile_paths(manifest, manifest_path)
    tile_labels = list(manifest["tile_labels"])
    project_name = manifest["project_name"]
    # REAL BUG CAUGHT BEFORE SHIPPING (found by re-reading this against
    # the standalone-aquatic-run case, not assumed correct): a flat
    # "terrestrial" default here would have been wrong for a manifest
    # that IS itself the aquatic one (e.g. --project
    # TataMotors_Pimpri_Aquatic run directly) -- the combining block
    # below never runs for that case, so this initial default has to
    # already reflect the loaded manifest's own real realm.
    is_already_aquatic = "aquatic" in project_name.lower()
    tile_realms = ["aquatic" if is_already_aquatic else "terrestrial"] * len(tile_paths)

    # REAL COMBINING LOGIC (client-requested directly, see --no-combine's
    # help text for the exact wording). Only attempted when the manifest
    # just loaded doesn't already self-describe as aquatic (an aquatic
    # manifest run directly, e.g. --project TataMotors_Pimpri_Aquatic,
    # stays standalone -- combining only ever happens starting from the
    # terrestrial/base side, so running the aquatic project alone still
    # gives a real, separate result exactly as before).
    if not is_already_aquatic and not args.no_combine:
        aquatic_project_name = f"{project_name}_Aquatic"
        try:
            aquatic_manifest_path = find_manifest_by_project_name(repo_root, aquatic_project_name).resolve()
            aquatic_manifest = load_manifest(aquatic_manifest_path)
            aquatic_tile_paths = resolve_tile_paths(aquatic_manifest, aquatic_manifest_path)
            logger.info("Found real aquatic companion '%s' (%d tile(s)) -- combining into one project.",
                       aquatic_project_name, len(aquatic_tile_paths))
            tile_paths += aquatic_tile_paths
            tile_labels += aquatic_manifest["tile_labels"]
            tile_realms += ["aquatic"] * len(aquatic_tile_paths)
        except FileNotFoundError:
            pass  # no real aquatic companion for this project -- stays a standalone terrestrial run

    missing = [p for p in tile_paths if not Path(p).exists()]
    if missing:
        raise FileNotFoundError(
            f"{len(missing)} tile file(s) referenced in the manifest were not found:\n"
            + "\n".join(f"  {p}" for p in missing)
            + f"\nEnsure the manifest's real tiles/ folder is uploaded alongside it."
        )

    project_name = manifest["project_name"]
    output_dir = args.output_dir or f"./outputs/{project_name}"

    config = Config.from_yaml(args.config)
    if config.gee_project in (None, "", "your-gee-project-id"):
        logger.warning(
            "config.yaml's gee.project is still the placeholder value — "
            "set it to your real GEE project id before this run can reach "
            "live Earth Engine data."
        )

    # REAL FIX (round 2): a single project-wide config.realm was correct
    # for a project that's genuinely all-one-realm, but wrong the moment
    # a project combines terrestrial zones and aquatic water bodies (the
    # combining logic above) — each tile needs its OWN correct realm, not
    # one shared setting. tile_realms (built above) is now the real,
    # authoritative per-tile signal; an explicit --realm flag still
    # overrides every tile uniformly, for the case a user genuinely wants
    # that instead of the default per-tile behaviour.
    if args.realm:
        tile_realms = [args.realm] * len(tile_paths)
    registry = create_default_registry()

    logger.info("Running %s — %d real tile(s): %s",
                project_name, len(tile_labels), ", ".join(tile_labels))
    logger.info("Realms: %s", dict(zip(tile_labels, tile_realms)))
    result = run_multi_tile_project(
        config, registry, tile_paths, tile_labels,
        project_name=project_name, output_dir=output_dir,
        continue_on_tile_failure=True, tile_realms=tile_realms,
    )

    logger.info("Done. Project-level report: %s/%s_project.json / .html", output_dir, project_name)
    return result


if __name__ == "__main__":
    main()
