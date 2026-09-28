# Indicator Audit Matrix — darukaa_reference v0.2.7

**Scope.** All 46 registered indicators (45 active + `ceri`, removed). No code was changed and nothing was committed for this audit.
**Commit audited:** `be73839` (population-restricted sampler) on `main`.

## How each finding was established

| Tag | What it means |
|---|---|
| **code** | I read the site extraction (`extract_*`) and the reference image (`_img_*`, taken as band 0) for this indicator in the audited commit. |
| **live** | Observed in the EMU_Deccan_forest single-tile run JSON (commit `be73839`, 35.6 min). |
| **verified** | Checked against a primary source during this project (dataset catalog or paper). |
| **unverified** | Stated from general knowledge or repo text and needs checking before it is relied on. |

The aquatic tiles have never been run live. Every aquatic finding below comes from reading the code only.

---

## 1. Cross-cutting defects

These eleven patterns explain almost every indicator-level problem. Fixing them as patterns, rather than indicator by indicator, is what makes the assessment audit-proof.

| ID | Defect | Where it occurs | Why it matters |
|---|---|---|---|
| **X1** | **Support mismatch.** The site value is a mean over the whole site polygon, but the reference is a distribution of *single pixels*. | Every GEE indicator. It is severe where the pixels are binary or categorical: `natural_habitat`, `natural_landcover`, `jrc_water_persistence`, `sdi`, `ivsi`, `cpland`, `forest_loss_rate`, `net_forest_change_rate`. | For a 0/1 image, a site proportion (e.g. 81.6 % natural) is compared with a reference median that can only be 0 or 100, and a MAD that is usually 0. For continuous images, a polygon mean is compared with a pixel distribution whose spread is larger than the spread of site-sized means, so the site's percentile is misplaced. |
| **X2** | **Selection on the outcome in Tier 2.** The reference pool is selected by a variable that determines the indicator. | (a) Dynamic World (DW) label indicators stratified by the DW label: `natural_habitat` (97 % of reference pixels = 100, live), `natural_landcover`, `pdf` (96 % = 0.1, live), and the `net_forest_change_rate` reference (median 1, live). (b) The HMI selector is a *direct input* of `flii` (its pressure term P is the TNC HM layer). (c) HMI is *correlated with the inputs* of the modelled products `bii` and `eii_structural`. | (a) and (b) produce a reference that is degenerate or circular by construction. (c) partly restates pressure as "condition" and needs disclosure plus a sensitivity test. |
| **X3** | **Site-relative normalisation.** The site value is min-max scaled by the site polygon's own min and max. | `wcpi`, `edpp`, `mspl`, `stsi` (code) | A value normalised by its own range cannot be compared with any reference, with any other site, or with the same site in another year. |
| **X4** | **Multi-band reference image; the sampler takes band 0.** | `edpp`, `mspl`: band 0 is land-surface temperature (LST) in °C (code) | The Tier-1 "reference" is a temperature, while the site value is a 0–1 index. |
| **X5** | **Population mismatch.** The site is computed on a sub-domain (water mask, riparian ring, shore buffer); the reference is computed on all pixels. | `rci`, `riparian_ndvi_trend`, `sdi`, `jrc_water_persistence`, `hsas`. `sabf` has **no water mask at all**. (code) | Riparian or shore condition is compared with all land. For `sabf`, land vegetation always exceeds the bloom threshold (FAI > 0.005), so land reads as permanent "bloom". |
| **X6** | **Coarse product vs small site.** The product's pixel is larger than, or a large share of, the zone. | EII family (code reads it at 300 m; native resolution **unverified**), `lai` (500 m), `lst_*` (1 km), `aridity_index` (~4.6 km, verified), `light_pollution` (~463 m, unverified). `ghm`'s *site* value is read at **1,000 m** although its native pixel is 90 m (verified). | The site value describes the surrounding landscape, not the zone. This is the likely explanation of audit item 5: EII-structural = 0.0003 in an industrial 300 m setting, and EII = min(components) ≈ 0.0002 (live; the min rule is from the repo's OD-C4 note). That makes it a real landscape signal rather than a bug. |
| **X7** | **Sampling below the native pixel.** The reference is sampled at 100 m for products with 300 m to 4.6 km pixels. | `aridity_index`, EII family, `lai`, `lst_*`, `stsi` (code) | Each coarse cell is counted many times (pseudo-replication). The stability gate and MAD then look more certain than the data are. |
| **X8** | **Tier 2 is the wrong reference for pressures.** The least-disturbed Tier-2 pool is near-zero pressure by construction. | `ghm`, `hdi`, `light_pollution`, `sdi`, `iri` | Pressure should be expressed against the *regional* distribution (Tier 1) or against an absolute scale. "Tier 1 only" is the correct design for pressures, not a fallback, and they should be scoreable on Tier 1. |
| **X9** | **The status model conflates different states.** | Item-8 report labels (live) | Five Tier-1-referenced indicators are labelled `no_reference`. "Not applicable" and "no data" share codes. Tier-1 benchmarks are computed but not written to the scorecard. |
| **X10** | **Redundancy and subdimension collisions.** | `ndvi`, `habitat_health`, `lai` and `chm` all have subdimension `structure`. `eii_compositional` is BII-based (its fallback *is* BII; primary source unverified). `eii_structural` is human-modification-based (overlaps `ghm`). `flii` is built from HMI + forest cover (overlaps `ghm` + `natural_habitat`). `iri` and `mspl` reuse the NDCI signal behind `tspi`, and `iri` reuses built-up (`hdi`). (code) | Scoring more than one of these double-counts the same evidence, or triggers the within-subdimension averaging that item 2 removed. |
| **X11** | **Applicability only checks the realm, not the ecosystem type or the target feature.** | `chm`, `forest_loss_rate`, `net_forest_change_rate`, `flii` (need woody vegetation); water-quality indicators (need a minimum area of pure water) | For example, canopy height on a grassland zone, or chlorophyll on a pond with no pure-water pixels, produces a value that means nothing. |

**Benchmark formulas (code).** B is the signed benchmark; positive is always better.

- **Log response ratio:** `B = ±ln(site / ref_median)`. Defined only when site and reference are both > 0.
- **Robust z:** `B = ±(site − ref_median) / (1.4826 × MAD)`. Suppressed when MAD = 0.
- **Bounded 0–1 score:** `logistic(k × B)`, with k = 1.0 for the log ratio and k = 0.5 for robust z.
- **Sign (±):** + when higher is better, − when lower is better.

---

## 2. Indicator contract (current implementation)

**Abbreviations.** T = terrestrial, A = aquatic, M = mixed. C1 = landscape, C2 = vegetation/water, C3 = fauna, C4 = pressure. S2 = Sentinel-2, S1 = Sentinel-1, DW = Dynamic World, L8 = Landsat 8. "poly" = mean over the site polygon. "px" = single-pixel distribution in the reference pool. ↑ = higher is better, ↓ = lower is better. LRR = log response ratio, rZ = robust z.

| # | Indicator | Domain | Pillar / subdim | Source (native res) | Site metric (support @ scale) | Reference metric (pool @ scale) | Tier now | Dir | Formula |
|---|---|---|---|---|---|---|---|---|---|
| 1 | natural_habitat | T,M | C1 extent | DW (10 m, unverified) | % natural DW classes, poly @10 | 0/100 per px @10 | T1+T2 | ↑ | LRR |
| 2 | natural_landcover | T,M | C1 extent | DW (10 m) | weighted naturalness 0/50/100, poly @10 | 0/50/100 per px @100 | T1+T2 | ↑ | — (context) |
| 3 | cpland | T,M | C1 configuration | Darukaa "PV binary" (provenance undocumented) | % core area after edge erosion, poly @native | **raw binary (not eroded)** per px @100 | T1 | ↑ | rZ |
| 4 | forest_loss_rate | T,M | C1 disturbance | Hansen GFC v1.13 (30 m) | gross loss %/yr over window, baseline ≥ 30 % canopy | **lossyear code (1–25) per px** @30 | T1+T2 | ↓ | LRR |
| 5 | net_forest_change_rate | T,M | C1 restoration | Hansen loss + DW trees | (gain − loss) %/yr, gain = DW trees now ∧ ¬Hansen 2000 forest | +1/0/−1 per px @30 | T1+T2 | ↑ | rZ |
| 6 | kba_overlap | T,A,M | C1 extent | KBA polygons | % site in a KBA | none | — | — | screening |
| 7 | ndvi | T,M | C2 structure | S2 (10 m) | annual median NDVI, poly @10 | same, px @100 | T1+T2 | ↑ | — (context) |
| 8 | habitat_health | T,M | C2 structure | S2 (10 m) | p5(NDVI)/σ(NDVI) over the year, poly @10 | same, px @100 | T1+T2 | ↑ | — (context) |
| 9 | flii | T,M | C1 forest integrity | Darukaa proxy: TNC HM + DW | 10/3 × (3 − P − Q − LFC) on forest px, poly @30; not applicable if forest < 10 % | same, px @100 | T1+T2 | ↑ | rZ |
| 10 | eii | T,M | C2 integrity | Landler EII v1 (res. **unverified**; code assumes 300 m) | poly @300 | px @100 | T1+T2 | ↑ | — (context) |
| 11 | eii_structural | T,M | C2 | Landler EII | poly @300 | px @100 | T1+T2 | ↑ | — (context) |
| 12 | eii_compositional | T,M | C2 | Landler EII (fallback = BII) | poly @300 | px @100 | T1+T2 | ↑ | — (context) |
| 13 | eii_functional | T,M | C2 | Landler EII (fallback = MODIS NPP) | poly @300 | px @100 | T1+T2 | ↑ | — (context) |
| 14 | bii | T,M | C3 abundance | BII v1.1, 2017–2025 (100 m, verified) | poly @100 | px @100 | T1+T2 | ↑ | rZ |
| 15 | pdf | T,M | C2 composition | DW class → fixed coefficient | poly @10 | px @100 | T1+T2 | ↓ | — (context) |
| 16 | aridity_index | T,A,M | C4 climate | CHIRPS / TerraClimate (~4.6 km, verified) | P/PET, poly @5000 | px @100 | T1+T2 | ↑ | — (context) |
| 17 | tspi | A,M | C2 water quality | S2 NDCI → chl-a → Carlson TSI | TSI on water px (MNDWI > 0), poly @10 | same, px @10 (water px only) | T1 | ↓ | rZ |
| 18 | sabf | A,M | C2 algal bloom | S2 FAI (Hu 2009) | share of dates with FAI > 0.005, **no water mask**, poly @10 | same, **all px** @10 | T1 | ↓ | rZ |
| 19 | wcpi | A,M | C2 clarity | S2 red → TSM (Nechad-type), 1/(TSM+1) | **min-max normalised within the site** | raw 1/(TSM+1) px @10 | T1 | ↑ | rZ |
| 20 | wsdi | A,M | C2 surface dynamics | S1 VV water occurrence | 1 − 2·\|occ − 0.5\|, poly @10 | same px @10 | T1 | ↓ | — (context, item 15) |
| 21 | hsas | A,M | C2 habitat suitability | S2 NDVI + water/built distance (Darukaa weights) | suitability, or alignment with eDNA if an eDNA asset is given | **suitability** px @100 | T1 | ↑ | rZ (eDNA-gated, item 13) |
| 22 | edpp | A,M | C2 eDNA persistence | L8 LST + S2 + DW | 0–1 product with site-relative thermal term | **band 0 = LST °C** @10 | T1 | ↑ | rZ |
| 23 | mspl | A,M | C2 microbial stress | S2 NDCI + L8 LST + turbidity + persistence | weighted 0–1, site-relative thermal term | **band 0 = LST °C** @10 | T1 | ↓ | rZ |
| 24 | rci | T,A,M | C1 riparian complexity | S2 composite (Darukaa weights) | RCI in a 100 m ring around the largest water body | RCI on **all px** @10 | T1 | ↑ | rZ |
| 25 | riparian_ndvi_trend | T,A,M | C1 hydrology | S2 NDVI trend | trend in the 100 m ring | trend on **all px** @100 | T1 | ↑ | — (context) |
| 26 | jrc_water_persistence | T,A,M | C1 hydrology | S1 VV occurrence > 0.75 (not JRC since item 6) | persistent-water area / polygon area @30 | 0/1 per px @30 | T1 | ↑ | LRR |
| 27 | shdi | A,M | C2 | S2 water polygon | shoreline development index (perimeter/(2√(πA))) | none | — | ↑ (sic) | — (context) |
| 28 | lai | T,M | C2 structure | MODIS MCD15A3H (500 m, unverified) | poly @500 | px @100 | T1+T2 | ↑ | — (context) |
| 29 | chm | T,M | C2 structure | ETH Global Canopy Height 2020 (10 m) | poly @25 | px @10 | T1+T2 | ↑ | LRR |
| 30 | endemic_richness | T,A,M | C3 representation | range maps | species per 100 km² | none (Tier-1 n = 1, live) | — | ↑ | screening |
| 31 | shi | T,A,M | C3 | — | not computed (no image) | none | — | ↑ | context |
| 32 | flagship_habitat | T,M | C3 | range / habitat layer | index | none | — | ↑ | context |
| 33 | endemic_plant_richness | T,A,M | C3 | IUCN plants | count | none | — | ↑ | screening |
| 34 | threatened_richness | T,A,M | C3 | IUCN | species per 100 km² | none (Tier-1 n = 1, live) | — | ↓ | screening |
| 35 | ceri | T,A,M | C3 | — | removed | — | — | — | removed |
| 36 | star_t | T,M | C3 | STAR threat-abatement layer | score | none | — | ↑ | context |
| 37 | threatened_plant_richness | T,A,M | C3 | IUCN plants | count | none | — | ↓ | screening |
| 38 | ghm | T,A,M | C4 land use | TNC HM v3 (90 m, verified) | poly **@1000** | px @90 (Tier 2 = unfiltered stratum, item 3) | T1+T2 | ↓ | rZ |
| 39 | light_pollution | T,A,M | C4 direct | VIIRS DNB monthly (~463 m, unverified) | poly @500 | px @500 | T1 | ↓ | rZ |
| 40 | hdi | T,A,M | C4 built-up | DW built-up distance | 1 − dist/1500 m, poly @10 | px @10 | T1 | ↓ | rZ |
| 41 | lst_day | T,A,M | C4 climate | MODIS MOD11A1 (1 km) | poly @1000 | px @100 | T1 | ↓ | — (context) |
| 42 | lst_night | T,A,M | C4 climate | MODIS MOD11A1 (1 km) | poly @1000 | px @100 | T1 | ↓ | — (context) |
| 43 | sdi | A,M | C4 shoreline | DW disturbed classes | disturbed area / 100 m shore buffer | 0/1 per px, **all px** @10 | T1 | ↓ | rZ |
| 44 | stsi | T,A,M | C4 direct | L8 LST | **min-max normalised within the site** | raw LST °C px @100 | T1 | ↓ | — (context) |
| 45 | iri | T,A,M | C4 invasion risk | S2 + DW composite (Darukaa weights) | poly @10 | px @10 | T1 | ↓ | rZ |
| 46 | ivsi | T,M | C4 | S2 NDVI expansion > 0.2 vs 5 years earlier | area fraction of site | 0/1 px @100 | T1 | ↓ | — (context) |

---

## 3. Audit matrix (item 13, table 1)

"Scoreable?" is the *proposed* status after the required action, not the current one. ✅ = holds, ❌ = fails, ⚠ = holds only with a caveat or an unresolved condition, — = not applicable.

"Current reason" is the reason recorded on the terrestrial EMU_Deccan_forest tile. "A-only" means the indicator did not run because the tile is terrestrial and the indicator applies only to aquatic or mixed sites. Aquatic tiles have not been run.

| Indicator | Domain | Pillar | Site metric valid? | Ref metric valid? | Units compatible? | Tier 1 valid? | Tier 2 valid? | **Scoreable?** | Current reason (Deccan tile) | Required action |
|---|---|---|---|---|---|---|---|---|---|---|
| natural_habitat | T | C1 | ✅ | ❌ binary px + stratified on DW class (X1, X2a) | ⚠ nominal % only | ⚠ once support-matched | ❌ degenerate by construction | **A: yes** | scored (B = −0.20) | Absolute reference level (100 % natural) or support-matched ecoregion reference; drop DW-class stratification |
| natural_landcover | T | C1 | ✅ | ❌ same as natural_habitat | ⚠ | ⚠ | ❌ | C | contextual | Keep context (redundant with natural_habitat) |
| cpland | T | C1 | ✅ | ❌ un-eroded binary (live T1 ref = 0) | ❌ core % vs habitat 0/1 | ⚠ after fix | — | **A: conditional** | "no_reference" (mislabelled; T1 exists) | Build the reference from the same eroded core image, support-matched; **document the PV binary source first** |
| forest_loss_rate | T | C1 | ✅ (defined only if baseline ≥ 5 ha) | ❌ year codes (live ref = 16/17) | ❌ %/yr vs year | ⚠ after rebuild | ⚠ after rebuild | **A: yes, if applicable** | suppressed: baseline 0.01 ha | Rebuild the reference as the same rate: identical window, 30 % threshold, 5 ha floor, support-matched |
| net_forest_change_rate | T | C1 | ❌ gain compares two different products (DW now vs Hansen 2000) | ❌ ±1 proxy, median 1 (live) | ❌ | ❌ | ❌ | **C: pending** | suppressed: baseline 0.01 ha | Rebuild as change *within one product over time*, or retire to context |
| kba_overlap | T,A | C1 | ✅ designation, not condition | — | — | — | — | D | screening | none |
| ndvi | T | C2 | ✅ | ✅ same image | ✅ | ✅ | ✅ (DW label does not determine NDVI) | **A: yes** | contextual | Promote with its own subdimension ("greenness"), support-matched |
| habitat_health | T | C2 | ⚠ Darukaa index; penalises natural seasonality | ✅ same image | ✅ | ⚠ | ⚠ | C | contextual | Keep context until validated |
| flii | T | C1 | ⚠ proxy (not Grantham FLII) | ❌ HMI is both input and selector (X2b) | ✅ | ⚠ | ❌ circular | **C** | scored (B = −4.31) | Demote: its information duplicates ghm + natural_habitat (X10) |
| eii | T | C2 | ⚠ too coarse for zones (X6) | ✅ | ✅ | ⚠ | ⚠ | C | contextual (site 0.0002) | Context; landscape-level only |
| eii_structural | T | C2 | ⚠ X6 | ⚠ correlated with the HMI selector (X2c) | ✅ | ⚠ | ⚠ | C | contextual (site 0.0003) | Context; close item 5 as "real landscape signal" once EII resolution is confirmed |
| eii_compositional | T | C2 | ⚠ X6 | ✅ | ✅ | ⚠ | ⚠ | C | contextual | Context (redundant with bii) |
| eii_functional | T | C2 | ⚠ X6 | ✅ | ✅ | ⚠ | ⚠ | C (A only for large sites) | contextual | Context unless the site support rule is met |
| bii | T | C3 | ✅ at ≥ ~10 ha | ⚠ X2c (low-HMI pool) | ✅ | ✅ | ⚠ | **A: yes, with disclosure** | scored (B = −14.3) | Support-match; sensitivity test with the pool selected on ecoregion + PNV only |
| pdf | T | C2 | ⚠ DW label lookup | ❌ degenerate under DW stratification (live, 96 % = 0.1) | ✅ | ⚠ | ❌ | C | contextual (no benchmark: MAD = 0) | Keep context |
| aridity_index | T,A | C4 | ✅ climate, not condition | ⚠ X7 | ✅ | ⚠ | — | C | contextual | Context; sample at native ~4.6 km |
| tspi | A | C2 | ⚠ empirical chl-a coefficients; small-pond mixed pixels | ✅ water px | ✅ | ⚠ pool = all regional water | ❌ none yet | **B: yes** | A-only | Water-body-unit reference; minimum pure-water pixel guard |
| sabf | A | C2 | ❌ no water mask | ❌ land counted as bloom | ✅ nominal | ❌ | ❌ | **B: yes after fix** | A-only | Add the water mask to both; drop pixels adjacent to the shore |
| wcpi | A | C2 | ❌ site-relative (X3) | ✅ raw | ❌ | ⚠ | ❌ | **B: yes after fix** | A-only | Remove site-relative normalisation; use TSM or 1/(TSM+1) for both |
| wsdi | A | C2 | ✅ | ✅ | ✅ | ⚠ | — | C | context (item 15) | none |
| hsas | A | C2 | ⚠ 50 % NDVI-weighted (land-biased) | ❌ suitability ≠ eDNA alignment | ❌ | ❌ | ❌ | C: pending | A-only | Keep eDNA-gated; not an EO condition metric |
| edpp | A | C2 | ❌ site-relative (X3) | ❌ LST °C (X4) | ❌ | ❌ | ❌ | **D** | A-only | Reclassify: a survey-design aid, not biodiversity condition |
| mspl | A | C2 | ❌ site-relative (X3) | ❌ LST °C (X4) | ❌ | ❌ | ❌ | C | A-only | Demote (overlaps tspi and wcpi; unvalidated weights) |
| rci | T,A | C1 | ⚠ Darukaa composite | ❌ all px vs riparian ring (X5) | ✅ nominal | ❌ | ❌ | C: pending | no site value (no water on this tile) | Rebuild as riparian-ring vegetation cover vs reference rings |
| riparian_ndvi_trend | T,A | C1 | ✅ | ❌ X5 | ✅ | ❌ | ❌ | C | contextual | Fix the reference pool if kept |
| jrc_water_persistence | T,A | C1 | ⚠ low persistence is natural for seasonal ponds | ❌ binary px (X1) | ⚠ | ⚠ | — | **C** | "no_reference" (mislabelled; site 0, T1 ref 0) | Demote for consistency with the WSDI decision; not applicable on dry tiles |
| shdi | A | C2 | ✅ morphometry, not condition | — | — | — | — | C | context | none |
| lai | T | C2 | ⚠ X6 | ⚠ X7 | ✅ | ⚠ | ⚠ | C | contextual | Context |
| chm | T | C2 | ✅ 2020 baseline only (X11: woody strata only) | ✅ | ✅ | ✅ | ✅ | **A: yes** | scored (B = −0.48) | Site read at native 10 m; support-match; woody-ecosystem applicability; mark as static baseline |
| endemic_richness | T,A | C3 | ✅ representation | — | — | — | — | D | screening | none |
| shi | T,A | C3 | ❌ not computed | — | — | — | — | D | context | none |
| flagship_habitat | T | C3 | ✅ | — | — | — | — | D | context | none |
| endemic_plant_richness | T,A | C3 | ✅ | — | — | — | — | D | screening | none |
| threatened_richness | T,A | C3 | ✅ | — | — | — | — | D | screening | none |
| ceri | — | C3 | — | — | — | — | — | removed | removed | none |
| star_t | T | C3 | ✅ | — | — | — | — | D | context | none |
| threatened_plant_richness | T,A | C3 | ✅ | — | — | — | — | D | screening | none |
| ghm | T,A | C4 | ❌ read at 1 km (X6) | ✅ | ✅ | ✅ (pressures, X8) | ⚠ item-3 pool ≈ the regional stratum | **A+B: yes** | scored (B = −0.18) | Site read at 90 m; score on the Tier-1 regional distribution, support-matched |
| light_pollution | T,A | C4 | ✅ (a landscape-level pressure is legitimate) | ✅ | ✅ | ✅ | — | **A+B: yes** | "no_reference" (mislabelled) | Score on Tier 1 |
| hdi | T,A | C4 | ✅ | ✅ | ✅ | ✅ | — | **A: yes** | "no_reference" (mislabelled) | Score on Tier 1; disclose overlap with ghm |
| lst_day | T,A | C4 | ✅ climate | ⚠ X7 | ✅ | ⚠ | — | C | contextual | Context; sample at native 1 km |
| lst_night | T,A | C4 | ✅ climate | ⚠ X7 | ✅ | ⚠ | — | C | contextual | Context; sample at native 1 km |
| sdi | A | C4 | ✅ | ❌ binary, all px (X1, X5) | ⚠ | ⚠ after fix | — | **B: yes after fix** | A-only | Reference built from shore-buffer units of other water bodies |
| stsi | T,A | C4 | ❌ site-relative (X3) | ✅ raw | ❌ | ❌ | — | C | contextual | Use raw LST if kept |
| iri | T,A | C4 | ⚠ Darukaa composite | ✅ | ✅ | ⚠ | — | C | "no_reference" (mislabelled) | Demote (double counts tspi's NDCI signal and hdi's built-up signal) |
| ivsi | T | C4 | ⚠ not taxonomic | ❌ binary px (X1) | ⚠ | ⚠ | — | C | contextual | Context |

---

## 4. Corrections table (item 13, table 2)

| Indicator | Current implementation | Scientific issue | Proposed correction | Evidence | Test required |
|---|---|---|---|---|---|
| **All proportion/rate indicators** | Polygon mean vs single-pixel reference | X1 support mismatch | **Support-matched reference:** turn the pixel image into "value within a site-sized window" (focal mean, or for rates focal sums of numerator and denominator, with window area ≈ site area) and sample *that*. For area proportions this aggregation is exact, so the 10 m classification is kept and only the comparison unit changes. | code; live (natural_habitat MAD = 0) | A binary image with a known site proportion gives a reference with non-zero spread; the reference mean equals the regional proportion |
| **All DW-label indicators** | Tier 2 stratified on the DW class of the site | X2a: the stratum fixes the value | For extent/composition indicators, use an absolute reference level (100 % natural, SEEA-style reference condition) or an ecoregion/PNV stratum without the DW class | live: 97 % / 96 % single-value pools | Registry test: an indicator whose image is a function of the DW label cannot use a DW-class-stratified Tier 2 |
| **All pressure indicators** | Tier-1-only means unscored | X8 | Pressures are scored on the Tier-1 regional distribution. Condition indicators need Tier 2. This is a documented, indicator-type rule, not a fallback | code | A pressure indicator with a valid Tier-1 reference reaches the score; a condition indicator with only Tier 1 does not |
| **Coarse products** | Read at 300 m–5 km on 1–40 ha zones; sampled at 100 m | X6, X7 | (a) Site-support rule: a *condition* indicator is scored only if the site contains ≥ N native pixels; otherwise status `not_applicable: site_below_product_resolution`. (b) Reference scale is never finer than the native pixel | verified: TerraClimate 4,638 m, TNC HM 90 m | Given site area and native resolution, the status is correct; the reference sampling scale is ≥ the native scale |
| natural_habitat | LRR vs a 0/100 pixel median | X1, X2a | Absolute reference: score = site % / 100 (LRR vs 100), or a support-matched ecoregion reference | live | Site 81.6 % gives B = ln(0.816); the reference is never a class-selected pool |
| cpland | Site = eroded core %, reference = raw binary | Different construct | Reference from the same erosion kernel, support-matched. Block scoring until the PV binary source (`biodiversity_India_PV_Binary_2025`) is documented | code; live T1 ref = 0 | Site and reference images are produced by one function |
| forest_loss_rate | Reference = `lossyear` codes | %/yr vs calendar year | Reference = focal(loss area in window) / focal(baseline forest area) / years; same 30 % threshold and window; keep the ≥ 5 ha baseline floor for reference units too; keep absolute-hectare diagnostics | live ref = 16/17 | One function returns both site and reference rates; the reference unit is %/yr; units < 5 ha are excluded; synthetic loss gives a known rate |
| net_forest_change_rate | Gain = DW trees now ∧ Hansen 2000 < 30 % canopy | Compares two products' definitions, not change; reference degenerate | Change within one product over time (e.g. DW tree-cover fraction, early window vs recent window, same classifier both ends); site and reference by the same function | live ref median = 1 | Identical start and end images give 0 change; the reference median is not fixed by the stratum |
| flii | Proxy uses HMI as P; Tier 2 selects on HMI | Circular | Demote to context | code | Registry test: no scored indicator may take the Tier-2 selector as a direct input |
| bii | Tier-2 pool selected on low HMI | Partial circularity (modelled from land use) | Keep scored; disclose; report a sensitivity benchmark using an ecoregion + PNV pool | code | The sensitivity benchmark is reported alongside |
| chm | Site @25 m, reference @10 m | Scale mismatch; no woody-type applicability | Site at 10 m; not applicable outside woody strata; label as a 2020 static baseline (no monitoring) | code | Grassland zone → not applicable |
| ndvi | Contextual, subdimension `structure` | Collides with chm, lai, habitat_health | Own subdimension (greenness); promote | code | Subdimension-uniqueness test (extends item 2) |
| ghm | Site @1000 m | X6 | Site at native 90 m | code; verified 90 m | Site scale equals native scale |
| sabf | No water mask | Land counted as bloom | Water mask (MNDWI) applied to both site and reference; exclude shore-adjacent pixels | code | An all-land region returns no value, not 1.0 |
| wcpi, stsi, edpp, mspl | Site min-max normalised within the polygon | X3 | Raw physical quantity for both site and reference (wcpi, stsi). edpp → screening. mspl → context | code | No extract function may normalise by the site's own min/max |
| edpp, mspl | Reference = band 0 (LST) | X4 | Reference image must be single-band and identical to the site construct | code | Registry test: reference image has exactly 1 band and its name matches the site metric |
| tspi | Tier 1 = all regional water pixels | Pool not comparable (rivers, sewage-fed lakes) | Water-body-unit reference: water bodies of similar size and permanence in the basin/ecoregion, metric computed per water body on its own water mask, same season window | code | Units are built per water body; a pond is compared with ponds |
| sdi, rci, riparian_ndvi_trend | Reference over all pixels | X5 | Reference from shore/riparian rings of the reference water bodies | code | The reference population uses the same ring definition as the site |
| jrc_water_persistence | Scored, direction ↑ | Same ecology problem as wsdi (seasonal ponds); binary px | Demote to context | code; item-15 decision | — |
| **Status model** | `no_reference` for Tier-1-only; Tier-1 benchmark dropped | X9 | Per-site status: `not_applicable` (with reason: realm / ecosystem type / no target feature / below resolution), `applicable_but_no_site_value`, `applicable_but_no_reference`, `reference_available_but_not_scoreable`, `scored`, `contextual_only`, `screening_only`, `suppressed_for_stability`, `pending_methodology`. Write both Tier-1 and Tier-2 benchmarks to JSON/CSV/HTML | live | Each status can be produced by at least one fixture; the report shows the Tier-1 reference whenever one exists |

---

## 5. Proposed scoring sets

This is 13 scoreable indicators across both domains, down from the 20 currently designated. It is fewer, but each one passes the seven criteria in your brief.

### A. Terrestrial scoreable (9)

| Pillar | Indicators | Reference tier |
|---|---|---|
| C1 landscape | natural_habitat (extent); cpland (configuration, **conditional on PV documentation**); forest_loss_rate (disturbance, only where baseline forest ≥ 5 ha) | absolute / support-matched; Tier 2 for the loss rate |
| C2 vegetation | ndvi (greenness); chm (structure, woody strata, 2020 baseline) | Tier 2 |
| C3 fauna | bii (with circularity disclosure and sensitivity test) | Tier 2 |
| C4 pressure | ghm, hdi, light_pollution | Tier 1 regional |

On the Deccan forest tile, forest_loss_rate is **not applicable** (0.01 ha baseline), so 8 would be applicable there.

### B. Aquatic scoreable (4 aquatic-specific + 2 shared pressures)

| Pillar | Indicators | Reference tier |
|---|---|---|
| C2 water condition | tspi (trophic state), wcpi (clarity, after fix), sabf (bloom frequency, after water mask) | water-body units |
| C4 pressure | sdi (shoreline disturbance, after fix); ghm and light_pollution (shared landscape pressures) | Tier 1 |
| C1 / C3 | **No defensible EO indicator.** Aquatic biota needs field data (eDNA; hsas stays gated) | — |

**The aquatic C3 gap must be stated in the report, not hidden.**

### C. Mixed / contextual (computed and reported, not scored)
natural_landcover, habitat_health, flii, eii, eii_structural, eii_compositional, eii_functional, pdf, lai, aridity_index, lst_day, lst_night, stsi, ivsi, iri, mspl, wsdi, shdi, jrc_water_persistence, riparian_ndvi_trend.

**Pending methodology:** rci, net_forest_change_rate, hsas.

### D. Screening / context only
kba_overlap, endemic_richness, endemic_plant_richness, threatened_richness, threatened_plant_richness, star_t, flagship_habitat, shi, edpp. `ceri` stays removed.

### Headline per domain (item 10)
Each tile's headline reports:
- counts of applicable, benchmarked, scored, contextual and unavailable indicators;
- coverage by pillar.

A pillar with no applicable scoreable indicator is shown as **"no scoreable evidence"**, never as 0, and it does not penalise the site. For example, aquatic C3 always shows this.

---

## 6. Decisions needed before implementation

| # | Decision | Options | My recommendation |
|---|---|---|---|
| D1 | Support matching method | (a) focal window with area ≈ site area; (b) tessellated reference units of site size | (a): one generic mechanism, exact for proportions. Its compute cost at 10 m needs one live timing check |
| D2 | Reference for extent indicators | absolute level (100 % natural) vs support-matched ecoregion distribution | Absolute level: transparent and SEEA-consistent. Report the regional context alongside |
| D3 | Site support rule | minimum native pixels inside the site before a *condition* indicator is scored | N = 10 as a starting point. This is a scientific threshold and is your call |
| D4 | Aquatic reference population | water-body units (new builder) vs interim Tier-1 regional water pixels | Water-body units. Until they are built, aquatic indicators run as "benchmarked, not scored" rather than scored on a non-comparable pool |
| D5 | net_forest_change_rate | rebuild on a single-product time series vs retire to context | Rebuild; it matters for restoration clients (your earlier point). Scoring stays pending until validated |
| D6 | flii | context vs rebuild without the HMI term | Context (it duplicates ghm + natural_habitat) |
| D7 | bii Tier-2 pool | keep low-HMI pool with disclosure vs ecoregion + PNV pool | Keep, disclose, and report the sensitivity benchmark |
| D8 | jrc_water_persistence | scored vs context | Context, for consistency with the WSDI decision |
| D9 | cpland | score now vs after documenting the PV binary asset | After documentation |

---

## 7. What this audit could not verify

- **Native resolutions.**
  - Landler EII: not found in any source; the code assumes 300 m.
  - Not re-verified today: VIIRS DNB (~463 m), MODIS LAI (500 m), MODIS LST (1 km), CHIRPS (~5.5 km).
- **Landler EII component sources** (whether compositional = BII and structural = human modification). This is inferred from the code's fallbacks and the repo's OD-C4 note.
- **Provenance and method of the Darukaa `PV_Binary_2025` asset** used by cpland.
- **Aquatic behaviour.** No aquatic tile has run on the current code, so every aquatic finding is code-level only.
- **Accuracy of the empirical algorithms** used by tspi, wcpi and sabf in small Indian water bodies: the NDCI→chl-a coefficients, the TSM coefficients, and the FAI threshold.
- **Compute cost of support matching** at 10 m (D1).
