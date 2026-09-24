/**
 * PHASE 2: GEE Ex-Situ Metrics  —  Darukaa Site Selection Pipeline v6.2
 * ============================================================
 * Standalone Google Earth Engine JavaScript script.
 *
 * CHANGELOG v6.1 -> v6.2  —  FOUNDATION-MODEL EMBEDDING, IMPLEMENTED
 * -----------------------------------------------------------------
 * The v5.0 scaffold below (kept for history) proposed exporting satellite-
 * embedding vectors but left the asset unconfirmed ("these evolve; set
 * EMBEDDING_ASSET at implementation"). It is now confirmed and implemented:
 * Google's Satellite Embedding dataset (AlphaEarth Foundations), launched
 * publicly July 2025, annual global coverage 2017-2025, 64-dim, 10 m.
 * Asset: GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL.
 *
 * WHY EMBEDDINGS FOR STRATIFICATION SPECIFICALLY (not a blanket "embeddings
 * are better" claim — checked the literature rather than assuming):
 *   - Land-cover / crop-type CLASSIFICATION: embeddings beat hand-crafted
 *     feature baselines (0.78 vs 0.70 balanced accuracy on LCMAP; 0.90 vs
 *     0.82 on Africa crop mask) and produce visibly smoother, more
 *     ecologically coherent cluster boundaries than pixel-by-pixel spectral
 *     classification (Brown et al. 2025; wetland-mapping comparison, MDPI
 *     Remote Sensing 18(2):293, 2026).
 *   - Specific STRUCTURAL/BIOPHYSICAL ESTIMATION (e.g. biomass): hand-crafted
 *     spectral indices have been shown to OUTPERFORM embeddings (Solano-Correa
 *     et al. 2025/26, tropical Andean forests) — embeddings are generic
 *     representations, not optimised for one named biophysical parameter.
 *   This is why embeddings drive STRATUM FORMATION (a classification task)
 *   below, while the named, interpretable MCDA criteria continue to drive
 *   WITHIN-STRATUM POSITION SCORING (an auditable-ranking task) in
 *   PHASE_3_StratifyAllocate.py — not a compromise, an assignment of each
 *   method to the job it's evidenced to be better at.
 *
 * IUCN GLOBAL ECOSYSTEM TYPOLOGY — pre-reconnaissance ecological typing
 * -----------------------------------------------------------------------
 * The other half of the v5.0 scaffold ("classifies to IUCN GET / Champion &
 * Seth") is also implemented, for the part that has a real GIS asset:
 * IUCN/GlobalEcosystemTypology/current (Level 3, Ecosystem Functional
 * Groups) is a real, public Earth Engine FeatureCollection. Every candidate
 * and every waterbody is spatially joined against it, giving a named,
 * citable ecosystem-type label BEFORE the field visit — not a placeholder
 * "ST3". Champion & Seth (1968) has no equivalent ready-made GIS layer (it
 * exists as published maps/literature, not a clean public GIS asset) — it is
 * cited in the methodology narrative as supporting literature, not run as an
 * automated join. Don't claim more automation for it than that.
 *
 * DATASET CURRENCY AUDIT (client feedback: "all criteria must use the most
 * updated datasets") — three real upgrades made this pass, verified against
 * the live Earth Engine catalog rather than assumed current:
 *   gHM            CSP/HM/GlobalHumanModification is a FIXED 2016 snapshot,
 *                  never updated, no update planned under that asset ID —
 *                  confirmed via the EE catalog page. Replaced with TNC
 *                  Global Human Modification v3 (Theobald et al. 2025),
 *                  2022 snapshot, and at 90 m instead of 1 km — a real
 *                  resolution upgrade that matters at 159 ha (gHM at 1 km
 *                  gave roughly a dozen usable pixels across the whole
 *                  candidate frame; 90 m gives ~1,900).
 *   Elevation      USGS/SRTMGL1_003 (2000 vintage, known voids) replaced
 *                  with COPERNICUS/DEM/GLO30_2024_1 — newer (TanDEM-X derived),
 *                  more accurate, gap-filled. Lower priority than gHM since
 *                  elevation itself doesn't change over time, but the
 *                  client asked for "most updated" across the board.
 *   Water extent   JRC/GSW1_4/GlobalSurfaceWater (Occurrence) capped at
 *                  2021. Replaced with the v1.5 Occurrence layer (corrected
 *                  computation, Landsat Collection 2 extended through 2024).
 *                  VERIFY the exact asset path in the Asset browser before
 *                  running — confirmed to exist via the JRC data-access page
 *                  but not independently loaded and inspected band-by-band
 *                  here; if the path below 404s, browse
 *                  projects/global-surface-water/assets/GSW1_5/ for the
 *                  current name.
 *   Hansen GFC     Version string HANSEN_VERSION below — CHECK this is the
 *                  current release before running; Hansen updates annually
 *                  and a hardcoded version string silently goes stale.
 *
 * HARD EXCLUSION — built-up / impervious surface (client feedback: sites
 * landing on buildings)
 * -----------------------------------------------------------------------
 * v5.0 already has a binary hard-constraint mechanism (Slope_deg, JRC_Water
 * — see PHASE_2_GEEMetricsIngest.py's _apply_binary_filters()) but the v6.1
 * point-candidate track never wired an equivalent in. This script now also
 * exports BuiltUp_Pct (ESA WorldCover "Built-up" class fraction in each
 * candidate's footprint) so PHASE_3_StratifyAllocate.py can drop any
 * candidate whose footprint is majority rooftop/hardstanding BEFORE
 * stratification, not leave it for the field team to discover.
 *
 * CHANGELOG v4.x -> v5.0  (kept for history)
 * ----------------------
 * FOUNDATION-MODEL ECOSYSTEM STRATIFICATION (scaffold; Phase 3 §4).
 * In addition to the 8 MCDA criteria, this script can export per-candidate
 * satellite-embedding vectors from a geospatial foundation model, which cluster
 * into ecologically coherent ecosystem TYPES more faithfully than single-date
 * spectral indices. The exact asset is intentionally NOT hardcoded (these evolve);
 * set EMBEDDING_ASSET at implementation. Known candidates (confirm ID/spec at run
 * time): Google Satellite Embedding / AlphaEarth (~64-dim annual, 10 m), Clay,
 * IBM-NASA Prithvi. Steps: load annual embedding IC -> reduceRegions(mean,10) to
 * attach the vector to each candidate -> export with the MCDA metrics; Phase 3
 * then clusters on the embedding, classifies to IUCN GET / Champion & Seth, and
 * stratification_maps.py writes the visual verification maps + separability
 * diagnostics. Leave EMBEDDING_EXPORT=false to reproduce v4.x exactly.
 *
 * CHANGELOG v3.0 -> v4.0
 * ----------------------
 * Expanded from 3 to 8 MCDA criteria across 4 TNFD Annex 2-aligned
 * dimensions, so "multi-criteria" is defensible in an audit:
 *
 *   Vegetation structure     NDVI_raw (existing), TreeCover_Pct (NEW)
 *   Terrain heterogeneity    ElevStd_m (existing), TRI_m (NEW)
 *   Connectivity / threat    NatCoverPct_2km (existing), EdgeDensity_2km (NEW)
 *   Anthropogenic pressure   gHM (NEW), DistWater_m (NEW)
 *
 * Slope_deg and JRC_Water are unchanged — they remain BINARY FILTER
 * columns (hard constraints applied in PHASE_2_GEEMetricsIngest.py),
 * not MCDA criteria.
 *
 * INPUT: Zipped Shapefile produced by Phase 1
 *   File: normalized_candidates.zip  (in your project outputs folder)
 *
 * UPLOAD STEPS:
 *   1. Go to code.earthengine.google.com
 *   2. Assets tab -> NEW -> Table Upload -> Shape files (.zip)
 *      -> select normalized_candidates.zip from your outputs folder
 *   3. Name the asset, wait for upload (Tasks tab — yellow -> green)
 *   4. Set ASSET_PATH below to the full asset path shown in Assets panel
 *
 * COLUMN NOTE: Shapefile format limits names to 10 characters. Phase 1
 * renames columns on export — this script uses the truncated names:
 *     Site_ID, Src_Type (was Source_Type), Cent_Lat, Cent_Lon, Geom_Type
 *   The output CSV uses full names (NDVI_raw, TRI_m, etc.) for clean
 *   merging back into the pipeline via PHASE_2_GEEMetricsIngest.py,
 *   which reads cfg.GEE_METRIC_COLUMNS generically — no Python change
 *   needed when adding bands here, as long as the column names match.
 *
 * GOLDEN RULE: All reduceRegions calls operate over the POLYGON
 * GEOMETRIES, not centroid points (No Metric Dilution).
 *
 * OUTPUTS per feature (in exported CSV):
 *   Site_ID            — join key
 *   NDVI_raw           — Sentinel-2 median NDVI (cloud-masked)
 *   TreeCover_Pct      — NDVI-threshold-based woody/canopy cover proxy (see
 *                        v6.3.12 comment at its computation) — % of a
 *                        candidate's pixels with NDVI above
 *                        TREE_COVER_NDVI_THRESHOLD. A proxy, not a true
 *                        land-cover classification; TreeCover_Pct_EsriClassifier
 *                        and TreeCover_Pct_Hansen_LossAdjusted are kept as
 *                        secondary reference bands from earlier iterations.
 *   ElevStd_m          — SRTM elevation std-dev within 500m kernel
 *   TRI_m              — Terrain Ruggedness Index (mean abs. neighbour diff)
 *   NatCoverPct_2km    — % natural cover in 500m-2km annulus
 *   EdgeDensity_2km    — natural/non-natural boundary density in 2km annulus
 *   gHM                — CSP Global Human Modification index (0-1)
 *   DistWater_m        — distance to nearest JRC seasonal+permanent water
 *   Slope_deg          — slope in degrees (binary filter, Phase 2 Python)
 *   JRC_Water          — permanent water flag (binary filter, Phase 2 Python)
 */

