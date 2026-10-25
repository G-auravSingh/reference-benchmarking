# Metric catalogue v1

**Status.** Approved by Gaurav on 23 Oct 2026, with his amendments C1–C9 (listed below). This catalogue is the specification for the first-draft build. **Nothing in it has been implemented yet.**

**Evidence behind it:**
- Static reading of the current extractors.
- The Tata run of 2026-10-11 (end-to-end Colab at commit 43bd210).
- Public dataset and paper pages, checked on 23 Oct. Sources are listed at the end.

Nothing here has been checked in a live Earth Engine (EE) run. Items marked *probe* are confirmed only by Colab run CR1.

**Source labels** used throughout:
- [STD]: a standard or framework.
- [VENDOR]: a vendor or tool approach.
- [ACAD]: an academic dataset.
- [DARUKAA]: Darukaa's own evidence.

**Granularity.** Every metric is **preparatory** under Nature Positive [STD]. There is no ground-truthing, and the natural/non-natural classification is not at GET level 3–4 (Guidance p.6 and p.15; TOR p.56).

## Gaurav's amendments (23 Oct)

- **C1. Nature Trace Forest Typology 2020 is added to the natural mask.** See the natural mask section below.
- **C2. Habitat health is corrected to follow Plan Vivo.** The current HHI is Darukaa's own construct: per-pixel temporal NDVI p5 ÷ σ, over a calendar year, then averaged. It is rebuilt as PV Nature Pillar 4.
  - *Correction to the 23 Oct draft:* the draft wrongly described `habitat_health` as a distance composite using `unmask(0)`. That description belonged to retired extractors.
- **C3. FLII, forest loss and EII are re-verified.** Findings:
  - **FLII:** zero pixels at Tata is correct product behaviour. FLII is defined only on forest pixels, and Tata is not forest. It gave values of 5.2–6.8 at Corbett in the TCF report (p.14).
  - **EII:** the near-zero value at Tata is genuine. EII = min-component × fuzzy-sum of the other two components. Its structural component is gHM core habitat averaged over 5 km, and that reads about 0.0003 around peri-urban Pune. The value is identical in all 9 EMUs.
  - **Forest loss:** the 2000 baseline was 0.01 ha at 30% canopy, so the metric has no meaning there. That is the C2 defect, and the metric is rebuilt.
- **C4. CPLAND and landscape connectivity are different constructs.** Both are kept.
- **C5. MSA is added.** It uses the newest public global map, GLOBIO4 2015.
- **C6. Finest available scale for every raster.** Small-parcel extraction rules are set out in their own section below.
- **C7. Licences.**
  - IUCN, STAR and LIFE cannot be used commercially and cannot be bought. P3 therefore uses licence-clean sources only.
  - WDPA, KBA and BirdLife layers are removed. Their commercial terms forbid client use.
- **C8. SBTN share-alike (CC-BY-SA-4.0) is accepted.**
- **C9. Approach 2 reference pool is approved.** It must work for every project type.
- **C10. Open metrics widely used by dMRV tools are added**, terrestrial first.

## Natural mask (shared by P1, P2 and the managed-land result)

A pixel is classified in this order:
1. **Nature Trace ForTy 2020** (`projects/nature-trace/assets/forest_typology/forest_typology_2020_v1_0_collection`; 10 m; CC-BY-4.0; Google DeepMind with WRI and IIASA [ACAD]).
   - Where its argmax class is 1 (primary) or 2 (naturally regenerating), the pixel is **natural forest**.
   - Where its argmax class is 3, 4 or 5 (planted, plantation, tree crops), the pixel is **managed**.
2. **SBTN Natural Lands v1.1 2020** (`WRI/SBTN/naturalLands/v1_1/2020`; 30 m; CC-BY-SA-4.0 [STD-named dataset]). Where ForTy says "other land", the SBTN `natural` band decides, and its `classification` band gives the type.
3. **Dynamic World V1** (10 m) for the assessment window:
   - It records loss of 2020 natural land: the current class is crops or built.
   - It records candidate gain: managed in 2020, natural-class vegetation now.
   - It is never used to promote a pixel to natural on its own.
