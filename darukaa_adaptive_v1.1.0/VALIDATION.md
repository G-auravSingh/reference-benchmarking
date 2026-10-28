# Validation ladder and status

Each rung must pass before the next starts. The evidence levels used below are:

- static reading
- unit tests
- mocks
- real Earth Engine (EE) run
- end-to-end Colab run

| Rung | What | Status (28 Oct 2026) |
|---|---|---|
| R1 Offline | Unit and mocked end-to-end tests, plus an independent review of the EE code (10 findings fixed) | **Pass**: 93 tests, Python 3.13 (unit tests and mocks only) |
| CR1 Probe | Read-only EE probe. Notebook section 4; send back `probe_results.json` | **Done** (24 Oct, live EE, commit 80f1ce38). See `validation/R2_review_2026-10-24.md` |
| R2a Controls | Forest, cropland, built-up and small-forest polygons with pre-registered expectations (`validation/`). Notebook section 6; send back `R2_controls_bundle.zip` | **Run 3** (26 Oct, commit 157d84b8): 30 PASS, 0 MISS, 2 NO_DATA. The 2 NO_DATA are cropland and built-up P4, withheld by design under D-26-1 (`reference_insufficient`). **Passed**, with that documented reason. See `validation/R2b_Karpa_review_2026-10-26.md` |
| R2b Single real polygon | Corbett Karpa (151 ha) | **Run 1** (26 Oct): ran end to end. Three layer errors fixed. **Run 2** (27 Oct, commit 1bfc37a7): new report confirmed (F-2 closed). F-1 diagnosed (source error on the small forest; stale epoch at Karpa), with P-27-4/P-27-5 approved and implemented as D-28-1 (needs a live run). Birds' Red List field confirmed |
| R3 Separated polygons | Corbett: 4 sites, 1–30 km apart | Pending |
| R4 Adjacent, fragmented EMUs | Tata, 9 EMUs inside a 126.7 ha boundary | Pending |
| R5 Other project types | SoulForest, FCF GV, FCF Soova; aquatic once the design exists | Pending |

## Questions the probe must answer before scores are read

1. Do these assets load, and what are their band names?
   - ForTy
   - SBTN v1.1
   - Meta canopy height
   - GLAD forest height
   - JRC GFC2020
   - GRIP4
   - the Darukaa FLII, KBA and IUCN assets
2. Which BII years exist?
3. How many hectares of Hansen year-2000 forest baseline are there at 10% and at 30% canopy?
4. What do all four EII bands read, and how many pixels support each unit?
5. For gHM: compare 90 m with the old 1,000 m extraction.
6. For the natural mask: what are the means and strata histogram, and how many Dynamic World images fall in the window?
