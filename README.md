# Darukaa Reference Benchmarking Pipeline

**An indicator-agnostic framework for comparing project-site biodiversity metrics against ecoregion-specific reference benchmarks, feeding into the State of Nature Module scoring architecture.**

Developed by Gaurav Singh, Scientific Lead — Biodiversity Methodology, Darukaa.Earth

---

## What This Solves

Every biodiversity indicator value is a number without meaning until you answer: *"Compared to what?"* An NDVI of 0.63 at a community reserve in Arunachal Pradesh needs context: is that good or degraded for this ecoregion?

This pipeline provides that context automatically for any indicator at any site, then converts the results into TNFD-aligned concern levels and a State of Nature Score (0–10) for disclosure.

---

## How It Works

For each site × indicator:

**Tier 1 — Regional Reference:** Extracts the indicator across a per-indicator buffer (25–150 km) around the site centroid. Gives regional landscape context.

**Tier 2 — Contemporary "Best-on-Offer" Reference:** Identifies least-disturbed pixels within the same land-cover class and elevation band via three-way stratification — same land cover (Copernicus LC 100m), same elevation ±300m (SRTM), and HMI ≤ dynamic threshold (ceiling 0.10).

**Intactness ratio:** `site / reference` for state indicators (higher=better); `reference / site` for pressure indicators (lower=better). Direction-corrected by pipeline. Output: 0–100%.

**Tier 2 eligibility:** Threat/pressure indicators (`tier2_eligible=False`) skip Tier 2 entirely — using HMI to select "least-disturbed" reference pixels for indicators that *measure* human disturbance is circular. Tier 1 is their correct comparison.

**Tier 2 behaviour for agricultural/modified landscapes:** For sites where gHM > 0.4 throughout the buffer (e.g., active agroforestry zones in Odisha), no pixels meet the HMI ≤ 0.10 ceiling. Tier 2 correctly returns `insufficient reference pixels` for all eligible indicators. This is expected behaviour — not a bug. Output reports: *"Tier 2 unavailable — no minimally-modified reference pixels within buffer. Tier 1 regional comparison applied."*

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

## Registered Indicators (25)

### Dim 1 — Ecosystem Extent (5)

| Indicator | Source | Radius | Tier 2 | Direction |
|-----------|--------|--------|--------|-----------|
| `natural_habitat` | Dynamic World 10m | 50 km | ✓ | Higher=better |
| `natural_landcover` | MODIS MCD12Q1 IGBP | 50 km | ✓ | Higher=better |
| `cpland` | Darukaa PV binary (India-only) | 30 km | ✗ Protocol C | Higher=better |
| `forest_loss_rate` | Hansen GFC v1.12 (2001–2024) | 50 km | ✓ | Lower=better |
| `kba_overlap` | IUCN KBA Global | 50 km | ✗ Protocol A | Higher=better |

### Dim 2 — Ecosystem Condition (10)

| Indicator | Source | Radius | Tier 2 | Threshold |
|-----------|--------|--------|--------|-----------|
| `ndvi` | Sentinel-2 SCL-masked, annual median | 50 km | ✓ | Protocol B |
| `habitat_health` (HHI) | S2 NDVI time series z5/σ | 50 km | ✓ | Protocol B |
| `flii` | MODIS LC + VIIRS (approx.) | **150 km** | ✓ | Protocol A (Potapov) |
| `eii` | Landbanking Group 300m | 75 km | ✓ | Protocol B |
| `eii_structural` | Landbanking 300m | 75 km | ✓ | Protocol B |
| `eii_compositional` | Landbanking / IO BII 300m | 75 km | ✓ | Protocol B |
| `eii_functional` | Landbanking / actual:potential NPP | 75 km | ✓ | Protocol B |
| `bii` | IO 300m (primary) / PREDICTS NHM (fallback) | 75 km | ✓ | Protocol A (NHM) |
| `pdf` | MODIS LC + ReCiPe CFs | 50 km | ✓ | Protocol B |
| `aridity_index` | CHIRPS + TerraClimate (PET ×0.1 mm conversion) | 50 km | ✓ | Protocol B |

