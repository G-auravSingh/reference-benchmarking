"""
engine_report.py -- v0.2.8 engine rows -> scorecard, per-realm aggregation, coverage and headline (v0.2.9 Phase 5)
================================================================================================================

Input: the audit rows the FROZEN v0.2.8 engine already produced (`assess.assess_zone`). Nothing here recomputes a site value, a reference, a benchmark or a
score; this module only decides what each row MAY be used for, aggregates what is valid, and reports what is not.

STATUS POLICY (strict; the adapter never reinterprets an engine status to suit the old report machinery)
  scored                                  -> aggregation_role "aggregate": eligible for score aggregation
  contextual_only                         -> "context": reported as context, never aggregated into condition
  screening_only                          -> "screening": reported in the screening section, never aggregated
  not_applicable                          -> "excluded", reason retained
  applicable_but_no_site_value            -> "excluded", reason retained
  applicable_but_no_reference             -> "excluded", reason retained
  reference_available_but_not_scoreable   -> "excluded", reason retained
  suppressed_for_stability                -> "excluded", explicitly reported
  pending_methodology                     -> "excluded", explicitly reported
An unknown status raises; a `scored` row without a score raises. Absent data is `None` everywhere: it is never averaged, never ranked, never turned into 0.

TWO DIFFERENT QUANTITIES are always kept apart
  * the raw ecological / Earth-observation MEASUREMENT: `site_value` (+ `site_unit`), and the `reference_median` it was compared with;
  * the BENCHMARK SCORE: `score` in [0, 1], the site relative to its reference population (0.5 = at the reference; higher = better, the direction is already
    encoded by the engine). A score of 1.00 means the site ranks at or above every reference unit (or far above the reference median). It is NOT
    "100 % ecological condition" and is never formatted as a percentage here.

AGGREGATION (per REALM; terrestrial and aquatic zones are never pooled)
  project-realm signal for an indicator = the WORST scored zone's `score` (non-compensatory, the limiting-factor rule already used by project_aggregation),
  fed to engine_profile.build_profile with the engine's score as is. Area-weighted figures are secondary context and labelled so.
HEADLINE: the existing profile-first mechanism (son_score), computed only from `scored` rows, with explicit pillar coverage. No scoreable condition evidence
  -> no headline (never a 0, never a default).
"""
from __future__ import annotations

import csv
import io
import math
from collections import Counter, OrderedDict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from darukaa_reference import indicator_contract as IC
from darukaa_reference import engine_profile, son_score

STATUS_POLICY: Dict[str, str] = {
    "scored": "aggregate",
    "contextual_only": "context",
    "screening_only": "screening",
    "not_applicable": "excluded",
    "applicable_but_no_site_value": "excluded",
    "applicable_but_no_reference": "excluded",
    "reference_available_but_not_scoreable": "excluded",
    "suppressed_for_stability": "excluded",
    "pending_methodology": "excluded",
}
# Import-time guard: if the engine ever gains or loses a status, this module refuses to load rather than silently mishandle it.
assert set(STATUS_POLICY) == set(IC.INDICATOR_STATUSES), (set(STATUS_POLICY) ^ set(IC.INDICATOR_STATUSES))

CONDITION_PILLARS = ("C1_landscape", "C2_vegetation", "C3_fauna")
PRESSURE_PILLAR = "C4_pressure"
REALMS = ("terrestrial", "aquatic")

SCORE_EXPLAINER = ("Benchmark score (0-1): this site relative to its own reference population; 0.5 = at the reference, higher = better (direction already encoded). "
                   "It is NOT a percentage of ecological condition: a score of 1.00 means the site ranks at or above every reference unit, not '100 % condition'. "
                   "The raw measurement (site value, unit) and the reference median are reported separately and are what the score was computed from.")


class EngineRowError(ValueError):
    """An engine row violates an engine invariant; surfaced, never skipped."""


# ----------------------------------------------------------------------------------------------------------------------
# row adapter
# ----------------------------------------------------------------------------------------------------------------------
def _contract(name: str):
    return IC.CONTRACTS.get(name)


