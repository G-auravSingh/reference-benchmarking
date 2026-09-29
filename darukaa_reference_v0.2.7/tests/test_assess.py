"""
Orchestrator tests (v0.2.8 smoke-test wiring): an offline FAKE provider drives assess_zone, so the control flow,
the audit-trail columns, the statuses and the "no wasted / no silent" guarantees are tested without Earth Engine.
The Earth Engine provider itself is verified live by the smoke test and parity harness, not here.
"""
import csv
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from darukaa_reference import assess as A
from darukaa_reference import benchmarking as B
from darukaa_reference import indicator_contract as IC
from darukaa_reference.indicators import create_default_registry

C = IC.CONTRACTS


class FakeProvider:
    """Deterministic provider: every implemented indicator gets a consistent site value + reference."""

    def __init__(self, evidence, site_values=None, n_ref=60, break_on=None):
        self._ev, self.calls, self.site_values, self.n_ref, self.break_on = evidence, [], site_values or {}, n_ref, break_on

    def evidence(self, zone):
        return self._ev

    def implemented(self, name):
        return name in A.IMPLEMENTED

    def site(self, name, zone, ev):
        self.calls.append(("site", name))
        if self.break_on == name:
            raise RuntimeError("boom")
        c = C[name]
        v = self.site_values.get(name, 55.0)
        spec = B.MetricSpec(name, "u", c.temporal, c.site_support, "site", native_scale_m=c.native_resolution_m)
        return A.SiteResult(v, "u", spec, {"m": 1})

    def references(self, name, zone, ev, site):
        self.calls.append(("reference", name))
        c = C[name]
        vals = np.random.default_rng(0).normal(50, 5, self.n_ref)
        win = ev.site_area_m2 if c.reference_support.startswith("site_window") else None
        if win and c.native_resolution_m:
            from darukaa_reference.support import cell_area_m2
            win = cell_area_m2(ev.site_area_m2, c.native_resolution_m)
        spec = B.MetricSpec(name, "u", c.temporal, c.reference_support, c.reference_population,
                            window_area_m2=win, native_scale_m=c.native_resolution_m)
        funnel = {"n_water_bodies_total": 30, "n_bodies_with_enough_pixels": 25, "n_rejected_size": 9,
                  "n_rejected_permanence": 4, "n_reference_bodies": self.n_ref}
        ref = B.ReferenceData(vals, spec, c.reference_tier, f"test population for {name}", {"funnel": funnel, "seed": 1})
        return {c.reference_tier: ref}


TERR = B.SiteEvidence("terrestrial", 4.0e5, frozenset({"woody"}), forest_baseline_m2=1e2)
AQUA = B.SiteEvidence("aquatic", 8.0e4, frozenset({"open_water"}), water_body_valid=True, n_pure_water_px=300)
ZT = A.Zone("EMU_test", None, "terrestrial", 296)
ZA = A.Zone("Lake_test", None, "aquatic", 296)


def rows_by(rows):
    return {r["indicator"]: r for r in rows}


def test_every_contract_gets_exactly_one_row_with_all_required_columns():
    rows = A.assess_zone(ZT, FakeProvider(TERR), log=lambda *a: None)
    assert [r["indicator"] for r in rows] == list(C)
    required = ["indicator", "status", "site_value", "site_unit", "site_support", "reference_population", "reference_n",
                "reference_unit", "reference_support", "benchmark", "scoring_method", "applicability_reason",
                "compatibility_checks", "provenance"]
    assert A.AUDIT_COLUMNS == required
    for r in rows:
        assert set(required) <= set(r) and r["status"] in IC.INDICATOR_STATUSES and r["status"] != "no_reference"
        json.loads(r["provenance"])                                        # provenance is valid JSON
        if r["status"] != "scored":
            assert r["reason"] or r["status"] in ("contextual_only", "screening_only"), r["indicator"]


