"""The v0.2.8 engine is FROZEN. Phase 5 may add a pipeline around it; these tests fail if the engine itself changes, and pin what Phase 5 is allowed to touch."""
import dataclasses
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from darukaa_reference import engine_identity as E
from darukaa_reference import provenance as PV
from darukaa_reference.config import Config

PKG = Path(E.PKG_DIR)
NB = dict(gee_project='gaurav-singh-007', output_dir='outputs', archetype='industrial', realm='terrestrial', assessment_mode='baseline',
          hmi_hard_ceiling=0.05, use_variance_stability_floor=True, reference_stratification='ecoregion_landcover')
TAG = "v0.2.8-contract-frozen"


def _git(*args):
    return subprocess.run(["git", "-C", str(PKG)] + list(args), capture_output=True)


def _tag_available():
    r = _git("rev-parse", "--verify", "--quiet", f"{TAG}^{{commit}}")
    return r.returncode == 0


needs_tag = pytest.mark.skipif(not _tag_available(), reason=f"tag {TAG} not available in this checkout")


def test_engine_files_hash_to_the_frozen_value():
    assert E.engine_sha256() == E.FROZEN_ENGINE_SHA256


@needs_tag
def test_every_engine_file_is_byte_identical_to_the_frozen_tag():
    top = _git("rev-parse", "--show-toplevel").stdout.decode().strip()
    rel = PKG.resolve().relative_to(Path(top).resolve())
    for f in E.ENGINE_FILES:
        blob = _git("show", f"{TAG}:{(rel / f).as_posix()}")
        assert blob.returncode == 0, f
        assert blob.stdout == (PKG / f).read_bytes(), f"ENGINE FILE CHANGED: {f}"


@needs_tag
def test_phase5_modifies_only_the_allowed_existing_modules():
    """Phase 5 may extend provenance (engine fingerprint), scoring (accept a precomputed score), html_report (dispatch) and nothing else that existed at the freeze."""
    top = _git("rev-parse", "--show-toplevel").stdout.decode().strip()
    rel = PKG.resolve().relative_to(Path(top).resolve())
    out = _git("diff", "--name-status", TAG, "--", str(rel / "darukaa_reference")).stdout.decode().splitlines()
    changed = {ln.split("\t", 1)[1].split("/")[-1]: ln.split("\t")[0] for ln in out if ln}
    allowed = {"provenance.py", "scoring.py", "html_report.py"}
    modified = {f for f, s in changed.items() if s != "A"}
    assert modified <= allowed, f"unexpected changes to existing frozen-era modules: {sorted(modified - allowed)}"
    assert not any(s == "D" for s in changed.values())


def test_engine_config_fingerprint_matches_the_frozen_standalone_configuration():
    assert E.engine_config_sha256(Config(**NB)) == E.FROZEN_ENGINE_CONFIG_SHA256
    assert E.engine_config_diff(Config(**NB)) == {}


def test_the_yaml_config_is_engine_equivalent_even_though_five_fields_differ():
    """config.yaml differs from the notebook Config in gee_project (stray space), raster_paths, output_dir, output_format and archetype; none changes engine behaviour,
    and 20 vs 20.0 / 100 vs 100.0 must not count as a difference."""
    y = Config.from_yaml(str(PKG.parent / "config.yaml"))
    full_nb, full_y = dataclasses.asdict(Config(**NB)), dataclasses.asdict(y)
    assert {k for k in full_nb if full_nb[k] != full_y[k]} >= {"gee_project", "raster_paths", "output_dir", "archetype"}      # they genuinely differ
    assert E.engine_config_diff(y) == {}


def test_a_real_engine_config_change_is_detected_and_a_cosmetic_one_is_not():
    base = Config(**NB)
    assert set(E.engine_config_diff(dataclasses.replace(base, ndvi_year=2024))) == {"ndvi_year"}
    assert set(E.engine_config_diff(dataclasses.replace(base, reference_sample_pixels=1000))) == {"reference_sample_pixels"}
    assert set(E.engine_config_diff(dataclasses.replace(base, riparian_ring_width_m=50.0))) == {"riparian_ring_width_m"}
    assert E.engine_config_diff(dataclasses.replace(base, output_dir="elsewhere", archetype="conservation", gee_project=" x", output_format="both")) == {}


def test_numbers_are_canonical_so_equal_values_hash_alike():
    base = Config(**NB)
    assert E.engine_config_sha256(dataclasses.replace(base, ndvi_cloud_threshold=20)) == E.engine_config_sha256(dataclasses.replace(base, ndvi_cloud_threshold=20.0))
    assert E.engine_config_sha256(dataclasses.replace(base, ndvi_cloud_threshold=20)) != E.engine_config_sha256(dataclasses.replace(base, ndvi_cloud_threshold=21))


def test_raster_paths_only_count_for_the_keys_the_engine_reads():
    base = Config(**NB)
    assert E.engine_config_diff(dataclasses.replace(base, raster_paths={"globio4_msa": "x.tif", "seed_biocomplexity": "y.tif"})) == {}
    assert "raster_paths" in E.engine_config_diff(dataclasses.replace(base, raster_paths={"bii": "local.tif"}))


def test_provenance_carries_the_engine_fingerprint_and_flags_a_non_frozen_engine(monkeypatch):
    p = PV.run_provenance(Config(**NB))
    e = p["engine"]
    assert e["engine_sha256_at_import"] == E.FROZEN_ENGINE_SHA256 and e["engine_matches_frozen"] is True and e["engine_config_matches_frozen"] is True
    assert e["engine_files"] == list(E.ENGINE_FILES) and e["frozen_engine_sha256"] == E.FROZEN_ENGINE_SHA256
    assert not [w for w in p["warnings"] if w.startswith("engine_")]
    loaded = dict(PV.LOADED); loaded["engine_sha256"] = "0" * 64
    monkeypatch.setattr(PV, "LOADED", loaded)
    q = PV.run_provenance(Config(**NB))
    assert q["engine"]["engine_matches_frozen"] is False and any(w.startswith("engine_not_frozen") for w in q["warnings"])
    assert "NOT FROZEN" in PV.brief(q)


def test_an_engine_config_difference_is_a_provenance_warning():
    p = PV.run_provenance(dataclasses.replace(Config(**NB), ndvi_year=2024))
    assert p["engine"]["engine_config_matches_frozen"] is False and any("ndvi_year" in w for w in p["warnings"])