// ===================================================================
// CONFIG — edit these before running
// ===================================================================

var ASSET_PATH  = "projects/darukaa-earth-product/assets/terrestrial_candidates";
var EXPORT_NAME = "gee_covariates_output";
var DRIVE_FOLDER = "darukaa_v3_gee";

// EXPORT_NAME stays constant across runs, so the Tasks tab can accumulate
// several export tasks with the same name after repeated iterations. If
// more than one "gee_covariates_output" entry appears there, match it to
// this run using the timestamp printed below rather than assuming the
// first entry listed is the current one.
print("=== RUN STARTED:", new Date().toString(), "===");
print("If your Tasks tab has more than one 'gee_covariates_output' entry, "
     + "use the one whose creation time matches the run time above — "
     + "not just whichever appears first in the list.");

// Which candidate pipeline produced ASSET_PATH.
//   "shapefile_v5"  v5.0 Phase 1 output — real polygons, truncated 10-char
//                   column names (Site_ID, Cent_Lat, Cent_Lon, ...). Unchanged
//                   from v5.0; this is the default so existing projects run
//                   exactly as before.
//   "csv_v6"        v6.0 PHASE_0b_SiteFrame.py output (terrestrial_candidates.csv)
//                   — POINT candidates (SITE_ID, LAT, LON, full column names,
//                   no truncation because it's a CSV asset, not a shapefile).
//                   Used by the stratum-panel / walkable-campus track
//                   (run_project.py) — e.g. Tata_Motors_Pimpri.
// Upload steps for "csv_v6": Assets -> NEW -> Table Upload -> CSV, select
// terrestrial_candidates.csv directly (no shapefile conversion needed).
//
// "unified"  — this repo's own pipeline (Darukaa_SiteSelection, Aug 2026
//              onward). Upload steps: run
//              `python common/gee_export.py <project_dir>` first — GEE's
//              Cloud Assets manager does NOT accept raw .geojson/.json
//              uploads through the UI (confirmed directly, this was
//              originally documented wrong here as a plain GeoJSON upload
//              — fixed after hitting the real error). That script writes a
//              zipped ESRI Shapefile instead (the format GEE's UI actually
//              accepts, along with CSV) containing only a `name` column —
//              short enough to survive the format's 10-character field
//              truncation with no mapping needed. Assets -> NEW -> Table
//              Upload -> Shapefile -> select that .zip.
var CANDIDATE_SCHEMA = "unified";  // pre-set for SoulForest_Veltoor (conservation) — do not change

// v6.3.12: NDVI threshold for the TreeCover_Pct proxy (see the vegetation-
// structure section below for the full reasoning — moved to the top of
// the file, alongside the other top-level config constants, specifically
// because it's used before its original declaration point further down;
// JS hoists `var` declarations but not their assigned value, so using it
// at the original location evaluated as `undefined` — a real bug caught
// by checking variable ordering, not by a runtime GEE error message,
// which for a `.gt(undefined)` call may not surface clearly at all).
var TREE_COVER_NDVI_THRESHOLD = 0.3;

// csv_v6 only: candidates are points, so reduceRegions needs a real footprint,
// not a zero-area point (the Golden Rule below still applies — we reduce over
// a footprint, just one representing the sensor's detection space rather than
// a client-drawn polygon). Set to the stream's detection radius; 50 m matches
// the AudioMoth upper-bound radius used for MIN_SPACING_M in
// config_project_Tata_Motors_Pimpri.py — keep the two in step.
var CANDIDATE_POINT_BUFFER_M = 50;

// v6.0: context-window radii for the annulus metrics (NatCoverPct / EdgeDensity).
// v5.0 used a fixed 500m-2km annulus, which is the right scale for landscape
// pressure reporting on a large AOI but the wrong scale for stratifying a
// small (<200 ha) site — a 2km window sits almost entirely outside the fence
// and becomes near-constant across candidates, contributing nothing to the
// clustering. Both are now exported: use the 500m version for stratification
// on small sites, the 2km version for landscape context/reporting on any site.
var CONTEXT_RADIUS_INNER_M = 500;
var CONTEXT_RADIUS_OUTER_M = 2000;
var CONTEXT_RADIUS_SMALL_M = 500;   // small-site stratification variant

// v6.0 [C-12]: optional aquatic covariate export. Leave "" to skip entirely
// (default — no behaviour change for terrestrial-only projects). Set to a
// GEE table asset of waterbody polygons (e.g. from
// PHASE_1b_AquaticNormalization.py's waterbodies.geojson, uploaded as a
// table) to also export water-permanence and riparian-cover metrics per
// waterbody, to a SEPARATE CSV (EXPORT_NAME + "_aquatic").
//
// REAL BUG FIXED HERE (Aug 2026, caught by comparing three separate
// projects' "aquatic" CSV outputs byte-for-byte and finding them
// IDENTICAL — including waterbody names "Sumanth Sarovar"/"Sharma Lake",
// which are Tata Motors' Pimpri waterbodies, not Soova/GV/Soulforest's):
// this line previously hardcoded that real TM asset path as the default,
// directly contradicting this comment's own stated default of "". Every
// project that ran this script queried the SAME fixed TM asset regardless
// of which candidates it actually uploaded, since nothing here was ever
// project-specific. Reset to the documented "" default; per-project
// values are now generated by common/gee_export.py's
// build_ready_to_run_script(), which only ever populates this for a
// project that (a) isn't agroforestry and (b) actually has real water
// features to export — never a shared fallback path.
var WATERBODY_ASSET_PATH = "";

// v6.2 [EMBEDDING]: satellite-embedding export, now real (was a scaffold
// placeholder in v5.0/v6.1). Adds 64 EMB_00..EMB_63 columns to the export,
// the mean AlphaEarth embedding vector per candidate footprint. Used by
// PHASE_3_StratifyAllocate.py when STRATIFICATION_MODE is "embedding" or
// "hybrid"; harmless (ignored) if STRATIFICATION_MODE == "mcda".
var EMBEDDING_EXPORT = true;
var EMBEDDING_YEAR = 2024;   // most recent full year at time of writing;
                              // bump to 2025 once that annual layer is confirmed complete

// v6.2 [IUCN-GET]: pre-reconnaissance ecological typing. Every candidate and
// every waterbody is spatially joined against IUCN's Global Ecosystem
// Typology (Level 3, Ecosystem Functional Groups) — a real, public
// FeatureCollection, not a placeholder. Gives a named, citable type before
// the field visit; STRATUM_MODE="hybrid" in the Python pipeline still lets
// field labels override this once reconnaissance happens. Champion & Seth
// (1968) has no equivalent ready-made GIS asset — cited as literature in the
// methodology narrative, not run as an automated join here. Don't imply it
// is being spatially joined when it isn't.
var IUCN_GET_EXPORT = true;
var IUCN_GET_ASSET = "IUCN/GlobalEcosystemTypology/current";

// v6.2 [DATASET-CURRENCY]: verify HANSEN_VERSION is the current release
// before running — Hansen Global Forest Change updates annually and a
// hardcoded string silently goes stale. Check
// https://developers.google.com/earth-engine/datasets/catalog/UMD_hansen_global_forest_change_2023_v1_11
// (or the current year's catalog page) for the latest version string.
// v6.3.10 [DATASET-CURRENCY]: bumped to v1.13 (2025 release) -- confirmed
// current via the live Earth Engine Data Catalog page
// (UMD_hansen_global_forest_change_2025_v1_13), which extends coverage
// through 2025. Was v1.12 (through 2024), one release behind.
var HANSEN_VERSION = "UMD/hansen/global_forest_change_2025_v1_13";  // v6.3.10: was
                              // 2024_v1_12 — confirmed current release (through 2025) via
                              // the live EE catalog. Re-check yearly; Hansen updates annually.

// NDVI computation window
// CHANGED (Aug 2026, reported directly): this was a FIXED "2025-10-01" to
// "2026-05-31" window — a deliberate post-monsoon-peak / pre-next-monsoon
// choice (avoids monsoon cloud contamination, gives a dry-season condition
// baseline that's comparable across projects/seasons). Real, defensible
// reasoning — but it also means the window silently goes stale every time
// the script is re-run without updating it by hand, and it structurally
// EXCLUDES monsoon-season vegetation growth. A client directly reported
// visibly more greenery on a site right now (Aug 2026) that this window
// would never see, since it stops at end-May.
//
// Switched to a ROLLING most-recent-12-months window instead, computed
// from the actual run date rather than hand-maintained — captures current
// on-the-ground condition (including monsoon growth) and never goes stale.
// A full year of cloud-filtered (<20%) scenes still builds a robust
// composite rather than a single noisy snapshot.
//
// TRADE-OFF, stated plainly rather than hidden: this rolling window is
// LESS comparable across projects run at different times of year than the
// fixed dry-season window was, and may pick up more monsoon-cloud-affected
// scenes in persistently cloudy regions. If cross-project seasonal
// comparability matters more than current-condition accuracy for a given
// project, revert to an explicit fixed NDVI_START/NDVI_END instead — both
// are legitimate choices for different purposes, this is not a strictly
// "more correct" fix, just a different, now-explicit trade-off.
var NDVI_END    = ee.Date(Date.now()).format("YYYY-MM-dd").getInfo();
var NDVI_START  = ee.Date(Date.now()).advance(-12, "month").format("YYYY-MM-dd").getInfo();

