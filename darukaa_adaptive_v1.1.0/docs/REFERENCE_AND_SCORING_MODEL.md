# Reference and scoring model

## 1. Reference population

The production default constructs an **ecologically matched, least-disturbed contemporary reference population**. It is not defined as the nearest good-looking pixel and it is not automatically synonymous with pristine condition.

Reference construction and approval are separate:

```text
candidate construction → ecological/pressure/temporal/spatial QA → approval → metric benchmark
```

Manual reference geometry/CSV uploads are not part of the production workflow.

## 2. Reference states

Supported reference states are:

- `undisturbed_minimally_disturbed`
- `least_disturbed_contemporary`
- `historical`
- `best_attainable`
- `paired_control`
- `published_target`

The default automated state is `least_disturbed_contemporary`. If both automatic stages fail, Colab exposes a single analyst-entered HMI threshold as the finite Stage-C fallback.

## 3. Reference distribution

Where reference values are available, the engine retains:

- n;
- median;
- mean;
- SD;
- MAD;
- P10/P25/P75/P90;
- bootstrap median interval and SE.

The median is the default central benchmark. Bootstrap uncertainty is descriptive because spatial pixels are not independent replicates.

## 4. Benchmarking

The benchmark layer produces a direction-aware comparison:

- higher-is-better: observed/reference;
- lower-is-better: reference/observed;
- reference-target: bounded departure from target.

The signed **relative departure** is the primary descriptive comparison.

The legacy `intactness_score_0_100` field is retained as an alias for compatibility. Production interpretation uses **reference attainment** and the declared reference state. A value at/above 100 means the observed metric meets or exceeds the selected reference under the current display convention; it does not mean ecological perfection.

## 5. Scoring eligibility

An indicator is score-eligible only when:

1. measurement is valid;
2. indicator is referenceable;
3. comparable reference exists;
4. reference passes the approval gate;
5. indicator direction/target is defensible;
6. evidence tier supports scoring;
7. proxy limitations do not invalidate the intended ecological interpretation.

Contextual/screening metrics remain visible without being silently converted into a composite score.

## 6. State versus pressure

- C1–C3 = ecosystem/species condition.
- C4 = pressure.

Pressure remains structurally separate from condition.

## 7. Landscape intactness

The term **landscape intactness** is reserved for spatial configuration concepts such as fragmentation, connectivity, core area and distance-to-collapse constructs. A site/reference ratio for an environmental variable is not called landscape intactness.

## 8. External evidence

Field, acoustic, eDNA and other evidence can enter the same downstream contract, but evidence-specific reference requirements remain explicit. A first baseline does not create a valid self-referential reference merely because the observed data exist.

## 9. v1.1.0 integrated-pipeline controls

The reference layer is now executed as part of the complete `AdaptivePipeline`, not as a separate post-processing step.

The pipeline records the automatic reference population summary and carries reference diagnostics into every benchmark record. The default central estimator for raster-derived reference metrics is the spatial median (`P50`) when available; spatial percentiles are retained for audit.

The aquatic profile requires a score-eligible C3 Fauna pillar before an overall condition score is emitted. C4 Pressure remains separate.

The live Nandoshi notebook includes a release-blocking check for reference-engine execution errors. A candidate can legitimately be rejected by the QA gates; that is different from a failed dataset/API operation.

The production workflow does not require or accept manual reference KML/CSV uploads. If both automatic contemporary stages fail, the Colab exposes a finite manual HMI-threshold fallback.
