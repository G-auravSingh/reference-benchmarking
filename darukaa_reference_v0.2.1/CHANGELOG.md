# Changelog — darukaa_reference

Format: Keep a Changelog; SemVer. Every entry cites a change-set (CS-xx) and, where
applicable, the reviewer comment (Cxx) and HMI/SEED audit fix (F-HMI-x).

## [0.2.1] — Self-contained multi-tile aggregation (agroforestry / large multi-parcel projects)

Adds a self-contained driver for projects whose AOI is too large or too fragmented for
one darukaa_reference run to be geographically meaningful (agroforestry with many
scattered smallholder parcels is the canonical case) -- previously this required a
separate pipeline for the run-and-aggregate step; it no longer does.

### Added
- project_aggregation.py -- new module:
  - _dissolve_tile_to_geojson(): merges every placemark within a tile's KML into ONE
    geometry before running the pipeline (a tile is one assessment unit, not N --
    Pipeline.run() otherwise treats every placemark as its own separate site).
  - aggregate_tiles_noncompensatory(): combines N tile-level reports into ONE
    project-level profile. THE AGGREGATION RULE: for every scored indicator, the
    project signal is the WORST TILE's signed benchmark (the same limiting-factor
    principle scoring.py already applies across subdimensions and components, applied
    one level further, across tiles) -- named explicitly, not averaged away. An
    area-weighted geometric mean (of normalised scores) and a plain area-weighted mean
    (of the raw indicator value, a physically additive quantity) are reported as
    secondary/context only, never as the headline. The combined worst-tile-per-indicator
    values feed into the SAME scoring.build_site_profile() a single site uses -- no
    parallel aggregation logic invented at the profile level.
  - run_multi_tile_project(): the orchestrator -- dissolves each tile, runs the existing
    single-site Pipeline on it unchanged, collects results, aggregates, and writes
    project-level + per-tile json/csv/html. Tile failures are caught, logged, and
    recorded explicitly in the output (never silently dropped); the project run
    continues with the remaining tiles by default.
- html_report.py: renders a "Multi-tile aggregation" section (aggregation rule,
  per-indicator worst-tile table) when a report contains multi_tile_summary.
- README.md: the agroforestry section now shows actual runnable code instead of prose
  describing a workflow that depended on a separate, external repository.
- notebooks/run_pipeline.ipynb: added a full multi-tile section (upload tiles, configure, run_multi_tile_project, worst-tile-per-indicator table, project profile, HTML report, download-everything cell) as an alternative to the single-site flow — the notebook previously had no path to the new driver.

### Verified (synthetic multi-parcel tiles, mocked GEE layer)
- A small (2.3 ha), degraded tile correctly dominates the project-level worst-tile
  headline for every scored indicator, despite a co-existing tile 4x larger and in
  good condition -- the non-compensatory property holds end-to-end through the real
  Pipeline / scoring.build_site_profile code paths, not just in isolated unit tests.
- The single-tile case (i.e. a conservation project run through this driver) produces
  the same result as calling Pipeline.run() directly -- confirmed the trivial case
  degrades correctly.

## [0.2.0.1] — Structural SEED-fidelity audit and correction

A careful re-read of McElderry et al. (2024) Sec. 3.1-3.2 and Eq. 1 against the actual
v0.2.0 code found that the earlier "SEED-faithful" reference path had diverged from the
paper in several places that mattered scientifically, not just cosmetically. All are
fixed here (not just re-documented). Full item-by-item record in
ASSUMPTIONS_AND_LIMITATIONS.md Section 1 (items S-1 through S-9).

### Fixed (structural -- the algorithm now matches the paper)
- PNV's role: was used as the primary land-cover classifier for every pixel. SEED
  uses it only to relabel pixels whose contemporary class is "artificial" with their
  potential natural class. Corrected in reference._build_ecoregion_landcover_image.
- Stratification unit: was "ecoregion as primary mask, PNV supplies the class."
  SEED strata are ecoregion AND land-cover, jointly. Corrected.
