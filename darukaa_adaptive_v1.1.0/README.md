# Darukaa Adaptive Biodiversity Assessment Framework

**Release:** `darukaa_adaptive_v1.1.0`  
**Scope:** aquatic, terrestrial and mixed biodiversity assessments

Darukaa Adaptive is a profile-driven assessment framework for reproducible Earth Observation and multi-source biodiversity baselines. It separates measurement, QA/QC, reference-condition construction, reference approval, benchmarking, scoring, evidence provenance and reporting.

This folder is intended to be copied as a **complete release unit**. Do not mix individual modules from older releases into it.

## Start here

For the complete methodology, read:

1. **`docs/METHODOLOGY.md`** — overall company methodology for the full pipeline.
2. **`docs/REFERENCE_CONDITION_METHODOLOGY.md`** — detailed reference-condition standard.
3. **`docs/REFERENCE_CONDITION_QA_CHECKLIST.md`** — reference QA gate.
4. **`docs/REFERENCE_AND_SCORING_MODEL.md`** — reference-relative scoring contract.
5. **`docs/METHOD_NOTES.md`** — implementation notes and metric-specific caveats.
6. **`docs/NOTEBOOK_RUNBOOK.md`** — Colab execution procedure.
7. **`VALIDATION.md`** — automated tests and live Earth Engine acceptance boundary.
8. **`CHANGELOG.md`** — release history.

## Full architecture

```text
Project KML/KMZ
      ↓
Geometry QA + SHA-256 provenance
      ↓
Standard ecological domains
      ↓
Raw metric extraction
      ↓
Measurement QA/QC
      ↓
Reference-condition construction
      ├── ecological comparability
      ├── pressure screening
      ├── temporal matching
      ├── spatial quality
      └── population adequacy
      ↓
Reference QA / approval
      ↓
Reference distribution + central estimator
      ↓
Direction-aware benchmarking
      ├── relative departure
      ├── reference attainment
      └── uncertainty/diagnostics
      ↓
Score eligibility
      ↓
C1 Extent + C2 Vegetation + C3 Fauna
      +
C4 Pressure reported separately
      ↓
Readiness + report + complete manifest
```

## Generalised finite reference selection

The production reference workflow uses one decision contract across aquatic, terrestrial and mixed assessments. It deliberately separates **ecological eligibility** from **disturbance ordering**. HMI can only order candidates that already belong to the ecologically eligible population; it cannot compensate for ecological mismatch.

There are exactly three contemporary stages:

1. **Strict low-pressure contemporary:** configured HMI threshold, plus mandatory ecological, temporal, spatial and population QA.
2. **Least-disturbed contemporary:** if Stage 1 fails, use the empirical low-HMI quantile within the *same ecologically eligible population* (10% by default).
3. **Manual HMI-threshold fallback:** if Stage 2 fails, the Colab can accept one analyst-entered HMI threshold. The same ecological/temporal/spatial/population gates still apply.

If Stage 3 is not configured or fails, the terminal result is `candidate_rejected_reference_unavailable`. The pipeline does not keep relaxing thresholds or searching indefinitely. Manual reference KML/CSV uploads are not part of the production workflow.

Aquatic and terrestrial profiles define different ecological eligibility rules; mixed assessments maintain separate domain-specific reference populations.

## What v1.1.0 contains

### Spatial framework

- KML/KMZ ingestion and geometry validation.
- Local-UTM area calculation.
- Fixed 100 m riparian domain for aquatic assessments.
- Configurable analytical context.
- Separate, broader automatic-reference search radius.
- Dynamic water domain derived per period rather than treating the supplied KML as permanent water.

### Aquatic workflow

- Dynamic World primary water detection.
- Sentinel-1 fallback when configured optical coverage is insufficient.
- Water extent and persistence.
- NDCI proxy.
- Red-reflectance turbidity proxy.
- FAI-derived surface bloom-frequency proxy.
- Riparian NDVI.
- Multi-year Theil–Sen/Kendall riparian trend.
- Standardized shoreline disturbance pressure proxy.
- Modal Dynamic World land-cover composition diagnostics.

### Terrestrial workflow

- Natural/semi-natural land-cover fraction.
- Terrestrial NDVI.
- Built fraction.
- Automatic terrestrial reference screening using ecoregion + Dynamic World comparability + human-modification screening.
- Shared downstream scoring/evidence architecture.

