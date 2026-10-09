# Darukaa Adaptive Biodiversity Assessment — Methodology v1.1.0

## 1. Purpose

This framework produces a reproducible Year-0 biodiversity baseline from spatial project inputs and available Earth-observation, environmental, field, acoustic, eDNA and modelled evidence. It is designed for projects containing one or many Ecological Management Units (EMUs), including multipart or spatially scattered EMUs.

The framework is **reference-relative, evidence-aware and profile-driven**. A measurement is not automatically an ecological score: the indicator must be applicable, quality-controlled, scientifically interpretable, and supported by a defensible reference or threshold before entering a composite condition score.

## 2. Scientific basis

The architecture follows the established distinction between ecosystem extent, ecosystem condition and species/biodiversity state, while keeping anthropogenic pressure separate from condition. TNFD LEAP describes reference condition as the state against which ecosystem condition or another aspect of the state of nature is compared; the appropriate reference may be pristine/undisturbed in some contexts or a functional/resilient managed ecosystem in others. TNFD also does not prescribe a single universal condition metric. SEEA similarly requires condition variables to be transformed to a common measurement basis before aggregation and emphasizes transparent, scientifically justified indicator selection, reference levels, uncertainty and non-redundant metric sets.

These principles are implemented here as engineering rules rather than as claims that any one score is a universal ecological truth.

## 3. Assessment hierarchy

```text
Project
  └── EMUs
       ├── ecological/domain characterization
       ├── reference population
       ├── raw metrics + QA/QC
       ├── metric benchmark
       ├── normalized 0–100 attainment
       ├── subdimension aggregation
       ├── pillar aggregation
       └── EMU interpretation

Project aggregation
  ├── metric summaries
  ├── pillar summaries
  ├── project condition / pressure
  └── EMU ecological comparison
```

An EMU is the fundamental assessment unit. EMUs are never silently merged simply because they belong to the same project.

## 4. Pillars

### P1 — Ecosystem Extent & Configuration

Measures the amount and configuration of the relevant ecosystem/habitat domain. Examples include natural/semi-natural cover or aquatic extent where the ecological optimum is defined by a matched reference target.

### P2 — Ecosystem Condition

Measures abiotic, vegetation, hydrological, structural or functional characteristics of the ecosystem. Examples include vegetation greenness, water persistence and calibrated/un-calibrated optical proxies where a reference-relative interpretation is defensible.

### P3 — Biodiversity Integrity

Measures biodiversity evidence such as validated field, acoustic or eDNA observations when sampling effort, QA/QC and a defensible comparator are available.

### P4 — Anthropogenic Pressure

Measures human modification or pressure. Pressure is deliberately kept separate from P1–P3 and is combined with condition only in the management interpretation layer.

## 5. Indicator roles

Every indicator has a registry role:

- **SCORED** — eligible for reference-relative condition scoring when all gates pass.
- **CONTEXTUAL** — reported and interpreted but not collapsed into a condition composite.
- **PRESSURE** — contributes to P4, not to State-of-Nature condition.
- **DIAGNOSTIC** — QA/diagnostic evidence only.
- **PENDING** — registered but not yet sufficiently validated for production scoring.

A field-derived metric without a defensible reference/comparator remains baseline evidence rather than a Year-0 condition score. It becomes scoreable when an appropriate matched control, historical reference, published target or other defensible comparator is supplied and the registry requirements are met.

## 6. Reference framework

Reference construction is finite and explicit:

1. **Strict contemporary low-pressure reference**.
2. **Empirical least-disturbed contemporary reference** within the ecologically eligible population.
3. **Explicit manual HMI threshold** entered by the analyst after reviewing reference diagnostics, labelled `best_attainable` by default.
4. If all configured stages fail, the reference status is `candidate_rejected_reference_unavailable`.

Ecological eligibility is evaluated before HMI ranking. HMI is therefore a pressure screen, not a substitute for ecological comparability. No weighted ecological-match × HMI trade-off is used.

No manual reference KML/CSV pathway exists in the production workflow.

## 7. Reference distributions

A reference is a population/distribution, not merely one number. The engine retains sample size, central estimate, dispersion, percentiles and diagnostics. Raster pixels are not treated as independent ecological replicates. Bootstrap diagnostics are descriptive uncertainty diagnostics for the reference estimator, not pseudo-replication-based inferential claims.

## 8. Metric benchmarking

Metric-level benchmarking is chosen according to the indicator contract. The package retains the raw observation, reference value, relative departure and reference attainment. Where the reference distribution supplies sufficient dispersion statistics, standardized and robust z diagnostics are also retained. These diagnostics are **not** used as the client-facing composite score.

The common aggregation scale is 0–100 reference attainment:

- 100 = reference-like / target-like attainment under the configured response function;
- 0 = the lower bound of the configured attainment function;
- intermediate values = degree of attainment relative to the declared reference.

The response function is indicator-specific in principle. The current production registry uses transparent reference-relative functions; future calibrated response functions can be added through the registry without changing the reporting hierarchy.

