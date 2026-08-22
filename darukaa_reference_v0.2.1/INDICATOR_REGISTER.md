# Indicator Register — darukaa_reference v0.2.0

Generated programmatically from `create_default_registry()` — the authoritative, machine-readable source. Do not hand-edit; regenerate after any registry change.

**Totals:** 44 registered · 10 scored · 33 contextual · 6 screening-only · 1 removed.

Scored = active AND computed-eligible (has reference + uncertainty + baseline tier, no unmet dependencies). Eligibility is computed, never hand-set.


## C1 · Landscape context & extent

| Indicator | Subdim | Disposition | Scored | Evidence | Scale | Estimator | Ref type | Inputs | Note |
|---|---|---|---|---|---|---|---|---|---|
| `cpland` | configuration | redefine | ✅ | baseline | ratio | robust_z | regional_distribution | india_pv_binary | Connectivity; state ecological scale (D8). Fragmentation suite to be a |
| `forest_loss_rate` | disturbance_regime | redefine | ✅ | baseline | ratio | log_response_ratio | regional_distribution | hansen_gfc | Change indicator; needs accuracy assessment (D4); low-baseline reliabi |
| `kba_overlap` | extent | screening | — | screening | bounded | — | — | kba | Proximity/overlap = screening, not site condition (F-style). |
| `natural_habitat` | extent | retain | ✅ | baseline | ratio | log_response_ratio | contemporary_best_on_offer | dynamic_world | Core extent metric; ratio-scale, true zero. |
| `natural_landcover` | extent | context | — | contextual | ratio | — | — | dynamic_world | Gate A: shares Dynamic World with natural_habitat -> demote (Fault 1/B |
| `flii` | forest_integrity | retain | ✅ | baseline | bounded | robust_z | published_threshold | flii_asset | Forest realm only (applicability precondition exists). NPI IND3 landsc |
| `jrc_water_persistence` | hydrology | retain | ✅ | baseline | ratio | log_response_ratio | regional_distribution | jrc_water | Hydrology/surface-water permanence. |
| `rci` | hydrology | context | — | contextual | bounded | — | — | sentinel2_ndvi | Riparian complexity; riparian strata only. Citation corrected (Naiman  |
| `riparian_ndvi_trend` | hydrology | context | — | contextual | interval | — | — | sentinel2_ndvi | Trend-based (correct NDVI use); contextual at cycle-1. |

## C2 · Vegetation condition

| Indicator | Subdim | Disposition | Scored | Evidence | Scale | Estimator | Ref type | Inputs | Note |
|---|---|---|---|---|---|---|---|---|---|
| `bii` | composition | context | — | contextual | bounded | — | — | predicts_bii | Modelled -> contextual, not baseline (NPI 'modelled, not responsive'). |
| `eii_compositional` | composition | context | — | contextual | bounded | — | — | landbanking_eii | Diagnostic context under parent EII. |
| `pdf` | composition | context | — | contextual | bounded | — | — | lc_impact_pdf | LCA-derived; ratio intactness invalid; not field-verifiable. |
| `eii_functional` | function | context | — | contextual | bounded | — | — | landbanking_eii | Diagnostic context under parent EII. |
| `eii` | integrity | retain | ✅ | baseline | bounded | robust_z | contemporary_best_on_offer | landbanking_eii | SCORED at PARENT (Landbanking fuzzy-min = non-compensatory, Q4). Compo |
| `chm` | structure | retain | ✅ | baseline | ratio | log_response_ratio | contemporary_best_on_offer | gedi_chm | Genuinely additive: GEDI canopy height, independent of NDVI/DW cluster |
| `eii_structural` | structure | context | — | contextual | bounded | — | — | landbanking_eii | Diagnostic context under parent EII (B2 double-count). |
| `habitat_health` | structure | context | — | contextual | bounded | — | — | sentinel2_ndvi | z-score construct; overlaps NDVI (Gate A). |
| `lai` | structure | context | — | contextual | ratio | — | — | modis_lai | Shares greenness with NDVI; MODIS grain too coarse for these sites. |
| `ndvi` | structure | context | — | contextual | interval | — | — | sentinel2_ndvi | Not ratio-scale; remove from intactness. Keep as trend/context (B1). |
| `edpp` | water_quality | context | — | contextual | bounded | — | — | sentinel2 | Persistence model; contextual. |
| `hsas` | water_quality | context | — | contextual | bounded | — | — | edna_points | Suitability model; contextual until eDNA-validated. |
| `mspl` | water_quality | context | — | contextual | bounded | — | — | sentinel2 | Stress model; contextual. |
| `sabf` | water_quality | context | — | contextual | bounded | — | — | sentinel2 | Algal-bloom frequency; aquatic module. |
| `shdi` | water_quality | context | — | contextual | ratio | — | — | sentinel2 | Scalar-only morphometry; not cross-site comparable. |
| `tspi` | water_quality | context | — | contextual | interval | — | — | sentinel2 | Trophic-state proxy; needs external ref or trend-only. |
| `wcpi` | water_quality | context | — | contextual | bounded | — | — | sentinel2 | Water-clarity proxy; aquatic module. |
| `wsdi` | water_quality | context | — | contextual | bounded | — | — | sentinel2 | Surface-dynamics; aquatic module. |

## C3 · Faunal condition

| Indicator | Subdim | Disposition | Scored | Evidence | Scale | Estimator | Ref type | Inputs | Note |
|---|---|---|---|---|---|---|---|---|---|
| `flagship_habitat` | habitat_suitability | context | — | contextual | bounded | — | — | sentinel2_ndvi | No named flagship species; weights unjustified (G3). Demote unless red |
| `ceri` | representation | remove | — | screening | bounded | — | — | iucn_range_maps | Averaging Red List weights is arithmetically perverse: adding common s |
| `endemic_plant_richness` | representation | screening | — | screening | ratio | — | — | iucn_range_maps | Range-map derived -> screening. |
| `endemic_richness` | representation | screening | — | screening | ratio | — | — | iucn_range_maps | Range-map derived -> screening, not observation. |
| `star_t` | representation | context | — | contextual | ratio | — | — | iucn_range_maps | Threat-abatement OPPORTUNITY, not site condition. Prioritisation narra |
| `threatened_plant_richness` | representation | screening | — | screening | ratio | — | — | iucn_range_maps | Same construct/defect as threatened_richness. |
| `threatened_richness` | representation | screening | — | screening | ratio | — | — | iucn_range_maps | Identical across co-located sites -> zero discrimination (F1). Screeni |

## C4 · Pressures & human interface

| Indicator | Subdim | Disposition | Scored | Evidence | Scale | Estimator | Ref type | Inputs | Note |
|---|---|---|---|---|---|---|---|---|---|
| `aridity_index` | climate_exposure | context | — | contextual | interval | — | — | chirps_terraclimate | Climate context; moved from C2 to C4 climate exposure. |
| `lst_day` | climate_exposure | context | — | contextual | interval | — | — | modis_lst | Temperature = exposure, not a manageable pressure. Climate-exposure co |
| `lst_night` | climate_exposure | context | — | contextual | interval | — | — | modis_lst | Climate-exposure context. |
| `iri` | direct_pressure | context | — | contextual | bounded | — | — | sentinel2_ndvi | Invasive RISK model; contextual until field-validated. |
| `ivsi` | direct_pressure | context | — | contextual | bounded | — | — | sentinel2_ndvi | Detects NDVI expansion, not taxonomic invasion (own docstring). Must N |
| `light_pollution` | direct_pressure | retain | ✅ | baseline | bounded | robust_z | regional_distribution | viirs_ntl | Distinct pressure, independent input (VIIRS). |
| `sdi` | direct_pressure | context | — | contextual | bounded | — | — | sentinel2 | Aquatic shoreline disturbance; aquatic module. |
| `stsi` | direct_pressure | context | — | contextual | bounded | — | — | modis_lst | Site-relative normalisation only; not cross-site comparable. |
| `ghm` | land_use_pressure | retain | ✅ | baseline | bounded | robust_z | regional_distribution | csp_ghm | THE land-use pressure metric. Pressure axis, NOT condition. Circularit |
| `hdi` | land_use_pressure | redefine | ✅ | baseline | bounded | robust_z | regional_distribution | dw_builtup | Rename to built-up/settlement pressure; health-adjusted HDI citation i |
