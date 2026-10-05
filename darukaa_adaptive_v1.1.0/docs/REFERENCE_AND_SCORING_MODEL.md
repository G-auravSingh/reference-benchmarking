# Reference, Benchmarking and Scoring Model

## Reference → benchmark → score → aggregate

The production pathway is:

```text
Ecologically eligible reference population
        ↓
Reference distribution + QA
        ↓
Observed/reference benchmark
        ↓
Indicator-specific 0–100 attainment
        ↓
Complementary metrics → geometric mean
        ↓
Subdimensions → limiting factor
        ↓
P1/P2/P3 → geometric mean + limiting pillar
        ↓
Project aggregation + EMU comparison
```

P4 pressure is kept separate.

## Why not aggregate raw z-scores?

Z-scores and robust z-scores are retained as statistical diagnostics when reference dispersion is available. They are not the client-facing aggregate because their magnitude depends on reference variance and is not naturally comparable as a management score across indicators. The common 0–100 scale is the reporting layer; the statistical benchmark remains visible underneath it.

## Why geometric means?

At the complementary-metric level, the geometric mean reduces compensatory behaviour while retaining more information than a minimum. It is applied only after metrics have been normalized to a common ecological attainment scale.

## Why limiting-factor at pillar level?

Different subdimensions within a pillar can represent genuinely distinct ecological constraints. A high vegetation-greenness score should not erase a severe hydrological deficit. The pillar therefore reports the weakest defensible subdimension and retains the metric responsible for that limitation.

## Why not a single universal weighting scheme?

The framework does not assign arbitrary weights to individual indicators. Indicator sets can change as better evidence becomes available, and equal weighting of redundant indicators would create hidden double-counting. The registry therefore groups metrics by ecological subdimension and requires an explicit scientific rationale for future additions.

## Project-level score

The project score is produced only after EMU-level assessment. The default common-score aggregation is area-weighted. The project report additionally shows the EMU distribution, coverage, limiting EMU and percentiles. This prevents a project headline from hiding strong internal ecological heterogeneity.

## Reference states

Reference state labels are explicit. `strict_contemporary`, `least_disturbed_contemporary` and `best_attainable` are not synonyms for pristine condition. They describe the governance basis for the comparison population.