def test_terrestrial_zone_statuses_and_no_wasted_reference_work():
    p = FakeProvider(TERR)
    rows = rows_by(A.assess_zone(ZT, p, log=lambda *a: None))
    scored = {n for n, r in rows.items() if r["status"] == "scored"}
    assert scored == {"natural_habitat", "net_tree_cover_change_rate", "ndvi", "chm", "bii", "ghm", "hdi", "light_pollution"}
    assert rows["forest_loss_rate"]["status"] == "not_applicable" and "baseline forest 0.01 ha < 5 ha" in rows["forest_loss_rate"]["applicability_reason"]
    for n in ("tspi", "sabf", "wcpi", "sdi"):
        assert rows[n]["status"] == "not_applicable" and "domain_mismatch" in rows[n]["applicability_reason"]
    assert rows["riparian_natural_veg_share"]["status"] == "not_applicable"           # no water body on the terrestrial zone
    assert rows["cpland"]["status"] == "pending_methodology" and rows["natural_landcover"]["status"] == "contextual_only"
    assert rows["kba_overlap"]["status"] == "screening_only"
    called = {n for _, n in p.calls}
    assert called == scored                                                             # NOTHING else touched Earth Engine
    assert all(rows[n]["reference_n"] == 60 for n in scored)
    assert rows["natural_habitat"]["scoring_method"].startswith("reference_percentile (higher_is_better")


def test_aquatic_zone_statuses_and_pending_construct():
    p = FakeProvider(AQUA)
    rows = rows_by(A.assess_zone(ZA, p, log=lambda *a: None))
    scored = {n for n, r in rows.items() if r["status"] == "scored"}
    assert scored == {"sabf", "wcpi", "sdi", "riparian_natural_veg_share", "ghm", "light_pollution", "hdi"}
    assert rows["tspi"]["status"] == "pending_methodology" and rows["tspi"]["reason"] == "v0.2.8_construct_not_implemented"
    for n in ("chm", "bii", "ndvi", "natural_habitat", "forest_loss_rate", "net_tree_cover_change_rate"):
        assert rows[n]["status"] == "not_applicable" and "domain_mismatch" in rows[n]["applicability_reason"]
    assert "tspi" not in {n for _, n in p.calls}                                       # not implemented: no Earth Engine work
    fun = json.loads(rows["sabf"]["reference_funnel"])
    assert {"n_water_bodies_total", "n_bodies_with_enough_pixels", "n_rejected_size", "n_rejected_permanence",
            "n_reference_bodies"} <= set(fun)                                          # decision 4: the whole funnel is exposed


def test_insufficient_reference_bodies_gives_the_explicit_status_and_keeps_the_funnel():
    rows = rows_by(A.assess_zone(ZA, FakeProvider(AQUA, n_ref=7), log=lambda *a: None))
    for n in ("sabf", "wcpi", "sdi", "riparian_natural_veg_share"):
        r = rows[n]
        assert r["status"] == "reference_available_but_not_scoreable" and r["reason"] == "insufficient_reference_n"
        assert r["reference_n"] == 7 and r["benchmark"] is None and "documented minimum 10" in r["detail"]
    assert rows["ghm"]["reference_n"] == 7 and rows["ghm"]["status"] == "reference_available_but_not_scoreable"   # 7 < 30


def test_compatibility_checks_are_listed_pass_or_fail():
    rows = rows_by(A.assess_zone(ZT, FakeProvider(TERR), log=lambda *a: None))
    chk = rows["natural_habitat"]["compatibility_checks"]
    for name in B.COMPATIBILITY_CHECKS:
        assert f"{name}=PASS" in chk, chk


def test_a_provider_failure_becomes_an_explicit_status_never_a_hole():
    rows = rows_by(A.assess_zone(ZT, FakeProvider(TERR, break_on="chm"), log=lambda *a: None))
    r = rows["chm"]
    assert r["status"] == "applicable_but_no_site_value" and r["reason"].startswith("provider_error: RuntimeError") and "boom" in r["detail"]
    assert rows["ndvi"]["status"] == "scored"                                          # the rest of the zone is unaffected


