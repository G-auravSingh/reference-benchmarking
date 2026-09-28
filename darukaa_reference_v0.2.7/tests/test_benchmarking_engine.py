"""
Engine tests (v0.2.8 Phase 3): estimators, guards, compatibility, applicability and the explicit status model.
Every expected value is derived by hand from the fixture, not read back from the code.
"""
import inspect
import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from darukaa_reference import benchmarking as B
from darukaa_reference import constructs as K
from darukaa_reference import indicator_contract as IC
from darukaa_reference.config import Config
from darukaa_reference.indicators import create_default_registry

C = IC.CONTRACTS
TERR = B.SiteEvidence("terrestrial", 4.0e5, frozenset({"woody"}), forest_baseline_m2=2.0e5)


# ------------------------------------------------------------------ helpers
def pair(contract, ref_values, site_area_m2=4.0e5, tier=None, **spec_over):
    """A consistent (site spec, reference) pair for a contract."""
    ref_support = contract.reference_support
    win = site_area_m2 if ref_support.startswith("site_window") else None
    site = B.MetricSpec("c", "u", "t", contract.site_support, "site", native_scale_m=contract.native_resolution_m)
    fields = dict(construct="c", unit="u", temporal="t", support=ref_support, population=contract.reference_population,
                  window_area_m2=win, native_scale_m=contract.native_resolution_m)
    fields.update(spec_over)
    ref = B.ReferenceData(np.asarray(ref_values, float), B.MetricSpec(**fields), tier or contract.reference_tier, "test population")
    return site, ref


def evaluate(name, site_value, ref_values, ev=TERR, **kw):
    c = C[name]
    site, ref = pair(c, ref_values, ev.site_area_m2)
    return B.evaluate_indicator(c, ev, site_value, site, {c.reference_tier: ref}, **kw)


NORMAL = np.random.default_rng(3).normal(50, 5, 300)


# ------------------------------------------------------------------ percentile estimator
def test_percentile_known_answers_and_direction():
    ref = np.arange(1, 101, dtype=float)
    hi = B.percentile_benchmark(50.0, ref, "higher_is_better")
    lo = B.percentile_benchmark(50.0, ref, "lower_is_better")
    assert hi["score"] == pytest.approx(0.49 + 0.5 * 0.01)      # 49 below + half of the single tie
    assert lo["score"] == pytest.approx(0.50 + 0.5 * 0.01)      # 50 above + half of the single tie
    assert hi["score"] + lo["score"] == pytest.approx(1.0)       # opposite directions are complementary
    assert hi["reference_n"] == 100 and hi["score_halfwidth_dkw95"] == pytest.approx(math.sqrt(math.log(40) / 200))


def test_percentile_lower_is_better_with_zero_inflated_reference():
    ref = np.r_[np.zeros(80), np.round(np.linspace(0.1, 2.0, 20), 10)]     # 80 % zero-loss windows
    zero_site = B.percentile_benchmark(0.0, ref, "lower_is_better")
    assert zero_site["p_reference_tied"] == pytest.approx(0.8) and zero_site["fraction_reference_zero"] == pytest.approx(0.8)
    assert zero_site["score"] == pytest.approx(0.2 + 0.5 * 0.8)   # explicit tie handling: mid-rank = 0.6
    worst = B.percentile_benchmark(3.0, ref, "lower_is_better")   # more loss than every reference window
    assert worst["score"] == 0.0 and worst["p_reference_worse"] == 0.0
    mid = B.percentile_benchmark(1.0, ref, "lower_is_better")     # 10 windows lose more, one ties
    assert mid["score"] == pytest.approx(0.10 + 0.5 * 0.01)
    # lower loss is BETTER: a lower-loss site never scores below a higher-loss site
    assert B.percentile_benchmark(0.2, ref, "lower_is_better")["score"] > B.percentile_benchmark(1.5, ref, "lower_is_better")["score"]
    assert zero_site["reference_n"] == 100                        # actual reference sample size retained


def test_percentile_requires_an_explicit_direction_and_handles_empty_reference():
    with pytest.raises(ValueError):
        B.percentile_benchmark(1.0, [1, 2, 3], "none")
    assert B.percentile_benchmark(1.0, [], "higher_is_better") is None
    assert B.percentile_benchmark(1.0, [np.nan, np.inf], "higher_is_better") is None


