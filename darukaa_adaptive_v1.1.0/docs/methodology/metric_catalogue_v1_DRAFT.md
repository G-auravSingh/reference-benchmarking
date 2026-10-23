# Metric catalogue v1: draft for approval (23 Oct 2026)

**Status: DRAFT. Nothing here is implemented yet.**

This catalogue follows decisions D-23-3 to D-23-11 and amendment A3 (re-verify every metric).

**Evidence used:**
- **Static reading** of the current extractors in `legacy_reference/indicators/__init__.py` at commit 61e2987.
- **The 2026-10-11 Tata run** (end-to-end Colab at 43bd210).
- **A dataset check of 23 Oct** against public catalogue pages. Sources are listed at the end of this document.

None of this has been checked in a live Earth Engine run. Asset IDs, band names and pixel counts marked *probe* are confirmed only in Colab run CR1.

**Source labels:**
- **[STD]** standard or framework
- **[VENDOR]** vendor or tool method
- **[DARUKAA]** Darukaa's own evidence

**Granularity.**
- Every metric below is **preparatory** in the Nature Positive sense [STD]. There is no ground-truthing, and the classification only separates natural from non-natural land (Guidance p.6 and p.15; Technical Output Report (TOR) p.56).
- Medium would need IUCN Global Ecosystem Typology (GET) level 3–4 classes plus ground-truth points (Guidance p.6).

**Framework tags** are provisional until the standards pass (prompt 2a):
- TNFD C1.0/C1.1: spatial footprint and land-use change
- ESRS E4-5: impact metrics
- SBTN S1: state of nature, natural land
- PV: Plan Vivo PV Nature

## Common contract fields

Every metric carries these fields:
- definition, unit, direction
- native scale
- assessment level: SITE or EMU
- natural-pixels-only flag
- minimum support: covered native pixels; the default is 4 (decision 5)
- reference type
- recommended role and the reason
- granularity
- pressure-derived flag
- dataset ID, version and licence
- effective period
- failure statuses
- map specification

**Failure statuses** are shared by all metrics, and none of them ever becomes a value:
- `not_run`
- `source_unavailable`
- `no_valid_pixels`
- `below_min_support`
- `not_applicable_<reason>`
- `out_of_range_review`

**Map specification.** Every raster metric is drawn from the same EE image that produced its number. The map shows:
- the site and EMU outlines;
- the native pixel grid for coarse layers;
- a context ring;
- a caption with dataset, year and resolution.

## Reference types (from the plan, re-checked)

| Type | Used for | How it is built |
|---|---|---|
| `reference_condition` | Condition metrics (P2) | Least-disturbed pixels of the same ecosystem type, inside the same ecoregion, outside the site plus a buffer (D-23-8). Spatial-block bootstrap gives the interval. Scored as attainment of the reference median, capped at 100. |
| `regional_context` | P4 pressure and P1 loss rates | All pixels of the ecoregion in the reference window, outside the site. Scored with the bounded function: 100 at or below the reference median, 0 at the regional p95 (decision 4, D-23-9). |
| `natural_scale` | Metrics with natural bounds (natural extent %, core area %) | Score = value on its 0–100 scale. No reference ratio. The cited bound is reported. |

## P1 Ecosystem extent (assessed at SITE level)

