"""
assess.py -- v0.2.8 live smoke-test wiring (Phase 5 / 6 prerequisite)
=====================================================================

Runs the v0.2.8 engine on ONE zone and writes a complete indicator-level audit trail. It does NOT touch
the production pipeline or the headline aggregation, and it computes ONLY what the contract says can be
scored: contextual / screening indicators are listed with their status and reason but not computed
(no wasted Earth Engine work, no silent exclusion).

Structure
  assess_zone(zone, provider, ...)  pure orchestration, unit-tested offline with a fake provider
  EEProvider                        the Earth Engine implementation (NOT verified live: this is what the smoke
                                    test exists to check; parity.py compares it with the numpy definitions)
  audit rows / writers              CSV + JSON + Markdown

Order per indicator (also decides what is computed): applicability -> contract class -> is the v0.2.8 construct
implemented -> site value -> reference -> engine (compatibility, minimum n, estimator, status).
"""
from __future__ import annotations

import csv
import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from darukaa_reference import benchmarking as B
from darukaa_reference import constructs as K
from darukaa_reference import indicator_contract as IC
from darukaa_reference import support as S

logger = logging.getLogger(__name__)

CODE_VERSION = "v0.2.8-contract (smoke-test fixes 1)"

AUDIT_COLUMNS = ["indicator", "status", "site_value", "site_unit", "site_support", "reference_population",
                 "reference_n", "reference_unit", "reference_support", "benchmark", "scoring_method",
                 "applicability_reason", "compatibility_checks", "provenance"]
EXTRA_COLUMNS = ["reason", "detail", "score", "direction", "reference_tier", "reference_median", "reference_mad",
                 "reference_funnel", "diagnostics", "flags", "other_references", "validation_status", "seconds",
                 "zone", "realm"]


# ----------------------------------------------------------------------------------------
# Data classes
# ----------------------------------------------------------------------------------------
@dataclass
class Zone:
    label: str
    geometry: Any                      # shapely geometry (WGS84)
    realm: str                         # terrestrial | aquatic | mixed
    eco_id: Optional[int] = None
    validation_label: Optional[str] = None   # E4: a methodological validation dataset, never project scoring


@dataclass
class SiteResult:
    value: Optional[float]
    unit: str
    spec: Optional[B.MetricSpec]
    meta: Dict = field(default_factory=dict)


def git_commit(default: str = "unknown") -> str:
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        return subprocess.check_output(["git", "-C", here, "rev-parse", "--short", "HEAD"],
                                       stderr=subprocess.DEVNULL, timeout=5).decode().strip()
    except Exception:
        return default


# ----------------------------------------------------------------------------------------
# Pure orchestration
# ----------------------------------------------------------------------------------------
def _provenance(c: IC.IndicatorContract, zone: Zone, a: B.IndicatorAssessment, ref: Optional[B.ReferenceData],
                site: Optional[SiteResult], config=None, commit: str = "") -> Dict:
    p = {"code_version": CODE_VERSION, "git_commit": commit, "zone": zone.label, "realm": zone.realm,
         "contract_inputs": list(c.inputs), "temporal": c.temporal, "native_resolution_m": c.native_resolution_m,
         "native_resolution_verified": c.resolution_verified, "implementation_status": c.implementation_status,
         "validated": c.validated, "parameters": dict(c.parameters), "reference_tier": c.reference_tier}
    if config is not None:
        p["ndvi_year"] = getattr(config, "ndvi_year", None)
        p["reference_seed"] = getattr(config, "reference_sample_seed", None)
    if ref is not None:
        p["reference_construction"] = {k: v for k, v in ref.diagnostics.items() if k != "funnel"}
    if site is not None and site.meta:
        p["site_meta"] = site.meta
    if c.reference_support.startswith("site_window"):
        p["ee_assumptions_unverified"] = ["A1: reduceResolution(mean, maxPixels=cell^2) + reproject = exact block mean on the native grid",
                                          "A2: stratifiedSample in the cell projection returns one value per cell"]
    if c.reference_population in ("comparable_water_bodies", "comparable_riparian_rings"):
        p["ee_assumptions_unverified"] = ["water-body vectorisation on the native UTM grid, pure-water erosion, reduceRegions per unit"]
    if validation := zone.validation_label:
        p["methodological_validation_dataset"] = validation
    return p


