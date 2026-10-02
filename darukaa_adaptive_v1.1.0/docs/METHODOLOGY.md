# Darukaa Adaptive Biodiversity Assessment Methodology

**Package:** `darukaa_adaptive_v1.1.0`  
**Status:** complete software/methodology build for live Earth Engine validation  
**Scope:** aquatic, terrestrial and mixed biodiversity baseline assessments

This is the **overall methodology document** for the package. `REFERENCE_CONDITION_METHODOLOGY.md` remains the detailed reference-condition standard, while this document covers the complete assessment pipeline: inputs, domains, metrics, QA/QC, references, scoring, evidence, reporting, provenance and release controls.

---

## 1. Purpose and design principles

Darukaa Adaptive is a profile-driven biodiversity assessment framework intended to turn a project boundary and available evidence into an auditable baseline.

The system is deliberately separated into:

1. spatial input and geometry QA;
2. ecological domain construction;
3. raw indicator measurement;
4. measurement QA/QC;
5. reference-condition construction;
6. reference QA and approval;
7. reference-relative benchmarking;
8. condition/pressure scoring;
9. readiness assessment;
10. report and provenance generation.

A valid measurement is not automatically a valid ecological score. A reference is not automatically valid merely because it is nearby or has low human modification. A remote-sensing proxy is not automatically a biological observation.

---

## 2. Input contract

### Required input

- One project boundary in KML or KMZ format.

The supplied boundary is treated as the **master assessment boundary**. It is not assumed to be a permanent water mask, habitat mask, or natural-ecosystem polygon.

### Optional inputs

- External/field/acoustic/eDNA evidence CSV.
- A project-specific Earth Engine configuration.
- An optional analyst-entered manual HMI threshold in the Colab, used only after both automatic contemporary reference stages fail.

The production workflow does **not** require or support uploading a reference KML/CSV.

The pipeline records the SHA-256 hash of the supplied site file in the assessment manifest.

---

## 3. Geometry QA and spatial domains

The site module:

- reads KML/KMZ polygons;
- strips unsupported Z coordinates;
- repairs invalid polygon geometry where possible;
- unions named polygon parts;
- computes area in a local UTM projection;
- records geometry bounds and input hash.

### Standard domains

For aquatic assessments the package creates:

- **master boundary:** supplied project geometry;
- **dynamic water domain:** derived independently for each analysis period;
- **fixed riparian ring:** external 100 m buffer in a local projected CRS;
- **context ring:** configurable 5 km analytical context;
- **reference search area:** separate configurable radius, default 25 km.

The reference-search radius is intentionally independent from the 5 km analytical context. The latter is a domain for contextual indicators; the former is a search space for comparable reference populations.

---

## 4. Temporal framework

The aquatic profile currently uses a configured Year-0 baseline of:

**1 August 2025 – 31 August 2026 inclusive.**

Earth Engine receives the exclusive end date `2026-09-01`.

The historical trend window is 2018–2026 by default and is used only for indicators that require multi-year temporal depth.

Future monitoring should use the same configured seasonal window shifted by complete years rather than arbitrary windows. Baseline and monitoring runs must retain the same metric definitions, spatial domains, sensor processing and configuration unless a documented methodology upgrade is being tested.

---

## 5. Aquatic water detection

### 5.1 Primary detector

Dynamic World is the primary source. The configured water probability threshold is 0.50 and at least three primary observations are required before the primary detector is used.

The primary dynamic-water mask is based on the mean Dynamic World `water` probability over the requested period.

### 5.2 Fallback detector

If primary optical coverage is insufficient and fallback is enabled, Sentinel-1 VV is used with the configured backscatter threshold and majority-observation rule.

Every result records the method actually used. The fallback is not silently represented as Dynamic World output.

### 5.3 Water extent

Water extent is reported as water area divided by the fixed master boundary area.

It is a **monitoring quantity**, not a universal higher-is-better condition score. A lake's expected water footprint depends on hydrology, seasonality, geomorphology and the reference state.

### 5.4 Water persistence

Water persistence is the spatial mean of per-pixel water occurrence over the configured analysis window. Spatial percentile diagnostics are retained where available.

Reference pixels are not treated as independent statistical replicates merely because they are numerous.

---

## 6. Aquatic indicator suite

The default lake profile includes:

| Indicator | Pillar | Interpretation |
|---|---|---|
| `water_extent` | C1 | Dynamic water footprint; reference-target metric |
| `water_persistence` | C1 | Water occurrence; reference-target metric |
| `ndci_proxy` | C1 | Water-masked optical chlorophyll/trophic proxy |
| `red_reflectance_turbidity_proxy` | C1 | Water-masked red-reflectance proxy |
| `surface_algal_bloom_frequency` | C1 | FAI threshold-exceedance frequency proxy |
| `riparian_ndvi` | C2 | Standardized riparian vegetation greenness proxy |
| `riparian_ndvi_sen_slope` | C2 | Descriptive multi-year trend; not automatically scored |
| `shoreline_disturbance_fraction` | C4 | Land-cover pressure proxy in the fixed riparian ring |

NDCI, red reflectance and FAI are **proxies**. They must not be described as calibrated chlorophyll concentration, laboratory turbidity, or confirmed harmful algal blooms without independent validation.

---

## 7. Dynamic land-cover interpretation

Dynamic World modal labels are used as a temporal land-cover **comparability/composition layer** where configured.

A modal Dynamic World class composition is not equivalent to a mean thresholded water extent. The report and methodology therefore keep these concepts separate.

The package does not infer that a Dynamic World class is naturally occurring simply because it has low human modification.

---

## 8. Reference-condition framework

The default automated reference state is:

`least_disturbed_contemporary`

This means a contemporary population selected to be ecologically comparable while passing explicit pressure and QA screens. It does **not** mean pristine, pre-human, or ecologically optimal by definition.

Supported reference states are:

- `undisturbed_minimally_disturbed`
- `least_disturbed_contemporary`
- `historical`
- `best_attainable`
- `paired_control`
- `published_target`

The detailed standard is in `docs/REFERENCE_CONDITION_METHODOLOGY.md`.

---

## 8A. Finite reference escalation and manual HMI fallback

Reference selection is deliberately finite. The production pipeline does not keep widening the search radius or relaxing ecological criteria until a reference is obtained. There are exactly three contemporary selection stages:

### Stage A — strict low-pressure contemporary

The engine first requires the ecologically/hydrologically comparable candidate population to satisfy the configured strict HMI screen (`HMI <= 0.05` by default), together with all population, temporal, spatial and ecological QA gates. If approved, this population becomes the reference.

### Stage B — least-disturbed contemporary

If Stage A cannot produce an approved population, the engine evaluates the same comparable candidate population and identifies its lower-disturbance tail. The default is the lowest 10% HMI quantile. This is a **least-disturbed contemporary** reference, not a pristine or minimally disturbed reference. The quantile is configurable and is not silently changed by the pipeline.

### Stage C — manual HMI-threshold fallback

If Stage B also fails, the Colab exposes `MANUAL_REFERENCE_HMI_THRESHOLD`. This is a single HMI threshold entered explicitly by the analyst after reviewing the reported pre-pressure HMI distribution, quantiles and threshold-retention diagnostics. The threshold is therefore a documented analyst decision, not an automatic relaxation.

The manual threshold must remain within `[0,1]` and still passes the normal candidate area, pixel, ecological, temporal and spatial QA gates. The resulting reference is labelled `best_attainable` by default and records the exact manual threshold and the preceding automatic results in the manifest.

If Stage C is not configured or fails QA, the process terminates with `candidate_rejected_reference_unavailable`. There is no fourth automatic stage and no manual KML/CSV upload mechanism.

This architecture prevents an assessment from manufacturing a reference merely because scoring requires one. It also provides a practical route for highly modified landscapes where a strict low-pressure reference does not exist.

## 9. Automatic aquatic reference selection

The aquatic search uses a configurable 25 km annulus by default and excludes the assessed site itself.

Candidate construction uses:

1. water occurrence/hydroperiod similarity to the focal site;
2. minimum water occurrence;
3. dominant RESOLVE 2017 ecoregion compatibility as a surrounding biogeographic stratum;
4. low human-modification screening in surrounding land context;
5. minimum candidate area and pixel population;
6. adequate observation depth.

### HMI implementation

The TNC Global Human Modification v3 90 m static snapshot is an **Earth Engine ImageCollection**, even though it represents a static 2022 product. The package therefore loads it as an ImageCollection and derives the configured band from the collection rather than treating the asset as a single Image.

For aquatic references, HMI is not interpreted as a water-quality variable. It is sampled through a focal land-context mean around candidate water pixels and used only as a pressure screen.

### Ecoregion implementation

RESOLVE Ecoregions 2017 is a terrestrial biogeographic FeatureCollection. For aquatic sites it is used as a surrounding landscape/ecological comparability stratum, not as a lake typology.

