# Darukaa Reference Benchmarking Pipeline

**An indicator-agnostic framework for comparing project-site biodiversity metrics against ecoregion-specific reference benchmarks, feeding into the State of Nature Module scoring architecture.**

Developed by Gaurav Singh, Scientific Lead — Biodiversity Methodology, Darukaa.Earth

---

## The Problem This Solves

Every biodiversity indicator value is a number without meaning until you answer: **"Compared to what?"** An NDVI of 0.63 at a community reserve in Arunachal Pradesh needs context: is that good or degraded for this ecoregion?

This pipeline provides that context automatically, for any indicator, at any site. Its outputs are the scientific input to the **State of Nature Module**, which converts intactness ratios into VL/L/M/H/VH concern levels, dimension scores, and a site-level State of Nature Score (0–10) for TNFD/SBTN/CSRD disclosure.

---

## How It Works

For each site × indicator, the pipeline computes two tiers of reference comparison:

**Tier 1 — Regional Reference:** Extracts the indicator across a per-indicator buffer (25–150 km) around the site centroid. Gives regional landscape context.

**Tier 2 — Contemporary "Best-on-Offer" Reference:** Identifies the least-disturbed pixels within the same land-cover class and elevation band via three-way stratification:
- Same **land cover class** (Copernicus LC, 100m)
- Same **elevation band** (±300m, SRTM 30m DEM)
- Lowest **Human Modification Index** (HMI ≤ dynamic threshold, ceiling 0.10)

The **intactness ratio** compares site to reference on a 0–100% scale, accounting for indicator directionality:
- State indicators (NDVI, BII, EII — `higher_is_better=True`): `intactness = site / reference`, capped at 100%
- Pressure indicators (`higher_is_better=False`): `intactness = reference / site`, capped at 100%

**Tier 2 eligibility:** Threat/pressure indicators (`tier2_eligible=False`) skip Tier 2 entirely. Using HMI to select "least-disturbed" reference pixels for indicators that *are themselves* proxies for human disturbance is methodologically circular. Tier 1 regional comparison is the correct benchmark for all pressure indicators.

---

## Reference Selection Methodology

Adapted from the SEED biocomplexity framework (McElderry et al. 2024, Supplement S1.1), with elevation stratification added.

### Dynamic HMI Threshold (SEED Equation S1)

```
if P5(HMI) ≤ ceiling:    use P5
elif P3(HMI) ≤ ceiling:  use P3
else:                     use ceiling (0.10)
```

**Ceiling is 0.10** — adapted from SEED's 0.05 for buffer-scale analysis. At 25–150 km buffer scale, fewer than 5 qualifying pixels are frequently found at 0.05, triggering the entire fallback cascade. 0.10 corresponds to Kennedy et al.'s "low-impact" HMI class and is methodologically defensible.

### Fallback Cascade

If fewer than `min_reference_pixels=5` survive:
1. Drop land cover mask, keep elevation + buffer
2. Expand buffer progressively: 2×, 3×, 4× radius up to 200 km
3. Log warning — Tier 2 returns null for that indicator

### Elevation Stratification (addition beyond SEED)

Filters reference pixels to within ±300m of site elevation (SRTM 30m DEM). Prevents ecologically incomparable mountain/valley pixels from contaminating the reference. Not present in SEED's original methodology.

**Citation:** *"Reference areas were selected following the contemporary minimal-disturbance approach, adapted from the SEED biocomplexity framework (McElderry et al. 2024, Supplement S1.1). A dynamic HMI threshold (5th percentile, ceiling 0.10, adapted from SEED's 0.05 for buffer-scale analysis) was applied within same land cover × elevation band strata (±300m SRTM). Threat/pressure indicators were excluded from Tier 2 reference selection to avoid methodological circularity. See McNellie et al. (2020) for the conceptual framework."*

---

## Registered Indicators (25)

Organised under the TNFD Annex 2 measurement tree. `tier2_eligible=False` indicators receive Tier 1 only.