# ------------------------------------------------------------------ zero-inflation guard
def test_zero_inflated_reference_never_falls_through_to_the_lrr_mad_logic(monkeypatch):
    ref = np.r_[np.zeros(80), np.linspace(0.1, 2.0, 20)]
    assert B.scale_estimator_guard(ref) == "reference_zero_inflated_or_tie_heavy"

    def boom(*a, **k):
        raise AssertionError("scale estimator reached on a zero-inflated reference")
    monkeypatch.setattr(B._est, "robust_z", boom)
    monkeypatch.setattr(B._est, "log_response_ratio", boom)
    for name in ("ndvi", "chm"):                                   # a robust_z and a log_response_ratio contract
        out = B.benchmark_by_estimator(C[name], 0.5, ref)
        assert out == {"suppressed": "reference_zero_inflated_or_tie_heavy"}
    a = evaluate("ndvi", 0.5, ref)                                  # ...and through the engine: explicit status
    assert a.status == "suppressed_for_stability" and a.reason == "reference_zero_inflated_or_tie_heavy" and a.score is None
    # the percentile contract handles the same reference without suppression
    assert B.benchmark_by_estimator(C["forest_loss_rate"], 0.5, ref)["estimator"] == "reference_percentile"


def test_log_response_ratio_refuses_nonpositive_values():
    assert B.benchmark_by_estimator(C["chm"], 0.0, NORMAL)["suppressed"] == "log_ratio_undefined_for_nonpositive_values"


def test_normal_reference_uses_the_scale_estimator():
    out = B.benchmark_by_estimator(C["ndvi"], 60.0, NORMAL)
    assert out["estimator"] == "robust_z" and out["benchmark"] > 1.5 and 0.5 < out["score"] < 1.0


# ------------------------------------------------------------------ compatibility (construct, unit, temporal, support, population)
@pytest.mark.parametrize("over, fragment", [
    ({"construct": "other"}, "construct differs"),
    ({"unit": "percent"}, "unit differs"),
    ({"temporal": "another window"}, "temporal window differs"),
    ({"support": "site_window_mean"}, "spatial support differs"),
    ({"population": "regional_all"}, "population differs"),
    ({"native_scale_m": 30.0}, "native scale differs"),
    ({"window_area_m2": 1.0e6}, "window area"),
])
def test_incompatible_site_reference_pairs_are_detected(over, fragment):
    c = C["natural_habitat"]
    site, ref = pair(c, NORMAL, **over)
    bad = B.check_compatibility(site, ref.spec, c, 4.0e5)
    assert any(fragment in b for b in bad), bad


def test_matching_pair_passes_and_incompatible_pair_is_never_scored():
    c = C["natural_habitat"]
    site, ref = pair(c, NORMAL)
    assert B.check_compatibility(site, ref.spec, c, 4.0e5) == []
    a = evaluate_with(c, ref_over={"unit": "percent_per_year"})
    assert a.status == "reference_available_but_not_scoreable" and a.reason == "incompatible_site_reference"
    assert "unit differs" in a.detail and a.score is None


def evaluate_with(c, ref_over):
    site, ref = pair(c, NORMAL, **ref_over)
    return B.evaluate_indicator(c, TERR, 60.0, site, {c.reference_tier: ref})


def test_a_pixel_reference_for_a_polygon_site_is_incompatible():
    """Audit X1: single-pixel reference vs polygon-level site value is refused by construction."""
    c = C["natural_habitat"]
    site, ref = pair(c, NORMAL, support="site_pixel")
    assert any("spatial support differs" in b for b in B.check_compatibility(site, ref.spec, c, 4.0e5))


# ------------------------------------------------------------------ applicability
def test_domain_ecosystem_feature_and_support_rules_give_explicit_reasons():
    aq = B.SiteEvidence("aquatic", 4e5, frozenset({"open_water"}), water_body_valid=True, n_pure_water_px=200)
    assert B.check_applicability(C["chm"], aq)[0] == "domain_mismatch"
    assert B.check_applicability(C["tspi"], TERR)[0] == "domain_mismatch"
    assert B.check_applicability(C["chm"], B.SiteEvidence("terrestrial", 4e5, frozenset()))[0] == "ecosystem_type_mismatch"
    assert B.check_applicability(C["forest_loss_rate"], B.SiteEvidence("terrestrial", 4e5, frozenset({"woody"}), forest_baseline_m2=3e4))[0] == "target_feature_absent"
    assert B.check_applicability(C["forest_loss_rate"], B.SiteEvidence("terrestrial", 4e5, frozenset({"woody"})))[0] == "target_feature_absent"
    assert B.check_applicability(C["forest_loss_rate"], TERR)[0] is None                       # 20 ha baseline
    assert B.check_applicability(C["sabf"], B.SiteEvidence("aquatic", 4e5, frozenset({"open_water"}), water_body_valid=False))[0] == "target_feature_absent"
    assert B.check_applicability(C["sabf"], B.SiteEvidence("aquatic", 4e5, frozenset({"open_water"}), water_body_valid=True, n_pure_water_px=9))[0] == "insufficient_pure_water"
    assert B.check_applicability(C["sabf"], aq)[0] is None


