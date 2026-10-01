# Validation status — Darukaa Adaptive v1.1.0 / R4

## Automated validation completed

- **29 pytest tests pass** in the clean R4 package tree.
- All Python modules compile with `python -m compileall`.
- Nandoshi notebook JSON is valid.
- All 28 notebook code cells compile as Python syntax.
- `aquatic_lake.yaml` loads successfully and passes configuration validation.
- Reference-condition pure functions are tested for:
  - reference distribution statistics;
  - reproducibility;
  - candidate population gates;
  - ecological-match gate;
  - pressure gate;
  - reference-state validation;
  - relative departure;
  - percentile calculation;
  - bounded reference attainment;
  - reference governance propagation;
  - missing-fauna report rendering.
- Existing package regression tests remain passing.

## Packaging validation

The source tree is internally consistent and the package imports correctly from the release tree. A local editable-install attempt was also checked; dependency/build isolation could not be fully exercised because this execution environment has no outbound package-index/network access. The package's normal Colab installation remains the authoritative dependency-resolution path.

## Live Earth Engine validation boundary

The following cannot be honestly claimed from this environment and must be executed in the target Colab/GEE project before a client result is issued:

1. Dynamic World access.
2. Sentinel-1/Sentinel-2 access.
3. RESOLVE ecoregion lookup.
4. TNC HM v3 90 m asset and band access.
5. Live automatic aquatic reference construction.
6. Live automatic terrestrial reference construction.
7. Reference candidate geometry/vectorization.
8. Live metric extraction over the reference population.
9. End-to-end Nandoshi baseline run under the R4 reference architecture.

The production acceptance criteria for that live test are documented in `docs/RELEASE_READINESS_R4.md`.

## Scientific validation boundary

Passing software tests does not establish that an EO proxy is ecologically calibrated. Metrics such as NDCI, red reflectance and FAI bloom frequency remain proxy measurements unless independently validated against field/laboratory observations or a defensible published response function.

Likewise, an automatically approved contemporary reference is a **least-disturbed reference candidate accepted by explicit spatial/QA rules**, not proof of pristine or pre-human condition.