### Dim 1 — Ecosystem Extent (5 indicators)

| Indicator | Source | Radius | Tier 2 | Direction |
|-----------|--------|--------|--------|-----------|
| `natural_habitat` | Dynamic World 10m | 50 km | ✓ | Higher=better |
| `natural_landcover` | MODIS MCD12Q1 IGBP | 50 km | ✓ | Higher=better |
| `cpland` | Darukaa PV binary (India-only) | 30 km | ✗ | Higher=better |
| `forest_loss_rate` | Hansen GFC v1.12 (2001–2024) | 50 km | ✓ | Lower=better |
| `kba_overlap` | IUCN KBA Global | 50 km | ✗ | Higher=better |

### Dim 2 — Ecosystem Condition (10 indicators)

| Indicator | Source | Radius | Tier 2 | Threshold Protocol |
|-----------|--------|--------|--------|-------------------|
| `ndvi` | Sentinel-2 SCL-masked, annual median | 50 km | ✓ | Protocol B |
| `habitat_health` (HHI) | S2 NDVI time series (z5/σ) | 50 km | ✓ | Protocol B |
| `flii` | MODIS LC + VIIRS (approx.) | **150 km** | ✓ | Protocol A (Potapov) |
| `eii` | Landbanking Group 300m | 75 km | ✓ | Protocol B |
| `eii_structural` | Landbanking Group 300m | 75 km | ✓ | Protocol B |
| `eii_compositional` | Landbanking / IO BII 300m | 75 km | ✓ | Protocol B |
| `eii_functional` | Landbanking / actual:potential NPP | 75 km | ✓ | Protocol B |
| `bii` | IO 300m (primary) / PREDICTS NHM (fallback) | 75 km | ✓ | Protocol A (NHM) |
| `pdf` | MODIS LC + ReCiPe CFs | 50 km | ✓ | Protocol B |
| `aridity_index` | CHIRPS + TerraClimate | 50 km | ✓ | Protocol B |

### Dim 3 — Species Population Size (2 indicators)

| Indicator | Source | Radius | Tier 2 |
|-----------|--------|--------|--------|
| `endemic_richness` | IUCN mammal ranges (< 100,000 km²) | 100 km | ✗ |
| `flagship_habitat` | Forest × elevation × inverse pressure, bird ranges | 50 km | ✗ |

### Dim 4 — Species Extinction Risk (3 indicators)

| Indicator | Source | Radius | Tier 2 | Notes |
|-----------|--------|--------|--------|-------|
| `threatened_richness` | IUCN CR/EN/VU mammals + birds | 100 km | ✗ | Count |
| `ceri` | IUCN mammals + birds (null-filtered) | 100 km | ✗ | Weighted index |
| `star_t` | Bird ranges × habitat × threat | 100 km | ✗ | Abatement score |

### Threats & Pressures (5 indicators — contextual only, not in SoN score)

All `tier2_eligible=False`. Not included in SoN Score per TNFD Annex 2.

| Indicator | Source | Radius |
|-----------|--------|--------|
| `ghm` | CSP/HM GlobalHumanModification 1km | 50 km |
| `light_pollution` | VIIRS DNB monthly | 25 km |
| `hdi` | ESA WorldCover urban distance transform | 25 km |
| `lst_day` | MODIS MOD11A1 daily, annual mean | 25 km |
| `lst_night` | MODIS MOD11A1 night, annual mean | 25 km |

---

## EII Methodology (Landbanking Group)

Uses pre-computed EII from `projects/landler-open-data/assets/eii/global/eii_global_v1` (300m). Authoritative implementation of Hill et al. (2022).

**Structural Integrity:** Quality-weighted core area. HMI < 0.4 → habitat; eroded 300m → core; weighted by HMI class (pristine=4, semi-natural=1); averaged within 5km neighbourhood.

**Compositional Integrity:** Impact Observatory BII at 300m. Average abundance of originally-present species vs. undisturbed baseline.

