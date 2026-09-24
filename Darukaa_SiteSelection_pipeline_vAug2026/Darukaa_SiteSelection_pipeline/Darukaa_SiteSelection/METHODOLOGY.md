# Methodology — Darukaa Site Selection Pipeline

This document states what each stage does, why, and what it can and cannot
support as a conclusion — the same purpose the Pimpri methodology doc
serves for that specific project, but generalized across archetypes. Every
citable decision is in `docs/PIPELINE_METHODOLOGY_REFERENCES.md`; this
document explains the mechanism, that one carries the evidence.

## 1. Design principles

Adapted from the Pimpri methodology's own six design principles (P1–P6),
which apply pipeline-wide, not just to that one project:

- **Segment/cluster before logistics.** The ecological unit (EMU) is
  decided on ecological grounds first — image segmentation for contiguous
  sites, ecological clustering for scattered ones — then fitted to
  devices, days, and access. Where logistics can't cover a unit, that unit
  is merged into its nearest neighbor rather than quietly under-sampled
  (see §3, minimum-mapping-unit auto-tune).
- **Spatial contiguity is a structural guarantee for segmentation-derived
  EMUs, not a hoped-for outcome.** Every segmentation-derived EMU is
  verified, by a hard runtime assertion, to be a single connected polygon
  before the pipeline will report it. This was not always true — see
  CHANGELOG for the real bug this assertion caught twice.
- **Effort determines claim.** Each stream's inference ceiling should be
  written down before data collection, not implied by the deliverable.
  (This principle is stated here for completeness; the pipeline does not
  yet enforce it programmatically — a documentation gap, not a code one.)

## 2. Stage-by-stage

### 01_ingestion
Parses client KML(s) — handling at least two real, different schema
variants seen in practice (legacy Earth-Pro description-table HTML, and
standard `ExtendedData`/`SchemaData`) — into a normalized candidate set.
Classifies every placemark into exactly one of: AOI boundary, ecological
anchor (a client-identified real ecological feature, adopted directly as
its own EMU), hard exclusion (buildings, roads, real water — removed from
candidate space entirely), soft exclusion (a zone that's only partially
built, e.g. a mixed admin/green area — tessellated normally, resolved
pixel-by-pixel once real covariate data exists), or a normal candidate.

For contiguous archetypes, also generates a dense tessellated grid (default
25m cells) across the unmasked matrix — needed because a client KML for
this archetype typically gives only a few large hand-drawn zones, and
per-cell `SEGMENT_ID` resolution needs many more, smaller candidates than
that to work with.

**District/admin-boundary data-quality corrections** (`district_corrections`
in config, Aug 2026): source KML attribute data can itself be wrong or
missing — confirmed on real GV data (13 parcels with no district at all,
several genuinely mistagged). Corrections are never applied on assumption
or on an unverified third-party analysis — each one is independently
checked via k-nearest-neighbour geographic voting against every other
confidently-tagged parcel (not a bounding-box heuristic, which was shown
directly to be unreliable here since districts' real coordinate ranges
overlap). This caught a real case where an external analysis had the
right parcels but the wrong target district for 2 of them. Applied as an
explicit, auditable table (parcel name → corrected value), each entry
with its own evidence in a comment — never a silent patch to the source
KML. This matters beyond the district label alone: `hard_barrier_attribute`
(district, for agroforestry) drives EMU partitioning in 03 and panel
purity in 04, so a wrong or missing district doesn't just mislabel one
parcel, it can produce a whole spurious `unknown_barrier_group` EMU and
scheduling group.

### 02_covariates
Ingests the manually-run GEE covariate CSV. ~15 covariates per candidate
(NDVI, tree cover, terrain, human modification, landscape-context
connectivity/fragmentation at two scales, land-surface temperature, night
lights, built-up %) — see the references doc for dataset citations. Hard
filters (built-up %, permanent water) are applied here, and the stage
refuses to proceed if the GEE CSV doesn't exist or is majority-unmatched
against the candidate set, rather than continuing on an imputed
placeholder.

