"""
06_reporting / field_map_builder.py
======================================

Standalone field_map.html — separate from the site selection report, the
one file to open first for anyone wanting the fastest orientation on a
project's design; meant to stand completely on its own, not be a section
inside a longer report.

Same visual language as the reference Tata Motors Field Recce map
(badge-style circular icons, Font Awesome, a collapsible legend, a layer
control), extended with a cycle/week selector so only one deployment
cycle's EMUs show at a time rather than every cycle overlaid and confused
together.

Shows real, individual device positions at their actual candidate
coordinates (not just an EMU centroid) — every marker is a genuine,
spacing-verified position from that EMU's own real candidate pool,
matching exactly what the deployment schedule assigns.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from shapely.geometry import mapping, shape
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
import config_schema  # noqa: E402

logger = logging.getLogger(__name__)

PALETTE = [
    # A standard, well-tested maximally-distinct categorical palette (hues
    # spread evenly around the colour wheel, each kept dark/saturated
    # enough to stay visible as a semi-transparent EMU polygon fill over
    # satellite imagery, rather than washing out) — same-hue-family
    # colours (e.g. two different greens) become hard to tell apart at
    # typical EMU fill opacity, especially for spatially adjacent EMUs.
    "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#42d4f4",
    "#f032e6", "#808000", "#9a6324", "#800000", "#000075", "#bfef45",
]


def _emu_display_name(emu_id: str) -> str:
    """Real zone/anchor names for the map, not internal EMU_ID strings.
    Strips the internal EMU_/EMU_ANCHOR_ prefix and turns
    underscores back into spaces; anything genuinely unrecognised is
    returned as-is rather than mangled."""
    name = emu_id
    for prefix in ("EMU_ANCHOR_", "EMU_"):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    return name.replace("_", " ")


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    return json.load(open(path)) if path.exists() else None


def _load_fc(path: Path) -> List[Dict[str, Any]]:
    fc = _load_json(path)
    return fc["features"] if fc else []


def _dissolve_emus(fc_features: List[Dict[str, Any]], is_contiguous: bool) -> Dict[str, Any]:
    if is_contiguous:
        return {f["properties"]["emu_id"]: shape(f["geometry"]) for f in fc_features}
    by_emu: Dict[str, List] = {}
    for f in fc_features:
        emu_id = f["properties"].get("emu_id")
        if emu_id is None:
            continue
        by_emu.setdefault(emu_id, []).append(shape(f["geometry"]))
    return {eid: unary_union(geoms) for eid, geoms in by_emu.items()}


def build_field_map(project_dir: Path, cfg: Dict[str, Any]) -> str:
    is_contiguous = cfg["archetype"] in ("conservation", "industrial")
    ing_dir = project_dir / "outputs" / "01_ingestion"
    emu_dir = project_dir / "outputs" / "03_emu_delineation"
    dep_dir = project_dir / "outputs" / "04_deployment_planning"

    emu_source = emu_dir / ("emus.geojson" if is_contiguous else "candidates_with_emu.geojson")
    emu_fc_features = _load_fc(emu_source)
    per_tile_features = _load_fc(emu_dir / "candidates_with_emu.geojson")  # ALL member
    # tiles/parcels per EMU, regardless of archetype (uniform since the
    # segmentation-path fix) — needed for the per-EMU toggle ("show me
    # EMU 1's full parcel set"), not just the position pool.
    position_pool_features = _load_fc(project_dir / "outputs" / "03b_position_scoring" / "position_pool.geojson")
    # camera_trap_pool.geojson (the old static, project-wide file) is no
    # longer read here — see the real bug fix note below at camera_points'
    # construction for why.
    anchors = _load_fc(ing_dir / "ecological_anchors.geojson")
    exclusions = _load_fc(ing_dir / "exclusion_zones.geojson")

    # Real Phase 01 field history (13-27 Aug 2026): Week 1 shows the real,
    # already-collected deployment for every stream instead of the
    # theoretical rotation; other weeks follow the designed rotation.
    # Optional and project-specific (only Tata Motors has a real Phase 01
    # history to show) — every other project's map is unaffected.
    historical_streams: Dict[str, List[Dict[str, Any]]] = {}
    crosswalk_path = project_dir / "historical" / "crosswalk_report.json"
    if crosswalk_path.exists():
        with open(crosswalk_path) as f:
            crosswalk = json.load(f)
        for stream_name, rows in crosswalk.get("streams", {}).items():
            historical_streams[stream_name] = [
                {
                    "lat": r["lat"], "lon": r["lng"],
                    "label": r.get("id") or r.get("name") or r.get("loc") or stream_name,
                    "zone": r.get("new_eco_zone"),
                    "date": r.get("date"),
                    "status": r["status"],
                }
                for r in rows
            ]

    # Real, one-time (not week-rotated) soil chemistry composite sample
    # points — client-reported design: 4 corners + 1 centre per EMU,
    # collected once during the final deployment week. Optional and
    # project-specific (currently only Soulforest has this file) — every
    # other project's map is unaffected.
    soil_chem_points: List[Dict[str, Any]] = []
    soil_chem_path = project_dir / "outputs" / "06_reporting" / "soil_chemistry_points.geojson"
    if soil_chem_path.exists():
        with open(soil_chem_path) as f:
            soil_chem_fc = json.load(f)
        for feat in soil_chem_fc["features"]:
            lon, lat = feat["geometry"]["coordinates"]
            soil_chem_points.append({"lat": lat, "lon": lon, "label": feat["properties"]["label"],
                                     "emu_id": feat["properties"]["emu_id"]})

    dissolved_emus = _dissolve_emus(emu_fc_features, is_contiguous)
    deployment_report = _load_json(dep_dir / "deployment_schedule.json") or {}
    schedule = deployment_report.get("schedule", [])
    regime = deployment_report.get("regime", "sequential_cluster")

    # week_active_positions: {week_number: {emu_id: [position_name, ...]}}
    # — built uniformly for BOTH regimes so the field map's week toggle
    # works the same way regardless. continuous_proportional already has
    # real per-week position_assignments; sequential_cluster doesn't do
    # within-cycle position rotation, so each active EMU's medoid stands
    # in as "the" position for that cycle.
    medoid_by_emu: Dict[str, str] = {}
    for feat in position_pool_features:
        if feat["properties"].get("is_medoid"):
            medoid_by_emu[feat["properties"]["emu_id"]] = feat["properties"].get("name")

    week_active_positions: Dict[int, Dict[str, List[str]]] = {}
    cycle_of_emu: Dict[str, int] = {}
    for c in schedule:
        week_num = c["cycle_number"]
        week_active_positions.setdefault(week_num, {})
        if c.get("position_assignments"):
            for a in c["position_assignments"]:
                week_active_positions[week_num][a["emu_id"]] = [p["name"] for p in a["positions"]]
                cycle_of_emu[a["emu_id"]] = week_num  # last-write, but continuous means "active every week" anyway
        else:
            for emu_id in c["emu_ids"]:
                cycle_of_emu[emu_id] = week_num
                if emu_id in medoid_by_emu:
                    week_active_positions[week_num][emu_id] = [medoid_by_emu[emu_id]]

    uncovered = set(deployment_report.get("uncovered_emu_ids", []))
    if not schedule:
        for emu_id in dissolved_emus:
            cycle_of_emu[emu_id] = 1

    # EMU-view must show exactly the same real, scheduled positions
    # week-view does, not the EMU's full theoretical position pool — the
    # pool can genuinely exceed what's actually deployed (e.g. an EMU
    # sharing a week's device budget with another EMU may only get some
    # of its own real pool positions actually allocated a device). The
    # union across every week that EMU is
    # actually active, not the full candidate pool it could theoretically
    # draw from. The full pool remains visible via the existing "pool
    # positions never used" layer, honestly labelled as such.
    ever_scheduled_by_emu: Dict[str, set] = {}
    for week_data in week_active_positions.values():
        for emu_id, names in week_data.items():
            ever_scheduled_by_emu.setdefault(emu_id, set()).update(names)

    emu_features = []
    color_by_emu: Dict[str, str] = {}
    # Sorting explicitly (anchors first, alphabetically; then
    # everything else in natural/numeric order, so SEG02 sorts before
    # SEG10) makes the colour assignment reproducible and predictable
    # across regenerations, not just internally consistent within one run.
    def _emu_sort_key(emu_id: str):
        is_anchor = emu_id.startswith("EMU_ANCHOR_")
        import re as _re
        num_match = _re.search(r"(\d+)$", emu_id)
        num = int(num_match.group(1)) if num_match else -1
        return (0 if is_anchor else 1, num, emu_id)

    for i, emu_id in enumerate(sorted(dissolved_emus.keys(), key=_emu_sort_key)):
        geom = dissolved_emus[emu_id]
        centroid = geom.centroid
        color = PALETTE[i % len(PALETTE)]
        color_by_emu[emu_id] = color
        emu_features.append({
            "type": "Feature", "geometry": mapping(geom),
            "properties": {
                "emu_id": emu_id, "displayName": _emu_display_name(emu_id), "color": color,
                "cycle": cycle_of_emu.get(emu_id),
                "activeEveryWeek": regime == "continuous_proportional",
                "uncovered": emu_id in uncovered,
                "centroid": [centroid.y, centroid.x],
            },
        })

    # Full per-EMU tile/parcel set (every real candidate, not just the
    # position pool) — this is what the per-EMU toggle shows alongside the
    # pool, per: "show me all the parcels that are there in emu 1 + the
    # selected parcels for deployment in that emu".
    emu_tiles: Dict[str, List[Dict[str, Any]]] = {}
    for feat in per_tile_features:
        emu_id = feat["properties"].get("emu_id")
        if emu_id is None or emu_id not in color_by_emu:
            continue
        c = shape(feat["geometry"]).centroid
        emu_tiles.setdefault(emu_id, []).append({
            "lat": c.y, "lon": c.x, "name": feat["properties"].get("display_name") or feat["properties"].get("name"),
        })

    # Candidate points carry real ranking data — typicality percentile,
    # whether it's the stratum medoid, and why it's or isn't in the active
    # position pool, not just a colour-matched dot. Split into two layers:
    # an active "position pool" (medoid + the spatially-binned
    # spatial-coverage picks) and "pool positions never used" (every
    # other real candidate, kept visible for transparency about the full
    # pool that was actually considered).
    pool_points, unused_points = [], []
    for feat in position_pool_features:
        emu_id = feat["properties"].get("emu_id")
        if emu_id is None or emu_id not in color_by_emu:
            continue
        c = shape(feat["geometry"]).centroid
        point = {
            "lat": c.y, "lon": c.x, "emu_id": emu_id, "color": color_by_emu[emu_id],
            "name": feat["properties"].get("name"),
            "percentile": feat["properties"].get("typicality_percentile"),
            "isMedoid": feat["properties"].get("is_medoid", False),
            "rationale": feat["properties"].get("selection_rationale", ""),
        }
        (pool_points if feat["properties"].get("in_position_pool") else unused_points).append(point)

    # Camera points are built directly from the real schedule data,
    # with real coordinates looked up from the same per-tile source
    # everything else on this map uses, and real typicality/rationale
    # pulled from the audiomoth position pool where the position happens
    # to also appear there (camera trap can pick a tile audiomoth never
    # scored as highly, in which case a plain, honest fallback is used
    # rather than fabricating a percentile).
    tile_coords = {}
    for feat in per_tile_features:
        nm = feat["properties"].get("display_name") or feat["properties"].get("name")
        c = shape(feat["geometry"]).centroid
        tile_coords[nm] = (c.y, c.x)
    pool_info_by_name = {p["properties"].get("display_name") or p["properties"].get("name"): p["properties"]
                         for p in position_pool_features}

    camera_points = []
    week_active_camera: Dict[int, List[str]] = {}
    for c in schedule:
        cam_positions = c.get("camera_trap_positions", [])
        week_active_camera[c["cycle_number"]] = [p["name"] for p in cam_positions]
        for p in cam_positions:
            name = p["name"]
            if name not in tile_coords:
                continue  # shouldn't happen — real position, real tile — but never crash the map over it
            lat, lon = tile_coords[name]
            info = pool_info_by_name.get(name)
            camera_points.append({
                "lat": lat, "lon": lon, "name": name, "emu_id": p.get("emu_id"),
                "percentile": info.get("typicality_percentile") if info else None,
                "rationale": (info.get("selection_rationale") if info
                             else ("shared with audiomoth — this EMU has only one real candidate "
                                   "position" if p.get("shared_with_audiomoth")
                                   else "camera trap position, co-located with this week's active EMU")),
            })

    n_cycles = max([c["cycle_number"] for c in schedule], default=1)
    map_data = {
        "emus": {"type": "FeatureCollection", "features": emu_features},
        "anchors": {"type": "FeatureCollection", "features": anchors},
        "exclusions": {"type": "FeatureCollection", "features": exclusions},
        "positionPool": pool_points,
        "unusedPool": unused_points,
        "cameraTrapPool": camera_points,
        "weekActiveCamera": week_active_camera,
        "emuTiles": emu_tiles,
        "weekActivePositions": week_active_positions,
        "everScheduledByEmu": {eid: sorted(names) for eid, names in ever_scheduled_by_emu.items()},
        "regime": regime,
        "n_cycles": n_cycles,
        "seasonLengthWeeks": cfg.get("season_length_weeks"),
        "historicalStreams": historical_streams,
        "soilChemPoints": soil_chem_points,
        # Only audiomoth and camera trap have real, rotating position
        # logic built. The others (soil/eDNA/water quality) are real
        # parts of the project but are one-time fixed-location samples,
        # not something with a rotating "position" to show on this kind
        # of map at all.
        "streamsActive": [s for s in cfg.get("streams_active", ["audiomoth"])
                          if s in ("audiomoth", "camera_trap")],
        "otherConfiguredStreams": [s for s in cfg.get("streams_active", [])
                                   if s not in ("audiomoth", "camera_trap")
                                   and not (s == "soil_sample" and soil_chem_points)],
    }
    if emu_features:
        first = shape(emu_features[0]["geometry"]).centroid
        center = [first.y, first.x]
    else:
        center = [20.0, 78.0]

    return FIELD_MAP_TEMPLATE.format(
        project_name=cfg["project_name"],
        map_data_json=json.dumps(map_data),
        center_lat=center[0], center_lon=center[1],
        n_cycles=n_cycles,
    )


FIELD_MAP_TEMPLATE = """<!DOCTYPE html>
<html><head>
<meta charset="UTF-8"/>
<title>{project_name} \u2014 Field Map</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.js"></script>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.css"/>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css"/>
<style>
  html, body, #map {{ width: 100%; height: 100%; margin: 0; padding: 0; font-family: system-ui, -apple-system, sans-serif; }}
  .cycle-selector {{
    background: #ffffff; padding: 10px 14px; border-radius: 8px;
    box-shadow: 0 3px 14px rgba(0,0,0,0.25); font-size: 13px;
  }}
  .cycle-selector select {{ font-size: 14px; padding: 4px 8px; margin-left: 6px; }}
  .badge-icon {{
    display: flex; align-items: center; justify-content: center;
    border-radius: 50%; color: #ffffff; font-size: 11px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.4); border: 2px solid #ffffff;
    transition: transform 0.15s ease-in-out;
  }}
  .badge-icon:hover {{ transform: scale(1.25); z-index: 1000 !important; }}
  .custom-legend {{
    background: #ffffff; padding: 12px 16px; border-radius: 8px;
    box-shadow: 0 3px 14px rgba(0,0,0,0.25); font-size: 12px; line-height: 1.8; max-width: 260px;
    cursor: pointer;
  }}
  .legend-header {{ font-weight: 700; display: flex; justify-content: space-between; align-items: center; }}
  .legend-body {{ margin-top: 6px; }}
  .legend-body.collapsed {{ display: none; }}
  .legend-row {{ display: flex; align-items: center; gap: 10px; cursor: default; }}
  .legend-badge {{
    width: 18px; height: 18px; border-radius: 50%; display: flex;
    align-items: center; justify-content: center; color: #fff; font-size: 9px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.3);
  }}