4. **Uncertain pixels.** A pixel is flagged `uncertain`, not assigned a class, when either:
   - the winning ForTy probability is below 0.5, or
   - ForTy and SBTN disagree.

   Uncertain area is reported.

**Known limits:**
- ForTy's planted vs naturally-regenerating classes are weak in Asia: F1 ≈ 0.46–0.73 (preprint Tables 23–24). Primary and naturally regenerating forest are therefore merged.
- Tropical dry forest was not evaluated by the ForTy authors.
- The ForTy paper's Scientific Data page could not be opened. The EarthArXiv preprint v2 (May 2026) was read instead.

## Small-parcel and scale rules (all rasters)

- **Finest source first.** Use the finest open source available for each metric (table below). Coarse layers are kept only where no finer equivalent exists.
- **Explicit scale and CRS.** Every reduction sets `scale` and `crs` explicitly. `bestEffort` is never used. (The 2026-10-11 run had `bestEffort=True`, so its scale was not what was recorded.)
- **Coverage-weighted values.** Values are coverage-weighted means; EE weights each pixel by its covered fraction [EE docs]. Two support measures are recorded:
  - `covered_pixel_equivalent`: the sum of coverage weights.
  - `touched_pixels`: the number of pixels touched at all.
- **Coarse pixels and the context window.** If `covered_pixel_equivalent` is below 4 native pixels (decision 5), the value comes from a context window instead: the site plus the smallest buffer that holds 4 pixel-equivalents. Status is then `scored_context_scale`, and the value is never presented as resolved to the site.
- **Uncertainty.** Each value carries:
  - the within-unit spread;
  - the product's own error, where it publishes one;
  - the reference bootstrap interval.

## P1 Ecosystem extent (SITE level)

| ID | Definition | Dataset | Reference | Role |
|---|---|---|---|---|
| `natural_extent_pct` | % of site area that is natural or semi-natural now (natural mask) | ForTy + SBTN + DW | natural_scale | SCORED |
| `natural_gross_loss_pct` | 2020 natural area that is now non-natural, as % of 2020 natural area. Broken down by type. Gross only. | as above | regional_context (landscape loss rate), lower is better | SCORED |
| `tree_cover_loss_rate` | % of 2000 tree cover (≥10% canopy) lost per year, averaged over the last 5 full years. Status `not_applicable_no_forest_baseline` if the baseline is under 1 ha. | `UMD/hansen/global_forest_change_2025_v1_13`, 30 m, CC-BY-4.0 | regional_context, lower is better | SCORED |
| `natural_core_area_pct` (CPLAND) | Core natural area (more than 30 m from a non-natural edge) as % of site area. **Within-site configuration.** Plan Vivo Pillar 5 uses CPLAND (PV Nature V1.2 p.28) [STD]. | natural mask, 10 m | natural_scale | SCORED |
| `natural_gross_gain_ha` | Candidate gain by type: managed in 2020, natural-class vegetation now | as above | none | CONTEXTUAL |
| `natural_extent_by_type_ha` | Natural area by type | as above | none | CONTEXTUAL |
| `forest_cover_2020_jrc_pct` (new) | Cross-check of forest extent in 2020 | `JRC/GFC2020/V2`, 10 m, CC-BY *(licence to confirm in probe)* | none | CONTEXTUAL (QA cross-check) |
| `surface_water_extent_ha` (new) | Permanent and seasonal water area; gross water loss since 2000 | `JRC/GSW1_4/GlobalSurfaceWater`, 30 m, open with attribution | regional_context | CONTEXTUAL (terrestrial), SCORED (aquatic, later) |
| `landscape_natural_extent_pct` | Natural extent in 5 km and 10 km rings, site excluded | natural mask | none | CONTEXTUAL, labelled landscape context |

**Removed for licence reasons (C7):** `kba_overlap` and `protected_area_overlap`. WDPA and KBA forbid commercial use without permission.

## P2 Ecosystem condition (natural pixels only; 10–30 m metrics per EMU, coarser metrics at SITE)