def scorecard_row(row: Dict[str, Any], display_name: Optional[str] = None) -> Dict[str, Any]:
    """One engine audit row -> one scorecard row. Every engine field is carried through unchanged; only role / exclusion labels and the contract's
    construct / subdimension / estimator are added. `None` stays `None`."""
    status = row.get("status")
    if status not in STATUS_POLICY:
        raise EngineRowError(f"unknown engine status {status!r} for {row.get('zone')}/{row.get('indicator')}")
    role = STATUS_POLICY[status]
    if status == "scored":
        missing = [k for k in ("score", "site_value", "benchmark", "reference_n") if row.get(k) is None]
        if missing:
            raise EngineRowError(f"{row.get('zone')}/{row.get('indicator')} is 'scored' but lacks {missing}")
        if not (0.0 <= float(row["score"]) <= 1.0) or not math.isfinite(float(row["score"])):
            raise EngineRowError(f"{row.get('zone')}/{row.get('indicator')} has a score outside [0, 1]: {row['score']!r}")
    c = _contract(row["indicator"])
    out: Dict[str, Any] = OrderedDict()
    out["zone"], out["realm"], out["indicator"] = row.get("zone"), row.get("realm"), row["indicator"]
    out["display_name"] = display_name or row["indicator"].replace("_", " ").title()
    out["construct"], out["subdimension"] = (c.construct if c else None), (c.subdimension if c else None)
    out["status"], out["reason"], out["detail"] = status, row.get("reason", ""), row.get("detail", "")
    out["aggregation_role"] = role
    out["excluded_reason"] = (f"{status}: {row.get('reason') or 'n/a'}" if role == "excluded" else None)
    # raw measurement (never a score)
    out["site_value"], out["site_unit"], out["site_support"] = row.get("site_value"), row.get("site_unit"), row.get("site_support")
    # reference
    for k in ("reference_n", "reference_median", "reference_mad", "reference_unit", "reference_support", "reference_population", "reference_tier",
              "reference_funnel"):
        out[k] = row.get(k)
    # benchmark score
    out["benchmark"], out["score"] = row.get("benchmark"), row.get("score")
    out["scoring_method"], out["direction"], out["estimator"] = row.get("scoring_method"), row.get("direction"), (c.estimator if c else None)
    # applicability, flags, provenance: passed through verbatim
    for k in ("applicability_reason", "flags", "compatibility_checks", "provenance", "diagnostics", "other_references", "validation_status", "seconds"):
        out[k] = row.get(k)
    return out


def adapt_rows(rows: Iterable[Dict[str, Any]], registry=None) -> List[Dict[str, Any]]:
    def disp(name):
        try:
            return registry.get(name).display_name if registry is not None and name in registry else None
        except Exception:
            return None
    return [scorecard_row(r, disp(r["indicator"])) for r in rows]


# ----------------------------------------------------------------------------------------------------------------------
# aggregation within ONE realm
# ----------------------------------------------------------------------------------------------------------------------
def _geomean(vals: Sequence[float], weights: Sequence[float]) -> Optional[float]:
    pairs = [(v, w) for v, w in zip(vals, weights) if v is not None and v > 0 and w > 0]
    if not pairs:
        return None
    tw = sum(w for _, w in pairs)
    return math.exp(sum(w * math.log(v) for v, w in pairs) / tw)


