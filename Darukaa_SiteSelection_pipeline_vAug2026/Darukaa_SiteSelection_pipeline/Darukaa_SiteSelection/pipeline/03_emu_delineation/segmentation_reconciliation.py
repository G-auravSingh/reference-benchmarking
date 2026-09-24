"""
03_emu_delineation / segmentation_reconciliation.py
======================================================

EMU delineation path for CONTIGUOUS archetypes (conservation/industrial:
Soulforest, Tata Motors) — reconciles GEE SNIC segmentation output with
client-drawn ecological anchors (e.g. Soulforest's Fruit Forest, Wetland)
and 01_ingestion's exclusion zones: run segmentation, then reconcile
against the named zones — a mix of both, not either alone.

A real, structural gap worth flagging directly rather than quietly working
around: the shared GEE script (pipeline/gee/covariates_and_segmentation.js)
computes SEGMENT_ID via `mode()`-reduction OVER EACH CANDIDATE POLYGON'S
FULL FOOTPRINT. That's correct for Tata Motors, which already has a dense
pre-generated grid of small candidate points/cells from an earlier phase —
mode-reducing a small cell gives a meaningful single dominant segment for
that cell. It does NOT work for a site like Soulforest, where 01_ingestion's
only real candidate is the single large "Island" polygon (the client's own
KML has no dense grid) — mode-reducing SEGMENT_ID over the whole Island
polygon collapses potentially several real internal segments down to just
whichever one covers the majority, throwing away exactly the spatial detail
SNIC was run to find.

The correct fix is a dense candidate-grid-generation step for contiguous
sites (small tessellated cells across the unmasked terrestrial matrix,
generated in 01_ingestion or a new 01b step, BEFORE the GEE run) so
SEGMENT_ID is computed per-cell, then this module dissolves cells sharing a
SEGMENT_ID into one EMU. That grid-generation step does not exist yet.
This module is built assuming its output (a "segment-tagged tile" GeoJSON)
as an input contract, and is unit-tested against a synthetic fixture
standing in for that future grid — clearly not Soulforest's real geometry.
Running this against Soulforest's actual current data (below) correctly
falls back to a documented single-candidate case rather than fabricating
sub-structure that isn't really there, and surfaces the real residual-area
gap this creates.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from shapely.geometry import shape, mapping
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
import config_schema  # noqa: E402
import crs              # noqa: E402

logger = logging.getLogger(__name__)


def _load_fc(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)["features"]


def _connected_components(
    tiles: List[Dict[str, Any]], projected_crs: str, touch_epsilon_m: float = 0.5
) -> List[List[Dict[str, Any]]]:
    """Splits a set of tiles into groups of TRUE spatial contiguity — two
    tiles are in the same component only if they actually touch (within a
    tiny floating-point epsilon, not a deliberate gap-bridging tolerance).

    A raw SNIC SEGMENT_ID, as assigned per grid cell by the GEE script's
    mode-reduction, can itself already span multiple disconnected areas of
    the site (two patches with similar spectral signature don't have to be
    adjacent to get the same cluster ID) — this function exists so a merge
    step downstream is never given a segment that's secretly already
    disjoint, upholding the real structural guarantee that every final EMU
    is one connected polygon, not a hoped-for outcome.

    Distance comparisons are computed in the metric (projected) CRS, not
    the raw lat/lon degrees candidate_grid.geojson stores geometry in —
    comparing touch_epsilon_m (metres) against degree-valued coordinates
    would make "adjacency" almost always true (0.5 degrees is roughly
    55km) and let genuinely distant pieces merge.

    Adjacency requires a real shared edge (positive-length boundary
    intersection), not just a touching point: two grid cells touching only
    at a single diagonal corner have real distance() == 0.0, but
    `unary_union` correctly refuses to dissolve a corner-only connection
    into one solid polygon, since a single point of contact isn't a real,
    walkable, physically contiguous connection. Matching this function's
    own adjacency criterion to exactly what `unary_union` will and won't
    dissolve means the two can never disagree.

    Uses a simple union-find over pairwise shared-edge checks. O(n^2) in
    tile count, fine at the few-hundred-cell scale this pipeline currently
    runs at; would need a spatial index (STRtree) well before that becomes
    a real cost."""
    n = len(tiles)
    geoms = [crs.to_m(shape(t["geometry"]), projected_crs) for t in tiles]
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    for i in range(n):
        for j in range(i + 1, n):
            if geoms[i].distance(geoms[j]) <= touch_epsilon_m:
                # A buffered-area fallback here would reintroduce the
                # exact leniency this check exists to remove — buffering
                # both geometries before checking overlap gives a
                # corner-only touch a positive overlap area too. Only a
                # real, un-buffered positive-length edge intersection
                # counts as adjacency.
                if geoms[i].intersection(geoms[j]).length > 0:
                    union(i, j)

    components: Dict[int, List[Dict[str, Any]]] = {}
    for i in range(n):
        components.setdefault(find(i), []).append(tiles[i])
    return list(components.values())


def _decompose_into_contiguous_pieces(
    by_segment: Dict[Any, List[Dict[str, Any]]], projected_crs: str,
    zone_attribute: Optional[str] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Runs _connected_components on EVERY raw segment BEFORE any MMU
    merging — a raw SEGMENT_ID that's already spatially disjoint gets split
    into its real contiguous pieces first, so the merge step (which now
    only merges truly-touching neighbours, see below) always starts from
    genuinely contiguous inputs and can never accumulate a disjoint result
    by construction.

    When `zone_attribute` is given (a real, client-provided ecological
    zonation — see Tata Motors Pimpri), a raw SNIC segment is first split
    by that attribute's value BEFORE
    connectivity is even checked — GEE's SNIC segmentation runs on the raw
    pixel matrix with no knowledge of any real, client-drawn zone boundary,
    so two spatially-touching cells with the same spectral cluster ID can
    legitimately sit in two different REAL zones (e.g. Deccan forest vs.
    Narmada valley). Splitting by zone first means the resulting EMUs can
    never straddle a real, ground-truthed zone boundary — the same
    architectural role `hard_barrier_attribute` already plays for
    agroforestry's district-based partitioning in ecological_clustering.py,
    now available for the segmentation-based archetype too."""
    pieces: Dict[str, List[Dict[str, Any]]] = {}
    for seg_id, tiles in by_segment.items():
        if zone_attribute:
            by_zone: Dict[Any, List[Dict[str, Any]]] = {}
            for t in tiles:
                zone_val = t["properties"].get(zone_attribute)
                by_zone.setdefault(zone_val, []).append(t)
        else:
            by_zone = {None: tiles}
        for zone_val, zone_tiles in by_zone.items():
            components = _connected_components(zone_tiles, projected_crs)
            zone_suffix = f"_{zone_val}" if zone_attribute else ""
            for i, comp in enumerate(components):
                key = f"{seg_id}{zone_suffix}_{i}" if len(components) > 1 else f"{seg_id}{zone_suffix}"
                pieces[key] = comp
    return pieces


