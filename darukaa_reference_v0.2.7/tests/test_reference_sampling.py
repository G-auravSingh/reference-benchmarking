"""
test_reference_sampling.py
==========================

Tests for the 2026-09-28 performance + numerical-stability fix:

  * scoring.normalize is a numerically stable logistic (no 'math range error').
  * Tier 1 / Tier 2 GEE reference statistics come from a deterministic, bounded,
    NATIVE-SCALE ee.Image.sample() taken AFTER all masks, with every statistic
    (including the true MAD) computed from the sampled values.
  * The variance-stability gate is now genuinely applied to sampled live-GEE values.
  * Per-stage timing is recorded.

HONEST LIMIT: these tests use fake ee objects. They verify the CALL CONTRACT (arguments,
ordering, statistics, diagnostics) -- they cannot verify real Earth Engine runtime or how
sample(numPixels=...) behaves on a heavily masked image. The single-tile live GEE run is
the required acceptance test; passing these tests does NOT establish that the runtime
problem is fixed.
"""
import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from darukaa_reference import estimators, scoring
from darukaa_reference.config import Config
from darukaa_reference.reference import ReferenceSelector, reference_stats_from_values


# ---------------------------------------------------------------- normalize
def _naive_logistic(k, v):
    return 1.0 / (1.0 + math.exp(-k * v))


@pytest.mark.parametrize("estimator", ["robust_z", "log_response_ratio"])
def test_normalize_extreme_benchmarks_do_not_overflow(estimator):
    assert scoring.normalize(5000, estimator) == pytest.approx(1.0)
    assert scoring.normalize(-5000, estimator) == pytest.approx(0.0, abs=1e-300)
    assert scoring.normalize(1e9, estimator) == pytest.approx(1.0)
    assert scoring.normalize(-1e9, estimator) == 0.0


@pytest.mark.parametrize("estimator,k", [("robust_z", scoring.K_Z), ("log_response_ratio", scoring.K_LRR)])
def test_normalize_agrees_exactly_with_the_logistic_for_ordinary_values(estimator, k):
    for v in np.linspace(-40, 40, 81):
        assert scoring.normalize(float(v), estimator) == pytest.approx(_naive_logistic(k, float(v)), rel=1e-12, abs=1e-15)
    assert scoring.normalize(0.0, estimator) == 0.5
    assert scoring.normalize(None, estimator) is None


def test_normalize_is_symmetric_and_monotonic():
    for v in (0.3, 2.0, 17.0, 300.0):
        assert scoring.normalize(-v, "robust_z") == pytest.approx(1.0 - scoring.normalize(v, "robust_z"))
    xs = [scoring.normalize(v, "robust_z") for v in (-2000, -50, -1, 0, 1, 50, 2000)]
    assert xs == sorted(xs)


def test_html_scorecard_survives_extreme_benchmarks():
    """The original failure: HTML generation died with 'math range error'."""
    from darukaa_reference import html_report
    rows = [{"indicator": "x", "display_name": "X", "construct": "C1_landscape", "evidence_tier": "baseline",
             "site_value": 0.1, "tier2_benchmark": b, "tier2_benchmark_estimator": "robust_z",
             "tier2_display_pct_of_reference": -1e5, "reference_type": "regional_distribution",
             "classification": {}, "site_id": "s"} for b in (-5000.0, 5000.0)]
    report = {"meta": {"generated_at": "t", "pipeline_version": "0.2.7", "n_sites": 1,
                       "archetype": "conservation", "tier2_hmi_ceiling": 0.05},
              "indicator_status": {"scored": ["x"], "contextual": [], "screening_only": [],
                                   "pending_inputs": [], "removed": []},
              "site_profiles": {}, "scorecard": rows, "son_summary": {}}
    html = html_report.render_html(report, "Extreme")
    assert "-5000" in html.replace("−", "-")  # raw benchmark preserved, not capped


