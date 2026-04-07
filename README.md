# Darukaa Reference Benchmarking Pipeline

**An indicator-agnostic framework for comparing project-site biodiversity metrics against ecoregion-specific reference benchmarks.**

Developed by Gaurav Singh, Scientific Lead — Biodiversity Methodology, Darukaa.Earth

---

## The Problem This Solves

Every biodiversity indicator value — NDVI, BII, MSA, acoustic indices — is a number without meaning until you answer: **"Compared to what?"** An NDVI of 0.63 at a community reserve in Arunachal Pradesh needs context: is that good or degraded for this ecoregion? How does it compare to the best intact vegetation nearby?

This pipeline provides that context automatically, for any indicator, at any site.

---

## How It Works

The pipeline takes a KML/KMZ file of project sites and, for each site × indicator, computes two tiers of reference comparison:

**Tier 1 — Regional Reference:** Extracts the indicator across a per-indicator buffer around the site (25–100 km depending on ecological scale). Gives regional landscape context — what the indicator looks like on average in the surrounding area.

**Tier 2 — Contemporary "Best-on-Offer" Reference (SEED-style):** Within the same buffer, identifies the top 5% least-disturbed pixels using three-way stratification:

- Same **land cover** class (Copernicus Land Cover, 100m)
- Same **elevation band** (±300m, SRTM 30m DEM)
- Lowest 5% **Human Modification Index** (Kennedy et al. 2019)

The **intactness ratio** (site / reference for state indicators, reference / site for pressure indicators) tells you how the site compares on a 0–100% scale.

### Key Methodological Features

- **Indicator-agnostic:** Adding a new indicator = write an extraction function + register it. No pipeline changes.
- **Directionality-aware:** State indicators (NDVI, BII — higher is better) and pressure indicators (gHM, light pollution — lower is better) use the correct intactness formula automatically.
- **Per-indicator spatial scale:** Each indicator uses an ecologically appropriate reference radius, from 25 km (LST, light pollution) to 100 km (macroecological metrics).
- **Elevation stratification:** Prevents ecologically incomparable high/low altitude pixels from contaminating the reference.

---

## Registered Indicators (17)

### Pillar 1 — Ecosystem Condition (9 metrics)

| Indicator | GEE Source | Radius | Direction | Citation |
|-----------|-----------|--------|-----------|----------|
| `ndvi` — Vegetation Structure | Sentinel-2 (SCL cloud mask) | 50 km | Higher=better | Drusch et al. (2012) |
| `lst_day` — Daytime Surface Temp | MODIS MOD11A1 daily | 25 km | Lower=better | Wan et al. (2021) |
| `lst_night` — Nighttime Surface Temp | MODIS MOD11A1 night | 25 km | Lower=better | Wan et al. (2021) |
| `natural_habitat` — Natural Habitat Extent | Dynamic World 10m | 50 km | Higher=better | Brown et al. (2022) |
| `natural_landcover` — Natural Land Cover | MODIS MCD12Q1 IGBP | 50 km | Higher=better | Friedl et al. (2019) |
| `flii` — Forest Landscape Integrity | MODIS LC + VIIRS (approx.) | 75 km | Higher=better | Grantham et al. (2020)* |
| `aridity_index` — Aridity Index | CHIRPS + TerraClimate | 50 km | Higher=better | Zomer et al. (2022) |
| `habitat_health` — Greenness Stability (HHI) | Sentinel-2 NDVI time series | 50 km | Higher=better | Darukaa methodology |
| `cpland` — Core Landscape Connectivity | Darukaa PV binary 10m | 30 km | Higher=better | McGarigal & Marks (1995) |

### Pillar 3 — Species / Population Status (2 metrics)

| Indicator | GEE Source | Radius | Direction | Citation |
|-----------|-----------|--------|-----------|----------|
| `bii` — Biodiversity Intactness Index | NHM PREDICTS (GEE asset) | 75 km | Higher=better | Newbold et al. (2016); Hudson et al. (2017) |
| `ceri` — Composite Extinction-Risk Index | IUCN mammal ranges (Darukaa asset) | 100 km | Lower=better | Butchart et al. (2007) |

### Pillar 4 — Threats & Pressures (5 metrics)

| Indicator | GEE Source | Radius | Direction | Citation |
|-----------|-----------|--------|-----------|----------|
| `ghm` — Global Human Modification | CSP/HM | 50 km | Lower=better | Kennedy et al. (2019) |
| `forest_loss_rate` — Habitat Loss Rate | Hansen GFC v1.11 | 50 km | Lower=better | Hansen et al. (2013) |
| `pdf` — Potentially Disappeared Fraction | MODIS LC + ReCiPe CFs | 50 km | Lower=better | Huijbregts et al. (2017) |
| `light_pollution` — VIIRS Nighttime Lights | VIIRS DNB Monthly | 25 km | Lower=better | Elvidge et al. (2017) |
| `hdi` — Human Disturbance Index | ESA WorldCover urban distance | 25 km | Lower=better | Zanaga et al. (2022) |

