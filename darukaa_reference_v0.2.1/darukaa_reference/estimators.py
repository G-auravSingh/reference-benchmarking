"""
Reference Estimators
====================

Responsive, scale-aware estimators for benchmarking a site value against a
reference condition. This module replaces the legacy capped intactness ratio
``min(site / reference, 1.0)`` (see ReferenceSelector._intactness_ratio, now
deprecated) which had two disqualifying properties for a monitoring baseline:

    1. It censored all above-reference performance (the 1.0 cap), so a restoring
       site could not register improvement — violating the core requirement that
       a State-of-Nature metric be "responsive to both increases AND decreases"
       (Nature Positive Initiative, SoN metric criteria, 2026).
    2. It applied a ratio to indicators whose measurement scale does not support
       ratios (NDVI in [-1, 1], temperature in degrees, z-score indices), where a
       ratio is not meaningful.

Design
------
Each indicator declares a ``measurement_scale`` and a ``reference_estimator`` in
its IndicatorSpec. The estimator is chosen to match the scale:

    - ratio-scale, strictly-positive, true-zero  -> log response ratio (LRR)
    - interval / bounded / index / z-score        -> robust standardised deviation
                                                     + percentile-in-reference

All estimators are UNCAPPED and signed so that improvement above the reference is
preserved. Direction (higher_is_better) orients the sign so that, for every
indicator, a positive oriented value = better-than-reference.

These functions are pure (numpy only, no Earth Engine) and unit-tested.

References
----------
- Hedges, Gurevitch & Curtis (1999). The meta-analysis of response ratios in
  experimental ecology. Ecology 80(4):1150-1156.  (log response ratio)
- SEED biocomplexity framework (McElderry et al., 2024) — reference-condition
  benchmarking (this module realigns the estimator to a distance/deviation logic
  consistent with SEED's kernel, rather than a capped ratio).
"""
from __future__ import annotations

import math
from typing import Dict, Optional, Sequence

import numpy as np

# Estimator identifiers
LRR = "log_response_ratio"
ROBUST_Z = "robust_z"
RATIO_LEGACY = "capped_ratio_legacy"

# Measurement scales an indicator may declare
SCALE_RATIO = "ratio"          # strictly positive, true zero (cover %, density, counts)
SCALE_INTERVAL = "interval"    # temperature, NDVI, indices, z-scores (no true zero)
SCALE_BOUNDED = "bounded"      # values on a fixed [a, b] interval / index in [0, 1]


def choose_estimator(measurement_scale: Optional[str],
                     declared: Optional[str] = None) -> str:
    """Pick an estimator from the declared value, else from the measurement scale.

    An explicit ``declared`` estimator on the IndicatorSpec always wins. Otherwise
    ratio-scale -> LRR; everything else -> robust_z.
    """
    if declared in (LRR, ROBUST_Z):
        return declared
    if measurement_scale == SCALE_RATIO:
        return LRR
    # interval, bounded, index, z-score, or unknown -> robust deviation
    return ROBUST_Z


def log_response_ratio(site_value: float, reference_value: float,
                       higher_is_better: bool = True) -> Optional[float]:
    """Signed, uncapped log response ratio: ln(site / reference).

    Oriented so that a POSITIVE value always means better-than-reference:
      - higher_is_better: ln(site / ref)      (more state = better)
      - lower_is_better : ln(ref / site)      (less pressure = better)

    Returns None when undefined (non-positive inputs).
    """
    if site_value is None or reference_value is None:
        return None
    if site_value <= 0 or reference_value <= 0:
        # LRR is only defined for strictly positive ratio-scale quantities.
        return None
    lrr = math.log(site_value / reference_value)
    return lrr if higher_is_better else -lrr


def robust_z(site_value: float, ref_median: float, ref_mad: float,
             higher_is_better: bool = True) -> Optional[float]:
    """Signed, uncapped robust standardised deviation from the reference.

    z = (site - ref_median) / (1.4826 * MAD), oriented so positive = better.
    The 1.4826 factor scales MAD to a normal-consistent standard-deviation
    estimate. Returns None if dispersion is zero/undefined.
    """
    if site_value is None or ref_median is None or ref_mad is None:
        return None
    scaled = 1.4826 * ref_mad
    if scaled <= 0:
        return None
    z = (site_value - ref_median) / scaled
    return z if higher_is_better else -z


