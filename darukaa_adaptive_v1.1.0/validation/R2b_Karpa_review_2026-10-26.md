# R2 run 3 and R2b (Corbett Karpa): review (26 Oct 2026)

**Evidence.** End-to-end Colab runs on live Earth Engine at commit `157d84b8`. The outputs were read offline here.

## R2 run 3: 30 PASS, 0 MISS, 2 NO_DATA

| Control | Result | Reading |
|---|---|---|
| Silent Valley forest | Condition 92.9 (90% interval 92.2–93.0); P4 98.3 | P4 used strict low-pressure blocks within 25 km. Fire frequency is now scored after D-26-2. |
| Small forest (0.5 ha) | Condition 74.9; P2 56.2 | P2 is limited by canopy height: Meta reads 4.7 m on this 0.5 ha, while GLAD reads 14.6 m. This is a source disagreement on a tiny patch. The new pillar flag names the limiting metric. |
| Ludhiana cropland | P4 not scored (NO_DATA) | No block ≥ 50% natural within 100 km in the same ecoregion, so the result is `reference_insufficient` (D-26-1). gHM class "high"; the "versus surroundings" figure is shown as context. The pre-registered rule "P4 ≤ 60" is unmet *by design*: the site is withheld rather than flattered. |
| Pune built-up | P4 not scored (NO_DATA) | Same cause as Ludhiana. gHM class "very high", "versus surroundings" score 0. |

**Consequence to note.** Sites in fully converted landscapes get no P4 score. They get the absolute class plus the comparison with their surroundings. If a P4 number is wanted there, the only defensible source is the absolute scale (option C), which is not yet available for all P4 metrics.

## R2b: Corbett Karpa (151 ha, single polygon)

**Ecoregion.** Narmada Valley dry deciduous forests (RESOLVE ID 296). The condition pool used strict least-disturbed pixels for forest, woodland and shrub.

**What the run says**
- **Natural vs managed.**
  - 10.1% of the site was natural in 2020 (ForTy/SBTN) and 9.6% is natural now.
  - 4.9% of the 2020 natural area has been lost.
  - **128 ha (85%) is candidate gain**: managed in 2020, natural-class vegetation now.
  - This matches the 2018–2026 agriculture-to-scrub transition in the TCF report (p.8).
  - Under Nature Positive rules, land restored after the baseline counts as *gain*, not as natural baseline extent.
- **P1 = 1.9.** Natural extent is 9.6%; core natural area is 1.9%.
- **P2 = 0.3.** The pillar is set by `canopy_height_m`: Meta 1 m reads about 0.002 m over the 14.6 ha of natural woodland and shrub. NDVI attainment is 94.7 and BII attainment 85.6.
  - EII is below support (2.9 natural pixel-equivalents). Fixed: the window now scales with the natural-pixel shortfall.
  - GEDI has 8.5 footprints, below the 10 needed.
  - FLII is not applicable because there is no natural-forest stratum.
- **Headline.** Condition 0.8 (P1 + P2). Pressure 67.3, with gHM 0.157 ("moderate") and population as the limiting component.
- **Errors (fixed).**
  - The threatened-species count failed because the birds snapshot has no `category` field. Birds are now excluded explicitly until their field is confirmed.
  - The restricted-range filter used `List.filter` incorrectly.
  - Aridity had no 2025 TerraClimate data. It is now anchored on the latest month TerraClimate covers.

**Comparison with the TCF baseline report (v1.1).**

The report was produced with the older methodology and is Darukaa's own earlier evidence [DARUKAA]. As Gaurav noted, it is read with caution, not as a target.

| Metric | TCF report (Karpa) | This run | Why they differ |
|---|---|---|---|
| Natural habitat % | 97.07 (p.12) | 9.6 (+128 ha candidate gain) | The old method counted current DW natural classes. The new method requires natural in 2020 (SBTN/ForTy), so regrowth since 2020 is reported as gain, not as baseline extent. |
| CPLAND | 93.67 | 1.9 | Follows from the change above. |
| NDVI | 0.308 (annual) | 0.515 (peak Aug–Oct, natural vegetated pixels) | Different statistic and different pixels. |
| FLII | 6.01 | not applicable | No natural-forest stratum at the site. |
| Night lights | 0.479 | 0.481 | Agree. |
| Human modification | 0.441 ("GHMI", older layer) | 0.157 (gHM v3, 90 m) | Different dataset and scale. |
| Day LST | 29.8 °C (MODIS) | 38.2 °C (Landsat median, 30 m) | Different sensor and statistic. Contextual only. |

## Findings that need a decision

**F-1. Canopy height at changing or young sites.**
- Meta's canopy height comes from imagery dated 2009–2020. Over Karpa's woodland it reads about 0 m.
- Probe CR1 has been extended to explain this, by comparing Meta, GLAD and GEDI with Dynamic World tree probability and the ForTy and SBTN classes at Karpa.
- Proposed rule, once the probe confirms the cause:
  - when canopy-height sources disagree by more than 50%, or Meta predates the land-cover state being measured, `canopy_height_m` becomes `source_disagreement`;
  - it is then not scored, so it cannot set a pillar.

