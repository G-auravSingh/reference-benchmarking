# Darukaa Adaptive v1.1.0 — Scientific Metric Audit

Date: 2026-10-04

## Scope

This audit reviews the live 46-metric inventory carried into v1.1.0 from the legacy implementation. The question is not whether a function executes, but whether the metric has a defensible ecological definition, data source, calculation, applicability rule, direction, and reference/scoring treatment.

A metric may therefore be **scored**, **contextual**, **screening**, **removed**, or **pending input**. A registered metric is not automatically a headline score.

## Site vs reference calculation

**Site:** the metric calculator is run over the EMU assessment boundary. Raster metrics use a spatial summary over valid pixels; the primary site value is the spatial mean unless a metric has an explicitly different calculation.

**Condition reference:** the automatic terrestrial reference population is constructed once per EMU from the surrounding search annulus, restricted to the dominant RESOLVE ecoregion and the site's dominant contemporary Dynamic World habitat class, then screened for low HMI. The selected candidate geometry is the full matched population, not one pixel and not the median of nearby sites. Each scored metric is then calculated over that entire candidate geometry with the same calculator used for the site.

**Pressure reference:** P4 pressure indicators do not use the low-HMI reference pool. They use the same ecological matching without an HMI filter. This prevents circularity, especially for GHM, where selecting the reference using GHM/HMI and then benchmarking GHM against that pool would pre-select the answer.

**Reference distribution:** server-side mean, median, SD, P05–P95 and valid-pixel count are retained as descriptive diagnostics. Robust-reference metrics use the spatial median as the central comparator; ratio/log-response metrics retain the spatial mean. Spatial pixels are not treated as independent ecological replicates.

## Metric decisions

