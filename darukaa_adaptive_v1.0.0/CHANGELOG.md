# Changelog

## 1.2.0 — universal intactness and four-pillar scoring

- Replaced the legacy adaptive scoring path with a universal 0–100 intactness framework.
- Standardized the common pillars to **C1 Extent, C2 Vegetation, C3 Fauna, C4 Pressure**.
- Added direction-aware reference comparison for higher-is-better, lower-is-better and reference-target indicators.
- Declared the five fixed concern bands: 0–<20 Very High, 20–<40 High, 40–<60 Moderate, 60–<80 Low, 80–100 Very Low.
- Documented the bands as a Darukaa product convention rather than universal ecological thresholds.
- Changed pillar aggregation to the geometric mean of continuous 0–100 intactness scores.
- Changed overall SoN aggregation to the geometric mean of the four pillar scores.
- Added explicit limiting-indicator reporting for each pillar and limiting-pillar/limiting-indicator reporting for overall SoN.
- Added explicit reference approval gating so candidate/reference values can be displayed without silently affecting scores.
- Added a generic external-observation scoring interface for field, terrestrial, acoustic, eDNA and other validated observations.
- Added baseline riparian NDVI as a C2 vegetation metric; retained riparian NDVI trend as contextual.
- Extended aquatic reference calculation to water extent, water persistence and baseline riparian NDVI.
- Updated readiness, documentation and notebook interpretation guardrails.
- Kept `legacy/darukaa_reference_v0.1.0/` unchanged.