### Reference-condition framework

- Explicit reference-state taxonomy.
- Automatic aquatic reference population construction.
- Automatic terrestrial reference population construction.
- Ecological matching and pressure screening separated from approval.
- QA-gated automated approval.
- Reference population diagnostics and spatial percentile summaries.
- Reference-relative departure and reference attainment.
- Legacy `intactness_score_0_100` retained only for compatibility.
- No fabricated 100% reference for water extent.

### Scoring and evidence

- C1 Extent, C2 Vegetation, C3 Fauna and C4 Pressure.
- C4 pressure remains separate from condition.
- Reference-gated score eligibility.
- Geometric-mean pillar aggregation.
- Explicit C3 gating for overall condition where configured.
- External/field/acoustic/eDNA evidence contract.
- Contextual proxies remain contextual unless scientifically approved for scoring.

### Reporting and provenance

- Machine-readable scorecards.
- Reference governance table.
- Readiness JSON.
- Overall condition/pressure JSON.
- Full assessment manifest.
- Self-contained HTML baseline report.
- Exact Git commit capture from Colab.
- Input KML SHA-256.

## Reference-condition principle

The default automated reference is a **least-disturbed contemporary reference population**. It is not automatically pristine, historical, natural, or optimal.

Automatic approval requires the configured ecological, pressure, temporal, spatial and population gates to pass. `auto_approve=True` only permits approval after those gates; it is not an unconditional bypass.

See `docs/REFERENCE_CONDITION_METHODOLOGY.md` for the full standard.

## Important dataset implementation detail

The configured TNC Global Human Modification v3 static 90 m product is an **Earth Engine ImageCollection**, not a single `ee.Image`. The reference engine loads it accordingly and uses the `All_threats_combined` band.

RESOLVE Ecoregions 2017 is a terrestrial FeatureCollection. For aquatic assessments it is used as a surrounding biogeographic comparability stratum, not as a lake typology.

## Running the Nandoshi validation workflow

Open:

`notebooks/Nandoshi_Lake_Aquatic_Assessment_Colab.ipynb`

The notebook:

1. clones the requested repository ref into a clean Colab directory;
2. installs only `darukaa_adaptive_v1.1.0`;
3. verifies package path/version and required reference modules;
4. records the exact Git SHA;
5. authenticates Earth Engine;
6. checks all configured public datasets, including TNC HM and RESOLVE;
7. uploads and hashes the master KML/KMZ;
8. validates the profile;
9. inspects water-domain diagnostics;
10. runs the complete pipeline;
11. performs a mandatory reference-condition validation checkpoint;
12. exports the complete output bundle.

The live reference checkpoint treats **software execution errors as failures**. A candidate that is legitimately rejected by QA is different from a reference engine that crashes.

## Local software validation

```bash
pip install -r requirements.txt
pip install -e .
pytest -q
python -m compileall -q darukaa_adaptive
```

Live Earth Engine validation must still be performed in the target Colab/GEE project before a client result is issued.

## Output contract

A complete assessment output contains, as applicable:

- `metric_scorecard.csv`
- `metric_qa_scorecard.csv`
- `reference_governance.csv`
- `benchmark_scorecard.csv`
- `metric_concern_scorecard.csv`
- `pillar_scorecard.csv`
- `overall_scorecard.json`
- `readiness.json`
- `assessment_manifest.json`
- `water_periods.csv`
- `water_monthly.csv`
- `landcover_composition.csv`
- `external_evidence.csv`
- `indicator_registry.csv`
- `legacy_metric_crosswalk.csv`
- `Year0_Biodiversity_Baseline_Report.html`
- `README_OUTPUTS.md`

## Scientific guardrails

The framework does not claim that:

- low human modification alone proves ecological integrity;
- a reference ratio is biodiversity itself;
- NDVI is biodiversity;
- exceeding a reference means ecological perfection;
- a protected area is automatically pristine;
- one search radius is valid for every ecosystem;
- spatial pixels are independent statistical replicates;
- remote sensing removes the need for field validation where validation is required.

## Release discipline

This release should be treated as a complete package. If a module, metric, dataset, formula, profile or notebook cell is changed, rerun the full software test suite and repeat the live acceptance checks before using the result for client delivery.
