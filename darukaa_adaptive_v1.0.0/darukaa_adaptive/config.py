from __future__ import annotations
from dataclasses import dataclass, field
from typing import List

@dataclass
class LakeConfig:
    gee_project: str = ""
    assessment_year: int = 2025
    baseline_start_year: int = 2019
    baseline_end_year: int = 2025
    s2_cloud_pct: float = 35.0
    dw_water_probability: float = 0.50
    dw_water_reference_probability: float = 0.70
    dynamic_water_min_observations: int = 6
    riparian_buffer_m: float = 100.0
    reference_buffer_km: float = 25.0
    reference_hmi_ceiling: float = 0.10
    reference_min_pixels: int = 20
    reference_min_water_occurrence: float = 0.50
    include_species_context: bool = True
    include_shdi_in_son: bool = False
    output_dir: str = "./output"
    indicators: List[str] = field(default_factory=lambda: [
        "water_extent", "water_persistence", "tspi", "sabf", "wcpi", "wsdi",
        "riparian_ndvi_trend", "rci", "shdi", "threatened_richness", "endemic_richness",
        "ceri", "star_t"
    ])
