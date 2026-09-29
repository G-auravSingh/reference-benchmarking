"""
tiling.py -- bounded-memory tiling logic (v0.2.8 smoke-test fixes)
=================================================================

Pure Python, no Earth Engine. Why it exists: the first live smoke test showed that asking Earth Engine for
one reference over a 100 km bounding box fails ("User memory limit exceeded", "Reprojection output too large
(10017x10017 pixels)"). The fix is NOT a coarser resolution: every request is confined to a tile of bounded
NATIVE pixel count, aligned to the site-sized cell grid, and the tiles are combined client-side.

  tile_grid / tiles_for_circle   tiles aligned to multiples of the cell size (a cell never straddles a tile)
  allocate                       proportional (self-weighting) allocation of the sample across tiles
  is_interior / owns             water-body edge and ownership predicates (shared with the numpy definition)
  is_retryable                   which Earth Engine errors mean "make the tile smaller"
  count_adaptive / sample_adaptive   split a tile in four and retry on a retryable error
"""
from __future__ import annotations

import math
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

Tile = Tuple[float, float, float, float]          # (x0, y0, x1, y1) in CRS metres

RETRYABLE_FRAGMENTS = ("memory limit", "too large", "timed out", "timeout", "computation time", "too many pixels",
                       "exceeded", "out of memory")


def is_retryable(exc: BaseException) -> bool:
    """True for Earth Engine errors that a smaller tile can fix (memory, reprojection size, timeouts)."""
    msg = str(exc).lower()
    return any(f in msg for f in RETRYABLE_FRAGMENTS)


def _snap_down(v: float, m: float) -> float:
    return math.floor(v / m + 1e-9) * m


def _snap_up(v: float, m: float) -> float:
    return math.ceil(v / m - 1e-9) * m


def tile_side_m(tile_native_px: int, native_scale_m: float, cell_m: float) -> float:
    """Tile side: about `tile_native_px` native pixels, rounded to a whole number of cells (at least one)."""
    return max(cell_m, round(tile_native_px * native_scale_m / cell_m) * cell_m)


def tile_grid(bounds: Tile, tile_m: float, cell_m: float) -> List[Tile]:
    """Tiles covering `bounds`, edges at multiples of the cell size from the CRS origin (so every cell belongs to
    exactly one tile and no cell is cut)."""
    tile_m = max(cell_m, round(tile_m / cell_m) * cell_m)
    x0, y0, x1, y1 = bounds
    xs = [_snap_down(x0, tile_m) + i * tile_m for i in range(int(math.ceil((x1 - _snap_down(x0, tile_m)) / tile_m - 1e-9)))]
    ys = [_snap_down(y0, tile_m) + j * tile_m for j in range(int(math.ceil((y1 - _snap_down(y0, tile_m)) / tile_m - 1e-9)))]
    return [(x, y, x + tile_m, y + tile_m) for y in ys for x in xs]


def circle_intersects(tile: Tile, cx: float, cy: float, r: float) -> bool:
    nx = min(max(cx, tile[0]), tile[2]); ny = min(max(cy, tile[1]), tile[3])
    return (nx - cx) ** 2 + (ny - cy) ** 2 <= r * r


def tiles_for_circle(cx: float, cy: float, r: float, tile_m: float, cell_m: float) -> List[Tile]:
    """Tiles that intersect the circle, ordered by distance from its centre (nearest first)."""
    tiles = [t for t in tile_grid((cx - r, cy - r, cx + r, cy + r), tile_m, cell_m) if circle_intersects(t, cx, cy, r)]
    return sorted(tiles, key=lambda t: ((t[0] + t[2]) / 2 - cx) ** 2 + ((t[1] + t[3]) / 2 - cy) ** 2)