def percentile_in_reference(site_value: float,
                            reference_values: Sequence[float],
                            higher_is_better: bool = True) -> Optional[float]:
    """Percentile (0-100) of the site value within the reference distribution.

    Scale-free and directly interpretable ("this site sits at the Nth percentile
    of contemporary least-disturbed comparable land"). Oriented so that 100 =
    best relative to reference.
    """
    if site_value is None or reference_values is None:
        return None
    arr = np.asarray([v for v in reference_values if v is not None], dtype=float)
    if arr.size == 0:
        return None
    pct = 100.0 * float(np.mean(arr <= site_value))
    return pct if higher_is_better else 100.0 - pct


def display_pct_of_reference(site_value: float, reference_value: float,
                             higher_is_better: bool = True) -> Optional[float]:
    """UNCAPPED 'percent of reference' for DISPLAY ONLY (never for arithmetic).

    Unlike the legacy intactness ratio this is not capped at 100, so a site at
    120% of reference reads as 120% (improvement is visible). Provided purely so
    reports can show an intuitive number alongside the signed estimator.
    """
    if site_value is None or reference_value is None or reference_value == 0:
        return None
    if higher_is_better:
        return 100.0 * site_value / reference_value
    if site_value == 0:
        return None
    return 100.0 * reference_value / site_value


def benchmark(site_value: Optional[float],
              reference_median: Optional[float],
              reference_mad: Optional[float] = None,
              reference_values: Optional[Sequence[float]] = None,
              measurement_scale: Optional[str] = None,
              reference_estimator: Optional[str] = None,
              higher_is_better: bool = True) -> Dict[str, Optional[float]]:
    """Compute the responsive benchmark for one indicator at one site.

    Returns a dict with the estimator used, the signed value (uncapped), an
    optional percentile, and a display-only percent-of-reference. The signed
    value is what downstream scoring should consume; the percent is display only.
    """
    estimator = choose_estimator(measurement_scale, reference_estimator)
    out: Dict[str, Optional[float]] = {
        "estimator": estimator,
        "value": None,               # signed, uncapped: >0 better than reference
        "percentile_in_reference": None,
        "display_pct_of_reference": display_pct_of_reference(
            site_value, reference_median, higher_is_better),
        "responsive": True,          # by construction (no cap)
    }

    if estimator == LRR:
        out["value"] = log_response_ratio(site_value, reference_median, higher_is_better)
    else:  # ROBUST_Z
        out["value"] = robust_z(site_value, reference_median, reference_mad, higher_is_better)

    if reference_values is not None:
        out["percentile_in_reference"] = percentile_in_reference(
            site_value, reference_values, higher_is_better)

    return out


# ============================================================================
# OD-4 — SEED multivariate kernel (CORRECTED v0.2.0, post peer-review-parity audit)
# ============================================================================
# SEED (McElderry et al. 2024), Eq. 1, is a genuine multivariate GAUSSIAN kernel using
# the MAHALANOBIS distance to the reference-sample mean:
#
#     K(x, x_r) = exp[ -delta * (x - x_r)^T  C_r^-1  (x - x_r) ]         in (0, 1]
#
# where C_r is the COVARIANCE of the reference sample. A prior build in this repo
# approximated this with a weighted MANHATTAN (L1) distance and independent per-indicator
# weights — that was not the SEED formula (no covariance term, wrong norm) and has been
# removed. This is the correction.
#
# Two modes, both real special cases of Eq. 1:
#   "diagonal" — C_r^-1 = diag(1/var_i): indicators within a construct treated as
#     uncorrelated. The numerically stable default: reference samples are typically
#     small (~12-30 pixels, OD-3), and a full covariance estimated from that few points
#     is unstable or singular. This mode needs only each indicator's own reference
#     variance — already available wherever the per-indicator z-score is computed.
#   "full" — the full reference covariance (with shrinkage regularisation toward the
#     diagonal, since small-sample covariance estimates are themselves unstable) from
#     co-located, multi-band-sampled reference pixels. Closer to Eq. 1 as written;
#     requires enough reference pixels to invert reliably (see min_n threshold).
#
# This remains an OPTIONAL, whole-construct SIMILARITY-TO-REFERENCE view. It complements
# — never replaces — the per-indicator responsive benchmarks used for scoring.

