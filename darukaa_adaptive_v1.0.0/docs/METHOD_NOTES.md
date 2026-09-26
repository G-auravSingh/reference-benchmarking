# Method notes — v1.2.0

## 1. Spatial frame

The supplied KML/KMZ is the master assessment boundary. Four deterministic analytical domains can be derived: dynamic water, a 50 m littoral/nearshore band, a 100 m fixed riparian band, and a broader 5 km terrestrial/context domain.

## 2. Reference selection

The reference workflow is fully automated. No project reference KML/CSV is required.

Terrestrial indicators use the site's resolved ecoregion, low-human-modification pixels and relevant land-cover masks. Aquatic indicators use comparable waterbodies from HydroLAKES within the site's ecoregion, approximate area similarity, spatial exclusion and a low-human-modification screen.

Reference populations are represented as distributions. A benchmark is approved only when the minimum reference sample size and relative uncertainty criteria are met and the estimator is valid for the metric's measurement scale.

## 3. Benchmarking and normalization

Ratio-scale metrics use a signed log response ratio. Bounded/index/interval metrics use a signed robust standardized deviation where reference dispersion permits. The sign is oriented so positive means better-than-reference.

The signed benchmark is transformed by a declared logistic to a 0–1 normalized score and displayed as 0–100. The reference condition is the midpoint (50%). The raw signed benchmark and reference distribution are retained for auditability.

## 4. Concern bands

- 80–100: Very Low
- 60–<80: Low
- 40–<60: Moderate
- 20–<40: High
- 0–<20: Very High

These are a declared Darukaa product convention and are not universal ecological thresholds.

## 5. Pillar aggregation

C1, C2, C3 and C4 are the fixed core pillars. Continuous 0–100 indicator scores are combined using geometric means. Concern labels are assigned only after aggregation. The limiting indicator/pillar is published alongside the aggregate.

Overall State of Nature is produced when all four pillars have valid scored evidence. Overall condition (C1–C3) and pressure (C4) remain separately available.

## 6. Evidence streams

Field, acoustic and eDNA metrics enter through a shared observation contract. A metric may be reported as measured/indicated/inferred/unresolved without being scored. Quantitative scoring requires a comparable reference and explicit approval.
