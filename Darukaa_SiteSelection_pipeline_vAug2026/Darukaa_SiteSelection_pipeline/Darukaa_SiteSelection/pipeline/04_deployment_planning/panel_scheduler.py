"""
04_deployment_planning / panel_scheduler.py
==============================================

Turns an EMU set (03's output) into an actual deployment calendar: which
EMUs get a device in which cycle, grouped into geographic PANELS purely for
field logistics. EMU is ecological and dashboard-facing; panel is
logistics-only and never shown as an ecological unit.

WHEN PANELS ARE NEEDED AT ALL: only if n_EMUs > n_devices. If every EMU can
get a device simultaneously (true for all three real projects on file today
— Soova 3 EMUs/4 devices, Soulforest 2 EMUs/7 devices), there's exactly one
deployment cycle and no panel-building logic runs at all. GV (11 EMUs/4
devices) is the real test case for the panel logic below.

PANEL FORMATION — greedy nearest-neighbour bin-packing on EMU centroids,
capped at n_devices per panel, NOT a full VRP/TSP solve. Documented
approximation, not claimed as optimal: build one panel at a time by
starting from the unassigned EMU farthest from all already-panelled EMUs
(so panels don't cannibalize each other's obvious geographic groups),
greedily adding its nearest unassigned neighbours until the panel reaches
n_devices, then starting the next panel the same way. This is a reasonable,
inspectable heuristic — exact optimality would need real road-network
routing (isochrones), which isn't available in this environment; the
travel-time figure attached to each panel uses straight-line distance /
an assumed average rural travel speed (config `avg_travel_speed_kmh`) as an
explicit, declared approximation, the same way `hard_barrier_attribute`
was declared an approximation in 03.

CALENDAR — cycle N starts at day `N * (cycle_length_days +
logistics_buffer_days)`, recording runs for `cycle_length_days`, then the
buffer gap before the next cycle. Relative day offsets from an unspecified
project start (config `project_start_date`, optional) rather than
hardcoded absolute dates.

SCOPE NOTE: this module schedules the ROTATIONAL stream (audiomoths, and
camera traps on the same cadence) across EMUs/cycles. One-time composite
sampling events tied to fixed physical features rather than EMU rotation
(soil chemistry, water/soil eDNA, water quality — see Soulforest's brief)
are NOT panel-scheduled here; they get a simple fixed-event list near the
end of the project instead, since forcing them through EMU/cycle logic
they were never described as needing would be over-engineering a problem
that isn't there. If that changes (e.g. a project wants eDNA rotated across
EMUs too), this module would need extending, not reworking.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from shapely.geometry import shape
from shapely.ops import unary_union
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
import config_schema  # noqa: E402
import crs              # noqa: E402

logger = logging.getLogger(__name__)


def _emu_centroids_agroforestry(fc: Dict[str, Any], projected_crs: str) -> Dict[str, Tuple[float, float, float]]:
    """Returns {emu_id: (x_m, y_m, total_area_ha)} from a per-candidate
    feature collection carrying an emu_id property (03's ecological_clustering
    output) — area-weighted centroid of member tiles, computed in the
    projected CRS so distances downstream are in real metres, not degrees."""
    members: Dict[str, List] = {}
    for feat in fc["features"]:
        emu_id = feat["properties"].get("emu_id")
        if emu_id is None:
            continue
        members.setdefault(emu_id, []).append(shape(feat["geometry"]))

    out = {}
    for emu_id, geoms in members.items():
        geoms_m = [crs.to_m(g, projected_crs) for g in geoms]
        union = unary_union(geoms_m)
        total_area_ha = sum(g.area for g in geoms_m) / 10_000.0
        c = union.centroid
        out[emu_id] = (c.x, c.y, total_area_ha)
    return out


def _emu_barrier_groups(fc: Dict[str, Any], barrier_attr: str) -> Dict[str, str]:
    """Returns {emu_id: barrier_group_value} — e.g. {emu_id: "Ganjam"} — so
    panels can be built WITHIN each barrier group separately, matching the
    hard constraint already applied at EMU delineation
    (ecological_clustering.py's hard_barrier_attribute). Without this, two
    EMUs from
    different districts that happen to sit close to each other across a
    district line could end up in the same logistics panel — asking a
    field team to cover two different districts in one cycle, which isn't
    how a multi-district agroforestry project like GV actually works."""
    groups: Dict[str, str] = {}
    for feat in fc["features"]:
        emu_id = feat["properties"].get("emu_id")
        if emu_id is None:
            continue
        if emu_id not in groups:
            groups[emu_id] = feat["properties"].get(barrier_attr) or "unknown"
    return groups


def _emu_centroids_contiguous(fc: Dict[str, Any], projected_crs: str) -> Dict[str, Tuple[float, float, float]]:
    """Returns {emu_id: (x_m, y_m, area_ha)} from 03's segmentation_
    reconciliation output — one feature per EMU already."""
    out = {}
    for feat in fc["features"]:
        emu_id = feat["properties"]["emu_id"]
        geom_m = crs.to_m(shape(feat["geometry"]), projected_crs)
        c = geom_m.centroid
        out[emu_id] = (c.x, c.y, geom_m.area / 10_000.0)
    return out


def _dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _allocate_panels_across_groups(group_sizes: Dict[str, int], total_target: int) -> Dict[str, int]:
    """Proportional allocation of the project's total target panel count
    across barrier groups (districts), by EMU count, every non-empty
    group guaranteed at least 1 — the same pattern already used for
    K_max allocation across partitions in ecological_clustering.py.
    Allocating the full target independently to EACH group (rather than
    proportionally across all of them) would give every small district
    its own uncapped share, producing far more total panels than the
    real target across the whole project."""
    total_n = sum(group_sizes.values())
    if total_n == 0:
        return {}
    raw = {g: max(1, round(total_target * n / total_n)) for g, n in group_sizes.items()}
    while sum(raw.values()) > total_target and any(v > 1 for v in raw.values()):
        biggest = max(raw, key=lambda g: raw[g])
        raw[biggest] -= 1
    return raw


def build_panels(
    centroids: Dict[str, Tuple[float, float, float]], n_devices: int,
    barrier_groups: Dict[str, str] | None = None, panel_cap: int | None = None,
    target_n_panels: int | None = None,
) -> List[List[str]]:
    """Greedy nearest-neighbour bin-packing. Returns a list of panels,
    each a list of emu_ids. See module docstring for why this is a
    declared heuristic, not a VRP solve.

    target_n_panels, when given, builds EXACTLY that many panels IN TOTAL
    across every barrier group combined (allocated proportionally to each
    group's own EMU count via _allocate_panels_across_groups, never
    independently per group — seven EMUs across 4 districts targeting 5
    total panels should not become 7, one per EMU, just because each
    small district's own count is below the global target). Distributes
    EMUs as evenly as possible within each group's own allocated share.
    Takes priority over panel_cap when both are given. panel_cap alone
    (defaulting to n_devices) is used when target_n_panels isn't given,
    preserving the simpler, original behaviour.

    barrier_groups, when given, partitions EMUs by group (e.g. district)
    FIRST and builds panels independently within each group — a panel can
    never mix EMUs from two different groups, however close they sit
    across the group boundary. Without this, a field team could in
    principle be scheduled to cover two districts in one cycle."""
    effective_cap = panel_cap if panel_cap is not None else n_devices
    if not barrier_groups:
        return _build_panels_within_group(centroids, effective_cap, target_n_panels)

    groups: Dict[str, Dict[str, Tuple[float, float, float]]] = {}
    for emu_id, c in centroids.items():
        group = barrier_groups.get(emu_id, "unknown")
        groups.setdefault(group, {})[emu_id] = c

    group_panel_targets: Dict[str, int] = {}
    if target_n_panels:
        group_sizes = {g: len(gc) for g, gc in groups.items()}
        group_panel_targets = _allocate_panels_across_groups(group_sizes, target_n_panels)

    all_panels: List[List[str]] = []
    for group, group_centroids in groups.items():
        group_target = group_panel_targets.get(group) if target_n_panels else None
        all_panels.extend(_build_panels_within_group(group_centroids, effective_cap, group_target))
    return all_panels


def _build_panels_within_group(
    centroids: Dict[str, Tuple[float, float, float]], panel_cap: int,
    target_n_panels: int | None = None,
) -> List[List[str]]:
    """Greedy nearest-neighbour bin-packing. See module docstring for why
    this is a declared heuristic, not a VRP solve. Returns a list of
    panels, each a list of emu_ids.

    With target_n_panels given, panel sizes are pre-computed to distribute
    all EMUs as evenly as possible across exactly that many panels (e.g.
    6 EMUs into 4 panels -> sizes [2, 2, 1, 1]), and each panel is grown
    to ITS OWN target size rather than a single shared cap — this is what
    actually hits a requested panel count exactly, which a uniform cap
    alone cannot guarantee whenever the EMU count doesn't divide evenly.
    Without target_n_panels, every panel uses panel_cap as its size limit,
    the original behaviour."""
    n = len(centroids)
    if target_n_panels:
        n_panels = min(target_n_panels, n)
        base, extra = divmod(n, n_panels)
        panel_sizes = [base + (1 if i < extra else 0) for i in range(n_panels)]
    else:
        panel_sizes = None  # each panel just uses panel_cap, computed as it's built

    remaining = dict(centroids)  # emu_id -> (x, y, area)
    panels: List[List[str]] = []

    while remaining:
        this_panel_cap = panel_sizes[len(panels)] if panel_sizes else panel_cap
        # Seed the next panel with the point farthest from the centroid of
        # everything already panelled (or, for the first panel, farthest
        # from the overall remaining centroid) — keeps panels from
        # overlapping the same geographic area.
        if panels:
            panelled_ids = [e for p in panels for e in p]
            ref_x = sum(centroids[e][0] for e in panelled_ids) / len(panelled_ids)
            ref_y = sum(centroids[e][1] for e in panelled_ids) / len(panelled_ids)
        else:
            xs = [v[0] for v in remaining.values()]
            ys = [v[1] for v in remaining.values()]
            ref_x, ref_y = sum(xs) / len(xs), sum(ys) / len(ys)

        seed = max(remaining, key=lambda e: _dist((remaining[e][0], remaining[e][1]), (ref_x, ref_y)))
        panel = [seed]
        del remaining[seed]

        while len(panel) < this_panel_cap and remaining:
            last = panel[-1]
            nearest = min(remaining, key=lambda e: _dist(
                (remaining[e][0], remaining[e][1]), (centroids[last][0], centroids[last][1])))

            panel.append(nearest)
            del remaining[nearest]

        panels.append(panel)

    return panels


def allocate_devices_largest_remainder(emu_sizes: Dict[str, float], n_devices: int) -> Dict[str, int]:
    """Proportional device allocation with a floor of 1 per EMU, largest-
    remainder method to hit n_devices exactly — the same method
    `PIPELINE_METHODOLOGY_REFERENCES.md` §5 documents as standard practice
    for stratified sampling design, applied here for real rather than just
    cited. Only used when n_emus <= n_devices (continuous_proportional
    regime) — the floor-of-1 guarantee requires that precondition."""
    total = sum(emu_sizes.values())
    if total <= 0:
        equal = n_devices // len(emu_sizes)
        return {e: max(1, equal) for e in emu_sizes}
    raw = {e: (s / total) * n_devices for e, s in emu_sizes.items()}
    floors = {e: max(1, int(v)) for e, v in raw.items()}
    remainder_budget = n_devices - sum(floors.values())
    if remainder_budget > 0:
        remainders = sorted(emu_sizes.keys(), key=lambda e: raw[e] - int(raw[e]), reverse=True)
        for e in remainders[:remainder_budget]:
            floors[e] += 1
    elif remainder_budget < 0:
        # Every EMU already had its floor-of-1 alone exceed n_devices
        # (very small n_devices relative to n_emus) — trim from the
        # largest allocations first, never below 1.
        trims = sorted(emu_sizes.keys(), key=lambda e: floors[e], reverse=True)
        i = 0
        while remainder_budget < 0 and i < len(trims) * 10:
            e = trims[i % len(trims)]
            if floors[e] > 1:
                floors[e] -= 1
                remainder_budget += 1
            i += 1
    return floors


def load_position_pools(project_dir: Path) -> Dict[str, List[Dict[str, Any]]]:
    """Reads 03b's position_pool.geojson, returns {emu_id: [positions...]}
    ordered by pool_rank (medoid first, rank None entries — the "never
    used" pool — excluded entirely, since a weekly rotation should only
    ever draw from the active pool)."""
    path = project_dir / "outputs" / "03b_position_scoring" / "position_pool.geojson"
    if not path.exists():
        return {}
    with open(path) as f:
        fc = json.load(f)
    by_emu: Dict[str, List[Dict[str, Any]]] = {}
    for feat in fc["features"]:
        props = feat["properties"]
        if not props.get("in_position_pool"):
            continue
        by_emu.setdefault(props["emu_id"], []).append(props)
    for emu_id in by_emu:
        by_emu[emu_id].sort(key=lambda p: (p.get("pool_rank") is None, p.get("pool_rank", 0)))
    return by_emu


def build_weekly_rotation(
    emu_ids: List[str], device_allocation: Dict[str, int],
    position_pools: Dict[str, List[Dict[str, Any]]], achievable_cycles: int,
    season_length_weeks: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """The actual continuous_proportional mechanism (Pimpri methodology
    §6): every EMU keeps its allocated device(s) for the WHOLE project,
    but the exact position rotates weekly through that EMU's position
    pool. When a pool has fewer positions than achievable_cycles, it wraps
    (repeats) — the Pimpri doc's own documented "pool wraps" behaviour for
    its smallest-pool segments, not an error condition.

    A project spanning multiple discrete seasons (e.g. 24 weeks = 3x8-week
    seasons) needs the SAME position at the SAME relative week in every
    season for a valid, ecologically-clean season-to-season comparison —
    variation observed at a fixed point should be attributable to the
    season, not to a different physical spot happening to be sampled that
    time. A single continuous rotation cycle does NOT give this: with a
    5-position pool over a 24-week programme, position 0 would recur at
    weeks 1, 6, 11, 16, 21 — not at week 1 of every season (1, 9, 17).
    `season_length_weeks`, when given, resets the rotation index at each
    season boundary instead of letting it run continuously. None (the
    default) preserves the original continuous behaviour unchanged for
    every project that isn't season-structured — the right choice for a
    different real goal (maximising raw spatial coverage with no
    season-to-season comparison requirement)."""
    weekly: List[Dict[str, Any]] = []
    for week in range(1, achievable_cycles + 1):
        rotation_week = ((week - 1) % season_length_weeks) if season_length_weeks else (week - 1)
        assignments = []
        for emu_id in emu_ids:
            pool = position_pools.get(emu_id, [])
            n_dev = device_allocation.get(emu_id, 1)
            if not pool:
                assignments.append({"emu_id": emu_id, "n_devices": n_dev, "positions": []})
                continue
            positions = []
            for d in range(n_dev):
                pos = pool[(rotation_week + d) % len(pool)]
                positions.append({
                    "name": pos.get("name"), "pool_rank": pos.get("pool_rank"),
                    "is_medoid": pos.get("is_medoid", False),
                    "wrapped": (rotation_week + d) >= len(pool),
                })
            assignments.append({"emu_id": emu_id, "n_devices": n_dev, "positions": positions})
        weekly.append({"week": week, "assignments": assignments})
    return weekly


def load_zone_grouping(project_dir: Path, zone_attribute: str) -> Dict[str, List[str]]:
    """Reads 03's candidates_with_emu.geojson, returns {zone_name: [emu_ids...]}
    — the real, authoritative zone membership of every EMU, ordered by each
    EMU's own real member-tile count descending (largest sub-EMU first, so
    a zone's rotation visits its most substantial real area before its
    smaller ones). Used to group EMUs into their real client-given zone for
    zone-scoped multi-EMU rotation — not derived by parsing EMU_ID strings,
    which would be fragile against any future naming change."""
    path = project_dir / "outputs" / "03_emu_delineation" / "candidates_with_emu.geojson"
    if not path.exists():
        return {}
    with open(path) as f:
        fc = json.load(f)
    emu_zone: Dict[str, str] = {}
    emu_tile_count: Dict[str, int] = {}
    for feat in fc["features"]:
        emu_id = feat["properties"].get("emu_id")
        zone_val = feat["properties"].get(zone_attribute)
        if emu_id is None or zone_val is None:
            continue
        emu_zone[emu_id] = zone_val
        emu_tile_count[emu_id] = emu_tile_count.get(emu_id, 0) + 1
    by_zone: Dict[str, List[str]] = {}
    for emu_id, zone_val in emu_zone.items():
        by_zone.setdefault(zone_val, []).append(emu_id)
    for zone_val in by_zone:
        by_zone[zone_val].sort(key=lambda e: -emu_tile_count[e])
    return by_zone


def select_representative_sub_emus(
    project_dir: Path, zone_to_emus: Dict[str, List[str]], max_sub_emus: int,
) -> Tuple[Dict[str, List[str]], Dict[str, Dict[str, Any]]]:
    """When a real zone's genuinely disconnected sub-areas outnumber how
    many a season can visit at least once (max_sub_emus, typically
    season_length_weeks), a rotating device cannot give every one of them
    even a single real visit. Rather than spread coverage so thin that
    most areas are barely sampled at all, this selects a REPRESENTATIVE
    SUBSET of size max_sub_emus to rotate through instead — using the same
    CRITIC-weighted typicality method already used to pick representative
    positions within one EMU (Diakoulaki, Mavrotas & Papayannakis 1995),
    just one level up: here, each candidate is a whole sub-EMU (scored by
    its own median covariate profile) rather than a single point, and
    "representative of the zone" replaces "representative of the EMU".

    Returns (trimmed zone_to_emus, per-zone selection report) — the report
    names exactly which real sub-areas were excluded and how many, so
    partial coverage is always visible, never silent."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "03b_position_scoring"))
    from position_scoring import critic_weights, typicality_within_emu
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "05_metrics_rollup"))
    from rollup import ALL_CONDITION_COVARIATES

    path = project_dir / "outputs" / "03_emu_delineation" / "candidates_with_emu.geojson"
    with open(path) as f:
        fc = json.load(f)
    by_emu_tiles: Dict[str, List[Dict[str, Any]]] = {}
    for feat in fc["features"]:
        emu_id = feat["properties"].get("emu_id")
        if emu_id:
            by_emu_tiles.setdefault(emu_id, []).append(feat["properties"])

    trimmed: Dict[str, List[str]] = {}
    selection_report: Dict[str, Dict[str, Any]] = {}
    for zone_val, emu_ids in zone_to_emus.items():
        if len(emu_ids) <= max_sub_emus:
            trimmed[zone_val] = emu_ids
            continue
        # Each sub-EMU's own median covariate profile becomes one "row" —
        # CRITIC weighting and typicality are computed relative to the
        # ZONE's own mean across its real sub-areas, exactly parallel to
        # how a single EMU's position typicality is relative to that EMU's
        # own mean, not a project-wide one.
        rows = []
        for emu_id in emu_ids:
            tiles = by_emu_tiles.get(emu_id, [])
            row = [np.nanmedian([t.get(c) for t in tiles if isinstance(t.get(c), (int, float))] or [np.nan])
                  for c in ALL_CONDITION_COVARIATES]
            rows.append(row)
        X = np.array(rows, dtype=float)
        weights, norm = critic_weights(X, ALL_CONDITION_COVARIATES, {})
        typicality = typicality_within_emu(norm, weights)
        order = np.argsort(-typicality)
        kept_idx = order[:max_sub_emus]
        kept_ids = [emu_ids[i] for i in kept_idx]
        excluded_ids = [emu_ids[i] for i in order[max_sub_emus:]]
        trimmed[zone_val] = kept_ids
        selection_report[zone_val] = {
            "n_real_sub_areas": len(emu_ids), "n_selected": len(kept_ids),
            "selected_emu_ids": kept_ids, "excluded_emu_ids": excluded_ids,
        }
    return trimmed, selection_report


