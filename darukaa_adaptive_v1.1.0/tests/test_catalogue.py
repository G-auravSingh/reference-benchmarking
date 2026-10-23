import pytest

from darukaa_adaptive import catalogue as cat


def test_every_contract_is_complete():
    assert cat.validate_catalogue() == []


def test_ids_are_unique():
    ids = [c.id for c in cat.CATALOGUE]
    assert len(ids) == len(set(ids))


def test_recommended_scored_counts_per_pillar():
    roles = cat.resolve_roles("recommended")
    assert len(cat.scored_ids(roles, "P1")) == 4
    assert set(cat.scored_ids(roles, "P2")) == {"ndvi_peak_season", "lai_s2", "canopy_height_m", "bii", "eii_functional", "flii"}
    assert cat.scored_ids(roles, "P3") == []          # licence-restricted: not covered (D-23-13)
    assert set(cat.scored_ids(roles, "P4")) == {"built_fraction", "ghm", "road_density", "fire_frequency", "night_lights"}
    assert cat.scored_ids(roles, "M") == []


def test_all_scoreable_mode_scores_every_scoreable_metric_but_respects_exclusive_groups():
    roles = cat.resolve_roles("all_scoreable")
    for c in cat.active():
        if not c.can_score:
            assert roles[c.id].applied_role != "scored", c.id
    # only one EII layer and one modelled-intactness layer may be scored
    eii_scored = [m for m in ("eii_functional", "eii", "eii_structural") if roles[m].applied_role == "scored"]
    assert eii_scored == ["eii_functional"]
    assert roles["bii"].applied_role == "scored" and roles["msa"].applied_role == "contextual"
    assert "exclusive group" in roles["msa"].reason
    # deviations from the recommendation are recorded
    assert roles["gedi_rh98_m"].deviates and roles["gedi_rh98_m"].applied_role == "scored"


def test_override_cannot_promote_unscoreable_metric():
    roles = cat.resolve_roles("recommended", {"species_records_screen": "scored", "msa": "scored", "bii": "contextual"})
    assert roles["species_records_screen"].applied_role == "screening"
    assert "refused" in roles["species_records_screen"].reason
    assert roles["msa"].applied_role == "scored"          # bii demoted, so msa is the group's scored member
    assert roles["bii"].applied_role == "contextual"


def test_unknown_override_fails_loudly():
    with pytest.raises(KeyError):
        cat.resolve_roles("recommended", {"not_a_metric": "scored"})
    with pytest.raises(ValueError):
        cat.resolve_roles("recommended", {"bii": "maybe"})


def test_managed_land_never_feeds_condition_and_condition_is_natural_only():
    for c in cat.CATALOGUE:
        if c.pillar == "P2" and c.can_score:
            assert c.natural_only
        if c.pillar == "M":
            assert c.recommended_role != "scored"


def test_kba_and_protected_areas_are_kept():
    assert cat.get("kba_overlap_pct").recommended_role == "screening"
    assert cat.get("protected_area_overlap_pct").recommended_role == "screening"


def test_proposed_metrics_are_excluded_until_approved():
    ids = {c.id for c in cat.active()}
    assert "built_up_within_1km_pct" not in ids
    assert "built_up_within_1km_pct" in {c.id for c in cat.active(include_proposed=True)}


def test_every_metric_is_preparatory_and_names_dataset_licence():
    for c in cat.CATALOGUE:
        assert c.granularity == "preparatory"
        for d in c.datasets:
            assert d.licence and d.source_label in {"STD", "ACAD", "VENDOR", "DARUKAA"}
