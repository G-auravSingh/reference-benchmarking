"""
Adapter / aggregation / headline / HTML behaviour. Statuses are never reinterpreted to suit the old report machinery; n/a never becomes 0; a benchmark score is
never presented as a percentage of condition; realms are never pooled.
"""
import copy
import json
import math
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from darukaa_reference import engine_report as ER
from darukaa_reference import indicator_contract as IC
from darukaa_reference import scoring, html_report

FIX = Path(__file__).resolve().parent / "fixtures" / "tata_v0_2_8_standalone"


def load(zone):
    return json.loads((FIX / f"{zone}_audit.json").read_text())


def row(zone="Z1", realm="terrestrial", indicator="natural_habitat", status="scored", score=0.7, benchmark=0.7, site=80.0, unit="%", n=5000, reason="", **kw):
    base = {"zone": zone, "realm": realm, "indicator": indicator, "status": status, "reason": reason, "detail": "", "site_value": site, "site_unit": unit,
            "site_support": "site_window_mean", "reference_n": n, "reference_median": 50.0, "reference_mad": 5.0, "reference_unit": unit, "reference_support": "site_window_mean",
            "reference_population": "regional", "reference_tier": "tier1", "reference_funnel": "", "benchmark": benchmark, "score": score,
            "scoring_method": "reference_percentile (higher_is_better; mid-rank percentile)", "direction": "higher_is_better", "applicability_reason": "applicable",
            "flags": "", "compatibility_checks": "ok", "provenance": "{}", "diagnostics": "{}", "other_references": "{}", "validation_status": "v", "seconds": 1.0}
    base.update(kw)
    if status != "scored":
        base.update(score=None, benchmark=None, reference_n=None)
        if status in ("not_applicable", "applicable_but_no_site_value", "pending_methodology", "contextual_only", "screening_only"):
            base["site_value"] = None
    return base


def zone(label, realm, rows, area=10.0):
    return {"label": label, "realm": realm, "area_ha": area, "rows": rows, "meta": {}, "realm_source": "manifest"}


# ---------------------------------------------------------------- status policy
POLICY = {"scored": "aggregate", "contextual_only": "context", "screening_only": "screening", "not_applicable": "excluded", "applicable_but_no_site_value": "excluded",
          "applicable_but_no_reference": "excluded", "reference_available_but_not_scoreable": "excluded", "suppressed_for_stability": "excluded", "pending_methodology": "excluded"}


def test_the_status_policy_is_exactly_the_approved_mapping_and_covers_every_engine_status():
    assert ER.STATUS_POLICY == POLICY and set(POLICY) == set(IC.INDICATOR_STATUSES)


@pytest.mark.parametrize("status", sorted(POLICY))
def test_each_status_gets_its_role_and_keeps_its_reason(status):
    r = ER.scorecard_row(row(status=status, reason="some_reason_xyz", detail="d"))
    assert r["aggregation_role"] == POLICY[status] and r["status"] == status and r["reason"] == "some_reason_xyz"
    if POLICY[status] == "excluded":
        assert r["excluded_reason"] == f"{status}: some_reason_xyz"
    else:
        assert r["excluded_reason"] is None


def test_an_excluded_row_without_a_reason_still_says_so_explicitly():
    assert ER.scorecard_row(row(status="suppressed_for_stability", reason=""))["excluded_reason"] == "suppressed_for_stability: n/a"


def test_an_unknown_status_and_a_scored_row_without_a_score_raise():
    with pytest.raises(ER.EngineRowError, match="unknown engine status"):
        ER.scorecard_row(row(status="mostly_fine"))
    for k in ("score", "site_value", "benchmark", "reference_n"):
        bad = row(); bad[k] = None
        with pytest.raises(ER.EngineRowError):
            ER.scorecard_row(bad)
    for s in (-0.01, 1.01, float("nan")):
        with pytest.raises(ER.EngineRowError):
            ER.scorecard_row(row(score=s))


