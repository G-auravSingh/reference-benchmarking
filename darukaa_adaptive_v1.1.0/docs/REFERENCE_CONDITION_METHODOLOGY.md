# Darukaa Reference-Condition Methodology

**Methodology status:** Production framework, v1.1 reference-condition architecture (R4, 2026-10-01)  
**Applies to:** `darukaa_adaptive_v1.1.0` and future compatible releases  
**Owner:** Darukaa.Earth Biodiversity Methodology  
**Primary purpose:** Define how Darukaa establishes an ecological reference condition, validates it, compares site observations with it, and prevents an arbitrary spatial comparison from becoming an ecological score.

---

## 1. Executive methodological position

Darukaa does **not** define ecological condition as "the site divided by the nearest good-looking pixel" and does not equate a low-pressure contemporary landscape with a pristine ecosystem by default.

A **reference condition** is the ecological state against which the observed state is compared. The appropriate reference depends on ecosystem type, assessment purpose, spatial context, temporal context and the question being answered. TNFD explicitly describes reference conditions as potentially pristine/undisturbed, functional/resilient managed, historical or otherwise appropriate to the environmental context. The UN SEEA ecosystem-accounting framework likewise distinguishes several reference-condition options for natural and anthropogenic ecosystems. The scientific literature also recognises contemporary least-disturbed reference states as a legitimate alternative when historical states are uncertain or unattainable.

For Darukaa, the default scalable approach is therefore:

> **ecologically matched + spatially explicit + low anthropogenic pressure + temporally compatible + statistically adequate reference population**

The result is a **reference population**, not a single pixel and not automatically a claim of pristine condition.

The reference architecture is deliberately independent of individual indicator formulas. An indicator dataset can change from Sentinel-2 to a newer product, from one canopy-height product to another, or from one water algorithm to another without changing the reference-condition contract.

---

## 2. Why a reference condition is necessary

A raw environmental measurement has little decision meaning without context.

For example:

- NDVI = 0.42 is not intrinsically good or bad.
- Built fraction = 0.12 is not intrinsically good or bad.
- Water persistence = 0.55 cannot be interpreted without knowing the natural hydrological regime.
- Turbidity proxy = 0.08 cannot be treated as a biodiversity condition metric without a validated response relationship.

The assessment therefore separates:

1. **Observed metric** — what the EO/field/model dataset measured.
2. **Reference condition** — what an ecologically comparable reference population represents.
3. **Reference-relative departure** — how the observation differs from the reference.
4. **Reference attainment** — a bounded product representation used only where the metric is eligible for scoring.
5. **Ecological interpretation** — what the departure means, including uncertainty and metric limitations.
6. **Trend** — whether the site is changing over time.

These are not interchangeable concepts.

---

## 3. Reference-state taxonomy

Every benchmark must declare a reference-state type.

| Reference state | Definition | Typical use |
|---|---|---|
| `undisturbed_minimally_disturbed` | Natural ecosystem with minimal anthropogenic disturbance and high ecological integrity | Natural forests, natural lakes, intact wetlands |
| `least_disturbed_contemporary` | Best currently available ecologically comparable condition after objective disturbance screening | Default automated reference |
| `historical` | A documented historical ecological state | Reliable historical imagery, inventories, palaeoecology |
| `best_attainable` | Ecologically appropriate state that can realistically be achieved under current constraints | Heavily modified ecosystems where historical restoration is not realistic |
| `paired_control` | Matched control/reference site selected for a specific intervention | BACI/restoration monitoring |
| `published_target` | A scientifically or regulatorily established threshold/target | Metrics with validated thresholds |

### 3.1 Default automated state

The production default is:

**`least_disturbed_contemporary`**

This wording is intentional. It does **not** say "pristine". It means the algorithm searches for currently existing, ecologically comparable areas subject to an explicit low-pressure screen.

Where a genuinely undisturbed/minimally disturbed reference can be demonstrated, the reference state can be promoted to `undisturbed_minimally_disturbed` with appropriate evidence.

---

## 4. Reference selection principles

A candidate reference population must satisfy four scientific principles.

### 4.1 Ecological comparability

The candidate must represent the same ecological system or a sufficiently close analogue.

Depending on realm, matching variables can include:

- ecosystem/habitat class;
- ecoregion;
- hydrological regime;
- climate;
- elevation/topography;
- soil/geology where ecologically relevant;
- land-cover/habitat structure;
- season/phenological window;
- disturbance regime.

The required variables are **metric- and ecosystem-specific**. The engine must not force the same covariate set on every ecosystem.

