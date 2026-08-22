# Scoring Logic Note

Plain-language specification of how a site goes from raw indicator values to the
profile-first output. The authoritative code is `scoring.py` + `estimators.py`.

## 1. Per-indicator benchmark (responsive, scale-aware)
Each scored indicator is compared to its reference via `estimators.benchmark`:
- **ratio-scale** (cover %, density, counts, canopy height) → **log response ratio**
  `ln(site/ref)`, signed, **uncapped** (above-reference gains stay visible);
- **interval / bounded / index** (NDVI, temperature, indices) → **robust standardised
  deviation** `(site−median)/(1.4826·MAD)` + percentile-in-reference.
Oriented so >0 = better than reference. The legacy capped ratio `min(site/ref,1)` is
retired for scoring (it censored improvement and was invalid off ratio-scale).

## 2. Normalise for aggregation (declared, reversible)
Signed benchmarks map to a 0–1 aggregation score via a declared logistic (0.5 = at
reference). This is for roll-up/banding only `[X]`; the profile always shows the raw
signed value + CI.

## 3. Within a component — limiting-factor rule
Across subdimensions, the component is reported at its **weakest subdimension** (the
binding constraint), never the mean. The mean is shown only as context. Averaging is
permitted *within* a subdimension (redundant measures of one construct), never across
distinct constructs.

## 4. Across components — non-compensatory roll-up (optional, secondary)
When a roll-up is produced it is a **penalised geometric mean** with the **minimum
component always published alongside**, so a strong component cannot mask a weak one.
Weights: equal by default `[X]`, methodology-version-locked; project weights only by
pre-registration. Uncertainty is propagated; a **sensitivity analysis** recomputes under
alternative weights and flags the roll-up **UNSTABLE** if its band flips.

## 5. State vs pressure — never blended
Condition (C1–C3) and pressure (C4) are scored on **separate axes** and combined only
into the condition × pressure **matrix** (Protect / Defend / Restore / Stabilise-then-
restore). No single number mixes state and pressure.

## 6. The framing block (published verbatim with every roll-up)
> The score is a transparent summary combined with pre-declared weights — a decision aid
> for triage. It is NOT a measurement of biodiversity, a probability of success, or
> comparable across organisations/projects unless module set and reference basis match. A
> change in the number is not by itself ecological change — read the profile and its
> uncertainty. Read the minimum component first, the profile second, the roll-up last.

## 7. Cluster→project (large multi-site AOIs)
Per-tile scores aggregate to project level **non-compensatorily**: the project headline
is the **worst tile**, with an area-weighted geometric mean as secondary context.
(Physical quantities like area/biomass keep the area-weighted mean.)

## 8. Cycle 2+ (change)
In-situ metrics score as **change** from the site's own Year-0 (`change.py`): delta with
propagated uncertainty + a detection test (does it exceed measurement noise?), and the
BACI contrast (impact change − control change) where a matched control exists.

## 9. Optional SEED kernel view (OD-4)
When enabled, a whole-construct SEED similarity `exp[-δ·‖w⊙z‖₁]` is attached per
construct — a similarity-to-reference view that complements, never replaces, the
direction-aware component score. (δ calibration is provisional — see limitations S-2.)
