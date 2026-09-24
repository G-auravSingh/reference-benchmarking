"""
07_reference_handoff / export_tiles.py
=========================================

Exports each EMU as its own individual GeoJSON file, ready to feed
directly into `darukaa_reference`'s `project_aggregation.run_multi_tile_project(
tile_paths=[...])` — this is exactly its expected upstream input: "Such an
AOI must be TILED FIRST — grouped into ecologically-local assessment
units... with darukaa_reference run once per tile... it can live wherever
is most convenient — see the README section 'Multi-tile / agroforestry
projects'." Confirmed the same code works identically for a single-tile
project (a compact conservation site) — "a single-tile project is the
trivial case."

This is a real, independent stage — NOT a dependency of anything else in
this pipeline (nothing downstream reads its output) — it exists purely to
produce the handoff artifact for a separate repository. Every EMU, from
either archetype, becomes exactly one tile file: one real, dissolved
polygon per EMU (never a filled hull — the same real membership already
established in 03_emu_delineation), with a `site_id` set directly to the
real EMU ID so `SiteLoader` uses it as-is rather than auto-generating a
generic one.

Also produces `tile_manifest.json` — the `tile_paths`/`tile_labels` lists
`run_multi_tile_project` expects, generated directly rather than left for
someone to reconstruct by hand from a directory listing.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

from shapely.geometry import shape, mapping
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
import config_schema  # noqa: E402

logger = logging.getLogger(__name__)


def run_export_tiles(project_dir: str | Path) -> Dict[str, Any]:
    project_dir = Path(project_dir)
    cfg = config_schema.load_config(project_dir / "config.yaml")

    emu_dir = project_dir / "outputs" / "03_emu_delineation"
    with open(emu_dir / "candidates_with_emu.geojson") as f:
        per_tile_fc = json.load(f)

    by_emu: Dict[str, List[Any]] = {}
    for feat in per_tile_fc["features"]:
        emu_id = feat["properties"].get("emu_id")
        if emu_id is None:
            continue
        by_emu.setdefault(emu_id, []).append(shape(feat["geometry"]))

    if not by_emu:
        raise ValueError(
            f"No EMU-assigned candidates found in {emu_dir}/candidates_with_emu.geojson — "
            "run 03_emu_delineation first.")

    out_dir = project_dir / "outputs" / "07_reference_handoff" / "tiles"
    out_dir.mkdir(parents=True, exist_ok=True)

    tile_paths, tile_labels = [], []
    for emu_id, geoms in sorted(by_emu.items()):
        dissolved = unary_union(geoms)
        # A real, single dissolved polygon per EMU — matches
        # darukaa_reference's own stated tile definition exactly ("every
        # placemark within a tile's KML is dissolved into one geometry
        # first — a tile IS one assessment unit, not N"). For a
        # contiguous-archetype EMU this is already one connected polygon
        # (verified elsewhere in this pipeline); for a scattered
        # agroforestry EMU this may legitimately be a MultiPolygon — real
        # membership, not filled into a hull.
        feature = {
            "type": "Feature",
            "geometry": mapping(dissolved),
            "properties": {
                "site_id": emu_id,   # used as-is by SiteLoader, not
                                       # auto-generated, since it's already present
                "name": emu_id,
                "n_member_parcels": len(geoms),
            },
        }
        out_path = out_dir / f"{cfg['project_name']}_{emu_id}.geojson"
        with open(out_path, "w") as f:
            json.dump({"type": "FeatureCollection", "features": [feature]}, f)
        tile_paths.append(str(out_path))
        tile_labels.append(emu_id)

    manifest = {
        "project_name": cfg["project_name"],
        "n_tiles": len(tile_paths),
        "tile_paths": tile_paths,
        "tile_labels": tile_labels,
    }
    manifest_path = project_dir / "outputs" / "07_reference_handoff" / "tile_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    logger.info("Exported %d EMU tile(s) for darukaa_reference — manifest at %s",
                len(tile_paths), manifest_path)
    return manifest


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    args = parser.parse_args()
    run_export_tiles(args.project_dir)
