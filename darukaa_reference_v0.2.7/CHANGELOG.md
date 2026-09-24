# Changelog — darukaa_reference

Format: Keep a Changelog; SemVer. Every entry cites a change-set (CS-xx) and, where
applicable, the reviewer comment (Cxx) and HMI/SEED audit fix (F-HMI-x).

## [0.2.7] -- Real site-selection integration, client-facing report rebuild, a connected multi-pipeline handoff, and real per-tile realm-aware combined reporting

*(Consolidated: every real change below shipped within the 0.2.7 line --
this changelog previously fragmented them across two stray "Unreleased"
headers plus a separate dated entry, none of which corresponded to any
real, different package version. `darukaa_reference.__version__` has
been 0.2.7 throughout all of it; this is now the single, accurate record.)*

### Real, per-indicator realm applicability (replaces a too-coarse module-based filter)
Checked every one of the 12 currently-scored indicators' actual extraction logic
individually, not assumed from a module tag. Excluded from aquatic (each gives a
degenerate/misleading value on open water, confirmed directly): `natural_habitat`
(`DW_NATURAL_CLASSES` checked directly -- excludes water entirely, so a pristine lake
would have wrongly shown ~0% "natural"), `cpland` (land-vegetation classification
layer), `forest_loss_rate` and `chm` (trivially ~0 on open water), `bii` (PREDICTS is
an explicitly terrestrial model), `eii` (real water-pixel behaviour unverifiable
without live GEE access -- conservative default), `flii` (forest-specific by
definition). Kept for aquatic (genuinely meaningful landscape-pressure concepts):
`ghm`, `hdi`, `light_pollution`, and `jrc_water_persistence` (found to be mistagged
`module="core"` instead of `"aquatic"` -- a real tagging bug, fixed). New
`applicable_realms` field (`registry.py`) is now the single, authoritative
realm-filtering gate, derived automatically from the contract table for aquatic-module
indicators (one source of truth) and set explicitly for the 12 core-scored ones.
Verified directly: `realm='terrestrial'` keeps 11/12 scored indicators,
`realm='aquatic'` keeps exactly 5 (`ghm`/`hdi`/`jrc_water_persistence`/
`light_pollution`/`tspi`), `realm='mixed'` keeps all 12. A real bug in the FIRST
attempt at this fix -- 5 registration-call edits had an inline comment that silently
swallowed the rest of that line's arguments -- was caught immediately by actually
building the registry before committing, not assumed to work from a syntax check alone.

### Real, per-tile realm-aware combined reporting for a mixed project (client-requested
directly: "if any project involves both aquatic + terrestrial the report can't be a
separate one -- but if it is just aquatic or just terrestrial then it would be separate")
Confirmed the existing non-compensatory aggregation math (`aggregate_tiles_noncompensatory`)
already handles partial-coverage indicators correctly -- it skips a tile that has no
data for a given indicator, so an indicator computed only for the terrestrial tiles
(e.g. `chm`) or only for the aquatic ones (e.g. `tspi`) correctly finds its worst tile
only among the tiles that actually have it. No change needed there. Built the real
missing piece: `run_multi_tile_project` now accepts `tile_realms` (one realm per tile,
via `dataclasses.replace` per-tile config override -- never mutates the shared config
object other tiles still use), and `run_project_from_manifest.py` auto-detects and
merges a project's real `<name>_Aquatic` companion manifest into ONE combined run
whenever both exist -- each tile keeps its own correct realm, never one project-wide
setting blindly applied to every tile. `--no-combine` forces a standalone terrestrial-only
run; running the aquatic manifest directly always stays standalone (combining only ever
starts from the terrestrial/base side). Verified directly, all three real cases:
`--project TataMotors_Pimpri` auto-finds and combines all 15 real tiles (9 terrestrial +
6 aquatic) with the correct realm each; `--project TataMotors_Pimpri_Aquatic` stays
standalone; `--project SoulForest_Veltoor` (no aquatic companion) is completely
unaffected. Full structural test confirms all 15 tiles in the combined run reach exactly
the expected live-GEE-credentials boundary, no earlier crash.



*(Consolidated: every real change below shipped within the 0.2.7 line -- this changelog previously fragmented them across two stray "Unreleased" headers plus a separate dated entry, none of which corresponded to any real, different package version. `darukaa_reference.__version__` has been 0.2.7 throughout all of it; this is now the single, accurate record.)*

### A real, generalised runner replacing bespoke per-project scripts
`run_project_from_manifest.py` reads ANY project's real `tile_manifest.json` directly
-- the exact handoff format the site-selection pipeline's `07_reference_handoff` stage
already produces for every archetype -- and runs it through `run_multi_tile_project`.
Verified directly against all four real, current site-selection projects' manifests
before shipping (not assumed from the format alone): Tata Motors' 9 real zones,
Soulforest's 7 real EMUs, and GV/Soova's 6 real EMUs each all load and dissolve to
their correct real areas (e.g. Tata Motors' Wildlife zone -> 3.78ha, Soulforest's
Fruit Forest -> 9.29ha), and the full pipeline runs cleanly through ecoregion
resolution before stopping at exactly the live-GEE-credentials boundary on every one
-- confirming this script's only real remaining requirement, for any of these four
projects, is live GEE authentication in the session running it.

For Tata Motors specifically, this confirms directly what the client asked: the
pipeline genuinely runs once per real zone (9 independent runs), not once over the
whole 126.66 ha campus -- the project-level report is built FROM those 9 real
per-zone results via non-compensatory aggregation, not a single run over the
dissolved boundary.

### HTML report rebuilt for client/product-facing use (client-reported: needs to be
scientifically rigorous, self-explanatory to a first-time reader, and reliable for a
product team to theme/consume on a platform built against an older methodology)
- Real executive summary in plain language, archetype-aware, before any table.
- A genuine embedded methodology primer (profile-first scoring, non-compensatory
  aggregation, condition/pressure separation, evidence tiers) -- not a citation list
  standing in for an explanation.
- Real inline SVG visuals (no external JS dependency, stays a single self-contained
  file): a ranked per-zone bar chart and a condition x pressure quadrant plot.
- **A real bug found and fixed during development, not shipped blind**: the
  quadrant plot's direct text labels overlapped illegibly whenever several zones
  scored similarly -- confirmed by rendering an actual 9-zone test report in a real
  headless-Chromium browser (not just checked for Python syntax), which also caught
  that the LibreOffice-based PDF converter used for an earlier visual check was
  itself misrendering flexbox spacing that a real browser handles correctly --
  re-verified with the right tool before concluding anything was actually broken.
  Fixed with numbered markers + a legend, which cannot overlap regardless of how
  tightly real zones cluster.