**Note on Aridity Index:** AI = P/PET is NOT bounded 0–1. Humid tropical forests have AI = 2–4 (rainfall exceeds PET). Values >1 are correct for wet regions. TerraClimate PET is stored in 0.1mm units and must be multiplied by 0.1 before dividing — failure to do this produces AI values 10× too low.

### Dim 3 — Species Population Size (2)

| Indicator | Source | Radius | Tier 2 | Notes |
|-----------|--------|--------|--------|-------|
| `endemic_richness` | IUCN mammals + IUCN birds (range < 100,000 km²) | 100 km | ✗ Protocol C | Both taxonomic groups |
| `flagship_habitat` | HSI × 0.6 + normalised species richness × 0.4 (birds + mammals) | 50 km | ✗ Protocol A | Composite; see below |

### Dim 4 — Species Extinction Risk (3)

| Indicator | Source | Radius | Tier 2 | Categories |
|-----------|--------|--------|--------|------------|
| `threatened_richness` | IUCN mammals + birds | 100 km | ✗ Protocol C | CR/EN/VU only |
| `ceri` | IUCN mammals + birds (null-filtered) | 100 km | ✗ Protocol A | All: EX/EW/CR/EN/VU/NT/LC |
| `star_t` | Bird + mammal ranges × habitat × threat pressure | 100 km | ✗ Protocol A | CR/EN/VU only |

**IUCN category consistency across indicators:**
- `threatened_richness`, `star_t`, `star_r`: CR/EN/VU only — strict TNFD threatened definition, equal weight per species
- `ceri`: All categories (EX/EW=5, CR=4, EN=3, VU=2, NT=1, LC=0) — NT intentionally included, CERI is a weighted index capturing full extinction risk spectrum
- `endemic_richness`: No category filter — endemism defined by range size (<100,000 km²), not threat status

### Threats & Pressures (5 — contextual only, not in SoN score)

All `tier2_eligible=False`. Not in SoN Score per TNFD Annex 2 design.

| Indicator | Source | Radius |
|-----------|--------|--------|
| `ghm` | CSP/HM GlobalHumanModification 1km | 50 km |
| `light_pollution` | VIIRS DNB monthly | 25 km |
| `hdi` | ESA WorldCover urban distance | 25 km |
| `lst_day` | MODIS MOD11A1 daily, annual mean | 25 km |
| `lst_night` | MODIS MOD11A1 night, annual mean | 25 km |

---

## Flagship Habitat Viability — Methodology Note

**Formula:** `HSI × 0.6 + bird_suit × 0.4`

where:
- `HSI` (0–1) = forest × elevation_suitability × inverse_light_pressure — structural habitat quality
- `species_suit` (0–1) = min((n_threatened_birds_CR/EN/VU + n_threatened_mammals_CR/EN/VU) / 50, 1.0) — normalised threatened species richness (birds + mammals per Mair et al. 2021)

**Rationale for composite:** Pure HSI answers "is this structurally suitable habitat?" The bird count component answers "do threatened species actually use it?" A site with HSI=0.93 and 0 threatened birds is ecologically different from one with HSI=0.93 and 45 threatened birds. The composite captures both dimensions.

**Normalisation:** Bird count is divided by 50 (provisional ceiling based on Eastern Himalayan regional context) before weighting, ensuring the index remains 0–1 bounded. The 50-species ceiling requires validation across sites and ecoregions.

**Field name:** `RedList__5` (double underscore) in the IUCN bird GEE asset.

---

## Species Lists

The pipeline captures species lists from the IUCN range maps for three indicators:

- **Threatened Richness:** All CR/EN/VU mammals and birds with ranges overlapping the site
- **CERI:** All IUCN-categorised mammals and birds, with their category recorded
- **Endemic Richness:** All small-ranged (<100,000 km²) mammals and birds

Species lists are returned in the `metadata` field of the extraction result and displayed in the notebook's species list cell. They are included in the `benchmark_scorecard_with_son.json` download. This supports TNFD LEAP Step 3 disclosure requirements for species-level evidence.

---

## EII Methodology (Landbanking Group)

