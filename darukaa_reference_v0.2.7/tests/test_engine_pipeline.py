"""General engine pipeline: orchestration, provenance gate, failure handling, resume, the CLI, and absence of project-specific code. Earth Engine is replaced by a
deterministic fake (tests/_fake_engine.py); the engine code (assess_zone / evaluate_indicator) is the REAL frozen engine."""
import dataclasses
import importlib.util
import json
import logging
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _fake_engine as F
from darukaa_reference import assess as A
from darukaa_reference import engine_identity as EI
from darukaa_reference import engine_pipeline as EP
from darukaa_reference import manifest as M
from darukaa_reference import provenance as PV
from darukaa_reference.config import Config
from darukaa_reference.indicators import create_default_registry

REPO = Path(__file__).resolve().parents[2]
PKG = Path(__file__).resolve().parents[1]
NB = dict(gee_project='gaurav-singh-007', output_dir='outputs', archetype='industrial', realm='terrestrial', assessment_mode='baseline',
          hmi_hard_ceiling=0.05, use_variance_stability_floor=True, reference_stratification='ecoregion_landcover')


@pytest.fixture(autouse=True)
def quiet():
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)


@pytest.fixture
def cfg():
    return Config(**NB)


@pytest.fixture
def reg():
    return create_default_registry()


@pytest.fixture
def clean_loaded(monkeypatch):
    """A clean, frozen loaded state, independent of whether the developer's tree has uncommitted edits."""
    loaded = dict(PV.LOADED); loaded.update(dirty=False, dirty_files=[], engine_sha256=EI.FROZEN_ENGINE_SHA256)
    monkeypatch.setattr(PV, "LOADED", loaded)
    return loaded


def specs_of(project):
    return M.resolve_zone_specs(M.find_manifest_by_project_name(REPO, project), REPO)


def run(cfg, reg, project, out, **kw):
    name, specs = specs_of(project)
    kw.setdefault("strict_provenance", False)
    return EP.run_engine_project(cfg, reg, name, specs, str(out), provider_factory=F.fake_factory, zone_loader=F.stub_zone_loader, log=lambda *a, **k: None, **kw)


# ---------------------------------------------------------------- orchestration
def test_every_zone_is_assessed_by_the_engine_and_every_output_is_written(tmp_path, cfg, reg):
    rep = run(cfg, reg, "TataMotors_Pimpri", tmp_path)
    assert rep["meta"]["n_zones"] == 15 and rep["meta"]["n_zones_failed"] == 0 and list(rep["realms"]) == ["terrestrial", "aquatic"]
    for label in rep["zones"]:
        for ext in ("json", "csv", "md"):
            assert (tmp_path / f"{label}_audit.{ext}").exists(), (label, ext)
    for ext in ("json", "csv", "html"):
        assert (tmp_path / f"TataMotors_Pimpri_project.{ext}").exists()
    assert all(len(z["rows"]) == len(IC_CONTRACTS()) for z in rep["zones"].values())
    assert any(r["status"] == "scored" for z in rep["zones"].values() for r in z["rows"])


def IC_CONTRACTS():
    from darukaa_reference import indicator_contract as IC
    return IC.CONTRACTS


def test_the_engine_is_called_through_the_same_entry_point_and_arguments_as_the_standalone_run(tmp_path, cfg, reg, monkeypatch):
    calls = []
    real = A.run_smoke_test

    def spy(config, registry, zone, out_dir="outputs/smoke", provider=None, log=print, only=None):
        calls.append({"config": config, "registry": registry, "label": zone.label, "realm": zone.realm, "out_dir": out_dir, "only": only,
                      "geometry_is_real": zone.geometry is not None and not zone.geometry.is_empty})
        return real(config, registry, zone, out_dir=out_dir, provider=provider, log=log, only=only)
    monkeypatch.setattr(A, "run_smoke_test", spy)
    name, specs = specs_of("TataMotors_Pimpri")
    run(cfg, reg, "TataMotors_Pimpri", tmp_path)
    assert [(c["label"], c["realm"]) for c in calls] == [(s.label, s.realm) for s in specs]
    assert all(c["config"] is cfg and c["registry"] is reg and c["out_dir"] == str(tmp_path) and c["only"] is None and c["geometry_is_real"] for c in calls)


