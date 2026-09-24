# Pipeline Methodology — References

> **Aug 2026 note:** this file is inherited from
> `Darukaa_SiteSelectionPipeline_v6.0/code/PIPELINE_METHODOLOGY_REFERENCES.md`
> unchanged below this note — every citation in it still applies directly,
> since this pipeline reuses the same GEE script (SNIC segmentation, CRITIC
> weighting is now also used for candidate ranking here, same dataset
> citations). New citations/decisions specific to THIS pipeline (not in
> v6.0) are appended in §6 at the end, rather than rewriting the sections
> below — they were independently verified in the original build and
> deserve to stay attributed to that work, not silently absorbed.


This document consolidates every citable methodological decision in the v6.x
pipeline in one place, so a client, auditor, or peer reviewer doesn't have
to hunt through in-code comments to find the evidentiary basis for a design
choice. Every entry below was checked against a live source during this
build (web search, the source's own documentation page, or direct testing
against real project data) — none are asserted from memory alone. Where a
citation's bibliographic detail (exact author list, volume/page number)
wasn't independently confirmed during this build, that's stated explicitly
rather than presented with false precision.

---

## 1. Stratification method — image segmentation (GEOBIA), not point clustering

**The core decision**: strata are now delineated by segmenting the continuous
covariate rasters (SNIC), not by clustering discrete candidate sample
points (K-means). This is the single most consequential methodological
change in v6.3 — see CHANGELOG.md §[6.3] for the full diagnostic trail that
led here (a real "checkerboard" pattern on the actual Pimpri site, confirmed
from the project's own map output, not a theoretical concern).

- Achanta, R., & Süsstrunk, S. (2017). *Superpixels and Polygons using
  Simple Non-Iterative Clustering*. Proceedings of the IEEE Conference on
  Computer Vision and Pattern Recognition (CVPR 2017).
  https://openaccess.thecvf.com/content_cvpr_2017/papers/Achanta_Superpixels_and_Polygons_CVPR_2017_paper.pdf
  — the original SNIC algorithm paper. Confirmed via direct access to the
  CVPR open-access paper.

- Google Earth Engine API documentation: `ee.Algorithms.Image.Segmentation.SNIC`.
  https://developers.google.com/earth-engine/apidocs/ee-algorithms-image-segmentation-snic
  — confirmed exact parameter signature (`image, size, compactness,
  connectivity, neighborhoodSize, seeds`) and output structure (a `clusters`
  band plus per-input-band cluster means) directly from Google's own API
  reference, not assumed.

- GEOBIA (Geographic Object-Based Image Analysis) as the standard method for
  ecological/habitat mapping from remote sensing, as distinct from point-
  based classification — a paper on **ecotope segmentation** (the smallest
  ecologically distinct landscape units in a landscape classification
  system), published in *Remote Sensing* (MDPI), 2019, was identified and
  reviewed for this build via search. Full author list and exact volume/
  issue were not independently re-confirmed beyond the search result
  snippet — cite the general method and journal, verify the precise
  bibliographic entry before this goes into an external-facing document.

- A Natura 2000 (EU conservation network) habitat-mapping study validating
  automated segmentation against GPS ground-truth boundary tracks — mean
  discrepancy reported at approximately one Sentinel-2 pixel (~11 m).
  Identified via search; author/venue not independently re-confirmed beyond
  the search snippet — same caveat as above.

### SNIC parameter choices, cited against independent published usage (not guessed)

| Parameter | Value used | Basis |
|---|---|---|
| `compactness` | 0 | Three independent applied studies, found and reviewed during this build, all set `compactness=0` specifically to let segments follow real spectral/feature boundaries rather than being forced toward geometric regularity: (1) Baradaran, H. (2025). *Object-based unsupervised classification... in Google Earth Engine*. Medium. https://hanieh-baradaran.medium.com/object-based-unsupervised-classification-and-the-effects-of-changing-the-snic-clusters-parameters-df58de998de1 — explicitly states compactness=0 "since most of the plots in the study area are rectangular." (2) A vegetation-productivity change-detection study at the Dexing Copper Mine, published in a Taylor & Francis journal (2025) — identified via search, full citation not independently re-confirmed. (3) An SNIC+GLCM object-oriented land-cover classification study, *Remote Sensing* (MDPI), 2020 — identified via search, full citation not independently re-confirmed. |
| `connectivity` | 8 | Standard default across all reviewed sources; confirmed via GEE's own API documentation. |
| `size` | project-specific (see `PHASE_2_GEE_ExSitu.js`'s `SNIC_SIZE_PIXELS`) | GEE's documented default is 5 pixels; published studies use values from ~10 to ~450 depending on the target object scale and image resolution — there is no universal correct value, it must be tuned per project. Tuning against Pimpri's real segmentation output (not yet available — requires the client's next GEE run) is the next step, not a value asserted here as final. |
| `neighborhoodSize` | `2 × size` | GEE's documented default, made explicit in the script rather than left implicit, to avoid tile-boundary segmentation artefacts on a single-tile analysis. |

---

## 2. MCDA weighting — CRITIC method

- Diakoulaki, D., Mavrotas, G., & Papayannakis, L. (1995). *Determining
  objective weights in multiple criteria problems: The CRITIC method*.
  Computers & Operations Research, 22(7), 763–770.
  — the CRITIC (CRiteria Importance Through Intercriteria Correlation)
  method: objective, data-driven covariate weighting that penalises
  correlated/redundant criteria, used in place of a hand-assigned weight
  scheme. This citation is from general domain knowledge of the MCDA
  literature (CRITIC is a long-established, widely-taught method), not
  independently re-verified via a live source during this specific build —
  flagged for that reason, unlike the segmentation citations above which
  were checked against live sources this session.

- Empirical validation on this project's own data: `weight_scheme_comparison.json`,
  generated by `PHASE_3_StratifyAllocate.py`'s `run_weight_scheme_comparison()`
  — CRITIC-derived weights measurably outperformed the hand-assigned scheme
  on both silhouette score and spatial coherence on the real Pimpri
  candidate set. This is a directly reproducible result from this pipeline,
  not a literature citation — regenerate it on any new project's data to
  re-confirm the comparison holds there too.

---

## 3. Embeddings vs hand-crafted covariates for classification tasks

- Brown, C. F., et al. (2025). *AlphaEarth Foundations: An embedding field
  model for accurate and efficient global mapping from sparse label data*.
  Google DeepMind. Identified via search this session; reports embeddings
  outperforming hand-crafted spectral-index baselines on land-cover
  classification (0.78 vs 0.70 balanced accuracy) and crop mapping (0.90 vs
  0.82) — the general finding that embeddings excel at classification/
  mapping tasks specifically, which informed (and was empirically
  contradicted, on this specific site, by the weight-scheme/mode
  comparison above — worth stating plainly: the literature trend did not
  hold for Pimpri, and the pipeline's own empirical comparison mechanism is
  what caught that, not an assumption that the general trend applies
  universally).

- A wetland-vegetation-mapping comparison study, *Remote Sensing* (MDPI),
  2026 issue, found embedding-based classification produced visibly
  smoother, more spatially coherent boundaries than spectral-index-based
  classification at similar accuracy — identified via search, full
  citation not independently re-confirmed beyond the search snippet.

- A counter-example, found via the same search pass: a study on aboveground
  biomass estimation in Andean forests found hand-crafted spectral indices
  *outperformed* AlphaEarth embeddings for that specific structural-
  estimation task — cited in this pipeline's design docs as the basis for
  NOT assuming embeddings are universally superior, and for building the
  `mcda`/`embedding`/`hybrid` comparison mechanism rather than committing to
  one on faith. Full citation not independently re-confirmed beyond the
  search snippet.

---

## 4. Dataset currency — specific asset citations, each independently verified this session

| Dataset | Confirmed via | Note |
|---|---|---|
| Google Open Buildings V3 | Own GEE catalog page | Confirmed as a real, official (non-community) catalog asset with South Asia/India coverage. |
| VIDA Combined Buildings (India) | Search, community catalog page | Real, India-specific, but community-hosted — not independently band-verified the way official-catalog assets were. |
| TNC Global Human Modification v3 | Search, TNC's own data page | Theobald et al., cited generally in the GHM literature; confirmed as covering 1990–2022, superseding the CSP GHM 2016 single-snapshot product previously in use. |
| IUCN Global Ecosystem Typology | Own GEE catalog page | Confirmed real, with the exact `efg_code` property name verified directly (a property-name bug, `code` vs `efg_code`, was caught and fixed as a direct result of this verification). |
| `COPERNICUS/DEM/GLO30_2024_1` | Own GEE catalog page | The unsuffixed `COPERNICUS/DEM/GLO30` is confirmed deprecated — caught and fixed during this build, not assumed correct because it compiled. |
| Hansen Global Forest Change v1.13 | Own GEE Data Catalog page | Confirmed current release (through 2025), superseding v1.12 (through 2024). `treecover2000` confirmed, from the dataset's own documentation, to be a FIXED year-2000 baseline — never updates; current cover requires subtracting cumulative loss (`lossyear` band) from it, not using it raw. **Superseded (Aug 2026) as the primary TreeCover_Pct source** — confirmed on real Soulforest Veltoor data that even the loss-adjusted version stayed at 0 (permanently zeroes any pixel with ANY historical loss event, wrong for a restoration site), and switching to Esri's land-cover "Trees" class also failed there (a genuine classifier limitation for that site's vegetation type, cross-confirmed against NatCoverPct and NDVI). TreeCover_Pct is now computed directly from an NDVI threshold (0.3) on the same Sentinel-2 composite used for NDVI_raw; both Hansen- and Esri-derived versions are kept as secondary reference bands only. |
| Esri/Impact Observatory Sentinel-2 10m Annual Land Cover Time Series (`projects/sat-io/open-datasets/landcover/ESRI_Global-LULC_10m_TS`) | Community catalog's own authoritative documentation page, including exact class-value table | Replaces ESA WorldCover v200, confirmed via its own GEE catalog entry to be a single fixed 2021 snapshot with no update mechanism. Esri's product is confirmed genuinely annually updated (2017–2025, most recent update 2026-05-25 per its own changelog) at identical 10m resolution and the same Sentinel-2 source imagery. Karra, Kontgis, et al. "Global land use/land cover with Sentinel-2 and deep learning." IGARSS 2021. Class values (1=Water, 2=Trees, 4=Flooded Vegetation, 5=Built Area, 7=Snow/Ice, 8=Bare Ground, 9=Rangeland, 10=Clouds) taken directly from the dataset's own class table, not inferred from a partial description. |
| Comparative cloud-cover robustness, ESA WorldCover vs Esri/Dynamic World | Peer-reviewed comparative validation study, ScienceDirect | ESA WorldCover's Sentinel-1 SAR + Sentinel-2 fusion gives it a documented cloud-penetration advantage Esri's Sentinel-2-only product does not have. Judged not decisive for this project (Pimpri has a distinct dry season; ESA's advantage is moot regardless since it hasn't been re-run since 2021) — stated as a site-specific judgement call in `PHASE_2_GEE_ExSitu.js`'s own comment, not asserted as universally correct. |

---

## 5. Deployment design principles (not literature citations — project-specific decisions, documented here for completeness)

The semi-anchor + boost design (v6.1–v6.2) and its replacement, the
`continuous_proportional` / `sequential_cluster` regime framework (v6.3),
are client-designed and project-specific — not drawn from a published
sampling-design literature citation. The general *principle* behind them
(proportional allocation of limited devices across strata, weighted by
relative size, using a largest-remainder rounding method) is standard
practice in stratified sampling design generally, but the specific
mechanism here was built and iteratively corrected against this project's
own requirements and real data, documented in full in `CHANGELOG.md`.

v6.3.10's manually-drawn exclusion zones (buildings, parking, other
inaccessible ground) are the same principle applied one layer earlier:
after three separate satellite-classification-based approaches to this
problem each failed a different way (see `CHANGELOG.md` §[6.2]–[6.3.8]),
a hand-drawn, ground-truthed polygon — subtracted purely geometrically,
before any GEE covariate is involved — is a more reliable exclusion
mechanism than any remote-sensing land-cover proxy for a case this
specific and this consequential to get right. Not a literature citation;
a project-specific engineering decision, made after real, repeated,
documented failure of the alternative.

---

## How to use this document

When this pipeline's methodology needs to be defended — to a client
reviewer, an external auditor, or in a public-facing disclosure document —
cite the specific entries above relevant to the claim being made, not the
whole document generically. Where a citation above is flagged as "not
independently re-confirmed beyond the search snippet," verify the full
bibliographic entry (author list, volume, pages) directly against the
publisher before it appears in an external-facing document — this file
records what was checked and how during the pipeline's construction, it is
not itself a peer-reviewed bibliography.

---

## 6. Additions specific to the unified pipeline (Aug 2026, not in v6.0)

### 6.1 Minimum-mapping-unit auto-tune — extended to a real merge algorithm

v6.0's PIPELINE note above (§1) already documented the MMU auto-tune
*concept* for Tata Motors (70 raw SNIC segments → auto-tuned
`MIN_MAPPING_UNIT=9` → 10 final segments matching device count). This
pipeline implements the actual merge mechanism generically: any segment
below the tuned threshold merges into its nearest neighbor, subject to two
requirements neither present in the original concept description:
(1) **true geometric adjacency** (distance-zero touching in projected
metres) rather than "nearest by any distance" — the latter was tried
first, found to produce segments with up to 12 disjoint spatial parts on
real data, and replaced; (2) **connected-component decomposition before
merging**, since a single raw `SEGMENT_ID` can itself already span
disconnected patches (confirmed directly on real Soulforest data). Every
final segment is verified, by a hard runtime assertion, to be a single
connected polygon.

### 6.2 Spatial connectivity constraint for non-segmentation (Gower)
clustering

For scattered agroforestry candidates, where SNIC segmentation cannot
apply (no contiguous raster surface — points are physically separate farm
parcels), spatial coherence is instead enforced via a k-nearest-neighbor
connectivity graph passed as `sklearn.cluster.AgglomerativeClustering`'s
`connectivity` parameter (confirmed directly, by testing, that this
parameter is compatible with `metric="precomputed"` — not obvious from the
library's documentation alone). A pure connectivity graph alone was found,
on real data, to still permit "chaining" (a hierarchical merge which
locally always joins nearby candidates can still produce a final cluster
spanning tens of kilometres); a hard post-processing spatial-diameter cap
(KMeans-based splitting) was added as a second, decisive layer specifically
because the connectivity constraint alone was empirically insufficient.

### 6.3 CRITIC weighting extended from segment tuning to candidate ranking

v6.0 (§2 above) used CRITIC for stratification weight comparison. This
pipeline additionally uses it for **within-EMU candidate typicality
ranking** — the same method, same citation (Diakoulaki, Mavrotas &
Papayannakis 1995), applied to a new purpose: scoring which candidate
position within an already-delineated EMU is most representative of that
EMU's own covariate profile, matching the Pimpri methodology's own
documented use of "CRITIC-weighted multi-criteria typicality" for
within-stratum position selection (that methodology's §4.4).

### 6.4 GEE asset upload format — a real, previously-undocumented bug

GEE's Cloud Assets manager does not accept raw `.geojson`/`.json` uploads
through its UI — confirmed directly from a real upload attempt, not
assumed from documentation. Every project's candidate set is now exported
as a zipped ESRI Shapefile instead (verified round-trip-readable before
being handed off), containing only a `name` join-key column short enough
to survive Shapefile's 10-character field-name truncation with no mapping
required.

### 6.5 A real, previously-undiagnosed bug in the shared GEE script's
aquatic export

The shared script's `WATERBODY_ASSET_PATH` was found to be hardcoded to a
single, fixed Tata Motors asset — confirmed by comparing three separate
projects' "aquatic" CSV exports and finding them byte-for-byte identical,
including waterbody names ("Sumanth Sarovar", "Sharma Lake") that belong
to a different project entirely. Fixed: the default is now `""` (skip,
matching the script's own pre-existing but previously-contradicted
comment), and each project's real waterbody asset (when it has one) is
generated fresh from that project's own client-declared water features.

### 6.6 Manual point specification for real, non-rotating sample designs

Soulforest's soil chemistry sampling (4-5 corner + 1 centre points per
EMU) went through several automated selection approaches before settling
on manual specification: farthest-point sampling (seeding with an
extremity, then greedily adding whichever remaining point maximises its
own minimum distance to every point already chosen) fixed an earlier
approach's clustering problem, but each automated method solved one real
problem while exposing another on real visual inspection of the actual
map — anchoring to a minimum-rotated-bounding-rectangle's own corners
broke down for an irregular EMU shape (a bounding box's corners can sit
in empty space entirely outside a winding polygon); a hard boundary-
clearance pre-filter could eliminate an entire narrow arm of a winding
shape from consideration regardless of how remaining candidates were
selected; and even unconstrained farthest-point sampling still produced
a spatial arrangement judged unworkable on the rendered map. Every point
is now a real, manually specified candidate name, checked to exist and
belong to its stated EMU before use — the more reliable choice once
automated placement repeatedly required a human, visual judgement call
this kind of design genuinely needs.

### 6.7 Season-reset rotation for multi-season comparison designs

Tata Motors Pimpri's `zone_scoped_continuous` regime resets its weekly
position-rotation index at every season boundary (`season_length_weeks`
in config) rather than running one long continuous cycle across the whole
programme — necessary specifically because the design calls for valid
season-to-season comparison at a fixed point: variation observed there
needs to be attributable to the season, not to a different physical spot
happening to be sampled that time. A continuous (never-reset) rotation is
the right choice for a different, real design goal — maximising raw
spatial coverage across a programme with no season-to-season comparison
requirement — and this pipeline's own earlier draft of this feature
initially, incorrectly, reused that continuous design before the actual
requirement was confirmed directly.