def test_every_engine_field_passes_through_unchanged():
    src = row(flags="f1;f2", provenance='{"a": 1}', diagnostics='{"b": 2}', applicability_reason="applicable [x]")
    out = ER.scorecard_row(src)
    for k, v in src.items():
        if k in ("zone", "realm", "indicator", "status", "reason", "detail"):
            assert out[k] == v
        elif k in out:
            assert out[k] == v and type(out[k]) is type(v), k
    assert out["construct"] == IC.CONTRACTS["natural_habitat"].construct and out["subdimension"] == IC.CONTRACTS["natural_habitat"].subdimension


# ---------------------------------------------------------------- n/a never becomes 0
def test_none_stays_none_through_the_adapter_for_every_real_tata_row():
    total = 0
    for f in sorted(FIX.glob("*_audit.json")):
        for src in json.loads(f.read_text())["rows"]:
            out = ER.scorecard_row(src)
            for k in ("site_value", "reference_n", "reference_median", "reference_mad", "benchmark", "score"):
                assert (out[k] is None) == (src[k] is None), (src["zone"], src["indicator"], k)
                if src[k] is None:
                    assert out[k] is None and out[k] != 0 and out[k] is not False
            total += 1
    assert total == 690


def test_csv_writes_an_empty_cell_for_an_absent_value_never_zero():
    rep = ER.build_project_report("p", [zone("Z1", "terrestrial", [row(), row(indicator="ndvi", status="not_applicable", reason="domain_mismatch")])])
    lines = ER.csv_text(rep).splitlines()
    hdr = lines[0].split(",")
    na = next(l for l in lines[1:] if ",ndvi," in l)
    cells = dict(zip(hdr, next(__import__("csv").reader([na]))))
    assert cells["score"] == "" and cells["benchmark"] == "" and cells["site_value"] == "" and cells["reference_n"] == ""


def test_an_indicator_absent_in_some_zones_is_not_averaged_or_counted_as_zero():
    rows_a = [row("A", indicator="ndvi", score=0.80, benchmark=0.8, site=0.5, unit="index")]
    rows_b = [row("B", indicator="ndvi", status="not_applicable", reason="site_below_product_resolution")]
    rows_c = [row("C", indicator="ndvi", score=0.60, benchmark=0.6, site=0.4, unit="index")]
    agg = ER.aggregate_realm([r for rs in (rows_a, rows_b, rows_c) for r in ER.adapt_rows(rs)], {"A": 5.0, "B": 5.0, "C": 5.0})
    i = agg["per_indicator"]["ndvi"]
    assert i["n_zones_scored"] == 2 and i["n_zones_in_realm"] == 3 and i["worst_zone"] == "C" and i["worst_zone_score"] == 0.60
    assert set(i["zone_scores"]) == {"A", "C"} and "B" not in i["zone_scores"]
    assert i["excluded_zones"] == [{"zone": "B", "status": "not_applicable", "reason": "site_below_product_resolution", "detail": ""}]
    assert i["area_weighted_geomean_score_context"] == pytest.approx(math.sqrt(0.8 * 0.6))          # over the two scored zones only; B contributes nothing, not a 0


def test_an_indicator_scored_in_no_zone_is_reported_as_such_and_has_no_number():
    rows = ER.adapt_rows([row("A", indicator="chm", status="not_applicable", reason="ecosystem_type_mismatch"),
                          row("B", indicator="chm", status="applicable_but_no_reference", reason="no_tier2_reference_units")])
    agg = ER.aggregate_realm(rows, {"A": 1.0, "B": 1.0})
    i = agg["per_indicator"]["chm"]
    assert i["status"] == "no_zone_scored" and "worst_zone_score" not in i and agg["combined_benchmarks"] == []


