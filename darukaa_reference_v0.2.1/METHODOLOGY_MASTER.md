# Darukaa Biodiversity & Restoration Monitoring — Methodology Master

**Version 0.2.0 · single citable source of methodological truth**
Companions: `INDICATOR_REGISTER.md`, `SCORING_LOGIC_NOTE.md`,
`ASSUMPTIONS_AND_LIMITATIONS.md`, `NEXT_CYCLE_IMPLEMENTATION.md`,
`NPI_CROSSWALK.md`, `TNFD_LEAP_CROSSWALK.md`, `SOCIAL_BASELINE_FRAMEWORK.md`,
`OPEN_DECISIONS.md`, `CHANGELOG.md`.

## 1. Purpose & scope
A standard, adaptive pipeline for Year-0 baselines (optionally seasonal) and repeated
monitoring, across realms (terrestrial / aquatic / mixed) and archetypes (conservation,
agroforestry, aquatic/lake, corporate, solar, mining, materials). It is written to
survive scientific peer review and to be convertible into a methods paper or technical
standard. The site-selection system is the front half of the same pipeline.

## 2. Design principles
Measure constructs, not datasets · separate evidence tiers · separate state from pressure
· average only within constructs · no score without a reference and an uncertainty ·
arbitrary constants become declared, tested parameters · fixed core + adaptive modules ·
run on partial data and light up as inputs arrive. The discipline that resolves most
reviewer concerns: **stop presenting product/reporting choices `[X]` as ecological facts
`[D]`.**

## 3. Construct architecture
Four fixed core components, each with named subdimensions (never averaged across):
C1 landscape context & extent · C2 vegetation condition · C3 faunal condition ·
C4 pressures & human interface. Ecosystem services / carbon are reported separately (an
outcome, not evidence of condition); screening layers are never scored. TNFD Annex 2 and
NPI IND1–9 are reporting **crosswalks** (§ TNFD/NPI docs), not the assessment skeleton —
this removed the pressure to invent metrics (e.g. range-overlap "population size") to fill
empty disclosure cells.

## 4. Indicator contract (machine-readable)
Every indicator declares construct, subdimension, ecological question, management use,
input layers, measurement scale, grain, period, effort basis, evidence tier, realm,
module, reference type, reference estimator, threshold basis, uncertainty method,
restoration sensitivity, reassessment frequency, management trigger, and the
`registered`/`active`/computed-`eligible` toggle. **Eligibility is computed, never
asserted:** an indicator scores only if registered, active, baseline/monitoring tier, with
a reference + uncertainty and no unmet dependencies. `input_layers` powers automatic
Gate-A redundancy screening. The full register (44 indicators; 10 scored) is
`INDICATOR_REGISTER.md`.

## 5. Reference benchmarking (SEED-aligned)

Contemporary least-disturbed counterfactual, selected within a joint **ecoregion x
land-cover** stratum (RESOLVE/ECOREGIONS/2017 x Dynamic World 10 m current modal
composite), HMI-masked at a **0.05 maximum** (SEED; realised threshold reported per
run; HMI from TNC Global Human Modification v3, 90 m, 2022). Pixels whose land-cover
class is artificial (crops/built) are relabelled with their Potential-Natural-Vegetation
class before stratum lookup — SEED's stated, narrow role for PNV — via a crosswalk that
**must be verified against the live PNV asset legend before first use** (flagged in the
config and in every run's diagnostics until verified). No elevation banding in this
default path (not part of SEED); an elevation-banded legacy mode remains available,
clearly separated, for users who want it.

Reference acceptance is gated by variance-stability (OD-3): a reference is used only if
its bootstrap median SE is within tolerance, else the score is suppressed rather than
computed on noise. A structural audit (v0.2.0.1) found and corrected several places
where an earlier build had diverged from the SEED paper's actual algorithm (PNV's role,
missing ecoregion constraint, wrong kernel norm) — see `ASSUMPTIONS_AND_LIMITATIONS.md`
§1 for the full item-by-item record, including what remains open (crosswalk
verification, delta calibration, live-GEE validation — all require real project data).

