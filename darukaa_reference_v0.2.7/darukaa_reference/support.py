"""
support.py -- comparison-unit ("support-matching") framework  (v0.2.8, Phase 2)
===============================================================================

WHY THIS EXISTS
---------------
A site value is computed over a UNIT (a polygon, a water body, a riparian ring) while the
v0.2.7 reference was a distribution of SINGLE PIXELS. For a binary image the site is a
proportion (e.g. 81.6 % natural) but the reference median can only be 0 or 100; for a
continuous image the pixel spread is wider than the spread of site-sized means; for a
rate, averaging per-pixel "rates" is not the rate of the aggregate. (Audit defect X1.)

This module makes the reference unit equal to the site unit:

  SiteSupport              matched ReferenceSupport          built by
  -----------------------  --------------------------------  -------------------------------
  polygon_proportion       site_window_proportion            window_mean  (binary input)
  polygon_mean             site_window_mean                  window_mean  (continuous input)
  polygon_rate             site_window_rate                  window_rate  (num/den SUMS)
  water_body_unit          water_body_unit                   label_units + unit_values
  riparian_ring_unit       riparian_ring_unit                ring_masks + unit_values

A "site window" is a circular window whose AREA equals the site area. Window statistics
are computed at the dataset's NATIVE resolution (never on a coarsened image); only the
comparison unit changes. For area proportions and area-weighted rates this aggregation is
exact, not an approximation.

NO PSEUDO-REPLICATION
---------------------
Windows are sampled on a grid whose spacing is >= max(native pixel, window diameter), so
sampled windows do not overlap and no coarse pixel is counted more than once. Coarse
products whose pixel exceeds the window are sampled at their own native spacing.

TWO LAYERS
----------
1. numpy layer (this file, top): the exact, executable DEFINITION of each operation. The
   synthetic tests in tests/test_support_framework.py check it against known answers.
2. Earth Engine layer (this file, bottom): builds the same operations as EE graphs.
   STATUS: structure-tested offline only. Two EE behaviours it relies on are NOT yet
   verified live and must be confirmed in the Phase 5 terrestrial run (see
   SCORING_ARCHITECTURE_v0.2.8.md, "Unverified EE assumptions").
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy import ndimage

# ----------------------------------------------------------------------------------------
# Support vocabulary (shared with indicator_contract.py)
# ----------------------------------------------------------------------------------------
SITE_SUPPORTS = (
    "polygon_proportion",   # fraction of the site polygon in a class (binary/categorical input)
    "polygon_mean",         # mean of a continuous variable over the site polygon
    "polygon_rate",         # numerator area / denominator area / years over the polygon
    "water_body_unit",      # metric over the site's water body, on its own (pure) water mask
    "riparian_ring_unit",   # metric over a fixed-width ring around the site's water body
    "polygon_scalar",       # geometry-derived scalar (e.g. overlap %, shoreline index): no pixel reference
    "not_computed",
)
MATCHED_REFERENCE_SUPPORT = {
    "polygon_proportion": "site_window_proportion",
    "polygon_mean": "site_window_mean",
    "polygon_rate": "site_window_rate",
    "water_body_unit": "water_body_unit",
    "riparian_ring_unit": "riparian_ring_unit",
    "polygon_scalar": "none",
    "not_computed": "none",
}


# ----------------------------------------------------------------------------------------
# Geometry helpers
# ----------------------------------------------------------------------------------------
def site_window_radius_m(site_area_m2: float) -> float:
    """Radius of the circle whose area equals the site area."""
    if site_area_m2 <= 0:
        raise ValueError("site area must be positive")
    return math.sqrt(site_area_m2 / math.pi)


def window_radius_px(site_area_m2: float, native_scale_m: float) -> float:
    return site_window_radius_m(site_area_m2) / float(native_scale_m)


def sampling_spacing_m(native_scale_m: float, site_area_m2: float) -> float:
    """Grid spacing that guarantees non-overlapping windows and never samples a native
    pixel twice: max(native pixel, window diameter)."""
    return max(float(native_scale_m), 2.0 * site_window_radius_m(site_area_m2))


def native_pixels_in_site(site_area_m2: float, native_scale_m: float) -> float:
    return site_area_m2 / (float(native_scale_m) ** 2)


def site_support_ok(site_area_m2: float, native_scale_m: float, min_native_pixels: Optional[int]) -> bool:
    """Site-support rule (audit X6). None means the rule does not apply (e.g. pressures)."""
    if min_native_pixels is None:
        return True
    return native_pixels_in_site(site_area_m2, native_scale_m) >= min_native_pixels


# ----------------------------------------------------------------------------------------
# numpy layer: window statistics
# ----------------------------------------------------------------------------------------
def disk_kernel(radius_px: float) -> np.ndarray:
    r = max(radius_px, 0.5)
    n = int(math.ceil(r))
    yy, xx = np.mgrid[-n:n + 1, -n:n + 1]
    return ((xx ** 2 + yy ** 2) <= r ** 2 + 1e-9).astype(float)


def _window_sum(a: np.ndarray, k: np.ndarray) -> np.ndarray:
    """Sum of `a` over the kernel footprint; zero outside the array (windows reaching past
    the edge lose coverage, handled by the callers). Small kernels: exact direct
    convolution. Large kernels: FFT convolution, cleaned of round-off near zero."""
    if k.shape[0] <= 51:
        return ndimage.convolve(a, k, mode="constant", cval=0.0)
    from scipy.signal import fftconvolve
    out = fftconvolve(a, k, mode="same")
    out[np.abs(out) < 1e-9] = 0.0
    return out


def window_mean(values: np.ndarray, valid: Optional[np.ndarray], radius_px: float,
                min_coverage: float = 0.9) -> np.ndarray:
    """Mean of `values` over each site-sized window, using only valid pixels.

    Windows whose valid coverage is < min_coverage of the kernel are set to NaN, so every
    reference window represents (almost) a full site-sized area. Binary input gives a
    window PROPORTION; continuous input gives a window MEAN."""
    values = np.asarray(values, dtype=float)
    valid = np.isfinite(values) if valid is None else (np.asarray(valid, bool) & np.isfinite(values))
    k = disk_kernel(radius_px)
    num = _window_sum(np.where(valid, values, 0.0), k)
    cnt = _window_sum(valid.astype(float), k)
    cover = cnt / k.sum()
    with np.errstate(invalid="ignore", divide="ignore"):
        out = num / cnt
    out[(cnt == 0) | (cover < min_coverage)] = np.nan
    return out


def window_rate(numerator: np.ndarray, denominator: np.ndarray, radius_px: float, years: float,
                pixel_area_m2: float = 1.0, min_denominator_area_m2: float = 0.0,
                min_coverage: float = 0.9, valid: Optional[np.ndarray] = None) -> np.ndarray:
    """Rate over each site-sized window = SUM(numerator area) / SUM(denominator area) * 100 / years.

    This is the rate of the aggregate, NOT the mean of per-pixel rates (they differ whenever
    the denominator varies across the window). Windows whose denominator area is below
    `min_denominator_area_m2` are NaN (e.g. the 5 ha forest-baseline floor)."""
    if years <= 0:
        raise ValueError("years must be positive")
    numerator = np.asarray(numerator, float)
    denominator = np.asarray(denominator, float)
    valid = np.ones_like(numerator, bool) if valid is None else np.asarray(valid, bool)
    k = disk_kernel(radius_px)
    num = _window_sum(np.where(valid, numerator, 0.0), k) * pixel_area_m2
    den = _window_sum(np.where(valid, denominator, 0.0), k) * pixel_area_m2
    cover = _window_sum(valid.astype(float), k) / k.sum()
    with np.errstate(invalid="ignore", divide="ignore"):
        out = num / den * 100.0 / years
    out[(den <= 0) | (den < min_denominator_area_m2) | (cover < min_coverage)] = np.nan
    return out


def polygon_rate(numerator: np.ndarray, denominator: np.ndarray, polygon: np.ndarray, years: float,
                 pixel_area_m2: float = 1.0, min_denominator_area_m2: float = 0.0) -> Optional[float]:
    """The SITE-side rate, computed by exactly the same aggregate rule as window_rate."""
    p = np.asarray(polygon, bool)
    den = float(np.sum(np.asarray(denominator, float)[p])) * pixel_area_m2
    if den <= 0 or den < min_denominator_area_m2:
        return None
    num = float(np.sum(np.asarray(numerator, float)[p])) * pixel_area_m2
    return num / den * 100.0 / years


def grid_sample(image: np.ndarray, spacing_px: int, offset: Tuple[int, int] = (0, 0)) -> np.ndarray:
    """Values on a regular grid (non-overlapping windows); NaNs dropped."""
    s = max(int(spacing_px), 1)
    v = np.asarray(image, float)[offset[0]::s, offset[1]::s].ravel()
    return v[np.isfinite(v)]


# ----------------------------------------------------------------------------------------
# numpy layer: water-body and riparian-ring units
# ----------------------------------------------------------------------------------------
def pure_water(water: np.ndarray, erode_px: int = 1) -> np.ndarray:
    """Remove mixed shoreline pixels by eroding the water mask `erode_px` pixels."""
    w = np.asarray(water, bool)
    if erode_px <= 0:
        return w
    return ndimage.binary_erosion(w, structure=np.ones((3, 3), bool), iterations=erode_px)


@dataclass
class WaterUnits:
    labels: np.ndarray          # 0 = not water, 1..n = water-body id
    areas_m2: Dict[int, float]  # id -> area (full water extent, before erosion)


def label_units(water: np.ndarray, pixel_area_m2: float = 1.0, min_area_m2: float = 0.0,
                eight_connected: bool = False) -> WaterUnits:
    """Identify water bodies as connected components of the water mask."""
    struct = np.ones((3, 3), bool) if eight_connected else None
    lab, n = ndimage.label(np.asarray(water, bool), structure=struct)
    areas = {}
    for i in range(1, n + 1):
        a = float(np.sum(lab == i)) * pixel_area_m2
        if a >= min_area_m2:
            areas[i] = a
        else:
            lab[lab == i] = 0
    return WaterUnits(lab, areas)


def match_units(units: WaterUnits, target_area_m2: float, size_factor: float = 3.0,
                permanence: Optional[np.ndarray] = None, target_permanence: Optional[float] = None,
                permanence_tolerance: float = 0.25, exclude_ids: Sequence[int] = ()) -> List[int]:
    """Reference water bodies comparable to the site: area within [target/f, target*f] and,
    if a permanence image is given, mean permanence within +/- tolerance of the site's."""
    out = []
    for i, a in units.areas_m2.items():
        if i in exclude_ids:
            continue
        if not (target_area_m2 / size_factor <= a <= target_area_m2 * size_factor):
            continue
        if permanence is not None and target_permanence is not None:
            p = float(np.nanmean(np.asarray(permanence, float)[units.labels == i]))
            if abs(p - target_permanence) > permanence_tolerance:
                continue
        out.append(i)
    return sorted(out)


