# Darukaa Reference Benchmarking Pipeline

**An indicator-agnostic framework for comparing project-site biodiversity metrics against ecoregion-specific reference benchmarks.**

---

## What This Does

Every biodiversity indicator value (NDVI, MSA, BII, acoustic indices, etc.) is meaningless without context. An NDVI of 0.41 at an agroforestry site in Jharkhand needs to be compared against what healthy, intact vegetation looks like in the same ecoregion. This pipeline answers the question: **"Compared to what?"**

It implements two tiers of reference benchmarking:

- **Tier 1 — Global Modelled Reference**: Extracts indicator values from pre-computed global layers (GLOBIO4, BII, EII, SEED) across the entire ecoregion to establish a regional baseline.

- **Tier 2 — Contemporary Reference (SEED-style)**: Identifies the top 5% least-disturbed pixels within the same ecoregion × land-cover combination using the Global Human Modification Index, then extracts indicator values from these "best-on-offer" reference patches.

The result is an **intactness ratio** (site value / reference value) for each indicator, with full statistical backing (Hedges' g, permutation tests, bootstrap CIs).

---

## Architecture

```
KML/GeoJSON → SiteLoader → EcoregionResolver → ReferenceSelector → StatisticalComparison → ReportGenerator
                                                      ↑
                                               IndicatorRegistry
                                            (indicator-agnostic core)
```

**Adding a new indicator requires only:**
1. Writing an extraction function: `(geometry, config) → {"value": float}`
2. Calling `registry.register(name="my_indicator", extract_fn=my_fn, ...)`

No changes to core pipeline code. Ever.

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Authenticate Google Earth Engine

```bash
earthengine authenticate
```

### 3. Download local rasters (optional, for GLOBIO4 MSA and SEED)

- GLOBIO4 MSA: https://dataportaal.pbl.nl/downloads/GLOBIO/
- SEED Biocomplexity: https://zenodo.org/records/13799961

### 4. Configure

Edit `config.yaml` with your GEE project ID and raster paths.

### 5. Run

```bash
# Full pipeline with all indicators
python example_run.py --kml path/to/sites.kml --config config.yaml

# GEE-only mode (no local rasters needed)
python example_run.py --kml sites.kml --config config.yaml --gee-only

# Specific indicators only
python example_run.py --kml sites.kml --config config.yaml --indicators ndvi bii ghm
```

### 6. Programmatic usage

```python
from darukaa_reference import Pipeline

pipeline = Pipeline.from_yaml("config.yaml")
report = pipeline.run("project_sites.kml")
```

---

## Pre-registered Indicators

| # | Name | Display Name | Source | Pillar | Citation |
|---|------|-------------|--------|--------|----------|
| 1 | `ndvi` | Vegetation Structure (NDVI) | Sentinel-2 (GEE) | 1 | Drusch et al. (2012) RSE |
| 2 | `lst` | Land Surface Temperature | MODIS MOD11A2 (GEE) | 1 | Wan et al. (2021) |
| 3 | `msa_globio4` | Mean Species Abundance | GLOBIO4 (local raster) | 3 | Schipper et al. (2020) GCB |
| 4 | `bii` | Biodiversity Intactness Index | Impact Observatory (GEE) | 3 | Newbold et al. (2016) Science |
| 5 | `eii` | Ecosystem Integrity Index | Derived (GEE) | 1 | Hill et al. (2022) bioRxiv |
| 6 | `seed` | SEED Biocomplexity Index | Zenodo (local raster) | 1 | McElderry et al. (2024) |
| 7 | `ghm` | Global Human Modification | CSP/HM (GEE) | 4 | Kennedy et al. (2019) GCB |

---

## Adding Custom Indicators

```python
from darukaa_reference.indicators import create_default_registry

registry = create_default_registry()

def extract_my_metric(geometry, config):
    # Your extraction logic — could call an API, read a raster, query GEE
    return {"value": 0.75, "pixels": None}

registry.register(
    name="my_metric",
    display_name="My Custom Metric",
    source_type="api",
    extract_fn=extract_my_metric,
    unit="index",
    value_range=(0.0, 1.0),
    citation="Author et al. (Year). Journal. DOI:xxx",
    tier2_eligible=True,
    pillar=2,
)
```

---

## Output Format

The pipeline produces a JSON + CSV scorecard:

```json
{
  "meta": {
    "generated_at": "2026-03-21T12:00:00Z",
    "n_sites": 12,
    "n_indicators": 7,
    "tier2_hmi_percentile": 5.0,
    "tier2_buffer_km": 100.0,
    "methodology_references": ["..."]
  },
  "scorecard": [
    {
      "site_id": "dumka_0001",
      "indicator": "ndvi",
      "site_value": 0.388,
      "tier1_reference": 0.45,
      "tier1_intactness": 0.862,
      "tier2_reference": 0.52,
      "tier2_intactness": 0.746,
      "hedges_g": -0.83,
      "permutation_p": 0.0012,
      "interpretation": "Moderate intactness (74.6% of Tier 2 benchmark); large difference below reference (g=-0.83); statistically significant (p=0.0012)"
    }
  ],
  "pillar_summary": [...]
}
```

---

## Methodology References

- Dinerstein, E. et al. (2017). An Ecoregion-Based Approach to Protecting Half the Terrestrial Realm. *BioScience*, 67(6), 534–545. DOI:10.1093/biosci/bix014
- McElderry, R.M. et al. (2024). Assessing the multidimensional complexity of biodiversity using a globally standardized approach. *EcoEvoRxiv*. DOI:10.32942/X2689N
- McNellie, M.J. et al. (2020). Reference state and benchmark concepts for better biodiversity conservation in contemporary ecosystems. *Global Change Biology*, 26(12), 6702–6714. DOI:10.1111/gcb.15383
- Yen, J.D.L. et al. (2019). Modeling biodiversity benchmarks in variable environments. *Ecological Applications*, 29(7), e01970. DOI:10.1002/eap.1970
- Schipper, A.M. et al. (2020). Projecting terrestrial biodiversity intactness with GLOBIO 4. *Global Change Biology*, 26(2), 760–771. DOI:10.1111/gcb.14848
- Newbold, T. et al. (2016). Has land use pushed terrestrial biodiversity beyond the planetary boundary? *Science*, 353(6296), 288–291. DOI:10.1126/science.aaf2201
- Kennedy, C.M. et al. (2019). Managing the middle: A shift in conservation priorities. *Global Change Biology*, 25(3), 811–826. DOI:10.1111/gcb.14549
- Hill, S.L.L. et al. (2022). The Ecosystem Integrity Index. *bioRxiv*. DOI:10.1101/2022.08.21.504707
- Cohen, J. (1988). *Statistical Power Analysis for the Behavioral Sciences* (2nd ed.). Erlbaum.
- Hedges, L.V. (1981). Distribution Theory for Glass's Estimator of Effect Size. *JESS*, 6(2), 107–128.

---

## License

Internal use — Darukaa.Earth. Contact: gaurav.singh@darukaa.com