| Metric | Current basis | Verdict | Production treatment |
|---|---|---|---|
| natural_habitat | Dynamic World natural-class fraction | Defensible EO extent proxy | Scored; reference-relative |
| natural_landcover | Dynamic World land-cover fraction | Defensible extent composition; potentially redundant with natural_habitat but client-selectable | Score-selectable; default scored |
| cpland | Core area percentage of target habitat / total landscape | Corrected to standard CPLAND definition; edge depth explicit | Scored; configuration indicator |
| forest_loss_rate | Hansen GFC loss within 2000 forest mask, divided by 2000 forest area and annualised | Corrected; inclusive year counts and numerator mask fixed; low baseline suppressed | Scored where baseline forest area is reliable |
| net_forest_change_rate | Hansen loss + contemporary Dynamic World tree expansion | Temporal gain signal is not annually resolved | Context only |
| kba_overlap | KBA spatial overlap | Conservation screening, not condition | Screening |
| ndvi | Sentinel-2 annual median NDVI | Valid vegetation condition proxy; not a direct biodiversity observation, but valid for reference-relative condition scoring | Score-selectable; default scored |
| habitat_health | NDVI-derived z5/SD construct | Quantitative habitat-condition derivative; correlated with NDVI and therefore user-selectable | Score-selectable; default scored |
| flii | Canonical Grantham FLII raster required | Former Darukaa proxy was not the published FLII | Scored only when canonical raster supplied; otherwise pending input |
| eii | External EII asset | Valid external composite; redundancy with components is a selection issue rather than a calculation failure | Score-selectable; default scored |
| eii_structural | External EII structural band | Valid if source band passes QA; can be scored independently with source/coverage caveat | Score-selectable; default scored |
| eii_compositional | External EII compositional band | Valid biodiversity-composition signal; correlation with BII should be assessed, not assumed | Score-selectable; default scored |
| eii_functional | External EII functional band | Valid functional condition signal when the external band is available and QA-passed | Score-selectable; default scored |
| bii | Impact Observatory/Vizzuality 100m PREDICTS-based BII v1.1 | Appropriate independent biodiversity-intactness layer; EII fallback removed | Scored |
| pdf | Dynamic World land-cover coefficients | Quantitative land-use biodiversity-loss proxy; label remains explicit and is client-selectable | Score-selectable; default scored |
| aridity_index | CHIRPS / TerraClimate | Climate exposure context; retained hard-context because it is not an anthropogenic pressure or site condition metric | Context-only |
| tspi | NDCI → chlorophyll-a → Carlson TSI(Chl) | Literature-supported chain; aquatic applicability required | Scored in aquatic profile |
| sabf | FAI > 0.005 frequency | Quantitative aquatic bloom-proxy metric; threshold/frequency caveat is explicit | Score-selectable; default scored |
| wcpi | Nechad turbidity inversion | Quantitative aquatic clarity proxy; only score when the implementation uses a comparable absolute/standardized scale | Score-selectable after scale QA |
| wsdi | Sentinel-1 water occurrence dynamism | Quantitative aquatic surface-dynamics metric; direction/target must follow the declared aquatic profile | Score-selectable; default scored |
| hsas | NDVI + water proximity + disturbance + eDNA alignment | Custom composite; score only when required eDNA evidence is present and label remains proxy | Score-selectable; default scored but evidence-gated |
| edpp | Thermal/turbidity/moisture/UV composite | Custom composite; quantitative and selectable, with proxy caveat | Score-selectable; default scored |
| mspl | Nutrient/thermal/turbidity/water-persistence weighted composite | Custom composite; quantitative and selectable, with proxy caveat | Score-selectable; default scored |
| rci | Riparian vegetation composite | Quantitative riparian condition proxy; weights remain declared and user-selectable | Score-selectable; default scored |
| riparian_ndvi_trend | NDVI temporal slope | Useful monitoring context; short-window slope is not a standalone condition score | Context |
| jrc_water_persistence | Sentinel-1 persistent-water proxy | Quantitative water-persistence metric; legacy key retained for compatibility | Score-selectable; default scored where applicable |
| shdi | Shoreline morphometric scalar | Current implementation remains hard-context because the scalar is not spatially benchmarkable | Context-only |
| lai | MODIS LAI | Valid structural proxy; coarse MODIS grain is a QA/applicability constraint, not a reason to prohibit scoring | Score-selectable; default scored where support is adequate |
| chm | ETH Global Canopy Height 2020, 10m | Direct structural measurement; fixed 2020 snapshot must be disclosed | Scored |
| endemic_richness | IUCN range-overlap density | Screening/proxy, not observed richness | Screening |
| shi | Map of Life/API placeholder | External dependency not guaranteed | Context/pending input |
| flagship_habitat | Generic HSI without named flagship species | Ecological target is under-specified | Context |
| endemic_plant_richness | Plant range-overlap density | Screening/proxy | Screening |
| threatened_richness | Threatened species range-overlap density | Pressure/conservation-priority screening, not direct site condition | Screening |
| ceri | Red-list extinction-risk composite | Previous aggregation was mathematically perverse | Removed |
| star_t | STAR threat-abatement opportunity | Conservation opportunity, not condition | Context |
| threatened_plant_richness | Threatened plant range-overlap density | Screening | Screening |
| ghm | TNC Global Human Modification | Anthropogenic pressure; reference must not be low-HMI-selected | Scored on P4 pressure axis with ecological-only reference |
| light_pollution | VIIRS night-time radiance | Direct pressure proxy; separate from condition | Scored on P4 |
| hdi | Built-up proximity/disturbance proxy | Custom built-up pressure, not a published generic HDI | Scored on P4 with explicit custom definition |
| lst_day | MODIS daytime LST | Climate/exposure context | Context |
| lst_night | MODIS night-time LST | Climate/exposure context | Context |
| sdi | Shoreline disturbed-cover fraction | Useful pressure proxy but custom shoreline definition | Context until independently validated |
| stsi | Landsat surface-temperature within-site normalisation | Site-relative normalisation is not cross-site comparable | Context |
| iri | Custom invasive-risk composite | Quantitative pressure-risk proxy; remains hard-context until the weighting/validation issue is resolved | Context-only |
| ivsi | NDVI expansion signal | Detects vegetation expansion, not biological invasion | Context |

