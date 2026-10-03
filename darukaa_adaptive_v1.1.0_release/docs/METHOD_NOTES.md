# Method notes

## 1. Spatial domains

The supplied KML/KMZ is the fixed master assessment boundary. The pipeline does not assume that every pixel inside the boundary is permanently water.

A dynamic water domain is derived separately for each requested period. A fixed external 100 m ring is used for standardized riparian pressure/vegetation metrics, and a broader 5 km context ring is available for contextual/reference work.

Exposed pixels are not automatically treated as terrestrial habitat, because exposed lakebed, littoral substrate and terrestrial vegetation are ecologically different states.

## 2. Dynamic water detection

Dynamic World is the primary water source when at least the configured minimum number of observations is available. The primary mask is the mean Dynamic World `water` probability meeting the configured threshold.

When optical coverage is insufficient and fallback is enabled, Sentinel-1 VV is converted to a per-image water detection using the configured backscatter threshold. The fallback water mask is the configured majority fraction of those observations. Fallback output is explicitly labelled.

Water extent and water persistence are reference-target indicators when a comparable reference is available. They are not assumed to be universally higher-is-better or lower-is-better.

## 3. Baseline and monitoring

The default Year-0 baseline is 1 August 2025 through 31 August 2026. This captures a complete seasonal cycle while the current assessment is in 2026.

The historical 2018–2026 window is retained for the riparian trend metric. Future monitoring should use the same seasonal baseline window shifted by one or more complete years rather than comparing arbitrary calendar windows.

## 4. Water-quality proxies

NDCI uses Sentinel-2 bands B5 and B4 and is masked to the dynamic water domain. The red-reflectance proxy uses B4 under the same water mask. The FAI bloom proxy uses B4, B8 and B11 and reports the frequency of threshold exceedance over valid water-masked observations.

These are remote-sensing proxies. They are not calibrated chlorophyll-a, turbidity concentration or confirmed harmful algal bloom occurrence unless independent observations support that interpretation.

## 5. Riparian metrics

The fixed riparian domain is a standardized external buffer generated in a local UTM projection to avoid applying a degree-based buffer in geographic coordinates.

Baseline riparian NDVI is reported as a vegetation-condition proxy in **C2 Vegetation**. The historical Theil–Sen/Kendall trend remains a contextual monitoring indicator and is not directly converted to reference attainment.

Shoreline disturbance is a transparent land-cover pressure proxy derived from Dynamic World mode classes for crops, built and bare land. Bare substrate can be natural, so the metric must not be equated directly with anthropogenic impact without local interpretation.

## 6. Universal reference and scoring model

The adaptive framework uses one common architecture across ecosystem realms:

`raw value → comparable reference → reference attainment 0–100 → concern → pillar geometric mean → overall condition/pressure`

The four common pillars are:

- C1 Extent
- C2 Vegetation
- C3 Fauna
- C4 Pressure

Concern bands are fixed at 0–<20, 20–<40, 40–<60, 60–<80 and 80–100, corresponding to Very High, High, Moderate, Low and Very Low concern. These are an explicit Darukaa product convention, not universal ecological thresholds.

Direction is indicator-specific. Higher-is-better and lower-is-better indicators use direction-aware ratios; reference-target indicators use bounded proportional distance from the reference.

Reference selection is finite: strict low-pressure contemporary → least-disturbed contemporary quantile → optional analyst-entered manual HMI threshold. Scoring remains reference-QA gated; the manual threshold is recorded as an explicit analyst decision.

## 7. Field and other indicators

The scoring engine can consume field, terrestrial, acoustic and other validated observations through the generic external-observation interface. Those observations must carry their own pillar, direction and reference metadata.

The domain module remains responsible for calculating the raw indicator; the common scoring engine does not invent field values or references.

## 8. JRC historical context

JRC Global Surface Water v1.4 is treated as historical context only. It is not used as though it contains current observations beyond its published water-history period.

## 9. Biological evidence boundary

Remote sensing cannot establish local species occurrence, population size, eDNA persistence or acoustic biodiversity health by itself. C3 Fauna should therefore be supplied by field observations, eDNA, acoustics or other independent biodiversity modules before a complete four-pillar composite is considered.

## R4 reference-condition note (2026-10-01)

The reference-condition architecture was upgraded in v1.1.0. See `REFERENCE_CONDITION_METHODOLOGY.md` for the authoritative method. In particular, an automatic candidate is now approved only after explicit ecological, pressure, temporal, spatial and population gates. The default automatic state is `least_disturbed_contemporary`; this is not a claim of pristine or pre-human condition.

## 10. Full v1.1.0 release integration note (2026-10-01)

The v1.1.0 release integrates the reference-condition architecture with the complete adaptive pipeline rather than treating reference selection as a standalone add-on.

The production path is now:

`geometry → domains → metrics → measurement QA → reference construction → reference QA → benchmarking → score eligibility → pillar/overall scoring → readiness → report → manifest`

The reference engine is required to distinguish a legitimate candidate rejection from a software execution failure. The Nandoshi Colab notebook therefore includes a mandatory reference-validation checkpoint after the full pipeline run.

### Reference central estimator

For referenceable raster-derived metrics, the default central reference estimator is the spatial median (`P50`) where available. Mean, SD and additional spatial percentiles are retained as diagnostics. These are spatial summaries, not independent-replicate confidence intervals.

### TNC Human Modification dataset

`TNC/HM/v3/90m_s` is loaded as an Earth Engine `ImageCollection` and the configured `All_threats_combined` band is aggregated as a median image. The product is the 2022 static 90 m snapshot. It is used as a pressure-screening surface, not as a water-quality metric.

### Aquatic HMI screening

For aquatic reference candidates, the HMI screen uses a focal mean of surrounding **land-context** pixels around candidate water. Dynamic World water pixels are excluded from the land-context mask when Dynamic World observations are available. This prevents the HMI screen from being interpreted as direct modification of the water itself.

### Terrestrial HMI screening

For terrestrial reference candidates, the same TNC HMI product is applied to the Dynamic World comparability stratum. A low HMI value is a pressure screen, not proof that the land-cover class is natural.

### Scoring gate

The aquatic profile requires a score-eligible C3 Fauna pillar before overall condition is scored. Missing fauna evidence is therefore reported as insufficient condition coverage rather than being represented as a complete or 100/100 pillar.

### Manual references

The production pipeline has no manual reference-file pathway. The only manual fallback is an explicitly entered HMI threshold in Colab, chosen from the reference diagnostics after the two automatic contemporary stages fail.

### Output governance

The assessment now exports `reference_governance.csv` in addition to `benchmark_scorecard.csv`. The manifest also retains benchmark, pillar, overall, readiness and reference-population governance records so the final output is self-contained for audit.
