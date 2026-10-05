
from darukaa_adaptive.registry import FULL_INDICATORS
from darukaa_adaptive.legacy_reference.indicators import create_default_registry

EXPECTED = {
"natural_habitat","natural_landcover","cpland","forest_loss_rate","net_forest_change_rate",
"kba_overlap","ndvi","habitat_health","flii","eii","eii_structural","eii_compositional",
"eii_functional","bii","pdf","aridity_index","tspi","sabf","wcpi","wsdi","hsas","edpp",
"mspl","rci","riparian_ndvi_trend","jrc_water_persistence","shdi","lai","chm",
"endemic_richness","shi","flagship_habitat","endemic_plant_richness","threatened_richness",
"ceri","star_t","threatened_plant_richness","ghm","light_pollution","hdi","lst_day",
"lst_night","sdi","stsi","iri","ivsi"
}

def test_full_inventory_is_exact_legacy_live_registry():
    assert {x.name for x in FULL_INDICATORS} == EXPECTED
    assert len(FULL_INDICATORS) == 46
    assert len({x.name for x in FULL_INDICATORS}) == 46

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


def test_water_specific_legacy_metrics_are_not_applicable_to_terrestrial():
    from darukaa_adaptive.registry import get_indicator_spec
    assert "terrestrial" not in get_indicator_spec("rci").applicable_realms
    assert "terrestrial" not in get_indicator_spec("jrc_water_persistence").applicable_realms