# ---------------------------------------------------- stats from sampled values
def test_mad_is_computed_from_sampled_values_not_sd():
    vals = [1, 1, 1, 2, 2, 3, 4, 50, 90]           # skewed: MAD != SD
    s = reference_stats_from_values(vals)
    med = float(np.median(vals))
    assert s["median"] == med
    assert s["mad"] == pytest.approx(float(np.median(np.abs(np.array(vals) - med))))
    assert s["mad"] != pytest.approx(s["std"])
    assert s["n"] == len(vals)
    for k in ("mean", "median", "std", "mad", "p25", "p75", "p90", "n"):
        assert k in s
    assert len(s["pixels"]) == len(vals)             # the gate/percentile code gets real values


def test_stats_from_values_ignores_none_nan_and_handles_empty():
    assert reference_stats_from_values([]) == {}
    assert reference_stats_from_values([None, float("nan")]) == {}
    s = reference_stats_from_values([1.0, None, 3.0, float("nan"), 5.0])
    assert s["n"] == 3 and s["median"] == 3.0


# ------------------------------------------------------- fake ee for sampling
class _FakeFC:
    def __init__(self, values):
        self._v = values
    def aggregate_array(self, name):
        assert name == "v"
        return self
    def getInfo(self):
        return list(self._v)


class _FakeImage:
    """Records the chain of calls so ordering (mask BEFORE sample) can be asserted."""
    def __init__(self, calls, valid_by_request=None):
        self.calls = calls
        self.valid_by_request = valid_by_request or {}
    def select(self, band):
        self.calls.append(("select", band)); return self
    def rename(self, name):
        self.calls.append(("rename", name)); return self
    def updateMask(self, m):
        self.calls.append(("updateMask", m)); return self
    def clip(self, g):
        self.calls.append(("clip", g)); return self
    def sample(self, **kw):
        self.calls.append(("sample", kw))
        n = kw["numPixels"]
        valid = self.valid_by_request.get(n, n)
        rng = np.random.default_rng(kw["seed"])
        return _FakeFC(rng.normal(10.0, 2.0, valid).tolist())


class _FakeMask:
    pass


class _FakeGhm:
    def lte(self, x):
        return _FakeMask()


def _selector(**cfg_kw):
    return ReferenceSelector(Config(**cfg_kw))


def test_sampling_uses_configured_native_scale_seed_and_bounded_size():
    sel = _selector()
    calls = []
    out = sel._sample_reference_stats(None, _FakeImage(calls), "REGION", 10, label="tier2",
                                      population="test population")
    (_, kw), = [c for c in calls if c[0] == "sample"]
    assert kw["scale"] == 10                       # native scale, not coarsened
    assert kw["numPixels"] == 5000                 # default sample size
    assert kw["seed"] == 12345                     # fixed seed
    assert kw["dropNulls"] is True and kw["geometries"] is False and kw["tileScale"] == 4
    assert kw["region"] == "REGION"
    d = out["sampling_diagnostics"]
    assert d["reference_sampling_method"] == "deterministic_native_scale_random_sample"
    assert d["reference_sample_requested"] == 5000
    assert d["reference_sample_n"] == 5000
    assert d["reference_sample_seed"] == 12345
    assert d["effective_scale_m"] == 10
    assert d["reference_sample_tilescale"] == 4          # explicit tileScale, documented
    assert d["reference_sample_max_pixels"] == 40000     # bounded retry ceiling, documented
    assert d["reference_sample_retry_min_fraction"] == 0.5
    assert d["reference_population_definition"] == "test population"
    assert out["effective_scale_m"] == 10


def test_sample_is_deterministic_for_the_same_seed_and_changes_with_it():
    a = _selector()._sample_reference_stats(None, _FakeImage([]), "R", 30, label="t1")
    b = _selector()._sample_reference_stats(None, _FakeImage([]), "R", 30, label="t1")
    c = _selector(reference_sample_seed=7)._sample_reference_stats(None, _FakeImage([]), "R", 30, label="t1")
    assert a["median"] == b["median"] and a["mad"] == b["mad"]
    assert a["median"] != c["median"]


def test_sample_size_is_configurable():
    calls = []
    _selector(reference_sample_pixels=1234)._sample_reference_stats(None, _FakeImage(calls), "R", 10, label="t")
    (_, kw), = [c for c in calls if c[0] == "sample"]
    assert kw["numPixels"] == 1234


