# Scoring Architecture and Indicator Contract — v0.2.8

**Status: Phases 1–3 delivered on branch `v0.2.8-contract`. The v0.2.8 engine is NOT wired into the production pipeline; `main` (and Colab) stay on v0.2.7.**

| Item | Where it is |
|---|---|
| Machine-readable contract | `darukaa_reference/indicator_contract.py` (46 contracts, validator, status vocabulary) |
| Comparison-unit framework | `darukaa_reference/support.py` (numpy reference semantics plus Earth Engine builders) |
| Tests | `tests/test_indicator_contract.py` (21), `tests/test_support_framework.py` (22). Full suite: 112 passing. |
| Evidence base | `docs/Indicator_Audit_Matrix_v0.2.7.md` |
| Main branch | Untouched. Colab keeps running the v0.2.7 code until the phases below pass. |

---

## 1. Principles

- **P1. Same construct.** A site value and its reference must measure the same quantity. That means the same unit, the same temporal window, the same spatial support and the same target population.
- **P2. Tier is not scoreability.** `reference_tier` only classifies the reference population:
  - tier1 = regional distribution;
  - tier2 = stratified or least-disturbed pool;
  - absolute = a fixed reference level.

  Whether an indicator is scored is a separate, documented decision.
- **P3. Condition vs pressure.**
  - A *condition* indicator is compared with a reference condition: a least-disturbed stratum, an absolute level, or comparable water bodies or rings.
  - A *pressure* indicator is compared with the regional distribution. A least-disturbed pool is near-zero pressure by construction (audit X8).
- **P4. No selection on the outcome.** An indicator may not use, as an input, a variable that selects its own reference pool (X2).
- **P5. Support matching.** The reference is built from units of the same size and kind as the site unit. It is never a single-pixel distribution for a polygon-level metric (X1).
- **P6. Native resolution.**
  - Statistics are computed at the dataset's native pixel.
  - The reference is never sampled finer than the native pixel (X7).
  - A condition indicator is not scored on a site smaller than N native pixels (X6).
- **P7. No silent exclusion.** Every indicator on every tile has exactly one status from §5, plus a reason.
- **P8. Validation before activation.** An indicator becomes scoreable only when:
  - its `current_defects` are empty;
  - it has passing synthetic and live evidence;
  - its native resolution has been verified.

## 2. Contract schema (`IndicatorContract`)

| Field | Meaning |
|---|---|
| `definition` | The quantity, in words, including numerator and denominator where relevant. |
| `site_support` | The unit the site value is computed over. See §3. |
| `reference_support` | The unit each reference value is computed over. It must be the matched counterpart of `site_support`. |
| `reference_population` | Which units form the reference: `regional_all`, `least_disturbed_stratum`, `regional_stratum_unfiltered`, `absolute_level`, `comparable_water_bodies`, `comparable_riparian_rings`, or `none`. |
| `reference_tier` | Classification only: `tier1`, `tier2`, `absolute`, or none. |
| `applicability` | Domains; ecosystem (`any` / `woody` / `open_water`); required feature (`water_body` / `forest_baseline_5ha`); `min_native_pixels`; `min_pure_water_pixels`. |
| `proposed_scoreability` | `scoreable` / `contextual` / `screening` / `pending_methodology` / `removed`. This is the **proposal**, not an active state. |
| `estimator`, `direction` | The benchmark formula (`log_response_ratio`, `robust_z`, `reference_percentile`) and its orientation. |
| `temporal` | A single window specification, shared by site and reference by construction. |
| `native_resolution_m`, `resolution_verified` | The native pixel size, and whether it has been checked against a primary source. |
| `inputs`, `redundancy_groups` | Inputs are used for the circularity check. Redundancy groups feed Phase 7. |
| `requires_sensitivity_check` | For example, `bii` under a low-HMI pool. |
| `image_is_single_band`, `site_relative_normalisation` | Must be `True` and `False` respectively for a scoreable indicator. |
| `current_defects` | The gap between the v0.2.7 code and this contract. Must be empty before `validated=True`. |
| `validated`, `validation_evidence` | Set only by Phases 3–6. |

