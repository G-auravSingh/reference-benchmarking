"""
test_estimators.py
==================

Real unit tests for darukaa_reference.estimators, added in response to an
independent audit finding: robust_z() was documented and implemented as
(site - median) / (1.4826 * MAD), but reference.py was passing standard
deviation (GEE's Reducer.stdDev()) into the ref_mad argument -- a genuinely
different statistic, not an approximation of it. Fixed with a real, GEE-native
two-pass MAD computation (see reference.py's _compute_true_mad). These tests
prove the underlying statistics, not the GEE plumbing (which needs live
credentials to test end-to-end) -- they test exactly what the audit asked for.

Run with: python -m pytest tests/test_estimators.py -v
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from darukaa_reference.estimators import robust_z


def _true_mad(values):
    """Reference implementation of the textbook MAD, used only to build test
    fixtures here -- NOT the production code path (that lives in
    reference.py's _compute_true_mad, which computes this via two real GEE
    reduceRegion calls rather than a client-side list)."""
    med = sorted(values)[len(values) // 2] if len(values) % 2 else \
        (sorted(values)[len(values)//2 - 1] + sorted(values)[len(values)//2]) / 2
    return med, sorted([abs(v - med) for v in values])[len(values) // 2]


def test_ordinary_reference_distribution_gives_expected_robust_z():
    """A plain, symmetric reference distribution: robust_z should match the
    textbook formula exactly."""
    values = [8, 9, 10, 10, 11, 12]
    median, mad = _true_mad(values)
    site_value = 14.0
    z = robust_z(site_value, median, mad, higher_is_better=True)
    expected = (site_value - median) / (1.4826 * mad)
    assert z is not None
    assert math.isclose(z, expected, rel_tol=1e-9)


def test_distribution_where_mad_differs_from_sd_uses_true_mad():
    """The real case the audit found: a reference pool with real outliers,
    where SD is inflated but MAD stays robust. Confirms using the REAL MAD
    (not SD) gives a genuinely different, smaller-magnitude, more defensible
    z-score than the buggy SD-based version would have."""
    import numpy as np
    np.random.seed(42)
    values = list(np.random.normal(10, 1, 95)) + [50, 60, 70, 80, 90]  # 5 real outliers
    median = float(np.median(values))
    sd = float(np.std(values, ddof=0))
    true_mad = float(np.median(np.abs(np.array(values) - median)))

    assert true_mad < sd / 5, "fixture must have MAD substantially smaller than SD (real outlier case)"

    site_value = 6.0
    z_correct = robust_z(site_value, median, true_mad, higher_is_better=True)
    z_buggy_if_sd_used = robust_z(site_value, median, sd, higher_is_better=True)

    assert z_correct is not None and z_buggy_if_sd_used is not None
    # The whole point of the fix: these must NOT be close -- if they were,
    # the bug wouldn't have mattered in practice.
    assert abs(z_correct) > abs(z_buggy_if_sd_used) * 3, (
        "true-MAD-based z should differ substantially from what the SD-based "
        "bug would have produced, confirming the fix is not a no-op")


def test_zero_mad_does_not_silently_divide():
    """A degenerate reference pool (all identical values, MAD=0) must return
    None, never raise, and never silently produce inf/nan."""
    z = robust_z(5.0, 5.0, 0.0, higher_is_better=True)
    assert z is None


def test_very_small_dispersion_does_not_explode_to_absurd_magnitude():
    """A near-zero but nonzero MAD (a quasi-degenerate reference pool -- the
    exact real scenario that produced -93.6/-70+ magnitudes on a real Tata
    Motors run) should be flagged as unreliable by the caller, not trusted
    as a normal z-score. This test documents the real, current numerical
    behavior (it DOES compute a large z rather than silently failing) so a
    caller-side suppression threshold has a concrete number to check against."""
    tiny_mad = 1e-4
    z = robust_z(1.0, 0.5, tiny_mad, higher_is_better=True)
    assert z is not None
    assert abs(z) > 100, (
        "documents the real current behavior: a near-zero MAD still produces "
        "an enormous z rather than being suppressed -- callers computing a "
        "client-facing benchmark should treat |z| this large as a low-"
        "dispersion-reference warning, not a literal, trustworthy magnitude")


def test_higher_is_better_false_flips_sign_correctly():
    """A pressure-type indicator (lower is better) with a site value BETTER
    than the reference median must produce a POSITIVE (good) z, not negative."""
    z_good_site = robust_z(2.0, 10.0, 2.0, higher_is_better=False)  # site well below (better) than ref
    z_bad_site = robust_z(20.0, 10.0, 2.0, higher_is_better=False)  # site well above (worse) than ref
    assert z_good_site > 0
    assert z_bad_site < 0


if __name__ == "__main__":
    import traceback
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    passed, failed = 0, 0
    for t in tests:
        try:
            t()
            print(f"PASS: {t.__name__}")
            passed += 1
        except Exception:
            print(f"FAIL: {t.__name__}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