</style>
</head>
<body>
  <div id="map"></div>
  <script>
    var mapData = {map_data_json};
    var map = L.map('map', {{ center: [{center_lat}, {center_lon}], zoom: 16 }});

    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
      attribution: 'Esri World Imagery'
    }}).addTo(map);

    // Badge-style icon, same visual language as the Tata Motors field
    // maps this was asked to match — a coloured circular badge with a
    // Font Awesome glyph, not a plain dot.
    function badgeIcon(iconClass, color, size) {{
      return L.divIcon({{
        className: 'custom-leaflet-icon',
        html: '<div class="badge-icon" style="background:' + color + ';width:' + size + 'px;height:' + size + 'px;"><i class="' + iconClass + '"></i></div>',
        iconSize: [size, size], iconAnchor: [size/2, size/2], popupAnchor: [0, -size/2],
      }});
    }}
    var STREAM_ICONS = {{
      audiomoth: 'fa-solid fa-microphone-lines',
      camera_trap: 'fa-solid fa-camera',
      water_edna: 'fa-solid fa-droplet',
      soil_edna: 'fa-solid fa-dna',
      water_quality: 'fa-solid fa-flask-vial',
      soil_sample: 'fa-solid fa-seedling',
    }};
    // Historical-stream icons/colours match the real Field Recce map's
    // own badge styling exactly, so a real Phase 01 marker looks the
    // same here as it did in that original file.
    var HISTORICAL_ICONS = {{
      audiomoths: {{icon: 'fa-solid fa-microphone-lines', color: '#15803d'}},
      hydro: {{icon: 'fa-solid fa-water', color: '#0369a1'}},
      camera_trap: {{icon: 'fa-solid fa-camera', color: '#c2410c'}},
      water_chem: {{icon: 'fa-solid fa-flask-vial', color: '#0891b2'}},
      soil_chem: {{icon: 'fa-solid fa-seedling', color: '#854d0e'}},
      water_edna: {{icon: 'fa-solid fa-droplet', color: '#2563eb'}},
      soil_edna: {{icon: 'fa-solid fa-dna', color: '#7e22ce'}},
    }};
    var PRIMARY_STREAM = mapData.streamsActive && mapData.streamsActive.length ? mapData.streamsActive[0] : 'audiomoth';
    var PRIMARY_ICON = STREAM_ICONS[PRIMARY_STREAM] || STREAM_ICONS.audiomoth;

    var emuLayerGroup = L.layerGroup().addTo(map);
    var poolLayer = L.layerGroup().addTo(map);
    var unusedLayer = L.layerGroup().addTo(map);  // on by default, so
    // every real surveyed candidate is visible without needing to find
    // and check a layer-control box first.
    var anchorLayer = L.geoJSON(mapData.anchors, {{
      style: {{ color: '#166534', weight: 3, dashArray: '4 4', fillOpacity: 0.08 }},
      onEachFeature: function(f, layer) {{ layer.bindPopup('Ecological anchor: ' + f.properties.name); }}
    }}).addTo(map);
    var exclusionLayer = L.geoJSON(mapData.exclusions, {{
      style: {{ color: '#991b1b', weight: 1, fillOpacity: 0.12, dashArray: '2 4' }},
      onEachFeature: function(f, layer) {{ layer.bindPopup('Exclusion (' + f.properties.role + '): ' + f.properties.name); }}
    }}).addTo(map);

    var anyUncovered = mapData.emus.features.some(function(f) {{ return f.properties.uncovered; }});
    var tileLayer = L.layerGroup();  // full parcel/tile set for the selected EMU only
    var cameraTrapLayer = L.layerGroup().addTo(map);
    var historicalLayer = L.layerGroup().addTo(map);
    // One-time soil chemistry composite points — not week-rotated, so
    // this layer is built once here (not inside render()) and never
    // cleared/rebuilt on week/EMU toggles, exactly like the underlying
    // real sampling design: collected once, not repeated.
    var soilChemLayer = L.layerGroup();
    (mapData.soilChemPoints || []).forEach(function(p) {{
      var marker = L.marker([p.lat, p.lon], {{ icon: badgeIcon('fa-solid fa-seedling', '#854d0e', 20) }});
      marker.bindPopup('<b>' + p.label + '</b><br>Soil chemistry composite sample' +
        '<br><i>One-time, collected during the final deployment week — not part of the weekly rotation.</i>' +
        '<br><span style="color:#666;font-size:11px;">' + p.lat.toFixed(6) + ', ' + p.lon.toFixed(6) + '</span>');
      marker.bindTooltip(p.label, {{sticky: true}});
      marker.addTo(soilChemLayer);
    }});

    var emuDisplayName = {{}};
    mapData.emus.features.forEach(function(f) {{ emuDisplayName[f.properties.emu_id] = f.properties.displayName; }});

    function popupHtml(p) {{
      return '<b>' + p.name + '</b><br>Zone: ' + (emuDisplayName[p.emu_id] || p.emu_id) +
        '<br>Typicality: ' + p.percentile + 'th percentile' +
        '<br><i>' + p.rationale + '</i>' +
        '<br><span style="color:#666;font-size:11px;">' +
        p.lat.toFixed(6) + ', ' + p.lon.toFixed(6) + '</span>';
    }}

    // Unified view state: {{mode: 'all'}} | {{mode: 'week', week: N}} |
    // {{mode: 'emu', emuId: X}}. EMU-view shows the EMU's real parcels plus
    // its real scheduled deployment positions; week-view shows only that
    // week's active positions.
    function render(view) {{
      emuLayerGroup.clearLayers();
      poolLayer.clearLayers();
      unusedLayer.clearLayers();
      tileLayer.clearLayers();
      historicalLayer.clearLayers();

      var activeEmuId = view.mode === 'emu' ? view.emuId : null;
      var activeWeek = view.mode === 'week' ? view.week : null;
      // Week 1 shows the real Phase 01 deployment for every stream;
      // every other week, including week 1 of later seasons, shows the
      // theoretical rotation as normal, since the real Phase 01
      // deployment only happened once. Only meaningful for a project
      // with real crosswalked history (mapData.historicalStreams
      // non-empty) — every other project's week 1 behaves exactly as
      // any other week.
      var showHistorical = activeWeek === 1 && mapData.historicalStreams
        && Object.keys(mapData.historicalStreams).length > 0;

      mapData.emus.features.forEach(function(f) {{
        var emuId = f.properties.emu_id;
        if (activeEmuId && emuId !== activeEmuId) return;
        if (activeWeek !== null) {{
          var weekData = mapData.weekActivePositions[String(activeWeek)] || {{}};
          if (!(emuId in weekData) && !f.properties.activeEveryWeek) return;
          if (!(emuId in weekData) && f.properties.activeEveryWeek === false) return;
        }}
        var style = {{
          color: f.properties.uncovered ? '#991b1b' : f.properties.color,
          weight: activeEmuId ? 3 : 2,
          fillOpacity: f.properties.uncovered ? 0.1 : (activeEmuId ? 0.5 : 0.35),
          dashArray: f.properties.uncovered ? '3 3' : null,
        }};
        var layer = L.geoJSON(f, {{ style: style }});
        var label = '<b>' + emuId + '</b>' +
          (f.properties.uncovered ? '<br><span style="color:#991b1b">Not scheduled this baseline</span>' : '');
        layer.bindPopup(label);
        layer.addTo(emuLayerGroup);

        // A very small EMU (one grid cell, ~25x25m) is a real polygon in
        // the data but genuinely imperceptible at normal zoom — a
        // legibility issue, not a rendering bug. A permanent centroid
        // marker keeps a tiny EMU always visible and clickable,
        // regardless of zoom level.
        var boundsCheck = layer.getBounds();
        if (boundsCheck.isValid()) {{
          var diag = boundsCheck.getNorthEast().distanceTo(boundsCheck.getSouthWest());
          if (diag < 40) {{
            L.circleMarker(f.properties.centroid, {{
              radius: 6, color: '#ffffff', weight: 2,
              fillColor: f.properties.uncovered ? '#991b1b' : f.properties.color, fillOpacity: 0.9,
            }}).bindPopup(label).bindTooltip(emuId, {{sticky: true}}).addTo(emuLayerGroup);
          }}
        }}
      }});

      // Full parcel/tile set — only ever shown for a specific selected EMU
      // (showing every project's every tile at once would be noise, not
      // the "show me EMU 1's full parcel set" view that was asked for).
      if (activeEmuId && mapData.emuTiles[activeEmuId]) {{
        mapData.emuTiles[activeEmuId].forEach(function(t) {{
          L.circleMarker([t.lat, t.lon], {{
            radius: 3, color: '#374151', weight: 1, fillColor: '#9ca3af', fillOpacity: 0.6,
          }}).bindTooltip(t.name, {{sticky: true}})
            .bindPopup('<b>' + t.name + '</b><br>EMU: ' + activeEmuId +
                       '<br><span style="color:#666;font-size:11px;">' + t.lat.toFixed(6) + ', ' + t.lon.toFixed(6) + '</span>')
            .addTo(tileLayer);
        }});
      }}

      if (!showHistorical) {{
        mapData.positionPool.forEach(function(p) {{
          if (activeEmuId && p.emu_id !== activeEmuId) return;
          if (activeWeek !== null) {{
            var weekData = mapData.weekActivePositions[String(activeWeek)] || {{}};
            var activeNames = weekData[p.emu_id] || [];
            if (activeNames.indexOf(p.name) === -1) return;  // only THIS week's active position(s)
          }} else {{
            // "all" (overlaid) mode uses the same real, scheduled-position
            // filter as EMU-view and week-view, so every mode shows
            // exactly the same real positions, just combined differently.
            var everScheduled = mapData.everScheduledByEmu[p.emu_id] || [];
            if (everScheduled.indexOf(p.name) === -1) return;
          }}
          var size = p.isMedoid ? 30 : 22;
          var marker = L.marker([p.lat, p.lon], {{ icon: badgeIcon(PRIMARY_ICON, p.color, size) }});
          marker.bindPopup(popupHtml(p));
          // The hover label is just the position name; the full technical
          // rationale (including "stratum medoid" where that applies)
          // still lives in the click popup for anyone who wants it.
          marker.bindTooltip(p.name, {{sticky: true}});
          marker.addTo(poolLayer);
        }});
      }}
      if (!activeWeek) {{
        mapData.unusedPool.forEach(function(p) {{
          if (activeEmuId && p.emu_id !== activeEmuId) return;
          var marker = L.circleMarker([p.lat, p.lon], {{ radius: 2, color: p.color, weight: 0, fillOpacity: 0.3 }});
          marker.bindPopup(popupHtml(p));
          marker.bindTooltip(p.name, {{sticky: true}});
          marker.addTo(unusedLayer);
        }});
        // A real, spacing-verified pool position that never actually got
        // a device allocated (e.g. it shares a week's device budget with
        // another EMU) is a genuine, useful fact — the site can support
        // more coverage than the current device count funds — not
        // something that should just disappear once it's excluded from
        // the main "Audiomoth" layer above. Shown the same way as a
        // never-selected pool position.
        if (!showHistorical) {{
          mapData.positionPool.forEach(function(p) {{
            if (activeEmuId && p.emu_id !== activeEmuId) return;
            var everScheduled = mapData.everScheduledByEmu[p.emu_id] || [];
            if (everScheduled.indexOf(p.name) !== -1) return;  // already shown in the main layer
            var marker = L.circleMarker([p.lat, p.lon], {{ radius: 2, color: p.color, weight: 0, fillOpacity: 0.3 }});
            marker.bindPopup(popupHtml(p) + '<br><i>In the real position pool, but no device currently funds it this cycle.</i>');
            marker.bindTooltip(p.name, {{sticky: true}});
            marker.addTo(unusedLayer);
          }});
        }}
      }}

      // Camera trap — independent pool/rotation from audiomoth, own icon,
      // own layer.
      cameraTrapLayer.clearLayers();
      if (!showHistorical) {{
        mapData.cameraTrapPool.forEach(function(p) {{
          if (activeEmuId && p.emu_id !== activeEmuId) return;
          if (activeWeek !== null) {{
            var activeCam = mapData.weekActiveCamera[String(activeWeek)] || [];
            if (activeCam.indexOf(p.name) === -1) return;
          }}
          var marker = L.marker([p.lat, p.lon], {{ icon: badgeIcon('fa-solid fa-camera', '#c2410c', 24) }});
          marker.bindPopup('<b>' + p.name + '</b><br>Camera trap pool' +
            (p.emu_id ? '<br>Zone: ' + (emuDisplayName[p.emu_id] || p.emu_id) : '') +
            '<br>Typicality: ' + p.percentile + 'th percentile' +
            '<br><i>' + p.rationale + '</i>' +
            '<br><span style="color:#666;font-size:11px;">' + p.lat.toFixed(6) + ', ' + p.lon.toFixed(6) + '</span>');
          marker.bindTooltip(p.name, {{sticky: true}});
          marker.addTo(cameraTrapLayer);
        }});
      }}

      // Real Phase 01 field history — shown ONLY for global week 1, in
      // place of the theoretical positions above, across every stream
      // that was actually deployed then (not just audiomoth/camera).
      if (showHistorical) {{
        Object.keys(mapData.historicalStreams).forEach(function(streamName) {{
          var style = HISTORICAL_ICONS[streamName] || {{icon: 'fa-solid fa-circle', color: '#374151'}};
          mapData.historicalStreams[streamName].forEach(function(p) {{
            var marker = L.marker([p.lat, p.lon], {{ icon: badgeIcon(style.icon, style.color, 24) }});
            marker.bindPopup('<b>' + p.label + '</b> (Phase 01, real deployment)' +
              '<br>Stream: ' + streamName.replace(/_/g, ' ') +
              (p.date ? '<br>Date: ' + p.date : '') +
              '<br>Falls in: ' + (p.zone || 'unmatched zone') +
              '<br><span style="color:#666;font-size:11px;">' + p.status + '</span>' +
              '<br><span style="color:#666;font-size:11px;">' + p.lat.toFixed(6) + ', ' + p.lon.toFixed(6) + '</span>');
            marker.bindTooltip(p.label, {{sticky: true}});
            marker.addTo(historicalLayer);
          }});
        }});
      }}

      if (activeEmuId) {{
        var b = L.geoJSON(mapData.emus.features.filter(function(f) {{ return f.properties.emu_id === activeEmuId; }})).getBounds();
        if (b.isValid()) map.fitBounds(b, {{padding: [40, 40]}});
      }}
    }}
    render({{mode: 'all'}});

    var selector = L.control({{position: 'topright'}});
    selector.onAdd = function() {{
      var div = L.DomUtil.create('div', 'cycle-selector');
      // When the project is season-structured, weeks are grouped into one
      // <optgroup> per season instead of one flat 24-entry list — each
      // season's own weeks numbered 1..season_length_weeks within it, not
      // the raw project-wide week number, since that's what's actually
      // meaningful to a field team planning one season's visits.
      var weekOptions = '';
      var seasonLen = mapData.seasonLengthWeeks;
      if (seasonLen) {{
        var nSeasons = Math.ceil({n_cycles} / seasonLen);
        for (var s = 0; s < nSeasons; s++) {{
          var seasonOptions = '';
          for (var w = 1; w <= seasonLen; w++) {{
            var globalWeek = s * seasonLen + w;
            if (globalWeek > {n_cycles}) break;
            seasonOptions += '<option value="week:' + globalWeek + '">Week ' + w + '</option>';
          }}
          weekOptions += '<optgroup label="Season ' + (s + 1) + '">' + seasonOptions + '</optgroup>';
        }}
      }} else {{
        var flatOptions = '';
        for (var i = 1; i <= {n_cycles}; i++) {{
          flatOptions += '<option value="week:' + i + '">Week ' + i + '</option>';
        }}
        weekOptions = '<optgroup label="By week">' + flatOptions + '</optgroup>';
      }}
      var emuOptions = '';
      mapData.emus.features.forEach(function(f) {{
        emuOptions += '<option value="emu:' + f.properties.emu_id + '">' + f.properties.displayName + '</option>';
      }});
      div.innerHTML = 'Show: <select id="viewSelect">' +
        '<option value="all">Everything (overlaid)</option>' +
        weekOptions +
        '<optgroup label="By EMU">' + emuOptions + '</optgroup>' +
        '</select>';
      L.DomEvent.disableClickPropagation(div);
      return div;
    }};
    selector.addTo(map);
    setTimeout(function() {{
      var el = document.getElementById('viewSelect');
      if (el) el.addEventListener('change', function(e) {{
        var val = e.target.value;
        if (val === 'all') render({{mode: 'all'}});
        else if (val.indexOf('week:') === 0) render({{mode: 'week', week: parseInt(val.slice(5), 10)}});
        else if (val.indexOf('emu:') === 0) render({{mode: 'emu', emuId: val.slice(4)}});
      }});
    }}, 100);

    // Collapsible legend — click the header to collapse/expand, same
    // affordance the reference field maps use. The uncovered-EMU note
    // only renders at all if the run actually has one (should be
    // structurally impossible given the hard coverage policy, but shown
    // truthfully rather than as boilerplate).
    var legend = L.control({{position: 'bottomleft'}});
    legend.onAdd = function() {{
      var div = L.DomUtil.create('div', 'custom-legend');
      // soil_sample is added to the legend's Streams list whenever it's
      // genuinely rendered on the map (soilChemPoints has real content)
      // -- every project without that layer is unaffected.
      var legendStreams = (mapData.streamsActive || ['audiomoth']).slice();
      if (mapData.soilChemPoints && mapData.soilChemPoints.length > 0) {{
        legendStreams.push('soil_sample');
      }}
      var badgeRows = legendStreams.map(function(s) {{
        var icon = STREAM_ICONS[s] || 'fa-solid fa-circle';
        var label = s.replace(/_/g, ' ').replace(/\\b\\w/g, function(c) {{ return c.toUpperCase(); }});
        return '<div class="legend-row"><div class="legend-badge" style="background:#374151;"><i class="' + icon + '"></i></div>' +
          label + '</div>';
      }}).join('');
      var emuRows = mapData.emus.features.map(function(f) {{
        return '<div class="legend-row"><span class="legend-badge" style="background:' +
          f.properties.color + '"></span>' + f.properties.displayName + '</div>';
      }}).join('');
      var uncoveredNote = anyUncovered
        ? '<div style="margin-top:8px;color:#991b1b;font-size:11px;">Dashed red = not scheduled this baseline</div>'
        : '';
      var historicalNote = (mapData.historicalStreams && Object.keys(mapData.historicalStreams).length)
        ? '<div style="margin-top:8px;padding-top:8px;border-top:1px solid #eee;font-size:11px;color:#374151;">' +
          '<b>Week 1</b> shows the real Phase 01 field deployment (13\u201327 Aug 2026) for every stream, ' +
          'not the theoretical rotation. Weeks 2 onward follow the design below.</div>'
        : '';
      div.innerHTML =
        '<div class="legend-header">Legend <span id="legendToggle">\u2212</span></div>' +
        '<div class="legend-body" id="legendBody">' +
        '<div style="font-weight:600;margin:6px 0 2px;">Streams</div>' + badgeRows +
        '<div style="font-weight:600;margin:10px 0 2px;">EMUs</div>' + emuRows +
        uncoveredNote + historicalNote + '</div>';
      L.DomEvent.disableClickPropagation(div);
      div.querySelector('.legend-header').addEventListener('click', function() {{
        var body = document.getElementById('legendBody');
        var toggle = document.getElementById('legendToggle');
        body.classList.toggle('collapsed');
        toggle.textContent = body.classList.contains('collapsed') ? '+' : '\u2212';
      }});
      return div;
    }};
    legend.addTo(map);

    var allBounds = L.geoJSON(mapData.emus).getBounds();
    if (allBounds.isValid()) {{ map.fitBounds(allBounds, {{padding: [20, 20]}}); }}
    L.control.scale().addTo(map);
    // The Phase 01 historical layer entry is only added to the layer
    // control when that project actually has real historical crosswalk
    // data — only Tata Motors does — matching the historical rendering
    // logic in render().
    var layerControlEntries = {{
      "EMU boundaries": emuLayerGroup,
      "Audiomoth": poolLayer,
      "Audiomoth (unused pool positions)": unusedLayer,
      "Full parcel/tile set (select an EMU above)": tileLayer,
      "Ecological anchors": anchorLayer,
      "Exclusion zones": exclusionLayer,
    }};
    // Same principle as the historical layer above — "Camera trap" only
    // appears in the layer control when camera_trap is actually a
    // configured stream for this project.
    if (mapData.streamsActive && mapData.streamsActive.indexOf('camera_trap') !== -1) {{
      layerControlEntries["Camera trap"] = cameraTrapLayer;
    }}
    if (mapData.historicalStreams && Object.keys(mapData.historicalStreams).length > 0) {{
      layerControlEntries["Phase 01 real deployment (week 1 only)"] = historicalLayer;
    }}
    if (mapData.soilChemPoints && mapData.soilChemPoints.length > 0) {{
      layerControlEntries["Soil chemistry (one-time composite samples)"] = soilChemLayer;
      soilChemLayer.addTo(map);
    }}
    L.control.layers(null, layerControlEntries, {{ collapsed: false }}).addTo(map);
  </script>
</body></html>
"""


def run_field_map_build(project_dir: str | Path) -> Path:
    project_dir = Path(project_dir)
    cfg = config_schema.load_config(project_dir / "config.yaml")
    html = build_field_map(project_dir, cfg)
    out_dir = project_dir / "outputs" / "06_reporting"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "field_map.html"
    out_path.write_text(html)
    logger.info("Field map written: %s", out_path)
    return out_path


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    args = parser.parse_args()
    run_field_map_build(args.project_dir)
