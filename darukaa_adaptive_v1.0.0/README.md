# Darukaa Adaptive Biodiversity Assessment Framework v1.1.0

## What this package is

This folder is the generalized adaptive layer for ecosystem-profiled biodiversity assessment. The supplied legacy package remains under `legacy/darukaa_reference_v0.1.0/` and is intentionally frozen for reproducibility.

The current production profile is `aquatic_lake`, with Nandoshi Lake as the first implementation. Nothing in the package hard-codes Nandoshi coordinates, area, or a hand-drawn water mask.

## Core architecture

The assessment separates five spatial concepts:

1. **Master assessment boundary** — the supplied KML/KMZ.
2. **Dynamic water domain** — derived from EO for each analysis period.
3. **Exposed/littoral domain** — conceptually the master boundary minus dynamic water; it is not automatically treated as terrestrial habitat.
4. **Fixed riparian domain** — standardized external buffer around the master boundary (default 100 m).
5. **Context/reference domain** — standardized broader external ring (default 5 km).

The same spatial reference frame is used across the assessment, but every metric applies its own ecologically valid mask. This prevents open-water pixels, exposed substrate and riparian vegetation from being mixed into a single generic raster mask.

## Time design

The Nandoshi profile is configured for:

- **Year-0 baseline:** 1 August 2025 through 31 August 2026, a complete seasonal cycle.
- **Historical context/trend:** 2018–2026.
- **Future monitoring:** use the same seasonal baseline window shifted by whole years. Do not compare different seasonal windows as though they were equivalent monitoring periods.

Dates are explicit in the configuration. The code converts the inclusive baseline end date to the exclusive end convention required by Earth Engine.

## Metrics

The default lake run reports:

- `water_extent` — EO-derived water area as a percentage of the master boundary.
- `water_persistence` — spatial mean of water occurrence over valid observations.
- `ndci_proxy` — water-masked chlorophyll/trophic spectral proxy.
- `red_reflectance_turbidity_proxy` — water-masked red reflectance proxy.
- `surface_algal_bloom_frequency` — frequency of FAI threshold exceedance over water-masked optical observations.
- `shoreline_disturbance_fraction` — crops + built + bare fraction in the standardized riparian ring.
- `riparian_ndvi_sen_slope` — Theil–Sen slope of annual riparian NDVI with Kendall significance retained in notes.
- land-cover composition by Dynamic World class as a contextual table.

Metrics are not automatically considered ecological state variables merely because an EO value exists. Proxy status, reference eligibility, uncertainty and scoring eligibility are retained in the output.

## Tier-1 and Tier-2 benchmarking

Benchmarking is metric-specific.

**Tier-1:** an externally justified reference source, supplied either as a reference KML/KMZ or a CSV of metric reference values.

**Tier-2:** an automatically generated candidate reference zone based on the fixed context ring. It is reported as a candidate peer/context benchmark, not silently treated as an intact ecological control.

Tier-1 is preferred when both tiers are available. Tier-2 cannot be used for scoring unless explicitly approved in configuration.

Reference benchmarking does not automatically imply concern scoring. The score layer only converts a metric to a 1–5 concern class when either:

- a reviewed metric-specific threshold set (`t1..t4`) is supplied, or
- explicitly approved reference-relative intactness bands (`r1..r4`) are supplied.

## Scoring

When enabled with reviewed thresholds, the hierarchy is:

**metric raw value → metric concern score (1–5) → pillar mean score → overall 0–10 score**.

Missing metrics are not silently removed from the evidence base. Each metric reports its status and score eligibility, pillar aggregation has a minimum metric requirement, and the overall score is withheld when required pillar coverage is incomplete.

The overall 0–10 formula is preserved from the legacy SoN convention:

`((sum(mean pillar scores) - n) / (n × 4)) × 10`

where `n` is the number of valid pillars included. By default the adaptive aquatic profile requires all four pillars, because EO-only lake measurements do not establish P2 species assemblage or P3 population status.

## Colab workflow

Open `notebooks/Nandoshi_Lake_Aquatic_Assessment_Colab.ipynb` in Google Colab and run top-to-bottom. The first setup cell:

- clones the repository if necessary;
- performs `git pull --ff-only origin main` when the repository already exists;
- records the commit SHA;
- installs only `darukaa_adaptive_v1.1.0` from the `darukaa_adaptive_v1.0.0/` folder;
- clears previously imported adaptive modules so later edits pulled from GitHub are actually reloaded.

This means manual edits made later in GitHub can be pulled into the same notebook by re-running the synchronization/install cell before continuing.

## Output package

The standard run produces:

- `metric_scorecard.csv`
- `benchmark_scorecard.csv`
- `metric_concern_scorecard.csv`
- `pillar_scorecard.csv`
- `overall_scorecard.json`
- `water_periods.csv`
- `landcover_composition.csv`
- `readiness.json`
- `indicator_registry.csv`
- `legacy_metric_crosswalk.csv`
- `assessment_manifest.json`
- `README_OUTPUTS.md`

The manifest records configuration, the input boundary SHA-256 and the visible Git commit when available.

## Legacy package policy

Do not modify the code under `legacy/darukaa_reference_v0.1.0/` when reproducibility of the supplied terrestrial workflow matters. The adaptive framework is deliberately additive rather than an in-place rewrite of that package.
