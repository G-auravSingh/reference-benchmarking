# Decisions of 25 Oct 2026 (approved by Gaurav)

**Evidence base**
- CR1 probe and R2 run 1. These were an end-to-end Colab run on live Earth Engine on 24 Oct, at commit 80f1ce38.
- The full review is in `validation/R2_review_2026-10-24.md`.

**D-25-1. Pressure (P4) reference: option B, without circularity.**
- **What changed.** This replaces D-23-9, which compared pressure against all land in the region. Under that rule an intensively used region flattered its sites: Ludhiana cropland scored P4 = 100.
- **Reference.** Low-pressure blocks:
  - The blocks are square, the same size as the site, and lie in the same ring and RESOLVE ecoregion.
  - They are selected by their 2020 natural-ecosystem share (ForTy / SBTN) in two stages:
    1. Strict: blocks that are at least 90% natural.
    2. Otherwise: the most natural 20% of blocks.
  - At least 20 blocks are required; otherwise the reference is marked `reference_insufficient`.
- **No circularity.** No pressure metric is used to choose the reference. The natural share comes from 2020 maps, while the pressure metrics come from other datasets and the current window.
- **Worst value.** The 95th percentile of all ring blocks, with the contract maximum as fallback.
- **Response.** The bounded function from decision 4, unchanged.
- **Shown beside the score, never blended into it:**
  - the all-ring score ("versus surroundings", option A);
  - for gHM, the absolute class from Kennedy et al. 2019 (0.1 / 0.4 / 0.7; option C) [ACAD].
- **Parameters.** The 90% threshold, 20% share and 20-block minimum are first-draft implementation values, logged in `PoolConfig` and reviewed at R3.

**D-25-2. Peak-greenness window.** The window is chosen over the sites plus a 1 km buffer, not the sites alone. Small or patchy sites, such as agroforestry plots and fragments, otherwise pick their window from too few clear pixels.

**Mechanical fixes from R2 run 1.** Covered by earlier decisions and committed separately:
- the reference sample fetch;
- the FLII ×1000 scale;
- the Meta CHM band;
- context-window growth;
- the GRIP4 asset path.
