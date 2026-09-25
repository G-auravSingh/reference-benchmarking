# Audit of `darukaa_reference_v0.1.0`

## Audit objective

The new adaptive framework was built only after a source-level review of the supplied legacy reference package. The legacy package is retained unchanged under `legacy/darukaa_reference_v0.1.0/`.

The review covered the package modules, registry, indicator implementations, reference-selection implementation, configuration, statistics, report generation, site loading, and the supplied `notebooks/run_pipeline.ipynb`.

## What the legacy package does well

The legacy pipeline has a coherent high-level structure: site geometry ingestion → indicator extraction → Tier-1/Tier-2 reference comparison → report generation. It also has a useful indicator registry and captures indicator metadata. The site loader supports several common geospatial formats. Those components are useful as a legacy-compatible terrestrial benchmark.

## Findings that justify an adaptive extension

1. **Tier-1 reference zone is centroid-buffer based.** `reference.py` builds the reference region from `site_geometry.centroid().buffer(...)`; it is not an ecoregion-overlap mask.

2. **Tier-2 documentation and implementation diverge.** Tier-2 documentation describes same-land-cover, elevation-stratified, low-HMI reference selection, but the implementation uses a centroid buffer and does not apply the resolved ecoregion geometry. The Tier-2 land-cover reference is the 100 m Copernicus Proba-V 2019 product.

3. **Configuration is not consistently authoritative.** The config contains `hmi_percentile_threshold`, while the reference implementation uses fixed percentile logic; the hard HMI ceiling has also appeared with inconsistent 0.05/0.10 documentation/defaults across the package/notebook.

4. **GEE pixel arrays are not retained.** The central `_reduce()` helper returns `"pixels": None`. Consequently, the statistical comparison layer cannot generally compute its pixel-level Hedges' g / bootstrap / permutation quantities for GEE-derived indicators.

5. **Report pillar summaries use Tier-2 only.** The report summary is therefore incomplete for indicators without Tier-2 eligibility, even when a site value exists.

6. **Several aquatic calculations use a broad geometry without a dynamic water domain.** Examples in `indicators/__init__.py` include NDCI/TSPI, FAI/SABF, and other water-related composites. A lake assessment should distinguish the fixed master boundary, dynamic water surface, exposed littoral/lakebed, fixed riparian context, and broader reference context.

7. **The old WSDI is not a generic stability score.** It is defined as `1 - 2*abs(occurrence - 0.5)`, which peaks when water occurrence is approximately 0.5. This is a hydrological-dynamics statistic, not a monotonic ecological-condition index.

8. **Riparian NDVI method mismatch.** The report/annexure references Sen's slope/Mann-Kendall, whereas the supplied implementation uses a two-year `linearFit()` slope.

9. **JRC water history is time-bounded.** JRC Global Surface Water v1.4 covers 1984–2021. The legacy implementation's configurable end date is not inherently constrained to that availability period, so a request extending beyond 2021 can return no valid data or an Earth Engine error.

10. **Some reported aquatic metrics are heuristic proxies.** EDPP, MSPL, IRI, and HSAS combine remote-sensing proxies using fixed weights. They should not be presented as direct measurements of eDNA persistence, microbial stress probability, invasive risk, or species habitat viability without validation/calibration.

11. **Species range-overlap metrics are not occurrence observations.** The endemic/threatened richness and CERI implementations count or weight species whose mapped ranges overlap the site. This is useful conservation-context screening but does not confirm local presence or population status.

12. **Some metrics are intrinsically terrestrial/forest-oriented.** FLII, flagship habitat viability, LAI/CHM and several terrestrial condition measures are not automatically appropriate inside an aquatic master boundary.

13. **Composite scoring has insufficient data-sufficiency gating.** The notebook averages populated concern classes; missing/invalid indicators can change the composition without a formal minimum evidence rule.

14. **The supplied Nandoshi notebook was materially different from the package.** It adds project-type, trajectory, scoring, and species-list logic outside the legacy package and clones GitHub `main` without pinning a commit, so the entire report workflow is not reproducible from the package archive alone.

## Why the new pipeline exists

The conclusion is not that every legacy calculation is unusable. Rather, the audit shows that the legacy implementation is a terrestrial/reference-benchmark prototype with documented limitations and that its aquatic implementation is not a sufficiently explicit, domain-aware, temporally consistent lake workflow.

The adaptive framework therefore **does not overwrite the legacy package**. It introduces explicit spatial-domain handling, dynamic EO-derived water detection, aquatic-specific metrics, temporal sufficiency checks, provenance, baseline/monitoring comparison, and conservative score eligibility. The legacy package remains available unchanged for reproducibility of prior terrestrial work.
