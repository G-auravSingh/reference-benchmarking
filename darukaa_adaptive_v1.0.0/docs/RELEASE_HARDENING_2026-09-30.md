# v1.0.0 Release Hardening — 2026-09-30

This replacement package is aligned to the current `main` v1.0.0 package API and includes a client-run hardening pass.

## Changes

1. Fixed the aquatic profile seasonal monitoring month list by removing the duplicated August. The Year-0 baseline remains 2025-08-01 through 2026-08-31 inclusive.
2. Rebuilt the Nandoshi Lake Colab notebook from the full workflow and migrated it to the current `AdaptivePipeline` API.
3. The notebook now installs only `darukaa_adaptive_v1.0.0`, explicitly verifies package version/path, records the Git SHA, validates the profile before expensive Earth Engine work, and avoids stale imports.
4. Replaced obsolete `summarize_composite()` usage with the current pipeline-generated benchmark, metric-concern, pillar, and overall scorecards.
5. Updated monthly water output handling from the obsolete `primary_images` field to the current `images_used` field.
6. The notebook retains the exploratory maps, monthly water series, dynamic-water mask, persistence, proxy inspection, riparian trend, baseline/monitoring comparison, readiness, report, manifest, and ZIP workflow.

## Scientific interpretation

Automatic reference populations remain benchmark candidates. They must not be described as pristine controls without ecological validation. Proxy indicators remain explicitly labelled as proxies and are not converted into calibrated water-quality measurements by the pipeline.

## Run gate

The live Earth Engine assessment should only proceed after the notebook prints a valid package version/path, successful profile validation, successful EE initialization, and the intended Git SHA is recorded.
