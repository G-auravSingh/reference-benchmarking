# Darukaa Adaptive v1.1.0

Darukaa Adaptive is an ex-situ biodiversity baseline assessment for any project geometry: one polygon, separate sites, or many adjacent management units. It measures open satellite and geospatial metrics in Google Earth Engine. It then compares them with reference conditions and reports four pillars, aligned with the Nature Positive Initiative State of Nature indicators.

> **Status: first draft of the rebuilt pipeline (23 Oct 2026).**
>
> | Evidence level | Status |
> |---|---|
> | Offline unit tests | Pass |
> | Mocked tests | Pass |
> | Live Earth Engine run | Not yet |
>
> Do not interpret scores until validation rungs CR1 and R2 are complete (see `VALIDATION.md`).

## What it reports

| Pillar | Nature Positive basis | Measured at | Default scored metrics |
|---|---|---|---|
| P1 Ecosystem extent | Extent indicator | Site | natural extent %, gross loss since 2020, tree-cover loss rate, core natural area |
| P2 Ecosystem condition (natural pixels only) | Condition indicator | Site and EMU | peak-season NDVI, canopy height, BII, EII functional, FLII (forest only); Sentinel-2 LAI pending |
| P3 Species | Extinction risk, populations | Site | none: licence-restricted data, reported as "not covered"; screening records only |
| P4 Pressure | Outside Nature Positive (TNFD pressures) | Site | built-up share, gHM, roads, fire frequency, night lights |
| Managed land | Outside the Nature Positive panel | Site and EMU | contextual only |

How the outputs are labelled:

- Every metric is **preparatory** under the Nature Positive measurement guidance.
- Landscape results are labelled as context.
- Each metric's status is reported as four separate facts: whether it ran, whether it was measured validly, whether there was enough to score, and whether the result is interpretable.
- Every score carries a 90% bootstrap interval and a High/Medium/Low confidence rating.

## Layout

```
darukaa_adaptive/
  catalogue.py        metric contracts (single source of truth) and role resolution
  config.py           run configuration; every parameter tied to a decision
  inputs.py, site.py  handoff ZIP / manifest / GeoJSON / KML(s) / boundary loading
  units.py            sites (full boundary) with EMUs nested inside; context windows
  natural_mask.py     ForTy 2020 + SBTN v1.1 natural mask, Dynamic World change
  layers.py           one Earth Engine builder per metric
  extraction.py       one measurement path for sites, EMUs and reference blocks
  reference_pool.py   least-disturbed condition pool; regional context blocks
  measurement.py      measurement records and the four status layers
  scorecard.py        response functions, bootstrap, confidence, aggregation
  assessment.py       end-to-end run
  outputs.py          CSV tables, manifest, HTML report, ZIP
  probe.py            read-only Earth Engine probe (CR1)
  validation_check.py compare run bundles with pre-registered expectations
docs/decisions/       approved decisions and the file audit
docs/methodology/     metric_catalogue_v1.md (approved specification)
validation/           R2 control polygons and expected answers
notebooks/            Colab notebook
```

## Running

Open `notebooks/Darukaa_Adaptive_Biodiversity_Assessment_Colab.ipynb` in Colab and follow its sections.

Offline tests:

```bash
pip install -r requirements.txt
pytest -q
```

## Rules this code follows

- Missing, failed or invalid data never becomes zero or a score.
- Condition and pressure are kept separate.
- Sources are labelled by type: standard, vendor/tool, academic dataset or Darukaa evidence.
- Scientific changes are made only through `docs/decisions/`.
