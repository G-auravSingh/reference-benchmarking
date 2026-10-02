"""
ACCEPTANCE: the integrated pipeline must reproduce the already-completed standalone v0.2.8 Tata results (15 zones, 690 rows) for the same zone, indicator, site value,
reference value, reference n, benchmark, score, status and reason, within the documented numerical tolerance.

How this is established offline, and what it does and does not prove
--------------------------------------------------------------------
* The standalone audits keep n, median, MAD, benchmark and score, but NOT the reference arrays, so the engine's own arithmetic cannot be replayed offline.
  The engine is therefore proven UNCHANGED instead (test_engine_identity: byte-identical engine files + engine fingerprint) and CALLED IDENTICALLY (entry point,
  arguments, zone, realm, order: below).
* Everything the pipeline owns -- manifest -> zones, the engine call, audit-file writing, the adapter, per-realm aggregation, coverage, headline, CSV, HTML --
  is exercised end to end with the engine replaced, at the single boundary it crosses (`assess_zone`), by a replay returning EXACTLY the standalone rows.
* The end-to-end engine call on Earth Engine is the separate live integration test.

NUMERICAL TOLERANCE: the pipeline performs no arithmetic on engine values (it copies them), so integers, strings and None must be IDENTICAL and floats must match to
REL_TOL = 1e-12 (JSON serialisation round-trip only). Aggregated figures are recomputed independently below and compared to 1e-12 as well.
"""
import copy
import json
import logging
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _fake_engine as F
from darukaa_reference import assess as A
from darukaa_reference import engine_pipeline as EP
from darukaa_reference import indicator_contract as IC
from darukaa_reference import manifest as M
from darukaa_reference import engine_profile, son_score
from darukaa_reference.config import Config
from darukaa_reference.indicators import create_default_registry

REPO = Path(__file__).resolve().parents[2]
FIX = Path(__file__).resolve().parent / "fixtures" / "tata_v0_2_8_standalone"
REL_TOL = 1e-12
NB = dict(gee_project='gaurav-singh-007', output_dir='outputs', archetype='industrial', realm='terrestrial', assessment_mode='baseline',
          hmi_hard_ceiling=0.05, use_variance_stability_floor=True, reference_stratification='ecoregion_landcover')
COMPARED = ("zone", "realm", "indicator", "status", "reason", "detail", "site_value", "site_unit", "reference_n", "reference_median", "reference_mad", "benchmark", "score",
            "scoring_method", "direction", "reference_tier", "reference_population", "applicability_reason", "flags", "provenance", "diagnostics")


def standalone():
    out = {}
    for f in sorted(FIX.glob("*_audit.json")):
        d = json.loads(f.read_text())
        out[d["rows"][0]["zone"]] = d
    return out


def same(a, b):
    if a is None or b is None:
        return a is b
    if isinstance(a, bool) or isinstance(b, bool) or isinstance(a, str) or isinstance(b, str):
        return a == b
    if isinstance(a, int) and isinstance(b, int):
        return a == b
    return math.isclose(float(a), float(b), rel_tol=REL_TOL, abs_tol=0.0)


@pytest.fixture(scope="module")
def parity_run(tmp_path_factory):
    logging.disable(logging.CRITICAL)
    SA = standalone()
    calls = []

    def replay(zone, provider, contracts=None, require_validated=False, config=None, log=print, only=None, meta_out=None):
        calls.append({"label": zone.label, "realm": zone.realm, "config": config, "only": only, "contracts": contracts, "require_validated": require_validated,
                      "has_geometry": zone.geometry is not None and not zone.geometry.is_empty})
        if meta_out is not None:
            meta_out.update(copy.deepcopy(SA[zone.label]["meta"]))
        return copy.deepcopy(SA[zone.label]["rows"])
    real = A.assess_zone
    A.assess_zone = replay
    out = tmp_path_factory.mktemp("parity")
    cfg = Config(**NB)
    name, specs = M.resolve_zone_specs(M.find_manifest_by_project_name(REPO, "TataMotors_Pimpri"), REPO)
    try:
        rep = EP.run_engine_project(cfg, create_default_registry(), name, specs, str(out), provider_factory=lambda c, r: object(), zone_loader=F.stub_zone_loader,
                                    strict_provenance=False, log=lambda *a, **k: None)
    finally:
        A.assess_zone = real
        logging.disable(logging.NOTSET)
    return {"report": rep, "out": out, "SA": SA, "calls": calls, "cfg": cfg, "specs": specs}