# ---------------------------------------------------------------- roles: context / screening are never aggregated
def test_context_and_screening_rows_never_enter_aggregation_even_if_they_carry_numbers():
    ctx = row("A", indicator="ndvi", status="contextual_only"); ctx.update(score=0.01, benchmark=-9.0, site_value=0.3)
    scr = row("B", indicator="ndvi", status="screening_only"); scr.update(score=0.02, benchmark=-8.0, site_value=0.2)
    good = row("C", indicator="ndvi", score=0.9, benchmark=0.9, site=0.5, unit="index")
    agg = ER.aggregate_realm(ER.adapt_rows([ctx, scr, good]), {})
    i = agg["per_indicator"]["ndvi"]
    assert i["worst_zone"] == "C" and i["n_zones_scored"] == 1 and i["context_zones"] == ["A"] and i["screening_zones"] == ["B"]
    assert [b["name"] for b in agg["combined_benchmarks"]] == ["ndvi"] and agg["combined_benchmarks"][0]["score"] == 0.9
    prof = ER.zone_profile(ER.adapt_rows([ctx]))
    assert prof["components"] == {} and prof["condition"].get("rollup") is None


# ---------------------------------------------------------------- the engine's score is used as is
def test_a_percentile_score_is_not_renormalised():
    r = ER.adapt_rows([row(score=0.745, benchmark=0.745)])
    prof = ER.zone_profile(r)
    assert prof["components"]["C1_landscape"]["headline"] == pytest.approx(0.745)
    legacy_would_say = scoring.normalize(0.745, "percentile")
    assert abs(legacy_would_say - 0.745) > 0.1                                       # the trap this change avoids


def test_a_z_scored_indicator_gets_the_same_number_the_legacy_normaliser_gives():
    z = 0.43297827941224715
    sc = scoring.normalize(z, "robust_z")
    r = ER.adapt_rows([row(indicator="ghm", score=sc, benchmark=z, site=0.44, unit="index", scoring_method="robust_z (lower_is_better)")])
    legacy = scoring.build_site_profile([{"name": "ghm", "construct": "C4_pressure", "subdimension": "land_use_pressure", "value": z, "estimator": "robust_z"}])
    assert ER.zone_profile(r)["pressure"] == legacy["pressure"]


# ---------------------------------------------------------------- realms are never pooled
def test_terrestrial_and_aquatic_zones_are_aggregated_separately():
    t = zone("T1", "terrestrial", [row("T1", "terrestrial", "ghm", score=0.80, benchmark=0.8, site=0.3, unit="index")])
    a = zone("A1", "aquatic", [row("A1", "aquatic", "ghm", score=0.20, benchmark=0.2, site=0.7, unit="index")])
    rep = ER.build_project_report("p", [t, a])
    assert rep["realms"]["terrestrial"]["aggregation"]["per_indicator"]["ghm"]["worst_zone"] == "T1"
    assert rep["realms"]["aquatic"]["aggregation"]["per_indicator"]["ghm"]["worst_zone"] == "A1"
    assert rep["realms"]["terrestrial"]["aggregation"]["per_indicator"]["ghm"]["worst_zone_score"] == 0.80       # the aquatic 0.20 never lowered it
    assert rep["realms"]["terrestrial"]["zones"] == ["T1"] and rep["realms"]["aquatic"]["zones"] == ["A1"]
    assert set(rep) == {"meta", "headline_policy", "status_policy", "realms", "zones"}              # no project-wide / cross-realm headline object exists
    assert set(rep["realms"]) == {"terrestrial", "aquatic"} and "NO blended" in rep["headline_policy"]
    assert rep["realms"]["terrestrial"]["profile"] != rep["realms"]["aquatic"]["profile"]


def test_a_realm_with_no_zones_is_absent_not_empty():
    rep = ER.build_project_report("p", [zone("T1", "terrestrial", [row("T1")])])
    assert list(rep["realms"]) == ["terrestrial"]