## High-priority conclusions

### BII
The pipeline now uses the independent 100m Impact Observatory/Vizzuality PREDICTS-based BII dataset directly. The EII compositional fallback has been removed. If the independent source is unavailable, BII is `pending_input` rather than a relabelled EII value.

### FLII
The previous Darukaa reconstruction is not the published Forest Landscape Integrity Index. The metric key remains for compatibility, but headline FLII scoring now requires the canonical Grantham et al. (2020) raster. No proxy is silently substituted.

### CHM
The metric uses the ETH Global Canopy Height 2020 product at 10m GSD. The product is a 2020 snapshot, not an annual current CHM. Site and reference values are spatial summaries of valid mapped canopy-height pixels.

### Tree-cover loss
The numerator now uses only loss pixels inside the same 2000 forest mask used for the denominator. Hansen 2001–2025 contains 25 annual observations; the previous 24-year divisor was wrong. The recent windows are similarly corrected to 6 and 3 years for 2020–2025 and 2023–2025.

The metric is therefore **Tree Cover Loss Rate under a declared 30% 2000 tree-cover threshold**, not a generic measure of all vegetation loss. Absolute loss area is retained for small-baseline EMUs; percentage scoring is suppressed when the baseline is too small to support a stable rate.

### CPLAND
CPLAND is now explicitly implemented as the standard **Core Area Percentage of Landscape**: summed core area of the target habitat class divided by total landscape area ×100, with an explicit edge-depth parameter. It should not be described as a generic graph-theoretic connectivity index.

The current Plan Vivo PV Nature methodology should not be conflated with this metric: PV Nature v1.2 quantifies within-site biodiversity change against the site's own Year-0 baseline and does not use measured or theoretical reference sites for PVBC quantification. Its terrestrial Pillar 4 uses the spatial distribution of Sentinel-2 NDVI. CPLAND is therefore an independent landscape-configuration indicator, not a PV Nature PVBC pillar metric.

## Acceptance rule

A metric can be technically executable and still fail scientific acceptance. The production package should only headline-score a metric when its definition, source, spatial/temporal scale, applicability, direction and reference basis are all defensible. Unvalidated custom composites remain visible as context rather than being converted into apparently precise biodiversity scores.

## 2026-10-05 metric-selection revision

The earlier audit was too conservative in one respect: it treated many valid quantitative indicators as context-only because they were not part of the legacy 20-indicator default score. That conflated **scientific scoreability** with **parsimony/redundancy preference**.

The production contract now separates these concepts:

- **default_scored**: the metric has a quantitative calculation, defensible direction and a reference/benchmark route. It is scored by default.
- **context_only**: the metric is useful but its current formulation is not suitable for a headline reference-relative score.
- **diagnostic**: screening/representation metric; never enters condition scoring.
- **removed**: construct is not accepted.

Any `default_scored` metric can be demoted in the Colab notebook using `METRIC_OVERRIDES = {"metric_name": "contextual"}`. This does not alter the calculator. Hard context/diagnostic/removed metrics cannot be promoted by a client override.

Current legacy inventory classification: **30 default-scoreable, 10 hard-context, 5 diagnostic, 1 removed**. This deliberately brings back legitimate scoreable metrics such as `ndvi`, `habitat_health`, `eii`, `eii_structural`, `eii_compositional`, `eii_functional`, `lai`, `natural_landcover`, and several aquatic/context indicators, while retaining hard gates where the construct itself is not suitable for a headline score.

### BII asset decision

The old v0.1.0 README listed `projects/landler-open-data/assets/eii/global/eii_global_v1` as an EII+BII asset and `projects/gaurav-singh-007/assets/bii-2020_v2-1-1` as a user-upload fallback. Those are not preferable to the current independent BII source. The v0.2.7 implementation already switched to `projects/ebx-data/assets/earthblox/IO/BII_V1_1`, an annual 100 m 2017-2025 Impact Observatory/Vizzuality dataset. The September 2026 release confirms the extension through 2025. This remains the production primary; no EII-derived BII fallback is permitted.

