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

**CHMv2 source found by Gaurav (27 Oct).** The public AWS bucket is `s3://dataforgood-fb-data/forests/v2/global/dinov3_global_chm_v2_ml3/`. Its layout, from the Meta and WRI notebook `facebookresearch/dinov3/notebooks/chmv2_dataset_exploration.ipynb` (read in full, 27 Oct):

- `chm/<quadkey>.tif`: cloud-optimised GeoTIFFs. Each covers one zoom-level-10 Web Mercator tile and is 32,768 × 32,768 pixels, `uint8`, in metres, EPSG:3857. The GeoTIFF mask band flags cloud in the input imagery.
- `metadata/`: GeoJSON polygons per tile, each carrying the observation date of the input imagery.
- `tiles.geojson`: the extent and quadkey of every tile.
- No Earth Engine asset is named in the notebook.

I could not check tile sizes from here, because the session proxy blocks S3.

**The integration problem.** Earth Engine reads cloud-optimised GeoTIFFs only from Google Cloud Storage (`gs://`), not from S3. Reading CHMv2 "like v1" therefore needs one of:

- **(a)** an Earth Engine asset published by Meta and WRI. The probe lists their folder.
- **(b)** copying the tiles that cover the sites and the reference search area (z10 tiles are about 35 km across at 20–30° N, so about 9 tiles for a 25 km ring and up to about 49 for 100 km) to a Darukaa Cloud Storage bucket, then reading them with `ee.Image.loadGeoTIFF`. This keeps one Earth Engine code path for sites, EMUs and reference samples.
- **(c)** reading the tiles in Colab outside Earth Engine. That is a second code path, needs the natural mask pulled to the client, and is not recommended.

Order: run the probe first, then (b) if a bucket is available.

**GLAD and GEDI** stay contextual, as independent cross-checks: Landsat plus GEDI lidar, and spaceborne lidar footprints.

## D-27-2. Headline presentation: option C (approved by Gaurav, 27 Oct)