def test_sparse_mask_triggers_bounded_oversampling_never_coarsening():
    calls = []
    img = _FakeImage(calls, valid_by_request={5000: 100, 20000: 15000})
    out = _selector()._sample_reference_stats(None, img, "R", 10, label="tier2")
    sample_calls = [kw for name, kw in calls if name == "sample"]
    assert [kw["numPixels"] for kw in sample_calls] == [5000, 20000]
    assert all(kw["scale"] == 10 for kw in sample_calls)          # scale never changed
    d = out["sampling_diagnostics"]
    assert d["reference_sample_attempts"] == 2
    assert d["reference_sample_requested_initial"] == 5000 and d["reference_sample_requested"] == 20000
    assert d["reference_sample_n"] == 15000


def test_oversampling_is_capped_and_accepts_a_genuinely_small_population():
    calls = []
    img = _FakeImage(calls, valid_by_request={5000: 40, 20000: 40, 40000: 40})
    out = _selector()._sample_reference_stats(None, img, "R", 10, label="tier2")
    sizes = [kw["numPixels"] for name, kw in calls if name == "sample"]
    assert sizes == [5000, 20000, 40000] and max(sizes) <= 40000
    assert out["sampling_diagnostics"]["reference_sample_n"] == 40   # recorded, not hidden


def test_tier2_sample_is_taken_after_the_reference_masks(monkeypatch):
    if not _try_ee():
        pytest.skip("ee not importable")
    import ee
    monkeypatch.setattr(ee, "Number", lambda x: x)   # avoid needing an initialised EE session
    calls = []
    _selector()._extract_tier2_stats(_FakeGhm(), 0.05, _FakeImage(calls), "GEOM", spec=None)
    names = [c[0] for c in calls]
    assert names.index("updateMask") < names.index("clip") < names.index("sample")


def _try_ee():
    try:
        import ee  # noqa: F401
        return True
    except Exception:
        return False


# ------------------------------------------------------------- native scales
def test_native_scales_are_kept_and_net_forest_change_has_a_declared_scale():
    sel = _selector()
    class S:  # minimal spec stand-in
        def __init__(self, name): self.name = name
    for name, expected in [("natural_habitat", 10), ("hdi", 10), ("forest_loss_rate", 30),
                           ("net_forest_change_rate", 30), ("ghm", 90), ("chm", 10)]:
        assert sel._effective_scale(S(name)) == expected, name
    assert Config().reference_sample_pixels == 5000 and Config().reference_sample_seed == 12345


# ------------------------------------------------ dispersion + stability gate
def test_low_dispersion_reference_is_flagged_from_sampled_values():
    vals = np.random.default_rng(3).normal(100.0, 0.5, 5000)     # MAD/median ~0.3% (< 2%)
    s = reference_stats_from_values(vals)
    b = estimators.benchmark(site_value=90.0, reference_median=s["median"], reference_mad=s["mad"],
                             reference_values=s["pixels"].tolist(), measurement_scale="interval",
                             reference_estimator="robust_z", higher_is_better=True)
    assert b["value"] is not None and b["low_dispersion_warning"] is True
    assert b["percentile_in_reference"] is not None      # now available for live GEE references

    # A fully degenerate pool (MAD == 0) is suppressed by the item-1 logic, never divided by.
    d = reference_stats_from_values([5.0] * 5000)
    b0 = estimators.benchmark(site_value=9.0, reference_median=d["median"], reference_mad=d["mad"],
                              reference_values=d["pixels"].tolist(), measurement_scale="interval",
                              reference_estimator="robust_z", higher_is_better=True)
    assert d["mad"] == 0.0 and b0["value"] is None


def test_stability_gate_now_operates_on_sampled_values():
    sel = _selector()
    rng = np.random.default_rng(1)
    good = reference_stats_from_values(rng.normal(50, 5, 5000))
    assert sel._reference_accepted(good) is True
    assert good["stability"]["reason"] == "stable"           # gate really ran
    assert good["stability"]["n"] == 5000

    noisy = reference_stats_from_values(rng.normal(1.0, 50, 40))    # tiny + noisy
    assert sel._reference_accepted(noisy) is False
    assert "stability" in noisy

    too_few = reference_stats_from_values([1, 2, 3])
    assert sel._reference_accepted(too_few) is False          # min_reference_pixels floor


