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
            assert c.current_defects, f"{n}: a proposed indicator must list its implementation gap"


def test_proposed_scoreable_sets_by_domain():
    sc = {n for n, c in C.items() if c.proposed_scoreability == "scoreable"}
    terr = {n for n in sc if "terrestrial" in C[n].applicability.domains}
    aqua_only = {n for n in sc if "terrestrial" not in C[n].applicability.domains}
    assert terr == {"natural_habitat", "forest_loss_rate", "ndvi", "chm", "bii", "ghm", "hdi", "light_pollution"}
    assert aqua_only == {"tspi", "sabf", "wcpi", "sdi"}
    assert C["cpland"].proposed_scoreability == "pending_methodology"      # blocked on provenance
    shared = {n for n in sc if {"terrestrial", "aquatic"} <= set(C[n].applicability.domains)}
    assert shared == {"ghm", "hdi", "light_pollution"}


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
    ({"applicability": IC.Applicability(("terrestrial",), "any", None, None)}, "site-support rule"),  # X6
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
