"""Offline integration tests for the Colab Git ref bootstrap logic."""
import json
import subprocess
from pathlib import Path


def test_clone_exact_ref_accepts_branch_and_full_commit_sha(tmp_path):
    notebook = json.loads((Path(__file__).resolve().parents[1] / "notebooks" / "Darukaa_Adaptive_Biodiversity_Assessment_Colab.ipynb").read_text())
    bootstrap = next("".join(c.get("source", [])) for c in notebook["cells"] if "def clone_exact_ref" in "".join(c.get("source", [])))
    prelude = bootstrap[:bootstrap.index("ACTUAL_GIT_SHA =")]
    ns = {}
    exec("import os, shutil, subprocess, pathlib, sys, re\n" + prelude, ns)

    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(source)], check=True, stdout=subprocess.PIPE)
    subprocess.run(["git", "-C", str(source), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(source), "config", "user.name", "Test"], check=True)
    (source / "payload.txt").write_text("first\n")
    subprocess.run(["git", "-C", str(source), "add", "payload.txt"], check=True)
    subprocess.run(["git", "-C", str(source), "commit", "-m", "first"], check=True, stdout=subprocess.PIPE)
    first = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    (source / "payload.txt").write_text("second\n")
    subprocess.run(["git", "-C", str(source), "commit", "-am", "second"], check=True, stdout=subprocess.PIPE)
    second = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()

    # The bootstrap uses origin fetch/check-out; this is an offline local remote,
    # so the exact branch/commit logic is tested without depending on GitHub.
    clone = tmp_path / "clone"
    actual = ns["clone_exact_ref"](str(source), first, str(clone))
    assert actual == first
    assert subprocess.check_output(["git", "-C", str(clone), "rev-parse", "HEAD"], text=True).strip() == first

    actual_branch = ns["clone_exact_ref"](str(source), "main", str(clone))
    assert actual_branch == second