def build_zone_scoped_rotation(
    zone_to_emus: Dict[str, List[str]], position_pools: Dict[str, List[Dict[str, Any]]],
    achievable_cycles: int, season_length_weeks: Optional[int] = None, n_devices: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """For a real zone that got sub-divided into multiple real EMUs (a
    "large" zone), the single device assigned to that ZONE rotates
    BETWEEN its own real sub-EMUs across weeks, not just
    between positions within one EMU — build_weekly_rotation handles the
    latter but has no concept of "zone" at all. A zone with only one
    EMU (a "small" zone) behaves identically to build_weekly_rotation for
    that EMU — this function is a strict generalisation, not a
    parallel mechanism with different behaviour for the simple case.

    Two nested rotations, both season-reset together (see
    build_weekly_rotation's docstring for why season-reset matters):
    which sub-EMU is visited this week
    cycles through the zone's own EMU list (largest first, wrapping if
    fewer EMUs than weeks-per-season); the exact position WITHIN whichever
    sub-EMU is visited also varies by how many times that specific sub-EMU
    has already been visited this season, so a sub-EMU revisited within
    the same season doesn't sit at the identical exact spot every time —
    the same "temporal replication instead of pretending there's more
    spatial replication than the geometry supports" principle already
    accepted for small zones, applied here to repeat VISITS of the same
    sub-EMU rather than repeat WEEKS at the same single position.

    n_devices, when given larger than the real zone count, allocates the
    leftover device(s) as a genuine SECOND position each week in the
    zone(s) with the largest real pool capacity, rather than leaving a
    real device unused every week. The bonus position uses a
    different rotation offset from the zone's own primary position, so it
    doesn't just duplicate the same spot with a second device."""
    weekly: List[Dict[str, Any]] = []
    # How many times each EMU has been visited so far THIS season — reset
    # whenever a new season starts, exactly parallel to the position-level
    # rotation index itself.
    visit_count_this_season: Dict[str, int] = {}
    current_season = None
    n_zones = len([z for z, e in zone_to_emus.items() if e])
    n_bonus_devices = max(0, (n_devices or n_zones) - n_zones)
    bonus_zones = []
    if n_bonus_devices:
        # Real pool capacity, not raw area — the zone(s) whose position
        # pool can genuinely support a second, well-separated device get
        # the bonus, not just the zone with the biggest declared boundary.
        zone_pool_size = {}
        for zone_val, emu_ids in zone_to_emus.items():
            if emu_ids:
                zone_pool_size[zone_val] = len(position_pools.get(emu_ids[0], []))
        bonus_zones = sorted(zone_pool_size, key=lambda z: -zone_pool_size[z])[:n_bonus_devices]

    for week in range(1, achievable_cycles + 1):
        season_idx = ((week - 1) // season_length_weeks) if season_length_weeks else 0
        rotation_week = ((week - 1) % season_length_weeks) if season_length_weeks else (week - 1)
        if season_idx != current_season:
            visit_count_this_season = {}
            current_season = season_idx

        assignments = []
        for zone_val, emu_ids in zone_to_emus.items():
            if not emu_ids:
                continue
            emu_idx = rotation_week % len(emu_ids)
            active_emu = emu_ids[emu_idx]
            pool = position_pools.get(active_emu, [])
            visit_n = visit_count_this_season.get(active_emu, 0)
            visit_count_this_season[active_emu] = visit_n + 1
            if not pool:
                assignments.append({"zone": zone_val, "emu_id": active_emu, "positions": [],
                                    "visit_number_this_season": visit_n + 1})
                continue
            positions_here = [pool[visit_n % len(pool)]]
            if zone_val in bonus_zones and len(pool) > 1:
                # Offset by roughly half the pool so the bonus position is
                # genuinely different from the primary one, not adjacent
                # to it — both still real, spacing-verified pool members.
                bonus_idx = (visit_n + len(pool) // 2) % len(pool)
                if bonus_idx != visit_n % len(pool):
                    positions_here.append(pool[bonus_idx])
            assignments.append({
                "zone": zone_val, "emu_id": active_emu,
                "positions": [{"name": p.get("name"), "pool_rank": p.get("pool_rank"),
                              "is_medoid": p.get("is_medoid", False),
                              "wrapped": visit_n >= len(pool)} for p in positions_here],
                "visit_number_this_season": visit_n + 1,
                "zone_rotation_wrapped": rotation_week >= len(emu_ids),  # True once the
                # zone's own EMU list has been fully cycled through and a
                # repeat round has started within this season
            })
        weekly.append({"week": week, "assignments": assignments})
    return weekly


def build_camera_trap_zone_rotation(
    project_dir: Path, cfg: Dict[str, Any], zone_to_emus: Dict[str, List[str]],
    position_pools: Dict[str, List[Dict[str, Any]]], achievable_cycles: int,
    season_length_weeks: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Under zone_scoped_continuous, every zone has its OWN
    permanently-assigned audiomoth, so camera trap co-locating with
    "whatever audiomoth is doing" doesn't mean anything — every zone would
    show as active every week. Camera trap needs its own independent
    rotation instead: with n_devices cameras and more real zones than
    that, each camera visits one zone per week, round-robin, wrapping.
    Season-reset consistent with every other rotation in this module."""
    zone_names = sorted(zone_to_emus.keys())
    n_cam = cfg.get("camera_trap_n_devices", 1)

    # When there are more real zones than a season can each visit at
    # least once, exclude the SAME smallest-area zone from
    # camera trap's rotation consistently, every season — not whichever
    # zone happens to be last in the rotation order, and not a different
    # zone each season. Audiomoth still covers the excluded zone every
    # week regardless, since it has its own permanently-assigned device
    # there; only camera trap coverage is affected.
    rotation_zones = zone_names
    if season_length_weeks and len(zone_names) > season_length_weeks:
        path = project_dir / "outputs" / "03_emu_delineation" / "candidates_with_emu.geojson"
        with open(path) as f:
            fc = json.load(f)
        projected_crs = crs.resolve(shape(fc["features"][0]["geometry"]))
        zone_area_m2: Dict[str, float] = {}
        for feat in fc["features"]:
            zv = feat["properties"].get("eco_zone")
            if zv in zone_to_emus:
                zone_area_m2[zv] = zone_area_m2.get(zv, 0.0) + crs.to_m(
                    shape(feat["geometry"]), projected_crs).area
        n_to_drop = len(zone_names) - season_length_weeks
        smallest = sorted(zone_area_m2, key=lambda z: zone_area_m2[z])[:n_to_drop]
        rotation_zones = [z for z in zone_names if z not in smallest]

    weekly = []
    for week in range(1, achievable_cycles + 1):
        rotation_week = ((week - 1) % season_length_weeks) if season_length_weeks else (week - 1)
        positions = []
        for d in range(n_cam):
            zone_idx = (rotation_week + d) % len(rotation_zones)
            zone_val = rotation_zones[zone_idx]
            emu_id = zone_to_emus[zone_val][0]  # one EMU per zone under zone_is_emu
            pool = position_pools.get(emu_id, [])
            if not pool:
                continue
            pos = pool[0]  # the zone's own medoid — the single most
            # representative point, matching a one-week visit's need for
            # one good spot rather than a further within-zone rotation
            positions.append({"name": pos.get("name"), "emu_id": emu_id, "zone": zone_val,
                             "wrapped": False, "shared_with_audiomoth": False})
        weekly.append({"week": week, "positions": positions})
    return weekly


def build_camera_trap_rotation_colocated(
    project_dir: Path, cfg: Dict[str, Any], week_active_emus: Dict[int, List[str]],
    position_pools: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]] | None:
    """REPLACES the old independent, project-wide camera trap pool (Aug
    2026, after confirming directly against the real Tata Motors
    methodology document: "Deployment logic: Co-located with the
    terrestrial PAM position, rotating which segment it accompanies week
    to week — with only one device, dedicating it permanently to one
    segment would leave nine unsampled by this stream entirely"). Camera
    trap now follows whatever EMU(s) audiomoth is actively covering each
    week — not a separately-optimised, independently-scheduled pool that
    could send the field team to a completely different, unrelated EMU
    the same week for no operational reason.

    Splits camera_trap_n_devices proportionally (largest-remainder, by
    that EMU's own audiomoth capacity) across a week's active EMU(s), then
    picks that many spacing-compliant positions from WITHIN each EMU's own
    real candidate pool — distinct from whatever positions audiomoth is
    already using there that week, so the two streams sample different
    exact spots inside the same stratum rather than duplicating a
    coordinate."""
    if "camera_trap" not in cfg.get("streams_active", []):
        return None
    n_dev_total = cfg.get("camera_trap_n_devices", 2)
    min_spacing_m = cfg.get("min_device_spacing_m", 100.0)

    # Import here to avoid a hard dependency at module load time if 03b's
    # module isn't on the path in every context this file is imported from.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "03b_position_scoring"))
    from position_scoring import select_spacing_compliant_positions

    emu_dir = project_dir / "outputs" / "03_emu_delineation"
    with open(emu_dir / "candidates_with_emu.geojson") as f:
        all_tiles = json.load(f)["features"]
    projected_crs = crs.resolve(shape(all_tiles[0]["geometry"]))
    by_emu_tiles: Dict[str, List[Dict[str, Any]]] = {}
    for feat in all_tiles:
        eid = feat["properties"].get("emu_id")
        if eid:
            by_emu_tiles.setdefault(eid, []).append(feat)

    excluded_emus = set(cfg.get("camera_trap_excluded_emus", []))

    weekly = []
    for week, active_emus in week_active_emus.items():
        # An EMU declared here never gets a camera trap allocation, even
        # in a week where audiomoth is actively there — the two streams
        # aren't required to always co-locate, just usually do.
        active_emus = [e for e in active_emus if e not in excluded_emus]
        if not active_emus:
            weekly.append({"week": week, "positions": []})
            continue
        # Proportional split by each active EMU's own real position-pool
        # size (a direct, already-computed proxy for that EMU's real
        # spatial capacity) — mirrors how audiomoth devices split within a
        # shared week.
        emu_weights = {e: max(1, len(position_pools.get(e, []))) for e in active_emus}
        cam_alloc = allocate_devices_largest_remainder(emu_weights, n_dev_total) if len(active_emus) > 1 \
            else {active_emus[0]: n_dev_total}

        week_positions = []
        for emu_id, n_here in cam_alloc.items():
            tiles = by_emu_tiles.get(emu_id, [])
            if not tiles:
                continue
            used_names = {p["name"] for p in position_pools.get(emu_id, [])[:cfg["n_devices"]]
                         if p.get("pool_rank") is not None}
            # Rank remaining (not-already-used-by-audiomoth) candidates by
            # the same typicality data already computed in 03b, so camera
            # trap still gets the objectively best available spots, not an
            # arbitrary pick.
            pool_by_name = {p["name"]: p for p in position_pools.get(emu_id, [])}
            candidates = [t for t in tiles
                         if (t["properties"].get("display_name") or t["properties"].get("name")) not in used_names]
            forced_shared_position = False
            if not candidates:
                # An EMU with only one real candidate tile has no
                # alternative position for camera trap to use once
                # audiomoth already occupies the only spot that exists —
                # falling back to the full tile set (reusing that same
                # position) is the only honest option, flagged explicitly
                # below as a declared constraint, not a silent coincidence.
                candidates = tiles
                forced_shared_position = True
            xy, typ, names = [], [], []
            for t in candidates:
                c = crs.to_m(shape(t["geometry"]), projected_crs).centroid
                xy.append((c.x, c.y))
                info = pool_by_name.get(t["properties"].get("name"))
                typ.append(info.get("typicality_percentile", 0) if info else 0)
                names.append(t["properties"].get("display_name") or t["properties"].get("name"))
            if not xy:
                continue
            # boundary_dist is computed from the EMU's FULL real geometry
            # (all member tiles, not just the candidates remaining after
            # excluding audiomoth's own picks), matching exactly how
            # position_scoring.py computes it for the audiomoth pool.
            emu_boundary = unary_union([crs.to_m(shape(t["geometry"]), projected_crs)
                                        for t in tiles]).boundary
            boundary_dist = np.array([crs.to_m(shape(t["geometry"]), projected_crs)
                                      .centroid.distance(emu_boundary) for t in candidates])
            seed = int(np.argmax(typ))
            picked_idx = select_spacing_compliant_positions(
                xy, np.array(typ), seed, min_spacing_m=min_spacing_m, max_positions=n_here,
                boundary_dist=boundary_dist, interior_bonus_weight=0.7)
            # interior_bonus_weight raised above the 0.5 default (reported
            # directly: "camera traps are mostly being put at edge or
            # corner of an EMU") — checked directly why the interior-bonus
            # fix, already wired in here, wasn't fully solving it: camera
            # trap draws from a SMALLER candidate subset (audiomoth's own
            # picks already excluded), so the most-interior spots are
            # often already claimed before camera trap gets to choose,
            # structurally biasing its remaining options toward the edge
            # more than audiomoth's own selection. A stronger interior
            # weight compensates for drawing from this reduced pool.
            for i in picked_idx:
                week_positions.append({"name": names[i], "emu_id": emu_id, "wrapped": False,
                                       "shared_with_audiomoth": forced_shared_position})
        weekly.append({"week": week, "positions": week_positions})
    return weekly


def compute_emu_capacity(area_ha: float, min_spacing_m: float, n_devices: int) -> int:
    """How many simultaneous, reasonably-spaced device positions an EMU
    can actually host — area divided by the area one spacing-radius
    circle needs, floored at 1 (every real EMU can host at least one
    device) and capped at the project's total device count (no EMU needs
    more than that regardless of size)."""
    spacing_area_ha = (min_spacing_m ** 2) / 10_000.0
    if spacing_area_ha <= 0:
        return n_devices
    return max(1, min(n_devices, int(area_ha / spacing_area_ha)))


def build_stratified_single_pass_weeks(
    capacities: Dict[str, int], n_devices: int, achievable_weeks: int,
) -> Dict[str, Any]:
    """Each EMU is sampled ONCE, in exactly one assigned week, with 1+
    devices proportional to its real spacing-based capacity — NOT every
    EMU getting a permanent device for the whole project (see
    config_schema.py's note on sampling_design; that's
    continuous_multi_week, a different regime for a different kind of
    project).

    `capacities` is the REAL, position-pool-verified count of
    spacing-compliant positions each EMU's actual candidate geometry
    supports (see 03b_position_scoring's select_spacing_compliant_positions)
    — not a crude area-divided-by-a-spacing-circle estimate, which
    doesn't know an EMU's real shape (an elongated wetland-plus-island
    can genuinely fit more well-spaced points than a compact area of the
    same total hectares would suggest, and vice versa for an irregular
    footprint).

    Algorithm: sort EMUs by capacity descending, deal round-robin into
    `achievable_weeks` buckets (spreads large and small EMUs across
    different weeks rather than front-loading), then within each week
    allocate that week's n_devices proportionally across its assigned
    EMUs by capacity (largest-remainder method), capped at each EMU's own
    capacity ceiling so a small EMU never gets more devices than it can
    actually host with real, verified spacing."""
    ordered = sorted(capacities, key=lambda e: -capacities[e])

    weeks: Dict[int, List[str]] = {w: [] for w in range(1, achievable_weeks + 1)}
    for i, emu_id in enumerate(ordered):
        week = (i % achievable_weeks) + 1
        weeks[week].append(emu_id)

    week_allocations: Dict[int, Dict[str, int]] = {}
    for week, emu_ids in weeks.items():
        if not emu_ids:
            week_allocations[week] = {}
            continue
        week_caps = {e: capacities[e] for e in emu_ids}
        raw_alloc = allocate_devices_largest_remainder(week_caps, n_devices)
        # Cap each EMU at its own real capacity — largest-remainder alone
        # can push an allocation above what allocate_devices_largest_remainder's
        # generic floor-of-1 logic assumes when there's only one EMU in a
        # week and its capacity is below n_devices; the leftover unused
        # devices in that case are a real, honest fact (not enough
        # spatially-distinct room for more), not silently hidden.
        capped_alloc = {e: min(raw_alloc.get(e, 1), week_caps[e]) for e in emu_ids}

        # A week whose only EMU has a small capacity would otherwise leave
        # most devices idle for that whole week — a real waste of field
        # time. Any leftover devices this week are redistributed as BONUS
        # positions to that week's active EMU(s), proportional to size,
        # for extra spatial replication rather than sitting unused —
        # capped at the SMALLER of 3x an EMU's base allocation (so a tiny
        # stratum doesn't get absurdly over-sampled just because the
        # calendar paired it with spare capacity) OR its own real capacity
        # ceiling — capacity here is the TRUE, position-pool-verified
        # achievable maximum, not a conservative area-based estimate the
        # "3x" multiplier could otherwise exceed.
        leftover = n_devices - sum(capped_alloc.values())
        if leftover > 0 and emu_ids:
            bonus_ceiling = {e: min(capped_alloc[e] * 3, week_caps[e]) for e in emu_ids}
            remaining_leftover = leftover
            # Distribute one bonus device at a time to whichever eligible
            # EMU currently has the largest capacity (mirrors the
            # proportional-by-size intent without a second, confusing
            # largest-remainder call on a different total).
            eligible = [e for e in emu_ids if capped_alloc[e] < bonus_ceiling[e]]
            while remaining_leftover > 0 and eligible:
                pick = max(eligible, key=lambda e: capacities[e])
                capped_alloc[pick] += 1
                remaining_leftover -= 1
                eligible = [e for e in emu_ids if capped_alloc[e] < bonus_ceiling[e]]
            # Any leftover after every active EMU hits its bonus ceiling is
            # a genuine fact (real spatial room is exhausted, not a
            # calculation gap) — left unused rather than forced further.
        week_allocations[week] = capped_alloc

    return {"weeks": weeks, "capacities": capacities, "week_allocations": week_allocations}


def run_panel_scheduling(project_dir: str | Path) -> Dict[str, Any]:
    project_dir = Path(project_dir)
    cfg = config_schema.load_config(project_dir / "config.yaml")
    is_contiguous = cfg["archetype"] in ("conservation", "industrial")
    emu_dir = project_dir / "outputs" / "03_emu_delineation"

    if is_contiguous:
        emu_path = emu_dir / "emus.geojson"
    else:
        emu_path = emu_dir / "candidates_with_emu.geojson"
    if not emu_path.exists():
        raise FileNotFoundError(f"{emu_path} not found — run 03_emu_delineation first.")
    with open(emu_path) as f:
        fc = json.load(f)

    aoi_path = project_dir / "outputs" / "01_ingestion" / "aoi_boundary.geojson"
    if aoi_path.exists():
        with open(aoi_path) as f:
            aoi_geom = shape(json.load(f)["features"][0]["geometry"])
        projected_crs = crs.resolve(aoi_geom)
    else:
        first_geom = shape(fc["features"][0]["geometry"])
        projected_crs = crs.resolve(first_geom)

    centroids = (_emu_centroids_contiguous(fc, projected_crs) if is_contiguous
                 else _emu_centroids_agroforestry(fc, projected_crs))
    n_emus = len(centroids)
    n_devices = cfg["n_devices"]

    # District-aware (or more generally barrier-aware) panels — only
    # meaningful for agroforestry, which is the only archetype using a
    # hard_barrier_attribute at EMU delineation in the first place.
    barrier_groups = None
    barrier_attr = cfg.get("hard_barrier_attribute")
    if not is_contiguous:
        if barrier_attr:
            barrier_groups = _emu_barrier_groups(fc, barrier_attr)

    cycle_turnover_days = cfg["cycle_length_days"] + cfg["logistics_buffer_days"]

    warnings = []
    sampling_design = cfg.get("sampling_design", "continuous_multi_week")
    # For a zone-partitioned contiguous project, a "large" real zone gets
    # split into MULTIPLE real sub-EMUs — so n_emus (total EMU count
    # across every zone) can genuinely exceed n_devices even though every
    # real zone still gets exactly one device. The regime choice needs
    # n_ZONES, not n_EMUS, for this case — otherwise a project like this
    # would wrongly fall through to sequential_cluster (a different
    # regime, not designed for "one device rotates within its own zone
    # forever"). Only activated if zone_attribute has REAL, non-null
    # values on at
    # least one EMU — the same defensive check used in
    # segmentation_reconciliation.py, so a project that never opted into
    # zone-partitioning (barrier_attr defaults to "attr_admin_district"
    # globally) is completely unaffected.
    zone_to_emus: Dict[str, List[str]] = {}
    zone_representative_selection: Dict[str, Dict[str, Any]] = {}
    if barrier_attr:
        zone_to_emus = load_zone_grouping(project_dir, barrier_attr)
        # When a real zone's genuinely disconnected sub-areas outnumber
        # how many a season can visit at least once, rotate through a
        # representative subset instead of spreading coverage so thin
        # that most areas barely get sampled at all — see
        # select_representative_sub_emus' own docstring for the real
        # reasoning and method. Only applied for a season-structured
        # project (season_length_weeks set); a project without seasons
        # has no natural "visit everything at least once" cap to trim to.
        season_len = cfg.get("season_length_weeks")
        if zone_to_emus and season_len:
            zone_to_emus, zone_representative_selection = select_representative_sub_emus(
                project_dir, zone_to_emus, season_len)
    n_zones = len(zone_to_emus)
    # zone_scoped_continuous is only correct for a project that explicitly
    # opted into treating each real zone as one EMU directly
    # (zone_is_emu) — a project doing normal sub-clustering within a
    # barrier-attribute partition (e.g. district, for agroforestry) that
    # just happens to have few real partition values relative to device
    # count is a completely different, unrelated situation.
    zone_scoped_active = bool(zone_to_emus) and n_zones <= n_devices and cfg.get("zone_is_emu", False)

    if sampling_design == "stratified_single_pass":
        regime = "stratified_single_pass"
    elif zone_scoped_active:
        regime = "zone_scoped_continuous"
    elif n_emus <= n_devices:
        regime = "continuous_proportional"
    else:
        regime = "sequential_cluster"

    # achievable_cycles uses a turnover-day formula that's right for
    # sequential_cluster (visiting a DIFFERENT, distant EMU genuinely needs
    # the full deploy+record+retrieve+buffer cycle before the next visit
    # can start) but wrong for continuous_proportional — the device never
    # leaves its EMU between weeks, only its exact position shifts, so
    # there's no multi-day gap to fit within the week count; it gets one
    # rotation per calendar week for the whole project duration instead.
    # stratified_single_pass ALSO uses straight weeks — each EMU's single
    # assigned week is just one of the project's real calendar weeks, no
    # turnover reduction applies to picking which week that is either.
    # zone_scoped_continuous is the same case as continuous_proportional
    # for this purpose: a device is permanently assigned to its own zone
    # and never travels to a different, distant one between weeks, so
    # there's no multi-day turnover gap to fit within the week count here
    # either.
    if regime in ("continuous_proportional", "stratified_single_pass", "zone_scoped_continuous"):
        achievable_cycles = max(1, cfg["project_duration_weeks"])
        achievable_cycles_extended = max(1, cfg["project_duration_weeks"] + cfg["max_duration_extension_weeks"])
    else:
        achievable_cycles = max(1, int((cfg["project_duration_weeks"] * 7) // cycle_turnover_days))
        extended_weeks = cfg["project_duration_weeks"] + cfg["max_duration_extension_weeks"]
        achievable_cycles_extended = max(1, int((extended_weeks * 7) // cycle_turnover_days))

    weekly_schedule = None
    stratified_result = None
    if regime == "stratified_single_pass":
        panels = None
        uncovered_emu_ids: List[str] = []
        used_extension = False
        # Capacity comes from the REAL, position-pool-verified count of
        # spacing-compliant positions each EMU's actual candidate
        # geometry supports (03b_position_scoring), not a crude
        # area-divided-by-a-spacing-circle formula that doesn't know an
        # EMU's real shape.
        position_pools_for_capacity = load_position_pools(project_dir)
        capacities = {e: len(position_pools_for_capacity.get(e, [])) or 1 for e in centroids}
        stratified_result = build_stratified_single_pass_weeks(capacities, n_devices, achievable_cycles)
        logger.info("sampling_design=stratified_single_pass: %d EMUs assigned across %d weeks, "
                    "capacities=%s", n_emus, achievable_cycles, stratified_result["capacities"])
    elif regime == "zone_scoped_continuous":
        panels = [[e for emu_ids in zone_to_emus.values() for e in emu_ids]]
        uncovered_emu_ids: List[str] = []
        used_extension = False
        position_pools = load_position_pools(project_dir)
        weekly_schedule = build_zone_scoped_rotation(
            zone_to_emus, position_pools, achievable_cycles,
            season_length_weeks=cfg.get("season_length_weeks"), n_devices=n_devices)
        missing_pools = [e for emu_ids in zone_to_emus.values() for e in emu_ids
                         if e not in position_pools]
        if missing_pools:
            warnings.append(
                f"No position pool found for {len(missing_pools)} EMU(s) "
                f"({missing_pools}) — run 03b_position_scoring before trusting "
                "the zone-scoped rotation for these.")
        for zone_val, sel in zone_representative_selection.items():
            warnings.append(
                f"Zone '{zone_val}' has {sel['n_real_sub_areas']} genuinely disconnected real "
                f"sub-areas — more than one season can each visit at least once. Rotating "
                f"through the {sel['n_selected']} most representative ones instead (CRITIC-"
                f"weighted typicality relative to this zone's own real covariate range), not "
                f"all of them: {sel['n_real_sub_areas'] - sel['n_selected']} real sub-area(s) "
                f"are not visited by audiomoth/camera trap this programme "
                f"({sel['excluded_emu_ids']}). Partial coverage by deliberate design, not an "
                "oversight — see the zone-scoped rotation methodology.")
        logger.info("n_zones (%d) <= n_devices (%d), zone-partitioned — "
                    "zone_scoped_continuous regime, %d-week rotation.",
                    n_zones, n_devices, achievable_cycles)
    elif regime == "continuous_proportional":
        panels = [list(centroids.keys())]
        uncovered_emu_ids: List[str] = []
        used_extension = False
        emu_sizes = {e: c[2] for e, c in centroids.items()}  # area_ha as the proportional-share basis
        device_allocation = allocate_devices_largest_remainder(emu_sizes, n_devices)
        position_pools = load_position_pools(project_dir)
        weekly_schedule = build_weekly_rotation(
            list(centroids.keys()), device_allocation, position_pools, achievable_cycles,
            season_length_weeks=cfg.get("season_length_weeks"))
        missing_pools = [e for e in centroids if e not in position_pools]
        if missing_pools:
            warnings.append(
                f"No position pool found for {len(missing_pools)} EMU(s) "
                f"({missing_pools}) — run 03b_position_scoring before trusting "
                "the weekly rotation for these. Falling back to no specific "
                "position assigned for them this run.")
        logger.info("n_EMUs (%d) <= n_devices (%d) — continuous_proportional regime, "
                    "%d-week position rotation.", n_emus, n_devices, achievable_cycles)
    else:  # sequential_cluster
        # Greedy bin-packing alone always minimises panel count; a
        # uniform per-panel cap based on project_duration_weeks can still
        # undershoot the real available weeks when the EMU count doesn't
        # divide evenly by it. target_n_panels builds EXACTLY the declared
        # number of weeks (or as close as EMU count allows), distributing
        # EMUs as evenly as possible across them.
        target_n_panels = min(n_emus, cfg["project_duration_weeks"])
        max_possible_panel_size = -(-n_emus // target_n_panels)  # ceil division
        if max_possible_panel_size > n_devices:
            # Real safety net: with very few weeks relative to EMU count,
            # even distribution could still require more devices than
            # exist in one panel — falls back to the simpler device-count
            # cap, which the "leftover devices become bonus positions"
            # logic downstream already handles safely.
            logger.warning("project_duration_weeks (%d) is too few for %d EMUs to spread "
                           "evenly within %d devices per panel — falling back to the "
                           "device-count cap instead of the requested week spread.",
                           cfg["project_duration_weeks"], n_emus, n_devices)
            all_panels = build_panels(centroids, n_devices, barrier_groups)
        else:
            all_panels = build_panels(centroids, n_devices, barrier_groups, target_n_panels=target_n_panels)
        used_extension = False
        # POLICY: devices are never added. Duration may extend by at most
        # max_duration_extension_weeks, and ONLY if that actually closes
        # the gap — otherwise accept partial coverage and say so
        # explicitly, rather than silently scheduling cycles beyond the
        # real timeline.
        if len(all_panels) <= achievable_cycles:
            cap = achievable_cycles
        elif len(all_panels) <= achievable_cycles_extended:
            cap = achievable_cycles_extended
            used_extension = True
        else:
            cap = achievable_cycles
        panels = all_panels[:cap]
        uncovered_emu_ids = [e for p in all_panels[cap:] for e in p]
        if used_extension:
            warnings.append(
                f"{len(all_panels)} panels needed; fits within "
                f"{extended_weeks} weeks (+{cfg['max_duration_extension_weeks']} week "
                f"extension) but NOT the base {cfg['project_duration_weeks']} weeks. "
                "Using the extension — this is the last-resort case per policy "
                "(devices cannot be added), flagged explicitly rather than applied "
                "silently. Confirm before mobilising.")
        if uncovered_emu_ids:
            # POLICY: an uncovered EMU is never an acceptable
            # report/deliverable outcome, not something to footnote and
            # move past. If 03_emu_delineation's target and this module's
            # real capacity ever disagree badly enough to reach this branch,
            # that's an internal inconsistency between the two stages, not
            # a fact about the site to report to a client. Hard failure,
            # pointing at the actual fix (re-tune the EMU target in 03),
            # rather than a soft warning that lets a bad state flow through
            # to a report.
            raise RuntimeError(
                f"{len(uncovered_emu_ids)} EMU(s) do not fit within "
                f"{extended_weeks if used_extension else cfg['project_duration_weeks']} weeks "
                f"at {n_devices} devices: {uncovered_emu_ids}.\n"
                "This should not happen if 03_emu_delineation's EMU count was "
                "correctly bounded by the same achievable-cycles logic used here — "
                "it means the two stages disagreed. Per policy, devices are never "
                "added and duration extends by at most "
                f"{cfg['max_duration_extension_weeks']} week(s). Fix at the source: "
                "reduce the EMU/segment target in 03 (segmentation_reconciliation's "
                "target_n_segments, or ecological_clustering's K_max inputs) so every "
                "delineated EMU is guaranteed a slot before it's ever presented as "
                "a design decision.")

    # Camera trap follows whichever EMU(s) audiomoth is actively covering
    # each week, built generically across regimes rather than assuming
    # any one regime specifically.
    if stratified_result:
        week_active_emus = stratified_result["weeks"]
    elif regime == "zone_scoped_continuous":
        # Every zone's currently-active sub-EMU (which varies week to week
        # — that's the whole point of zone-scoped rotation) is active,
        # every week — camera trap co-locates with whichever real sub-EMU
        # audiomoth happens to be visiting that week within each zone.
        week_active_emus = {
            row["week"]: [a["emu_id"] for a in row["assignments"]] for row in weekly_schedule
        }
    elif regime == "continuous_proportional":
        week_active_emus = {w: list(centroids.keys()) for w in range(1, achievable_cycles + 1)}
    else:
        week_active_emus = {}  # sequential_cluster: built per-cycle further down if ever needed
    position_pools_for_camera = load_position_pools(project_dir)
    if regime == "zone_scoped_continuous" and cfg.get("camera_trap_n_devices", 1) < n_zones:
        # Real fix: under zone_is_emu, every zone's audiomoth is
        # permanently present — "co-locate with audiomoth's active zone"
        # no longer distinguishes anything, since every zone is always
        # active. Camera trap gets its own independent rotation instead
        # — see build_camera_trap_zone_rotation's own docstring.
        camera_trap_weekly = build_camera_trap_zone_rotation(
            project_dir, cfg, zone_to_emus, position_pools_for_camera,
            achievable_cycles, season_length_weeks=cfg.get("season_length_weeks"))
        zones_with_camera_coverage = {p["zone"] for w in camera_trap_weekly for p in w["positions"]}
        excluded_zones = set(zone_to_emus.keys()) - zones_with_camera_coverage
        if excluded_zones:
            warnings.append(
                f"Camera trap ({cfg.get('camera_trap_n_devices', 1)} device(s)) cannot visit "
                f"every one of {n_zones} real zones at least once per {cfg.get('season_length_weeks')}"
                f"-week season — {sorted(excluded_zones)} (smallest by real area) excluded from "
                "camera trap rotation for the whole programme, every season, by deliberate design. "
                "Audiomoth still covers it every week via its own permanently-assigned device; "
                "only camera trap coverage is affected.")
    else:
        camera_trap_weekly = build_camera_trap_rotation_colocated(
            project_dir, cfg, week_active_emus, position_pools_for_camera)
    if camera_trap_weekly:
        shared_positions = [(w["week"], p["emu_id"], p["name"]) for w in camera_trap_weekly
                            for p in w["positions"] if p.get("shared_with_audiomoth")]
        if shared_positions:
            warnings.append(
                f"Camera trap forced to share the exact same position as audiomoth in "
                f"{len(shared_positions)} case(s) — the EMU has only one real candidate "
                f"tile, so there's no alternative spot: {shared_positions}. A real, "
                "unavoidable constraint of that EMU's size, not a selection error.")

    avg_speed_kmh = cfg.get("avg_travel_speed_kmh", 25.0)
    max_travel_hours = cfg["max_panel_travel_hours"]
    schedule = []
    if regime == "stratified_single_pass":
        # Each EMU appears in exactly ONE week's schedule entry, with
        # capacity-proportional devices drawn from the top of its own
        # position pool (no rotation — the whole point of this regime is
        # that a stratum is sampled once, not compared week over week).
        position_pools = load_position_pools(project_dir)
        camera_by_week = {w["week"]: w["positions"] for w in (camera_trap_weekly or [])}
        for week_num in range(1, achievable_cycles + 1):
            start_day = (week_num - 1) * cfg["cycle_length_days"]
            assignments = []
            for emu_id in stratified_result["weeks"].get(week_num, []):
                n_dev_here = stratified_result["week_allocations"][week_num].get(emu_id, 1)
                pool = position_pools.get(emu_id, [])
                positions = [{"name": p.get("name"), "pool_rank": p.get("pool_rank"),
                             "is_medoid": p.get("is_medoid", False), "wrapped": False}
                            for p in pool[:n_dev_here]]
                if len(positions) < n_dev_here:
                    warnings.append(
                        f"{emu_id} (week {week_num}): allocated {n_dev_here} devices but its "
                        f"position pool only has {len(positions)} distinct positions — "
                        "re-run 03b_position_scoring with a larger pool target, or accept "
                        "fewer devices there this baseline.")
                assignments.append({"emu_id": emu_id, "n_devices": n_dev_here, "positions": positions})
            schedule.append({
                "cycle_number": week_num,
                "start_day_offset": start_day,
                "recording_end_day_offset": start_day + cfg["cycle_length_days"],
                "emu_ids": stratified_result["weeks"].get(week_num, []),
                "n_devices_used": sum(stratified_result["week_allocations"][week_num].values()),
                "position_assignments": assignments,
                "camera_trap_positions": camera_by_week.get(week_num, []),
                "est_max_internal_travel_km": 0.0,
                "est_max_internal_travel_hours": 0.0,
            })
    elif regime == "continuous_proportional":
        # Every week is its own schedule entry — ALL EMUs active every
        # week (that's the whole point of "continuous"), each with that
        # week's rotated position(s) attached. No panel/travel logic
        # applies here — devices don't move between EMUs, only the exact
        # position within each EMU changes.
        #
        # Day-offsets here use cycle_length_days alone, not
        # cycle_turnover_days (cycle length + logistics buffer) — that
        # buffer is right for sequential_cluster (a genuinely separate
        # redeployment trip needs it) but wrong here, since a
        # continuous_proportional device never leaves its EMU, so weeks
        # are back-to-back with no extra gap between them.
        assignments_by_week = {w["week"]: w["assignments"] for w in weekly_schedule}
        camera_by_week = {w["week"]: w["positions"] for w in (camera_trap_weekly or [])}
        for week_num in range(1, achievable_cycles + 1):
            start_day = (week_num - 1) * cfg["cycle_length_days"]
            schedule.append({
                "cycle_number": week_num,
                "start_day_offset": start_day,
                "recording_end_day_offset": start_day + cfg["cycle_length_days"],
                "emu_ids": list(centroids.keys()),
                "n_devices_used": n_devices,
                "position_assignments": assignments_by_week.get(week_num, []),
                "camera_trap_positions": camera_by_week.get(week_num, []),
                "est_max_internal_travel_km": 0.0,
                "est_max_internal_travel_hours": 0.0,
            })
    elif regime == "zone_scoped_continuous":
        # Real day-offset reasoning matches continuous_proportional exactly
        # (see that branch's own note) — a device never leaves its ZONE,
        # so weeks are back-to-back with no extra logistics-buffer gap,
        # even though which specific sub-EMU it's visiting within the zone
        # changes week to week.
        assignments_by_week = {w["week"]: w["assignments"] for w in weekly_schedule}
        camera_by_week = {w["week"]: w["positions"] for w in (camera_trap_weekly or [])}
        for week_num in range(1, achievable_cycles + 1):
            start_day = (week_num - 1) * cfg["cycle_length_days"]
            active_emus_this_week = week_active_emus.get(week_num, [])
            schedule.append({
                "cycle_number": week_num,
                "start_day_offset": start_day,
                "recording_end_day_offset": start_day + cfg["cycle_length_days"],
                "emu_ids": active_emus_this_week,
                "n_devices_used": len(zone_to_emus),
                "position_assignments": assignments_by_week.get(week_num, []),
                "camera_trap_positions": camera_by_week.get(week_num, []),
                "est_max_internal_travel_km": 0.0,
                "est_max_internal_travel_hours": 0.0,
            })
    else:
        for cycle_num, panel in enumerate(panels, start=1):
            start_day = (cycle_num - 1) * cycle_turnover_days
            pairwise_km = [
                _dist((centroids[a][0], centroids[a][1]), (centroids[b][0], centroids[b][1])) / 1000.0
                for i, a in enumerate(panel) for b in panel[i + 1:]
            ]
            max_km = max(pairwise_km) if pairwise_km else 0.0
            est_travel_hours = round(max_km / avg_speed_kmh, 2)
            if est_travel_hours > max_travel_hours:
                warnings.append(
                    f"Cycle {cycle_num} panel {panel}: estimated max internal travel "
                    f"{est_travel_hours}h exceeds max_panel_travel_hours={max_travel_hours}h "
                    f"(straight-line distance / {avg_speed_kmh} km/h — a declared "
                    "approximation, not real road routing; treat as a flag for "
                    "manual logistics review, not a hard verdict).")
            # position_assignments is always computed here, for every
            # panel composition — a panel with exactly n_devices EMUs
            # (one device each, no bonus needed) or more EMUs than
            # devices both need real positions just as much as the
            # "leftover devices" bonus case does.
            position_pools_sc = load_position_pools(project_dir)
            panel_sizes = {e: centroids[e][2] for e in panel}
            bonus_alloc = allocate_devices_largest_remainder(panel_sizes, n_devices)
            # allocate_devices_largest_remainder distributes by EMU AREA,
            # which can give an EMU more devices than its own real,
            # spacing-verified pool actually contains — the shortfall is
            # redistributed here to another EMU in the SAME panel with
            # real spare pool capacity, iteratively, until every device
            # is used or every EMU's real pool in the panel is genuinely
            # exhausted, rather than silently dropped.
            capped_alloc = {e: min(bonus_alloc.get(e, 1), len(position_pools_sc.get(e, [])) or 1)
                           for e in panel}
            shortfall = n_devices - sum(capped_alloc.values())
            while shortfall > 0:
                capacity_left = {e: len(position_pools_sc.get(e, [])) - capped_alloc[e] for e in panel}
                candidates = [e for e in panel if capacity_left[e] > 0]
                if not candidates:
                    break  # every real pool in this panel is genuinely exhausted
                # Give the next device to whichever EMU has the most real
                # spare capacity — spreads the redistribution rather than
                # dumping it all on one EMU.
                best = max(candidates, key=lambda e: capacity_left[e])
                capped_alloc[best] += 1
                shortfall -= 1
            position_assignments = []
            for emu_id in panel:
                n_dev_here = max(1, capped_alloc.get(emu_id, 1))
                pool = position_pools_sc.get(emu_id, [])
                positions = [{"name": p.get("name"), "pool_rank": p.get("pool_rank"),
                             "is_medoid": p.get("is_medoid", False), "wrapped": False}
                            for p in pool[:n_dev_here]]
                position_assignments.append({"emu_id": emu_id, "n_devices": len(positions) or 1,
                                             "positions": positions})
            schedule.append({
                "cycle_number": cycle_num,
                "start_day_offset": start_day,
                "recording_end_day_offset": start_day + cfg["cycle_length_days"],
                "emu_ids": panel,
                "n_devices_used": (sum(a["n_devices"] for a in position_assignments)
                                  if position_assignments else len(panel)),
                "position_assignments": position_assignments,
                "est_max_internal_travel_km": round(max_km, 2),
                "est_max_internal_travel_hours": est_travel_hours,
            })

    non_rotational_streams = [s for s in cfg["streams_active"] if s != "audiomoth" and s != "camera_trap"]
    fixed_events_note = None
    if non_rotational_streams:
        last_cycle_end = schedule[-1]["recording_end_day_offset"] if schedule else 0
        fixed_events_note = {
            "streams": non_rotational_streams,
            "note": (
                "These are one-time composite samples tied to fixed physical "
                "features (waterbodies, soil zones), not rotated across EMUs/"
                "cycles — out of scope for panel scheduling by design (see "
                "module docstring). Scheduled as a single event near the end "
                f"of the project, around day {last_cycle_end}, per the "
                "original project brief's timing (final 1-2 weeks)."
            ),
        }

    report = {
        "project_name": cfg["project_name"],
        "regime": regime,
        "n_emus": n_emus,
        "n_devices": n_devices,
        "device_allocation": (device_allocation if regime == "continuous_proportional"
                              else stratified_result["capacities"] if stratified_result
                              else None),
        "emu_week_assignment": (stratified_result["weeks"] if stratified_result else None),
        "project_duration_weeks": cfg["project_duration_weeks"],
        "achievable_cycles": achievable_cycles,
        "used_duration_extension": used_extension,
        "n_cycles_scheduled": len(schedule),
        "n_emus_covered": n_emus - len(uncovered_emu_ids),
        "uncovered_emu_ids": uncovered_emu_ids,
        "avg_travel_speed_kmh_assumed": avg_speed_kmh,
        "schedule": schedule,
        "fixed_events": fixed_events_note,
        "warnings": warnings,
    }

    out_dir = project_dir / "outputs" / "04_deployment_planning"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "deployment_schedule.json", "w") as f:
        json.dump(report, f, indent=2)

    logger.info("Deployment scheduling complete: %d EMUs -> %d cycles (achievable=%d), "
                "%d warning(s)", n_emus, len(schedule), achievable_cycles, len(warnings))
    return report


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    args = parser.parse_args()
    run_panel_scheduling(args.project_dir)