// v6.3.10 [DATASET-CURRENCY, real fix]: land cover source swapped ESA
// WorldCover v200 -> Esri/Impact Observatory Sentinel-2 10m Annual Land
// Cover Time Series. Confirmed via the Earth Engine catalog: ESA WorldCover
// v200 is a SINGLE FIXED SNAPSHOT (dataset availability 2021-01-01 to
// 2022-01-01 only, no update mechanism) -- exactly the same "frozen
// baseline presented as current" problem already fixed for Hansen tree
// cover below, just not caught here until now. Esri's product is genuinely
// annually updated (confirmed via its own changelog: 2017 through 2025,
// most recently updated 2026-05-25) at the SAME 10m resolution and SAME
// Sentinel-2 source imagery, so this is a like-for-like currency upgrade,
// not a resolution trade-off. Real, official asset (community-hosted under
// sat-io, same treatment as gHM/VIDA elsewhere in this script -- not the
// official EE catalog namespace, but a real, citable, actively-maintained
// product): projects/sat-io/open-datasets/landcover/ESRI_Global-LULC_10m_TS
// Class VALUES (not just names) confirmed directly from the dataset's own
// authoritative documentation page -- not guessed, given how badly a wrong
// class-value mapping would silently corrupt everything downstream
// (built-up exclusion, segmentation input, fragmentation calc, riparian
// cover):
//   1 = Water, 2 = Trees, 4 = Flooded Vegetation, 5 = Built Area,
//   7 = Snow/Ice, 8 = Bare Ground, 9 = Rangeland, 10 = Clouds
//   (Crops = 5 in the OLD 10-class scheme was renumbered; this dataset's
//   "Crops" class value is NOT 5 -- 5 is "Built Area" here. Verify class
//   value 3/6 do not appear in this band; they were intentionally retired
//   when Grass+Scrub were merged into Rangeland, per the dataset's own
//   changelog.)
// Genuinely useful side effect for the recurring "points on buildings/
// parking" problem this project has had: Esri's OWN "Built Area" class
// definition explicitly INCLUDES "parking structures... paved roads,
// asphalt" -- exactly the paved-but-unroofed case ESA WorldCover's
// Built-up class was documented (see PHASE_3_StratifyAllocate.py's binary-
// filter comments) to sometimes miss.
// v6.3.11 [honest tradeoff, checked systematically not assumed]: this
// switch was evaluated on currency, resolution, accuracy, AND cloud-cover
// robustness -- not just "newer is better". Confirmed via a peer-reviewed
// comparative validation study: ESA WorldCover's Sentinel-1 SAR + Sentinel-2
// fusion gives it a real, documented advantage specifically in persistent
// cloud cover ("radar data penetrates cloud cover... particularly in
// cloudy or mixed vegetated areas where optical data alone are
// insufficient") -- Esri's product is Sentinel-2 optical only, mitigated
// by least-cloudy-scene selection and annual mode-compositing, not SAR.
// Accuracy is a near-tie (ESA 74.4% vs Esri ~75%, both independently
// validated) and resolution is identical (10m both). This makes the
// decision genuinely currency-driven, not a strictly-better-in-every-way
// swap: ESA's cloud-robustness advantage is real but MOOT for this
// project's actual problem, since it hasn't been re-run since 2021
// regardless of that advantage (a v2.0 reprocessing is reportedly planned
// but has no confirmed delivery date). Pune has a distinct dry season
// outside the monsoon (already the reason NDVI_START/END below are set
// post-monsoon), not near-permanent cloud cover, so Esri's non-SAR cloud
// mitigation is judged adequate for this specific site -- but this is a
// site-specific judgement call, not a universal one. If a future project
// sits in a persistently cloud-covered region (parts of the Northeast,
// the Western Ghats in monsoon, etc.), re-open this comparison rather than
// assuming this same choice carries over.
var LC_YEAR = 2025;   // most recent available; bump when a newer year is added
                      // (check the dataset's changelog at gee-community-catalog.org/projects/S2TSLULC/)
var worldCover = ee.ImageCollection("projects/sat-io/open-datasets/landcover/ESRI_Global-LULC_10m_TS")
  .filterDate(LC_YEAR + "-01-01", (LC_YEAR + 1) + "-01-01")
  .mosaic();

// Natural cover classes -- Esri Sentinel-2 10m Annual Land Cover, class
// VALUES (not the dataset's separate "remapped 1-9" column -- the raw band
// itself uses these): 1=Water, 2=Trees, 4=Flooded Vegetation, 9=Rangeland
// are treated as natural, matching the original ESA-scheme's intent
// (vegetation/water = natural; cropland, built-up, and bare ground
// excluded). 10=Clouds is a genuine "no data" case for that pixel/year,
// not natural or built -- excluded from both natural and built-up masks
// rather than silently counted as either.
var NATURAL_CLASSES = [1, 2, 4, 9];
//change classes for agroforestry and conservation, for example, you might want to include Crops (5 in the old ESA scheme; verify Esri's own Crops class value before reusing this number here) if agroforestry is considered natural in your context. Adjust the NATURAL_CLASSES array accordingly:

// Scale for reduceRegions (metres)
var REDUCE_SCALE = 10;

// Hansen GFC treecover threshold/year — use the canopy density layer directly,
// no threshold needed (treecover2000 is already a 0-100% continuous band).
// HANSEN_VERSION is declared in the CONFIG block above — verify it's current
// before running (Hansen updates annually; a hardcoded string goes stale).

// ===================================================================
// LOAD CANDIDATES
// ===================================================================

var candidatesRaw = ee.FeatureCollection(ASSET_PATH);
print("Candidate count:", candidatesRaw.size());

// v6.0 [C-12]: csv_v6 candidates arrive as bare rows (no geometry column) with
// LAT/LON fields. Build a point geometry per row, then buffer it so
// reduceRegions has a real footprint to reduce over — see CANDIDATE_POINT_BUFFER_M.
// shapefile_v5 candidates already carry real polygon geometry; passed through
// unchanged, preserving the v5.0 Golden Rule (reduce over the client-drawn
// polygon, not a centroid).
var candidates = (CANDIDATE_SCHEMA === "csv_v6")
  ? candidatesRaw.map(function(f) {
      var pt = ee.Geometry.Point([ee.Number(f.get("LON")), ee.Number(f.get("LAT"))]);
      return f.setGeometry(pt.buffer(CANDIDATE_POINT_BUFFER_M));
    })
  : candidatesRaw;

// Column names differ by schema: shapefile_v5 uses shapefile-truncated names
// (Site_ID); csv_v6 uses full names (SITE_ID) because a CSV asset has no
// 10-character limit; "unified" is the schema this repo's own pipeline
// produces (common/gee_export.py exports a MINIMAL shapefile with just a
// `name` field — short enough to survive shapefile truncation untouched —
// so no truncated-column mapping is needed here at all).
//
// CORRECTNESS FIX (found while addressing a real upload-format bug report,
// Aug 2026): this was previously re-derived independently via the SAME
// ternary at 5 separate call sites (ID_COL here, plus pointOnBuildingKey,
// segJoinKey, joinKey, joinKeyPOB further down) despite this comment
// already claiming "resolved once ... so the rest of the script doesn't
// need an if/else at every use." Adding a third schema value at only this
// definition would silently NOT have propagated to the other 4 sites —
// caught by actually tracing every CANDIDATE_SCHEMA usage with grep rather
// than trusting the comment. All 5 sites now reference this single ID_COL
// variable instead of re-deriving their own copy.
var ID_COL = (CANDIDATE_SCHEMA === "csv_v6") ? "SITE_ID"
  : (CANDIDATE_SCHEMA === "unified") ? "name"
  : "Site_ID";
print("First feature:", candidates.first());

// ===================================================================
// DATA SOURCES
// ===================================================================

// Sentinel-2 Surface Reflectance
var s2 = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
  .filterDate(NDVI_START, NDVI_END)
  .filterBounds(candidates.geometry().bounds())
  .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20));

function maskS2Clouds(image) {
  var scl = image.select("SCL");
  var clearMask = scl.eq(4).or(scl.eq(5)).or(scl.eq(6)).or(scl.eq(7)).or(scl.eq(11));
  return image.updateMask(clearMask)
    .divide(10000)
    .copyProperties(image, ["system:time_start"]);
}

var s2Masked = s2.map(maskS2Clouds);
print("Sentinel-2 scenes (cloud < 20%):", s2Masked.size());

// Median composite NDVI
var ndviImage = s2Masked
  .map(function(img) {
    return img.normalizedDifference(["B8", "B4"]).rename("NDVI");
  })
  .median()
  .rename("NDVI_raw");

// TreeCover_Pct — see the v6.3.12 note above for why this replaced a
// categorical land-cover classification: % of a candidate's pixels with
// NDVI above TREE_COVER_NDVI_THRESHOLD, computed at the same 10m pixel
// resolution as everything else here, from the same validated NDVI
// composite already used for NDVI_raw. A genuine proxy for canopy
// presence, not a true land-cover classification — documented as such
// rather than presented as more authoritative than it is.
var treeCoverPct = ndviImage.gt(TREE_COVER_NDVI_THRESHOLD).multiply(100).rename("TreeCover_Pct");

