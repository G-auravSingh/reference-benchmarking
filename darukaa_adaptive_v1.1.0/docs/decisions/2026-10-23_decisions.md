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

**D-23-9. Pressure scoring (P4).**
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

## Access

- Push access was granted on 23 Oct. The git proxy still refused the push, because the repo is not in this session's authorised source set.
- Commits are kept locally until the push works.
