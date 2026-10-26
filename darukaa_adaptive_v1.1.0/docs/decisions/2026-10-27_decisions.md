# Decisions of 27 Oct 2026

Evidence: R2 run 3 and the Corbett Karpa run, both end-to-end Colab runs on live Earth Engine at commit 157d84b8 (`validation/R2b_Karpa_review_2026-10-26.md`), and desk research on 27 Oct (sources below).

## D-27-1. Canopy height: switch to Meta/WRI CHMv2 when it can be read like v1 (approved by Gaurav, 27 Oct)

**What CHMv2 is [ACAD].**
- Released 10 Mar 2026 by Meta and WRI. Built on DINOv3 and Maxar Vivid2 imagery (0.6 m), giving output at about 1.2 m.
- On the authors' SatLidar test set, R² rose from 0.53 to 0.86 and mean absolute error fell from 4.3 m to 3.0 m against v1 (arXiv 2603.06382).
- Licence CC BY 4.0 (AWS registry and Zenodo record 20628959).

**Limits.**
- **Imagery dates.** Single-date imagery, about 80% from 2018–2020 (paper, limitations). It cannot show change after 2020, so F-1 (the rule for disagreeing or out-of-date sources) is still needed.
- **Tall forests.** The authors report continued underestimation in very tall forests.
- **Not evaluated in the paper:** shrubs, leaf-off dry deciduous forest, and South Asia.
- **Not accessible:** the full *Scientific Data* article (s41597-026-07882-0) could not be opened.

**Access.**
- No public Earth Engine asset ID was found on 27 Oct. Pages checked: the Meta blog, the AWS registry, Zenodo and the GEE community catalogue (which lists v1 only).
- Meta and WRI run an Earth Engine viewer app (project `meta-forest-monitoring-okw37`), so an Earth Engine asset probably exists.

**Implemented (mechanical, this batch).**
- `layers.chm_source(options)` sets the canopy-height source.
  - The default stays v1 (`projects/sat-io/open-datasets/facebook/meta-canopy-height`, band `cover_code`).
  - CHMv2 is switched on by setting `chm_asset`, `chm_band` and `chm_label` together.
  - A partial setting raises an error; it never falls back to v1 silently.
- The source asset, band and label are recorded in each measurement's `period`.
- **Probe.** `probe.chmv2_search` lists the likely folders read-only and describes each candidate asset. The probe also measures each candidate beside v1 on the probe units, giving a histogram and mean (`chmv2_vs_v1`). Notebook section 4 has a `CHMV2_CANDIDATES` list for pasting an asset ID.

**Next.**
- If the probe finds a readable CHMv2 asset with a height band in metres, the default switches to it in a mechanical batch. That batch also updates the catalogue dataset and the metric catalogue.
- If no Earth Engine asset exists, the only route is importing AWS tiles per site. That is not "as easy as v1", so it will go back to Gaurav before any work.

**GLAD and GEDI** stay contextual, as independent cross-checks: Landsat plus GEDI lidar, and spaceborne lidar footprints.

## D-27-2. Headline presentation: option C (approved by Gaurav, 27 Oct)

