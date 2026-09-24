"""
clustering_utils.py — Gower distance + silhouette-based K selection
=====================================================================

Written by hand rather than pulled from a `gower` PyPI package: the formula
is a handful of lines, and for a "scientifically defensible" pipeline
(Aura's standing requirement — every architectural decision cited/auditable)
it's worth a reviewer being able to read the exact distance computation
here rather than trust an unmaintained third-party package's internals.

Gower distance handles MIXED numeric + categorical features in one
distance metric — needed because our clustering features are a genuine mix
(NDVI/tree-cover = numeric, admin_block/plantation_year-bucket = categorical
or ordinal). Per-column missing values are excluded from that pair's
distance rather than imputed — Gower's standard missing-data handling —
since imputing a fake NDVI value for a candidate whose GEE covariates
haven't landed yet would quietly bias its cluster assignment.

K SELECTION is output-driven rather than a fixed target: EMU count is a
result of ecological similarity, bounded by device/logistics feasibility
(compute_k_bounds below), not a number imposed beforehand.
silhouette_score over the feasible range of K gives a real, checkable
diagnostic instead of a guessed number.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy.spatial.distance import pdist, cdist
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.metrics import silhouette_score
from sklearn.neighbors import kneighbors_graph

logger = logging.getLogger(__name__)


def gower_distance_matrix(
    records: List[Dict[str, Any]],
    numeric_cols: List[str],
    categorical_cols: List[str],
) -> np.ndarray:
    """records: list of {col_name: value or None}. Returns an (n, n)
    symmetric distance matrix in [0, 1] (Gower's normalized range)."""
    n = len(records)
    D = np.zeros((n, n))

    # Numeric columns: normalize by the observed range across all records
    # (Gower's standard convention), guarding against a constant/degenerate
    # column (range=0) by treating it as contributing zero distance rather
    # than dividing by zero.
    ranges = {}
    for col in numeric_cols:
        vals = [r[col] for r in records if r.get(col) is not None]
        if vals:
            lo, hi = min(vals), max(vals)
            ranges[col] = (lo, hi - lo if hi > lo else 1.0)
        else:
            ranges[col] = (0.0, 1.0)

    for i in range(n):
        for j in range(i + 1, n):
            total, count = 0.0, 0
            for col in numeric_cols:
                vi, vj = records[i].get(col), records[j].get(col)
                if vi is None or vj is None:
                    continue
                lo, rng = ranges[col]
                total += abs(vi - vj) / rng
                count += 1
            for col in categorical_cols:
                vi, vj = records[i].get(col), records[j].get(col)
                if vi is None or vj is None:
                    continue
                total += 0.0 if vi == vj else 1.0
                count += 1
            d = (total / count) if count > 0 else 1.0  # no shared observed
            # columns at all -> treat as maximally dissimilar rather than
            # silently identical (0.0 would be the wrong default here).
            D[i, j] = D[j, i] = d
    return D


def compute_k_bounds(
    n_candidates: int,
    n_devices: int,
    project_duration_weeks: float,
    cycle_length_days: int,
    logistics_buffer_days: int,
    emu_min_tiles: int,
) -> Dict[str, int]:
    """K_max from two independent constraints, take the tighter one:
      - logistics: every EMU must be reachable within the achievable number
        of full deployment cycles (cycle + buffer) inside the project
        timeline, given the device count.
      - replication: every EMU needs at least `emu_min_tiles` member tiles
        to be a statistically meaningful unit at all.
    K_min is fixed at 2 (silhouette is undefined for K=1) — no artificial
    floor beyond that; see module docstring on why count is output-driven."""
    cycle_turnover_days = cycle_length_days + logistics_buffer_days
    achievable_cycles = max(1, int((project_duration_weeks * 7) // cycle_turnover_days))
    k_max_logistics = n_devices * achievable_cycles
    k_max_replication = max(1, n_candidates // max(1, emu_min_tiles))
    k_max = max(1, min(k_max_logistics, k_max_replication))
    return {
        "k_min": 2 if k_max >= 2 else 1,
        "k_max": k_max,
        "achievable_cycles": achievable_cycles,
        "k_max_logistics": k_max_logistics,
        "k_max_replication": k_max_replication,
    }


def spatial_connectivity(coords_xy: np.ndarray, n_neighbors: int = 6):
    """Builds a k-nearest-neighbours connectivity graph on projected (x, y)
    coordinates for use as AgglomerativeClustering's `connectivity`
    constraint. Without this, Gower-distance clustering has no spatial
    constraint at all and can group ecologically-similar farms scattered
    across an entire district into one "EMU" purely on covariate
    similarity, with geography only entering later, in the logistics
    panel-building step.

    This constrains agglomerative merging so two candidates can only end
    up in the same cluster if they're connected through a chain of
    genuinely NEARBY candidates (k-NN graph) — geography now participates
    in EMU formation itself, not just in scheduling afterward. n_neighbors
    is deliberately not 1 (a pure minimum-spanning-tree constraint would be
    too rigid and produce oddly elongated, single-file clusters); 6 gives
    each candidate several real nearby options to connect through while
    still ruling out grouping two farms that are, functionally, nowhere
    near each other."""
    n = coords_xy.shape[0]
    k = min(n_neighbors, n - 1)
    if k < 1:
        return None
    graph = kneighbors_graph(coords_xy, n_neighbors=k, include_self=False)
    return graph.maximum(graph.T)  # symmetrize — kneighbors_graph is directed


def select_k_via_silhouette(
    distance_matrix: np.ndarray, k_min: int, k_max: int, connectivity=None,
) -> Tuple[int, Dict[int, float], np.ndarray]:
    """Tries every K in [k_min, k_max], returns (best_k, {k: silhouette},
    best_labels). Falls back to a single cluster (k=1, no silhouette
    defined) if the candidate pool is too small to support k_min clusters.

    `connectivity`, when given, is a spatial adjacency graph — see
    spatial_connectivity() above — restricting agglomerative merges to
    spatially-connected candidates. sklearn supports `connectivity`
    together with `metric="precomputed"`, which isn't obvious from the
    docs alone."""
    n = distance_matrix.shape[0]
    if n < max(k_min, 2):
        logger.warning("Only %d candidates — too few for silhouette-based "
                        "K selection; using a single EMU.", n)
        return 1, {}, np.zeros(n, dtype=int)

    k_max_feasible = min(k_max, n - 1)
    scores: Dict[int, float] = {}
    best_k, best_score, best_labels = None, -2.0, None

    for k in range(max(2, k_min), k_max_feasible + 1):
        try:
            model = AgglomerativeClustering(
                n_clusters=k, metric="precomputed", linkage="average", connectivity=connectivity)
            labels = model.fit_predict(distance_matrix)
        except ValueError as e:
            # A connectivity graph can leave more connected components than
            # k (e.g. genuinely isolated outlier farms) — sklearn raises
            # rather than silently ignoring this. Skip this k rather than
            # crash the whole search; a different k may resolve cleanly.
            logger.debug("k=%d infeasible under spatial connectivity: %s", k, e)
            continue
        if len(set(labels)) < 2:
            continue
        score = silhouette_score(distance_matrix, labels, metric="precomputed")
        scores[k] = round(float(score), 4)
        if score > best_score:
            best_k, best_score, best_labels = k, score, labels

    if best_k is None:
        logger.warning("No valid K in [%d, %d] produced >=2 real clusters — "
                        "using a single EMU.", k_min, k_max_feasible)
        return 1, scores, np.zeros(n, dtype=int)

    # Silhouette scores often plateau across a wide range of K rather than
    # peaking sharply — picking the literal maximum in a flat plateau can
    # produce an unnecessarily fragmented result with no real statistical
    # justification for the extra splits over a simpler one. Standard
    # practice for this (the "one standard error" rule used for
    # LASSO/ridge model selection) is to prefer the simplest model within
    # a tolerance of the best score, not the literal maximum: the smallest
    # k whose score is within 25% of the real score range (best minus
    # worst) of the single best score, a standard elbow-style tolerance.
    valid_scores = {k: s for k, s in scores.items() if s > -2.0}
    if len(valid_scores) > 1:
        score_range = best_score - min(valid_scores.values())
        tolerance = 0.25 * score_range
        parsimony_k = min(k for k, s in valid_scores.items() if s >= best_score - tolerance)
        if parsimony_k != best_k:
            logger.info("K selection: absolute-best k=%d (score=%.4f) vs parsimony-preferred "
                        "k=%d (score=%.4f, within 25%% of the real score range of best) — "
                        "using the smaller, simpler k.", best_k, best_score,
                        parsimony_k, valid_scores[parsimony_k])
            best_k = parsimony_k
            model = AgglomerativeClustering(
                n_clusters=best_k, metric="precomputed", linkage="average", connectivity=connectivity)
            best_labels = model.fit_predict(distance_matrix)

    return best_k, scores, best_labels


def enforce_spatial_compactness_budget_aware(
    labels: np.ndarray, centroids_xy: np.ndarray, max_diameter_m: float, k_max: int,
) -> np.ndarray:
    """Budget-aware variant of enforce_spatial_compactness() below: that
    function is all-or-nothing — if fully resolving every compactness
    violation needs more clusters than the device budget allows, applying
    none of the available headroom would leave even the worst violations
    (e.g. tiles tens of kilometres from the rest of their EMU) completely
    unaddressed, even with several free EMU slots unused.

    This version spends whatever budget IS available, greedily: repeatedly
    finds the single most-spread-out cluster and splits off its most
    dissimilar half (via 2-means on just that cluster), stopping only when
    either no cluster still violates the diameter limit or the label count
    would exceed k_max. This guarantees the worst violations get resolved
    first even when a full fix isn't affordable, rather than an all-or-
    nothing choice that can leave a 100km outlier fully unaddressed even
    with several free EMU slots sitting unused."""
    label_arr = np.array(labels, dtype=int)
    next_label = int(label_arr.max()) + 1 if len(label_arr) else 0

    def _diameter(idxs):
        if len(idxs) < 2:
            return 0.0
        return pdist(centroids_xy[idxs]).max()

    while len(np.unique(label_arr)) < k_max:
        worst_label, worst_diam, worst_idx = None, max_diameter_m, None
        for lab in np.unique(label_arr):
            idxs = np.where(label_arr == lab)[0]
            d = _diameter(idxs)
            if d > worst_diam:
                worst_diam, worst_label, worst_idx = d, lab, idxs
        if worst_label is None:
            break  # nothing left violates the limit
        km = KMeans(n_clusters=2, n_init=10, random_state=0).fit(centroids_xy[worst_idx])
        # The smaller half becomes the new label — isolates the minority
        # outlier(s) rather than arbitrarily splitting down the middle.
        sizes = np.bincount(km.labels_)
        minority = int(np.argmin(sizes))
        minority_idx = worst_idx[km.labels_ == minority]
        label_arr[minority_idx] = next_label
        next_label += 1

    return label_arr


def enforce_spatial_compactness(
    labels: np.ndarray, centroids_xy: np.ndarray, max_diameter_m: float
) -> np.ndarray:
    """Hard backstop against clustering "chaining" — a connectivity
    constraint only guarantees a path between members, not a short
    overall diameter, and spatial coordinates as just two more Gower
    features among ~15 get diluted by covariate similarity; neither is
    enough on its own to keep a cluster spatially coherent (every
    consecutive pair of members can be close while the overall span is
    still enormous).

    This is the hard backstop: after clustering, check every resulting
    cluster's actual spatial diameter (max pairwise centroid distance). Any
    cluster exceeding max_diameter_m gets split via KMeans on projected
    coordinates alone into enough spatially-compact sub-groups to bring
    every piece under the limit, repeated until nothing exceeds it. This
    runs strictly after the ecological clustering — it never changes which
    candidates are ecologically similar, only whether an ecologically-
    similar-but-geographically-scattered group stays as one EMU or becomes
    several smaller, spatially real ones."""
    label_arr = np.array(labels, dtype=int)
    next_label = int(label_arr.max()) + 1 if len(label_arr) else 0
    changed = True
    while changed:
        changed = False
        for lab in list(np.unique(label_arr)):
            member_idx = np.where(label_arr == lab)[0]
            if len(member_idx) < 2:
                continue
            pts = centroids_xy[member_idx]
            diam = pdist(pts).max() if len(pts) > 1 else 0.0
            if diam <= max_diameter_m:
                continue
            n_sub = max(2, min(len(member_idx), int(np.ceil(diam / max_diameter_m)) + 1))
            km = KMeans(n_clusters=n_sub, n_init=10, random_state=0).fit(pts)
            for si in range(n_sub):
                sub_idx = member_idx[km.labels_ == si]
                if len(sub_idx) == 0:
                    continue
                if si == 0:
                    label_arr[sub_idx] = lab  # first sub-group keeps the original label
                else:
                    label_arr[sub_idx] = next_label
                    next_label += 1
            changed = True
    return label_arr


def merge_orphan_clusters(labels: np.ndarray, centroids_xy: np.ndarray, min_cluster_size: int) -> np.ndarray:
    """Merges a genuinely orphaned, too-small EMU into its nearest real
    neighbour. Agroforestry has no ecological-anchor concept to merge an
    orphan into (unlike the contiguous-archetype equivalent — see
    segmentation_reconciliation.py's orphan-segment-to-anchor merging) —
    but the same principle applies: a 1-2 parcel EMU sitting near other,
    larger EMUs is far more likely a clustering artifact than a genuinely
    distinct stratum. Any cluster below min_cluster_size is folded into
    whichever OTHER cluster's nearest member is geometrically closest —
    real proximity, not requiring literal touching, since farm parcels
    within the same partition are rarely if ever adjacent the way
    tessellated grid cells are."""
    label_arr = np.array(labels, dtype=int)
    changed = True
    while changed:
        changed = False
        sizes = {lab: int((label_arr == lab).sum()) for lab in np.unique(label_arr)}
        if len(sizes) <= 1:
            break
        small = sorted([lab for lab, sz in sizes.items() if sz < min_cluster_size], key=lambda l: sizes[l])
        for target_lab in small:
            if target_lab not in sizes or len(sizes) <= 1:
                continue
            target_idx = np.where(label_arr == target_lab)[0]
            other_labs = [lab for lab in sizes if lab != target_lab]
            best_lab, best_dist = None, float("inf")
            for lab in other_labs:
                other_idx = np.where(label_arr == lab)[0]
                d = cdist(centroids_xy[target_idx], centroids_xy[other_idx]).min()
                if d < best_dist:
                    best_dist, best_lab = d, lab
            if best_lab is not None:
                label_arr[target_idx] = best_lab
                sizes = {lab: int((label_arr == lab).sum()) for lab in np.unique(label_arr)}
                changed = True
    return label_arr
