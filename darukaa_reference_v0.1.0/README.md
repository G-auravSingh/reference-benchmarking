# Darukaa Reference Benchmarking Pipeline

**An indicator-agnostic framework for comparing project-site biodiversity metrics against ecoregion-specific reference benchmarks.**

Developed by Gaurav Singh, Scientific Lead — Biodiversity Methodology, Darukaa.Earth

---

## The Problem This Solves

Every biodiversity indicator value — NDVI, MSA, BII, acoustic indices — is a number without meaning until you answer: **"Compared to what?"** An NDVI of 0.63 at an agroforestry site in Arunachal Pradesh needs context: is that good or degraded for this ecoregion? How does it compare to the best intact vegetation nearby?

This pipeline provides that context automatically, for any indicator, at any site.

---

## How It Works

The pipeline takes a KML/KMZ file of project sites as input and, for each site × indicator, computes two tiers of reference comparison:

**Tier 1 — Regional Reference:** Extracts the indicator value across a configurable buffer around the site (per-indicator radius: 25–100 km depending on ecological scale). Gives regional landscape context.

**Tier 2 — Contemporary "Best-on-Offer" Reference (SEED-style):** Within the same buffer, identifies the top 5% least-disturbed pixels using the Global Human Modification Index (Kennedy et al. 2019), stratified by land cover type AND elevation band (±300m via SRTM DEM). Extracts the indicator from only those reference pixels. This is what intact, comparable habitat looks like in the site's landscape today.

The **intactness ratio** (site / reference, or reference / site for pressure indicators) tells you how the site compares on a 0–100% scale.

### Key Methodological Features

- **Indicator-agnostic:** Adding a new indicator requires only writing an extraction function and registering it. No pipeline changes.
- **Directionality-aware:** State indicators (NDVI, BII — higher is better) and pressure indicators (gHM, LST, noise — lower is better) are handled with the correct intactness formula.
- **Per-indicator spatial scale:** Each indicator uses an ecologically appropriate buffer radius (e.g., 25 km for LST to avoid elevation confounding, 100 km for macroecological metrics like MSA).
- **Elevation stratification:** Reference pixels are filtered to within ±300m of the site's elevation using SRTM 30m DEM, preventing ecologically incomparable high/low altitude pixels from contaminating the reference.
- **Three-way stratification for Tier 2:** Same land cover × same elevation band × lowest 5% human modification.

---

## Validated Result — Paglam Community Reserve, Arunachal Pradesh

| Indicator | Site Value | Tier 1 Ref | T1 Intactness | Tier 2 Ref | T2 Intactness |
|-----------|-----------|------------|---------------|------------|---------------|
| Vegetation Structure (NDVI) | 0.628 | 0.675 | 93.0% | 0.729 | 86.1% |
| Biodiversity Intactness Index | 0.406 | 0.457 | 88.7% | 0.606 | 67.0% |
| Ecosystem Integrity Index | 0.260 | 0.366 | 71.2% | 0.511 | 51.0% |
| Global Human Modification | 0.337 | 0.389 | 100% | — | — |
| Land Surface Temperature | 23.5°C | 23.9°C | 100% | 23.8°C | 100% |

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
├── site_loader.py       # KML/KMZ/GeoJSON/Shapefile → GeoDataFrame (Z-strip)
├── ecoregion.py         # WWF RESOLVE Ecoregions 2017 spatial join
├── reference.py         # Tier 1 + Tier 2 reference selection engine
├── statistics.py        # Hedges' g, permutation tests, bootstrap CIs
├── report.py            # JSON + CSV scorecard generator
├── pipeline.py          # Orchestrator
└── indicators/
    └── __init__.py      # 7 pre-registered indicators + GEE image builders
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

Open `notebooks/run_pipeline.ipynb` and follow the cells. Upload your KML, configure indicators, run.

### 4. Programmatic usage

```python
from darukaa_reference import Pipeline

pipeline = Pipeline.from_yaml("config.yaml")
report = pipeline.run("project_sites.kml")
```

---

## Pre-registered Indicators

