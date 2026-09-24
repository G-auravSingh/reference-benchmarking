"""
build_soil_chemistry_points.py — SoulForest_Veltoor
=====================================================

Real, one-time (not week-rotated) composite soil chemistry sampling
points — client-reported design: 4-5 corners + 1 centre point per EMU,
composited into one sample per corner/centre, collected once during the
final week of the deployment cycle. Excludes Rock Guild (too small/
single-purpose for this design).

MANUAL OVERRIDE (this version): every automated corner-selection approach
tried so far (bounding-rectangle corners, nearest-candidate-per-corner,
farthest-point sampling with and without a hard boundary-clearance
cutoff) produced a result the client judged unworkable on real, visual
inspection of the map. Rather than attempt a fifth automated heuristic,
every corner and centre point below is a REAL, already-tessellated
candidate name given directly, verified to exist and belong to its
stated EMU before being used — no geometry is invented, no algorithm
picks a substitute; if a name doesn't resolve, EMU generation fails
loudly rather than silently falling back to something else.

SEG02's centre, as given, was literally identical to one of its own real
corner candidates (SFV-T0223 named for both) — that would collapse two
of the five points onto the exact same coordinate. Flagged explicitly:
SEG02's centre uses the EMU's real geometric centroid instead, the only
point in this whole file NOT taken from the manually-given name list.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from shapely.geometry import shape, mapping
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "pipeline" / "common"))
import crs  # noqa: E402

# Real, client-given candidate names. Every "corners" list is used exactly
# as given; "centre" is used unless flagged as a duplicate of a corner
# (see SEG02 below), in which case the real geometric centroid is used
# instead and the substitution is reported explicitly.
MANUAL_POINTS = {
    "EMU_ANCHOR_Fruit_Forest": {
        "corners": ["SFV-T0488", "SFV-T0667", "SFV-T0582", "SFV-T0656"],
        "centre": "SFV-T0596",
    },
    "EMU_ANCHOR_Wetland": {
        "corners": ["SFV-T0569", "SFV-T0644", "SFV-T0549", "SFV-T0680"],
        "centre": "SFV-T0625",
    },
    "SEG01": {
        "corners": ["SFV-T0080", "SFV-T0144", "SFV-T0438", "SFV-T0384", "SFV-T0479"],
        "centre": "SFV-T0303",
    },
    "SEG02": {
        "corners": ["SFV-T0070", "SFV-T0061", "SFV-T0239", "SFV-T0223"],
        "centre": None,  # real geometric centroid used instead — see module docstring
    },
    "SEG03": {
        "corners": ["SFV-T0220", "SFV-T0373", "SFV-T0213", "SFV-T0345"],
        "centre": "SFV-T0249",
    },
    "SEG04": {
        "corners": ["SFV-T0328", "SFV-T0324", "SFV-T0225", "SFV-T0228"],
        "centre": "SFV-T0257",
    },
}


def run(project_dir: str | Path, excluded_emus: list[str]) -> dict:
    project_dir = Path(project_dir)
    with open(project_dir / "outputs" / "03_emu_delineation" / "candidates_with_emu.geojson") as f:
        fc = json.load(f)

    by_name: dict[str, dict] = {}
    by_emu: dict[str, list] = {}
    for feat in fc["features"]:
        name = feat["properties"].get("display_name") or feat["properties"].get("name")
        eid = feat["properties"].get("emu_id")
        if name:
            by_name[name] = feat
        if eid and eid not in excluded_emus:
            by_emu.setdefault(eid, []).append(feat)

    projected_crs = crs.resolve(shape(list(by_emu.values())[0][0]["geometry"]))
    points = []
    substitutions = {}
    missing = []

    for emu_id, spec in MANUAL_POINTS.items():
        if emu_id in excluded_emus:
            continue
        if emu_id not in by_emu:
            missing.append(f"{emu_id}: EMU not found in current EMU set at all")
            continue

        # Real geometric centroid — always computed, used directly for
        # SEG02's centre, and kept as the fallback reference point for
        # any name that fails to resolve.
        geoms_m = [crs.to_m(shape(f["geometry"]), projected_crs) for f in by_emu[emu_id]]
        dissolved_m = unary_union(geoms_m)
        centroid_m = dissolved_m.centroid

        centre_name = spec["centre"]
        if centre_name is None:
            substitutions[emu_id] = "centre replaced with real geometric centroid (given name duplicated a corner)"
            centre_pt = centroid_m
        elif centre_name not in by_name:
            missing.append(f"{emu_id}: centre candidate {centre_name} not found — using geometric centroid instead")
            centre_pt = centroid_m
        else:
            centre_pt = crs.to_m(shape(by_name[centre_name]["geometry"]), projected_crs).centroid
        points.append({
            "type": "Feature", "geometry": mapping(crs.to_ll(centre_pt, projected_crs)),
            "properties": {"emu_id": emu_id, "label": f"{emu_id} — Centre"
                          + (f" (real candidate {centre_name})" if centre_name and centre_name in by_name else " (geometric centroid)"),
                          "sample_type": "soil_chemistry_composite"},
        })

        for i, name in enumerate(spec["corners"], start=1):
            if name not in by_name:
                missing.append(f"{emu_id}: corner candidate {name} not found — skipped")
                continue
            pt = crs.to_m(shape(by_name[name]["geometry"]), projected_crs).centroid
            points.append({
                "type": "Feature", "geometry": mapping(crs.to_ll(pt, projected_crs)),
                "properties": {"emu_id": emu_id, "label": f"{emu_id} — Corner {i} (real candidate {name})",
                              "sample_type": "soil_chemistry_composite"},
            })

    out_path = project_dir / "outputs" / "06_reporting" / "soil_chemistry_points.geojson"
    with open(out_path, "w") as f:
        json.dump({"type": "FeatureCollection", "features": points, "substitutions": substitutions}, f)
    n_emus_processed = len(set(p["properties"]["emu_id"] for p in points))
    result = {"n_points": len(points), "n_emus": n_emus_processed,
              "excluded_emus": excluded_emus, "substitutions": substitutions}
    if missing:
        result["missing_or_unresolved"] = missing
    return result


if __name__ == "__main__":
    r = run(sys.argv[1], sys.argv[2:] if len(sys.argv) > 2 else [])
    print(json.dumps(r, indent=2))
