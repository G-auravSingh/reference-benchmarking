"""
engine_identity.py -- which engine, and which engine-relevant configuration, produced a result (v0.2.9 Phase 5)
==============================================================================================================

The v0.2.8 benchmarking engine is FROZEN (tag v0.2.8-contract-frozen). The general pipeline (Phase 5) must call it without changing it, and every output must
be able to PROVE that. Two fingerprints, both pure functions of what is on disk / in the configuration:

  * `engine_sha256()`        SHA-256 over the relative path and bytes of the engine modules (ENGINE_FILES). Compared with FROZEN_ENGINE_SHA256, which
                             was computed from git at the frozen tag. A pipeline layer can change; these files cannot, without this changing.
  * `engine_config_sha256()` SHA-256 over ONLY the configuration fields the engine reads (ENGINE_CONFIG_FIELDS, found by static scan of the engine source),
                             with `raster_paths` restricted to the keys the engine reads. Cosmetic fields (output_dir, output_format, archetype, a stray
                             space in gee_project, unused raster keys) do not change it; any change to a field the engine reads does, and is listed by
                             `engine_config_diff()`.
Nothing else lives here: no project names, no scoring, no Earth Engine.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, Optional

PKG_DIR = os.path.dirname(os.path.abspath(__file__))

# every module that computes site values, references, applicability, benchmarks and scores, or loads and tags a zone
ENGINE_FILES = ("assess.py", "benchmarking.py", "config.py", "constructs.py", "ecoregion.py", "indicator_contract.py", "indicators/__init__.py",
                "reference_builders.py", "reference_builders_ee.py", "site_loader.py", "support.py", "tiling.py")

# computed from git at v0.2.8-contract-frozen (commit 3d01100), not from the working tree
FROZEN_ENGINE_SHA256 = "4ec83137870211be21931d5a92b90389db0c5b4a9591a02c11b6d5124eaf7b01"

ENGINE_CONFIG_FIELDS = ('bii_gee_asset', 'ecoregion_gee_asset', 'ecoregion_source', 'flii_edge_effect_radius_m', 'forest_loss_primary_window', 'forest_loss_windows', 'hmi_gee_asset', 'hmi_gee_asset_legacy', 'hmi_gee_band', 'hmi_gee_band_legacy', 'hmi_hard_ceiling', 'lst_year', 'ndvi_cloud_threshold', 'ndvi_year', 'net_change_early_years', 'reference_buffer_km', 'reference_sample_pixels', 'reference_sample_seed', 'reference_tile_native_px', 'riparian_ring_width_m', 'use_legacy_hmi_asset', 'water_body_max_extent_m', 'water_body_reference_radii_km')
ENGINE_RASTER_KEYS = ('iucn_mammals', 'iucn_birds', 'kba_global', 'bii', 'pv_binary', 'edna_points_asset')

# the engine-relevant configuration of the frozen standalone runs (config sha 7f64f9f0 in the frozen standalone production audits)
FROZEN_ENGINE_CONFIG: Dict[str, Any] = {'bii_gee_asset': None,
 'ecoregion_gee_asset': 'RESOLVE/ECOREGIONS/2017',
 'ecoregion_source': 'gee',
 'flii_edge_effect_radius_m': 300.0,
 'forest_loss_primary_window': 'loss_longterm_2001_2025',
 'forest_loss_windows': [['loss_longterm_2001_2025', 1, 25, 25],
                         ['loss_recent_2020_2025', 20, 25, 6],
                         ['loss_current_2023_2025', 23, 25, 3]],
 'hmi_gee_asset': 'TNC/HM/v3/90m_s',
 'hmi_gee_asset_legacy': 'CSP/HM/GlobalHumanModification',
 'hmi_gee_band': 'All_threats_combined',
 'hmi_gee_band_legacy': 'gHM',
 'hmi_hard_ceiling': 0.05,
 'lst_year': 2025,
 'ndvi_cloud_threshold': 20.0,
 'ndvi_year': 2025,
 'net_change_early_years': [2017, 2018],
 'raster_paths': {},
 'reference_buffer_km': 100.0,
 'reference_sample_pixels': 5000,
 'reference_sample_seed': 12345,
 'reference_tile_native_px': 3072,
 'riparian_ring_width_m': 100.0,
 'use_legacy_hmi_asset': False,
 'water_body_max_extent_m': 2000.0,
 'water_body_reference_radii_km': [10.0, 25.0, 50.0]}


def engine_sha256(pkg_dir: str = PKG_DIR) -> str:
    h = hashlib.sha256()
    for f in sorted(ENGINE_FILES):
        with open(os.path.join(pkg_dir, f), "rb") as fh:
            h.update(f.encode()); h.update(fh.read())
    return h.hexdigest()


def _canon(v: Any) -> Any:
    """Canonical form: 20 and 20.0 are the SAME configuration (they compare equal and the engine treats them alike), so they must hash alike."""
    if isinstance(v, bool) or v is None or isinstance(v, str):
        return v
    if isinstance(v, (int, float)):
        return int(v) if float(v).is_integer() else float(v)
    if isinstance(v, dict):
        return {str(k): _canon(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_canon(x) for x in v]
    return str(v)


def engine_config_view(config: Any) -> Dict[str, Any]:
    """JSON-safe, canonical view of exactly the configuration the engine reads."""
    out = {f: _canon(json.loads(json.dumps(getattr(config, f, None), default=str))) for f in ENGINE_CONFIG_FIELDS}
    rp = getattr(config, "raster_paths", None) or {}
    out["raster_paths"] = _canon({k: v for k, v in rp.items() if k in ENGINE_RASTER_KEYS})
    return out


def _digest(d: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()


def engine_config_sha256(config: Any) -> str:
    return _digest(engine_config_view(config))


FROZEN_ENGINE_CONFIG_SHA256 = _digest(_canon(FROZEN_ENGINE_CONFIG))


def engine_config_diff(config: Any) -> Dict[str, Any]:
    """{field: (frozen value, actual value)} for every engine-read field that differs from the frozen standalone configuration."""
    now, frozen = engine_config_view(config), _canon(FROZEN_ENGINE_CONFIG)
    return {k: (frozen.get(k), now.get(k)) for k in sorted(set(now) | set(frozen)) if json.dumps(now.get(k), sort_keys=True) != json.dumps(frozen.get(k), sort_keys=True)}