Uses pre-computed EII from `projects/landler-open-data/assets/eii/global/eii_global_v1` (300m). Authoritative implementation of Hill et al. (2022).

**Structural:** Quality-weighted core area. HMI<0.4 → habitat; eroded 300m → core; weighted by HMI class; averaged in 5km neighbourhood.

**Compositional:** Impact Observatory BII 300m. Average abundance of originally-present species.

**Functional:** Observed NPP vs. ML-modelled potential NPP. 2/3 magnitude + 1/3 seasonality.

**Aggregation:** `EII = M × FuzzySum(A,B)` where M = min(S,C,F), FuzzySum(A,B) = A+B−A×B.

**BII alignment:** BII uses same IO 300m source as EII compositional for both site and reference.

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
| STAR_T | 0 | 1–3 | 3–6 | 6–9 | >9 | IUCN STAR methodology |
| KBA/IBA Overlap | <1% | 1–25% | 25–75% | 75–99% | 100% | TNFD/IBAT disclosure scheme |

**Protocol B v1.0 — Fixed, version-controlled thresholds (applied to Tier 2 intactness %):**
```
≥ 85% → VL  Basis: Newbold et al. 2016 planetary boundary (~90% BII)
70–84% → L   Noticeably impacted, recoverable (SBTN science)
50–69% → M   Substantially degraded — material loss (GLOBIO4)
30–49% → H   Severely impaired
< 30%  → VH  Critically impaired
```
Protocol B applies to: natural_habitat, natural_landcover, forest_loss_rate, ndvi, habitat_health, eii (all components), pdf, aridity_index.

**Protocol C — Tier 1 regional comparison (same B thresholds applied to Tier 1 intactness):**
For count/connectivity indicators where absolute thresholds are ecoregion-dependent: cpland, endemic_richness, threatened_richness. ⚠️ Count indicators subject to Species-Area Relationship artefact — see Known Limitations.

**Version:** Protocol B v1.0. Review trigger: ≥10 Darukaa sites across ≥3 ecoregion types.

### Dimension Scoring

```
dim_score = mean(concern_numeric for all populated metrics in dimension)
```
Rounded to nearest 0.5 → Very Low / Low / Moderate / High / Very High.

No minimum metric constraints at current pipeline stage. Missing metrics shown as n/N.

### SoN Score Formula

```
SoN_Score = (Σ dim_scores − n_dims) / (n_dims × 4) × 10
Full (4 dims): (Σ − 4) / 16 × 10   [SoN PRD v2.0, normalized sum]
```
Output: 0–10. Concern levels: 0–4=Very Low, 4–5=Low, 5–7=Moderate, 7–8=High, 8–10=Very High.

**Threats excluded from SoN Score** per TNFD Annex 2. In-situ indicators (species richness, acoustic health) reported as standalone values — no spatial reference benchmark available from this pipeline.

**Threat indicator categorical labels** (absolute thresholds, shown in notebook threat assessment block):

| Indicator | Very Low | Low | Moderate | High | Very High | Source |
|-----------|----------|-----|----------|------|-----------|--------|
| gHM | < 0.10 | 0.10–0.25 | 0.25–0.40 | 0.40–0.60 | > 0.60 | Kennedy et al. 2019 |
| Light Pollution (nW/cm²/sr) | < 0.05 | 0.05–0.5 | 0.5–5.0 | 5.0–50 | > 50 | Falchi et al. 2016 |
| HDI | < 0.10 | 0.10–0.30 | 0.30–0.60 | 0.60–0.80 | > 0.80 | ESA WorldCover proxy |
| LST Day/Night | Reported as ±°C deviation from Tier 1 regional mean | | | | | Context-dependent |

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

**Bird asset field name:** `RedList__5` (double underscore). Mammal asset uses `category`.

---

## Configuration (config.py)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `hmi_hard_ceiling` | **0.10** | Max HMI for Tier 2 (adapted from SEED's 0.05) |
| `elevation_band_m` | **300.0** | ±m elevation filter for Tier 2 |
| `min_reference_pixels` | **5** | SEED minimum before fallback cascade |
| `reference_buffer_km` | 100 | Default radius (per-indicator overrides apply) |
| `ndvi_year` / `lst_year` | 2024 | Remote sensing year |