### 4.2 Low anthropogenic pressure

A low-pressure screen is used to identify contemporary candidates that are less affected by anthropogenic modification.

For terrestrial reference construction, the production engine uses the TNC Global Human Modification v3 90 m 2022 surface (`TNC/HM/v3/90m_s`, band `All_threats_combined`) as the default cumulative-pressure screen. The Earth Engine asset is an `ImageCollection`; the configured band is derived from that collection.

For aquatic reference construction, HMI is used only through a focal mean of surrounding land-context pixels around candidate water. It is not interpreted as a water-quality or direct lake-condition variable.

The HM surface is a pressure proxy, not a direct biodiversity-condition measurement. It therefore cannot by itself establish reference condition.

### 4.3 Temporal compatibility

Reference data must represent a compatible temporal regime.

Examples:

- seasonal vegetation metrics should compare the same seasonal window;
- lake hydroperiod should compare equivalent hydrological periods;
- annual vegetation metrics should use comparable annual composites;
- a 2025 observation should not silently be benchmarked against an unrelated 2015 ecological state unless the reference is explicitly historical.

### 4.4 Statistical adequacy

A reference population must be large and stable enough to support the intended comparison.

At minimum, the pipeline records:

- candidate area;
- candidate pixel count;
- central estimate (median by default);
- dispersion;
- MAD;
- percentile range;
- bootstrap uncertainty where values are available;
- reference QA status.

Spatial pixels are not treated as fully independent replicates. Bootstrap uncertainty is therefore descriptive uncertainty around the sampled reference statistic, not a formal independent-pixel confidence interval.

---

## 5. Spatial reference architecture

The automated reference search is deliberately broader than the site's immediate analytical context.

### 5.1 Search geometry

The production default uses a **25 km search radius** around the assessment boundary, configurable by profile.

This is distinct from the 5 km landscape/context buffer used for some site metrics.

Reason:

> The immediate surroundings of a project may themselves be degraded and therefore unsuitable as a reference population.

A broader search provides the opportunity to find an ecological analogue rather than simply the nearest available land.

### 5.2 Exclusion of the assessed site

The master assessment boundary is excluded from the automatically constructed reference population.

This prevents the site from becoming its own reference.

### 5.3 Ecoregion matching

The reference search is intersected with the site's RESOLVE 2017 ecoregion geometry where available.

If an ecoregion cannot be resolved, the pipeline does not silently claim that ecoregional matching occurred. The diagnostic records the limitation and the automated approval gate can reject the candidate.

### 5.4 Fragmentation and patch quality

Reference pixels should not be interpreted as one ecological patch simply because they share a raster mask. Future releases should retain patch-level diagnostics where patch-sensitive metrics require them.

For configuration/intactness metrics, the reference unit should be an ecosystem patch/landscape population rather than independent raster pixels.

---

## 6. Aquatic reference construction

Aquatic systems require a different reference logic from terrestrial vegetation.

### 6.1 Why terrestrial logic cannot simply be copied

A lake's natural condition is not represented by:

- maximum water area;
- 100% water cover;
- low NDVI around the lake;
- nearby low-HMI land alone.

Natural lakes and wetlands have characteristic hydroperiods, water extent dynamics, seasonal variability and catchment contexts.

### 6.2 Production aquatic candidate

The aquatic engine constructs a candidate population using:

1. a 25 km reference search zone;
2. exclusion of the assessment boundary;
3. RESOLVE ecoregion compatibility;
4. Dynamic Water / water-occurrence information from the same baseline window;
5. a minimum water-occurrence requirement;
6. tolerance around the focal site's water-occurrence regime;
7. low anthropogenic-pressure screening using HM in the surrounding land context;
8. minimum candidate area and pixel requirements.

The water-occurrence similarity is a **hydrological comparability filter**, not a claim that every qualifying pixel is the same lake type.

### 6.3 Aquatic limitation

The current automated aquatic reference is a strong spatial screening framework but is not equivalent to a field-confirmed natural lake typology.

Where lake type, trophic state, geomorphology or hydrological class materially changes the ecological meaning of a metric, the profile should add a corresponding classification variable before that metric is promoted to scored status.

### 6.4 Water extent

Water extent is not automatically benchmarked as:

`observed water area / 100% = condition`

Instead, it is treated as a **reference-target / hydrological dynamics** construct. A natural lake can occupy substantially less than its maximum mapped footprint during part of the year.

---

## 7. Terrestrial reference construction

