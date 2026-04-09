# Darukaa Reference Benchmarking Pipeline

**An indicator-agnostic framework for comparing project-site biodiversity metrics against ecoregion-specific reference benchmarks.**

Developed by Gaurav Singh, Scientific Lead — Biodiversity Methodology, Darukaa.Earth

---

## The Problem This Solves

Every biodiversity indicator value is a number without meaning until you answer: **"Compared to what?"** An NDVI of 0.63 at a community reserve in Arunachal Pradesh needs context: is that good or degraded for this ecoregion?

This pipeline provides that context automatically, for any indicator, at any site.

---

## How It Works

For each site × indicator, the pipeline computes two tiers of reference comparison:

**Tier 1 — Regional Reference:** Extracts the indicator across a per-indicator buffer (25–100 km). Gives regional landscape context.

**Tier 2 — Contemporary "Best-on-Offer" Reference:** Identifies the top 5% least-disturbed pixels via three-way stratification:

- Same **land cover** class (Copernicus LC, 100m)
- Same **elevation band** (±300m, SRTM 30m DEM)
- Lowest 5% **Human Modification Index** (Kennedy et al. 2019)

The **intactness ratio** (site / reference for state indicators, reference / site for pressure indicators) tells you how the site compares on a 0–100% scale.

### Key Methodological Features

- **Indicator-agnostic:** Adding a new indicator = write an extraction function + register it.
- **Directionality-aware:** Correct intactness formula for state vs pressure indicators.
- **Per-indicator spatial scale:** 25–100 km buffers based on ecological process scale.
- **Elevation stratification:** Prevents altitude-confounded reference selection.
- **Landbanking Group EII integration:** Uses their authoritative pre-computed EII at 300m with full methodology.
- **Consistent data sources:** BII uses Impact Observatory 300m (via Landbanking) for both site extraction AND reference computation, preventing cross-product comparison artefacts.

### Reference Selection Methodology

Our reference selection is **our own implementation**, inspired by and building on published frameworks:

- **McNellie et al. (2020)** — The contemporary "best-on-offer" reference state concept: instead of comparing against a theoretical pristine baseline, compare against the best measurably intact habitat currently existing in the same landscape.
- **Yen et al. (2019)** — Statistical benchmarking framework for biodiversity indicators in variable environments.
- **Kennedy et al. (2019)** — Global Human Modification Index as the disturbance filter for identifying least-disturbed reference areas.

The specific implementation choices — 5% HMI percentile threshold, land cover stratification (Copernicus LC), elevation stratification (SRTM ±300m), per-indicator buffer radii, and buffer-based spatial extent (rather than full ecoregion polygons) — are ours, informed by the ecological rationale in these papers but not a direct reproduction of any single published protocol. Buffer-based extent was a pragmatic choice to avoid GEE computation timeouts with complex ecoregion geometries.

This approach should be cited as "Darukaa.Earth reference benchmarking methodology, following the contemporary reference state framework of McNellie et al. (2020)" rather than attributed to any single external methodology.

---

## Registered Indicators (20)

### Pillar 1 — Ecosystem Condition (9 metrics)

| Indicator | Source | Radius | Direction |
|-----------|--------|--------|-----------|
| `ndvi` — Vegetation Structure | Sentinel-2 (SCL mask) | 50 km | Higher=better |
| `lst_day` — Daytime Surface Temp | MODIS MOD11A1 daily | 25 km | Lower=better |
| `lst_night` — Nighttime Surface Temp | MODIS MOD11A1 night | 25 km | Lower=better |
| `natural_habitat` — Natural Habitat Extent | Dynamic World 10m | 50 km | Higher=better |
| `natural_landcover` — Natural Land Cover | MODIS MCD12Q1 IGBP | 50 km | Higher=better |
| `flii` — Forest Landscape Integrity | MODIS LC + VIIRS (approx.) | 75 km | Higher=better |
| `aridity_index` — Aridity Index | CHIRPS + TerraClimate | 50 km | Higher=better |
| `habitat_health` — Greenness Stability | S2 NDVI time series (z5/σ) | 50 km | Higher=better |
| `cpland` — Core Landscape Connectivity | Darukaa PV binary 10m | 30 km | Higher=better |

