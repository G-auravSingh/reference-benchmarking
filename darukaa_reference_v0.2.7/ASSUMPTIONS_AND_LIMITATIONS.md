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

- A first Year-0 baseline is, honestly, typically **mostly Entry-level (screening/contextual) with a thin
  baseline layer**. Indicators show as `pending` where their field/in-situ dependency is unmet.
- In-situ metrics do **not** score in cycle 1 (self-referential thresholds are not a
  baseline); they score as **change** from cycle 2 (change.py).

## 5. Not runnable in the build environment

- Live GEE runs of `darukaa_reference` (needs an authenticated GEE project).
- Live GEE runs of site-selection (needs GEE + real candidate KMLs).
- The foundation-model embedding export (asset-agnostic scaffold; asset unconfirmed).
- The carbon p.29 arithmetic fix (handled manually, separate track).

## 6. Indicator asset audit (v0.2.1) — scope and findings

A full resolution/recency audit of all 44 registered indicators has NOT been done —
this covers the 10 scored-by-default indicators, audited directly against their code.

| Indicator | Finding | Status |
|---|---|---|
| natural_habitat, natural_landcover | Dynamic World 10m (current) | OK |
| ndvi, habitat_health | Sentinel-2 SR, `ndvi_year` configurable (default 2025) | OK |
| forest_loss_rate | Hansen GFC 2025 v1.13 (current); windows were hardcoded, now `config.forest_loss_windows` (configurable) with `config.forest_loss_primary_window` pinning which window scores (anti-cherry-pick, deliberate). **Real, separate issue found on a live Tata Motors run**: a near-zero Hansen 2000 baseline (e.g. 0.01 ha, against 24.26 ha of real current Dynamic World tree cover — likely genuine restoration, not noise) makes the percentage-rate formula arithmetically unstable (one real case produced 10,851%/yr). `low_baseline_flag` already detected this but nothing downstream acted on it; the exploded value silently drove this indicator's score, and through the non-compensatory limiting-factor rule, its whole pillar. Now suppressed to `None` when `baseline_forest_ha < 5.0`; the real absolute-area numbers (`baseline_forest_ha`, `gain_detected_ha`, `loss_ha_by_window`, `absolute_net_change_ha`) stay available in metadata instead of a percentage rate that can't be trusted at this scale. | Fixed |
| **flii** | **Was cited as the actual Grantham et al. (2020) Forest Landscape Integrity Index. It is NOT — the code computes a Darukaa proxy (VIIRS nightlight + Dynamic World forest fragmentation). Citation corrected; indicator renamed "Forest Fragmentation & Pressure Proxy (Darukaa)"; `reference_type` changed from `published_threshold` to `contemporary_best_on_offer`.** A live GEE asset for the real FLII product was searched for but not confirmed with confidence — if one is found, this proxy should be replaced with it. | **Fixed (citation); asset replacement still open** |
| eii | Landbanking EII asset (external, not independently re-verified this pass) | Not re-audited |
| jrc_water_persistence | JRC Global Surface Water (current, actively maintained) | OK |
| chm | GEDI L2A (current spaceborne LiDAR) | OK |
| ghm | See §1 S-5 — upgraded to TNC HM v3 90m/2022 | Fixed (§1) |
| light_pollution | VIIRS DNB monthly (current) | OK |

**The other 34 registered (contextual/screening/removed) indicators have not been
re-audited for asset currency in this pass** — they don't drive the scored output, so
were lower priority, but should not be assumed current without checking.

## 7. Choosing what gets scored beyond the default (v0.2.1)

