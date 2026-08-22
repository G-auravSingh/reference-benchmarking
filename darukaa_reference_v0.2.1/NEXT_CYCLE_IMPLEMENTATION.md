# Next-Cycle Implementation Plan

What is deferred from the current revision to future cycles, and why. Generated from the
`requires[]` dependency fields + OPEN_DECISIONS. Immediate/partial-now items are already
in the pipeline; this is the forward standard.

## Field / in-situ (require new sampling design & seasons)
- Vegetation composition, regeneration density, deadwood, ground cover, invasives
  (field plots) — the real C2 baseline; currently absent.
- Effort-standardised acoustic richness / Hill numbers + detection-corrected occupancy
  for focal guilds — the real C3 baseline (RS faunal indicators are screening/context).
- Multi-season coverage (≥ summer + winter) at fixed stations/duty cycles.
- Permanent vegetation & carbon plots (DBH/height/wood density/allometrics + uncertainty).
- Social-dependency & tenure baseline (SOCIAL_BASELINE_FRAMEWORK.md).

## Reference logic (SEED completion — see ASSUMPTIONS_AND_LIMITATIONS §1)
- Select & wire a real **PNV dataset** (S-4); verify ecoregion asset (S-5).
- **Live-GEE validation** of Tier-2 / PNV / ecoregion selection across project sites (S-6/S-7).
- **Calibrate δ** for the SEED kernel the way SEED does (S-2).
- Variance-stability floor (OD-3): tune `reference_stability_rel_tol` against real data.

## Landscape / RS
- Harmonised classifier + accuracy assessment (confusion matrices, class-wise accuracy).
- Locally-meaningful classes (Champion & Seth / IUCN GET); class transition matrix.
- Fragmentation suite (patch size, edge density, core area, NN) as scored C1 config.
- "Landscape intactness" as configuration / distance-to-collapse (IUCN RLE) — Advanced tier.

## Site selection
- Foundation-model embedding stratification live (confirm asset) + field-confirm strata.
- Autocorrelation-range spacing already wired; validate ranges per landscape.

## Reporting / carbon / climate
- Carbon: permanent plots + CIs; p.29 arithmetic fix (manual, separate).
- Climate: exposure / sensitivity / adaptive-capacity per veg–terrain stratum.