| ID | Component | Dataset and scale | Reference | Role | Notes |
|---|---|---|---|---|---|
| `ndvi_peak_season` | function | `COPERNICUS/S2_SR_HARMONIZED` with `COPERNICUS/S2_CLOUD_PROBABILITY`. Median over the 3-month peak-greenness window inside the assessment period. 10 m. | reference_condition, by type | SCORED | Replaces the calendar-year median. |
| `pv_habitat_health_sbi` | function / heterogeneity | Plan Vivo PV Nature V1.2 Pillar 4 (§1.5.4, pp.24–27) [STD]: SBI = Sq / z05 of the peak-season NDVI surface across the unit. Sq is RMS roughness. z05 is the height at 5% bearing area, which is the NDVI p95 (geodiv `height_ba` source). 10 m. | none at baseline; year-on-year % change in monitoring years, as Plan Vivo specifies | CONTEXTUAL at baseline; change metric afterwards | Plan Vivo defines no absolute reference. Its direction and the role of mean-plane removal (geodiv `sq`) must be checked against PV p.26 before implementation. Replaces Darukaa HHI. |
| `lai_s2` (new, replaces MODIS LAI) | structure / function | Sentinel-2 LAI from SL2P (CCRS LEAF toolbox algorithm, open source), 20 m | reference_condition | SCORED | MODIS `MCD15A3H` at 500 m is kept only as a context cross-check. The LEAF EE implementation needs verifying. |
| `canopy_height_m` | structure | Meta/WRI 1 m, `projects/sat-io/open-datasets/facebook/meta-canopy-height`, CC-BY-4.0, imagery 2009–2020 | reference_condition; forest and shrub types only | SCORED | The current `okw37` asset ID is unverified *(probe)*. |
| `canopy_height_glad_m` (new) | structure | GLAD forest height 2020, 30 m, `projects/sat-io/open-datasets/GLAD/GEDI_V27` *(ID to confirm in probe)* | reference_condition | CONTEXTUAL (cross-check) | |
| `gedi_rh98_m` (new) | structure | `LARSE/GEDI/GEDI02_A_002_MONTHLY` rh98 with quality filter, 25 m footprints | reference_condition | CONTEXTUAL; becomes SCORED where there are at least 10 footprints | Footprints are sparse on small sites. |
| `bii` | composition | `projects/ebx-data/assets/earthblox/IO/BII_V1_1`, 100 m, 2017–2025, CC-BY-4.0 | reference_condition | SCORED, labelled preparatory and pressure-modelled | Uses the latest year at or before the window end, and records that year. |
| `eii_functional` | function | Landbanking EII v1 functional band: observed NPP vs potential NPP, 300 m | reference_condition | SCORED at context scale, labelled preparatory | Of the three EII components, the most observation-based. The data licence is unverified (ask Landbanking). |
| `eii` (parent), `eii_structural` | integrity | Landbanking EII v1, 300 m. Structural = gHM core habitat over 5 km. | — | CONTEXTUAL | Structural is built from pressure data (gHM), which double-counts P4. The Guidance allows pressure-modelled condition only as a last resort at preparatory level (p.20). Can be switched on in Colab. |
| `eii_compositional` | composition | Landbanking EII v1 | — | DIAGNOSTIC | This is BII aggregated to 300 m (Landbanking docs). It duplicates `bii`. |
| `flii` | forest integrity | Grantham et al. 2020 FLII, 300 m, forest at the start of 2019; uploaded by Gaurav from the official WCS download | reference_condition; forest pixels only | SCORED where at least 4 forest pixel-equivalents exist in the context window; otherwise `not_applicable_non_forest` | Licence unverified. The status text currently says "Darukaa proxy", which is stale and will be corrected. |
| `msa` (new version) | composition | GLOBIO4 MSA 2015 (Schipper et al. 2020), about 300 m, CC-BY-4.0 per globio.info. Not in EE; to be uploaded as a Darukaa asset. | — | CONTEXTUAL (can be switched on in Colab) | Fully pressure-modelled from six pressures. It overlaps BII and P4. No version newer than 2015 was found. |
| `landscape_connectivity` (new) | landscape condition | Connectance of natural patches in 5 km and 10 km rings, from the natural mask | none | CONTEXTUAL, labelled landscape context | The Nature Positive landscape condition metric (Framework p.13; Guidance pp.24–25) [STD]. **It differs from CPLAND:** connectivity *between* patches across the landscape, versus core area *within* the site. |

## P3 Species (SITE): licence-clean sources only

