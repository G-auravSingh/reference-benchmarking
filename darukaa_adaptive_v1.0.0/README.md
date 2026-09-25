# Darukaa Adaptive Biodiversity Assessment Framework v1.0.0

## Purpose

This package adds a generalized, ecosystem-profiled assessment layer while preserving the supplied `darukaa_reference_v0.1.0` package unchanged.

The first implementation is the **aquatic lake profile**, designed to run from Google Colab with Google Earth Engine (GEE). Nandoshi Lake is used as the first project implementation, but the code is not hard-coded to Nandoshi coordinates, masks, or dates.

## Design principle

A fixed master KML is the assessment boundary. It is not silently reused as the same ecological mask for every metric.

The pipeline distinguishes:

- **Master boundary:** the supplied KML; used for project-area accounting and boundary-level metrics.
- **Dynamic water domain:** derived from Earth observation for each period; no manually drawn water polygon is required.
- **Exposed/littoral domain:** master boundary minus the dynamic water surface when needed; it is *not* automatically treated as terrestrial habitat.
- **Fixed riparian domain:** a standardized external buffer around the master boundary (default 100 m).
- **Context domain:** a standardized broader buffer (default 5 km).

## Primary current EO inputs

The lake profile uses Dynamic World V1 for the primary dynamic water signal and Sentinel-2 SR Harmonized for optical metrics. Sentinel-1 VV can be used as an automatic fallback when optical observations are insufficient. Google Earth Engine's current Data Catalog lists Dynamic World as a 10 m near-real-time land-use/land-cover product, Sentinel-2 SR Harmonized from 2017 to present, and Sentinel-1 GRD from 2014 to present. JRC Global Surface Water v1.4 is retained only as a historical context product because its mapped water history ends in 2021.

## Metric philosophy

The lake profile reports direct, interpretable quantities and clearly marks proxy metrics. A proxy metric without a reviewed ecological threshold is **not automatically converted into a five-class concern score**. Composite aquatic State-of-Nature scoring is therefore disabled by default.

The current lake suite includes:

- dynamic water extent,
- water-class persistence/occurrence,
- NDCI trophic/chlorophyll proxy,
- red-reflectance turbidity proxy,
- FAI-based surface bloom-proxy frequency,
- standardized 100 m riparian disturbance fraction, and
- multi-year riparian NDVI trend using a robust Sen/Theil slope with Kendall tau p-value.

The purpose of the initial release is to create a repeatable measurement framework. Field measurements, species observations, eDNA results, or expert-reviewed thresholds can be attached later without changing the spatial architecture.

## Reproducibility

The supplied input KML is hashed and recorded in `assessment_manifest.json`. For a client-grade release, pin the Git repository to an exact commit rather than `main`.

## Running the Colab notebook

Open `notebooks/Nandoshi_Lake_Aquatic_Assessment_Colab.ipynb` in Google Colab. The notebook walks through repository installation, GEE authentication, KML upload, geometry QA, automatic water-domain generation, metrics, readiness checks, output generation, and baseline comparison.

## Legacy package

The exact supplied reference package is preserved under `legacy/darukaa_reference_v0.1.0/`. It is not imported into the lake profile and should remain frozen when reproducing older terrestrial reports.

## Package structure

```text
darukaa_adaptive/
  config.py
  site.py
  water.py
  metrics.py
  benchmark.py
  scoring.py
  trajectory.py
  readiness.py
  report.py
  pipeline.py
profiles/
  aquatic_lake.yaml
  terrestrial_legacy.yaml
notebooks/
  Nandoshi_Lake_Aquatic_Assessment_Colab.ipynb
legacy/
  darukaa_reference_v0.1.0/
docs/
  REFERENCE_PIPELINE_AUDIT.md
  METHOD_NOTES.md
tests/
```

## Important methodological note

The lake profile is intentionally more conservative than the older report workflow. It does not interpret a raw EO proxy as a validated ecological state variable merely because a five-class threshold can be written around it. Thresholds can be added through configuration after scientific review and calibration.
