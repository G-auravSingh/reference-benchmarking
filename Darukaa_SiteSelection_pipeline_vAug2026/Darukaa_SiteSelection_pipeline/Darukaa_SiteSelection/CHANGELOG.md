# Changelog

Chronological record of what changed and why, in the order it was found —
not a marketing summary. Several entries here contradict an earlier
entry's stated result; that's intentional, it's the real trail.

## v0.1 — Initial unified architecture (from `Darukaa_SiteSelectionPipeline_v6.0`)

Consolidated the old repo's two separate tracks (`main.py` geographic-
cluster path, `run_project.py` segmentation path) into one pipeline routed
by archetype (`agroforestry` / `conservation` / `industrial`). Reused
rather than rewrote: `crs.py` (unchanged) and `PHASE_2_GEE_ExSitu.js`
(copied as `pipeline/gee/covariates_and_segmentation.js`, then
progressively fixed — see below).

## v0.2 — Real bugs found by running against real project data

- **Legacy KML attribute parser off-by-one.** Soova's description-table
  KML format was parsed with every field shifted by one column
  (`{'763493190': 'latitude', ...}` instead of `{'farmername': 'Jagala
  Majhi', ...}`). Fixed by anchoring on the literal `"Name"` cell instead
  of the first "non-structural" one.
- **44/50 Soova farm polygons found genuinely self-intersecting** in the
  source KML (real digitization artifact, not a parser bug) — 12 of them
  resolve to `MultiPolygon` after repair. Flagged for client review rather
  than silently accepted.
- **GEE asset upload format wrong.** Documented as "Table Upload → GeoJSON"
  — GEE's Assets manager does not accept this. Fixed: every project now
  exports a verified-readable zipped Shapefile instead.
- **`CANDIDATE_SCHEMA`'s join-key logic re-derived independently at 5
  separate call sites** in the shared GEE script, despite the script's own
  comment claiming it was "resolved once." Added a `"unified"` schema
  value and fixed all 5 sites to share one resolved variable.
- **`RUN_SEGMENTATION` toggle wrapped the wrong code**, including the
  unconditional polygon-level covariate reduction — meant that with
  segmentation off (every agroforestry project), the reduction step never
  ran at all, producing GEE's real "Required argument (primary) missing"
  error. Fixed by splitting into two `if` blocks around the always-runs
  reduction.

## v0.3 — Contiguity

- **Every segmentation-derived EMU found spatially disjoint** on real data
  (one "segment" had 12 separate parts). Root cause: a raw SNIC
  `SEGMENT_ID` can itself span disconnected patches, and the merge step
  only chose which segment to merge into, never verified the result stayed
  connected. Fixed with connected-component decomposition before merging,
  strict adjacency-only merging, and a hard runtime assertion.
- **That same fix had a units bug**, found when the assertion fired again
  on the very next real run: adjacency was computed on raw lat/lon
  *degrees* against a metres-denominated threshold (0.5m read as 0.5°, or
  ~55km) — making "adjacency" nearly meaningless. Fixed by reprojecting to
  the metric CRS before every distance comparison.
- **Agroforestry EMUs found even more scattered** than the segmentation
  case — one real EMU had 471 tiles and 481 disjoint parts (essentially no
  two members adjacent). Added a spatial k-NN connectivity constraint to
  the Gower-distance clustering.
- **The connectivity constraint alone still allowed "chaining"** — a real
  EMU spanned 22km despite every consecutive link being locally close.
  Added a hard post-processing spatial-diameter cap (KMeans split) — but
  only applied when it doesn't push EMU count past the device-coverage
  ceiling; otherwise the spread is kept and reported honestly rather than
  breaking the coverage guarantee to fix it.

## v0.4 — Minimum-mapping-unit auto-tune, position scoring

- **42 EMUs for a 27ha site** — SNIC's raw segmentation was used
  completely unmerged, with no analog to agroforestry's device-count
  ceiling. Implemented MMU auto-tune matching the Pimpri methodology's own
  documented precedent (70 raw segments → tuned threshold → 10 final,
  matching device count).
- **The "uncovered EMU" fallback was a soft warning** — changed to a hard
  error per explicit policy: "if we decide an EMU, we must cover it." A
  project that can't cover every EMU it delineates is a bug to fix at the
  source (re-tune the EMU target), never a client-facing finding.
- Built `03b_position_scoring`: CRITIC-weighted typicality ranking within
  each EMU, matching the Pimpri methodology's own documented method.
- **The first position-pool algorithm (farthest-point sampling) was found
  to be mathematically biased toward EMU corners/edges** — a real,
  checkable property of that algorithm, not a tuning issue. Replaced with
  spatial-bin selection (KMeans-partitioned regions, best-typicality pick
  per region), which gives the EMU's interior a real chance at a pool slot.

## v0.5 — Exclusion zones, anchors, aquatic

- **Soft-exclusion zones (e.g. a mixed admin/green area) were fully
  excluded from the candidate grid**, identical treatment to hard
  exclusions — meaning a genuinely green sub-patch inside a "mostly
  built" zone could never become a candidate. Fixed: only hard exclusions
  are removed from tessellation; soft-exclusion area is tessellated
  normally and resolved pixel-by-pixel once real `BuiltUp_Pct` data exists.
- **Ecological anchors (client-declared real habitat features) had zero
  member tiles** beyond their own boundary — meaning no real covariate
  data and no actual candidate points ever existed inside them. Fixed:
  anchors are now tessellated too, with resulting tiles claimed directly
  by that anchor (never split into multiple EMUs).
- **The shared GEE script's aquatic export was hardcoded to a single,
  fixed Tata Motors waterbody asset** — confirmed by three separate
  projects' aquatic CSVs being byte-for-byte identical, including
  waterbody names belonging to a different project. Fixed: default is now
  "skip" (`WATERBODY_ASSET_PATH = ""`), matching the script's own
  previously-contradicted comment; each project now gets a real waterbody
  asset generated from its own declared water features (agroforestry
  projects never get one, by hard rule).

## v0.6 — Documentation gap, and the four items above resolved

- **A real, serious gap found and fixed**: this pipeline had zero
  documentation files despite `Darukaa_SiteSelectionPipeline_v6.0` having
  nine (README, START_HERE, METHODOLOGY, ASSUMPTIONS, CHANGELOG, PATCHES,
  REFERENCES). Added `README.md`, `METHODOLOGY.md`, `CHANGELOG.md` (this
  file), `docs/PIPELINE_METHODOLOGY_REFERENCES.md` (the real v6.0 file,
  carried forward with its citations intact, extended for what's new
  here), and `docs/OUTPUT_FILE_GUIDE.md`.
- **District-aware logistics panels** — implemented and verified: GV's
  panels are now checked to never mix EMUs from different districts.
  Real cost surfaced honestly rather than hidden: this pushed one project
  into needing its policy-allowed 1-week extension, and made one panel's
  travel-time flag worse — because it's now measuring the real
  same-district spread instead of an artifact of cross-district mixing.
- **Weekly within-EMU position rotation implemented** (`continuous_proportional`
  regime) — the biggest remaining gap from v0.5, now real: device
  allocation per EMU (largest-remainder method), and a genuine week-by-week
  schedule rotating through each EMU's position pool, verified on real
  Soulforest data (a 1-tile EMU correctly "pool wraps" — repeats its only
  position both weeks, matching the Pimpri methodology's own documented
  behaviour for its smallest-pool segments).
- **Field map rebuilt with real per-EMU and per-week filtering** — not
  just an overlay toggle. Selecting an EMU shows that EMU's full candidate/
  parcel pool plus its position pool, isolated. Selecting a week shows only
  that week's real active position(s) per EMU (from the actual weekly
  rotation data), not a generic "cycle" grouping.
- **Report rebuilt** to match the Pimpri methodology document's depth:
  purpose/scope, the site as measured, design principles, this run's real
  methodology diagnostics (MMU search trace, clustering K-bounds, CRITIC
  weights — all read from actual JSON, nothing invented), stratification
  result, position pool status, deployment schedule, covariate profile, an
  output-file guide, and declared caveats compiled from every stage's own
  warnings.
- **This changelog's own "Open" section was found stale** while writing
  this entry — it still listed weekly rotation and district-aware panels
  as unresolved after both had already been fixed earlier in the same
  work session. Corrected here as a reminder to re-check documentation
  against actual pipeline state before considering a round of work done,
  not just at the end of a long session.

## v0.7 — Field map/report client-readiness pass, verified against a real Tata Motors reference file

Working from a real TM `field_map.html` and its methodology doc, compared
directly against ours rather than assumed correct:

- **Cycle count bug, root cause found**: `continuous_proportional`'s
  achievable-cycles count used the same turnover-day formula as
  `sequential_cluster`. Confirmed against the real TM file
  ("New position every week, all season" — no reduction applied there) that
  a device which never leaves its EMU doesn't need the multi-day
  redeployment buffer between weeks. Fixed: cycles = `project_duration_weeks`
  directly for this regime. Soulforest went from 1 cycle to the correct 4.
- **A second, related date bug found while verifying the fix**: the
  schedule's day-offset labels still used the buffer-inclusive turnover
  even after the cycle-count fix, producing a 10-day gap between weeks
  instead of 7 (caught by a real date mismatch in the CSV export, not by
  inspection). Fixed — weeks are now genuinely back-to-back.
- **A third, unrelated stale-config bug found in the same pass**:
  Soulforest's own `config.yaml` still had `logistics_buffer_days: 3`, the
  same stale override fixed in FCF_Soova/FCF_GV two rounds ago but missed
  here. Corrected.
- **Candidate-points invisibility, root cause found**: the "pool positions
  never used" layer (600+ real candidates) was built but never added to
  the map by default — visible only if someone found and checked a layer
  control box they had no reason to expect existed. Now on by default,
  matching the TM reference file's own always-visible "Candidate frame."
- **EMU count mismatch (7 in legend, 6 visible), root cause found**: not a
  data bug — a genuinely tiny EMU (one 25x25m grid cell) is imperceptible
  as a polygon at normal zoom. Added a permanent centroid marker for any
  EMU under 40m across.
