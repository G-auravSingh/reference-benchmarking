# Pre-Colab metric coverage and spatial-area audit — 2026-10-11

## Scope and evidence

This memo uses (a) the previous live output archive from commit `aecad24068d57f73f45302a3cee63392070ddad2`, generated 2026-10-09, and (b) static inspection of the current v1.1.0 source and handoff. The new changes have been unit-tested offline but **have not yet been run in Earth Engine/Colab**. Therefore, the metric values below are evidence from the previous run, not claims that the repaired pipeline has re-produced them.

## Why the previous P1/P2/P3 scores were narrow

The previous output produced 27 terrestrial metric records from the active inventory, but only eight project-level metrics were actually scored: `natural_habitat`, `cpland`, `forest_loss_rate`, `chm`, `bii`, `built_fraction`, `ghm`, and `light_pollution`. P1 had three scored metrics; P2 had CHM only; P3 had BII only; P4 had three metrics. `score_all_scoreable_metrics=True` was configured, but this did not mean every metric was eligible in practice: the active registry and benchmark layer disagreed for several metrics, reference gates blocked some metrics, and some raster results lacked valid native-pixel support. The `min_valid_metrics_per_pillar` setting was also recorded but not enforced by the pillar aggregator.

## Current metric disposition after repair

- **Default-scored when calculation, native support and reference QA pass:** `natural_habitat`, `cpland`, `forest_loss_rate`, `ndvi`, `chm`, `bii`, `built_fraction`, `ghm`, `light_pollution`, and `flii` (FLII only with valid canonical-raster support and adequate valid pixels).
- **Contextual pending source/value QA:** `eii`, `eii_structural`, `eii_compositional`, `eii_functional`, `msa`, and `star_t`. The EII values in the previous run were anomalous and must not drive a headline score before the asset/path and scale are resolved. STAR-T is a conservation-opportunity metric and must not be synthesized from a Dynamic World/VIIRS proxy.
- **Contextual by design / redundancy or scale limitation:** `habitat_health` (NDVI-derived and redundant with NDVI by default), `lai` (coarse native scale and insufficient support for these small units), `aridity_index`, `lst_day`, `lst_night`, `shdi`, and other trend/composition indicators that lack a defensible cross-sectional scoring response.
- **Diagnostic, not presence evidence:** `kba_overlap`, `endemic_richness`, `endemic_plant_richness`, `threatened_richness`, and `threatened_plant_richness`. Range-map overlap/counts are not proof that taxa occur on the site.
- **Not applicable in terrestrial mode:** the 11 aquatic-module metrics. They should not be scored merely to inflate the metric count.

The repaired default still scores every metric that is both scientifically scoreable and validly measured. It does not force invalid, redundant, unsupported or non-applicable metrics into a headline.

## Specific previous-run values requiring checks

| Metric | Previous Deccan-forest observation | QA interpretation / action |
|---|---:|---|
| `natural_habitat` | 67.38% | Plausible as a land-cover fraction; check Dynamic World class grouping and temporal window. |
| `cpland` | 74.23% | Check connectivity metric definition, units and denominator; raw `%` must correspond to the documented landscape-configuration calculation. |
| `forest_loss_rate` | 0 ha/year | All nine EMUs received score 100 against a zero reference. Preserve the boundary-concentration QA flag; verify Hansen loss-year window and ≥30% canopy mask before release. |
| `ndvi` | 0.4503; reference median ~0.6111 | Previously blocked because it was interval-scale but the matrix said default-scored. Now scored with a direction-aware p05-to-median reference response, not an NDVI ratio. |
| `habitat_health` | 2.466; reference median ~4.471 | Retain as context by default because it is NDVI-derived and strongly redundant; do not count alongside NDVI unless a deliberate alternative-mode contract is added. |
| `flii` | 0 with 0 valid pixels | Invalid placeholder, not a valid ecological zero. Normalize to `no_valid_observation` and suppress from scoring/aggregation. |
| `eii` | ~0.000204; structural component ~0.000285; compositional ~0.450; functional ~0.489 | Inconsistent with expected parent/component relationship and previous cross-EMU anomaly. Keep all EII layers contextual until source path, band, scale, units and per-EMU variation are verified. |
| `bii` | ~0.442; reference ~0.817 | Numerically plausible as a 0–1 modelled intactness layer, but retain source/vintage, valid-pixel count and scale QA. BII is the active alternative while EII is unvalidated. |
| `chm` | ~0.759 m; reference ~4.845 m | Needs explicit plausibility review against the selected CanopyHeight asset, band, native scale, NoData and the mapped vegetation type. Do not assume it is correct solely because the pixel count is large. |
| `ghm` | ~0.598 with 3 valid pixels | Insufficient support for site-level score; mark `no_valid_observation` rather than score. |
| `light_pollution` | ~21.05 with 10 valid pixels | Keep only if the source band, scale and pixel support are confirmed; 10 is above the computational minimum but does not establish independent ecological replicates. |
| `built_fraction` | ~0.150; reference 0 | The 84.98 score uses an explicit bounded absolute response `100*(1-observed)` because a zero reference denominator is undefined. Confirm the built class mapping and whether this score is interpreted as pressure-intactness, not condition. |

## Area audit of the supplied handoff

The supplied `TataMotors_Pimpri_terrestrial_handoff.zip` contains nine EMU polygons and no independent project-boundary geometry/area. Reprojected to local UTM, their areas are: Deccan forest 40.088 ha; Narmada valley 9.245 ha; water margin 6.478 ha; wildlife 3.776 ha; grassland 2.802 ha; trail plots 2.033 ha; savana ecosystem 1.720 ha; seasonal wetland polygon 0.726 ha; wetland forest 0.472 ha. Their sum is **67.340 ha**. The geometries are mutually non-overlapping in the supplied handoff, so the union footprint is also approximately **67.340 ha**.

The Deccan-forest polygon alone is **40.088 ha**. Each of the other eight polygons lies outside that Deccan-forest polygon. Therefore, if 40.088 ha was intended to be the actual project boundary, the handoff includes eight EMUs outside that boundary and the run must not be interpreted as a 40.088-ha project assessment. If the intended project footprint is the union of all nine polygons, the current EMU footprint is 67.340 ha, but that still cannot be independently certified as the project boundary without the original site-selection boundary. The new report will label this as EMU footprint only and flag area reconciliation for review.

## Headline release gate now enforced

A pillar score requires at least **three valid scored metrics across three distinct subdimensions**. A condition headline requires all three condition pillars; P3 biodiversity evidence is required. These are configurable framework release gates, not universal ecological constants. Raw values, contextual indicators, QA and individual metric scores remain available even when a headline pillar or overall condition score is withheld. This avoids presenting a one-metric P2 or P3 as a broad ecological assessment.

## Offline verification completed

- 101 automated tests passed after the repairs.
- NDVI reference-distribution response tested, including interval-scale non-ratio semantics.
- Context-only EII/HHI and diagnostic metrics cannot be silently promoted by the global default.
- Zero/low pixel support is normalized before benchmarking/scoring.
- Project output records EMU sum, union footprint and missing project-boundary provenance separately.
- Canonical STAR-T raster gate replaces the non-canonical proxy implementation.

**Not yet verified:** fresh Earth Engine asset values, GEE reduction scales, reference distributions, and the new project output. Run Colab only after the original project boundary is supplied/reconciled; then audit the fresh output bundle before client release.
