"""Configuration models for the generalized Darukaa adaptive assessment pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class GEEConfig:
    project_id: Optional[str] = None
    service_account: Optional[str] = None
    key_path: Optional[str] = None


@dataclass
class TemporalConfig:
    start_year: int = 2018
    end_year: int = 2025
    baseline_start_year: int = 2018
    baseline_end_year: int = 2022
    monitoring_months: List[int] = field(default_factory=lambda: list(range(1, 13)))
    min_years_for_trend: int = 5
    max_cloud_pct: float = 60.0


@dataclass
class WaterConfig:
    primary_dataset: str = "GOOGLE/DYNAMICWORLD/V1"
    primary_probability_threshold: float = 0.50
    fallback_enabled: bool = True
    fallback_dataset: str = "COPERNICUS/S1_GRD"
    fallback_vv_threshold_db: float = -17.0
    min_primary_images: int = 3
    water_presence_area_fraction_threshold: float = 0.05
    fai_bloom_threshold: float = 0.005


@dataclass
class SpatialConfig:
    riparian_buffer_m: float = 100.0
    context_buffer_km: float = 5.0
    reference_buffer_km: float = 5.0
    working_crs: str = "EPSG:4326"


@dataclass
class ProfileConfig:
    name: str = "aquatic_lake"
    version: str = "1.0.0"
    composite_son_enabled: bool = False
    allow_terrestrial_metrics: bool = False
    notes: str = ""


@dataclass
class AssessmentConfig:
    gee: GEEConfig = field(default_factory=GEEConfig)
    temporal: TemporalConfig = field(default_factory=TemporalConfig)
    water: WaterConfig = field(default_factory=WaterConfig)
    spatial: SpatialConfig = field(default_factory=SpatialConfig)
    profile: ProfileConfig = field(default_factory=ProfileConfig)
    output_dir: str = "outputs"
    site_boundary_type: str = "assessment_boundary"

    @classmethod
    def from_yaml(cls, path: str | Path) -> "AssessmentConfig":
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        return cls(
            gee=GEEConfig(**raw.get("gee", {})),
            temporal=TemporalConfig(**raw.get("temporal", {})),
            water=WaterConfig(**raw.get("water", {})),
            spatial=SpatialConfig(**raw.get("spatial", {})),
            profile=ProfileConfig(**raw.get("profile", {})),
            output_dir=raw.get("output_dir", "outputs"),
            site_boundary_type=raw.get("site_boundary_type", "assessment_boundary"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def validate(self) -> List[str]:
        errors: List[str] = []
        if self.temporal.start_year > self.temporal.end_year:
            errors.append("temporal.start_year must be <= temporal.end_year")
        if self.temporal.baseline_start_year > self.temporal.baseline_end_year:
            errors.append("baseline_start_year must be <= baseline_end_year")
        if not 0 < self.water.primary_probability_threshold <= 1:
            errors.append("water.primary_probability_threshold must be in (0,1]")
        if self.spatial.riparian_buffer_m <= 0:
            errors.append("spatial.riparian_buffer_m must be > 0")
        if self.temporal.min_years_for_trend < 5:
            errors.append("min_years_for_trend should be >= 5 for long-term trend screening")
        return errors
