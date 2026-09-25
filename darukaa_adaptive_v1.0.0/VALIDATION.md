# Validation record

## Scope

This release validates the adaptive package structure, configuration logic, pure-Python geometry utilities, benchmark/scoring functions, notebook syntax and output schema without claiming that Earth Engine-derived ecological proxies are field-validated.

## Automated checks

The test suite covers:

- explicit inclusive baseline date handling;
- baseline shifting and monthly/annual period generation;
- geometry parsing and area calculation;
- direction-aware benchmark ratios;
- 1–5 threshold concern scoring;
- reference-relative intactness scoring;
- pillar aggregation and overall-score gating;
- prevention of scoring when the composite is disabled;
- legacy 44-indicator crosswalk completeness;
- trajectory comparison semantics.

## Earth Engine validation boundary

The package cannot authenticate the user's Earth Engine account from this build environment. Therefore, the following require execution in the supplied Colab notebook:

- Dynamic World/Sentinel-1 water detection;
- Sentinel-2 optical metrics;
- GEE reduceRegion/sample results;
- Nandoshi-specific benchmark extraction;
- end-to-end map rendering;
- project-account dataset access.

The notebook includes explicit dataset initialization checks and prints the exact Git commit used by the runtime.

## Interpretation boundary

EO proxies such as NDCI, red-band reflectance and FAI bloom frequency are retained as screening indicators unless independent field observations support calibration. Biological P2/P3 evidence is not manufactured from EO-only layers, and overall SoN scoring is withheld by default when complete pillar evidence is absent.
