"""
test_forest_indicators.py
===========================

Real tests for independent audit item 9: forest_loss_rate's contract said
measurement_scale='ratio' + reference_estimator='log_response_ratio' (only
defined for strictly positive values -- see estimators.log_response_ratio),
but a real v0.2.5 change had made its site_value a SIGNED net (gain - loss)
rate, silently breaking scoring for the common real case of net loss.

Fix (2026-09-27, confirmed via a real client conversation: restoration/
agroforestry clients plant trees and a real gain needs to be visible, not
silently netted into a ratio-scale indicator): split into two indicators.
forest_loss_rate goes back to gross loss only (always >=0, matching its
original historically-established "Tree Cover Loss Rate" definition -- see
Thread 01/03). A new net_tree_cover_change_rate carries the signed gain-minus-
loss picture on its own robust_z-based contract instead.

These tests cover the pure-Python rate arithmetic shared by both indicators
(no live GEE needed) and the contract-level guarantees (no live GEE needed
either -- this is exactly the registry-validation pattern test_contracts.py
already established).

Run with: python -m pytest tests/test_forest_indicators.py -v
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from darukaa_reference.indicators import _annualized_rate_pct, create_default_registry
from darukaa_reference.estimators import log_response_ratio, robust_z


def test_annualized_rate_pct_matches_hand_computation():
    """area=1500 m2, baseline=50000 m2, 5 years -> (1500/50000)*100/5 = 0.6"""
    rate = _annualized_rate_pct(1500, 50000, 5)
    assert math.isclose(rate, 0.6, rel_tol=1e-9)


def test_annualized_rate_pct_floors_near_zero_baseline_like_gee_max1():
    """Mirrors the GEE-side `.max(1)` baseline floor exactly -- a near-zero
    baseline (e.g. Hansen 2000 baseline of 0.01 ha = 100 m2, real case from
    the Tata Motors Deccan forest zone) must floor at 1 m2, not divide by a
    near-zero number and explode further than the real GEE path would."""
    rate_at_true_value = _annualized_rate_pct(24_2600, 100, 24)   # not floored
    rate_at_floor = _annualized_rate_pct(24_2600, 0.001, 24)      # floored to 1
    assert math.isclose(rate_at_floor, _annualized_rate_pct(24_2600, 1, 24), rel_tol=1e-9)
    # both are still absurdly large (this is exactly why low_baseline suppression
    # exists downstream in extract_forest_loss_rate / extract_net_tree_cover_change_rate)
    assert rate_at_floor > 1000
    assert rate_at_true_value > 1000


def test_annualized_rate_pct_handles_zero_area():
    """No loss/gain at all -> rate is exactly 0, not None or an error."""
    assert _annualized_rate_pct(0, 50000, 5) == 0.0


def test_forest_loss_rate_and_net_tree_cover_change_rate_are_both_registered():
    reg = create_default_registry()
    assert "forest_loss_rate" in reg
    assert "net_tree_cover_change_rate" in reg


def test_forest_loss_rate_contract_is_log_response_ratio_compatible():
    """forest_loss_rate's contract (log_response_ratio) requires site_value
    to always be > 0 -- confirmed here it's still assigned that estimator,
    and separately (by construction of extract_forest_loss_rate, which sums
    a >=0 loss area and never subtracts gain) that its value_range floor is
    non-negative."""
    reg = create_default_registry()
    spec = reg.get("forest_loss_rate")
    assert spec.reference_estimator == "log_response_ratio"
    assert spec.measurement_scale == "ratio"
    assert spec.value_range[0] >= 0, "forest_loss_rate must stay non-negative for LRR to be defined"
    # sanity: log_response_ratio really is undefined at/below zero
    assert log_response_ratio(0.0, 5.0) is None
    assert log_response_ratio(-3.0, 5.0) is None
    assert log_response_ratio(2.0, 5.0) is not None


def test_net_tree_cover_change_rate_contract_uses_robust_z_not_log_response_ratio():
    """net_tree_cover_change_rate is where the real, signed gain-minus-loss value
    now lives -- must use an estimator defined for negative/zero values."""
    reg = create_default_registry()
    spec = reg.get("net_tree_cover_change_rate")
    assert spec.reference_estimator == "robust_z"
    assert spec.reference_estimator != "log_response_ratio"
    assert spec.value_range[0] < 0, "net_tree_cover_change_rate must allow negative (net loss) values"
    # sanity: robust_z IS defined for a negative site_value (a real net-loss case)
    assert robust_z(-4.0, ref_median=0.0, ref_mad=2.0) is not None


def test_forest_loss_rate_and_net_tree_cover_change_rate_do_not_share_a_subdimension():
    """Both are C1_landscape and both scored -- if they shared a subdimension,
    scoring.py would silently AVERAGE the pure-loss signal with the signed
    net signal, exactly the class of bug independent audit item 2 fixed for
    ghm/hdi. Real regression guardrail, same pattern as test_contracts.py."""
    reg = create_default_registry()
    loss_spec = reg.get("forest_loss_rate")
    net_spec = reg.get("net_tree_cover_change_rate")
    assert loss_spec.construct == net_spec.construct == "C1_landscape"
    assert loss_spec.subdimension != net_spec.subdimension
    assert loss_spec.scoring_eligible
    assert net_spec.scoring_eligible


if __name__ == "__main__":
    test_annualized_rate_pct_matches_hand_computation()
    test_annualized_rate_pct_floors_near_zero_baseline_like_gee_max1()
    test_annualized_rate_pct_handles_zero_area()
    test_forest_loss_rate_and_net_tree_cover_change_rate_are_both_registered()
    test_forest_loss_rate_contract_is_log_response_ratio_compatible()
    test_net_tree_cover_change_rate_contract_uses_robust_z_not_log_response_ratio()
    test_forest_loss_rate_and_net_tree_cover_change_rate_do_not_share_a_subdimension()
    print("All test_forest_indicators tests passed.")
