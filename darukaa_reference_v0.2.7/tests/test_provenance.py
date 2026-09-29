"""Provenance: the audit trail records the ACTUAL repository state the run used. Nothing is hard-coded."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from darukaa_reference import assess as A
from darukaa_reference import provenance as PV
from darukaa_reference.config import Config


def _git(cwd, *args):
    return subprocess.check_output(["git", "-C", str(cwd)] + list(args), stderr=subprocess.STDOUT).decode().strip()


def _repo(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "branchx")
    (tmp_path / "m.py").write_text("x = 1\n")
    _git(tmp_path, "add", "."); _git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "one")
    return tmp_path


def test_repo_state_reports_the_real_head_branch_and_dirtiness(tmp_path):
    r = _repo(tmp_path)
    s = PV.repo_state(str(r))
    assert s["commit"] == _git(r, "rev-parse", "HEAD") and s["commit_short"] == s["commit"][:7] and s["branch"] == "branchx" and s["dirty"] is False
    (r / "m.py").write_text("x = 2\n")                                            # an uncommitted edit
    d = PV.repo_state(str(r))
    assert d["dirty"] is True and d["dirty_files"] == ["m.py"] and d["commit"] == s["commit"]
    _git(r, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "two")
    assert PV.repo_state(str(r))["commit"] != s["commit"]                         # a new commit is a new commit id: nothing is cached or constant


def test_outside_a_git_checkout_the_commit_is_unknown_not_invented(tmp_path):
    s = PV.repo_state(str(tmp_path))
    assert s["commit"] == "unknown" and s["in_git_checkout"] is False and s["dirty"] is None


def test_a_remote_url_with_an_embedded_token_is_masked(tmp_path):
    r = _repo(tmp_path)
    _git(r, "remote", "add", "origin", "https://x-access-token:SECRET123@github.com/o/r.git")
    assert "SECRET123" not in json.dumps(PV.repo_state(str(r)))


def test_source_fingerprint_changes_with_any_code_change_and_ignores_pycache(tmp_path):
    (tmp_path / "a.py").write_text("a=1\n"); (tmp_path / "__pycache__").mkdir(); (tmp_path / "__pycache__" / "z.py").write_text("junk")
    f1 = PV.source_fingerprint(str(tmp_path))
    assert f1 == PV.source_fingerprint(str(tmp_path))
    (tmp_path / "__pycache__" / "z.py").write_text("more junk"); assert PV.source_fingerprint(str(tmp_path)) == f1
    (tmp_path / "a.py").write_text("a=2\n"); assert PV.source_fingerprint(str(tmp_path)) != f1


def test_the_recorded_commit_is_the_loaded_one_and_is_not_a_literal():
    p = PV.run_provenance(Config(), A.CODE_VERSION)
    assert p["git_commit"] == PV.LOADED["commit"] == A.git_commit() or A.git_commit() == PV.LOADED["commit_short"]
    src = Path(A.__file__).read_text()
    assert "41496ed" not in src and "0d5839d" not in src and "7dac5aa" not in src        # never hard-coded
    if PV.LOADED["in_git_checkout"]:
        assert PV.LOADED["commit"] == _git(Path(PV.PKG_DIR).parent, "rev-parse", "HEAD") or PV.run_provenance(None)["checkout_changed_since_import"] is not None


def test_provenance_block_has_the_required_fields():
    p = PV.run_provenance(Config(riparian_ring_width_m=100.0), A.CODE_VERSION)
    for k in ("git_commit", "git_commit_short", "branch", "dirty", "package_version", "contract_version", "code_version", "config",
              "config_sha256", "source_sha256_at_import", "environment", "written_utc", "imported_utc", "checkout_now", "warnings"):
        assert k in p, k
    assert p["contract_version"] == "0.2.8" and p["code_version"] == A.CODE_VERSION and p["config"]["riparian_ring_width_m"] == 100.0
    assert p["environment"]["python"] and "ee" in p["environment"]


def test_config_hash_changes_when_configuration_changes():
    a = PV.run_provenance(Config(riparian_ring_width_m=100.0)); b = PV.run_provenance(Config(riparian_ring_width_m=50.0))
    assert a["config_sha256"] != b["config_sha256"] and a["config_sha256"] == PV.run_provenance(Config(riparian_ring_width_m=100.0))["config_sha256"]


def test_a_checkout_that_moves_after_import_is_flagged_not_silently_relabelled(monkeypatch):
    """The run-2 question: HEAD on disk vs the code the process loaded. Simulate a `git pull` after import."""
    loaded = dict(PV.LOADED); loaded["commit"] = "a" * 40; loaded["commit_short"] = "aaaaaaa"
    monkeypatch.setattr(PV, "LOADED", loaded)
    p = PV.run_provenance(None)
    assert p["git_commit"] == "a" * 40                                                    # what was LOADED, not what is on disk now
    if PV.repo_state()["in_git_checkout"]:
        assert p["checkout_changed_since_import"] is True and any("RESTART" in w for w in p["warnings"])
        assert "checkout_changed_since_import" in PV.brief(p)


def test_source_edited_after_import_is_flagged_even_without_git(monkeypatch):
    loaded = dict(PV.LOADED); loaded["source_sha256"] = "0" * 64
    monkeypatch.setattr(PV, "LOADED", loaded)
    p = PV.run_provenance(None)
    assert p["source_changed_since_import"] is True and p["warnings"]


def test_a_dirty_tree_at_import_is_stated(monkeypatch):
    loaded = dict(PV.LOADED); loaded["dirty"] = True; loaded["dirty_files"] = ["x.py"]
    monkeypatch.setattr(PV, "LOADED", loaded)
    p = PV.run_provenance(None)
    assert p["dirty"] is True and any("dirty" in w for w in p["warnings"]) and "(DIRTY)" in PV.brief(p)


def test_audit_files_carry_the_provenance_block_and_a_header(tmp_path):
    rows = [{"zone": "Z", "realm": "terrestrial", "indicator": "ghm", "status": "scored", "reason": "", "site_value": 1.0, "reference_n": 40,
             "reference_median": 1.0, "benchmark": 0.0, "score": 0.5, "seconds": 1.0}]
    cfg = Config(riparian_ring_width_m=100.0)
    paths = A.write_audit(rows, str(tmp_path), "Z", meta={}, config=cfg)
    d = json.loads(Path(paths["json"]).read_text())
    assert d["provenance"]["git_commit"] == d["git_commit"] == PV.LOADED["commit"]
    assert d["provenance"]["config"]["riparian_ring_width_m"] == 100.0 and d["provenance"]["branch"] == PV.LOADED["branch"]
    assert Path(paths["md"]).read_text().splitlines()[2].startswith("Provenance: commit ")


def test_parity_files_carry_the_same_provenance(tmp_path):
    from darukaa_reference import parity as P
    paths = P.write_parity([P.ParityResult("c", "i", P.MATCH)], str(tmp_path))
    assert json.loads(Path(paths["json"]).read_text())["provenance"]["git_commit"] == PV.LOADED["commit"]
    assert "Provenance: commit " in Path(paths["md"]).read_text()
