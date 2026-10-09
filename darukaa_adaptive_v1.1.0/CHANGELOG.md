## 1.1.0 — scientific metric correction (2026-10-09)

- Reduced the active metric registry from the historical 62-item inventory to a smaller accepted set; invalid and misleading metrics are removed from runtime registration rather than merely downgraded.
- Retired the ad hoc land-cover-weighted `pdf` proxy; it was not the published Potentially Disappeared Fraction metric. Added an MSA candidate layer using the existing 2015 raster reference, explicitly contextual until source/model provenance is verified.
- Removed unsupported aquatic composites and mislabeled proxies (`tspi`, `wcpi`, `wsdi`, `hsas`, `edpp`, `mspl`, `rci`, and misnamed Sentinel-1 `jrc_water_persistence`). Retained published/defensible aquatic EO signals only where their interpretation is explicit; uncalibrated NDCI and FAI-frequency products are contextual, not scored.
- Removed invalid context-only constructs (`stsi`, `iri`, `ivsi`), generic unvalidated flagship HSI, non-canonical STAR-T proxy, CERI composite, Map of Life placeholder, duplicate land-cover/NDVI aliases, and temporally asymmetric net-tree-change proxy.
- Retained `habitat_health` and made the published EII parent the default scored EII mode; EII components are contextual unless `eii_mode=components` is explicitly selected. Parent and components remain mutually exclusive.
- FLII extraction now uses only the supplied canonical raster `projects/darukaa-earth-product/assets/flii_global_2019`; the previous local P/Q/LFC reconstruction is no longer used by the active image builder.
- LAI remains a contextual MODIS product at its native ~500 m resolution and now requires at least four valid native-scale pixels for a spatially representative value. It is not resampled to imply finer detail.
- Added `docs/METRIC_CONTRACT_MATRIX.csv` covering the historical 62-metric inventory plus the MSA candidate, including dispositions, evidence gaps, support rules and limitations.
- Package version remains `1.1.0`; no version bump.

## 2026-10-07 — scoring participation + zero-reference pressure fix

- Valid metric records with status `calculated` are now eligible for scoring when their value, reference, QA and scoring-role gates pass; previously only `ok`/`usable` records could enter the scorecard.
- Added a metric-specific zero-reference safeguard for `built_fraction`: when the approved reference median is exactly 0, the ratio response is undefined and no longer collapses every positive built fraction to 0. The bounded native response `100 × (1 − built_fraction)` is used and labelled `bounded_absolute_zero_reference`.
- No change to reference-population selection, BII methodology, P1–P3 aggregation, or the underlying non-zero-reference pressure response functions.


## 2026-10-06 — v1.1.0 runtime hotfix

- Fixed `indicator_table(config)` report call compatibility so the per-EMU indicator registry can receive runtime temporal-period metadata.
- No scoring, reference-selection, partial-SoN, or pressure-intactness semantics changed in this hotfix.


## v1.1.0 — partial condition coverage + pressure-intactness semantics (2026-10-06)

- Condition/State-of-Nature headline scoring now uses all score-eligible P1–P3 condition pillars available for the assessment; missing pillars are excluded rather than assigned zero.
- Results are explicitly labelled `condition_scored_partial` when fewer than 3 condition pillars are available, with `condition_pillar_count` and `condition_coverage` retained in the output.
- The default condition gate no longer requires P3 fauna/biodiversity evidence; P3 remains a distinct biodiversity-integrity pillar and its absence is reported as an evidence gap. An explicit fauna gate remains configurable for profiles that require it.
- P4 headline output is now exposed as `pressure_intactness_score_0_to_100`, making the direction explicit: higher values indicate lower pressure / better condition. The prior `pressure_score_0_to_100` field remains as a backward-compatible alias.
- The underlying P4 metric/reference scoring formula was not changed in this release; boundary-saturated pressure results remain subject to QA review.

## v1.1.0 — live-output audit hardening (2026-10-06)
- Added runtime population of `temporal_period` in the registry using the configured assessment/trend window; the static registry remains date-agnostic.
- Added automatic project-level output QA (`project_output_qa.json`) for condition coverage, extreme pressure scores, and boundary-concentrated metric scores.
- Added automatic creation of a self-contained `<project_id>_assessment_outputs.zip` outside the output directory and automatic Colab download at the end of the main run cell.
- Added the project archive and post-run QA record to the project manifest.
# Changelog

## v1.1.0 — Scientific metric audit and EII hierarchy gate — 2026-10-05

