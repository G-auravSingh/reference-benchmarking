"""Configuration models for the generalized Darukaa adaptive assessment framework."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
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
    end_year: int = 2026
    baseline_start_date: str = "2025-08-01"
    baseline_end_date: str = "2026-08-31"  # inclusive; GEE conversion is exclusive internally
    baseline_label: str = "Year-0 (Aug 2025-Aug 2026)"
    monitoring_months: List[int] = field(default_factory=lambda: list(range(1, 13)))
    min_years_for_trend: int = 5
    max_cloud_pct: float = 60.0

    @staticmethod
    def _coerce_date(value) -> date:
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value))

    def baseline_dates(self) -> tuple[str, str]:
        """Return ISO start and GEE-compatible exclusive end dates."""
        start = self._coerce_date(self.baseline_start_date)
        end_inclusive = self._coerce_date(self.baseline_end_date)
        if end_inclusive < start:
            raise ValueError("baseline_end_date must be on or after baseline_start_date")
        return start.isoformat(), (end_inclusive + timedelta(days=1)).isoformat()

    def baseline_inclusive_window(self) -> tuple[str, str]:
        return self._coerce_date(self.baseline_start_date).isoformat(), self._coerce_date(self.baseline_end_date).isoformat()

    def trend_dates(self) -> tuple[str, str]:
        if self.end_year < self.start_year:
            raise ValueError("end_year must be >= start_year")
        return f"{self.start_year}-01-01", f"{self.end_year + 1}-01-01"

    def shifted_baseline(self, years: int) -> tuple[str, str]:
        """Shift the baseline window by whole calendar years for future monitoring."""
        start = self._coerce_date(self.baseline_start_date)
        end = self._coerce_date(self.baseline_end_date)
        try:
            s = start.replace(year=start.year + years)
            e = end.replace(year=end.year + years)
        except ValueError as exc:
            raise ValueError("Baseline date cannot be shifted by the requested number of years") from exc
        return s.isoformat(), e.isoformat()


@dataclass
class WaterConfig:
    primary_dataset: str = "GOOGLE/DYNAMICWORLD/V1"
    primary_probability_threshold: float = 0.50
    fallback_enabled: bool = True
    fallback_dataset: str = "COPERNICUS/S1_GRD"
    fallback_vv_threshold_db: float = -17.0
    fallback_majority_fraction: float = 0.50
    min_primary_images: int = 3
    water_presence_area_fraction_threshold: float = 0.05
    fai_bloom_threshold: float = 0.005


@dataclass
class SpatialConfig:
    riparian_buffer_m: float = 100.0
    context_buffer_km: float = 5.0
    working_crs: str = "EPSG:4326"


@dataclass
class ReferenceConfig:
    enabled: bool = True
    tier1_enabled: bool = True
    tier2_enabled: bool = True
    tier1_approved_for_scoring: bool = False
    tier2_approved_for_scoring: bool = False
    tier1_reference_kml: Optional[str] = None
    tier1_reference_csv: Optional[str] = None
    tier2_min_water_occurrence: float = 0.50
    tier2_min_area_ha: float = 1.0


@dataclass
class ScoringConfig:
    enabled: bool = True
    composite_son_enabled: bool = False
    reference_relative_enabled: bool = False
    min_valid_metrics_per_pillar: int = 1
    min_valid_pillars: int = 4
    total_pillars: int = 4
    require_complete_pillars: bool = True
    thresholds_by_metric: Dict[str, Dict[str, float]] = field(default_factory=dict)
    reference_ratio_thresholds_by_metric: Dict[str, Dict[str, float]] = field(default_factory=dict)


@dataclass
class ProfileConfig:
    name: str = "aquatic_lake"
    version: str = "1.1.0"
    allow_terrestrial_metrics: bool = False
    notes: str = ""


@dataclass
class AssessmentConfig:
    gee: GEEConfig = field(default_factory=GEEConfig)
    temporal: TemporalConfig = field(default_factory=TemporalConfig)
    water: WaterConfig = field(default_factory=WaterConfig)
    spatial: SpatialConfig = field(default_factory=SpatialConfig)
    reference: ReferenceConfig = field(default_factory=ReferenceConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    profile: ProfileConfig = field(default_factory=ProfileConfig)
    output_dir: str = "outputs"
    site_boundary_type: str = "assessment_boundary"

    @classmethod
    def from_yaml(cls, path: str | Path) -> "AssessmentConfig":
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        # Backward compatible with the earlier profile typo/casing used in v1.0.0.
        gee_raw = raw.get("gee")
        if gee_raw is None:
            gee_raw = raw.get("gEE", {})

        return cls(
            gee=GEEConfig(**gee_raw),
            temporal=TemporalConfig(**raw.get("temporal", {})),
            water=WaterConfig(**raw.get("water", {})),
            spatial=SpatialConfig(**raw.get("spatial", {})),
            reference=ReferenceConfig(**raw.get("reference", {})),
            scoring=ScoringConfig(**raw.get("scoring", {})),
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
        try:
            self.temporal.baseline_dates()
        except Exception as exc:
            errors.append(f"invalid baseline dates: {exc}")
        if not 0 < self.water.primary_probability_threshold <= 1:
            errors.append("water.primary_probability_threshold must be in (0,1]")
        if not 0 < self.water.fallback_majority_fraction <= 1:
            errors.append("water.fallback_majority_fraction must be in (0,1]")
        if self.water.min_primary_images < 1:
            errors.append("water.min_primary_images must be >= 1")
        if self.spatial.riparian_buffer_m <= 0:
            errors.append("spatial.riparian_buffer_m must be > 0")
        if self.temporal.min_years_for_trend < 5:
            errors.append("temporal.min_years_for_trend should be >= 5 for long-term trend screening")
        if sorted(set(self.temporal.monitoring_months)) != sorted(self.temporal.monitoring_months):
            errors.append("temporal.monitoring_months must not contain duplicate months")
        if any(m < 1 or m > 12 for m in self.temporal.monitoring_months):
            errors.append("temporal.monitoring_months values must be between 1 and 12")
        if self.scoring.min_valid_metrics_per_pillar < 1:
            errors.append("scoring.min_valid_metrics_per_pillar must be >= 1")
        if self.scoring.min_valid_pillars < 1:
            errors.append("scoring.min_valid_pillars must be >= 1")
        if self.scoring.total_pillars < self.scoring.min_valid_pillars:
            errors.append("scoring.total_pillars must be >= min_valid_pillars")

        for name, thresholds in self.scoring.thresholds_by_metric.items():
            if set(thresholds) != {"t1", "t2", "t3", "t4"}:
                errors.append(f"scoring threshold set for {name} must contain t1..t4 only")
            else:
                vals = [float(thresholds[k]) for k in ("t1", "t2", "t3", "t4")]
                if not vals[0] < vals[1] < vals[2] < vals[3]:
                    errors.append(f"scoring threshold set for {name} must satisfy t1<t2<t3<t4")

        for name, thresholds in self.scoring.reference_ratio_thresholds_by_metric.items():
            if set(thresholds) != {"r1", "r2", "r3", "r4"}:
                errors.append(f"reference ratio thresholds for {name} must contain r1..r4 only")
            else:
                vals = [float(thresholds[k]) for k in ("r1", "r2", "r3", "r4")]
                if not vals[0] < vals[1] < vals[2] < vals[3]:
                    errors.append(f"reference ratio thresholds for {name} must satisfy r1<r2<r3<r4")

        return errors
