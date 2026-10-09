# Release validation — darukaa_adaptive_v1.1.0

## 2026-10-07 scoring-participation + zero-reference pressure fix

- Package version remains **1.1.0**.
- Valid metric records with status `calculated` are eligible for scoring when value, reference, QA and scoring-role gates pass.
- `built_fraction` now has an explicit zero-reference safeguard: if the approved reference median is exactly 0, the score uses the bounded native response `100 × (1 − built_fraction)` and records `comparison_method=bounded_absolute_zero_reference`.
- No change to reference-population selection, BII calculation, partial-SoN aggregation, or non-zero-reference pressure response functions.
- 69/69 tests passed.
- Python compilation passed.
- Colab notebook JSON/code-cell compilation passed (11 code cells).

## Recommended Git commit

`Fix scoring participation and zero-reference built fraction`


## 2026-10-09 scientific metric audit and correction

- Package version remains **1.1.0**.
- Active registry is reduced to **38 metrics**; the 62-metric historical inventory is preserved as a 63-row contract matrix including the added MSA candidate.
- 25 original metric IDs are removed from active registration; invalid constructs cannot be revived by score overrides. The retired calculators are not reachable from the active registry.
- `pdf` removed because the old fixed land-cover coefficients were not the published Potentially Disappeared Fraction method. MSA added as contextual only pending asset/model provenance verification.
- `habitat_health` retained; EII parent is now the default scored EII mode, with components contextual unless `eii_mode=components` is explicitly selected.
- FLII image extraction now uses only the canonical `projects/darukaa-earth-product/assets/flii_global_2019` raster; no reconstructed FLII proxy is used.
- Unsupported aquatic composites, mislabeled JRC/STAR/HDI constructs, generic flagship HSI, CERI, site-relative STSI, and NDVI-as-invasion proxy were removed or replaced by explicitly gated canonical-only inputs.
- LAI remains contextual at native ~500 m and is suppressed below four valid native pixels. CHM requests its native ~1 m analysis scale and reports that Earth Engine `bestEffort` may coarsen large geometries; actual scale is not fabricated.
- EII hierarchy regression tests, retirement tests, canonical FLII test, and MSA/STAR gate tests added.
- **74/74 tests passed.** Python package compilation passed. Colab notebook JSON and all 11 code cells compile.
- Live Earth Engine asset access/provenance was not tested in this local validation; MSA and STAR-T remain non-scored pending required source verification/configuration.

## Recommended Git commit

`Correct metric registry and enforce scientific source gates`


## 2026-10-09 project-report completeness and audit reconciliation

- Package version remains **1.1.0**.
- Project HTML report now presents project overview, condition and pressure separately, project pillar/metric summaries, EMU ecological comparison, concern-band distribution, evidence gaps, output-QA flags, and an EMU/reference index.
- Added `emu_condition_concern_distribution.csv`. Overall EMU condition bands are assigned only when P1/P2/P3 are all scored; partial and insufficient-evidence areas are reported separately. Existing concern thresholds are reused; no new cut-offs were introduced.
- Area-share denominator is summed EMU area and assumes non-overlapping EMUs; this is stated in the report.
- Project archive creation now occurs after the manifest is finalized, so the ZIP includes final output-QA and archive provenance. Post-render checks validate required files/sections and reconcile EMU counts, area totals and area-share percentages.
- Historical pre-repair metric lists in the scientific audit and migration guide are explicitly marked superseded; current active inventory remains 38 metrics and the contract matrix remains a historical 63-row audit crosswalk.
- **79/79 local tests passed**; Python package compilation passed. Report generation, output-bundle completeness and concern-distribution reconciliation are covered by regression tests.
- **Not validated in this local run:** live Earth Engine asset access, API quotas, real client input end-to-end execution, visual rendering across browsers, or ecological interpretation of any particular project result. These require the intended Colab run and analyst review.

### Recommended Git commit

`Complete project report and reconcile metric audit documentation`


## 2026-10-09 — runtime registry/Colab checkout hotfix

- Fixed the production `KeyError: Unknown indicator: natural_landcover_fraction`: the obsolete terrestrial aliases `natural_landcover_fraction` and `terrestrial_ndvi` are no longer emitted by the active terrestrial calculator. `built_fraction` remains the direct built-surface pressure metric; the canonical legacy `natural_habitat`/`ndvi` calculators remain governed by the active registry.
- Removed the active aquatic call to retired `red_reflectance_turbidity_proxy`; the uncalibrated metric was never in the v1.1.0 active registry and must not be emitted.
- Added a strict calculator/runtime registry contract before metric QA, reference benchmarking, scoring and report generation. A retired ID is suppressed and recorded; an unknown non-retired ID raises a clear contract error before downstream processing. Registry resolution and registration now explicitly reject retired identifiers.
- Fixed Colab git checkout semantics: a 40-character commit SHA is fetched and checked out detached with hash verification; branches/tags are checked out by name. A Git commit SHA must not be passed as `git clone --branch`. The notebook reports the resolved pinned commit.
- Added regression tests for the exact terrestrial no-observation error path, aquatic retired-metric emission, registry rejection, runtime contract order and SHA checkout logic.
- **85/85 local automated tests passed**; Python compilation passed; notebook JSON valid and all 11 code cells compile. A local disposable Git repository verified SHA checkout logic.
- **Not tested here:** live Colab execution, public GitHub network clone of the target ref, live Earth Engine permissions/assets/quotas, or real project EMU end-to-end output. Those remain explicit acceptance gates before client release.

### Recommended Git commit

`Fix retired metric runtime contract and commit-pinned Colab checkout`
