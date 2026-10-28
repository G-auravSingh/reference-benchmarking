# Decisions of 28 Oct 2026 (approved by Gaurav)

## D-28-1. Canopy-height evidence rules (P-27-4 and P-27-5 approved)

**Evidence.** Probe of 27 Oct (end-to-end Colab run on live Earth Engine) and Karpa run 2. See `validation/R2b_Karpa_review_2026-10-26.md`, "Run 2".

### What `canopy_height_m` measures

- The mean of Meta/WRI v1 1 m top-of-canopy heights.
- Gaps between crowns count as about 0 m, so the value mixes height and cover. It is not tree height.
- It is computed over natural woody pixels (ForTy natural forest, Dynamic World woodland, Dynamic World shrub). A pixel counts only if it already had the same woody class as the 2018–2020 Dynamic World mode:
  - trees, for forest and woodland;
  - shrub and scrub, for shrub.
- The value is reported by type, with the area in ha.

### Statuses

None of these is ever a 0. They are applied in this order:

1. **`source_predates_state`.** Too little support remains because the woody cover is newer than the imagery. The excluded area in ha is reported.
2. **`source_disagreement`.** Like-for-like sources differ by more than 50%. The comparison is the Meta 95th percentile per 30 m cell, averaged, against:
   - GLAD 2019 over the same pixels, with at least 4 px; or
   - GEDI rh98 median, with at least 10 quality-filtered footprints and a reading of at least 5 m.

   A gap-inclusive mean is never compared with a top height.
3. **`below_detection`.**
   - Meta: under 2 m. The weakness of v1 on low vegetation is described in the CHMv2 paper; the 2 m floor itself is Darukaa's choice.
   - GLAD: every pixel reads 0 ("no forest canopy detected").
   - GEDI: under 5 m. This is an empirical floor: the probe read 4.9 m over cropland and 15.3 m over buildings.

The raw reading is kept in the extras as `raw_mean_m`.

### Labels and evidence panel

- The report and `canopy_height_evidence.csv` list each source with its quantity, reading, support and the caveats.
- **Caveats shown:**
  - single-date imagery, mostly 2018–2020;
  - no field validation above 25 m (WRI Land & Carbon Lab);
  - limited training geographies;
  - slope and shadow bias;
  - GLAD saturates above 30 m (GEE community catalogue);
  - no India-specific validation was found.
- **Small-forest probe step.** Section 4 now records like-for-like evidence per unit (`canopy_like_for_like`). It also records image links for Meta 0–30 m, Sentinel-2 RGB and the Dynamic World 2018–2020 mode (`canopy_thumbnails`).

### Thresholds to review on live data

- 2 m (Meta floor);
- 5 m (GEDI floor);
- 50% (disagreement);
- 4 px (GLAD support) and 10 footprints (GEDI support).

These are Darukaa choices [DARUKAA].

## D-28-2. Preparatory species metrics for P3 (Gaurav, 28 Oct)

Gaurav's instruction: keep the range-map metrics, add the Nature Positive preparatory extinction-risk and species-population metrics, and set licence questions aside. The range snapshots are Darukaa-held.

### Metrics added

All three are reported, not scored.

| Metric | Standard basis | Calculation |
|---|---|---|
| `star_t_estimated` | Guidance p.26: preparatory example "estimated STAR-t"; range allowed where area of habitat is unavailable (p.26 footnote) [STD] | 100 × Σ species of weight × (site area in range ÷ global range area). Weights CR 4, EN 3, VU 2, NT 1, LC 0 (Mair et al. 2021). |
| `rarity_weighted_richness` | Guidance p.26 example [STD] | Σ species of (site area in range ÷ global range area) |
| `priority_species_habitat_trend` | Guidance p.28 (species populations); Technical Output Report p.74: at preparatory level, relative abundance using area of habitat as a proxy is accepted [STD] | For each CR/EN/VU species: natural habitat within range on site, 2020 against now, plus candidate gain. Declining at −5% or worse; increasing (candidate) when gain is at least 5%; otherwise stable. Value = % declining. |

### Range filters and data handling

- Range features are filtered to presence 1 (extant), origin 1–2 (native or reintroduced) and seasonal 1–2 (resident or breeding).
- If the filter removes every overlapping feature, that is an error (a field-type mismatch), never zero species.
- Category fields: mammals `category`, birds `RedList__5`, plants `category` (plant values not yet checked).
- Global range area is the sum of feature areas, so overlapping seasonal polygons may inflate it slightly. Per-species site area is capped at the site area.

### Why reported but not scored

- **Extinction-risk shares measure importance**, the site's share of global threat-weighted range. They have no good or bad direction at a baseline. Under the Guidance, change in that share over time is what is tracked.
- **The habitat trend largely restates P1 on small sites**, where most ranges cover the whole site. Scoring it would double-count.
- **Consequence:** P3 stays `insufficient_evidence`, and the SoN score stays P1 + P2. The Nature Positive coverage table now reads "partly (preparatory, reported not scored)" for both species indicators.
- **Open question for Gaurav:** whether any of these should be scored once monitoring years exist (change in STAR-t, share of priority species not declining).

## D-28-3. CHMv2 parked

Stay on Meta v1. The Cloud Storage route (D-27-1 option b) is not pursued for now. The configurable source (`chm_source`) stays in place for later.
