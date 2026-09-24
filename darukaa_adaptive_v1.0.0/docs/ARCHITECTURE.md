# Architecture and design decisions

## 1. Two-track strategy

### Legacy track
`legacy_darukaa_reference_v0.1.0/` remains unchanged. It is the reproducibility anchor for historical terrestrial assessments.

### Adaptive track
`darukaa_adaptive/` contains ecosystem-aware domain derivation and lake metrics.

The two tracks are intentionally separated so that correcting lake logic cannot silently change historical terrestrial outputs.

## 2. Spatial model

The master KML is always fixed. It is never replaced by a water polygon derived from one image.

Secondary domains are generated automatically:

- dynamic water = per-observation Dynamic World water probability mask inside the fixed KML;
- riparian = standardized external buffer around the fixed KML;
- exposed lakebed = conceptually recognized as a distinct state rather than automatically reclassified as terrestrial habitat.

## 3. Metric classes

Each metric should eventually carry:

- ecological target;
- spatial domain;
- temporal window;
- data source;
- nominal resolution;
- formula;
- direction of concern;
- benchmark protocol;
- SoN inclusion flag;
- data-quality requirements.

## 4. No-data policy

A metric that cannot be computed from available data is recorded as `failed` or `not_run`; it is not silently converted to zero.

## 5. Current-year water persistence

The original Nandoshi implementation attempted to use JRC Monthly Water History through a modern year. JRC v1.4 is historical through 2021. The adaptive profile therefore uses Dynamic World for current-year water observations and reserves JRC for historical context.

## 6. SoN status

The current lake SoN is explicitly marked **PROVISIONAL**. The purpose of this package is to establish the correct automated spatial architecture first, while retaining the supplied Nandoshi thresholds as a compatibility layer. Aquatic benchmark validation should be completed before treating the composite as a finalized credit-grade metric.