def _merge_small_segments(
    by_segment: Dict[Any, List[Dict[str, Any]]], min_mapping_unit: int,
    projected_crs: str, touch_epsilon_m: float = 0.5,
    zone_attribute: Optional[str] = None,
) -> Dict[Any, List[Dict[str, Any]]]:
    """One pass of standard GEOBIA minimum-mapping-unit merging: any segment
    with fewer than min_mapping_unit member tiles gets folded into its
    nearest TRULY-ADJACENT neighbour, repeated until nothing is below
    threshold, no valid adjacent merge remains, or only one segment is left.

    Adjacency uses the same strict, correct-units criterion as
    _connected_components (see that function's docstring: a real shared
    edge, in the metric CRS, not a touching corner). If a small segment
    has NO truly-adjacent neighbour
    (real shared edge, not just a touching corner), it's left as-is rather
    than force-merged into something far away purely to hit a target
    count — a real isolated micro-patch is a real ecological fact, not
    something to paper over for a rounder number.

    Zone-aware merging: `_decompose_into_contiguous_pieces` already
    guarantees every group passed in here is
    zone-pure, but two tiny pieces from DIFFERENT real zones can still be
    genuinely touching at the zone boundary itself — a purely geometric
    adjacency check would happily merge them, silently erasing a real,
    client-drawn ecological distinction at exactly the place it matters
    most. When `zone_attribute` is given, a candidate merge target must
    also share the same zone value."""
    groups = {k: list(v) for k, v in by_segment.items()}
    dissolved_cache: Dict[Any, Any] = {
        k: unary_union([crs.to_m(shape(t["geometry"]), projected_crs) for t in v])
        for k, v in groups.items()
    }
    zone_of: Dict[Any, Any] = {}
    if zone_attribute:
        for k, v in groups.items():
            zone_of[k] = v[0]["properties"].get(zone_attribute)  # zone-pure by construction

    changed = True
    while changed and len(groups) > 1:
        changed = False
        small = sorted([k for k, v in groups.items() if len(v) < min_mapping_unit],
                       key=lambda k: len(groups[k]))
        for target_key in small:
            if target_key not in groups:
                continue  # already absorbed by an earlier merge this pass
            target_geom = dissolved_cache[target_key]
            adjacent = {k: v for k, v in groups.items()
                       if k != target_key and dissolved_cache[k].distance(target_geom) <= touch_epsilon_m
                       and dissolved_cache[k].intersection(target_geom).length > 0
                       and (not zone_attribute or zone_of[k] == zone_of[target_key])}
            if not adjacent:
                continue  # no valid merge target — leave it, see docstring
            nearest_key = min(adjacent, key=lambda k: dissolved_cache[k].distance(target_geom))
            groups[nearest_key] = groups[nearest_key] + groups.pop(target_key)
            dissolved_cache[nearest_key] = unary_union(
                [crs.to_m(shape(t["geometry"]), projected_crs) for t in groups[nearest_key]])
            del dissolved_cache[target_key]
            if zone_attribute:
                del zone_of[target_key]
            changed = True
    return groups


