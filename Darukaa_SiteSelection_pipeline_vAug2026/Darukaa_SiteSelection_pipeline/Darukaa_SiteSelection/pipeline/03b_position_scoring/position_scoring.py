"""
03b_position_scoring / position_scoring.py
=============================================

Ranks every candidate tile WITHIN each EMU by an objective, auditable
"typicality" score, and builds a spatially-spread position pool from that
ranking. A reference field map for this kind of deliverable doesn't just
color
candidates by segment, it shows a rich popup per candidate ("Ecological
stratum: SEG06", "MCDA score: 100th percentile typicality", "stratum
medoid — most representative position" / "maximum-minimum distance —
extends spatial coverage of the stratum"), and a separate "pool positions
never used" layer. None of that existed before; the pipeline only had raw
candidate dots or, before that, nothing between EMU polygon and manual
point-picking.

METHOD — CRITIC weighting (Diakoulaki, Mavrotas & Papayannakis 1995),
matching the Pimpri methodology's own documented method exactly (§4.4):
  1. Normalize every covariate to [0,1] across ALL surviving candidates
     project-wide (min-max, direction-corrected via rollup.py's
     DIRECTIONALITY so "lower is better" covariates don't get inverted
     rankings).
  2. Weight = std-dev of that covariate (more spread = more discriminating)
     x sum(1 - correlation with every other covariate) (less redundant
     with other covariates = more independent information). This is the
     whole point of CRITIC over just "pick weights that feel right" — the
     weights are a direct, recomputable function of the actual data, not a
     judgment call, and change automatically if the underlying data does.
  3. Within EACH EMU, typicality(candidate) = 1 - (weighted distance from
     that candidate to its OWN EMU's mean, normalized to [0,1] within the
     EMU) — so 100th percentile means "most representative of what this
     EMU actually looks like", not "best score on some absolute scale".
  4. Position pool = the medoid (highest typicality) plus, on top of it,
     a farthest-point (max-min distance) walk in real geographic space —
     each subsequent pool member is whichever remaining candidate is
     farthest from every already-picked pool member. This is what actually
     produces spatial spread across the EMU rather than a cluster of
     similar-looking points bunched in one corner.

TWO FEATURE TIERS, same honesty pattern as 02/03/05: if satellite
covariates exist (GEE has run), score on the full ~15-covariate profile.
If not, fall back to whatever numeric attributes 01_ingestion actually
found (plantation_year, area, etc.) and stamp the output
feature_tier="attribute_only" so nobody mistakes a provisional ranking for
the final one. Categorical attributes (admin_block) are not used here —
CRITIC is a continuous-variable method; a categorical feature would need a
different (dummy-coded) treatment this module doesn't attempt yet.

SAME CODE PATH FOR BOTH ARCHETYPES — reads candidates_with_emu.geojson,
which is now uniformly produced by BOTH ecological_clustering.py and
segmentation_reconciliation.py (the latter fixed for this exact reason
last round). No archetype branching needed here at all.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
from shapely.geometry import shape
from shapely.ops import unary_union
from sklearn.cluster import KMeans

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "05_metrics_rollup"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "03_emu_delineation"))
import config_schema  # noqa: E402
import crs              # noqa: E402
import rollup as rollup_module  # noqa: E402 — reuse the authoritative covariate/directionality lists, not a second copy
from ecological_clustering import ATTRIBUTE_NUMERIC_COLS  # noqa: E402 — reuse Tier-1 fallback list, not a second copy

logger = logging.getLogger(__name__)


def critic_weights(
    X: np.ndarray, feature_names: List[str], directionality: Dict[str, str]
) -> Tuple[np.ndarray, np.ndarray]:
    """X: (n_candidates, n_features) raw values, NaN for missing. Returns
    (weights, normalized_matrix). Columns that are entirely NaN or constant
    get zero weight rather than dividing by zero or NaN-poisoning every
    other weight via the correlation matrix."""
    n, m = X.shape
    norm = np.zeros((n, m))
    valid_cols = []
    for j, name in enumerate(feature_names):
        col = X[:, j]
        finite = col[~np.isnan(col)]
        if len(finite) < 2 or np.nanmax(finite) == np.nanmin(finite):
            continue  # no discriminating information in this column at all
        lo, hi = np.nanmin(col), np.nanmax(col)
        rng = hi - lo
        col_norm = (col - lo) / rng
        if directionality.get(name) == "lower_better":
            col_norm = 1.0 - col_norm
        norm[:, j] = np.nan_to_num(col_norm, nan=0.5)  # missing -> neutral midpoint
        valid_cols.append(j)

    weights = np.zeros(m)
    if not valid_cols:
        return weights, norm

    sub = norm[:, valid_cols]
    std = np.std(sub, axis=0)
    corr = np.corrcoef(sub, rowvar=False)
    corr = np.nan_to_num(corr, nan=0.0)
    if corr.ndim == 0:  # single valid column
        corr = np.array([[1.0]])
    info = std * np.sum(1 - corr, axis=1)
    total = info.sum()
    sub_weights = (info / total) if total > 0 else np.ones(len(valid_cols)) / len(valid_cols)
    for k, j in enumerate(valid_cols):
        weights[j] = sub_weights[k]
    return weights, norm


def typicality_within_emu(norm_emu: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """1.0 = most representative of this EMU's own mean covariate profile,
    0.0 = most atypical member. Computed relative to the EMU's OWN mean,
    not a project-wide reference — matches the Pimpri doc's framing
    exactly ("most representative position" WITHIN a stratum, not overall)."""
    if norm_emu.shape[0] == 1:
        return np.array([1.0])
    mean_vec = norm_emu.mean(axis=0)
    diffs = (norm_emu - mean_vec) * weights
    dist = np.sqrt((diffs ** 2).sum(axis=1))
    max_dist = dist.max()
    return 1.0 - (dist / max_dist) if max_dist > 0 else np.ones(len(dist))


def farthest_point_pool(points_xy: List[Tuple[float, float]], seed_idx: int, pool_size: int) -> List[int]:
    """SUPERSEDED — pure farthest-point sampling is mathematically biased
    toward the convex hull of the candidate set: maximizing minimum
    pairwise distance systematically pushes picks toward extremes/corners,
    since a point near the middle can never be "farthest" from everything
    else the way an edge point can. A real, known property of this
    algorithm, not a tuning issue. Kept here only for reference; see
    spatial_bin_pool() below for the replacement actually used."""
    n = len(points_xy)
    pool_size = min(pool_size, n)
    picked = [seed_idx]
    if pool_size == 1:
        return picked
    remaining = set(range(n)) - {seed_idx}
    pts = np.array(points_xy)
    while len(picked) < pool_size and remaining:
        picked_pts = pts[picked]
        best_idx, best_min_dist = None, -1.0
        for idx in remaining:
            d = np.sqrt(((picked_pts - pts[idx]) ** 2).sum(axis=1)).min()
            if d > best_min_dist:
                best_min_dist, best_idx = d, idx
        picked.append(best_idx)
        remaining.discard(best_idx)
    return picked


def select_spacing_compliant_positions(
    points_xy: List[Tuple[float, float]], typicality: np.ndarray, seed_idx: int,
    min_spacing_m: float, max_positions: int | None = None,
    boundary_dist: np.ndarray | None = None, interior_bonus_weight: float = 0.5,
) -> List[int]:
    """REPLACES spatial_bin_pool: position selection needs to be a genuine
    minimum-distance CONSTRAINT SATISFACTION check against real candidate
    coordinates, not a KMeans spatial partition, which spreads picks
    across regions but never verifies any actual pairwise distance and can
    place two selected points in the same EMU directly next to each other.

    True Euclidean pairwise distance, used here throughout, is also
    direction-agnostic by construction — it needs no lattice correction
    for diagonal neighbours the way a naive square-grid spacing check
    would (a diagonal sits at 1.41x the orthogonal pitch).

    Pure greedy max-min-distance selection has a real, confirmed
    mathematical tendency to push points toward the boundary of a bounded
    region — there's structurally more "room" to be far from already-picked
    points near an edge than deep in the interior. `boundary_dist`, when
    given,
    blends each candidate's real distance to the EMU's own dissolved
    boundary into the SELECTION ORDER (not the spacing constraint itself,
    which stays purely geometric) — candidates are ranked by a weighted
    combination of typicality percentile and interior-ness percentile
    within the eligible set, so the greedy search actively prefers a
    reasonably interior point over a marginally-more-typical edge one,
    rather than chasing pure typicality until spacing forces an edge
    choice. The medoid itself (seed_idx) is exempt — it's specifically
    meant to be the single most representative point by typicality alone,
    not interior-biased.

    Greedy: start from the medoid (seed_idx, guaranteed feasible alone),
    then repeatedly add the highest-remaining-ranked candidate that is
    >= min_spacing_m from EVERY already-selected point, until no more
    candidates qualify or max_positions is reached. The number of
    positions this returns IS the EMU's real, verified device capacity —
    not a separate area-based estimate that can disagree with what the
    actual candidate geometry supports."""
    n = len(points_xy)
    if n == 0:
        return []
    pts = np.array(points_xy)

    if boundary_dist is not None and n > 1:
        # Percentile-rank both signals within this EMU's own eligible set
        # so they're on a comparable 0-1 scale regardless of each one's
        # raw units/range, then blend for ordering only.
        typ_rank = np.argsort(np.argsort(typicality)) / max(1, n - 1)
        interior_rank = np.argsort(np.argsort(boundary_dist)) / max(1, n - 1)
        combined = (1 - interior_bonus_weight) * typ_rank + interior_bonus_weight * interior_rank
    else:
        combined = typicality

    order = list(np.argsort(-combined))
    order.remove(seed_idx)
    order.insert(0, seed_idx)  # medoid always tried first, on pure typicality, guaranteed feasible alone

    selected: List[int] = []
    for idx in order:
        if max_positions is not None and len(selected) >= max_positions:
            break
        pt = pts[idx]
        if not selected:
            selected.append(int(idx))
            continue
        dists = np.sqrt(((pts[selected] - pt) ** 2).sum(axis=1))
        if dists.min() >= min_spacing_m:
            selected.append(int(idx))
    return selected


def spatial_bin_pool(
    points_xy: List[Tuple[float, float]], typicality: np.ndarray, seed_idx: int, pool_size: int,
) -> List[int]:
    """SUPERSEDED — see select_spacing_compliant_positions above for the
    replacement and the real reasoning. Kept only for reference: never
    verified actual pairwise distance between selections, only spread
    them across KMeans regions, which could still place two picks close
    together near a shared region boundary."""
    n = len(points_xy)
    pool_size = min(pool_size, n)
    if pool_size <= 1 or n <= 1:
        return [seed_idx]

    pts = np.array(points_xy)
    km = KMeans(n_clusters=pool_size, n_init=10, random_state=0).fit(pts)
    region_labels = km.labels_

    seed_region = region_labels[seed_idx]
    picked = []
    for region in range(pool_size):
        region_idx = np.where(region_labels == region)[0]
        if len(region_idx) == 0:
            continue
        if region == seed_region and seed_idx in region_idx:
            picked.append(int(seed_idx))
            continue
        best_in_region = region_idx[np.argmax(typicality[region_idx])]
        picked.append(int(best_in_region))
    if seed_idx not in picked:
        picked.insert(0, int(seed_idx))
    return picked


def find_deployment_outliers(points_xy: List[Tuple[float, float]], mad_threshold: float = 3.5) -> np.ndarray:
    """A severe spatial outlier within an EMU doesn't need its own EMU at
    all — ecological membership stays real and intact for metrics
    purposes — it just should never be picked as a device position, since
    no field team is making a separate trip for 1-2 parcels regardless of
    which EMU they're nominally grouped into (see ecological_clustering.py's
    docstring for why this is simpler and more correct than splitting the
    EMU itself).

    A simple median + MAD distance-to-centre approach assumes a single
    dominant cluster with a small minority of true stragglers — this
    breaks badly for a genuinely BIMODAL EMU (two large, real,
    roughly-equal sub-populations), flagging a large, legitimate portion
    of the EMU as "outliers" simply because the site-wide median sits in
    the other half, with no regard for whether the "far" points are
    themselves a real, substantial, coherent group.

    DBSCAN finds real spatial sub-clusters first, and only
    flags a candidate as a genuine deployment outlier if it belongs to a
    TINY cluster (below a small absolute size floor, not a fraction of the EMU's total
    membership) that's genuinely isolated — never a large, coherent
    sub-population, however far it sits from another part of the same
    EMU. `eps` is set relative to the EMU's own typical nearest-neighbour
    spacing (not a fixed absolute distance), so this works correctly at
    both Soulforest's ~100m scale and GV's ~100km scale without separate
    tuning. Returns a boolean array, True = flagged as a deployment
    outlier (excluded from medoid/pool eligibility, NOT from EMU
    membership)."""
    pts = np.array(points_xy)
    n = len(pts)
    if n < 4:
        return np.zeros(n, dtype=bool)  # too few points for a meaningful check

    # Real, data-driven eps: the median nearest-neighbour distance across
    # the EMU's own candidates, scaled up — captures "how close together
    # are points that are actually part of the same real cluster HERE",
    # rather than assuming one fixed distance works at every EMU's scale.
    from scipy.spatial.distance import cdist
    dmat = cdist(pts, pts)
    np.fill_diagonal(dmat, np.inf)
    nearest = dmat.min(axis=1)
    typical_spacing = np.median(nearest)
    eps = max(typical_spacing * 5, 1.0)  # 1.0m floor avoids a zero-eps
    # degenerate case if many points are literally coincident

    from sklearn.cluster import DBSCAN
    # A real cluster needs at least a small, ABSOLUTE minimum number of
    # members, not a PERCENTAGE of the EMU's total size — an EMU made of
    # many real small village-level communities would otherwise have every
    # genuine community below that percentage wrongly flagged as
    # "outliers", when only a genuine 1-2 point isolated straggler should
    # be excluded.
    min_real_cluster_size = 3
    min_samples = 3
    labels = DBSCAN(eps=eps, min_samples=min_samples).fit_predict(pts)

    # DBSCAN's own -1 (noise) label already means "not part of any real
    # cluster at this density" — those points are the true outliers.
    # Additionally, even a DBSCAN-found cluster below the fraction
    # threshold (possible with the eps/min_samples interaction) is still
    # treated as outlier-flagged, for the same reason.
    is_outlier = labels == -1
    for lab in set(labels):
        if lab == -1:
            continue
        cluster_size = (labels == lab).sum()
        if cluster_size < min_real_cluster_size:
            is_outlier |= (labels == lab)
    return is_outlier


def run_position_scoring(project_dir: str | Path) -> Dict[str, Any]:
    project_dir = Path(project_dir)
    cfg = config_schema.load_config(project_dir / "config.yaml")
    emu_path = project_dir / "outputs" / "03_emu_delineation" / "candidates_with_emu.geojson"
    if not emu_path.exists():
        raise FileNotFoundError(f"{emu_path} not found — run 03_emu_delineation first.")
    with open(emu_path) as f:
        fc = json.load(f)
    features = [f for f in fc["features"] if f["properties"].get("emu_id") is not None]

    has_satellite = any(
        any(isinstance(f["properties"].get(c), (int, float)) for c in rollup_module.ALL_CONDITION_COVARIATES)
        for f in features
    )
    if has_satellite:
        feature_cols = rollup_module.ALL_CONDITION_COVARIATES
        directionality = rollup_module.DIRECTIONALITY
        feature_tier = "full_with_satellite_covariates"

        def get_val(props, col):
            return props.get(col)
    else:
        feature_cols = ATTRIBUTE_NUMERIC_COLS
        directionality = {}
        feature_tier = "attribute_only"

        def get_val(props, col):
            v = props.get(col)
            return v if isinstance(v, (int, float)) else None

        logger.warning(
            "No satellite covariates found — scoring on %s only (attribute_only tier). "
            "Re-run once GEE covariates land for a real typicality ranking.", feature_cols)

    X = np.full((len(features), len(feature_cols)), np.nan)
    for i, f in enumerate(features):
        for j, col in enumerate(feature_cols):
            v = get_val(f["properties"], col)
            if v is not None:
                X[i, j] = v

    weights, norm = critic_weights(X, feature_cols, directionality)
    weights_report = {col: round(float(w), 4) for col, w in zip(feature_cols, weights)}

    first_geom = shape(features[0]["geometry"])
    projected_crs = crs.resolve(first_geom)

    by_emu: Dict[str, List[int]] = {}
    for i, f in enumerate(features):
        by_emu.setdefault(f["properties"]["emu_id"], []).append(i)

    cycle_turnover_days = cfg["cycle_length_days"] + cfg["logistics_buffer_days"]
    # Pool target size depends on the sampling design (see
    # config_schema.py's sampling_design note for the full reasoning):
    # continuous_multi_week rotates ONE device through the pool
    # across many weeks, so achievable_cycles is the right size. But
    # stratified_single_pass can assign MANY devices to one EMU
    # SIMULTANEOUSLY in its single assigned week — the pool needs to be
    # sized for that, not for a weekly rotation that isn't happening. Using
    # n_devices as the ceiling (an EMU can never need more than the
    # project's total device count at once) rather than achievable_cycles.
    if cfg.get("sampling_design") == "stratified_single_pass":
        pool_target = cfg["n_devices"]
    else:
        pool_target = max(1, int((cfg["project_duration_weeks"] * 7) // cycle_turnover_days))
    achievable_cycles = pool_target  # kept as the existing variable name below

    pool_features = []
    emu_reports = {}
    for emu_id, idxs in by_emu.items():
        emu_norm = norm[idxs]
        typicality = typicality_within_emu(emu_norm, weights)

        points_xy = []
        for i in idxs:
            g_m = crs.to_m(shape(features[i]["geometry"]), projected_crs)
            c = g_m.centroid
            points_xy.append((c.x, c.y))

        # Greedy selection that maximises minimum pairwise distance in a
        # bounded region structurally tends toward the boundary (there's
        # more "room" to be far from already-picked points near an edge
        # than deep in the interior) — the same property pure
        # farthest-point sampling has, reintroduced here by a different,
        # otherwise-necessary algorithm (real spacing verification).
        # Computing each candidate's real distance
        # to the EMU's own dissolved boundary and blending it with
        # typicality for the SELECTION ORDER only — the medoid itself
        # stays picked on pure typicality (it's specifically meant to be
        # the single most representative point, not an interior-biased
        # one), but the additional spatial-coverage picks now also weigh
        # "is this reasonably interior" against "is this a good spot",
        # instead of chasing pure typicality until spacing forces an edge.
        emu_boundary = unary_union([crs.to_m(shape(features[i]["geometry"]), projected_crs)
                                    for i in idxs]).boundary
        boundary_dist = np.array([crs.to_m(shape(features[i]["geometry"]), projected_crs)
                                  .centroid.distance(emu_boundary) for i in idxs])

        # Deployment-eligibility outlier exclusion — see
        # find_deployment_outliers()'s docstring for the real history this
        # replaces. Excluded points are NEVER the medoid and NEVER enter
        # the position pool, but stay full EMU members everywhere else
        # (metrics rollup, EMU geometry, candidate counts).
        is_outlier = find_deployment_outliers(points_xy)
        # Manual deployment exclusion — same treatment as a geometric
        # outlier (real EMU member, never a device position), but driven
        # by an explicit per-candidate flag (e.g. client-reported access
        # constraint) rather than distance-based detection. Generic to any
        # project; not Soova-specific.
        is_manual_excluded = np.array([
            bool(features[i]["properties"].get("manual_deployment_exclude")) for i in idxs
        ])
        is_outlier = is_outlier | is_manual_excluded
        eligible_local = [i for i in range(len(idxs)) if not is_outlier[i]]
        n_outliers = int(is_outlier.sum())

        order = np.argsort(-typicality)  # descending: highest typicality first
        ranks = np.empty_like(order)
        ranks[order] = np.arange(len(order))
        percentiles = 100 * (1 - ranks / max(1, len(order) - 1)) if len(order) > 1 else np.array([100.0])

        # Medoid must come from the eligible (non-outlier) set — falls back
        # to the full set only if every single member was somehow flagged
        # (shouldn't happen given find_deployment_outliers' own minority-
        # only design, but never silently produces no medoid at all).
        candidate_pool_for_medoid = eligible_local if eligible_local else list(range(len(idxs)))
        medoid_local_idx = max(candidate_pool_for_medoid, key=lambda i: typicality[i])

        eligible_points_xy = [points_xy[i] for i in eligible_local] if eligible_local else points_xy
        eligible_typicality = typicality[eligible_local] if eligible_local else typicality
        eligible_boundary_dist = boundary_dist[eligible_local] if eligible_local else boundary_dist
        medoid_pos_in_eligible = eligible_local.index(medoid_local_idx) if eligible_local else medoid_local_idx

        # A named sub-area bias (e.g. Soulforest's Wetland/Island: one of
        # two audiomoth devices should be on the more accessible island)
        # can conflict with the medoid — the true medoid can sit as little
        # as 25m from the
        # best real island candidate — well under the 100m spacing
        # guarantee — meaning no amount of picking a DIFFERENT second
        # position can ever include the island alongside a fixed medoid;
        # they're just too close together geometrically. Rather than
        # silently drop the client's request (the medoid always wins) or
        # silently relax the spacing guarantee (never done elsewhere in
        # this pipeline), the greedy selection's own seed is swapped to
        # the best real in-subarea candidate for this EMU specifically —
        # the true medoid is still correctly reported as the medoid
        # wherever it's used (is_medoid is computed by direct comparison,
        # not by seed position), it just may not end up in the final pool
        # if it's geometrically incompatible with the client's explicit
        # requirement.
        greedy_seed_pos = medoid_pos_in_eligible

        # An agroforestry EMU can span tens to over a hundred kilometres,
        # at which scale min_device_spacing_m (100m, derived from acoustic
        # detection radius — correct for a compact conservation site) is
        # meaningless — any real candidate placement trivially satisfies
        # 100m spacing without needing to spread across more than a tiny
        # fraction of the EMU's real extent. The EFFECTIVE spacing
        # requirement scales with the EMU's own
        # bounding-box diagonal and target pool size — enough to force
        # genuine geographic spread across a vast, scattered EMU — while
        # never going BELOW the real acoustic floor, so a compact EMU
        # (e.g. Soulforest's ~100-300m diagonals) is completely unaffected
        # and still gets exactly the acoustic-derived spacing it needs.
        if len(eligible_points_xy) > 1:
            xy_arr = np.array(eligible_points_xy)
            bbox_diag_m = float(np.hypot(xy_arr[:, 0].max() - xy_arr[:, 0].min(),
                                         xy_arr[:, 1].max() - xy_arr[:, 1].min()))
        else:
            bbox_diag_m = 0.0
        extent_based_spacing = bbox_diag_m / (2 * max(1, pool_target) ** 0.5)
        # The uncapped formula scales with the EMU's FULL bounding-box
        # diagonal, which a genuinely vast, non-uniformly-distributed EMU
        # can push to an extreme even though the real candidate
        # distribution isn't uniform — a rich, real local cluster of
        # candidates can sit well within the uncapped requirement's
        # exclusion radius, excluding it entirely from ever contributing
        # another position. Capped at MAX_EXTENT_SPACING_M — a reasonable
        # ceiling for what "a genuinely different region" means at
        # landscape-monitoring scale, past which forcing MORE separation
        # excludes legitimate additional coverage rather than adding real
        # spread. Every EMU already under this ceiling is unaffected.
        MAX_EXTENT_SPACING_M = 25_000.0
        extent_based_spacing = min(extent_based_spacing, MAX_EXTENT_SPACING_M)
        effective_min_spacing_m = max(cfg.get("min_device_spacing_m", 100.0), extent_based_spacing)

        subarea_cfg_for_seed = (cfg.get("position_pool_named_subarea_bias") or {}).get(emu_id)
        if subarea_cfg_for_seed and eligible_local is not None:
            subarea_name = subarea_cfg_for_seed["subarea_placemark_name"]
            in_subarea_eligible = [
                i for i in range(len(eligible_points_xy))
                if features[idxs[eligible_local[i]] if eligible_local else idxs[i]]
                ["properties"].get("named_subarea") == subarea_name]
            if in_subarea_eligible:
                best_subarea_i = max(in_subarea_eligible, key=lambda i: eligible_typicality[i])
                medoid_pt = np.array(eligible_points_xy[medoid_pos_in_eligible])
                subarea_pt = np.array(eligible_points_xy[best_subarea_i])
                if np.linalg.norm(medoid_pt - subarea_pt) < effective_min_spacing_m:
                    greedy_seed_pos = best_subarea_i

        # pool_target (n_devices) is a CEILING, not a target to
        # force-fill via spatial partitioning — the real
        # number of usable positions is whatever the min-spacing
        # constraint actually allows for this EMU's real candidate
        # geometry, which is the pipeline's genuine, verified device
        # capacity for it (see select_spacing_compliant_positions).
        pool_local_order_eligible = select_spacing_compliant_positions(
            eligible_points_xy, eligible_typicality, greedy_seed_pos,
            min_spacing_m=effective_min_spacing_m, max_positions=pool_target,
            boundary_dist=eligible_boundary_dist)

        # A small EMU at the standard 100m spacing can be reduced to just
        # 1-2 real positions, forcing the same exact spot every week;
        # halving the floor for that EMU specifically can meaningfully
        # increase real capacity. This is a genuine trade-off, not a free
        # improvement — 100m derives from
        # the acoustic detection radius specifically to avoid overlapping
        # detection zones between devices; 50m carries real risk of some
        # acoustic overlap. Applied ONLY when an EMU's true capacity at
        # the full 100m floor is below min_positions_before_relaxation
        # (an EMU with real room for a full season's rotation never needs
        # this), and
        # always reported explicitly in the EMU's own report — never a
        # silent substitution of a weaker guarantee for a stronger one.
        relaxed_spacing_used = None
        # The real, meaningful target for triggering relaxation is
        # season_length_weeks itself, not an arbitrary small number — a
        # low fixed threshold can miss an EMU whose capacity is enough to
        # clear it but still means every position gets revisited multiple
        # times within one season. An EMU whose 100m capacity already
        # reaches that many positions needs no relaxation at all (full
        # season coverage with zero repeats); one that falls short is
        # exactly the case this trade-off is for.
        MIN_POSITIONS_BEFORE_RELAXATION = cfg.get("season_length_weeks") or 3
        RELAXED_SPACING_FLOOR_M = 50.0
        if (len(pool_local_order_eligible) < MIN_POSITIONS_BEFORE_RELAXATION
                and effective_min_spacing_m > RELAXED_SPACING_FLOOR_M
                and cfg.get("allow_small_emu_spacing_relaxation", False)):
            relaxed_min_spacing = max(RELAXED_SPACING_FLOOR_M,
                                      extent_based_spacing if len(eligible_points_xy) > 1 else RELAXED_SPACING_FLOOR_M)
            relaxed_pool = select_spacing_compliant_positions(
                eligible_points_xy, eligible_typicality, greedy_seed_pos,
                min_spacing_m=relaxed_min_spacing, max_positions=pool_target,
                boundary_dist=eligible_boundary_dist)
            if len(relaxed_pool) > len(pool_local_order_eligible):
                pool_local_order_eligible = relaxed_pool
                relaxed_spacing_used = relaxed_min_spacing

        # Map back from eligible-subset indices to the EMU's full local indices
        pool_local_order = ([eligible_local[i] for i in pool_local_order_eligible]
                            if eligible_local else pool_local_order_eligible)
        pool_set = set(pool_local_order)

        for local_i, global_i in enumerate(idxs):
            feat = features[global_i]
            in_pool = local_i in pool_set
            if is_manual_excluded[local_i]:
                reason = feat["properties"].get("manual_deployment_exclude_reason")
                rationale = ("excluded from device positions — " +
                            (reason if reason else "flagged inaccessible") +
                            "; a real EMU member for metrics purposes")
            elif is_outlier[local_i]:
                rationale = ("spatial outlier — excluded from device positions (too far from "
                            "the rest of this EMU for a field visit to be practical), but a "
                            "real EMU member for metrics purposes")
            elif local_i == medoid_local_idx:
                rationale = "stratum medoid — most representative position within this EMU"
            elif in_pool:
                rationale = "best-scoring position in its spatial region — extends coverage of the EMU"
            else:
                rationale = "pool position never used this baseline"
            pool_features.append({
                "type": "Feature", "geometry": feat["geometry"],
                "properties": {
                    "name": feat["properties"].get("display_name") or feat["properties"].get("name"),
                    "emu_id": emu_id,
                    "typicality_percentile": round(float(percentiles[local_i]), 1),
                    "is_medoid": local_i == medoid_local_idx,
                    "in_position_pool": in_pool,
                    "pool_rank": pool_local_order.index(local_i) + 1 if in_pool else None,
                    "selection_rationale": rationale,
                },
            })

        emu_reports[emu_id] = {
            "n_candidates": len(idxs),
            "pool_size": len(pool_local_order),
            "medoid_name": (features[idxs[medoid_local_idx]]["properties"].get("display_name")
                           or features[idxs[medoid_local_idx]]["properties"].get("name")),
            "n_deployment_outliers_excluded": n_outliers,
            "relaxed_spacing_used_m": relaxed_spacing_used,
        }

    report = {
        "project_name": cfg["project_name"],
        "feature_tier": feature_tier,
        "feature_cols_used": feature_cols,
        "critic_weights": weights_report,
        "achievable_cycles_used_as_pool_target": achievable_cycles,
        "n_emus": len(by_emu),
        "emu_reports": emu_reports,
        "warnings": [] if feature_tier == "full_with_satellite_covariates" else [
            f"PROVISIONAL: scored on {feature_cols} only (no satellite covariates yet). "
            "Re-run once GEE covariates are ingested for a real ranking."
        ],
    }

    total_outliers = sum(r["n_deployment_outliers_excluded"] for r in emu_reports.values())
    if total_outliers > 0:
        outlier_detail = {eid: r["n_deployment_outliers_excluded"] for eid, r in emu_reports.items()
                          if r["n_deployment_outliers_excluded"] > 0}
        report["warnings"].append(
            f"{total_outliers} candidate(s) across {len(outlier_detail)} EMU(s) are real "
            f"members (kept for metrics) but excluded from device-position eligibility — "
            f"either as spatial outliers (too far from the rest of their EMU for a field "
            f"visit to be practical) or via an explicit manual_deployment_exclude flag "
            f"(e.g. a reported access constraint): {outlier_detail}. This is a deliberate "
            "design choice: neither case needs its own EMU, it just shouldn't be a device "
            "candidate.")

    relaxed_emus = {eid: r["relaxed_spacing_used_m"] for eid, r in emu_reports.items()
                    if r.get("relaxed_spacing_used_m")}
    if relaxed_emus:
        report["warnings"].append(
            f"{len(relaxed_emus)} EMU(s) had real capacity below what a full season's rotation "
            f"needs at the standard {cfg.get('min_device_spacing_m', 100.0):.0f}m spacing floor "
            "(fewer real positions than season_length_weeks, meaning some positions would repeat "
            f"within a single season) — relaxed for these EMUs specifically: {relaxed_emus}. Real "
            "trade-off (some acoustic overlap risk between devices) accepted in exchange for "
            "genuine spatial/temporal variety instead of an unnecessarily repeated spot. Not "
            "applied to any other EMU in this project.")

    camera_trap_features = []
    if "camera_trap" in cfg.get("streams_active", []):
        # Camera trap gets its own project-wide pool, not
        # per-EMU (a camera trap doesn't need one per stratum the way an
        # acoustic sensor does) — spatially binned across the WHOLE site
        # by typicality percentile (already computed above, per-EMU but on
        # a comparable 0-100 scale), so the pool_size points spread across
        # real distinct areas rather than clustering in one high-scoring EMU.
        pool_size = cfg.get("camera_trap_pool_size", 4)
        all_percentiles = np.array([f["properties"]["typicality_percentile"] for f in pool_features])
        all_xy = []
        for f in pool_features:
            g_m = crs.to_m(shape(f["geometry"]), projected_crs)
            all_xy.append((g_m.centroid.x, g_m.centroid.y))
        seed_idx = int(np.argmax(all_percentiles))
        cam_pool_idx = spatial_bin_pool(all_xy, all_percentiles, seed_idx, pool_size)
        for rank, idx in enumerate(cam_pool_idx, start=1):
            f = pool_features[idx]
            camera_trap_features.append({
                "type": "Feature", "geometry": f["geometry"],
                "properties": {
                    "name": f["properties"]["name"], "emu_id": f["properties"]["emu_id"],
                    "typicality_percentile": f["properties"]["typicality_percentile"],
                    "pool_rank": rank,
                    "selection_rationale": (
                        "highest-scoring position in its site region — camera trap pool "
                        f"({rank} of {len(cam_pool_idx)})"),
                },
            })
        report["camera_trap_pool_size"] = len(camera_trap_features)
        report["camera_trap_n_devices"] = cfg.get("camera_trap_n_devices", 2)

    out_dir = project_dir / "outputs" / "03b_position_scoring"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "position_pool.geojson", "w") as f:
        json.dump({"type": "FeatureCollection", "features": pool_features}, f)
    if camera_trap_features:
        with open(out_dir / "camera_trap_pool.geojson", "w") as f:
            json.dump({"type": "FeatureCollection", "features": camera_trap_features}, f)
    with open(out_dir / "position_scoring_report.json", "w") as f:
        json.dump(report, f, indent=2)

    logger.info("Position scoring complete [%s]: %d EMUs, top weights=%s",
                feature_tier, len(by_emu),
                dict(sorted(weights_report.items(), key=lambda kv: -kv[1])[:3]))
    return report


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    args = parser.parse_args()
    run_position_scoring(args.project_dir)