def ring_masks(units: WaterUnits, width_px: int, all_water: Optional[np.ndarray] = None) -> Dict[int, np.ndarray]:
    """Riparian ring of each water body: dilation by `width_px` minus the body itself and
    minus any other water (a ring is land/vegetation, never water)."""
    water = (units.labels > 0) if all_water is None else np.asarray(all_water, bool)
    rings = {}
    for i in units.areas_m2:
        body = units.labels == i
        grown = ndimage.binary_dilation(body, structure=np.ones((3, 3), bool), iterations=int(width_px))
        rings[i] = grown & ~body & ~water
    return rings


def unit_values(values: np.ndarray, masks: Dict[int, np.ndarray], min_pixels: int = 1,
                reducer: str = "mean") -> Dict[int, float]:
    """One value per unit, computed ONLY over that unit's own mask."""
    v = np.asarray(values, float)
    out = {}
    for i, m in masks.items():
        x = v[m & np.isfinite(v)]
        if x.size < min_pixels:
            continue
        out[i] = float(np.mean(x) if reducer == "mean" else np.median(x))
    return out


def unit_masks(units: WaterUnits, pure: bool = True, erode_px: int = 1) -> Dict[int, np.ndarray]:
    """Per-unit masks; with pure=True each body is eroded to remove mixed shoreline pixels."""
    out = {}
    for i in units.areas_m2:
        body = units.labels == i
        out[i] = pure_water(body, erode_px) if pure else body
    return out


