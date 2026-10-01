# R4 Release Readiness

## Scope

This release hardens the reference-condition architecture. It does not claim that every ecological metric already has a scientifically validated response function.

## Automated tests required

- Python compilation of all package modules.
- Existing package regression suite.
- Reference-condition unit tests.
- Configuration validation.
- Benchmark compatibility tests.
- Report-generation regression test for missing C3.
- Manifest provenance test.

## Live Earth Engine validation

A live Earth Engine run is required before a client result is issued from a new release. The live test must confirm:

1. reference search returns an expected candidate population;
2. RESOLVE ecoregion filtering resolves correctly;
3. TNC HM v3 asset/band resolves;
4. Dynamic World label asset resolves;
5. water occurrence and candidate hydrological matching execute;
6. candidate geometry is valid;
7. reference QA diagnostics are populated;
8. reference approval changes correctly when a QA gate is intentionally failed;
9. benchmark values are generated only for approved/referenceable metrics;
10. report and manifest contain the reference governance fields.

## Nandoshi acceptance criteria

For Nandoshi Lake, the release is accepted only if:

- the automatic aquatic reference does not use the lake boundary itself;
- the reference search is broader than the 5 km analytical context;
- candidate water is hydrologically comparable to the focal lake;
- candidate surroundings pass the pressure screen;
- reference approval is explicitly recorded;
- `water_extent` remains a hydrological/reference-target metric and is not benchmarked against 100% water;
- NDCI/turbidity/bloom proxies remain labelled as proxies;
- missing C3 evidence cannot appear as a scored 100;
- exact Git commit is present in the manifest.

## Known methodological boundary

Reference selection can be automated spatially, but ecological validation cannot be reduced to one universal EO rule. Ecosystem-specific typology, field validation, historical evidence and metric-specific response functions may be required for higher evidence tiers.