def test_missing_site_value_means_no_reference_is_computed():
    p = FakeProvider(TERR, site_values={"ndvi": None})
    p.site_values["ndvi"] = None
    orig = p.site
    p.site = lambda n, z, e: (A.SiteResult(None, "u", None) if n == "ndvi" else orig(n, z, e))
    rows = rows_by(A.assess_zone(ZT, p, log=lambda *a: None))
    assert rows["ndvi"]["status"] == "applicable_but_no_site_value" and ("reference", "ndvi") not in p.calls


def test_validation_zone_is_labelled_in_the_audit_trail():
    z = A.Zone("external_forest", None, "terrestrial", 1, validation_label="external forested validation polygon (not Tata)")
    ev = B.SiteEvidence("terrestrial", 4e5, frozenset({"woody"}), forest_baseline_m2=3e5)
    rows = rows_by(A.assess_zone(z, FakeProvider(ev), log=lambda *a: None))
    r = rows["forest_loss_rate"]
    assert r["status"] == "scored" and "methodological_validation_dataset" in r["flags"]
    assert json.loads(r["provenance"])["methodological_validation_dataset"].startswith("external forested")


def test_writers_produce_csv_json_and_markdown(tmp_path):
    rows = A.assess_zone(ZT, FakeProvider(TERR), log=lambda *a: None)
    paths = A.write_audit(rows, str(tmp_path), "EMU_test")
    got = list(csv.DictReader(open(paths["csv"], encoding="utf-8")))
    assert len(got) == len(C) and got[0]["indicator"] in C
    assert list(got[0].keys())[:14] == A.AUDIT_COLUMNS
    js = json.load(open(paths["json"], encoding="utf-8"))
    assert js["summary"]["scored"] == 8 and len(js["rows"]) == len(C)
    assert "| indicator | status |" in open(paths["md"], encoding="utf-8").read()


# ------------------------------------------------------------------ the Earth Engine provider: structure only
def test_every_scoreable_contract_is_either_implemented_or_reported_pending():
    scoreable = {n for n, c in C.items() if c.proposed_scoreability == "scoreable"}
    assert scoreable - A.IMPLEMENTED == {"tspi"}                                       # tspi is Phase 4
    assert A.IMPLEMENTED <= scoreable
    for n in A.WINDOW_NAMES + (A.FOREST_NAME,):
        assert C[n].reference_support.startswith("site_window")
    for n in A.AQUATIC_NAMES:
        assert C[n].reference_support in ("water_body_unit", "riparian_ring_unit")


def test_ee_provider_dispatch_uses_native_scale_utm_and_the_shared_population_code(monkeypatch):
    ee = MagicMock()
    reg = create_default_registry()
    sel = MagicMock()
    lc = MagicMock()
    lc.reduceRegion.return_value.getInfo.return_value = {"label": 1}                    # the site's land-cover class
    sel._build_ecoregion_landcover_image.return_value = (lc, {})
    sel._dynamic_hmi_threshold.return_value = 0.0488
    from darukaa_reference.config import Config
    prov = A.EEProvider(Config(), reg, ee=ee, selector=sel, log=lambda *a: None)
    prov._ctx["z"] = {"eg": MagicMock(), "crs": "EPSG:32643", "area": 4.0e5}
    zone = A.Zone("z", None, "terrestrial", 296)
    rz, mask, pdef, diag = prov._population(zone, "least_disturbed_stratum", 50.0)
    assert mask is not None and "ecoregion ECO_ID=296" in pdef and "HMI <= 0.0488" in pdef and diag["hmi_threshold"] == 0.0488
    sel._dynamic_hmi_threshold.assert_called_once()                                    # the SAME threshold code as the v0.2.7 live runs
    rz, mask, pdef, diag = prov._population(zone, "regional_stratum_unfiltered", 50.0)
    assert "NO pressure (HMI) filter" in pdef and "hmi_threshold" not in diag
    rz, mask, pdef, diag = prov._population(zone, "regional_ecoregion", 50.0)
    assert "Dynamic World land-cover class" not in pdef and "ecoregion ECO_ID=296" in pdef      # no stratum on the outcome
    rz, mask, pdef, diag = prov._population(zone, "regional_all", 50.0)
    assert mask is None and "ecoregion" not in pdef
    no_eco = A.Zone("z", None, "terrestrial", None)
    assert "warning" in prov._population(no_eco, "regional_ecoregion", 50.0)[3]        # missing ecoregion is never silent


