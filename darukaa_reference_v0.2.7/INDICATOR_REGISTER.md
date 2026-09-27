# Indicator Register — darukaa_reference

Generated programmatically from `create_default_registry()` by `generate_indicator_register.py` — the authoritative, machine-readable source. Do not hand-edit the table columns; re-run the generator after any registry/contract change (it preserves the free-text Note column from whatever is currently on disk).

**Totals:** 46 registered · 20 scored · 20 contextual · 6 screening-only · 1 removed.

Scored = active AND computed-eligible (has reference + uncertainty + baseline tier, no unmet dependencies). Eligibility is computed, never hand-set. **Realms** = which of terrestrial/aquatic/mixed this indicator is valid for — checked directly against real extraction logic for every indicator (not assumed from a module tag); see CHANGELOG.md's real per-indicator classification.


## C1 · Landscape context & extent

| Indicator | Subdim | Disposition | Scored | Evidence | Scale | Estimator | Ref type | Realms | Inputs | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| `cpland` | configuration | retain | ✅ | baseline | ratio | robust_z | regional_distribution | terr/mixe | india_pv_binary | Connectivity; state ecological scale (D8). Fragmentation suite to be added. |
| `forest_loss_rate` | disturbance_regime | retain | ✅ | baseline | ratio | log_response_ratio | regional_distribution | terr/mixe | hansen_gfc | Change indicator; needs accuracy assessment (D4); low-baseline reliability flag; report wi |
| `kba_overlap` | extent | screening | — | screening | bounded | — | — | terr/aqua/mixe | kba | Proximity/overlap = screening, not site condition (F-style). |
| `natural_habitat` | extent | retain | ✅ | baseline | ratio | log_response_ratio | contemporary_best_on_offer | terr/mixe | dynamic_world | Core extent metric; ratio-scale, true zero. |
| `natural_landcover` | extent | context | — | contextual | ratio | — | — | terr/mixe | dynamic_world | Gate A: shares Dynamic World with natural_habitat -> demote (Fault 1/B1). |
| `flii` | forest_integrity | retain | ✅ | baseline | bounded | robust_z | contemporary_best_on_offer | terr/mixe | flii_asset | Forest realm only. v0.2.1: renamed from 'FLII' — this is a Darukaa-computed proxy (VIIRS + |
| `jrc_water_persistence` | hydrology | retain | ✅ | baseline | ratio | log_response_ratio | regional_distribution | terr/aqua/mixe | jrc_water | Hydrology/surface-water permanence. |
| `riparian_ndvi_trend` | hydrology | context | — | contextual | interval | — | — | terr/aqua/mixe | sentinel2_ndvi | Trend-based (correct NDVI use); contextual at cycle-1. |
| `net_forest_change_rate` | restoration_trajectory | retain | ✅ | baseline | interval | robust_z | regional_distribution | terr/mixe | hansen_gfc, dynamic_world |  |
| `rci` | riparian_complexity | retain | ✅ | baseline | bounded | robust_z | regional_distribution | terr/aqua/mixe | sentinel2_ndvi | Riparian complexity; riparian strata only. Citation corrected (Naiman & Decamps 1997). |

## C2 · Vegetation condition

| Indicator | Subdim | Disposition | Scored | Evidence | Scale | Estimator | Ref type | Realms | Inputs | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| `sabf` | algal_bloom_frequency | retain | ✅ | baseline | bounded | robust_z | regional_distribution | aqua/mixe | sentinel2 | Algal-bloom frequency; aquatic module. |
| `eii_compositional` | composition | context | — | contextual | bounded | — | — | terr/mixe | — | Diagnostic context under parent EII. |
| `pdf` | composition | context | — | contextual | bounded | — | — | terr/mixe | lc_impact_pdf | LCA-derived species-area-relationship metric (PDF = 1-(A_new/A_reference)^z; z~0.25 is the |
| `edpp` | edna_persistence | retain | ✅ | baseline | bounded | robust_z | regional_distribution | aqua/mixe | sentinel2 | Persistence model; contextual. |
| `eii_structural` | eii_structure | context | — | contextual | bounded | — | — | terr/mixe | — | Diagnostic context under parent EII (B2 double-count). |
| `eii_functional` | function | context | — | contextual | bounded | — | — | terr/mixe | — | Diagnostic context under parent EII. |
| `hsas` | habitat_suitability | retain | ✅ | baseline | bounded | robust_z | regional_distribution | aqua/mixe | edna_points | Suitability model; contextual until eDNA-validated. |
| `eii` | integrity | context | — | contextual | bounded | — | — | terr/mixe | landbanking_eii | STALE NOTE CORRECTED (item 19): this row previously said "SCORED at PARENT" -- DEMOTED to context; its 3 sub-scores (eii_structural/compositional/functional) are scored separately instead, ALL 3 currently SUSPENDED pending an unresolved anomaly (independent audit item 5) -- nothing EII-related is currently scored. See OPEN_DECISIONS.md OD-C4. |
| `mspl` | microbial_stress | retain | ✅ | baseline | bounded | robust_z | regional_distribution | aqua/mixe | sentinel2 | Stress model; contextual. |
| `chm` | structure | retain | ✅ | baseline | ratio | log_response_ratio | contemporary_best_on_offer | terr/mixe | gedi_chm | Genuinely additive, independent of NDVI/DW cluster. STALE NOTE CORRECTED (item 19): live asset is ETH Global Canopy Height 2020 (10m), not GEDI -- switched to fix widespread site_value=None from GEDI's sparse orbital sampling; see ASSUMPTIONS_AND_LIMITATIONS.md §15. |
| `habitat_health` | structure | context | — | contextual | bounded | — | — | terr/mixe | sentinel2_ndvi | z-score construct; overlaps NDVI (Gate A). |
| `lai` | structure | context | — | contextual | ratio | — | — | terr/mixe | modis_lai | Shares greenness with NDVI; MODIS grain too coarse for these sites. |
| `ndvi` | structure | context | — | contextual | interval | — | — | terr/mixe | sentinel2_ndvi | Not ratio-scale; remove from intactness. Keep as trend/context (B1). |
| `wcpi` | water_clarity | retain | ✅ | baseline | bounded | robust_z | regional_distribution | aqua/mixe | sentinel2 | Water-clarity proxy; aquatic module. |
| `shdi` | water_quality | context | — | contextual | ratio | — | — | aqua/mixe | sentinel2 | Scalar-only morphometry; not cross-site comparable. |
| `tspi` | water_quality | retain | ✅ | baseline | interval | robust_z | published_threshold | aqua/mixe | sentinel2 | v0.2.5: upgraded from a bare NDCI proxy to the real Carlson (1977) TSI(Chl) formula via Mi |
| `wsdi` | water_surface_dynamics | context | — | contextual | bounded | — | — | aqua/mixe | sentinel2 | Surface-dynamics; aquatic module. |

## C3 · Faunal condition

| Indicator | Subdim | Disposition | Scored | Evidence | Scale | Estimator | Ref type | Realms | Inputs | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| `bii` | abundance_intactness | retain | ✅ | baseline | bounded | robust_z | contemporary_best_on_offer | terr/mixe | predicts_bii | v0.2.4: moved C2->C3 and promoted context->scored — this is C3's real signal, closing the |
| `shi` | habitat_intactness | context | — | contextual | bounded | — | — | terr/aqua/mixe | mol_api | OD-12 placeholder: real, defensible metric once Map of Life API access is confirmed (no simple GEE asset exists). Gated by requires=["mol_api_credentials"] until then. |
| `flagship_habitat` | habitat_suitability | context | — | contextual | bounded | — | — | terr/mixe | sentinel2_ndvi | No named flagship species; weights unjustified (G3). Demote unless redesigned around a nam |
| `ceri` | representation | remove | — | screening | bounded | — | — | terr/aqua/mixe | iucn_range_maps | Averaging Red List weights is arithmetically perverse: adding common species LOWERS risk ( |
| `endemic_plant_richness` | representation | screening | — | screening | ratio | — | — | terr/aqua/mixe | iucn_range_maps | Range-map derived -> screening. |
| `endemic_richness` | representation | screening | — | screening | ratio | — | — | terr/aqua/mixe | iucn_range_maps | Range-map derived -> screening, not observation. |
| `star_t` | representation | context | — | contextual | ratio | — | — | terr/mixe | iucn_range_maps | Threat-abatement OPPORTUNITY, not site condition. Prioritisation narrative only. NPI IND4 |
| `threatened_plant_richness` | representation | screening | — | screening | ratio | — | — | terr/aqua/mixe | iucn_range_maps | Same construct/defect as threatened_richness. |
| `threatened_richness` | representation | screening | — | screening | ratio | — | — | terr/aqua/mixe | iucn_range_maps | Identical across co-located sites -> zero discrimination (F1). Screening-only priority lis |

## C4 · Pressures & human interface

| Indicator | Subdim | Disposition | Scored | Evidence | Scale | Estimator | Ref type | Realms | Inputs | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| `hdi` | built_up_pressure | retain | ✅ | baseline | bounded | robust_z | regional_distribution | terr/aqua/mixe | dw_builtup | Rename to built-up/settlement pressure; health-adjusted HDI citation is WRONG (G4). Check |
| `aridity_index` | climate_exposure | context | — | contextual | interval | — | — | terr/aqua/mixe | chirps_terraclimate | Climate context; moved from C2 to C4 climate exposure. |
| `lst_day` | climate_exposure | context | — | contextual | interval | — | — | terr/aqua/mixe | modis_lst | Temperature = exposure, not a manageable pressure. Climate-exposure context. |
| `lst_night` | climate_exposure | context | — | contextual | interval | — | — | terr/aqua/mixe | modis_lst | Climate-exposure context. |
| `ivsi` | direct_pressure | context | — | contextual | bounded | — | — | terr/mixe | sentinel2_ndvi | Detects NDVI expansion, not taxonomic invasion (own docstring). Must NOT be labelled invas |
| `light_pollution` | direct_pressure | retain | ✅ | baseline | bounded | robust_z | regional_distribution | terr/aqua/mixe | viirs_ntl | Distinct pressure, independent input (VIIRS). |
| `stsi` | direct_pressure | context | — | contextual | bounded | — | — | terr/aqua/mixe | modis_lst | Site-relative normalisation only; not cross-site comparable. |
| `iri` | invasive_risk | retain | ✅ | baseline | bounded | robust_z | regional_distribution | terr/aqua/mixe | sentinel2_ndvi | Invasive RISK model; contextual until field-validated. |
| `ghm` | land_use_pressure | retain | ✅ | baseline | bounded | robust_z | regional_distribution | terr/aqua/mixe | csp_ghm | THE land-use pressure metric. Pressure axis, NOT condition. Circularity (Fault 2): if gHM |
| `sdi` | shoreline_disturbance | retain | ✅ | baseline | bounded | robust_z | regional_distribution | aqua/mixe | sentinel2 | Aquatic shoreline disturbance; aquatic module. |
