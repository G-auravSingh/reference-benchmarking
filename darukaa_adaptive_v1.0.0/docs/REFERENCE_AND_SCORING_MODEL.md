# Reference, Intactness and Scoring Model

## Scope

The standard adaptive workflow is automated. A project does **not** require a client-supplied reference KML or reference CSV.

## Automatic reference hierarchy

### Terrestrial

The engine resolves the project's ecological context using the RESOLVE 2017 ecoregion layer. It excludes the project area and its immediate exclusion buffer, applies a least-modified Human Modification filter, and uses the site's terrestrial land-cover context for appropriate condition metrics. The resulting pixel population is the reference distribution.

### Aquatic

The engine resolves the site's ecoregion and searches the HydroLAKES catalog for comparable waterbodies. Candidates are screened by ecological region, approximate area similarity, spatial exclusion and near-shore Human Modification context. Candidate-level water metrics are then calculated under the same definitions used at the project site. There is no automatic promotion of a generic 5 km context ring to a reference population.

A manually supplied reference can be supported as an explicit future override, but it is not required by the standard workflow.

## Reference uncertainty

The reference median is accompanied by a bootstrap standard error. A reference is approved for scoring only when the minimum reference sample size, estimator validity and configured relative-SE tolerance are satisfied.

## Indicator benchmark

The benchmark estimator is scale-aware:

- ratio-scale quantities use a signed log response ratio;
- interval/bounded/index quantities use a signed robust standardized deviation;
- direction is oriented so a positive signed benchmark means better relative to reference.

The signed benchmark is converted through a declared logistic normalization for aggregation and reporting. **50% is the normalized midpoint at the reference condition.** This is a product normalization, not a claim that 50% represents a universal ecological threshold.

## Concern convention

Concern is assigned only after the continuous normalized score exists:

| Intactness / normalized score | Concern |
|---:|---|
| 80–100 | Very Low |
| 60–<80 | Low |
| 40–<60 | Moderate |
| 20–<40 | High |
| 0–<20 | Very High |

These five equal-width bands are a declared Darukaa product convention.

## Pillars and aggregation

The fixed core is:

- C1 — Extent
- C2 — Vegetation / ecosystem condition
- C3 — Fauna
- C4 — Pressure

Indicators are aggregated on continuous 0–100 scores using the geometric mean. Concern labels are never averaged. The overall condition score is the geometric mean of C1–C3. C4 is retained as a separate pressure axis; the four-pillar State of Nature score is exposed when all four pillars have valid scored evidence.

Every roll-up names the limiting pillar and limiting indicator where available.
