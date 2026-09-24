"""
03_emu_delineation / ecological_clustering.py
================================================

EMU delineation path for SCATTERED archetypes (agroforestry: Soova, GV).
Segmentation (see segmentation_reconciliation.py) cannot run here — there is
no contiguous raster surface to segment, only hundreds/thousands of small,
physically separated farm polygons. Method instead (per architecture
discussion): barrier-aware ecological clustering, producing EMUs that are
MULTIPART features (the member farm polygons themselves), never a filled
enclosing hull.

TWO-TIER FEATURE SET — this module auto-detects which tier is available and
says so plainly, rather than silently running on less than what's possible:
  Tier 2 (full): 02_covariates/candidates_with_covariates.geojson exists —
     satellite covariates (NDVI, tree cover, terrain, connectivity, gHM,
     DistWater_m) join the clustering features.
  Tier 1 (attribute-only): GEE hasn't been run yet. Falls back to whatever
     canonical attributes 01_ingestion actually found for this project
     (area_ha, plantation_year, admin_block, ...). This is a REAL,
     genuinely-run clustering on REAL data — not a placeholder — it's just
     missing the satellite half of the feature table until GEE catches up.
     Every output from a Tier-1 run is stamped feature_tier="attribute_only"
     so nobody downstream mistakes it for the final clustering.

HARD-BARRIER PARTITIONING — implements the ChatGPT transcript's point that
distance alone shouldn't split/merge farms, but a real discontinuity should.
Lacking an actual river/mountain GIS layer right now, `admin_district` is
used as the working proxy for "major discontinuity" (a district boundary in
Odisha very often does coincide with a real physiographic change, and it's
already 99%+ populated in both real KMLs) — this is a declared APPROXIMATION,
not a claim that administrative and ecological boundaries are the same
thing. Candidates never get clustered across a hard-barrier group boundary;
K is then chosen independently within each group, so a genuinely small,
ecologically distinct group (e.g. one district with only 8 parcels) isn't
diluted into a district with 1,800.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from shapely.geometry import shape
from scipy.spatial.distance import pdist

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
import clustering_utils  # noqa: E402
import config_schema      # noqa: E402
import crs                 # noqa: E402

logger = logging.getLogger(__name__)

SATELLITE_NUMERIC_COLS = [
    "NDVI_raw", "TreeCover_Pct", "Elev_m", "TRI_m",
    "NatCoverPct_2km", "EdgeDensity_2km", "gHM", "DistWater_m",
]
ATTRIBUTE_NUMERIC_COLS = ["attr_area_ha_computed", "attr_plantation_year_numeric"]
ATTRIBUTE_CATEGORICAL_COLS = ["attr_admin_block"]
BARRIER_ATTR_DEFAULT = "attr_admin_district"

_YEAR_RE = re.compile(r"(\d{4})")


def _parse_year(val: Any) -> Optional[float]:
    """Handles both real formats seen: Soova's '2025', GV's '2022-23'."""
    if val is None:
        return None
    m = _YEAR_RE.search(str(val))
    return float(m.group(1)) if m else None


def _load_candidates(project_dir: Path) -> Tuple[Dict[str, Any], str]:
    tier2_path = project_dir / "outputs" / "02_covariates" / "candidates_with_covariates.geojson"
    tier1_path = project_dir / "outputs" / "01_ingestion" / "candidates.geojson"
    if tier2_path.exists():
        with open(tier2_path) as f:
            return json.load(f), "full_with_satellite_covariates"
    if not tier1_path.exists():
        raise FileNotFoundError(f"Neither {tier2_path} nor {tier1_path} exist — run 01_ingestion first.")
    logger.warning(
        "No GEE covariates yet (%s absent) — running Tier-1 attribute-only "
        "clustering on %s. Re-run this module once the GEE CSV lands to get "
        "the full-covariate EMU set.", tier2_path.name, tier1_path.name)
    with open(tier1_path) as f:
        return json.load(f), "attribute_only"


def _build_feature_record(props: Dict[str, Any], numeric_cols: List[str],
                            categorical_cols: List[str]) -> Dict[str, Any]:
    rec = {}
    for col in numeric_cols:
        v = props.get(col)
        rec[col] = float(v) if isinstance(v, (int, float)) else None
    for col in categorical_cols:
        rec[col] = props.get(col)
    return rec


def _allocate_k_across_partitions(partition_sizes: Dict[str, int], total_k_max: int) -> Dict[str, int]:
    """Proportional allocation of the project's overall k_max across
    hard-barrier partitions, by candidate count, with every non-empty
    partition guaranteed at least 1 (never zero EMUs for a real district
    with parcels in it, however small)."""
    total_n = sum(partition_sizes.values())
    if total_n == 0:
        return {}
    raw = {p: max(1, round(total_k_max * n / total_n)) for p, n in partition_sizes.items()}
    # Rounding can overshoot total_k_max slightly; trim from the largest
    # allocations first rather than from the guaranteed minimums.
    while sum(raw.values()) > total_k_max and any(v > 1 for v in raw.values()):
        biggest = max(raw, key=lambda p: raw[p])
        raw[biggest] -= 1
    return raw


def run_ecological_clustering(project_dir: str | Path) -> Dict[str, Any]:
    project_dir = Path(project_dir)
    cfg = config_schema.load_config(project_dir / "config.yaml")
    if cfg["archetype"] != "agroforestry":
        raise ValueError(
            f"ecological_clustering is for scattered/agroforestry archetypes; "
            f"{cfg['project_name']} is archetype={cfg['archetype']!r} — use "
            f"segmentation_reconciliation.py instead.")

    fc, feature_tier = _load_candidates(project_dir)
    all_features = fc["features"]
    # A candidate that failed the built-up/water hard filter (from
    # 02_covariates) should never become an EMU member or device
    # candidate, regardless of archetype — the same rule
    # segmentation_reconciliation.py applies for contiguous archetypes.
    features = [f for f in all_features if f["properties"].get("hard_filter_pass", True)]
    n_filtered_out = len(all_features) - len(features)
    n_candidates = len(features)

    numeric_cols = list(ATTRIBUTE_NUMERIC_COLS)
    categorical_cols = list(ATTRIBUTE_CATEGORICAL_COLS)
    if feature_tier == "full_with_satellite_covariates":
        numeric_cols = SATELLITE_NUMERIC_COLS + numeric_cols

    # Only include a stratification attribute if config asked for it AND
    # it's actually present in this project's data (per Aura: use plantation
    # year/block/type when available — "available" is checked, not assumed).
    active_numeric, active_categorical = [], []
    for col in numeric_cols:
        canonical = col.replace("attr_", "").replace("_numeric", "")
        if canonical in ("plantation_year",) and canonical not in cfg["stratification_attributes"]:
            continue
        active_numeric.append(col)
    for col in categorical_cols:
        canonical = col.replace("attr_", "")
        if canonical == "admin_block" and canonical not in cfg["stratification_attributes"]:
            continue
        active_categorical.append(col)

    records = []
    for feat in features:
        props = dict(feat["properties"])
        yr = _parse_year(props.get("attr_plantation_year"))
        props["attr_plantation_year_numeric"] = yr
        area = props.get("area_ha")
        props["attr_area_ha_computed"] = float(area) if area is not None else None
        records.append(_build_feature_record(props, active_numeric, active_categorical))

    # Projected centroids for the spatial-connectivity constraint below —
    # see clustering_utils.spatial_connectivity()'s docstring for why this
    # constraint is necessary.
    projected_crs = crs.resolve(shape(features[0]["geometry"]))
    import numpy as np
    centroids_xy = np.array([
        [crs.to_m(shape(f["geometry"]), projected_crs).centroid.x,
         crs.to_m(shape(f["geometry"]), projected_crs).centroid.y]
        for f in features
    ])

    # SECOND FIX for the same real issue, found by checking spatial spread
    # after the connectivity fix above: a k-NN connectivity graph alone can
    # still "chain" — A near B near C near D, but A and D end up far apart,
    # because connectivity only requires a PATH to exist, not a short
    # overall diameter. Confirmed directly: one real Soova EMU spanned
    # 22 km despite every consecutive link being locally close. Adding
    # projected X/Y as Gower features too (not just a hard connectivity
    # permission) means spatial distance now also counts toward
    # dissimilarity itself, actively penalizing long chains instead of
    # merely permitting them. Injected directly into each record here
    # (rather than extending active_numeric before the records loop above)
    # so the ordering is unambiguous — every record always gets its real
    # coordinate regardless of what the loop above happened to do first.
    for i, rec in enumerate(records):
        rec["attr_x_m"] = float(centroids_xy[i, 0])
        rec["attr_y_m"] = float(centroids_xy[i, 1])
    active_numeric = active_numeric + ["attr_x_m", "attr_y_m"]

    barrier_attr = cfg.get("hard_barrier_attribute", BARRIER_ATTR_DEFAULT)
    partitions: Dict[str, List[int]] = {}
    for i, feat in enumerate(features):
        val = feat["properties"].get(barrier_attr) or "unknown_barrier_group"
        partitions.setdefault(val, []).append(i)

    k_bounds = clustering_utils.compute_k_bounds(
        n_candidates=n_candidates,
        n_devices=cfg["n_devices"],
        project_duration_weeks=cfg["project_duration_weeks"],
        cycle_length_days=cfg["cycle_length_days"],
        logistics_buffer_days=cfg["logistics_buffer_days"],
        emu_min_tiles=cfg["emu_min_tiles"],
    )
    partition_sizes = {p: len(idxs) for p, idxs in partitions.items()}
    k_alloc = _allocate_k_across_partitions(partition_sizes, k_bounds["k_max"])

    emu_assignment = [None] * n_candidates  # candidate index -> emu_id
    partition_reports = {}

    for partition_val, idxs in partitions.items():
        sub_records = [records[i] for i in idxs]
        k_max_here = min(k_alloc.get(partition_val, 1), len(idxs))
        D = clustering_utils.gower_distance_matrix(sub_records, active_numeric, active_categorical)
        connectivity = clustering_utils.spatial_connectivity(centroids_xy[idxs])
        best_k, scores, labels = clustering_utils.select_k_via_silhouette(
            D, k_min=k_bounds["k_min"], k_max=k_max_here, connectivity=connectivity)

        # EMU membership is exactly what silhouette-based clustering
        # produced, unmodified — no post-hoc spatial-compactness splitting
        # is applied here. A severe spatial outlier doesn't need to be
        # split into its own EMU: ecologically it can stay exactly where
        # clustering put it (real metrics still get computed over its true
        # membership, outliers included). It just should never be
        # ELIGIBLE AS A DEVICE POSITION, since sending a field team hours
        # away for 1-2 parcels isn't viable regardless of which EMU
        # they're nominally grouped into — that's a `03b_position_scoring`
        # concern (see its outlier exclusion), not one this stage acts on.
        # A per-EMU spread warning naming actual EMUs and candidate counts
        # is issued there, which is why no partition-level spread warning
        # is issued here.
        spatial_spread_warning = None

        labels = clustering_utils.merge_orphan_clusters(
            labels, centroids_xy[idxs], min_cluster_size=cfg["emu_min_tiles"])

        # Merging an orphan cluster into another (above) reassigns its
        # members' labels but never renumbers the remaining label VALUES —
        # a label that gets fully absorbed leaves a gap (e.g. original
        # labels 0,1,2 with label 1 merged away become EMU names "_1" and
        # "_3", skipping "_2"). Renumbered sequentially, by descending
        # size (so "_1" is always the partition's largest
        # EMU, a consistent, meaningful convention rather than an
        # arbitrary leftover clustering index), right before ID assignment.
        unique_labels_by_size = sorted(np.unique(labels), key=lambda lab: -(labels == lab).sum())
        relabel_map = {old: new for new, old in enumerate(unique_labels_by_size)}
        labels = np.array([relabel_map[lab] for lab in labels])

        safe_partition_name = re.sub(r"[^A-Za-z0-9]+", "_", str(partition_val)).strip("_") or "unknown"
        for local_idx, global_idx in enumerate(idxs):
            emu_id = f"{cfg['project_name']}_EMU_{safe_partition_name}_{int(labels[local_idx]) + 1}"
            emu_assignment[global_idx] = emu_id

        partition_reports[partition_val] = {
            "n_candidates": len(idxs),
            "k_max_allocated": k_alloc.get(partition_val, 1),
            "k_selected": best_k,
            "n_emus_after_compactness_split": len(set(labels.tolist())) if hasattr(labels, "tolist") else len(set(labels)),
            "silhouette_by_k": scores,
            "spatial_spread_warning": spatial_spread_warning,
        }

    # Attach EMU id back onto candidate properties, write outputs.
    emu_members: Dict[str, List[int]] = {}
    for i, feat in enumerate(features):
        feat["properties"]["emu_id"] = emu_assignment[i]
        emu_members.setdefault(emu_assignment[i], []).append(i)

    emu_summary = []
    for emu_id, member_idxs in emu_members.items():
        areas = [features[i]["properties"].get("area_ha") or 0.0 for i in member_idxs]
        emu_summary.append({
            "emu_id": emu_id,
            "n_tiles": len(member_idxs),
            "total_area_ha": round(sum(areas), 3),
            "member_candidate_names": [features[i]["properties"]["name"] for i in member_idxs],
        })

    report = {
        "project_name": cfg["project_name"],
        "method": "ecological_clustering",
        "feature_tier": feature_tier,
        "active_numeric_features": active_numeric,
        "active_categorical_features": active_categorical,
        "barrier_attribute_used": barrier_attr,
        "k_bounds": k_bounds,
        "n_partitions": len(partitions),
        "n_emus_total": len(emu_members),
        "partition_reports": partition_reports,
        "emu_summary": emu_summary,
        "warnings": [],
    }
    if n_filtered_out > 0:
        report["warnings"].append(
            f"{n_filtered_out} candidate(s) excluded before clustering — failed the "
            "built-up/water hard filter in 02_covariates. Never eligible as EMU "
            "members or device candidates, regardless of archetype.")
    if feature_tier == "attribute_only":
        report["warnings"].append(
            "PROVISIONAL RUN: no satellite covariates yet — clustering used "
            f"only {active_numeric + active_categorical}. Re-run once GEE "
            "covariates are ingested (02_covariates).")

    small_emus = [e for e in emu_summary if e["n_tiles"] < cfg["emu_min_tiles"]]
    if small_emus:
        report["warnings"].append(
            f"{len(small_emus)} EMU(s) below emu_min_tiles={cfg['emu_min_tiles']}: "
            f"{[e['emu_id'] for e in small_emus]}")

    for pv, pr in partition_reports.items():
        if pr.get("spatial_spread_warning"):
            report["warnings"].append(pr["spatial_spread_warning"])

    out_dir = project_dir / "outputs" / "03_emu_delineation"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "candidates_with_emu.geojson", "w") as f:
        json.dump(fc, f)
    with open(out_dir / "emu_delineation_report.json", "w") as f:
        json.dump(report, f, indent=2)

    logger.info("Ecological clustering complete [%s]: %d partitions -> %d EMUs "
                "(k_max=%d from logistics=%d/replication=%d)",
                feature_tier, len(partitions), len(emu_members),
                k_bounds["k_max"], k_bounds["k_max_logistics"], k_bounds["k_max_replication"])
    return report


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    args = parser.parse_args()
    run_ecological_clustering(args.project_dir)
