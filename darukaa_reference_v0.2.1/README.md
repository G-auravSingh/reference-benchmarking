# darukaa_reference

**Profile-first, non-compensatory, evidence-graded biodiversity benchmarking against a SEED-aligned reference condition.**

Developed by Gaurav Singh, Scientific Lead — Biodiversity Methodology, Darukaa.Earth.

This is the **monitoring half** of Darukaa's biodiversity pipeline: given a set of site
polygons (Year-0 baseline or a later monitoring cycle), it benchmarks each indicator
against a defensible, ecologically-matched reference condition, aggregates the results
without hiding weak components behind an average, and emits an evidence-graded report.
Site selection (choosing *where* to sample) is a separate, decoupled repository.

---

## 1. What this pipeline does, in one paragraph

For each site, for each **scored** indicator (a deliberately lean subset — see
`INDICATOR_REGISTER.md`), the pipeline finds the least-disturbed comparable land in the
same ecoregion and land-cover class, benchmarks the site against it with a **signed,
uncapped** estimator (so restoration gains stay visible), and combines the results using
a **non-compensatory** rule (the profile is always shown; any roll-up is secondary and
always published with its weakest component). Every run writes a standalone,
**evidence-graded HTML report** — the client deliverable — plus JSON and CSV.

## 2. Read this first

| Document | What it's for |
|---|---|
| **`METHODOLOGY_MASTER.md`** | The methodology, start to finish. Read this before anything else. |
| **`ASSUMPTIONS_AND_LIMITATIONS.md`** | **Read before quoting any result.** Every arbitrary constant, every un-validated code path, and the exact status of SEED fidelity (what's fixed, what's still open, and why). |
| `INDICATOR_REGISTER.md` | Every indicator: is it scored, why or why not, on what evidence. |
| `SCORING_LOGIC_NOTE.md` | How raw values become the profile-first output, in plain language. |
| `OPEN_DECISIONS.md` | Running log of decisions and open items (OD-1 through OD-11). |
| `CHANGELOG.md` | What changed, per version, with rationale. |
| `NPI_CROSSWALK.md`, `TNFD_LEAP_CROSSWALK.md` | Mapping to external disclosure standards. |
| `SOCIAL_BASELINE_FRAMEWORK.md` | Placeholder for the social/tenure dependency module (not yet populated). |
| `NEXT_CYCLE_IMPLEMENTATION.md` | Everything deliberately deferred, and why. |

## 3. Repository layout

```
darukaa_reference/
├── config.py            # Everything you configure lives here (see §5)
├── registry.py           # IndicatorSpec dataclass + the contract (construct,
│                          #   evidence tier, reference type, active/eligible toggle)
├── contracts.py           # The declarative table of all 44 indicators' dispositions
│                          #   (scored / contextual / screening / removed) — the
│                          #   single source of truth for what gets scored
├── indicators/__init__.py  # Indicator extraction functions (GEE calls) + registration
├── estimators.py          # Responsive benchmarks (LRR, robust-z) + the SEED
│                          #   Mahalanobis kernel + delta calibration
├── reference.py           # Reference-condition selection (Tier 1/2, SEED stratification)
├── statistics.py          # Bootstrap CIs, Hedges' g, propagates the benchmark
├── scoring.py             # Profile-first non-compensatory aggregation + sensitivity
├── change.py              # Cycle-2+ change scoring (delta vs Year-0, BACI contrast)
├── project_aggregation.py # Multi-tile driver for agroforestry/large multi-parcel
│                          #   projects: runs each tile, combines non-compensatorily
├── report.py              # Assembles the report dict (JSON/CSV source of truth)
├── html_report.py         # Renders the evidence-graded HTML from that dict
├── pipeline.py            # Orchestrates all of the above; the thing you actually run
├── ecoregion.py           # Ecoregion (RESOLVE) lookup helper
└── site_loader.py         # KML/KMZ/shapefile ingestion

notebooks/run_pipeline.ipynb   # Recommended way to run this (Colab-ready)
example_run.py                 # CLI alternative
config.yaml                    # Optional external config (mirrors config.py fields)
```

**How to find anything:** if you're wondering "where does X happen" — indicator
*definitions* are in `indicators/__init__.py`; which ones get *scored* is decided in
`contracts.py`; the *reference condition* is built in `reference.py`; how a value
becomes a *responsive benchmark* is `estimators.py`; how benchmarks become the
*profile/score* is `scoring.py`; the *report* is assembled in `report.py` and rendered
in `html_report.py`. `pipeline.py` is the only file that calls all of the above in order.

## 4. Quick start

**Colab (recommended):** open `notebooks/run_pipeline.ipynb`, run top to bottom. It
handles cloning, installing, GEE auth, KML upload, running, and downloading results.

**Local:**
```bash
pip install -r requirements.txt
pip install -e .
python example_run.py --site your_site.kml --gee-project your-gee-project-id
```

Every run writes `outputs/benchmark_scorecard.{json,csv,html}`. **Open the `.html`** —
that's the evidence-graded report a client would see.

## 5. Configuration — the options that matter

Everything is one `Config` object (`config.py`). The full field list is documented
inline in that file; these are the ones you're likely to actually touch:

```python
from darukaa_reference.config import Config

config = Config(
    gee_project="your-gee-project-id",
    output_dir="outputs",
    # --- project context (drives which modules activate; does not change scoring) ---
    realm="terrestrial",          # terrestrial | aquatic | mixed
    archetype="conservation",     # conservation | agroforestry | aquatic |
                                  # corporate | solar | mining | materials
    assessment_mode="baseline",   # baseline (Year-0) | monitoring (Year-N, needs change.py)
    # --- reference condition (SEED-aligned; see METHODOLOGY_MASTER.md §5) ---
    reference_stratification="ecoregion_landcover",  # default, SEED-faithful
    hmi_hard_ceiling=0.05,        # SEED's maximum allowable HMI for a reference pixel
    use_variance_stability_floor=True,   # suppress the score if the reference is noisy
    # --- optional SEED similarity view (never replaces the primary scoring) ---
    use_seed_kernel=False,
)
```