def _row(c, a, zone, site, ref, seconds, prov) -> Dict:
    checks = "; ".join(f"{k}={v}" for k, v in a.compatibility.items()) if a.compatibility else ""
    funnel = ref.diagnostics.get("funnel") if ref is not None else None
    if a.status == "not_applicable":
        appl = f"not_applicable: {a.reason}" + (f" ({a.detail})" if a.detail else "")
    else:
        appl = "applicable" + (f" [{'; '.join(a.flags)}]" if a.flags else "")
    method = (f"{c.estimator} ({c.direction}; {'mid-rank percentile' if c.estimator == 'reference_percentile' else 'scale estimator with zero-inflation guard'})"
              if c.estimator else "none (not a scored indicator)")
    ref_pop = a.reference_population if (ref is not None) else c.reference_population
    return {
        "indicator": c.name, "status": a.status,
        "site_value": (None if a.site_value is None else float(a.site_value)),
        "site_unit": (site.unit if site else ""), "site_support": c.site_support,
        "reference_population": ref_pop, "reference_n": a.reference_n,
        "reference_unit": (ref.spec.unit if ref is not None else ""),
        "reference_support": (ref.spec.support if ref is not None else c.reference_support),
        "benchmark": a.benchmark, "scoring_method": method, "applicability_reason": appl,
        "compatibility_checks": checks, "provenance": json.dumps(prov, default=str),
        "reason": a.reason, "detail": a.detail, "score": a.score, "direction": c.direction,
        "reference_tier": c.reference_tier, "reference_median": a.reference_median, "reference_mad": a.reference_mad,
        "reference_funnel": json.dumps(funnel) if funnel else "",
        "diagnostics": json.dumps({**a.diagnostics, **({"benchmark_details": a.benchmark_details} if a.benchmark_details else {})}, default=str),
        "flags": "; ".join(a.flags), "other_references": json.dumps(a.other_references, default=str),
        "validation_status": c.implementation_status, "seconds": round(seconds, 1),
        "zone": zone.label, "realm": zone.realm,
    }


def assess_zone(zone: Zone, provider, contracts: Optional[Dict[str, IC.IndicatorContract]] = None,
                require_validated: bool = False, config=None, log=print, only: Optional[Sequence[str]] = None,
                meta_out: Optional[Dict] = None) -> List[Dict]:
    """One audit row per contract. Nothing is skipped silently: every indicator gets a status and a reason."""
    contracts = contracts or IC.CONTRACTS
    commit = git_commit()
    t0 = time.perf_counter()
    ev = provider.evidence(zone)
    ev.validation_dataset_label = zone.validation_label
    if meta_out is not None:                                       # persist EVERYTHING the applicability rules were based on
        meta_out["evidence"] = {"domain": ev.domain, "site_area_m2": ev.site_area_m2, "ecosystem_tags": sorted(ev.ecosystem_tags),
                                "forest_baseline_m2": ev.forest_baseline_m2, "water_body_valid": ev.water_body_valid,
                                "n_pure_water_px": ev.n_pure_water_px, "water_probe": ev.water_probe,
                                "water_probe_detail": ev.water_probe_detail, "water_body_invalid_reason": ev.water_body_invalid_reason,
                                "diagnostics": ev.diagnostics}
    log(f"[{zone.label}] evidence ({time.perf_counter() - t0:.1f}s): domain={ev.domain} area={ev.site_area_m2:.0f} m2 "
        f"tags={sorted(ev.ecosystem_tags)} forest_baseline_m2={ev.forest_baseline_m2} "
        f"water_body_valid={ev.water_body_valid} pure_water_px={ev.n_pure_water_px}")
    rows: List[Dict] = []
    for name, c in contracts.items():
        if only and name not in only:
            continue
        t1 = time.perf_counter()
        site: Optional[SiteResult] = None
        refs: Dict[str, B.ReferenceData] = {}
        reason, _detail, _flags = B.check_applicability(c, ev)
        try:
            if reason or c.proposed_scoreability != "scoreable":
                a = B.evaluate_indicator(c, ev, None, None, {}, require_validated)      # no Earth Engine work at all
            elif not provider.implemented(name):
                a = B.evaluate_indicator(c, ev, None, None, {}, require_validated)
                a = B.IndicatorAssessment(indicator=name, status="pending_methodology",
                                          reason="v0.2.8_construct_not_implemented",
                                          detail="contract proposes scoring but the v0.2.8 site/reference construct is a later phase",
                                          direction=c.direction, estimator=c.estimator, reference_tier=c.reference_tier,
                                          reference_population=c.reference_population, reference_support=c.reference_support,
                                          flags=list(a.flags))
            else:
                site = provider.site(name, zone, ev)
                if site is not None and site.value is not None:
                    refs = provider.references(name, zone, ev, site) or {}
                a = B.evaluate_indicator(c, ev, None if site is None else site.value,
                                         None if site is None else site.spec, refs, require_validated)
        except Exception as e:                                        # never a silent hole: the failure IS the status
            logger.exception("indicator %s failed", name)
            a = B.IndicatorAssessment(indicator=name, status="applicable_but_no_site_value" if site is None or site.value is None
                                      else "applicable_but_no_reference",
                                      reason=f"provider_error: {type(e).__name__}", detail=str(e)[:300],
                                      direction=c.direction, estimator=c.estimator, reference_tier=c.reference_tier,
                                      reference_population=c.reference_population, reference_support=c.reference_support)
        ref = refs.get(c.reference_tier) if c.reference_tier else None
        prov = _provenance(c, zone, a, ref, site, config, commit)
        rows.append(_row(c, a, zone, site, ref, time.perf_counter() - t1, prov))
        log(f"  {name:28s} {a.status:38s} site={rows[-1]['site_value']!s:>12.12s} n={a.reference_n!s:>5s} "
            f"bench={a.benchmark if a.benchmark is None else round(a.benchmark, 4)!s:>8.8s} {rows[-1]['seconds']:>6.1f}s {a.reason}")
    return rows