**Validator rules** (`validate_contract`; each rule has a test that fires on a deliberately bad contract):

1. The site and reference supports are matched.
2. A scoreable indicator has a reference population, estimator, direction, temporal window and native resolution.
3. There is no site-relative normalisation (X3).
4. The reference image is single-band (X4).
5. The reference population fits the construct type (X8).
6. The indicator's inputs are disjoint from its population's selectors (X2).
7. A condition indicator has a site-support rule (X6).
8. A water-body indicator has a pure-water rule.
9. `validated` requires no defects, evidence, and a verified resolution.

## 3. Comparison-unit framework (`support.py`)

| Site support | Matched reference support | Construction |
|---|---|---|
| `polygon_proportion` | `site_window_proportion` | Mean of a 0/1 image over a tessellation cell (square block of native pixels, area ≈ site area) |
| `polygon_mean` | `site_window_mean` | Mean of a continuous image over the same cell |
| `polygon_rate` | `site_window_rate` | Σ numerator area / Σ denominator area × 100 / years over the cell, with a denominator floor. It is **never** the mean of per-pixel rates. |
| `water_body_unit` | `water_body_unit` | The metric over each comparable water body's own pure-water mask (eroded 1 px) |
| `riparian_ring_unit` | `riparian_ring_unit` | The metric over a fixed-width ring around each comparable water body, excluding all water |
| `polygon_scalar`, `not_computed` | none | Not benchmarked |

