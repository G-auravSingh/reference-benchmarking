"""Formal Site Selection -> Adaptive Assessment handoff contract."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable

HANDOFF_SCHEMA_VERSION = "1.0.0"

REQUIRED_TILE_FIELDS = ("emu_id", "path")

@dataclass(frozen=True)
class HandoffContract:
    schema_version: str = HANDOFF_SCHEMA_VERSION
    required_manifest_fields: tuple[str, ...] = ("project_id", "tiles")
    required_tile_fields: tuple[str, ...] = REQUIRED_TILE_FIELDS


def validate_handoff_manifest(data: Dict[str, Any]) -> list[str]:
    errors=[]
    if str(data.get("schema_version", "")) != HANDOFF_SCHEMA_VERSION:
        errors.append(f"schema_version must be {HANDOFF_SCHEMA_VERSION}")
    for key in ("project_id", "tiles"):
        if key not in data: errors.append(f"missing required field: {key}")
    tiles=data.get("tiles")
    if not isinstance(tiles,list) or not tiles: errors.append("tiles must be a non-empty list")
    else:
        ids=set()
        for i,t in enumerate(tiles,1):
            if not isinstance(t,dict): errors.append(f"tile {i} must be an object"); continue
            for key in REQUIRED_TILE_FIELDS:
                if not t.get(key): errors.append(f"tile {i} missing required field: {key}")
            if t.get("emu_id") in ids: errors.append(f"duplicate emu_id: {t.get('emu_id')}")
            ids.add(t.get("emu_id"))
            if t.get("domain") not in (None,"terrestrial","aquatic","mixed","auto"):
                errors.append(f"tile {i} has invalid domain")
    return errors


def handoff_manifest_template(project_id: str, tiles: Iterable[Dict[str, Any]], *, project_name: str | None = None, domain: str = "auto") -> Dict[str, Any]:
    data={"schema_version":HANDOFF_SCHEMA_VERSION,"project_id":project_id,"project_name":project_name or project_id,"domain":domain,"tiles":list(tiles)}
    errors=validate_handoff_manifest(data)
    if errors: raise ValueError("Invalid handoff manifest: "+"; ".join(errors))
    return data