- A real per-zone breakdown section for any multi-tile/multi-zone project: every real
  zone's own independent result, not just the project-level aggregate on top of them.
- Semantic `.dk-*` CSS classes throughout, replacing inline styles, so a product team
  can reliably theme or scrape specific values.
- Every evidence-grading and transparency feature from the previous version preserved
  exactly -- additive design work, not a reduction in scientific rigor.

### A real, separate bug found while verifying the above
The report footer's `pipeline_version` was hardcoded to `"0.2.5"` in `report.py` --
silently two real versions stale by the time this was checked (confirmed directly:
a v0.2.7 test run's rendered report still said "Pipeline v0.2.5"). Fixed to reference
the package's own real `__version__` instead of a separate hardcoded string, so this
specific drift cannot recur on a future release.


Client-requested directly: "reduce this manual downloading and uploading process...
the two pipelines can be connected." The site-selection pipeline's real output is now
pushed into this same repository, and `run_project_from_manifest.py` gained a real
`--project <name>` mode (`find_manifest_by_project_name`) that searches this repo for
that project's real `outputs/07_reference_handoff/tile_manifest.json` automatically --
no manual zip, no manual upload, no exact-path lookup required. Deliberately searches
by project name rather than assuming a fixed nested path, since the real pushed copy
sits under a specific, not-guaranteed-stable nesting
(`Darukaa_SiteSelection_pipeline_vAug2026/.../Darukaa_SiteSelection/projects/<name>/...`)
-- this stays robust if that nesting changes on a future push. Ambiguity (two real
manifests matching the same project name) is surfaced as a real error, never silently
guessed at.

Verified directly, by name alone, for all four real, current site-selection projects
now that both pipelines share a repo: Tata Motors (9 zones), Soulforest (7 EMUs), GV
(6 EMUs), and Soova (5 EMUs -- its real count changed in the latest site-selection
push since this was last checked; this resolver reads whatever the current real
manifest says, never a remembered figure).

The GEE step inside the site-selection pipeline itself (`02_covariates`, the
GEE-Code-Editor paste/run/download workflow) remains manual by explicit client
decision for now -- this connects the HANDOFF between the two pipelines, not that
separate, older workflow.

A real, separate finding while verifying this, not yet acted on: Tata Motors' real
`07_reference_handoff/tiles/` folder in the pushed site-selection output contains 146
files, but only the 9 real `EMU_*.geojson` files are referenced by the current
manifest -- the other 137 (`SEG01.geojson` ... `SEG137.geojson`) are orphaned,
stale tiles from before the zone-is-emu redesign. Harmless (never read by this
resolver, which only opens what the manifest lists), but worth a real cleanup pass
on the site-selection side.

### Real module/realm-based indicator filtering (completes an existing, unwired hook)
`config.realm` ("terrestrial"|"aquatic"|"mixed") was already loaded and logged every
run but never actually used to filter anything -- found directly, not assumed, before
completing it. `Pipeline.run()` now filters the active indicator set by realm against
each indicator's own real module tag -- "terrestrial" (default) excludes aquatic-module
indicators, "aquatic" keeps core+aquatic, "mixed" keeps everything -- fully backward
compatible, no existing run's behaviour changes unless realm is explicitly set.
`run_project_from_manifest.py` auto-detects realm="aquatic" from the real project name
(e.g. TataMotors_Pimpri_Aquatic) rather than relying on a user remembering to hand-edit
a shared config.yaml between runs -- a forgotten edit there would have silently
filtered OUT every real aquatic indicator from an aquatic run. Verified directly
(unit-level, since live GEE ecoregion resolution blocks a full run in this sandbox
regardless of this change): realm filtering against the real, current registry gives
terrestrial 35/44 (0 aquatic), aquatic 42/44 (9/9 real aquatic indicators present),
mixed 44/44.

### A real, honest answer on aquatic reference comparison (client asked directly)
Checked every real aquatic-module indicator's actual registration before answering:
wcpi, wsdi, hsas, edpp, mspl, and rci are ALL registered `tier2_eligible=False` --
none currently get a reference comparison or a concern level; they are real,
site-relative context values only (`wcpi`'s own citation note says so explicitly:
"Not comparable across sites"). The underlying Tier-2 stratification mechanism itself
was traced and confirmed sound for a real waterbody regardless (it stratifies the
reference pool by the site's OWN Dynamic World land-cover class, so a lake would
correctly draw other water pixels as reference, not terrestrial ones) -- but that
mechanism never runs for these six indicators today. Promoting any of them to scored
would be real, new, deliberate work (including validating their 10km default
reference radius against how sparsely real water bodies are actually distributed),
not a default to flip on.

### Real aquatic tile extraction for Tata Motors' real water bodies
Confirmed directly against the raw KML: Tata Motors has 6 real, named water body
placemarks (Lake Suman 8.47ha, Lake Sharma 3.61ha, Ponds 1-4) that were only ever
used to build the hard exclusion mask during site selection -- never available as
their own assessable tiles, so the real aquatic-module indicators above have never
had anything to run against for this project. `extract_aquatic_tiles.py` (in the
site-selection repo, alongside Tata Motors' own project folder) extracts them
directly using that pipeline's own proven `kml_utils.parse_kml`, and writes a real,
separate `tile_manifest.json` ("TataMotors_Pimpri_Aquatic") in the exact schema the
terrestrial handoff uses -- runnable via the same `--project` path, verified directly
alongside the terrestrial manifest with no collision between the two.


### C3 fauna pillar — real research done before any code change
Explored external ESG/EIA/TNFD-aligned species metrics directly (not from memory)
before deciding anything. Real finding: IBAT/STAR's own documentation states
"Estimated STAR has a 5km2 resolution, so is not granular enough to offer much
distinction at the level of a farm or asset" -- independent, industry confirmation
that range-map-based species metrics cannot discriminate condition at site/EMU
scale, matching this repo's own existing `threatened_richness` contract note
("zero discrimination (F1)"). Conclusion: BII remains the correct sole scored C3
signal; genuine site-level fauna discrimination has to come from in-situ data
(camera trap, eDNA) via change.py, not another ex-situ proxy.

- **`shi` registered as a real, structural placeholder** (OD-12): SHI is GBF-adopted
  (Goal A) and would be the genuinely correct second C3 signal, but has no simple,
  directly-loadable GEE asset -- confirmed directly (real search): it is served
  species-by-species through Map of Life's own API (api.mol.org), requiring
  registration. `extract_shi` returns an honest `None` with a clear reason, and
  `requires=["mol_api_credentials"]` keeps it out of scoring entirely (verified via
  `registry.eligible`) until real access exists and the function is genuinely
  implemented -- activation is then a single `requires[]` removal, not a
  re-registration.
- **`endemic_richness` / `threatened_richness` area-normalised** to species-per-100km2
  (both the site-level extract_fn and the Tier-1 regional reference fn) -- the raw
  species-range-overlap count scaled mechanically with polygon area, making a small
  site look artificially poorer than a large reference buffer regardless of real
  habitat quality. Real, necessary correctness fix, kept even though disposition
  stays screening-only (client-confirmed: the deeper F1 zero-discrimination problem
  is structural, not a units problem -- promoting these to scored would still be
  wrong). Verified directly via `create_default_registry()` + `apply_contracts()`:
  both indicators confirmed `eligible=False`, correct new units confirmed.

### Corbett's 4 real North Shahdol sites -- verified end-to-end, not assumed
- All 4 real site KMLs (Masira, Pipri, Karpa, Amanar) load correctly via the actual
  `SiteLoader` code -- real areas 100.8/135.2/151.2/15.4 ha, cross-checked directly
  against each KML's own embedded area hint (e.g. "NGO 100H" -> 100.8ha, "AAMANAR
  15.00 HECTOR" -> 15.4ha).
- Ran the real `run_multi_tile_project` path against all 4 sites together as one
  combined, non-compensatorily-aggregated project: registry builds (44 indicators),
  every site dissolves to its correct real area, ecoregion resolution is reached for
  every site, and the run fails cleanly and only at the live-GEE-credentials
  boundary, with `continue_on_tile_failure` correctly recording each site's failure
  independently rather than aborting the whole project on the first one. Confirms
  this repo's only real coupling to a project's own upstream pipeline (or lack of
  one, for a standalone site set like Corbett's) is geometry format.
- Shipped `run_corbett_northshahdol.py`, a ready-to-run Colab entry point for this
  real project (site KMLs go in `corbett_sites/`) -- tested as an actual script
  invocation, not just inline code, before shipping.

## [0.2.6] -- Real site-selection integration built and tested; dead-code sweep; a real validation gap fixed

Started from a direct question: "will this pipeline actually work on our current
EMU delineation, and will it also take independent inputs (Corbett's 4 standalone
polygons, no site-selection run)?" Verified both with real tests, not just code
reading, before building anything further.

### Site-selection integration — built and tested
- Confirmed directly against this repo's own code that `SiteLoader`/
  `project_aggregation.run_multi_tile_project` need one real GeoJSON file per tile,
  each independently loadable, with `site_id` used as-is when already present in the
  file's own properties. The unified site-selection pipeline now has a matching
  `07_reference_handoff/export_tiles.py` stage that produces exactly this — one file
  per EMU, `site_id` set to the real EMU ID, wired into that pipeline's full run.
- **Real test performed, not assumed**: exported EMU tiles from two live projects
  (a compact conservation site, 5 tiles, real single Polygons; a scattered
  agroforestry project, 7 tiles, real MultiPolygons) and loaded every one of them
  with this repo's actual `SiteLoader` code — all confirmed loading correctly.
- **Independent-input claim verified directly**: built a standalone polygon with no
  site-selection pipeline involvement at all (matching a real Corbett-style block)
  and confirmed `SiteLoader` loads it correctly with a sensible auto-generated
  `site_id`. This repo's only real coupling to the site-selection pipeline is
  geometry format — confirmed, not assumed.

### Fixed — a real, latent validation gap
- `scoring.py`: `cond_constructs` (the three declared condition-construct names) was
  defined but never actually used to validate anything — a bare `else` branch
  silently treated ANY benchmark construct label that wasn't literally
  `"C4_pressure"` as a valid condition construct, with no check against the three
  real ones. A typo'd or unexpected construct label from upstream data would have
  been silently folded into the condition rollup as if it were real. Found by an
  automated unused-variable check, confirmed as a genuine gap (not a false
  positive) by tracing the logic, and fixed with real validation — re-tested
  directly with a deliberately bad construct label, confirmed it's now skipped
  with a warning instead of silently scored.

### Removed — confirmed dead code, not working logic
- `reference.py`: a duplicate HMI (human modification index) GEE fetch — the exact
  same asset was being fetched twice under two different variable names one path
  apart; the first fetch (`hmi`) was never used anywhere, confirmed by an automated
  check and by tracing every reference to it. The real, used fetch (`ghm_raw`,
  which the rest of the function's masking logic depends on) is unaffected.
- Unused imports across `change.py`, `config.py`, `html_report.py`, `reference.py`,
  `site_loader.py` — each confirmed genuinely unused (grepped for real usage
  beyond the import line itself, not just trusted the automated flag) before
  removal.
- One automated-check flag (an `ee` reference in `reference.py`) was investigated
  and confirmed to be a false positive — `import ee` is correctly present within
  the same function's scope, just structured in a way the static checker didn't
  follow cleanly. Left as-is, documented as checked rather than silently ignored.

## [0.2.5] -- Colleague-script QA/QC review: real bugs found and fixed, two indicators upgraded, tree-cover gain detection added

A batch of 10 colleague-authored GEE scripts (tree cover loss, FLII, PDF, CHM, TSI(Chl),
SBF, eDNA-PP, riparian NDVI trend, IVSI, JRC water persistence) was reviewed against
this pipeline's existing implementations and against the cited literature -- not
adopted at face value. Findings below; each script is credited where it drove a real
improvement, and this pipeline's own existing code is kept where it was already better.

### Fixed -- a real bug found in THIS pipeline (not the reviewed scripts)
- indicators/__init__.py `_img_ghm`: the SCORED `ghm` indicator's own site-value
  extraction was still hardcoded to the stale CSP/HM/GlobalHumanModification (~2016,
  1km) asset, even though config.hmi_gee_asset was upgraded to TNC HM v3 (90m, 2022)
  for the SEED reference-condition construction back in the SEED-fidelity audit. This
  meant ghm's site value and the reference distribution it gets benchmarked against
  were computed from two DIFFERENT assets -- an apples-to-oranges mismatch. Fixed to
  read the same config-driven asset reference.py already uses. Also fixed the same
  staleness in `_img_eii_s`'s fallback path.
- indicators/__init__.py: a fragile water-body-selection pattern (`water_vec.geometry(1)`
  -- a fixed literal index into whatever order reduceToVectors happens to return) was
  found independently in THREE places: this pipeline's own `extract_rci` and
  `extract_riparian_ndvi_trend`, AND a colleague-authored script for the same purpose.
  All three silently assumed the water body of interest is the second vectorised
  feature, which is not guaranteed and is wrong whenever the water mask is noisy or
  fragmented. Extracted the already-correct pattern from this pipeline's own
  `extract_shdi` (pick the LARGEST polygon by area) into a shared
  `_largest_water_polygon()` helper and applied it to both existing indicators.

### Fixed -- gain/regrowth blindness (the specific concern raised: plantation growth)
- indicators/__init__.py `extract_forest_loss_rate`: Hansen GFC only tracks LOSS. This
  pipeline's own prior version, AND the independently-reviewed colleague script for the
  same metric, both silently assumed loss is the only thing that can happen -- wrong for
  restoration/agroforestry/plantation projects where forest cover genuinely increases.
  Hansen's own "gain" band is a one-time 2000-2012 product, too stale for a current
  assessment. Added independent gain detection: current Dynamic World "trees" presence
  on pixels NOT forested in the 2000 baseline. Both loss and gain rates are now
  computed and reported per window; the SCORED site_value is the NET rate
  (gain - loss), so plantation growth is no longer invisible to the score.

### Upgraded (adopting the colleague scripts' more scientifically rigorous formulas)
- **tspi** (renamed conceptually from a bare NDCI proxy to a real Trophic State Index):
  now computes NDCI (Mishra & Mishra 2012) -> chlorophyll-a via their published
  quadratic regression -> Carlson (1977) TSI(Chl) logarithmic transform -- the actual
  published formula chain end to end, not an approximation of it. Promoted
  context -> scored; given a literature-anchored classification in son_score.py
  (Carlson's classification is one of the few cases where the literature-anchored view
  is arguably MORE authoritative than the reference-relative one, since TSI is
  explicitly designed as a universal lentic-water standard, unlike land indices).
- **flii**: adopted the real published aggregation formula structure,
  `FLII = (10/3)*(3-min(3,P+Q+LFC))`, which the colleague script implemented faithfully
  even though its own P/Q/LFC data sources remained simplifications. This pipeline's
  prior version blended VIIRS nightlight and a crude fragmentation term through an
  ad-hoc combination that didn't structurally match the published formula at all --
  adopting the correct structure is a genuine fidelity improvement. Also fixed the
  weakest link: P (observed pressure) now uses TNC HM v3 (this pipeline's own current,
  already-verified HMI asset) instead of VIIRS alone, which badly understates unlit
  pressures (agriculture, logging roads, most rural conversion). Q and LFC's focal
  radius is now a declared, configurable parameter (config.flii_edge_effect_radius_m,
  default 300m) rather than silently fixed. Still explicitly a Darukaa proxy, not the
  published Grantham et al. raster -- citation and reference_type unchanged from the
  prior audit's correction.
- **chm**: GEDI quality masking upgraded from a bare value-range filter (0-80m) to
  GEDI's own documented quality indicators (quality_flag==1, degrade_flag==0,
  sensitivity>0.9) in addition to the value range -- catches genuinely unreliable shots
  that can still fall within a plausible height range. Neither this pipeline's prior
  version nor the colleague script had this.

### Reviewed and NOT adopted (this pipeline's existing implementation was already better)
- **JRC water persistence**: colleague script hardcoded a 2020-2021 window (now stale,
  ~5-6 years old). This pipeline's own implementation already uses a rolling recent
  window (config.ndvi_year - 1 to ndvi_year) -- kept ours.
- **eDNA persistence potential**: colleague script uses temperature only (openly
  disclosed as a simplification pending UV-B/pH data). This pipeline's own EDPP already
  combines four factors (thermal stress, turbidity protection, moisture, exposure to
  bare ground) from legitimately sourced remote-sensing proxies -- kept ours (context
  tier, unchanged; still a simplification of true eDNA persistence chemistry, but a
  more complete one).
- **IVSI**: colleague script matches this pipeline's existing implementation closely
  (same NDVI-expansion-vs-5-year-prior approach, same honest disclaimer that this is a
  proxy, not species-specific invasive detection, citing the same Paz-Kagan et al. 2019
  caveat). No change needed.

### Reclassified (a categorisation clarification, not a numeric fix)
- **PDF** (Potentially Disappeared Fraction): documented as structurally a WITHIN-SITE
  temporal comparison (site vs. its own historical baseline, like forest_loss_rate),
  not a cross-sectional ecoregion-reference comparison like most other C2 indicators --
  kept context tier (unchanged), but the note now states this explicitly rather than
  leaving it ambiguous. The z=0.25 species-area exponent is not arbitrary despite not
  being pinned by the source document -- it is the commonly-cited canonical SAR
  exponent (Preston 1962; MacArthur & Wilson 1967) -- now cited as such.

### Verified (full end-to-end test on the exact packaged tree)
- Registry: 44 registered, 12 scored (added tspi; C3_fauna still bii). Full mocked
  pipeline run confirms tspi's dual-mode classification (reference-relative AND
  Carlson-literature-anchored) both compute correctly and independently on the same
  input, and every fixed extraction function byte-compiles and loads without error.
- A genuine bug in son_score.classify() was ALSO found and fixed during this batch's
  own testing (not from the reviewed scripts): a position-based special-case fallback
  fired incorrectly whenever a literature-anchored band list was NOT in the same
  descending order as DEFAULT_BANDS (e.g. Carlson TSI, which is ascending), silently
  misclassifying most values to the first band regardless of the true match. Fixed by
  removing the special case and relying on generous outer bounds instead (already the
  correct pattern for every band list) -- caught by testing all 5 TSI bands explicitly
  before shipping, not assumed correct from the earlier natural_habitat-only test.

## [0.2.4] -- Product/dashboard layer: SoN score+class, closed the C3 gap, bidirectional indicator control, maps

Responds directly to a product-design review: "how does a product team building a
client/investor dashboard use this pipeline, and how does it feed a TNFD SoN module."

### Fixed (a real bug, found while building the C3 fix)
- indicators/__init__.py `_img_bii`: was deriving "BII" from EII's own
  `compositional_integrity` band -- not independent data at all, just EII's
  sub-component relabelled. This meant C3 (fauna) had zero genuinely independent scored
  indicators, and made any BII/EII "redundancy" concern true by construction rather than
  a real question. FIXED: now uses the Impact Observatory / Vizzuality Biodiversity
  Intactness dataset (`projects/ebx-data/assets/earthblox/IO/BIOINTACT`, 100m,
  PREDICTS-database-derived; verified as a real, live, widely-used GEE community-catalog
  asset -- Bloomberg's biodiversity risk tooling and TNFD/CSRD reporting products cite
  the same dataset). Moved C2->C3, promoted context->scored. contracts.py, config.py
  citations corrected accordingly. See ASSUMPTIONS §9 for full caveats (community
  catalog, 2017-2020 composite, modelled not observed, not fauna-exclusive).

### Added -- SoN Condition/Pressure score + classification (son_score.py, new module)
- overall_condition(profile) -- the condition roll-up already computed by scoring.py,
  exposed as ONE 0-1 score + a declared 5-band concern class (Very Low..Very High) +
  a confidence flag (how many of the 3 condition pillars actually had data this run --
  so an incomplete assessment never looks identical to a complete one).
- overall_pressure(profile) -- the same for the pressure axis, kept STRUCTURALLY
  SEPARATE from condition, by design -- never combined into one number inside this
  pipeline. AGGREGATION_WALKTHROUGH.md Part C documents this decision explicitly.
- Per-indicator dual-mode classification: "reference_relative" (bands the same
  normalised benchmark already used for scoring -- always available) and
  "literature_anchored" (bands the RAW value using a published breakpoint, only where
  one is defensibly ecoregion-independent -- currently just natural_habitat, anchored
  to Andren/Fahrig fragmentation thresholds; see son_score.LITERATURE_BREAKPOINTS).
  Both shown where both exist; never one silently replacing the other.
- report.py: son_summary now in every report; scorecard rows carry per-indicator
  classification.
- html_report.py: Overall Condition / Overall Pressure rendered as colour-coded badges
  at the top of the report, with confidence and limiting-component stated alongside;
  scorecard table gains a Class column showing both classification modes.

### Added -- bidirectional indicator control (contracts.py)
- request_deactivation() -- the counterpart to request_activation() (v0.2.1): lets a
  client turn OFF a default-scored indicator, not just add beyond the default. No safety
  tiers needed in this direction (deactivating can only make a report smaller, never
  less defensible). Every deactivation carries the same client_override visibility as
  an activation -- never silent.

### Added -- maps in Colab (geemap)
- notebooks/run_pipeline.ipynb, new Section 9b: renders an interactive geemap.Map for
  every scored indicator with a live GEE image behind it (site + buffer, indicator layer
  + site boundary overlay). Indicators without a mapped GEE image are listed, not
  silently skipped.

### Changed -- notebook Section 4b, full rebuild
- Now shows ALL 44 registered indicators grouped by pillar (C1-C4), with the Darukaa
  recommended default highlighted, in one table -- readable without opening any other
  document, as requested. Both activation and deactivation lists editable in the same
  cell. Mirrored into the multi-tile section.

### Changed -- documentation
- AGGREGATION_WALKTHROUGH.md: corrected an now-outdated statement that the pipeline
  produces no single score/class (true before this batch, no longer the whole story);
  added Part C describing the new product layer precisely, including what remains
  deliberately NOT done (blending condition+pressure into one number).
- ASSUMPTIONS_AND_LIMITATIONS.md: SS9 (BII fix) and SS10 (classification system caveats)
  added.
- README.md, INDICATOR_REGISTER.md: regenerated/updated to reflect the above.

### Verified (full end-to-end test on the exact packaged tree)
- C3_fauna now has a real scored indicator (bii) with independent data; confidence flag
  correctly reports 3/3 condition pillars assessed (was structurally impossible before,
  since C3 was always empty).
- overall_condition and overall_pressure both populate correctly and independently;
  natural_habitat's dual-mode classification correctly shows two different bands from
  its two different bases (reference-relative vs literature-anchored) on the same
  synthetic input, proving they are genuinely computed separately, not aliased.
- Bidirectional control: deactivating a default then activating a new one both take
  effect correctly in the same run; deactivating an already-inactive indicator returns
  "already_inactive" rather than erroring.

## [0.2.3] -- Ex-situ metrics review, terminology fix, general-purpose cleanup

A team-authored ex-situ metrics methodology document was reviewed carefully against the
existing pipeline (not accepted at face value). Findings and their disposition:

### Confirmed correct, no change needed
- forest_loss_rate: the reviewed document's own Formula field says "no official formula"
  and proposes an unannualized static-window percentage. Our existing windowed,
  annualized, baseline-stability-flagged implementation (config.forest_loss_windows) is
  already more rigorous; not changed.
- KBA/IBA overlap, threatened/endemic species richness: reviewed document's own framing
  (static IUCN range polygons; "should not be interpreted as official classification")
  confirms the existing screening (not scored) disposition was correct.

### Fixed (terminology, found during review)
- contracts.py, OPEN_DECISIONS.md, INDICATOR_REGISTER.md: EII's aggregation was
  documented as "fuzzy-minimum". The reviewed document's own scientific justification
  confirms it is a hard LIMITING-FACTOR MINIMUM (lowest of 3 sub-scores), not fuzzy
  logic. Corrected throughout; OD-1 closed on this point (sub-score formulas themselves
  remain Landbanking's unpublished proprietary algorithm -- flagged as still open).

### Flagged as findings, not adopted
- FLII: the reviewed document also computes a Dynamic-World+VIIRS proxy (not the real
  Grantham et al. product) but then applies Grantham's official numeric thresholds
  (9.6/6.0) to that proxy's output. Those thresholds are calibrated to the original
  four-component algorithm, not to a simplified proxy -- adopting them would manufacture
  false precision. Not adopted; existing relative (robust-z, no absolute threshold)
  treatment retained.
- Aridity Index: reviewed document proposes scoring absolute aridity as "concern"
  (hyper-arid = Very High Concern) -- a category error for naturally arid ecoregions
  (a desert is not "degraded" for being a desert). Not adopted; aridity stays context,
  not scored, as before. If ever scored, must be an anomaly/trend relative to the site's
  own ecoregion norm, never an absolute global scale.
- LAI: reviewed document confirms MODIS MCD15A3H (500m) -- the same coarse-resolution
  pattern already fixed for land cover (Copernicus 100m -> Dynamic World 10m). Flagged
  for a future finer-resolution alternative; not changed this batch (no confirmed
  10m-class LAI product identified yet).
- EII/BII/MSA/PDF redundancy: these are four different methodological traditions
  measuring closely related signals (species/community condition relative to reference).
  Flagged as a Gate-A-style redundancy candidate (keep EII as scored parent, others as
  context if added) -- a decision for the next batch that adds them, not made here since
  BII/MSA/PDF are not yet in the registry.

### Added
- AGGREGATION_WALKTHROUGH.md -- new standalone document: the complete indicator ->
  subdimension -> component -> condition roll-up -> pressure -> matrix-cell path,
  written out step by step for (a) a conservation project (single or multiple separate
  sites) and (b) an agroforestry project (many tiled parcels), with the one additional
  cross-tile step named explicitly. States plainly that the pipeline does NOT produce a
  universal 0-10 score or a VL-VH concern label at the pillar/overall level -- a
  deliberate methodology choice, not a gap.

### Removed (general-purpose cleanup)
- START_HERE.md -- a stale, redundant duplicate of README.md that had been silently
  reappearing in packaged zips since it was only ever deleted from a staging copy, never
  from the source tree. Removed permanently from source.
- All references to specific past projects and a personal GEE project ID
  (North Shahdol, Corbett, gaurav-singh-007) genericized across README.md,
  METHODOLOGY_MASTER.md, ASSUMPTIONS_AND_LIMITATIONS.md, NPI_CROSSWALK.md,
  OPEN_DECISIONS.md, config.py, and the notebook -- this is a general-purpose pipeline,
  not tied to any one project. CHANGELOG's own historical provenance entries (which
  describe what actually happened, by version) were left as-is; that is legitimate
  audit-trail content, not a stray reference.

## [0.2.2] — First-live-run fixes: blocking bug, real PNV crosswalk, indicator activation, citation fix

Everything here came from an actual first live-run attempt and the questions it raised.

### Fixed (blocking)
- notebooks/run_pipeline.ipynb Section 5: `Pipeline(config).run(...)` was missing the
  required `registry` argument (`TypeError: Pipeline.__init__() missing 1 required
  positional argument: 'registry'`) -- registry was never constructed in the notebook.
  Fixed in both the single-site and multi-tile sections.

### Fixed (real data supplied by the user)
- config.py: pnv_to_dw_crosswalk was an empty, unverified placeholder (OD-8). Replaced
  with the REAL mapping built from the live PNV asset's actual class legend (20 biomes,
  band 'biome_type') -- pnv_to_dw_crosswalk_verified is now True. Three biome mappings
  (sclerophyll woodland, open woodland, tropical savanna) are documented judgement calls,
  flagged inline, since Dynamic World's 9 classes are coarser than PNV's 20 biomes.

### Fixed (citation integrity, found during a targeted asset audit)
- indicators/__init__.py + contracts.py: the `flii` indicator was cited as the actual
  Grantham et al. (2020) Forest Landscape Integrity Index. It is NOT -- the code computes
  a Darukaa-built proxy (VIIRS nightlight + Dynamic World forest fragmentation), not that
  published 300m product. Citation and reference_type corrected; renamed "Forest
  Fragmentation & Pressure Proxy (Darukaa)". A live GEE asset for the real FLII product
  was searched for but not confirmed -- flagged as open in ASSUMPTIONS §6.
- indicators/__init__.py: forest_loss_rate's three temporal windows were hardcoded with
  an explicit "never per-client configurable" comment. Moved to
  config.forest_loss_windows (freely extensible, e.g. add a 10-year window) while
  config.forest_loss_primary_window stays pinned to the long-term record by default --
  preserving the anti-cherry-picking protection (the SCORE can't be silently swapped to
  a favourable window) while making the reporting genuinely customisable.

### Added -- indicator activation (client-facing "what could I score instead")
- registry.py: IndicatorSpec.client_override / client_override_note fields;
  IndicatorRegistry.availability_table() -- every registered indicator, its disposition,
  current scoring status, and why, in one table.
- contracts.py: request_activation() -- lets a client request indicators beyond the
  default scored set be scored, tiered by how defensible that is: "context" disposition
  promotes freely; "screening" only with an explicit force flag (caveat travels with it
  permanently); "remove" (e.g. CERI) never promotable this way -- refuses with the
  specific construct flaw, since that needs a methodology fix, not a config flip.
- report.py / html_report.py: client_override is now visible in the JSON scorecard and
  rendered as a "CLIENT-ACTIVATED" badge in the HTML report -- never indistinguishable
  from a Darukaa-default scored indicator.
- notebooks/run_pipeline.ipynb: new Section 4b -- displays the full availability table,
  lets the user edit two lists (indicators to activate, which to force past a screening
  caveat) and applies them before the pipeline runs. Same mechanism wired into the
  multi-tile section.

### Verified (full end-to-end test replicating the exact fixed notebook flow)
- Pipeline(config, registry) constructs and runs correctly; an activated
  ("natural_landcover") indicator is confirmed scored, confirmed client_override=True
  in the real report output; flii's corrected display name and reference_type confirmed
  in the actual scorecard row.

### Known gaps, documented (not fixed this batch)
- Monitoring mode (config.assessment_mode="monitoring") is accepted but not auto-wired
  -- pipeline.py logs a warning and still runs baseline-style. change.py exists and is
  unit-tested but must be invoked manually across two runs' reports. See ASSUMPTIONS §8.
- Asset audit for resolution/recency covered the 10 scored-by-default indicators only;
  the other 34 registered indicators have not been re-audited. See ASSUMPTIONS §6.

## [0.2.1] — Self-contained multi-tile aggregation (agroforestry / large multi-parcel projects)

Adds a self-contained driver for projects whose AOI is too large or too fragmented for
one darukaa_reference run to be geographically meaningful (agroforestry with many
scattered smallholder parcels is the canonical case) -- previously this required a
separate pipeline for the run-and-aggregate step; it no longer does.

### Added
- project_aggregation.py -- new module:
  - _dissolve_tile_to_geojson(): merges every placemark within a tile's KML into ONE
    geometry before running the pipeline (a tile is one assessment unit, not N --
    Pipeline.run() otherwise treats every placemark as its own separate site).
  - aggregate_tiles_noncompensatory(): combines N tile-level reports into ONE
    project-level profile. THE AGGREGATION RULE: for every scored indicator, the
    project signal is the WORST TILE's signed benchmark (the same limiting-factor
    principle scoring.py already applies across subdimensions and components, applied
    one level further, across tiles) -- named explicitly, not averaged away. An
    area-weighted geometric mean (of normalised scores) and a plain area-weighted mean
    (of the raw indicator value, a physically additive quantity) are reported as
    secondary/context only, never as the headline. The combined worst-tile-per-indicator
    values feed into the SAME scoring.build_site_profile() a single site uses -- no
    parallel aggregation logic invented at the profile level.
  - run_multi_tile_project(): the orchestrator -- dissolves each tile, runs the existing
    single-site Pipeline on it unchanged, collects results, aggregates, and writes
    project-level + per-tile json/csv/html. Tile failures are caught, logged, and
    recorded explicitly in the output (never silently dropped); the project run
    continues with the remaining tiles by default.