def mahalanobis_kernel_diagonal(deviations_std, delta: float = 0.5) -> Optional[float]:
    """Diagonal-covariance Mahalanobis kernel: K = exp[-delta * sum(z_i^2)].

    deviations_std : iterable of standardised deviations from the reference mean
                      (e.g. robust_z values; a value already divided by its own
                      reference SD, i.e. C_r^-1 = diag(1/var) applied).
    delta           : SEED's scaling parameter (see fit_delta_diagonal for calibration).
    Returns similarity in (0, 1], or None if no data.
    """
    z = np.asarray([x for x in deviations_std if x is not None], dtype=float)
    if z.size == 0:
        return None
    quad_form = float(np.sum(z ** 2))   # (x-x_r)^T diag(1/var) (x-x_r), std units
    return float(np.exp(-delta * quad_form))


def shrinkage_covariance(X: np.ndarray, shrinkage: float = 0.2) -> np.ndarray:
    """Reference-sample covariance, regularised by shrinking toward a scaled identity.

    X : (n_pixels, n_indicators) array of co-located reference pixel values.
    shrinkage in [0,1]: 0 = raw sample covariance (unstable for small n),
                        1 = fully diagonal (= the "diagonal" kernel mode).
    Standard shrinkage estimator (Ledoit-Wolf-style, simplified): keeps the matrix
    invertible even when n_pixels is close to or below n_indicators.
    """
    X = np.asarray(X, dtype=float)
    n, d = X.shape
    if n < 2:
        return np.eye(d)
    S = np.cov(X, rowvar=False)
    S = np.atleast_2d(S)
    target = np.diag(np.diag(S))  # shrink toward the diagonal (= per-indicator variances)
    shrinkage = float(np.clip(shrinkage, 0.0, 1.0))
    return (1 - shrinkage) * S + shrinkage * target


def mahalanobis_kernel_full(x: np.ndarray, ref_mean: np.ndarray, ref_cov: np.ndarray,
                            delta: float = 0.5, min_n: int = 30,
                            n_ref_pixels: Optional[int] = None) -> Dict[str, Optional[float]]:
    """Full-covariance Mahalanobis kernel with automatic fallback to the diagonal mode
    when the reference sample is too small to invert reliably.

    Returns a dict with the similarity value and which mode was actually used
    (never silently approximates without disclosing it).
    """
    x = np.asarray(x, dtype=float)
    ref_mean = np.asarray(ref_mean, dtype=float)
    d = len(x)
    out = {"value": None, "mode_used": None, "condition_number": None}

    fallback_reason = None
    if n_ref_pixels is not None and n_ref_pixels < min_n:
        fallback_reason = f"n_ref_pixels={n_ref_pixels} < min_n={min_n}"
    elif ref_cov.shape != (d, d):
        fallback_reason = "covariance shape mismatch"

    if fallback_reason is None:
        try:
            cond = np.linalg.cond(ref_cov)
            out["condition_number"] = float(cond)
            if cond > 1e8:  # near-singular; fall back rather than invert garbage
                fallback_reason = f"ill-conditioned covariance (cond={cond:.2e})"
            else:
                cov_inv = np.linalg.inv(ref_cov)
                diff = x - ref_mean
                quad_form = float(diff.T @ cov_inv @ diff)
                out["value"] = float(np.exp(-delta * quad_form))
                out["mode_used"] = "full"
                return out
        except np.linalg.LinAlgError as e:
            fallback_reason = f"inversion failed ({e})"

    # Fallback: diagonal mode using the same reference variances
    var = np.diag(ref_cov) if ref_cov.shape == (d, d) else np.ones(d)
    var = np.where(var > 0, var, 1.0)
    z = (x - ref_mean) / np.sqrt(var)
    out["value"] = mahalanobis_kernel_diagonal(z, delta=delta)
    out["mode_used"] = f"diagonal_fallback ({fallback_reason})"
    return out


def construct_seed_similarity(signed_benchmarks, delta: float = 0.5) -> Optional[float]:
    """Whole-construct SEED similarity (diagonal-covariance Mahalanobis kernel).

    signed_benchmarks : the construct's per-indicator signed benchmark values
                        (robust_z is already a standardised deviation; log response
                        ratio is treated as an approximate standardised deviation —
                        both are on a "standard-deviations-from-reference" scale).
    Uses mahalanobis_kernel_diagonal (Eq. 1 with C_r^-1 = diag(1/var)) — the numerically
    stable default given typically small reference samples. For the full-covariance
    version, use mahalanobis_kernel_full with a real reference sample matrix.
    """
    return mahalanobis_kernel_diagonal(signed_benchmarks, delta=delta)


