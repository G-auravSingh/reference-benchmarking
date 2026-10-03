# Metric Registry and Extensibility Standard

## 1. Purpose

Darukaa Adaptive is designed as a multi-source biodiversity assessment framework, not as a fixed list of Earth Observation indicators. The metric architecture therefore separates **indicator definition**, **data acquisition**, **measurement**, **QA/QC**, **reference eligibility**, **benchmarking**, **aggregation**, and **reporting**.

The production objective is that a new indicator can be introduced without rewriting the assessment engine or creating a parallel scoring framework.

## 2. Indicator contract

Every production indicator must have, at minimum:

- stable machine-readable name;
- pillar and ecological construct;
- subdimension;
- applicable domain/ecosystem type;
- units;
- directionality or reference-target behavior;
- evidence tier;
- reference eligibility;
- scoring pathway;
- ecological question;
- management use;
- scientific/implementation notes.

The current `IndicatorSpec` contract is the metadata layer. It is deliberately independent from the metric calculator.

## 3. Evidence tiers

Indicators may originate from:

- Earth Observation;
- field sampling;
- camera traps;
- acoustic monitoring;
- eDNA;
- species observations;
- laboratory measurements;
- model-derived estimates;
- conservation datasets;
- contextual external evidence.

The evidence source does not by itself determine whether an indicator is score-eligible. Validation, sampling design, uncertainty, ecological interpretation and reference comparability must also be established.

## 4. Proxy discipline

Indicators such as NDVI, spectral water-quality proxies, human-modification indices and land-cover fractions are proxies. Their labels must remain scientifically accurate in machine-readable outputs and client reports.

A proxy must not be relabelled as a direct biodiversity observation simply because it is convenient for a composite score.

## 5. Reference eligibility

A metric may be:

- reference-relative and score-eligible;
- reference-relative but contextual until validated;
- contextual without reference benchmarking;
- descriptive only;
- explicitly excluded from a given domain.

Reference eligibility is therefore a property of the indicator and its configuration, not a universal property of all metrics.

## 6. Directionality

Supported behaviors include:

- `higher_is_better`;
- `lower_is_better`;
- `reference_target` where deviation from the reference in either direction requires interpretation;
- `context_dependent` where no universal monotonic ecological direction is defensible.

This is particularly important for metrics such as water extent or hydroperiod, where greater magnitude is not intrinsically better across all ecosystem types or seasons.

## 7. Future field-derived metrics

Field-derived metrics must enter through the same registry rather than through a separate reporting path. Examples include standardized vegetation plots, camera-trap occupancy, acoustic diversity/occupancy, eDNA richness, fish assemblage measures, habitat-structure observations and validated population indicators.

Before activation for scoring, each field metric should document:

1. sampling design;
2. effort and detectability;
3. laboratory/observer QA where relevant;
4. spatial and temporal support;
5. uncertainty;
6. reference comparability;
7. aggregation rule;
8. evidence provenance;
9. limitations and interpretation boundaries.

## 8. Metric lifecycle

New metrics should follow:

`proposal → scientific review → implementation → unit tests → QA/QC validation → reference/aggregation validation → pilot assessment → documentation → production activation`.

A metric is not production-ready merely because its code executes.

## 9. 0.2.7 migration policy

The legacy `darukaa_reference_v0.2.7` metric catalogue is a source for candidate indicators, not an automatic import list. Every candidate must be assessed separately for:

- scientific validity;
- data-source validity;
- spatial/temporal suitability;
- implementation correctness;
- uncertainty;
- domain applicability;
- reference suitability;
- aggregation behavior;
- reporting usefulness.

Only validated indicators should be promoted into the active registry.
