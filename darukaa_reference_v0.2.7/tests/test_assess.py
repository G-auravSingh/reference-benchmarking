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
