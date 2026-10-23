"""Assessment units: sites and the EMUs nested inside them (decision D-23-8).

A *site* is the full project boundary (Site Selection ``aoi_boundary.geojson`` or any
supplied boundary). Without a boundary, EMUs closer than ``site_cluster_distance_m``
are grouped into one site whose geometry is their union; widely separated polygons
(for example the four Corbett sites, 1-30 km apart) each become their own site.

Site level carries extent, pressure, species, coarse layers and the headline; EMU
level carries 10-30 m condition metrics and the managed-land result. Built-up land
and water are classified, never cut out of the site.

All geometry work here is plain Shapely/pyproj so it is fully testable offline.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .inputs import EMU, ProjectInput
from .site import _normalise_geometry, _reproject, _utm_epsg, area_ha, projected_buffer


@dataclass
class Site:
    site_id: str
    geometry: BaseGeometry
    emus: List[EMU]
    boundary_source: str  # "supplied_boundary" | "emu_union"
    area_ha: float
    emu_area_ha: float
    emu_area_outside_site_ha: float = 0.0
    flags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "site_id": self.site_id,
            "boundary_source": self.boundary_source,
            "area_ha": round(self.area_ha, 4),
            "emu_ids": [e.emu_id for e in self.emus],
            "emu_area_ha": round(self.emu_area_ha, 4),
            "emu_share_of_site_pct": round(100 * self.emu_area_ha / self.area_ha, 2) if self.area_ha else None,
            "emu_area_outside_site_ha": round(self.emu_area_outside_site_ha, 4),
            "flags": list(self.flags),
        }


@dataclass
class AssessmentUnits:
    project_id: str
    sites: List[Site]
    site_cluster_distance_m: float
    flags: List[str] = field(default_factory=list)

    @property
    def total_site_area_ha(self) -> float:
        return float(sum(s.area_ha for s in self.sites))

    def footprint(self) -> BaseGeometry:
        return _normalise_geometry(unary_union([s.geometry for s in self.sites]))

    def to_dict(self) -> Dict[str, object]:
        return {
            "project_id": self.project_id,
            "n_sites": len(self.sites),
            "n_emus": sum(len(s.emus) for s in self.sites),
            "total_site_area_ha": round(self.total_site_area_ha, 4),
            "site_cluster_distance_m": self.site_cluster_distance_m,
            "sites": [s.to_dict() for s in self.sites],
            "flags": list(self.flags),
        }


def _projected(geoms: Sequence[BaseGeometry]):
    from pyproj import Transformer
    epsg = _utm_epsg(unary_union(list(geoms)))
    fwd = Transformer.from_crs("EPSG:4326", epsg, always_xy=True)
    return [_reproject(g, fwd) for g in geoms]


def cluster_by_distance(geoms: Sequence[BaseGeometry], distance_m: float) -> List[List[int]]:
    """Group geometry indices whose metric distance is <= ``distance_m`` (single linkage)."""
    if not geoms:
        return []
    proj = _projected(geoms)
    n = len(proj)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            if proj[i].distance(proj[j]) <= distance_m:
                parent[find(i)] = find(j)
    groups: Dict[int, List[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return sorted(groups.values(), key=lambda g: g[0])


def build_units(project: ProjectInput, boundary: Optional[BaseGeometry] = None,
                site_cluster_distance_m: float = 1000.0) -> AssessmentUnits:
    """Build sites and nest EMUs inside them.

    With a boundary, its parts are clustered by the same distance rule and every EMU
    is assigned to the site it overlaps most; EMU area outside the boundary is
    reported, never dropped silently. Without a boundary, EMUs are clustered and each
    cluster's union is the site.
    """
    if site_cluster_distance_m < 0:
        raise ValueError("site_cluster_distance_m must be >= 0")
    emus = list(project.emus)
    flags: List[str] = []
    sites: List[Site] = []
    if boundary is not None:
        boundary = _normalise_geometry(boundary)
        if boundary.is_empty or not boundary.is_valid:
            raise ValueError("Supplied site boundary is empty or invalid")
        parts = list(getattr(boundary, "geoms", [boundary]))
        groups = cluster_by_distance(parts, site_cluster_distance_m)
        site_geoms = [_normalise_geometry(unary_union([parts[i] for i in g])) for g in groups]
        assigned: Dict[int, List[EMU]] = {i: [] for i in range(len(site_geoms))}
        unassigned = []
        for e in emus:
            overlaps = [e.geometry.intersection(sg).area for sg in site_geoms]
            best = max(range(len(site_geoms)), key=lambda i: overlaps[i])
            if overlaps[best] <= 0:
                unassigned.append(e.emu_id)
                continue
            assigned[best].append(e)
        if unassigned:
            raise ValueError(f"EMUs outside the supplied site boundary: {unassigned}")
        for i, sg in enumerate(site_geoms):
            members = assigned[i]
            emu_area = sum(area_ha(e.geometry) for e in members)
            outside = sum(area_ha(e.geometry.difference(sg)) for e in members if not e.geometry.difference(sg).is_empty)
            s = Site(f"SITE_{i + 1:02d}", sg, members, "supplied_boundary", area_ha(sg), emu_area, outside)
            if outside > 0.01:
                s.flags.append(f"emu_area_outside_boundary_ha={outside:.3f}")
            if not members:
                s.flags.append("site_has_no_emu")
            sites.append(s)
    else:
        groups = cluster_by_distance([e.geometry for e in emus], site_cluster_distance_m)
        for i, g in enumerate(groups):
            members = [emus[k] for k in g]
            sg = _normalise_geometry(unary_union([m.geometry for m in members]))
            emu_area = sum(area_ha(m.geometry) for m in members)
            s = Site(f"SITE_{i + 1:02d}", sg, members, "emu_union", area_ha(sg), emu_area)
            if emu_area - s.area_ha > 0.01:
                s.flags.append(f"emu_overlap_ha={emu_area - s.area_ha:.3f}")
            sites.append(s)
        flags.append("no_boundary_supplied: site = union of EMU polygons")
    if len(sites) == 1 and len(sites[0].emus) == 1 and sites[0].boundary_source == "emu_union":
        flags.append("single_polygon: site and EMU coincide")
    return AssessmentUnits(project.project_id, sites, site_cluster_distance_m, flags)


def context_window(geom: BaseGeometry, scale_m: float, min_pixels: float = 4.0,
                   max_buffer_m: float = 5000.0) -> Tuple[BaseGeometry, float]:
    """Smallest outward buffer whose area holds ``min_pixels`` native pixels (decision 5).

    Returns ``(geometry, buffer_m)``; ``buffer_m == 0`` when the unit already holds
    enough pixel-equivalents. Raises if even ``max_buffer_m`` is not enough, so a
    caller can never silently use an undersized window.
    """
    if scale_m <= 0 or min_pixels <= 0:
        raise ValueError("scale_m and min_pixels must be positive")
    target_ha = min_pixels * scale_m * scale_m / 10_000.0
    if area_ha(geom) >= target_ha:
        return geom, 0.0
    lo, hi = 0.0, max(scale_m, math.sqrt(target_ha * 10_000.0 / math.pi))
    while area_ha(projected_buffer(geom, hi)) < target_ha:
        hi *= 2
        if hi > max_buffer_m:
            raise ValueError(f"context window would exceed {max_buffer_m} m")
    for _ in range(40):
        mid = (lo + hi) / 2
        if area_ha(projected_buffer(geom, mid)) >= target_ha:
            hi = mid
        else:
            lo = mid
        if hi - lo < 1.0:
            break
    return projected_buffer(geom, hi), round(hi, 1)