def auto_tune_mmu(
    by_segment: Dict[Any, List[Dict[str, Any]]], target_n_segments: int,
    projected_crs: str, max_search: int = 60, zone_attribute: Optional[str] = None,
) -> Dict[str, Any]:
    """Searches minimum_mapping_unit = 1, 2, 3, ... merging at each step,
    stopping at the first value whose resulting segment count is <=
    target_n_segments (mirrors the Pimpri precedent's search direction and
    stopping rule exactly). Returns the merged groups AND the tuning
    diagnostics — never just the final answer with no trace of how it
    was reached, since that's exactly the kind of unexplainable number
    that erodes trust in a site-selection deliverable.

    `zone_attribute`, when given, is passed straight through to
    `_merge_small_segments` as defense-in-depth — reconcile() already
    calls this function once per real zone with pre-filtered, zone-pure
    input when zone-partitioning is active, so this check is normally
    redundant, but a caller that passes mixed-zone input by mistake still
    can't silently merge across a real zone boundary."""
    trace = []
    for mmu in range(1, max_search + 1):
        merged = _merge_small_segments(by_segment, mmu, projected_crs, zone_attribute=zone_attribute)
        trace.append({"min_mapping_unit": mmu, "n_segments": len(merged)})
        if len(merged) <= target_n_segments:
            return {"merged_groups": merged, "min_mapping_unit_used": mmu,
                    "search_trace": trace, "converged": True}
    # Search exhausted without reaching target — return the best (smallest
    # count) attempt rather than silently the raw unmerged segmentation.
    best = min(trace, key=lambda t: t["n_segments"])
    merged = _merge_small_segments(by_segment, best["min_mapping_unit"], projected_crs,
                                   zone_attribute=zone_attribute)
    return {"merged_groups": merged, "min_mapping_unit_used": best["min_mapping_unit"],
            "search_trace": trace, "converged": False}


def _reconcile_zone_as_emu(
    segment_tagged_tiles: List[Dict[str, Any]], anchors: List[Dict[str, Any]],
    aoi_boundary_area_ha: float, exclusion_area_ha: float,
    projected_crs: str, zone_attribute: str,
) -> Dict[str, Any]:
    """Real zone = EMU, directly — every tile whose zone_attribute has a
    real value is grouped by that value alone and dissolved into one EMU,
    with no segmentation-driven sub-clustering at all. A real zone may
    legitimately end up as several physically disconnected pieces (the
    same as any agroforestry EMU spanning scattered parcels) — that's
    real ecological/geographic fact, not something this function tries to
    force into one connected shape.

    Anchors, if any are declared for this project, still get their own
    dedicated EMU as usual, on top of the zone-based ones."""
    emus = []
    for anchor in anchors:
        emus.append({
            "emu_id": f"EMU_ANCHOR_{anchor['properties'].get('name', 'anchor')}",
            "emu_type": "ecological_anchor",
            "geometry": anchor["geometry"],
            "member_tiles": [], "member_tile_names": [],
        })

    by_zone: Dict[Any, List[Dict[str, Any]]] = {}
    for t in segment_tagged_tiles:
        zone_val = t["properties"].get(zone_attribute)
        if zone_val is not None:
            by_zone.setdefault(zone_val, []).append(t)

    for zone_val, tiles in sorted(by_zone.items()):
        safe_zone_name = re.sub(r"[^A-Za-z0-9]+", "_", str(zone_val)).strip("_") or "unknown"
        dissolved = unary_union([crs.to_m(shape(t["geometry"]), projected_crs) for t in tiles])
        emus.append({
            "emu_id": f"EMU_{safe_zone_name}",
            "emu_type": "zone",
            "geometry": mapping(crs.to_ll(dissolved, projected_crs)),
            "member_tiles": tiles,
            "member_tile_names": [t["properties"]["name"] for t in tiles],
        })

    covered_ha = 0.0
    for emu in emus:
        covered_ha += crs.to_m(shape(emu["geometry"]), projected_crs).area / 10_000.0
    residual_ha = round(aoi_boundary_area_ha - exclusion_area_ha - covered_ha, 3)

    return {
        "emus": emus,
        "n_emus": len(emus),
        "n_anchor_emus": len(anchors),
        "n_segmentation_emus": len(by_zone),
        "mmu_diagnostics": None,
        "orphan_segments_merged_into_anchors": [],
        "aoi_boundary_area_ha": round(aoi_boundary_area_ha, 3),
        "exclusion_area_ha": round(exclusion_area_ha, 3),
        "covered_by_emus_ha": round(covered_ha, 3),
        "residual_unclassified_ha": residual_ha,
        "warnings": [],
    }


