"""
provenance.py -- what code and configuration actually produced an output (v0.2.8)
=================================================================================

The audit trail must record the repository state the run USED, never a constant and never merely "whatever HEAD is when the file is
written" (a `git pull` in a live notebook session changes HEAD but not the modules already imported).

  * `LOADED` is captured ONCE, when the package is first imported: full commit, branch, dirty flag and a SHA-256 fingerprint of every
    package source file. This is the code the run executed.
  * `run_provenance()` adds the state NOW and says whether it still agrees with what was loaded (`checkout_changed_since_import`,
    `source_changed_since_import`). If it does not, the run is flagged: the label cannot be trusted without a restart.
  * Nothing is hard-coded: outside a git checkout the commit is reported as "unknown" and the source fingerprint still identifies the code.
"""
from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import os
import platform
import subprocess
import sys
from typing import Any, Dict, Optional

PKG_DIR = os.path.dirname(os.path.abspath(__file__))


def _git(args, cwd: str, timeout: int = 10, strip: bool = True) -> Optional[str]:
    try:
        out = subprocess.check_output(["git", "-C", cwd] + list(args), stderr=subprocess.DEVNULL, timeout=timeout).decode()
        return out.strip() if strip else out.rstrip("\n")          # porcelain lines start with a space: never strip them
    except Exception:
        return None


def repo_state(path: str = PKG_DIR) -> Dict[str, Any]:
    """Actual git state of the checkout containing `path` (never hard-coded)."""
    commit = _git(["rev-parse", "HEAD"], path)
    if commit is None:
        return {"commit": "unknown", "commit_short": "unknown", "branch": None, "dirty": None, "dirty_files": [], "in_git_checkout": False}
    status = _git(["status", "--porcelain", "--untracked-files=no"], path, strip=False) or ""
    dirty_files = [ln[3:] for ln in status.splitlines() if ln.strip()]
    remote = _git(["config", "--get", "remote.origin.url"], path) or ""
    if "@" in remote:                                             # never leak an embedded token
        remote = remote.split("://")[0] + "://***@" + remote.split("@", 1)[1]
    return {"commit": commit, "commit_short": commit[:7], "branch": _git(["rev-parse", "--abbrev-ref", "HEAD"], path),
            "dirty": bool(dirty_files), "dirty_files": dirty_files[:20], "commit_time_utc": _git(["show", "-s", "--format=%cI", "HEAD"], path),
            "describe": _git(["describe", "--always", "--dirty"], path), "remote": remote, "in_git_checkout": True}


def source_fingerprint(pkg_dir: str = PKG_DIR) -> str:
    """SHA-256 over the relative path and bytes of every .py file in the package (sorted): identifies the code irrespective of git."""
    h = hashlib.sha256()
    for root, dirs, files in os.walk(pkg_dir):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for f in sorted(files):
            if f.endswith(".py"):
                p = os.path.join(root, f)
                h.update(os.path.relpath(p, pkg_dir).replace(os.sep, "/").encode())
                with open(p, "rb") as fh:
                    h.update(fh.read())
    return h.hexdigest()


