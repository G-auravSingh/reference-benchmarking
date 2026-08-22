# Assumptions & Limitations

Every provisional `[P]` and product-choice `[X]` decision, every arbitrary constant, and
every un-validated code path in the pipeline. This document exists so nothing is silently
assumed solved. Read it before quoting any result as defensible.

## 1. SEED reference — status after the v0.2.0 structural audit

The reference-benchmarking concept follows SEED (McElderry et al. 2024). A first
implementation (documented in earlier revisions of this file) had **diverged from the
paper in ways that mattered**, found on a careful re-read of Sec. 3.1-3.2 and Eq. 1
against the actual code. That divergence has been corrected; status below.

| # | Item | Status |
|---|---|---|
| S-1 | Stratification unit | **Fixed.** Ecoregion AND land-cover are now BOTH the stratum jointly (`reference_stratification="ecoregion_landcover"`, default), matching SEED exactly. A prior build used ecoregion as a "primary mask" with PNV standing in as the sole classifier for every pixel — wrong; corrected. |
| S-2 | PNV's role | **Fixed.** PNV now corrects ONLY pixels whose land-cover class is artificial (crops/built by default), exactly as SEED states ("all artificial land use classes... updated with the predicted land cover from the PNV"). A prior build used PNV as the primary classifier for ALL pixels, natural or not — wrong; corrected. The PNV->Dynamic-World class crosswalk (`config.pnv_to_dw_crosswalk`) is a **placeholder pending verification** against the live PNV asset's legend — see S-4b. |
| S-3 | Elevation banding | **Fixed.** Not part of SEED. Moved out of the default path entirely; available only in the explicitly-labelled `reference_stratification="legacy_landcover_elevation"` mode, off by default. |
| S-4a | Land-cover source | **Upgraded.** Was Copernicus 100 m/2019 (coarse, frozen). Now Dynamic World (10 m, modal composite over a rolling lookback window — current by construction). |
| S-4b | PNV dataset | Still 1 km / biome-level (`OpenLandMap/PNV/PNV_BIOME-TYPE_BIOME00K_C/v01`, Hengl et al. 2018) — a finer 250 m alternative exists (Bonannella et al., Zenodo) but is not a ready GEE catalog asset and would need a custom upload; not done. **The PNV->Dynamic-World class crosswalk has NOT been verified against the live asset's legend** (`config.pnv_to_dw_crosswalk_verified=False` by default) — the numeric biome codes in the placeholder crosswalk were not independently confirmed and MUST be checked in the GEE Code Editor before relying on the PNV correction. |
| S-5 | HMI asset | **Upgraded (the single highest-value fix).** Was CSP gHM: 1 km, frozen at ~2016. Now TNC Global Human Modification v3, 90 m, 2022 static snapshot (RMSE 0.178 at 90 m; Theobald et al. 2025) — same authors' direct successor, 11x finer, 6 years more current. Legacy asset available via `use_legacy_hmi_asset=True` for exact reproduction of pre-audit runs. |
| S-6 | Kernel formula | **Fixed.** `estimators.mahalanobis_kernel_diagonal` / `mahalanobis_kernel_full` implement the actual Eq. 1 (Mahalanobis distance with reference covariance). A prior build used a weighted Manhattan (L1) distance with no covariance term — not the SEED formula; removed. Default mode is "diagonal" (covariance treated as uncorrelated) for numerical stability given typically small reference samples (~12-30 pixels); "full" mode is implemented and unit-tested but not wired into the default data flow (would need co-located multi-band reference sampling — real, bounded future work, not started). |
| S-7 | Delta calibration | **Still open, by necessity.** `estimators.fit_delta_diagonal` implements SEED's stated calibration (maximise corr(K, 1-HMI) within a stratum) and is verified to recover a known delta on synthetic data (fitted 1.33 vs true 1.30, r=0.995). It CANNOT be run for real until genuine (indicator z-score, HMI) pairs exist from a live GEE run. The default `seed_kernel_delta=0.5` remains an undisguised placeholder, not a calibrated value. |
| S-8 | Ecoregion constraint (legacy mode) | **Fixed, a latent gap.** `eco_id` was threaded through the whole call chain into `_compute_tier2` but was NEVER ACTUALLY APPLIED — the legacy path only used a buffer radius, a weak geographic proxy. Both modes now apply a real ecoregion polygon mask via `ECO_ID`. |
| S-9 | Live execution | **Still open.** None of the above has been run against live Earth Engine (no GEE in the build sandbox). Validated by construction + unit tests on synthetic data only. This is the next required step — see the "Validating against a live run" section of the README. |

**Bottom line:** the structural/formula errors (S-1, S-2, S-3, S-6, S-8) are genuinely
fixed, not just documented as gaps. What remains open (S-4b crosswalk verification, S-7
delta calibration, S-9 live validation) requires real project data and cannot be closed
from this environment — they are now the precise, minimal list of what a first live run
needs to settle.

## 2. Arbitrary constants (each declared, tested where possible)

| Constant | Value | Status |
|---|---|---|
| HMI ceiling | 0.05 | `[D]` restored to SEED maximum |
| `min_reference_pixels` | 12 | `[X]` provisional; superseded as the *acceptance criterion* by OD-3 variance-stability when enabled |
| `reference_stability_rel_tol` | 0.15 | `[X]` declared tolerance for OD-3; not empirically derived |
| `elevation_band_m` | ±300 | `[P]` uncalibrated; SEED uses PNV+ecoregion, not elevation |
| Normalisation logistic slopes `K_LRR`, `K_Z` | 1.0, 0.5 | `[X]` display/aggregation only; declared, reversible |
| Redundancy correlation gate | \|r\| ≥ 0.8 | `[X]` conventional, not derived |
| Matrix band cut points | 0.5 | `[X]` declared display bands |
| Equal component weighting | equal | `[X]` transparent convention, NOT an ecological truth (OD-2 to confirm as published default) |
| Spacing independence factor | 2.0 | `[X]` declared; site-selection |

## 3. Aggregation & scoring caveats

- The composite roll-up is a **decision index, not a measurement of biodiversity** — see the
  framing block published with every roll-up.
- Cross-project comparison is valid only within the fixed core **and** within archetype.
- The limiting-factor rule assumes the weakest subdimension is the ecologically binding
  constraint; `[P]` needs case validation that the minimum is truly binding in practice.

## 4. Evidence-tier honesty

- North Shahdol Year-0 is, honestly, **mostly Entry-level (screening/contextual) with a thin
  baseline layer**. Indicators show as `pending` where their field/in-situ dependency is unmet.
- In-situ metrics do **not** score in cycle 1 (self-referential thresholds are not a
  baseline); they score as **change** from cycle 2 (change.py).

## 5. Not runnable in the build environment

- Live GEE runs of `darukaa_reference` (needs auth to project `gaurav-singh-007`).
- Live GEE runs of site-selection (needs GEE + real candidate KMLs).
- The foundation-model embedding export (asset-agnostic scaffold; asset unconfirmed).
- The carbon p.29 arithmetic fix (handled manually, separate track).
