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

Baseline riparian NDVI is reported as a vegetation-condition proxy in **C2 Vegetation**. The historical Theil–Sen/Kendall trend remains a contextual monitoring indicator and is not directly converted to intactness.

Shoreline disturbance is a transparent land-cover pressure proxy derived from Dynamic World mode classes for crops, built and bare land. Bare substrate can be natural, so the metric must not be equated directly with anthropogenic impact without local interpretation.

## 6. Universal reference and scoring model

The adaptive framework uses one common architecture across ecosystem realms:

`raw value → comparable reference → intactness 0–100 → concern → pillar geometric mean → overall geometric mean`

The four common pillars are:

- C1 Extent
- C2 Vegetation
- C3 Fauna
- C4 Pressure

Concern bands are fixed at 0–<20, 20–<40, 40–<60, 60–<80 and 80–100, corresponding to Very High, High, Moderate, Low and Very Low concern. These are an explicit Darukaa product convention, not universal ecological thresholds.

Direction is indicator-specific. Higher-is-better and lower-is-better indicators use direction-aware ratios; reference-target indicators use bounded proportional distance from the reference.

Tier-1 references are preferred when available. Tier-2 is a candidate regional/context benchmark. Scoring requires explicit approval of the selected reference tier.

## 7. Field and other indicators

The scoring engine can consume field, terrestrial, acoustic and other validated observations through the generic external-observation interface. Those observations must carry their own pillar, direction and reference metadata.

The domain module remains responsible for calculating the raw indicator; the common scoring engine does not invent field values or references.

## 8. JRC historical context

JRC Global Surface Water v1.4 is treated as historical context only. It is not used as though it contains current observations beyond its published water-history period.

## 9. Biological evidence boundary

Remote sensing cannot establish local species occurrence, population size, eDNA persistence or acoustic biodiversity health by itself. C3 Fauna should therefore be supplied by field observations, eDNA, acoustics or other independent biodiversity modules before a complete four-pillar composite is considered.