- html_report.py: renders a "Multi-tile aggregation" section (aggregation rule,
  per-indicator worst-tile table) when a report contains multi_tile_summary.
- README.md: the agroforestry section now shows actual runnable code instead of prose
  describing a workflow that depended on a separate, external repository.
- notebooks/run_pipeline.ipynb: added a full multi-tile section (upload tiles, configure, run_multi_tile_project, worst-tile-per-indicator table, project profile, HTML report, download-everything cell) as an alternative to the single-site flow — the notebook previously had no path to the new driver.

### Verified (synthetic multi-parcel tiles, mocked GEE layer)
- A small (2.3 ha), degraded tile correctly dominates the project-level worst-tile
  headline for every scored indicator, despite a co-existing tile 4x larger and in
  good condition -- the non-compensatory property holds end-to-end through the real
  Pipeline / scoring.build_site_profile code paths, not just in isolated unit tests.
- The single-tile case (i.e. a conservation project run through this driver) produces
  the same result as calling Pipeline.run() directly -- confirmed the trivial case
  degrades correctly.

## [0.2.0.1] — Structural SEED-fidelity audit and correction

A careful re-read of McElderry et al. (2024) Sec. 3.1-3.2 and Eq. 1 against the actual
v0.2.0 code found that the earlier "SEED-faithful" reference path had diverged from the
paper in several places that mattered scientifically, not just cosmetically. All are
fixed here (not just re-documented). Full item-by-item record in
ASSUMPTIONS_AND_LIMITATIONS.md Section 1 (items S-1 through S-9).

