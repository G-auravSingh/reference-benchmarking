# Changelog

## 1.0.0 — initial adaptive lake architecture

- Preserved supplied `darukaa_reference_v0.1.0` as an untouched legacy package.
- Added KML-only automatic lake characterization.
- Added Dynamic World-based water probability masks.
- Added automatic fixed riparian buffer.
- Added water-aware TSPI, SABF, WCPI and WSDI calculations.
- Added multi-year riparian NDVI trend.
- Added RCI and descriptive SHDI.
- Added explicit metric status/no-data handling.
- Added compatibility scoring using thresholds from the supplied Nandoshi methodology.
- Marked lake SoN as provisional until aquatic reference/benchmark validation is completed.
- Corrected the current-year water persistence architecture so JRC v1.4 is not incorrectly requested beyond its historical coverage.
