# Darukaa Site Selection Pipeline — README

**Status:** Active development, Aug 2026. Successor to
`Darukaa_SiteSelectionPipeline_v6.0` — unifies that repo's two separate
tracks (`main.py`'s geographic-cluster path for agroforestry, and
`run_project.py`'s segmentation path for compact single-perimeter sites)
into one pipeline that routes automatically by project archetype. See
`CHANGELOG.md` for the full list of what changed and why, and
`docs/PIPELINE_METHODOLOGY_REFERENCES.md` for every citation behind a
methodological decision.

## Read in this order

1. **This file** — what the pipeline does, how to run it.
2. **`METHODOLOGY.md`** — what every stage does and why, the scientific
   basis for each decision.
3. **`docs/PIPELINE_METHODOLOGY_REFERENCES.md`** — every citation,
   inherited from v6.0 where still applicable, extended for what's new here.
4. **`docs/OUTPUT_FILE_GUIDE.md`** — which output file is for whom (field
   team / client / internal QA), and which files are safe to hand to a
   client as-is.
5. **`CHANGELOG.md`** — chronological record of every real bug found and
   fixed, in the order it was found. Read this before assuming a number in
   an old output is still correct — several were not.

## What this pipeline does

Turns a client's site KML into: an Ecological Monitoring Unit (EMU) map, a
ranked candidate position pool per EMU, a device deployment schedule, an
ex-situ covariate/metrics rollup, and two client-facing outputs — a site
selection report and an interactive field map.

Three project archetypes, auto-detected from `config.yaml`:

| Archetype | Example | EMU delineation method |
|---|---|---|
| `agroforestry` | FCF Soova, FCF GV | Ecological clustering (Gower distance) over scattered farm parcels, with a real spatial-adjacency constraint |
| `conservation` | SoulForest Veltoor | GEE SNIC image segmentation over a dense tessellated grid |
| `industrial` | Tata Motors Pimpri | Same underlying segmentation machinery as `conservation`, with `zone_is_emu: true` — each real, client-declared ecological zone becomes one EMU directly (no further spectral sub-clustering), a `custom_ingestion.py` for the project's own non-standard KML structure, and its own `zone_scoped_continuous` deployment regime (see METHODOLOGY.md) |

## Running a project

```bash
pip install -r requirements.txt   # add --break-system-packages if your
                                    # Python install requires it
python pipeline/run_pipeline.py projects/<PROJECT_NAME>
```

That single command runs every stage (01 through 06b, see `METHODOLOGY.md`
for what each does), skipping any stage whose inputs haven't changed since
its last successful run. Two flags:
- `--force` — re-run every stage regardless of staleness (use after editing
  a stage's own code, since the caching only tracks *data* file changes).
- `--from 03` — force a re-run starting at a given stage (use this after a
  new GEE CSV lands — that only changes a data file two stages upstream of
  where you actually need things to re-run).

**The GEE step is manual, on purpose** (see CHANGELOG for why automating it
wasn't worth doing yet). After `01_ingestion` and `02_covariates` run once,
each project gets a `gee_output/GEE_RUN_INSTRUCTIONS.md` with the exact,
numbered steps for that specific project — including a real, generated
Shapefile (GEE's asset uploader does not accept raw GeoJSON — a real bug
found and fixed, see CHANGELOG) and a ready-to-paste `.js` script with the
project's archetype-specific settings already filled in.

## Setting up a new project

1. `mkdir -p projects/<NAME>/raw`
2. Put the client's KML(s) in `projects/<NAME>/raw/`
3. Write `projects/<NAME>/config.yaml` — copy an existing project's as a
   starting point (`FCF_Soova` for agroforestry, `SoulForest_Veltoor` for a
   compact single-perimeter site) and adjust. Every config key has a
   documented default in `pipeline/common/config_schema.py` — a new
   project's config.yaml only needs to state what differs from those
   defaults.
4. Run it: `python pipeline/run_pipeline.py projects/<NAME>`

## Repository layout

```
pipeline/
  01_ingestion/          KML parsing, exclusion/anchor classification, dense grid for contiguous sites
  02_covariates/         GEE CSV ingestion, hard filters (built-up %, water)
  03_emu_delineation/    ecological_clustering.py (agroforestry) / segmentation_reconciliation.py (contiguous)
  03b_position_scoring/  CRITIC-weighted within-EMU candidate ranking, position pools
  04_deployment_planning/ device/cycle scheduling, deployment_schedule.csv/.xlsx export
  05_metrics_rollup/     EMU/project-level covariate distribution stats
  06_reporting/          site selection report + field_map.html
  07_reference_handoff/  per-EMU tile export for darukaa_reference (see METHODOLOGY.md)
  common/                shared utilities (config schema, CRS handling, clustering, GEE export)
  gee/                   the shared Earth Engine script
projects/<NAME>/
  config.yaml
  custom_ingestion.py     (optional — see below)
  raw/                   client KML(s) — never modified by the pipeline
  gee_output/            GEE run instructions, generated shapefiles, and where you place downloaded CSVs
  outputs/               everything the pipeline produces, one subfolder per stage
docs/                    methodology references, output file guide (this folder)
```

### Non-standard KML structures: `custom_ingestion.py`

A project whose source KML doesn't fit the standard placemark-classification
model `01_ingestion/kml_ingest.py` expects (a small set of named
anchor/exclusion/candidate placemarks) can provide its own
`projects/<NAME>/custom_ingestion.py`, exposing a single function
`run_ingestion(project_dir)`. When present, the orchestrator (`run_pipeline.py`)
uses it in place of the standard ingestion for that project's Stage 01 —
including on `--force`, so this never silently falls back to logic that
was never designed for that project's KML. Tata Motors Pimpri uses this
for its real, many-layered thematic zonation KML — see
`projects/TataMotors_Pimpri/preprocess_eco_zones.py` for the actual logic
and `custom_ingestion.py` for the thin adapter.

## Known, currently-open items

See `CHANGELOG.md`'s "Open" section for the live list — as of this
writing, that includes: a real, unresolved tension between EMU spatial
compactness and the device-coverage guarantee (surfaced directly on real
data, not resolved — see `METHODOLOGY.md` §3), and aquatic covariates not
yet rolled into the metrics rollup. The `darukaa_reference` handoff
(Phase 4 of the original architecture plan) is real, tested, and
connected now — not just the EMU tile export (`07_reference_handoff`),
but the consuming side too: `darukaa_reference`'s own
`run_project_from_manifest.py` reads it directly by project name, no
manual handoff step, for all four real projects here plus a dedicated
aquatic-tile extraction for Tata Motors' own water bodies. See
`darukaa_reference`'s own README/CHANGELOG for the real, current detail.