### Pillar 3 — Species / Population (2 metrics)

| Indicator | Source | Radius | Direction |
|-----------|--------|--------|-----------|
| `bii` — Biodiversity Intactness Index | Impact Observatory 300m (primary) / PREDICTS NHM (fallback) | 75 km | Higher=better |

Note: BII uses the same Impact Observatory 300m product for both site extraction AND Tier 1/Tier 2 reference computation. This ensures intactness ratios are methodologically consistent — comparing like with like.
| `ceri` — Composite Extinction-Risk Index | IUCN mammal ranges (Darukaa asset) | 100 km | Lower=better |

### Pillar 4 — Threats & Pressures (5 metrics)

| Indicator | Source | Radius | Direction |
|-----------|--------|--------|-----------|
| `ghm` — Global Human Modification | CSP/HM | 50 km | Lower=better |
| `forest_loss_rate` — Habitat Loss Rate | Hansen GFC v1.12 (2001–2024) | 50 km | Lower=better |
| `pdf` — Potentially Disappeared Fraction | MODIS LC + ReCiPe CFs | 50 km | Lower=better |
| `light_pollution` — VIIRS Nighttime Lights | VIIRS DNB Monthly | 25 km | Lower=better |
| `hdi` — Human Disturbance Index | ESA WorldCover urban distance | 25 km | Lower=better |

### Ecosystem Integrity (4 metrics — EII + components)

| Indicator | Source | Description |
|-----------|--------|-------------|
| `eii` — Ecosystem Integrity Index | Landbanking Group (300m) | Composite: min × fuzzy_sum aggregation |
| `eii_structural` — Structural Integrity | Landbanking Group (300m) | Quality-weighted core area; HMI quality classes, 300m erosion, 5km neighbourhood |
| `eii_compositional` — Compositional Integrity | Landbanking Group (300m) | Impact Observatory BII — species abundance relative to pristine baseline |
| `eii_functional` — Functional Integrity | Landbanking Group (300m) | Actual / potential NPP deviation + seasonality integrity |

---

## EII Methodology (Landbanking Group)

The pipeline uses the pre-computed EII from the Landbanking Group's open GEE asset. This is the authoritative implementation of the Hill et al. (2022) framework.

### Three Pillars

**Structural Integrity:** Uses a quality-weighted core area approach. Pixels with HMI < 0.4 are classified as habitat, eroded by 300m to identify core (interior, edge-free) areas, quality-weighted by HMI class (pristine → 4, semi-natural → 1), and averaged within a 5km neighbourhood. Captures fragmentation and configuration, not just habitat amount.

**Compositional Integrity:** Uses Impact Observatory's BII at 300m resolution. This measures the average abundance of originally-present species relative to an undisturbed baseline.

**Functional Integrity:** Compares observed NPP (from Copernicus/Sentinel-3) against machine-learning-modelled potential NPP trained on pristine/protected areas. Combines magnitude deviation (proportional + absolute scoring) with seasonality integrity (observed vs natural intra-annual variability). Weighted 2/3 magnitude + 1/3 seasonality.

### Aggregation

Following Liebig's Law of the Minimum:

**EII = M × FuzzySum(A, B)**

where M = min(Structural, Compositional, Functional) and A, B are the other two components. FuzzySum(A, B) = A + B − A×B. This ensures the score is constrained by the worst pillar but penalises cumulative multi-pillar degradation.

### BII Source Alignment

When the Landbanking asset is available (default), BII uses Impact Observatory data at 300m — the same source used inside EII's compositional component. This ensures consistency. When the asset is unavailable, the pipeline falls back to PREDICTS/NHM BII at ~10km with appropriate warnings.

### Fallback Behaviour

If the Landbanking GEE asset (`projects/landler-open-data/assets/eii/global/eii_global_v1`) is inaccessible, the pipeline falls back to a simplified approximation using 1−gHM (structural), PREDICTS BII (compositional), normalised MODIS NPP (functional), and simple minimum aggregation. Warnings are logged documenting the methodological differences.