def aggregate_realm(rows: Sequence[Dict[str, Any]], zone_areas_ha: Dict[str, Optional[float]]) -> Dict[str, Any]:
    """Worst-zone aggregation over the zones of ONE realm. `rows` are scorecard rows of that realm's zones."""
    zones = sorted({r["zone"] for r in rows})
    by_ind: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        by_ind.setdefault(r["indicator"], []).append(r)
    per_indicator: Dict[str, Dict[str, Any]] = OrderedDict()
    out_of_domain: List[str] = []
    combined: List[Dict[str, Any]] = []
    for ind in sorted(by_ind):
        rs = by_ind[ind]
        if all(r["status"] == "not_applicable" and r["reason"] == "domain_mismatch" for r in rs):
            out_of_domain.append(ind)
            continue
        counts = Counter(r["status"] for r in rs)
        scored = [r for r in rs if r["aggregation_role"] == "aggregate"]
        excluded = [{"zone": r["zone"], "status": r["status"], "reason": r["reason"], "detail": r["detail"]}
                    for r in rs if r["aggregation_role"] == "excluded"]
        entry: Dict[str, Any] = {"indicator": ind, "display_name": rs[0]["display_name"], "construct": rs[0]["construct"], "subdimension": rs[0]["subdimension"],
                                 "n_zones_in_realm": len(zones), "n_zones_scored": len(scored), "status_counts": dict(counts),
                                 "excluded_zones": excluded,
                                 "context_zones": [r["zone"] for r in rs if r["aggregation_role"] == "context"],
                                 "screening_zones": [r["zone"] for r in rs if r["aggregation_role"] == "screening"]}
        if not scored:
            entry["status"] = "no_zone_scored"           # the evidence is absent: reported as such, never as a number
            per_indicator[ind] = entry
            continue
        worst = min(scored, key=lambda r: (float(r["score"]), r["zone"]))        # ties broken by zone label, deterministically
        areas = [zone_areas_ha.get(r["zone"]) for r in scored]
        w = [a if a else 1e-6 for a in areas]
        units = {r["site_unit"] for r in scored}
        entry.update({
            "status": "ok", "estimator": worst["estimator"],
            "worst_zone": worst["zone"], "worst_zone_score": float(worst["score"]), "worst_zone_benchmark": worst["benchmark"],
            "worst_zone_scoring_method": worst["scoring_method"], "worst_zone_site_value": worst["site_value"], "worst_zone_site_unit": worst["site_unit"],
            "worst_zone_reference_median": worst["reference_median"], "worst_zone_reference_n": worst["reference_n"],
            "zone_scores": {r["zone"]: float(r["score"]) for r in sorted(scored, key=lambda r: r["zone"])},
            "area_weighted_geomean_score_context": _geomean([float(r["score"]) for r in scored], w),
            "area_weighted_mean_site_value_context": (sum(wi * r["site_value"] for wi, r in zip(w, scored)) / sum(w) if len(units) == 1 else None),
        })
        per_indicator[ind] = entry
        combined.append({"name": ind, "construct": entry["construct"], "subdimension": entry["subdimension"], "value": worst["benchmark"],
                         "estimator": worst["estimator"] or "", "score": float(worst["score"])})
    return {"zones": zones, "per_indicator": per_indicator, "indicators_out_of_domain": out_of_domain, "combined_benchmarks": combined,
            "rule": ("Realm signal per indicator = the WORST scored zone's benchmark score (non-compensatory). Zones where the indicator is not scored are "
                     "listed with their status and reason; they are never imputed, averaged or counted as 0.")}


