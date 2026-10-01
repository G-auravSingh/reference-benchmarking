# v1.1.0 Release Readiness and Live Acceptance

## Purpose

This document defines the boundary between **software validation** and **live Earth Engine/scientific validation** for `darukaa_adaptive_v1.1.0`.

The package is complete only when the automated checks pass and the live Nandoshi workflow executes without reference-engine errors.

## Automated checks

Required before GitHub replacement:

- all Python modules compile;
- all package tests pass;
- configuration validation passes;
- package version is `1.1.0`;
- notebook JSON is valid;
- notebook code cells compile;
- package integrity checks pass;
- release hash file is regenerated after final changes;
- no runtime/cache artifacts are included in the release archive.

## Live Earth Engine acceptance

The Nandoshi notebook must confirm:

1. Dynamic World resolves as an ImageCollection;
2. Sentinel-2 resolves;
3. Sentinel-1 resolves;
4. `TNC/HM/v3/90m_s` resolves as an ImageCollection;
5. `All_threats_combined` resolves;
6. `RESOLVE/ECOREGIONS/2017` resolves as a FeatureCollection;
7. the master KML loads and its SHA-256 is recorded;
8. the configured baseline dates are correct;
9. dynamic water detection executes;
10. monthly water diagnostics contain only actual baseline periods and observations;
11. the automatic aquatic reference engine executes without software/API errors;
12. reference candidate diagnostics are populated;
13. candidate rejection is distinguishable from execution failure;
14. the reference candidate excludes the assessed site itself;
15. reference selection uses the broader search radius rather than only the 5 km analytical context;
16. water extent is not assigned a fabricated 100% reference;
17. referenceable metrics receive a reference only when a valid candidate/value exists;
18. only explicitly approved references can influence score eligibility;
19. NDCI/red-reflectance/FAI indicators remain labelled as proxies;
20. missing C3 fauna evidence cannot appear as a scored 100;
21. report and machine-readable scorecards agree;
22. the assessment manifest contains the exact Git commit and site-file hash.

## Reference-engine acceptance

A successful live run should produce either:

- `validated_candidate` with explicit approval and diagnostics; or
- a documented non-error rejection such as insufficient population, failed ecological match, failed pressure screen, insufficient observations, or unresolved spatial stratum.

A status beginning with `error:` or a diagnostic containing an execution exception is **not** an acceptable final state.

## Scientific acceptance

Live execution does not by itself validate the ecological meaning of every EO proxy. The following remain scientific interpretation requirements:

- NDCI must not be described as calibrated chlorophyll without validation;
- red reflectance must not be described as calibrated turbidity without validation;
- FAI threshold exceedance must not be described as confirmed harmful algal bloom occurrence without validation;
- low HMI must not be described as proof of naturalness;
- a contemporary reference must not be described as pristine unless independently supported;
- spatial pixels must not be treated as independent ecological replicates;
- C3 fauna should be supplied by appropriate biological evidence before a complete condition statement is made.

## Final client-run rule

Do not issue a client result from this release until the live Nandoshi validation has been inspected and the complete output directory has been retained.