def test_hard_floor_and_indicator_specific_floor():
    # natural_habitat: 10 m pixels, specific floor 100 px (1 ha)
    assert B.check_applicability(C["natural_habitat"], B.SiteEvidence("terrestrial", 9.9e3))[0] == "site_below_product_resolution"
    assert B.check_applicability(C["natural_habitat"], B.SiteEvidence("terrestrial", 1.0e4))[0] is None
    # bii: 100 m pixels, generic floor 10 px (10 ha)
    assert B.check_applicability(C["bii"], B.SiteEvidence("terrestrial", 9.9e4))[0] == "site_below_product_resolution"
    assert B.check_applicability(C["bii"], B.SiteEvidence("terrestrial", 1.0e5))[0] is None


def test_tata_zone_consequences_of_the_floors_documented():
    """Real Tata EMU zone areas (ha, from the tile GeoJSONs). At 10 m every zone clears the generic 10-px
    floor; the specific 100-px floor of natural_habitat excludes the two smallest; at the 100 m BII product
    only the 40 ha Deccan forest clears 10 native pixels."""
    zones = {"Deccan_forest": 40.10, "Grass_land": 2.80, "Narmada_valley": 9.25, "Savana": 1.72,
             "Seasonal_wetland": 0.73, "Trail_plots": 2.03, "Water_margin": 6.48, "Wetland_forest": 0.47, "Wildlife": 3.78}
    nh = {z: B.check_applicability(C["natural_habitat"], B.SiteEvidence("terrestrial", ha * 1e4))[0] is None for z, ha in zones.items()}
    assert [z for z, ok in nh.items() if not ok] == ["Seasonal_wetland", "Wetland_forest"]
    bii = {z: B.check_applicability(C["bii"], B.SiteEvidence("terrestrial", ha * 1e4))[0] is None for z, ha in zones.items()}
    assert [z for z, ok in bii.items() if ok] == ["Deccan_forest"]
    ghm = {z: B.check_applicability(C["ghm"], B.SiteEvidence("terrestrial", ha * 1e4)) for z, ha in zones.items()}
    assert all(r[0] is None for r in ghm.values())                                            # exempt landscape pressure
    assert "below_generic_floor_landscape_pressure_exempt" in ghm["Wetland_forest"][2]


# ------------------------------------------------------------------ the explicit status model
def test_every_status_is_reachable_with_a_reason():
    ok_ref = NORMAL
    seen = {}

    seen["scored"] = evaluate("natural_habitat", 80.0, ok_ref)
    seen["not_applicable"] = evaluate("tspi", 1.0, ok_ref)
    seen["applicable_but_no_site_value"] = evaluate("natural_habitat", None, ok_ref)
    c = C["natural_habitat"]
    seen["applicable_but_no_reference"] = B.evaluate_indicator(c, TERR, 80.0, pair(c, ok_ref)[0], {})
    seen["reference_available_but_not_scoreable"] = evaluate("natural_habitat", 80.0, ok_ref[:10])   # n < 30
    seen["suppressed_for_stability"] = evaluate("ndvi", 0.5, np.r_[np.zeros(80), np.ones(20)])
    seen["contextual_only"] = B.evaluate_indicator(C["natural_landcover"], TERR, 50.0, None, {})
    seen["screening_only"] = B.evaluate_indicator(C["kba_overlap"], TERR, 5.0, None, {})
    seen["pending_methodology"] = B.evaluate_indicator(C["cpland"], TERR, 5.0, None, {})
    assert {k: v.status for k, v in seen.items()} == {k: k for k in seen}
    assert set(seen) == set(IC.INDICATOR_STATUSES)                                    # all nine states covered
    for k, a in seen.items():
        if k not in ("scored",):
            assert a.reason, f"{k} must explain itself"


def test_reference_available_but_not_scoreable_reasons():
    a = evaluate("natural_habitat", 80.0, NORMAL[:10])
    assert a.reason == "insufficient_reference_n" and "10 < documented minimum 30" in a.detail
    a = evaluate("natural_habitat", 80.0, NORMAL, require_validated=True)
    assert a.reason == "awaiting_live_validation" and a.benchmark is not None      # benchmark visible, not scored
    assert evaluate("natural_habitat", 80.0, NORMAL).status == "scored"


def test_removed_indicator_is_not_applicable_with_a_reason():
    a = B.evaluate_indicator(C["ceri"], TERR, 1.0, None, {})
    assert a.status == "not_applicable" and a.reason == "indicator_removed"