# ================================================================== evidence: probe outcomes and persisted diagnostics
def _provider_with_probe(monkeypatch, probe_result=None, raises=None):
    import darukaa_reference.indicators as I
    from darukaa_reference import reference_builders_ee as RB
    from shapely.geometry import box as sbox
    from darukaa_reference.config import Config
    ee = MagicMock()
    ee.Image.constant.return_value.updateMask.return_value.reproject.return_value.reduceRegion.return_value.getInfo.return_value = {"constant": 458.0}
    monkeypatch.setattr(I, "_to_ee", lambda g: MagicMock(area=lambda m: MagicMock(getInfo=lambda: 84700.0)))
    monkeypatch.setattr(I, "_dw_mode", lambda c: MagicMock())
    monkeypatch.setattr(I, "_s2_masked", lambda c: MagicMock())
    monkeypatch.setattr(I, "_forest_baseline_and_loss", lambda eg, c: (None, None, MagicMock(getInfo=lambda: 12.0)))
    def probe(*a, **k):
        if raises:
            raise raises
        return probe_result
    monkeypatch.setattr(RB, "water_body_reference_ee", probe)
    prov = A.EEProvider(Config(), create_default_registry(), ee=ee, selector=MagicMock(), log=lambda *a: None)
    zone = A.Zone("Lake_test", sbox(73.809, 18.640, 73.812, 18.643), "aquatic", 296)
    return prov, zone


def test_evidence_records_a_found_water_body_with_all_diagnostics(monkeypatch):
    target = {"uid": "u", "n_px": 458, "area_m2": 45800.0, "geodesic_area_m2": 45962.0, "pure_px": 340, "bbox": (1, 2, 3, 4), "cx": 5.0, "cy": 6.0, "interior": True}
    prov, zone = _provider_with_probe(monkeypatch, {"valid": True, "invalid_reason": "", "target": target, "n_pure_water_px": 340,
                                                    "diagnostics": {"probe": [{"margin_m": 500.0}], "max_extent_m": 2000.0}})
    ev = prov.evidence(zone)
    assert ev.water_probe == "ok" and ev.water_body_valid and ev.n_pure_water_px == 340 and "open_water" in ev.ecosystem_tags
    d = ev.diagnostics
    assert d["water_mask"]["water_area_in_site_m2"] == 45800.0 and d["water_body_probe"]["target"]["pure_px"] == 340
    assert d["ecosystem_classification"]["open_water"] is True and "MNDWI" in d["water_mask"]["definition"]
    meta = {}
    A.assess_zone(zone, prov, only=["sabf"], log=lambda *a: None, meta_out=meta)
    assert meta["evidence"]["n_pure_water_px"] == 340 and meta["evidence"]["diagnostics"]["crs"] == "EPSG:32643"      # persisted for the audit JSON


def test_evidence_probe_exception_is_an_error_with_the_message_not_a_silent_no_water(monkeypatch):
    prov, zone = _provider_with_probe(monkeypatch, raises=RuntimeError("User memory limit exceeded."))
    ev = prov.evidence(zone)
    assert ev.water_probe == "error" and not ev.water_body_valid and "memory limit" in ev.water_probe_detail
    assert "memory limit" in ev.diagnostics["errors"]["water_probe"]
    rows = {r["indicator"]: r for r in A.assess_zone(zone, prov, log=lambda *a: None)}
    assert rows["sabf"]["status"] == "applicable_but_no_site_value" and rows["sabf"]["reason"] == "applicability_undetermined"