**Does the archetype/project-type change how you run this?** The fixed core constructs
(C1 landscape, C2 vegetation, C3 fauna, C4 pressure) and the scoring logic are the same
for every project — that's what keeps results comparable. What changes by archetype:

- **`conservation`** (default): no special handling. Runs as documented above.
- **`agroforestry`**: large multi-parcel AOIs are typically too big / too scattered for
  one `darukaa_reference` run to be geographically meaningful. **This repo now ships a
  self-contained multi-tile driver** — `darukaa_reference/project_aggregation.py` — so no
  dependency on any other repository is needed for the run-and-aggregate step:

  ```python
  from darukaa_reference.config import Config
  from darukaa_reference.indicators import create_default_registry
  from darukaa_reference.project_aggregation import run_multi_tile_project

  config = Config(gee_project="your-gee-project-id", archetype="agroforestry")
  registry = create_default_registry()

  project = run_multi_tile_project(
      config, registry,
      tile_paths=["data/tile_01.kml", "data/tile_02.kml", "..."],  # one file per tile
      tile_labels=["tile_01", "tile_02", "..."],                   # optional
      project_name="my_agroforestry_project",
  )
  ```

  Each tile's KML may itself contain many individual farm parcels — they are
  automatically dissolved into one geometry per tile (a tile IS one assessment unit, not
  N). The project-level result is combined **non-compensatorily**: the project's signal
  for every indicator is set by its **worst tile** (named explicitly), not masked by
  averaging over a larger, better-performing area. See the module docstring in
  `project_aggregation.py` for the full rationale, and `outputs/<project>_project.html`
  for the transparency table showing exactly which tile drove each indicator.

  **Producing the tiles themselves** (grouping parcels into tiles, e.g. via DBSCAN on
  parcel centroids) is a separate, upstream, purely-geometric step that this repo does
  not do — it depends only on parcel locations, not on anything ecological
  `darukaa_reference` computes, so it can be done with whatever tool is convenient (a
  simple DBSCAN script, GIS software, or the site-selection repo if you're using it).
  What matters for this repo is only that each tile arrives as its own KML/GeoJSON file.
- **`corporate` / `solar` / `mining` / `materials`**: registered but **inactive by
  default** in the indicator contract (`contracts.py`) — a mitigation-hierarchy/no-net-loss
  framing is more appropriate than the conservation-oriented default indicator set, and
  building that out is deferred (see `NEXT_CYCLE_IMPLEMENTATION.md`). Do not run these
  archetypes expecting a populated indicator set without first reviewing the register.
- **`assessment_mode="monitoring"`**: requires a stored Year-0 report to diff against —
  see `change.py` and the "Monitoring mode" cell in the notebook.

## 6. Validating against a live run

Everything in this pipeline has been validated **by construction and unit/integration
tests on synthetic data** — none of the Earth Engine calls have been executed live
(no GEE access in the build environment). Before trusting real output:

1. **Verify the PNV crosswalk first (blocking).** `config.pnv_to_dw_crosswalk` maps
   Potential-Natural-Vegetation biome codes to Dynamic World classes, for relabelling
   converted/artificial land before reference lookup (see `METHODOLOGY_MASTER.md` §5).
   The default crosswalk is an **unverified placeholder** — inspect the PNV asset's
   actual class legend in the GEE Code Editor, correct the mapping if needed, then set
   `config.pnv_to_dw_crosswalk_verified = True`. The pipeline logs a warning on every
   run until this is done.
2. **Run it** against 2-3 real sites of different archetypes/land-cover types.
3. **Send back `outputs/benchmark_scorecard.json`** (the full file — it's self-sufficient
   for review; no separate diagnostic export is needed). Each scorecard row's
   `stratification_diagnostics` field shows exactly which ecoregion/land-cover stratum
   was used, whether the PNV correction fired, the realised HMI threshold, and which
   fallback level (if any) was needed — this is what lets a second pass check whether
   the reference selection is behaving sensibly on real landscapes.
4. Also useful: the console log from the run (catches early GEE errors — wrong band
   names, empty collections, auth issues — before they show up as silent gaps in output).

## 7. Known limitations (do not skip)

`ASSUMPTIONS_AND_LIMITATIONS.md` is the authoritative list. Headlines:
- SEED fidelity: the reference-selection **algorithm** is now structurally correct
  (verified against the paper's Sec. 3.1-3.2), but the PNV crosswalk is unverified and
  the SEED kernel's `delta` parameter is an undisguised placeholder pending real data —
  see §1 there for the full item-by-item status.
- The scored indicator set is deliberately lean (10 of 44 registered) — see
  `INDICATOR_REGISTER.md` for why each of the other 34 is contextual, screening-only,
  or removed.
- In-situ (field/acoustic/eDNA) indicators do not score in cycle 1 by design — see
  `METHODOLOGY_MASTER.md` §7.

## 8. Citations

- McElderry et al. (2024). SEED framework. DOI:10.32942/X2689N
- Kennedy et al. (2019); Theobald et al. (2025). Global Human Modification.
- Hengl et al. (2018). Global Potential Natural Vegetation. *PeerJ* 6:e5457.
- Dinerstein et al. (2017). RESOLVE Ecoregions. *BioScience* 67:534-545.
- Hedges, Gurevitch & Curtis (1999). Log response ratio. *Ecology* 80:1150-1156.
- Full reference list in `METHODOLOGY_MASTER.md` Appendix A.