def zone_profile(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """profile-first scoring for ONE zone from its `scored` rows only, using the engine's score as is."""
    items = [{"name": r["indicator"], "construct": r["construct"], "subdimension": r["subdimension"], "value": r["benchmark"],
              "estimator": r["estimator"] or "", "score": float(r["score"])} for r in rows if r["aggregation_role"] == "aggregate"]
    return engine_profile.build_profile(items)


# ----------------------------------------------------------------------------------------------------------------------
# headline (no percentages, explicit coverage, no headline without evidence)
# ----------------------------------------------------------------------------------------------------------------------
def _strip_pct(obj: Any) -> Any:
    """son_score adds 1-100 % display strings; a benchmark score must never be shown as a percentage of condition, so they are dropped here."""
    if isinstance(obj, dict):
        return {k: _strip_pct(v) for k, v in obj.items() if not str(k).endswith("_pct")}
    if isinstance(obj, list):
        return [_strip_pct(v) for v in obj]
    return obj


def _sc(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{x:.2f}"


def headline(profile: Dict[str, Any], marker_rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """`marker_rows` need construct, subdimension, indicator, display_name and a non-None site_value (the limiting chain names indicators from them)."""
    oc, op = son_score.overall_condition(profile), son_score.overall_pressure(profile)
    available = oc.get("score") is not None
    chain = son_score.limiting_chain(profile, list(marker_rows))
    if chain.get("available"):
        inds = chain.get("limiting_indicators") or [chain.get("limiting_subdimension") or "unknown"]
        chain["display"] = (f"limited primarily by {chain.get('limiting_pillar_label')} (benchmark score {_sc(chain.get('limiting_pillar_score'))}), "
                            f"itself limited by {' & '.join(inds)}")
    out = {"available": available, "condition": oc, "pressure": op, "matrix_cell": profile.get("matrix_cell"), "limiting_chain": chain,
           "pillars": son_score.pillar_summary(profile, list(marker_rows)),
           "no_headline_reason": (None if available else
                                  "No condition pillar (C1 landscape, C2 vegetation, C3 fauna) has a scored indicator with valid evidence: "
                                  "no overall condition is reported. Nothing was defaulted or set to 0."),
           "pressure_available": op.get("score") is not None,
           "score_scale": SCORE_EXPLAINER}
    return _strip_pct(out)


def marker_rows(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{"indicator": r["indicator"], "display_name": r["display_name"], "construct": r["construct"], "subdimension": r["subdimension"],
             "site_value": r["site_value"]} for r in rows if r["aggregation_role"] == "aggregate"]


# ----------------------------------------------------------------------------------------------------------------------
# coverage
# ----------------------------------------------------------------------------------------------------------------------
def zone_coverage(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    scored = [r for r in rows if r["aggregation_role"] == "aggregate"]
    pillars = Counter(r["construct"] for r in scored)
    cond_covered = [p for p in CONDITION_PILLARS if pillars.get(p)]
    return {"n_rows": len(rows), "status_counts": dict(Counter(r["status"] for r in rows)),
            "n_scored": len(scored), "scored_indicators": sorted(r["indicator"] for r in scored),
            "scored_per_pillar": {p: pillars.get(p, 0) for p in CONDITION_PILLARS + (PRESSURE_PILLAR,)},
            "condition_pillars_covered": cond_covered, "n_condition_pillars_covered": len(cond_covered), "n_condition_pillars_total": len(CONDITION_PILLARS),
            "pressure_covered": bool(pillars.get(PRESSURE_PILLAR)), "headline_available": bool(cond_covered),
            "context_indicators": sorted(r["indicator"] for r in rows if r["aggregation_role"] == "context"),
            "screening_indicators": sorted(r["indicator"] for r in rows if r["aggregation_role"] == "screening")}


def pillar_zone_coverage(zone_cov: Dict[str, Dict[str, Any]], areas: Dict[str, Optional[float]]) -> Dict[str, Any]:
    """For each pillar: in how many of the realm's zones (and what share of its area) is the pillar evidenced by at least one scored indicator?
    The legacy confidence flag counts PILLARS; this counts ZONES, because a worst-zone headline built from one zone says little about the others."""
    labels = sorted(zone_cov)
    total_area = sum(a for a in areas.values() if a)
    out: Dict[str, Any] = {}
    for p in CONDITION_PILLARS + (PRESSURE_PILLAR,):
        zs = [k for k in labels if zone_cov[k]["scored_per_pillar"].get(p, 0) > 0]
        area = sum(areas.get(k) or 0 for k in zs)
        out[p] = {"zones_scored": len(zs), "zones_total": len(labels), "zones": zs, "area_fraction": (area / total_area if total_area else None)}
    short = [p for p, v in out.items() if v["zones_scored"] < v["zones_total"]]
    note = None
    if short:
        note = ("Worst-zone headline over the zones that HAVE evidence, not over all zones. Pillar coverage: " +
                "; ".join(f"{p} evidenced in {out[p]['zones_scored']} of {out[p]['zones_total']} zones"
                          + (f" ({out[p]['area_fraction'] * 100:.0f}% of the realm's area)" if out[p]["area_fraction"] is not None else "") for p in out) +
                ". Zones without evidence for a pillar are listed under their status and reason; they are not scored, averaged or set to 0.")
    return {"per_pillar": out, "partial_or_absent_pillars": short, "caveat": note}


def realm_coverage(zone_cov: Dict[str, Dict[str, Any]], agg: Dict[str, Any]) -> Dict[str, Any]:
    per_pillar: Dict[str, Dict[str, Any]] = {}
    for p in CONDITION_PILLARS + (PRESSURE_PILLAR,):
        inds = [i for i in agg["per_indicator"].values() if i["construct"] == p]
        per_pillar[p] = {"indicators_in_domain": [i["indicator"] for i in inds],
                         "indicators_scored_somewhere": [i["indicator"] for i in inds if i["n_zones_scored"] > 0],
                         "indicators_never_scored": [{"indicator": i["indicator"], "why": i["excluded_zones"][:3]} for i in inds if i["n_zones_scored"] == 0]}
    n = len(zone_cov)
    return {"n_zones": n, "n_zones_with_headline": sum(1 for z in zone_cov.values() if z["headline_available"]),
            "zones_without_condition_evidence": sorted(k for k, z in zone_cov.items() if not z["headline_available"]), "per_pillar": per_pillar}


# ----------------------------------------------------------------------------------------------------------------------
# the project report
# ----------------------------------------------------------------------------------------------------------------------
REPORT_KIND = "engine_v0.2.8"


def build_project_report(project_name: str, zones: Sequence[Dict[str, Any]], registry=None, meta: Optional[Dict[str, Any]] = None,
                         failed_zones: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """zones: [{label, realm, area_ha, rows (engine audit rows), meta (audit meta), realm_source, companion_source, resumed, audit_files}, ...]"""
    failed_zones = dict(failed_zones or {})
    zone_out: Dict[str, Any] = OrderedDict()
    for z in zones:
        rows = adapt_rows(z["rows"], registry)
        bad = [r["zone"] for r in rows if r["zone"] not in (None, z["label"]) or r["realm"] not in (None, z["realm"])]
        if bad:
            raise EngineRowError(f"rows of zone {z['label']!r} carry another zone/realm: {sorted(set(bad))}")
        prof = zone_profile(rows)
        zone_out[z["label"]] = {"label": z["label"], "realm": z["realm"], "area_ha": z.get("area_ha"), "realm_source": z.get("realm_source"),
                                "companion_source": z.get("companion_source"), "resumed_from_existing_audit": bool(z.get("resumed")),
                                "audit_files": z.get("audit_files"), "evidence": (z.get("meta") or {}).get("evidence"),
                                "coverage": zone_coverage(rows), "profile": prof, "headline": headline(prof, marker_rows(rows)), "rows": rows}
    realms: Dict[str, Any] = OrderedDict()
    for realm in REALMS:
        labels = [k for k, v in zone_out.items() if v["realm"] == realm]
        if not labels:
            continue
        rrows = [r for k in labels for r in zone_out[k]["rows"]]
        areas = {k: zone_out[k]["area_ha"] for k in labels}
        agg = aggregate_realm(rrows, areas)
        prof = engine_profile.build_profile(agg["combined_benchmarks"])
        mk = [{"indicator": i["indicator"], "display_name": i["display_name"], "construct": i["construct"], "subdimension": i["subdimension"],
               "site_value": i["worst_zone_site_value"]} for i in agg["per_indicator"].values() if i["status"] == "ok"]
        zc = {k: zone_out[k]["coverage"] for k in labels}
        pzc = pillar_zone_coverage(zc, areas)
        hl = headline(prof, mk)
        hl["pillar_zone_coverage"], hl["coverage_caveat"] = pzc["per_pillar"], pzc["caveat"]      # shown WITH the headline, always
        realms[realm] = {"zones": labels, "n_zones": len(labels), "total_area_ha": round(sum(a for a in areas.values() if a), 2),
                         "aggregation": agg, "profile": prof, "headline": hl, "coverage": dict(realm_coverage(zc, agg), pillar_zone_coverage=pzc)}
    unknown = sorted({v["realm"] for v in zone_out.values()} - set(REALMS))
    if unknown:
        raise EngineRowError(f"zones with an unsupported realm {unknown}")
    meta = dict(meta or {})
    meta.update({"report_kind": REPORT_KIND, "project_name": project_name, "n_zones": len(zone_out), "n_zones_failed": len(failed_zones),
                 "failed_zones": failed_zones, "zones_by_realm": {r: v["zones"] for r, v in realms.items()}})
    return {"meta": meta,
            "headline_policy": ("Terrestrial and aquatic zones are assessed and reported separately; there is NO blended terrestrial/aquatic headline. Each realm's "
                                "headline comes from its scored indicators only, with explicit pillar coverage, and is withheld where there is no scoreable "
                                "condition evidence. " + SCORE_EXPLAINER),
            "status_policy": dict(STATUS_POLICY), "realms": realms, "zones": zone_out}


# ----------------------------------------------------------------------------------------------------------------------
# flat tables
# ----------------------------------------------------------------------------------------------------------------------
CSV_COLUMNS = ["zone", "realm", "indicator", "display_name", "construct", "subdimension", "status", "reason", "aggregation_role", "site_value", "site_unit",
               "reference_n", "reference_median", "reference_mad", "benchmark", "score", "scoring_method", "direction", "applicability_reason", "flags", "detail"]


def csv_text(report: Dict[str, Any]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for z in report["zones"].values():
        for r in z["rows"]:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in CSV_COLUMNS})      # an absent value is an EMPTY cell, never 0
    return buf.getvalue()
