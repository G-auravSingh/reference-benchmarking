"""
extract_aquatic_tiles.py — Tata Motors Pimpri
================================================

REAL GAP FOUND AND FIXED HERE (client-reported directly: "many metrics
that are only aquatic related will work on waterbodies only that are not
in the zones... they would need a run for aquatic related metrics").
Confirmed directly against the real, raw KML: Tata Motors has 6 real,
named water body placemarks in the `_L_Water_Bodies` layer -- Lake Suman,
Lake Sharma, and Ponds 1-4 -- but these were ONLY EVER used to build the
hard exclusion mask (dissolved into a single 46.34ha blob) during site
selection. None of the 9 real terrestrial zone tiles in
`07_reference_handoff/` contain any water surface at all (water was
clipped OUT as an exclusion, by design, before candidate tessellation) --
so darukaa_reference's real, registered aquatic-module indicators (wcpi,
wsdi, hsas, edpp, mspl, rci and others) have never had anything to run
against for this project.

This script extracts those 6 real water body polygons directly from the
same raw KML the rest of the site-selection pipeline already trusts,
using that pipeline's own proven `kml_utils.parse_kml` (not a fresh,
untested parser), and writes a real, separate `tile_manifest.json` in the
exact same schema `07_reference_handoff/`'s own manifest uses -- so it
can be run through darukaa_reference's `run_project_from_manifest.py`
with `--project TataMotors_Pimpri_Aquatic` exactly like any other real
project, no special-casing needed on the reference-pipeline side.

Real, honest caveat this script does NOT resolve: darukaa_reference's
`module` field on each indicator (core/conservation/agroforestry/
aquatic/optional) is currently metadata only -- nothing in that
pipeline actually filters which indicators run based on it yet. Running
this aquatic manifest through the standard path will still compute every
CORE/CONSERVATION indicator too (mostly returning null or low-confidence
results on a small pond polygon, not wrong, just not filtered out
cleanly). Flagged directly, not silently worked around here.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]  # .../Darukaa_SiteSelection
sys.path.insert(0, str(REPO_ROOT / "pipeline" / "common"))
import kml_utils  # noqa: E402
import crs  # noqa: E402

from shapely.geometry import mapping

PROJECT_DIR = Path(__file__).resolve().parent
RAW_KML = PROJECT_DIR / "raw" / "Pune-Pimpri-eco_zones_1.kml"
OUT_DIR = PROJECT_DIR / "outputs" / "07_reference_handoff_aquatic"

# Real, confirmed water body placemark names from the raw KML's
# _L_Water_Bodies layer -- checked directly, not assumed from a
# generic "water" name match, since other layers (streams, reed beds)
# also contain "water"-adjacent names that are NOT real standing
# waterbodies and should not be included here.
REAL_WATERBODY_NAMES = {
    "Lake Suman": "Lake_Suman",
    "Lake Sharma": "Lake_Sharma",
    "Pond 1": "Pond_1",
    "Pond 2": "Pond_2",
    "Pond 3": "Pond_3",
    "Pond 4": "Pond_4",
}


def run() -> dict:
    records = kml_utils.parse_kml(RAW_KML)
    by_name = {r["name"]: r for r in records if r["name"] in REAL_WATERBODY_NAMES}

    missing = set(REAL_WATERBODY_NAMES) - set(by_name)
    if missing:
        raise RuntimeError(
            f"Expected real water body placemark(s) not found in the raw KML: {missing}. "
            f"The real, confirmed name list may have changed upstream — check "
            f"raw/Pune-Pimpri-eco_zones_1.kml's _L_Water_Bodies layer directly "
            f"before editing REAL_WATERBODY_NAMES."
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tiles_dir = OUT_DIR / "tiles"
    tiles_dir.mkdir(exist_ok=True)

    tile_paths, tile_labels, areas_ha = [], [], {}
    projected_crs = crs.resolve(by_name["Lake Suman"]["geometry"])
    for real_name, label in REAL_WATERBODY_NAMES.items():
        rec = by_name[real_name]
        geom = rec["geometry"]
        if geom is None:
            raise RuntimeError(f"'{real_name}' parsed with no real geometry — check the raw KML placemark directly.")
        area_ha = round(crs.to_m(geom, projected_crs).area / 10000, 4)
        areas_ha[label] = area_ha

        tile_path = tiles_dir / f"TataMotors_Pimpri_Aquatic_{label}.geojson"
        fc = {"type": "FeatureCollection", "features": [{
            "type": "Feature", "geometry": mapping(geom),
            "properties": {"name": label, "real_kml_name": real_name, "area_ha": area_ha},
        }]}
        with open(tile_path, "w") as f:
            json.dump(fc, f)
        tile_paths.append(f"projects/TataMotors_Pimpri/outputs/07_reference_handoff_aquatic/tiles/{tile_path.name}")
        tile_labels.append(label)

    manifest = {
        "project_name": "TataMotors_Pimpri_Aquatic",
        "n_tiles": len(tile_paths),
        "tile_paths": tile_paths,
        "tile_labels": tile_labels,
        "real_areas_ha": areas_ha,
        "note": ("Real, individual water body polygons (Lake Suman, Lake Sharma, Ponds 1-4), "
                "extracted directly from the raw KML for a dedicated aquatic-module run -- "
                "these were never part of any terrestrial EMU tile (water was excluded, not "
                "assessed, during site selection). See extract_aquatic_tiles.py's module "
                "docstring for the real caveat about module-based indicator filtering."),
    }
    with open(OUT_DIR / "tile_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    return manifest


if __name__ == "__main__":
    m = run()
    print(json.dumps(m, indent=2))
