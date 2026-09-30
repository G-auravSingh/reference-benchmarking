# Audit of `darukaa_reference_v0.1.0`

## Audit objective

The adaptive framework was built only after a source-level review of the supplied legacy reference package. The legacy package is retained unchanged under `legacy/darukaa_reference_v0.1.0/`.

The review covered the package modules, registry, indicator implementations, reference-selection implementation, configuration, statistics, report generation, site loading, and the supplied legacy notebook.

## Legacy strengths retained conceptually

The legacy pipeline has a coherent high-level structure: site geometry ingestion → indicator extraction → Tier-1/Tier-2 reference comparison → report generation. It also has a useful indicator registry and captures indicator metadata. Those components are valuable for a terrestrial benchmark architecture.

## Findings that justify an adaptive extension

1. **Tier-1 reference zone is centroid-buffer based.** The legacy reference implementation does not implement the described ecoregion-overlap concept as a direct spatial mask.
2. **Tier-2 documentation and implementation diverge.** Same-land-cover, elevation-stratified and low-HMI documentation is not consistently realized in the implementation.
3. **Configuration is not consistently authoritative.** Several reference-selection parameters appear in configuration without consistently controlling all implementation paths.
4. **GEE pixel arrays are not retained by the legacy reduction helper.** This limits downstream pixel-distribution statistics for GEE-derived values.
5. **Report pillar summaries can depend disproportionately on Tier-2-populated indicators.** This can omit valid site metrics from the summary layer.
6. **Aquatic calculations are not consistently separated from the fixed project geometry.** A lake workflow needs a dynamic water domain plus fixed riparian/context domains.
7. **The legacy WSDI formulation is non-monotonic.** It peaks around 50% occurrence and therefore does not behave like a universal ecological-condition score.
8. **Riparian trend documentation and implementation are not fully aligned.** The adaptive implementation uses explicit Theil–Sen slope and Kendall significance.
9. **JRC Global Surface Water v1.4 is historical.** It is not treated as a current-data source in the adaptive profile.
10. **Several named aquatic metrics are heuristic proxies.** They require calibration before being presented as direct measurements of biological processes.
11. **Range-overlap species metrics do not confirm local occurrence.** The adaptive framework therefore treats analogous biodiversity screening as contextual rather than inventing local species records.
12. **Several legacy indicators are terrestrial/forest-oriented.** A profile system is required to prevent inappropriate metric application.
13. **Composite scoring needs evidence gates.** Missing/invalid indicators should not silently change the composite composition.
14. **The supplied Nandoshi workflow was partly implemented outside the legacy package.** Reproducibility therefore requires an explicit adaptive package + notebook + manifest workflow.

## Adaptive response in v1.1.0

The adaptive package now separates:

- explicit date-driven Year-0 baseline from historical trend/context;
- fixed master boundary from dynamic water, fixed riparian and context domains;
- metric extraction from benchmark construction;
- Tier-1 external reference from Tier-2 candidate/context reference;
- raw metric values from concern scoring;
- metric scoring from pillar aggregation;
- pillar aggregation from overall composite eligibility;
- measurement readiness from ecological/field validation readiness.

The native aquatic registry controls applicability, reference eligibility and scoring disposition. The 44-indicator legacy crosswalk remains available as a governance/selection table and does not activate the legacy terrestrial implementation.

## Deliberate non-goals

The adaptive package does not create field biodiversity observations from Earth observation, does not call a proxy a calibrated water-quality concentration, and does not invent universal aquatic concern thresholds. It also does not modify the frozen legacy implementation.
