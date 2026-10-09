
from darukaa_adaptive.registry import FULL_INDICATORS
from darukaa_adaptive.legacy_reference.indicators import create_default_registry

EXPECTED = {
"natural_habitat", "cpland", "forest_loss_rate", "kba_overlap", "ndvi", "habitat_health",
"flii", "eii", "eii_structural", "eii_compositional", "eii_functional", "bii", "msa", "star_t",
"aridity_index", "shdi", "lai", "chm", "endemic_richness", "endemic_plant_richness",
"threatened_richness", "threatened_plant_richness", "ghm", "light_pollution", "lst_day", "lst_night"
}

def test_full_inventory_is_exact_legacy_live_registry():
    assert {x.name for x in FULL_INDICATORS} == EXPECTED
    assert len(FULL_INDICATORS) == len(EXPECTED)
    assert len({x.name for x in FULL_INDICATORS}) == len(EXPECTED)

def test_full_inventory_matches_legacy_calculator_functions():
    legacy = create_default_registry()
    assert {x.name for x in legacy.all()} == {x.name for x in FULL_INDICATORS}
    for spec in legacy.all():
        assert callable(spec.extract_fn)
        assert spec.extract_fn.__name__.startswith("extract_")

def test_scored_metrics_require_reference_and_uncertainty():
    for spec in FULL_INDICATORS:
        if spec.scoring_role == "SCORED":
            assert spec.reference_allowed
            assert spec.reference_type
            assert spec.uncertainty_method not in ("", "none")


def test_retired_aquatic_composites_are_absent_from_active_registry():
    from darukaa_adaptive.registry import INDICATORS
    active = {x.name for x in INDICATORS}
    for name in ("rci", "jrc_water_persistence", "tspi", "wcpi", "wsdi", "hsas", "edpp", "mspl"):
        assert name not in active
