"""Configuration for the generalized Darukaa biodiversity baseline engine."""
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
    baseline_end_date: str = "2026-08-31"
    baseline_label: str = "Year-0 (Aug 2025-Aug 2026)"
    monitoring_months: List[int] = field(default_factory=lambda: list(range(1, 13)))
    min_years_for_trend: int = 5
    max_cloud_pct: float = 60.0

    @staticmethod
    def _coerce_date(value: Any) -> date:
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value))

    def baseline_dates(self) -> tuple[str, str]:
        start = self._coerce_date(self.baseline_start_date)
        end = self._coerce_date(self.baseline_end_date)
        if end < start:
            raise ValueError("baseline_end_date must be on or after baseline_start_date")
        return start.isoformat(), (end + timedelta(days=1)).isoformat()

    def baseline_inclusive_window(self) -> tuple[str, str]:
        return self._coerce_date(self.baseline_start_date).isoformat(), self._coerce_date(self.baseline_end_date).isoformat()

    def trend_dates(self) -> tuple[str, str]:
        if self.end_year < self.start_year:
            raise ValueError("end_year must be >= start_year")
        return f"{self.start_year}-01-01", f"{self.end_year + 1}-01-01"


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
    littoral_band_m: float = 50.0
    context_buffer_km: float = 5.0
    reference_exclusion_buffer_m: float = 1000.0
    working_crs: str = "EPSG:4326"


@dataclass
class ReferenceConfig:
    enabled: bool = True
    strategy: str = "auto_ecoregion_stratum"
    ecoregion_dataset: str = "RESOLVE/ECOREGIONS/2017"
    human_modification_dataset: str = "CSP/HM/GlobalHumanModification"
    human_modification_threshold: float = 0.05
    terrestrial_search_radius_km: float = 75.0
    aquatic_search_radius_km: float = 150.0
    aquatic_area_ratio_min: float = 0.5
    aquatic_area_ratio_max: float = 2.5
    aquatic_max_candidates: int = 12
    minimum_reference_n: int = 6
    maximum_reference_relative_se: float = 0.25
    bootstrap_iterations: int = 500
    auto_approve: bool = True
    use_ecoregion_for_terrestrial: bool = True
    use_hydrolakes_for_aquatic: bool = True
    hydrolakes_asset: str = "projects/sat-io/open-datasets/HydroLakes/lake_poly_v10"
    allow_historical_reference: bool = False


@dataclass
class ScoringConfig:
    enabled: bool = True
    composite_son_enabled: bool = True
    concern_band_reference_point: float = 0.50
    logistic_ratio_scale: float = 0.6931471805599453  # ln(2); ratio 2 => ~0.667 intactness
    min_valid_metrics_per_pillar: int = 1
    min_valid_pillars: int = 4
    total_pillars: int = 4
    require_complete_pillars: bool = True
    condition_pillars: List[str] = field(default_factory=lambda: ["C1_extent", "C2_vegetation", "C3_fauna"])
    pressure_pillar: str = "C4_pressure"


@dataclass
class InputConfig:
    field_csv: Optional[str] = None
    acoustic_csv: Optional[str] = None
    edna_csv: Optional[str] = None
    edna_pdf: Optional[str] = None
    edna_html: Optional[str] = None
    krona_html: Optional[str] = None


@dataclass
class ProfileConfig:
    name: str = "mixed_lake"
    version: str = "1.2.0"
    mode: str = "mixed"
    aquatic_enabled: bool = True
    terrestrial_enabled: bool = True
    notes: str = "Generalized profile; modules activate from the configured assessment realm."


@dataclass
class AssessmentConfig:
    gee: GEEConfig = field(default_factory=GEEConfig)
    temporal: TemporalConfig = field(default_factory=TemporalConfig)
    water: WaterConfig = field(default_factory=WaterConfig)
    spatial: SpatialConfig = field(default_factory=SpatialConfig)
    reference: ReferenceConfig = field(default_factory=ReferenceConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    inputs: InputConfig = field(default_factory=InputConfig)
    profile: ProfileConfig = field(default_factory=ProfileConfig)
    output_dir: str = "outputs"
    site_boundary_type: str = "assessment_boundary"

    @classmethod
    def from_yaml(cls, path: str | Path) -> "AssessmentConfig":
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        gee_raw = raw.get("gee", raw.get("gEE", {})) or {}
        return cls(
            gee=GEEConfig(**gee_raw),
            temporal=TemporalConfig(**(raw.get("temporal", {}) or {})),
            water=WaterConfig(**(raw.get("water", {}) or {})),
            spatial=SpatialConfig(**(raw.get("spatial", {}) or {})),
            reference=ReferenceConfig(**(raw.get("reference", {}) or {})),
            scoring=ScoringConfig(**(raw.get("scoring", {}) or {})),
            inputs=InputConfig(**(raw.get("inputs", {}) or {})),
            profile=ProfileConfig(**(raw.get("profile", {}) or {})),
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
        if self.spatial.riparian_buffer_m <= 0 or self.spatial.littoral_band_m <= 0:
            errors.append("riparian and littoral widths must be > 0")
        if self.spatial.context_buffer_km <= 0:
            errors.append("spatial.context_buffer_km must be > 0")
        if self.reference.minimum_reference_n < 2:
            errors.append("reference.minimum_reference_n must be >= 2")
        if not 0 < self.reference.maximum_reference_relative_se:
            errors.append("reference.maximum_reference_relative_se must be > 0")
        if self.reference.bootstrap_iterations < 100:
            errors.append("reference.bootstrap_iterations must be >= 100")
        if not self.profile.aquatic_enabled and not self.profile.terrestrial_enabled:
            errors.append("at least one of profile.aquatic_enabled or profile.terrestrial_enabled must be true")
        if self.scoring.total_pillars != 4:
            errors.append("four core pillars are fixed: C1-C4")
        if self.scoring.min_valid_metrics_per_pillar < 1:
            errors.append("scoring.min_valid_metrics_per_pillar must be >= 1")
        return errors