# ----------------------------------------------------------------------------------------
# Earth Engine layer  (same semantics; structure-tested offline, NOT yet verified live)
# ----------------------------------------------------------------------------------------
def ee_native_projection(ee, native_scale_m: float, crs: str = "EPSG:4326"):
    """Explicit native projection. Composites (e.g. a median of an ImageCollection) have a
    default 1-degree projection, so their native grid must be imposed explicitly."""
    return ee.Projection(crs).atScale(native_scale_m)


def ee_window_image(ee, image, native_scale_m: float, site_area_m2: float,
                    min_coverage: float = 0.9, crs: str = "EPSG:4326"):
    """Site-window mean/proportion of `image` (band 0), computed at the native scale.

    UNVERIFIED EE ASSUMPTION A1: .reproject(native) forces the focal sums to be computed on
    the native grid even when the result is later sampled at a coarser spacing."""
    r = site_window_radius_m(site_area_m2)
    v = image.select(0)
    valid = v.mask().gt(0)
    k = ee.Kernel.circle(radius=r, units="meters", normalize=False)
    num = v.unmask(0).multiply(valid).reduceNeighborhood(reducer=ee.Reducer.sum(), kernel=k)
    cnt = valid.reduceNeighborhood(reducer=ee.Reducer.sum(), kernel=k)
    full = ee.Image.constant(1).reduceNeighborhood(reducer=ee.Reducer.sum(), kernel=k)
    out = num.divide(cnt).updateMask(cnt.divide(full).gte(min_coverage))
    return out.rename("window_value").reproject(ee_native_projection(ee, native_scale_m, crs))


