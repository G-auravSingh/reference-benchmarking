# Method notes

## 1. Spatial domains

The supplied KML/KMZ is the fixed master assessment boundary. The pipeline does not assume that every pixel inside the boundary is permanently water.

A dynamic water domain is derived separately for each requested period. A fixed external 100 m ring is used for standardized riparian pressure/vegetation metrics, and a broader 5 km context ring is available for contextual/reference work.

Exposed pixels are not automatically treated as terrestrial habitat, because exposed lakebed, littoral substrate and terrestrial vegetation are ecologically different states.

## 2. Dynamic water detection

Dynamic World is the primary water source when at least the configured minimum number of observations is available. The primary mask is the mean Dynamic World `water` probability meeting the configured threshold.

When optical coverage is insufficient and fallback is enabled, Sentinel-1 VV is converted to a per-image water detection using the configured backscatter threshold. The fallback water mask is the configured majority fraction of those observations. Fallback output is explicitly labelled.

Water extent is a descriptive quantity. It should be compared using the same seasonal window and should not be interpreted as a monotonic ecological-quality score without hydrological context.

## 3. Baseline and monitoring

The default Year-0 baseline is 1 August 2025 through 31 August 2026. This captures a complete seasonal cycle while the current assessment is in 2026.

The historical 2018–2026 window is retained for the riparian trend metric. Future monitoring should use the same seasonal baseline window shifted by one or more complete years rather than comparing arbitrary calendar windows.

## 4. Water-quality proxies

NDCI uses Sentinel-2 bands B5 and B4 and is masked to the dynamic water domain. The red-reflectance proxy uses B4 under the same water mask. The FAI bloom proxy uses B4, B8 and B11 and reports the frequency of threshold exceedance over valid water-masked observations.

These are remote-sensing proxies. They are not calibrated chlorophyll-a, turbidity concentration or confirmed harmful algal bloom occurrence unless independent observations support that interpretation.

## 5. Riparian metrics

The fixed riparian domain is a standardized external buffer generated in a local UTM projection to avoid applying a degree-based buffer in geographic coordinates.

Shoreline disturbance is a transparent land-cover pressure proxy derived from Dynamic World mode classes for crops, built and bare land. Bare substrate can be natural, so the metric must not be equated directly with anthropogenic impact without local interpretation.

Riparian vegetation trend uses annual Sentinel-2 median NDVI composites, Theil–Sen slope and Kendall tau significance. The slope is a descriptive trend statistic and is not automatically labelled ecological recovery or degradation.

## 6. Reference framework

### Tier-1

Tier-1 is an externally justified reference. It can come from a reference KML/KMZ or a metric-value CSV. It is preferred over Tier-2 when available.

### Tier-2

Tier-2 is generated from the standardized context ring and is treated as a candidate peer/context benchmark. For water-quality metrics, the same metric code applies the dynamic water mask within the Tier-2 zone. For riparian disturbance, the candidate zone is treated as an external context ring rather than falsely calling the entire landscape an intact shoreline.

Tier-2 is not automatically approved for scoring.

## 7. Scoring

Metric-level concern classes are 1–5, where a larger score means greater concern. The mapping is allowed only after a metric-specific threshold basis is supplied.

For threshold scoring, the four ordered cut points are `t1<t2<t3<t4`. Lower-is-better metrics use the higher-value side as greater concern; higher-is-better metrics reverse that mapping.

Reference-relative scoring uses a direction-aware intactness ratio capped to 0–1. Reference-relative concern bands are also metric-specific and must be explicitly configured.

Pillar scores are the mean of eligible metric concern scores after a minimum metric-coverage rule. The overall 0–10 score is only produced when the configured minimum number of pillars is satisfied; the default aquatic profile requires all four pillars.

## 8. JRC historical context

JRC Global Surface Water v1.4 is treated as historical context only. It is not used as though it contains current observations beyond its published water-history period.

## 9. Biological evidence boundary

Remote sensing cannot establish local species occurrence, population size, eDNA persistence or acoustic biodiversity health by itself. P2 species assemblage and P3 population-status evidence should be supplied by field observations, eDNA, acoustics or other independent biodiversity modules before a complete four-pillar composite is considered.