def test_site_extraction_applicability_reference_benchmark_and_score_all_come_from_the_engine(tmp_path, cfg, reg, monkeypatch):
    seen = {"assess_zone": 0, "evaluate_indicator": 0, "check_applicability": 0}
    from darukaa_reference import benchmarking as B
    real_az, real_ev, real_ca = A.assess_zone, B.evaluate_indicator, B.check_applicability

    def az(*a, **k):
        seen["assess_zone"] += 1
        return real_az(*a, **k)

    def ev(*a, **k):
        seen["evaluate_indicator"] += 1
        return real_ev(*a, **k)

    def ca(*a, **k):
        seen["check_applicability"] += 1
        return real_ca(*a, **k)
    monkeypatch.setattr(A, "assess_zone", az); monkeypatch.setattr(B, "evaluate_indicator", ev); monkeypatch.setattr(B, "check_applicability", ca)
    run(cfg, reg, "TataMotors_Pimpri", tmp_path)
    assert seen["assess_zone"] == 15 and seen["evaluate_indicator"] == 15 * 46 and seen["check_applicability"] >= 15 * 46      # applicability is checked in assess_zone AND inside evaluate_indicator


def test_the_legacy_pipeline_is_not_involved_in_the_engine_path(tmp_path, cfg, reg, monkeypatch):
    from darukaa_reference import pipeline as legacy
    monkeypatch.setattr(legacy.Pipeline, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("legacy Pipeline.run was called")))
    import darukaa_reference.reference as R
    monkeypatch.setattr(R.ReferenceSelector, "compute", lambda *a, **k: (_ for _ in ()).throw(AssertionError("legacy ReferenceSelector was called")))
    run(cfg, reg, "TataMotors_Pimpri", tmp_path)


def test_realms_in_the_report_are_the_manifest_declared_realms_and_stay_separate(tmp_path, cfg, reg):
    rep = run(cfg, reg, "TataMotors_Pimpri", tmp_path)
    assert rep["meta"]["zones_by_realm"]["terrestrial"] == [s.label for s in specs_of("TataMotors_Pimpri")[1][:9]]
    assert len(rep["meta"]["zones_by_realm"]["aquatic"]) == 6
    assert set(rep["meta"]["realm_sources"].values()) == {"manifest"}
    for z in rep["zones"].values():
        assert {r["realm"] for r in z["rows"]} == {z["realm"]}
    t_ind = rep["realms"]["terrestrial"]["aggregation"]["per_indicator"]
    a_ind = rep["realms"]["aquatic"]["aggregation"]["per_indicator"]
    assert "sabf" not in t_ind and "natural_habitat" not in a_ind                         # in-domain tables differ: realm separation by the frozen contract


# ---------------------------------------------------------------- provenance gate
def test_the_run_is_refused_if_the_engine_is_not_the_frozen_engine_even_when_not_strict(tmp_path, cfg, reg, monkeypatch, clean_loaded):
    loaded = dict(PV.LOADED); loaded["engine_sha256"] = "0" * 64
    monkeypatch.setattr(PV, "LOADED", loaded)
    name, specs = specs_of("SoulForest_Veltoor")
    with pytest.raises(EP.ProvenanceRefusal, match="engine_not_frozen"):
        EP.run_engine_project(cfg, reg, name, specs, str(tmp_path), provider_factory=F.fake_factory, zone_loader=F.stub_zone_loader, strict_provenance=False)
    assert not list(tmp_path.glob("*_audit.json"))                                          # nothing was assessed


def test_strict_provenance_refuses_a_dirty_checkout_but_non_strict_records_it(tmp_path, cfg, reg, monkeypatch, clean_loaded):
    dirty = dict(PV.LOADED); dirty.update(dirty=True, dirty_files=["x.py"])
    monkeypatch.setattr(PV, "LOADED", dirty)
    name, specs = specs_of("SoulForest_Veltoor")
    with pytest.raises(EP.ProvenanceRefusal, match="strict_provenance"):
        EP.run_engine_project(cfg, reg, name, specs, str(tmp_path), provider_factory=F.fake_factory, zone_loader=F.stub_zone_loader)
    rep = EP.run_engine_project(cfg, reg, name, specs, str(tmp_path / "ok"), provider_factory=F.fake_factory, zone_loader=F.stub_zone_loader,
                                strict_provenance=False, log=lambda *a, **k: None)
    assert rep["meta"]["provenance"]["dirty"] is True and rep["meta"]["provenance"]["warnings"]