**Functional Integrity:** Observed NPP vs. ML-modelled potential NPP. Weighted 2/3 magnitude + 1/3 seasonality.

**Aggregation:** `EII = M × FuzzySum(A, B)` where M = min(S, C, F) and FuzzySum(A,B) = A + B − A×B. Constrained by worst pillar, penalises cumulative degradation.

**BII source alignment:** BII uses Impact Observatory 300m (same as EII compositional) for both site and reference, ensuring consistent intactness ratios.

---

## State of Nature Scoring Architecture

Per **Darukaa State of Nature Module PRD v2.0** and **TNFD LEAP Annex 2**.

### Tier 1 — Per-Metric Concern Level

Numeric encoding: `VL=1 · L=2 · M=3 · H=4 · VH=5`

**Protocol A — Published literature thresholds (applied to raw site value):**

| Metric | VL | L | M | H | VH | Source |
|--------|----|----|----|----|-----|--------|
| BII | > 80% | 60–80% | 40–60% | 20–40% | ≤ 20% | NHM / TNFD Annex 2 |
| FLII | > 8.0 | 6.0–8.0 | 4.0–6.0 | 2.0–4.0 | ≤ 2.0 | Potapov et al. 2020 |
| MSA | > 0.8 | 0.6–0.8 | 0.4–0.6 | 0.2–0.4 | ≤ 0.2 | GLOBIO4 |
| Flagship Habitat | > 0.8 | 0.6–0.8 | 0.4–0.6 | 0.2–0.4 | ≤ 0.2 | HSI literature (higher=better) |
| CERI | < 0.10 | 0.10–0.20 | 0.20–0.35 | 0.35–0.50 | > 0.50 | Butchart et al. 2007 (lower=better) |
| STAR_T | 0 | 1–3 | 3–6 | 6–9 | > 9 | IUCN STAR methodology (lower=better) |
| KBA/IBA Overlap | < 1% | 1–25% | 25–75% | 75–99% | 100% | TNFD/IBAT disclosure scheme |

**Protocol B — Tier 2 intactness thresholds (applied to intactness %, direction already corrected):**
```
≥ 85% → VL    70–84% → L    50–69% → M    30–49% → H    < 30% → VH
```
If Tier 2 unavailable, falls back to Tier 1 intactness with lower confidence flag.

**Protocol B v1.0 — Fixed, version-controlled thresholds.** Scientific basis: the ≥85% Very Low boundary is consistent with Newbold et al. (2016) planetary boundary for BII (≈90% intactness), adjusted to 85% to allow for measurement uncertainty. The 70/50/30 breaks correspond to noticeably impacted, substantially degraded, and severely impaired ecosystem condition respectively, consistent with GLOBIO4 and SBTN degradation literature. Thresholds are version-controlled and subject to empirical review when ≥10 Darukaa-monitored sites across ≥3 ecoregion types are available for calibration — not before.

Protocol B (Tier 2 intactness) applies to: natural_habitat, natural_landcover, forest_loss_rate, ndvi, habitat_health, eii (all components), pdf, aridity_index.

Protocol A (published absolute thresholds) applies to: bii, flii, msa, flagship_habitat, ceri, star_t, kba_overlap.

Protocol C (Tier 1 regional, same B thresholds) applies to count/connectivity indicators where absolute thresholds are ecoregion-dependent: cpland, endemic_richness, threatened_richness. Note: count indicators are subject to the Species-Area Relationship artefact — see Known Limitations.

### Tier 2 — Dimension Score (1–5)

```
dim_score = mean(concern_numeric for all populated metrics in dimension)
```
Rounded to nearest 0.5:
`1.0–1.5=Very Low · 1.5–2.5=Low · 2.5–3.5=Moderate · 3.5–4.5=High · 4.5–5.0=Very High`

**Data sufficiency minimums (SoN PRD v2.0):**
- Dim 1: ≥ 2 of 5 metrics
- Dim 2: ≥ 3 of 12 metrics, must include ≥ 1 of: EII, BII, NDVI
- Dim 3: ≥ 2 of 6 metrics, Species Richness required
- Dim 4: ≥ 1 of 4 metrics, CERI or STAR_T required

