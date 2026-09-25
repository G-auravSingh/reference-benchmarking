# darukaa_reference (v0.2.6)

**Profile-first, non-compensatory, evidence-graded biodiversity benchmarking against a SEED-aligned reference condition.**

Developed by Gaurav Singh, Scientific Lead — Biodiversity Methodology, Darukaa.Earth.

This is the **monitoring half** of Darukaa's biodiversity pipeline: given a set of site
polygons (Year-0 baseline or a later monitoring cycle), it benchmarks each indicator
against a defensible, ecologically-matched reference condition, aggregates the results
without hiding weak components behind an average, and emits an evidence-graded report.
Site selection (choosing *where* to sample) is a separate, decoupled repository.

---

## 1. What this pipeline does, in one paragraph

For each site, for each **scored** indicator (a deliberately lean but pillar-complete
default set, fully customisable — see §5), the pipeline finds the least-disturbed
comparable land in the same ecoregion and land-cover class, benchmarks the site against
it with a **signed, uncapped** estimator (so restoration gains stay visible), and
combines the results using a **non-compensatory** rule (the profile is always shown;
any roll-up is secondary and always published with its weakest component). On top of
that profile, `son_score.py` exposes exactly what a dashboard or a downstream risk model
needs: an **Overall Condition score + class**, a **separate Overall Pressure score +
class**, and a confidence flag — see `AGGREGATION_WALKTHROUGH.md` Part C. Every run
writes a standalone **evidence-graded HTML report** (with these as visible badges) — the
client deliverable — plus JSON and CSV, and the notebook can render an interactive map
for any indicator with a live GEE raster behind it.

## 2. Read this first

| Document | What it's for |
|---|---|
| **`METHODOLOGY_MASTER.md`** | The methodology, start to finish. Read this before anything else. |
| **`ASSUMPTIONS_AND_LIMITATIONS.md`** | **Read before quoting any result.** Every arbitrary constant, every un-validated code path, and the exact status of SEED fidelity (what's fixed, what's still open, and why). |
| `INDICATOR_REGISTER.md` | Every indicator: is it scored, why or why not, on what evidence. |
| `SCORING_LOGIC_NOTE.md` | How raw values become the profile-first output, in plain language. |
| **`AGGREGATION_WALKTHROUGH.md`** | Step-by-step: indicator → pillar → overall, for conservation (single/multi-site) and agroforestry (multi-tile), separately. |
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
├── son_score.py           # Product/dashboard layer: Overall Condition score+class,
│                          #   separate Pressure score+class, per-indicator classification
├── change.py              # Cycle-2+ change scoring (delta vs Year-0, BACI contrast)
├── project_aggregation.py # Multi-tile driver for agroforestry/large multi-parcel
│                          #   projects: runs each tile, combines non-compensatorily
├── report.py              # Assembles the report dict (JSON/CSV source of truth)
├── html_report.py         # Renders the client/product-facing HTML report — executive
│                          #   summary, plain-language methodology primer, per-zone SVG
│                          #   visuals (ranked bar chart, condition x pressure quadrant),
│                          #   evidence-graded scorecard. See §4a below.
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
that's the client/product-facing report.

## 4a. The HTML report — what changed and why

Rebuilt (v0.2.7) to be genuinely self-explanatory to a first-time reader and reliable
for a product team to theme or consume, not just internally correct:

- **Executive summary in plain language** before any table — states the project's
  archetype-appropriate framing, its non-compensatory headline, and the confidence
  behind it, in real sentences.
- **An embedded methodology primer** — not a citation list standing in for an
  explanation. Explains profile-first scoring, why the worst-scoring component sets
  the score (non-compensatory), why condition and pressure stay structurally separate,
  and what an evidence tier means — in the report itself, so it never depends on the
  reader having read a separate document first.
- **Real inline SVG visuals**, no external chart library dependency (the report stays
  a single self-contained file): a ranked per-zone bar chart (worst zone at the top,
  a dashed reference line at "at reference") and a condition x pressure quadrant plot.
  For a multi-zone project, points use numbered markers with a legend rather than
  direct text labels — confirmed directly (rendered in an actual browser during
  development, not assumed) that direct labels overlap illegibly whenever several
  zones score similarly, which is a common real pattern, not a rare edge case.