A future higher-tier aquatic reference method should add explicit lake typology where the assessment question requires it, for example hydrological regime, geomorphic setting, trophic class or other validated lake-type variables.

---

## 10. Automatic terrestrial reference selection

The terrestrial reference engine uses:

- dominant RESOLVE ecoregion;
- Dynamic World modal land-cover class as a comparability stratum;
- TNC Global Human Modification v3 90 m low-pressure screening;
- minimum candidate population requirements;
- the same QA approval contract.

The land-cover class is a matching stratum, not evidence that a candidate is natural.

The current terrestrial reference engine is intentionally a baseline automated screen. It does not claim that climate, soil, elevation, potential natural vegetation, disturbance history and ecological community composition are fully matched. These variables should be added where the assessment requires higher ecological specificity.

---

## 11. Reference QA gates

Automatic approval requires all configured gates to pass:

### Gate A — population adequacy

- minimum candidate area;
- minimum candidate pixel count.

### Gate B — ecological match

- configured ecological similarity score meets the minimum.

### Gate C — pressure screen

- candidate population passes the configured HMI screen.

### Gate D — temporal compatibility

- sufficient observations are available for the reference comparison window.

### Gate E — spatial quality

- the ecological search stratum resolves successfully.

`auto_approve=True` means only that automated approval is permitted **after all gates pass**. It is not a bypass.

Execution errors are different from valid candidate rejection. The final Colab validation notebook explicitly treats reference-engine execution errors as release-blocking.

---

## 12. Reference population and uncertainty

The framework treats a reference as a population/distribution rather than a single number.

Where spatial metric distributions are available, the system retains:

- valid-pixel count;
- mean;
- standard deviation;
- P05/P10/P25/P50/P75/P90/P95;
- median as the default central reference estimator.

A spatial standard-error proxy may be retained for diagnostics, but it must not be described as a formal confidence interval for independent replicates because spatial autocorrelation reduces effective sample size.

Bootstrap functions in `reference_condition.py` are provided for non-spatial arrays and explicitly document this limitation.

---

## 13. Reference-relative benchmarking

Benchmarking is direction-aware.

### Higher is better

`relative departure = (observed - reference) / |reference|`

### Lower is better

`relative departure = (reference - observed) / |reference|`

### Reference target

`relative departure = -|observed - reference| / |reference|`

Positive departure means directionally better than the reference for monotonic indicators. Negative departure means directionally worse. Reference-target indicators are interpreted as distance from the target rather than monotonic improvement.

The legacy `intactness_score_0_100` field is retained for compatibility. The production term is **reference attainment**.

---

## 14. Reference attainment

The current 0–100 attainment mapping is a bounded product display convention:

- 100 means the observed value meets or exceeds the selected reference for a higher-is-better metric;
- 100 means the observed value is at or below the selected reference for a lower-is-better metric;
- reference-target metrics receive a bounded distance-from-target value.

A score of 100 does **not** mean perfect ecology, maximum biodiversity, or ecological integrity.

Metric-specific response functions are architecturally supported as a future scientific upgrade and must be validated before replacing the generic display mapping for a metric.

---

## 15. Scoring architecture

The package uses four common pillars:

- **C1 Extent**
- **C2 Vegetation**
- **C3 Fauna**
- **C4 Pressure**

C4 is structurally separate from condition.

### Indicator scoring eligibility

An indicator is score-eligible only when:

1. the measurement is usable;
2. the indicator is referenceable;
3. a comparable reference exists;
4. the reference is approved for scoring;
5. direction/target semantics are defined;
6. the evidence and proxy limitations support the intended use.

### Pillar aggregation

Scored indicators within a pillar are aggregated using the configured geometric mean.

### Overall condition

Condition combines C1, C2 and C3 only when the configured minimum coverage is met. The aquatic profile currently requires a scored C3 Fauna pillar before overall condition can be scored.

This prevents an EO-only assessment with no fauna evidence from presenting a complete condition score.

### Pressure

C4 is reported independently and is never silently mixed into condition.

### Concern bands

The fixed Darukaa display convention is:

| Score | Concern label |
|---:|---|
| 0–<20 | Very High |
| 20–<40 | High |
| 40–<60 | Moderate |
| 60–<80 | Low |
| 80–100 | Very Low |

These are product bands, not universal ecological risk thresholds.

---

## 16. Biological and external evidence

Field, acoustic, eDNA and modelled observations can enter through the external evidence contract.

Each observation must retain:

- metric name;
- pillar;
- raw value;
- units where applicable;
- direction;
- reference value;
- reference approval status;
- evidence type;
- status/notes.