The primary view is the pillar profile, not a single number:
- P1, P2 and P3 (with P3's coverage status), each with an interval and a confidence rating;
- P4 shown separately;
- the limiting pillar and metric named.

For sites with candidate gain, a restoration panel shows candidate gain by type, as gross figures and never netted.

Implemented together with D-27-3 (see below).

## D-27-3 (was P-27-2). Overall State of Nature (SoN) score: approved by Gaurav, 27 Oct; implemented

Gaurav asked for a single SoN score for when one is needed, such as investor screening, with option C still the primary view.

### Approaches compared

| # | Approach | Source type | How it combines | Fit |
|---|---|---|---|---|
| 1 | NatureMetrics Global Nature Risk | VENDOR | State of nature, dependencies and impact combined into one 0–1 *risk* score per asset. The formula and weights are not published on the product pages read (27 Oct). | It is a risk score, not a state score. It mixes state with exposure, which our rules keep apart. |
| 2 | NatureMetrics Ecosystem Condition Index (accredited by Accounting for Nature) | VENDOR | Three biological communities from eDNA combined into one site score. Aggregation not published in the source read. | eDNA-based (P3-type evidence); no usable formula. |
| 3 | Ecosystem Integrity Index (Hill et al. 2022) | ACAD | Minimum component × fuzzy sum of the other components | Strong limiting-factor logic. With two pillars it reduces to P1 × P2 / 100 and double-penalises (Karpa: 1.9 × 0.3 / 100 = 0.006). |
| 4 | UNDP HDI (since 2010); OECD/JRC Handbook on Constructing Composite Indicators (2008) | Method guidance (not a biodiversity standard) | Geometric mean with equal weights, chosen to limit substitution between dimensions. The handbook advises equal weights when there is no agreed basis for weighting, plus a sensitivity check. | Partly non-compensating; widely understood. |
| 5 | Nature Positive State of Nature indicators | STD | Defines no composite number. The indicators are "designed to be combined" as a holistic set and embedded *alongside* pressure metrics (Technical Output Report Box 7.1, p. 83; Initial Measurement Guidance App. A, p. 33). | Any single number is therefore a Darukaa construct and must be labelled as one. |

### Adopted (approved 27 Oct)

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

### Implementation (27 Oct, offline tests and mocks only)

- `scorecard.headline` returns:
  - the SoN score, interval and status;
  - the weakest pillar, with its score and limiting metric;
  - the lowest pillar confidence (a pillar's confidence is the confidence of the metric that sets it; unknown if any is missing, never assumed High);
  - the coverage label;
  - the divergence flag (more than 20 points);
  - the pressure confidence;
  - the label.
- The project roll-up (`project["son"]`) carries the same companions. Each pillar also records its confidence and limiting metrics.
- Report order:
  1. Nature Positive coverage;
  2. the state of nature profile (P1, P2, P3 tiles, then P4 separately);
  3. restoration and change (gross loss and candidate gross gain by type, never netted, partial totals labelled);
  4. the SoN composite as a secondary figure;
  5. the site headline table.
- Gross loss is split by 2020 type (ForTy natural forest or other natural) and by replacement (cropland or built-up). Candidate gain is split by Dynamic World class. New table: `restoration_and_change.csv`.
- Field renames:
  - `condition_*` becomes `son_*`.
  - `R2_expected.json` keys become `son_status` and `son_status_not`. The expectations themselves are unchanged.

## P-27-4. Canopy height at changing or young sites (F-1): proposal, awaiting approval

Evidence: Karpa run 2 and the probe of 27 Oct (`validation/R2b_Karpa_review_2026-10-26.md`, "Run 2").

There are two different problems:
- **Source error.** On the small forest, Meta v1 reads 4.8 m against GLAD's 14.6 m.
- **Stale epoch.** At Karpa, every source agrees on about 0 m for 2018–2020, but Dynamic World now labels the land woody.

### Options compared

| Option | Rule | Small forest | Karpa | Weakness |
|---|---|---|---|---|
| A | `source_disagreement` when independent sources over the same natural pixels differ by more than 50% (GLAD where it has at least 4 px, GEDI where it has at least 10 footprints) | not scored | still 0.3 | Misses the stale-epoch case |
| B | Epoch check. Canopy height is scored only on natural pixels whose Dynamic World mode in the source epoch (2018–2020) was already the same woody class. Pixels that became woody later are excluded and reported in ha. If support falls below the minimum, the status is `source_predates_state`. | unchanged | depends on 2018–2020 labels: not scored if the woody cover is newer; kept (as real low structure) if it was already woody | Adds a Dynamic World 2018–2020 composite |
| C | Score canopy height only on ForTy 2020 natural forest; contextual on woodland and shrub | unchanged | not scored. P2 then has 2 components and is withheld under the 3-component gate. | Drops structure for all non-forest natural types |

### Recommendation

**A and B together.** A catches source error and B catches stale epochs. Both are explicit statuses, never a zero, and the excluded area is reported.

C is not recommended: it removes structure for savanna, woodland and shrub types everywhere, not only where the data is stale.

CHMv2 (via a Cloud Storage bucket) would reduce A cases but not B: its imagery is also mostly 2018–2020.

## Sources (accessed 27 Oct 2026)

- [ACAD] Meta AI blog, "Mapping the World's Forests with Greater Precision: Introducing Canopy Height Maps v2": https://ai.meta.com/blog/world-resources-institute-dino-canopy-height-maps-v2/
- [ACAD] CHMv2 paper, arXiv 2603.06382: https://www.alphaxiv.org/abs/2603.06382
- [ACAD] CHMv2 in *Scientific Data*, s41597-026-07882-0 (not accessible): https://www.nature.com/articles/s41597-026-07882-0
- AWS Open Data registry, CHMv2: https://registry.opendata.aws/dataforgood-fb-forestsv2/
- Zenodo record 20628959: https://zenodo.org/records/20628959
- Meta and WRI CHMv2 dataset notebook: https://github.com/facebookresearch/dinov3/blob/main/notebooks/chmv2_dataset_exploration.ipynb
- GEE community catalogue, Meta trees: https://gee-community-catalog.org/projects/meta_trees/
- [VENDOR] NatureMetrics Global Nature Risk: https://naturemetrics.com/products/global-nature-risk and https://naturemetrics.com/news/global-nature-risk-why-we-built-it
- [VENDOR] NatureMetrics Ecosystem Condition Index (8point9 article): https://8point9.com/ecosystem-condition-metric-provides-a-single-score-to-simplify-restoration/
- [STD] Nature Positive Initiative, State of Nature Technical Output Report, Box 7.1, p. 83; Initial Measurement Guidance v1, Appendix A, p. 33 (project files).
- Cited from prior knowledge and not re-read on 27 Oct: Hill et al. 2022 (EII), UNDP HDI technical notes, and the OECD/JRC 2008 Handbook on Constructing Composite Indicators.
