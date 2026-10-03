"""Canonical input and EMU handoff ingestion.

The assessment engine consumes a normalized project model rather than depending on
KML filenames or project-specific folder conventions. Supported sources are:
site-selection handoff manifests, GeoJSON/FeatureCollections, KML/KMZ, and a
single polygon geometry supplied by Python callers.
"""
from __future__ import annotations

import json
import zipfile
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from shapely.geometry import shape, mapping
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .site import _normalise_geometry, area_ha, read_kml

SUPPORTED_DOMAINS = {"terrestrial", "aquatic", "mixed", "auto"}


@dataclass(frozen=True)
class EMU:
    """Canonical ecological management unit.

    An EMU may be multipart/disconnected. Geometry is therefore a MultiPolygon or
    Polygon and is never assumed to be contiguous merely because it is one EMU.
    """

    emu_id: str
    geometry: BaseGeometry
    domain: str = "auto"
    parent_zone: Optional[str] = None
    area_ha: Optional[float] = None
    source_project: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)

    def resolved_domain(self, project_default: str = "auto") -> str:
        value = self.domain if self.domain != "auto" else project_default
        if value == "auto":
            # Conservative geometry-only fallback. Aquatic routing must be declared
            # by a manifest/feature attribute or assessment profile; we do not guess
            # aquatic ecology from polygon shape alone.
            return "terrestrial"
        if value not in SUPPORTED_DOMAINS - {"auto"}:
            raise ValueError(f"Unsupported EMU domain: {value}")
        return value

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["geometry"] = mapping(self.geometry)
        out["area_ha"] = float(self.area_ha if self.area_ha is not None else area_ha(self.geometry))
        return out


@dataclass
class ProjectInput:
    project_id: str
    project_name: str
    source_path: str
    emus: List[EMU]
    project_domain: str = "auto"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> List[str]:
        errors: List[str] = []
        if not self.project_id.strip(): errors.append("project_id is required")
        if not self.emus: errors.append("at least one EMU is required")
        if self.project_domain not in SUPPORTED_DOMAINS: errors.append("project_domain must be terrestrial, aquatic, mixed or auto")
        seen = set()
        for e in self.emus:
            if e.emu_id in seen: errors.append(f"duplicate EMU id: {e.emu_id}")
            seen.add(e.emu_id)
            if e.geometry.is_empty or not e.geometry.is_valid: errors.append(f"invalid geometry for EMU {e.emu_id}")
        return errors

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "source_path": self.source_path,
            "project_domain": self.project_domain,
            "metadata": self.metadata,
            "emus": [e.to_dict() for e in self.emus],
        }


def _feature_properties(feature: Dict[str, Any]) -> Dict[str, Any]:
    p = feature.get("properties") or {}
    return dict(p) if isinstance(p, dict) else {}


def _domain_from_properties(props: Dict[str, Any]) -> str:
    for key in ("domain", "ecosystem_domain", "realm", "assessment_domain"):
        value = props.get(key)
        if isinstance(value, str) and value.lower() in SUPPORTED_DOMAINS:
            return value.lower()
    return "auto"


def _emu_id(props: Dict[str, Any], fallback: str) -> str:
    for key in ("emu_id", "EMU_ID", "emu", "id", "tile_id", "zone_id"):
        value = props.get(key)
        if value not in (None, ""):
            return str(value)
    return fallback