def test_no_indicator_ever_produces_no_reference_or_a_silent_null():
    for domain, tags in (("terrestrial", frozenset({"woody"})), ("aquatic", frozenset({"open_water"})),
                         ("mixed", frozenset())):
        ev = B.SiteEvidence(domain, 4e5, tags, forest_baseline_m2=2e5, water_body_valid=True, n_pure_water_px=100)
        for name, c in C.items():
            a = B.evaluate_indicator(c, ev, None, None, {})
            assert a.status in IC.INDICATOR_STATUSES and a.status != "no_reference" and a.reason != "no_reference", name
            assert a.status != "scored" and a.score is None, name                     # nothing scores from nothing
            assert a.reason, f"{name}/{domain}: status {a.status} has no reason"


def test_tier1_and_tier2_references_are_both_kept_visible_and_the_contract_tier_scores():
    c = C["ghm"]
    site, ref2 = pair(c, NORMAL / 100.0, site_area_m2=4e5)
    _, ref1 = pair(c, NORMAL / 90.0, site_area_m2=4e5, tier="tier1", population="regional_all")
    ref1 = B.ReferenceData(ref1.values, ref1.spec, "tier1", "regional windows, all pixels")
    a = B.evaluate_indicator(c, TERR, 0.6, site, {"tier1": ref1, "tier2": ref2})
    assert a.status == "scored" and a.reference_tier == "tier2"
    assert set(a.other_references) == {"tier1", "tier2"}
    assert a.other_references["tier1"]["reference_n"] == 300 and a.other_references["tier2"]["reference_n"] == 300
    assert a.reference_n == 300 and a.reference_median is not None and a.reference_mad is not None


def test_absolute_natural_reference_is_a_separate_diagnostic_never_inside_the_score():
    a = evaluate("natural_habitat", 81.6, NORMAL)
    d = a.diagnostics["absolute_natural_reference"]
    assert d["departure_percentage_points"] == pytest.approx(18.4) and d["ratio_to_reference_condition"] == pytest.approx(0.816)
    # the benchmark uses the regional windows, not 100 %
    assert a.benchmark_details["estimator"] == "reference_percentile" and a.reference_population == "test population"
    assert a.benchmark == pytest.approx(B.percentile_benchmark(81.6, NORMAL, "higher_is_better")["score"])


# ------------------------------------------------------------------ structural guards (audit X3 / X4)
def test_no_scoreable_indicator_normalises_its_site_value_by_the_sites_own_range():
    reg = create_default_registry()
    for name, c in C.items():
        if c.proposed_scoreability != "scoreable":
            continue
        spec = reg.get(name)
        for fn in (spec.extract_fn, spec.metadata.get("gee_image_fn")):
            if fn is None:
                continue
            assert "minMax" not in inspect.getsource(fn), f"{name}: {fn.__name__} uses a site-derived min/max"


def test_reference_image_of_a_scoreable_or_changed_indicator_is_single_band_by_contract():
    for name in ("edpp", "mspl") + tuple(n for n, c in C.items() if c.proposed_scoreability == "scoreable"):
        assert C[name].image_is_single_band and not C[name].site_relative_normalisation, name


def test_shared_constants_equal_the_legacy_module_constants():
    import darukaa_reference.indicators as I
    for k in ("DW_TREES", "DW_GRASS", "DW_FLOODED_VEG", "DW_CROPS", "DW_SHRUB_SCRUB", "DW_BUILT", "DW_BARE"):
        assert getattr(I, k) == getattr(K, k), k
    assert list(I.DW_NATURAL_CLASSES) == list(K.NATURAL_CLASSES)


def test_validation_dataset_results_can_never_enter_project_scoring():
    """E4: an external forested polygon used to validate forest loss is labelled and excluded."""
    ev_val = B.SiteEvidence("terrestrial", 4e5, frozenset({"woody"}), forest_baseline_m2=3e5,
                            validation_dataset_label="external forest validation polygon (not a Tata zone)")
    c = C["forest_loss_rate"]
    site, ref = pair(c, np.r_[np.zeros(60), np.linspace(0.1, 2, 40)], 4e5)
    v = B.evaluate_indicator(c, ev_val, 0.2, site, {"tier2": ref})
    p = B.evaluate_indicator(c, TERR, 0.2, site, {"tier2": ref})
    assert v.status == p.status == "scored"                       # it can be validated like any site...
    assert v.validation_only and any(f.startswith("methodological_validation_dataset:") for f in v.flags)
    assert not p.validation_only
    kept = B.project_assessments([v, p])
    assert kept == [p]                                             # ...but never joins the project result