The package does not invent biological evidence when it is absent.

An eDNA persistence-potential proxy is contextual unless the project has a defensible reference and validation pathway for converting it into an ecological score.

---

## 17. QA/QC and readiness

Measurement QA is separate from ecological interpretation.

The QA layer checks items such as:

- missing/non-finite values;
- metric status;
- valid observations/pixels;
- temporal adequacy;
- score eligibility;
- reference availability and approval.

Readiness summarizes:

- geometry readiness;
- temporal baseline configuration;
- historical coverage;
- metric coverage;
- reference readiness;
- evidence availability;
- condition/pressure scoring status.

Readiness is not an ecological condition score.

---

## 18. Provenance and reproducibility

Every production run should retain:

- exact Git commit;
- package version;
- profile version;
- complete configuration;
- input KML/KMZ SHA-256;
- Earth Engine project;
- metric dataset names;
- temporal windows;
- metric statuses;
- reference method/state/approval basis;
- reference diagnostics;
- score eligibility;
- report and machine-readable scorecards.

The Nandoshi notebook clones the requested Git ref into a clean Colab directory, installs only the current package, verifies the import path/version, records the exact commit and exports it through `DARUKAA_GIT_COMMIT` so the assessment manifest retains the release identity.

---

## 19. Output contract

A complete assessment output directory should contain, as applicable:

- `metric_scorecard.csv`
- `metric_qa_scorecard.csv`
- `reference_governance.csv`
- `benchmark_scorecard.csv`
- `metric_concern_scorecard.csv`
- `pillar_scorecard.csv`
- `overall_scorecard.json`
- `readiness.json`
- `assessment_manifest.json`
- `water_periods.csv`
- `water_monthly.csv` for the Nandoshi notebook
- `landcover_composition.csv` where applicable
- `external_evidence.csv`
- `indicator_registry.csv`
- `legacy_metric_crosswalk.csv`
- `Year0_Biodiversity_Baseline_Report.html`
- `README_OUTPUTS.md`

---

## 20. Report interpretation rules

The report must distinguish:

- measured value;
- reference value;
- reference state;
- reference approval;
- reference-relative departure;
- reference attainment;
- concern band;
- data/coverage limitations.

A missing pillar must be shown as **Not assessed**, not as 100.

A missing reference must be shown as unavailable/not approved, not replaced by a fabricated universal target.

A contextual proxy must not be rewritten as a direct biological observation.

---

## 21. Dataset governance

Dataset upgrades must be checked for:

- asset type and band names;
- spatial resolution;
- temporal availability;
- preprocessing assumptions;
- changes in algorithm/product version;
- comparability with historical runs;
- citation/licensing requirements.

The current TNC HM v3 static 90 m product is documented as a 2022 snapshot and an ImageCollection in Earth Engine. It should not be silently mixed with the change-consistent series as though they were the same quantitative product.

RESOLVE Ecoregions 2017 is a terrestrial ecoregion framework and should not be described as an aquatic lake typology.

---

## 22. Scientific limitations

The current automated framework does not claim to solve, universally:

- lake typology;
- trophic-state calibration;
- species population size;
- eDNA persistence;
- biodiversity integrity from NDVI alone;
- independent statistical replication of raster pixels;
- historical pristine-state reconstruction;
- metric-specific ecological response functions.

These require ecosystem-specific evidence, field validation, historical data, or validated models where the assessment question demands them.

---

## 23. External methodological basis

The methodology is informed by:

- TNFD LEAP/reference-condition principles;
- UN SEEA ecosystem accounting concepts;
- Nature Positive Initiative State of Nature Metrics;
- reference-condition and least-disturbed-site ecology literature;
- ecological restoration reference-ecosystem principles;
- habitat-condition approaches such as Natural England's Biodiversity Metric;
- Google Earth Engine dataset documentation for the actual EO assets used.

The external frameworks are evolving. Darukaa maintains an explicit internal methodology contract and should re-audit external standards and datasets at major methodology releases.

---

## 24. Release rule

A package can pass software tests and still fail scientific/live validation.

Before a client result is issued, the target Earth Engine project must demonstrate:

1. all configured datasets resolve;
2. water detection runs;
3. the reference engine runs without execution errors;
4. the candidate/reference diagnostics are populated;
5. legitimate reference rejection is distinguished from software failure;
6. benchmark values are produced only where reference governance permits them;
7. C3 gating behaves as configured;
8. report and manifest agree with machine-readable outputs;
9. exact Git commit and input hash are retained.

This live acceptance step is part of the release process, not an optional afterthought.