def test_the_standalone_fixture_is_the_complete_15_zone_690_row_production_result():
    SA = standalone()
    assert len(SA) == 15 and sum(len(d["rows"]) for d in SA.values()) == 690 and all(len(d["rows"]) == 46 for d in SA.values())
    v = json.loads((FIX / "verification_report.json").read_text())
    assert v["n_audits"] == 15 and v["verification"]["ok"] is True and len(v["zones_terrestrial"]) == 9 and len(v["zones_aquatic"]) == 6


def test_the_pipeline_calls_the_engine_once_per_zone_with_the_standalone_zone_realm_and_arguments(parity_run):
    calls, SA, cfg = parity_run["calls"], parity_run["SA"], parity_run["cfg"]
    assert sorted(c["label"] for c in calls) == sorted(SA) and len(calls) == 15
    for c in calls:
        assert c["realm"] == SA[c["label"]]["rows"][0]["realm"], c["label"]                     # the realm the standalone run used for this zone
        assert c["config"] is cfg and c["only"] is None and c["contracts"] is None and c["require_validated"] is False and c["has_geometry"]
    legacy = {}
    for proj in ("TataMotors_Pimpri", "TataMotors_Pimpri_Aquatic"):
        mp = M.find_manifest_by_project_name(REPO, proj)
        man = M.load_manifest(mp)
        legacy.update(dict(zip(man["tile_labels"], M.resolve_tile_paths(man, mp))))
    assert {s.label: s.path for s in parity_run["specs"]} == legacy                                # the same tile files the standalone notebook resolved


def test_every_audit_file_the_pipeline_wrote_holds_exactly_the_standalone_rows(parity_run):
    for label, d in parity_run["SA"].items():
        written = json.loads((parity_run["out"] / f"{label}_audit.json").read_text())
        assert written["rows"] == d["rows"], label                                              # identical, key for key (provenance block of the FILE is new, rows are not)
        assert written["meta"]["evidence"] == d["meta"]["evidence"]
        assert written["provenance"]["engine"]["engine_closure_sha256_at_import"] == written["provenance"]["engine"]["frozen_engine_closure_sha256"]


def test_zone_indicator_site_reference_benchmark_score_status_and_reason_reproduce_for_all_690_rows(parity_run):
    rep, SA = parity_run["report"], parity_run["SA"]
    n = 0
    for label, d in SA.items():
        got = {r["indicator"]: r for r in rep["zones"][label]["rows"]}
        assert set(got) == {r["indicator"] for r in d["rows"]}
        for src in d["rows"]:
            r = got[src["indicator"]]
            for k in COMPARED:
                assert same(r[k], src[k]), (label, src["indicator"], k, r[k], src[k])
            n += 1
    assert n == 690


def test_status_counts_over_the_whole_project_are_the_standalone_counts(parity_run):
    from collections import Counter
    rep, SA = parity_run["report"], parity_run["SA"]
    want = Counter(r["status"] for d in SA.values() for r in d["rows"])
    got = Counter(r["status"] for z in rep["zones"].values() for r in z["rows"])
    assert got == want and got["scored"] == 89 and got["applicable_but_no_site_value"] == 1 and got["not_applicable"] == 319


def test_realm_aggregation_reproduces_an_independent_worst_zone_derivation(parity_run):
    rep, SA = parity_run["report"], parity_run["SA"]
    for realm in ("terrestrial", "aquatic"):
        rows = [r for d in SA.values() for r in d["rows"] if r["realm"] == realm and r["status"] == "scored"]
        by = {}
        for r in rows:
            by.setdefault(r["indicator"], []).append(r)
        agg = rep["realms"][realm]["aggregation"]["per_indicator"]
        assert {k for k, v in agg.items() if v["status"] == "ok"} == set(by)
        for ind, rs in by.items():
            worst = min(rs, key=lambda r: (r["score"], r["zone"]))
            a = agg[ind]
            assert a["worst_zone"] == worst["zone"] and same(a["worst_zone_score"], worst["score"]) and same(a["worst_zone_benchmark"], worst["benchmark"])
            assert same(a["worst_zone_site_value"], worst["site_value"]) and a["worst_zone_reference_n"] == worst["reference_n"] and a["n_zones_scored"] == len(rs)
            assert set(a["zone_scores"]) == {r["zone"] for r in rs}


