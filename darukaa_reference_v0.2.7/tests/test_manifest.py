"""Manifest -> zones: realms are DECLARED by the manifest; legacy name inference is a warned fallback only; nothing project-specific."""
import importlib.util
import json
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from darukaa_reference import manifest as M

REPO = Path(__file__).resolve().parents[2]
PKG = Path(__file__).resolve().parents[1]


def _tile(d, name):
    (d / "tiles").mkdir(parents=True, exist_ok=True)
    p = d / "tiles" / f"{name}.geojson"
    p.write_text(json.dumps({"type": "FeatureCollection", "features": []}))
    return f"tiles/{name}.geojson"


def _manifest(tmp, project, labels, **extra):
    d = tmp / project
    d.mkdir(parents=True, exist_ok=True)
    m = {"project_name": project, "n_tiles": len(labels), "tile_labels": list(labels), "tile_paths": [_tile(d, l) for l in labels], **extra}
    (d / "tile_manifest.json").write_text(json.dumps(m))
    return d / "tile_manifest.json"


def test_explicit_list_dict_and_shorthand_declarations(tmp_path):
    p = _manifest(tmp_path, "P1", ["a", "b"], tile_realms=["terrestrial", "aquatic"])
    name, specs = M.resolve_zone_specs(p, tmp_path)
    assert [(s.label, s.realm, s.realm_source) for s in specs] == [("a", "terrestrial", "manifest"), ("b", "aquatic", "manifest")]
    p = _manifest(tmp_path, "P2", ["a", "b"], tile_realms={"b": "aquatic", "a": "terrestrial"})
    assert [(s.label, s.realm) for s in M.resolve_zone_specs(p, tmp_path)[1]] == [("a", "terrestrial"), ("b", "aquatic")]
    p = _manifest(tmp_path, "P3", ["a", "b"], realm="aquatic")
    assert {s.realm for s in M.resolve_zone_specs(p, tmp_path)[1]} == {"aquatic"}


def test_invalid_or_inconsistent_declarations_are_errors_not_guesses(tmp_path):
    for extra in ({"tile_realms": ["terrestrial"]},                                          # wrong length
                  {"tile_realms": ["terrestrial", "mixed"]},                                  # unsupported realm
                  {"tile_realms": {"a": "terrestrial"}},                                      # missing label
                  {"tile_realms": {"a": "terrestrial", "b": "aquatic", "zzz": "aquatic"}},    # unknown label
                  {"tile_realms": 5}):
        p = _manifest(tmp_path, "Bad", ["a", "b"], **extra)
        with pytest.raises(M.ManifestError):
            M.resolve_zone_specs(p, tmp_path)


def test_legacy_inference_is_a_warned_fallback_and_is_recorded(tmp_path, caplog):
    p = _manifest(tmp_path, "Plain", ["a"])
    with caplog.at_level(logging.WARNING):
        _, specs = M.resolve_zone_specs(p, tmp_path)
    assert specs[0].realm == "terrestrial" and specs[0].realm_source == "legacy_project_name_inference"
    assert any("LEGACY project-name inference" in r.message for r in caplog.records)
    caplog.clear()
    p = _manifest(tmp_path, "Plain_Aquatic", ["w"])
    with caplog.at_level(logging.WARNING):
        _, specs = M.resolve_zone_specs(p, tmp_path)
    assert specs[0].realm == "aquatic" and specs[0].realm_source == "legacy_project_name_inference"


def test_a_manifest_declaration_wins_over_the_project_name(tmp_path, caplog):
    p = _manifest(tmp_path, "Looks_Aquatic_Project", ["a"], tile_realms=["terrestrial"])
    with caplog.at_level(logging.WARNING):
        _, specs = M.resolve_zone_specs(p, tmp_path)
    assert specs[0].realm == "terrestrial" and specs[0].realm_source == "manifest" and not caplog.records


def test_legacy_inference_can_be_disabled(tmp_path):
    p = _manifest(tmp_path, "Plain", ["a"])
    with pytest.raises(M.ManifestError, match="legacy project-name inference is disabled"):
        M.resolve_zone_specs(p, tmp_path, allow_legacy_inference=False)


def test_explicit_companions_are_merged_with_their_own_realms(tmp_path, caplog):
    _manifest(tmp_path, "Water", ["w1", "w2"], tile_realms=["aquatic", "aquatic"])
    p = _manifest(tmp_path, "Land", ["l1"], tile_realms=["terrestrial"], companions=["Water"])
    with caplog.at_level(logging.WARNING):
        name, specs = M.resolve_zone_specs(p, tmp_path)
    assert name == "Land" and [(s.label, s.realm, s.companion_source) for s in specs] == [("l1", "terrestrial", None), ("w1", "aquatic", "manifest"), ("w2", "aquatic", "manifest")]
    assert not caplog.records                                                              # nothing inferred, nothing warned
    _, only = M.resolve_zone_specs(p, tmp_path, combine_companions=False)
    assert [s.label for s in only] == ["l1"]


