# v1.1.0 Production Release Checklist

## Package freeze

- [ ] Replace the complete `darukaa_adaptive_v1.1.0` folder from the release archive.
- [ ] Run `pytest -q`.
- [ ] Run `python -m compileall -q darukaa_adaptive`.
- [ ] Validate notebook JSON and Python code-cell syntax.
- [ ] Confirm package/profile version `1.1.0`.
- [ ] Generate and record the final ZIP SHA-256.

## GitHub / provenance

- [ ] Commit the complete package replacement.
- [ ] Record the resulting Git commit SHA.
- [ ] Pin that SHA in client Colab runs.

## Colab preflight

- [ ] Start from a clean runtime.
- [ ] Confirm the package is imported from the intended release checkout.
- [ ] Confirm Earth Engine authentication/project.
- [ ] Confirm Dynamic World, Sentinel-2 and TNC HM v3 datasets resolve.
- [ ] Confirm RESOLVE Ecoregions resolves as a FeatureCollection.
- [ ] Confirm profile validation returns no errors.

## Input/EMU QA

- [ ] Use the standardized Site Selection handoff where available.
- [ ] Confirm project ID/name and EMU count.
- [ ] Confirm every EMU has a unique ID and valid geometry.
- [ ] Confirm multipart EMUs remain intact.
- [ ] Confirm domain routing for every EMU.
- [ ] Confirm project and EMU areas.

## Reference QA

- [ ] Confirm strict contemporary reference stage.
- [ ] Confirm empirical least-disturbed stage where strict fails.
- [ ] If Stage C is needed, record the explicit manual HMI threshold and reason.
- [ ] Confirm ecological eligibility precedes HMI ordering.
- [ ] Confirm population size/area/pixel gates.
- [ ] Confirm temporal/spatial QA.
- [ ] Confirm approval is QA-gated.
- [ ] Confirm execution errors are distinguished from valid reference rejection.
- [ ] Confirm reference distribution diagnostics and uncertainty.

## Scoring QA

- [ ] Confirm metric scoring roles.
- [ ] Confirm statistical benchmark diagnostics are retained.
- [ ] Confirm 0–100 reference attainment is the aggregation scale.
- [ ] Confirm geometric mean is used only within complementary metric groups.
- [ ] Confirm pillar headline is the limiting subdimension.
- [ ] Confirm P1/P2/P3 overall condition uses geometric mean when coverage gates pass.
- [ ] Confirm P4 pressure remains separate.
- [ ] Confirm missing evidence is not converted to zero or 100.
- [ ] Confirm limiting pillar → subdimension → metric traceability.

## Project aggregation QA

- [ ] Confirm area-weighted project metric summaries.
- [ ] Confirm area-weighted project pillar summaries.
- [ ] Confirm EMU coverage statistics.
- [ ] Confirm limiting EMU.
- [ ] Confirm `emu_ecological_comparison.csv` is populated when scored EMU evidence exists.
- [ ] Confirm project condition and pressure scorecards.
- [ ] Confirm project HTML report.

## Final EMU output bundle

- [ ] `metric_scorecard.csv`
- [ ] `metric_qa_scorecard.csv`
- [ ] `reference_governance.csv`
- [ ] `benchmark_scorecard.csv`
- [ ] `metric_concern_scorecard.csv`
- [ ] `pillar_scorecard.csv`
- [ ] `overall_scorecard.json`
- [ ] `readiness.json`
- [ ] `assessment_manifest.json`
- [ ] `water_periods.csv` where aquatic processing applies
- [ ] `landcover_composition.csv` where available
- [ ] `external_evidence.csv`
- [ ] `indicator_registry.csv`
- [ ] `Year0_Biodiversity_Baseline_Report.html`
- [ ] `README_OUTPUTS.md`

## Project output bundle

- [ ] `project_assessment_manifest.json`
- [ ] `project_overall_scorecard.json`
- [ ] `project_metric_raw_aggregation.csv`
- [ ] `project_metric_score_aggregation.csv`
- [ ] `project_pillar_aggregation.csv`
- [ ] `emu_ecological_comparison.csv`
- [ ] `Project_Biodiversity_Baseline_Report.html`

Retain the exact input handoff/archive, output bundle, configuration and Git commit together.
