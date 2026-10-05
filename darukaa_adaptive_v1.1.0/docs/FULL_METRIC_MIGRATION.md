# Full Metric Migration — darukaa_adaptive_v1.1.0

## Purpose

v1.1.0 uses the v0.2.7 calculator implementations as the authoritative source for the
full ex-situ metric inventory, while v1.1.0 remains authoritative for EMU ingestion,
realm applicability, status handling, reference routing, benchmarking, scoring,
aggregation, QA and reporting.

The legacy pipeline, legacy scoring implementation and legacy project aggregation are
**not** invoked by the adaptive pipeline.

## Live inventory

The v0.2.7 source contains 46 live registered calculators. The migration preserves all
46:

- Ecosystem extent/configuration: natural_habitat, natural_landcover, cpland,
  forest_loss_rate, net_forest_change_rate, kba_overlap, flii, rci,
  riparian_ndvi_trend, jrc_water_persistence
- Ecosystem condition: ndvi, habitat_health, eii, eii_structural,
  eii_compositional, eii_functional, pdf, aridity_index, tspi, sabf, wcpi,
  wsdi, hsas, edpp, mspl, shdi, lai, chm
- Biodiversity integrity/species: bii, endemic_richness, shi, flagship_habitat,
  endemic_plant_richness, threatened_richness, ceri, star_t,
  threatened_plant_richness
- Anthropogenic pressure: ghm, light_pollution, hdi, lst_day, lst_night, sdi,
  stsi, iri, ivsi

The stale v0.2.7 module header says "44"; the live registry actually registers 46.
The live registration inventory is therefore treated as authoritative.

## Status semantics

Every migrated metric is represented using the v1 MetricResult contract:

- `calculated`: calculator returned a finite value.
- `not_applicable`: metric is outside the configured realm.
- `pending_input`: an optional dependency/input required for the calculator is unavailable.
- `calculation_failed`: calculator raised an execution error.
- `no_valid_observation`: calculator completed but returned no usable value.

A non-calculated metric is never silently converted to zero.

## Scoring roles

Legacy contract metadata is mapped into explicit v1 roles:

- `SCORED`: contract-retained/redefined metric with defensible reference and uncertainty metadata.
- `CONTEXTUAL`: reported but not automatically collapsed into a condition score.
- `DIAGNOSTIC`: screening/context signal; not part of the composite condition score.
- `REMOVED`: retained only for transparent historical/crosswalk provenance and never scored.

The calculator adapter does not invoke the legacy scoring or reference-selection code.

## Reference benchmarking

For migrated scored metrics, the v1 pipeline applies the same calculator to the approved
v1 reference-population geometry and passes the resulting reference value into the v1
benchmarking layer. This keeps observed and reference calculations semantically aligned
while retaining v1 reference-selection and approval rules.

Where a calculator returns a pixel array, the adapter also preserves descriptive
reference diagnostics (n, SD, and percentile summaries). Where the legacy calculator
returns only a scalar, the v1 output explicitly lacks those pixel-level diagnostics
rather than inventing them.

## Scientific guardrails

The framework retains the principle that condition is assembled from ecologically
relevant characteristics and indicators and that aggregation is optional and must remain
interpretable. SEEA likewise emphasizes selecting indicators scientifically and relating
them to a reference condition, while warning that aggregation can conceal important
information. See the SEEA ecosystem condition framework and indicator-account guidance.

## Acceptance status

- Existing v1.1.0 regression suite: 48 tests passed.
- Full-migration regression suite: 52 tests passed.
- Full legacy live registry: 46/46 calculators discovered.
- Full v1 registry inventory: 46/46 migrated calculator names.
- Duplicate-name check: passed.
- Scored-metric reference/uncertainty contract check: passed.
