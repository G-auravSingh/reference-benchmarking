"""
manifest.py -- project / site manifest -> assessment zones (v0.2.9 Phase 5)
==========================================================================

A project is described by a `tile_manifest.json`. This module turns one into an ordered list of `ZoneSpec` (label, resolved tile path, REALM) for the general
engine pipeline. It knows nothing about any particular project: everything it needs is in the manifest.

Manifest keys
-------------
  project_name   (required)  str
  tile_labels    (required)  list[str]            unique within the project (and across merged companions)
  tile_paths     (required)  list[str]            same length as tile_labels
  tile_realms    (optional)  list[str] | {label: str}   each "terrestrial" or "aquatic". THE DECLARATION. A single `realm` string is accepted as
                                                  shorthand for "every tile".
  companions     (optional)  list[str]            project_names of other manifests merged into this project's report (e.g. a project whose water
                                                  bodies are delivered as a separate manifest). Each companion declares its OWN realms.

Legacy fallbacks (kept for manifests written before this declaration existed; each one is WARNED and recorded in the zone's `realm_source`):
  * no tile_realms / realm      -> "aquatic" if "aquatic" appears in the project_name, else "terrestrial"   (realm_source = legacy_project_name_inference)
  * no `companions` key         -> an existing manifest named "<project_name>_Aquatic" is merged           (companion_source = legacy_companion_inference)
`allow_legacy_inference=False` turns both into errors.

The realm decides which indicators can apply (domain rule of the frozen contract); it is never inferred from the geometry.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

logger = logging.getLogger(__name__)

VALID_REALMS = ("terrestrial", "aquatic")


class ManifestError(ValueError):
    """A manifest is inconsistent. Never papered over."""


@dataclass(frozen=True)
class ZoneSpec:
    label: str
    path: str
    realm: str
    project: str                          # the manifest this zone came from
    realm_source: str                     # "manifest" | "legacy_project_name_inference"
    companion_source: Optional[str] = None  # None for the primary manifest | "manifest" | "legacy_companion_inference"


def load_manifest(manifest_path: Union[str, Path]) -> dict:
    manifest_path = Path(manifest_path)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    with open(manifest_path) as f:
        m = json.load(f)
    for key in ("project_name", "tile_paths", "tile_labels"):
        if key not in m:
            raise ManifestError(f"Manifest is missing required key '{key}': {manifest_path}")
    if len(m["tile_paths"]) != len(m["tile_labels"]):
        raise ManifestError(f"Manifest has {len(m['tile_paths'])} tile_paths but {len(m['tile_labels'])} tile_labels: {manifest_path}")
    if len(set(m["tile_labels"])) != len(m["tile_labels"]):
        raise ManifestError(f"Manifest tile_labels are not unique: {manifest_path}")
    return m


def resolve_tile_paths(manifest: dict, manifest_path: Union[str, Path]) -> List[str]:
    """Tile paths are relative to the manifest's own location (not the working directory)."""
    base = Path(manifest_path).parent
    out = []
    for p in manifest["tile_paths"]:
        cand = base / Path(p).name if not (base / p).exists() else base / p
        if not cand.exists():
            cand = base / "tiles" / Path(p).name
        out.append(str(cand))
    return out


def find_manifest_by_project_name(repo_root: Union[str, Path], project_name: str) -> Path:
    """The manifest whose OWN `project_name` equals the argument (the authoritative identity, not a path convention). Exactly one match is required."""
    matches = []
    for p in Path(repo_root).rglob("tile_manifest.json"):
        try:
            with open(p) as f:
                if json.load(f).get("project_name") == project_name:
                    matches.append(p)
        except (json.JSONDecodeError, OSError):
            continue
    if not matches:
        raise FileNotFoundError(f"No tile_manifest.json with project_name '{project_name}' found under {repo_root}")
    if len(matches) > 1:
        raise ManifestError(f"{len(matches)} manifests claim project_name '{project_name}': " + "; ".join(map(str, matches)))
    return matches[0]