**F-2. What the condition headline means for restoration sites.**
- The headline is the geometric mean of P1 (how much natural) and P2 (condition of the natural part).
- At a restoration site it is therefore near zero by construction: Karpa scores 0.8, even though 85% of the area is regrowing.
- Nature Positive keeps extent and condition as *separate* indicators.
- Proposed:
  1. Report P1 (extent, with gross gain beside it) and P2 (condition) side by side, and drop the combined P1 × P2 number.
  2. Show a restoration panel (candidate gain in ha and as % of site) prominently, labelled preparatory.

## Run 2 (27 Oct 2026, commit 1bfc37a7)

**Evidence.** End-to-end Colab run on live Earth Engine: `probe_results.json` (controls plus Karpa) and `Corbett_Karpa.zip`, read offline here.

### Results

| Item | Value | Note |
|---|---|---|
| Natural extent (P1) | 1.9, High confidence | Set by core area (1.9%); extent is 9.6% |
| Condition (P2) | 0.3 (0.2–0.4), Medium | Set by `canopy_height_m`; function component 86.4, composition 85.6 |
| Species (P3) | not covered | Licence-restricted (comply or explain) |
| Pressure (P4) | 67.3 (57.8–79.3), Low | Set by population density (WorldPop 2020: 211 per km² against a reference of 100) |
| SoN score | 0.8 (0.6–0.9), Medium | Weakest pillar P2; coverage "extent and condition only; species not covered"; no divergence flag (the gap is under 20 points) |
| Candidate gross gain | 128.2 ha | Shrub 98.3, trees 29.5, grass 0.4 |
| Gross loss | 0.76 ha | All from other natural land, converted to cropland; no natural-forest loss |
| Low-pressure reference | 24 blocks within 25 km | All at least 82% natural (D-26-1) |

**F-2 is addressed.** The report now leads with the pillar profile and the restoration panel (D-27-2, D-27-3).

### F-1 evidence: canopy-height sources on the probe units

Whole-unit means, all classes:

| Unit | Meta v1 (1 m) | GLAD (30 m) | GEDI rh98 (footprints) | DW tree probability | ForTy / SBTN 2020 |
|---|---|---|---|---|---|
| Silent Valley forest | 15.7 m | 17.0 m | 23.9 m (500) | 0.72 | ForTy primary or regenerating forest |
| Small forest (0.5 ha) | 4.8 m | 14.6 m (5.6 px) | none | 0.72 | ForTy naturally regenerating |
| Karpa | 0.003 m | 0.0 m (all pixels code 0) | 3.3 m (95) | 0.20 | ForTy "other land"; SBTN mostly class 15, with about 10% class 3 |
| Ludhiana cropland | 0.05 m | 0.03 m | 4.9 m (328) | 0.09 | SBTN 12 |
| Pune built-up | 1.4 m | 0.18 m | 15.3 m (319) | 0.04 | SBTN 13 |

**Reading the table:**
- **Small forest.** The sources disagree: Meta reads 4.8 m where GLAD reads 14.6 m. Meta v1's known underestimation (MAE 4.3 m) makes this a likely source error.
- **Karpa.** The sources do not disagree. Meta and GLAD both read about 0 m, and GEDI reads 3.3 m over the whole site. In 2020, SBTN's map shows Karpa's natural land as about 10% class 3 (natural short vegetation, if the class codes are as I recall). That share matches the mask's 10.1% natural in 2020.
- **The "woodland" (8.9 ha) and "shrub" (5.6 ha) strata** come from current Dynamic World labels. The 0.3 is therefore a 2018–2020 structural reading of land that Dynamic World now labels woody. It is not a source error. Whether the reading still describes the site cannot be known from data that predates the change.
- **GEDI over built-up land** (Pune, 15.3 m) reads buildings. GEDI is valid only on natural vegetated pixels, which is how `gedi_rh98_m` is already weighted.
- The SBTN class codes above are from my reading of the SBTN v1.1 legend and have not been re-checked against the asset metadata.

The proposal is P-27-4 in `docs/decisions/2026-10-27_decisions.md`.

### Other findings and fixes

- **Birds' Red List field confirmed.** `RedList__5` holds CR/DD/EN/LC/NT/VU; `RedList_IU` is an ID and `RedList__1` is the taxonomic order. Birds now count in `threatened_species_range_count` (mechanical; completes the 26 Oct exclusion).
- **Aridity reported a 0-year data gap** although TerraClimate ends 2024-12. Its period text carries no year, so the gap was missed. Fixed: the gap is now read from the recorded `period_end`. Aridity is contextual, so no score changed.
  - Remaining metrics whose recorded period has no year: KBA and WDPA ("current release") and the IUCN range snapshots. None is scored. Their gap is shown as 0 and should be read as "not recorded".
- **JRC GFC2020 V2 is deprecated** (Earth Engine warning: superseded by V4). The probe now reads V4 bands; the switch follows once they are confirmed.
- **CHMv2 is not reachable in Earth Engine.**
  - Listing Meta and WRI's project is denied.
  - `projects/sat-io/open-datasets/facebook` is not a folder.
  - The 403 warning in the Colab log is this listing call; it is harmless.