### Fixed (structural -- the algorithm now matches the paper)
- PNV's role: was used as the primary land-cover classifier for every pixel. SEED
  uses it only to relabel pixels whose contemporary class is "artificial" with their
  potential natural class. Corrected in reference._build_ecoregion_landcover_image.
- Stratification unit: was "ecoregion as primary mask, PNV supplies the class."
  SEED strata are ecoregion AND land-cover, jointly. Corrected.
- Elevation banding: not part of SEED; was the default. Moved to an explicitly
  separate, off-by-default legacy_landcover_elevation mode.
- Ecoregion constraint (latent bug): eco_id was threaded through the entire call
  chain into _compute_tier2 but never actually applied -- the reference pool was only
  buffer-constrained. Now genuinely ecoregion-masked via ECO_ID, in both modes.
- Kernel formula: was a weighted Manhattan (L1) distance with independent per-
  indicator weights -- not SEED's Eq. 1. Replaced with a real Mahalanobis-distance
  kernel (estimators.mahalanobis_kernel_diagonal / _full) using the reference sample's
  covariance, with a numerically-stable diagonal default and an honest, disclosed
  fallback path for "full" mode when the reference sample is too small to invert.

### Upgraded (resolution/recency audit)
- HMI asset: CSP/HM/GlobalHumanModification (1 km, frozen ~2016) -> TNC/HM/v3/90m_s
  (90 m, 2022 static snapshot, RMSE 0.178) -- same authors' direct successor. Legacy
  asset available via use_legacy_hmi_asset=True.
