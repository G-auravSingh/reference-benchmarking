from dataclasses import dataclass

from darukaa_adaptive.reference_profiles import (
    AQUATIC_LAKE_PROFILE, TERRESTRIAL_PROFILE, ReferenceSelectionPolicy
)


@dataclass
class Ref:
    automatic_enabled: bool = True
    least_disturbed_enabled: bool = True
    least_disturbed_quantile: float = 0.10
    manual_hmi_fallback_enabled: bool = True
    manual_hmi_threshold: float | None = None
    manual_hmi_reference_state: str = "best_attainable"


@dataclass
class Cfg:
    reference: Ref = __import__("dataclasses").field(default_factory=Ref)


def test_policy_is_finite_and_does_not_trade_ecology_for_hmi():
    p = ReferenceSelectionPolicy(Cfg())
    plan = p.stage_plan()
    assert [x["stage"] for x in plan] == [
        "strict_low_pressure", "least_disturbed_quantile", "manual_hmi_threshold"
    ]
    assert plan[0]["enabled"] is True
    assert plan[1]["enabled"] is True
    assert plan[2]["enabled"] is False
    d = p.ecological_gate_diagnostics(
        profile=AQUATIC_LAKE_PROFILE, passed=True,
        rule="ecoregion + hydrological regime",
        components={"water_occurrence": True},
    )
    assert d["ecological_hmi_tradeoff_used"] is False
    assert d["ecological_match_score_used_for_selection"] is False


def test_manual_stage_is_only_enabled_when_explicitly_configured():
    cfg = Cfg(Ref(manual_hmi_threshold=0.31))
    plan = ReferenceSelectionPolicy(cfg).stage_plan()
    assert plan[-1]["enabled"] is True
    assert plan[-1]["reference_state"] == "best_attainable"


def test_profiles_separate_realm_specific_ecological_gates():
    assert AQUATIC_LAKE_PROFILE.realm == "aquatic"
    assert TERRESTRIAL_PROFILE.realm == "terrestrial"
    assert AQUATIC_LAKE_PROFILE.ecological_gate != TERRESTRIAL_PROFILE.ecological_gate


def test_terrestrial_pressure_candidate_uses_valid_reference_state():
    import inspect
    from darukaa_adaptive.reference_engine import AutomaticReferenceEngine
    src=inspect.getsource(AutomaticReferenceEngine.terrestrial_pressure_reference_candidate)
    assert '"least_disturbed_contemporary"' in src
    assert 'ecologically_matched_contemporary_pressure_distribution' not in src
