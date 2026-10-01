# Validation — darukaa_adaptive_v1.1.0

## Automated validation target

The release must pass:

- complete pytest suite;
- Python compilation of all package modules;
- configuration validation for the aquatic profile;
- notebook JSON validation;
- notebook Python-code-cell compilation;
- package integrity checks;
- release SHA-256 regeneration after all source/documentation changes.

## Live Earth Engine validation boundary

Software tests cannot verify Earth Engine authentication, current dataset availability or live geospatial results. The Nandoshi Colab workflow is therefore the authoritative live acceptance test.

The live run must verify:

1. Dynamic World access;
2. Sentinel-1 access;
3. Sentinel-2 access;
4. TNC HM v3 90 m ImageCollection access and `All_threats_combined` band;
5. RESOLVE Ecoregions FeatureCollection access;
6. master KML geometry and hash;
7. dynamic water detection;
8. Year-0 monthly water series;
9. automatic aquatic reference construction;
10. reference QA diagnostics;
11. reference candidate geometry/metrics;
12. reference benchmark generation;
13. reference approval/score-eligibility gating;
14. C3 fauna gating;
15. report/manifest consistency.

## Scientific validation boundary

Passing code tests does not validate ecological calibration. NDCI, red reflectance, FAI bloom frequency and NDVI remain EO proxies unless independent evidence supports a stronger interpretation.

An automatically approved contemporary reference is a reference candidate accepted by explicit rules; it is not proof of pristine or pre-human ecological condition.

## Current release-build status

The package has been rebuilt and internally checked in this environment. The remaining acceptance step is the user's live Colab/GEE execution and inspection of the resulting output bundle.

The final package should not be described as live-validated until that step is complete.