- Elevation banding: not part of SEED; was the default. Moved to an explicitly
  separate, off-by-default legacy_landcover_elevation mode.
- Ecoregion constraint (latent bug): eco_id was threaded through the entire call
  chain into _compute_tier2 but never actually applied -- the reference pool was only
  buffer-constrained. Now genuinely ecoregion-masked via ECO_ID, in both modes.
- Kernel formula: was a weighted Manhattan (L1) distance with independent per-
  indicator weights -- not SEED's Eq. 1. Replaced with a real Mahalanobis-distance
  kernel (estimators.mahalanobis_kernel_diagonal / _full) using the reference sample's
  covariance, with a numerically-stable diagonal default and an honest, disclosed
  fallback path for "full" mode when the reference sample is too small to invert.

### Upgraded (resolution/recency audit)
- HMI asset: CSP/HM/GlobalHumanModification (1 km, frozen ~2016) -> TNC/HM/v3/90m_s
  (90 m, 2022 static snapshot, RMSE 0.178) -- same authors' direct successor. Legacy
  asset available via use_legacy_hmi_asset=True.
- Land-cover source: COPERNICUS/Landcover/100m/Proba-V-C3/Global/2019 (100 m, frozen)
  -> GOOGLE/DYNAMICWORLD/V1 (10 m, modal composite over a rolling lookback window)
  for the SEED-faithful path.

### Added
- estimators.fit_delta_diagonal -- SEED's stated delta-calibration routine (maximise
  corr(K, 1-HMI) within a stratum); verified to recover a known delta on synthetic data.
- estimators.shrinkage_covariance, mahalanobis_kernel_full -- full-covariance kernel
  path with shrinkage regularisation, implemented and unit-tested, available but not
  the default (see "Known scope boundary" below).
- ReferenceResult.stratification_diagnostics / ComparisonResult.stratification_diagnostics
  / scorecard row stratification_diagnostics -- mode, masks applied, land-cover class,
  PNV-correction status, and fallback level now flow into the standard JSON report
  automatically. No separate diagnostic export needed to validate a live run.
- config.pnv_to_dw_crosswalk + pnv_to_dw_crosswalk_verified -- the PNV to Dynamic-World
  class relabelling table, shipped as an explicitly-flagged, unverified placeholder
  (logs a warning every run until verified against the live asset legend -- OD-8).

### Removed
- estimators.seed_kernel (L1 magnitude-weighted) -- replaced; not SEED's formula.

### Known scope boundary (not a bug -- a deliberate, disclosed limit)
- The "full" Mahalanobis covariance path needs co-located, multi-band reference pixel
  sampling (all of a construct's indicators sampled from the same pixels) to produce a
  meaningful covariance matrix. That GEE-side sampling infrastructure is not wired into
  the default pipeline; "diagonal" mode remains the default for this reason (OD-10).

## [0.2.0] — UNRELEASED — "Peer-review response"

### Batch 5 — OD-3 / OD-4 / OD-5 + cycle-2 change scoring
- **OD-3 variance-stability reference floor** (`estimators.reference_is_stable`, wired into
  `reference._reference_accepted`): a reference is accepted only if it clears the pixel
  floor AND its bootstrap median SE is within tolerance (`reference_stability_rel_tol`,
  default 0.15); otherwise the score is **suppressed** rather than computed on noise.
  Replaces the arbitrary fixed floor as the acceptance criterion (gated by
  `use_variance_stability_floor`). Applied at all three Tier-2 acceptance points.
- **OD-4 multivariate SEED kernel** (`estimators.seed_kernel`,
  `construct_seed_similarity`): the SEED `exp[-δ·‖w⊙(z−z_r)‖₁]` similarity-to-reference,
  attached per construct as an OPTIONAL view (`use_seed_kernel`, `seed_kernel_delta`) —
  complements, never replaces, the direction-aware per-indicator benchmarks.
- **OD-5 ecoregion-primary + PNV reference stratification** (`reference._compute_tier2`):
  `reference_stratification="pnv_ecoregion"` uses the Potential Natural Vegetation class
  and constrains the reference to the site's ecoregion FIRST (SEED-faithful; avoids
  stratifying on already-modified contemporary land cover). Legacy
  `landcover_elevation` remains the default. New config: `pnv_gee_asset`,
  `ecoregion_gee_asset`. (GEE code path; validated by construction.)