def test_evidence_distinguishes_no_water_from_insufficient_pure_water_and_inconclusive(monkeypatch):
    prov, zone = _provider_with_probe(monkeypatch, {"valid": False, "invalid_reason": "no_water_body_in_site", "target": None, "diagnostics": {"probe": []}})
    ev = prov.evidence(zone)
    assert ev.water_probe == "no_water_body" and not ev.water_body_valid
    prov, zone = _provider_with_probe(monkeypatch, {"valid": False, "invalid_reason": "insufficient_pure_water", "n_pure_water_px": 4,
                                                    "target": {"uid": "u", "n_px": 30, "area_m2": 3000.0, "pure_px": 4, "bbox": (0, 0, 60, 60), "cx": 1, "cy": 1, "interior": True},
                                                    "diagnostics": {"probe": []}})
    ev = prov.evidence(zone)
    assert ev.water_probe == "ok" and ev.water_body_valid and ev.n_pure_water_px == 4 and "open_water" not in ev.ecosystem_tags
    prov, zone = _provider_with_probe(monkeypatch, {"valid": False, "invalid_reason": "target_truncated_at_region_edge", "target": None, "diagnostics": {"probe": []}})
    ev = prov.evidence(zone)
    assert ev.water_probe == "error" and "inconclusive" in ev.water_probe_detail


def test_site_values_are_coverage_weighted_never_unweighted():
    import inspect
    src = inspect.getsource(A.EEProvider._site_mean)
    assert "Reducer.mean()" in src and "unweighted" not in src                        # frozen convention: coverage-weighted polygon mean
    from darukaa_reference import support as S
    assert S.SITE_SUPPORT_CONVENTION == "polygon_coverage_weighted"


# ================================================================== forest validation zone (never invented; measured live)
def test_forest_validation_zone_is_chosen_by_measured_baseline_and_loss_and_labelled(monkeypatch):
    import darukaa_reference.indicators as I
    from shapely.geometry import box as sbox
    from darukaa_reference.config import Config
    zones = [A.Zone("small_no_forest", sbox(0, 0, .1, .1), "terrestrial"), A.Zone("forest_a", sbox(1, 1, 1.1, 1.1), "terrestrial"),
             A.Zone("forest_b", sbox(2, 2, 2.1, 2.1), "terrestrial"), A.Zone("no_loss", sbox(3, 3, 3.1, 3.1), "terrestrial"),
             A.Zone("errors", sbox(4, 4, 4.1, 4.1), "terrestrial")]
    stats = {"small_no_forest": (0.01, 0.0, 40.0), "forest_a": (150.0, 4.0, 300.0), "forest_b": (90.0, 9.0, 200.0), "no_loss": (200.0, 0.0, 250.0), "errors": (0.0, 0.0, 10.0)}
    cur = {}
    def to_ee(g):
        cur["k"] = next(z.label for z in zones if z.geometry.equals(g))
        return MagicMock(area=lambda m: MagicMock(getInfo=lambda: stats[cur["k"]][2] * 1e4))
    def fbl(eg, cfg):
        if cur["k"] == "errors":
            raise RuntimeError("Computation timed out.")
        b, l, _ = stats[cur["k"]]
        return (None, None, MagicMock(getInfo=lambda: b * 1e4), None, "p", {"p": MagicMock(getInfo=lambda: l * 1e4)})
    monkeypatch.setattr(I, "_to_ee", to_ee); monkeypatch.setattr(I, "_forest_baseline_and_loss", fbl)
    prov = MagicMock(); prov.config = Config()
    best, table = A.select_forest_validation_zone(prov, zones, log=lambda *a: None)
    assert best.label == "forest_b" and best.validation_label == A.FOREST_VALIDATION_LABEL          # largest loss among eligible
    by = {r["label"]: r for r in table}
    assert not by["small_no_forest"]["eligible"] and not by["no_loss"]["eligible"] and by["forest_a"]["eligible"]
    assert "timed out" in by["errors"]["error"] and not by["errors"]["eligible"]
    none, _ = A.select_forest_validation_zone(prov, [zones[0], zones[3]], log=lambda *a: None)
    assert none is None                                                                            # nothing eligible: report, never invent


