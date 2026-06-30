# Darukaa Reference Benchmarking Pipeline V4.0

**An indicator-agnostic framework for comparing project-site biodiversity metrics against ecoregion-specific reference benchmarks, feeding into the State of Nature Module scoring architecture.**

Developed by Gaurav Singh, Scientific Lead — Biodiversity Methodology, Darukaa.Earth

---

## What This Solves

Every biodiversity indicator value is a number without meaning until you answer: *"Compared to what?"* An NDVI of 0.63 at a community reserve in Arunachal Pradesh needs context: is that good or degraded for this ecoregion?

This pipeline provides that context automatically for any indicator at any site, then converts the results into TNFD-aligned concern levels and a State of Nature Score (0–10) for disclosure.

---

## How It Works

For each site × indicator:

**Tier 1 — Regional Reference:** Extracts the indicator across a per-indicator buffer (10–150 km) around the site centroid. Gives regional landscape context.

**Tier 2 — Contemporary "Best-on-Offer" Reference:** Identifies least-disturbed pixels within the same land-cover class and elevation band via three-way stratification — same land cover (Copernicus LC 100m), same elevation ±300m (SRTM), and HMI ≤ dynamic threshold (ceiling 0.10).

**Intactness ratio:** `site / reference` for state indicators (higher=better); `reference / site` for pressure indicators (lower=better). Direction-corrected by pipeline. Output: 0–100%.

**Tier 2 eligibility:** Threat/pressure indicators (`tier2_eligible=False`) skip Tier 2 entirely — using HMI to select "least-disturbed" reference pixels for indicators that *measure* human disturbance is circular. Tier 1 is their correct comparison. All aquatic, eDNA, scalar, and plant-species indicators are also `tier2_eligible=False` — no global reference baselines exist for these.

**Tier 2 behaviour for agricultural/modified landscapes:** For sites where gHM > 0.4 throughout the buffer, no pixels meet the HMI ≤ 0.10 ceiling. Tier 2 correctly returns `insufficient reference pixels`. This is expected behaviour — not a bug.

---

## Reference Selection Methodology

Adapted from SEED biocomplexity framework (McElderry et al. 2024, Supplement S1.1) with elevation stratification added.

**Dynamic HMI threshold (SEED Equation S1):**
```
if P5(HMI) ≤ 0.10:   use P5
elif P3(HMI) ≤ 0.10:  use P3
else:                  use 0.10
```
Ceiling is 0.10 — adapted from SEED's 0.05 for buffer-scale analysis. Corresponds to Kennedy et al. "low-impact" HMI class.

**Fallback cascade:** Drop LC mask → expand buffer 2×/3×/4× up to 200km → warn.

**Elevation stratification:** Filters reference pixels to ±300m of site elevation (SRTM). Not in SEED. Critical for mountainous sites.

**Citation:** *"Reference areas selected following the contemporary minimal-disturbance approach, adapted from McElderry et al. (2024) SEED framework Supplement S1.1. Dynamic HMI threshold (5th percentile, ceiling 0.10) applied within same land cover × elevation strata (±300m SRTM). Threat/pressure indicators excluded from Tier 2 to avoid methodological circularity. See McNellie et al. (2020)."*

---

## Registered Indicators (44) — v4.0

### Dim 1 — Ecosystem Extent (5)

| Indicator | Source | Radius | Tier 2 | Direction |
|-----------|--------|--------|--------|-----------|
| `natural_habitat` | Dynamic World 10m | 50 km | ✓ | Higher=better |
| `natural_landcover` | Dynamic World 10m | 50 km | ✓ | Higher=better |
| `cpland` | Darukaa PV binary (India-only, native-resolution) | 30 km | ✗ Protocol C | Higher=better |
| `forest_loss_rate` | Hansen GFC v1.12 (2001–2024) | 50 km | ✓ | Lower=better |
| `kba_overlap` | IUCN KBA Global | 50 km | ✗ Protocol A | Higher=better |

### Dim 2 — Ecosystem Condition (23)

**Terrestrial core (10):**

| Indicator | Source | Radius | Tier 2 | Threshold |
|-----------|--------|--------|--------|-----------|
| `ndvi` | Sentinel-2 SCL-masked, annual median | 50 km | ✓ | Protocol B |
| `habitat_health` (HHI) | S2 NDVI time series z5/σ | 50 km | ✓ | Protocol B |
| `flii` | Dynamic World 10m forest mask + VIIRS (approx.) | **150 km** | ✓ | Protocol A (Potapov) |
| `eii` | Landbanking Group 300m | 75 km | ✓ | Protocol B |
| `eii_structural` | Landbanking 300m | 75 km | ✓ | Protocol B |
| `eii_compositional` | Landbanking / IO BII 300m | 75 km | ✓ | Protocol B |
| `eii_functional` | Landbanking / actual:potential NPP | 75 km | ✓ | Protocol B |
| `bii` | IO 300m (primary) / PREDICTS NHM (fallback) | 75 km | ✓ | Protocol A (NHM) |
| `pdf` | Dynamic World 10m + ReCiPe CFs | 50 km | ✓ | Protocol B |
| `aridity_index` | CHIRPS + TerraClimate (PET ×0.1 mm) | 50 km | ✓ | Protocol B |

**Aquatic & eDNA (8) -- aquatic sites only:**