At the current pipeline-only stage, dimension scores are computed from all indicators with populated data — no minimum metric constraints are enforced. Missing metrics are shown as n_pop/n_total so confidence is transparent. Data sufficiency rules from SoN PRD v2.0 (requiring Species Richness for Dim 3, CERI/STAR_T for Dim 4) will be enforced in the product UI layer once in-situ data is integrated.

### Tier 3 — State of Nature Score (0–10)

```
SoN_Score = (Σ dim_scores − is_min) / (is_max − is_min) × 10

Full formula (all 4 dims): (Σ − 4) / 16 × 10
is_min = 4   (4 × VL=1)
is_max = 20  (4 × VH=5)
```

When < 4 dimensions are populated, normalise against available dims and flag as partial score.

**Overall SoN concern thresholds:**
```
0–4 = Very Low · 4–5 = Low · 5–7 = Moderate · 7–8 = High · 8–10 = Very High
```

**Excluded from SoN Score:** Threats layer (gHM, light pollution, HDI, LST) — contextual only per TNFD Annex 2. In-situ indicators (species richness, acoustic health, etc.) — reported as standalone values, no spatial reference benchmark available.

---

## GEE Assets Required

| Asset | Indicator(s) | Access |
|-------|-------------|--------|
| `projects/landler-open-data/assets/eii/global/eii_global_v1` | EII + BII (primary) | Public |
| `projects/gaurav-singh-007/assets/bii-2020_v2-1-1` | BII (fallback only) | User upload |
| `projects/darukaa-earth130226/assets/RedList_Mammals_Terrestrial` | CERI, Threatened, Endemic | Darukaa |
| `projects/darukaa-earth130226/assets/RedList_Bird_IUCN_Category` | CERI, STAR_T, Flagship | Darukaa |
| `projects/darukaa-earth130226/assets/KBA_Global_POL_SEP25` | KBA/IBA Overlap | Darukaa |
| `projects/darukaa-earth-product/assets/biodiversity_India_PV_Binary_2025_Full_Mosaic` | CPLAND | Darukaa (India only) |

---