- **Client-facing candidate names fixed**: were showing raw internal IDs
  (`grid_00535`) in map popups. Added a separate `display_name` field
  (e.g. `SFV-T0001`, matching TM's `PMP-T060` convention) used only for
  display — the internal `name` field is left untouched specifically
  because it's the join key already baked into any GEE asset/CSV a project
  has already uploaded; renaming it would have silently broken that match.
- **Camera trap given real position logic**, not just a legend entry: a
  project-wide (not per-EMU) 4-position pool, spatially binned so the
  positions spread across distinct site regions, 2-device weekly rotation
  independent of the audiomoth schedule.
- **Streams legend fixed** to only list streams with real position logic
  (audiomoth, camera trap) — the other configured streams (soil/eDNA/water
  quality) are real parts of the project but are one-time fixed-location
  samples, not something with a rotating position to show on this kind of
  map; they now get their own separate, honest note instead of implying
  they work the same way.
- **Medoid/best-scoring distinction simplified**: hover tooltips now show
  just the position name; the full technical rationale (including "stratum
  medoid" where it applies) stays in the click popup, where there's room
  to actually explain it.
- **Report jargon removed**: "Member cells" (meaningless to a client)
  replaced with real computed EMU area in hectares and a plain-language
  "how it was identified" description.
- **Deployment schedule CSV/Excel export built** — real calendar dates
  (start date set per-project in `config.yaml`; Soulforest's is
  2026-09-06, given directly), not just day-offsets. Falls back to
  relative day labels for a project that hasn't set a start date yet,
  rather than refusing to export.

## v0.8 — Two more real bugs found by cross-checking suspicious numbers, plus the sampling-design redesign

Working through a batch of feedback that started with "we are not going to
cover all stratums in each week" (a fundamental correction — Soulforest is
a one-time baseline survey, not a season-long comparison like Tata Motors)
and ended up surfacing two independent, serious data-quality bugs along
the way:

- **`sampling_design: stratified_single_pass` added as a genuinely
  separate regime** from `continuous_multi_week` (the existing TM-style
  one). Each EMU is now assigned to exactly ONE week, with 1+ devices
  proportional to a real spacing-based capacity estimate — large EMUs
  anchor their own week near-full, small ones share a week and split
  devices by size, matching the described design exactly once run against
  real Soulforest data (verified: Fruit Forest and SEG01 each got 6
  devices in their own week, SEG02 got 4 in a shared week, small EMUs
  paired up with 1 each).
- **Idle-device inefficiency found and fixed in the new regime**: a week
  with only a small-capacity EMU left most devices unused (Wetland alone
  used 1 of 7). Fixed with a bonus-redistribution pass — leftover devices
  go to that week's active EMU(s) for extra spatial coverage, capped at
  3x base capacity so a tiny stratum doesn't get absurdly over-sampled.
- **Camera trap pool size corrected**: was a 4-position rotating pool;
  now 8 distinct positions (2 devices x 4 weeks), no wrapping, per
  direct correction ("we can actually cover 8 points distributed properly").
- **A real, serious bug found in `TreeCover_Pct`**: confirmed at the raw
  GEE CSV level — all 653 Soulforest candidates showed exactly 0.0, while
  NDVI showed real, varied vegetation. Root cause: the existing formula
  permanently zeroes any pixel with ANY recorded forest-loss event since
  2000, with no mechanism to recognize regrowth — exactly wrong for a
  restoration/plantation site, which is this project's entire premise.
  Fixed by switching to the current (2025), already-loaded Esri land-cover
  "Trees" class instead of the frozen Hansen-based calculation. Requires a
  fresh GEE run to take effect in already-downloaded data.
- **A defensive check added** to `05_metrics_rollup`: any covariate
  showing identical values across every EMU is now flagged automatically
  (zero variance across a whole site is almost never real ecological
  uniformity) — this would have caught the TreeCover_Pct bug without
  needing it pointed out by eye.
- **A second, independent, more serious bug found while verifying EMU
  membership counts**: 149 of 618 EMU-assigned candidate tiles (24%) had
  actually FAILED the built-up/water hard filter in `02_covariates` —
  `segmentation_reconciliation.py` was only checking `SEGMENT_ID`, never
  the hard-filter result, meaning candidates sitting on real buildings or
  water could become valid, schedulable device positions. Fixed at both
  the anchor-claiming and segment-grouping stages.
- **That fix then surfaced a THIRD bug, this time in the land-cover
  classifier itself**: applying the hard filter correctly caused the
  client-confirmed "Fruit Forest" ecological anchor to drop from 148
  candidates to 7 — 141 of its tiles showed `BuiltUp_Pct` near 100.
  Cross-checked against NDVI for those exact same tiles: 0.24-0.35,
  essentially identical to the "non-built" tiles and physically
  inconsistent with a real impervious surface (which shows NDVI near
  zero). This is the Esri land-cover product misclassifying a young
  plantation's bare-soil-between-rows pattern as "Built Area" — a real
  classifier failure mode on managed/transitional landscapes, not a
  genuine finding. Fixed with an NDVI override: a cell with NDVI at or
  above a conservative real-vegetation threshold (0.2) is kept regardless
  of what the built-up classifier says. 179 candidates were affected at
  Soulforest; this is now flagged explicitly in `02_covariates`'s
  warnings whenever it fires, on any project.
- **EMU colour assignment made deterministic**: was whatever order a plain
  dict happened to iterate in; now explicitly sorted (anchors first
  alphabetically, then segments in natural numeric order) so colours are
  reproducible and predictable across regenerations, not just internally
  consistent within one run.

## v0.9 — Camera trap repeat-position bug, and a full manual report read-through

- **Camera trap positions were repeating across weeks** despite the pool
  being correctly sized to 8 distinct positions — found by reading the
  actual CSV output line by line, not by inspection. The rotation used a
  sliding window (`pool[(week-1+d) % len(pool)]`), which reuses an index
  across consecutive weeks by construction. Fixed to consecutive
  non-overlapping slices — confirmed all 8 positions now genuinely distinct.
- **A full manual read-through of the rendered report** (not just "does it
  build without error") surfaced three more real issues:
  - "Total candidates ingested: 1" sat right next to "Tessellated grid
    cells: 653" for a contiguous archetype — technically correct (the "1"
    is the pre-tessellation KML placemark count) but looked exactly like a
    broken pipeline to anyone reading it. Removed for contiguous
    archetypes in favour of the real, meaningful number.
  - The position pool table was still showing raw internal names
    (`grid_00582`) — the `display_name` fix from two rounds ago had been
    applied to the field map and CSV export, but missed this one spot in
    `position_scoring.py`'s own report output.
  - The covariate profile table showed `BuiltUp_Pct`'s worst-EMU flag
    (Fruit Forest, 100) with no link to the classifier-misclassification
    finding already documented elsewhere — a client reading only this
    table would see an unexplained, alarming number. Added a caveat
    connection and a visible warning marker directly in the table row,
    not just buried in the caveats section.

## v1.0 — Compactness architecture redesign, and the same client-readiness pass applied to GV

The GV compactness issue turned into a real lesson in stopping before compounding a bad fix:

- **Confirmed the client's read of "secluded points" directly**: EMU_Ganjam_2's
  two outlier tiles are 86-100km from its other 47 members — real,
  correctly-labelled Ganjam-district parcels, not a data error.
- **Two increasingly complex EMU-splitting attempts, both found broken on
  the next real run, and reverted rather than patched further**: an
  all-or-nothing compactness split left the worst violations completely
  unaddressed even with budget headroom available; a budget-aware version
  fixed that but crashed the scheduling stage's own panel-count budget; a
  panel-aware version stopped the crash but verified NOT to actually
  resolve the spread (several EMUs still spanned 80-133km). Rather than
  attempt a fourth patch under time pressure, reported this honestly and
  reverted `ecological_clustering.py` to the pre-compactness-splitting
  state.
- **Adopted a fundamentally simpler fix instead, suggested directly**: a
  severe spatial outlier doesn't need its own EMU at all — real ecological
  membership (and therefore real ex-situ metrics) stays intact regardless
  of how far-flung a member parcel is. It just shouldn't be eligible as a
  DEVICE POSITION, since no field team makes a separate trip for 1-2
  parcels. Implemented in `03b_position_scoring.py` via the modified
  z-score method (median + MAD, robust to the outliers themselves skewing
  the threshold) — confirmed on real data: flagged exactly the 2 real
  Ganjam_2 outliers, and found a genuine, cleanly bimodal 20km+ gap in a
  much larger partition (Gajapati_1) rather than over-flagging a normal
  continuous spread.
- **The idle-device inefficiency (found for Soulforest) generalized to
  `sequential_cluster` too** — confirmed the same problem in GV's real
  schedule (3 EMUs using 3 of 4 devices in cycle 1). Fixed with the same
  bonus-redistribution principle: under-filled panels get proportional
  extra positions instead of leaving devices idle.
- **The missing hard-filter check (found and fixed for Soulforest's
  segmentation path) was never added to `ecological_clustering.py`** —
  fixed for consistency, though it currently has zero real impact on GV
  (0 of 1893 candidates fail the filter there).
- **Colour palette replaced** — the old set had three different greens and
  two different blues, which wash out at the ~35-50% fill opacity used for
  EMU polygons and become hard to tell apart for adjacent EMUs. Replaced
  with a standard maximally-distinct categorical palette.
- **Two stale/misleading report statements found and fixed**: the "spatial
  contiguity is a structural guarantee" design principle was shown
  unconditionally in every report, including agroforestry ones, where
  EMUs are legitimately multipart/scattered by design — now archetype-
  aware. The methodology section still described the compactness-cap
  approach after it was removed — updated to describe what the pipeline
  actually does now.
- Position pool table and declared caveats now surface exactly how many
  candidates were excluded from device eligibility as spatial outliers,
  per EMU.

## v1.1 — Fresh GEE re-run for both projects, and the TreeCover_Pct fix confirmed insufficient

- **Fresh GEE data ingested for both SoulForest Veltoor and FCF GV** — first
  real re-run since the v0.8 TreeCover_Pct fix (Esri land-cover "Trees"
  class) was written.
- **Confirmed directly: the v0.8 fix did NOT resolve TreeCover_Pct for
  Soulforest** — still exactly 0.0 across all 653 candidates on the fresh
  data. Cross-referenced against `NatCoverPct_2km` (only ~10-12% here
  despite real NDVI of 0.24-0.50) confirmed this is a genuine Esri
  land-cover classifier failure to recognize this site's vegetation at
  all — the same root cause as the BuiltUp_Pct misclassification, not a
  formula bug that picking a different class value could fix.
- **Real fix implemented**: replaced the categorical land-cover dependency
  entirely with an NDVI-threshold-based canopy proxy (NDVI > 0.3,
  documented as a deliberately moderate, site-context-aware choice, not a
  universal forest definition), computed at the pixel level from the
  same validated NDVI composite already used for `NDVI_raw` — not from
  land-cover classification at all. The Esri-classifier and Hansen-based
  versions are kept as secondary reference bands
  (`TreeCover_Pct_EsriClassifier`, `TreeCover_Pct_Hansen_LossAdjusted`).
- **A real ordering bug caught while implementing the fix, before it ever
  ran**: the new threshold constant was used before its own declaration
  point in the script (JS hoists `var` declarations but not their
  assigned value — would have silently evaluated as `undefined`). Fixed
  by moving the constant to the top of the file with the other
  configuration values.
- **Confirmed working on GV's fresh data**: TreeCover_Pct now shows real,
  meaningful variation there (median 35.5%, 1105 of 1893 candidates
  nonzero) — GV's classifier isn't affected by the same failure Soulforest's
  is, and the new NDVI-based formula generalizes correctly to a site where
  the old approach would have worked too.
- **Requires a fresh GEE run to actually produce corrected Soulforest
  values** — this round's report still shows TreeCover_Pct = 0 for
  Soulforest because the uploaded CSV was run against the pre-fix script.
  The regenerated `ready_to_run.js` has the fix baked in for next time.
- Re-verified every other Aug 2026 fix (outlier exclusion, idle-device
  redistribution, camera trap distinctness, NDVI override) against this
  fresh data rather than assuming they still held — all confirmed working,
  including on GV EMUs not previously spot-checked (outliers now also
  found and correctly excluded in Ganjam_3, Gajapati_1, Kalahandi_1).

## v1.2 — Real position-selection algorithm redesign, grounded directly against the Tata Motors methodology document

Started from three direct questions and a detailed critique of a real
Soulforest run, and went to the actual Pimpri methodology document for
grounding rather than guessing:

- **Confirmed TM's own TreeCover_Pct uses the same Hansen loss-adjusted
  approach this pipeline started with, and it works fine there** —
  Soulforest's failure (v1.1) is a genuine, site-specific edge case
  (restoration ecology), not a needless departure from a validated method.
- **Minimum device spacing was never actually verified** — the KMeans
  spatial-binning position selector spread picks across regions but never
  checked real pairwise distance, confirmed capable of placing two
  positions in the same EMU directly next to each other. Replaced with a
  genuine greedy constraint-satisfaction algorithm
  (`select_spacing_compliant_positions`) using true Euclidean distance —
  confirmed against the real TM document's own explanation of why a
  square-grid spacing check under-serves diagonal neighbours (1.41x the
  pitch) that true Euclidean distance needs no lattice correction for.
  Re-verified directly on real output: zero spacing violations across
  every simultaneously-active position.
- **EMU device capacity was a crude area-divided-by-a-spacing-circle
  estimate** — confirmed against the real TM document ("each segment's own
  candidate pool is checked for how many spacing-compliant positions it
  can actually support — this is what the deployment schedule actually
  draws from") that capacity should come from actually checking real
  candidate positions, not an area formula. Fixed: capacity is now
  whatever `select_spacing_compliant_positions` actually finds. Confirmed
  on real data this was a real, meaningful error in both directions — SEG04
  (flagged directly as "big but only getting one device") went from a
  formula-estimated capacity of 1 to a verified 3; Wetland went from an
  estimated 1 to a verified 2 (checked its real bounding box — 171m x
  101m — which appears to be genuinely too tight for 4 positions at 100m
  spacing, not a bug).
- **A bug caught immediately after that fix**: the idle-device bonus-
  redistribution ceiling (3x base capacity) could exceed the newly-correct,
  tighter real capacity — confirmed directly (SEG04 allocated 7 devices
  against only 3 real available positions). Fixed to cap bonus allocation
  at the real capacity ceiling, never above it.
- **Camera trap redesigned from an independent project-wide pool to
  co-located with whichever EMU(s) audiomoth covers each week** — found
  the exact justification directly in the real TM document ("co-located
  with the terrestrial PAM position, rotating which segment it accompanies
  week to week"). Two more real bugs caught while verifying this: a
  name-mismatch (internal vs. display name) meant camera trap's own
  "avoid audiomoth's exact spot" logic silently never worked at all, and
  a genuinely single-candidate EMU (SEG05) forces camera trap to share
  audiomoth's exact position with no alternative — not a bug, but now
  explicitly flagged as a declared, unavoidable constraint rather than a
  silent coincidence.
- **A scientific-defensibility check added**: flags any pair of EMUs with
  near-identical covariate profiles (a real, direct question: "are these
  ecologically different? We should be able to defend that"). Building
  this properly surfaced its own real bug — land surface temperature
  (1km resolution) and night lights (~500m) are far coarser than these
  segments and were contributing pure noise, not signal, to the
  comparison; excluded, matching this pipeline's own documented caveat
  about those two covariates. **The corrected, full-covariate check found
  no defensibility concern for Soulforest's current segmentation** — an
  earlier informal 4-covariate eyeball comparison had overstated the
  similarity between SEG01 and SEG03/SEG04; the proper, comprehensive
  check (13 real covariates, appropriately normalized) shows real,
  meaningful separation.
- **`stratum_profile.csv` added** — matches the real Tata Motors
  deliverable of the same purpose ("what each segment IS, in covariate
  terms"), one row per EMU across all 15 covariates.
- `min_device_spacing_m`'s default (100m) is unchanged, but now cites its
  real derivation, confirmed against the TM document: double the
  upper-bound effective acoustic detection radius (25-50m in vegetated
  habitat), so two recorders' detection zones cannot overlap even under
  favourable conditions.

## v1.3 — Orphan-segment-to-anchor merging, a real methodology gap closed

Started from a direct, image-grounded observation: "SEG05 doesn't really
make much sense as an ecological monitoring unit — it's so small that
just one point comes inside it, and ecologically it sits simply between
the wetland and fruit forest."

- **Confirmed exactly against real geometry**: SEG05 (1 tile, 0.06ha) had
  distance = 0.0m to BOTH the Fruit Forest and Wetland anchors (genuinely
  touching both), and 50m+ from every other segment — a real three-way
  transition point, not a distinct micro-habitat.
- **Root cause found**: `_merge_small_segments`'s MMU auto-tune only ever
  considered merging a small segment into another SEGMENT — anchors are
  resolved earlier (via centroid-containment) and were never revisited as
  a possible merge target for a leftover tiny segment touching them from
  outside. This is a structural methodology gap, not specific to one
  segment.
- **Fixed generically**: any segment remaining below `emu_min_tiles` after
  MMU merging that genuinely touches an anchor is now folded into
  whichever anchor it shares the LONGEST real boundary with (checked
  directly: the real case was a near-tie, ~26m vs ~24m, confirming a
  meaningful tie-break was actually necessary, not just point-adjacency).
  The anchor's own displayed boundary is dissolved to include the merged
  tile, so its polygon on the map matches its true membership.
- **A real units bug caught immediately while verifying this fix**: the
  merge computation used raw, unprojected lat/lon geometry with a
  0.5-unit epsilon meant for metres (the same class of bug fixed twice
  before elsewhere in this exact file) — the reported shared-boundary
  length came out as 0.0m against an independently-verified real value of
  ~26m. Fixed by reprojecting to the metric CRS before every distance/
  length computation in this block, matching every other place in the
  module that already does this correctly.
- **Result on real Soulforest data**: SEG05 is gone; 6 real EMUs remain (2
  anchors + 4 segments); contiguity re-verified — every EMU still a
  single connected polygon after the merge; the schedule's idle-device
  warning also cleared (0 warnings, down from 1) as a side effect of the
  cleaner EMU set.

## v1.4 — TreeCover_Pct fix confirmed working, and a real corner-touching contiguity bug found and fixed

Fresh GEE re-run of Soulforest, first real test of the NDVI-threshold
TreeCover_Pct fix (v1.1/v1.2) against real data:

- **Confirmed TreeCover_Pct fix works**: real, meaningful variation across
  the site now (2.0% to 63.0%, median ~19%) — no longer flagged as
  identical/suspicious. The defensive "identical value" check correctly
  stayed silent on it this run, confirming the check itself responds
  dynamically to real data rather than being hardcoded to a known issue.
- **A real, new contiguity crash found and fixed**: the same segment ID
  that caused a contiguity failure in an earlier round failed again on
  this fresh data (different underlying SNIC topology, since tree-cover
  and other bands changed, but the same structural bug). Root cause this
  time: two grid cells touching only at a single diagonal CORNER have
  real distance() == 0.0 (not a units issue) — `unary_union` correctly
  refuses to dissolve a corner-only connection into one solid polygon,
  but this pipeline's own connectivity check treated distance <= epsilon
  as sufficient, without requiring an actual shared edge. Fixed in both
  `_connected_components` and `_merge_small_segments` by requiring a
  positive-length boundary intersection, not just proximity — matching
  exactly what `unary_union` will and won't dissolve, so the two checks
  can no longer disagree.
- **Caught and fixed a bug in the fix itself**: the first attempt added an
  `or shared.area > 0` fallback using buffered geometries, which silently
  re-introduced the same corner-touching leniency the fix was meant to
  remove (a small buffer around any touching corner always has positive
  overlap area). Found by re-testing directly against the same real data
  rather than assuming the first attempt worked — removed the fallback
  entirely.
- **Result**: full pipeline re-run clean, every EMU re-verified as a
  single connected polygon (2 anchors + 3 segments this run — the exact
  segment count and topology shifted from previous runs since the input
  bands feeding SNIC changed, which is expected and correct, not a
  regression). Zero spacing violations, 8 distinct camera trap positions,
  all previously-verified fixes re-confirmed holding on the new data
  rather than assumed to still apply.
- GV and Soova re-confirmed stable — this fix lives entirely in
  `segmentation_reconciliation.py`, used only by contiguous archetypes.

## v1.5 — GV district correction, extent-aware position spacing, and the Soulforest camera trap map bug fixed

- **Soulforest camera trap map bug fixed**: confirmed the exact root cause
  reported directly — the map still read from a static, project-wide
  `camera_trap_pool.geojson` left over from before camera trap was
  redesigned to co-locate with audiomoth's weekly active EMU(s). Checked
  directly: that file's position names had ZERO overlap with the real
  schedule's actual camera positions, so a week filter never matched
  anything. Camera points are now built directly from the real schedule,
  with coordinates looked up from the same source everything else on the
  map uses. Verified: exact match between rendered points and each week's
  real active camera names.

- **GV district data quality — independently verified, not assumed from
  either side**: checked the client's own manual correction (13
  previously-unassigned parcels) via k-nearest-neighbour geographic voting
  against all ~1900 confidently-tagged parcels — confirmed exactly
  correct (11 to Ganjam, 1 to Gajapati, 1 to Kandhmal, all 6-8/8 votes
  under 1.5km). Separately checked a Gemini-sourced claim of "28
  mistagged Kandhmal parcels" the same rigorous way — found NOT supported
  by the data at all (checked all 412 Kandhmal-tagged parcels
  comprehensively, zero disagreements) — and found that a smaller, real
  batch of 4 "mistagged Kalahandi" parcels was correctly identified but 2
  of the 4 had the wrong TARGET district claimed (should be Kandhmal, not
  Ganjam as reported). Implemented as an explicit, auditable
  `district_corrections` config table, each entry with its own real
  verification evidence in a comment — not a silent data patch.
  `unknown_barrier_group` is now completely gone from GV's output.
- **A real bug in this fix, caught immediately by checking actual
  output**: the correction was written under the wrong dict key (missing
  that `canonical_attrs`' internal keys are unprefixed — the `attr_`
  prefix is added later), silently making the whole correction a no-op
  despite the config loading correctly and the matching logic being
  right. Fixed and re-verified: 0 empty districts, every named correction
  confirmed applied to the exact right value.

- **The "EMUs appear to intersect" concern investigated directly**:
  checked every pair of GV's 9 EMU polygons for genuine geometric overlap
  — zero found. The visual effect is real but not data corruption:
  scattered agroforestry EMUs with interleaved parcels look like they
  cross on a map even though no polygon ever actually overlaps.

- **The same "concentrated deployment points" issue from Soulforest,
  confirmed present here too — and traced to a real, different root
  cause**: checked GV's real EMU extents directly — they span 14 to
  152km, not the ~100-300m of Soulforest's compact segments. The 100m
  minimum-spacing constraint (correct, acoustic-detection-derived, for a
  compact site) is essentially meaningless at that scale — any real
  candidate placement trivially satisfies it without needing to spread
  across more than a tiny fraction of the EMU. Fixed by scaling the
  effective spacing requirement to each EMU's own bounding-box diagonal
  and target pool size, with the real acoustic floor as a hard minimum —
  a compact EMU is completely unaffected, a vast one now gets genuinely
  representative spread. Verified directly: one EMU's positions now span
  62-131km apart, actually representing its real 152km extent, instead of
  a concentrated cluster.

- **Panel district-purity re-verified** after the district corrections
  changed EMU composition — confirmed all 4 GV cycles are still
  single-district only.

- **Two stale/confusing report messages found and fixed** while reading
  the actual rendered GV report: a Soulforest-specific finding
  ("141 of 148 candidates...") was hardcoded into a shared warning
  message and leaked verbatim into GV's report — generalized. A
  partition-level "spans more than Xkm" warning had become redundant with
  (and less informative than) the newer per-EMU outlier-exclusion
  warning from `03b_position_scoring` — removed in favour of the
  authoritative, more specific one.

## v1.6 — Outlier detection redesigned twice in one round, and a real orphan-EMU merge fix for agroforestry

Three direct, specific observations about a real GV run, each investigated
before any code changed:

- **"Intersecting EMUs" clarified**: not overlapping polygons (already
  checked, zero) but an interleaved spatial pattern (EMU1, EMU2, EMU1,
  EMU2...). Checked directly with a real, decisive test: for every
  parcel, is its single nearest neighbour in the same EMU? Result: 97.7
  to 100% consistency across all four districts — the clustering is
  genuinely locally coherent, not truly interleaved. The earlier visual
  impression was very likely a symptom of the two real bugs below, both
  now fixed.
- **A serious, real bug found in the outlier-exclusion redesign** (the
  same mechanism from v1.5): confirmed directly that Gajapati_1's
  deployment points were ALL clustered in one area while a large,
  legitimate northern portion of the same EMU had zero — traced to the
  outlier detector (median + MAD distance-to-centre) wrongly flagging 174
  of 246 real northern parcels (71%!) as "outliers" simply because they
  sat far from the EMU's overall median, with no regard for whether that
  "far" group was itself a real, substantial population. Gajapati_1 is
  genuinely bimodal (in fact, made of dozens of real village-level
  sub-communities), not one dominant cluster with a few strays — the
  method's core assumption was wrong for this data.
- **Redesigned with DBSCAN, then found and fixed a bug in the redesign
  itself within the same round** — checked immediately rather than
  trusting the first version: scaling `min_samples` to a fraction of EMU
  size (24 for a 493-member EMU) made DBSCAN's density requirement too
  strict for real but non-uniformly-packed clusters, making exclusion
  WORSE (87%, up from 36%). Then found a second bug on the very next
  check: using a PERCENTAGE-of-EMU-size threshold for "is this a real
  cluster" wrongly flagged dozens of genuine small village communities
  (5-40 members each) as outliers just because each was small relative to
  a 493-member EMU. Fixed by decoupling cluster formation (small, fixed
  `min_samples=3`) from the "real cluster" decision (a small ABSOLUTE
  size floor, not a fraction) — verified directly: Gajapati_1's northern
  exclusion dropped from 71% to 10%, and its real deployment points now
  span both real sub-populations instead of only the southern one.
  Re-verified Soulforest unaffected (0 false positives on its compact,
  non-bimodal EMUs).
- **A real, direct EMU_Ganjam_2 (1 parcel, sitting near larger EMUs)
  investigated and fixed generically**: agroforestry has no ecological-
  anchor concept to merge an orphan into (unlike the equivalent Soulforest
  fix), but the same principle applies — a 1-2 parcel EMU near other,
  larger EMUs is far more likely a clustering artifact than a genuinely
  distinct stratum. Added `merge_orphan_clusters`: any cluster below
  `emu_min_tiles` is folded into whichever other cluster's nearest member
  is geometrically closest, real proximity rather than requiring literal
  touching (farm parcels are rarely adjacent the way grid cells are).
  Verified: GV went from 9 EMUs (2 spurious 1-2 parcel orphans) to 7, all
  with real, substantial membership; panel district-purity re-confirmed
  unaffected.

## v1.7 — EMU renumbering, client-facing report cleanup, documentation audit

- **EMU numbering gap fixed**: reported directly ("still using older names
  like Ganjam 1 and 3 are there but no 2"). Root cause: merging an orphan
  cluster (v1.6) reassigns its members but never renumbers the remaining
  label values, leaving gaps. Fixed by renumbering sequentially by
  descending size right before EMU ID assignment — "_1" is now always a
  partition's largest EMU, a consistent, meaningful convention. Verified:
  GV's 7 EMUs are now Ganjam_1/_2, Kandhmal_1/_2, Gajapati_1,
  Kalahandi_1/_2, no gaps.
- **A real, serious client-facing bug found and fixed**: the report
  template referenced `METHODOLOGY.md`, `CHANGELOG.md`, and
  `docs/OUTPUT_FILE_GUIDE.md` — internal repository files a client
  receiving only the HTML report would never have access to. Found in
  three places (design principles, output files section, references).
  Fixed: removed the redundant internal pointers where the surrounding
  content already covered the ground, and replaced the References section
  entirely with real, curated, inline citations (CRITIC, SNIC, Hansen,
  Esri land cover) instead of pointing at an inaccessible file — a
  references section that just points to a file the reader can't open
  isn't a references section.
- **The "5 weeks" report confusion investigated and fixed**: not a bug —
  `project_duration_weeks` (5, the available project timeline) and
  `n_cycles_scheduled` (4, what's actually needed) are both real, correct,
  different numbers, but the report only showed the first, with nothing
  explaining why the schedule below only showed 4. Overview table now
  shows both explicitly, with a plain-language note on which applies and
  why.
- **Documentation audit**: checked every project's field_map.html and
  stratum_profile.csv for the same internal-reference leak — none found
  (issue was report-template-specific). Confirmed README.md's repository
  layout table against the actual file tree — found and fixed one real
  gap (`schedule_export.py` / the CSV/Excel export wasn't mentioned).
  Confirmed CHANGELOG.md's own chronological ordering is intact.

## v1.8 — Interior/edge balance in position selection, a real mathematical bias confirmed and fixed

- **A real, client-raised scientific concern, verified before agreeing or
  changing anything**: "best selected points are always at the edge —
  there should be a proper mix-match." Checked empirically first: computed
  every pool position's real distance to its EMU's own dissolved boundary
  and compared against the full candidate distribution. Confirmed real —
  several positions sat closer to the boundary than 90%+ of that EMU's
  actual candidates.
- **Root cause identified as mathematical, not a data bug**: greedy
  selection that maximises minimum pairwise distance has a real,
  well-known tendency to push points toward a bounded region's boundary —
  there's structurally more room to be far from already-picked points
  near an edge than deep in the interior. This is the same underlying
  property farthest-point sampling was replaced for once already (Aug
  2026, earlier); it was reintroduced by the otherwise-necessary switch to
  real spacing verification, which farthest-point sampling didn't
  guarantee.
- **Fixed by blending real distance-to-boundary into the selection order**
  (not the spacing constraint itself, which stays purely geometric): every
  pick after the medoid now weighs "is this reasonably interior" against
  "is this a good, typical spot," instead of chasing pure typicality until
  spacing forces an edge choice. The medoid itself is exempt — it's
  specifically meant to be the single most representative point by
  typicality alone.
- **Verified honestly, not oversold**: most EMUs showed a real, meaningful
  improvement (one went from picks clustered at low percentiles to a
  genuine spread across the full range). One small EMU (bounding box 100m
  x 254m) still shows edge-heavy positions after the fix — checked
  directly and confirmed this is a genuine geometric constraint (no
  arrangement of 3 points >=100m apart stays interior in a polygon that
  narrow), not an algorithm failure left unfixed.
- Re-verified the hard minimum-spacing guarantee is untouched: zero
  violations after the change. Confirmed GV and Soova unaffected (same
  shared code, real re-run, no regressions).

## v1.9 — Camera trap never got the interior-bonus fix; a real geometric limit distinguished from a real bug

Two specific, concrete complaints about SEG01 and SEG03, investigated
geometrically before any change:

- **SFV-T0172 (SEG01) checked against the real AOI boundary directly**:
  confirmed it was NOT actually outside the property (12.1m inside; the
  grid cell's own polygon touches but does not cross the boundary — 0m²
  outside). Checked every EMU's dissolved geometry against the real AOI:
  zero area outside anywhere. The "extends beyond the KML" impression was
  not a geometry bug on inspection — most likely a visual read at a given
  zoom level on a point genuinely close to the edge.
- **A real, second bug found in the exact same mechanism just built**:
  the camera trap position selection (`panel_scheduler.py`) never passed
  `boundary_dist` to `select_spacing_compliant_positions` at all — it was
  still running the pre-fix, pure-typicality algorithm regardless of the
  interior-bonus fix already applied to the main audiomoth pool. This
  directly explains why a camera trap position in SEG03 sat at the exact
  minimum-X edge — the correction simply never applied to it. Fixed:
  computed from the EMU's real full geometry, same method as the
  audiomoth pool.
- **`interior_bonus_weight` increased from 0.3 to 0.5** after testing
  directly against SEG03's real data — confirmed real, if bounded,
  further improvement (a pick moved 25m off the exact edge at higher
  weights) before plateauing.
- **SEG03 (100m x 254m bounding box) still shows some edge-proximate
  picks after both fixes — checked and confirmed this is a genuine
  geometric constraint, not an unfixed bug**: the medoid itself sits
  reasonably centrally (37.5m from the boundary — confirming this EMU's
  most representative point isn't an edge artifact), but the *additional*
  positions, once forced >=100m away from it in a polygon only 100m wide,
  have nowhere non-edge-adjacent left to go. Reported honestly rather than
  claimed fixed.
- Re-verified after both fixes: zero spacing violations, GV and Soova
  unaffected, SFV-T0172 no longer selected at all under the corrected
  ranking.

## v2.0 — Real darukaa_reference integration built and tested

- **New `07_reference_handoff` stage**: exports each EMU as its own real
  GeoJSON tile file, matching `darukaa_reference`'s actual, confirmed
  input requirement (`project_aggregation.run_multi_tile_project`, one
  file per tile). Wired into the full pipeline run for all archetypes.
- **Real test performed, not assumed working**: exported tiles from both
  Soulforest (5 tiles, real Polygons) and GV (7 tiles, real MultiPolygons)
  and loaded every one of them with `darukaa_reference`'s actual
  `SiteLoader` code directly — all confirmed loading correctly, `site_id`
  used exactly as provided.
- **A real, serious bug found and fixed in the existing handoff
  artifact**: `emu_reference_handoff.geojson` (from `05_metrics_rollup`)
  had `"geometry": None` hardcoded, with a comment claiming downstream
  code would "dissolve on demand" — no such code existed anywhere,
  making the file completely non-functional as a handoff artifact
  despite existing since an earlier round. Fixed with real dissolved
  geometry per EMU. Also found and removed a genuinely dead variable
  (`handoff_features = []`, created but never populated or read).
- Confirmed directly (not just asserted) that `darukaa_reference` also
  accepts fully independent inputs with no site-selection involvement at
  all — built a standalone polygon matching a real Corbett-style block
  and loaded it successfully with the same `SiteLoader` code.

## v2.1 — Season-reset position rotation for multi-season projects (Tata Motors Pimpri)

- **A real correction to my own proposal, caught by a direct question**:
  I initially proposed reusing a "continuous, never-reset" rotation design
  built for a completely different device role ("boost" — maximum spatial
  coverage, explicitly NOT meant for season comparison). The actual
  requirement (confirmed directly: keep positions consistent across
  seasons so observed variation is attributable to season, not to a
  different physical spot) needed the OTHER already-validated design
  ("semi-anchor" — reset every season, same position at the same relative
  week each time). Corrected before any code shipped, not after.
- **`build_weekly_rotation` now supports season-reset**, via a new
  `season_length_weeks` config field (None by default — every existing
  project's behaviour is completely unchanged; only a project that
  explicitly declares itself season-structured gets the new logic).
  Verified directly with a synthetic test: a 5-position pool over 8-week
  seasons gives the exact same position at week-in-season 1 of every one
  of 3 seasons, with the wrap-around wholly consistent across seasons too.
- **A second real, explicitly-accepted design decision**: small zones
  with fewer real spacing-verified positions than a season has weeks will
  necessarily get more temporal replication at their few real positions
  than large zones with more positions get at each of theirs (confirmed
  directly: a 5-position pool over 8 weeks gives 3 positions 6 visits and
  2 positions only 3). This is real, visible, and correctable later
  (e.g. via position-ID as a random effect at analysis time) — not hidden
  or silently treated as equal-confidence data.
- Re-verified: Soulforest and GV, which never set `season_length_weeks`,
  produce byte-identical rotation behaviour to before this change.

## v2.2 — Zone-scoped multi-EMU rotation for large zones (Tata Motors Pimpri)

- **New `zone_scoped_continuous` regime**: for a real zone split into
  multiple real sub-EMUs (a "large" zone — Deccan forest, Narmada
  valley), the single device assigned to that zone now rotates BETWEEN
  its own sub-EMUs across weeks, not just between positions within one
  EMU. A "small" zone (one sub-EMU) behaves identically to the existing
  position-only rotation — this is a strict generalisation, not a
  parallel mechanism with different behaviour for the simple case,
  confirmed directly via a synthetic test mixing both.
- **Nested, season-reset rotation, verified directly**: which sub-EMU is
  visited cycles through the zone's own EMU list (largest first);
  position WITHIN whichever sub-EMU is currently visited also varies by
  how many times that specific sub-EMU has already been revisited this
  season — the same "real temporal replication instead of pretending
  more spatial replication than the geometry supports" principle already
  agreed for small zones, applied here to repeated EMU visits. Verified
  with a synthetic 3-sub-EMU zone over a 24-week/3-season programme:
  correct round-robin order, correct position advance on each revisit,
  correct full reset at week 9 (season 2) back to sub-EMU 1 / position 0.
- **A real architectural gap caught and fixed**: the existing regime-
  selection logic chooses `continuous_proportional` only when total EMU
  count fits within device count — but a zone-partitioned project's TOTAL
  EMU count (summed across every zone's own sub-EMUs) can exceed device
  count even though every REAL ZONE still gets exactly one device. Fixed
  by selecting on zone count, not EMU count, for zone-partitioned
  projects — with the same real-data-presence check used elsewhere so a
  project that never opted into zone-partitioning is unaffected.
- Wired through camera trap co-location and the final schedule-entry
  builder, each needing their own real branch — reusing
  `continuous_proportional`'s would have incorrectly shown every sub-EMU
  as simultaneously active every week. Caught and fixed a real scoping
  bug in this wiring before it shipped (a variable computed in a sibling
  branch, silently unavailable in the new one).
- Re-verified: Soulforest (4 cycles, unchanged schedule structure) and
  GV completely unaffected — neither ever activates the new regime.

## v2.3 — TataMotors_Pimpri runs end-to-end on real data; representative sub-EMU selection for fragmented zones

First real run against live GEE covariate data surfaced and fixed several
genuine bugs, then a real design problem that needed a real decision:

- **Orchestrator dispatch bug**: `--force` silently routed TM's ingestion
  through the generic `kml_ingest.py` instead of the project's own
  correct custom preprocessing, since the custom logic had only ever been
  invoked manually. Fixed with a general `custom_ingestion.py` convention
  any project can use, not a TM-specific patch.
- **A genuine MultiPolygon candidate bug** in `candidate_grid.py`: clipping
  a cell against an exclusion or zone boundary could leave disconnected
  slivers whose summed area passed the coverage check even though neither
  piece alone was one coherent spot. Fixed to keep only the largest
  connected piece.
- **`gee/covariates_and_segmentation.js`'s own default export name didn't
  match what this pipeline's ingestion expects** (`gee_metrics_output`
  vs. the required `gee_covariates_output`) — a leftover from the old
  pipeline's naming. Fixed at the template level.
- **Diagnostics shape mismatches**, found one at a time as each real
  consumer crashed on the zone-partitioned `mmu_diagnostics` structure:
  fixed comprehensively (`converged`, `min_mapping_unit_used`,
  `search_trace` all now type-consistent with the non-zone-partitioned
  case) rather than patched reactively per crash, and the report builder
  now shows real per-zone tuning detail instead of a placeholder.
- **A real, latent bug in the scientific-defensibility check** (05_metrics_rollup):
  `all()` over an empty generator is vacuously True in Python — a
  covariate absent from every EMU's results incorrectly passed the
  "is this real data" filter, then crashed on an empty `max()`. Fixed
  with an explicit presence check.
- **Water margin corrected** from the source KML's own typo
  ("Water margion"), applied as an explicit, documented label correction
  — the raw layer name is never altered, only the display label.

**The real finding, and the real decision**: 137 EMUs from just 9 zones —
several real zones (Water margin, Deccan forest, Narmada valley, Trail
plots, Savana ecosystem) turned out to be genuinely fragmented into more
disconnected real sub-areas (up to 40) than one device rotating within a
season could ever visit even once. Confirmed directly this wasn't a
merge-logic bug — the fragmentation is real, verified against raw
geometry before any EMU logic touched it.

- **`select_representative_sub_emus`**: when a zone's real sub-area count
  exceeds season_length_weeks, rotates through a representative subset
  instead of all of them — using the same CRITIC-weighted typicality
  method already used for within-EMU position selection, one level up
  (each candidate is a whole sub-EMU, scored by its own median covariate
  profile, "representative of the zone" replacing "representative of the
  EMU"). Verified directly: the real schedule now uses 56 EMUs (down from
  137), with explicit, honest warnings naming exactly which real
  sub-areas were excluded and how many, per zone — partial coverage by
  deliberate, visible design, never silent.
- Full pipeline (ingestion through reference handoff) now runs cleanly
  end-to-end on real data for the first time. Re-verified Soulforest, GV,
  and Soova unaffected by every fix in this round.

## v2.4 — Major TM redesign: zone = EMU directly; two real bugs found and fixed

Started from a direct, firm redirection: SNIC-based sub-segmentation
within a real client-given zone was producing ecologically meaningless
micro-fragments (137 EMUs from 9 zones). The fix is a real simplification,
not a workaround:

- **`zone_is_emu` config option**: each real zone becomes exactly one EMU
  directly, no further spectral sub-clustering — the same "one EMU can
  span many real, physically disconnected parcels" model agroforestry
  already uses for districts, applied here to zones. New
  `_reconcile_zone_as_emu` bypasses the SNIC/MMU machinery entirely for
  projects that opt in. Verified: 9 EMUs from 9 real zones, 0 warnings,
  matching the client's own real zonation exactly.
- **A real, serious camera trap bug found on the very next check**: with
  every zone now permanently assigned its own audiomoth, "co-locate with
  whatever audiomoth is doing" no longer meant anything — every zone
  showed as active every week, so 1 real camera trap was scheduled into
  all 9 zones simultaneously. Fixed with a new, independent
  `build_camera_trap_zone_rotation` — one zone per week, round-robin,
  matching the real Tata Motors methodology's own documented precedent
  for its single physical camera trap.
- **A second real conflict surfaced immediately after fixing that**: 9
  real zones but an 8-week season meant one zone would never get camera
  coverage in any season, ever — confirmed directly (zero visits across
  21 scheduled weeks). Resolved per direct instruction: the SAME
  smallest-real-area zone is excluded from camera rotation consistently,
  every season (not whichever zone the rotation order happened to reach
  last) — audiomoth still covers it every week via its own device. Real
  area computed directly from candidate geometry, not assumed: turned out
  to be Wetland forest (0.82ha), not the example zone given in the
  request — reported honestly rather than silently substituted.
- **A real, separate finding surfaced while investigating that**: "Eco
  region" doesn't exist as an EMU at all — it has genuine eligible area
  (0.15ha, confirmed after exclusion clipping) but is split into two
  fragments too small for any 25m grid cell's centroid to land inside
  either one. A real limitation of grid resolution for a very small zone,
  not a bug, reported rather than silently left unexplained.
- **A real bug in achievable-cycles found from a direct number check**:
  "there would be 24 weeks, not 21" — `zone_scoped_continuous` was never
  added to the regime list exempt from the multi-day logistics-turnover
  reduction, despite a device under this regime never actually leaving
  its zone between weeks (same reasoning already applied to
  continuous_proportional). Fixed: full 24-week programme now achievable,
  confirmed directly (24 cycles, not 21).
- Re-verified Soulforest, GV, and Soova unaffected by every change in
  this round.

## v2.5 — Field map rebuild: real zone names, season-grouped weeks, real Phase 01 history

- **Real zone/anchor names throughout the map**, not internal EMU_ID
  strings — legend, week/EMU selector, and every popup. `_emu_display_name`
  strips the internal prefix and restores spaces; every project's map
  benefits, not just Tata Motors (Soulforest's "SEG01" etc. render exactly
  as before, since those already were the real names there).
- **Season-grouped week selector**: for a season-structured project, weeks
  render as one `<optgroup>` per season with per-season numbering (1-8),
  not one flat 24-entry list. Falls back to the original flat list for any
  project without `season_length_weeks` set — verified directly that
  Soulforest/GV/Soova are byte-identical in this respect.
- **Real Phase 01 field history wired into Week 1**: extended the
  historical crosswalk to include the two streams it was missing (water
  eDNA, soil eDNA — 18 real positions), so all 7 real streams from the
  original Field Recce map are represented. Week 1 now shows the real,
  already-collected deployment for every stream instead of the
  theoretical rotation, each popup naming which real zone it falls into;
  every other week renders the designed rotation as normal. Icons and
  colours match the original Field Recce map's own styling exactly.
- **Layer control and legend relabelled** — "Position pool (active)" →
  "Audiomoth", "Camera trap pool" → "Camera trap", matching how the
  streams are actually named elsewhere in this pipeline's own outputs.
- **A real escape-sequence bug caught and fixed properly, not just
  silenced**: a JS regex embedded in the Python template
  (`/\b\w/g`, used for legend label capitalisation) was under-escaped,
  producing a genuine `SyntaxWarning: invalid escape sequence '\w'` on
  compile. Traced to the exact byte level (not assumed from the warning
  text alone) before fixing, then re-verified the actual runtime string
  contains the correct single backslashes for valid JS, and that Node
  itself accepts the extracted script without error — not just that the
  warning went away.
- Full pipeline re-run end-to-end for Tata Motors Pimpri and regression-
  tested against Soulforest, GV, and Soova — all four confirmed producing
  syntactically valid JS (checked with Node, not assumed).

## v2.6 — Soulforest boundary/anchor updates, Island position bias, Project Soova rebuild

### Soulforest
- Boundary extended (704 candidate cells, up from 653, matching a real
  2.70ha extension confirmed directly against the client's new KML — the
  new boundary is a strict superset, nothing removed).
- Rock Guild added as a new ecological anchor (client-reported: real
  biodiversity value even though it might not stand out to spectral
  segmentation alone). New `camera_trap_excluded_emus` config lets an
  anchor be audiomoth-only — verified directly: week 4's real schedule
  shows audiomoth in Rock Guild but camera trap only in the other active
  EMU that week.
- New `position_pool_named_subarea_bias` capability (client-reported:
  "one of the two audiomoth devices... should be on the island"). Real,
  serious bug found and fixed in this feature within the same session:
  a first swap-based implementation correctly refused to violate the
  100m spacing guarantee (checked directly: the true medoid sits only
  25m from the best real island candidate — geometrically incompatible,
  not a bug), but was too narrow to find a *different* valid combination
  that could include the island. Redesigned to swap the greedy
  selection's seed itself to the island candidate when the true medoid
  conflicts with it — the medoid stays honestly labelled wherever it's
  reported (`is_medoid` is computed by direct comparison, never by seed
  position), it simply may not end up in the final pool if incompatible.
  Verified directly: Wetland's real capacity is actually 3 well-spaced
  positions (103.1m minimum, confirmed), not 2 — a real, positive
  side-effect of searching from a different valid starting point, not
  assumed or forced.
- `project_start_date` updated to match the client's real Sept 9
  schedule.
- Fresh GEE upload package regenerated (704 real candidates) — confirmed
  directly that 51 of the new cells have no covariate data yet, matching
  the client's own expectation that a fresh run is needed.

### Project Soova
- New, corrected KML placed — genuine interior rings (44 parcels, 443
  holes) confirmed preserved, not cleaned, per direct instruction that
  they are real, not digitisation noise.
- Config already matched the requested logistics (4 devices, 5 weeks,
  single district) from an earlier round — no changes needed there.
- Fresh GEE upload package generated. This session's pipeline run used
  stale covariate data (matched by parcel ID) purely to confirm the
  pipeline runs cleanly on the new geometry — real segmentation/EMU
  results are not final until the fresh GEE run completes.

Re-verified GV and Tata Motors Pimpri (shared code) completely
unaffected by every change in this round.

## v2.7 — Fresh GEE runs for Soulforest and Soova: real stability findings, and two serious bugs found and fixed

### Soulforest — real stability analysis (client concern: "credibility issue" if segments reshuffle unpredictably)
Direct, real spatial-overlap comparison (not name matching, which turned
out to be unreliable — see below) between the previous and fresh run:
- **Anchors essentially perfectly stable**: Fruit Forest 98.3% real area
  overlap, Wetland and Rock Guild 100%. Exactly as expected — anchors are
  geometry-defined by the client's own drawn boundary, not dependent on
  fresh satellite segmentation.
- **The large background segment (27ha) genuinely reorganised into 4
  pieces this round** — checked directly whether this was arbitrary
  noise or real signal: the 4 new pieces show real, substantial
  covariate differences (TreeCover_Pct spanning 4.6% to 66.6% across
  them), consistent with fresh imagery revealing genuine ecological
  sub-structure that wasn't detected before, not an arbitrary reshuffle.
  Reported honestly as a real, meaningful change rather than glossed
  over.
- **A separate, real finding**: candidate ID names (SFV-T####) shifted
  between runs — confirmed directly (SFV-T0572's real physical location,
  checked by coordinates, is now called SFV-T0571) — because the
  boundary extension changed the tessellation's sweep origin, not
  because any real error occurred. Worth knowing if any old ID reference
  is still in use anywhere, since it no longer points to the same spot.

### Project Soova — a serious, blocking parsing bug found and fixed
- **The new corrected KML's description-table markup is HTML-entity-
  escaped** (`&lt;td&gt;`) rather than wrapped in `<![CDATA[...]]>` (real
  `<td>` tags) — a valid difference in how different export tool
  versions serialise the same underlying Earth-Pro table, not a data
  quality issue. The existing parser only handled the CDATA form,
  silently returning zero attributes for every single one of 50 real
  parcels (confirmed directly: `attr_source: 'none'` for all of them,
  cascading into a spurious single "unknown_barrier_group" covering the
  whole project). Fixed by un-escaping HTML entities before parsing,
  verified directly against the real placemark: district, farmer name,
  block, and every other real attribute now parse correctly.
- **A second, real, unrelated bug found while re-verifying the fix**:
  Soova (and any agroforestry project with few real districts relative
  to device count) was silently getting `zone_scoped_continuous` — the
  regime built specifically for Tata Motors Pimpri's `zone_is_emu`
  redesign — instead of its own explicitly-configured
  `deployment_regime: sequential_cluster`. The regime-selection logic
  never actually checked the explicit config value at all. Fixed by
  gating `zone_scoped_continuous` on `zone_is_emu` being true, not just
  on having few real zones — re-verified Soova now correctly uses
  `sequential_cluster` (3 real cycles, matching FCF_GV's proven pattern)
  and Tata Motors Pimpri is completely unaffected (still correctly
  zone_scoped_continuous, 24-week rotation).

Re-verified GV and Soulforest unaffected by both fixes.

## v2.8 — Field map consistency fixes, camera trap interior bias, soil chemistry layer, K-selection parsimony rule

### Field map (shared code — affects every project)
- **Real bug fixed**: the "Phase 01 real deployment" layer entry was
  hardcoded into every project's layer control regardless of whether
  that project has real historical data — only Tata Motors does. Now
  conditional, verified directly that the string is present but inert
  (never added to the control) for Soulforest and Soova.
- **Real, confirmed bug fixed**: EMU-view toggle showed a project's FULL
  theoretical position pool with no schedule filter, while week-view
  correctly showed only what's actually deployed — confirmed directly
  this explains a client-reported example exactly (Wetland's "extra"
  3rd point, Fruit Forest's two "extra" points were all real pool
  members never actually funded a device). Both views now show the same
  real, scheduled positions; the full theoretical pool remains visible,
  honestly labelled, in the existing "unused pool" layer.
- Checked directly whether "points clustered on one side" (a separate
  client report) was a real distribution problem or a symptom of the
  above bug: the actual 5 deployed Fruit Forest positions span 13%-87%
  of the EMU's real extent in x and 15%-77% in y — a reasonable spread,
  strongly suggesting this was the same underlying bug, not a new one.

### Camera trap interior bias
- Confirmed real: camera trap draws from a smaller, pre-filtered
  candidate subset (excluding audiomoth's own picks), which structurally
  biases it toward the edge even with the same interior-bonus weight
  already wired in. Raised specifically for camera trap (0.5 -> 0.7) to
  compensate for the reduced candidate pool it draws from.

### Soulforest soil chemistry layer (new capability)
- New `build_soil_chemistry_points.py`: 4 real corners (minimum rotated
  bounding rectangle, snapped to the actual polygon boundary when a raw
  corner falls outside an irregular EMU's real shape) + 1 centre per
  EMU, Rock Guild excluded — 30 real points across 6 EMUs, confirmed.
  Wired into field_map_builder.py as a genuinely one-time layer (built
  once, never rebuilt on week/EMU toggles — matching the real sampling
  design of a single collection during the final deployment week).

### Site selection report (Soulforest/Soova template)
- Incorporated the client's own real edits to an earlier report:
  "Client" -> "Project", devices split into separate Terrestrial
  Acoustic / Camera Trap rows, cycles shown as a single accurate number
  (the "available vs needed" split this replaced was specifically for a
  case already fixed at the source), added the Chrome browser note.

### Project Soova
- **B1 checked against GV directly, not assumed a bug**: GV also only
  uses 4 of its 5 available weeks — confirmed this is real, established,
  consistent `sequential_cluster` behaviour (use as many weeks as panels
  need), not something specific or wrong about Soova.
- **B2, a real architectural finding**: Soova's single-district structure
  meant it received the ENTIRE undivided device/logistics k_max ceiling
  (16), while GV's ceiling gets split proportionally across 4 districts
  (~4 each) — a real, structural reason single-district projects
  fragment more than multi-district ones under the same total device
  budget. Checked the real silhouette scores rather than assume the
  highest-scoring k was right: nearly flat from k=7 through k=16
  (0.21-0.27) — the "best" k=14 was not meaningfully better than k=7.
- **New parsimony rule in `select_k_via_silhouette`** (shared clustering
  code): prefers the smallest k within 25% of the real score range of
  the best score, rather than the literal maximum — standard practice
  for exactly this situation (the same principle behind the "one
  standard error" rule in LASSO/ridge model selection). Soova: 10 -> 6
  EMUs, 3 -> 2 real cycles.
  **This is a shared-code change and also affected GV (7 -> 6 EMUs)** —
  reported prominently, not hidden, since GV was an already-reviewed,
  trusted result before this change.
- Verified directly: no EMU is split across multiple weeks in the new
  6-EMU/2-cycle structure (client requirement, confirmed satisfied).

All four projects (Soulforest, GV, Soova, Tata Motors Pimpri) re-run
end-to-end and their field map JS validated with Node directly, not
assumed from the Python build succeeding.

## v2.9 — Real scheduling bugs across Soova/GV/TM, soil sampling refinements

### Soulforest
- Soil chemistry corners pulled 5m inward toward centroid (reported
  directly: a sample taken exactly at a boundary corner risks edge-effect
  soil, not material representative of the EMU). Legend cleaned up —
  removed the "not shown on this map" note entirely, added soil_sample
  to the Streams legend with its real icon since it's now genuinely
  mapped.

### Shared field map fix
- Soova's legend showed "Camera trap" despite that project having
  audiomoth only — same bug class as the earlier Tata Motors leak: the
  layer entry was unconditional. Now gated on `camera_trap` actually
  being a configured stream.

### A real, serious scheduling bug found and fixed (Soova + GV)
- `position_assignments` was only ever computed when a panel had FEWER
  EMUs than devices — a panel with EXACTLY n_devices EMUs (one device
  each, no bonus needed) silently returned None entirely, and a panel
  with MORE EMUs than devices was never handled either. Confirmed
  directly: Soova's week 1 (4 EMUs, 4 devices) had a completely empty
  schedule for that week. Fixed to always compute real positions for
  every panel composition.
- **Panel-building always greedily minimised week count** regardless of
  real available weeks — confirmed via a direct client requirement ("has
  to be four-five weeks, I made it clear") that this needed to change.
  New `target_n_panels` builds EXACTLY the declared number of panels
  (not just a smaller per-panel cap, which can still undershoot when EMU
  count doesn't divide evenly — checked directly: 6 EMUs at cap=2 still
  gives only 3 panels, not a requested 4). Fixed with proper "distribute
  N EMUs across exactly K panels as evenly as possible" allocation.
- **A second, real bug found while testing this against GV**: with
  multiple barrier groups (districts), the panel target was applied
  independently and in full to EACH group rather than divided
  proportionally across them — confirmed directly this made GV's 4
  districts each try to hit the full project-wide target, producing 7
  total panels (one per EMU, zero consolidation) instead of the intended
  5. Fixed with real proportional allocation across groups by EMU count
  (the same pattern already used for K_max allocation in
  ecological_clustering.py), guaranteeing every non-empty group at least
  1 panel.
- Found and fixed a real config mismatch along the way: Soova's
  `project_duration_weeks` was still 5 from an earlier round; the client
  explicitly said 4. Fixed. GV confirmed correctly stays at 5.
- Verified directly: Soova now produces exactly 4 real cycles, GV exactly
  5, neither with any EMU split across multiple weeks.

### Project Soova — investigated, not a bug
- Checked Mayurbhanj_6's real geometry directly (client asked whether
  its 3 parcels being "too adjacent" was intentional): the 3 parcels are
  400-800m apart from each other, and the EMU's centroid is 9.7-27km
  from every other EMU. Genuinely well-separated — 1 device per parcel
  (3 total) is the same established design used throughout this
  pipeline, not an oversight.

### Tata Motors Pimpri — five real questions, checked individually
- **Large-zone sub-EMU rotation and small-zone "fixed position" concerns
  turned out to be explained by real, already-correct behaviour**:
  confirmed directly that Deccan forest rotates through 8 different real
  positions across its season with a clean reset, and Trail plots
  correctly cycles its 4 real positions twice per 8-week season (the
  already-agreed temporal-replication design). Wetland forest's
  single-position "no rotation" is a genuine geometric fact — its real
  area (0.82ha) is too small to fit two points 100m apart, not a bug to
  fix without relaxing the spacing guarantee.
- **A real, confirmed bug**: only 9 of 10 real devices were used every
  week — the 10th sat idle since "1 device per zone" naturally uses
  exactly 9 for 9 zones. Fixed: leftover devices now go to the zone(s)
  with the largest REAL pool capacity (not just declared area) as a
  genuine second position each week, offset from the primary position so
  it isn't a duplicate. Verified directly: all 10 devices now used every
  week, Deccan forest correctly receiving the bonus.
- EMU/week toggle consistency (already fixed via the shared A2 fix from
  the previous round) re-verified directly against TM's real data —
  Trail plots and Deccan forest both show exactly their real, complete
  rotation sets in EMU-view, matching week-view.

All four projects re-run end-to-end; every field map's JS validated
directly with Node.

## v2.10 — Real, root-cause fix for the "everything overlaid" inconsistency; soil sampling refinements

### The core bug, found and fixed properly this time
Direct, exact numbers from the client proved this wasn't fixed by the
previous round: "week 1 shows only 3... everything overlaid shows 17...
EMU by EMU shows 13." Traced to TWO distinct, real bugs stacked together:

1. **Device allocation didn't account for real pool-size limits**:
   `allocate_devices_largest_remainder` distributes by EMU AREA, which
   can give an EMU more devices than its own real, spacing-verified pool
   contains. The shortfall was silently dropped instead of going to
   another EMU in the SAME panel with real spare capacity. Confirmed
   directly: Mayurbhanj_1 (pool of 2) got allocated 3 by area and was
   capped to 2; Mayurbhanj_3 (pool of 3) only got 1, even though it had
   two more real, valid positions sitting unused. Fixed with a real
   iterative redistribution loop — the freed device now goes to
   whichever EMU in the panel has the most genuine spare pool capacity,
   repeated until every device is used or every EMU's pool is genuinely
   exhausted.
2. **"Everything overlaid" mode never applied the real-schedule filter
   at all** — EMU-view was fixed in the previous round, but "all" mode
   fell through to the full theoretical pool regardless, which is
   exactly why the overlaid total didn't match either week-view or
   EMU-view combined. Fixed: all three view modes now apply the same
   `everScheduledByEmu` filter, verified directly for Soova (14/14/14),
   GV (19/19/19), and Tata Motors Pimpri (56/56/56) — checked
   programmatically against the actual embedded map data, not assumed
   from the code change alone.

Some EMUs (Ganjam_1, Mayurbhanj_5, Mayurbhanj_2 — each capped at 3 real
positions, alone in their panel with nothing to redistribute to) mean
the real achievable total is genuinely below the naive n_devices x
n_weeks maximum (19 not 20 for GV, 14 not 16 for Soova) — reported
honestly as a real pool-size constraint, not glossed over.

### Soulforest
- Soil chemistry corner inset raised from 5m to 15m — confirmed directly
  the original 5m wasn't visually distinguishable from the raw corner at
  normal map zoom.
- New report section (7b, only rendered when a project has a real
  soil chemistry design): design rationale, corner-inset methodology,
  and real coverage numbers — client-reported: "site selection report
  should talk about sampling design including for soil samples."

All four projects re-run end-to-end; every field map's JS validated
directly with Node; three-way view consistency (all/week/EMU) verified
programmatically for every project, not just Soova.

## v2.11 — Small-EMU spacing relaxation (TM), real-candidate soil sampling (Soulforest), GV finding

### Tata Motors — small-EMU spacing relaxation, validated before implementing
Client proposal: relax min_device_spacing_m to 50m specifically for
EMUs too small to get real position variety at the standard 100m floor.
Tested empirically FIRST, not assumed: Wetland forest went from 1-2 real
positions to 2-3 at 50m; Trail plots-scale EMUs showed similarly real
gains. Implemented as a new opt-in `allow_small_emu_spacing_relaxation`
config flag (default False — every other project unaffected):
- Threshold for triggering relaxation is `season_length_weeks` itself
  (an EMU with real room for a full season's rotation never needs
  this), not an arbitrary small number — corrected mid-implementation
  after finding a first attempt at "<3" missed Trail plots entirely,
  even though its 4-position pool still meant repeating within a season.
- Real trade-off, never hidden: relaxation is only attempted when
  standard spacing genuinely falls short, always reported by name in
  the EMU's own report with the exact relaxed value used, and never
  applied anywhere else in the project.
- Verified directly: Wetland forest 1->2, Trail plots 4->7, Wildlife
  also gained real capacity — all three explicitly listed in the
  warning. Deccan forest, Narmada valley, and other already-adequate
  zones completely unaffected (checked directly: relaxed_spacing_used_m
  is None for all of them).

### Soulforest — soil sampling corners rebuilt on real candidate cells
Real redesign, not another distance-tuning pass: a synthetic geometric
corner point (even inset) could still land at or need a large snap
correction for an irregular EMU shape — confirmed directly, some
corners needed 100m+ snaps in the previous version, which isn't "a few
metres inside" by any reasonable reading. Rebuilt from scratch: each
corner now uses the REAL, already-tessellated 25m candidate cell nearest
that geometric corner, filtered to genuine >=25m clearance from the
EMU's real boundary (a true geometric distance, so diagonal proximity
to an edge is correctly excluded too, not just an axis-aligned margin).
No synthetic coordinate is ever invented. Verified directly: all 4
selected corners for Fruit Forest sit at 35-40m real clearance. Report
text updated to describe the real, current methodology, not the
replaced one.

### GV — a real, honest finding, not silently fixed
Checked directly whether Ganjam_1's real capacity of 3 (vs. its target
of 4) was a bug: it is not. The extent-aware spacing formula — built
specifically for a "vast EMU" like this (158km real bounding-box
diagonal) — computed a genuine ~39.6km effective spacing requirement for
a 4th position; the client's named candidate parcels sit only 24-27km
from the medoid, correctly failing that threshold. Real tension found
while checking: 268 of Ganjam_1's 618 real candidates sit within 30km of
the medoid — a genuine, rich local cluster the current formula's
whole-EMU-extent basis excludes from ever contributing a 4th point.
This is a real methodology trade-off (the formula was built to prevent
over-concentration in one region of a vast, scattered EMU), not
something to change unilaterally without confirming which behaviour is
actually wanted — reported for a decision, not silently altered.

## v2.12 — GV's extent-aware spacing formula fixed with a real, tested cap

Continued from the flagged finding: Ganjam_1's real capacity (3) fell
short of its target (4) because the extent-aware spacing formula scales
with an EMU's FULL bounding-box diagonal, and Ganjam_1's genuinely vast
158.6km diagonal pushed the requirement to ~39.6km — excluding a real,
rich local cluster (268 of 618 candidates within 30km of the medoid)
from ever contributing a 4th position.

- **Capped the extent-based scaling at 25km** — a defensible ceiling for
  what "a genuinely different region" means at landscape-monitoring
  scale, past which forcing more separation excludes legitimate
  coverage rather than adding real spread. Chosen and verified against
  real data across every GV and Soova EMU (14.5km to 158.6km diagonals)
  before applying — every EMU already under 25km-equivalent spacing is
  completely unaffected, confirmed directly (Soova's pool sizes
  unchanged: 3,2,3,3,3,3).
- **Real result, better than just fixing the one flagged case**: all 6
  GV EMUs now reach their full pool_target of 4 (up from Ganjam_1's 3),
  and the real schedule now uses all 4 devices in every one of the 5
  weeks — 20 total real positions, the genuine theoretical maximum.
  Verified directly: the new 4th Ganjam_1 position (735356793) sits a
  real, meaningful 28.1km from the medoid — inside the rich local
  cluster the client pointed at — while all 4 of Ganjam_1's positions
  remain at least 28.1km from each other.
- Three-way view consistency re-verified for GV: all/week/EMU all show
  exactly 20, programmatically confirmed against the real embedded map
  data.

All four projects re-run end-to-end; every field map's JS validated
directly with Node.

## v2.13 — Soil sampling clustering fixed with real minimum separation; real deployment dates set

### Soulforest soil sampling — real bug found and fixed properly
Client-reported, confirmed with real numbers: the candidate-based corner
selection (previous round) worked for large EMUs but clustered badly for
small ones — Wetland's 4 "corners" included a pair only 25m apart.
Root cause: each corner picked its nearest real interior candidate
INDEPENDENTLY, never checking the 4 results were separated from EACH
OTHER — for a small EMU, all 4 corners' nearest real candidates can
legitimately be nearly the same spot.

Fixed with a real greedy algorithm (`_select_separated_corners`):
corners are still real, already-tessellated candidate cells with genuine
25m boundary clearance, but now assigned in order of whichever corner
has the closest currently-available match, each pick required to clear
a genuine 40m minimum separation from every point already chosen for
that EMU. Where an EMU's real geometry can't support 4 separated
corners at that minimum, this reports fewer points honestly rather than
force clustering — the same "real capacity, not forced" principle used
everywhere else in this pipeline.

Verified directly: Wetland, SEG03, and SEG04 (all small EMUs) now
correctly show 3 well-separated points (50-100m apart, confirmed) rather
than 4 clustered ones. Report's own soil chemistry section now
explicitly names every EMU affected and why, rather than silently
reporting a lower total.

### Real deployment dates set for all four projects
- Soulforest: 2026-09-09 (unchanged, already correct)
- Tata Motors Pimpri: 2026-09-12 — real field context noted directly in
  config: this is Week 2 of Season 1, since Week 1 was already completed
  under the old plan before this redesign (13-27 Aug 2026)
- Project Soova: 2026-09-14 (tentative)
- FCF_GV: 2026-10-19 (tentative)

Verified directly in each project's real exported schedule.csv that the
calendar dates land correctly (including the "which regime" check —
project_start_date now confirmed working for continuous, sequential,
and zone-scoped regimes alike, not just Soulforest's stratified regime
it was originally built for).

All four projects re-run end-to-end; every field map's JS validated
directly with Node.

## v2.14 — Full comment-style cleanup across the pipeline

Every source file in `pipeline/` reviewed and rewritten to remove
journal-style "Aug 2026, reported directly / found directly / confirmed
directly" narration, replacing it with clean, present-tense documentation
of current behaviour and its real rationale — the substance of every real
bug, design decision, and trade-off is preserved; only the "here's the
story of how I found this" framing is removed. Every file re-run and
validated after its own edit, not just checked for syntax:

`clustering_utils.py`, `ecological_clustering.py`, `rollup.py`,
`report_builder.py`, `covariate_ingest.py`, `config_schema.py`,
`segmentation_reconciliation.py`, `position_scoring.py`,
`field_map_builder.py`, `panel_scheduler.py`, `candidate_grid.py`,
`kml_ingest.py`, `schedule_export.py`, `export_tiles.py`, `gee_export.py`,
`kml_utils.py`, `run_pipeline.py`.

Two real, substantive issues found and fixed while doing this, not just
style changes:
- `field_map_builder.py`'s module docstring had a stale "HONEST SCOPE
  NOTE" claiming the map only shows EMU centroids, not individual device
  positions — no longer true (it's shown real, individual candidate
  positions for a long time). Corrected to describe current behaviour.
- A mid-edit duplication artifact in `field_map_builder.py`'s
  showHistorical logic and a grammatical break in `kml_ingest.py`'s
  district-correction comment, both caught and fixed before they could
  ship, by reading the actual file content after editing rather than
  assuming the edit landed cleanly.

Full regression sweep after every file: all four projects re-run
end-to-end, every field map's JS validated with Node, and the specific
numbers from every fix in this session re-verified unchanged (GV 20/20/20,
Soova 14/14/14, TM week 1 using all 10 devices, Soulforest's 30 soil
points with zero corner-separation shortfalls) — confirming the cleanup
changed no behaviour, only documentation.

## v2.15 — Soil sampling: manual point specification, replacing algorithms

Every automated corner-selection approach tried (bounding-rectangle
corners, nearest-candidate-per-corner, farthest-point sampling) solved
one real problem while exposing another on real visual inspection of the
rendered map. Client provided real, manually chosen candidate names for
every corner and centre point across all 6 EMUs directly — rebuilt to
use these exactly, verified to exist and belong to their stated EMU
before use, no algorithm involved.

- All 30 given names checked directly against the real candidate set
  before use; all confirmed valid and correctly assigned.
- One real issue found and flagged rather than silently handled: SEG02's
  given centre candidate (SFV-T0223) was identical to one of its own
  given corners — using both as given would collapse two labelled points
  onto the same coordinate. Substituted the EMU's real geometric centroid
  for SEG02's centre instead, and reported this substitution explicitly
  in both the tool's own output and the client-facing report, not fixed
  silently.
- A real reporting bug caught while implementing: `substitutions` was
  computed by the generator but never actually written into the geojson
  file itself, only returned from the function call — meaning the
  report's own substitution note would always have shown empty. Fixed by
  writing it as a real top-level field in the geojson output.
- Report section rewritten to describe the manual design accurately (no
  longer claims an algorithm picked the points), including the
  substitution note. METHODOLOGY.md and PIPELINE_METHODOLOGY_REFERENCES.md
  updated to match — the algorithmic sections are now history, not current
  behaviour.

Verified: 31 real points across 6 EMUs (Fruit Forest, Wetland, SEG01-04),
each point traceable to either a manually-given real candidate name or
the one explicitly-flagged geometric-centroid substitution. All four
projects re-run end-to-end; every field map's JS validated with Node.

## v2.16 — Real bug found and fixed: low-confidence covariates were being silently dropped, not flagged

Client question, checked directly rather than assumed: "we had so many covariates
and got a real GEE run output... did we need another run, or is something wrong?"
Checked the raw GEE covariate CSV directly — every parcel-intrinsic covariate
(NDVI, TreeCover, BuiltUp, Elevation, Slope, TRI, gHM, DistWater, LST, NightLights)
has real, genuine values for every candidate cell. The GEE run was correct; no
re-run was needed.

The real bug was downstream, in `05_metrics_rollup/rollup.py`. Its own module
docstring documents the intended design: a value from a tile below the small-tile
confidence floor (0.25 ha) should be "shown but flagged low-confidence, never
silently dropped." The actual code did the opposite — a sub-floor value was
excluded from the covariate's value list entirely (`continue`, never appended),
so whenever EVERY tile in an EMU sits below the floor (confirmed: exactly Tata
Motors' situation, its entire 25m grid is uniformly 0.0625ha, under the 0.25ha
floor), the whole covariate silently vanished from that EMU's row and from
`stratum_profile.csv` — contradicting the code's own stated intent.

Fixed: `rollup_emu()` now keeps low-confidence values in their own real,
separately-computed distribution and surfaces them explicitly
(`low_confidence_stats`, `n_valid: 0` on the parent entry to distinguish this case
from a genuine mix of confident/unconfident tiles) rather than omitting the
covariate. `stratum_profile.csv`'s writer now shows the real low-confidence value
with a clear inline flag (e.g. "0.4424 (low-confidence, n=693)") instead of a
blank cell. The project-level aggregation loop (`project_covariates`) was fixed
to explicitly exclude low-confidence-only EMUs from cross-EMU statistics (would
otherwise KeyError on the now-different low-confidence entry shape) — the
project-level summary correctly stays conservative and doesn't claim a confident
project-wide number from universally-low-confidence per-tile data, while the
per-EMU detail is now honestly visible for anyone who wants to see it.

Verified directly: re-ran Tata Motors' rollup, confirmed real values now appear
with the low-confidence flag for every zone (e.g. Deccan forest NDVI_raw =
0.4424, n=693). Re-ran the other three projects (Soulforest, GV, Soova) to
confirm no regression — their tiles are large enough to clear the floor, and
their values correctly remain unflagged (e.g. Soulforest Fruit Forest NDVI_raw =
0.2909, no flag).

A separate, real data-quality finding surfaced while pulling real numbers for
the Tata Motors methodology document: `TreeCover_Pct` reports a flat 100% across
every zone, including Grass land and Water margin — almost certainly the same
land-cover classifier limitation on managed/transitional landscapes already
documented elsewhere in this pipeline, not a genuine 100% canopy finding.
Flagged honestly in the methodology document rather than presented uncritically;
NDVI (0.42-0.71, real sensible variation) used instead where a covariate value
was needed for that document's stratification table.

TataMotors_Pimpri_Sampling_Methodology_v1_0.docx updated to match: §4.2, §5, and
§11.1 now correctly state covariates are available with a low-confidence flag,
not unavailable.

## Open (as of this writing)
- **Soova's 22km-spread EMU has not been re-run against the new
  deployment-eligibility outlier exclusion (v1.0)** — the mechanism
  applies project-wide and is confirmed working on GV, but Soova itself is
  on hold pending an updated client KML, by explicit instruction.
- **Aquatic covariates** are ingested per-project (real per-project
  waterbody data confirmed, not the earlier hardcoded-asset bug) but not
  yet rolled into `05_metrics_rollup` or shown on the field map.
- **Tata Motors** — CORRECTED, this line was stale: ported into this
  pipeline and working (zone_is_emu, zone_scoped_continuous regime) for
  many releases now; see the real history throughout this changelog.
  Real remaining Tata Motors item instead: 137 orphaned, stale
  `SEG01.geojson`...`SEG137.geojson` tile files sit alongside the real 9
  current `EMU_*.geojson` tiles in `outputs/07_reference_handoff/tiles/`
  — harmless (nothing reads them; `tile_manifest.json` only lists the 9
  real ones) but worth a real cleanup pass.
- **`darukaa_reference` handoff** — CORRECTED, this line was stale: not
  only started but real, tested, and connected — `07_reference_handoff`
  now feeds `darukaa_reference`'s own `run_project_from_manifest.py`
  directly (`--project <name>`, both pipelines in one repository), for
  all four real projects (Tata Motors, Soulforest, GV, Soova), plus a
  real, separate aquatic-tile extraction for Tata Motors' own water
  bodies (`extract_aquatic_tiles.py`). See `darukaa_reference`'s own
  CHANGELOG.md for the full, real history of this connection.