def test_legacy_companion_discovery_is_warned_and_labelled(tmp_path, caplog):
    _manifest(tmp_path, "Site_Aquatic", ["w1"], tile_realms=["aquatic"])
    p = _manifest(tmp_path, "Site", ["l1"], tile_realms=["terrestrial"])
    with caplog.at_level(logging.WARNING):
        _, specs = M.resolve_zone_specs(p, tmp_path)
    assert [s.label for s in specs] == ["l1", "w1"] and specs[1].companion_source == "legacy_companion_inference"
    assert any("LEGACY inference merged" in r.message for r in caplog.records)
    _, specs = M.resolve_zone_specs(p, tmp_path, allow_legacy_inference=False)
    assert [s.label for s in specs] == ["l1"]


def test_duplicate_labels_across_merged_manifests_and_missing_tiles_are_errors(tmp_path):
    _manifest(tmp_path, "Water", ["x"], tile_realms=["aquatic"])
    p = _manifest(tmp_path, "Land", ["x"], tile_realms=["terrestrial"], companions=["Water"])
    with pytest.raises(M.ManifestError, match="not unique"):
        M.resolve_zone_specs(p, tmp_path)
    p2 = _manifest(tmp_path, "Gone", ["g"], tile_realms=["terrestrial"])
    (tmp_path / "Gone" / "tiles" / "g.geojson").unlink()
    with pytest.raises(FileNotFoundError):
        M.resolve_zone_specs(p2, tmp_path)
    p3 = _manifest(tmp_path, "Dup", ["a", "a"], tile_realms=["terrestrial", "terrestrial"])
    with pytest.raises(M.ManifestError):
        M.load_manifest(p3)


def test_a_missing_companion_that_is_declared_is_an_error(tmp_path):
    p = _manifest(tmp_path, "Land", ["l1"], tile_realms=["terrestrial"], companions=["Nope"])
    with pytest.raises(FileNotFoundError):
        M.resolve_zone_specs(p, tmp_path)


def _real(project):
    return M.find_manifest_by_project_name(REPO, project)


def test_the_real_tata_manifests_declare_their_realms_and_the_companion():
    name, specs = M.resolve_zone_specs(_real("TataMotors_Pimpri"), REPO)
    assert name == "TataMotors_Pimpri" and len(specs) == 15
    assert [s.realm for s in specs] == ["terrestrial"] * 9 + ["aquatic"] * 6
    assert all(s.realm_source == "manifest" for s in specs) and {s.companion_source for s in specs} == {None, "manifest"}
    assert [s.label for s in specs[9:]] == ["Lake_Suman", "Lake_Sharma", "Pond_1", "Pond_2", "Pond_3", "Pond_4"]


def test_the_real_soulforest_manifest_declares_all_seven_zones_terrestrial():
    name, specs = M.resolve_zone_specs(_real("SoulForest_Veltoor"), REPO)
    assert len(specs) == 7 and {s.realm for s in specs} == {"terrestrial"} and {s.realm_source for s in specs} == {"manifest"}
    assert next(s for s in specs if s.label == "EMU_ANCHOR_Wetland").realm == "terrestrial"           # the water has receded: terrestrial / wetland-adjacent
    assert all(s.companion_source is None for s in specs)


def test_resolved_paths_equal_the_legacy_runners_paths_for_every_real_manifest():
    spec = importlib.util.spec_from_file_location("legacy_runner", PKG / "run_project_from_manifest.py")
    legacy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(legacy)
    for proj in ("TataMotors_Pimpri", "TataMotors_Pimpri_Aquatic", "SoulForest_Veltoor", "FCF_GV", "FCF_Soova"):
        mp = legacy.find_manifest_by_project_name(REPO, proj)
        assert mp == M.find_manifest_by_project_name(REPO, proj)
        lm = legacy.load_manifest(mp)
        assert M.resolve_tile_paths(M.load_manifest(mp), mp) == legacy.resolve_tile_paths(lm, mp)


def test_every_real_manifest_still_loads_through_the_legacy_loader_with_the_new_keys():
    spec = importlib.util.spec_from_file_location("legacy_runner2", PKG / "run_project_from_manifest.py")
    legacy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(legacy)
    for proj in ("TataMotors_Pimpri", "TataMotors_Pimpri_Aquatic", "SoulForest_Veltoor"):
        assert legacy.load_manifest(legacy.find_manifest_by_project_name(REPO, proj))["project_name"] == proj
