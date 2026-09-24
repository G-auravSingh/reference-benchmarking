"""
05_metrics_rollup / rollup.py
===============================

Implements the tile->EMU->project aggregation designed in the architecture
discussion: full distribution (median, IQR, area-weighted mean) shown
ALONGSIDE a non-compensatory "worst tile/EMU" flag — never the flag alone,
per Aura's concern that a single declining tile inside an 11-tile EMU
shouldn't read as "no improvement happening" (son_score.py's existing
profile-first pattern, applied one level down).

SCOPE — deliberately limited. This module does NOT compute a composite
biodiversity/condition SCORE or a concern-class (Low/Moderate/High/
Critical) — that requires comparing against a reference ecoregion, which is
`darukaa_reference`'s job (explicitly deferred to "Phase 4: reference
pipeline updates" in the original brief). What this module DOES produce is
the distribution profile per covariate per EMU/project, and the fixed
EMU->reference handoff schema, so Phase 4 has something real to consume
instead of starting from nothing.

TWO INDICATOR FAMILIES (Q6 resolution, carried through from 03/rollup):
  PARCEL_INTRINSIC — computed on the tile's own polygon (NDVI_raw,
    TreeCover_Pct, BuiltUp_Pct). Affected by the small-tile confidence
    floor (`small_tile_area_ha_floor`) — a value from a sub-floor tile is
    still shown but flagged low-confidence, never silently dropped or
    silently trusted.
  LANDSCAPE_BUFFER — computed on a fixed buffer regardless of tile size
    (NatCoverPct_2km, EdgeDensity_2km, gHM, DistWater_m). Never affected by
    the small-tile floor — this is the whole point of that family split.

DIRECTIONALITY — needed only to identify "worst" for the non-compensatory
flag, not to compute a score. Declared explicitly per covariate rather than
assumed.
"""
from __future__ import annotations

import json
import logging
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from shapely.geometry import shape, mapping
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
import config_schema  # noqa: E402

logger = logging.getLogger(__name__)

PARCEL_INTRINSIC = [
    "NDVI_raw", "TreeCover_Pct", "BuiltUp_Pct", "Elev_m", "ElevStd_m",
    "TRI_m", "Slope_deg", "gHM", "DistWater_m", "LST_C", "NightLights",
]
# gHM and DistWater_m are parcel-intrinsic, not buffer-based — every
# covariate above is computed by the SAME polygon-level reduceRegions() call
# as NDVI_raw
# (the "POLYGON-LEVEL REDUCTION" section) — none of them use a buffer.
# Only the annulus/context-window metrics below genuinely do (a separate
# computeAnnulusMetrics() pass at a fixed radius, independent of tile
# size) — those are the only ones the small-tile confidence floor should
# NOT apply to.
LANDSCAPE_BUFFER = ["NatCoverPct_2km", "EdgeDensity_2km", "NatCoverPct_500m", "EdgeDensity_500m"]
# JRC_Water and PointOnBuilding deliberately excluded from rollup — both
# are pure binary pass/fail hard filters already enforced upstream
# (02_covariates); every surviving candidate is 0 by construction, so a
# distribution over them carries no information.
ALL_CONDITION_COVARIATES = PARCEL_INTRINSIC + LANDSCAPE_BUFFER

# "higher_better" / "lower_better" — used only to pick which end of the
# distribution is "worst" for the non-compensatory flag. Elev_m, ElevStd_m,
# TRI_m, Slope_deg, DistWater_m, LST_C, NightLights are deliberately absent
# — these are terrain/context descriptors, not condition indicators with a
# universal better/worse direction (a steep slope or a cold microclimate
# isn't "bad" the way high human-modification is). Shown in every
# distribution profile; never flagged as a worst-value.
DIRECTIONALITY = {
    "NDVI_raw": "higher_better",
    "TreeCover_Pct": "higher_better",
    "NatCoverPct_2km": "higher_better",
    "NatCoverPct_500m": "higher_better",
    "BuiltUp_Pct": "lower_better",
    "gHM": "lower_better",
    "EdgeDensity_2km": "lower_better",
    "EdgeDensity_500m": "lower_better",
}