44 indicators are registered; 10 are scored by default (see `INDICATOR_REGISTER.md` for
why each of the other 34 isn't). `contracts.request_activation()` lets a client request
additional indicators be scored, tiered by how defensible that is:
- `context` disposition — freely activatable (usually a parsimony/redundancy choice,
  not a construct flaw).
- `screening` disposition — activatable only with an explicit `force` flag; the original
  caveat travels with it permanently into every report.
- `remove` disposition (e.g. CERI) — never activatable this way; the construct itself is
  broken (CERI's averaging makes adding a common species LOWER its risk score), and no
  config flip fixes that.
Every activation sets `client_override=True`, visible in the JSON scorecard and as a
"CLIENT-ACTIVATED" badge in the HTML report — never indistinguishable from a default.

## 8. Monitoring mode / cycle-2 change scoring — known gap

`config.assessment_mode="monitoring"` is accepted but **not yet auto-wired**:
`pipeline.py` currently logs a warning and runs baseline-style computation regardless.
`change.py` (delta vs Year-0, detection test, BACI contrast) exists and is unit-tested,
but must be invoked manually — run the pipeline once per cycle, then call
`change.from_report()` on both cycles' JSON reports and feed them to
`change.score_cycle()` yourself. Automatic wiring (store Year-0, auto-diff on a
monitoring-mode run) is not built.

## 9. BII / C3 fauna fix (v0.2.4)

Prior to v0.2.4, the `bii` indicator was NOT independent data — `_img_bii` derived it
from EII's own `compositional_integrity` band, i.e. it was EII's sub-component
relabelled. This meant (a) C3 (fauna) had zero genuinely independent scored indicators,
and (b) any "BII vs EII redundancy" concern was true by construction, not a genuine
methodological question. Fixed: `bii` now uses the Impact Observatory / Vizzuality
Biodiversity Intactness dataset (`projects/ebx-data/assets/earthblox/IO/BIOINTACT`,
100 m, PREDICTS-database-derived), a genuinely separate source, moved to C3_fauna, and
promoted to scored by default.

Caveats, stated plainly:
- This is a **GEE community-catalog asset** (gee-community-catalog.org), not the
  official Google Earth Engine catalog. Widely used (cited by Bloomberg's biodiversity
  risk tooling, TNFD/CSRD reporting products) but worth re-verifying if the asset path
  ever returns an error on a live run.
- **Temporally limited to a 2017–2020 composite** — not continuously updated like
  Dynamic World or the current HMI asset. The best currently-available GLOBAL option
  for this signal, not a "most recent" annual product.
- **A modelled product** (statistical response of species abundance/compositional
  similarity to land-use and pressure), not a direct observation — same category as
  EII, MSA, PDF.
- **Not fauna-exclusive.** BII covers plants, fungi, and invertebrates alongside birds
  and mammals. It is the best available satellite-model-derived signal that includes
  fauna, not a vertebrate-specific measurement — the report's display name reflects
  this ("fauna & flora abundance"), not oversold as fauna-only.
- A genuinely fauna-EXCLUSIVE ex-situ signal (species distribution models for named
  taxa, structural-complexity-as-habitat-proxy) remains a real next-cycle item if a
  narrower faunal signal is wanted later.

## 10. SoN condition/pressure score & classification (v0.2.4)

`son_score.py`'s 5-band classification is a **declared product convention** applied to
the already-normalised, reference-relative benchmark — not an independent claim that
these five specific bands are in the ecological literature. This is different in kind
from the universal-threshold problem the methodology redesign removed (see §5 of
`METHODOLOGY_MASTER.md`): those thresholds were applied to raw, incommensurable units
across ecoregions; these bands are applied to a value that is ALREADY a normalised
distance-from-reference, comparable by construction.

`LITERATURE_BREAKPOINTS` is deliberately short (currently: `natural_habitat` only) —
populated only where a document review found a breakpoint argued to be structurally
general rather than ecoregion-dependent. Extending this list requires the same
literature-verification discipline as everything else in this pipeline, not an
assumption that any cited breakpoint transfers.

`overall_condition`/`overall_pressure` are never combined into one number inside this
pipeline. This is a deliberate boundary, not an oversight — see
`AGGREGATION_WALKTHROUGH.md` Part C.

## 11. v0.2.5 script-review fixes and remaining FLII/EII honesty

- **ghm/site-value asset mismatch (fixed):** `_img_ghm` had not been updated when
  `config.hmi_gee_asset` was upgraded to TNC HM v3 during the SEED-fidelity audit --
  the scored `ghm` indicator's own value and its reference distribution were computed
  from two different HMI assets until this was found and fixed. Worth knowing: any
  results generated before v0.2.5 with `ghm` scored should be treated as computed on
  the stale 2016 asset for the site value specifically.
- **FLII remains a Darukaa proxy**, now with the real published aggregation FORMULA
  (P+Q+LFC structure) but still simplified underlying data sources (single-layer P via
  HMI rather than Grantham's multiple observed-pressure layers; a fixed focal radius
  for edge effects rather than a proper decay model; local-density LFC rather than
  circuit-theory connectivity). This is a genuine improvement over the prior ad-hoc
  blend, not a claim that FLII is now faithfully reproduced. See CHANGELOG v0.2.5.
- **EII's own internal HMI reference was also stale** (`_img_eii_s` fallback) --
  fixed alongside ghm for consistency, same caveat about pre-v0.2.5 results.
- **Forest-loss gain detection is a one-time snapshot, not annually resolved** the way
  loss is (Hansen provides no continuously-updated annual gain signal) -- the detected
  gain area is annualised per configured window as a documented approximation, not
  claimed to have the same temporal precision as the loss side.

## 12. C3 (fauna) -- the genuinely correct answer identified, not yet integrated

The Species Habitat Index (SHI) is the real, officially-recognised answer to "what
ex-situ fauna-relevant metric does the ESG/TNFD/GBF community actually use" -- it is a
formally adopted Global Biodiversity Framework Goal-A indicator, built on Google Earth
Engine + BigQuery by Map of Life in partnership with Google, genuinely species/fauna-
relevant (vertebrates prominently represented), updated annually since 2001, at 1km
resolution.

**Why it is not integrated yet:** SHI is computed by Map of Life as a species-by-species
workflow (IUCN/species-distribution-model ranges x habitat suitability x land-cover
change, aggregated across tens of thousands of species via their own BigQuery
pipeline) -- this search found strong evidence the INDICATOR is real and
Google-Earth-Engine-powered, but did NOT confirm a simple, publicly-loadable GEE
Image/ImageCollection asset ID that an external pipeline could point at directly, the
way TNC HM v3 or Dynamic World can be. Fabricating an asset path here would repeat
exactly the mistake this pipeline's discipline has been built to avoid.

**Next-cycle item, with the specific next step:** check mol.org's own data-access /
API documentation (not just the GEE catalog) for a country- or region-level SHI export
mechanism, or contact Map of Life directly about programmatic access at the project-AOI
scale. Until resolved, `bii` remains C3's sole scored indicator -- a genuinely
independent, real signal (v0.2.4 fix), but not fauna-EXCLUSIVE (see SS9).

## 13. Site size vs. reference dataset resolution -- real, quantified, not yet fully resolved

Client-raised directly: "the site size, combinations of sites and reference region
(resolution matters)... some zones would be very small." Checked directly against real
site data: Tata Motors' smallest real zone (EMU_Wetland_forest) is 0.47 ha -- roughly
68m x 68m if square. Checked every currently-SCORED indicator's real native resolution
against that real, worst-case site size:

- `chm` (GEDI): not a resolution problem in the traditional sense -- a sparsity problem
  (sparse orbital-track shots, not a continuous grid at any resolution). See its own
  documented issue and the ETH Global Canopy Height alternative already researched
  (real, confirmed GEE asset, 10m continuous -- pending a real decision, not yet
  switched).
- `light_pollution` (VIIRS DNB): ~500m native resolution -- roughly 7x the site's own
  linear dimension. A `reduceRegion` mean over a 68m x 68m polygon at this resolution is
  not really measuring the site; it is sampling most of one much larger regional pixel.
  Real, unresolved limitation for this indicator on small real sites.
- `ghm` (TNC HM v3): 90m native resolution (checked directly -- this was itself already
  upgraded from a stale 1km asset, v0.2.5 fix) -- roughly 1.3x the site's own linear
  dimension. Meaningfully better than light_pollution's mismatch, but still coarser than
  the site itself for real, very small zones.
- 10m-native indicators (Dynamic World-based: `natural_habitat`, `hdi`; Sentinel-2-based:
  most C2 vegetation/aquatic indicators) are the closest real match to sites this small
  -- a 68m x 68m site is still only ~7x7 pixels at 10m, genuinely thin for a stable mean,
  but at least sampling real, site-specific variation rather than one enclosing regional
  pixel.

**What this means, honestly:** for a real site this small, a coarse-resolution
indicator's "site value" is closer to "the value of the one regional pixel this site
happens to sit inside" than a genuine site-specific measurement. This is not a bug to
fix in code -- it is a real, physical limit of what these public datasets can resolve --
but it is a real reason to read a coarse indicator's result on a very small real zone
with corresponding caution, and a real argument for eventually weighting confidence (or
flagging fine-print) by the site-area-to-pixel-area ratio, not yet implemented. Not
unique to Tata Motors' Wetland_forest zone -- the same real caution applies to any small
real EMU or agroforestry parcel this pipeline is asked to assess.

## 14. Fragmented (multi-polygon) sites -- verified correct, one real, named characteristic

Also client-raised: "some zones are fragmented and we are calculating combined scores
on the whole zones... composite of those fragments." Verified directly against a real
Tata Motors zone (Deccan_forest, confirmed 19 real disconnected polygons after dissolve):
`reduceRegion` over a real MultiPolygon geometry is natively, correctly supported by
Earth Engine -- it aggregates across every real fragment together, which is the
ecologically correct question ("what is this zone's overall condition, across all its
real scattered pieces"), not a bug needing a fix. One real, named, honest characteristic
worth keeping in mind: the geometric centroid used to anchor the (much larger, 10-150km)
regional reference-search buffer can fall outside the fragmented shape itself (confirmed
directly for Deccan_forest) -- inconsequential at that buffer scale, but worth knowing
if a future indicator ever anchors something at a finer scale from that same centroid.