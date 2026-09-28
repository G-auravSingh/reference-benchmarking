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


def test_stop_rule_ends_retries_when_a_larger_request_returns_no_more_pixels():
    calls = []
    img = _FakeImage(calls, valid_by_request={5000: 40, 20000: 40, 40000: 40})
    out = _selector()._sample_reference_stats(None, img, "R", 10, label="tier2")
    sizes = [kw["numPixels"] for name, kw in calls if name == "sample"]
    assert sizes == [5000, 20000]                       # third, identical, expensive request is NOT made
    d = out["sampling_diagnostics"]
    assert d["reference_sample_stop_reason"] == "indicator_valid_population_below_requested_sample"
    assert d["reference_sample_counts_by_attempt"] == [{"requested": 5000, "valid": 40},
                                                        {"requested": 20000, "valid": 40}]
    assert d["reference_sample_n"] == 40                 # actual valid count recorded, not hidden


def test_stop_rule_on_an_empty_population_stops_after_two_attempts():
    calls = []
    img = _FakeImage(calls, valid_by_request={5000: 0, 20000: 0, 40000: 0})
    out = _selector()._sample_reference_stats(None, img, "R", 30, label="tier2")
    assert [kw["numPixels"] for n, kw in calls if n == "sample"] == [5000, 20000]
    assert out == {**out} and out["sampling_diagnostics"]["reference_sample_n"] == 0
    assert out["sampling_diagnostics"]["reference_sample_stop_reason"] == \
        "indicator_valid_population_below_requested_sample"


def test_growing_counts_keep_retrying_until_cap_and_report_the_cap():
    calls = []
    img = _FakeImage(calls, valid_by_request={5000: 300, 20000: 1200, 40000: 2400})
    out = _selector()._sample_reference_stats(None, img, "R", 10, label="tier2")
    assert [kw["numPixels"] for n, kw in calls if n == "sample"] == [5000, 20000, 40000]
    assert out["sampling_diagnostics"]["reference_sample_stop_reason"] == "max_sample_cap_reached"
    assert out["sampling_diagnostics"]["reference_sample_n"] == 2400


def test_met_request_reports_requested_sample_met():
    out = _selector()._sample_reference_stats(None, _FakeImage([]), "R", 10, label="t")
    assert out["sampling_diagnostics"]["reference_sample_stop_reason"] == "requested_sample_met"
    assert len(out["sampling_diagnostics"]["reference_sample_counts_by_attempt"]) == 1


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


# =====================================================================================
# Population-restricted Tier-2 sampling (2026-09-28)
# A semantic fake of ee.Image.stratifiedSample / ee.Image.sample that follows Google's documented
# behaviour: stratifiedSample's numPoints is the DEFAULT for every class and classValues/classPoints
# only override the listed classes; sample() draws numPixels points from the WHOLE region and only
# then drops masked ones (dropNulls is a post-filter).
# =====================================================================================
import types


class _FC:
    def __init__(self, feats): self.feats = feats
    def filter(self, pred): return _FC([f for f in self.feats if pred(f)])
    def aggregate_array(self, name): return _FC([f[name] for f in self.feats])
    def getInfo(self): return self.feats


class _SemImage:
    """zone = n_valid valid pixels (values ~ N(50,5)) + n_invalid masked pixels (unmasked -> 0)."""
    def __init__(self, n_valid=20000, n_invalid=180000, rec=None, dist=(50.0, 5.0)):
        rng = np.random.default_rng(0)
        self.valid_vals = rng.normal(dist[0], dist[1], n_valid)
        self.n_invalid = n_invalid
        self.rec = rec if rec is not None else {}
    # chain methods used by production code
    def select(self, b): return self
    def rename(self, n): return self
    def unmask(self, x): return self
    def addBands(self, o): return self
    def mask(self): return self
    def toInt(self): return self
    def updateMask(self, m): self.rec.setdefault("order", []).append("updateMask"); return self
    def clip(self, g): self.rec.setdefault("order", []).append("clip"); return self

    def stratifiedSample(self, numPoints, classBand, region, scale, seed, classValues, classPoints,
                         dropNulls, tileScale, geometries):
        self.rec.setdefault("order", []).append("stratifiedSample")
        self.rec["strat"] = dict(numPoints=numPoints, classBand=classBand, scale=scale, seed=seed,
                                 classValues=classValues, classPoints=classPoints, tileScale=tileScale)
        rng = np.random.default_rng(seed)
        feats = []
        for cls, pool in ((0, np.zeros(self.n_invalid)), (1, self.valid_vals)):
            n_c = classPoints[classValues.index(cls)] if cls in classValues else numPoints
            k = int(min(n_c, pool.size))
            idx = rng.choice(pool.size, k, replace=False) if k else []
            feats += [{"v": float(pool[i]), "valid": cls} for i in idx]
        return _FC(feats)

    def sample(self, region, scale, numPixels, seed, dropNulls, geometries, tileScale):
        self.rec.setdefault("order", []).append("sample")
        rng = np.random.default_rng(seed)
        pool = np.concatenate([self.valid_vals, np.full(self.n_invalid, np.nan)])
        k = int(min(numPixels, pool.size))
        drawn = pool[rng.choice(pool.size, k, replace=False)]
        return _FC([{"v": (None if np.isnan(x) else float(x))} for x in drawn if not (dropNulls and np.isnan(x))])


