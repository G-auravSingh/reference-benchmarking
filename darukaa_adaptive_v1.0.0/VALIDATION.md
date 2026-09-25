# Validation record

## Scope

This release validates the adaptive package structure, configuration logic, pure-Python geometry utilities, reference benchmarking, universal 0–100 intactness scoring, four-pillar aggregation, notebook syntax and output schema without claiming that Earth Engine-derived ecological proxies are field-validated.

## Automated checks

The test suite covers:

- explicit inclusive baseline date handling;
- baseline shifting and monthly/annual period generation;
- geometry parsing and area calculation;
- direction-aware reference comparisons;
- the fixed 0–100 concern bands;
- reference-target intactness;
- geometric-mean pillar and overall aggregation;
- explicit limiting-indicator and limiting-pillar reporting;
- reference-approval scoring gates;
- generic field/external observation scoring;
- four-pillar C1/C2/C3/C4 registry structure;
- legacy 44-indicator crosswalk completeness;
- trajectory comparison semantics.

## Earth Engine validation boundary

The package cannot authenticate the user's Earth Engine account from this build environment. Therefore, the following require execution in the supplied Colab notebook:

- Dynamic World/Sentinel-1 water detection;
- Sentinel-2 optical metrics;
- GEE reduceRegion/sample results;
- Nandoshi-specific reference extraction;
- end-to-end map rendering;
- project-account dataset access.

The notebook includes explicit dataset initialization checks and prints the exact Git commit used by the runtime.

## Interpretation boundary

EO proxies such as NDCI, red-band reflectance and FAI bloom frequency remain screening indicators unless an appropriate comparable reference and independent validation support their use in the ecological score.

The five concern bands are a declared Darukaa product convention, not universal ecological thresholds.

A complete overall State of Nature score requires scoreable evidence in all four pillars. C3 Fauna must be supplied by appropriate biodiversity observations (for example field surveys, acoustics or eDNA) rather than inferred from EO water proxies.