- Land-cover source: COPERNICUS/Landcover/100m/Proba-V-C3/Global/2019 (100 m, frozen)
  -> GOOGLE/DYNAMICWORLD/V1 (10 m, modal composite over a rolling lookback window)
  for the SEED-faithful path.

### Added
- estimators.fit_delta_diagonal -- SEED's stated delta-calibration routine (maximise
  corr(K, 1-HMI) within a stratum); verified to recover a known delta on synthetic data.
- estimators.shrinkage_covariance, mahalanobis_kernel_full -- full-covariance kernel
  path with shrinkage regularisation, implemented and unit-tested, available but not
  the default (see "Known scope boundary" below).
- ReferenceResult.stratification_diagnostics / ComparisonResult.stratification_diagnostics
  / scorecard row stratification_diagnostics -- mode, masks applied, land-cover class,
  PNV-correction status, and fallback level now flow into the standard JSON report
  automatically. No separate diagnostic export needed to validate a live run.
- config.pnv_to_dw_crosswalk + pnv_to_dw_crosswalk_verified -- the PNV to Dynamic-World
  class relabelling table, shipped as an explicitly-flagged, unverified placeholder
  (logs a warning every run until verified against the live asset legend -- OD-8).

### Removed
- estimators.seed_kernel (L1 magnitude-weighted) -- replaced; not SEED's formula.

