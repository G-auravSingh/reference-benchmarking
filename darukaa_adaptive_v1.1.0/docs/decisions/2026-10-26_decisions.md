# Decisions of 26 Oct 2026 (approved by Gaurav)

Evidence: R2 run 2, an end-to-end Colab run on live Earth Engine at commit 83dc82a9. See `validation/R2_review_2026-10-24.md`, "R2 run 2".

**D-26-1. Low-pressure reference: a naturalness floor and a wider search.** This refines D-25-1.

1. **Floor.** A block must be at least 50% natural in 2020 to qualify for the low-pressure reference, at either stage:
   - the strict stage (≥ 90% natural);
   - the quantile stage (the most natural 20% of blocks).
2. **Wider search.** If fewer than 20 blocks qualify, the search widens from 25 km to 50 km, then to 100 km.
   - The search stays in the same RESOLVE ecoregion.
   - Every widened ring still excludes all sites plus 1 km.
   - Natural share is measured first; pressure metrics are measured only on the blocks that qualify.
3. **If still too few.** P4 is not scored (`reference_insufficient`). The report then shows only the absolute class and the "versus surroundings" figure.

The stage and the search radius actually used are recorded for each site. The "worst" end of the scale stays the 95th percentile of all blocks in the 25 km ring.

**Why.** In R2 run 2, Ludhiana's "most natural 20%" of blocks were only 0.3% natural. The site was being compared with cropland like itself and scored P4 = 100.

**D-26-2. Fire-year validity.** A pixel-year counts as observed if:
- any month records a burn, or
- at least 6 months carry the MCD64A1 valid-data QA flag.

Pixel-years that are not observed stay masked; they are never counted as unburned.

**Why.** The earlier rule required all 12 months valid. Monsoon cloud then removed most years in the Western Ghats, and only 12 of 23 Silent Valley reference blocks had any valid year.

**Mechanical, under the existing contracts.** `ndvi_peak_season` and `lai_s2` apply only to vegetated natural types: forest, woodland, shrub, grass and wetland. In R2 run 2, Pune's only natural pixels were water.