def test_a_zone_whose_rows_carry_another_realm_is_rejected():
    with pytest.raises(ER.EngineRowError):
        ER.build_project_report("p", [zone("T1", "terrestrial", [row("T1", "aquatic")])])
    with pytest.raises(ER.EngineRowError):
        ER.build_project_report("p", [zone("T1", "mixed", [row("T1", "mixed")])])


# ---------------------------------------------------------------- headline
def test_no_condition_evidence_means_no_headline_and_no_zero():
    only_pressure = zone("P", "aquatic", [row("P", "aquatic", "ghm", score=0.3, benchmark=0.3, site=0.5, unit="index"),
                                          row("P", "aquatic", "natural_habitat", status="not_applicable", reason="domain_mismatch")])
    rep = ER.build_project_report("p", [only_pressure])
    h = rep["realms"]["aquatic"]["headline"]
    assert h["available"] is False and h["condition"]["score"] is None and h["condition"]["concern_class"] is None
    assert "Nothing was defaulted" in h["no_headline_reason"] and h["pressure_available"] is True
    assert rep["realms"]["aquatic"]["coverage"]["zones_without_condition_evidence"] == ["P"]
    assert rep["zones"]["P"]["coverage"]["headline_available"] is False


def test_a_headline_never_contains_a_percentage_field_or_percentage_text():
    rep = ER.build_project_report("p", [zone("T", "terrestrial", [row("T"), row("T", indicator="ghm", score=0.4, benchmark=0.4, site=0.3, unit="index")])])
    txt = json.dumps(rep["realms"]["terrestrial"]["headline"])
    assert "_pct" not in txt and not re.search(r"\(\d+%\)", txt)
    assert "benchmark score" in rep["realms"]["terrestrial"]["headline"]["limiting_chain"]["display"]


def test_the_coverage_caveat_names_the_zones_pillars_and_area_behind_a_headline():
    a = zone("A", "terrestrial", [row("A", indicator="bii", score=0.001, benchmark=0.001, site=0.4, unit="index"), row("A", indicator="natural_habitat")], area=60.0)
    b = zone("B", "terrestrial", [row("B", indicator="bii", status="not_applicable", reason="site_below_product_resolution"), row("B", indicator="natural_habitat")], area=40.0)
    h = ER.build_project_report("p", [a, b])["realms"]["terrestrial"]["headline"]
    assert h["pillar_zone_coverage"]["C3_fauna"] == {"zones_scored": 1, "zones_total": 2, "zones": ["A"], "area_fraction": 0.6}
    assert h["pillar_zone_coverage"]["C1_landscape"]["zones_scored"] == 2
    assert "C3_fauna evidenced in 1 of 2 zones (60% of the realm's area)" in h["coverage_caveat"] and "not scored, averaged or set to 0" in h["coverage_caveat"]


def test_full_coverage_has_no_caveat():
    rep = ER.build_project_report("p", [zone(z, "terrestrial", [row(z, indicator=i, site=1.0, score=0.5, benchmark=0.5) for i in ("natural_habitat", "ndvi", "bii", "ghm")])
                                         for z in ("A", "B")])
    assert rep["realms"]["terrestrial"]["headline"]["coverage_caveat"] is None


def test_worst_zone_ties_are_broken_deterministically_by_label():
    rs = ER.adapt_rows([row("Zb", score=0.5, benchmark=0.5), row("Za", score=0.5, benchmark=0.5), row("Zc", score=0.9, benchmark=0.9)])
    assert ER.aggregate_realm(rs, {})["per_indicator"]["natural_habitat"]["worst_zone"] == "Za"