| # | Name | Source | Pillar | Radius | Direction | Citation |
|---|------|--------|--------|--------|-----------|----------|
| 1 | `ndvi` | Sentinel-2 (GEE) | 1 | 50 km | Higher=better | Drusch et al. (2012) |
| 2 | `lst` | MODIS MOD11A2 (GEE) | 1 | 25 km | Lower=better | Wan et al. (2021) |
| 3 | `msa_globio4` | GLOBIO4 (local raster) | 3 | 100 km | Higher=better | Schipper et al. (2020) |
| 4 | `bii` | PREDICTS/NHM (GEE asset) | 3 | 75 km | Higher=better | Newbold et al. (2016) |
| 5 | `eii` | Composite (GEE) | 1 | 75 km | Higher=better | Hill et al. (2022) |
| 6 | `seed` | SEED (local raster) | 1 | 100 km | Higher=better | McElderry et al. (2024) |
| 7 | `ghm` | CSP/HM (GEE) | 4 | 50 km | Lower=better | Kennedy et al. (2019) |

### Adding a Custom Indicator

```python
registry.register(
    name="acoustic_health",
    display_name="Acoustic Health (NDSI)",
    source_type="in_situ",
    extract_fn=your_ndsi_function,
    reference_radius_km=10.0,     # Soundscape operates at 1-10 km
    higher_is_better=True,
    pillar=2,
    citation="Kasten et al. (2012). Ecological Informatics.",
)
```

---

## Configuration

Key parameters in `config.yaml` or passed programmatically:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `gee_project` | — | Your GEE project ID |
| `bii_gee_asset` | — | GEE asset path for NHM BII raster |
| `reference_buffer_km` | 100 | Fallback buffer radius (per-indicator overrides) |
| `hmi_percentile_threshold` | 5.0 | Top N% least-disturbed = reference |
| `elevation_band_m` | 300.0 | ±m elevation filter for reference selection |
| `min_reference_pixels` | 20 | Minimum pixels for valid Tier 2 reference |

---

## Methodology References

- McElderry, R.M. et al. (2024). Assessing the multidimensional complexity of biodiversity using a globally standardized approach. *EcoEvoRxiv*. DOI:10.32942/X2689N
- McNellie, M.J. et al. (2020). Reference state and benchmark concepts for better biodiversity conservation in contemporary ecosystems. *Global Change Biology*, 26(12), 6702–6714. DOI:10.1111/gcb.15383
- Yen, J.D.L. et al. (2019). Modeling biodiversity benchmarks in variable environments. *Ecological Applications*, 29(7), e01970. DOI:10.1002/eap.1970
- Schipper, A.M. et al. (2020). Projecting terrestrial biodiversity intactness with GLOBIO 4. *Global Change Biology*, 26(2), 760–771. DOI:10.1111/gcb.14848
- Newbold, T. et al. (2016). Has land use pushed terrestrial biodiversity beyond the planetary boundary? *Science*, 353(6296), 288–291. DOI:10.1126/science.aaf2201
- Hudson, L.N. et al. (2017). The database of the PREDICTS project. *Ecology and Evolution*, 7(1), 145–188. DOI:10.1002/ece3.2579
- Kennedy, C.M. et al. (2019). Managing the middle. *Global Change Biology*, 25(3), 811–826. DOI:10.1111/gcb.14549
- Hill, S.L.L. et al. (2022). The Ecosystem Integrity Index. *bioRxiv*. DOI:10.1101/2022.08.21.504707
- Farr, T.G. et al. (2007). The Shuttle Radar Topography Mission. *Reviews of Geophysics*, 45, RG2004. DOI:10.1029/2005RG000183
- Dinerstein, E. et al. (2017). An Ecoregion-Based Approach to Protecting Half the Terrestrial Realm. *BioScience*, 67(6), 534–545. DOI:10.1093/biosci/bix014
- Thornton, D.H. et al. (2011). Landscape Ecology, 26, 7–18. DOI:10.1007/s10980-010-9549-z

---

## Known Limitations

- **BII (PREDICTS)** is at ~10 km resolution — coarse for small sites. The pipeline handles this via centroid sampling, but the value represents a landscape-scale estimate, not site-level precision.
- **EII** uses a simplified fuzzy-minimum of three components. The full Landbanking Group implementation includes additional refinements (Local Modulation for fine-grained improvements).
- **Two key references are preprints** (SEED: McElderry et al. 2024; EII: Hill et al. 2022). Track publication status.
- **Acoustic indicators** cannot use satellite-based Tier 2 references. They require paired field recordings at reference sites identified via the same HMI methodology.
- **Statistical tests** (Hedges' g, permutation tests) require pixel-level data from both site and reference, which is available for GEE indicators but not yet for coarse local rasters.

---

## Status

Working prototype — validated on Paglam Community Reserve (Arunachal Pradesh). Requires engineering review, unit tests, and formal QA before production deployment.

## License

Internal use — Darukaa.Earth
