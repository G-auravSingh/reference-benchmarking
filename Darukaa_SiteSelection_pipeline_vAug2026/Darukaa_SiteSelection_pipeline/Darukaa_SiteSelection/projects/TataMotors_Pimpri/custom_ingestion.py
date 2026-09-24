"""
Entry point the pipeline orchestrator (run_pipeline.py) looks for when a
project's source KML doesn't fit the standard placemark-classification
model used by pipeline/01_ingestion/kml_ingest.py.

TataMotors_Pimpri's source KML has 20 real thematic layers (buildings,
paths, water, and ten named ecological zones) rather than a small set of
named anchor/exclusion/candidate placemarks — see preprocess_eco_zones.py
for the actual logic. This file only adapts that logic's real entry point
to the run_ingestion(project_dir) signature every project's stage 01 is
expected to expose.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from preprocess_eco_zones import run_tm_ingestion as run_ingestion  # noqa: F401
