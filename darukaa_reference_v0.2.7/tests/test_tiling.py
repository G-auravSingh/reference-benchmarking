"""Tiling / allocation / adaptive-split logic (pure Python). Every expectation is derived by hand."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from darukaa_reference import tiling as T


def test_tile_grid_edges_are_on_the_cell_grid_and_cover_the_bounds():
    cell = 630.0
    tiles = T.tile_grid((500123.0, 2000456.0, 560000.0, 2050000.0), 30870.0, cell)
    assert all(abs(t[0] / cell - round(t[0] / cell)) < 1e-9 and abs(t[1] / cell - round(t[1] / cell)) < 1e-9 for t in tiles)
    assert min(t[0] for t in tiles) <= 500123.0 and max(t[2] for t in tiles) >= 560000.0
    assert min(t[1] for t in tiles) <= 2000456.0 and max(t[3] for t in tiles) >= 2050000.0
    xs = sorted({t[0] for t in tiles}); assert all(abs((b - a) - 30870.0) < 1e-6 for a, b in zip(xs, xs[1:]))


def test_tile_side_is_a_whole_number_of_cells_of_about_the_requested_native_pixels():
    assert T.tile_side_m(3072, 10.0, 630.0) == pytest.approx(630.0 * round(30720 / 630))             # 49 cells
    assert T.tile_side_m(3072, 10.0, 70.0) == pytest.approx(70.0 * round(30720 / 70))
    assert T.tile_side_m(3072, 463.83, 463.83) == pytest.approx(463.83 * 3072)                       # 1-px cells
    assert T.tile_side_m(10, 100.0, 5000.0) == 5000.0                                                # never below one cell


def test_tiles_for_circle_are_only_those_intersecting_it_nearest_first():
    tiles = T.tiles_for_circle(0.0, 0.0, 50000.0, 30000.0, 100.0)
    assert all(T.circle_intersects(t, 0, 0, 50000.0) for t in tiles)
    d = [((t[0] + t[2]) / 2) ** 2 + ((t[1] + t[3]) / 2) ** 2 for t in tiles]
    assert d == sorted(d)
    assert 0 < len(tiles) < len(T.tile_grid((-50000, -50000, 50000, 50000), 30000.0, 100.0)) + 1
    assert not T.circle_intersects((60000, 60000, 70000, 70000), 0, 0, 50000.0)


def test_split_tile_stays_on_the_cell_grid_and_partitions_the_tile():
    tile = (0.0, 0.0, 630.0 * 7, 630.0 * 5)
    subs = T.split_tile(tile, 630.0)
    assert len(subs) == 4 and sum(T.n_cells(s, 630.0) for s in subs) == 35
    assert all(abs(s[0] / 630 - round(s[0] / 630)) < 1e-9 for s in subs)
    assert T.split_tile((0, 0, 630, 630), 630.0) == [(0, 0, 630, 630)]                              # one cell: cannot split
    assert len(T.split_tile((0, 0, 630 * 3, 630), 630.0)) == 2


def test_allocation_is_proportional_deterministic_and_capped():
    counts = {(0, 0, 1, 1): 6000, (1, 0, 2, 1): 3000, (2, 0, 3, 1): 1000, (3, 0, 4, 1): 0}
    a = T.allocate(counts, 500)
    assert sum(a.values()) == 500 and a[(0, 0, 1, 1)] == 300 and a[(1, 0, 2, 1)] == 150 and a[(2, 0, 3, 1)] == 50 and a[(3, 0, 4, 1)] == 0
    assert T.allocate(counts, 500) == a                                                              # deterministic
    small = T.allocate({(0, 0, 1, 1): 10, (1, 0, 2, 1): 5}, 500)
    assert small == {(0, 0, 1, 1): 10, (1, 0, 2, 1): 5}                                              # population <= n: take every cell
    odd = T.allocate({(0, 0, 1, 1): 1, (1, 0, 2, 1): 1, (2, 0, 3, 1): 1}, 2)
    assert sum(odd.values()) == 2 and max(odd.values()) == 1                                         # largest-remainder, capped by count
    capped = T.allocate({(0, 0, 1, 1): 3, (1, 0, 2, 1): 1000}, 500)
    assert capped[(0, 0, 1, 1)] <= 3 and sum(capped.values()) == 500


def test_allocation_gives_every_cell_the_same_inclusion_probability():
    counts = {(i, 0, i + 1, 1): c for i, c in enumerate([7000, 2500, 400, 100])}
    n = 1000
    a = T.allocate(counts, n)
    for t, c in counts.items():
        assert abs(a[t] / c - n / sum(counts.values())) < 1.0 / c + 1e-9                             # inclusion probability = n / N


@pytest.mark.parametrize("msg, expected", [("User memory limit exceeded.", True),
                                            ("Image.stratifiedSample: Reprojection output too large (10017x10017 pixels).", True),
                                            ("Computation timed out.", True), ("Image.reduceResolution: Bad maxPixels arg.", False),
                                            ("Collection.reduceColumns: no such band", False)])
def test_only_size_related_errors_are_retryable(msg, expected):
    assert T.is_retryable(RuntimeError(msg)) is expected


def test_count_adaptive_splits_only_where_needed_and_never_loses_or_duplicates_cells():
    cell = 100.0
    big = (0.0, 0.0, 6400.0, 6400.0)                                        # 64 x 64 cells
    calls = []

    def count(t):
        calls.append(t)
        if T.n_cells(t, cell) > 1024:                                        # the "server" cannot do more than 32 x 32 cells
            raise RuntimeError("User memory limit exceeded.")
        return T.n_cells(t, cell) // 2                                       # half of every tile eligible
    stats = {}
    leaves = T.count_adaptive(big, count, cell, stats)
    assert stats["splits"] == 1 and len(leaves) == 4                         # one split into four 32x32 tiles
    assert sum(c for _, c in leaves) == 64 * 64 // 2
    assert all(T.n_cells(t, cell) == 1024 for t, _ in leaves)
    assert sum(T.n_cells(t, cell) for t, _ in leaves) == 64 * 64             # exact partition


def test_a_non_retryable_error_is_not_swallowed():
    def bad(t):
        raise RuntimeError("Image.reduceResolution: Bad maxPixels arg.")
    with pytest.raises(RuntimeError, match="Bad maxPixels"):
        T.count_adaptive((0, 0, 1000, 1000), bad, 100.0)
    with pytest.raises(RuntimeError):
        T.count_adaptive((0, 0, 100, 100), lambda t: (_ for _ in ()).throw(RuntimeError("User memory limit exceeded.")), 100.0)   # one cell: give up


def test_sample_adaptive_reallocates_after_a_split_and_returns_exactly_m():
    cell = 100.0
    tile = (0.0, 0.0, 6400.0, 6400.0)
    rng = np.random.default_rng(0)

    def count(t):
        return T.n_cells(t, cell)

    def sample(t, m):
        if T.n_cells(t, cell) > 1024:
            raise RuntimeError("Image.stratifiedSample: Reprojection output too large (10017x10017 pixels).")
        return [(t[0], t[1], i) for i in range(m)]
    stats = {}
    out = T.sample_adaptive(tile, 400, sample, count, cell, stats)
    assert len(out) == 400 and stats["splits"] == 1
    per_tile = {}
    for x, y, _ in out:
        per_tile[(x, y)] = per_tile.get((x, y), 0) + 1
    assert sorted(per_tile.values()) == [100, 100, 100, 100]                 # equal counts -> equal shares
    assert T.sample_adaptive(tile, 0, sample, count, cell) == []


def test_interior_and_ownership_predicates():
    region = (0.0, 0.0, 700.0, 700.0)
    assert T.is_interior((100, 100, 300, 300), region, 20.0)
    assert not T.is_interior((10, 100, 300, 300), region, 20.0)              # reaches the edge margin
    assert not T.is_interior((100, 100, 300, 690), region, 20.0)
    core = (0.0, 0.0, 500.0, 500.0)
    assert T.owns(0.0, 0.0, core) and T.owns(499.9, 499.9, core) and not T.owns(500.0, 100.0, core) and not T.owns(-0.1, 100.0, core)
    other = (500.0, 0.0, 1000.0, 500.0)
    assert sum(T.owns(x, 250.0, c) for x in (250.0, 500.0, 750.0) for c in (core, other)) == 3     # every centroid owned exactly once