def test_realm_headline_reproduces_an_independent_profile_from_the_standalone_scores(parity_run):
    rep, SA = parity_run["report"], parity_run["SA"]
    for realm in ("terrestrial", "aquatic"):
        worst = {}
        for d in SA.values():
            for r in d["rows"]:
                if r["realm"] == realm and r["status"] == "scored" and (r["indicator"] not in worst or r["score"] < worst[r["indicator"]]["score"]):
                    worst[r["indicator"]] = r
        items = [{"name": i, "construct": IC.CONTRACTS[i].construct, "subdimension": IC.CONTRACTS[i].subdimension, "value": r["benchmark"], "estimator": IC.CONTRACTS[i].estimator,
                  "score": r["score"]} for i, r in sorted(worst.items())]
        prof = engine_profile.build_profile(items)
        h = rep["realms"][realm]["headline"]
        oc = son_score.overall_condition(prof)
        assert same(h["condition"]["score"], oc["score"]) and h["condition"]["minimum_component"] == oc["minimum_component"]
        assert same(h["pressure"]["score"], son_score.overall_pressure(prof)["score"]) and h["matrix_cell"] == prof["matrix_cell"]
        assert h["condition"]["confidence"]["n_pillars_assessed"] == oc["confidence"]["n_pillars_assessed"]


def test_the_realm_headlines_are_pinned_to_the_values_derived_from_the_standalone_scores(parity_run):
    """Golden values (4 d.p., as son_score rounds): they change only if the aggregation, the scoring layer or the standalone results change."""
    t, a = parity_run["report"]["realms"]["terrestrial"]["headline"], parity_run["report"]["realms"]["aquatic"]["headline"]
    assert (t["condition"]["score"], t["condition"]["minimum_component"], t["pressure"]["score"], t["matrix_cell"]) == (0.0108, "C3_fauna", 0.1165, "stabilise_then_restore")
    assert (a["condition"]["score"], a["condition"]["minimum_component"], a["pressure"]["score"], a["matrix_cell"]) == (0.6708, "C2_vegetation", 0.1585, "defend_abate_threat")
    assert t["pillar_zone_coverage"]["C3_fauna"]["zones_scored"] == 1 and t["pillar_zone_coverage"]["C3_fauna"]["zones_total"] == 9
    assert a["pillar_zone_coverage"]["C1_landscape"]["zones_scored"] == 2 and a["coverage_caveat"] and "C3_fauna evidenced in 0 of 6" in a["coverage_caveat"]


def test_no_na_became_zero_anywhere_in_the_integrated_outputs(parity_run):
    rep, SA = parity_run["report"], parity_run["SA"]
    for label, d in SA.items():
        for src in d["rows"]:
            r = next(x for x in rep["zones"][label]["rows"] if x["indicator"] == src["indicator"])
            for k in ("site_value", "reference_n", "benchmark", "score"):
                if src[k] is None:
                    assert r[k] is None
    import csv
    rows = list(csv.DictReader((parity_run["out"] / "TataMotors_Pimpri_project.csv").open()))
    assert len(rows) == 690
    for r in rows:
        if r["status"] != "scored":
            assert r["score"] == "" and r["benchmark"] == "", (r["zone"], r["indicator"])
    for realm in rep["realms"].values():
        for i in realm["aggregation"]["per_indicator"].values():
            if i["status"] == "no_zone_scored":
                assert "worst_zone_score" not in i
            else:
                assert all(0.0 <= s <= 1.0 for s in i["zone_scores"].values()) and set(i["zone_scores"]) <= set(rep["zones"])
                assert len(i["zone_scores"]) == i["n_zones_scored"]            # exactly the scored zones: a zone without a score is absent, never present as 0


def test_project_json_csv_and_html_exist_and_the_html_shows_every_scored_row(parity_run):
    out, SA = parity_run["out"], parity_run["SA"]
    html = (out / "TataMotors_Pimpri_project.html").read_text()
    assert (out / "TataMotors_Pimpri_project.json").exists()
    for label in SA:
        assert label in html
    for label, d in SA.items():
        for r in d["rows"]:
            if r["status"] == "scored":
                assert f"{r['score']:.2f}" in html
    assert "Terrestrial realm" in html and "Aquatic realm" in html
    assert "(NOT FROZEN)" not in html and "(frozen)" in html                         # the engine behind this report is the frozen one
