# Changelog — darukaa_adaptive_v1.1.0

## v1.1.0 — Complete adaptive methodology and pipeline build — 2026-10-01

This release consolidates the full adaptive assessment workflow into one internally consistent package. The reference-condition changes are integrated with measurement QA, benchmarking, scoring, readiness, reporting, provenance and the Nandoshi Colab workflow.

### Assessment architecture

- Profile-driven aquatic, terrestrial and mixed workflows retained.
- Master KML/KMZ remains the canonical project boundary input.
- Geometry QA, local-UTM area calculation and input SHA-256 provenance retained.
- Aquatic dynamic-water, riparian, shoreline and landscape-context domains remain explicit.
- Reference search radius is separated from the ordinary analytical context.

### Aquatic metrics and water detection

- Dynamic World remains the primary water detector.
- Sentinel-1 VV remains the configured fallback when optical coverage is insufficient.
- Water extent remains descriptive/reference-target rather than universally higher-is-better.
- Water persistence now retains spatial distribution diagnostics in addition to its central value.
- NDCI, red reflectance and FAI bloom frequency remain explicitly labelled optical proxies.
- Riparian NDVI and Theil–Sen/Kendall trend remain separated into baseline condition and contextual monitoring roles.
- Shoreline disturbance remains a transparent pressure proxy.
- Modal Dynamic World land-cover composition is retained as a composition diagnostic and is not conflated with dynamic water extent.

### Reference-condition framework

- Added explicit reference-state taxonomy.
- Automatic aquatic reference selection now combines hydrological similarity, dominant RESOLVE ecoregion compatibility, low-pressure screening, temporal adequacy and population gates.
- Automatic terrestrial reference selection combines ecoregion, Dynamic World comparability stratum and low human-modification screening.
- Automatic approval is strictly QA-gated.
- Reference candidates exclude the assessed site from the search annulus.
- Raster-derived reference metrics use the spatial median (`P50`) as the default central estimator when available, while retaining additional spatial percentiles for audit.
- Reference diagnostics distinguish candidate rejection from software execution failure.
- Legacy `intactness_score_0_100` is retained only as a compatibility alias; production terminology is reference attainment.
- Water extent is never assigned a false 100% reference.
- Manual Tier-1 reference KML and CSV inputs are supported; explicit Tier-1 approval remains required for scoring.

### Earth Engine implementation hardening

- Corrected TNC HM v3 90 m static snapshot handling: `TNC/HM/v3/90m_s` is loaded as an Earth Engine ImageCollection and the configured `All_threats_combined` band is derived from the collection.
- Aquatic HMI screening uses surrounding land context rather than interpreting terrestrial HMI as water quality.
- RESOLVE ecoregion selection now chooses the dominant site-overlap feature rather than indiscriminately unioning all intersecting ecoregions.
- Reference-engine exception diagnostics are retained rather than silently reduced to empty diagnostics.

### Scoring and readiness

- Condition and pressure remain structurally separate.
- Overall condition now respects the configured C3 Fauna requirement.
- Missing C3 cannot be represented as a valid 100/100 condition pillar.
- Reference approval is required before a reference-derived metric can become score-eligible.
- Reference governance fields propagate through benchmark, scorecard, readiness and manifest outputs.

### Reporting and provenance

- Added `reference_governance.csv`.
- Assessment manifest now retains benchmark, metric-concern, pillar and reference-population governance records in addition to configuration and provenance.
- HTML reports distinguish unassessed pillars from scored pillars.
- HTML reports expose reference method/state/approval and relative-departure fields.
- Output README expanded into an auditable output contract.

### Colab workflow

- Nandoshi notebook now installs only `darukaa_adaptive_v1.1.0` from a clean repository checkout.
- Package path/version checks include the reference-condition modules.
- Dataset preflight explicitly checks TNC HM as an ImageCollection and RESOLVE as a FeatureCollection.
- Exact Git commit is recorded in `DARUKAA_GIT_COMMIT` and therefore in the assessment manifest.
- Added mandatory live reference-condition validation checkpoint.
- Any automatic-reference execution error is treated as a validation failure rather than silently accepted.
- Monthly water diagnostics remain aligned to the configured Year-0 baseline.

### Documentation

- Added `docs/METHODOLOGY.md` as the overall company methodology for the full pipeline.
- Updated reference-condition, scoring, method notes, runbook, release-readiness and validation documents.
- Documentation now distinguishes implementation status, methodological guardrails and live-validation requirements.

## Historical base

Earlier `darukaa_adaptive_v1.0.0` work remains represented by the historical package and migration documentation. Historical releases should be retained when exact reproducibility of an older assessment is required; they should not be mixed module-by-module with v1.1.0.