def reconcile(
    segment_tagged_tiles: List[Dict[str, Any]],
    anchors: List[Dict[str, Any]],
    aoi_boundary_area_ha: float,
    exclusion_area_ha: float,
    projected_crs: str,
    target_n_segments: Optional[int] = None,
    emu_min_tiles: int = 3,
    zone_attribute: Optional[str] = None,
    zone_is_emu: bool = False,
) -> Dict[str, Any]:
    """Core reconciliation logic, kept pure/testable (no file I/O) so it
    can be exercised against a synthetic fixture independent of any one
    project's real (currently insufficient) input data.

    segment_tagged_tiles: features with properties.SEGMENT_ID and a real
        polygon geometry — the dense-grid contract described above.
    anchors: ecological_anchor features from 01_ingestion — each becomes
        its own fixed EMU, never merged into a segmentation group.
    target_n_segments: if given, runs auto_tune_mmu() to merge small raw
        SNIC segments down to at most this many final segments before
        building EMUs. Standard GEOBIA practice is to merge segments below
        a minimum mapping unit — without this, SNIC's raw, unmerged output
        can produce far more EMUs than any realistic device/logistics
        budget could cover; see auto_tune_mmu()'s docstring for the exact
        search precedent this follows.
    zone_is_emu: when True, skips SNIC-segment-based sub-clustering
        entirely — each real value of zone_attribute becomes exactly one
        EMU directly, dissolving all its member tiles regardless of raw
        SEGMENT_ID or geometric adjacency. This is the same "one EMU can
        span many real, physically disconnected parcels" model
        agroforestry already uses for districts, applied here to a real,
        client-given zone instead — segmentation-driven sub-division
        within such a zone can otherwise produce ecologically meaningless
        micro-fragments.
    """
    if zone_is_emu and zone_attribute:
        return _reconcile_zone_as_emu(
            segment_tagged_tiles, anchors, aoi_boundary_area_ha, exclusion_area_ha,
            projected_crs, zone_attribute)

    emus = []
    mmu_diagnostics = None

    # candidate_grid.py tessellates anchor areas too, so any tile whose
    # centroid falls inside an anchor is claimed directly by that anchor
    # here — BEFORE segmentation grouping runs — giving the anchor real
    # member tiles for rollup and real candidate points for the field map,
    # while it still stays exactly one EMU (never split; client ecological
    # identity wins per the architecture decision).
    anchor_geoms = [(a, shape(a["geometry"])) for a in anchors]
    claimed_tile_ids = set()
    anchor_member_tiles: Dict[str, List[Dict[str, Any]]] = {a["properties"]["name"]: [] for a in anchors}
    for tile in segment_tagged_tiles:
        # A tile that failed the built-up/water hard filter in
        # 02_covariates is excluded from EMU membership entirely, same as
        # a masked SEGMENT_ID=-1 cell — it's not a real candidate,
        # regardless of which EMU's boundary it happens to sit inside.
        if not tile["properties"].get("hard_filter_pass", True):
            continue
        centroid = shape(tile["geometry"]).centroid
        for anchor, anchor_geom in anchor_geoms:
            if anchor_geom.contains(centroid):
                anchor_member_tiles[anchor["properties"]["name"]].append(tile)
                claimed_tile_ids.add(id(tile))
                break

    for anchor in anchors:
        name = anchor["properties"]["name"]
        member_tiles = anchor_member_tiles[name] or [anchor]  # fall back to
        # the anchor's own boundary feature if literally no tessellated
        # tile fell inside it (e.g. grid cell size larger than the anchor)
        emus.append({
            "emu_id": f"EMU_ANCHOR_{name.replace(' ', '_')}",
            "emu_type": "ecological_anchor",
            "geometry": anchor["geometry"],
            "member_tile_names": [t["properties"]["name"] for t in member_tiles],
            "member_tiles": member_tiles,
        })

    by_segment: Dict[Any, List[Dict[str, Any]]] = {}
    for tile in segment_tagged_tiles:
        if id(tile) in claimed_tile_ids:
            continue  # already claimed by an anchor above — never double-counted
        if not tile["properties"].get("hard_filter_pass", True):
            continue  # same fix as above — a built-up/water candidate is
            # never a real segment member, regardless of its SEGMENT_ID
        seg_id = tile["properties"].get("SEGMENT_ID")
        if seg_id is None or seg_id == -1:
            continue  # -1 = fell on masked water/built-up ground, not a real segment
        by_segment.setdefault(seg_id, []).append(tile)

    # hard_barrier_attribute defaults to "attr_admin_district" globally
    # (config_schema.py, for agroforestry) — a conservation-archetype
    # project that never overrides it would resolve every tile's
    # zone_val to None if this weren't checked, which would leak a
    # spurious "_None" suffix into every segment key and downstream EMU
    # naming. Only treated as zone-partitioned if the attribute has a
    # REAL, non-null value on at least one tile.
    zone_active = bool(zone_attribute) and any(
        t["properties"].get(zone_attribute) is not None
        for tiles in by_segment.values() for t in tiles)
    effective_zone_attribute = zone_attribute if zone_active else None

    # A raw SEGMENT_ID can already span disconnected patches (see
    # _connected_components' docstring). Decomposing into true connected
    # components FIRST means every input
    # to the merge step below is genuinely one contiguous piece, so the
    # merge (which now only merges truly-touching neighbours) can never
    # accumulate a disjoint result.
    n_raw_segments = len(by_segment)
    by_segment = _decompose_into_contiguous_pieces(by_segment, projected_crs, effective_zone_attribute)
    n_contiguous_pieces = len(by_segment)

    if target_n_segments is not None and len(by_segment) > target_n_segments:
        remaining_target = max(1, target_n_segments - len(anchors))
        if zone_active:
            # MMU auto-tune runs INDEPENDENTLY per real zone, each
            # targeting a share of the remaining device budget
            # proportional to its own real (post-exclusion-clipping) area,
            # with a floor of 1 — every real, client-drawn zone is
            # guaranteed at least one EMU, rather than a purely global
            # search that could merge a whole small zone down to nothing
            # while a large one keeps many pieces.
            by_zone_groups: Dict[Any, Dict[Any, List[Dict[str, Any]]]] = {}
            for key, tiles in by_segment.items():
                zone_val = tiles[0]["properties"].get(zone_attribute)
                by_zone_groups.setdefault(zone_val, {})[key] = tiles
            zone_areas = {
                zone_val: sum(crs.to_m(shape(t["geometry"]), projected_crs).area
                             for tiles in groups.values() for t in tiles)
                for zone_val, groups in by_zone_groups.items()
            }
            total_area = sum(zone_areas.values()) or 1.0
            merged_groups: Dict[Any, List[Dict[str, Any]]] = {}
            per_zone_diagnostics = {}
            for zone_val, groups in by_zone_groups.items():
                zone_target = max(1, round(remaining_target * zone_areas[zone_val] / total_area))
                if len(groups) > zone_target:
                    tuning = auto_tune_mmu(groups, zone_target, projected_crs, zone_attribute=zone_attribute)
                    merged_groups.update(tuning["merged_groups"])
                    per_zone_diagnostics[str(zone_val)] = {
                        "target": zone_target, "min_mapping_unit_used": tuning["min_mapping_unit_used"],
                        "n_final": len(tuning["merged_groups"]), "converged": tuning["converged"]}
                else:
                    merged_groups.update(groups)
                    per_zone_diagnostics[str(zone_val)] = {
                        "target": zone_target, "min_mapping_unit_used": None,
                        "n_final": len(groups), "converged": True}
            by_segment = merged_groups
            mmu_diagnostics = {
                "n_raw_segments": n_raw_segments,
                "n_contiguous_pieces_after_split": n_contiguous_pieces,
                "zone_attribute": zone_attribute,
                "per_zone": per_zone_diagnostics,
                # Aggregate fields, kept at the top level in the same shape
                # as the non-zone-partitioned case below, so every caller
                # works identically regardless of which path produced this
                # dict — "converged" is True only if every zone's own
                # search converged; "min_mapping_unit_used" and
                # "search_trace" don't have one global value when each
                # zone tunes independently, so they point to per_zone
                # instead of a single number that would misrepresent it.
                "converged": all(z["converged"] for z in per_zone_diagnostics.values()),
                # Kept type-consistent with the non-zone-partitioned case
                # below (None / empty list, not a descriptive string) so
                # every existing consumer of this dict keeps working
                # without a special case — the real per-zone detail is in
                # per_zone above for anything that wants it.
                "min_mapping_unit_used": None,
                "search_trace": [],
                "converged": all(z["converged"] for z in per_zone_diagnostics.values()),
            }
        else:
            tuning = auto_tune_mmu(by_segment, remaining_target, projected_crs)
            by_segment = tuning["merged_groups"]
            mmu_diagnostics = {
                "n_raw_segments": n_raw_segments,
                "n_contiguous_pieces_after_split": n_contiguous_pieces,
                "min_mapping_unit_used": tuning["min_mapping_unit_used"],
                "converged": tuning["converged"],
                "search_trace": tuning["search_trace"],
            }

    # SAFETY ASSERTION, not a soft warning: every final group must be a
    # single connected polygon. If this ever fires, the strict-adjacency
    # merge logic above has a bug — better to fail loudly here than ship a
    # disjoint "EMU" silently a second time.
    for seg_id, tiles in by_segment.items():
        u = unary_union([shape(t["geometry"]) for t in tiles])
        n_parts = len(list(u.geoms)) if u.geom_type == "MultiPolygon" else 1
        if n_parts > 1:
            raise RuntimeError(
                f"Contiguity check failed for segment {seg_id}: {n_parts} disjoint "
                "parts after merging. This should be structurally impossible with "
                "strict-adjacency merging — investigate _merge_small_segments before "
                "trusting this run's EMU set.")

    # A segment that survives MMU merging as tiny (below emu_min_tiles)
    # AND genuinely touches an anchor's boundary is very likely a
    # segmentation edge artifact — a sliver sitting in the spectral
    # transition zone between two real, larger ecological units — not a
    # genuinely distinct micro-habitat worth its own EMU and device-week.
    # _merge_small_segments only ever considers merging into OTHER
    # SEGMENTS, never into an adjacent ANCHOR (anchors are resolved
    # earlier, via centroid-containment, and are never revisited as a
    # possible merge target for a leftover tiny segment touching them
    # from outside), so this is handled separately here: any remaining
    # segment below emu_min_tiles that touches an anchor is folded into
    # whichever anchor it shares the LONGEST real boundary with — a more
    # geometrically meaningful tie-break than raw point-adjacency when a
    # tiny segment touches two anchors nearly equally.
    orphans_merged_into_anchors = []
    touch_epsilon_m = 0.5
    for seg_id in list(by_segment.keys()):
        tiles = by_segment[seg_id]
        if len(tiles) >= emu_min_tiles:
            continue
        # Distances/lengths here must be computed in the metric CRS, not
        # raw lat/lon degrees — the same real-units precaution used
        # everywhere else in this module (0.5 degrees is roughly 55km, so
        # an un-reprojected touch_epsilon_m=0.5 would mean nothing).
        seg_geom = crs.to_m(unary_union([shape(t["geometry"]) for t in tiles]), projected_crs)
        best_anchor, best_shared_len = None, 0.0
        for anchor_emu in emus:
            if anchor_emu["emu_type"] != "ecological_anchor":
                continue
            anchor_geom = crs.to_m(shape(anchor_emu["geometry"]), projected_crs)
            if seg_geom.distance(anchor_geom) > touch_epsilon_m:
                continue
            shared_len = seg_geom.boundary.intersection(anchor_geom.buffer(touch_epsilon_m)).length
            if shared_len > best_shared_len:
                best_anchor, best_shared_len = anchor_emu, shared_len
        if best_anchor is not None:
            best_anchor["member_tiles"] = best_anchor["member_tiles"] + tiles
            best_anchor["member_tile_names"] = best_anchor["member_tile_names"] + [
                t["properties"]["name"] for t in tiles]
            # Dissolve the anchor's displayed boundary to actually include
            # the newly-absorbed tile — without this, the EMU's polygon on
            # the map wouldn't match its true membership (a merged tile
            # would sit geometrically outside the boundary claiming it).
            # seg_geom is metric (see the reprojection fix above) — union
            # in metric space, then convert back to lat/lon for storage,
            # matching every other geometry stored in this module's output.
            merged_geom_m = unary_union([crs.to_m(shape(best_anchor["geometry"]), projected_crs), seg_geom])
            best_anchor["geometry"] = mapping(crs.to_ll(merged_geom_m, projected_crs))
            orphans_merged_into_anchors.append(
                {"segment_id": str(seg_id), "n_tiles": len(tiles),
                 "merged_into": best_anchor["emu_id"], "shared_boundary_m": round(best_shared_len, 1)})
            del by_segment[seg_id]

    for seg_id, tiles in by_segment.items():
        geoms = [shape(t["geometry"]) for t in tiles]
        dissolved = unary_union(geoms)  # segmentation members ARE spatially
        # contiguous by construction (SNIC groups adjacent pixels) — unlike
        # the scattered-agroforestry case, dissolving here does not create
        # the "fill the gap between unrelated farms" problem the ChatGPT
        # transcript warned about, because there is no gap: these cells
        # really do share a border.
        emus.append({
            "emu_id": None,  # assigned below, after sorting by size — see note
            "_raw_segment_id": seg_id,
            "emu_type": "segmentation_derived",
            "geometry": mapping(dissolved),
            "member_tile_names": [t["properties"]["name"] for t in tiles],
            # Keeping the full tile features (not just member names) lets
            # run_segmentation_reconciliation() write a per-TILE output
            # (candidates_with_emu.geojson) alongside the dissolved
            # per-EMU one, so 05_metrics_rollup can compute a real
            # distribution across member cells instead of a meaningless
            # median-of-one-dissolved-polygon.
            "member_tiles": tiles,
        })

    # Raw SNIC cluster IDs are arbitrary signed integers (e.g.
    # "EMU_SEG_-1825272994.0") — not meaningful in a client-facing report
    # or map. Renamed to the Pimpri methodology's own convention (SEG01,
    # SEG02, ...), assigned by descending size so SEG01 is always the
    # largest segment — a stable, sensible ordering rather than an
    # arbitrary one tied to SNIC's internal cluster numbering.
    seg_emus = [e for e in emus if e["emu_type"] == "segmentation_derived"]
    seg_emus.sort(key=lambda e: len(e["member_tiles"]), reverse=True)
    for i, e in enumerate(seg_emus, start=1):
        e["emu_id"] = f"SEG{i:02d}"
        del e["_raw_segment_id"]

    covered_ha = 0.0
    for emu in emus:
        covered_ha += crs.to_m(shape(emu["geometry"]), projected_crs).area / 10_000.0
    residual_ha = round(aoi_boundary_area_ha - exclusion_area_ha - covered_ha, 3)

    return {
        "emus": emus,
        "n_emus": len(emus),
        "n_anchor_emus": len(anchors),
        "n_segmentation_emus": len(by_segment),
        "mmu_diagnostics": mmu_diagnostics,
        "orphan_segments_merged_into_anchors": orphans_merged_into_anchors,
        "aoi_boundary_area_ha": round(aoi_boundary_area_ha, 3),
        "exclusion_area_ha": round(exclusion_area_ha, 3),
        "covered_by_emus_ha": round(covered_ha, 3),
        "residual_unclassified_ha": residual_ha,
    }