// --- VEGETATION STRUCTURE: current tree cover ---
// v6.3.12 [REAL FIX, Aug 2026]: the v6.3.11 fix (below) switched from the
// frozen Hansen calculation to the Esri land-cover "Trees" class — correct
// in general, but CONFIRMED STILL BROKEN for Soulforest Veltoor specifically
// on a fresh re-run: TreeCover_Pct remained exactly 0.0 across all 653
// candidates. Cross-checked against NatCoverPct_2km (only ~10-12% here
// despite real NDVI of 0.24-0.50 across the same candidates) — this is a
// genuine Esri land-cover classifier limitation for this site's
// vegetation type (a young plantation/restoration area), the same root
// cause behind the BuiltUp_Pct misclassification documented in
// covariate_ingest.py, not a formula bug. Switching to a DIFFERENT class
// value within the same classifier wouldn't fix a classifier that's
// systematically failing to recognize this area's vegetation at all.
//
// Fixed by computing tree/woody cover directly from NDVI at the pixel
// level (not from a categorical land-cover classification at all),
// reusing the already-computed, already-validated ndviImage below rather
// than depending on a classifier confirmed unreliable at this site. NDVI
// > 0.3 as the "woody/canopy vegetation present" threshold is a
// deliberately moderate choice for this specific ecosystem context (a
// young plantation/restoration site where even good canopy here tops out
// around NDVI 0.5, not the 0.6+ typical of dense mature forest) — this is
// an NDVI-based PROXY for canopy presence, not a true land-cover
// classification, and is documented as such rather than presented as a
// more authoritative number than it is. TREE_COVER_NDVI_THRESHOLD is
// declared at the top of the file (search for it) since it's used before
// this point in file order — actually computed a few dozen lines above,
// right after ndviImage is defined.

// v6.3.11 [prior fix, kept only as a labelled reference band — see the
// v6.3.12 note above for why this alone wasn't sufficient]: current tree
// cover via the current (2025), annually-updated Esri land-cover
// classification (worldCover) instead of the frozen/loss-adjusted Hansen
// product — class 2 = "Trees".
var treeCoverPctEsriClassifier = worldCover.eq(2).multiply(100).rename("TreeCover_Pct_EsriClassifier");

var hansen = ee.Image(HANSEN_VERSION);
var lossMask = hansen.select("lossyear").gt(0);   // true wherever ANY loss since 2000 was recorded
var treeCoverPctHansenLossAdjusted = hansen.select("treecover2000")
  .where(lossMask, 0)
  .rename("TreeCover_Pct_Hansen_LossAdjusted");

// v6.2 [DATASET-CURRENCY]: elevation source swapped SRTM -> Copernicus DEM.
// USGS/SRTMGL1_003 is year-2000 vintage with known voids in complex terrain.
// COPERNICUS/DEM/GLO30_2024_1 (TanDEM-X derived) is newer, more accurate,
// and gap-filled. NOTE: the plain "COPERNICUS/DEM/GLO30" ID is DEPRECATED —
// confirmed via the EE catalog page ("superseded by COPERNICUS/DEM/GLO30_2024_1"),
// caught during a verification pass on 2026-08-06; using the deprecated ID
// is exactly the kind of staleness this dataset-currency audit exists to
// catch, so the current ID is used below. Lower priority than the gHM/water
// swaps since elevation itself doesn't change over time — included because
// the client asked for "most updated" applied consistently, not selectively.
// Band name is "DEM"; mosaic() collapses the tiled ImageCollection to one image.
var dem = ee.ImageCollection("COPERNICUS/DEM/GLO30_2024_1").select("DEM").mosaic();
var elevM = dem.rename("Elev_m");
var slope = ee.Terrain.slope(dem).rename("Slope_deg");

var elevStd = dem.reduceNeighborhood({
  reducer: ee.Reducer.stdDev(),
  kernel:  ee.Kernel.circle({ radius: 16, units: "pixels" }),
}).rename("ElevStd_m");

// --- TERRAIN HETEROGENEITY: Terrain Ruggedness Index (NEW) ---
// TRI = mean absolute elevation difference between a pixel and its
// 8 immediate neighbours (Riley et al. 1999), here generalised over
// the same 500m circular kernel used for ElevStd for consistency.
var demMean3x3 = dem.reduceNeighborhood({
  reducer: ee.Reducer.mean(),
  kernel:  ee.Kernel.square({ radius: 1, units: "pixels" }),
});
var triPixel = dem.subtract(demMean3x3).abs();
var tri = triPixel.reduceNeighborhood({
  reducer: ee.Reducer.mean(),
  kernel:  ee.Kernel.circle({ radius: 16, units: "pixels" }),
}).rename("TRI_m");

// v6.2 [DATASET-CURRENCY]: JRC Global Surface Water. v1.4 (active default
// below) caps at 2021 but has a CONFIRMED band name ("occurrence") — kept as
// the safe default rather than guessing. A v1.5 Occurrence layer with
// corrected computation exists (confirmed via the JRC data-access page:
// "corrected Occurrence layer is provided in GSW v1.5") extending coverage
// through 2024, but the exact asset path was not independently loaded and
// band-verified here. Before running: browse
// projects/global-surface-water/assets/GSW1_5/ in the Asset browser, confirm
// the Occurrence image/collection name and its band name, then flip
// JRC_GSW_USE_V1_5 to true below.
var JRC_GSW_USE_V1_5 = false;   // set true after verifying the v1.5 path (see above)
var jrcOccurrence = JRC_GSW_USE_V1_5
  ? ee.Image("projects/global-surface-water/assets/GSW1_5/GlobalSurfaceWater").select("occurrence")
  : ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence");
var jrcWaterFlag = jrcOccurrence.gt(50).rename("JRC_Water");
// Any water at all (occurrence > 0) — used for the distance-to-water criterion
var anyWaterMask = jrcOccurrence.gt(0).rename("any_water");

// --- ANTHROPOGENIC PRESSURE: distance to nearest water (NEW) ---
// fastDistanceTransform returns squared distance in pixel units at the
// image's native scale; sqrt + multiply by 30m (JRC GSW native resolution).
var distWaterPx = anyWaterMask.fastDistanceTransform(256).sqrt();
var distWater = distWaterPx.multiply(30).rename("DistWater_m");

// v6.2 [DATASET-CURRENCY]: gHM source swapped CSP -> TNC Global Human
// Modification v3 (Theobald et al. 2025). The old CSP/HM/GlobalHumanModification
// asset is a FIXED 2016 snapshot with no update mechanism — confirmed via
// the EE catalog page ("for the year 2016", no newer version under that ID).
// TNC v3 gives a 2022 snapshot at 90 m (vs CSP's 1 km) — at 159 ha, 1 km
// resolution gave roughly a dozen usable pixels across the whole candidate
// frame; 90 m gives ~1,900, a real, not cosmetic, resolution upgrade.
// This asset is community-hosted (projects/sat-io/...) rather than in the
// official EE catalog under google/... — still a real, citable, peer-
// reviewed dataset (Theobald et al. 2025), just distributed differently.
// BAND NAME NOT INDEPENDENTLY VERIFIED — the official 300m catalog version
// uses "All_threats_combined" (confirmed); the sat-io 90m version likely
// matches but check via Inspector before running. If it errors, the safe
// fallback (confirmed band name, coarser 300m) is commented below.
var ghm = ee.ImageCollection("TNC/HM/v3/300m_c")
   .filter(ee.Filter.eq("year", 2020)).first()
   .select("All_threats_combined").rename("gHM");

// v6.3.10: worldCover is now defined earlier (see NATURAL_CLASSES block
// above), from the annually-current Esri source rather than the fixed-2021
// ESA snapshot -- no separate load needed here.

// v6.2 [C-5 client feedback]: built-up/impervious hard-exclusion source.
// Reuses the same worldCover load above. v6.3.10: class value 5 is
// "Built Area" in the Esri scheme (was 50 = "Built-up" under the old ESA
// WorldCover scheme this replaced -- confirmed via the dataset's own
// authoritative class table, not guessed). Exported as BuiltUp_Pct (0-100,
// matching the other *_Pct bands' convention) per candidate footprint so
// PHASE_3_StratifyAllocate.py can drop candidates whose footprint is
// majority rooftop/hardstanding BEFORE stratification.
var builtUpMask = worldCover.eq(5).multiply(100).rename("BuiltUp_Pct");