def fit_delta_diagonal(z_matrix: np.ndarray, hmi_values: np.ndarray,
                       delta_range=(0.01, 5.0), n_grid: int = 200) -> Dict:
    """Calibrate delta the way SEED does: maximise the relationship between K(delta) and
    (1 - HMI) across a sample of reference-adjacent pixels within one stratum.

    z_matrix   : (n_pixels, n_indicators) standardised deviations for each sample pixel.
    hmi_values : (n_pixels,) HMI at the same pixels.
    Returns the fitted delta, the achieved correlation, and diagnostics. Requires REAL
    co-located (indicator, HMI) pairs from a live GEE run — cannot be meaningfully run on
    placeholder data; the caller is responsible for supplying genuine samples.
    """
    Z = np.asarray(z_matrix, dtype=float)
    hmi = np.asarray(hmi_values, dtype=float)
    ok = np.isfinite(hmi) & np.all(np.isfinite(Z), axis=1)
    Z, hmi = Z[ok], hmi[ok]
    if len(hmi) < 10:
        return {"delta": None, "correlation": None,
                "note": f"insufficient paired samples (n={len(hmi)} < 10)"}

    target = 1.0 - hmi  # SEED optimises K against (low HMI = high similarity)
    quad = np.sum(Z ** 2, axis=1)

    best = {"delta": None, "correlation": -np.inf}
    for delta in np.linspace(delta_range[0], delta_range[1], n_grid):
        k = np.exp(-delta * quad)
        if np.std(k) == 0 or np.std(target) == 0:
            continue
        corr = float(np.corrcoef(k, target)[0, 1])
        if corr > best["correlation"]:
            best = {"delta": float(delta), "correlation": corr}

    best["n_samples"] = int(len(hmi))
    best["note"] = ("fitted by grid search maximising corr(K(delta), 1-HMI), per "
                    "McElderry et al. 2024 Sec. 3.1")
    return best


# ============================================================================
# OD-3 — Variance-stability reference floor
# ============================================================================
# A fixed pixel floor is arbitrary (a mean/median from ~5-12 pixels is noise). Instead,
# accept a reference only when the bootstrap standard error of its median is small
# relative to the median — i.e. the reference is statistically stable. This makes the
# floor DATA-DERIVED and defensible, and lets the pipeline SUPPRESS a score when the
# reference is too uncertain rather than proceed on noise.

def reference_median_se(pixels, n_boot=500, seed=0):
    """Bootstrap standard error of the median of the reference pixel sample."""
    x = np.asarray([v for v in np.atleast_1d(pixels).ravel() if v is not None], dtype=float)
    x = x[np.isfinite(x)]
    if x.size < 2:
        return None
    rng = np.random.default_rng(seed)
    meds = np.median(rng.choice(x, size=(n_boot, x.size), replace=True), axis=1)
    return float(np.std(meds, ddof=1))


def reference_is_stable(pixels, min_n=8, rel_tol=0.15, abs_tol=None, n_boot=500):
    """True if the reference sample is statistically stable enough to benchmark against.

    Requires at least min_n finite pixels AND a bootstrap median SE within either a
    relative tolerance (SE/|median| <= rel_tol) or an absolute tolerance. Returns
    (is_stable, diagnostics).
    """
    x = np.asarray([v for v in np.atleast_1d(pixels).ravel() if v is not None], dtype=float)
    x = x[np.isfinite(x)]
    diag = {"n": int(x.size), "median": None, "se": None, "rel_se": None,
            "min_n": min_n, "rel_tol": rel_tol}
    if x.size < min_n:
        diag["reason"] = f"n<{min_n}"
        return False, diag
    med = float(np.median(x)); se = reference_median_se(x, n_boot=n_boot)
    diag["median"] = med; diag["se"] = se
    if se is None:
        diag["reason"] = "se_undefined"; return False, diag
    rel = se / abs(med) if med != 0 else float("inf")
    diag["rel_se"] = rel
    ok = (rel <= rel_tol) or (abs_tol is not None and se <= abs_tol)
    diag["reason"] = "stable" if ok else f"rel_se {rel:.3f} > tol {rel_tol}"
    return bool(ok), diag
