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
| `polygon_proportion` | `site_window_proportion` | Mean of a 0/1 image over a circular window with area = site area |
| `polygon_mean` | `site_window_mean` | Mean of a continuous image over the same window |
| `polygon_rate` | `site_window_rate` | Σ numerator area / Σ denominator area × 100 / years over the window, with a denominator floor. It is **never** the mean of per-pixel rates. |
| `water_body_unit` | `water_body_unit` | The metric over each comparable water body's own pure-water mask (eroded 1 px) |
| `riparian_ring_unit` | `riparian_ring_unit` | The metric over a fixed-width ring around each comparable water body, excluding all water |
| `polygon_scalar`, `not_computed` | none | Not benchmarked |

- **Coverage.** Windows with less than 90 % valid coverage are dropped, so every reference value represents a full site-sized area.
- **Sampling.** Windows are sampled on a grid spaced at max(native pixel, window diameter). Windows therefore never overlap, and a coarse cell is never counted twice.
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

**Unverified Earth Engine assumptions** (to be checked in the first live run, Phase 5):
- **A1.** `.reproject(native)` forces the focal sums to be computed on the native grid.
- **A2.** Sampling a reprojected image at a coarser spacing is point sampling, not re-aggregation.
- **Cost.** A 10 m focal window of radius ~357 m (a 40 ha site) over a 50 km zone is heavy. The planned mitigation is exact pre-aggregation: sum and count at an intermediate grid via `reduceResolution(sum)`, then the focal step on that grid. This is exact for area proportions and area-weighted means. It is not yet implemented, and its timing must be measured.

## 4. Proposed scoreable sets (from the contract; none active)

| Domain | Scoreable indicators |
|---|---|
| Terrestrial (8) | natural_habitat, forest_loss_rate (only where baseline forest ≥ 5 ha), ndvi, chm (woody ecosystems only), bii, ghm, hdi, light_pollution |
| Aquatic (4) | tspi, sabf, wcpi, sdi |
| Shared with aquatic | ghm, hdi, light_pollution are landscape pressures and also apply to aquatic sites |
| Pending | cpland (asset provenance), net_forest_change_rate (redefinition), rci (redefinition), hsas (eDNA) |

**Aquatic C3 (fauna) has no EO-based indicator.** The report must say so explicitly.

## 5. Status model (per tile, per indicator)

The statuses are:
- `not_applicable`, with one of these reasons: `domain_mismatch`, `ecosystem_type_mismatch`, `target_feature_absent`, `site_below_product_resolution`, `insufficient_pure_water`;
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
1. Applicability (domain → ecosystem → feature → site support). If not applicable, no reference is computed.
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
| net_forest_change_rate | redefine (proposal): change in DW tree-cover share, early window (2017–18) vs recent window, percentage points per year, same classifier both ends | window version of the same | identical start/end → 0; planting from bare land → positive | after you decide on the definition |
| sabf | pure-water mask per water body | comparable water bodies | land never counts as bloom | aquatic tile |
| wcpi | raw 1/(TSM+1) over pure water, no site normalisation | comparable water bodies | site value independent of its own min/max | aquatic tile |
| edpp | single-band EDPP, absolute thermal scaling | same construct | reference band = site construct | stays screening |
| mspl | remove the site-relative thermal term | single-band | same | stays context |
| rci | redefine (proposal): natural-vegetation share of the riparian ring | comparable rings | ring geometry test (exists) | aquatic tile |
| sdi | disturbed share of the ring | comparable rings | ring vs all-land difference | aquatic tile |
| ghm | site read at native 90 m | window mean, regional unfiltered stratum | site scale = native | Deccan |
| natural_habitat | unchanged | absolute level (100 %) or window proportion (§8) | 81.6 % → ln(0.816) | Deccan |
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
| D3 | Generic hard floor 10 native pixels; indicator-specific floors where justified; aquatic ≥ 10 pure-water px + valid water-body geometry; explicit in contract | `Applicability.min_native_pixels=10`, `indicator_min_native_pixels` (natural_habitat, net_forest_change_rate: 100 px, rationale recorded), `floor_basis` (`polygon_native_pixels` / `pure_water_pixels` / `exempt_landscape_pressure`). **Landscape pressures (ghm, hdi, light_pollution) are exempt from the polygon floor: my assumption, needs your confirmation.** |
| D5 | net_forest_change_rate rebuilt on one product/time series | Dynamic World tree-cover share, early (2017–18) vs recent (ndvi_year−1..ndvi_year), pp/yr between period mid-points; one function builds both endpoints; no Hansen. Percentile estimator (tie-heavy reference). |
| E1 | forest loss: empirical percentile/CDF; explicit direction, ties, zero windows; keep distribution and n | `reference_percentile`, `lower_is_better`, mid-rank ties, `fraction_reference_zero`, `p_reference_tied/worse/better`, `reference_n`, DKW 95 % half-width |
| E2 | Comparable water bodies: area ratio in [1/3, 3], \|permanence difference\| ≤ 0.25; documented minimum n; `reference_n` exposed; otherwise `reference_available_but_not_scoreable` | `MIN_COMPARABLE_WATER_BODIES = 10` (my proposal), radius ladder 10/25/50 km, funnel counts (`n_rejected_size`, `n_rejected_permanence`, …) in the audit trail |
| E3 | RCI → 100 m riparian-ring natural-vegetation proportion, honestly named | `rci` retired; `riparian_natural_veg_share` (same ring, DW natural classes, land only, all water excluded, for target and every reference ring) |
| E4 | External forested validation polygon, labelled, never in Tata scoring | `SiteEvidence.validation_dataset_label`; `project_assessments()` drops validation-only results. **The polygon itself is not chosen yet.** |

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
