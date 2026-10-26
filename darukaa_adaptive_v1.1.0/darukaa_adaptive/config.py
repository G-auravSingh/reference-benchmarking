"""Run configuration for the Darukaa Adaptive v1.1.0 assessment.

Every scientific parameter lives here with its source decision, so a run's
configuration file records exactly how it was produced. Parameters marked
"set from probe evidence" are first-draft values to be confirmed (D-23-14).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .reference_pool import PoolConfig

VERSION = "1.1.0"


@dataclass
class ScoringConfig:
    role_mode: str = "recommended"            # "all_scoreable" in Colab (amendment A2)
    metric_overrides: Dict[str, str] = field(default_factory=dict)
    include_proposed: bool = False
    min_metrics_per_pillar: int = 3            # unchanged from v1.1.0 gate
    min_components_per_pillar: int = 3         # unchanged from v1.1.0 gate
    n_bootstrap: int = 200
    bootstrap_seed: int = 20261023
    confidence_max_interval_width: float = 20.0
    confidence_min_reference_blocks: int = 10
    min_stratum_weight_share: float = 0.5      # share of a unit's metric weight that must have a usable reference


@dataclass
class AssessmentConfig:
    window_start: str = "2025-08-01"           # decision 9 (16 Oct)
    window_end: str = "2026-08-31"             # inclusive
    baseline_year: int = 2020                  # D-23-11, Guidance p.10
    site_cluster_distance_m: float = 1000.0    # D-23-8
    min_support_px: float = 4.0                # decision 5
    natural_mask_min_probability: float = 0.5  # metric catalogue v1, natural mask
    gee_project: Optional[str] = None
    output_dir: str = "outputs"
    raster_paths: Dict[str, str] = field(default_factory=dict)
    options: Dict[str, Any] = field(default_factory=lambda: {
        "tree_cover_threshold_pct": 10,        # decision 3 (FAO forest definition)
        "hansen_last_year": 2025,              # Hansen v1.13
        "tree_loss_years": 5,                  # decision 3
        "min_forest_baseline_ha": 1.0,         # decision 3
        "low_forest_baseline_ha": 5.0,         # low_baseline_flag threshold (implementation detail, logged)
        "core_edge_depth_m": 30.0,             # metric catalogue v1
        "fire_first_year": 2016, "fire_last_year": 2025,
        "s2_cloud_prob_max": 50.0, "s2_scene_cloud_max": 60.0,
        "iucn_category_field": "category",
        "iucn_category_fields": {"mammals": "category", "birds": "RedList__5"},   # probe 27 Oct: birds RedList__5 = CR/DD/EN/LC/NT/VU
        "flii_scale_factor": 0.001,            # EE probe 24 Oct: FLII stored x1000
        "peak_window_buffer_m": 1000.0,        # D-25-2
        "fire_min_valid_months": 6,            # D-26-2
    })
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    pool: PoolConfig = field(default_factory=PoolConfig)

    def window_exclusive(self) -> tuple[str, str]:
        s = date.fromisoformat(str(self.window_start))
        e = date.fromisoformat(str(self.window_end))
        if e < s:
            raise ValueError("window_end must be on or after window_start")
        return s.isoformat(), (e + timedelta(days=1)).isoformat()

    def validate(self) -> List[str]:
        errors = []
        try:
            self.window_exclusive()
        except Exception as exc:  # noqa: BLE001 - reported as a validation error
            errors.append(f"invalid assessment window: {exc}")
        if self.scoring.role_mode not in {"recommended", "all_scoreable"}:
            errors.append("scoring.role_mode must be 'recommended' or 'all_scoreable'")
        for k, v in self.scoring.metric_overrides.items():
            if v not in {"scored", "contextual"}:
                errors.append(f"metric override for {k} must be 'scored' or 'contextual'")
        if self.min_support_px < 1:
            errors.append("min_support_px must be >= 1")
        if not 0 < self.natural_mask_min_probability < 1:
            errors.append("natural_mask_min_probability must be in (0,1)")
        if self.pool.exclusion_m < 1000:
            errors.append("pool.exclusion_m must be >= 1000 m (D-23-14)")
        return errors

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["version"] = VERSION
        return d

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "AssessmentConfig":
        raw = dict(raw or {})
        raw.pop("version", None)
        scoring = ScoringConfig(**(raw.pop("scoring", None) or {}))
        pool = PoolConfig(**(raw.pop("pool", None) or {}))
        options = cls().options
        options.update(raw.pop("options", None) or {})
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(raw) - known)
        if unknown:
            raise ValueError(f"Unknown configuration keys: {unknown}")
        for key in ("window_start", "window_end"):
            if hasattr(raw.get(key), "isoformat"):
                raw[key] = raw[key].isoformat()
        return cls(scoring=scoring, pool=pool, options=options, **raw)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "AssessmentConfig":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(yaml.safe_load(f) or {})