def _percentile(sorted_vals: List[float], pct: float) -> float:
    if not sorted_vals:
        return float("nan")
    k = (len(sorted_vals) - 1) * pct
    f, c = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def _distribution_stats(values: List[float], areas: List[float]) -> Dict[str, Any]:
    if not values:
        return {"n_valid": 0}
    s = sorted(values)
    weighted_sum = sum(v * a for v, a in zip(values, areas))
    total_area = sum(areas)
    area_weighted_mean = weighted_sum / total_area if total_area > 0 else statistics.mean(values)
    return {
        "n_valid": len(values),
        "median": round(statistics.median(values), 4),
        "p25": round(_percentile(s, 0.25), 4),
        "p75": round(_percentile(s, 0.75), 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "area_weighted_mean": round(area_weighted_mean, 4),
    }


def _tiles_by_emu(fc: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Both archetypes produce the same shape here — a per-MEMBER-TILE
    feature collection tagged with emu_id, so a single code path handles
    the rollup for both, rather than a separate one per archetype."""
    by_emu: Dict[str, List[Dict[str, Any]]] = {}
    for feat in fc["features"]:
        emu_id = feat["properties"].get("emu_id")
        if emu_id is None:
            continue
        by_emu.setdefault(emu_id, []).append(feat)
    return by_emu


def rollup_emu(tiles: List[Dict[str, Any]], small_tile_floor_ha: float) -> Dict[str, Any]:
    per_covariate = {}
    for cov in ALL_CONDITION_COVARIATES:
        values, areas, low_conf_values, low_conf_areas = [], [], [], []
        for t in tiles:
            props = t["properties"]
            v = props.get(cov)
            if not isinstance(v, (int, float)):
                continue
            area_ha = props.get("area_ha") or props.get("attr_area_ha_computed") or 0.0
            if cov in PARCEL_INTRINSIC and small_tile_floor_ha and area_ha < small_tile_floor_ha:
                # REAL BUG FIXED HERE (confirmed directly against Tata
                # Motors: the raw GEE covariate CSV has real, populated
                # NDVI/TreeCover/BuiltUp/Elevation/etc. values for every
                # cell — nothing wrong with the GEE run at all — but this
                # function's own docstring says a sub-floor value should
                # be "shown but flagged low-confidence, never silently
                # dropped", while the code actually did the opposite:
                # `continue` here meant a sub-floor value never reached
                # `values` at all, so whenever EVERY tile in an EMU sits
                # below the floor (exactly TM's real situation — its
                # entire 25m grid is 0.0625ha, uniformly under the
                # 0.25ha floor), the whole covariate silently vanished
                # from that EMU's row instead of appearing with a
                # confidence flag as documented. Low-confidence values
                # are now kept in their own real, separately-computed
                # distribution and surfaced explicitly, never blended
                # into the same numbers as confidently-sized tiles.
                low_conf_values.append(float(v))
                low_conf_areas.append(float(area_ha) or 1.0)
                continue
            values.append(float(v))
            areas.append(float(area_ha) or 1.0)

        if not values and not low_conf_values:
            continue
        if values:
            stats = _distribution_stats(values, areas)
        else:
            # No tile in this EMU clears the confidence floor for this
            # covariate at all — the ONLY real data available is
            # low-confidence, so it's surfaced as such rather than
            # silently omitted. n_valid=0 keeps this distinguishable
            # from a genuine "some tiles confident, some not" mix below.
            stats = {"n_valid": 0}
        stats["n_low_confidence_excluded"] = len(low_conf_values)
        if low_conf_values:
            stats["low_confidence_stats"] = _distribution_stats(low_conf_values, low_conf_areas)
        per_covariate[cov] = stats

    return per_covariate


def _ecological_rationale(emu_id: str, tiles: List[Dict[str, Any]], is_contiguous: bool) -> str:
    if is_contiguous:
        emu_type = tiles[0]["properties"].get("emu_type", "unknown")
        if emu_type == "ecological_anchor":
            return "Client-identified ecological feature, adopted directly as an EMU."
        if emu_type == "segmentation_derived":
            return f"GEE SNIC segmentation-derived unit, {len(tiles)} grid cells."
        return "Unclassified."
    n = len(tiles)
    return f"Ecological clustering over {n} tiles (see emu_delineation_report.json for active features and silhouette diagnostics)."


def run_rollup(project_dir: str | Path) -> Dict[str, Any]:
    project_dir = Path(project_dir)
    cfg = config_schema.load_config(project_dir / "config.yaml")
    is_contiguous = cfg["archetype"] in ("conservation", "industrial")
    emu_dir = project_dir / "outputs" / "03_emu_delineation"
    emu_path = emu_dir / "candidates_with_emu.geojson"  # same filename, both
    # archetypes now (see _tiles_by_emu docstring for why this was a bug fix)
    if not emu_path.exists():
        raise FileNotFoundError(f"{emu_path} not found — run 03_emu_delineation first.")
    with open(emu_path) as f:
        fc = json.load(f)

    by_emu = _tiles_by_emu(fc)
    small_floor = cfg["small_tile_area_ha_floor"]

    emu_results = {}
    for emu_id, tiles in by_emu.items():
        emu_results[emu_id] = {
            "n_tiles": len(tiles),
            "covariates": rollup_emu(tiles, small_floor),
            "ecological_rationale": _ecological_rationale(emu_id, tiles, is_contiguous),
        }

    # Project-level: non-compensatory "worst EMU median" per covariate,
    # shown alongside the full EMU-median distribution — never the worst
    # value alone (this IS the fix for the "one bad tile reads as no
    # improvement" problem, one level up).
    project_covariates = {}
    for cov in ALL_CONDITION_COVARIATES:
        # REAL FOLLOW-UP FIX: an EMU whose covariate entry is
        # low-confidence-only (n_valid==0, see rollup_emu) has no real
        # "median" key to aggregate here — including it in the
        # cross-EMU median-of-medians would either crash (KeyError) or,
        # if guarded carelessly, silently treat a low-confidence number
        # as equally trustworthy as a confidently-sized one. Excluded
        # from THIS project-level statistic specifically; still fully
        # visible per-EMU (see emu_results) with its own honest flag.
        emu_medians = [(eid, r["covariates"][cov]["median"]) for eid, r in emu_results.items()
                       if cov in r["covariates"] and r["covariates"][cov].get("n_valid", 0) > 0]
        if not emu_medians:
            continue
        values_only = [v for _, v in emu_medians]
        direction = DIRECTIONALITY.get(cov)
        worst_emu_id, worst_val = None, None
        if direction == "higher_better":
            worst_emu_id, worst_val = min(emu_medians, key=lambda t: t[1])
        elif direction == "lower_better":
            worst_emu_id, worst_val = max(emu_medians, key=lambda t: t[1])
        project_covariates[cov] = {
            "n_emus_with_data": len(emu_medians),
            "median_of_emu_medians": round(statistics.median(values_only), 4),
            "min_emu_median": round(min(values_only), 4),
            "max_emu_median": round(max(values_only), 4),
            "worst_emu_id": worst_emu_id,
            "worst_emu_median": round(worst_val, 4) if worst_val is not None else None,
        }
        # A client reading this table would otherwise see e.g. "BuiltUp_Pct,
        # worst EMU: Fruit Forest, max 100" with no indication that the
        # value is affected by a known land-cover classifier
        # misclassification (see 02_covariates' NDVI-override warning) —
        # that warning excludes affected candidates from device eligibility,
        # but the raw covariate VALUE shown here is untouched by it and can
        # still mislead on its own, so it's cross-referenced here too.
        if cov == "BuiltUp_Pct" and max(values_only) > 80:
            report_note = (
                f"BuiltUp_Pct's high end (up to {round(max(values_only),1)}, worst EMU "
                f"{worst_emu_id}) may reflect the land-cover classifier misclassification "
                "documented in 02_covariates' warnings, not necessarily real built area — "
                "cross-check against that project's NDVI values for the same candidates "
                "before treating this number as a finding.")
            project_covariates[cov]["caveat"] = report_note

    # EMU -> darukaa_reference handoff export (real geometry — see
    # 07_reference_handoff/export_tiles.py for the per-EMU FILE export
    # darukaa_reference's tile_paths actually needs; this combined
    # multi-feature file is a convenient single-file reference, not what
    # gets fed to SiteLoader directly).
    #
    emu_geoms: Dict[str, Any] = {}
    for feat in fc["features"]:
        emu_id = feat["properties"].get("emu_id")
        if emu_id is None or emu_id not in by_emu:
            continue
        emu_geoms.setdefault(emu_id, []).append(shape(feat["geometry"]))
    handoff = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": mapping(unary_union(emu_geoms[emu_id])) if emu_id in emu_geoms else None,
                "properties": {
                    "emu_id": emu_id,
                    "n_tiles": r["n_tiles"],
                    "ecological_rationale": r["ecological_rationale"],
                    "dominant_habitat_type": None,  # PENDING — needs land-cover
                    # classification not yet computed by this pipeline; never
                    # fabricated here.
                    "covariate_profile": r["covariates"],
                },
            }
            for emu_id, r in emu_results.items()
        ],
    }

    report = {
        "project_name": cfg["project_name"],
        "n_emus": len(emu_results),
        "emu_results": emu_results,
        "project_covariates": project_covariates,
        "warnings": [],
    }
    if not any(r["covariates"] for r in emu_results.values()):
        report["warnings"].append(
            "No condition covariates present in any EMU yet — GEE hasn't been "
            "run for this project. Rollup structure is real; the numbers "
            "inside it are not, because there aren't any yet.")

    missing_parcel_intrinsic = [c for c in PARCEL_INTRINSIC if c not in project_covariates]
    if missing_parcel_intrinsic and any(r["covariates"] for r in emu_results.values()):
        report["warnings"].append(
            f"{missing_parcel_intrinsic} have ZERO project-level coverage despite "
            "other covariates having real data — found while validating against "
            f"Soulforest's real GEE output: this project's grid cell size "
            f"({cfg.get('contiguous_grid_cell_size_m', '?')}m, "
            f"{round((cfg.get('contiguous_grid_cell_size_m', 25)/100.0)**2, 4)} ha) sits "
            f"BELOW small_tile_area_ha_floor ({cfg['small_tile_area_ha_floor']} ha), so "
            "every single cell is excluded from these parcel-intrinsic metrics as "
            "low-confidence — not a bug, the floor is doing exactly what it's "
            "configured to do, but it silently zeroes out this whole indicator "
            "family for any contiguous-archetype project at this resolution. "
            "Needs a decision: raise the grid cell size, lower the floor for "
            "contiguous archetypes specifically, or accept these indicators "
            "being unavailable at this resolution.")

    # A covariate showing IDENTICAL values (zero variance) across
    # every single EMU is almost never real ecological signal — it's
    # usually a computation defect (a masked/frozen band, a units error, a
    # wrong-class filter) presenting as data.
    for cov, d in project_covariates.items():
        if d.get("min_emu_median") == d.get("max_emu_median"):
            note = ""
            if cov == "TreeCover_Pct":
                note = (
                    " TreeCover_Pct is computed from an NDVI threshold (0.3) on the same "
                    "validated Sentinel-2 composite already used for NDVI_raw, not from any "
                    "land-cover classification — land-cover-based tree-cover classes have "
                    "shown genuine classifier limitations for some vegetation types (a flat "
                    "0.0 despite real NDVI vegetation of 0.24-0.5, confirmed against "
                    "NatCoverPct_2km). If this report predates that fix, re-run against a "
                    "fresh GEE export before treating TreeCover_Pct as reliable; NDVI_raw "
                    "remains the reliable vegetation-condition indicator in the meantime.")
            report["warnings"].append(
                f"{cov}: identical value ({d['min_emu_median']}) across every EMU — "
                "zero variance across a whole site is almost always a computation "
                "defect, not real ecological uniformity. Treat this covariate as "
                f"unreliable until investigated at the GEE script level.{note}")
        if d.get("caveat"):
            report["warnings"].append(d["caveat"])

    # Scientific defensibility check: flags any pair of EMUs whose
    # covariate profiles are statistically very close, using the numeric
    # covariates already computed above, normalized by the project's own
    # observed range so the comparison isn't dominated by covariates with
    # naturally larger raw units — a real, honest finding to hand to field
    # reconnaissance rather than silently accept or silently re-merge two
    # segments that may be a spectral oversegmentation rather than a
    # genuine ecological distinction.
    #
    # LST_C (1km native resolution) and NightLights (~500m) are far
    # coarser than a typical EMU and contribute pixel-sampling noise, not
    # real signal, at this spatial scale — a single coarse covariate can
    # dominate the normalized distance and hide a real, meaningful
    # similarity behind noise, so both are excluded here, matching this
    # pipeline's own documented caveat about these two covariates being
    # "informative at landscape scale only."
    numeric_covs = [c for c in ALL_CONDITION_COVARIATES
                    if c not in ("LST_C", "NightLights")
                    and any(c in r["covariates"] for r in emu_results.values())
                    and all(isinstance(r["covariates"].get(c, {}).get("median"), (int, float))
                          for r in emu_results.values() if c in r["covariates"])]
    similar_pairs = []
    if len(emu_results) > 1 and numeric_covs:
        emu_ids_list = list(emu_results.keys())
        cov_ranges = {}
        for c in numeric_covs:
            vals = [r["covariates"][c]["median"] for r in emu_results.values() if c in r["covariates"]]
            cov_ranges[c] = (max(vals) - min(vals)) or 1.0
        for i, e1 in enumerate(emu_ids_list):
            for e2 in emu_ids_list[i + 1:]:
                shared = [c for c in numeric_covs if c in emu_results[e1]["covariates"]
                         and c in emu_results[e2]["covariates"]]
                if len(shared) < 3:
                    continue
                sq_diffs = [((emu_results[e1]["covariates"][c]["median"]
                            - emu_results[e2]["covariates"][c]["median"]) / cov_ranges[c]) ** 2
                           for c in shared]
                norm_dist = (sum(sq_diffs) / len(sq_diffs)) ** 0.5
                if norm_dist < 0.08:
                    similar_pairs.append((e1, e2, round(norm_dist, 4)))
    if similar_pairs:
        report["warnings"].append(
            f"SCIENTIFIC DEFENSIBILITY: {len(similar_pairs)} EMU pair(s) show near-identical "
            f"covariate profiles (normalized distance < 0.08): {similar_pairs}. Image "
            "segmentation found a real spectral discontinuity between them, but their "
            "aggregate covariate values barely differ — plausibly SNIC oversegmentation "
            "rather than a genuine ecological distinction. Field reconnaissance should "
            "confirm or correct this before treating them as separately meaningful strata "
            "in any client-facing ecological interpretation.")

    out_dir = project_dir / "outputs" / "05_metrics_rollup"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "metrics_rollup_report.json", "w") as f:
        json.dump(report, f, indent=2)
    with open(out_dir / "emu_reference_handoff.geojson", "w") as f:
        json.dump(handoff, f, indent=2)

    # stratum_profile.csv — "what each segment IS, in covariate terms".
    # One row per EMU, one column per covariate's median — the source data
    # behind the report's own stratification table, at full covariate
    # resolution for anyone who wants to see it directly.
    csv_cols = ["EMU ID", "N candidates", "Ecological rationale"] + list(ALL_CONDITION_COVARIATES)
    csv_rows = []
    for emu_id, r in emu_results.items():
        row = [emu_id, r["n_tiles"], r.get("ecological_rationale", "")]
        for cov in ALL_CONDITION_COVARIATES:
            stat = r["covariates"].get(cov)
            if not stat:
                row.append("")
            elif stat.get("n_valid", 0) > 0:
                row.append(stat["median"])
            else:
                # REAL FIX: every tile in this EMU is below the small-tile
                # confidence floor for this covariate — the real value is
                # shown (not left blank, matching this module's own
                # documented intent) but visibly marked so it's never
                # mistaken for a confidently-sized-tile statistic.
                lc = stat.get("low_confidence_stats", {})
                row.append(f"{lc.get('median', '')} (low-confidence, n={stat.get('n_low_confidence_excluded', 0)})"
                           if lc else "")
        csv_rows.append(row)
    import csv as csv_module
    with open(out_dir / "stratum_profile.csv", "w", newline="") as f:
        writer = csv_module.writer(f)
        writer.writerow(csv_cols)
        writer.writerows(csv_rows)

    logger.info("Metrics rollup complete: %d EMUs, %d project-level covariates with data",
                len(emu_results), len(project_covariates))
    return report


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    args = parser.parse_args()
    run_rollup(args.project_dir)