### Known scope boundary (not a bug -- a deliberate, disclosed limit)
- The "full" Mahalanobis covariance path needs co-located, multi-band reference pixel
  sampling (all of a construct's indicators sampled from the same pixels) to produce a
  meaningful covariance matrix. That GEE-side sampling infrastructure is not wired into
  the default pipeline; "diagonal" mode remains the default for this reason (OD-10).

## [0.2.0] — UNRELEASED — "Peer-review response"

### Batch 5 — OD-3 / OD-4 / OD-5 + cycle-2 change scoring
- **OD-3 variance-stability reference floor** (`estimators.reference_is_stable`, wired into
  `reference._reference_accepted`): a reference is accepted only if it clears the pixel
  floor AND its bootstrap median SE is within tolerance (`reference_stability_rel_tol`,
  default 0.15); otherwise the score is **suppressed** rather than computed on noise.
  Replaces the arbitrary fixed floor as the acceptance criterion (gated by
  `use_variance_stability_floor`). Applied at all three Tier-2 acceptance points.
- **OD-4 multivariate SEED kernel** (`estimators.seed_kernel`,
  `construct_seed_similarity`): the SEED `exp[-δ·‖w⊙(z−z_r)‖₁]` similarity-to-reference,
  attached per construct as an OPTIONAL view (`use_seed_kernel`, `seed_kernel_delta`) —
  complements, never replaces, the direction-aware per-indicator benchmarks.
- **OD-5 ecoregion-primary + PNV reference stratification** (`reference._compute_tier2`):
  `reference_stratification="pnv_ecoregion"` uses the Potential Natural Vegetation class
  and constrains the reference to the site's ecoregion FIRST (SEED-faithful; avoids
  stratifying on already-modified contemporary land cover). Legacy
  `landcover_elevation` remains the default. New config: `pnv_gee_asset`,
  `ecoregion_gee_asset`. (GEE code path; validated by construction.)
