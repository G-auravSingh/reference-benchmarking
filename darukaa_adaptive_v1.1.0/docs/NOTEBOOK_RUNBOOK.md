# Nandoshi Lake Colab Runbook — v1.1.0

## 1. Open the notebook

Open:

`notebooks/Nandoshi_Lake_Aquatic_Assessment_Colab.ipynb`

## 2. Run from a clean Colab runtime

Use a fresh runtime where possible. The notebook also deletes any existing `/content/reference-benchmarking` checkout before cloning, so stale package imports are not reused.

## 3. Configuration

The notebook defaults to:

- repository: `G-auravSingh/reference-benchmarking`
- branch/ref: `main`
- package: `darukaa_adaptive_v1.1.0`
- profile: `profiles/aquatic_lake.yaml`
- Earth Engine project: `darukaa-earth-product`

For a client-frozen run, replace `GIT_REF = "main"` with the exact verified Git commit SHA printed by the notebook.

## 4. Mandatory preflight

Run the cells in order. The notebook verifies:

- package version/path;
- reference-condition modules;
- Dynamic World;
- Sentinel-1;
- Sentinel-2;
- TNC HM v3 90 m;
- RESOLVE Ecoregions 2017;
- JRC historical context;
- profile configuration.

A dataset/API error at this stage should be fixed before proceeding.

## 5. Upload the master boundary

Upload exactly one KML or KMZ. The notebook prints:

- named geometry parts;
- master boundary area;
- input SHA-256;
- bounds.

Retain the exact input file with the final output bundle.

## 6. Inspect spatial domains

Confirm the map shows:

- master boundary;
- fixed 100 m riparian ring;
- 5 km context.

The automatic reference search is broader than the 5 km context and is not the same geometry.

## 7. Inspect water detection

Inspect:

- configured baseline dates;
- Dynamic World observation depth;
- fallback use if triggered;
- baseline monthly water series;
- final baseline-period water mask.

Do not interpret water extent as universally higher-is-better.

## 8. Run the complete pipeline

The pipeline executes:

`metrics → QA → references → benchmarks → scoring → readiness → report`

## 9. Mandatory reference checkpoint

Inspect:

- automatic reference population summary;
- candidate area/pixel count;
- ecoregion diagnostics;
- water-occurrence similarity;
- HMI diagnostics;
- temporal gate;
- approval status;
- benchmark reference values;
- reference attainment and relative departure.

A reference-engine execution error is a validation failure. A candidate rejected because a QA gate failed is a valid scientific outcome.

## 10. Inspect scorecards

Review separately:

- `metric_scorecard.csv`
- `metric_qa_scorecard.csv`
- `reference_governance.csv`
- `benchmark_scorecard.csv`
- `metric_concern_scorecard.csv`
- `pillar_scorecard.csv`
- `overall_scorecard.json`
- `readiness.json`

For the default aquatic profile, overall condition should remain unavailable when C3 Fauna is not score-eligible.

## 11. Inspect the HTML report

Open:

`Year0_Biodiversity_Baseline_Report.html`

Check that:

- reference state and approval basis are visible;
- unavailable pillars say `Not assessed`;
- proxy indicators remain labelled as proxies;
- condition and pressure are separate;
- data gaps are explicit.

## 12. Baseline storage

For Year-0, retain `baseline_metric_scorecard.csv` with the output bundle.

Future monitoring should use the same profile and metric definitions unless a documented methodology upgrade is intentionally introduced.

## 13. Final package

Zip the complete output directory and retain:

- output ZIP;
- master KML/KMZ;
- exact Git commit;
- profile/configuration;
- final HTML report.