---

## Agroforestry Projects — Multi-Cluster Support

For agroforestry projects with spatially dispersed farm parcels (e.g., 335 farms across multiple Odisha blocks), running a single union polygon through the pipeline produces ecologically incoherent results because the centroid buffer mixes many unrelated landscapes. The correct approach is DBSCAN cluster-based aggregation.

**Workflow:**

1. The generalised PAM site selection pipeline (separate codebase) runs DBSCAN (eps=2000m, min_samples=3) on all farm centroids and outputs N cluster KMLs + a `manifest.json` with per-cluster area weights.

2. In the notebook, set `PROJECT_TYPE = "agroforestry"` and `MANIFEST_FILE` to your manifest path (Cell 8). The manifest format is:
```json
[{"cluster_id": "cluster_01", "kml_path": "/content/cluster_01.kml", "area_ha": 142.3}, ...]
```

3. Cell 10 loops over clusters internally, runs the full pipeline for each, then area-weighted aggregates into one project scorecard before passing to SoN scoring. No CSV round-trip required — the aggregation happens inside the notebook.

**Area-weighted aggregation formula:**
```
project_value = Σ(cluster_value × area_ha) / Σ area_ha
```
Applied to `site_value`, `tier1_intactness`, and `tier2_intactness` for each indicator independently. Tier 2 aggregation only uses clusters where Tier 2 succeeded; clusters with Tier 2 failures contribute only to Tier 1 aggregation.

**For conservation projects** (`PROJECT_TYPE = "conservation"`): notebook behaviour is unchanged — single KML, single pipeline run, no aggregation.

---

## Trajectory Tracking (Year 1+)

Supports longitudinal monitoring for restoration and agroforestry projects. Scientifically aligned with SBTN AR3T Step 4 (trajectory reporting alongside status reporting).

**Configuration:**
- `IS_BASELINE_RUN = True` (Year 0): runs normally, saves `baseline_scorecard.csv` alongside other outputs
- `IS_BASELINE_RUN = False` (Year 1+): loads `baseline_scorecard.csv`, computes trajectory columns per indicator

**Trajectory columns added at Year 1+:**

| Column | Definition |
|--------|-----------|
| `delta_site_value` | `current_site_value − baseline_site_value` |
| `delta_intactness` | `current_intactness − baseline_intactness` (Tier 2 preferred, Tier 1 fallback) |
| `trajectory_label` | `Improving` / `Stable` / `Declining` |

**Thresholds for `trajectory_label`:**
- Raster indices (NDVI, EII, BII, FLII, PDF, AI, HHI, CPLAND): ±2% intactness change
- Protocol A / count indicators (CERI, STAR_T, Flagship, Endemic Richness, Threatened Richness): ±0.05 absolute change in site_value

**Year 0:** Trajectory columns are blank. `baseline_scorecard.csv` is written to `OUTPUT_DIR`.

**Year 1+:** Trajectory columns populated and printed in the notebook output. `trajectory.csv` downloaded alongside the main scorecard.

**Protocol A/B/C thresholds and SoN formula are unchanged** — trajectory is an additional layer, not a replacement for the existing concern levels.

---

## Package Architecture (current state)

