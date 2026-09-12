# Nature Positive Initiative (NPI) Crosswalk

Alignment of the Darukaa framework to the NPI State-of-Nature metrics consultation
(Feb 2026 brief + Oct 2024 terrestrial metrics longlist). NPI is the closest emerging
industry standard; we adopt three things from it (criteria, maturity ladder, exclusion
taxonomy) and map our constructs to their indicators.

## 1. Constructs ↔ NPI indicators (IND1–9)
| Darukaa | NPI indicator |
|---|---|
| C1 extent | IND1 Ecosystem extent (change & classification) |
| C1 configuration / forest integrity | IND3 Landscape intactness (config / distance-to-collapse); IND8 (connectance, core area) |
| C2 vegetation condition | IND2 Ecosystem condition |
| C3 faunal (abundance/occupancy as change) | IND9 Species population abundance (change in triggering-species trends) |
| Confirmed priority-species status (not scored) | IND4 Species extinction risk (STAR, resolution-aware) |
| Screening (range overlap) | — (NPI excludes as "not a state metric" / coarse) |

## 2. Maturity ladder = our evidence tiers
| NPI tier | Darukaa evidence tier | Meaning |
|---|---|---|
| Entry-level | screening / contextual | RS/modelled only |
| Standard | baseline | RS + ground-truthing |
| Advanced | monitoring | high-res + ground-truth + change |
A first Year-0 baseline typically sits at **Entry-level trending to Standard** — a named, recognised
maturity level, not a failure.

## 3. NPI criteria adopted as our eligibility gate
Credible & science-based · Assurable/verifiable (field-verifiable) · **Responsive to
increases AND decreases** (the direct external basis for retiring the `min(ratio,1)`
cap) · Aligned · Future-proof · Flexible · Accessible.

## 4. Exclusion taxonomy adopted
"not a state metric" (validates pressure/state separation — NPI's largest exclusion) ·
duplicate (redundancy screen) · not clearly directional · data too old (>5 yr) · coarse
resolution · modelled-not-responsive · incompletely described. Used as our
`exclusion_reason` vocabulary.

## 5. Key NPI-driven correction
"Intactness" in the mature standard means **landscape configuration / distance-to-
ecosystem-collapse (IUCN RLE, ecoregion scale)** — NOT a site÷contemporary-reference
ratio. Our current construct is renamed accordingly; the configuration/distance-to-
collapse "landscape intactness" is the Advanced-tier C1 target (not yet built).