- **Cycle-2 change scoring** (`change.py`): `change_score` (delta vs own Year-0 with
  propagated uncertainty + a detection test), `baci_contrast` (impact minus control
  change), `score_cycle`, and `from_report` (diff two cycle report dicts). This is where
  in-situ metrics finally score — as change, from cycle 2 onward.

### Batch 4 — pipeline wire-through
- **`pipeline.py`:** runtime toggle applied — REMOVED (`registered=False`) and deactivated
  indicators are never computed (CERI excluded live); `assessment_mode`/`realm`/`archetype`
  logged and stamped into the report; monitoring-mode guard added (change-vs-baseline needs
  a stored Year-0 artifact — OD); completion log reports scored-profile count and .json/.csv/.html.
- **`report.py`:** the evidence-graded **HTML report is now emitted on every run** (standard
  pipeline output, CS-10); project context (`assessment_mode`, `realm`, `archetype`) added to meta.
- **`example_run.py`:** summary rewritten to the profile-first output (indicator status counts,
  per-site limiting factor, condition roll-up + minimum + sensitivity, pressure axis); fixed the
  stale `pillar_summary` key; docstring updated.
- **Version bumped to 0.2.0** (`__init__.py`, `setup.py`).

### Batch 3 — benchmark propagation, sensitivity harness, evidence-graded HTML report
- **`statistics.py`:** `ComparisonResult` now carries the responsive benchmark
  (`tier1/2_benchmark`, estimator, percentile, display %, `reference_type`,
  `reference_hmi_realised`), propagated from `ReferenceResult` in `compare()`. This is
  the connector that makes `site_profiles` populate on real runs — scoring consumes the
  signed benchmark, never the capped ratio (CS-3/CS-10).
