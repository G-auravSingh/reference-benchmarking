# Darukaa Adaptive Biodiversity Assessment Framework v1.2.0

## What this package is

This folder is the generalized adaptive layer for ecosystem-profiled biodiversity assessment. The supplied legacy package remains under `legacy/darukaa_reference_v0.1.0/` and is intentionally frozen for reproducibility.

The current production profile is `aquatic_lake`, with Nandoshi Lake as the first implementation. Nothing in the package hard-codes Nandoshi coordinates, area, or a hand-drawn water mask.

## Universal scoring architecture

The same scoring architecture is used across aquatic, terrestrial and other ecosystem profiles, and across Earth-observation, acoustic, field, eDNA and other validated observation sources:

**Raw value → comparable reference → intactness (0–100) → indicator concern → pillar geometric mean → pillar concern → overall geometric mean → overall concern**

The four common pillars are:

- **C1 — Extent**
- **C2 — Vegetation**
- **C3 — Fauna**
- **C4 — Pressure**

Concern bands are:

| Intactness | Concern |
|---:|---|
| 80–100% | Very Low |
| 60–<80% | Low |
| 40–<60% | Moderate |
| 20–<40% | High |
| 0–<20% | Very High |

These bands are a **declared Darukaa product convention**, not universal ecological thresholds.

## Reference model

Tier-1 is an externally justified or supplied reference. Tier-2 is an automatically generated candidate regional/context reference.

Tier-1 is preferred when both are available. A benchmark may be shown without being approved for scoring. **Only an explicitly approved selected reference can make an indicator score-eligible.**

Reference comparison is direction-aware:

- higher-is-better: observed/reference, capped to 0–1;
- lower-is-better: reference/observed, capped to 0–1;
- reference-target: bounded proportional distance from the comparable reference.

This means different raw metrics can be standardized to one common interpretation:

**100% intactness = reference-like; 0% = maximum departure represented by the metric transformation.**

## Pillar and overall aggregation

Pillar score:

`geometric mean(scoreable indicator intactness values)`

Overall SoN:

`geometric mean(C1, C2, C3, C4)`

Labels are never averaged.

The pipeline also names the limiting indicator within each pillar. The overall result names the limiting pillar and the limiting indicator within that pillar.

Example output language:

> C1: 62% (Low concern) — limited primarily by `surface_algal_bloom_frequency` at 31%.

> Overall SoN: 51% (Moderate) — limited primarily by C3 Fauna (34%), itself limited by `bii` (8%).

The overall score is withheld when the required four-pillar evidence coverage is not met.

## Current aquatic spatial architecture

The assessment separates five spatial concepts:

1. **Master assessment boundary** — the supplied KML/KMZ.
2. **Dynamic water domain** — derived from EO for each analysis period.
3. **Exposed/littoral domain** — conceptually the master boundary minus dynamic water; it is not automatically treated as terrestrial habitat.
4. **Fixed riparian domain** — standardized external 100 m buffer.
5. **Context/reference domain** — standardized broader 5 km external ring.

The same spatial reference frame is used across the assessment, but every metric applies its own ecologically valid mask.

## Time design

The Nandoshi profile is configured for:

- **Year-0 baseline:** 1 August 2025 through 31 August 2026.
- **Historical context/trend:** 2018–2026.
- **Future monitoring:** shift the complete baseline seasonal window by whole years.

## Current aquatic metrics

The default lake run reports:

- `water_extent` — EO-derived water area relative to the master boundary.
- `water_persistence` — spatial mean water occurrence.
- `ndci_proxy` — water-masked chlorophyll/trophic spectral proxy.
- `red_reflectance_turbidity_proxy` — water-masked red reflectance proxy.
- `surface_algal_bloom_frequency` — FAI threshold-exceedance frequency.
- `riparian_ndvi` — baseline riparian vegetation greenness proxy.
- `shoreline_disturbance_fraction` — crop + built + bare fraction in the fixed riparian ring.
- `riparian_ndvi_sen_slope` — historical Theil–Sen riparian trend.
- Dynamic World land-cover composition as contextual output.

The first six/some are benchmarkable where a comparable reference exists; the trend and class composition remain contextual unless the registry is explicitly expanded.

## Field, acoustic and terrestrial metrics

The scoring engine is deliberately independent of the aquatic metric calculator.

Use `score_external_observations()` with a table containing:

`metric, pillar, raw_value, direction, reference_value`

and optionally:

`units, reference_type, reference_level, reference_approved_for_scoring, status, notes`

This allows metrics such as species richness, abundance, acoustic diversity, vegetation condition, habitat extent, BII/MSA and project-specific field measures to use the same scoring framework without changing the scoring logic.

The relevant domain module remains responsible for calculating the raw value.

## Colab workflow

Open `notebooks/Nandoshi_Lake_Aquatic_Assessment_Colab.ipynb` in Google Colab and run top-to-bottom.

The setup cell:

- clones the repository if necessary;
- performs `git pull --ff-only origin main` when the repository already exists;
- records the commit SHA;
- installs only `darukaa_adaptive_v1.2.0` from the `darukaa_adaptive_v1.0.0/` folder;
- clears cached `darukaa_adaptive` modules.

Re-run that synchronization/install cell whenever you make manual changes in GitHub.

## Outputs

The standard run produces:

- `metric_scorecard.csv` — raw measurements and metric provenance.
- `metric_qa_scorecard.csv` — automated structural/data-quality QA flags for each metric.
- `benchmark_scorecard.csv` — Tier-1/Tier-2 references, raw comparison and intactness.
- `metric_concern_scorecard.csv` — raw value, reference, intactness and concern for scoreable metrics.
- `pillar_scorecard.csv` — C1/C2/C3/C4 geometric means and limiting indicators.
- `overall_scorecard.json` — 0–100 SoN, concern, limiting pillar and limiting indicator.
- `water_periods.csv` — dynamic water summaries.
- `landcover_composition.csv`.
- `readiness.json`.
- `indicator_registry.csv`.
- `legacy_metric_crosswalk.csv`.
- `assessment_manifest.json`.

## Legacy package policy

Do not modify code under `legacy/darukaa_reference_v0.1.0/`. The adaptive framework is additive and preserves the supplied legacy implementation for reproducibility.