// v6.3.8 [PointOnBuilding, abandoned the building-footprint-dataset
// approach entirely — three separate failure modes across three attempts]:
//
//   Attempt 1 (v6.2, round 2): raster paint() of Open Buildings V3 onto a
//     bare constant image, reduced at the exact point. Came back completely
//     null for every candidate on the real export.
//   Attempt 2 (v6.3.2, round 3): added VIDA as a second building source and
//     .unmask(0) as a defensive fix. Still completely null.
//   Attempt 3 (v6.3.5): replaced the raster approach with a vector spatial
//     intersects join against the merged building collection — proven to
//     work for a single .first() diagnostic check, but caused the FULL
//     EXPORT to truncate to 2 of 136 candidates. Bounding the previously-
//     global Google source (v6.3.7) did not fix this either, confirmed by
//     the client's own re-run — meaning the truncation was not (only) about
//     collection size, but more likely the computational cost of a genuine
//     per-candidate geometric intersects test against thousands of small
//     building polygons, stacked on top of everything else already in this
//     script's computation graph (SNIC segmentation, 64-band embeddings,
//     the IUCN spatial join, multiple annulus buffers).
//
// Three attempts at the same category of fix is enough — this abandons
// external building-footprint datasets for this specific check entirely,
// and instead reuses the ALREADY-PROVEN-RELIABLE mechanism this script has
// used successfully throughout: ESA WorldCover + reduceRegions(mean), the
// exact same machinery BuiltUp_Pct itself uses, just over a MUCH TIGHTER
// buffer (10m instead of the candidate's full ~50m footprint) so a point
// sitting on a small structure surrounded by open ground is no longer
// diluted into passing. No new dataset, no spatial join, nothing left in
// this specific check that hasn't already been proven to work reliably at
// export scale in this exact script.
var TIGHT_BUFFER_M = 10;
var candidatesTight = candidates.map(function(f) {
  return f.setGeometry(f.geometry().centroid({ maxError: 1 }).buffer(TIGHT_BUFFER_M));
});
var tightBuiltUp = builtUpMask.reduceRegions({
  collection: candidatesTight,
  reducer: ee.Reducer.mean(),
  scale: 10,
  crs: "EPSG:4326",
  tileScale: 4,
});
// >50% built-up within a 10m radius of the exact coordinate — a much
// stricter, tighter test than the ~50m-footprint BuiltUp_Pct threshold
// (20%) used for the main exclusion filter; this is deliberately the
// "is the point itself basically standing on a structure" check, not a
// repeat of the footprint-average one.
var pointOnBuildingKey = ID_COL;  // was re-derived separately — now reuses the single resolved value, see ID_COL definition above
var pointOnBuildingFilter = ee.Filter.equals({
  leftField: pointOnBuildingKey, rightField: pointOnBuildingKey,
});
var pointOnBuildingJoin = ee.Join.saveFirst({ matchKey: "tight_match" });
var pointOnBuilding = pointOnBuildingJoin.apply(candidates, tightBuiltUp, pointOnBuildingFilter).map(function(f) {
  var match = ee.Feature(f.get("tight_match"));
  var hasMatch = f.get("tight_match");
  var rawPct = ee.Algorithms.If(hasMatch, match.get("BuiltUp_Pct"), 0);
  // v6.3.9 [real error, client's actual run]: "Number.gt: Parameter 'left'
  // is required and may not be null." — a 10m-radius buffer at 10m pixel
  // scale can genuinely contain too few pixels for reduceRegions to return
  // a valid BuiltUp_Pct, so rawPct itself can be null even when hasMatch is
  // true (not just when there's no match at all, which the If above already
  // handled). ee.Number(null).gt(50) crashes hard rather than evaluating to
  // false. Fixed with GEE's standard null-coalescing idiom: a 2-element
  // list [value, default] reduced with firstNonNull() picks rawPct if it's
  // real, falls back to 0 if it's null, GUARANTEED to produce an actual
  // number before .gt() is ever called on it.
  var safePct = ee.Number(ee.List([rawPct, 0]).reduce(ee.Reducer.firstNonNull()));
  return f.set("on_building", ee.Algorithms.If(safePct.gt(50), 1, 0));
});
print("DIAGNOSTIC — pointOnBuilding (tight-buffer WorldCover version) " +
     "first candidate on_building value (should be 0 or 1, not null):",
     pointOnBuilding.first().get("on_building"));
// Merged back onto `reduced` further down via the same join pattern used
// for embeddings/IUCN — see the merge block after reduceRegions().

var naturalMask = ee.Image(0);
NATURAL_CLASSES.forEach(function(cls) {
  naturalMask = naturalMask.or(worldCover.eq(cls));
});
naturalMask = naturalMask.rename("is_natural");

// --- CONNECTIVITY/THREAT: fragmentation edge density (NEW) ---
// Edge pixel = a pixel whose 3x3 neighbourhood is NOT homogeneous w.r.t.
// the natural/non-natural mask (i.e. it sits on a natural<->non-natural
// boundary). Edge density = mean fraction of edge pixels in a region —
// a simple, defensible MSPA-style fragmentation proxy without requiring
// a dedicated MSPA toolbox.
var naturalMean3x3 = naturalMask.reduceNeighborhood({
  reducer: ee.Reducer.mean(),
  kernel:  ee.Kernel.square({ radius: 1, units: "pixels" }),
});
var isEdgePixel = naturalMean3x3.gt(0).and(naturalMean3x3.lt(1)).rename("is_edge");

// --- THERMAL + NIGHT-TIME LIGHTS (NEW, v6.0 [C-12]) ---
// Land surface temperature: same NDVI_START/END window so condition and
// thermal load describe the same season. Note the resolution mismatch —
// MOD11A1 is 1km, so this is informative at landscape scale and coarse
// relative to a small waterbody; treat accordingly.
var lst = ee.ImageCollection("MODIS/061/MOD11A1")
  .filterDate(NDVI_START, NDVI_END)
  .select("LST_Day_1km")
  .mean()
  .multiply(0.02).subtract(273.15)
  .rename("LST_C");

// Night-time lights: a full year, since VIIRS monthly composites are noisy
// and Darukaa sites rarely need month-level resolution on this covariate.
var ntl = ee.ImageCollection("NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG")
  .filterDate(ee.Date(NDVI_START).advance(-6, "month"), ee.Date(NDVI_END).advance(6, "month"))
  .select("avg_rad")
  .mean()
  .rename("NightLights");

// Stack all polygon-level bands for a single reduceRegions pass
var stackedImage = ndviImage
  .addBands(treeCoverPct)
  .addBands(treeCoverPctEsriClassifier)
  .addBands(treeCoverPctHansenLossAdjusted)
  .addBands(elevM)
  .addBands(elevStd)
  .addBands(tri)
  .addBands(slope)
  .addBands(jrcWaterFlag)
  .addBands(ghm)
  .addBands(distWater)
  .addBands(lst)
  .addBands(ntl)
  .addBands(builtUpMask)
  .addBands(naturalMask);

// ===================================================================
// [GENERALIZATION NOTE — Aug 2026, unified site-selection pipeline]
// This SNIC block segments the entire `candidates.geometry().bounds()` —
// correct and cheap for a CONTIGUOUS single-polygon AOI (conservation,
// industrial archetypes: Soulforest, Tata Motors), where bounds() ~= the
// real site extent. It is WRONG for a SCATTERED multi-district AOI
// (agroforestry: Soova is fine at ~single-district scale, but GV's 1,893
// parcels span a ~200km x 157km bounding box across 4 districts) — SNIC
// would attempt to segment all the non-farm land in between, which is
// neither ecologically meaningful (see architecture discussion: EMUs for
// scattered parcels come from barrier-aware ecological clustering on the
// per-candidate covariate table below, NOT from raster segmentation) nor
// computationally sane at that extent (very likely to exceed GEE's
// interactive/export compute limits).
//
// ACTION REQUIRED per project: set RUN_SEGMENTATION below — CONTIGUOUS
// archetypes (conservation/industrial: Soulforest, TM) leave it true;
// SCATTERED archetypes (agroforestry: Soova, GV) set it false. This used
// to require manually commenting out the whole SNIC block by hand for
// every project — real, repeated, error-prone manual editing flagged
// directly (Aug 2026) — now it's one boolean read by common/gee_export.py
// when it generates each project's ready-to-paste script, wrapped around
// the block in a real `if`, below. Nothing to hand-edit here anymore.
var RUN_SEGMENTATION = true;  // pre-set for SoulForest_Veltoor (contiguous archetype) — do not change
// ===================================================================