def _capture() -> Dict[str, Any]:
    from darukaa_reference import engine_identity as EI
    s = repo_state()
    s["source_sha256"] = source_fingerprint()
    s["engine_closure_sha256"] = EI.engine_closure_sha256()                  # the frozen engine files this process loaded
    s["captured_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    return s


LOADED: Dict[str, Any] = _capture()          # the code THIS process imported


def config_snapshot(config: Any) -> Dict[str, Any]:
    """JSON-safe copy of the configuration (dataclass or object) and its hash."""
    if config is None:
        return {}
    try:
        d = dataclasses.asdict(config) if dataclasses.is_dataclass(config) else dict(vars(config))
    except Exception:
        d = {k: getattr(config, k) for k in dir(config) if not k.startswith("_") and not callable(getattr(config, k))}
    return json.loads(json.dumps(d, default=str, sort_keys=True))


def _versions() -> Dict[str, Any]:
    out: Dict[str, Any] = {"python": platform.python_version()}
    for name in ("ee", "numpy", "shapely", "pyproj", "scipy", "pandas"):
        try:
            out[name] = __import__(name).__version__
        except Exception:
            out[name] = None
    return out


def run_provenance(config: Any = None, code_version: str = "") -> Dict[str, Any]:
    """The provenance block written into every audit / parity output."""
    from darukaa_reference import __version__ as pkg_version
    from darukaa_reference import indicator_contract as IC
    now, cfg = repo_state(), config_snapshot(config)
    changed_commit = now["commit"] != LOADED["commit"]
    changed_src = source_fingerprint() != LOADED["source_sha256"]
    warnings = []
    if changed_commit or changed_src:
        warnings.append("checkout_changed_since_import: the files on disk are not the code this process loaded; RESTART the runtime before trusting this label")
    if LOADED.get("dirty"):
        warnings.append("dirty_working_tree_at_import: uncommitted changes were loaded, the commit alone does not identify the code")
    from darukaa_reference import engine_identity as EI
    engine_now = EI.engine_closure_sha256()
    engine = {"engine_closure_sha256_at_import": LOADED.get("engine_closure_sha256"), "engine_closure_sha256_now": engine_now, "frozen_engine_closure_sha256": EI.FROZEN_ENGINE_CLOSURE_SHA256,
              "engine_closure_matches_frozen": LOADED.get("engine_closure_sha256") == EI.FROZEN_ENGINE_CLOSURE_SHA256 and engine_now == EI.FROZEN_ENGINE_CLOSURE_SHA256,
              "engine_closure_files": list(EI.ENGINE_CLOSURE_FILES), "engine_config_sha256": EI.engine_config_sha256(config) if config is not None else None,
              "frozen_engine_config_sha256": EI.FROZEN_ENGINE_CONFIG_SHA256, "engine_config_diff": EI.engine_config_diff(config) if config is not None else None}
    engine["engine_config_matches_frozen"] = (None if config is None else not engine["engine_config_diff"])
    if not engine["engine_closure_matches_frozen"]:
        warnings.append("engine_not_frozen: the engine modules differ from the frozen v0.2.8 engine (engine_closure_sha256); results are NOT v0.2.8-engine results")
    if engine["engine_config_matches_frozen"] is False:
        warnings.append("engine_config_differs_from_frozen: engine-read configuration fields differ from the frozen standalone configuration: " + ", ".join(sorted(engine["engine_config_diff"])))
    return {"git_commit": LOADED["commit"], "git_commit_short": LOADED["commit_short"], "branch": LOADED["branch"], "dirty": LOADED["dirty"],
            "dirty_files": LOADED.get("dirty_files", []), "commit_time_utc": LOADED.get("commit_time_utc"), "remote": LOADED.get("remote"),
            "in_git_checkout": LOADED["in_git_checkout"], "source_sha256_at_import": LOADED["source_sha256"], "imported_utc": LOADED["captured_utc"],
            "checkout_now": {"commit": now["commit"], "branch": now["branch"], "dirty": now["dirty"]},
            "checkout_changed_since_import": changed_commit, "source_changed_since_import": changed_src, "warnings": warnings,
            "package_version": pkg_version, "contract_version": getattr(IC, "CONTRACT_VERSION", None), "code_version": code_version,
            "engine": engine, "config": cfg, "config_sha256": hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest(),
            "environment": _versions(), "written_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}


def brief(p: Dict[str, Any]) -> str:
    """One line for markdown headers."""
    w = f" | WARNING: {'; '.join(p['warnings'])}" if p.get("warnings") else ""
    return (f"commit {p['git_commit_short']} on {p['branch']}{' (DIRTY)' if p.get('dirty') else ''} | code {p.get('code_version')} | "
            f"contract {p.get('contract_version')} | package {p.get('package_version')} | config sha {p['config_sha256'][:10]} | "
            f"source sha {p['source_sha256_at_import'][:10]} | engine {(p.get('engine') or {}).get('engine_closure_sha256_at_import', '')[:10]}"
            f"{' (FROZEN)' if (p.get('engine') or {}).get('engine_closure_matches_frozen') else ' (NOT FROZEN)'}{w}")


def verify_outputs(out_dir: str, expected_commit: Optional[str] = None, expected_contract: Optional[str] = None,
                   check_session: bool = True, only=None) -> Dict[str, Any]:
    """Gate before shipping results: every `*_audit.json` and `parity.json` in `out_dir` must carry a provenance block whose commit is the code
    THIS process loaded, that was written after this process imported the code (so it cannot be a leftover from an earlier session), that is
    not dirty, has no warnings, and records the contract version. A legacy file without a provenance block, or with another commit, is an
    ISSUE, never silently accepted. Returns {'ok', 'files', 'issues'}; nothing is hard-coded.

    check_session=False (with an explicit `expected_commit`) verifies outputs produced by an EARLIER commit in an EARLIER session against that
    commit: it drops the "written after this process imported the code" and "source fingerprint equals the code loaded now" tests, nothing else.
    `only` restricts the check to those file names."""
    import glob
    expected_commit = expected_commit or LOADED["commit"]
    if expected_contract is None:
        from darukaa_reference import indicator_contract as IC
        expected_contract = getattr(IC, "CONTRACT_VERSION", None)
    files, issues = [], []
    paths = sorted(glob.glob(os.path.join(out_dir, "*_audit.json")) + glob.glob(os.path.join(out_dir, "parity.json")))
    if only is not None:
        paths = [q for q in paths if os.path.basename(q) in set(only)]
    if not paths:
        issues.append(f"no audit or parity json found in {out_dir}")
    for path in paths:
        name, problems = os.path.basename(path), []
        try:
            with open(path, encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception as e:
            issues.append(f"{name}: unreadable ({type(e).__name__})"); continue
        pv = d.get("provenance")
        if not pv:
            problems.append(f"NO provenance block (legacy or stale file; top-level git_commit={d.get('git_commit')!r})")
        else:
            c = pv.get("git_commit") or ""
            if not c or not (expected_commit.startswith(c) or c.startswith(expected_commit)):
                problems.append(f"commit {c[:7] or None} is not the loaded commit {expected_commit[:7]}")
            if pv.get("dirty"):
                problems.append("dirty working tree")
            if pv.get("warnings"):
                problems.append("warnings: " + "; ".join(pv["warnings"]))
            if expected_contract and pv.get("contract_version") != expected_contract:
                problems.append(f"contract_version {pv.get('contract_version')!r} != {expected_contract!r}")
            if not pv.get("config_sha256") or not pv.get("source_sha256_at_import"):
                problems.append("config/source provenance missing")
            if check_session and (pv.get("written_utc") or "") < LOADED["captured_utc"]:
                problems.append(f"written {pv.get('written_utc')} before this process imported the code {LOADED['captured_utc']}: a leftover from an earlier session")
            if check_session and pv.get("source_sha256_at_import") != LOADED["source_sha256"]:
                problems.append("source fingerprint differs from the code loaded now")
        for r in d.get("rows", []):                                      # per-row provenance must agree with the file's
            rp = r.get("provenance")
            rp = json.loads(rp) if isinstance(rp, str) else (rp or {})
            rc = rp.get("git_commit") or ""
            if rc and not (expected_commit.startswith(rc) or rc.startswith(expected_commit)):
                problems.append(f"row {r.get('indicator')} carries commit {rc[:7]}")
                break
        files.append({"file": name, "ok": not problems, "commit": (pv or {}).get("git_commit_short"), "problems": problems})
        issues += [f"{name}: {p}" for p in problems]
    return {"ok": not issues, "expected_commit": expected_commit, "files": files, "issues": issues}
