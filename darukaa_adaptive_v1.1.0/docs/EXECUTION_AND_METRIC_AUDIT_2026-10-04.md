# v1.1.0 Execution and Metric Audit — 2026-10-04

## Purpose

This pass was performed after the first Tata Motors Colab execution exceeded two hours. The objective was to remove execution multipliers and correct metric applicability/status handling without redesigning the package around Tata Motors.

## Corrections implemented

### 1. CPLAND Earth Engine geometry error
The CPLAND calculator now supplies an explicit 1 m `maxError` to `Geometry.area()`. This resolves the repeated Earth Engine error:

`Geometry.area: Unable to perform this geometry operation. Please specify a non-zero error margin.`

### 2. Reference execution multiplier removed
The previous adaptive pipeline calculated the complete migrated metric suite once per scored metric when constructing the reference benchmark. For the 13 terrestrial score-eligible legacy metrics, this multiplied expensive GEE calls unnecessarily.

The reference path now calculates the filtered scored-metric set once per reference population and reuses those results for all metric benchmarks. `FullMetricEngine.run(..., metric_names=...)` provides the execution filter.

### 3. Removed metrics are not executed
Indicators explicitly marked `registered=False` are no longer sent to their legacy calculators during a migrated run.

### 4. Metric status is preserved
The adaptive adapter now preserves explicit legacy status/metadata instead of converting every `value=None` result into `no_valid_observation`. It recognizes `not_applicable`, `pending_input`, and diagnostic metadata where supplied.

### 5. HSAS evidence gate
HSAS is not treated as fully scored when the eDNA asset is absent. Habitat suitability alone is retained as diagnostic context and the metric is marked `pending_input` for scoring purposes.

### 6. BII fallback provenance
The EII compositional fallback is explicitly identified as a non-independent fallback and excluded from scoring when it is the only BII source available. Primary/legacy BII assets remain usable when available.

### 7. Water-specific applicability
`rci` and `jrc_water_persistence` are now explicitly restricted to aquatic/mixed EMUs. A dry terrestrial EMU should not be penalized merely because it lacks persistent surface water or a riparian domain.

## Forest-loss handling

The low-baseline safeguard remains in place. Where the Hansen 2000 forest baseline is below 5 ha, the percentage loss/net-change rate is not scored because the percentage denominator is unstable at that scale. Absolute loss/change remains in metric metadata. This is deliberately retained as a scoring safeguard rather than replacing a small denominator with an arbitrary zero.

## Scientific audit position

The v0.2.7 calculators remain the implementation source for the 46-metric inventory, but their legacy implementation is not being treated as automatic scientific validation. The adaptive registry, applicability, status, reference and scoring layers are authoritative. Metrics with unresolved methodological or evidence limitations remain contextual/screening/pending rather than being silently promoted.

## Regression validation

- Python compilation: PASS
- pytest: 52 passed
- 46 registered legacy metrics remain discoverable
- CPLAND geometry fix retained
- terrestrial water-specific applicability regression tests added

## Expected execution impact

The largest runtime reduction comes from eliminating the nested full-suite reference recalculation. The next Tata Motors Colab run should therefore be materially shorter than the previous multi-hour execution, although Earth Engine dataset latency and the remaining 46-metric site pass still depend on GEE service performance.


## Scientific audit continuation — 2026-10-04

### Plan Vivo distinction
Plan Vivo PV Nature v1.2 explicitly uses within-site change against the site's own Year-0 baseline and does not use measured or theoretical reference sites for PVBC quantification. Its terrestrial methodology uses five pillar metrics, with Pillar 4 based on the spatial distribution of Sentinel-2 NDVI. Therefore this Adaptive pipeline's EO reference benchmarking must not be described as a Plan Vivo PVBC calculation or as a direct implementation of PV Nature. CPLAND may be retained as an independent landscape-configuration indicator, but it is not a Plan Vivo PVBC pillar metric.

### Reference calculation contract
For Adaptive benchmarking, the reference population is the full spatial candidate geometry after ecological matching and pressure screening (dominant Dynamic World habitat class + dominant RESOLVE ecoregion + HMI screen). Each metric is then calculated over that entire candidate population using the same calculator used for the site. The reference is retained as a spatial distribution (mean, median, SD, P05–P95, valid-pixel count); the central comparator is metric-specific: robust-reference metrics use the spatial median, while ratio/log-response metrics retain the spatial mean. Spatial pixels are descriptive observations, not independent ecological replicates.

### High-priority metric decisions
- **BII:** canonical Impact Observatory/Vizzuality PREDICTS-based BII v1.1 is used directly at 100 m. No EII-derived fallback is permitted; if the independent BII source is unavailable the metric is `pending_input`.
- **FLII:** the metric name is reserved for the canonical Grantham et al. (2020) 300 m 2019 raster. The former Darukaa P/Q/LFC reconstruction is no longer scored as FLII. A canonical raster must be supplied through `raster_paths['flii']` or an approved GEE asset.
- **CHM:** uses ETH Global Canopy Height 2020 at its native 10 m resolution. The product is a 2020 snapshot, not a current annual CHM. Site/reference values are spatial means over valid mapped canopy-height pixels.
- **CPLAND:** implemented as standard Core Area Percentage of Landscape: summed core area of the target habitat class divided by total landscape area ×100, with an explicit configurable edge depth. It is not labelled as a generic connectivity index.
- **Tree Cover Loss Rate:** Hansen GFC loss is restricted to pixels in the same 2000 baseline forest mask (treecover2000 ≥ configured threshold) used as the denominator. Inclusive annual windows are counted correctly: 2001–2025 = 25 years, 2020–2025 = 6 years, 2023–2025 = 3 years.
- **Net Forest Change Proxy:** retained for diagnostic restoration context, not headline scoring, because the current Dynamic World tree-expansion signal is a contemporary snapshot and is not temporally resolved enough to support a defensible annual gain rate.