def test_stability_gate_can_be_disabled_and_supports_abs_tolerance():
    zero_inflated = reference_stats_from_values([0.0] * 4900 + [1.0] * 100)   # median 0 -> relative SE undefined
    assert _selector()._reference_accepted(dict(zero_inflated)) is False       # documents current behaviour
    assert _selector(reference_stability_abs_tol=0.05)._reference_accepted(dict(zero_inflated)) is True
    assert _selector(use_variance_stability_floor=False)._reference_accepted(dict(zero_inflated)) is True


# ------------------------------------------------------------ timing + labels
def test_timing_records_required_fields():
    sel = _selector()
    sel._timing_ctx = ("EMU_Deccan_forest", "chm")
    with sel._timed("tier2_reference") as t:
        t["n"] = 4321
    rec = sel.timing_log[-1]
    assert rec["site_id"] == "EMU_Deccan_forest" and rec["indicator"] == "chm"
    assert rec["stage"] == "tier2_reference" and rec["n_reference_pixels"] == 4321
    assert rec["elapsed_seconds"] >= 0


def test_population_definition_distinguishes_ghm_and_fallbacks():
    f = ReferenceSelector._tier2_population_definition
    assert "NO HMI filter" in f({"ghm_independent_reference": True}, None)
    assert "HMI <= 0.0500" in f({"fallback_level": "primary"}, 0.05)
    assert "land-cover constraint dropped" in f({"fallback_level": "fallback_1_dropped_landcover"}, 0.05)
    assert "widened" in f({"fallback_level": "fallback_2_widened_100.0km"}, 0.05)


# ------------------------------------------------ end-to-end plumbing via compute()
def test_compute_carries_required_diagnostics_timing_and_percentile_end_to_end():
    import dataclasses
    from darukaa_reference.indicators import create_default_registry
    spec = dataclasses.replace(create_default_registry().get("chm"),
                               extract_fn=lambda g, c: {"value": 12.0})
    sel = _selector()
    sel._compute_tier1 = lambda sp, geom: sel._sample_reference_stats(
        None, _FakeImage([]), "R", 10, "tier1", "tier1 population")
    def _t2(sp, geom, eco):
        out = sel._sample_reference_stats(None, _FakeImage([]), "R", 10, "tier2", "ignored")
        assert sel._reference_accepted(out)                      # gate runs on sampled values
        return {**out, "stratification_diagnostics": {"fallback_level": "primary"}, "hmi_realised": 0.04}
    sel._compute_tier2 = _t2

    r = sel.compute(spec, "GEOM", "siteA", 1)
    d = r.stratification_diagnostics
    for key in ("reference_sampling_method", "reference_sample_requested", "reference_sample_n",
                "reference_sample_seed", "effective_scale_m", "reference_population_definition"):
        assert d.get(key) is not None, key
    assert "HMI <= 0.0400" in d["reference_population_definition"]
    assert d["reference_stability"]["reason"] == "stable"        # stability diagnostics recorded
    assert d["tier1_reference_sampling"]["reference_sample_n"] == 5000
    assert r.tier2_n_pixels == 5000 and r.tier2_mad is not None
    assert r.tier2_benchmark is not None                          # raw signed benchmark preserved
    assert r.tier2_percentile_in_reference is not None            # real values now reach the estimator

    stages = {(t["site_id"], t["indicator"], t["stage"]) for t in sel.timing_log}
    for stage in ("site_extraction", "tier1_reference", "tier2_reference", "reference_sampling_tier1",
                  "reference_sampling_tier2", "benchmark_calculation_tier2"):
        assert ("siteA", "chm", stage) in stages, stage
    assert all({"site_id", "indicator", "stage", "elapsed_seconds", "n_reference_pixels"} <= set(t)
               for t in sel.timing_log)