def summarise(rows: Sequence[Dict]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for r in rows:
        out[r["status"]] = out.get(r["status"], 0) + 1
    return out


# ----------------------------------------------------------------------------------------
# Writers
# ----------------------------------------------------------------------------------------
def write_audit(rows: Sequence[Dict], out_dir: str, stem: str, meta: Optional[Dict] = None) -> Dict[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    cols = AUDIT_COLUMNS + EXTRA_COLUMNS
    paths = {"csv": os.path.join(out_dir, f"{stem}_audit.csv"), "json": os.path.join(out_dir, f"{stem}_audit.json"),
             "md": os.path.join(out_dir, f"{stem}_audit.md")}
    with open(paths["csv"], "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    with open(paths["json"], "w", encoding="utf-8") as f:
        json.dump({"code_version": CODE_VERSION, "git_commit": git_commit(), "summary": summarise(rows),
                   "meta": meta or {}, "rows": list(rows)}, f, indent=1, default=str)
    short = ["indicator", "status", "reason", "site_value", "reference_n", "reference_median", "benchmark", "score", "seconds"]
    with open(paths["md"], "w", encoding="utf-8") as f:
        f.write(f"# Audit trail: {rows[0]['zone'] if rows else ''}  ({rows[0]['realm'] if rows else ''})\n\n")
        f.write(f"Summary: {summarise(rows)}\n\n| " + " | ".join(short) + " |\n|" + "---|" * len(short) + "\n")
        for r in rows:
            f.write("| " + " | ".join("" if r.get(k) is None else (f"{r[k]:.4g}" if isinstance(r[k], float) else str(r[k])) for k in short) + " |\n")
    return paths


# ----------------------------------------------------------------------------------------
# Earth Engine provider (NOT verified live)
# ----------------------------------------------------------------------------------------
WINDOW_NAMES = ("natural_habitat", "net_tree_cover_change_rate", "ndvi", "chm", "bii", "ghm", "hdi", "light_pollution")
FOREST_NAME = "forest_loss_rate"
AQUATIC_NAMES = {"sabf": ("water", "_img_sabf"), "wcpi": ("water", "_img_wcpi"),
                 "sdi": ("ring", "_img_sdi"), "riparian_natural_veg_share": ("ring", "_img_natural_veg")}
IMPLEMENTED = set(WINDOW_NAMES) | {FOREST_NAME} | set(AQUATIC_NAMES)


class EEProvider:
    """Site values, evidence and references from Earth Engine, using the v0.2.8 cell / water-body builders and the
    SAME ecoregion / land-cover-stratum / HMI-threshold code the v0.2.7 live runs already exercised."""

    def __init__(self, config, registry, ee=None, selector=None, log=print):
        if ee is None:
            import ee as _ee
            ee = _ee
        self.ee, self.config, self.registry, self.log = ee, config, registry, log
        if selector is None:
            from darukaa_reference.reference import ReferenceSelector
            selector = ReferenceSelector(config)
        self.sel = selector
        self._ctx: Dict[str, Dict] = {}
        self._wb: Dict[tuple, Dict] = {}

    # ---------------------------------------------------------------- basics
    def implemented(self, name: str) -> bool:
        return name in IMPLEMENTED

    def _c(self, zone) -> Dict:
        return self._ctx[zone.label]

    def _img(self, name):
        import darukaa_reference.indicators as I
        fn = self.registry.get(name).metadata.get("gee_image_fn")
        return fn(self.config) if fn else None

    def _unit(self, name) -> str:
        return self.registry.get(name).unit

    def _temporal(self, c) -> str:
        return f"{c.temporal} | ndvi_year={getattr(self.config, 'ndvi_year', None)}"

    def _site_mean(self, image, zone, native: float) -> Optional[float]:
        ee, ctx = self.ee, self._c(zone)
        img = image.select(0).reproject(S.ee_native_projection(ee, native, ctx["crs"]))
        r = img.reduceRegion(reducer=ee.Reducer.mean(), geometry=ctx["eg"], scale=native, crs=ctx["crs"],
                             maxPixels=1e9).getInfo()
        for v in (r or {}).values():
            if v is not None:
                return float(v)
        return None

    # ---------------------------------------------------------------- evidence
    def evidence(self, zone: Zone) -> B.SiteEvidence:
        """Everything the applicability rules need, measured once per zone. EVERYTHING measured is kept in
        `diagnostics` and written to the audit trail (the first smoke test discarded it, so the Lake_Suman
        classification could not be explained). A failed probe is recorded as an ERROR, never as 'no water'."""
        import pyproj
        from shapely.ops import transform
        import darukaa_reference.indicators as I
        from darukaa_reference import reference_builders_ee as RB
        ee, cfg = self.ee, self.config
        eg = I._to_ee(zone.geometry)
        area = float(eg.area(1).getInfo())
        cen = zone.geometry.centroid
        crs = S.utm_crs_for(cen.x, cen.y)
        tr = pyproj.Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        poly_utm = transform(tr.transform, zone.geometry)
        centre_xy = tr.transform(cen.x, cen.y)
        ctx = {"eg": eg, "crs": crs, "area": area, "centre_xy": centre_xy, "site_bounds_utm": poly_utm.bounds}
        self._ctx[zone.label] = ctx
        diag: Dict[str, Any] = {"crs": crs, "site_area_m2": area, "site_area_utm_m2": poly_utm.area,
                                "centre_xy_utm": centre_xy, "site_bounds_utm": poly_utm.bounds, "errors": {}}
        tags = set()
        try:
            dw = I._dw_mode(cfg)
            tf = dw.eq(K.DW_TREES).reduceRegion(ee.Reducer.mean(), eg, 10, maxPixels=1e9).getInfo()
            tree_frac = next((v for v in (tf or {}).values() if v is not None), None)
            diag["tree_fraction"] = tree_frac
            if tree_frac is not None and tree_frac >= K.WOODY_MIN_TREE_FRACTION:
                tags.add("woody")
        except Exception as e:
            diag["errors"]["tree_fraction"] = f"{type(e).__name__}: {e}"[:300]
        baseline = None
        try:
            baseline = float(I._forest_baseline_and_loss(eg, cfg)[2].getInfo())
        except Exception as e:
            diag["errors"]["forest_baseline"] = f"{type(e).__name__}: {e}"[:300]
        diag["forest_baseline_m2"] = baseline
        probe, probe_detail, invalid_reason, wb_valid, n_pure = "error", "", "", False, None
        try:
            wm = RB.water_mask_s2(I._s2_masked(cfg).median())
            out = RB.water_body_reference_ee(
                ee, site_geometry=eg, site_bounds_utm=poly_utm.bounds, centre_xy=centre_xy, water_mask=wm,
                metric_image=ee.Image.constant(1), kind="water", native_scale_m=10.0, construct="probe", unit="u", temporal="t",
                population="comparable_water_bodies", want_reference=False, crs=crs,
                max_extent_m=float(getattr(cfg, "water_body_max_extent_m", K.MAX_WATER_BODY_EXTENT_M)), log=self.log)
            t = out.get("target")
            water_px = ee.Image.constant(1).updateMask(wm).reproject(S.ee_native_projection(ee, 10.0, crs)).reduceRegion(
                ee.Reducer.sum(), eg, scale=10, crs=crs, maxPixels=1e9).getInfo()
            wpx = next((v for v in (water_px or {}).values() if v is not None), None)
            diag["water_mask"] = {"definition": "MNDWI(B3,B11) > 0 on the S2 annual median; pure water = mask eroded 1 px",
                                  "water_px_in_site_coverage_weighted": wpx,
                                  "water_area_in_site_m2": None if wpx is None else wpx * 100.0, "grid": f"{crs} @ 10 m"}
            diag["water_body_probe"] = {"valid": out["valid"], "invalid_reason": out["invalid_reason"],
                                        "target": (None if t is None else {k: t.get(k) for k in
                                                   ("uid", "n_px", "area_m2", "geodesic_area_m2", "pure_px", "bbox", "cx", "cy", "interior")}),
                                        "attempts": out["diagnostics"].get("probe"), "max_extent_m": out["diagnostics"].get("max_extent_m")}
            invalid_reason = out["invalid_reason"]
            n_pure = out.get("n_pure_water_px")
            if out["valid"] or invalid_reason == "insufficient_pure_water":
                probe, wb_valid = "ok", True            # a complete water body exists; enough PURE water is a separate rule
            elif invalid_reason == "no_water_body_in_site":
                probe = "no_water_body"
            elif invalid_reason == "target_exceeds_max_extent":
                probe = "ok"                            # a body exists; it is outside the population rule (explicit reason)
            else:
                probe, probe_detail = "error", f"inconclusive: {invalid_reason}"
        except Exception as e:
            probe, probe_detail = "error", f"{type(e).__name__}: {e}"[:400]
            diag["errors"]["water_probe"] = probe_detail
        diag["ecosystem_classification"] = {
            "woody": "woody" in tags, "open_water": bool(wb_valid and (n_pure or 0) >= IC.MIN_PURE_WATER_PIXELS),
            "rule_open_water": f"a complete water body touches the site with >= {IC.MIN_PURE_WATER_PIXELS} pure-water px",
            "water_probe": probe, "water_probe_detail": probe_detail, "invalid_reason": invalid_reason}
        if diag["ecosystem_classification"]["open_water"]:
            tags.add("open_water")
        return B.SiteEvidence(domain=zone.realm, site_area_m2=area, ecosystem_tags=frozenset(tags), forest_baseline_m2=baseline,
                              water_body_valid=wb_valid, n_pure_water_px=n_pure, water_probe=probe, water_probe_detail=probe_detail,
                              water_body_invalid_reason=invalid_reason, diagnostics=diag)

    # ---------------------------------------------------------------- site values
    def site(self, name: str, zone: Zone, ev: B.SiteEvidence) -> Optional[SiteResult]:
        import darukaa_reference.indicators as I
        c = IC.CONTRACTS[name]
        native = float(c.native_resolution_m)
        if name in WINDOW_NAMES:
            img = self._img(name)
            if img is None:
                return SiteResult(None, self._unit(name), None, {"reason": "indicator image unavailable"})
            v = self._site_mean(img, zone, native)
            spec = B.MetricSpec(name, self._unit(name), self._temporal(c), c.site_support, "site", native_scale_m=native)
            return SiteResult(v, self._unit(name), spec, {"native_scale_m": native, "crs": self._c(zone)["crs"],
                                                          "aggregation": "reduceRegion(mean) on the native UTM grid"})
        if name == FOREST_NAME:
            r = I.extract_forest_loss_rate(zone.geometry, self.config)
            spec = B.MetricSpec(name, "percent_per_year", self._temporal(c), c.site_support, "site", native_scale_m=native)
            return SiteResult(r.get("value"), "percent_per_year", spec, r.get("metadata", {}) or {})
        if name in AQUATIC_NAMES:
            out = self._water_body(name, zone, want_reference=True)
            spec = out.get("site_spec")
            if not out["valid"] or spec is None:
                return SiteResult(None, self._unit(name), spec, {"reason": out["invalid_reason"]})
            t = out["target"]
            return SiteResult(float(t["value"]), self._unit(name), spec,
                              {"target_area_m2": t["area_m2"], "n_pure_water_px": t["pure_px"], "target_permanence": t.get("permanence"),
                               "radius_used_km": out.get("radius_used_km")})
        return None

    def _water_body(self, name: str, zone: Zone, want_reference: bool) -> Dict:
        key = (zone.label, name)
        if key in self._wb:
            return self._wb[key]
        import darukaa_reference.indicators as I
        from darukaa_reference import reference_builders_ee as RB
        ee, cfg, ctx = self.ee, self.config, self._c(zone)
        c = IC.CONTRACTS[name]
        kind, fn = AQUATIC_NAMES[name]
        metric = getattr(I, fn)(cfg)
        wm = RB.water_mask_s2(I._s2_masked(cfg).median())
        out = RB.water_body_reference_ee(
            ee, site_geometry=ctx["eg"], site_bounds_utm=ctx["site_bounds_utm"], centre_xy=ctx["centre_xy"], water_mask=wm,
            metric_image=metric, kind=kind, native_scale_m=float(c.native_resolution_m), construct=name, unit=self._unit(name),
            temporal=self._temporal(c), population=c.reference_population, tier=c.reference_tier or "tier2",
            radii_km=tuple(getattr(cfg, "water_body_reference_radii_km", (10.0, 25.0, 50.0))),
            min_reference_n=c.min_reference_n or IC.MIN_COMPARABLE_WATER_BODIES, permanence_image=I._s1_water_occurrence(cfg),
            ring_width_m=float(getattr(cfg, "riparian_ring_width_m", K.RIPARIAN_RING_WIDTH_M)),
            min_pure_px=IC.MIN_PURE_WATER_PIXELS, want_reference=want_reference, crs=ctx["crs"],
            max_extent_m=float(getattr(cfg, "water_body_max_extent_m", K.MAX_WATER_BODY_EXTENT_M)), log=self.log)
        self._wb[key] = out
        return out

    # ---------------------------------------------------------------- references
    def references(self, name: str, zone: Zone, ev: B.SiteEvidence, site: SiteResult) -> Dict[str, B.ReferenceData]:
        c = IC.CONTRACTS[name]
        if name in AQUATIC_NAMES:
            ref = self._water_body(name, zone, want_reference=True).get("reference")
            return {c.reference_tier: ref} if ref is not None else {}
        if name in WINDOW_NAMES or name == FOREST_NAME:
            return self._cell_references(name, zone, ev, site)
        return {}

    def _radius_km(self, name) -> float:
        return float(self.registry.get(name).reference_radius_km or getattr(self.config, "reference_buffer_km", 50.0))

    def _population(self, zone: Zone, pop: str, radius_km: float):
        """(reference_zone, mask_image|None, definition text, diagnostics) for a reference population."""
        ee, cfg, sel, ctx = self.ee, self.config, self.sel, self._c(zone)
        eg = ctx["eg"]
        rz = eg.centroid().buffer(radius_km * 1000.0)
        diag: Dict[str, Any] = {"population": pop, "radius_km": radius_km}
        parts, mask = [f"within {radius_km:g} km of the site"], None

        def AND(m, x):
            return x if m is None else m.And(x)
        eco_masked = None
        if pop != "regional_all":
            if zone.eco_id is not None and getattr(cfg, "ecoregion_gee_asset", ""):
                fc = ee.FeatureCollection(cfg.ecoregion_gee_asset).filter(ee.Filter.eq("ECO_ID", int(zone.eco_id)))
                eco_masked = ee.Image.constant(0).paint(fc, 1).selfMask()
                mask = AND(mask, eco_masked.eq(1))
                parts.append(f"ecoregion ECO_ID={zone.eco_id}")
            else:
                diag["warning"] = "no ecoregion available: population NOT ecoregion-constrained"
        lc_mask = None
        if pop in ("least_disturbed_stratum", "regional_stratum_unfiltered"):
            lc_image, lc_diag = sel._build_ecoregion_landcover_image(ee, rz)
            site_lc = lc_image.reduceRegion(reducer=ee.Reducer.mode(), geometry=eg, scale=10, maxPixels=1e6).getInfo()
            lc_value = next((v for v in (site_lc or {}).values() if v is not None), None)
            diag["landcover_class"] = lc_value
            if lc_value is None:
                return rz, None, "", {**diag, "failed": "site land-cover class unavailable"}
            lc_mask = lc_image.eq(ee.Number(lc_value))
            mask = AND(mask, lc_mask)
            parts.append(f"Dynamic World land-cover class {lc_value} (ecoregion_landcover stratum)")
        if pop == "least_disturbed_stratum":
            hmi = (ee.ImageCollection(cfg.hmi_gee_asset_legacy).first().select(cfg.hmi_gee_band_legacy)
                   if getattr(cfg, "use_legacy_hmi_asset", False)
                   else ee.ImageCollection(cfg.hmi_gee_asset).first().select(cfg.hmi_gee_band))
            base = hmi
            if eco_masked is not None:
                base = base.updateMask(eco_masked)
            if lc_mask is not None:
                base = base.updateMask(lc_mask)
            thr = sel._dynamic_hmi_threshold(base.clip(rz), rz, cfg.hmi_hard_ceiling)
            diag["hmi_threshold"] = thr
            if thr is None:
                return rz, None, "", {**diag, "failed": "HMI threshold unavailable"}
            mask = AND(mask, hmi.lte(ee.Number(thr)))
            parts.append(f"HMI <= {float(thr):.4f} (min(P5, ceiling {cfg.hmi_hard_ceiling}))")
        if pop == "regional_stratum_unfiltered":
            parts.append("NO pressure (HMI) filter (independent-reference design, item 3 option B)")
        return rz, mask, "; ".join(parts), diag

    def _cell_references(self, name, zone, ev, site) -> Dict[str, B.ReferenceData]:
        import darukaa_reference.indicators as I
        from darukaa_reference import reference_builders_ee as RB
        ee, cfg, ctx = self.ee, self.config, self._c(zone)
        c = IC.CONTRACTS[name]
        native, crs, area = float(c.native_resolution_m), ctx["crs"], ev.site_area_m2
        radius_km = self._radius_km(name)
        rz, mask, pdef, diag = self._population(zone, c.reference_population, radius_km)
        if mask is None and c.reference_population != "regional_all":
            self.log(f"  {name}: population could not be built ({diag.get('failed')})")
            return {}
        if name == FOREST_NAME:
            num, den, years = I._forest_loss_terms_image(cfg)
            cell = S.ee_block_rate_image(ee, num, den, native, area, years, crs, IC.FOREST_BASELINE_MIN_M2)
            support, unit = "site_window_rate", "percent_per_year"
        else:
            cell = S.ee_block_mean_image(ee, self._img(name), native, area, crs)
            support, unit = c.reference_support, self._unit(name)
        k = S.cell_size_px(area, native)
        definition = (f"{c.reference_population}: site-sized cells ({k} x {k} native px of {native:g} m, centre pixel eligible) {pdef}")
        ref = RB.cell_reference_tiled_ee(
            ee, cell_image=cell, mask=mask, centre_xy=ctx["centre_xy"], radius_m=radius_km * 1000.0, native_scale_m=native,
            site_area_m2=area, crs=crs, n=int(getattr(cfg, "reference_sample_pixels", 5000)),
            seed=int(getattr(cfg, "reference_sample_seed", 12345)), support=support, construct=name, unit=unit,
            temporal=self._temporal(c), population=c.reference_population, tier=c.reference_tier,
            population_definition=definition, tile_native_px=int(getattr(cfg, "reference_tile_native_px", 3072)),
            extra={**diag, "cell_area_ratio_to_site": (k * native) ** 2 / area}, log=self.log)
        return {c.reference_tier: ref}


# ----------------------------------------------------------------------------------------
# Convenience entry points for the notebook
# ----------------------------------------------------------------------------------------
def load_zone(config, registry, path: str, label: str, realm: str, validation_label: Optional[str] = None) -> Zone:
    """Load one tile exactly as the pipeline does (loader + ecoregion resolver)."""
    from darukaa_reference.pipeline import Pipeline
    pipe = Pipeline(config, registry)
    sites = pipe.resolver.resolve(pipe.loader.load(path))
    row = sites.iloc[0]
    eco = row.get("ECO_ID")
    return Zone(label=label, geometry=row.geometry, realm=realm,
                eco_id=None if eco is None or (isinstance(eco, float) and np.isnan(eco)) else int(eco),
                validation_label=validation_label)


FOREST_VALIDATION_LABEL = "methodological_validation_forest_loss"
FOREST_VALIDATION_PROJECTS = ("FCF_GV", "FCF_Soova")          # existing Darukaa forest-project assets (Odisha); NOT Tata, never in Tata scoring


def find_candidate_tiles(repo_root: str, projects: Sequence[str] = FOREST_VALIDATION_PROJECTS, top: int = 6) -> List[Dict]:
    """Existing tile files of the forest projects, largest first: [{label, path, area_ha, project}]. Nothing is invented; if the
    assets are missing the list is empty and the caller must say so."""
    import glob
    import geopandas as gpd
    rows = []
    for proj in projects:
        for path in glob.glob(os.path.join(repo_root, "**", "projects", proj, "outputs", "07_reference_handoff*", "tiles", "*.geojson"), recursive=True):
            g = gpd.read_file(path)
            rows.append({"label": os.path.basename(path)[:-len(".geojson")], "path": path, "project": proj,
                         "area_ha": float(g.to_crs(6933).geometry.area.sum()) / 1e4})
    return sorted(rows, key=lambda r: -r["area_ha"])[:top]


def select_forest_validation_zone(provider, candidates: Sequence[Zone], min_baseline_ha: float = IC.FOREST_BASELINE_MIN_M2 / 1e4,
                                  log=print) -> Tuple[Optional[Zone], List[Dict]]:
    """Measure LIVE Hansen baseline forest and primary-window loss inside each existing candidate tile and pick the one that gives the
    forest-loss parity check real power: baseline >= 5 ha (the applicability rule) AND non-zero loss; among those the largest loss.
    Returns (zone relabelled as a methodological validation dataset | None, table of every candidate). Never invents a polygon."""
    import dataclasses
    import darukaa_reference.indicators as I
    table: List[Dict] = []
    for z in candidates:
        row = {"label": z.label, "area_ha": None, "baseline_ha": None, "loss_ha_primary_window": None, "eligible": False, "error": ""}
        try:
            eg = I._to_ee(z.geometry)
            row["area_ha"] = float(eg.area(1).getInfo()) / 1e4
            out = I._forest_baseline_and_loss(eg, provider.config)
            row["baseline_ha"] = float(out[2].getInfo()) / 1e4
            row["loss_ha_primary_window"] = float(out[5][out[4]].getInfo()) / 1e4
            row["eligible"] = row["baseline_ha"] >= min_baseline_ha and row["loss_ha_primary_window"] > 0
        except Exception as e:
            row["error"] = f"{type(e).__name__}: {e}"[:200]
        table.append(row)
        log(f"  validation candidate {z.label}: baseline {row['baseline_ha']} ha, loss {row['loss_ha_primary_window']} ha, eligible={row['eligible']} {row['error']}")
    ok = [(r, z) for r, z in zip(table, candidates) if r["eligible"]]
    if not ok:
        return None, table
    best_row, best = max(ok, key=lambda rz: (rz[0]["loss_ha_primary_window"], -rz[0]["area_ha"]))
    return dataclasses.replace(best, validation_label=FOREST_VALIDATION_LABEL), table


def run_smoke_test(config, registry, zone: Zone, out_dir: str = "outputs/smoke", provider=None, log=print,
                   only: Optional[Sequence[str]] = None) -> List[Dict]:
    """Assess one zone end to end and write the audit trail. Never touches headline aggregation."""
    provider = provider or EEProvider(config, registry, log=log)
    t0 = time.perf_counter()
    meta: Dict = {}
    rows = assess_zone(zone, provider, config=config, log=log, only=only, meta_out=meta)
    paths = write_audit(rows, out_dir, f"{zone.label}", meta=meta)
    log(f"\n[{zone.label}] done in {(time.perf_counter() - t0) / 60:.1f} min. Status summary: {summarise(rows)}")
    log(f"Audit trail written: {paths}")
    return rows