def test_an_engine_config_difference_is_refused_in_strict_mode_and_recorded_otherwise(tmp_path, cfg, reg, clean_loaded):
    changed = dataclasses.replace(cfg, ndvi_year=2024)
    name, specs = specs_of("SoulForest_Veltoor")
    with pytest.raises(EP.ProvenanceRefusal, match="ndvi_year"):
        EP.run_engine_project(changed, reg, name, specs, str(tmp_path), provider_factory=F.fake_factory, zone_loader=F.stub_zone_loader)
    rep = EP.run_engine_project(changed, reg, name, specs, str(tmp_path / "x"), provider_factory=F.fake_factory, zone_loader=F.stub_zone_loader,
                                strict_provenance=False, log=lambda *a, **k: None)
    assert rep["meta"]["engine"]["engine_config_matches_frozen"] is False and "ndvi_year" in rep["meta"]["engine"]["engine_config_diff"]


def test_a_clean_frozen_checkout_passes_strict_mode_and_the_report_carries_the_engine_identity(tmp_path, cfg, reg, clean_loaded):
    name, specs = specs_of("SoulForest_Veltoor")
    rep = EP.run_engine_project(cfg, reg, name, specs, str(tmp_path), provider_factory=F.fake_factory, zone_loader=F.stub_zone_loader, log=lambda *a, **k: None)
    e = rep["meta"]["engine"]
    assert e["engine_sha256_at_import"] == EI.FROZEN_ENGINE_SHA256 and e["engine_matches_frozen"] and e["engine_config_matches_frozen"]
    assert e["contract_version"] == "0.2.8" and e["code_version"] == A.CODE_VERSION
    for z in rep["zones"].values():                                                         # the per-zone audit file carries the same engine identity
        d = json.loads(Path(z["audit_files"]["json"]).read_text())
        assert d["provenance"]["engine"]["engine_sha256_at_import"] == EI.FROZEN_ENGINE_SHA256


# ---------------------------------------------------------------- failures
def test_a_failed_zone_is_recorded_not_dropped_and_the_rest_continue(tmp_path, cfg, reg):
    def loader(config, registry, path, label, realm):
        if label == "Pond_2":
            raise RuntimeError("Computation timed out.")
        return F.stub_zone_loader(config, registry, path, label, realm)
    name, specs = specs_of("TataMotors_Pimpri")
    rep = EP.run_engine_project(cfg, reg, name, specs, str(tmp_path), provider_factory=F.fake_factory, zone_loader=loader, strict_provenance=False, log=lambda *a, **k: None)
    assert rep["meta"]["failed_zones"] == {"Pond_2": "RuntimeError: Computation timed out."} and rep["meta"]["n_zones"] == 14
    assert "Pond_2" not in rep["zones"] and "Pond_2" in (tmp_path / "TataMotors_Pimpri_project.html").read_text()      # the failure is shown in the report
    with pytest.raises(RuntimeError, match="Computation timed out"):
        EP.run_engine_project(cfg, reg, name, specs, str(tmp_path / "b"), provider_factory=F.fake_factory, zone_loader=loader, strict_provenance=False,
                              continue_on_zone_failure=False, log=lambda *a, **k: None)


def test_if_every_zone_fails_there_is_no_report(tmp_path, cfg, reg):
    def loader(*a, **k):
        raise RuntimeError("boom")
    name, specs = specs_of("SoulForest_Veltoor")
    with pytest.raises(RuntimeError, match="All 7 zone"):
        EP.run_engine_project(cfg, reg, name, specs, str(tmp_path), provider_factory=F.fake_factory, zone_loader=loader, strict_provenance=False, log=lambda *a, **k: None)


# ---------------------------------------------------------------- resume
def test_resume_reuses_only_audits_from_identical_code_engine_and_configuration(tmp_path, cfg, reg):
    first = run(cfg, reg, "SoulForest_Veltoor", tmp_path)
    calls = []

    class Counting(F.FakeEngineProvider):
        def evidence(self, zone):
            calls.append(zone.label)
            return super().evidence(zone)
    again = run(cfg, reg, "SoulForest_Veltoor", tmp_path, resume=True) if False else None
    name, specs = specs_of("SoulForest_Veltoor")
    rep = EP.run_engine_project(cfg, reg, name, specs, str(tmp_path), provider_factory=lambda c, r: Counting(c, r), zone_loader=F.stub_zone_loader,
                                resume=True, strict_provenance=False, log=lambda *a, **k: None)
    assert calls == [] and all(z["resumed_from_existing_audit"] for z in rep["zones"].values())
    for label, z in rep["zones"].items():                                                   # a resumed zone's rows equal the original run's
        assert [r["score"] for r in z["rows"]] == [r["score"] for r in first["zones"][label]["rows"]]
    # tamper: a different engine fingerprint, a different configuration, a different source -> NOT reused
    victim = tmp_path / "SEG01_audit.json"
    d = json.loads(victim.read_text()); d["provenance"]["engine"]["engine_sha256_at_import"] = "1" * 64; victim.write_text(json.dumps(d))
    victim2 = tmp_path / "SEG02_audit.json"
    d = json.loads(victim2.read_text()); d["provenance"]["config_sha256"] = "2" * 64; victim2.write_text(json.dumps(d))
    victim3 = tmp_path / "SEG03_audit.json"
    d = json.loads(victim3.read_text()); d["provenance"]["source_sha256_at_import"] = "3" * 64; victim3.write_text(json.dumps(d))
    calls.clear()
    EP.run_engine_project(cfg, reg, name, specs, str(tmp_path), provider_factory=lambda c, r: Counting(c, r), zone_loader=F.stub_zone_loader,
                          resume=True, strict_provenance=False, log=lambda *a, **k: None)
    assert sorted(calls) == ["SEG01", "SEG02", "SEG03"]