```
darukaa_reference/
├── registry.py          — IndicatorSpec: name, tier2_eligible, higher_is_better,
│                          reference_radius_km, pillar, metadata
├── config.py            — hmi_hard_ceiling=0.10, elevation_band_m=300, min_reference_pixels=5
├── reference.py         — Tier 1 + Tier 2 engine
│                          • tier2_eligible check before Tier 2
│                          • metadata["fc_tier1_fn"] hook for FeatureCollection Tier 1
│                            (endemic richness — mammals+birds, threatened richness — mammals+birds)
│                          • metadata["gee_image_fn"] for custom image builders
│                          • Fallback cascade: drop LC → expand buffer → warn
└── indicators/__init__.py — 25 indicators, key decisions:
    • tier2_eligible=False: cpland, kba_overlap, endemic_richness, flagship_habitat,
      threatened_richness, ceri, star_t, ghm, light_pollution, hdi, lst_day, lst_night
    • flii: reference_radius_km=150 (forest-only, needs wider search area)
    • threatened_richness: higher_is_better=False; uses both mammals + birds
    • ceri: ee.Filter.notNull([cat_col]) before bird .map(); mammals + birds; NT included
    • endemic_richness: mammals + birds; species list returned in metadata
    • threatened_richness: species list returned in metadata
    • flagship_habitat: HSI*0.6 + normalised_bird_count*0.4; RedList__5 (double underscore)
    • Bird asset field: RedList__5 (double underscore) — confirmed from GEE asset schema
    • Aridity Index: TerraClimate PET multiplied by 0.1 to convert 0.1mm units → mm
```

---

## Validated Results — Paglam Community Reserve, Arunachal Pradesh

| Indicator | Site Value | T1 Ref | T1% | T2 Ref | T2% | Concern |
|-----------|-----------|--------|-----|--------|-----|---------|
| Natural Habitat Extent | 96.0% | 100.0 | 96.0% | 100.0 | 96.0% | VL |
| Natural Land Cover | 87.4% | 100.0 | 87.4% | 100.0 | 87.4% | VL |
| CPLAND | 88.2% | 1.0 | 100% | — | — | VL (Protocol C) |
| Habitat Loss Rate | 0.28%/yr | 4.17%/yr | 100% | 4.17%/yr | 100% | VL |
| KBA/IBA Overlap | 100% | — | — | — | — | VH (Protocol A — high importance) |
| NDVI | 0.613 | 0.675 | 93.3% | 0.864 | 72.9% | L |
| HHI | 2.47 | 4.32 | 57.2% | 9.80 | 25.2% | VH ‡ |
| FLII | 7.57 | 9.98 | 75.9% | 9.98 | 75.9% | L (Protocol A) |
| EII | 0.468 | 0.459 | 100% | 0.482 | 97.0% | VL |
| EII Structural | 0.601 | 0.629 | 95.5% | 0.605 | 99.2% | VL |
| EII Compositional | 0.845 | 0.865 | 97.7% | 0.900 | 93.9% | VL |
| EII Functional | 0.499 | 0.557 | 89.6% | 0.333 | 100% | VL |
| BII | 0.845 | 0.865 | 97.7% | 0.900 | 93.9% | VL (Protocol A) |
| PDF | 0.286 | 0.300 | 100% | 0.100 | 34.9% | H § |
| Aridity Index | 2.897 | 2.739 | 100% | 3.466 | 83.6% | L |
| Endemic Richness | ~48 spp | — | — | — | — | VH (Protocol C, SAR artefact) |
| Flagship Habitat | ~0.56 | 0.894 | 100% | — | — | L (Protocol A) |
| Threatened Richness | 13 spp | 26 | 100% | — | — | VL (Protocol C) |
| CERI | 0.106 | — | — | — | — | L (Protocol A) |
| STAR_T | 0.008 | — | — | — | — | VL (Protocol A) |
| gHM | 0.337 | 0.389 | 100% | — | — | Contextual |
| Light Pollution | 0.341 | 0.449 | 100% | — | — | Contextual |
| HDI | 0.000 | 0.863 | 100% | — | — | Contextual |
| LST Day | 22.6°C | 22.9°C | 100% | — | — | Contextual |
| LST Night | 17.3°C | 17.5°C | 100% | — | — | Contextual |

**SoN Score: ~2.7/10 — Very Low concern** (provisional; Protocol B v1.0 thresholds)

‡ HHI VH: Tier 2 reference selects primary old-growth pixels. Community reserve at 25% of primary forest reference is ecologically expected — report as "below primary forest reference."

§ PDF H: Tier 2 reference (0.10) reflects pure forest pixels. Site value (0.286) may reflect MODIS 500m boundary mixing.

---

## Known Limitations