def test_suppressed_pending_and_no_reference_zones_are_listed_with_their_reason_in_the_report():
    rows = [row("S", indicator="chm", status="suppressed_for_stability", reason="reference_has_too_many_ties"),
            row("S", indicator="tspi", status="pending_methodology", reason="v0.2.8_construct_not_implemented"),
            row("S", indicator="ndvi", status="applicable_but_no_reference", reason="no_tier2_reference_units"),
            row("S", indicator="bii", status="reference_available_but_not_scoreable", reason="insufficient_reference_n"),
            row("S", indicator="ghm", status="applicable_but_no_site_value", reason="site_value_not_computed")]
    rep = ER.build_project_report("p", [zone("S", "terrestrial", rows)])
    ex = {(e["zone"], e["status"], e["reason"]) for i in rep["realms"]["terrestrial"]["aggregation"]["per_indicator"].values() for e in i["excluded_zones"]}
    assert ex == {("S", "suppressed_for_stability", "reference_has_too_many_ties"), ("S", "pending_methodology", "v0.2.8_construct_not_implemented"),
                  ("S", "applicable_but_no_reference", "no_tier2_reference_units"), ("S", "reference_available_but_not_scoreable", "insufficient_reference_n"),
                  ("S", "applicable_but_no_site_value", "site_value_not_computed")}
    html = html_report.render_html(rep, "p")
    for s in ("suppressed_for_stability", "pending_methodology", "applicable_but_no_reference", "reference_available_but_not_scoreable", "applicable_but_no_site_value"):
        assert s in html


# ---------------------------------------------------------------- HTML
def _report():
    zs = []
    for f in sorted(FIX.glob("*_audit.json")):
        d = json.loads(f.read_text())
        zs.append({"label": d["rows"][0]["zone"], "realm": d["rows"][0]["realm"], "area_ha": d["meta"]["evidence"]["site_area_m2"] / 1e4, "rows": d["rows"], "meta": d["meta"],
                   "realm_source": "manifest"})
    rep = ER.build_project_report("fixture", zs)
    rep["meta"]["engine"] = {"engine_sha256_at_import": "x" * 64, "engine_matches_frozen": True}
    rep["meta"]["provenance"] = {"git_commit_short": "abc1234"}
    return rep


def test_html_separates_score_from_measurement_and_never_formats_a_score_as_a_percentage():
    html = html_report.render_html(_report(), "fixture")
    text = re.sub(r"<[^>]+>", " ", html)
    assert "NOT a percentage of ecological condition" in text and "100 % condition" in text
    for col in ("Benchmark score (0-1)", "Raw measurement", "Reference median"):
        assert col in text
    assert not re.search(r"<b>\d\.\d\d\s*%</b>", html)                                              # every bold score cell is a bare 0-1 number
    assert not re.search(r"concern class[^<]*\d+\s*%", html)
    assert "57.69 %" in text or "57.7" in text                                                      # a raw measurement in % is still shown, as a measurement


def test_html_has_two_realm_sections_the_coverage_caveat_and_no_blended_headline():
    html = html_report.render_html(_report(), "fixture")
    assert html.count("realm &mdash;") == 2 and "Terrestrial realm" in html and "Aquatic realm" in html
    assert "C3_fauna evidenced in 1 of 9 zones" in html and "No blended headline" in html
    assert "NOT FROZEN" not in html and "(frozen)" in html


def test_every_excluded_real_row_shows_status_and_reason_in_the_html():
    rep = _report()
    html = html_report.render_html(rep, "fixture")
    seen = set()
    for z in rep["zones"].values():
        for r in z["rows"]:
            if r["aggregation_role"] == "excluded" and r["reason"]:
                seen.add((r["status"], r["reason"]))
    assert seen and all(s in html and why in html for s, why in seen)


def test_the_legacy_html_path_is_unchanged_for_legacy_reports():
    legacy_like = {"meta": {"pipeline_version": "x", "archetype": "conservation", "n_sites": 0, "n_indicators": 0}, "indicator_status": {}, "scorecard": [], "site_profiles": {}}
    assert (legacy_like.get("meta") or {}).get("report_kind") != ER.REPORT_KIND
    try:
        html_report.render_html(legacy_like, "legacy")
    except Exception as e:                                              # an old-model report may need more keys; the point is that it does NOT go to the engine renderer
        assert "engine" not in str(e).lower()