| ID | Dataset | Role | Notes |
|---|---|---|---|
| `species_records_screen` (new) | GBIF occurrences limited to CC0 and CC-BY records, including the eBird Observation Dataset (CC-BY-4.0). Within the site plus 5 km and 10 km rings, from 2015 onwards. | SCREENING | Reported as "recorded", never as absent. Effort and sampling bias are shown. |
| `scheduled_species_records` (new) | The same records, matched to the Schedules of India's Wildlife (Protection) Amendment Act 2022 | SCREENING | A national protection status, **not** IUCN extinction risk, and labelled as such. |
| `star_t`, `life_score`, IUCN range richness | — | **NOT USED** (C7) | Commercial use needs an IBAT licence or IUCN permission. Optional: write to IUCN to ask whether Red List *Categories* can be used per species, and whether a pilot waiver exists. |
| in-situ `acoustic_*`, `edna_*`, `field_*` | client data | CONTEXTUAL (hooks) | Not scored this week. |

**P3 scored status:** not covered. The report states "Species extinction risk and populations: not covered. Licence-restricted data. Screening records and in-situ hooks shown" (comply or explain, TOR p.83). The headline uses P1 and P2 (D-23-10).

## P4 Pressure (SITE; low_pressure reference, D-25-1; native value, all-ring comparison and absolute class shown beside each score)

**Reference for P4 (option B, approved 25 Oct).**
- **Reference value.** The median over *low-pressure* blocks in the same ring and ecoregion.
  - These blocks are chosen by their 2020 natural-ecosystem share from ForTy and SBTN: at least 90% natural, or failing that the most natural 20% of blocks, with at least 20 blocks either way.
  - Because no pressure metric is used to choose them, the reference is not circular with what it scores.
- **Worst value.** The 95th percentile of all ring blocks, falling back to the contract maximum if that is not usable.
- **Context figures shown beside the score, not used in it:**
  - the all-ring comparison (option A);
  - for gHM, the Kennedy et al. 2019 class (option C).

| ID | Dataset and scale | Role | Notes |
|---|---|---|---|
| `built_fraction` | DW built class share in the window, 10 m | SCORED | Uses the pressure population (H2). |
| `ghm` | `TNC/HM/v3/90m_s` (ImageCollection; `All_threats_combined`; 2022), 90 m, CC-BY-4.0 | SCORED | Rebuilt at native scale (H4). Never mixed with the 300 m time series. |
| `road_density` (new) | GRIP4, `projects/sat-io/open-datasets/GRIP4/*`, CC-BY-4.0, about 2018; km of road per km² in the site + 1 km | SCORED | Vector data, so scale is not an issue. |
| `fire_frequency` (new) | `MODIS/061/MCD64A1`, 500 m: share of 2016–2025 with a burn. Plus VIIRS 375 m active-fire counts from FIRMS as a finer cross-check *(ID to probe)* | SCORED at context scale | |
| `night_lights` | `NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG` `avg_rad`, about 464 m, window median | SCORED at context scale | No finer open source exists. |
| `forest_disturbance_alerts` (new) | GFW integrated alerts (GLAD-L, GLAD-S2, RADD), 10–30 m, CC-BY-4.0, 30°N–30°S only | CONTEXTUAL | Covers almost all of India. Access through EE is to be confirmed in the probe. |
| `population_density` (new) | `WorldPop/GP/100m/pop` 2020, about 93 m, CC-BY-4.0 | CONTEXTUAL | Modelled; overlaps gHM. |
| `lst_day`, `lst_night` | Landsat Collection 2 ST_B10 (100 m thermal, delivered at 30 m) for day; MODIS `MOD11A1` (1 km) for night | CONTEXTUAL (climate exposure) | Finer source used for day. |
| `aridity_index` | source to confirm | CONTEXTUAL (climate) | |

## Managed-land result (non-natural pixels per EMU; outside the Nature Positive panel; D-22-2)

- **Reported:**
  - managed area;
  - ForTy managed class shares (planted, plantation, tree crops) and DW shares;
  - peak-season NDVI and canopy height on managed pixels, against the same managed class in the region (regional_context).
- **Label:** "Managed-land vegetation [DARUKAA]". It never feeds the condition headline.