The production terrestrial candidate uses:

1. the 25 km reference search zone;
2. RESOLVE ecoregion matching;
3. Dynamic World modal land-cover class as a contemporary habitat stratum;
4. the same habitat class as the focal site where technically appropriate;
5. a low HM pressure screen;
6. candidate area and pixel thresholds;
7. explicit QA before scoring.

### 7.1 Important interpretation

Dynamic World class is a **comparability stratum**, not proof of naturalness.

For example, "trees" does not prove old-growth forest, native composition, absence of grazing or ecological integrity.

Where a metric is sensitive to these distinctions, additional covariates should be introduced rather than treating the land-cover class as sufficient.

---

## 8. Reference QA and automated approval

Candidate construction and candidate approval are separate operations.

The production gate evaluates:

### Gate A — population adequacy

- candidate area ≥ configured minimum;
- candidate pixels ≥ configured minimum.

### Gate B — ecological match

- ecosystem/habitat compatibility;
- ecoregion compatibility;
- hydrological similarity for aquatic metrics where required;
- configured ecological match score ≥ threshold.

### Gate C — pressure screen

- low-pressure criterion passes;
- candidate is not simply a high-quality-looking pixel surrounded by severe pressure where the surrounding context matters.

### Gate D — temporal compatibility

- sufficient observations;
- compatible assessment period;
- no silent use of future or unrelated periods.

### Gate E — spatial quality

- reference geometry is valid;
- candidate is distinct from the site;
- required ecological region can be resolved.

Only after these gates pass may `auto_approve=true` authorize automatic approval.

**`auto_approve` is therefore not a bypass.** It is a permission to approve a candidate that has already passed the automated QA gate.

---

## 9. Reference distribution rather than a single number

The pipeline retains the reference distribution concept even when the median is used for the default comparison.

For every metric where the underlying sample is available, the reference summary should contain:

- `n`;
- mean;
- median;
- standard deviation;
- MAD;
- P05/P10;
- P25;
- P50;
- P75/P90;
- P95;
- descriptive uncertainty where a valid bootstrap sample is available.

The median (`P50`) is the default central estimator because environmental distributions are often skewed and can contain extreme values. For live raster reference populations, the stored spatial percentiles are not treated as independent-replicate confidence intervals.

### 9.1 Why the median is not the whole answer

Consider two reference populations with the same median:

```text
Reference A: 0.50–0.55
Reference B: 0.25–0.80
```

An observation of 0.48 is close to A's reference population but sits near the low tail of B.

Therefore the client report should eventually expose both:

- central reference;
- reference distribution / uncertainty.

---

## 10. Reference-relative departure

For a directional metric:

### Higher is better

`departure = (observed - reference) / |reference|`

### Lower is better

`departure = (reference - observed) / |reference|`

### Reference target

`departure = -|observed - reference| / |reference|`

Positive values mean directionally better than the reference; negative values mean worse.

This is a **descriptive comparison**, not a biodiversity measurement.

---

## 11. Reference attainment versus intactness

The legacy field `intactness_score_0_100` is retained for compatibility with previous outputs.

It should no longer be interpreted as a universal ecological measure of intactness.

The production concept is:

> **Reference attainment (0–100)**

The current default display convention remains bounded at 100 because a site exceeding the selected contemporary reference should not automatically be described as "more than 100% intact" or "perfect".

This is intentionally conservative.

A future metric-specific response-function layer can replace the generic attainment mapping when there is sufficient ecological evidence.

---

## 12. Landscape intactness is a separate construct

Darukaa reserves **landscape intactness** for spatial configuration concepts such as:

- ecosystem extent remaining;
- patch configuration;
- fragmentation;
- core area;
- connectivity;
- functional connectivity;
- distance to ecosystem collapse where a validated framework exists.

A site/reference ratio for NDVI, turbidity, canopy height or another condition variable should not be called landscape intactness.

This distinction aligns with the emerging State of Nature Metrics framing, which separates ecosystem extent, ecosystem condition and landscape intactness.

---

## 13. Metric-specific scoring rule

The reference engine does **not** make every metric scoreable.

An indicator can enter the condition composite only when all of the following hold:

1. measurement is valid;
2. ecological meaning is established;
3. the metric is referenceable;
4. a comparable reference is available;
5. the reference passes the approval gate;
6. the metric has a defensible direction/target;
7. uncertainty is documented;
8. the metric is not merely a screening/context proxy.

### 13.1 Uncalibrated proxies

Spectral indices that correlate with ecological properties are not automatically equivalent to field measurements.