**Tree cover** (Aug 2026, after two rounds of real, confirmed failures) is
computed directly from an NDVI threshold on the current Sentinel-2
composite, not from a categorical land-cover classification — two
different classifier-based approaches (Hansen loss-adjustment, then Esri's
"Trees" class) were each tried and confirmed broken on real Soulforest
data, the second one traced to a genuine classifier failure to recognize
that site's vegetation at all (cross-confirmed against NatCoverPct and
NDVI on the same candidates). The classifier-derived versions are kept as
secondary reference bands, not the primary metric.

**A defensive check** in `05_metrics_rollup` flags any covariate showing
identical values across every EMU — zero variance across a whole site is
almost never real ecological signal.

**BuiltUp_Pct** gets an NDVI override: a candidate above the built-up
threshold is kept anyway if its NDVI shows real vegetation, since a
genuine impervious surface doesn't produce meaningful photosynthetic
reflectance — found necessary after the same land-cover classifier
misclassified a young plantation's bare-soil-between-rows pattern as
built area.

### 03_emu_delineation
Two methods, routed by archetype:

**Ecological clustering** (agroforestry) — Gower distance (handles mixed
numeric/categorical covariates) with a **spatial k-nearest-neighbor
connectivity constraint** on top, so clustering can never group two
candidates that aren't geographically reachable through a chain of nearby
candidates. EMU membership from this clustering is taken as final —
REVISED (Aug 2026, after two increasingly complex EMU-splitting attempts
were each found broken on the next real run and reverted rather than
patched further): a member parcel that ends up geographically far from
the rest of its EMU is NOT split into its own EMU. Real ecological
membership stays intact (a scattered EMU still gets real, complete ex-situ
metrics), and the outlier is instead excluded from **device-position
eligibility** in 03b — see that stage below. This is both simpler and more
correct than trying to keep every EMU spatially compact: an EMU's
scientific identity and its field-logistics feasibility are genuinely
different concerns, and conflating them (as the removed compactness-
splitting approach did) created a real, confirmed-broken interaction with
the device-coverage guarantee's own budget accounting.

**Segmentation reconciliation** (conservation/industrial) — GEE SNIC
segmentation over the dense grid, reconciled with client-declared
ecological anchors, then **minimum-mapping-unit (MMU) auto-tuning**:
segments below a candidate-count threshold merge into their nearest truly
*adjacent* neighbor — meaning a genuine shared edge (positive-length
boundary intersection), not just "nearest by any distance" or even mere
proximity. Three real bugs found in this single mechanism, each caught by
the same hard contiguity assertion firing on real data (see CHANGELOG):
wrong distance metric, wrong units (degrees vs. metres), and — found most
recently — two cells touching only at a single diagonal corner having
real distance 0.0 but not a genuine edge connection `unary_union` will
dissolve into one solid polygon. Every resulting EMU is verified to be a
single connected polygon.

**`zone_is_emu`** (opt-in config flag, currently Tata Motors Pimpri only)
— skips segmentation-driven sub-clustering entirely: each real value of
the project's `hard_barrier_attribute` (a client-declared ecological
zone, not a spectral cluster) becomes exactly one EMU directly, dissolving
all its member tiles regardless of raw SNIC segment ID or geometric
adjacency — the same "one EMU can span many real, physically disconnected
parcels" model agroforestry already uses for districts, applied here to a
zone instead. Added directly in response to segmentation-driven
sub-division producing small, ecologically meaningless fragments within a
real, named zone (137 EMUs from 9 real zones, before this). A real zone
that turns out to be internally fragmented into more physically
disconnected pieces than a season can each visit at least once (confirmed
directly for several zones — one had 40 real disconnected clusters) uses
`select_representative_sub_emus` to rotate through a representative
subset instead of all of them, chosen by the same CRITIC-weighted
typicality method used for within-EMU position selection, one level up —
partial coverage by deliberate, visible design, always named explicitly
in the deployment warnings, never silent.

