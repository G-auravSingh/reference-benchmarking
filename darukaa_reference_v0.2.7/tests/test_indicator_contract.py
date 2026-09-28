"""
Tests for the v0.2.8 indicator contract (Phase 1 frozen specification).
"""
import dataclasses
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from darukaa_reference import indicator_contract as IC
from darukaa_reference.indicators import create_default_registry

C = IC.CONTRACTS


def test_every_registered_indicator_has_exactly_one_contract():
    names = {s.name for s in create_default_registry().all()}
    assert names == set(C), (names ^ set(C))
    assert len(C) == 46


def test_every_contract_satisfies_the_rules():
    bad = {n: IC.validate_contract(c) for n, c in C.items() if IC.validate_contract(c)}
    assert bad == {}


def test_nothing_is_validated_yet_and_proposals_carry_their_defects():
    assert not any(c.validated for c in C.values())                 # the 13-set is NOT active
    for n, c in C.items():
        if c.proposed_scoreability == "scoreable":
            assert c.current_defects or c.implementation_status == "v0.2.8_synthetic_tested", \
                f"{n}: a proposed indicator must list its implementation gap or be synthetic-tested"
            assert c.implementation_status != "v0.2.8_live_validated"


def test_proposed_scoreable_sets_by_domain():
    sc = {n for n, c in C.items() if c.proposed_scoreability == "scoreable"}
    terr = {n for n in sc if "terrestrial" in C[n].applicability.domains}
    aqua_only = {n for n in sc if "terrestrial" not in C[n].applicability.domains}
    assert terr == {"natural_habitat", "forest_loss_rate", "net_forest_change_rate", "ndvi", "chm", "bii",
                    "ghm", "hdi", "light_pollution", "riparian_natural_veg_share"}
    assert aqua_only == {"tspi", "sabf", "wcpi", "sdi"}
    assert C["cpland"].proposed_scoreability == "pending_methodology"      # blocked on provenance
    shared = {n for n in sc if {"terrestrial", "aquatic"} <= set(C[n].applicability.domains)}
    assert shared == {"ghm", "hdi", "light_pollution", "riparian_natural_veg_share"}
    assert "rci" not in C


def test_tier_is_not_scoreability():
    tier1_scoreable = [n for n, c in C.items() if c.reference_tier == "tier1" and c.proposed_scoreability == "scoreable"]
    tier2_not = [n for n, c in C.items() if c.reference_tier == "tier2" and c.proposed_scoreability != "scoreable"]
    assert tier1_scoreable and tier2_not


def test_status_vocabulary_is_complete():
    assert set(IC.INDICATOR_STATUSES) == {
        "not_applicable", "applicable_but_no_site_value", "applicable_but_no_reference",
        "reference_available_but_not_scoreable", "scored", "contextual_only", "screening_only",
        "suppressed_for_stability", "pending_methodology"}
    assert "no_reference" not in IC.INDICATOR_STATUSES


def test_redundancy_conflicts_needing_a_phase7_rule():
    assert IC.redundancy_conflicts(C) == {"R1_vegetation_signal": ["chm", "ndvi"]}


# ---------------------------------------------------------------- each rule fires
BASE = C["ndvi"]


def _violations(**changes):
    return IC.validate_contract(dataclasses.replace(BASE, **changes))


@pytest.mark.parametrize("changes, fragment", [
    ({"reference_support": "none"}, "support mismatch"),                                    # X1
    ({"site_support": "polygon_proportion"}, "support mismatch"),
    ({"site_relative_normalisation": True}, "site-relative"),                              # X3
    ({"image_is_single_band": False}, "single-band"),                                      # X4
    ({"reference_population": "regional_all", "reference_support": "site_window_mean"}, "condition indicator"),  # X8
    ({"inputs": ("s2", "dw_label")}, "circular reference"),                                # X2
    ({"applicability": IC.Applicability(("terrestrial",), "any", None, None)}, "hard floor"),          # X6 / D3
    ({"estimator": None}, "estimator"),
    ({"direction": "none"}, "direction"),
    ({"native_resolution_m": None}, "native resolution"),
    ({"validated": True}, "current_defects"),
])
def test_rule_violation_is_detected(changes, fragment):
    assert any(fragment in v for v in _violations(**changes)), _violations(**changes)


def test_pressure_cannot_use_the_least_disturbed_pool():
    ghm = C["ghm"]
    bad = dataclasses.replace(ghm, reference_population="least_disturbed_stratum", inputs=("viirs",))
    assert any("pressure indicator" in v for v in IC.validate_contract(bad))