def test_find_candidate_tiles_reads_only_existing_assets(tmp_path):
    import geopandas as gpd
    from shapely.geometry import box as sbox
    d = tmp_path / "x" / "projects" / "FCF_GV" / "outputs" / "07_reference_handoff" / "tiles"; d.mkdir(parents=True)
    gpd.GeoDataFrame(geometry=[sbox(84.4, 19.7, 84.42, 19.72)], crs=4326).to_file(d / "FCF_GV_EMU_Ganjam_1.geojson", driver="GeoJSON")
    rows = A.find_candidate_tiles(str(tmp_path))
    assert [r["label"] for r in rows] == ["FCF_GV_EMU_Ganjam_1"] and rows[0]["area_ha"] > 0
    assert A.find_candidate_tiles(str(tmp_path / "nothing")) == []


# ================================================================== aquatic permanence: one definition for every aquatic indicator
def test_every_aquatic_indicator_matches_on_the_same_permanence_source(monkeypatch):
    """Run 2 unintended mismatch: ring indicators 0.031 vs water indicators ~0.9. All four must receive the SAME canonical permanence image."""
    import darukaa_reference.indicators as I
    from darukaa_reference import reference_builders_ee as RB
    from shapely.geometry import box as sbox
    from darukaa_reference.config import Config
    sentinel = object()
    monkeypatch.setattr(I, "_s1_water_occurrence", lambda c: sentinel)
    for fn in ("_img_sabf", "_img_wcpi", "_img_sdi", "_img_natural_veg", "_s2_masked"):
        monkeypatch.setattr(I, fn, lambda c: MagicMock())
    monkeypatch.setattr(RB, "water_mask_s2", lambda comp: MagicMock())
    seen = {}
    def fake(*a, **k):
        seen[k["construct"]] = k
        return {"valid": True, "invalid_reason": "", "target": {"permanence": 0.9}, "diagnostics": {}}
    monkeypatch.setattr(RB, "water_body_reference_ee", fake)
    prov = A.EEProvider(Config(), create_default_registry(), ee=MagicMock(), selector=MagicMock(), log=lambda *a: None)
    zone = A.Zone("Z", sbox(73.8, 18.6, 73.81, 18.61), "aquatic", 296)
    prov._ctx[zone.label] = {"eg": MagicMock(), "crs": "EPSG:32643", "area": 1e5, "centre_xy": (0.0, 0.0), "site_bounds_utm": (0, 0, 1, 1)}
    for n in ("sabf", "wcpi", "sdi", "riparian_natural_veg_share"):
        prov._water_body(n, zone, True)
    assert set(seen) == {"sabf", "wcpi", "sdi", "riparian_natural_veg_share"}
    assert all(k["permanence_image"] is sentinel for k in seen.values())                                # one source for all four
    assert seen["sdi"]["kind"] == seen["riparian_natural_veg_share"]["kind"] == "ring" and seen["sabf"]["kind"] == "water"
    assert prov.aquatic_permanence(zone) == {n: 0.9 for n in seen}


def test_the_audit_meta_records_target_permanence_per_indicator_and_flags_a_spread():
    class P:
        def __init__(self, perm): self.perm = perm
        def aquatic_permanence(self, zone): return self.perm
        # minimal provider surface used by assess_zone with only=[] (no indicators run)
        def evidence(self, zone): return B.SiteEvidence("aquatic", 1e5, water_body_valid=True, n_pure_water_px=100, water_probe="ok")
    logs = []
    for perm, ok in (({"sabf": 0.884, "wcpi": 0.910, "sdi": 0.905, "riparian_natural_veg_share": 0.91}, True),
                     ({"sabf": 0.884, "wcpi": 0.910, "sdi": 0.031, "riparian_natural_veg_share": 0.031}, False)):        # the run-2 pattern
        meta = {}
        A.assess_zone(A.Zone("Z", None, "aquatic"), P(perm), only=[], log=logs.append, meta_out=meta)
        m = meta["aquatic_permanence"]
        assert m["consistent"] is ok and m["target_permanence_by_indicator"] == perm and abs(m["spread"] - (max(perm.values()) - min(perm.values()))) < 1e-12
    assert any("WARNING: aquatic target permanence differs" in l for l in logs)


from darukaa_reference import benchmarking as B   # noqa: E402  (used by the fake provider above)