**Orphan-segment-to-anchor merging** (Aug 2026, added after a direct,
image-grounded observation that a real single-tile segment sat exactly at
a transition point between two anchors, touching both): MMU merging above
only ever considers merging a small segment into another *segment* —
anchors, resolved earlier via centroid-containment, were never revisited
as a possible merge target for a leftover tiny segment touching one from
outside. Any segment still below `emu_min_tiles` after MMU merging that
genuinely touches an anchor is now folded into whichever anchor it shares
the longest real boundary with (a meaningful tie-break, confirmed
necessary directly — the real case was a near-tie between two anchors).
The anchor's displayed boundary is dissolved to include the merged tile so
its polygon matches its true membership.

**Device-coverage guarantee**, both paths: an EMU that can't be covered by
available devices within the project timeline is a **hard error**, not a
soft warning — if this fires, it means the EMU-count target and the
deployment scheduler's own capacity calculation disagreed, which is a bug
to fix at the source, never a "some EMUs uncovered" finding to report to a
client.

### 03b_position_scoring
Ranks every candidate WITHIN each EMU by an objective **CRITIC-weighted
typicality score** (Diakoulaki, Mavrotas & Papayannakis 1995) — weights
computed from the actual covariate data (variance × independence from
other covariates), not hand-assigned. The highest-typicality candidate is
the EMU's medoid.

**Position selection and device capacity** (Aug 2026, redesigned after
confirming directly against the real Tata Motors methodology document
that this pipeline's own approach didn't verify what it needed to):
`select_spacing_compliant_positions` greedily adds the next-highest-
typicality candidate to an EMU's position pool only if it is at least
`min_device_spacing_m` (true Euclidean distance — direction-agnostic by
construction, handling diagonal neighbours correctly with no lattice
correction needed) from every already-selected position, starting from
the medoid. This replaces an earlier KMeans spatial-binning approach that
spread picks across regions but never verified any actual pairwise
distance — confirmed directly to sometimes place two positions in the
same EMU right next to each other. The size of the resulting pool IS the
EMU's real, verified device capacity — not a separate area-based estimate
that can disagree with what the real candidate geometry actually supports
(confirmed on real data in both directions: a formula-based capacity of 1
for one EMU turned out to verify at 3; another's estimate of 1 verified at
2 after checking its real, geometrically tight bounding box).