def _realms_for(manifest: dict, allow_legacy: bool) -> Tuple[List[str], str]:
    labels, name = manifest["tile_labels"], manifest["project_name"]
    decl = manifest.get("tile_realms", manifest.get("realm"))
    if decl is not None:
        if isinstance(decl, str):
            realms = [decl] * len(labels)
        elif isinstance(decl, dict):
            unknown = sorted(set(decl) - set(labels))
            missing = [l for l in labels if l not in decl]
            if unknown or missing:
                raise ManifestError(f"{name}: tile_realms has unknown labels {unknown} / lacks labels {missing}")
            realms = [decl[l] for l in labels]
        elif isinstance(decl, (list, tuple)):
            if len(decl) != len(labels):
                raise ManifestError(f"{name}: tile_realms has {len(decl)} entries for {len(labels)} tiles")
            realms = list(decl)
        else:
            raise ManifestError(f"{name}: tile_realms must be a list, a {{label: realm}} dict or a string")
        bad = sorted({r for r in realms if r not in VALID_REALMS})
        if bad:
            raise ManifestError(f"{name}: invalid realm(s) {bad}; each must be one of {VALID_REALMS}")
        return realms, "manifest"
    if not allow_legacy:
        raise ManifestError(f"{name}: no tile_realms declared and legacy project-name inference is disabled")
    inferred = "aquatic" if "aquatic" in name.lower() else "terrestrial"
    logger.warning("Manifest '%s' declares no tile_realms: falling back to LEGACY project-name inference -> '%s' for all %d tile(s). "
                   "Declare tile_realms in the manifest.", name, inferred, len(labels))
    return [inferred] * len(labels), "legacy_project_name_inference"


def _specs(manifest: dict, manifest_path: Path, allow_legacy: bool, companion_source: Optional[str]) -> List[ZoneSpec]:
    realms, source = _realms_for(manifest, allow_legacy)
    paths = resolve_tile_paths(manifest, manifest_path)
    missing = [p for p in paths if not Path(p).exists()]
    if missing:
        raise FileNotFoundError(f"{len(missing)} tile file(s) of '{manifest['project_name']}' not found: {missing[:3]}")
    return [ZoneSpec(l, p, r, manifest["project_name"], source, companion_source) for l, p, r in zip(manifest["tile_labels"], paths, realms)]


def resolve_zone_specs(manifest_path: Union[str, Path], repo_root: Union[str, Path, None] = None, combine_companions: bool = True,
                       allow_legacy_inference: bool = True) -> Tuple[str, List[ZoneSpec]]:
    """-> (project_name, ordered ZoneSpecs: the primary manifest's zones, then each companion's). Labels must be unique across the merged set."""
    manifest_path = Path(manifest_path)
    repo_root = Path(repo_root) if repo_root is not None else manifest_path.parent
    m = load_manifest(manifest_path)
    specs = _specs(m, manifest_path, allow_legacy_inference, None)
    if combine_companions:
        if "companions" in m:
            names, src = list(m["companions"]), "manifest"
        else:
            names, src = [], None
            if allow_legacy_inference and "aquatic" not in m["project_name"].lower():
                legacy = f"{m['project_name']}_Aquatic"
                try:
                    find_manifest_by_project_name(repo_root, legacy)
                    names, src = [legacy], "legacy_companion_inference"
                    logger.warning("Manifest '%s' declares no `companions`: LEGACY inference merged the existing '%s'. Declare `companions` in the manifest.",
                                   m["project_name"], legacy)
                except FileNotFoundError:
                    pass
        for name in names:
            cpath = find_manifest_by_project_name(repo_root, name)
            specs += _specs(load_manifest(cpath), cpath, allow_legacy_inference, src)
    labels = [s.label for s in specs]
    dup = sorted({l for l in labels if labels.count(l) > 1})
    if dup:
        raise ManifestError(f"zone labels are not unique across the merged manifests: {dup}")
    return m["project_name"], specs
