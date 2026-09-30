# Reference and scoring model

## Reference population

A manually supplied reference is optional. The default engine constructs a candidate population using standardized spatial/ecological rules. Aquatic and terrestrial reference populations are domain-specific and are never silently substituted for one another.

The reference record retains method, candidate size, diagnostics and approval status. Reference uncertainty can be represented separately from the observed metric uncertainty.

## Benchmarking

The benchmark layer converts a raw value into a direction-aware comparison:

- `higher_is_better`: observed / reference;
- `lower_is_better`: reference / observed;
- `reference_target`: bounded departure from the comparable reference.

The displayed intactness is bounded to 0–100. This is a normalization convention, not a claim that all ecological indicators share identical response functions.

## Scoring eligibility

An indicator is score-eligible only when:

1. the measurement is valid;
2. the indicator is referenceable;
3. a comparable reference is available;
4. the reference is approved by the configured reference pathway.

Contextual/screening metrics remain visible without being silently converted into a composite score.

## Pillars

- C1 Extent
- C2 Vegetation / Habitat Condition
- C3 Fauna
- C4 Pressure

C1–C3 are aggregated as condition. C4 is reported separately as pressure. A complete four-pillar composite can be enabled deliberately, but the aquatic Year-0 profile does not require a synthetic composite when fauna evidence is absent.
