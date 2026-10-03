# v1.1.0 Release Checklist

## Before replacing the GitHub package folder

- [ ] Replace the entire `darukaa_adaptive_v1.1.0` folder from the supplied release archive.
- [ ] Do not mix individual files with older v1.0.x files.
- [ ] Run `pytest -q` locally.
- [ ] Run `python -m compileall -q darukaa_adaptive`.
- [ ] Validate the notebook JSON and Python code cells.
- [ ] Confirm the package version is `1.1.0`.
- [ ] Regenerate/verify `docs/ADAPTIVE_RELEASE_SHA256.txt` after the final source tree is frozen.

## GitHub Desktop

- [ ] Pull origin before committing.
- [ ] Review the complete Changes panel.
- [ ] Commit the complete replacement package as one release commit.
- [ ] Push to the intended branch/main according to repository workflow.
- [ ] Record the resulting Git commit SHA.

## Colab preflight

- [ ] Start from a clean runtime.
- [ ] Notebook clones the intended Git ref.
- [ ] Package import path is inside `darukaa_adaptive_v1.1.0`.
- [ ] Package version is `1.1.0`.
- [ ] TNC HM v3 resolves as an ImageCollection.
- [ ] RESOLVE Ecoregions resolves as a FeatureCollection.
- [ ] Dynamic World/Sentinel-1/Sentinel-2 resolve.
- [ ] Profile validation returns no errors.

## Site and temporal QA

- [ ] Upload the correct master KML/KMZ.
- [ ] Record the KML SHA-256.
- [ ] Confirm boundary area and map domains.
- [ ] Confirm Year-0 dates.
- [ ] Confirm historical trend window.
- [ ] Inspect baseline monthly water series.
- [ ] Confirm no invented future zero-water months.

## Reference QA

- [ ] Confirm reference search radius.
- [ ] Confirm assessed site is excluded.
- [ ] Confirm ecoregion stratum.
- [ ] Confirm hydrological similarity.
- [ ] Confirm HMI pressure screen.
- [ ] Confirm population size.
- [ ] Confirm temporal observation depth.
- [ ] Confirm automatic approval is QA-gated.
- [ ] Confirm reference diagnostics contain no execution error.
- [ ] Confirm reference central estimator and percentiles.
- [ ] Confirm `water_extent` is not assigned a false 100% reference.

## Scoring QA

- [ ] Inspect raw metrics separately from scores.
- [ ] Inspect benchmark/reference governance separately from scores.
- [ ] Confirm only approved references become score-eligible.
- [ ] Confirm C4 pressure remains separate.
- [ ] Confirm C3 fauna requirement is applied.
- [ ] Confirm unassessed pillars are not rendered as 100.
- [ ] Confirm proxy indicators remain correctly labelled.

## Final outputs

- [ ] `metric_scorecard.csv`
- [ ] `metric_qa_scorecard.csv`
- [ ] `reference_governance.csv`
- [ ] `benchmark_scorecard.csv`
- [ ] `metric_concern_scorecard.csv`
- [ ] `pillar_scorecard.csv`
- [ ] `overall_scorecard.json`
- [ ] `readiness.json`
- [ ] `assessment_manifest.json`
- [ ] `water_periods.csv`
- [ ] `water_monthly.csv`
- [ ] `landcover_composition.csv`
- [ ] `external_evidence.csv`
- [ ] `indicator_registry.csv`
- [ ] `legacy_metric_crosswalk.csv`
- [ ] `Year0_Biodiversity_Baseline_Report.html`
- [ ] `README_OUTPUTS.md`

Retain the complete output ZIP together with the master KML/KMZ and exact Git commit.
