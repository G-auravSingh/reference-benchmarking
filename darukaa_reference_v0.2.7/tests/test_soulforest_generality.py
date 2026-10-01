"""
SoulForest is the second project-level generality test: the SAME pipeline, driven only by its manifest (7 zones, all declared terrestrial), with no project-specific code.
Offline here (fake Earth Engine); the live run follows the Tata live integration test.
"""
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _fake_engine as F
from darukaa_reference import benchmarking as B
from darukaa_reference import engine_pipeline as EP
from darukaa_reference import manifest as M
from darukaa_reference.config import Config
from darukaa_reference.indicators import create_default_registry

REPO = Path(__file__).resolve().parents[2]
NB = dict(gee_project='gaurav-singh-007', output_dir='outputs', archetype='industrial', realm='terrestrial', assessment_mode='baseline',
          hmi_hard_ceiling=0.05, use_variance_stability_floor=True, reference_stratification='ecoregion_landcover')
LABELS = ["EMU_ANCHOR_Fruit_Forest", "EMU_ANCHOR_Rock_Guild", "EMU_ANCHOR_Wetland", "SEG01", "SEG02", "SEG03", "SEG04"]


class WetlandWithWater(F.FakeEngineProvider):
    """The wetland zone has a measurable water body in the evidence (so water-adjacent rules COULD apply); every other zone has none."""
    def evidence(self, zone):
        ev = super().evidence(zone)
        if zone.label == "EMU_ANCHOR_Wetland":
            ev.water_body_valid, ev.n_pure_water_px, ev.water_probe = True, 50, "ok"
            ev.ecosystem_tags = frozenset(set(ev.ecosystem_tags) | {"open_water"})
        return ev


def run(tmp, factory):
    logging.disable(logging.CRITICAL)
    try:
        name, specs = M.resolve_zone_specs(M.find_manifest_by_project_name(REPO, "SoulForest_Veltoor"), REPO)
        return EP.run_engine_project(Config(**NB), create_default_registry(), name, specs, str(tmp), provider_factory=factory, zone_loader=F.stub_zone_loader,
                                     strict_provenance=False, log=lambda *a, **k: None)
    finally:
        logging.disable(logging.NOTSET)


@pytest.fixture(scope="module")
def soul(tmp_path_factory):
    return run(tmp_path_factory.mktemp("soul"), F.fake_factory)


@pytest.fixture(scope="module")
def soul_wet(tmp_path_factory):
    return run(tmp_path_factory.mktemp("soul_wet"), lambda c, r: WetlandWithWater(c, r))


def test_seven_zones_all_terrestrial_declared_by_the_manifest(soul):
    assert list(soul["zones"]) == LABELS and {z["realm"] for z in soul["zones"].values()} == {"terrestrial"}
    assert set(soul["meta"]["realm_sources"].values()) == {"manifest"} and not soul["meta"]["companion_sources"]
    assert list(soul["realms"]) == ["terrestrial"] and "aquatic" not in soul["realms"] and soul["meta"]["n_zones_failed"] == 0


def test_every_zone_has_46_rows_and_only_terrestrial_domain_indicators_apply(soul):
    for z in soul["zones"].values():
        assert len(z["rows"]) == 46
        for r in z["rows"]:
            if r["indicator"] in ("sabf", "wcpi", "sdi", "tspi"):
                assert (r["status"], r["reason"]) == ("not_applicable", "domain_mismatch"), (z["label"], r["indicator"])


def test_the_aquatic_only_indicators_never_apply_to_any_soulforest_zone_even_the_wetland_with_water(soul_wet):
    wet = soul_wet["zones"]["EMU_ANCHOR_Wetland"]
    assert wet["realm"] == "terrestrial" and "aquatic" not in soul_wet["realms"]
    for r in wet["rows"]:
        if r["indicator"] in ("sabf", "wcpi", "sdi", "tspi"):
            assert (r["status"], r["reason"]) == ("not_applicable", "domain_mismatch")


def test_the_wetland_can_activate_the_water_adjacent_indicator_where_the_contract_allows_it(soul, soul_wet):
    """`riparian_natural_veg_share` is in the terrestrial domain of the frozen contract: with a water body in the evidence it is applicable and scored, still inside the
    TERRESTRIAL realm; without one it is target_feature_absent. The pipeline adds no rule of its own."""
    r_with = next(r for r in soul_wet["zones"]["EMU_ANCHOR_Wetland"]["rows"] if r["indicator"] == "riparian_natural_veg_share")
    r_without = next(r for r in soul["zones"]["EMU_ANCHOR_Wetland"]["rows"] if r["indicator"] == "riparian_natural_veg_share")
    assert r_with["status"] == "scored" and r_with["realm"] == "terrestrial"
    assert (r_without["status"], r_without["reason"]) == ("not_applicable", "target_feature_absent")
    agg = soul_wet["realms"]["terrestrial"]["aggregation"]["per_indicator"]["riparian_natural_veg_share"]
    assert agg["status"] == "ok" and agg["zone_scores"].keys() == {"EMU_ANCHOR_Wetland"} and agg["n_zones_scored"] == 1 and agg["n_zones_in_realm"] == 7


def test_small_zones_are_excluded_by_the_support_floor_with_the_reason_kept_never_scored_as_zero(soul):
    rock = soul["zones"]["EMU_ANCHOR_Rock_Guild"]                                        # 0.17 ha
    floors = [r for r in rock["rows"] if r["reason"] == "site_below_product_resolution"]
    assert floors and all(r["status"] == "not_applicable" and r["score"] is None and r["site_value"] is None for r in floors)
    assert rock["coverage"]["n_scored"] < soul["zones"]["SEG01"]["coverage"]["n_scored"] + 1
    ind = soul["realms"]["terrestrial"]["aggregation"]["per_indicator"]
    for i in ind.values():
        for e in i["excluded_zones"]:
            assert e["status"] and (e["reason"] is not None)


def test_the_headline_for_soulforest_carries_coverage_and_the_score_explainer(soul):
    h = soul["realms"]["terrestrial"]["headline"]
    assert h["score_scale"].startswith("Benchmark score (0-1)") and "NOT a percentage" in h["score_scale"]
    assert set(h["pillar_zone_coverage"]) == {"C1_landscape", "C2_vegetation", "C3_fauna", "C4_pressure"}
    if h["pillar_zone_coverage"]["C3_fauna"]["zones_scored"] < 7:
        assert "C3_fauna evidenced in" in h["coverage_caveat"]
    assert "_pct" not in str(h)


def test_every_output_is_written_for_the_project_and_carries_the_frozen_engine_identity(tmp_path):
    rep = run(tmp_path, F.fake_factory)
    for label in LABELS:
        assert all((tmp_path / f"{label}_audit.{e}").exists() for e in ("json", "csv", "md"))
    assert all((tmp_path / f"SoulForest_Veltoor_project.{e}").exists() for e in ("json", "csv", "html"))
    assert rep["meta"]["engine"]["engine_matches_frozen"] is True and rep["meta"]["pipeline_version"] == EP.PIPELINE_VERSION
    html = (tmp_path / "SoulForest_Veltoor_project.html").read_text()
    assert "Terrestrial realm" in html and "Aquatic realm" not in html