**PDF returning None for non-forest sites:** `_img_pdf` previously used `.updateMask(cf)` which masked pixels where characterisation factor (CF) = 0. Sites dominated by water, barren, wetland, or unmatched MODIS LC classes had no unmasked pixels → `reduceRegion` returned None. Fixed by removing the mask — CF=0 pixels now contribute 0 to the mean. A site with pure shrubland (CF=0.20) correctly returns PDF≈0.20; a site with water (CF=0) correctly returns PDF=0.00.

**Species-Area Relationship (SAR) artefact — count indicators:** Endemic Richness and Threatened Richness Protocol C reference uses raw species count in the Tier 1 buffer (100km radius). A small site polygon always has fewer species than a large buffer. Fix is density normalisation (species/km²). Flagged for next methodology revision. Current Protocol C results for these indicators should carry interpretation caveats.

**FLII** is an approximation (MODIS LC + VIIRS), not the official Grantham et al. 2020 dataset.

**CPLAND** is India-only (Darukaa PV binary mosaic). Tier 1 reference = mean PV binary proportion in 30km buffer (binary 0/1 raster, not true CPLAND landscape metric).

**Flagship Habitat** normalisation ceiling (50 threatened birds) is provisional. Requires validation across Eastern Himalayan and other ecoregion types.

**LST:** Annual mean used. Soudipta's scripts use summer-only (Apr–Jun). Decision pending.

**UHII** and **MSA (GLOBIO)** are WIP, not yet registered.

**STAR_R** (restoration) not yet implemented in pipeline. When implemented, use birds + mammals per Mair et al. (2021).

**Bugs fixed (session record):**
- HMI ceiling: 0.05 → 0.10
- Threat indicators: tier2_eligible=True → False (light_pollution, hdi, lst_day, lst_night)
- FLII radius: 75 → 150 km
- CERI birds: .filter(ee.Filter.notNull([cat_col])) before .map()
- Endemic richness: mammals only → mammals + birds
- Threatened richness: higher_is_better corrected to False
- fc_tier1_fn hook added to reference.py for FeatureCollection Tier 1
- Flagship habitat: pure HSI → normalised composite (HSI×0.6 + bird_norm×0.4)
- STAR_T: extended to birds + mammals (per Mair et al. 2021 taxonomic scope)
- Flagship: species_suit now uses birds + mammals CR/EN/VU count
- Species lists now returned in extraction metadata
- Aridity Index: our PET ×0.1 conversion confirmed correct; Soudipta's script missing conversion (10× error)
- Agroforestry multi-cluster support: Cell 10 now loops over DBSCAN cluster KMLs with area-weighted aggregation
- Trajectory layer: Cells 16 + 20 now support baseline write (Year 0) and delta computation (Year 1+)
- Tier 2 failure for agricultural landscapes documented as correct behaviour, not error

---

## Status

Working prototype. Validated on Paglam Community Reserve with 25 indicators, no pipeline warnings. SoN scoring implemented with Protocol B v1.0 fixed thresholds.

**Repository:** github.com/G-auravSingh/reference-benchmarking
**Runtime:** Google Colab (`notebooks/run_pipeline.ipynb`)

**Notebook cells changed in this release:**
- **Cell 8 (Configuration):** Added `PROJECT_TYPE`, `IS_BASELINE_RUN`, `MANIFEST_FILE`, `BASELINE_FILE` config variables
- **Cell 10 (Run pipeline):** Added agroforestry cluster loop + area-weighted aggregation; conservation path unchanged
- **Cell 12 (Scorecard display):** Shows cluster metadata columns for agroforestry runs
- **Cell 16 (Dimension scores):** Added trajectory computation block (baseline write + delta calculation)
- **Cell 20 (Download):** Downloads `baseline_scorecard.csv` on Year 0 runs; downloads `trajectory.csv` on Year 1+ runs

**Core package files unchanged:** `reference.py`, `registry.py`, `config.py`, `indicators/__init__.py`
**Related:** State of Nature Module PRD v2.0 (`son_module_PRD_v2_0.html`)
**License:** Internal use — Darukaa.Earth

---

## References

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
- Mair et al. (2021) Nature Ecology & Evolution DOI:10.1038/s41559-021-01432-0 — STAR metric (birds + mammals scope)