def _patch_ee_filter(monkeypatch):
    import ee
    monkeypatch.setattr(ee, "Filter", types.SimpleNamespace(eq=lambda k, v: (lambda f: f[k] == v)), raising=False)
    return ee


def test_the_v2_diagnostic_bug_is_reproduced_by_numPoints_default_and_fixed_by_zero():
    """v2 Part 4 called stratifiedSample(numPoints=N, classValues=[1], classPoints=[N]): numPoints applies to
    the UNLISTED class 0 too, so half the sample was masked pixels unmasked to 0 (n=10000, KS~0.5,
    MAD==median, p25==0 in every row). numPoints=0 returns only the valid class."""
    img = _SemImage()
    bad = img.stratifiedSample(5000, "valid", "Z", 10, 1, [1], [5000], True, 4, False).feats
    assert len(bad) == 10000 and sum(1 for f in bad if f["valid"] == 0) == 5000
    good = img.stratifiedSample(0, "valid", "Z", 10, 1, [1], [5000], True, 4, False).feats
    assert len(good) == 5000 and all(f["valid"] == 1 for f in good)


def test_restricted_sampler_returns_only_valid_points_with_the_intended_call(monkeypatch):
    _patch_ee_filter(monkeypatch)
    rec = {}
    sel = _selector()
    import ee
    vals = sel._population_restricted_values(ee, _SemImage(rec=rec), "ZONE", 10, 5000, 12345, 4)
    assert len(vals) == 5000 and min(vals) > 20.0                 # no masked-pixel zeros
    assert rec["strat"] == dict(numPoints=0, classBand="valid", scale=10, seed=12345,
                                classValues=[1], classPoints=[5000], tileScale=4)


def test_restricted_stats_diagnostics_and_gate_input(monkeypatch):
    _patch_ee_filter(monkeypatch)
    import ee
    sel = _selector()
    out = sel._sample_reference_stats(ee, _SemImage(), "ZONE", 10, label="tier2",
                                      population="pop", restricted=True)
    d = out["sampling_diagnostics"]
    assert d["reference_sampling_method"] == "population_restricted_stratified_sample"
    assert d["reference_sample_requested"] == 5000 and d["reference_sample_n"] == 5000
    assert d["reference_sample_stop_reason"] == "requested_sample_met"
    assert d["reference_sample_tilescale"] == 4 and d["effective_scale_m"] == 10
    assert len(out["pixels"]) == 5000 and out["n"] == 5000       # real values reach the stability gate
    assert abs(out["median"] - 50.0) < 0.5 and abs(1.4826 * out["mad"] - 5.0) < 0.3
    assert sel._reference_accepted(dict(out)) is True


def test_restricted_sampler_reports_when_the_valid_population_is_smaller_than_requested(monkeypatch):
    _patch_ee_filter(monkeypatch)
    import ee
    out = _selector()._sample_reference_stats(ee, _SemImage(n_valid=300), "ZONE", 10, label="tier2", restricted=True)
    d = out["sampling_diagnostics"]
    assert d["reference_sample_n"] == 300
    assert d["reference_sample_stop_reason"] == "valid_population_smaller_than_requested_sample"


def test_equivalence_check_agrees_when_both_samplers_draw_the_same_population(monkeypatch):
    _patch_ee_filter(monkeypatch)
    import ee
    sel = _selector(reference_sampling_equivalence_check=True, reference_sampling_check_draw_pixels=100000)
    out = sel._sample_reference_stats(ee, _SemImage(), "ZONE", 10, label="tier2", restricted=True)
    ec = out["sampling_diagnostics"]["equivalence_check"]
    assert ec["legacy_n"] > 1000 and ec["restricted_n"] == 5000
    assert ec["ks_p"] > 0.01 and abs(ec["median_diff_in_legacy_se"]) < 4
    assert set(ec["quantiles_legacy"]) == {"p10", "p25", "p50", "p75", "p90"}
    assert len(ec["hist_legacy"]) == 10 and len(ec["hist_restricted"]) == 10


def test_equivalence_summary_flags_a_real_difference():
    rng = np.random.default_rng(1)
    same = ReferenceSelector._equivalence_summary(rng.normal(0, 1, 500), rng.normal(0, 1, 5000))
    diff = ReferenceSelector._equivalence_summary(rng.normal(0, 1, 500), np.r_[np.zeros(5000), rng.normal(0, 1, 5000)])
    assert same["ks_p"] > 0.01 and diff["ks_p"] < 1e-6
    assert ReferenceSelector._equivalence_summary([1.0], [2.0, 3.0]).get("note")


def test_tier2_extraction_uses_restricted_by_default_after_all_masks_and_legacy_when_configured(monkeypatch):
    _patch_ee_filter(monkeypatch)
    import ee
    monkeypatch.setattr(ee, "Number", lambda x: x)
    rec = {}
    _selector()._extract_tier2_stats(_FakeGhm(), 0.05, _SemImage(rec=rec), "GEOM", spec=None)
    assert rec["order"] == ["updateMask", "clip", "stratifiedSample"]      # sampling AFTER every mask
    rec2 = {}
    _selector(reference_sampling_method="whole_zone_draw")._extract_tier2_stats(
        _FakeGhm(), 0.05, _SemImage(rec=rec2), "GEOM", spec=None)
    assert "stratifiedSample" not in rec2["order"] and rec2["order"][-1] == "sample"
