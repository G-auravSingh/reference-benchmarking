# Production Colab Runbook

## 1. Open the generalized notebook

`notebooks/Darukaa_Adaptive_Biodiversity_Assessment_Colab.ipynb`

This is the only production assessment notebook in the package.

## 2. Pin the package

For a client run, replace `GIT_REF = "main"` with the exact verified commit SHA.

## 3. Select domain

Use `auto` unless the upstream handoff explicitly declares a domain. For Tata terrestrial site-selection outputs, use `terrestrial`. For a mixed project, use `mixed`.

## 4. Upload input

Preferred: the Site Selection handoff ZIP containing `tile_manifest.json` and its GeoJSON tiles.

Supported interoperability inputs are GeoJSON, KML/KMZ and single polygons.

## 5. First reference run

Leave `MANUAL_REFERENCE_HMI_THRESHOLD = None`. Run the pipeline and inspect the reference governance diagnostics.

## 6. Stage C, if required

Only if strict and empirical least-disturbed reference stages fail, review the reported HMI distribution and enter one explicit threshold in the configuration. The threshold does not override ecological eligibility or QA gates.

## 7. Inspect before delivery

Check every EMU for:

- domain routing;
- reference status and approval;
- metric coverage;
- score eligibility;
- limiting subdimension/metric;
- pressure separation;
- uncertainty and proxy labels.

Then inspect the project-level `emu_ecological_comparison.csv`, project pillar summary and HTML project report.


## Pinning a production code revision

Set `GIT_REF` to either a branch/tag name such as `main` or a complete 40-character commit SHA. The bootstrap cell checks out the SHA detached and verifies that `git rev-parse HEAD` matches exactly. Do not use `git clone --branch <SHA>`: `--branch` expects a branch or tag name and causes “Remote branch not found” for a raw commit hash. Record the printed `ACTUAL_GIT_SHA` alongside the output manifest for reproducibility.

## Retired metric runtime contract

The 63-row metric contract matrix is an audit/crosswalk, not an instruction to calculate all rows. Only IDs in `darukaa_adaptive.registry.INDICATORS` are active in v1.1.0. Retired IDs such as `natural_landcover_fraction`, `terrestrial_ndvi`, and `red_reflectance_turbidity_proxy` are historical records, not runnable metrics. The pipeline rejects an unexpected unregistered output before reference benchmarking, scoring or reporting. If this guard fails, do not bypass it; repair the calculator/registry contract and rerun.
