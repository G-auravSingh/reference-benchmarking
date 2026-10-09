# Darukaa Adaptive Biodiversity Assessment v1.1.0

A generalized, evidence-aware biodiversity baseline framework designed to operate downstream of Darukaa Site Selection.

## Production architecture

```text
Site Selection / project geometry
            ↓
Standardized EMU handoff
            ↓
Domain + ecological characterization
            ↓
Reference population construction
            ↓
Metric extraction + QA/QC
            ↓
Reference benchmarking
            ↓
0–100 metric attainment
            ↓
Metric → subdimension (geometric mean)
            ↓
Subdimension → pillar (limiting factor)
            ↓
P1/P2/P3 condition (geometric mean + limiting pillar)
            +
P4 anthropogenic pressure
            ↓
Project aggregation + EMU ecological comparison
            ↓
Client report + auditable manifest
```

## Inputs

Preferred production input is the Site Selection handoff ZIP with `tile_manifest.json` and EMU GeoJSON tiles. The parser also supports GeoJSON FeatureCollections, KML/KMZ and single polygons.

An EMU may be multipart/disconnected. The framework does not assume contiguity is required for ecological identity.

## Domains

- `terrestrial`
- `aquatic`
- `mixed`
- `auto`

Domain-specific profiles determine which metrics and reference populations apply. Mixed projects retain aquatic and terrestrial reference populations separately.

## Reference framework

Reference selection is finite:

1. strict contemporary low-pressure;
2. empirical least-disturbed contemporary within the ecologically eligible population;
3. explicit manual HMI threshold after diagnostics;
4. otherwise reference unavailable.

Ecological eligibility precedes HMI ranking. HMI is a pressure screen, not a substitute for ecological comparability. Manual KML/CSV reference files are not supported.

## Scoring

The common 0–100 score is **reference attainment**, not a claim of absolute ecological intactness.

- complementary metrics within a subdimension: geometric mean;
- subdimensions within a pillar: limiting factor;
- P1/P2/P3 overall condition: geometric mean;
- limiting pillar and metric are always reported;
- P4 pressure remains separate.

Statistical benchmarks such as z-scores and robust z-scores are retained as diagnostics when reference dispersion permits. They are not silently substituted for the common client-facing score.

## Project aggregation and comparison

Project summaries are generated only after EMU-level assessment. The package outputs:

- project metric score aggregation;
- project pillar aggregation;
- project overall scorecard;
- EMU ecological comparison table with pillar scores, concerns and limiting metrics;
- project HTML report with project overview, pillar/metric summaries, EMU comparison, concern-band distribution, evidence gaps, output-QA flags and EMU/reference index;
- `emu_condition_concern_distribution.csv`, including counts and area shares for complete three-pillar condition bands and separate partial/insufficient-evidence categories;
- `project_output_qa.json` with explicit review flags;
- one auditable manifest linking EMUs to their output directories and recording the final QA state and downloadable archive.

Area-weighting is the default project aggregation for normalized common scores, while metric-level raw values remain available. Missing EMUs are represented through coverage fields rather than converted to zero. Overall EMU concern bands are assigned only where P1, P2 and P3 are all scored. Area shares use summed EMU area and assume non-overlapping EMUs; this assumption is disclosed in the report. Condition and anthropogenic pressure remain separate. Automated output-QA PASS is not ecological certification.

## Current indicators

The active production registry is deliberately conservative. It includes only indicators whose calculation and interpretation are implemented in this release. Future EO, field, acoustic and eDNA indicators can be registered through the same contract; field-derived indicators without a defensible comparator remain contextual until reference/threshold requirements are satisfied.

## Reproducibility

The manifest records the input SHA-256, package version, configuration, Git commit when available, metric provenance, reference governance, scoring eligibility and aggregation coverage.

For client runs, pin the exact verified Git commit in the Colab notebook rather than using `main`.

## Validation

The package contains automated tests for:

- input/handoff parsing;
- Site Selection `tile_paths` manifests;
- multipart EMUs;
- finite reference policy;
- metric benchmarking;
- scoring hierarchy;
- pressure separation;
- project aggregation;
- EMU comparison;
- configuration validation;
- package integrity.

A passing software suite does not substitute for live Earth Engine acceptance. Dataset/API failures are technical failures, not ecological findings.

## Metric selection (v1.1.0 scientific production contract)

Metric calculation is independent of metric selection. The registry exposes every registered metric with its pillar, construct, direction, source, reference type, native scale and scoreability class. By default, all `default_scored` metrics are scored. A client can demote any of these to contextual in the Colab notebook using `METRIC_OVERRIDES`, without modifying the calculator or package code. Diagnostic, removed and hard-context metrics remain non-scoreable unless their scientific contract is changed in a future audited release.

The active metric registry is deliberately smaller than the historical audit inventory. Metrics that are invalid, misleadingly named, redundant, or based on unvalidated composites are removed from runtime calculation and reporting. See `docs/METRIC_CONTRACT_MATRIX.csv` for the 62 original metric IDs plus the MSA candidate (63 audit rows), including dispositions, caveats and source/provenance fields.