## 9. Scoring hierarchy

### 9.1 Metric → subdimension

Complementary metrics measuring the same ecological subdimension are combined using a geometric mean on the common 0–100 scale. This reduces the ability of one very high metric to completely compensate for a very low metric while avoiding a hard minimum at the lowest hierarchy.

### 9.2 Subdimension → pillar

The pillar headline is the **limiting subdimension**. The pillar therefore answers two questions simultaneously:

- what is the strongest defensible pillar-level condition estimate; and
- which ecological subdimension is constraining that pillar?

The limiting metric is retained beneath the limiting subdimension for traceability.

### 9.3 Pillar → overall condition

P1, P2 and P3 are combined with a geometric mean when the configured condition-coverage gate is satisfied. The weakest pillar is always reported separately as the limiting pillar. P4 is not blended into this condition score.

## 10. Concern bands

The 0–100 concern labels are a product interpretation convention, not universal ecological thresholds:

| Score | Concern |
|---:|---|
| 80–100 | Very Low |
| 60–<80 | Low |
| 40–<60 | Moderate |
| 20–<40 | High |
| 0–<20 | Very High |

Where literature-anchored or ecosystem-specific thresholds become defensible, they should be added to the indicator contract rather than silently replacing the common product bands.

## 11. Pressure interpretation

P4 is scored on the same 0–100 attainment orientation: higher means lower relative anthropogenic pressure / better pressure condition. The pressure score is kept separate. The final interpretation uses a condition × pressure management matrix rather than a hidden condition-pressure weighted average.

## 12. Project aggregation

Project aggregation is performed **after** EMU assessment.

For a metric whose registry aggregation method is `area_weighted_mean`, the project value is the area-weighted mean across valid EMUs. For the common 0–100 condition score, the same area-weighted summary is used as the default project headline because the score is already normalized to a common scale and area represents the amount of project area represented by each EMU.

The project output always retains:

- number of EMUs represented;
- area coverage;
- mean and median;
- SD/MAD where meaningful;
- percentiles;
- minimum/maximum;
- limiting EMU;
- metric/pillar coverage.

Missing EMUs are not converted to zero.

## 13. EMU comparison

A project report contains a dedicated ecological comparison layer. It is not a second hidden index. It exposes EMU-level pillar scores, concerns, limiting metrics and score coverage so clients can identify spatial heterogeneity, outliers, stronger/weaker zones and management priorities.

Where appropriate, future releases may add multivariate ecological similarity analyses; such analyses must remain descriptive unless a validated inferential design is supplied.

## 14. Domain routing

The input contract supports:

- terrestrial;
- aquatic;
- mixed projects;
- single polygons;
- GeoJSON FeatureCollections;
- KML/KMZ;
- Site Selection handoff manifests and ZIPs.

Aquatic and terrestrial EMUs use domain-specific metric and reference profiles. Mixed projects do not force aquatic and terrestrial units into one ecological reference population.

## 15. Current core datasets

The production profiles use public, documented datasets where appropriate, including Dynamic World for 10 m land-cover probabilities/labels, RESOLVE Ecoregions 2017 for terrestrial biogeographic context, Sentinel-2 SR Harmonized for optical metrics, and TNC Global Human Modification v3 90 m for terrestrial human-modification pressure screening. Dataset choice is not equivalent to ecological validation: every proxy retains its provenance and limitations.

## 16. QA/QC and provenance

The assessment records:

- exact input SHA-256;
- Git commit when available;
- package version;
- configuration/profile;
- metric source and temporal window;
- metric QA/QC;
- reference candidate and approval diagnostics;
- benchmark method and uncertainty;
- scoring eligibility;
- project aggregation coverage.

A software execution failure is not interpreted as a biological finding. Reference rejection is a valid ecological outcome; an API/dataset/calculation failure is a release-blocking technical error.

## 17. Scope limitations

The framework does not claim that EO proxies directly measure biodiversity. It does not treat HMI as a complete ecological integrity measure. It does not infer species abundance from eDNA detection alone. It does not assign a condition score to field metrics lacking a defensible comparator. It does not treat raster pixels as independent ecological replicates. These distinctions are preserved in the output registry and report.


## Project-level reporting and aggregation

For multi-EMU projects, report the project headline together with EMU-level variation. Area-weighted project scores are descriptive summaries on the common 0–100 scale and do not replace EMU distributions, limiting indicators or reference diagnostics. Condition (P1–P3) and anthropogenic pressure (P4) remain separate.

The generated project HTML report includes project-level pillar and metric summaries, an EMU comparison, a condition concern-band distribution, explicit partial/insufficient evidence categories, automated output-QA flags, an EMU/reference index and a deliverables inventory. Overall EMU concern bands are assigned only when all three condition pillars are score-eligible; incomplete EMUs are not assigned a synthetic band or zero. The concern bands use the existing scoring thresholds. Area shares use the sum of EMU areas and assume non-overlapping EMUs; if overlap is present, area-share interpretation requires a validated non-overlapping area basis. Automated QA flags support review but do not certify ecological validity.
