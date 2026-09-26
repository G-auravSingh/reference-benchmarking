# Validation record

## Scope

The adaptive package is validated at the software and methodology-contract level. Earth Engine-derived ecological values still require execution in the user's authenticated Google Earth Engine environment and should be interpreted with the validation limits declared in the indicator registry.

## Automated checks completed for this release

- 17 Python tests pass.
- All adaptive Python modules compile successfully.
- Colab notebook syntax compiles cell-by-cell after treating shell commands as execution-time commands.
- Final notebook cell is the HTML report generator.
- Nandoshi KML parsing and geometry-domain utilities remain covered by tests.
- Four-pillar C1–C4 contract and fixed five-band concern convention are tested.
- Reference-relative benchmarking and geometric aggregation are tested.
- External CSV boolean parsing is tested so text/blank `reference_approved` fields cannot silently become True.
- eDNA template schema and C2/C3 placement are tested.
- Frozen legacy SHA-256 manifest checks remain passing.

## Earth Engine validation boundary

The package cannot authenticate the project user's Earth Engine account from this build environment. The following therefore require execution in the Colab notebook:

- automatic ecoregion resolution;
- automatic HydroLAKES candidate search;
- near-shore Human Modification screening;
- terrestrial reference sampling;
- Dynamic World/Sentinel-1 water detection;
- Sentinel-2 metric extraction;
- project-specific reference populations and benchmark values;
- end-to-end spatial rendering.

## Interpretation boundary

EO proxy metrics such as NDCI, red-band reflectance and FAI-based surface-bloom frequency remain proxy measures and should be validated against appropriate field observations before being treated as direct water-quality measurements. Broad shotgun-metagenomic taxonomic assignment counts are not treated as confirmed species richness; the eDNA layer distinguishes measured sequencing outputs from indicated pressure/condition signals and inferred functional potential.