| ID | Definition and unit | Dataset (ID, resolution, licence) | Reference | Recommended role | Why | Current code |
|---|---|---|---|---|---|---|
| `natural_extent_pct` **(rebuild of natural_habitat)** | % of site area that is natural or semi-natural in the assessment window. A pixel counts as natural when **both** hold: it is natural in SBTN Natural Lands 2020, and its current Dynamic World (DW) class is natural. This removes plantation and crop that DW labels "trees" or "grass". | `WRI/SBTN/naturalLands/v1_1/2020`, 30 m, CC-BY-SA-4.0 (derived maps must be shared alike); `GOOGLE/DYNAMICWORLD/V1`, 10 m, CC-BY-4.0 | natural_scale | SCORED | Nature Positive extent metric [STD]. The SBTN map is the named preparatory classification layer (Guidance p.15; TOR pp.89, 105, 116). | Current code is DW-only, mode of calendar year 2026 (a partial year), so plantations count as natural. **Rebuild.** |
| `natural_gross_loss_pct` **(new)** | Natural area in 2020 that is non-natural now, as % of 2020 natural area. Gross only, never netted. Broken down by type. | SBTN 2020 plus DW in the assessment window | regional_context, lower is better | SCORED | Nature Positive extent losses [STD]. Gross only by Darukaa rule [DARUKAA]. | None. **New.** |
| `natural_gross_gain_ha` **(new)** | Non-natural in 2020 → natural-class DW now, in ha by type. Labelled "candidate gain": DW cannot confirm natural status. | Same as above | none | CONTEXTUAL | No defensible reference. Restoration progress is shown, but not scored. | **New.** |
| `tree_cover_loss_rate` **(rebuild of forest_loss_rate)** | % of the year-2000 tree cover (≥10% canopy) lost per year. Annual mean over the last 5 full years in the Hansen version. Status `not_applicable_no_forest_baseline` when the baseline is under 1 ha. | `UMD/hansen/global_forest_change_2025_v1_13`, 30 m, CC-BY-4.0 (lossyear 1–25 = 2001–2025) | regional_context, lower is better | SCORED | Decision 3 of 16 Oct. | Current value is cumulative ha at 30% canopy, with a hard-coded flag. **Rebuild.** |
| `natural_core_area_pct` **(rebuild of cpland)** | Core area (natural pixels more than 30 m from a non-natural edge) as % of site area. | Natural mask from `natural_extent_pct` | natural_scale | SCORED | Configuration measure. Oji used CPLAND (TOR p.110). | Current code uses a private, India-only PV binary asset, `unmask(0)`, and a 10 m edge. **Rebuild** on the open mask. |
| `natural_extent_by_type_ha` | Natural area by DW class: trees, grass, shrub, flooded vegetation, water, bare | SBTN plus DW | none | CONTEXTUAL | Breakdown by type [STD]. | **New.** |
| `landscape_natural_extent_pct` | Same as `natural_extent_pct`, in 5 km and 10 km rings, with the site excluded | Same as above | none | CONTEXTUAL (labelled landscape context) | TOR p.132 [STD] | **New.** |
| `protected_area_overlap`, `kba_overlap` | % of site inside or near WDPA and KBA areas | `WCMC/WDPA/current/polygons`; KBA `projects/ee-kbas-in-gee/assets/current` | none | SCREENING | **Licence: no commercial use without UNEP-WCMC or BirdLife permission.** KBA access also needs an approved request. | KBA is diagnostic now. Pending licence. |

## P2 Ecosystem condition (natural pixels only; 10 m metrics per EMU, coarse metrics at SITE)

| ID | Component | Dataset | Reference | Recommended role | Why | Current code |
|---|---|---|---|---|---|---|
| `ndvi_growing_season` **(rebuild of ndvi)** | Function | Median NDVI over cloud-masked growing-season scenes in the window. Sentinel-2 `COPERNICUS/S2_SR_HARMONIZED`, 10 m, Copernicus open licence. | reference_condition, by DW class | SCORED | Sentinel-2 indices were used for condition at preparatory level (TOR pp.102, 116). | Current code is a calendar-year median including the dry season, using all pixels. **Rebuild** with the window and the natural mask. |
| `canopy_height_m` (`chm`) | Structure | Meta/WRI 1 m. The documented asset is `projects/sat-io/open-datasets/facebook/meta-canopy-height`, CC-BY-4.0, imagery 2009–2020 (mostly 2018–2020). The current code's `okw37` ID is unverified (*probe*). | reference_condition, forest and shrub types only | SCORED | Structure component [STD]. | Unverified asset, plus a dead `try/except` fallback. **Rebuild.** |
| `lai` | Structure and function | `MODIS/061/MCD15A3H`, 500 m, no restrictions. Uses QC-filtered `Lai` × 0.1. | reference_condition | SCORED at context scale (SITE) | Decision 5. | Current code applies no QC and uses a calendar year. **Rebuild.** |
| `bii` | Composition | `projects/ebx-data/assets/earthblox/IO/BII_V1_1`, 100 m, 2017–2025, CC-BY-4.0 | reference_condition | SCORED, labelled **preparatory, pressure-modelled** | D-23-3. The pressure-modelled limit is Guidance p.20. | Current code silently falls back to an all-years mean. **Fix:** use the latest year at or before the window end, and record it. |
| `eii` | Integrity (all components) | `projects/landler-open-data/assets/eii/global/eii_global_v1`, 300 m, "beta-quality". **Data licence unverified.** | reference_condition | CONTEXTUAL until the probe | Tata run: 0.000 in all 9 EMUs, so the values themselves are suspect. Licence not confirmed. | Wait for probe CR1. |
| `eii_structural`, `eii_compositional`, `eii_functional` | Components | Same as above | none | CONTEXTUAL | `eii_compositional` may be BII-derived. Srishti: 0.5505 = BII. | Keep contextual. |
| `flii` | Forest integrity | **No official or community EE asset found.** The current code reads a Darukaa-hosted asset of unknown provenance. Licence unverified. | — | DROP from scoring; CONTEXTUAL only if provenance is documented | Zero valid pixels in all 9 Tata EMUs. Provenance unknown. | **Drop**, or document provenance. |
| `msa` | Composition | GLOBIO MSA 2015, private asset `ee-jayankandir`, pressure-modelled | — | CONTEXTUAL | Duplicates the BII construct. Old data. Private asset. | Keep contextual. |
| `habitat_health` | Composite | Custom composite of distances to water, built-up and roads, with `unmask(0)` | — | DROP | Silent zeros. Built from pressure distances, which the Guidance does not allow as condition beyond the last resort (p.20). | **Delete.** |
| `landscape_connectivity` **(new)** | Landscape condition | Connectance of natural patches in 5 km and 10 km rings, from the natural mask | none | CONTEXTUAL (landscape context) | The Nature Positive landscape condition metric is connectivity (Framework p.13; Guidance pp.24–25) [STD]. | **New.** |