def ee_window_rate_image(ee, numerator_bin, denominator_bin, native_scale_m: float,
                         site_area_m2: float, years: float, min_denominator_area_m2: float = 0.0,
                         crs: str = "EPSG:4326"):
    """Site-window rate = sum(numerator area) / sum(denominator area) * 100 / years."""
    r = site_window_radius_m(site_area_m2)
    k = ee.Kernel.circle(radius=r, units="meters", normalize=False)
    pa = ee.Image.pixelArea()
    num = pa.multiply(numerator_bin.unmask(0)).reduceNeighborhood(reducer=ee.Reducer.sum(), kernel=k)
    den = pa.multiply(denominator_bin.unmask(0)).reduceNeighborhood(reducer=ee.Reducer.sum(), kernel=k)
    rate = num.divide(den).multiply(100.0 / years)
    rate = rate.updateMask(den.gt(0).And(den.gte(min_denominator_area_m2)))
    return rate.rename("window_rate").reproject(ee_native_projection(ee, native_scale_m, crs))


def ee_sample_windows(ee, window_image, region, native_scale_m: float, site_area_m2: float,
                      n: int, seed: int, tile_scale: int = 4):
    """Sample non-overlapping windows: points on a grid of spacing max(native, window diameter).

    UNVERIFIED EE ASSUMPTION A2: sampling a reprojected (fixed-projection) image at a coarser
    `scale` point-samples it (nearest neighbour) rather than re-aggregating it."""
    spacing = sampling_spacing_m(native_scale_m, site_area_m2)
    v = window_image.select(0).rename("v")
    img = v.unmask(0).addBands(v.mask().rename("valid").toInt())
    fc = img.stratifiedSample(numPoints=0, classBand="valid", region=region, scale=spacing, seed=seed,
                              classValues=[1], classPoints=[n], dropNulls=True,
                              tileScale=tile_scale, geometries=False)
    return fc.filter(ee.Filter.eq("valid", 1)).aggregate_array("v")


def ee_water_body_units(ee, water_mask, region, native_scale_m: float, min_area_m2: float,
                        max_units: int = 5000):
    """Water bodies as vectors (connected components of the water mask), with area."""
    vec = water_mask.selfMask().rename("w").reduceToVectors(
        geometry=region, scale=native_scale_m, geometryType="polygon", eightConnected=False,
        maxPixels=1e10, bestEffort=True)
    vec = vec.map(lambda f: f.set("area_m2", f.geometry().area(1)))
    return vec.filter(ee.Filter.gte("area_m2", min_area_m2)).limit(max_units)


def ee_match_units(ee, units, target_area_m2: float, size_factor: float = 3.0):
    return units.filter(ee.Filter.rangeContains("area_m2", target_area_m2 / size_factor,
                                                target_area_m2 * size_factor))


def ee_ring(ee, feature, width_m: float, error_m: float = 1.0):
    """Riparian ring of one water body (the caller also masks out any other water)."""
    g = feature.geometry()
    return ee.Feature(g.buffer(width_m, error_m).difference(g, error_m)).copyProperties(feature)


def ee_unit_values(ee, units, value_image, native_scale_m: float, extra_mask=None, tile_scale: int = 4):
    """One mean value per unit, over that unit's own geometry (and optional pure-water mask)."""
    img = value_image.select(0).rename("v")
    if extra_mask is not None:
        img = img.updateMask(extra_mask)
    return img.reduceRegions(collection=units, reducer=ee.Reducer.mean(),
                             scale=native_scale_m, tileScale=tile_scale)
