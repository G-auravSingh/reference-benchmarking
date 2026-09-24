# Output File Guide

Every file a pipeline run produces, what it's for, and who it's for. When
in doubt about whether something is safe to hand to a client, check here
first.

## Client-facing (safe to share as-is)

| File | Location | What it is |
|---|---|---|
| `<PROJECT>_site_selection_report.html` | `outputs/06_reporting/` | The main client deliverable — overview, EMU summary, deployment schedule, covariate profile. Open in any browser. |
| `field_map.html` | `outputs/06_reporting/` | Interactive map — EMU boundaries, position pool, deployment cycles. The fastest way for anyone (client, field team) to orient on the design. Open in any browser, works offline once downloaded. |
| `deployment_schedule.csv` / `.xlsx` | `outputs/04_deployment_planning/` | Field-ready schedule with real calendar dates (set via each project's `project_start_date` config) — which position each device visits each cycle. Hand this directly to the field team. |
| `stratum_profile.csv` | `outputs/05_metrics_rollup/` | What each EMU IS, in covariate terms — one row per EMU, real median values across all 15 covariates. Matches the equivalent Tata Motors deliverable. |
| `soil_chemistry_points.geojson` | `outputs/06_reporting/` | Where a project has a real, one-time soil chemistry sampling design (currently Soulforest only — see `<PROJECT>/build_soil_chemistry_points.py`) — real, farthest-point-sampled corner + centre coordinates per EMU. Rendered as its own toggle-able layer on `field_map.html`. |

## Internal / working files (not for clients without review)

| File | Location | What it is | Why not client-ready |
|---|---|---|---|
| `candidates.geojson`, `candidate_grid.geojson` | `outputs/01_ingestion/` | Raw parsed candidate set | Pre-covariate, pre-EMU — an intermediate working file, not a finding |
| `ingestion_report.json` | `outputs/01_ingestion/` | Ingestion diagnostics (geometry issues, attribute coverage) | Technical QA record |
| `candidates_with_covariates.geojson` | `outputs/02_covariates/` | Per-candidate satellite covariate values | Raw data, not yet aggregated to an EMU-level finding |
| `emus.geojson`, `candidates_with_emu.geojson` | `outputs/03_emu_delineation/` | EMU geometry and membership | Feeds the report/map; the report is the client-ready summary of this |
| `emu_delineation_report.json` | `outputs/03_emu_delineation/` | Clustering/segmentation diagnostics (silhouette scores, MMU search trace) | Technical audit trail — genuinely useful if a reviewer asks "how was this number reached," not a first-read document |
| `position_pool.geojson`, `position_scoring_report.json` | `outputs/03b_position_scoring/` | Per-candidate typicality ranking | Feeds the field map; CRITIC weights themselves are worth surfacing to a technical reviewer, not a general client read |
| `deployment_schedule.json` | `outputs/04_deployment_planning/` | Machine-readable schedule | The report's deployment table is the client-facing rendering of this |
| `metrics_rollup_report.json`, `emu_reference_handoff.geojson` | `outputs/05_metrics_rollup/` | Covariate distribution stats, reference-pipeline handoff schema | The report's covariate table is the client-facing rendering; the handoff file is for the downstream `darukaa_reference` pipeline, not a client |
| `tile_manifest.json`, `tiles/*.geojson` | `outputs/07_reference_handoff/` | One real GeoJSON tile per EMU, for direct use by `darukaa_reference`'s `run_multi_tile_project` | Internal handoff to a different pipeline, not a client artefact |
| `historical/crosswalk_report.json` | `<PROJECT>/historical/` (Tata Motors only) | Every real Phase 01 field position (13-27 Aug 2026) spatially joined against the corrected boundary/exclusion/zone structure | Internal audit trail for reconciling already-collected data with the redesigned zones; feeds Week 1 of `field_map.html`, not a standalone deliverable |

## Never shared externally

| File | Location | Why |
|---|---|---|
| `GEE_RUN_INSTRUCTIONS.md`, `*_ready_to_run.js`, `*_gee_upload.zip`, `*_waterbodies.zip` | `gee_output/` | Internal tooling for running the manual GEE step — meaningless and potentially confusing outside the team |
| `config.yaml` | project root | Internal configuration — contains no client-sensitive data but isn't a deliverable |

## A note on trust

Every JSON report file's `warnings` field is where this pipeline puts
anything it isn't fully confident about — a provisional Tier-1 (no
satellite data yet) result, a spatial-compactness tradeoff, an unmatched
GEE row count. Before sharing a report or field map externally, check that
project's `warnings` fields aren't flagging something that should be
resolved first (e.g. "PROVISIONAL RUN" almost always means: don't ship
this yet, re-run once real GEE data lands).
