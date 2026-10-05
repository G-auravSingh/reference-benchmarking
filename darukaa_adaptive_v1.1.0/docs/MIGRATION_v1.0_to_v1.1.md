# Migration from v1.0.0 to v1.1.0

## What changed

The main methodological change is the reference-condition architecture.

### Before

```text
automatic spatial candidate
        ↓
reference value
        ↓
reference-relative intactness
```

### v1.1.0

```text
automatic candidate
        ↓
ecological matching
        ↓
pressure screen
        ↓
temporal compatibility
        ↓
population/spatial QA
        ↓
approved reference population
        ↓
reference distribution
        ↓
reference-relative departure
        ↓
reference attainment
```

## Output changes

New benchmark fields include:

- `reference_state`
- `reference_approval_basis`
- `reference_diagnostics`
- `relative_departure_pct`
- `reference_attainment_0_100`
- `interpretation_status`

The legacy `intactness_score_0_100` field remains so downstream systems do not break immediately.

## Configuration changes

New reference controls include:

- `search_radius_km`
- `ecoregion_gee_asset`
- `landcover_asset`
- `hmi_gee_asset`
- `hmi_gee_band`
- `hmi_max_for_reference`
- `hmi_context_radius_m`
- `water_occurrence_tolerance`
- `min_ecological_match_score`
- `min_reference_observations`

## Interpretation change

Do not describe a reference-attainment value of 100 as "perfect" or "100% intact". It means that the observed metric meets or exceeds the selected reference under the current bounded display convention.

## Reproducibility

Results from v1.0.0 and v1.1.0 should not be mixed as though they came from the same reference methodology. Re-run baseline assessments if a client requires a comparable time series under the new methodology, and retain the old release for exact historical reproduction.