- **Coverage.** Windows with less than 90 % valid coverage are dropped, so every reference value represents a full site-sized area.
- **Cells, not moving windows (Phase 3 revision).** A disc window at every 10 m pixel costs ~4,000 neighbours per pixel over a ~78-million-pixel zone, which Earth Engine cannot compute even when sampling only spaced points. The reference unit is therefore a **tessellation cell**: side = round(√site area / native pixel) native pixels, aligned to the native grid (a 40 ha site at 10 m → 63×63 px = 39.7 ha; 0.47 ha → 7×7 px). Cells tile the zone without overlap, so no pixel is counted twice. A product whose pixel exceeds the site uses 1 pixel per cell (the covering pixel's value). The moving-disc functions in `support.py` remain as a tested alternative definition but are not what Earth Engine computes.
- **Comparable water bodies** have an area within [site/3, site × 3] and a mean permanence within ±0.25 of the site's. Both thresholds are proposed and need your decision (§8).

**Verified by synthetic tests with known answers:**
- A window proportion recovers the regional proportion, with the analytic binomial spread.
- A window mean has the analytic σ/√k spread. The pixel spread overstates it more than 10-fold.
- A rate is the ratio of sums. The mean of per-pixel rates is shown to differ.
- The site rate equals the reference window rate at identical support.
- The 5 ha floor is enforced.
- Water bodies are found with exact areas.
- A 2 × 2 pond has no pure water.
- Water metrics carry no land contamination.
- Ring pixel counts match the analytic value and rings exclude neighbouring water.
- A coarse 4.6 km cell is sampled exactly once.

**Unverified Earth Engine assumptions** (checked by the parity harness in the smoke test):
- **A1.** `image.reproject(native).reduceResolution(mean, maxPixels=cell²).reproject(cell)` is the exact mean of the native pixels in each cell (masked pixels ignored), on a grid aligned to multiples of the cell size from the CRS origin.
- **A2.** `stratifiedSample` in the cell projection returns one value per valid cell.
- **A3.** Water bodies vectorised on the native UTM grid, pure-water erosion via `focal_min`, and `reduceRegions` per unit match the numpy `label_units` / `unit_values`.
- **Cost.** One pass over the native pixels (`reduceResolution` + `reproject`), the same order as the v0.2.7 10 m sampling. Not yet timed live.

## 4. Proposed scoreable sets (from the contract; none active)

| Domain | Scoreable indicators |
|---|---|
| Terrestrial (8) | natural_habitat, forest_loss_rate (only where baseline forest ≥ 5 ha), ndvi, chm (woody ecosystems only), bii, ghm, hdi, light_pollution |
| Aquatic (4) | tspi, sabf, wcpi, sdi |
| Shared with aquatic | ghm, hdi, light_pollution are landscape pressures and also apply to aquatic sites |
| Pending | cpland (asset provenance), net_tree_cover_change_rate (redefinition), rci (redefinition), hsas (eDNA) |

**Aquatic C3 (fauna) has no EO-based indicator.** The report must say so explicitly.

## 5. Status model (per tile, per indicator)

The statuses are:
- `not_applicable`, with one of these reasons: `domain_mismatch`, `target_feature_absent`, `ecosystem_type_mismatch` (woody only), `site_below_product_resolution`, `insufficient_pure_water`;
- an indicator whose applicability could not be *determined* (the water-body probe failed or was inconclusive) is **`applicable_but_no_site_value` with reason `applicability_undetermined`**, never `not_applicable` (§12.2);
- `applicable_but_no_site_value`;
- `applicable_but_no_reference`;
- `reference_available_but_not_scoreable`;
- `scored`;
- `contextual_only`;
- `screening_only`;
- `suppressed_for_stability`;
- `pending_methodology`.

`no_reference` is retired.

**Order of evaluation** (this also determines which references are computed):
1. Applicability (domain → water-body feature and pure-water floor → woody ecosystem → forest baseline → site support). If not applicable, no reference is computed.
2. Site value. If none, no reference is computed.
3. Reference.
4. Stability.
5. Scoreability.

Tier-1 and Tier-2 references are both written to JSON, CSV and HTML whenever they exist.

## 6. Redundancy (Phase 7 input)

Only one group has more than one proposed-scoreable member: **R1** (chm + ndvi). The other groups have at most one scoreable member, because their other members are contextual:

| Group | Scoreable | Contextual |
|---|---|---|
| R2 | ghm | eii_structural, flii |
| R3 | bii | eii_compositional |
| R4 | tspi | iri, mspl |
| R5 | hdi | iri |

The aggregation rules must be defined before the headline is computed. The proposal for R1 is to give `ndvi` its own subdimension (greenness) and keep `chm` in structure, with each scored in its own subdimension. That is a Phase 7 decision.

## 7. Indicator-by-indicator implementation plan

### Step 0: shared infrastructure (before any indicator)
1. **Applicability and status engine.** It evaluates each contract per tile (§5), skips reference computation when an indicator is not applicable or has no site value, and emits the status and reason.
2. **Support-matched reference paths** in `reference.py`. These are the window, rate, water-body and ring builders from `support.py`, replacing the single-pixel reference for contracted indicators only.
3. **`reference_percentile` estimator** in `scoring.py`, if you approve it (§8).
4. **Report fields.** Both tiers, reference support, reference median and MAD, reference n, status and reason.

### Phase 3: indicators with confirmed defects

| Indicator | Site change | Reference change | Synthetic test | Live check |
|---|---|---|---|---|
| forest_loss_rate | keep num/den rate | `ee_window_rate_image` (same window, 30 % threshold, 5 ha floor) in the least-disturbed stratum | known-rate fixture; site = window at identical support; values in %/yr | **Deccan is not applicable (0.01 ha).** Needs a tile with ≥ 5 ha forest baseline, possibly not in Tata (§8) |
| net_tree_cover_change_rate | redefine (proposal): change in DW tree-cover share, early window (2017–18) vs recent window, percentage points per year, same classifier both ends | window version of the same | identical start/end → 0; planting from bare land → positive | after you decide on the definition |
| sabf | pure-water mask per water body | comparable water bodies | land never counts as bloom | aquatic tile |
| wcpi | raw 1/(TSM+1) over pure water, no site normalisation | comparable water bodies | site value independent of its own min/max | aquatic tile |
| edpp | single-band EDPP, absolute thermal scaling | same construct | reference band = site construct | stays screening |
| mspl | remove the site-relative thermal term | single-band | same | stays context |
| rci | redefine (proposal): natural-vegetation share of the riparian ring | comparable rings | ring geometry test (exists) | aquatic tile |
| sdi | disturbed share of the ring | comparable rings | ring vs all-land difference | aquatic tile |
| ghm | site read at native 90 m | window mean, regional unfiltered stratum | site scale = native | Deccan |
| natural_habitat | unchanged | cell proportion, regional ecoregion (D2); 100 % as a diagnostic | known answer in `test_natural_habitat_regional_window_reference_and_absolute_diagnostic` | Deccan |
| cpland | — | — | — | **blocked until the PV binary provenance is documented** |

### Phase 4: remaining proposed-scoreable indicators
- **ndvi, chm, bii, hdi, light_pollution:** wire to window references.
- **chm:** site read at 10 m, plus woody-ecosystem applicability.
- **bii:** add the sensitivity benchmark.
- **Each indicator** gets a synthetic fixture and appears in the Phase 5 table.

### Phase 5: terrestrial live validation (EMU_Deccan_forest)

The output table has these columns: `indicator | applicable | site_value | reference_n | reference_median | reference_MAD | reference_support | benchmark | scoreable | status | exclusion_reason`. Both tiers are shown.

The run also checks the Earth Engine assumptions A1 and A2 and the cost of the window step.

### Phase 6: aquatic live validation
1. **Lake_Suman first:** the larger body, with the most pure-water pixels.
2. **Then one pond,** to exercise the minimum-pixel rule.
3. **Checks:** the pure-water mask, water-body identification, size and permanence matching, the season window, ring construction, the reference water bodies, and tspi / wcpi / sabf / sdi behaviour.

### Phase 7: redundancy and headline aggregation rules (§6)

### Phase 8: reporting (§5), across JSON, CSV and HTML

## 8. Decisions taken (Phase 3 brief) and how they are implemented

| # | Decision | Implementation |
|---|---|---|
| D2 | natural_habitat: benchmark = site-sized windows in the regional/ecoregional population; keep 100 % natural as a separate diagnostic | population `regional_ecoregion` (no land-cover stratum, no pressure filter); percentile estimator; `absolute_natural_reference` diagnostic reported beside, never inside, the score |
| D3 | Generic hard floor 10 native pixels; indicator-specific floors where justified; aquatic ≥ 10 pure-water px + valid water-body geometry; explicit in contract | `Applicability.min_native_pixels=10`, `indicator_min_native_pixels` (natural_habitat, net_tree_cover_change_rate: 100 px, rationale recorded), `floor_basis` (`polygon_native_pixels` / `pure_water_pixels` / `exempt_landscape_pressure`). **Landscape pressures (ghm, hdi, light_pollution) are exempt from the polygon floor: my assumption, needs your confirmation.** |
| D5 | net_tree_cover_change_rate rebuilt on one product/time series | Dynamic World tree-cover share, early (2017–18) vs recent (ndvi_year−1..ndvi_year), pp/yr between period mid-points; one function builds both endpoints; no Hansen. Percentile estimator (tie-heavy reference). |
| E1 | forest loss: empirical percentile/CDF; explicit direction, ties, zero windows; keep distribution and n | `reference_percentile`, `lower_is_better`, mid-rank ties, `fraction_reference_zero`, `p_reference_tied/worse/better`, `reference_n`, DKW 95 % half-width |
| E2 | Comparable water bodies: area ratio in [1/3, 3], \|permanence difference\| ≤ 0.25; documented minimum n; `reference_n` exposed; otherwise `reference_available_but_not_scoreable` | `MIN_COMPARABLE_WATER_BODIES = 10` (my proposal), radius ladder 10/25/50 km, funnel counts (`n_rejected_size`, `n_rejected_permanence`, …) in the audit trail |
| E3 | RCI → 100 m riparian-ring natural-vegetation proportion, honestly named | `rci` retired; `riparian_natural_veg_share` (same ring, DW natural classes, land only, all water excluded, for target and every reference ring) |
| E4 | External forested validation polygon, labelled, never in Tata scoring | `SiteEvidence.validation_dataset_label`; `project_assessments()` drops validation-only results. **The polygon itself is not chosen yet.** |

## 8b. Decisions confirmed at the Phase 3 review

| # | Decision | Where it lives |
|---|---|---|
| 1 | Generic condition support floor = **10 native pixels**. A stricter floor is allowed only if scientifically justified and documented (validator requires `min_support_rationale`); **none is currently used**, so `natural_habitat` and `net_tree_cover_change_rate` use 10 and all Tata zones (≥ 47 px at 10 m) are assessed. | `Applicability`, `effective_min_native_pixels` |
| 2 | `ghm`, `hdi`, `light_pollution` are exempt from the condition-polygon floor as **landscape-pressure indicators** (one named rule, `PRESSURE_SUPPORT_RULE`); condition indicators are never exempt (test). | `indicator_contract.PRESSURE_SUPPORT_RULE` |
| 3 | Minimum reference population = **30 windows** (cells); below it `reference_available_but_not_scoreable` (`insufficient_reference_n`), tested for all nine window indicators at n = 29 vs 30. | `MIN_REFERENCE_WINDOWS` |
| 4 | Minimum comparable aquatic references = **10 water bodies**; the audit trail exposes candidate count, size rejections, permanence rejections and the final count. | `reference_funnel` column |
| 5 | Percentile scoring approved for `natural_habitat`, `net_tree_cover_change_rate`, `sabf`, `sdi`, `riparian_natural_veg_share` (and `forest_loss_rate`). Convention defined once, ties tested per indicator. | `IC.PERCENTILE_CONVENTION`, `benchmarking.percentile_benchmark` |
| 6 | **20–40 °C withdrawn.** EDPP / MSPL thermal term is scaled over the source product's documented valid range (Landsat C2 L2 ST: DN 293–65535 → 150–373 K → −123.15…99.85 °C, USGS) as a numerical / QC bound; values outside it are masked. No ecological threshold is adopted; both stay screening / context. | `constructs.LST_QC_*` |
| 7 | Riparian ring **100 m**, stored in the contract (`parameters`) and `Config.riparian_ring_width_m`. | contract + config |
| 8 | Early period **2017–18** for the tree-cover change, identical processing at both endpoints, in the contract and `Config.net_change_early_years`. | contract + config |
| 9 | `net_forest_change_rate` → **`net_tree_cover_change_rate`**: documented as a remote-sensing tree-cover proxy. Equivalence with forest change is **not demonstrated** (the DW "trees" class can include plantations and tall tree crops; "forest" is a definitional / land-use concept). | registry citation, contract limitation |
| 10 | `forest_loss_rate` keeps the ≥ 5 ha rule; the 25/6/3-year denominators and baseline-canopy masking are checked by a synthetic known-rate case; a live check needs a forested polygon (Deccan has 0.01 ha). | tests; smoke notebook cell 8 |

## 9. Phase 3 delivered

New modules: `constructs.py` (shared constants), `benchmarking.py` (engine), `reference_builders.py` (numpy definitions),
`reference_builders_ee.py` (Earth Engine builders + shared water-body selection rule). Tests: 175 passing (112 before Phase 3).

**Engine guarantees (each has a test):** every site/reference pair passes construct, unit, temporal, spatial-support and
population checks or the indicator is `reference_available_but_not_scoreable` with the violations listed; a zero-inflated
or tie-heavy reference can never reach robust-z / log-response-ratio (explicit `suppressed_for_stability`, never a silent
fall-through); nine explicit statuses, each with a reason; `no_reference` cannot be produced; Tier-1 and Tier-2
references are both kept visible; minimum reference n is enforced from the contract.

### Defects found while implementing (not in the earlier audit)
1. **forest_loss_rate year counts (a numbers change).** Windows were divided by 24 / 5 / 2 for windows that contain
   25 / 6 / 3 annual loss codes. v0.2.7 rates were therefore too high by 4 % (long-term), 20 % (2020–25) and 50 % (2023–25).
2. **forest_loss_rate numerator (a numbers change).** Loss was counted on any pixel with canopy > 0 % but divided by a
   ≥ 30 % canopy baseline, so the numerator was not a subset of the denominator.

## 10. Still to do (Phase 5 first task: wiring)

The v0.2.8 engine and builders are not called by `ReferenceSelector.compute()` yet. The Phase 5 work is to:
1. orchestrate per-tile evidence (domain, ecosystem tags, forest baseline, water body), site values and references, and call
   `evaluate_indicator`; 2. write both reference tiers and the nine statuses to JSON / CSV / HTML (Phase 8 wording);
3. verify the Earth Engine assumptions A1 / A2 and the cost of window and water-body builders on EMU_Deccan_forest.

## 11. Live smoke-test wiring (this delivery)

`assess.py` (orchestrator + `EEProvider` + audit-trail writers), `parity.py` (EE vs numpy), `notebooks/v028_smoke_test.ipynb`.
It runs ONE terrestrial zone (`EMU_Deccan_forest`) and ONE aquatic zone (`Lake_Suman`); it does not touch the headline
aggregation, `main`, or the 15-tile run. Only indicators that are applicable AND proposed-scoreable are computed; contextual and
screening indicators are listed with their status and reason. `tspi` is reported `pending_methodology` (Phase 4).

Audit trail columns: `indicator, status, site_value, site_unit, site_support, reference_population, reference_n, reference_unit,
reference_support, benchmark, scoring_method, applicability_reason, compatibility_checks, provenance` (+ reason, detail, score,
direction, tier, reference median / MAD, water-body funnel, diagnostics, flags, other references, validation status, seconds).

Parity checks (statuses MATCH / DISCREPANCY / INFO / HARNESS_ERROR): per-pixel constructs vs the numpy formulas on the same
pixels (natural share, riparian natural cover, shoreline disturbance, net tree-cover change, raw wcpi, forest-loss numerator /
denominator / year count); block cells (A1); cell sampling (A2); site aggregation (EE `reduceRegion` vs numpy coverage-weighted mean,
with the boundary-pixel weighting effect reported separately); water-body records (area, pure-water pixels, unit value).


## 12. Smoke-test review 1: findings and fixes (branch `v0.2.8-contract`, "smoke-test fixes 1")

The first live run (Deccan forest and Lake_Suman, commit 7dac5aa) validated block-cell aggregation (A1: 49/49 cells), cell sampling (A2:
3,451 cells), NDVI and HDI site parity, and scored `bii`, `ghm`, `hdi` on Deccan. It also exposed the problems below. **Everything in this
section is verified offline (synthetic and fake-Earth-Engine tests) only; the live re-run is the verification.**

### 12.1 Frozen site-support convention: coverage-weighted polygon mean

Every polygon-level site metric is `Σ wᵢ·vᵢ / Σ wᵢ` over the valid native pixels the polygon touches, `wᵢ` = fraction of pixel *i* inside the
polygon. `support.SITE_SUPPORT_CONVENTION = "polygon_coverage_weighted"`; the numpy definition is `support.polygon_coverage` +
`support.weighted_mean` (used by `reference_builders.site_mean`) and, for rates, a ratio of coverage-weighted sums (`support.polygon_rate`).
Earth Engine's `reduceRegion(mean)` is coverage-weighted by default and is what the provider uses; a site value must never use `.unweighted()`
(a test enforces it). Reference cells are whole native-pixel blocks (coverage 1) and need no weights.

Why not pixel-centre inclusion: on the live Deccan tile (corrected values; the review pasted the two columns the wrong way round)

| metric | coverage-weighted (PRODUCTION) | centre-inclusion (rejected) | EE `reduceRegion` |
|---|---|---|---|
| natural_habitat (%) | 81.945 | 81.832 | 81.956 |
| net_tree_cover_change (pp/yr) | −0.1231 | −0.1533 | −0.1237 |
| ghm | 0.4464 | 0.5071 | 0.4448 |

Centre-inclusion moves `ghm` by 13.6 % and net change by 24 %, because a coarse pixel is either in or out. Earth Engine already implements the
production convention; its residual against the exact numpy weighting (0.014 %, 0.47 %, 0.36 %) is **unexplained and deliberately not
investigated** (review decision). The parity harness now reports up to 0.1 % as MATCH, up to 1 % as INFO ("residual, not investigated") and above
1 % as DISCREPANCY.

**GHM (landscape pressure).** Its support is the same coverage-weighted polygon mean at native 90 m; its reference is site-sized cells of the same
native pixels (7×7 px for 40 ha). A separate "landscape neighbourhood" support was considered and rejected: it would be a new construct with its
own reference definition, and two supports for one metric would be the silent mixing the review forbids. **Known consequence:** when the site is
smaller than one native pixel (0.47 ha vs 0.81 ha at 90 m; nearly every site vs 21.5 ha VIIRS pixels) the reference cell is one pixel while the
site value is a weighted mean of up to four pixels, and the cell area can differ from the site area by up to (k±½)²/k². The audit records
`cell_area_ratio_to_site` and the flag `site_smaller_than_one_native_pixel`; the exemption rule (`PRESSURE_SUPPORT_RULE`) is unchanged.

### 12.2 Water bodies: area, edges, population, applicability

**Root cause of the parity mismatch (2 EE bodies vs 1 numpy).** The two areas are exactly 458 px × 100 m² × 1.00354 and 42 px × 100 m² × 1.00354:
EE's `polygon.area()` is *geodesic*; the numpy area is a pixel count. The 42-px component is real (the same pixels are on both sides). The harness
applied the "interior" (edge) filter to numpy only; EE records had no interior flag and defaulted to True. So the discrepancy is an asymmetry in the
comparison, not a different water mask. *Confidence: high, not proven live* (the live run did not record the body's location); the new harness prints
the centroid, bounding box and distance to the region edge of every unmatched body, and the live synthetic fixture reproduces the pattern.

Fixes: (1) unit **area = pixel count × native²** (sum of the water mask inside the unit), the geodesic area is kept as a diagnostic;
(2) every record carries `interior` (bounding box clear of the region edge by erosion + 1 px, or ring width + 2 px for rings) and both the numpy
definition and the Earth Engine builder apply it; (3) records carry UTM centroid, bounding box and `touches_site`; the bounding box is read as
min/max of the ring, not by vertex order.

**New explicit population rule: `MAX_WATER_BODY_EXTENT_M = 2000 m`** (`constructs`, `indicator_contract`, `Config.water_body_max_extent_m`).
A target or comparable body must have a bounding-box extent ≤ 2 km. It is what makes tiling lossless: a body owned by a tile (centroid in its core)
then lies wholly inside core + 2 km, so the tile margin is *derived* as `max_extent + interior margin + 1 px` and tiling can never drop an eligible
body. An earlier draft used a fixed 200 m margin and silently dropped legitimate lakes that straddled a tile edge (found by the offline equivalence
test); the rule replaces that hidden side effect with a stated one. Excluded bodies get explicit reasons (`target_exceeds_max_extent`,
`target_truncated_at_region_edge`; funnel counters `n_rejected_extent`, `n_excluded_truncated_at_tile_edge`). **This is a Darukaa choice that
needs your confirmation.**

**Applicability order and the undetermined state.** Domain → water-body feature and pure-water floor → woody ecosystem → forest baseline → site
support. An absent water body is `target_feature_absent` (v0.2.7 wrongly said `ecosystem_type_mismatch`); `ecosystem_type_mismatch` is now a woody
rule only. If the water-body probe raises or is inconclusive the status is `applicable_but_no_site_value` / `applicability_undetermined` with the
error text. The complete evidence (water-mask area inside the site, target body area / pixel count / pure pixels / bounding box / centroid,
ecosystem classification, every probe attempt, every error) is written to the audit JSON under `meta.evidence`.

**Lake_Suman.** The parity pull found a body of 458 px (4.58 ha; 340 pure-water px, mean wcpi 0.1467) inside the 700 m window around the tile, so
the lake **does** satisfy the open-water definition (a complete body with ≥ 10 pure-water px). The v0.2.7 classification was wrong (option b), not
the lake. Why the probe returned "no valid body" is **not** known: the evidence step discarded its diagnostics and swallowed exceptions. The
likeliest cause is an Earth Engine error in the heavy 2 km vectorise-plus-ring probe. The probe is now a small region around the site (margin doubles
until the body is interior), records every outcome, and Step A of the notebook prints it before anything is run.

### 12.3 Memory-safe reference construction

Five providers failed live for **three different reasons** (the review grouped them as memory):

| indicator(s) | error | cause | fix |
|---|---|---|---|
| natural_habitat, net_tree_cover_change_rate, ndvi | `User memory limit exceeded` | one request covered a 100 km box of 10 m pixels (10,000 × 10,000 px) | tiled cell references |
| chm | `Reprojection output too large (10017x10017 pixels)` | same region size, hit a different limit | tiled cell references |
| light_pollution | `reduceResolution: Bad maxPixels arg` | **a bug in this code**: a cell of one native pixel gave `maxPixels=1` | a one-pixel cell skips `reduceResolution` |

**Tiled cell references** (`reference_builders_ee.cell_reference_tiled_ee`, `tiling.py`). Resolution, cell definition, non-overlap, the n = 30 minimum
and the population definitions are unchanged; only the *request* is bounded. (1) tile the reference circle into tiles of ≈ 3,072 native px per side
with edges on the cell grid (no cell is cut, each cell in exactly one tile); (2) count the eligible cells per tile from the eligibility mask on the
cell grid (`Reducer.count().unweighted()`); (3) allocate the n draws in proportion to those counts (largest remainder), so every eligible cell has
inclusion probability n/N and the pooled sample is a self-weighting simple random sample, no weights needed; (4) sample each tile; a tile that raises a
memory/size error is split in four and retried. If the population has ≤ n cells every cell is taken. Diagnostics: tile size, tiles, splits,
eligible cells, allocation range, cells returned.

**Tiled water-body references** (`water_body_reference_ee`): 10 km cores plus the derived margin, one owner tile per body (half-open centroid rule),
adaptive split, an incremental radius ladder (10 → 25 → 50 km) that re-uses tiles and stops as soon as the minimum comparable count is reached.

**Cost.** Bounded per request, not necessarily fast: a 100 km zone is ~16 tiles of 30 km at 10 m, and each cell reference is a count pass plus a
sample pass. Quota was still restricted during run 1, so live timings are contaminated; `hdi` already took 251–380 s.

### 12.4 Parity harness and validation zone

Each check is isolated (one exception no longer discards the rest); a fully masked band (Earth Engine omits a masked pixel's property, the live
`KeyError: 'lossyear'`) is filled with NaN and reported as a `band_coverage` row; water bodies are compared like-for-like with per-body area / pure px /
value / bounding box and a diagnosis of every unmatched body; a **live synthetic fixture** paints known rectangles inside Earth Engine (lake, 42-px
edge pond, two corner-touching bodies that must NOT merge, an island lake, an edge-cut body) and runs the real `unit_records_ee`; the INFO rows
that compared the two site conventions no longer put numbers in the "EE" / "numpy" columns.

The Deccan tile has 0.01 ha of Hansen baseline forest, so forest-loss parity there is trivially true. `select_forest_validation_zone` measures live
baseline and primary-window loss inside the **existing** FCF_GV / FCF_Soova tiles and picks the one with ≥ 5 ha baseline and the largest loss; it is
labelled `methodological_validation_forest_loss` and never enters Tata scoring. If none qualifies it reports the table and stops.

### 12.5 Earth Engine assumptions still to be verified live

A1 and A2 were verified live. New or changed, unverified until run 2: **A3'** water-body vectorisation on the native UTM grid, area as a pixel count
via `reduceRegions(sum)`, pure water via `focal_min`; **A4** `Reducer.count().unweighted()` at the cell scale counts eligible cell centres and
matches what `stratifiedSample` can draw; **A5** `geometry.bounds()` ring and `centroid` in UTM equal the numpy bounding box and pixel-mean centroid;
**A6** `Image.paint` of grid-aligned rectangles rasterises by pixel centre (the synthetic fixture); **A7** a 3,072-px tile is small enough for the
heaviest composites (the adaptive split is the safety net); **A8** proportional allocation from eligibility counts is close enough to the counts of
cells that are also metric-valid (any shortfall is visible as `n_returned` < `sample_requested`).

`tspi` remains `pending_methodology` (Phase 4). Headline aggregation is unchanged; the engine is not wired into the production pipeline.