## P3 Species (SITE)

| ID | Dataset | Recommended role | Why |
|---|---|---|---|
| `star_t` | IBAT STAR-t. Access and licence go through IBAT (commercial use needs a licence). | SCORED only once Darukaa holds an IBAT licence; otherwise P3 is "not covered" | Extinction-risk metric [STD]. TOR pp.68 and 74: IBAT is paywalled for commercial users. |
| `life_score` | LIFE (Eyres et al. 2025), Zenodo, about 1.8 km. **Commercial use needs written IUCN permission.** | Same rule as `star_t` | Same reason. |
| `threatened_range_richness`, `endemic_range_richness`, plant richness | IUCN range maps (IUCN terms) | DIAGNOSTIC | Counts depend on area. The plant values were the same in every Tata EMU. |
| `gbif_occurrence_screen` **(new, optional)** | GBIF records within 10 km (CC0 / CC-BY records only) | SCREENING | Sampling bias. Presence only. |
| `acoustic_*`, `edna_*`, `field_*` | Client in-situ data | CONTEXTUAL (hooks) | Not scored this week. |

**Consequence:** without an IBAT or IUCN licence, P3 has **no scored metric**. It is reported as "not covered: species datasets need a commercial licence" (TOR p.83, "comply or explain"). Under D-23-10 the headline then uses P1 and P2.

## P4 Pressure (SITE; outside Nature Positive; TNFD drivers)

| ID | Dataset | Reference | Recommended role | Current code |
|---|---|---|---|---|
| `built_fraction` | DW `built` class share in the window, 10 m | regional_context | SCORED | Matched against the wrong population (H2). **Fix.** |
| `ghm` | `TNC/HM/v3/90m_s` ImageCollection, `All_threats_combined`, 2022, 90 m, CC-BY-4.0. The 300 m 1990–2020 series must not be mixed with it, per the catalogue. | regional_context. Absolute class shown beside it (Kennedy et al. 2019 / Theobald et al. 2025 thresholds, to be cited). | SCORED | Extracted at a 1,000 m scale with `.first()` and no bounds filter (H4). **Rebuild** at 90 m. |
| `night_lights` | `NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG` `avg_rad`, about 464 m, window median, `cf_cvg` > 0 | regional_context | SCORED at context scale | Calendar year. **Rebuild.** |
| `fire_frequency` **(new)** | `MODIS/061/MCD64A1`, 500 m. Share of years 2016–2025 with burning. | regional_context | SCORED at context scale | **New.** The plan cites Vale's use of fire (TOR p.119). |
| `population_density` **(new)** | `WorldPop/GP/100m/pop` 2020 (CC-BY-4.0) or GHS-POP 2025 (EC reuse) | regional_context | CONTEXTUAL | **New.** Modelled. Overlaps with gHM. |
| `lst_day`, `lst_night`, `aridity_index` | MODIS LST `MOD11A1`, 1 km; aridity (source to be verified) | none | CONTEXTUAL (climate exposure, not anthropogenic pressure) | Keep. Relabel as climate context. |

## Managed-land result (non-natural pixels per EMU; outside the Nature Positive panel, D-22-2)
- **What is reported:**
  - managed area in ha;
  - DW class shares;
  - NDVI and canopy height on managed pixels, compared with the same managed class in the region (regional_context).
- **How it is labelled:** "Managed-land vegetation score [DARUKAA]". It never feeds the condition headline.

## Scored count per pillar (first draft)

