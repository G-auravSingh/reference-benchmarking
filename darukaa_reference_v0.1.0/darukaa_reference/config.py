"""
Configuration
=============

Loads pipeline configuration from a YAML file specifying file paths,
GEE project ID, buffer radius, HMI threshold, and indicator toggles.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class Config:
    """Pipeline configuration."""

    # Google Earth Engine
    gee_project: str = ""
    gee_service_account: Optional[str] = None
    gee_key_path: Optional[str] = None

    # Local raster paths
    raster_paths: Dict[str, str] = field(default_factory=dict)
    # Expected keys: "globio4_msa", "seed_biocomplexity", "ecoregions", "ghm", etc.

    # Ecoregion shapefile or GEE asset
    ecoregion_source: str = "gee"  # "gee" or path to local shapefile
    ecoregion_gee_asset: str = "RESOLVE/ECOREGIONS/2017"

    # Tier 2 reference selection parameters
    reference_buffer_km: float = 100.0  # search radius for reference patches
    hmi_percentile_threshold: float = 5.0  # top N% least disturbed
    min_reference_pixels: int = 20  # minimum pixels for valid reference
    landcover_gee_asset: str = "COPERNICUS/Landcover/100m/Proba-V-C3/Global/2019"

    # Remote sensing parameters
    ndvi_year: int = 2024
    ndvi_cloud_threshold: float = 20.0  # max cloud cover %
    lst_year: int = 2024

    # Statistical parameters
    bootstrap_iterations: int = 10000
    permutation_iterations: int = 10000
    confidence_level: float = 0.95
    random_seed: int = 42

    # Output
    output_dir: str = "./output"
    output_format: str = "json"  # "json", "csv", or "both"

    # Indicator selection (empty = all registered)
    enabled_indicators: List[str] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: str) -> "Config":
        """Load configuration from a YAML file."""
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}

        # Flatten nested sections
        flat = {}
        for section in data.values() if isinstance(data, dict) else []:
            if isinstance(section, dict):
                flat.update(section)
            else:
                flat.update(data)
                break

        # If the YAML is already flat, use directly
        if not any(isinstance(v, dict) for v in data.values()):
            flat = data

        # Merge nested structure
        if "gee" in data and isinstance(data["gee"], dict):
            flat["gee_project"] = data["gee"].get("project", "")
            flat["gee_service_account"] = data["gee"].get("service_account")
            flat["gee_key_path"] = data["gee"].get("key_path")

        if "rasters" in data and isinstance(data["rasters"], dict):
            flat["raster_paths"] = data["rasters"]

        if "tier2" in data and isinstance(data["tier2"], dict):
            t2 = data["tier2"]
            flat["reference_buffer_km"] = t2.get("buffer_km", 100.0)
            flat["hmi_percentile_threshold"] = t2.get("hmi_percentile", 5.0)
            flat["min_reference_pixels"] = t2.get("min_pixels", 20)

        if "statistics" in data and isinstance(data["statistics"], dict):
            st = data["statistics"]
            flat["bootstrap_iterations"] = st.get("bootstrap_n", 10000)
            flat["permutation_iterations"] = st.get("permutation_n", 10000)
            flat["confidence_level"] = st.get("confidence", 0.95)
            flat["random_seed"] = st.get("seed", 42)

        if "output" in data and isinstance(data["output"], dict):
            flat["output_dir"] = data["output"].get("dir", "./output")
            flat["output_format"] = data["output"].get("format", "json")

        if "indicators" in data and isinstance(data["indicators"], list):
            flat["enabled_indicators"] = data["indicators"]

        # Build config, ignoring unknown keys
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in flat.items() if k in valid_fields}
        return cls(**filtered)

    @classmethod
    def default(cls) -> "Config":
        """Return default configuration."""
        return cls()