The primary view is the pillar profile, not a single number:
- P1, P2 and P3 (with P3's coverage status), each with an interval and a confidence rating;
- P4 shown separately;
- the limiting pillar and metric named.

For sites with candidate gain, a restoration panel shows candidate gain by type, as gross figures and never netted.

Implementation is held until P-27-2 is decided, so that the report changes once.

## P-27-2. Overall State of Nature (SoN) score: proposal, awaiting approval

Gaurav asked for a single SoN score for when one is needed, such as investor screening, with option C still the primary view.

### Approaches compared

| # | Approach | Source type | How it combines | Fit |
|---|---|---|---|---|
| 1 | NatureMetrics Global Nature Risk | VENDOR | State of nature, dependencies and impact combined into one 0–1 *risk* score per asset. The formula and weights are not published on the product pages read (27 Oct). | It is a risk score, not a state score. It mixes state with exposure, which our rules keep apart. |
| 2 | NatureMetrics Ecosystem Condition Index (accredited by Accounting for Nature) | VENDOR | Three biological communities from eDNA combined into one site score. Aggregation not published in the source read. | eDNA-based (P3-type evidence); no usable formula. |
| 3 | Ecosystem Integrity Index (Hill et al. 2022) | ACAD | Minimum component × fuzzy sum of the other components | Strong limiting-factor logic. With two pillars it reduces to P1 × P2 / 100 and double-penalises (Karpa: 1.9 × 0.3 / 100 = 0.006). |
| 4 | UNDP HDI (since 2010); OECD/JRC Handbook on Constructing Composite Indicators (2008) | Method guidance (not a biodiversity standard) | Geometric mean with equal weights, chosen to limit substitution between dimensions. The handbook advises equal weights when there is no agreed basis for weighting, plus a sensitivity check. | Partly non-compensating; widely understood. |
| 5 | Nature Positive State of Nature indicators | STD | Defines no composite number. The indicators are "designed to be combined" as a holistic set and embedded *alongside* pressure metrics (Technical Output Report Box 7.1, p. 83; Initial Measurement Guidance App. A, p. 33). | Any single number is therefore a Darukaa construct and must be labelled as one. |

### Recommendation

**Definition.** SoN score = equal-weight geometric mean of the scored state pillars: P1 and P2, plus P3 once it is covered. This is the number the code already computes as the headline (D-23-10). The change is in its label and in the information that must travel with it.

**Withheld unless P1 and P2 are both scored.** Pressure is never included.

**Always shown with:**
- the pillar profile;
- the limiting pillar;
- a coverage label (for example "extent and condition only; species not covered");
- a confidence rating equal to the lowest confidence among the contributing pillars;
- the bootstrap 90% interval;
- the label "Darukaa composite, preparatory; not a Nature Positive standard metric".

**Sensitivity check.** The weakest-pillar score (option B) is printed beside it. When the two differ by more than 20 points, the report flags that the composite hides a weak pillar.

**Why the geometric mean.**
- A zero pillar gives zero.
- Imbalance is penalised, but less harshly than EII-style multiplication.
- Equal weights, because no standard gives pillar weights.

**A NatureMetrics-style "nature risk" view** would combine state with pressure and dependency. It should be a separate product, shown as a state-versus-pressure matrix rather than a merged number, because condition and pressure stay separate under our rules. Not part of this proposal.

## Sources (accessed 27 Oct 2026)

- [ACAD] Meta AI blog, "Mapping the World's Forests with Greater Precision: Introducing Canopy Height Maps v2": https://ai.meta.com/blog/world-resources-institute-dino-canopy-height-maps-v2/
- [ACAD] CHMv2 paper, arXiv 2603.06382: https://www.alphaxiv.org/abs/2603.06382
- [ACAD] CHMv2 in *Scientific Data*, s41597-026-07882-0 (not accessible): https://www.nature.com/articles/s41597-026-07882-0
- AWS Open Data registry, CHMv2: https://registry.opendata.aws/dataforgood-fb-forestsv2/
- Zenodo record 20628959: https://zenodo.org/records/20628959
- GEE community catalogue, Meta trees: https://gee-community-catalog.org/projects/meta_trees/
- [VENDOR] NatureMetrics Global Nature Risk: https://naturemetrics.com/products/global-nature-risk and https://naturemetrics.com/news/global-nature-risk-why-we-built-it
- [VENDOR] NatureMetrics Ecosystem Condition Index (8point9 article): https://8point9.com/ecosystem-condition-metric-provides-a-single-score-to-simplify-restoration/
- [STD] Nature Positive Initiative, State of Nature Technical Output Report, Box 7.1, p. 83; Initial Measurement Guidance v1, Appendix A, p. 33 (project files).
- Cited from prior knowledge and not re-read on 27 Oct: Hill et al. 2022 (EII), UNDP HDI technical notes, and the OECD/JRC 2008 Handbook on Constructing Composite Indicators.