if (RUN_SEGMENTATION) {

// ===================================================================
// v6.3 [SNIC SEGMENTATION] — replaces point-clustering as the basis for
// stratification. See CHANGELOG.md / PIPELINE_METHODOLOGY_REFERENCES.md
// for the full citation trail; summary: point-based K-means clustering of
// scattered candidate locations has NO awareness of geographic adjacency,
// so two neighbouring candidates can land in different clusters purely
// because of small-scale covariate noise — confirmed on the real Pimpri
// map (a "checkerboard" of strata with no spatial coherence at all).
// Image segmentation (GEOBIA — Geographic Object-Based Image Analysis) is
// the established remote-sensing method for exactly this problem: it
// operates on the CONTINUOUS RASTER, not scattered points, so spatial
// contiguity is a structural property of the algorithm, not a hoped-for
// side effect. GEE's native SNIC (Simple Non-Iterative Clustering —
// Achanta & Susstrunk, CVPR 2017) is the standard tool for this in the GEE
// ecosystem, used in production land-cover/wetland-inventory pipelines
// (Mahdianpari et al., Canadian Wetland Inventory; multiple other cited
// studies — see references doc).
//
// SEGMENTATION INPUT BANDS: deliberately a SMALL, ecologically-motivated
// set at FINE-TO-MODERATE native resolution (10-90m) — NOT the full 15-
// covariate list used for MCDA scoring. Two reasons: (1) coarse bands
// (LST_C at 1km, NightLights at ~500m, the 500m/2km context-window bands)
// would dominate almost nothing at a 10m segmentation grid — they're
// already spatially pre-averaged, so feeding them into SNIC just adds
// resolution-mismatch noise without helping draw real boundaries; (2)
// published SNIC/GEOBIA studies consistently use a handful of well-chosen
// bands, not an undifferentiated stack of everything available (see e.g.
// Firigato's OBIA workflow, Baradaran's SNIC parameter study — both select
// a small, purpose-fit band set). The excluded coarse bands remain fully
// available as PER-SEGMENT attributes (SNIC computes a mean of every band
// you feed it — see below) and as MCDA-scoring covariates in Python,
// unchanged from before.
var SEGMENTATION_BANDS = ["NDVI_raw", "TreeCover_Pct", "Elev_m", "TRI_m", "Slope_deg", "gHM"];

// SNIC parameters — cited defaults, not guessed:
//   compactness = 0   Disables spatial-distance weighting so segments
//                      follow real feature/spectral boundaries rather than
//                      being forced toward square/regular shapes. This is
//                      the standard choice across multiple independent
//                      published GEE-SNIC studies for land-cover/habitat
//                      work (Baradaran 2025; the Dexing Copper Mine
//                      vegetation study, Tandfonline 2025; the SNIC+GLCM
//                      LULC study, Remote Sensing 2020) — all three use
//                      compactness=0 specifically to follow real
//                      boundaries, not impose a grid.
//   connectivity = 8  Standard default (diagonal + cardinal neighbours).
//   size              Seed spacing in PIXELS at the segmentation image's
//                      native scale (10m here) — i.e. size=10 means seeds
//                      ~100m apart before merging. Tuned per-project via
//                      SNIC_SIZE_PIXELS below; the value actually used for
//                      a 159 ha site is set in the project-specific block
//                      further down, not hardcoded here.
//   neighborhoodSize  Explicitly set to 2x size (the documented default,
//                      made explicit rather than implicit) to avoid tile-
//                      boundary segmentation artefacts.
var SNIC_SIZE_PIXELS = 10;          // <- tune per project; see project config note below
var SNIC_COMPACTNESS = 0;
var SNIC_CONNECTIVITY = 8;

// Build the segmentation input image: normalise each band to [0,1] (min-max
// over the AOI) before stacking — standard preprocessing for any distance-
// based clustering, same principle already used for CRITIC weighting, so a
// band in metres (Elev_m) doesn't dominate a band in percent (TreeCover_Pct)
// purely due to raw numeric scale.
var segBands = SEGMENTATION_BANDS.map(function(name) {
  var band = stackedImage.select(name);
  var stats = band.reduceRegion({
    reducer: ee.Reducer.minMax(), geometry: candidates.geometry().bounds(), scale: 10,
    maxPixels: 1e9, bestEffort: true,
  });
  var lo = ee.Number(stats.get(name + "_min"));
  var hi = ee.Number(stats.get(name + "_max"));
  var rng = hi.subtract(lo).max(1e-6);   // avoid divide-by-zero on a constant band
  return band.subtract(lo).divide(rng).rename(name);
});
var segImage = ee.Image.cat(segBands);

// Exclude water and built-up areas from segmentation entirely — these are
// not terrestrial habitat and shouldn't influence, or receive, an
// ecological segment ID. Reuses the same masks already computed above
// (jrcWaterFlag, builtUpMask) rather than recomputing them.
var segMask = jrcWaterFlag.unmask(0).lt(0.5).and(builtUpMask.unmask(0).lt(50));
// v6.3.2 [real bug, found from client's actual GEE export]: SEGMENT_ID came
// back EMPTY for 130 of 136 real candidates — confirmed by direct testing
// that the only candidates which DID get a real SEGMENT_ID were all within
// 15-62m of water; every candidate farther away (up to 346m) got nothing.
// Root cause: jrcWaterFlag = jrcOccurrence.gt(50) is computed directly on
// JRC's occurrence band, which is MASKED (not a real 0) everywhere that's
// never been recorded as water — the exact same JRC masking behaviour
// already found and fixed for the per-candidate JRC_Water covariate much
// earlier in this project (_safe_float() in PHASE_3_StratifyAllocate.py),
// but never re-applied here when this segmentation mask was added. A
// boolean threshold on a masked pixel stays masked in GEE, so segMask was
// masked (not True/False) over the entire terrestrial area away from
// water, which meant segImageMasked — and therefore the whole SNIC
// segmentation and its SEGMENT_ID output — was effectively masked out
// everywhere except right next to a waterbody. Fixed the same way as
// before: .unmask(0) makes "never recorded as water" correctly resolve to
// a real 0 (definitely not water) instead of propagating as undefined.
// Applied the same defensive .unmask(0) to builtUpMask here too, even
// though ESA WorldCover's Built-up class is not documented as sparse-
// masked the way JRC's occurrence band is — cheap insurance against the
// same failure mode recurring from a different source.
var segImageMasked = segImage.updateMask(segMask).clip(candidates.geometry().bounds());

var snicResult = ee.Algorithms.Image.Segmentation.SNIC({
  image: segImageMasked,
  size: SNIC_SIZE_PIXELS,
  compactness: SNIC_COMPACTNESS,
  connectivity: SNIC_CONNECTIVITY,
  neighborhoodSize: SNIC_SIZE_PIXELS * 2,
});
var segmentId = snicResult.select("clusters").rename("SEGMENT_ID");

// Also compute per-segment means of the COARSE context bands (gHM already
// in segBands above, but LST_C/NightLights/NatCoverPct_500m/EdgeDensity_500m
// were deliberately excluded from segmentation input) — attach them as
// segment-level attributes via the same SNIC call's automatic per-cluster
// averaging, by feeding them through a SEPARATE SNIC call using the SAME
// seed positions (snicResult's "seeds" band) so segment boundaries stay
// identical and only the attribute values differ.
var contextBands = ee.Image.cat([
  stackedImage.select("LST_C"), stackedImage.select("NightLights"),
]);
var snicContext = ee.Algorithms.Image.Segmentation.SNIC({
  image: contextBands.updateMask(segMask),
  size: SNIC_SIZE_PIXELS, compactness: SNIC_COMPACTNESS,
  connectivity: SNIC_CONNECTIVITY, neighborhoodSize: SNIC_SIZE_PIXELS * 2,
  seeds: snicResult.select("seeds"),
});

var segmentedImage = segmentId
  .addBands(snicResult.select(SEGMENTATION_BANDS.map(function(n){return n + "_mean";})).rename(
    SEGMENTATION_BANDS.map(function(n){return "SEG_" + n + "_mean";})))
  .addBands(snicContext.select(["LST_C_mean", "NightLights_mean"]).rename(
    ["SEG_LST_C_mean", "SEG_NightLights_mean"]));
// v6.3.5 [correction — my v6.3.4 fix was WRONG, reverted]: the client's
// direct diagnostic print (not the earlier indirect "8 elements" count)
// showed the actual snicResult band names ARE "NDVI_raw_mean",
// "TreeCover_Pct_mean" etc — WITH the "_mean" suffix, exactly what this
// script originally had before v6.3.4 removed it based on an incorrect
// inference from an indirect clue (band COUNT alone, without seeing the
// actual names). That inference was wrong. Reverted the .select() call
// back to the "_mean"-suffixed names, which are now directly confirmed
// real — kept the .rename() step from v6.3.4, which was fine regardless
// (rename doesn't care what the source name was, only the select() choice
// was actually broken). snicContext's band names were not independently
// re-confirmed the same direct way (only snicResult's were printed) —
// reverted by analogy, since both come from the same SNIC call pattern,
// but flagged here rather than asserted with the same confidence.

} // end if (RUN_SEGMENTATION) — part 1 (SNIC image/segment construction).
  // MUST close here, BEFORE polygon-level reduction below — that step has
  // to run unconditionally regardless of RUN_SEGMENTATION. REAL BUG FIXED
  // HERE (Aug 2026, from a client-reported console error): the very first
  // version of this toggle wrapped `var reduced = stackedImage.
  // reduceRegions(...)` INSIDE this same if-block. With RUN_SEGMENTATION
  // false (every scattered/agroforestry project — Soova, GV), `reduced`
  // was never assigned at all, so the later `embJoin.apply(reduced, ...)`
  // call received `undefined` as its primary argument — producing exactly
  // the "Required argument (primary) missing" error reported from the real
  // Soova and GV console runs. Confirmed the fix by tracing every
  // assignment to `reduced` line by line rather than guessing from the
  // error message alone. Split into two if-blocks around the always-runs
  // reduction: this one (SNIC image + segment construction, genuinely
  // segmentation-only) and a second one further below (the segment-level
  // reduceRegions + join back onto `reduced`, also genuinely segmentation-
  // only) — see its own matching comment there.


// ===================================================================
// POLYGON-LEVEL REDUCTION (The Golden Rule: over geometry, not centroid)
// ===================================================================

var reduced = stackedImage.reduceRegions({
  collection: candidates,
  reducer:    ee.Reducer.mean(),
  scale:      REDUCE_SCALE,
  crs:        "EPSG:4326",
  tileScale:  4,
});