def _load_geojson(path: Path) -> Tuple[List[EMU], Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("type") == "FeatureCollection":
        features = data.get("features", [])
    elif data.get("type") == "Feature":
        features = [data]
    elif data.get("type") in {"Polygon", "MultiPolygon"}:
        features = [{"type": "Feature", "properties": {}, "geometry": data}]
    else:
        raise ValueError(f"Unsupported GeoJSON object type: {data.get('type')}")
    emus: List[EMU] = []
    for i, feature in enumerate(features, 1):
        geom_data = feature.get("geometry")
        if not geom_data: continue
        geom = _normalise_geometry(shape(geom_data))
        if geom.is_empty: continue
        props = _feature_properties(feature)
        emus.append(EMU(_emu_id(props, f"EMU_{i:03d}"), geom, _domain_from_properties(props), props.get("parent_zone"), area_ha(geom), props.get("source_project"), props))
    metadata = data.get("metadata") or {}
    return emus, metadata


def _load_handoff_manifest(path: Path) -> ProjectInput:
    data = json.loads(path.read_text(encoding="utf-8"))
    root = path.parent
    tile_manifest = data
    if "tiles" not in tile_manifest and "tile_manifest" in data:
        ref = Path(data["tile_manifest"])
        tile_manifest = json.loads((root / ref).read_text(encoding="utf-8"))
    tiles = tile_manifest.get("tiles") or tile_manifest.get("emus") or tile_manifest.get("features")
    if not isinstance(tiles, list) or not tiles:
        raise ValueError("Handoff manifest must contain a non-empty 'tiles' or 'emus' list")
    emus: List[EMU] = []
    for i, item in enumerate(tiles, 1):
        if isinstance(item, str):
            item = {"path": item}
        rel = item.get("path") or item.get("file") or item.get("geojson") or item.get("tile_path")
        if not rel: raise ValueError(f"Handoff tile {i} has no GeoJSON path")
        tile_path = root / rel
        if not tile_path.exists(): raise FileNotFoundError(tile_path)
        tile_emus, _ = _load_geojson(tile_path)
        if len(tile_emus) != 1:
            raise ValueError(f"Handoff tile {tile_path} must contain exactly one EMU feature")
        e = tile_emus[0]
        emu_id = str(item.get("emu_id") or item.get("id") or e.emu_id)
        domain = str(item.get("domain") or e.domain or "auto").lower()
        parent = item.get("parent_zone") or item.get("parent_zone_id")
        attrs = dict(e.attributes); attrs.update({k:v for k,v in item.items() if k not in {"path","file","geojson","tile_path"}})
        emus.append(EMU(emu_id, e.geometry, domain, parent, e.area_ha, item.get("source_project"), attrs))
    project_id = str(data.get("project_id") or data.get("project") or path.stem)
    return ProjectInput(project_id, str(data.get("project_name") or project_id), str(path), emus, str(data.get("domain") or data.get("project_domain") or "auto"), data.get("metadata") or {})


def _load_kml_project(path: Path) -> ProjectInput:
    union, parts = read_kml(path)
    emus = [EMU(f"EMU_{i:03d}", g, "auto", None, area_ha(g), None, {"source_name": n}) for i,(n,g) in enumerate(parts.items(), 1)]
    # If a KML contains one site polygon, retain it as one EMU. If it contains
    # multiple placemarks, each named polygon is an EMU; the union is only used as
    # the project envelope by callers that need it.
    if not emus:
        emus = [EMU("EMU_001", union)]
    return ProjectInput(path.stem, path.stem, str(path), emus)


def _load_handoff_zip(path: Path) -> ProjectInput:
    tmp = Path(tempfile.mkdtemp(prefix="darukaa_handoff_"))
    with zipfile.ZipFile(path, "r") as z:
        z.extractall(tmp)
    manifests = list(tmp.rglob("tile_manifest.json")) + list(tmp.rglob("project_manifest.json"))
    if not manifests:
        raise ValueError("Handoff ZIP must contain tile_manifest.json or project_manifest.json")
    return _load_handoff_manifest(manifests[0])


def load_project_input(source: str | Path | BaseGeometry, *, project_id: Optional[str] = None,
                       project_name: Optional[str] = None, domain: str = "auto",
                       attributes: Optional[Dict[str, Any]] = None) -> ProjectInput:
    """Normalize supported assessment inputs into a validated project model."""
    if isinstance(source, BaseGeometry):
        emu = EMU(project_id or "EMU_001", _normalise_geometry(source), domain, None, area_ha(source), project_id, attributes or {})
        project = ProjectInput(project_id or "project", project_name or project_id or "project", "<geometry>", [emu], domain, attributes or {})
    else:
        path = Path(source)
        if not path.exists(): raise FileNotFoundError(path)
        suffix = path.suffix.lower()
        if suffix == ".zip":
            project = _load_handoff_zip(path)
        elif suffix in {".kml", ".kmz"}:
            project = _load_kml_project(path)
        elif suffix in {".geojson", ".json"}:
            raw = json.loads(path.read_text(encoding="utf-8"))
            # Explicit handoff manifests are JSON metadata documents, not GeoJSON.
            if "tiles" in raw or "emus" in raw or "tile_manifest" in raw:
                project = _load_handoff_manifest(path)
            else:
                emus, meta = _load_geojson(path)
                project = ProjectInput(str(meta.get("project_id") or path.stem), str(meta.get("project_name") or path.stem), str(path), emus, str(meta.get("domain") or domain), meta)
        else:
            raise ValueError("Supported inputs are .geojson/.json, .kml/.kmz, or a Shapely geometry")
        if project_id: project.project_id = project_id
        if project_name: project.project_name = project_name
        if domain != "auto": project.project_domain = domain
    if project.project_domain not in SUPPORTED_DOMAINS: raise ValueError(f"Unsupported project domain: {project.project_domain}")
    errors = project.validate()
    if errors: raise ValueError("Invalid project input: " + "; ".join(errors))
    return project