| Indicator | Source | Radius | Tier 2 | Notes |
|-----------|--------|--------|--------|-------|
| `tspi` | Sentinel-2 NDCI (B5−B4)/(B5+B4) | 10 km | ✗ | Higher = more eutrophication |
| `sabf` | Sentinel-2 FAI bloom frequency | 10 km | ✗ | Higher = more bloom events |
| `wcpi` | Sentinel-2 Nechad TSM inversion | 10 km | ✗ | Site-relative; higher = clearer |
| `wsdi` | Sentinel-1 SAR VV water occurrence | 10 km | ✗ | Higher = more hydrologically dynamic |
| `hsas` | Sentinel-2 habitat suitability model | 10 km | ✗ | Requires `edna_points_asset` in config |
| `edpp` | Landsat LST + S2 moisture/turbidity/UV | 10 km | ✗ | Higher = better eDNA preservation |
| `mspl` | S2 NDCI + Landsat LST + turbidity | 10 km | ✗ | Higher = more microbial stress |
| `rci` | Sentinel-2 riparian vegetation structure | 25 km | ✗ | 100m riparian buffer; 2-year window |

**Terrestrial vegetation (5):**

| Indicator | Source | Radius | Tier 2 | Notes |
|-----------|--------|--------|--------|-------|
| `riparian_ndvi_trend` | Sentinel-2 linear NDVI slope | 25 km | ✗ | NDVI/year; negative = degradation |
| `jrc_water_persistence` | JRC GSW Monthly History | 10 km | ✗ | Fraction >75% months with water |
| `shdi` | Sentinel-2 NDWI vectorization | 10 km | ✗ | **Scalar only**; ≥1.0; higher = more complex |
| `lai` | MODIS MCD15A3H (500m, scale 0.1) | 50 km | ✓ | m²/m²; valid 0–8 |
| `chm` | GEDI L2A rh98 monthly mosaic | 50 km | ✓ | Metres; quality-masked 0–80m |

**Note on Aridity Index:** AI = P/PET is NOT bounded 0–1. Humid tropical forests have AI = 2–4 (rainfall exceeds PET). TerraClimate PET is stored in 0.1mm units — must be multiplied by 0.1 before dividing.

**Note on WSDI semantics:** WSDI peaks at 0.5 occurrence (maximally dynamic/unstable water body). A stable permanent lake scores low. Direction: `higher_is_better=False`.

**Note on SHDI:** This is the morphometric Shoreline Development Index (shape complexity). Do not confuse with `sdi` (Shoreline Disturbance Index, anthropogenic pressure, pillar 5).

**Note on FLII applicability (v4.0):** FLII is conceptually a forest-integrity index. `extract_flii` now checks 10m forest-class fraction before computing; sites with <10% forest cover (e.g. active agroforestry/farmland) return `None` with explicit `metadata.note = "Not Applicable — non-forest site"` rather than a silently-failed null. Always check `metadata.applicable` before treating a missing FLII value as a data-quality issue.

**Note on data-source consistency (v4.0):** Dynamic World V1 (10m) is the single canonical land-cover classification source for this entire module — `natural_habitat`, `natural_landcover`, `pdf`, `flii`, `hdi`, `sdi`, `hsas`, `iri`, `edpp`, `flagship_habitat`, `star_t` all share one helper (`_dw_mode`) and one set of named class constants (`DW_TREES`, `DW_CROPS`, `DW_BUILT`, etc. — see `darukaa_reference/indicators/__init__.py`). ESA WorldCover and MODIS MCD12Q1 have been fully retired from this pipeline as of v4.0. See "v4.0 — 10m Resolution Migration" below for rationale.

### Dim 3 — Species Population Size (3)

| Indicator | Source | Radius | Tier 2 | Direction | Notes |
|-----------|--------|--------|--------|-----------|-------|
| `endemic_richness` | IUCN mammals + birds (range < 100,000 km²) | 100 km | ✗ Protocol C | Higher=better (lower concern) | Both groups; species list in metadata |
| `flagship_habitat` | HSI × 0.6 + normalised species richness × 0.4 | 50 km | ✗ Protocol A | Higher=better (lower concern) | Composite; see methodology note |
| `endemic_plant_richness` | IUCN Plant Redlist (range < 100,000 km²) | 100 km | ✗ Protocol C | Higher=better (lower concern) | species list in metadata |

**Conservation-priority vs. concern (v4.0 clarification):** A high `endemic_richness`/`endemic_plant_richness`/`flagship_habitat` value correctly scores LOW concern in the SoN axis — the presence of biodiversity is not itself a risk signal. Concern in this framework measures degradation/risk, not ecological significance. Sites with unusually high endemism should still be separately flagged for conservation-priority narrative reporting (see `conservation_priority_flag` in `endemic_richness` registry metadata) — that is a distinct claim ("this site is valuable, prioritize protecting it") from a concern score ("this site is degraded"). Conflating the two would invert the SoN score's purpose: a community reserve with 40 endemic species sitting inside intact forest is a conservation *success*, not a site "of concern."

### Dim 4 — Species Extinction Risk (4)

| Indicator | Source | Radius | Tier 2 | Direction | Categories |
|-----------|--------|--------|--------|-----------|------------|
| `threatened_richness` | IUCN mammals + birds | 100 km | ✗ Protocol C | Lower=better (more spp present = more concern) | CR/EN/VU only |
| `ceri` | IUCN mammals + birds (null-filtered) | 100 km | ✗ Protocol A | Lower=better (higher weighted risk = more concern) | All: EX/EW/CR/EN/VU/NT/LC |
| `star_t` | Bird + mammal ranges × habitat × threat pressure | 100 km | ✗ Protocol A | **Higher=better (v4.0 flip — see note)** | CR/EN/VU only |
| `threatened_plant_richness` | IUCN Plant Redlist | 100 km | ✗ Protocol C | Lower=better (more spp present = more concern) | CR/EN/VU; species list in metadata |

**STAR_T direction fix (v4.0):** Previously registered `higher_is_better=False`, which contradicted this pipeline's own documented interpretation. STAR_T measures threat-ABATEMENT OPPORTUNITY at a site — i.e. how much global extinction risk could be reduced by conservation action there — not threat presence. It is structurally a benefit/opportunity metric like `endemic_richness`, not a risk-presence metric like `threatened_richness` or `ceri`. A high STAR_T score means a site is a high-value conservation opportunity (lower concern); the previous `False` setting would have scored exactly those sites as high-concern, inverting the metric's intended meaning. Flipped to `higher_is_better=True` in v4.0.