def run_segmentation_reconciliation(project_dir: str | Path) -> Dict[str, Any]:
    project_dir = Path(project_dir)
    cfg = config_schema.load_config(project_dir / "config.yaml")
    if cfg["archetype"] not in ("conservation", "industrial"):
        raise ValueError(
            f"segmentation_reconciliation is for contiguous archetypes; "
            f"{cfg['project_name']} is archetype={cfg['archetype']!r} — use "
            f"ecological_clustering.py instead.")

    ing_dir = project_dir / "outputs" / "01_ingestion"
    cov_dir = project_dir / "outputs" / "02_covariates"

    anchors = _load_fc(ing_dir / "ecological_anchors.geojson")
    exclusions = _load_fc(ing_dir / "exclusion_zones.geojson")
    aoi = _load_fc(ing_dir / "aoi_boundary.geojson")
    tiles = _load_fc(cov_dir / "candidates_with_covariates.geojson")  # has SEGMENT_ID, if GEE has run

    projected_crs = crs.resolve(shape(aoi[0]["geometry"])) if aoi else "EPSG:4326"
    aoi_area_ha = (crs.to_m(shape(aoi[0]["geometry"]), projected_crs).area / 10_000.0) if aoi else 0.0
    # Only HARD exclusions are subtracted here — soft-exclusion area is now
    # tessellated into the grid (see candidate_grid.py's fix) and gets
    # filtered per-cell by the real BuiltUp_Pct hard-filter in
    # 02_covariates instead of being blanket-removed at the polygon level.
    # Counting it here too would double-subtract area that's legitimately
    # back in candidate space.
    exclusion_area_ha = sum(
        crs.to_m(shape(e["geometry"]), projected_crs).area / 10_000.0
        for e in exclusions if e["properties"].get("role") == "exclusion_hard")

    has_segment_ids = any(t["properties"].get("SEGMENT_ID") is not None for t in tiles)
    n_candidate_tiles = len(tiles) if tiles else len(_load_fc(ing_dir / "candidates.geojson"))

    warnings = []
    if not tiles:
        warnings.append(
            "No 02_covariates output yet — GEE hasn't been run for this project. "
            "Reconciliation proceeds with anchors only; segmentation-derived "
            "EMUs cannot exist until then.")
    elif not has_segment_ids:
        warnings.append("candidates_with_covariates.geojson has no SEGMENT_ID values.")
    elif n_candidate_tiles <= 2:
        warnings.append(
            f"Only {n_candidate_tiles} candidate tile(s) exist for this site — "
            "SEGMENT_ID would be mode-reduced over the whole tile footprint, "
            "collapsing any real internal sub-structure SNIC found. A dense "
            "candidate-grid-generation step (see module docstring) is needed "
            "before this project's segmentation output is meaningful. "
            "Proceeding with anchors only; treat any segmentation EMU below "
            "as provisional at best.")

    result = reconcile(
        segment_tagged_tiles=tiles if (has_segment_ids and n_candidate_tiles > 2) else [],
        anchors=anchors,
        aoi_boundary_area_ha=aoi_area_ha,
        exclusion_area_ha=exclusion_area_ha,
        projected_crs=projected_crs,
        # Target = device count, matching the Pimpri methodology's own
        # documented precedent (70 raw segments -> auto-tuned MMU -> 10
        # final segments, exactly matching TM's 10 devices). Without this,
        # SNIC's raw, unmerged output was used directly — confirmed
        # directly from a client report: 40 raw segments for a 27ha site
        # against 7 devices, producing a schedule no real field team could
        # execute.
        target_n_segments=cfg["n_devices"],
        emu_min_tiles=cfg["emu_min_tiles"],
        zone_attribute=cfg.get("hard_barrier_attribute"),
        zone_is_emu=cfg.get("zone_is_emu", False),
    )
    result["project_name"] = cfg["project_name"]
    result["method"] = "segmentation_reconciliation"
    result["warnings"] = warnings
    if result.get("orphan_segments_merged_into_anchors"):
        for m in result["orphan_segments_merged_into_anchors"]:
            result["warnings"].append(
                f"Segment {m['segment_id']} ({m['n_tiles']} tile(s)) was too small to stand "
                f"as its own EMU and genuinely touches {m['merged_into']} "
                f"({m['shared_boundary_m']}m shared boundary) — merged into it rather than "
                "kept as a spurious standalone EMU. Real ecological identity preserved: "
                "this is a transition-zone sliver, not a fabricated exclusion.")

    if result["mmu_diagnostics"] and not result["mmu_diagnostics"]["converged"]:
        mmu_used = result["mmu_diagnostics"]["min_mapping_unit_used"]
        mmu_note = (f"min_mapping_unit={mmu_used}" if isinstance(mmu_used, int)
                   else "a per-zone min_mapping_unit (see mmu_diagnostics.per_zone for each zone's value)")
        result["warnings"].append(
            f"MMU auto-tune search (1..60) could not bring segment count down to the "
            f"device-count target — used {mmu_note} as the best available, "
            f"still {result['n_segmentation_emus']} segments. See mmu_diagnostics.search_trace "
            "for the full curve; likely means real ecological heterogeneity that a bigger "
            "merge value can't responsibly paper over — worth a manual look.")

    if result["residual_unclassified_ha"] > 0.1 * max(aoi_area_ha, 0.1):
        result["warnings"].append(
            f"{result['residual_unclassified_ha']} ha "
            f"({round(100*result['residual_unclassified_ha']/aoi_area_ha, 1) if aoi_area_ha else '?'}%"
            f" of AOI) is not covered by any anchor, exclusion, or EMU — "
            "this is real leftover land, not dropped silently; needs either "
            "the candidate-grid fix above or manual review before reporting.")

    out_dir = project_dir / "outputs" / "03_emu_delineation"
    out_dir.mkdir(parents=True, exist_ok=True)

    # emus.geojson: one dissolved feature per EMU, for the map/report table.
    # member_tiles is dropped from properties here — it's the full feature
    # dicts (with geometry), not something that belongs in a properties
    # dict, and it's written separately below where it's actually used.
    fc = {"type": "FeatureCollection",
          "features": [{"type": "Feature", "geometry": e["geometry"],
                        "properties": {k: v for k, v in e.items()
                                       if k not in ("geometry", "member_tiles")}}
                       for e in result["emus"]]}
    with open(out_dir / "emus.geojson", "w") as f:
        json.dump(fc, f)

    # candidates_with_emu.geojson: one feature per MEMBER TILE, tagged with
    # its emu_id, carrying whatever covariate properties 02_covariates
    # attached — this is what 05_metrics_rollup needs for a real
    # distribution (median/IQR across member cells), matching the
    # agroforestry path's output shape so rollup can use one code path for
    # both archetypes instead of a contiguous-only special case that
    # (incorrectly) assumed one feature = one EMU with no sub-structure.
    per_tile_features = []
    for e in result["emus"]:
        for tile in e["member_tiles"]:
            feat = dict(tile)
            feat["properties"] = {**tile["properties"], "emu_id": e["emu_id"], "emu_type": e["emu_type"]}
            per_tile_features.append(feat)
    with open(out_dir / "candidates_with_emu.geojson", "w") as f:
        json.dump({"type": "FeatureCollection", "features": per_tile_features}, f)

    with open(out_dir / "emu_delineation_report.json", "w") as f:
        json.dump({k: v for k, v in result.items() if k != "emus"}, f, indent=2)

    logger.info("Segmentation reconciliation [%s]: %d anchor EMUs, %d segmentation EMUs, "
                "%.1f ha residual unclassified", cfg["project_name"],
                result["n_anchor_emus"], result["n_segmentation_emus"],
                result["residual_unclassified_ha"])
    return result


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    args = parser.parse_args()
    run_segmentation_reconciliation(args.project_dir)