## Configuration (config.py)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `gee_project` | — | GEE project ID |
| `bii_gee_asset` | — | NHM BII GEE asset (fallback path) |
| `hmi_hard_ceiling` | **0.10** | Max HMI for Tier 2 (adapted from SEED's 0.05) |
| `elevation_band_m` | **300.0** | ±m elevation filter for Tier 2 |
| `min_reference_pixels` | **5** | SEED minimum before fallback cascade |
| `reference_buffer_km` | 100 | Default radius (per-indicator overrides apply) |
| `ndvi_year` / `lst_year` | 2024 | Remote sensing year |

---

## Package Architecture (current state)

### registry.py — IndicatorSpec fields
```python
@dataclass
class IndicatorSpec:
    name: str
    display_name: str
    source_type: str              # "gee" | "local_raster" | "api" | "in_situ"
    extract_fn: Callable
    unit: str = ""
    value_range: Tuple = (0.0, 1.0)
    citation: str = ""
    tier1_layer: Optional[str] = None
    tier2_eligible: bool = True   # False for all threat/pressure indicators
    higher_is_better: bool = True
    reference_radius_km: Optional[float] = None
    pillar: Optional[int] = None
    metadata: Dict = field(default_factory=dict)
```

### indicators/__init__.py — Key registration decisions
- `tier2_eligible=False`: cpland, kba_overlap, endemic_richness, flagship_habitat, threatened_richness, ceri, star_t, **ghm, light_pollution, hdi, lst_day, lst_night**
- `flii`: `reference_radius_km=150.0` (increased from 75 — forest-only indicator needs wider search)
- `ceri`: `.filter(ee.Filter.notNull([cat_col]))` applied before bird `.map()` to prevent null crash
- All EII components + BII: `reference_radius_km=75.0`
- All threat indicators: `tier2_eligible=False, higher_is_better=False`

### reference.py — Tier 2 logic
- Checks `spec.tier2_eligible` before entering `_compute_tier2()`
- HMI ceiling read from `config.hmi_hard_ceiling` (default 0.10)
- Elevation stratification (±`config.elevation_band_m`) applied in `_compute_tier2()`
- Fallback cascade: drop LC mask → expand buffer (2×, 3×, 4× up to 200km)
- `_intactness_ratio()` is directionality-aware: state=site/ref, pressure=ref/site
- `_compute_tier1()` now checks `metadata["fc_tier1_fn"]` when `_get_indicator_image()` returns None — enables Tier 1 for FeatureCollection-based indicators (endemic richness, threatened richness) that have no raster image

---

## Validated Results — Paglam Community Reserve, Arunachal Pradesh

All 25 indicators, no pipeline warnings. Post all bug fixes.

| Indicator | Site Value | T1 Ref | T1% | T2 Ref | T2% | Protocol B v1.0 concern |
|-----------|-----------|--------|-----|--------|-----|-------------------|
| Natural Habitat Extent | 96.7% | 100.0 | 96.7% | 100.0 | 96.7% | VL |
| Natural Land Cover | 87.4% | 100.0 | 87.4% | 100.0 | 87.4% | VL |
| CPLAND | 88.2% | — | — | — | — | — |
| Habitat Loss Rate | 0.28%/yr | 4.17%/yr | 100% | 4.17%/yr | 100% | VL |
| KBA/IBA Overlap | 100% | — | — | — | — | — |
| NDVI | 0.613 | 0.652 | 93.9% | 0.842 | 72.8% | L |
| HHI | 3.46 | 5.24 | 66.0% | 11.64 | 29.7% | H ‡ |
| FLII | 7.56 | 9.97 | 75.8% | 9.97 | 75.8% | L (Protocol A) |
| EII | 0.468 | 0.459 | 100% | 0.482 | 97.0% | VL |
| EII: Structural | 0.601 | 0.629 | 95.5% | 0.605 | 99.2% | VL |
| EII: Compositional | 0.845 | 0.865 | 97.7% | 0.900 | 93.9% | VL |
| EII: Functional | 0.499 | 0.557 | 89.6% | 0.333 | 100% | VL |
| BII | 0.845 | 0.865 | 97.7% | 0.900 | 93.9% | VL (Protocol A) |
| PDF | 0.286 | 0.300 | 100% | 0.100 | 34.9% | H § |
| Aridity Index | 2.897 | 2.739 | 100% | 3.466 | 83.6% | L |
| Endemic Richness | 3 spp | — | — | — | — | — |
| Flagship Habitat | 0.929 | — | — | — | — | — |
| Threatened Richness | 13 spp | — | — | — | — | — |
| CERI | 0.106 | — | — | — | — | — |
| STAR_T | — | — | — | — | — | — |
| gHM | 0.337 | 0.389 | 100% | — | — | Contextual |
| Light Pollution | 0.390 | 0.506 | 100% | — | — | Contextual |
| HDI | 0.000 | 0.863 | 100% | — | — | Contextual |
| LST Day | 23.7°C | 23.8°C | 100% | — | — | Contextual |
| LST Night | 15.7°C | 16.0°C | 100% | — | — | Contextual |

**‡ HHI H concern:** Tier 2 reference (11.64) selects old-growth primary forest with very high multi-year NDVI stability. A community reserve at 29.7% of primary forest reference is ecologically expected — historical use patterns, not acute degradation. Report as "below primary forest reference."

**§ PDF H concern:** Tier 2 reference (0.10) reflects pure forest LC pixels. Site PDF (0.286) may reflect MODIS 500m pixel mixing at community reserve boundary.

---

## Known Limitations & Open Issues

**Methodological:**
- FLII is an approximation (MODIS LC + VIIRS), not the official Grantham et al. 2020 dataset
- CPLAND is India-only (Darukaa PV binary mosaic)
- LST: pipeline uses annual mean; Darukaa team scripts use summer-only (Apr–Jun) — decision pending
- UHII and MSA (GLOBIO) are WIP, not yet registered
- **Species-Area Relationship (SAR) artefact — count indicators:** Endemic Richness and Threatened Richness use raw species count in the Tier 1 buffer (100km radius) as regional reference. A small site polygon always has fewer species than a large buffer by area alone, producing artificially low intactness ratios. The correct fix is density-normalisation (species per km²) rather than raw count. Current Protocol C results for these two indicators should be interpreted with caution. Flagged for next methodology revision.

**Engineering:**
- Repo structure nested (`darukaa_reference_v0.1.0/darukaa_reference/`) — flat cleanup pending
- Statistical tests (Hedges' g, permutation) scaffolded but not fully wired
- In-situ indicators out of scope — require field/bioacoustic data, handled in SoN Module

**Bugs fixed (session record):**
- HMI ceiling: 0.05 → 0.10
- Tier 2 exclusion: light_pollution, hdi, lst_day, lst_night set to `tier2_eligible=False`
- FLII radius: 75 → 150 km
- CERI birds: `.filter(ee.Filter.notNull([cat_col]))` before `.map()`
- Previously fixed: FLII MODIS data lag, Aridity CHIRPS year, CERI/CPLAND cross-project access, Hansen deprecated version

---

## Status

Working prototype. Validated on Paglam Community Reserve with 25 indicators, no warnings. SoN scoring implemented in notebook (provisional thresholds).

**Repository:** github.com/G-auravSingh/reference-benchmarking  
**Runtime:** Google Colab (`notebooks/run_pipeline.ipynb`)  
**Related:** State of Nature Module PRD v2.0 (`son_module_PRD_v2_0.html`)  
**License:** Internal use — Darukaa.Earth

---

## Methodology References

- McElderry et al. (2024) EcoEvoRxiv DOI:10.32942/X2689N
- McNellie et al. (2020) Global Change Biology DOI:10.1111/gcb.15383
- Yen et al. (2019) Ecological Applications DOI:10.1002/eap.1970
- Kennedy et al. (2019) Global Change Biology DOI:10.1111/gcb.14549 — HMI
- Hill et al. (2022) bioRxiv DOI:10.1101/2022.08.21.504707 — EII
- Newbold et al. (2016) Science DOI:10.1126/science.aaf2201 — BII / planetary boundary
- Hudson et al. (2017) Ecology and Evolution DOI:10.1002/ece3.2579 — PREDICTS
- Butchart et al. (2007) PLoS ONE DOI:10.1371/journal.pone.0000140 — CERI
- Hansen et al. (2013) Science DOI:10.1126/science.1244693 — GFC v1.12
- Brown et al. (2022) Scientific Data DOI:10.1038/s41597-022-01307-4 — Dynamic World
- Grantham et al. (2020) Nature Communications DOI:10.1038/s41467-020-19493-3 — FLII
- Elvidge et al. (2017) Int J Remote Sensing DOI:10.1080/01431161.2017.1342050 — VIIRS
- Zanaga et al. (2022) ESA WorldCover DOI:10.5281/zenodo.7254221
- Wan et al. (2021) MODIS MOD11A1 DOI:10.5067/MODIS/MOD11A1.061
- Zomer et al. (2022) Scientific Data DOI:10.1038/s41597-022-01493-1 — Aridity
- Huijbregts et al. (2017) Int J LCA DOI:10.1007/s11367-016-1246-y — PDF/ReCiPe
- Friedl et al. (2019) MODIS MCD12Q1 DOI:10.5067/MODIS/MCD12Q1.061
- Farr et al. (2007) Reviews of Geophysics DOI:10.1029/2005RG000183 — SRTM
- Dinerstein et al. (2017) BioScience DOI:10.1093/biosci/bix014 — Ecoregions