- **Cycle-2 change scoring** (`change.py`): `change_score` (delta vs own Year-0 with
  propagated uncertainty + a detection test), `baci_contrast` (impact minus control
  change), `score_cycle`, and `from_report` (diff two cycle report dicts). This is where
  in-situ metrics finally score — as change, from cycle 2 onward.

### Batch 4 — pipeline wire-through
- **`pipeline.py`:** runtime toggle applied — REMOVED (`registered=False`) and deactivated
  indicators are never computed (CERI excluded live); `assessment_mode`/`realm`/`archetype`
  logged and stamped into the report; monitoring-mode guard added (change-vs-baseline needs
  a stored Year-0 artifact — OD); completion log reports scored-profile count and .json/.csv/.html.
- **`report.py`:** the evidence-graded **HTML report is now emitted on every run** (standard
  pipeline output, CS-10); project context (`assessment_mode`, `realm`, `archetype`) added to meta.
- **`example_run.py`:** summary rewritten to the profile-first output (indicator status counts,
  per-site limiting factor, condition roll-up + minimum + sensitivity, pressure axis); fixed the
  stale `pillar_summary` key; docstring updated.
- **Version bumped to 0.2.0** (`__init__.py`, `setup.py`).

### Batch 3 — benchmark propagation, sensitivity harness, evidence-graded HTML report
- **`statistics.py`:** `ComparisonResult` now carries the responsive benchmark
  (`tier1/2_benchmark`, estimator, percentile, display %, `reference_type`,
  `reference_hmi_realised`), propagated from `ReferenceResult` in `compare()`. This is
  the connector that makes `site_profiles` populate on real runs — scoring consumes the
  signed benchmark, never the capped ratio (CS-3/CS-10).
- **`scoring.py`:** added `sensitivity_report()` (CS-5 condition 4) — recomputes the
  condition roll-up under equal + each-component-tilted weightings; if the coarse band
  flips the roll-up is flagged **UNSTABLE** (publish as such or withhold; profile shown
  regardless). Attached to every site's `condition.sensitivity`.
- **Added `html_report.py`** — evidence-graded standalone HTML "Evidence Record"
  (Nandoshi model, CS-10): every claim carries its evidence grade; scored / contextual /
  screening / pending / removed shown separately; profile-first (limiting factor →
  condition × pressure matrix → secondary roll-up with stability flag + framing block);
  signed benchmark and uncapped % of reference displayed. Deterministic projection of the
  report dict; no external dependencies.

### Batch 2 — indicator contract population, redundancy screen, profile-first scoring
- **Added `contracts.py`** — declarative CS-1 contract + disposition for all 44
  indicators (construct, subdimension, measurement scale, evidence tier, reference
  type/estimator, input layers, module) with `apply_contracts()` and a Gate-A
  `redundancy_guard()`. Auto-applied by `create_default_registry()` (CS-1/CS-2/CS-4/CS-7).
- **Added `scoring.py`** — profile-first hybrid: limiting-factor rule within components,
  non-compensatory penalised geometric mean + published minimum across components, state
  vs pressure separated into a condition × pressure matrix, declared reversible logistic
  normalisation, and the mandatory framing block (CS-4/CS-5).
- **Dispositions applied:** scored set reduced from 44 → **10** (7 condition + 3
  pressure). `ceri` **removed** (registered=False; arithmetically perverse, F3);
  `threatened_richness`/`endemic_richness`/plant variants/`kba_overlap` → **screening**
  (F1); `eii` scored at **parent** with structural/compositional/functional as context
  (Q4); `natural_landcover`/`ndvi`/`habitat_health`/`bii`/`pdf`/`lai`/EII-components →
  **context** (Gate A / modelled); `chm` retained (additive); `star_t` → context.