- **`scoring.py`:** added `sensitivity_report()` (CS-5 condition 4) — recomputes the
  condition roll-up under equal + each-component-tilted weightings; if the coarse band
  flips the roll-up is flagged **UNSTABLE** (publish as such or withhold; profile shown
  regardless). Attached to every site's `condition.sensitivity`.
- **Added `html_report.py`** — evidence-graded standalone HTML "Evidence Record"
  (Nandoshi model, CS-10): every claim carries its evidence grade; scored / contextual /
  screening / pending / removed shown separately; profile-first (limiting factor →
  condition × pressure matrix → secondary roll-up with stability flag + framing block);
  signed benchmark and uncapped % of reference displayed. Deterministic projection of the
  report dict; no external dependencies.

### Batch 2 — indicator contract population, redundancy screen, profile-first scoring
- **Added `contracts.py`** — declarative CS-1 contract + disposition for all 44
  indicators (construct, subdimension, measurement scale, evidence tier, reference
  type/estimator, input layers, module) with `apply_contracts()` and a Gate-A
  `redundancy_guard()`. Auto-applied by `create_default_registry()` (CS-1/CS-2/CS-4/CS-7).
- **Added `scoring.py`** — profile-first hybrid: limiting-factor rule within components,
  non-compensatory penalised geometric mean + published minimum across components, state
  vs pressure separated into a condition × pressure matrix, declared reversible logistic
  normalisation, and the mandatory framing block (CS-4/CS-5).
- **Dispositions applied:** scored set reduced from 44 → **10** (7 condition + 3
  pressure). `ceri` **removed** (registered=False; arithmetically perverse, F3);
  `threatened_richness`/`endemic_richness`/plant variants/`kba_overlap` → **screening**
  (F1); `eii` scored at **parent** with structural/compositional/functional as context
  (Q4); `natural_landcover`/`ndvi`/`habitat_health`/`bii`/`pdf`/`lai`/EII-components →
  **context** (Gate A / modelled); `chm` retained (additive); `star_t` → context.
- **`report.py`:** version → 0.2.0; new `site_profiles` (profile-first) and
  `indicator_status` (scored/contextual/screening/removed) sections; scorecard rows carry
  construct/subdimension/evidence_tier/scoring_eligible + signed benchmark; **corrected
  pillar labels** ("Species Population Size" → "Faunal abundance/activity … NOT population
  size"; extinction-risk pillar marked retired, B8/F1); legacy `_pillar_summary`
  **deprecated** (kept for comparison), scoring now consumes the signed benchmark not the
  capped ratio.

### Batch 1 — foundations + SEED reference keystone

### Added
- **Indicator contract** on `IndicatorSpec` (CS-1): `construct`, `subdimension`,
  `ecological_question`, `management_use`, `input_layers`, `measurement_scale`,
  `spatial_grain`, `temporal_period`, `effort_basis`, `evidence_tier`, `realm`,
  `module`, `reference_type`, `reference_estimator`, `threshold_basis`,
  `uncertainty_method`, `restoration_sensitivity`, `reassessment_frequency`,
  `management_trigger`, `registered`, `active`, `requires`. All additive with safe
  defaults — existing `register(...)` calls remain valid unchanged.
- **Computed eligibility** (`IndicatorSpec.eligible`, `.scoring_eligible`) enforcing
  the toggle rule *active ⟹ eligible*; `eligible` is never hand-set (CS-1 / Q7).
- **`estimators.py`** — responsive, scale-aware reference estimators: log response
  ratio (ratio-scale), robust standardised deviation + percentile-in-reference
  (interval/bounded), `benchmark()` dispatcher (CS-3, C-G2, F-HMI-1).
- Registry queries: `by_construct`, `scored`, `contextual`, `pending`,
  `by_input_layer` (the last powers redundancy Gate A).
- `Config` project context: `realm`, `archetype`, `assessment_mode`,
  `reference_estimator_default` (CS-10) + YAML `project:` section.
- `ReferenceResult` responsive-benchmark fields (`tier*_benchmark`,
  `tier2_percentile_in_reference`, `tier2_display_pct_of_reference`,
  `reference_type`, `reference_hmi_realised`).

### Changed
- **Reference estimator (CS-3):** the responsive `estimators.benchmark` is now
  computed for every indicator alongside the legacy ratio; scoring will consume the
  responsive value (enforcement in the scoring batch). Signed & uncapped, so
  above-reference restoration gains are visible (NPI "responsive to increases AND
  decreases"; C-B6/C-G2).
- **HMI ceiling restored to 0.05** (was 0.10) — SEED's maximum allowable HMI for the
  counterfactual reference (F-HMI-2). Now also loadable from YAML and the realised
  threshold is reported per run (F-HMI-2 transparency).
- **Reference pixel floor** unified to `12` in both the dataclass and the YAML loader
  (F-HMI-5; interim value pending a variance-stability criterion — OD-3).

### Fixed
- **`min_reference_pixels` inconsistency bug** — `config.py` default (5) and the YAML
  loader default (20) disagreed; both now `12` (F-HMI-5, repo-hygiene CS-13).
- HMI ceiling documentation contradiction (docstring 0.05 vs config 0.10) resolved.

### Deprecated
- `ReferenceSelector._intactness_ratio` — legacy capped ratio; retained for
  back-compat/display only. Do not use for scoring (censors improvement; invalid for
  non-ratio scales). Superseded by `estimators.benchmark`.

### Deferred (next batches / next cycle)
- Populate the contract on all 44 indicators; redundancy screen demotions (CS-2).
- Switch `report.py` scoring to the responsive benchmark; profile-first hybrid;
  non-compensatory aggregation; uncertainty + sensitivity (CS-4/CS-5).
- Multivariate SEED kernel option; PNV stratification; variance-stability pixel
  criterion (F-HMI-3/4/5, OD-3).

## [0.1.0] — as-reviewed baseline (archived)
- The state of the pipeline as submitted for the North Shahdol review. Preserved for
  before/after comparison in the peer-review response.
