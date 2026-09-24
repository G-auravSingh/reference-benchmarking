# Darukaa Adaptive Ecosystem Assessment Pipeline v1.0.0

## Purpose

This package adds a **project-type-aware aquatic/lake profile** to the supplied Darukaa biodiversity assessment framework while preserving the supplied terrestrial reference package as a separate, untouched legacy implementation.

**Design principle:** the client supplies a KML; the pipeline automatically derives secondary spatial domains from Earth-observation data. No hand-drawn water polygon, littoral polygon, or riparian polygon is required for the first-pass assessment.

## What is preserved

`legacy_darukaa_reference_v0.1.0/` is a verbatim copy of the supplied reference package. Do not edit it when developing the adaptive profile. Existing terrestrial projects can continue to use their existing notebook/package workflow.

## New lake workflow

```text
KML
  ↓
Fixed project geometry
  ↓
Automatic site characterisation
  ├─ Dynamic World land/water composition
  └─ JRC historical water context (1984–2021 where available)
  ↓
Automatic ecosystem profile
  ↓
Derived domains
  ├─ dynamic water pixels
  ├─ fixed external riparian buffer
  └─ fixed KML / context
  ↓
Lake metrics
  ├─ water extent
  ├─ water persistence
  ├─ TSPI / NDCI
  ├─ SABF / FAI frequency
  ├─ WCPI
  ├─ WSDI
  ├─ riparian NDVI trend
  ├─ RCI
  └─ SHDI (descriptive only)
  ↓
Compatibility scoring
  ↓
Lake scorecard + run manifest
```

Dynamic World is a 10 m near-real-time land-cover product with water probability and a water class, available from 2015-06-27 onward. Google recommends probability thresholding for confident class selection. urlEarth Engine Dynamic World documentationhttps://developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1

JRC Global Surface Water v1.4 provides historical surface-water information through 2021; it is therefore not used as a current-year persistence source in this package. urlEarth Engine water dataset cataloguehttps://developers.google.com/earth-engine/datasets/catalog

## Important methodological status

This is **v1.0.0 of the adaptive architecture**, not a claim that every aquatic metric or benchmark has already been fully validated for all lake types.

The lake profile deliberately distinguishes:

- **computed** — automatically derived;
- **descriptive_only** — useful but not allowed to affect SoN by default;
- **not_run** — requires species/context assets or an additional evidence source;
- **failed** — data/asset/processing issue;
- **provisional scoring** — uses compatibility thresholds inherited from the supplied Nandoshi methodology and must be QA-reviewed before client publication.

## Running Nandoshi

### Colab / notebook

Open `notebooks/Nandoshi_Lake_Aquatic_Assessment.ipynb`, set the GEE project, upload the KML, authenticate, and run all cells.

### Command line

```bash
pip install -r requirements.txt
python run_lake.py --kml "input/Nandoshi lake.kml" --gee-project darukaa-earth-product --year 2025 --out output/nandoshi
```

## Outputs

- `lake_scorecard.csv` — one row per metric, raw value, domain, status, and compatibility concern score.
- `characterization.json` — automatic site/ecosystem characterisation.
- `lake_run_manifest.json` — complete run metadata and limitations.

## Backward compatibility

The adaptive package does **not** modify the legacy terrestrial package. A regression test against old terrestrial projects should be added before any future migration of the terrestrial workflow onto the adaptive architecture.

## Next QA phase

Before using the lake profile for client-facing biodiversity-credit claims, validate:

1. Dynamic World water probability threshold against several Indian lakes/reservoirs.
2. Seasonal observation design and water-extent aggregation.
3. Aquatic Tier-2 reference selection using comparable water bodies rather than generic terrestrial pixels.
4. Metric-specific applicability and scoring direction.
5. SHDI treatment as a descriptive morphometric variable.
6. Species-range metrics as contextual conservation-significance measures rather than confirmed occurrence.
7. Regression equivalence of the frozen terrestrial pipeline.
