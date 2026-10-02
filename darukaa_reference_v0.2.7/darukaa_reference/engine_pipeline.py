"""
engine_pipeline.py -- the general assessment pipeline on the frozen v0.2.8 engine (v0.2.9 Phase 5)
=================================================================================================

    project / site manifest  ->  ZoneSpecs (label, tile, REALM)  ->  frozen engine, once per zone  ->  per-zone audit trail (JSON/CSV/MD)
                             ->  engine_report (status policy, per-realm worst-zone aggregation, coverage, headline)  ->  project JSON / CSV / HTML

Site extraction, applicability, reference construction, benchmarking and scoring are done by the FROZEN engine (`assess.run_smoke_test` -> `assess_zone`), called
exactly as the standalone (notebook) runs called it; this module adds orchestration only. It contains no project names and no per-project branches: everything it
knows about a project comes from the manifest (see manifest.py).

Safety: before any zone is assessed, the run's provenance is checked. If the engine modules differ from the frozen engine (`engine_closure_matches_frozen`), the run
is refused (results would not be v0.2.8-engine results). `strict_provenance=True` (default) also refuses on a dirty / moved checkout or a changed engine-read
configuration, because those make the result's identity unprovable.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
from typing import Any, Callable, Dict, List, Optional, Sequence

from darukaa_reference import assess as A
from darukaa_reference import engine_report as ER
from darukaa_reference import indicator_contract as IC
from darukaa_reference import provenance as PV
from darukaa_reference.manifest import ZoneSpec

logger = logging.getLogger(__name__)

PIPELINE_VERSION = "v0.2.9-pipeline (phase 5: general engine pipeline)"


class ProvenanceRefusal(RuntimeError):
    """The run's identity cannot be proven; no zone was assessed."""


def check_run_provenance(config: Any, strict: bool = True) -> Dict[str, Any]:
    prov = PV.run_provenance(config, A.CODE_VERSION)
    engine = prov["engine"]
    hard = [w for w in prov["warnings"] if w.startswith("engine_not_frozen")]
    if hard:
        raise ProvenanceRefusal("; ".join(hard))
    if strict and prov["warnings"]:
        raise ProvenanceRefusal("strict_provenance: " + "; ".join(prov["warnings"]))
    return prov


def _resumable(audit_json: str, prov: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """An existing audit is reused only if it was produced by EXACTLY this code (source SHA), engine SHA and configuration."""
    if not os.path.exists(audit_json):
        return None
    try:
        with open(audit_json, encoding="utf-8") as fh:
            d = json.load(fh)
        p = d.get("provenance") or {}
        e = p.get("engine") or {}
        same = (p.get("source_sha256_at_import") == prov["source_sha256_at_import"] and p.get("config_sha256") == prov["config_sha256"]
                and e.get("engine_closure_sha256_at_import") == prov["engine"]["engine_closure_sha256_at_import"] and e.get("engine_closure_matches_frozen") is True)
        return d if same else None
    except Exception:
        return None


def _zone_record(spec: ZoneSpec, d: Dict[str, Any], resumed: bool, out_dir: str) -> Dict[str, Any]:
    ev = (d.get("meta") or {}).get("evidence") or {}
    area_m2 = ev.get("site_area_m2")
    return {"label": spec.label, "realm": spec.realm, "area_ha": (area_m2 / 1e4 if area_m2 else None), "rows": d["rows"], "meta": d.get("meta") or {},
            "realm_source": spec.realm_source, "companion_source": spec.companion_source, "resumed": resumed,
            "audit_files": {k: os.path.join(out_dir, f"{spec.label}_audit.{k}") for k in ("json", "csv", "md")}}


def run_engine_project(config: Any, registry: Any, project_name: str, specs: Sequence[ZoneSpec], output_dir: str,
                       provider_factory: Optional[Callable[[Any, Any], Any]] = None, zone_loader: Optional[Callable[..., Any]] = None,
                       resume: bool = False, continue_on_zone_failure: bool = True, strict_provenance: bool = True, write_report: bool = True,
                       log: Callable[..., None] = print) -> Dict[str, Any]:
    """Assess every zone with the frozen engine and build the project report. Returns the report dict (also written to
    `<output_dir>/<project_name>_project.{json,csv,html}` when write_report)."""
    prov = check_run_provenance(config, strict_provenance)
    os.makedirs(output_dir, exist_ok=True)
    zone_loader = zone_loader or A.load_zone
    zones: List[Dict[str, Any]] = []
    failed: Dict[str, str] = {}
    for spec in specs:
        audit_json = os.path.join(output_dir, f"{spec.label}_audit.json")
        existing = _resumable(audit_json, prov) if resume else None
        if existing is not None:
            log(f"[{spec.label}] RESUMED from an existing audit produced by identical code, engine and configuration")
            zones.append(_zone_record(spec, existing, True, output_dir))
            continue
        try:
            zone = zone_loader(config, registry, spec.path, spec.label, spec.realm)
            provider = provider_factory(config, registry) if provider_factory else None
            # the SAME call the standalone run made: A.run_smoke_test(config, registry, zone, out_dir=OUT)
            A.run_smoke_test(config, registry, zone, out_dir=output_dir, provider=provider, log=log)
            with open(audit_json, encoding="utf-8") as fh:
                zones.append(_zone_record(spec, json.load(fh), False, output_dir))
        except Exception as e:                                  # a failed zone is recorded and reported, never silently dropped
            logger.error("zone %s FAILED: %s", spec.label, e)
            failed[spec.label] = f"{type(e).__name__}: {e}"
            if not continue_on_zone_failure:
                raise
    if not zones:
        raise RuntimeError(f"All {len(specs)} zone(s) failed; no project report can be built: {failed}")
    meta = {"generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "pipeline_version": PIPELINE_VERSION,
            "engine": {"code_version": A.CODE_VERSION, "contract_version": getattr(IC, "CONTRACT_VERSION", None), **prov["engine"]},
            "provenance": prov, "n_zones_requested": len(specs), "realm_sources": {s.label: s.realm_source for s in specs},
            "companion_sources": {s.label: s.companion_source for s in specs if s.companion_source},
            "zone_projects": {s.label: s.project for s in specs}}
    report = ER.build_project_report(project_name, zones, registry, meta=meta, failed_zones=failed)
    if write_report:
        write_project_outputs(report, output_dir, project_name)
    return report


def write_project_outputs(report: Dict[str, Any], output_dir: str, project_name: str) -> Dict[str, str]:
    from darukaa_reference import html_report
    os.makedirs(output_dir, exist_ok=True)
    base = os.path.join(output_dir, f"{project_name}_project")
    paths = {"json": base + ".json", "csv": base + ".csv", "html": base + ".html"}
    with open(paths["json"], "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1, default=str)
    with open(paths["csv"], "w", encoding="utf-8", newline="") as fh:
        fh.write(ER.csv_text(report))
    html_report.write_html(report, paths["html"], project_name=project_name)
    return paths