| Pillar | Scored | Notes |
|---|---|---|
| P1 | 4 | natural extent, gross loss, tree loss rate, core area |
| P2 | 4 | NDVI, canopy height, LAI, BII. EII may join after the probe. |
| P3 | 0–2 | 0 without an IBAT or IUCN licence |
| P4 | 4 | built-up, gHM, night lights, fire |

Under A2, the Colab cell will let the user switch any contextual metric to scored, and the report will flag that switch. Licence-blocked and DROP metrics cannot be switched on.

## Open points for Gaurav
1. **Licences.** Does Darukaa hold, or want, an IBAT licence (STAR, KBA, WDPA) or an IUCN permission (LIFE, range maps)? This decides P3.
2. **SBTN Natural Lands licence.** It is CC-BY-SA-4.0. Derived natural-extent maps given to clients would need to carry the same licence. Acceptable?
3. **Drop FLII and habitat_health, and keep EII contextual until the probe.** Agree?

## Sources for the dataset check (23 Oct)
- EE catalogue pages for:
  - Dynamic World
  - Hansen v1.13
  - TNC HM v3 (90m_s and 300m_c)
  - CSP gHM (CC-BY-NC-SA, not used)
  - MCD15A3H, MOD11A1 and MCD64A1
  - VIIRS VCMSLCFG
  - RESOLVE 2017
  - SBTN Natural Lands v1.1
  - WDPA and KBA
  - WorldPop and GHS-POP
  - WorldCover
  - GEDI
- Community-catalogue pages for:
  - BII v1.1
  - Meta canopy height
  - GWL_FCS30
- Other sources:
  - Landbanking EII docs and GitHub
  - LIFE FAQ and Zenodo 14188450
  - IUCN STAR page
  - forestlandscapeintegrity.com

## Reference design for any EMU layout (A6, D-23-8): four approaches compared

**Approach 1. Current: one reference per EMU.**
- **How it works.** Each EMU gets a 25 km ring around it. Pixels in the ring match the EMU's single most common DW class. Human modification is then screened in steps: HMI ≤ 0.05, then the least-disturbed 10%, then a manually set HMI cut-off.
- **Weaknesses on Tata-like layouts:**
  - The nine Tata EMUs sit inside 2.1 km². Their reference rings are almost identical, so the same work is repeated nine times.
  - The ring for one EMU can include the other EMUs.
  - A single "most common class" misrepresents mixed EMUs.
  - Reference populations came out at only 13–71 ha in the Tata run.
- **Source:** [DARUKAA]

**Approach 2. Proposed: one pixel pool per project, split by ecosystem type.**
- **How the pool is built.**
  1. Take the union of all sites, plus a buffer of at least 1 km, and exclude it.
  2. Inside the site's ecoregion and a radius R (default 25 km), keep the least-disturbed pixels. Use the same human-modification steps as Approach 1, applied to gHM v3 at 90 m.
  3. Divide those pixels by ecosystem type: SBTN natural classes × current DW class.
  4. For each type, draw a stratified random sample of n pixels.
- **How the sample is used.**
  - Every metric is sampled at those same pixel locations, so each metric gets a full distribution and every site and EMU is compared against the same reference.
  - The reference interval comes from a spatial-block bootstrap.
  - A natural pixel inside an EMU is benchmarked against the pool sample of its own type. The EMU value is the area-weighted result across its types.
- **Why it suits every layout.** It works the same for one polygon or for many fragmented, adjacent EMUs.
- **Source.** Fits SEEA-EA's definition of reference condition (TOR p.150) and the Guidance's "best available" benchmark (Guidance p.21) [STD]. The pool design itself is Darukaa's own [DARUKAA].

**Approach 3. Fixed published benchmarks.**
- **How it works.** Fixed values per biome taken from the literature.
- **Strengths and weaknesses.** Simple, but not specific to the site, and few benchmarks exist for 10 m metrics. It is used only where a natural scale exists, under the `natural_scale` reference type.

**Approach 4. Control area in rings, as 3Bee does [VENDOR].**
- **How it works.** The site is compared with a control area in 5, 10 and 15 km rings. This is taken from 3Bee's public pages; their full method is not published.
- **What we adopt.** We use it for `regional_context` (P4 and the P1 loss rates) and for the landscape-context rings. It does not select least-disturbed conditions, so it is not used as a condition reference.

**Recommendation: Approach 2 for condition and Approach 4 for pressure and landscape context.**
- If a reference type has fewer pool pixels than the minimum (default 200 sample pixels, configurable), its status becomes `reference_insufficient` and its metrics are not scored. The pipeline never falls back silently.
- The minimum pool size and R are scientific parameters. They will be set from the probe evidence and recorded in the decision log.