- **`report.py`:** version → 0.2.0; new `site_profiles` (profile-first) and
  `indicator_status` (scored/contextual/screening/removed) sections; scorecard rows carry
  construct/subdimension/evidence_tier/scoring_eligible + signed benchmark; **corrected
  pillar labels** ("Species Population Size" → "Faunal abundance/activity … NOT population
  size"; extinction-risk pillar marked retired, B8/F1); legacy `_pillar_summary`
  **deprecated** (kept for comparison), scoring now consumes the signed benchmark not the
  capped ratio.

### Batch 1 — foundations + SEED reference keystone

### Added
- **Indicator contract** on `IndicatorSpec` (CS-1): `construct`, `subdimension`,
  `ecological_question`, `management_use`, `input_layers`, `measurement_scale`,
  `spatial_grain`, `temporal_period`, `effort_basis`, `evidence_tier`, `realm`,
  `module`, `reference_type`, `reference_estimator`, `threshold_basis`,
  `uncertainty_method`, `restoration_sensitivity`, `reassessment_frequency`,
  `management_trigger`, `registered`, `active`, `requires`. All additive with safe
  defaults — existing `register(...)` calls remain valid unchanged.
- **Computed eligibility** (`IndicatorSpec.eligible`, `.scoring_eligible`) enforcing
  the toggle rule *active ⟹ eligible*; `eligible` is never hand-set (CS-1 / Q7).
- **`estimators.py`** — responsive, scale-aware reference estimators: log response
  ratio (ratio-scale), robust standardised deviation + percentile-in-reference
  (interval/bounded), `benchmark()` dispatcher (CS-3, C-G2, F-HMI-1).
- Registry queries: `by_construct`, `scored`, `contextual`, `pending`,
  `by_input_layer` (the last powers redundancy Gate A).
- `Config` project context: `realm`, `archetype`, `assessment_mode`,
  `reference_estimator_default` (CS-10) + YAML `project:` section.
- `ReferenceResult` responsive-benchmark fields (`tier*_benchmark`,
  `tier2_percentile_in_reference`, `tier2_display_pct_of_reference`,
  `reference_type`, `reference_hmi_realised`).

### Changed
- **Reference estimator (CS-3):** the responsive `estimators.benchmark` is now
  computed for every indicator alongside the legacy ratio; scoring will consume the
  responsive value (enforcement in the scoring batch). Signed & uncapped, so
  above-reference restoration gains are visible (NPI "responsive to increases AND
  decreases"; C-B6/C-G2).
- **HMI ceiling restored to 0.05** (was 0.10) — SEED's maximum allowable HMI for the
  counterfactual reference (F-HMI-2). Now also loadable from YAML and the realised
  threshold is reported per run (F-HMI-2 transparency).
- **Reference pixel floor** unified to `12` in both the dataclass and the YAML loader
  (F-HMI-5; interim value pending a variance-stability criterion — OD-3).

### Fixed
- **`min_reference_pixels` inconsistency bug** — `config.py` default (5) and the YAML
  loader default (20) disagreed; both now `12` (F-HMI-5, repo-hygiene CS-13).
- HMI ceiling documentation contradiction (docstring 0.05 vs config 0.10) resolved.

### Deprecated
- `ReferenceSelector._intactness_ratio` — legacy capped ratio; retained for
  back-compat/display only. Do not use for scoring (censors improvement; invalid for
  non-ratio scales). Superseded by `estimators.benchmark`.

### Deferred (next batches / next cycle)
- Populate the contract on all 44 indicators; redundancy screen demotions (CS-2).
- Switch `report.py` scoring to the responsive benchmark; profile-first hybrid;
  non-compensatory aggregation; uncertainty + sensitivity (CS-4/CS-5).
- Multivariate SEED kernel option; PNV stratification; variance-stability pixel
  criterion (F-HMI-3/4/5, OD-3).

## [0.1.0] — as-reviewed baseline (archived)
- The state of the pipeline as submitted for the North Shahdol review. Preserved for
  before/after comparison in the peer-review response.