## Scored metrics per pillar (default; every metric can be switched on in Colab, A2)

| Pillar | Scored | Contextual, screening or diagnostic |
|---|---|---|
| P1 | 4: natural extent, gross loss, tree loss rate, core area | gain, extent by type, JRC forest check, surface water, landscape extent |
| P2 | 7: NDVI, S2 LAI, canopy height, BII, EII functional, FLII (forest only); plus GEDI where there are enough footprints | PV SBI (baseline), GLAD height, EII parent and structural, MSA, connectivity, EII compositional |
| P3 | 0 (not covered) | GBIF and eBird records, scheduled species, in-situ hooks |
| P4 | 5: built-up, gHM, roads, fire, night lights | alerts, population, LST, aridity |

## Aquatic (after terrestrial; listed for later)

| Dataset | Use |
|---|---|
| JRC GSW occurrence, seasonality and yearly history (30 m) | Water extent; gross loss and gain |
| Sentinel-2 NDCI and turbidity (20 m) | Preparatory condition; needs in-situ calibration |
| WWF free-flowing rivers; Global Dam Watch (CC-BY-4.0) | Connectivity context |
| Riparian NDVI | Condition of riparian vegetation |

## Reference design (approved, C9)

**Approach 2 for condition** [DARUKAA design; consistent with the SEEA-EA reference-condition definition, TOR p.150; Guidance p.21]. The reference is one least-disturbed pixel pool per project.
1. Exclude every site in the project plus a buffer of at least 1 km.
2. Keep pixels in the same ecoregion within a radius R.
3. Screen the least disturbed with the human-modification ladder on gHM v3 at 90 m.
4. Stratify by natural-mask type.
5. Take a stratified pixel sample from each stratum.
6. Sample every metric at those same pixels.
7. Derive the reference interval with a spatial-block bootstrap.

A natural EMU pixel is benchmarked against the sample for its own type. When a stratum is too small, the result is `reference_insufficient`; there is no silent fallback.

**Approach 4 for regional context** [VENDOR precedent: 3Bee control rings]. All ring blocks in the ecoregion, outside the site. Used for P1 loss rates and managed land. For P4 it supplies only the worst value and the 'versus surroundings' context figure; the P4 reference itself is the low-pressure block subset (D-25-1).

**Robustness requirements for any project type:**
- R and the minimum stratum size are set from probe evidence and logged.
- The test ladder covers one compact polygon, separated polygons (Corbett), adjacent and fragmented EMUs (Tata, SoulForest), and agroforestry (FCF).

## Sources (checked 23 Oct; nothing run in EE)

**Standards and frameworks**
- Nature Positive Framework, Initial Measurement Guidance v1.0 and Technical Output Report, as cited by page.
- Plan Vivo PV Nature Methodology & Data Protocol V1.2 (2026-04-29), pp.24–30. The bodies of Eqs. 6–11 did not render.

**Datasets**
- EE catalogue pages:
  - Dynamic World, Hansen v1.13, TNC HM v3, SBTN v1.1, JRC GSW
  - MODIS MCD64A1, MOD11A1, MCD15A3H
  - VIIRS VCMSLCFG, GEDI, WorldPop
  - ForTy and Natural Forests 2020
- EarthArXiv 10.31223/X58R27 (ForTy preprint v2): Table 6 p.15; Tables 23–24 pp.33–34; §4.6 pp.18–19.
- Community catalogue: BII v1.1, Meta canopy height, GRIP4, GLAD forest height.
- Landbanking EII documentation and GitHub.
- globio.info and PBL README (GLOBIO4).
- forestlandscapeintegrity.com and the WCS fact sheet.

**Licence pages**
- GBIF licence processing.
- eBird terms.
- IUCN Red List terms of use.
- IBAT pricing.
- Protected Planet legal terms.
- BirdLife data terms.

**Methods**
- geodiv R source (`bearingarea.R`: `sbi` = Sq / `height_ba(x, 0.05)`).
- EE reduceRegion weighting guide.

**Could not access**
- The ForTy Scientific Data page.
- The FLII Nature Communications paper (blocked), and the FLII licence.
- The EII data licence.
- The Plan Vivo equation bodies.
- The exact LIFE licence wording.