# ---------------------------------------------------------------- no project-specific code
FORBIDDEN = re.compile(r"tata|soul ?forest|pimpri|veltoor|corbett|\bfcf\b|soova|deccan|narmada|suman|sharma|ganjam", re.I)
GENERAL_MODULES = ["manifest.py", "engine_pipeline.py", "engine_report.py", "engine_html.py", "engine_identity.py"]


@pytest.mark.parametrize("module", GENERAL_MODULES)
def test_general_modules_contain_no_project_names(module):
    src = (PKG / "darukaa_reference" / module).read_text()
    assert not FORBIDDEN.findall(src), (module, FORBIDDEN.findall(src))


def test_the_engine_path_in_the_runner_contains_no_project_names():
    src = (PKG / "run_project_from_manifest.py").read_text()
    body = src[src.index("def _main_engine"):src.index("def main():")]
    assert not FORBIDDEN.findall(body)


# ---------------------------------------------------------------- CLI
def _runner():
    spec = importlib.util.spec_from_file_location("runner_under_test", PKG / "run_project_from_manifest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_cli_defaults_to_the_v028_engine_and_resolves_zones_from_the_manifest(monkeypatch, tmp_path):
    import darukaa_reference.engine_pipeline as ep
    seen = {}
    mod = _runner()
    monkeypatch.setattr(mod, "_ensure_ee", lambda config: None)
    monkeypatch.setattr(ep, "run_engine_project", lambda config, registry, project_name, specs, output_dir, **kw: seen.update(project=project_name, specs=specs, out=output_dir, cfg=config, kw=kw) or {})
    monkeypatch.setattr(sys, "argv", ["run", "--project", "SoulForest_Veltoor", "--output-dir", str(tmp_path)])
    mod.main()
    assert seen["project"] == "SoulForest_Veltoor" and len(seen["specs"]) == 7 and {s.realm for s in seen["specs"]} == {"terrestrial"}
    assert seen["cfg"].gee_project == seen["cfg"].gee_project.strip() and seen["kw"]["strict_provenance"] is True and seen["kw"]["resume"] is False


def test_the_cli_realm_override_is_explicit_and_mixed_is_refused(monkeypatch, tmp_path):
    import darukaa_reference.engine_pipeline as ep
    seen = {}
    mod = _runner()
    monkeypatch.setattr(mod, "_ensure_ee", lambda config: None)
    monkeypatch.setattr(ep, "run_engine_project", lambda config, registry, project_name, specs, output_dir, **kw: seen.update(specs=specs) or {})
    monkeypatch.setattr(sys, "argv", ["run", "--project", "SoulForest_Veltoor", "--realm", "aquatic", "--output-dir", str(tmp_path)])
    mod.main()
    assert {s.realm for s in seen["specs"]} == {"aquatic"} and {s.realm_source for s in seen["specs"]} == {"cli_override"}
    monkeypatch.setattr(sys, "argv", ["run", "--project", "SoulForest_Veltoor", "--realm", "mixed"])
    with pytest.raises(SystemExit):
        mod.main()


def test_the_legacy_engine_remains_callable_and_is_selected_explicitly(monkeypatch, tmp_path):
    mod = _runner()
    seen = {}
    monkeypatch.setattr(mod, "run_multi_tile_project", lambda config, registry, tile_paths, tile_labels, **kw: seen.update(labels=tile_labels, realms=kw["tile_realms"]) or {})
    monkeypatch.setattr(sys, "argv", ["run", "--engine", "legacy", "--project", "TataMotors_Pimpri", "--output-dir", str(tmp_path)])
    mod.main()
    assert len(seen["labels"]) == 15 and seen["realms"] == ["terrestrial"] * 9 + ["aquatic"] * 6          # the original behaviour, untouched