### 5.1 Estimator (responsive, scale-aware)
The legacy capped ratio `min(site/ref, 1)` is retired for scoring (censors improvement;
invalid off ratio-scale). Ratio-scale indicators use **log response ratio** (signed,
uncapped); interval/bounded indicators use **robust standardised deviation** +
percentile-in-reference. Honesty label `reference_type` accompanies every benchmarked
value. *Reference:* Hedges, Gurevitch & Curtis (1999) *Ecology* 80:1150.

### 5.2 Optional SEED similarity kernel (Eq. 1)
`K = exp[-delta (x-x_r)^T C_r^-1 (x-x_r)]` — a genuine Mahalanobis-distance kernel using
the reference sample's covariance, attached per construct as an **optional** view (never
replaces the direction-aware per-indicator benchmarks that drive scoring). Default mode
is "diagonal" (covariance treated as uncorrelated) for numerical stability given
typically small reference samples; "full" covariance (with shrinkage regularisation) is
implemented and available but not the default. Delta is a documented, uncalibrated
placeholder pending real project data (`estimators.fit_delta_diagonal` implements SEED's
stated calibration and is ready to run once that data exists).

## 6. Aggregation & scoring
Non-compensatory throughout: limiting-factor across subdimensions; penalised geometric
mean + published minimum across components; profile-first hybrid with an optional roll-up
(decision index, not a measurement) carrying propagated uncertainty, a sensitivity/
stability flag, and the mandatory framing block. State and pressure are separate axes
combined into a condition × pressure matrix. Cluster→project aggregation for large
multi-site AOIs is likewise non-compensatory (worst-tile headline). Full detail:
`SCORING_LOGIC_NOTE.md`.

## 7. In-situ metrics & cycles
Cycle 1: observed values + uncertainty + within-project rank (no concern classes —
self-referential thresholds are not a baseline). Cycle 2+: **change** vs the site's own
Year-0 with a detection test, plus the **BACI contrast** where a matched control exists
(`change.py`).

## 8. Modules by archetype
Fixed core + conservation / agroforestry (BAU-counterfactual reference) / aquatic /
corporate-extractive (mitigation-hierarchy, no-net-loss — registered-inactive by default)
modules; screening-only layers never scored. Comparability holds only within the fixed
core and within archetype.

## 9. Site selection (front half; v5.0)
Ecology-before-logistics (Stage A design / Stage B allocation); foundation-model
ecosystem stratification with visual verification maps + separability diagnostics;
spacing derived from detection distance × independence factor and the empirical
spatial-autocorrelation range; BACI/control at Year-0; a logistics envelope and an honest
representativeness statement (dropped strata are stated, not hidden). Assessment-cluster
tiling for large multi-site AOIs (renamed from "reference clusters" to reserve "reference"
for SEED). See the site-selection repo's README/CHANGELOG.

## 10. Reporting
Auto-generated **evidence-graded HTML** as a deterministic projection of the registry
(Nandoshi model, emitted every run): every claim carries its evidence grade; observed vs
modelled kept separate; scored / contextual / screening / pending / removed shown
honestly; the framing block published with any roll-up.

## Appendix A — External alignment
NPI State-of-Nature criteria, maturity ladder, exclusion taxonomy (`NPI_CROSSWALK.md`);
TNFD Annex 2 / LEAP (`TNFD_LEAP_CROSSWALK.md`); SEED biocomplexity; IUCN Global Ecosystem
Typology; Champion & Seth forest types.

## Appendix B — Honest maturity
North Shahdol Year-0 is Entry-level trending to Standard (mostly screening/contextual with
a thin baseline). This is a recognised NPI maturity level with a defined upgrade path
(`NEXT_CYCLE_IMPLEMENTATION.md`), stated openly rather than overclaimed.