### Composite (1 metric)

| Indicator | Components | Radius | Direction | Citation |
|-----------|-----------|--------|-----------|----------|
| `eii` — Ecosystem Integrity Index | Structural (gHM) + Compositional (BII) + Functional (NPP) | 75 km | Higher=better | Hill et al. (2022) |

*\*FLII is a simplified approximation using MODIS LC + VIIRS nightlights, not the official Grantham et al. (2020) dataset.*

---

## Validated Result — Paglam Community Reserve, Arunachal Pradesh

| Indicator | Site Value | Tier 1 Ref | T1 Intactness | Tier 2 Ref | T2 Intactness |
|-----------|-----------|------------|---------------|------------|---------------|
| Vegetation Structure (NDVI) | 0.628 | 0.675 | 93.0% | 0.729 | 86.1% |
| Biodiversity Intactness (BII) | 0.406 | 0.457 | 88.7% | 0.606 | 67.0% |
| Ecosystem Integrity (EII) | 0.260 | 0.366 | 71.2% | 0.511 | 51.0% |
| Global Human Modification | 0.337 | 0.389 | 100% | — | — |
| Land Surface Temperature | 23.5°C | 23.9°C | 100% | 23.8°C | 100% |

**Ecological interpretation:** Structural recovery without compositional recovery — vegetation is 86% of best available but species assemblage only 67%. EII at 51% is driven by BII as the weakest component via the fuzzy minimum principle. Common pattern in community forests.

---

## Architecture

```
KML/KMZ → SiteLoader → EcoregionResolver → ReferenceSelector → StatisticalComparison → ReportGenerator
                                                    ↑
                                             IndicatorRegistry
                                          (indicator-agnostic core)
```

### Package Structure

```
darukaa_reference/
├── __init__.py          # Package root + methodology citations
├── registry.py          # IndicatorSpec + IndicatorRegistry
├── config.py            # YAML config loader
├── site_loader.py       # KML/KMZ/GeoJSON → GeoDataFrame (Z-coordinate stripping)
├── ecoregion.py         # WWF RESOLVE Ecoregions 2017 spatial join
├── reference.py         # Tier 1 + Tier 2 reference engine (elevation-stratified)
├── statistics.py        # Hedges' g, permutation tests, bootstrap CIs
├── report.py            # JSON + CSV scorecard
├── pipeline.py          # Orchestrator
└── indicators/
    └── __init__.py      # 17 registered indicators + GEE builders
```

---

## Quick Start

### 1. Install

```bash
pip install -e .
```

### 2. Authenticate GEE

```bash
earthengine authenticate
```

### 3. Run on Google Colab

Open `notebooks/run_pipeline.ipynb` and follow cells. Upload your KML, configure, run.

### 4. Programmatic usage

