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
