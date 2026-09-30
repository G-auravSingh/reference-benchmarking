# Validation — darukaa_adaptive_v1.0.0

## Local validation completed

- Python module compilation: passed.
- Package tests: **14 passed**.
- Notebook JSON parsing and every code cell syntax compilation: passed.
- Supplied `Nandoshi lake.kml` parsing: passed; one valid polygon named `Nandoshi lake`.
- Supplied Nandoshi KML area calculation: approximately **8.78 ha**.
- HTML report generation from synthetic/no-data scorecards: passed.
- Version consistency outside the frozen legacy package: `1.0.0`.
- No nested `darukaa_adaptive_v1.0.0/darukaa_adaptive_v1.0.0` release folder.

## Earth Engine validation boundary

The package was structurally validated locally. Live Earth Engine execution depends on the user's Colab account/project permissions and current Earth Engine availability. The notebook therefore authenticates and initializes GEE before any server-side metric calls.

## Scientific validation boundary

Automatic reference candidates are a reproducible benchmark-construction mechanism, not a claim that every candidate is pristine. Metric-specific ecological validity, calibration of remote-sensing proxies, and eDNA laboratory/taxonomic QC remain explicit evidence gates.