```python
from darukaa_reference import Pipeline
pipeline = Pipeline.from_yaml("config.yaml")
report = pipeline.run("project_sites.kml")
```

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
    citation="Hengl, T. et al. (2017). SoilGrids250m. PLoS ONE.",
)
```

No pipeline changes needed. The reference engine, statistical comparison, and report generator work automatically.

---

## Configuration

Key parameters (set in `config.yaml` or programmatically):

| Parameter | Default | Description |
|-----------|---------|-------------|
| `gee_project` | — | Your GEE project ID |
| `bii_gee_asset` | — | GEE asset path for NHM BII raster |
| `reference_buffer_km` | 100 | Fallback buffer radius (overridden per-indicator) |
| `hmi_percentile_threshold` | 5.0 | Top N% least-disturbed = reference |
| `elevation_band_m` | 300.0 | ±m elevation filter for Tier 2 |
| `ndvi_year` | 2024 | Year for NDVI, VIIRS, Dynamic World, etc. |
| `lst_year` | 2024 | Year for LST day/night |

---

## Data Source Dependencies

| Category | Source | Access | Resolution |
|----------|--------|--------|------------|
| Ecoregions | WWF RESOLVE 2017 | GEE (free) | Ecoregion polygons |
| Cloud-free imagery | Sentinel-2 SR Harmonized | GEE (free) | 10 m |
| Land surface temp | MODIS MOD11A1 v061 | GEE (free) | 1 km |
| Land cover | Dynamic World / MODIS MCD12Q1 | GEE (free) | 10 m / 500 m |
| Human modification | CSP gHM | GEE (free) | 1 km |
| Forest change | Hansen GFC v1.11 | GEE (free) | 30 m |
| Nighttime lights | VIIRS DNB Monthly | GEE (free) | 500 m |
| Urban cover | ESA WorldCover v200 | GEE (free) | 10 m |
| Precipitation | CHIRPS Daily | GEE (free) | 5 km |
| Evapotranspiration | TerraClimate | GEE (free) | 4 km |
| Biodiversity intactness | NHM PREDICTS BII v2.1.1 | GEE asset (upload) | ~10 km |
| Net primary productivity | MODIS MOD17A3HGF | GEE (free) | 500 m |
| Elevation | SRTM v3 | GEE (free) | 30 m |
| IUCN species ranges | Red List mammals | GEE asset (Darukaa) | Vector polygons |
| PV binary | Darukaa India mosaic | GEE asset (Darukaa) | 10 m |

---

## Methodology References

**Reference benchmarking:**
- McElderry, R.M. et al. (2024). Assessing the multidimensional complexity of biodiversity. *EcoEvoRxiv*. DOI:10.32942/X2689N
- McNellie, M.J. et al. (2020). Reference state and benchmark concepts. *Global Change Biology*, 26(12), 6702–6714. DOI:10.1111/gcb.15383
- Yen, J.D.L. et al. (2019). Modeling biodiversity benchmarks. *Ecological Applications*, 29(7), e01970. DOI:10.1002/eap.1970

**Indicator-specific:**
- Newbold, T. et al. (2016). *Science*, 353(6296), 288–291. DOI:10.1126/science.aaf2201
- Hudson, L.N. et al. (2017). *Ecology and Evolution*, 7(1), 145–188. DOI:10.1002/ece3.2579
- Kennedy, C.M. et al. (2019). *Global Change Biology*, 25(3), 811–826. DOI:10.1111/gcb.14549
- Hill, S.L.L. et al. (2022). *bioRxiv*. DOI:10.1101/2022.08.21.504707
- Grantham, H.S. et al. (2020). *Nature Communications*, 11, 5978. DOI:10.1038/s41467-020-19493-3
- Hansen, M.C. et al. (2013). *Science*, 342(6160), 850–853. DOI:10.1126/science.1244693
- Huijbregts, M.A.J. et al. (2017). *Int J LCA*, 22, 138–147. DOI:10.1007/s11367-016-1246-y
- Brown, C.F. et al. (2022). *Scientific Data*, 9, 251. DOI:10.1038/s41597-022-01307-4
- Elvidge, C.D. et al. (2017). *Int. J. Remote Sensing*, 38(21), 5860–5879. DOI:10.1080/01431161.2017.1342050
- Zomer, R.J. et al. (2022). *Scientific Data*, 9, 409. DOI:10.1038/s41597-022-01493-1
- Butchart, S.H.M. et al. (2007). *PLoS ONE*, 2(1), e140. DOI:10.1371/journal.pone.0000140
- Zanaga, D. et al. (2022). ESA WorldCover 10m v200. DOI:10.5281/zenodo.7254221
- Dinerstein, E. et al. (2017). *BioScience*, 67(6), 534–545. DOI:10.1093/biosci/bix014
- Farr, T.G. et al. (2007). *Reviews of Geophysics*, 45, RG2004. DOI:10.1029/2005RG000183
- Thornton, D.H. et al. (2011). *Landscape Ecology*, 26, 7–18. DOI:10.1007/s10980-010-9549-z

**Statistical methods:**
- Cohen, J. (1988). *Statistical Power Analysis for the Behavioral Sciences* (2nd ed.). Erlbaum.
- Hedges, L.V. (1981). *Journal of Educational Statistics*, 6(2), 107–128.

---

## Known Limitations

- **FLII** is a simplified approximation (MODIS LC + VIIRS), not the official Grantham et al. (2020) dataset which is not available on GEE.
- **CERI** uses Darukaa-hosted IUCN mammal range maps. May need asset path update for other GEE projects. Returns `None` if asset is inaccessible.
- **CPLAND** uses a Darukaa India-specific PV binary raster. India-only; asset path needs updating for other regions.
- **BII** (PREDICTS) is ~10 km resolution — the pipeline uses centroid sampling for small sites.
- **SEED and EII** references are preprints (McElderry et al. 2024; Hill et al. 2022). Track publication status.
- **Acoustic indicators** (NDSI, ACI) cannot use satellite Tier 2. They require paired field recordings (future Tier 3).
- **UHII and MSA (GLOBIO)** are work in progress and not yet included.
- **Statistical tests** (Hedges' g, permutation tests) are scaffolded but require pixel-level data not yet fully wired for all indicators.

---

## Status

Working prototype — validated on Paglam Community Reserve (Arunachal Pradesh) with 5 indicators. 17 indicators registered; full validation pending on remaining 12. Requires engineering review, unit tests, and formal QA before production deployment.

**Repository:** github.com/G-auravSingh/reference-benchmarking
**Runtime:** Google Colab (notebooks/run_pipeline.ipynb)
**Data:** Google Earth Engine + NHM PREDICTS BII (GEE asset)

## License

Internal use — Darukaa.Earth