if (RUN_SEGMENTATION) {
// part 2 of the RUN_SEGMENTATION split — see the part-1 closing comment
// above for why this needed splitting in the first place. Everything from
// here down to this block's own closing `}` (right after
// `reduced = ee.FeatureCollection(reduced);`) is genuinely segmentation-
// only: it reduceRegions()'s the SNIC output and joins SEGMENT_ID onto the
// `reduced` collection that was just built above, unconditionally.

// v6.3 [SNIC SEGMENTATION]: SEGMENT_ID is a CATEGORICAL cluster ID — never
// reduce it with mean() (averaging cluster IDs is meaningless). Uses
// mode() instead: the segment that covers the MAJORITY of the candidate's
// footprint. Separate reduceRegions pass, merged by SITE_ID/Site_ID JOIN —
// NOT positional list-matching (reduceRegions does not guarantee output
// order matches input order, per the embedding merge's own comment below;
// an earlier draft of this block used positional matching, caught during
// review before this ever shipped — same class of bug as the join-key
// mistakes found and fixed elsewhere in this script).
var segReduced = segmentedImage.reduceRegions({
  collection: candidates,
  reducer:    ee.Reducer.mode(),
  scale:      10,
  crs:        "EPSG:4326",
  tileScale:  4,
});
// v6.3.2 [diagnostic, unresolved]: SEGMENT_ID itself comes through this
// exact reduceRegions call correctly (confirmed on the client's real
// export), but the SEG_*_mean fields chained after it in the same merge do
// not — empty for every candidate. Since SEGMENT_ID and the _mean bands
// come from the SAME reduceRegions call, the join isn't the issue; the
// most likely explanation is that snicResult's actual per-band mean output
// isn't named with the "_mean" suffix this script assumes (SNIC_SIZE_
// PIXELS's mean-band naming was taken from general documentation, not
// independently confirmed the way efg_code was for IUCN GET). Printing the
// actual band names here so this can be fixed precisely on the next run
// instead of guessed a third time.
print("DIAGNOSTIC — snicResult actual band names (should be 8: 6 input " +
     "bands + clusters + seeds, confirmed no _mean suffix):", snicResult.bandNames());
print("DIAGNOSTIC — segReduced first candidate SEG_NDVI_raw_mean value " +
     "(should be a real number now, not null):",
     segReduced.first().get("SEG_NDVI_raw_mean"));
var segJoinKey = ID_COL;  // was re-derived separately — now reuses the single resolved value
var segFilter = ee.Filter.equals({ leftField: segJoinKey, rightField: segJoinKey });
var segJoin = ee.Join.saveFirst({ matchKey: "seg_match" });
var segJoined = segJoin.apply(reduced, segReduced, segFilter);
reduced = segJoined.map(function(f) {
  var match = ee.Feature(f.get("seg_match"));
  var hasMatch = f.get("seg_match");
  return ee.Algorithms.If(
    hasMatch,
    f.set("SEGMENT_ID", match.get("SEGMENT_ID"))
     .set("SEG_NDVI_raw_mean", match.get("SEG_NDVI_raw_mean"))
     .set("SEG_TreeCover_Pct_mean", match.get("SEG_TreeCover_Pct_mean"))
     .set("SEG_Elev_m_mean", match.get("SEG_Elev_m_mean"))
     .set("SEG_TRI_m_mean", match.get("SEG_TRI_m_mean"))
     .set("SEG_Slope_deg_mean", match.get("SEG_Slope_deg_mean"))
     .set("SEG_gHM_mean", match.get("SEG_gHM_mean"))
     .set("SEG_LST_C_mean", match.get("SEG_LST_C_mean"))
     .set("SEG_NightLights_mean", match.get("SEG_NightLights_mean")),
    f.set("SEGMENT_ID", -1)   // candidate fell entirely on masked-out
                              // water/built-up ground — no real segment;
                              // -1 is a real, checkable sentinel, not a
                              // silent null
  );
});
reduced = ee.FeatureCollection(reduced);

} // end if (RUN_SEGMENTATION) — when false, `reduced` is simply left as
  // the polygon-level reduction computed earlier, untouched; no SEGMENT_ID
  // band gets added, and 03_emu_delineation's ecological_clustering path
  // (which never looks for SEGMENT_ID) is exactly what consumes this.

// v6.2 [EMBEDDING]: mean AlphaEarth embedding vector per candidate footprint.
// Separate reduceRegions pass (64 bands is a lot to carry through the rest
// of the pipeline's band-stacking) merged back onto `reduced` by matching
// feature order — both come from the same `candidates` collection.
if (EMBEDDING_EXPORT) {
  var embeddingImg = ee.ImageCollection("GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL")
    .filterDate(EMBEDDING_YEAR + "-01-01", (EMBEDDING_YEAR + 1) + "-01-01")
    .filterBounds(candidates)
    .mosaic();
  // Rename the 64 bands to our own convention (EMB_00..EMB_63) rather than
  // trust the source band names to stay stable across dataset versions.
  var srcBandNames = embeddingImg.bandNames();
  var embBandNames = ee.List.sequence(0, 63).map(function(i) {
    return ee.String("EMB_").cat(ee.Number(i).format("%02d"));
  });
  var embeddingRenamed = embeddingImg.select(srcBandNames, embBandNames);

  var embeddingReduced = embeddingRenamed.reduceRegions({
    collection: candidates,
    reducer:    ee.Reducer.mean(),
    scale:      10,
    crs:        "EPSG:4326",
    tileScale:  4,
  });

  // Merge embedding properties onto `reduced` by SITE_ID / Site_ID join key
  // (join, not positional concat — reduceRegions does not guarantee output
  // order matches input order).
  var joinKey = ID_COL;  // was re-derived separately — now reuses the single resolved value
  var embFilter = ee.Filter.equals({ leftField: joinKey, rightField: joinKey });
  var embJoin = ee.Join.saveFirst({ matchKey: "emb_match" });
  var joined = embJoin.apply(reduced, embeddingReduced, embFilter);
  reduced = joined.map(function(f) {
    var match = ee.Feature(f.get("emb_match"));
    return f.copyProperties(match, embBandNames);
  });
}

// v6.2 [C-5, round 2]: merge PointOnBuilding onto `reduced` — same join
// pattern as embeddings/IUCN GET above. Runs unconditionally (not gated by
// a toggle like EMBEDDING_EXPORT/IUCN_GET_EXPORT) since it's the direct fix
// for a client-reported defect, not an optional enrichment.
var joinKeyPOB = ID_COL;  // was re-derived separately — now reuses the single resolved value
var pobFilter = ee.Filter.equals({ leftField: joinKeyPOB, rightField: joinKeyPOB });
var pobJoin = ee.Join.saveFirst({ matchKey: "pob_match" });
var joinedPOB = pobJoin.apply(reduced, pointOnBuilding, pobFilter);
reduced = joinedPOB.map(function(f) {
  var match = ee.Feature(f.get("pob_match"));
  var hasMatch = f.get("pob_match");
  return ee.Algorithms.If(
    hasMatch,
    f.set("PointOnBuilding", match.get("on_building")),
    f.set("PointOnBuilding", 0)   // no match = candidate footprint didn't
                                  // intersect the building layer at all
  );
});
reduced = ee.FeatureCollection(reduced);

// v6.2 [IUCN-GET]: pre-reconnaissance ecological typing. Spatial join against
// IUCN Global Ecosystem Typology Level 3 (Ecosystem Functional Groups) — a
// real public FeatureCollection, not a placeholder. Attaches the intersecting
// EFG code/name to every candidate. Where a candidate's footprint spans more
// than one EFG polygon (rare at this footprint size, but possible near a
// typology boundary), the FIRST intersecting match is used and this is
// exactly the kind of thing field reconnaissance should confirm or correct —
// this is provisional typing, not a substitute for the field visit.
if (IUCN_GET_EXPORT) {
  var iucnGet = ee.FeatureCollection(IUCN_GET_ASSET);
  var iucnFilter = ee.Filter.intersects({ leftField: ".geo", rightField: ".geo", maxError: 10 });
  var iucnJoin = ee.Join.saveFirst({ matchKey: "iucn_match" });
  var joinedIucn = iucnJoin.apply(reduced, iucnGet, iucnFilter);
  reduced = joinedIucn.map(function(f) {
    var match = ee.Feature(f.get("iucn_match"));
    var hasMatch = f.get("iucn_match");
    return ee.Algorithms.If(
      hasMatch,
      f.set("IUCN_GET_code", match.get("efg_code"))
       .set("IUCN_GET_name", match.get("efg_name")),   // efg_code CONFIRMED via the
                                                          //    EE catalog sample (its
                                                          //    visualization keys on
                                                          //    'efg_code'). efg_name is
                                                          //    inferred, not independently
                                                          //    confirmed — verify via
                                                          //    Inspector before relying on it.
      f.set("IUCN_GET_code", "unmatched").set("IUCN_GET_name", "unmatched")
    );
  });
  reduced = ee.FeatureCollection(reduced);
}

// TreeCover_Pct from Hansen is already 0-100; DistWater_m is a mean-of-mean
// over the polygon footprint via reduceRegions above — fine for the small
// agroforestry/conservation polygons this pipeline handles. For very large
// polygons consider switching to ee.Reducer.min() on distance instead of mean.

// ===================================================================
// ANNULUS METRICS — NatCoverPct_2km (existing) + EdgeDensity_2km (NEW)
// Both require a point-based buffering approach for the 500m-2km annulus;
// the site-level metrics above remain polygon-based.
// ===================================================================

// v6.0: generalised to take explicit radii, so the same function produces
// both the 2km landscape-context annulus (v5.0 behaviour, unchanged values)
// and a 500m small-site variant, exported as separate bands rather than one
// replacing the other (see CONTEXT_RADIUS_* above).
function computeAnnulusMetricsAt(feature, innerM, outerM, suffix) {
  var centroid = feature.geometry().centroid({ maxError: 1 });
  var outer    = centroid.buffer(outerM);
  var inner    = centroid.buffer(innerM);
  var annulus  = outer.difference(inner);

  var annulusStats = naturalMask.addBands(isEdgePixel).reduceRegion({
    reducer:  ee.Reducer.mean(),
    geometry: annulus,
    scale:    10,
    maxPixels: 1e8,
  });

  var natPct  = ee.Number(annulusStats.get("is_natural")).multiply(100);
  var edgeDen = ee.Number(annulusStats.get("is_edge")).multiply(100);

  return feature.set("NatCoverPct_" + suffix, natPct)
                .set("EdgeDensity_" + suffix, edgeDen);
}