- Added an explicit EII hierarchy gate: parent EII and its three components are mutually exclusive in headline scoring.
- Default `eii_mode="components"` scores structural, compositional and functional EII components while retaining parent EII as diagnostic/contextual.
- Added `eii_mode="parent"` and `"none"` alternatives; metric overrides cannot bypass the hierarchy gate.
- Corrected adaptive registry provenance for EII (~300 m), independent BII v1.1 (100 m), and Meta/WRI CHM (~1 m primary with ETH 10 m fallback).
- Preserved the independent Impact Observatory/Vizzuality BII source with no EII-derived fallback.
- Added regression tests for EII exclusivity, override hard-gating, source contracts and complete 46-metric inventory.
- Clarified that the active v1.1.0 reference engine does not use the legacy 5,000-pixel sampling/retry ladder; those settings remain only in the vendored historical calculator/reference module.

## 2026-10-03 — Site Selection handoff compatibility hardening

- Added native ingestion of the Site Selection `tile_manifest.json` contract using `tile_paths` and `tile_labels`.
- Rebased absolute Site Selection tile paths safely when a handoff is transferred as a ZIP.
- Added explicit ambiguity/missing-tile failures rather than silently selecting files.
- Added regression tests for both direct manifests and zipped handoffs.

## v1.1.0 — Generalized EMU architecture

- Added canonical project/EMU input model.
- Added Site Selection handoff contract and handoff validation.
- Added ZIP, GeoJSON, FeatureCollection, KML/KMZ and single-geometry ingestion paths.
- Added per-EMU domain routing for terrestrial, aquatic and mixed projects.
- Added project-level coverage-aware metric and pillar aggregation while retaining EMU-level outputs.
- Added extensible indicator registry API for future EO, field, acoustic, camera-trap, eDNA and model-derived indicators.
- Added generalized production Colab notebook.
- Added formal EMU/handoff and metric-extensibility methodology documents.
- Retained finite reference-condition policy: ecological eligibility is a gate; HMI orders eligible candidates and does not compensate for ecological mismatch.
- No manual KML/CSV reference fallback was introduced.
- Existing Nandoshi aquatic workflow remains available as a historical validation path during transition.


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
- Replaced manual reference-file fallback with a finite analyst-entered HMI-threshold fallback in Colab.

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

### Reference escalation hardening
- Added governed least-disturbed contemporary fallback using a configurable lower HMI quantile after strict minimally-disturbed screening fails.
- Added terminal explicit manual HMI-threshold reference fallback without reference-file uploads.
- Added HMI distribution and threshold-sensitivity diagnostics and retained the strict HMI threshold unchanged.
- Corrected diagnostic naming/handling so candidate pixel counts are not presented as a fixed 10 m count when Earth Engine uses best-effort reduction.

## v1.1.0 — Generalised reference-selection contract

- Generalised reference selection into a realm-agnostic finite decision policy.
- Separated ecological eligibility from disturbance ordering.
- Removed the production use of a weighted/aggregate ecological-match score as a trade-off against HMI.
- Aquatic candidates are now defined by hard ecological eligibility (ecoregion + water-occurrence regime), followed by HMI screening.
- Terrestrial candidates now use the same finite strict → least-disturbed quantile → manual-HMI decision structure.
- Mixed assessments retain separate aquatic and terrestrial reference populations.
- Reduced production-run HMI diagnostics to one distribution calculation per reference stage; removed the expensive multi-threshold area sweep from the live pipeline.
- Added unit tests for the finite reference-selection policy.


## 2026-10-09 — Project reporting and output-bundle completeness (v1.1.0; version unchanged)

- Expanded the project HTML report with summed EMU area, EMU count, condition coverage, existing concern-band distribution, explicit partial/insufficient-evidence categories, output-QA flags, and an EMU/reference output index.
- Added `emu_condition_concern_distribution.csv`; overall EMU concern bands require all three condition pillars and use existing scoring thresholds.
- Kept anthropogenic pressure separate from ecosystem condition and documented the non-overlap assumption behind area shares.
- Added regression tests for distribution counts/area shares, complete EMU inventory, required report sections and output-bundle integrity checks.
- Corrected archive sequencing so the downloaded ZIP contains the final manifest including output-QA state and archive path.
- Reconciled historical metric audit/migration documentation so pre-repair metric inventories are explicitly labelled historical and cannot be mistaken for the current active registry.
- Local validation: 76 tests passed; Python package compilation passed. Live Earth Engine execution and client-specific output remain to be validated in Colab.