For example:

- NDCI is a chlorophyll/trophic proxy;
- red reflectance is a water-quality proxy;
- FAI-based bloom frequency is a bloom proxy.

They should not be represented as calibrated chlorophyll, turbidity or biodiversity condition without validation.

A metric may therefore remain visible in the report while being excluded from the ecological condition composite.

---

## 14. Reference uncertainty

Reference uncertainty and observation uncertainty are distinct.

### Observation uncertainty

Examples:

- cloud contamination;
- sparse Sentinel-2 observations;
- fallback sensor use;
- small-site resolution;
- classifier uncertainty.

### Reference uncertainty

Examples:

- small reference population;
- spatial heterogeneity;
- unstable reference median;
- ecological mismatch;
- sensitivity to reference-search radius;
- sensitivity to pressure threshold.

Both should be retained in the manifest and report.

---

## 15. Sensitivity analysis requirement

Reference conditions should not be accepted merely because one parameterization passes.

The production roadmap therefore requires sensitivity testing for:

- search radius;
- pressure threshold;
- ecological-match tolerance;
- minimum candidate size;
- temporal window.

If small parameter changes produce large changes in the reference, the reference should receive lower confidence or be rejected for scoring.

---

## 16. Manual references

Manual reference KML/CSV uploads are intentionally **not supported in the production workflow**. The finite manual fallback is an HMI threshold entered in Colab after reviewing the automatic diagnostics.

The manual HMI fallback should document:

- the exact HMI threshold entered;
- the HMI distribution used to justify it;
- the strict threshold and least-disturbed quantile that were already attempted;
- the resulting candidate area/pixel population;
- the analyst rationale for treating the threshold as a best-attainable contemporary reference.

## 17. Dataset upgrade policy

Metric datasets will change over time. The reference framework therefore treats datasets as versioned dependencies rather than permanent truths.

Every metric must retain:

- dataset identifier;
- dataset version/date where available;
- native resolution;
- processing formula/version;
- temporal window;
- masking rules;
- reference method;
- reference-state type.

A dataset replacement must trigger:

1. formula review;
2. unit/range review;
3. resolution review;
4. temporal coverage review;
5. reference compatibility review;
6. regression tests;
7. methodology changelog entry;
8. release version bump where outputs can change.

Historical results must remain reproducible through pinned release versions.

---

## 18. External methodological basis

The architecture is informed by, but is not presented as a literal implementation of, any single reporting framework.

Primary references include:

1. **TNFD LEAP Approach** — reference condition and baseline concepts, including context-dependent reference states.
2. **UN SEEA Ecosystem Accounting** — ecosystem condition and reference-condition options.
3. **Nature Positive Initiative State of Nature Metrics** — distinction among ecosystem extent, ecosystem condition, landscape intactness and species metrics; tiered maturity approach.
4. **SBTN freshwater/nature guidance** — location-specific state-of-nature measurement and pressure/state separation.
5. **Natural England Biodiversity Metric** — habitat-specific ecological optimum/condition assessment as an example of why generic cross-habitat raw thresholds are inappropriate.
6. **Jakobsson et al. (2020)** — conceptual framework for contemporary and historical reference states.
7. **Stoddard et al. / reference-condition literature** — least-disturbed reference approaches where true pristine sites are unavailable.
8. **Theobald et al. (2025)** — Global Human Modification v3 as a contemporary cumulative anthropogenic-pressure surface.

References should be rechecked during each major methodology release because external frameworks and datasets are actively evolving.

---

## 19. What the method does NOT claim

Darukaa does not claim that:

- the nearest low-HM pixel is pristine;
- a protected area is automatically a reference;
- low human modification proves biodiversity integrity;
- NDVI is biodiversity;
- a reference-relative ratio is landscape intactness;
- a 100/100 reference-attainment value means ecological perfection;
- a global EO reference replaces field validation where field validation is necessary;
- all ecosystems can share one reference-search radius;
- all metrics can share one scoring response function.

These limitations are methodological guardrails, not optional wording.

---

## 20. Production output contract

Every production assessment should expose, at minimum:

```text
Observed value
Reference value
Reference state
Reference method
Reference sample size
Reference QA status
Reference approval basis
Reference uncertainty
Relative departure
Reference attainment (if scoreable)
Interpretation status
```

This contract is intentionally stable even when the underlying metric implementation changes.

---

## 21. Future extensions

The architecture is designed to support, without redesigning the downstream scoring API:

- ecosystem typology from IUCN Global Ecosystem Typology;
- climate/topography matching;
- soil/geology matching;
- hydrological class matching;
- protected-area and management-history evidence;
- patch-level independence controls;
- Mahalanobis / propensity-score ecological matching;
- spatial block bootstrap;
- metric-specific response functions;
- historical/pre-intensification reference reconstruction;
- paired-control/BACI references;
- validated field reference populations;
- ecosystem-specific distance-to-collapse models.

The reference engine should therefore be treated as a **versioned scientific subsystem**, not as a helper function inside a metric script.

## Finite Reference Escalation (v1.1.0)

The adaptive engine does not relax reference criteria indefinitely. It follows a fixed sequence:

1. **Strict minimally-disturbed contemporary** — configured HMI threshold (default 0.05) plus ecological, hydrological, temporal and population QA.
2. **Least-disturbed contemporary** — if Tier A has no approved population, select the configured lowest-disturbance quantile of the same ecologically/hydrologically comparable candidate population (default 10%). This is explicitly *not* labelled pristine or minimally disturbed.
3. **Manual HMI-threshold fallback** — if Stage B fails, the analyst may enter a defensible HMI threshold in Colab based on the reported HMI distribution. The same QA gates remain mandatory.
4. **Terminal state** — if no manual threshold is configured or it fails QA, the result is `candidate_rejected_reference_unavailable`. The pipeline does not keep widening the search or relaxing thresholds automatically.

The least-disturbed quantile is a governed selection rule, not a claim that the selected population is natural. Raster HMI observations are treated as spatial evidence; they are not counted as independent ecological replicates.

---

## 15. Generalised reference-selection contract (v1.1.0)

The reference engine is **realm-agnostic at the decision level**. Aquatic, terrestrial and mixed assessments use the same finite decision contract; only the ecological eligibility profile changes.

### 15.1 Two different jobs — never one trade-off score

The engine explicitly separates:

**Ecological eligibility** — does the candidate belong to the same ecological reference population?

**Disturbance ordering** — among ecologically eligible candidates, which currently available areas are least modified?

HMI answers the second question. It does **not** compensate for failure of the first.

The production engine therefore does **not** select a reference using a weighted formula such as:

`ecological similarity × HMI preference`

and does not repeatedly add new criteria until one candidate wins.

### 15.2 Universal decision sequence

```text
Assessment site
      ↓
Define ecosystem/domain-specific eligible population
      ↓
Apply mandatory ecological + temporal + spatial + population QA
      ↓
Within that eligible population, screen/order by HMI
      ↓
Stage 1: strict low-pressure
      ↓ if no approval
Stage 2: empirical least-disturbed HMI quantile
      ↓ if no approval
Stage 3: one explicitly configured HMI threshold
      ↓
Approved reference OR reference unavailable
```

This is a **finite decision tree**, not an iterative optimisation process.

### 15.3 Aquatic ecological profile

For the current lake implementation, ecological eligibility is defined by:

- RESOLVE ecoregion compatibility;
- a minimum water-occurrence requirement; and
- pixel-level compatibility with the focal site's water-occurrence regime within the configured tolerance.

The candidate population is then filtered by HMI. The aggregate water-occurrence value is retained as a diagnostic, but it is **not converted into an arbitrary 0–1 ecological match score for trading against HMI**.

### 15.4 Terrestrial ecological profile

For the current terrestrial implementation, ecological eligibility is defined by:

- RESOLVE ecoregion compatibility; and
- a contemporary Dynamic World habitat stratum matching the focal site's modal class.

The land-cover class is a **comparability stratum**, not evidence that the candidate is natural or intact. HMI then orders the eligible contemporary population by disturbance.

Future forest/grassland/shrubland profiles may add scientifically justified structural, climatic, topographic or habitat variables without changing the decision contract.

### 15.5 Mixed assessments

A mixed assessment does not force aquatic and terrestrial pixels into one reference population. It constructs **separate domain-specific reference populations** and passes them to the relevant metric groups.

This is important for sites containing, for example, forest + grassland + wetland or water + terrestrial margins. The reference engine therefore remains general without pretending that all ecosystem components share one ecological reference state.

### 15.6 What constitutes the endpoint

The algorithm is considered complete when it can do one of two things without analyst rescue:

1. produce an approved reference population satisfying all fixed gates; or
2. return `reference_unavailable` with a documented reason.

The engine must not be modified simply because one test site fails to produce a reference. A failure at one site is an ecological result unless it exposes a software error or a demonstrably incorrect general rule.