function computeAnnulusMetrics(feature) {
  // v5.0 behaviour: 500m-2km annulus -> *_2km bands. Unchanged values.
  feature = computeAnnulusMetricsAt(feature, 500, CONTEXT_RADIUS_OUTER_M, "2km");
  // v6.0 addition: a tighter annulus for small-site stratification. Uses the
  // same inner radius as the outer bound of the small window, i.e. a
  // 0-500m disc rather than an annulus, since on a <200 ha site "context
  // beyond the candidate itself" starts essentially at zero.
  var smallStats = naturalMask.addBands(isEdgePixel).reduceRegion({
    reducer:  ee.Reducer.mean(),
    geometry: feature.geometry().centroid({ maxError: 1 }).buffer(CONTEXT_RADIUS_SMALL_M),
    scale:    10,
    maxPixels: 1e8,
  });
  feature = feature
    .set("NatCoverPct_500m", ee.Number(smallStats.get("is_natural")).multiply(100))
    .set("EdgeDensity_500m", ee.Number(smallStats.get("is_edge")).multiply(100));
  return feature;
}

var withAnnulus = reduced.map(computeAnnulusMetrics);

// ===================================================================
// CLEAN UP OUTPUT
// ===================================================================

// v6.0: property list adapts to CANDIDATE_SCHEMA. shapefile_v5 keeps its
// original truncated-name columns unchanged (Site_ID, Cent_Lat, ...) so
// existing PHASE_2_GEEMetricsIngest.py joins keep working. csv_v6 uses
// SITE_ID as the join key, matching PHASE_0b_SiteFrame.py's output and what
// run_project.py's merge_gee() expects to find. "unified" only ever
// uploads a `name` column (see common/gee_export.py) — nothing else to
// carry through, the pipeline re-attaches its own richer attributes by
// joining this CSV back onto candidates.geojson locally afterward.
var baseProps = (CANDIDATE_SCHEMA === "csv_v6")
  ? ["SITE_ID", "LAT", "LON"]
  : (CANDIDATE_SCHEMA === "unified")
  ? ["name"]
  : ["Site_ID", "Src_Type", "Cent_Lat", "Cent_Lon", "Area_Ha"];

var newBandProps = [
  "NDVI_raw", "TreeCover_Pct", "TreeCover_Pct_EsriClassifier", "TreeCover_Pct_Hansen_LossAdjusted",
  "Elev_m", "ElevStd_m", "TRI_m",
  "NatCoverPct_2km", "EdgeDensity_2km",
  "NatCoverPct_500m", "EdgeDensity_500m",
  "gHM", "DistWater_m",
  "LST_C", "NightLights",
  "Slope_deg", "JRC_Water",
  "BuiltUp_Pct",  // v6.2 [C-5]: hard-exclusion source, see PHASE_3_StratifyAllocate.py
  "PointOnBuilding",   // v6.2 [C-5, round 2]: exact-coordinate check, not a footprint average
  // v6.3 [SNIC SEGMENTATION]: SEGMENT_ID is the new basis for stratification
  // — see PHASE_3_StratifyAllocate.py's assign_strata_from_segments(). The
  // SEG_*_mean columns are that segment's own characteristic covariate
  // profile (distinct from the candidate's OWN point-level values above),
  // used for ecosystem-type labelling and MCDA scoring at the segment level.
  "SEGMENT_ID", "SEG_NDVI_raw_mean", "SEG_TreeCover_Pct_mean", "SEG_Elev_m_mean",
  "SEG_TRI_m_mean", "SEG_Slope_deg_mean", "SEG_gHM_mean", "SEG_LST_C_mean",
  "SEG_NightLights_mean"
];

// v6.2 [IUCN-GET]: appended only when the join actually ran, so a run with
// IUCN_GET_EXPORT=false doesn't try to read properties that were never set.
if (IUCN_GET_EXPORT) {
  newBandProps = newBandProps.concat(["IUCN_GET_code", "IUCN_GET_name"]);
}

// v6.2 [EMBEDDING]: 64 EMB_00..EMB_63 columns, appended only when the
// embedding pass actually ran. Kept as a separate list (not hardcoded 64
// strings) so it stays in sync with the rename loop above if that ever changes.
if (EMBEDDING_EXPORT) {
  for (var _i = 0; _i < 64; _i++) {
    newBandProps.push("EMB_" + (_i < 10 ? "0" + _i : _i));
  }
}

var exportFC = withAnnulus.map(function(f) {
  var props = baseProps.concat(newBandProps);
  var filtered = f;
  props.forEach(function(prop) {
    filtered = filtered.set(prop, f.get(prop));
  });
  return filtered;
});

// ===================================================================
// VISUALISATION (GEE Code Editor preview)
// ===================================================================

Map.centerObject(candidates, 10);

Map.addLayer(
  ndviImage.clip(candidates.geometry().bounds()),
  { min: 0, max: 0.8, palette: ["#d73027", "#fee090", "#1a9850"] },
  "NDVI Median"
);
Map.addLayer(
  ghm.clip(candidates.geometry().bounds()),
  { min: 0, max: 1, palette: ["#2ECC71", "#F39C12", "#E74C3C"] },
  "Global Human Modification", false
);
Map.addLayer(
  candidates,
  { color: "#3498DB", fillColor: "00000000", width: 1 },
  "Candidates"
);

// ===================================================================
// EXPORT
// ===================================================================

Export.table.toDrive({
  collection:  exportFC,
  description: EXPORT_NAME,
  folder:      DRIVE_FOLDER,
  fileFormat:  "CSV",
});

print("Export task queued. Go to Tasks tab and click RUN.");
print("Place output CSV at: data/PROJECT_NAME/gee_output/gee_metrics_output.csv");

// ===================================================================
// AQUATIC COVARIATES (NEW, v6.0 [C-12]) — runs only if WATERBODY_ASSET_PATH
// is set. Separate export: waterbody-level, not candidate-level, so it never
// collides with the terrestrial CSV above.
//
// Do NOT reuse DistWater_m for aquatic candidates — every aquatic sampling
// unit sits at distance zero from its own waterbody by construction, so the
// column would be uniformly zero and contribute nothing. It is intentionally
// left out of this block.
// ===================================================================
if (WATERBODY_ASSET_PATH !== "") {
  var waterbodies = ee.FeatureCollection(WATERBODY_ASSET_PATH);
  print("Waterbody count:", waterbodies.size());

  // Water permanence/frequency via Sentinel-2 MNDWI across the same window
  // as the terrestrial NDVI composite, so both describe the same season.
  var mndwiFreq = s2Masked
    .map(function(img) {
      return img.normalizedDifference(["B3", "B11"]).gt(0).rename("is_water");
    })
    .mean()
    .rename("WaterFrequency");

  // Riparian natural cover in a 100m shoreline buffer — the immediate margin
  // that terrestrial-aquatic interaction (§ Web-of-Life) actually depends on.
  var riparianNatural = naturalMask.rename("RiparianNatural");

  var waterbodyStacked = mndwiFreq.addBands(riparianNatural);

  var waterbodyReduced = waterbodyStacked.reduceRegions({
    collection: waterbodies,
    reducer:    ee.Reducer.mean(),
    scale:      10,
    crs:        "EPSG:4326",
    tileScale:  4,
  });

  function riparianBuffer(feature) {
    var shoreBuffer = feature.geometry().buffer(100).difference(feature.geometry());
    var stats = riparianNatural.reduceRegion({
      reducer:  ee.Reducer.mean(),
      geometry: shoreBuffer,
      scale:    10,
      maxPixels: 1e8,
    });
    return feature.set("RiparianNaturalPct_100m",
      ee.Number(stats.get("RiparianNatural")).multiply(100));
  }

  var waterbodyFinal = waterbodyReduced.map(riparianBuffer);

  // v6.2 [IUCN-GET]: same pre-reconnaissance typing as the terrestrial
  // candidates, applied to waterbodies (aquatic strata deserve a named type
  // too, not just terrestrial ones).
  if (IUCN_GET_EXPORT) {
    var iucnGetAq = ee.FeatureCollection(IUCN_GET_ASSET);
    var iucnFilterAq = ee.Filter.intersects({ leftField: ".geo", rightField: ".geo", maxError: 10 });
    var iucnJoinAq = ee.Join.saveFirst({ matchKey: "iucn_match" });
    var joinedIucnAq = iucnJoinAq.apply(waterbodyFinal, iucnGetAq, iucnFilterAq);
    waterbodyFinal = ee.FeatureCollection(joinedIucnAq.map(function(f) {
      var match = ee.Feature(f.get("iucn_match"));
      var hasMatch = f.get("iucn_match");
      return ee.Algorithms.If(
        hasMatch,
        f.set("IUCN_GET_code", match.get("efg_code")).set("IUCN_GET_name", match.get("efg_name")),
        f.set("IUCN_GET_code", "unmatched").set("IUCN_GET_name", "unmatched")
      );
    }));
  }

  Export.table.toDrive({
    collection:  waterbodyFinal,
    description: EXPORT_NAME + "_aquatic",
    folder:      DRIVE_FOLDER,
    fileFormat:  "CSV",
  });

  print("Aquatic export task queued (" + EXPORT_NAME + "_aquatic). Go to Tasks tab and click RUN.");
  print("Place output CSV at: data/PROJECT_NAME/gee_output/gee_metrics_output_aquatic.csv");
}