- **A real per-zone breakdown section** for any multi-tile/multi-zone project (Tata
  Motors' 9 zones, Soulforest's 7 EMUs, Corbett's 4 sites): shows every real zone's own
  independent result, not just the project-level aggregate — the pipeline genuinely
  ran once per zone, and the report now shows that work, not just the number it
  produced.
- **Semantic CSS classes** (`.dk-*` prefix, no inline styles in the body markup) so a
  product team can reliably theme or scrape specific values, rather than needing to
  parse inline style attributes.
- Every evidence-grading, transparency, and honesty feature from the previous version
  is preserved exactly — this is additive design work, not a reduction in rigor.

Verified by rendering real (synthetic but schema-accurate) single-site and 9-zone
project-level reports through an actual headless-Chromium browser during development,
not just checked for Python syntax — including catching and fixing the label-overlap
issue above before it shipped.

### 4a.1 — Superseded by a real, deeper rebuild (client-requested: the version above
still buried raw values, jumped straight to a confusing roll-up, and used numbers
(like an uncapped z-score of -70) never meant to be client-facing)

Every score shown is now a genuine **1–100% intactness score**, not a raw z-score —
the underlying bounded value already existed (a logistic transform in
`scoring.normalize`); this added the missing display conversion. Every level of the
hierarchy is now real and traceable:

- **Per indicator**: raw value (with unit) → intactness % → concern level (Very Low
  through Very High), grouped into real pillar cards (C1–C4).
- **Per pillar**: score (geometric mean of that pillar's indicators) + concern level +
  the actual limiting indicator **named explicitly** — e.g. *"limited by: Tree Cover
  Loss Rate"* — not just a bare number.
- **Overall SoN**: score + concern + the full traceable chain, e.g. *"limited
  primarily by C1 — Landscape extent (22%), itself limited by Forest Fragmentation &
  Pressure Proxy."* One line, no cross-referencing three tables to find the real cause.
- **"No bare dashes" rule**: every indicator that isn't a real value states which of
  three real, different reasons it looks empty — genuinely "not applicable to this
  geometry" (a real reason the extraction gave), a real extraction failure, or "not
  scored" (context/screening tier) — never a silent `—`.
- **Project-level distribution**: real "N of M zones in each concern band" summary
  (`_project_distribution_html`), not just a ranked list — matters more, not less, as
  the real unit count grows (an agroforestry project's many real parcels, not just a
  handful of conservation zones).
- **In-situ (field-collected) metrics** — species richness/diversity from camera
  traps, eDNA, etc. — get their own clearly-separated section: real value + rank
  among this project's own zones, explicitly **never** a concern level at baseline (no
  valid spatial reference pool exists for field data — see `change.py`); a real trend
  signal becomes available from Year-1 monitoring onward instead.

Geometric mean (not arithmetic average) was a deliberate, real choice, not a default:
arithmetic mean lets one strong indicator fully hide a real weak one; geometric mean
is real precedent (the same reasoning the UN's Human Development Index used when it
switched away from arithmetic mean) and is far less forgiving of a single bad number,
while the always-named limiting indicator keeps the non-compensatory,
worst-factor-matters principle fully visible alongside it — client-confirmed
explicitly: showing both, chained, rather than two separate composite numbers that
could disagree.

Verified directly: rendered a realistic 9-zone project and a single-site case through
the real pipeline functions (not fabricated JSON) in an actual headless-Chromium
browser. Two real bugs were caught this way before shipping, not assumed correct from
a syntax check — a name collision that silently turned "30%" into "0%" (this module
already had its own, differently-scaled `_pct`), and Python's `str.capitalize()`
lowercasing "C1" inside the limiting-chain text.

## 5. Configuration — the options that matter

Everything is one `Config` object (`config.py`). The full field list is documented
inline in that file; these are the ones you're likely to actually touch:

```python
from darukaa_reference.config import Config

config = Config(
    gee_project="your-gee-project-id",
    output_dir="outputs",
    # --- project context ---
    realm="terrestrial",          # terrestrial | aquatic | mixed -- REAL, ACTIVE FILTER
                                  # (was loaded but unused before this was completed; now
                                  # genuinely determines which indicators get computed at
                                  # all for a run -- see the real per-indicator breakdown
                                  # just below this block, not a cosmetic label)
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

**`realm` — which indicators actually run in each realm, checked individually against
real extraction logic for every one of the 45 registered indicators (not just the
scored subset), not guessed from a name or module tag** (client-caught directly: "we
have many more indicators right which would go in the report even if they are not
scored... so we need to check everything for them as well" — correct: the pipeline
computes every registered, active indicator by default, "scored" only means "gets a
reference benchmark," and any of them can be promoted to scored at runtime via
`contracts.request_activation` — so every one needed a real, checked answer, not just
today's default-scored 12):

| Indicator | terrestrial | aquatic | Why |
|---|---|---|---|
| `natural_habitat`, `natural_landcover`, `cpland`, `forest_loss_rate`, `chm`, `bii`, `eii`, `eii_structural`, `eii_compositional`, `eii_functional`, `flii`, `ndvi`, `habitat_health`, `pdf`, `lai`, `flagship_habitat`, `star_t`, `ivsi` | yes | no | Land/vegetation-specific — checked directly: `DW_NATURAL_CLASSES` (checked directly) excludes water entirely, so a pristine lake would wrongly show ~0% "natural"/"habitat suitability"; canopy height, leaf area, and forest loss are trivially ~0 on open water; NDVI/HHI/PDF/IVSI are vegetation-greenness-based; BII's PREDICTS model is explicitly terrestrial. `eii` and its 3 sub-components excluded as a conservative default — real water-pixel behaviour isn't verifiable without live GEE access yet. |
| `ghm`, `hdi`, `light_pollution`, `aridity_index`, `lst_day`, `lst_night` | yes | yes | Landscape-wide context surfaces — genuinely meaningful for a water body's surroundings (and water surface temperature is itself a real, meaningful signal), same as for land. |
| `jrc_water_persistence`, `rci`, `riparian_ndvi_trend` | yes | yes | Water-specific or water-finding by definition/design — `jrc_water_persistence` and `rci`/`riparian_ndvi_trend` were actually mistagged `module="core"` (the latter two explicitly locate the water body within the site geometry first, then compute a 100m riparian buffer around it — essentially aquatic-specific, not just tolerant of it). |
| `endemic_richness`, `threatened_richness`, `endemic_plant_richness`, `threatened_plant_richness`, `ceri`, `shi`, `kba_overlap`, `iri` | yes | yes | Real species-range-overlap or geometric-overlap logic — genuinely meaningful for water-dependent species and real wetland/lake-containing KBAs too (all screening/context-tier regardless of realm — see §7). |
| `tspi`, `sabf`, `wcpi`, `wsdi`, `hsas`, `edpp`, `mspl`, `shdi`, `sdi` | no | yes | Aquatic-only by definition (trophic state, water clarity/quality, surface dynamics — meaningless on land). |

`realm="mixed"` runs every indicator regardless of this table — useful for a genuinely
uncertain site, but the result will include some indicators that don't really apply;
prefer `terrestrial`/`aquatic` (or let a combined multi-tile run set this per-tile
automatically — see §4a's multi-tile section) whenever you know which one you have.
Promoting a screening/context indicator to scored status (`request_activation`) never
bypasses this table — confirmed directly: activating a land-specific indicator still
correctly excludes it from an aquatic run.

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

  This same driver applies identically to a genuinely different case: several real,
  independent standalone sites reported as one combined project (not sub-tiles of one
  larger boundary) — e.g. Corbett's 4 real North Shahdol plantation sites (Masira,
  Pipri, Karpa, Amanar). `run_multi_tile_project` doesn't distinguish the two cases;
  it just needs a list of geometry files. A ready-to-run example ships at
  `run_corbett_northshahdol.py` (site KMLs go in `corbett_sites/`) — verified directly
  before shipping: all 4 real sites load correctly (areas 100.8/135.2/151.2/15.4 ha,
  matching each KML's own embedded area hint), and the full pipeline runs cleanly
  through ecoregion resolution before stopping at exactly the live-GEE-credentials
  boundary, with a clear error — confirming the only remaining requirement to get a
  real result is authenticating GEE in the session running it.

  **For any project that already has a site-selection pipeline run** (Tata Motors,
  Soulforest, GV, Soova, or any future project using that pipeline's own
  `07_reference_handoff` stage): use `run_project_from_manifest.py` instead of writing
  a bespoke script — it reads that project's real `tile_manifest.json` directly (the
  exact handoff format the site-selection pipeline already produces, one real
  dissolved GeoJSON tile per EMU/zone) and runs it through the same
  `run_multi_tile_project` path.

  **The two pipelines' outputs now live in this same repository** (client-requested:
  "reduce this manual downloading and uploading process... the two pipelines can be
  connected") — so the manifest is already on disk the moment this repo is cloned,
  with no zip/upload step in between:

  ```bash
  python run_project_from_manifest.py --project TataMotors_Pimpri
  ```

  `--project <name>` searches this repo for that project's real handoff automatically
  (see `find_manifest_by_project_name` in the script) — it doesn't require knowing the
  exact nested path the site-selection folder happens to be pushed under, which is
  real (not guaranteed to stay fixed): the current push sits at
  `Darukaa_SiteSelection_pipeline_vAug2026/Darukaa_SiteSelection_pipeline/`
  `Darukaa_SiteSelection/projects/<name>/...`. Use `--manifest <exact path>` instead
  if you want to point at a specific manifest directly (e.g. one outside this repo).

  Verified directly, by name alone, for all four real, current site-selection
  projects before shipping this — Tata Motors' 9 real zones, Soulforest's 7 real
  EMUs, GV's 6, and Soova's 5 (its EMU count changed in the latest site-selection
  push — this reads whatever the current real manifest says, not a remembered
  count) all resolve and dissolve to their correct real areas. For Tata Motors
  specifically, this means the pipeline genuinely runs once per real zone (9
  independent runs), not once over the whole 126.66 ha campus — the project-level
  report is built FROM those real per-zone results via the same non-compensatory
  aggregation described above, and the rendered report's "per-zone breakdown" section
  shows every real result explicitly, not just the aggregate on top of them.

  **A project that has BOTH real terrestrial zones and real water bodies gets ONE
  combined report, never two separate ones** (client-requested directly: "if any
  project involves both aquatic + terrestrial the report can't be a separate one").
  Running `--project TataMotors_Pimpri` automatically finds and merges in its real
  `TataMotors_Pimpri_Aquatic` companion manifest if one exists (see
  `extract_aquatic_tiles.py`) — no separate command needed. Each tile still gets its
  own correct realm (`tile_realms` in `run_multi_tile_project`), never one
  project-wide setting blindly applied to every tile: a terrestrial zone gets
  terrestrial-applicable indicators, a water body gets aquatic-applicable ones (see
  `applicable_realms` in `registry.py` — checked individually against real extraction
  logic for every currently-scored indicator, not assumed from a module tag; §5 below
  has the full real breakdown). Verified directly: Tata Motors' combined run correctly
  attempts all 15 real tiles (9 terrestrial + 6 aquatic) with the right realm each.
  Pass `--no-combine` to force a standalone terrestrial-only run instead. Running the
  aquatic manifest directly (`--project TataMotors_Pimpri_Aquatic`) always stays
  standalone — combining only ever happens starting from the terrestrial/base side.

  `notebooks/run_pipeline.ipynb`'s Section 11 has the same real combining logic
  (`COMBINE_AQUATIC` toggle in its manifest-discovery cell) — it had drifted out of
  sync with the script for a while (found directly: it still only discovered a single
  manifest, no aquatic merge, no per-tile realm), fixed to match exactly rather than
  left as a script-only feature.

  `run_corbett_northshahdol.py` remains as the reference example for the OTHER real
  case this same driver handles: a project with no site-selection pipeline involvement
  at all (raw KML boundaries only) — build a manifest by hand in the same shape
  (`corbett_sites/` for the pattern) and point either script at it.
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