---

## Validated Result — Paglam Community Reserve, Arunachal Pradesh

| Indicator | Site Value | T1 Ref | T1 Intactness | T2 Ref | T2 Intactness |
|-----------|-----------|--------|---------------|--------|---------------|
| Vegetation (NDVI) | 0.630 | 0.675 | 93.3% | 0.729 | 86.3% |
| Biodiversity Intactness (BII) | 0.845 | — | — | — | — |
| Ecosystem Integrity (EII) | 0.468 | — | — | — | — |
| EII: Structural | 0.601 | — | — | — | — |
| EII: Compositional | 0.845 | — | — | — | — |
| EII: Functional | 0.499 | — | — | — | — |
| Natural Habitat Extent | 96.0% | 100% | 96.0% | 100% | 96.0% |
| Natural Land Cover | 87.4% | 100% | 87.4% | 100% | 87.4% |
| Human Modification (gHM) | 0.337 | 0.389 | 100% | — | — |
| Habitat Loss Rate | 0.29%/yr | 4.35%/yr | 100% | 4.35%/yr | 100% |
| Light Pollution | 0.34 | 0.45 | 100% | 0.31 | 90.5% |
| LST Day | 22.6°C | 23.0°C | 100% | 23.1°C | 100% |
| LST Night | 17.3°C | 17.5°C | 100% | 17.0°C | 98.4% |
| Habitat Health (HHI) | 2.47 | 4.32 | 57.2% | 5.69 | 43.4% |
| Human Disturbance (HDI) | 0.00 | 0.86 | 100% | 0.86 | 100% |

### Ecological Interpretation

Paglam Community Reserve shows strong structural condition (gHM low, natural habitat at 96%, near-zero human disturbance), with EII structural integrity at 0.60. Compositional integrity is high at 0.85 (IO BII), but functional integrity is the weakest pillar at 0.50 — the ecosystem's NPP deviates significantly from its modelled potential. This drives the EII to 0.47 via the limiting-factor principle.

The habitat health index (HHI = greenness stability) at 43% of reference is notably low, suggesting temporal NDVI instability despite decent overall NDVI. This could indicate edge effects, selective logging, or seasonal disturbance not captured by single-date indicators.

---

## Architecture

```
KML/KMZ → SiteLoader → EcoregionResolver → ReferenceSelector → ReportGenerator
                                                    ↑
                                             IndicatorRegistry
                                          (indicator-agnostic core)
```

### Package Structure

```
darukaa_reference/
├── __init__.py, registry.py, config.py
├── site_loader.py, ecoregion.py
├── reference.py          # Tier 1 + Tier 2 (elevation-stratified)
├── statistics.py, report.py, pipeline.py
└── indicators/
    └── __init__.py       # 20 registered indicators
```

---

## Quick Start

```bash
pip install -e .
```

```python
from darukaa_reference import Pipeline
pipeline = Pipeline.from_yaml("config.yaml")
report = pipeline.run("project_sites.kml")
```

Or use Google Colab: `notebooks/run_pipeline.ipynb`

---

## Adding a Custom Indicator

```python
registry.register(
    name="soil_carbon",
    display_name="Soil Organic Carbon",
    source_type="gee",
    extract_fn=your_extraction_function,
    reference_radius_km=50.0,
    higher_is_better=True,
    pillar=1,
)
```

---

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `gee_project` | — | Your GEE project ID |
| `bii_gee_asset` | — | GEE asset for NHM BII (fallback) |
| `reference_buffer_km` | 100 | Fallback radius (per-indicator overrides) |
| `elevation_band_m` | 300.0 | ±m elevation filter for Tier 2 |
| `raster_paths["iucn_mammals"]` | Darukaa asset | IUCN mammal range maps for CERI |
| `raster_paths["pv_binary"]` | Darukaa asset | PV binary raster for CPLAND (India) |

---

## Data Dependencies

All core indicators use freely available GEE datasets. Three indicators depend on Darukaa-specific or uploaded assets:

| Indicator | Asset | Access |
|-----------|-------|--------|
| BII (fallback) | NHM PREDICTS BII v2.1.1 | Upload to GEE project |
| CERI | IUCN mammal range maps | Darukaa GEE project |
| CPLAND | PV binary raster | Darukaa GEE project (India only) |
| EII + components | Landbanking Group | Open data — `projects/landler-open-data/assets/eii/global/eii_global_v1` |

---

## Methodology References

**Reference benchmarking:**
- McElderry, R.M. et al. (2024). EcoEvoRxiv. DOI:10.32942/X2689N
- McNellie, M.J. et al. (2020). Global Change Biology, 26(12). DOI:10.1111/gcb.15383
- Yen, J.D.L. et al. (2019). Ecological Applications, 29(7). DOI:10.1002/eap.1970

**Ecosystem Integrity Index:**
- Hill, S.L.L. et al. (2022). bioRxiv. DOI:10.1101/2022.08.21.504707
- Kennedy, C.M. et al. (2019). Global Change Biology, 25(3). DOI:10.1111/gcb.14549
- Gassert, F. et al. (2022). Impact Observatory BII.
- Miguet, P. et al. (2016). Landscape Ecology, 31(6). DOI:10.1007/s10980-016-0357-z
- Ries, L. et al. (2004). Annual Rev. Ecol. Evol. Syst., 35. DOI:10.1146/annurev.ecolsys.35.112202.130148

**Biodiversity & species:**
- Newbold, T. et al. (2016). Science, 353(6296). DOI:10.1126/science.aaf2201
- Hudson, L.N. et al. (2017). Ecology and Evolution, 7(1). DOI:10.1002/ece3.2579
- Butchart, S.H.M. et al. (2007). PLoS ONE, 2(1). DOI:10.1371/journal.pone.0000140

**Remote sensing & land cover:**
- Hansen, M.C. et al. (2013). Science, 342(6160). DOI:10.1126/science.1244693
- Brown, C.F. et al. (2022). Scientific Data, 9. DOI:10.1038/s41597-022-01307-4
- Elvidge, C.D. et al. (2017). Int. J. Remote Sensing, 38(21). DOI:10.1080/01431161.2017.1342050
- Zanaga, D. et al. (2022). ESA WorldCover. DOI:10.5281/zenodo.7254221
- Wan, Z. et al. (2021). MODIS MOD11A1. DOI:10.5067/MODIS/MOD11A1.061
- Zomer, R.J. et al. (2022). Scientific Data, 9. DOI:10.1038/s41597-022-01493-1
- Huijbregts, M.A.J. et al. (2017). Int J LCA, 22. DOI:10.1007/s11367-016-1246-y

**Spatial scale & elevation:**
- Thornton, D.H. et al. (2011). Landscape Ecology, 26. DOI:10.1007/s10980-010-9549-z
- Farr, T.G. et al. (2007). Reviews of Geophysics, 45. DOI:10.1029/2005RG000183
- Dinerstein, E. et al. (2017). BioScience, 67(6). DOI:10.1093/biosci/bix014

---

## Known Limitations

- **FLII** is a simplified approximation (MODIS LC + VIIRS), not the official Grantham et al. (2020) dataset.
- **CERI** and **CPLAND** use Darukaa-hosted GEE assets. Asset paths are configurable but may need updating for different GEE projects.
- **CPLAND** is India-only (Darukaa PV binary mosaic).
- **UHII** and **MSA (GLOBIO)** are work in progress and not yet included.
- **Acoustic indicators** (NDSI, ACI) cannot use satellite Tier 2 — require paired field recordings (future Tier 3).
- **Statistical tests** (Hedges' g, permutation tests) are scaffolded but not yet fully wired for all indicators.

---

## Status

Working prototype — validated on Paglam Community Reserve (Arunachal Pradesh) with 20 indicators. Requires engineering review, unit tests, and formal QA before production deployment.

**Repository:** github.com/G-auravSingh/reference-benchmarking
**Runtime:** Google Colab (`notebooks/run_pipeline.ipynb`)
**License:** Internal use — Darukaa.Earth