def split_tile(tile: Tile, cell_m: float) -> List[Tile]:
    """Split into (up to) four sub-tiles whose edges stay on the cell grid. A tile of one cell cannot be split."""
    x0, y0, x1, y1 = tile
    nx, ny = int(round((x1 - x0) / cell_m)), int(round((y1 - y0) / cell_m))
    if nx <= 1 and ny <= 1:
        return [tile]
    mx = x0 + max(1, nx // 2) * cell_m if nx > 1 else x1
    my = y0 + max(1, ny // 2) * cell_m if ny > 1 else y1
    xs = [(x0, mx), (mx, x1)] if nx > 1 else [(x0, x1)]
    ys = [(y0, my), (my, y1)] if ny > 1 else [(y0, y1)]
    return [(a, c, b, d) for (c, d) in ys for (a, b) in xs]


def n_cells(tile: Tile, cell_m: float) -> int:
    return int(round((tile[2] - tile[0]) / cell_m)) * int(round((tile[3] - tile[1]) / cell_m))


def allocate(counts: Dict[Tile, int], n_target: int) -> Dict[Tile, int]:
    """Proportional allocation of `n_target` draws over tiles (largest-remainder, deterministic, capped by the tile's
    own count). Each eligible cell then has the SAME inclusion probability n / N: a self-weighting simple random
    sample, so no weights are needed downstream. If the whole population is <= n_target every cell is taken."""
    total = sum(max(0, c) for c in counts.values())
    if total <= n_target:
        return {t: max(0, c) for t, c in counts.items()}
    quota = {t: n_target * max(0, c) / total for t, c in counts.items()}
    base = {t: min(int(math.floor(q)), counts[t]) for t, q in quota.items()}
    left = n_target - sum(base.values())
    order = sorted(counts, key=lambda t: (-(quota[t] - math.floor(quota[t])), t))
    for t in order:
        if left <= 0:
            break
        if base[t] < counts[t]:
            base[t] += 1
            left -= 1
    return base


# ----------------------------------------------------------------------------------------
# Adaptive split-and-retry (memory safety without changing the resolution)
# ----------------------------------------------------------------------------------------
def count_adaptive(tile: Tile, count_fn: Callable[[Tile], int], cell_m: float, stats: Optional[Dict] = None) -> List[Tuple[Tile, int]]:
    """[(leaf tile, eligible cell count)]. On a retryable error the tile is split in four and retried."""
    stats = stats if stats is not None else {}
    try:
        return [(tile, int(count_fn(tile)))]
    except Exception as e:
        subs = split_tile(tile, cell_m)
        if not is_retryable(e) or len(subs) == 1:
            raise
        stats["splits"] = stats.get("splits", 0) + 1
        stats.setdefault("split_errors", []).append(str(e)[:120])
        out: List[Tuple[Tile, int]] = []
        for s in subs:
            out += count_adaptive(s, count_fn, cell_m, stats)
        return out


def sample_adaptive(tile: Tile, m: int, sample_fn: Callable[[Tile, int], List[float]], count_fn: Callable[[Tile], int],
                    cell_m: float, stats: Optional[Dict] = None) -> List[float]:
    """Draw m cells from `tile`; on a retryable error split the tile, re-allocate m over the sub-tiles by their counts."""
    stats = stats if stats is not None else {}
    if m <= 0:
        return []
    try:
        return list(sample_fn(tile, m))
    except Exception as e:
        subs = split_tile(tile, cell_m)
        if not is_retryable(e) or len(subs) == 1:
            raise
        stats["splits"] = stats.get("splits", 0) + 1
        stats.setdefault("split_errors", []).append(str(e)[:120])
        leaves: List[Tuple[Tile, int]] = []
        for s in subs:
            leaves += count_adaptive(s, count_fn, cell_m, stats)
        alloc = allocate({t: c for t, c in leaves}, m)
        out: List[float] = []
        for t, _c in leaves:
            out += sample_adaptive(t, alloc.get(t, 0), sample_fn, count_fn, cell_m, stats)
        return out


# ----------------------------------------------------------------------------------------
# Water-body edge and ownership predicates (used identically by the numpy definition and the EE builder)
# ----------------------------------------------------------------------------------------
def is_interior(bbox: Tile, region: Tile, margin: float) -> bool:
    """True if the body's bounding box lies inside the region shrunk by `margin` on every side. A body that reaches
    the margin may have been clipped by the region (area, pure-water erosion or ring truncated), so it is not used."""
    return bool(bbox[0] >= region[0] + margin and bbox[1] >= region[1] + margin
                and bbox[2] <= region[2] - margin and bbox[3] <= region[3] - margin)


def owns(cx: float, cy: float, core: Tile) -> bool:
    """Half-open ownership: a body belongs to the tile whose core contains its centroid, so tiles never double count."""
    return core[0] <= cx < core[2] and core[1] <= cy < core[3]