**Extent-aware spacing** (Aug 2026, reported directly: "for such a vast
EMU we are not actually representing the whole EMU if points are simply
getting chosen from concentrated clusters"): `min_device_spacing_m`
(100m, derived from acoustic detection radius) is correct for a compact
conservation site but was confirmed meaningless for a scattered
agroforestry EMU — real GV EMUs span 14 to 152km, at which scale any real
candidate placement trivially satisfies 100m spacing without needing to
spread across more than a tiny fraction of the EMU. The EFFECTIVE spacing
requirement used by `select_spacing_compliant_positions` now scales with
each EMU's own bounding-box diagonal and target pool size, with the real
acoustic-derived value as a hard floor — a compact EMU is completely
unaffected (the extent-based term stays below the floor), a vast one now
gets genuinely representative geographic spread. Confirmed on real data:
one EMU's positions went from a concentrated cluster to spanning 62-131km
apart, actually representing its real extent.

**Extent-aware spacing cap at 25km** (found directly, GV Ganjam_1): the
uncapped formula scales with an EMU's FULL bounding-box diagonal, which a
genuinely vast, non-uniformly-distributed EMU can push to an extreme
(158.6km diagonal produced a ~39.6km required spacing) even though the
real candidate distribution isn't uniform — 268 of that EMU's 618 real
candidates sat within 30km of the medoid, a genuine, rich local cluster
the uncapped requirement excluded entirely from ever contributing another
position. Capped at 25km — a defensible ceiling for what "a genuinely
different region" means at landscape-monitoring scale, past which forcing
more separation excludes legitimate additional coverage rather than
adding real spread. Verified directly against every real EMU in both GV
and Soova (14.5km to 158.6km diagonals) before applying — every EMU
already under the cap is completely unaffected. Real result: every one of
GV's 6 EMUs now reaches its full target pool size, and the real schedule
uses every available device in every week.

**Small-EMU spacing relaxation** (`allow_small_emu_spacing_relaxation`,
opt-in, currently Tata Motors Pimpri only): a real EMU whose capacity at
the standard acoustic-derived spacing floor falls short of a full
season's rotation (fewer real positions than `season_length_weeks`,
meaning some would repeat within a single season) gets a second attempt
at a relaxed 50m floor — tested empirically before implementing (a real
EMU's capacity went from 1-2 positions to 2-3 at the relaxed floor). A
genuine trade-off (some acoustic overlap risk between devices), only
attempted when the standard floor genuinely falls short, and always
reported by name with the exact relaxed value used — never applied
project-wide or silently.

**Interior/edge balance** (Aug 2026, reported directly: "best selected
points are always at the edge... there should be a proper mix-match"):
confirmed empirically that pure greedy max-min-distance selection has a
real mathematical tendency to push points toward a bounded region's
boundary — there's structurally more room to be far from already-picked
points near an edge than deep in the interior. Fixed by blending each
candidate's real distance to the EMU's own dissolved boundary into the
SELECTION ORDER (not the spacing constraint itself, which stays purely
geometric) — the greedy search now weighs "is this reasonably interior"
against "is this a good spot" for every pick after the medoid, which stays
chosen on pure typicality (it's meant to be the single most representative
point, not interior-biased). Confirmed a real, meaningful improvement on
most EMUs; one small EMU (bounding box 100m x 254m, barely wider than the
100m spacing requirement itself) still shows edge-heavy positions after
the fix — confirmed this is a genuine geometric constraint (the medoid
itself sits reasonably centrally, 37.5m from the boundary, but any
*additional* position forced >=100m away from it in a polygon this narrow
has nowhere non-edge-adjacent left to go — verified directly, not assumed
after the medoid check alone), not an algorithm failure.

**Applies to camera trap too** — found and fixed a real bug in the same
round the audiomoth fix shipped: camera trap's own position selection
(in `04_deployment_planning`, a separate call site) never passed the
boundary-distance data at all, so it kept running the pre-fix, pure-
typicality algorithm regardless of the correction already live for the
main pool. `interior_bonus_weight` (0.5, raised from an initial 0.3 after
testing directly against real data and confirming further, if bounded,
improvement) now applies identically to both.

**Deployment-eligibility outlier exclusion** (Aug 2026 — see 03's note on
why this lives here rather than in EMU delineation): before ranking, each
EMU's members are checked for severe spatial outliers. REDESIGNED after a
real bug found the original method's core assumption wrong: a modified
z-score (median + MAD distance-to-centre) assumes a single dominant
cluster with a small minority of strays — confirmed directly this breaks
badly for a genuinely bimodal or multi-cluster EMU (a real GV EMU, made of
dozens of real village-level sub-communities, had 71% of one entire real
sub-population wrongly flagged). Now uses DBSCAN to find real spatial
sub-clusters first (a small, fixed `min_samples=3` so density variation
across a real but non-uniformly-packed area doesn't itself cause
under-clustering), then flags a candidate as a genuine outlier only if it
belongs to a cluster below a small ABSOLUTE size floor — not a percentage
of the EMU's total membership, which was tried first and found to
wrongly flag every real small community in a large EMU. `eps` is derived
from the EMU's own typical nearest-neighbour spacing, so this works
correctly at both a compact conservation site's ~100m scale and a
scattered agroforestry EMU's ~100km scale without separate tuning. A
flagged outlier is never the medoid and never enters the position pool,
but keeps its EMU membership everywhere else — real ex-situ metrics still
include it.

**Orphan-cluster merging for agroforestry** (Aug 2026, reported directly:
a real 1-parcel EMU sitting near other, larger EMUs): agroforestry has no
ecological-anchor concept to merge an orphan into, unlike the equivalent
contiguous-archetype fix — but the same principle applies. Any cluster
below `emu_min_tiles` after K-selection is folded into whichever other
cluster's nearest member is geometrically closest, using real proximity
rather than requiring literal touching (farm parcels within a partition
are rarely if ever adjacent the way tessellated grid cells are).

### 04_deployment_planning
Builds the device/cycle schedule. Four regimes, selected by
`sampling_design` in config (explicit choice takes priority) or, absent
that, by whether the project opted into `zone_is_emu` with a real,
non-null `hard_barrier_attribute` (see 03_emu_delineation), then by
whether `n_emus <= n_devices`:

- **`sequential_cluster`** — for scattered, more-EMUs-than-devices projects
  (agroforestry). Groups EMUs into geographic panels, **never mixing EMUs
  from different districts/barrier groups in one panel**, each panel
  visited in one cycle. Panel size targets the project's real, declared
  `project_duration_weeks` via `target_n_panels` (distributing EMUs as
  evenly as possible across exactly that many panels, allocated
  proportionally across barrier groups by real EMU count) rather than
  greedily minimising cycle count — a real fix, found directly: greedy
  packing alone can leave real available weeks completely unused, and
  splitting a fixed target evenly across every barrier group (not
  independently in full to each one) was needed too, or a project with
  several small districts would massively over-fragment. Capped at what
  the project timeline can actually achieve (policy: devices are never
  added; duration may extend by a small, explicitly-flagged amount as a
  last resort; anything that still doesn't fit is a hard error, per the
  coverage guarantee above). A panel whose real device allocation (by
  EMU area) would exceed any one EMU's own real, spacing-verified pool
  capacity redistributes the shortfall to another EMU in the same panel
  with genuine spare capacity, iteratively, rather than silently losing
  devices — confirmed directly this was the root cause of a panel
  showing fewer real deployments than its device budget allowed.
- **`continuous_multi_week`** (the config value `sampling_design` uses;
  internally still called `continuous_proportional`) — for a long-term,
  season-long comparison design. Every EMU keeps a dedicated device for
  the whole project, and the exact position rotates weekly through that
  EMU's position pool — one new position every calendar week, wrapping
  (repeating) once a small EMU's pool is exhausted. Weeks are back-to-back
  with no extra gap (the device never leaves its EMU).
- **`zone_scoped_continuous`** — for a project with `zone_is_emu: true`
  (currently Tata Motors Pimpri only): every real, client-declared zone
  is its own EMU directly (see 03_emu_delineation), gets its own
  permanently-assigned device, and the position rotates weekly through
  that zone's own real pool exactly like `continuous_multi_week` — but
  additionally season-resets (see `season_length_weeks` config): the
  rotation index resets at every season boundary rather than running as
  one long continuous cycle, so a fixed point lands at the same relative
  week in every season, which a client-stated requirement for valid
  season-to-season comparison needed directly (a first attempt reused a
  different, deliberately non-resetting rotation design built for a
  different purpose — corrected before it shipped). Leftover devices
  (more real zones' worth of coverage than 1-device-per-zone uses) go to
  whichever zone has the largest real pool capacity as a genuine second
  position each week, offset from the first so it isn't a duplicate.
  Where a real zone's own capacity at the standard acoustic-derived
  spacing floor falls short of a full season's worth of distinct
  positions, `allow_small_emu_spacing_relaxation` (opt-in, off by
  default) permits a real, explicitly-reported drop to a 50m floor for
  that EMU specifically — a genuine trade-off (some acoustic overlap
  risk), never applied silently or project-wide.
- **`stratified_single_pass`** — REAL CORRECTION (Aug 2026, stated
  directly): a one-time baseline survey, where stratification exists
  purely as a sampling design device, not because the EMUs themselves need
  a season of repeated, comparable visits. Each EMU is visited in exactly
  ONE assigned week (not every week), with 1+ devices allocated
  proportional to a real spacing-based capacity estimate (area divided by
  the area one minimum-spacing radius needs, `min_device_spacing_m` in
  config). EMUs are dealt round-robin (sorted by capacity descending) into
  the project's weeks, so large and small EMUs spread across different
  weeks rather than compressing into a few. Any devices left unused in a
  week (a small EMU's low capacity doesn't use the full device count) are
  redistributed as bonus spatial-coverage positions to that week's active
  EMU(s), capped at 3x base capacity so a genuinely tiny stratum doesn't
  get absurdly over-sampled just because the calendar paired it with spare
  capacity.

**Camera trap** follows whichever EMU(s) audiomoth is actively covering
each week (for `continuous_multi_week`/`stratified_single_pass`), rather
than an earlier independent, project-wide pool that could send the field
team to a completely unrelated EMU the same week for no operational
reason. Devices split proportionally across a week's active EMU(s), and
positions are drawn from that EMU's own real candidate pool via the same
spacing-compliant selection used for audiomoth (interior-bias weighted
higher than audiomoth's own, 0.7 vs 0.5 — camera trap draws from a
smaller, already-filtered candidate subset with audiomoth's own picks
excluded, which structurally biases it toward the edge more than
audiomoth's selection unless compensated). For `zone_scoped_continuous`
specifically, where every zone's audiomoth is permanently present every
week, camera trap instead gets its own independent rotation — one real
zone per week, round-robin — since "co-locate with audiomoth's active
EMU" stops meaning anything once audiomoth is never NOT active anywhere.

**Soil chemistry sampling** (currently Soulforest only — see
`build_soil_chemistry_points.py`) is a real, one-time, non-rotating
design: 4-5 corner + 1 centre point per EMU. After several automated
selection approaches (bounding-rectangle corners, nearest-candidate-per-
corner, farthest-point sampling) each solved one real problem but
exposed another on real visual inspection of the map, every point is now
a manually specified, real candidate name, verified to exist and belong
to its stated EMU before use rather than algorithmically chosen — no
geometry is invented, and a name that fails to resolve fails loudly
rather than silently substituting something else. One real exception,
flagged explicitly rather than silently handled: an EMU whose given
centre candidate is identical to one of its own given corners uses the
EMU's real geometric centroid for the centre instead, to avoid two
labelled points collapsing onto the same coordinate. Rendered as its own
field-map layer, not modelled by the weekly rotation logic at all. Other
configured streams (water/soil eDNA, water quality) remain one-time,
fixed-location samples with no real coordinates generated by this
pipeline at all — the
field map's legend says so explicitly.

A deployment schedule CSV/Excel export (`04b_schedule_export`) turns the
JSON schedule into real calendar dates, using each project's
`project_start_date` config value — falling back to relative day labels
("Day 1", "Day 8", ...) for a project that hasn't set one yet, rather than
refusing to export. Confirmed directly working for every regime, not just
the one it was originally built against.

### 05_metrics_rollup
EMU and project-level covariate distributions (median, IQR, area-weighted
mean) — always shown alongside a non-compensatory "worst" flag, never the
flag alone (a specific, deliberate design choice: a single declining tile
inside an otherwise-healthy EMU should never read as "no improvement
happening" project-wide). Two indicator families, split by whether the
small-tile confidence floor applies: parcel-intrinsic (computed on the
candidate's own footprint) vs. landscape-buffer (computed on a fixed-radius
buffer regardless of candidate size).

**Scientific defensibility check** (Aug 2026, added after a direct
question: "are these ecologically different? We should be able to defend
that"): every pair of EMUs is compared on their real, fine-resolution
covariate medians (normalized by the project's own observed range),
flagging any pair whose profiles are statistically near-identical as
worth field verification before treating them as separately meaningful
strata in any client-facing interpretation. Coarse-resolution covariates
(LST_C at 1km, NightLights at ~500m) are excluded from this specific
comparison — confirmed directly that including them contributed pixel-
sampling noise, not real signal, at the spatial scale of a single EMU,
which could otherwise mask or exaggerate a real similarity. Building this
check properly reversed an earlier, narrower informal assessment: a
4-covariate eyeball comparison had suggested two Soulforest segments
looked suspiciously similar, but the full, correctly-normalized 13-
covariate check found real, meaningful separation between them instead —
a reminder that a quick manual check on a handful of covariates can
overstate similarity that a comprehensive one doesn't support.

**`stratum_profile.csv`** (Aug 2026, matching the equivalent Tata Motors
deliverable) exports one row per EMU across all 15 covariates' real
median values — the source data behind the report's own stratification
table, at full resolution for anyone who wants to see it directly.

### 06_reporting
Generates the client-facing site selection report and `field_map.html` —
two separate files (the report never duplicates the interactive map,
mirroring the Pimpri methodology doc's own relationship to its
`field_map.html`). The report's structure matches that document's depth:
purpose/scope, the site as measured, design principles, the real
methodology diagnostics this specific run produced (MMU search trace,
clustering K-bounds, CRITIC weights), stratification result, position pool
status per EMU, deployment schedule, covariate profile, an output-file
guide, and declared caveats compiled from every prior stage's own
`warnings` field. Every number in it is read from a prior stage's JSON —
nothing is stated that the underlying data doesn't support.

The field map supports three real view modes, not just an overlay: **all**
(everything shown together), **by week** (only that week's active EMUs and
their real active position(s) for that specific week — using the actual
weekly rotation data for `continuous_proportional` projects, or that
cycle's panel for `sequential_cluster` ones), and **by EMU** (that one
EMU's full candidate/parcel pool plus its position pool, isolated from
everything else). See `docs/OUTPUT_FILE_GUIDE.md` for exactly which files
in a project's `outputs/` folder are meant to reach a client.

### 07_reference_handoff
Exports each EMU as its own individual GeoJSON file, ready for
`darukaa_reference`'s `project_aggregation.run_multi_tile_project(
tile_paths=[...])` (Aug 2026, built and tested directly against that
repo's real code, not assumed from its docs alone). One real, dissolved
polygon per EMU — a Polygon for a contiguous-archetype EMU, a MultiPolygon
for a scattered agroforestry one, both confirmed loading correctly with
`darukaa_reference`'s actual `SiteLoader`. `site_id` is set directly to
the real EMU ID in each file's own properties, so `SiteLoader` uses it
as-is rather than auto-generating a generic one. Also writes
`tile_manifest.json` — the `tile_paths`/`tile_labels` lists
`run_multi_tile_project` expects, generated directly.

This is a genuinely independent stage: nothing else in this pipeline reads
its output, and `darukaa_reference` itself has no dependency on this stage
existing at all — it accepts any real site boundary (KML/GeoJSON/
shapefile) regardless of origin, confirmed directly with a standalone
polygon that never touched this pipeline. This stage exists purely to
save the manual step of producing per-tile files by hand when the
boundaries did come from EMU delineation.

## 3. Open methodological gaps

Stated plainly rather than hidden:
- **The EMU compactness vs. device-coverage tension flagged here previously
  is now resolved by decoupling the two concerns** (Aug 2026 — see 03b's
  deployment-eligibility outlier exclusion): EMU identity and its ex-situ
  metrics are never affected by device-logistics feasibility, and a
  severely isolated member parcel is excluded from device-position
  eligibility rather than forced into a separate EMU or left as an
  unaddressed spread violation. Confirmed working on real GV data (the
  86-100km EMU_Ganjam_2 outliers). **Soova's own 22km-spread case has not
  been re-run against this fix** — that project is on hold pending an
  updated client KML, by explicit instruction, not because the mechanism
  doesn't apply to it.
- Aquatic covariates (waterbody-level, separate from the terrestrial grid)
  are ingested per-project now, but not yet rolled into 05's metrics or
  shown on the field map.
- `darukaa_reference` handoff (the original architecture plan's "Phase 4")
  — not started.
- Tata Motors has not been ported into this pipeline — stays on
  `Darukaa_SiteSelectionPipeline_v6.0`'s `run_project.py`.
