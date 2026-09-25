# Method notes

## Dynamic water

Primary water detection uses the Dynamic World `water` probability composite. A period is considered optically supportable when at least the configured minimum number of Dynamic World images are available. The primary mask is `mean(water_probability) >= threshold`.

When the minimum optical observation count is not met and fallback is enabled, Sentinel-1 VV is used with a configurable backscatter threshold. Because SAR water thresholds can be scene- and incidence-dependent, fallback detections are explicitly labeled as `sentinel1_vv` in outputs.

## Water extent

`water_fraction_pct = mean dynamic water area / master boundary area × 100`.

This is a monitoring quantity, not a universal “more is better” score. Seasonal and interannual hydroclimatic variability must be considered.

## Water persistence

The pipeline estimates the spatial mean of the fraction of valid Dynamic World observations classified as water. Cloud-masked observations are not counted as water or non-water observations when their pixels are masked.

## Optical water metrics

NDCI and the red-reflectance turbidity proxy are always masked to the dynamically detected water domain for the analysis period. Surface bloom-proxy frequency uses FAI and the configurable FAI threshold. These are presented as proxies, not field-calibrated concentrations.

## Riparian trend

A standardized fixed 100 m external buffer is derived automatically from the master boundary. Annual seasonal NDVI composites are generated from Sentinel-2 SR Harmonized. At least five usable years are required by default. The trend is calculated from the annual values using Theil-Sen slope and Kendall tau significance testing in Python.

## Threshold scoring

No generic aquatic ecological threshold is silently embedded for the proxy metrics. The scoring utility accepts explicit `t1..t4` thresholds when an approved threshold set is supplied. This prevents a mathematically neat but biologically unsupported composite from being mistaken for an empirical ecological assessment.

## JRC context

JRC Global Surface Water v1.4 is suitable for historical water context through 2021. It should not be requested as though it contains 2022–present observations.

## Legacy crosswalk

The adaptive package contains a 44-indicator crosswalk in `darukaa_adaptive.registry`. It records whether each frozen legacy metric is directly usable, needs modification, is contextual only, or is excluded for the lake profile. This prevents an ecosystem-agnostic loop from applying every legacy indicator to a lake simply because the legacy registry contains the metric.
