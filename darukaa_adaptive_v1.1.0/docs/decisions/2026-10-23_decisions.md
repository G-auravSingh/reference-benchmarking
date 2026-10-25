# Decisions of 23 Oct 2026 (approved by Gaurav)

Evidence base:
- Static reading of commit 88a23d3.
- 101 offline tests.
- Offline loads of the four Site Selection handoffs.
- The Tata run of 2026-10-11 (end-to-end Colab, commit 43bd210).
- The Nature Positive documents [STD], all read in full. Image-only tables could not be read: TOR Tables 6.1–6.6, Guidance Appendix B, and the Framework graphic on p.15.

## Method and process

**D-23-1. Working method approved, with amendments A1–A10.**
- The method is in the project doc `claude/Adaptive_v1.1.0_Method_2026-10-23.md`.
- Every metric is re-verified against its dataset and the literature (A3).
- The pipeline must reach a working first draft before Colab testing starts (A4).
- In Colab, every metric that *can* be scored is ON by default (A2). The selection cell shows each metric's recommended role and the reason for it.
- Validity gates still apply; a metric that fails them is never scored.
- Overrides of the recommended role are recorded in the outputs and in the report.

**D-23-2. `legacy_reference/` is pruned and merged.**
- Only code reachable from the active registry metrics is kept and moved into the main package.
- Each moved extractor is verified before it moves.
- Nothing is copied from the v0.x sibling packages, which stay untouched.
- Evidence: an AST call graph from the 26 active metrics. It reaches 50 of the 101 functions in `indicators/__init__.py`. The 12 other modules (about 5,100 lines) are never imported.

**D-23-12. Naming.** "Corbett" and "North Shahdol (TCF)" are the same project; TCF is The Corbett Foundation. Its sites are:
- Masira, 100.72 ha
- Pipri, 135.11 ha
- Karpa, 151.09 ha
- Amanar, 15.42 ha

## Pillars and metrics

**D-23-3. Hybrid pillar structure aligned to the Nature Positive indicators [STD].**

| Pillar | Basis |
|---|---|
| P1 Ecosystem extent | Nature Positive indicator: ecosystem extent |
| P2 Ecosystem condition | Nature Positive indicator: ecosystem condition; natural and semi-natural pixels only |
| P3 Species | Nature Positive indicators: extinction risk and populations |
| P4 Pressure | TNFD drivers and pressures; outside the Nature Positive set |

- BII moves to P2 as a composition metric. It is labelled preparatory because it is modelled from pressure data, and the Guidance (p.20) allows that only at preparatory level.
- Each pillar should carry several scored metrics plus contextual and screening metrics. More scorable metrics will be added over time.

**D-23-4. P3 coverage.**
- P3 is scored only where a validated dataset exists.
- Otherwise it is reported as "not covered", with the reason, and its contextual and in-situ metrics are shown. This is "comply or explain" (TOR p.83).

**D-23-5. Natural or managed split, per pixel.**
- Within each assessment unit, condition is computed on natural and semi-natural pixels only. This follows Guidance pp.14 and 20 and TOR p.49 [STD].
- Managed land gets a separate managed-land result, labelled as such.
- Client zone labels are kept as declared ecosystem types and checked against land cover. Mismatches are flagged.

**D-23-6. Area-share label.**
- Every project-level number states how many EMUs it comes from and what share of the area they cover.
- Nothing is withheld because of this label.

**D-23-7. Coarse layers.**
- Decision 5 of 16 Oct (the 4-native-pixel context window) applies to every coarse layer, including EII and BII.
- It replaces the "at least 1 pixel" gate from decision 1 of 16 Oct.

## Assessment units, references and scoring

**D-23-8. Nested assessment units: site plus EMUs.**
- **Site.**
  - The site is the full project boundary: the Site Selection `aoi_boundary.geojson`, or the union of the polygons when no boundary exists.
  - Built-up land and water are classified, not excluded.
  - Measured at site level: extent and natural/managed share, gross loss and gain, pressure, species, coarse layers, and the project headline.
- **EMU.**
  - EMUs are management sub-units (Guidance Box 2, p.9 [STD]).
  - Measured per EMU: 10 m condition metrics on natural pixels, plus the managed-land result.
  - Coarse layers are not repeated per EMU.
- **References.**
  - One reference is built per project and ecosystem type.
  - It excludes the whole site plus a buffer.
