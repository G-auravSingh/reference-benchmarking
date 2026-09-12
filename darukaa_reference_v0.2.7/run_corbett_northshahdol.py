"""
run_corbett_northshahdol.py
============================

Runs Corbett's 4 real North Shahdol sites (Masira, Pipri, Karpa, Amanar)
through darukaa_reference as one combined, non-compensatorily-aggregated
project — the same real `run_multi_tile_project` path already verified
directly against the site-selection pipeline's own EMU tile handoffs.

Verified structurally before this script was written (not assumed): all
4 real KMLs load correctly (real areas 100.8ha, 135.2ha, 151.2ha, 15.4ha
— matching the source KMLs' own embedded area hints, e.g. "NGO 100H"),
and the full pipeline runs cleanly through ecoregion resolution before
failing at exactly and only the live-GEE-credentials boundary, with a
clear, actionable error — confirming this script's only remaining
requirement is real GEE authentication in the Colab session running it.

USAGE (in Colab):
    1. Upload this repo + the 4 site KMLs.
    2. Run: !earthengine authenticate   (or ee.Authenticate() in a cell)
    3. Edit config.yaml: set gee.project to your real GEE project id.
    4. python run_corbett_northshahdol.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("run_corbett")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from darukaa_reference.config import Config
from darukaa_reference.indicators import create_default_registry
from darukaa_reference.project_aggregation import run_multi_tile_project

# Real site KMLs — filenames as provided directly, not renamed.
SITE_DIR = Path(__file__).resolve().parent / "corbett_sites"
TILE_PATHS = [
    str(SITE_DIR / "Site_1_Masira_kml.kml"),
    str(SITE_DIR / "Site_2_Pipri_kml.kml"),
    str(SITE_DIR / "Site_3_Karpa_kml.kml"),
    str(SITE_DIR / "Site_4_Amanar_kml.kml"),
]
# Clean, real site names for reporting — the KMLs' own internal
# placemark names ("NGO 100H", "ngo 289+288", ...) are informal field
# labels, not names a client-facing report should use directly.
TILE_LABELS = ["Masira", "Pipri", "Karpa", "Amanar"]

PROJECT_NAME = "Corbett_NorthShahdol"
OUTPUT_DIR = "./outputs/corbett_northshahdol"


def main():
    for p in TILE_PATHS:
        if not Path(p).exists():
            raise FileNotFoundError(
                f"Expected site file not found: {p}\n"
                f"Place the 4 real Corbett KMLs in {SITE_DIR} before running, "
                f"using their original filenames."
            )

    config = Config.from_yaml(str(Path(__file__).resolve().parent / "config.yaml"))
    if config.gee_project in (None, "", "your-gee-project-id"):
        logger.warning(
            "config.yaml's gee.project is still the placeholder value — "
            "set it to your real GEE project id before this run can reach "
            "live Earth Engine data."
        )

    registry = create_default_registry()

    logger.info("Running Corbett North Shahdol — 4 real sites, non-compensatory project aggregation")
    result = run_multi_tile_project(
        config, registry, TILE_PATHS, TILE_LABELS,
        project_name=PROJECT_NAME, output_dir=OUTPUT_DIR,
        continue_on_tile_failure=True,  # one broken site is recorded explicitly, never silently drops the rest
    )

    logger.info("Done. Project-level report: %s/%s_project.json", OUTPUT_DIR, PROJECT_NAME)
    return result


if __name__ == "__main__":
    main()