### Canopy height decision

The previous ETH 10 m product was scientifically defensible but not the only valid canopy-height source. The Meta/WRI High Resolution Canopy Height Maps GEE collection provides approximately 1 m wall-to-wall canopy height and is better suited to small EMUs because it preserves fine structural heterogeneity. Most source imagery is concentrated in 2018-2020, so it is still a baseline structural surface rather than a live annual CHM. The package now uses the Meta/WRI GEE collection as the primary CHM source and the ETH 10 m 2020 map as fallback.

Meta/WRI released CHMv2 in March 2026 with substantially improved reported accuracy and global consistency, but the current public v2 distribution is exposed through the Meta/WRI AWS/open-data workflow and the model/inference code; a verified stable GEE asset was not established for this package. CHMv2 should therefore be treated as the next source-upgrade candidate rather than silently substituted.

### Tree-cover loss versus growth

`forest_loss_rate` is intentionally **gross tree-cover loss rate**. A gain cannot mathematically cancel a loss inside that metric because loss and gain are different ecological processes. The package therefore retains gain/net-change information separately. A positive net-change signal is useful for restoration, but it should not be mislabeled as a corrected loss rate. The current net-change proxy remains context-only until its gain definition is made temporally and ecologically symmetric with the Hansen loss series.

### Reference calculation rule

For every scoreable metric, the site value and reference value use the same calculator and the same metric definition. The reference is a population/geometry matched to the EMU, not a single arbitrary reference pixel. The reference distribution is retained with mean, median, SD and percentiles; the metric's declared estimator determines whether mean or median is used as the benchmark.


## 2026-10-05 EII hierarchy and source-contract implementation

The final implementation separates **metric scoreability** from **simultaneous contribution**.

### EII hierarchy

The Landbanking EII parent is a composite of structural, compositional and functional integrity. The package therefore exposes an explicit runtime gate:

- `eii_mode = "components"` (default): score `eii_structural`, `eii_compositional`, and `eii_functional`; retain parent `eii` as contextual/diagnostic.
- `eii_mode = "parent"`: score the parent `eii`; retain all three components as contextual/diagnostic.
- `eii_mode = "none"`: retain all EII layers as contextual/diagnostic.

A metric override cannot promote an EII layer excluded by the selected hierarchy. This prevents parent-plus-component double counting while preserving the option to use the published parent index as the headline.

The independent PREDICTS-based BII remains a separate P3 biodiversity-integrity metric. It is not derived from the EII compositional band and has no EII-derived fallback.

### Current source metadata

The registry's v1.1.0 source contract now records the calculators actually shipped by this package rather than stale legacy metadata:

- EII parent/components: Landbanking EII global asset, approximately 300 m.
- BII: Impact Observatory/Vizzuality BII v1.1, 100 m, `BII_V1_1`.
- CHM: Meta/WRI High Resolution Canopy Height Maps GEE collection, approximately 1 m, with ETH Global Canopy Height 2020 retained as calculator fallback.

The CHM product is a structural baseline surface, not an annual current-condition series; its source imagery is concentrated around 2018–2020. CHMv2 is not silently substituted because a stable verified GEE asset was not established for this release.

### Reference execution clarification

The active v1.1.0 reference engine does **not** use the legacy 5,000-pixel `sample()`/retry ladder. That 5,000-pixel setting exists only in the vendored `legacy_reference` implementation retained for historical calculator compatibility. The active reference engine constructs an ecologically matched candidate geometry, applies the finite HMI policy, and benchmarks each scoreable metric over the resulting candidate population using the same metric calculator.

Therefore no legacy `reference_sample_pixels` setting is part of the active v1.1.0 reference contract.