- **Separated polygons.**
  - Polygons far apart from each other each form their own site. Example: Corbett, where the sites are 1–30 km apart.
  - The project rolls up across sites.
- **Boundary evidence.**
  - Tata: the AOI is 126.7 ha, the EMUs 67 ha.
  - SoulForest: the AOI is 44.3 ha, the EMUs 41 ha.
- This reverses decision 11 of 16 Oct.

**D-23-9. Pressure scoring (P4).** *Superseded on 25 Oct by D-25-1. The P4 reference is now low-pressure blocks; the all-region comparison is kept as context.*
- P4 is scored 0–100 against a regional reference: same ecoregion, all land, no human-modification filter.
- The scoring function is the bounded one from decision 4 of 16 Oct. A site at or below the least-pressured reference level scores 100; a site at the regional p95 scores 0.
- The native value and a published absolute class (where one exists) are shown beside the score.

**D-23-10. Condition headline.**
- The headline is P1 + P2, and adds P3 when P3 is scored.
- It is labelled with the pillars it uses.
- This replaces `min_condition_pillars = 3`.

**D-23-11. Baselines.**
- The extent and condition change baseline is 2020 (Guidance p.10 [STD]).
- The assessment window stays 2025-08-01 to 2026-08-31 (decision 9 of 16 Oct).
- Each metric records the years it actually used.

## Catalogue and references

**D-23-13. Metric catalogue v1 approved, with Gaurav's amendments C1–C10.** The full specification is `docs/methodology/metric_catalogue_v1.md`. Its main points:
- **Natural mask.** Built from Nature Trace ForTy 2020 (10 m) and SBTN Natural Lands v1.1 (30 m). Dynamic World is used only to detect change.
- **Habitat health.** Rebuilt as Plan Vivo PV Nature Pillar 4 (SBI). This corrects the 23 Oct draft, which misdescribed `habitat_health`.
- **FLII.** Kept for forest pixels only.
- **EII.**
  - The functional component is scored.
  - The parent index and the structural component are contextual: structural is built from gHM, which is a pressure layer.
  - The compositional component is diagnostic, because it duplicates BII.
- **MSA.** GLOBIO4 2015, contextual.
- **Scale.** The finest available source is used for each metric (for example Sentinel-2 LAI, Landsat land-surface temperature, 1 m canopy height).
- **Extraction rules.** No `bestEffort`. Values are coverage-weighted. Support counts as covered-pixel equivalents.
- **Licence removals.** WDPA, KBA, BirdLife, IUCN, STAR and LIFE are removed.
- **P3 coverage.** P3 has no scored metric; only screening metrics from GBIF CC0/CC-BY records and India's WPA 2022 schedules.
- **New open metrics:** roads (GRIP4), fire, forest disturbance alerts, population, JRC surface water, GEDI, GLAD forest height.

**D-23-14. Approach 2 reference pool approved** for condition, and Approach 4 for pressure and landscape context. It must work for every project type. R and the minimum stratum size are set from probe evidence.

## Access and commit identity

**D-23-15. Commits stay authored as Gaurav Singh.**
- Gaurav reconfirmed this on 23 Oct.
- An automated session check asked for re-authoring to a Claude identity so that GitHub shows commits as Verified. This was declined because the user's rule takes precedence.
- Commits are unsigned, so GitHub shows them as Unverified.
- Gaurav supplied a time-limited PAT on 23 Oct to push. It is not stored in any file or in the git config, and Gaurav will revoke it.

## Later on 23 Oct

**D-23-16. KBA and protected-area overlap stay in the catalogue.** They are screening metrics. Their commercial-licence terms are recorded but set aside for now, per Gaurav.

**D-23-17. Aquatic modules removed from the active package.** `water.py`, `metrics.py` and the aquatic profiles were taken out pending the aquatic design. Their last version is commit 43bd210, kept as evidence for that redesign.

**D-23-18. The human disturbance index (HDI) stays retired.** HDI was built as 1 minus the distance to Dynamic World built-up land, capped at 1.5 km. The 1.5 km decay was arbitrary, and the index overlapped gHM and the built-up share.
- A proposed successor is in the catalogue as `built_up_within_1km_pct`: the share of built land in a 1 km ring around the site.
- Its suggested role is CONTEXTUAL.
- **Status: proposed.** It is excluded from runs until approved.
