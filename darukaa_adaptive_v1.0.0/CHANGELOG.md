# Changelog

## 1.2.0
- Generalized the package from an aquatic-only implementation to terrestrial, aquatic and mixed profiles.
- Standardized the four pillars to C1 Extent, C2 Vegetation/Ecosystem Condition, C3 Fauna and C4 Pressure.
- Removed the context-ring reference strategy from the normal workflow.
- Added automatic ecoregion + least-modified terrestrial reference selection.
- Added automatic comparable-lake reference selection using HydroLAKES, ecoregion, area similarity, spatial exclusion and human-modification filtering.
- Added scale-aware reference benchmarking and responsive normalized 0–100 intactness.
- Locked the five Darukaa concern bands as a declared product convention.
- Added geometric-mean pillar and four-pillar SoN aggregation on continuous normalized scores.
- Kept C4 pressure as a separate axis while also exposing a four-pillar SoN when all four pillars have valid scored evidence.
- Added terrestrial EO metrics for natural habitat, vegetation NDVI, connectivity proxy, built-up fraction and human modification.
- Corrected aquatic metric pillar assignment: hydrology/extent to C1, water-quality/ecosystem-condition proxies to C2, shoreline disturbance to C4.
- Added generic field/acoustic/eDNA ingestion and future-proof external metric metadata.
- Added conservative eDNA evidence integration and templates.
- Added professional client-facing HTML report generation as the final Colab output.
- Hardened Earth Engine map callbacks with explicit `ee.Image` casting.
- Reference stability now uses bootstrap median standard error; aquatic human-modification screening is evaluated on near-shore context rather than the water interior.
- Broad shotgun-metagenomic assignment richness is kept out of the fauna pillar; a future fauna-specific eDNA richness metric is reserved for C3.
- Final report includes automatic reference-candidate diagnostics, metric definitions, readiness/data-gap reporting and source eDNA artefact links.

## 1.1.x
- Prior adaptive implementation and aquatic proof-of-concept.
