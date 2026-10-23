# Phase 1 decisions (approved 16 Oct 2026, re-verified 23 Oct 2026)

These decisions were approved on 16 Oct from the Phase 1 audit of commit 43bd210 [DARUKAA]. They were re-verified on 23 Oct by static reading and offline tests at 88a23d3. The package code is identical to 43bd210 at that commit.

The re-verification used two sources:
- the Tata run outputs of 2026-10-11 (an end-to-end Colab run at 43bd210);
- the Nature Positive documents [STD].

**Status codes:**
- `OPEN`: approved but not implemented.
- `MODIFIED`: changed on 23 Oct; see the note on that decision.
- `SUPERSEDED`: replaced by a later decision.
- `DONE <commit>`: implemented in that commit.

| # | Finding | Approved change (16 Oct) | Re-verification 23 Oct | Status |
|---|---|---|---|---|
| 1 | C1 | EII parent SCORED in P2. BII SCORED in P3. EII bands CONTEXTUAL. EII gate: asset and band present, value finite in 0–1, at least 1 valid pixel, pixel and area ratio recorded, `context_scale` when the EMU is smaller than a pixel. BII gate the same, plus the year read is recorded. | Confirmed in code: the runtime role table has `eii`=SCORED and `bii`=CONTEXTUAL. In the Tata run, EII was 0.000 in all 9 EMUs. **Modified by D-23-3:** BII moves to P2 (composition, labelled preparatory and pressure-modelled). EII stays a validation candidate until the EE probe. The pixel gate is replaced by decision 5 (D-23-7). | MODIFIED |
| 2 | H1 | P3 may qualify on a single metric (BII). | P3 is restructured to "Species" (D-23-3, D-23-4). | SUPERSEDED by D-23-3/4 |
| 3 | C2 | `forest_loss_rate` measured as % of the year-2000 forest baseline lost per year, using: 10% canopy; trailing 5 full years; the same function for site and reference; `not_applicable_no_forest_baseline` below 1 ha; `low_baseline_flag` computed. | Confirmed in code: the current value is cumulative hectares for 2001–2025 at 30% canopy, and `low_baseline_flag` is hard-coded `False`. | OPEN |
| 4 | C3 | Lower-is-better score = 100 × (1 − clamp((obs − ref)/(worst − ref), 0, 1)), with worst = p95 of the reference population (falling back to the registry maximum). No floor. Subdimensions scoring 0 are flagged. The old ratio is kept as a diagnostic. | Confirmed in code (`reference_condition.reference_attainment`). Reaffirmed for P4 by D-23-9. | OPEN |
| 5 | H3 | Coarse metrics get an EMU-plus-buffer context window covering at least 4 native pixels. Site and reference use the same scale. Status `scored_context_scale`. | Confirmed in code. **Extended by D-23-7:** applies to all coarse layers, including EII and BII. Under D-23-8, coarse layers are measured at site level, not per EMU. | MODIFIED |
| 6 | Fauna | `require_fauna_for_condition = False`. | Confirmed in code: the default is `True`. | OPEN |
| 7 | H6 | 80% coverage gate dropped. EMU completeness counts shown beside the headline. | **Refined by D-23-6:** every project number states its contributing EMU count and area share. Headline basis changes under D-23-8 and D-23-10. | MODIFIED |
| 8 | H2 | Dynamic World (DW) class matching kept for vegetation condition. All P4 metrics use one population, `pressure_pop`. | Confirmed in code: `built_fraction` uses the DW class-matched population. | OPEN |
| 9 | H5 | One baseline window, 2025-08-01 to 2026-08-31. Annual layers use the latest year at or before the window end, with the gap recorded. Per-metric effective periods. | Confirmed in code: the 2026-10-11 run records 2025-08-01:2026-09-01 for all 27 metrics. **Note:** the extent baseline year is 2020 (D-23-11), separate from the assessment window. | OPEN |
| 10 | H4 | Check the GHM native scale, then use the same image construction for site and reference. | Confirmed in code: extraction scale 1000 and `.first()` without `filterBounds`. | OPEN (needs EE probe) |
| 11 | H7 | Project-boundary input dropped; area = EMU footprint. Unconditional flag removed. Blanket `except` narrowed. | **Reversed by D-23-8:** the site boundary (`aoi_boundary`) becomes an input. The unconditional flag is still removed, and the blanket `except` is still narrowed. | SUPERSEDED in part by D-23-8 |
| 12 | M1–M7 | Exact percentile keys; `value_range` as a REVIEW flag; `cpland` no_coverage outside India; loud registry import; KML holes and multi-geometries; CRS and bounds validation; `project_id` from the manifest; handoff validator called or removed; real "PASS"; four-layer readiness; explicit reference-engine construction. | Confirmed in code. Correction: the handoff validator is *imported* in notebook cell 10 but never called. | OPEN |
| 13 | M8, L1 | Aquatic changes wait for detail. Cleanup deferred. | Cleanup is brought forward by D-23-2 (legacy pruning). | OPEN |
| 14 | Process | Git identity Gaurav Singh. Colab outputs go to a `validation-runs/` branch. | Unchanged. | OPEN |