def test_validated_requires_evidence_verified_resolution_and_no_defects():
    ok = dataclasses.replace(C["bii"], current_defects=(), validated=True,
                             validation_evidence=("synthetic", "live EMU_Deccan_forest"))
    assert IC.validate_contract(ok) == []
    assert any("verified native resolution" in v for v in
               IC.validate_contract(dataclasses.replace(ok, resolution_verified=False)))
    assert any("validation_evidence" in v for v in
               IC.validate_contract(dataclasses.replace(ok, validation_evidence=())))


def test_water_body_indicator_needs_pure_water_rule():
    bad = dataclasses.replace(C["tspi"], applicability=IC.Applicability(("aquatic",), "open_water", "water_body", 10, None))
    assert any("pure-water" in v for v in IC.validate_contract(bad))


# ---------------------------------------------------------------- v0.2.8 Phase 3 rules
def test_generic_floor_is_10_native_pixels_and_specific_floors_are_explicit():
    assert IC.GENERIC_MIN_NATIVE_PIXELS == 10
    assert IC.effective_min_native_pixels(C["bii"]) == 10
    assert IC.effective_min_native_pixels(C["natural_habitat"]) == 100          # indicator-specific
    assert IC.effective_min_native_pixels(C["net_forest_change_rate"]) == 100
    assert C["natural_habitat"].min_support_rationale and C["net_forest_change_rate"].min_support_rationale
    assert IC.effective_min_native_pixels(C["ghm"]) is None                    # exempt landscape pressure
    assert C["ghm"].applicability.floor_basis == "exempt_landscape_pressure" and C["ghm"].min_support_rationale


def test_specific_floor_below_generic_or_without_rationale_is_rejected():
    bad = dataclasses.replace(C["natural_habitat"], applicability=IC.Applicability(
        ("terrestrial", "mixed"), "any", None, 10, None, 5, "polygon_native_pixels"))
    assert any("must not be below the generic floor" in v for v in IC.validate_contract(bad))
    bad = dataclasses.replace(C["natural_habitat"], min_support_rationale="")
    assert any("rationale" in v for v in IC.validate_contract(bad))


def test_exemption_only_for_pressures_with_rationale():
    bad = dataclasses.replace(C["ndvi"], applicability=IC.Applicability(
        ("terrestrial", "mixed"), "any", None, None, None, None, "exempt_landscape_pressure"))
    assert any("only a pressure indicator" in v for v in IC.validate_contract(bad))


def test_aquatic_contracts_require_10_pure_water_px_min_reference_bodies_and_water_body_feature():
    for n in ("tspi", "sabf", "wcpi", "sdi", "riparian_natural_veg_share"):
        c = C[n]
        assert c.applicability.floor_basis == "pure_water_pixels"
        assert c.applicability.requires_feature == "water_body"
        assert c.applicability.min_pure_water_pixels >= 10
        assert c.min_reference_n >= 10                                          # documented minimum comparable bodies
        assert c.reference_population in ("comparable_water_bodies", "comparable_riparian_rings")
    assert IC.WATER_BODY_AREA_RATIO == 3.0 and IC.WATER_BODY_PERMANENCE_TOL == 0.25


def test_tied_reference_forces_the_percentile_estimator():
    for n in ("forest_loss_rate", "natural_habitat", "net_forest_change_rate", "sabf", "sdi",
              "riparian_natural_veg_share"):
        assert C[n].estimator == "reference_percentile" and C[n].expects_tied_reference
    bad = dataclasses.replace(C["forest_loss_rate"], estimator="robust_z")
    assert any("never robust_z" in v for v in IC.validate_contract(bad))
    assert C["forest_loss_rate"].direction == "lower_is_better"                  # E1: lower loss = better


def test_scoreable_needs_documented_minimum_reference_n():
    bad = dataclasses.replace(C["ndvi"], min_reference_n=None)
    assert any("min_reference_n" in v for v in IC.validate_contract(bad))


def test_rci_replaced_and_net_change_uses_a_single_product():
    assert "riparian_natural_veg_share" in C and "rci" not in C
    assert "complexity" not in C["riparian_natural_veg_share"].definition.lower().split("replaces")[0]
    nf = C["net_forest_change_rate"]
    assert "hansen" not in nf.inputs and nf.inputs == ("dw_label",)             # D5: DW only, no cross-product
    assert nf.reference_population == "regional_ecoregion"                      # not stratified on the outcome


def test_every_named_synthetic_test_exists():
    text = "\n".join(p.read_text() for p in Path(__file__).parent.glob("test_*.py"))
    missing = [(n, t) for n, c in C.items() for t in c.synthetic_tests if f"def {t}(" not in text]
    assert missing == []
