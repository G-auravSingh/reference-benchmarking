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