**IUCN category consistency across indicators:**
- `threatened_richness`, `threatened_plant_richness`, `star_t`: CR/EN/VU only — strict TNFD threatened definition
- `ceri`: All categories (EX/EW=5, CR=4, EN=3, VU=2, NT=1, LC=0) — NT intentionally included
- `endemic_richness`, `endemic_plant_richness`: No category filter — endemism defined by range size (<100,000 km²)

### Threats & Pressures (9 — contextual only, not in SoN score)

All `tier2_eligible=False`. Not in SoN Score per TNFD Annex 2 design.

| Indicator | Source | Radius | Notes |
|-----------|--------|--------|-------|
| `ghm` | CSP/HM GlobalHumanModification 1km | 50 km | |
| `light_pollution` | VIIRS DNB monthly | 25 km | |
| `hdi` | Dynamic World 10m built-up distance | 25 km | |
| `lst_day` | MODIS MOD11A1 daily, annual mean | 25 km | |
| `lst_night` | MODIS MOD11A1 night, annual mean | 25 km | |
| `sdi` | Sentinel-2 + Dynamic World shoreline disturbance | 10 km | disturbed fraction in 100m shore buffer |
| `stsi` | Landsat 8 LST site-normalized | 25 km | v6.4; site-relative only; optional |
| `iri` | Sentinel-2 multi-factor invasion risk | 10 km | road proxy = built-up edge, not true roads |
| `ivsi` | Sentinel-2 NDVI change detection | 25 km | expansion > 0.2 NDVI vs 5-year prior |

---

## Indicators Rejected (Redundancy Record)

The following were proposed but not registered. Documented here for traceability.

| Proposed | Reason | Already Covered By |
|----------|--------|--------------------|
| EVI | Redundant; same greenness concept from same sensor | `ndvi` (pillar 2); EVI used internally in `rci` |
| Native Vegetation Cover (ESA WorldCover) | Redundant; third native-extent metric adds source noise. **v4.0: ESA WorldCover fully retired from pipeline** (was previously used only by `hdi`; HDI now uses Dynamic World — see "v4.0 — 10m Resolution Migration") | `natural_habitat` + `natural_landcover` (pillar 1), both DW-based |
| Plant Phenological Stability Index (PSI) | Redundant; PSI = mean/σ ≈ HHI = z5/σ — same NDVI stability concept | `habitat_health` (pillar 2) |
| Vegetation Drought Stress Index | Deferred — may pick up later | — |
| Burn Severity (dNBR) | Proposed in separate session; event-specific, not a standing indicator | — |

---

## Flagship Habitat Viability — Methodology Note

**Formula:** `HSI × 0.6 + species_suit × 0.4`

where:
- `HSI` (0–1) = forest × elevation_suitability × inverse_light_pressure
- `species_suit` (0–1) = min((n_threatened_birds_CR/EN/VU + n_threatened_mammals_CR/EN/VU) / 50, 1.0)

**Normalisation ceiling:** 50 species (provisional, Eastern Himalayan context). Requires validation across ecoregions.
**Rationale for composite:** Pure HSI answers "is this structurally suitable habitat?" The bird count component answers "do threatened species actually use it?" A site with HSI=0.93 and 0 threatened birds is ecologically different from one with HSI=0.93 and 45 threatened birds. The composite captures both dimensions.

**Normalisation:** Bird count is divided by 50 (provisional ceiling based on Eastern Himalayan regional context) before weighting, ensuring the index remains 0–1 bounded. The 50-species ceiling requires validation across sites and ecoregions.

**Field name:** `RedList__5` (double underscore) in the IUCN bird GEE asset.
---

## Species Lists

The pipeline captures species lists from IUCN range maps for four indicators:
- **Threatened Richness** (mammals + birds): CR/EN/VU, with category breakdown
- **CERI** (mammals + birds): All categories with weights
- **Endemic Richness** (mammals + birds): Range <100,000 km²
- **Endemic Plant Richness**: Range <100,000 km² from IUCN Plant Redlist
- **Threatened Plant Richness**: CR/EN/VU from IUCN Plant Redlist, with n_CR/n_EN/n_VU counts

Species lists are returned in the `metadata` field of each extraction result and included in `benchmark_scorecard_with_son.json`. Supports TNFD LEAP Step 3 disclosure.

---

## EII Methodology (Landbanking Group)

Uses pre-computed EII from `projects/landler-open-data/assets/eii/global/eii_global_v1` (300m).

**Structural:** Quality-weighted core area. HMI<0.4 → habitat; eroded 300m → core; weighted by HMI class; averaged in 5km neighbourhood.

**Compositional:** Impact Observatory BII 300m. Average abundance of originally-present species.

**Functional:** Observed NPP vs. ML-modelled potential NPP. 2/3 magnitude + 1/3 seasonality.

**Aggregation:** `EII = M × FuzzySum(A,B)` where M = min(S,C,F), FuzzySum(A,B) = A+B−A×B.

**BII alignment:** BII uses same IO 300m source as EII compositional for both site and reference.

---

## v4.0 — 10m Resolution Migration

### Problem: "swallowed polygons"

Several indicators (`natural_landcover`, `pdf`, `flii`) previously relied on MODIS MCD12Q1 (500m, ~25 ha/pixel) or ESA WorldCover (`hdi` only). For project sites smaller than one MODIS pixel — common in agroforestry/restoration contexts, e.g. several FCF Gujarat (Banaskantha) clusters at 2.7–5.2 ha — these indicators were effectively measuring the dominant land cover of a much larger surrounding neighbourhood, not the site itself. This produced internally contradictory results on the same pipeline run, e.g.:

```
Natural Land Cover Proportion — FCF Gujarat aggregated run:
  site_value = 0.0%   tier2_reference = 100.0%
```

A site cannot legitimately have 0% natural cover while its own least-disturbed regional reference (drawn from the same buffer) reads 100% — this was a resolution artefact, not an ecological finding.

### Fix: single canonical 10m source

Dynamic World V1 (10m, Brown et al. 2022, DOI:10.1038/s41597-022-01307-4) is now the **only** land-cover classification source used across the module. ESA WorldCover and MODIS MCD12Q1 have been fully retired from indicator computation.

**Why Dynamic World over ESA WorldCover, and why not both:**
- ESA WorldCover has only 2 static epochs (v100=2020, v200=2021) — not a continuous monitoring product. A 5-year biannual M&E program requiring 10 comparable longitudinal timepoints cannot be anchored to a source with 2 total epochs; by the program's second cycle the "baseline" would already be 4 years stale.
- Dynamic World has continuous near-real-time coverage since 2015 (~5-day Sentinel-2 revisit), matching the program's monitoring cadence.
- Running two 10m classifiers in parallel for conceptually related indicators (e.g. one for `natural_habitat`, a different one for `natural_landcover`) produces persistent cross-indicator disagreement that is measurement noise, not ecological signal — confirmed by the contradiction above. A single classifier with one consistent class taxonomy avoids this.
- ESA WorldCover's finer class taxonomy (11 classes vs. DW's 9, e.g. separate mangrove/wetland classes) was considered but not adopted as a parallel source, since no current indicator's scientific validity depends on that distinction; it can be revisited as a dedicated one-time stratification layer if a specific future indicator needs it.

**Migrated indicators:**

| Indicator | Was | Now | Reduce scale fixed |
|---|---|---|---|
| `natural_landcover` | MODIS MCD12Q1 500m | Dynamic World 10m | 500 → 10 |
| `pdf` | MODIS MCD12Q1 500m | Dynamic World 10m | 500 → 10 |
| `flii` | MODIS MCD12Q1 500m forest mask | Dynamic World 10m forest mask (`DW_TREES`) | 500 → 30 |
| `hdi` | ESA WorldCover v200/2021 | Dynamic World 10m built-up class | already 10 |

**Unchanged by design:**
- `eii`, `eii_structural`, `eii_compositional`, `eii_functional`, `bii` — pre-computed composite indices from Landbanking/Impact Observatory at 300m. These are not raw classification outputs and cannot be recomputed at 10m without rebuilding someone else's published model. Native resolution is correct here.
- `ghm` (1km, CSP/HM) — external pre-computed pressure index, same reasoning.
- `cpland` — uses a dedicated Darukaa India PV-binary asset, not MODIS/DW. Its native resolution is auto-detected at runtime via `img.projection().nominalScale()`, so it was already resolution-correct prior to v4.0 and required no migration.

### Single source of truth: shared helper and class constants

Prior to v4.0, six different functions (`_img_natural_habitat`, `_img_sdi`, `_img_hsas`, `_img_iri`, `_img_edpp_bands`, `_img_flagship_hsi`) each independently called Dynamic World inline with hardcoded magic-number class IDs (e.g. `dw.eq(6)` for built-up, repeated six times with no shared definition). This meant a future change to DW's date range, cloud handling, or composite method would require finding and fixing six separate call sites — and any inconsistency between them (e.g. one function using `dw.eq(7)` for bare ground, another forgetting it) would silently produce different "bare ground" definitions across indicators.

v4.0 introduces:
```python
_dw_mode(c, years_back=0)   # single shared DW annual-composite call site
DW_TREES, DW_GRASS, DW_FLOODED_VEG, DW_CROPS, DW_SHRUB_SCRUB,
DW_BUILT, DW_BARE, DW_SNOW_ICE, DW_WATER     # named class constants
DW_NATURAL_CLASSES = [DW_TREES, DW_GRASS, DW_FLOODED_VEG, DW_SHRUB_SCRUB]
```
All classification-derived indicators now call `_dw_mode(c)` and reference the named constants rather than re-deriving class numbers inline. `natural_landcover`'s fractional-weighting scheme (1.0 natural / 0.5 "mixed" / 0.0 non-natural) is preserved from its prior MODIS implementation, with the MODIS mosaic class (14) — which has no Dynamic World equivalent, since DW is a hard per-pixel classifier with no IGBP-style mosaic category — approximated via a 3×3 focal-window heterogeneity check (a natural pixel adjacent to a non-natural pixel gets the 0.5 "mixed" weight).

### FLII applicability precondition

FLII is conceptually a forest-integrity index. Under the old MODIS-masked implementation, sites with no qualifying forest pixels (e.g. active agroforestry/farmland project sites — by definition non-forest) silently returned `None` via mask failure, with no indication of *why*. This looked like a pipeline bug rather than a methodological limitation, and was the literal symptom that surfaced on the FCF Gujarat agroforestry run (`Forest Landscape Integrity Index | — | 9.83 | 4.97`: reference computed, site value null).

`extract_flii` (v4.0) now explicitly checks 10m forest-class fraction before computing FLII. Below 10% forest cover, it returns:
```python
{"value": None, "pixels": None,
 "metadata": {"applicable": False, "forest_fraction": 0.0XX,
              "note": "Not Applicable — site is X% forest ..."}}
```
Report layers should check `metadata.applicable` and render "Not Applicable — non-forest land use" rather than treating this as missing/failed data.

### Direction-flag (`higher_is_better`) audit

Three corrections made in v4.0, after cross-checking every Pillar 3/4 indicator's documented interpretation against the underlying ecological logic — see Dim 3 and Dim 4 sections above for full detail:

1. **`star_t`: `False` → `True`.** This was the one genuine bug. STAR_T measures threat-abatement *opportunity*, not threat presence; higher = more conservation upside = lower concern. The prior `False` setting contradicted this pipeline's own documented interpretation and would have inverted the metric.
2. **`endemic_richness`, `flagship_habitat`: made explicit (`True`).** Both were relying on the dataclass default rather than an explicit flag. Confirmed correct as-is — high endemism/habitat-suitability scores correctly indicate low concern (ecological value, not risk).
3. **`threatened_richness`, `threatened_plant_richness`, `ceri`: confirmed already correct (`False`).** No change — these genuinely are risk-presence metrics where more = more concern.

A conceptual distinction worth restating: **"ecologically valuable" and "concerning" are not the same claim.** A site with 40 endemic species inside an intact reserve should score low concern (it's a conservation success, not a risk), while that same fact — high endemism — is still worth surfacing separately in narrative reporting as a conservation-priority signal. Conflating the two by scoring high endemism as "high concern" would invert the SoN score's purpose.

---

## State of Nature Scoring

### Threshold Protocols

**Protocol A — Published absolute thresholds (applied to raw site value):**

| Metric | VL | L | M | H | VH | Source |
|--------|----|----|----|----|-----|--------|
| BII | >80% | 60–80% | 40–60% | 20–40% | ≤20% | NHM / TNFD Annex 2 |
| FLII | >8.0 | 6.0–8.0 | 4.0–6.0 | 2.0–4.0 | ≤2.0 | Potapov et al. 2020 |
| MSA | >0.8 | 0.6–0.8 | 0.4–0.6 | 0.2–0.4 | ≤0.2 | GLOBIO4 |
| Flagship Habitat | >0.8 | 0.6–0.8 | 0.4–0.6 | 0.2–0.4 | ≤0.2 | HSI literature |
| CERI | <0.10 | 0.10–0.20 | 0.20–0.35 | 0.35–0.50 | >0.50 | Butchart et al. 2007 |
| STAR_T | >9 | 6–9 | 3–6 | 1–3 | 0 | IUCN STAR methodology (v4.0: direction flipped — see Dim 4 note above) |
| KBA/IBA Overlap | <1% | 1–25% | 25–75% | 75–99% | 100% | TNFD/IBAT disclosure scheme |

**Protocol B v1.0 — Fixed, version-controlled thresholds (applied to Tier 2 intactness %):**
```
≥ 85% → VL  Basis: Newbold et al. 2016 planetary boundary (~90% BII)
70–84% → L   Noticeably impacted, recoverable (SBTN science)
50–69% → M   Substantially degraded — material loss (GLOBIO4)
30–49% → H   Severely impaired
< 30%  → VH  Critically impaired
```
Protocol B applies to: `natural_habitat`, `natural_landcover`, `forest_loss_rate`, `ndvi`, `habitat_health`, `eii` (all components), `pdf`, `aridity_index`, `lai`, `chm`.

**Protocol C — Tier 1 regional comparison (same B thresholds applied to Tier 1 intactness):**
For count/connectivity indicators where absolute thresholds are ecoregion-dependent: `cpland`, `endemic_richness`, `threatened_richness`, `endemic_plant_richness`, `threatened_plant_richness`. ⚠️ Count indicators subject to Species-Area Relationship artefact — see Known Limitations.

**Version:** Protocol B v1.0. Review trigger: ≥10 Darukaa sites across ≥3 ecoregion types.

### Dimension Scoring

```
dim_score = mean(concern_numeric for all populated metrics in dimension)
```
Rounded to nearest 0.5 → Very Low / Low / Moderate / High / Very High.

Aquatic and eDNA indicators (v6.4), `riparian_ndvi_trend`, `jrc_water_persistence`, and `shdi` contribute to Dim 2 scoring only when the site is an aquatic/riparian context. `shdi` is scalar-only and may be reported separately rather than scored.

### SoN Score Formula

```
SoN_Score = (Σ dim_scores − n_dims) / (n_dims × 4) × 10
Full (4 dims): (Σ − 4) / 16 × 10   [SoN PRD v2.0, normalized sum]
```
Output: 0–10. Concern levels: 0–4=Very Low, 4–5=Low, 5–7=Moderate, 7–8=High, 8–10=Very High.

**Threats excluded from SoN Score** per TNFD Annex 2.

**Threat indicator categorical labels:**

| Indicator | Very Low | Low | Moderate | High | Very High | Source |
|-----------|----------|-----|----------|------|-----------|--------|
| gHM | 0.00–0.10 | 0.10–0.30 | 0.30–0.60 | 0.60–0.90 | 0.90–1.00 | Theobald et al. 2025 |
| Light Pollution (nW·cm⁻²·sr⁻¹) | < 1.0 | 1.0–5.0 | 5.0–30.0 | 30.0–100.0 | > 100.0 | NASA Black Marble / VIIRS DNB |
| HDI | < 0.50 | 0.50–0.60 | 0.60–0.70 | 0.70–0.80 | ≥ 0.80 | Mishra et al. 2017 |
| LST Nighttime (°C) | < 22 | 22–26 | 26–30 | 30–34 | > 34 | KMC et al. 2025 |
| LST Daytime (°C) | < 32 | 32–36 | 36–40 | 40–44 | > 44 | Muse, Clement & Mach 2024 |

Aquatic threat indicators (`sdi`, `stsi`, `iri`, `ivsi`) do not yet have published absolute thresholds — reported as raw values with contextual interpretation only.

---

## GEE Assets

| Asset | Indicators | Access |
|-------|-----------|--------|
| `projects/landler-open-data/assets/eii/global/eii_global_v1` | EII + BII | Public |
| `projects/gaurav-singh-007/assets/bii-2020_v2-1-1` | BII fallback | User upload |
| `projects/darukaa-earth130226/assets/RedList_Mammals_Terrestrial` | CERI, Threatened, Endemic | Darukaa |
| `projects/darukaa-earth130226/assets/RedList_Bird_IUCN_Category` | CERI, Threatened, Endemic, Flagship, STAR | Darukaa |
| `projects/darukaa-earth130226/assets/KBA_Global_POL_SEP25` | KBA Overlap | Darukaa |
| `projects/darukaa-earth-product/assets/biodiversity_India_PV_Binary_2025_Full_Mosaic` | CPLAND | Darukaa (India only) |
| `projects/darukaa-earth130226/assets/IUCN_Plant_Redlist` | Endemic Plant, Threatened Plant | Darukaa |
| `projects/darukaa-earth130226/assets/Nandoshi_Lake` | Aquatic pilot ROI | Darukaa |

**Bird asset field name:** `RedList__5` (double underscore). Mammal asset uses `category`. Plant asset uses `category` and `sci_name`.

---

## Configuration (config.py)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `hmi_hard_ceiling` | **0.10** | Max HMI for Tier 2 (adapted from SEED's 0.05) |
| `elevation_band_m` | **300.0** | ±m elevation filter for Tier 2 |
| `min_reference_pixels` | **5** | SEED minimum before fallback cascade |
| `reference_buffer_km` | 100 | Default radius (per-indicator overrides apply) |
| `ndvi_year` / `lst_year` | 2025 | Remote sensing year |
| `raster_paths['edna_points_asset']` | None | GEE FC asset path for HSAS eDNA points |

---

## Agroforestry Projects — Multi-Cluster Support

For agroforestry projects with spatially dispersed farm parcels, run DBSCAN cluster-based aggregation.

**Workflow:**
1. DBSCAN (eps=2000m, min_samples=3) on farm centroids → N cluster KMLs + `manifest.json`
2. Set `PROJECT_TYPE = "agroforestry"` and `MANIFEST_FILE` in Cell 8
3. Cell 10 loops over clusters, aggregates with area-weighted formula:
```
project_value = Σ(cluster_value × area_ha) / Σ area_ha
```
Applied to `site_value`, `tier1_intactness`, and `tier2_intactness` for each indicator independently. Tier 2 aggregation only uses clusters where Tier 2 succeeded; clusters with Tier 2 failures contribute only to Tier 1 aggregation.

**For conservation projects** (`PROJECT_TYPE = "conservation"`): notebook behaviour is unchanged — single KML, single pipeline run, no aggregation.

---

## Trajectory Tracking (Year 1+)

Supports longitudinal monitoring for restoration and agroforestry projects. Scientifically aligned with SBTN AR3T Step 4 (trajectory reporting alongside status reporting).

- `IS_BASELINE_RUN = True` (Year 0): saves `baseline_scorecard.csv`
- `IS_BASELINE_RUN = False` (Year 1+): computes `delta_site_value`, `delta_intactness`, `trajectory_label`; computes trajectory columns per indicator

**Trajectory columns added at Year 1+:**

| Column | Definition |
|--------|-----------|
| `delta_site_value` | `current_site_value − baseline_site_value` |
| `delta_intactness` | `current_intactness − baseline_intactness` (Tier 2 preferred, Tier 1 fallback) |
| `trajectory_label` | `Improving` / `Stable` / `Declining` |

**Thresholds for `trajectory_label`:**
- Raster indices: ±2% intactness change
- Protocol A / count indicators: ±0.05 absolute change in site_value

**Year 0:** Trajectory columns are blank. `baseline_scorecard.csv` is written to `OUTPUT_DIR`.

**Year 1+:** Trajectory columns populated and printed in the notebook output. `trajectory.csv` downloaded alongside the main scorecard.

**Protocol A/B/C thresholds and SoN formula are unchanged** — trajectory is an additional layer, not a replacement for the existing concern levels.

---

## Package Architecture (v3.0)

```
darukaa_reference/
├── registry.py          — IndicatorSpec: name, tier2_eligible, higher_is_better,
│                          reference_radius_km, pillar, metadata
├── config.py            — hmi_hard_ceiling=0.10, elevation_band_m=300, min_reference_pixels=5
├── reference.py         — Tier 1 + Tier 2 engine; fc_tier1_fn + gee_image_fn hooks
└── indicators/__init__.py — v6.5: 44 indicators
    Terrestrial core (v6.3): ndvi, habitat_health, flii, eii×4, bii, pdf, aridity_index,
      natural_habitat, natural_landcover, cpland, forest_loss_rate, kba_overlap,
      endemic_richness, flagship_habitat, threatened_richness, ceri, star_t,
      ghm, light_pollution, hdi, lst_day, lst_night
    Aquatic & eDNA (v6.4): tspi, sabf, wcpi, wsdi, hsas, edpp, mspl, rci, sdi, stsi, iri
    Terrestrial vegetation + plants (v6.5): riparian_ndvi_trend, jrc_water_persistence,
      shdi, lai, chm, endemic_plant_richness, threatened_plant_richness, ivsi

    Key design decisions:
    • tier2_eligible=False: all aquatic/eDNA/plant/scalar indicators
    • flii: reference_radius_km=150
    • tspi: raw NDCI returned (not rescaled); higher_is_better=False
    • hsas: requires edna_points_asset; falls back to habitat suitability if absent
    • wsdi: higher_is_better=False (peak at 0.5 occurrence = most unstable)
    • shdi: scalar only — no spatial map; pillar=2 condition
    • stsi: site-relative normalization only — not cross-site comparable
    • ivsi: NDVI expansion proxy, not taxonomic invasion detection
    • endemic_plant_richness: range < 100,000 km², distinct by sci_name
    • threatened_plant_richness: CR/EN/VU, returns n_CR/n_EN/n_VU counts
    • RCI citation corrected: Naiman & Decamps (1997), not MacArthur/Wilson
```

---

## Validated Results — Paglam Community Reserve, Arunachal Pradesh

*(25-indicator run, v2.0 terrestrial indicators only)*

| Indicator | Site Value | T1% | T2% | Concern |
|-----------|-----------|-----|-----|---------|
| Natural Habitat Extent | 96.0% | 96.0% | 96.0% | VL |
| Natural Land Cover | 87.4% | 87.4% | 87.4% | VL |
| CPLAND | 88.2% | 100% | — | VL (Protocol C) |
| Habitat Loss Rate | 0.28%/yr | 100% | 100% | VL |
| KBA/IBA Overlap | 100% | — | — | VH (Protocol A) |
| NDVI | 0.613 | 93.3% | 72.9% | L |
| HHI | 2.47 | 57.2% | 25.2% | VH ‡ |
| FLII | 7.57 | 75.9% | 75.9% | L (Protocol A) |
| EII | 0.468 | 100% | 97.0% | VL |
| BII | 0.845 | 97.7% | 93.9% | VL (Protocol A) |
| Aridity Index | 2.897 | 100% | 83.6% | L |
| Endemic Richness | ~48 spp | 100% | — | VH (Protocol C, SAR artefact) |
| Threatened Richness | 13 spp | 100% | — | VL (Protocol C) |
| CERI | 0.106 | — | — | L (Protocol A) |
| STAR_T | 0.008 | — | — | VL (Protocol A) |

**SoN Score: ~2.7/10 — Very Low concern** (provisional; Protocol B v1.0)

‡ HHI VH: Tier 2 reference selects primary old-growth pixels. Community reserve at 25% of primary forest reference is ecologically expected — report as "below primary forest reference."

§ PDF H: Tier 2 reference (0.10) reflects pure forest pixels. Site value (0.286) may reflect MODIS 500m boundary mixing.

---

## Known Limitations

**Species-Area Relationship artefact:** Endemic and Threatened Richness Protocol C reference uses raw count in 100km buffer. Fix is density normalisation (species/km²) — flagged for next revision.

**SHDI is scalar-only:** Returns a single dimensionless value per site. No spatial map. Use for lake morphometric reporting only.

**HSAS without eDNA data:** Falls back to habitat suitability surface mean. The returned value is NOT a true HSAS. Clearly flagged in extraction metadata.

**IVSI detects expansion, not invasion:** NDVI increase >0.2 could be native regeneration. Requires ground truth to interpret as invasive spread.

**STSI is site-relative:** Not comparable across sites. Use only for within-site temporal comparison or relative pixel mapping.

**FLII** is an approximation (Dynamic World 10m forest mask + VIIRS), not the official Grantham et al. 2020 dataset. As of v4.0, returns explicit "Not Applicable" (not silent `None`) on non-forest sites below 10% forest-class fraction — see "v4.0 — 10m Resolution Migration" above.

**CPLAND** is India-only (Darukaa PV binary).

**CHM / GEDI coverage gaps:** GEDI L2A has latitudinal coverage limits and cloud/vegetation penetration gaps. Sites with sparse GEDI passes may return None.

**LAI MODIS 500m:** Sites smaller than ~1 km² may have insufficient pixels. (LAI remains on MODIS — it is a structural canopy index sourced from a dedicated product, MCD15A3H, not a classification layer, so it was out of scope for the v4.0 DW migration.)

**Minimum recommended site area: ~1 km²:** Sites smaller than 1 km² may return None for remaining coarser-resolution indicators (LAI/MODIS 500m, gHM 1km). As of v4.0, `natural_landcover`, `pdf`, `flii`, and `hdi` no longer have this limitation — they now resolve reliably down to single-DW-pixel scale (~0.01 ha).

**Flagship Habitat** normalisation ceiling (50 threatened birds) is provisional. Requires validation across Eastern Himalayan and other ecoregion types.

**Aquatic threat thresholds (sdi, stsi, iri, ivsi):** No published absolute thresholds exist — these are reported as raw values only, not scored.

**UHII**, **MSA (GLOBIO)**, **STAR_R** (restoration), and **Vegetation Drought Stress Index** are WIP or deferred — not yet registered.

**PDF returning None for non-forest sites (resolved in v4.0):** `_img_pdf` previously used MODIS LC and, before that, masked CF=0 pixels entirely, causing water/barren/unmatched-class sites to return None. As of v4.0, PDF runs on Dynamic World 10m with no mask — CF=0 pixels (water, bare, snow/ice) correctly contribute 0 to the mean rather than being excluded.

**Species-Area Relationship (SAR) artefact — count indicators:** Endemic Richness and Threatened Richness Protocol C reference uses raw species count in the Tier 1 buffer (100km radius). A small site polygon always has fewer species than a large buffer. Fix is density normalisation (species/km²). Flagged for next methodology revision. Current Protocol C results for these indicators should carry interpretation caveats.
**`forest_loss_rate` Tier 2 warning always fires:** Hansen forest loss Tier 2 requires pixels with both forest baseline and HMI ≤ ceiling. In agricultural or mixed landscapes these rarely exist. This warning is expected correct behaviour, not a bug. The intactness ratio is now correctly set to 100% when site_value = 0 (zero forest loss at site), rather than returning `—`.

**`interpretation` column — context-specific messages:** The scorecard now distinguishes: (a) Protocol A indicators — assessed via absolute threshold, no spatial reference needed; (b) reference = 0 — regional landscape has no signal in that metric (e.g. Natural Land Cover in agricultural buffer); (c) Tier 2 unavailable — Tier 1 comparison applied; (d) no data — check site polygon size or GEE asset coverage.


---

## Status

Working prototype. Validated on Paglam Community Reserve (25 terrestrial indicators, pre-v4.0). Aquatic/eDNA suite and terrestrial vegetation/plant suite are code-complete but not yet validated on field sites. v4.0 resolution migration and direction-flag fixes are code-complete and registry-validated; pending a fresh end-to-end run against FCF Gujarat (Banaskantha) to confirm the "swallowed polygon" contradiction is resolved in practice.

**Repository:** github.com/G-auravSingh/reference-benchmarking
**Runtime:** Google Colab (`notebooks/run_pipeline.ipynb`)
**Files touched in v4.0:** `darukaa_reference/indicators/__init__.py` (10m DW migration, FLII precondition, direction-flag fixes), `README.md` (this file)
**Related:** State of Nature Module PRD v2.0 (`son_module_PRD_v2_0.html`)
**License:** Internal use — Darukaa.Earth

---

## References

**Core framework:**
- McElderry et al. (2024) EcoEvoRxiv DOI:10.32942/X2689N — SEED reference selection
- McNellie et al. (2020) Global Change Biology DOI:10.1111/gcb.15383
- Kennedy et al. (2019) Global Change Biology DOI:10.1111/gcb.14549 — HMI
- Hill et al. (2022) bioRxiv DOI:10.1101/2022.08.21.504707 — EII
- Newbold et al. (2016) Science DOI:10.1126/science.aaf2201 — BII / planetary boundary
- Butchart et al. (2007) PLoS ONE DOI:10.1371/journal.pone.0000140 — CERI
- Hansen et al. (2013) Science DOI:10.1126/science.1244693 — GFC v1.12
- Brown et al. (2022) Scientific Data DOI:10.1038/s41597-022-01307-4 — Dynamic World
- Grantham et al. (2020) Nature Communications DOI:10.1038/s41467-020-19493-3 — FLII
- Elvidge et al. (2017) Int J Remote Sensing DOI:10.1080/01431161.2017.1342050 — VIIRS
- Zanaga et al. (2022) ESA WorldCover DOI:10.5281/zenodo.7254221
- Wan et al. (2021) MODIS MOD11A1 DOI:10.5067/MODIS/MOD11A1.061
- Zomer et al. (2022) Scientific Data DOI:10.1038/s41597-022-01493-1 — Aridity
- Huijbregts et al. (2017) Int J LCA DOI:10.1007/s11367-016-1246-y — PDF/ReCiPe
- Farr et al. (2007) Reviews of Geophysics DOI:10.1029/2005RG000183 — SRTM
- Dinerstein et al. (2017) BioScience DOI:10.1093/biosci/bix014 — Ecoregions
- Mair et al. (2021) Nature Ecology & Evolution DOI:10.1038/s41559-021-01432-0 — STAR

**Aquatic & eDNA suite (v6.4):**
- Mishra S & Mishra DR (2012) RSE 117:394-405. DOI:10.1016/j.rse.2011.10.016 — TSPI/NDCI
- Hu C (2009) RSE 113:2118-2129. DOI:10.1016/j.rse.2009.05.012 — SABF/FAI
- Nechad B et al. (2010) RSE 114:1167-1177. DOI:10.1016/j.rse.2009.11.022 — WCPI turbidity
- Binding CE et al. (2018) L&O 63:1616-1629. DOI:10.1002/lno.10940 — WCPI Secchi
- Pekel JF et al. (2016) Nature 540:418-422. DOI:10.1038/nature20584 — WSDI / JRC GSW
- Elith J & Leathwick JR (2009) Annu Rev Ecol Evol Syst 40:677-697. DOI:10.1146/annurev.ecolsys.110308.120159 — HSAS
- Strickler KM et al. (2015) Environ Sci Technol 49:4209-4216. DOI:10.1021/es404734p — EDPP
- Roussel JM et al. (2015) Biol Conserv 183:50-58. DOI:10.1016/j.biocon.2014.11.038 — EDPP
- Shade A et al. (2012) Microb Ecol 63:795-805. DOI:10.1007/s00248-012-0159-y — MSPL
- Naiman RJ & Decamps H (1997) Annu Rev Ecol Syst 28:621-658. DOI:10.1146/annurev.ecolsys.28.1.621 — RCI
- Allan JD et al. (2002) BioScience 52:883-890. DOI:10.1641/0006-3568(2002)052[0883:UBAC]2.0.CO;2 — SDI
- Jimenez-Munoz JC et al. (2014) RSE 155:11-25. DOI:10.1016/j.rse.2013.08.027 — STSI
- Bellard C et al. (2016) Glob Change Biol 22:1869-1883. DOI:10.1111/gcb.13004 — IRI
- Mandrak NE & Cudmore B (2009) Can J Fish Aquat Sci 67:1135-1144. DOI:10.1139/F08-099 — IRI

**Terrestrial vegetation + plant species suite (v6.5):**
- Naiman RJ et al. (2005) TREE 20:312-318. DOI:10.1016/j.tree.2005.05.011 — Riparian NDVI trend
- Jennings E et al. (2003) Freshwater Biology 48:301-310. DOI:10.1046/j.1365-2427.2003.00988.x — SHDI
- Myneni RB et al. (2002) RSE 83:214-231. DOI:10.1016/S0034-4257(02)00074-3 — LAI
- Dubayah R et al. (2020) Sci Remote Sens 1:100002. DOI:10.1016/j.srs.2020.100002 — CHM/GEDI
- Paz-Kagan T et al. (2019) RSE 233:111396. DOI:10.1016/j.rse.2019.111396 — IVSI
- IUCN Standards and Petitions Committee (2022) Guidelines v15.1. DOI:10.2305/IUCN.CH.2022.24.en — Plant species indicators
