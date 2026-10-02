"""
engine_identity.py -- which engine, and which engine-relevant configuration, produced a result (v0.2.9 Phase 5)
==============================================================================================================

The v0.2.8 benchmarking engine is FROZEN (tag v0.2.8-contract-frozen). The general pipeline (Phase 5) must call it without changing it, and every output must
be able to PROVE that. Two fingerprints, both pure functions of what is on disk / in the configuration:

  * `engine_closure_sha256()` SHA-256 over the relative path and bytes of the ENGINE CLOSURE: every module that DETERMINES a result (site value, reference, applicability,
                             benchmark, score, status) when `assess.assess_zone` / `assess.load_zone` run. It is the explicit import closure of `assess.py` (AST, including
                             function-level imports) minus (a) modules that only RECORD or RENDER (EXECUTED_NON_RESULT_FILES) and (b) pipeline-layer modules added after the freeze.
                             Compared with FROZEN_ENGINE_CLOSURE_SHA256, computed from git at the frozen tag. A pipeline layer can change; these files cannot, without this changing.
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

# The executable ENGINE CLOSURE (19 files). Derived from the explicit import closure of assess.py; each file is byte-identical to v0.2.8-contract-frozen.
# `scoring.py` is in it because benchmarking.py computes the engine score with scoring.normalize; `reference.py` because assess.py builds every Dynamic World stratum
# and HMI threshold through ReferenceSelector; `pipeline.py` because assess.load_zone loads a tile through it. reference_builders.py is NOT in it: assess never imports it.
ENGINE_CLOSURE_FILES = ('__init__.py', 'assess.py', 'benchmarking.py', 'config.py', 'constructs.py', 'contracts.py', 'ecoregion.py', 'estimators.py', 'indicator_contract.py', 'indicators/__init__.py', 'pipeline.py', 'reference.py', 'reference_builders_ee.py', 'registry.py', 'scoring.py', 'site_loader.py', 'statistics.py', 'support.py', 'tiling.py')

# Executed when the engine runs, but they only RECORD or RENDER: no site value, reference, applicability, benchmark, score or status depends on them. They may differ
# from the frozen tag (provenance.py and html_report.py do, in Phase 5); a test pins exactly which.
EXECUTED_NON_RESULT_FILES = ("provenance.py", "report.py", "html_report.py", "son_score.py")

# computed from git at v0.2.8-contract-frozen (commit 3d01100), not from the working tree
FROZEN_ENGINE_CLOSURE_SHA256 = "56b57ebe4d62fb804c966c504c3f8776e62954f378fdf8f27b8757f4ff4c6ed8"
# per-file SHA-256 at the frozen tag (so a mismatch can be located, not just detected)
FROZEN_ENGINE_CLOSURE_FILE_SHA256 = {'__init__.py': '636d9ceef64c6625d25adda5895b7060417428edf698878adf6ff0d7e7c1eb6a', 'assess.py': 'b644c153d40abf884a46fb0444d00bc975d4145133ddf1ca33b0808161f0cba3', 'benchmarking.py': '33a8ae57bf3a0c16054ca874bccb9f2dd8c067ad3203bd065abd6aff9dfec6dc', 'config.py': 'cacd6d747d0bbb7f7e19d83c8abe1f691a533ca57ed58e9127f3185861d89242', 'constructs.py': '99b9a42a7dfcf2849f5d2afa0863384e54a4b01fe6127bdbce88b482b5a79ca1', 'contracts.py': 'f0d7e651a118d1d1789a744a3ebacf6c11b24edf76f192b56be604d85c6e501b', 'ecoregion.py': '3f9023794363d2433d2413621a05346f8796ec5fa6a536e4e90328d2dee0712a', 'estimators.py': '0f0597102b3eeffd2c4872ea965f6faec509ef1ba934d7f9a47b57daf9a097ef', 'indicator_contract.py': '3aa1e1106f645055ace24fa6dd416eba4d08facb82eaf87d1026d24d349b4e1d', 'indicators/__init__.py': '4ff8f5538361357bd62ad9ef358b01229b7a6e6b27da68afe77ca551a8acd7bc', 'pipeline.py': 'd749bf3e6807a71ed355f8395a16b9e3e67e9f5ba74b1e0e3d5ed3e0b81bde8b', 'reference.py': 'b22e4c874ee8a33648656402d9a4d1453d5521e062c5f219fef208b8e0726a54', 'reference_builders_ee.py': '59ec64192318a0ab37ee3a5a7e41683b14312ffd2dcce2250938d8babb22947c', 'registry.py': '8e2d6bab3f6df1a569cdcbbcf66a217a1ff533e8f367afec37692b44eb5b9bd3', 'scoring.py': '3637a39f6b360678a2f158fe3cd1b5142f19606a17c77c855422cd273c645bb3', 'site_loader.py': 'af79768308b76ca72b3acb522c507063523324e452b24a3c860dfa18f1d032c3', 'statistics.py': '701acc8ee81910e8dc8685e757e79ca9ffa93e28ac990a746744e42b7e2da244', 'support.py': '6e4a5e24549fa90fe46d86f43128767b527c55e04b8181e798f4aca317ebe425', 'tiling.py': '05b74323056c472c9996118ea3d12cda5b74acc6b3dcdbeabdd37d41b7e30684'}

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


def engine_closure_file_sha256(pkg_dir: str = PKG_DIR) -> Dict[str, str]:
    out = {}
    for f in sorted(ENGINE_CLOSURE_FILES):
        with open(os.path.join(pkg_dir, f), "rb") as fh:
            out[f] = hashlib.sha256(fh.read()).hexdigest()
    return out


def engine_closure_sha256(pkg_dir: str = PKG_DIR) -> str:
    h = hashlib.sha256()
    for f in sorted(ENGINE_CLOSURE_FILES):
        with open(os.path.join(pkg_dir, f), "rb") as fh:
            h.update(f.encode()); h.update(fh.read())
    return h.hexdigest()


def engine_closure_differences(pkg_dir: str = PKG_DIR) -> Dict[str, str]:
    """{file: 'differs'|'missing'} for every closure file that is not byte-identical to the frozen tag (empty = identical)."""
    now, out = engine_closure_file_sha256(pkg_dir), {}
    for f, frozen in FROZEN_ENGINE_CLOSURE_FILE_SHA256.items():
        if f not in now:
            out[f] = "missing"
        elif now[f] != frozen:
            out[f] = "differs"
    return out


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
