# Phase 5: the general assessment pipeline on the frozen v0.2.8 engine

Branch `v0.2.9-pipeline`, cut from tag `v0.2.8-contract-frozen` (3d01100). The tag is untouched. The engine is untouched (see "Engine identity").

## What it is
```
manifest (tile_manifest.json)  ->  ZoneSpec(label, tile, REALM)            manifest.py
   -> frozen engine, once per zone (assess.run_smoke_test -> assess_zone)  engine_pipeline.py   [site extraction, applicability, reference, benchmark, score]
   -> per-zone audit trail  <label>_audit.{json,csv,md}                    (the engine's own writer, as in the standalone runs)
   -> status policy, per-realm worst-zone aggregation, coverage, headline  engine_report.py
   -> <project>_project.{json,csv,html}                                    engine_html.py via html_report.write_html
```
`python run_project_from_manifest.py --project <name>` runs it (default `--engine v0.2.8`). `--engine legacy` still runs the original v0.2.7 pipeline, unchanged.

## Manifest (project-agnostic)
`tile_realms` (list, `{label: realm}` or a single `realm`) declares each zone `terrestrial` or `aquatic`; `companions: [project_name, ...]` merges other manifests. Both are
DECLARATIONS. Legacy inference (project name contains "aquatic"; an existing `<name>_Aquatic` manifest) remains only as a **warned fallback**, recorded per zone
(`realm_source`, `companion_source`), and can be disabled. A realm is never inferred from geometry. No module contains a project name (a test enforces it).

## Status policy (never reinterpreted)
scored -> aggregate | contextual_only -> context | screening_only -> screening | not_applicable, applicable_but_no_site_value, applicable_but_no_reference,
reference_available_but_not_scoreable, suppressed_for_stability, pending_methodology -> excluded (status and reason kept, shown in the report).
An unknown status, or a `scored` row without a score, raises. Absent values are `None` in JSON, an empty cell in CSV, "n/a" in HTML: never 0, never averaged, never ranked.

## Score vs measurement
`score` (0-1) is the site **relative to its reference population** (0.5 = at reference, higher = better, direction already encoded by the engine). It is not a percentage of
condition: 1.00 means the site ranks at or above every reference unit. The raw measurement (`site_value`, `site_unit`) and the reference median are separate columns and
fields. The report never formats a score as a percentage (son_score's 1-100 % display strings are stripped).

## Aggregation, per realm
Project-realm signal per indicator = the worst scored zone's engine `score` (non-compensatory). `engine_profile.build_profile` (pipeline layer) takes the engine's `score` as is and
never normalises it (a percentile fed through the old z-score logistic would be silently wrong: 0.745 would become 0.592); it uses the unchanged roll-up helpers of `scoring.py`, which is
part of the engine closure and byte-identical to the frozen tag. A test proves it agrees exactly with the legacy `build_site_profile` wherever the two are comparable. Terrestrial and aquatic
zones are never pooled: one profile and one headline per realm, no blended headline. Area-weighted figures are labelled context.

## Headline and coverage
The existing profile-first headline (condition roll-up, pressure kept separate, pillar confidence) is computed only from `scored` rows; with no scoreable condition evidence
there is no headline. The legacy confidence flag counts **pillars**; because a worst-zone headline built from one zone says little about the rest, every realm headline also carries
**per-pillar zone coverage** and a caveat (e.g. C3 fauna evidenced in 1 of 9 zones, 60 % of the realm's area).

## Engine identity and provenance
**Executable engine closure** (`engine_identity.ENGINE_CLOSURE_FILES`, 19 files): the explicit import closure of `assess.py` (AST, including function-level imports) minus modules that only
record or render and modules added after the freeze. It contains every module that determines a site value, reference, applicability, benchmark, score or status: `__init__`, `assess`, `benchmarking`,
`config`, `constructs`, `contracts`, `ecoregion`, `estimators`, `indicator_contract`, `indicators/__init__`, `pipeline`, `reference`, `reference_builders_ee`, `registry`, `scoring`, `site_loader`, `statistics`,
`support`, `tiling`. `scoring.py` is in it because `benchmarking.py` computes the engine score with `scoring.normalize`; `reference.py` because `assess.py` builds every Dynamic World stratum and HMI
threshold through `ReferenceSelector`; `pipeline.py` because `assess.load_zone` loads a tile through it. `reference_builders.py` is not imported by `assess` and is not in the closure.
**Executed but not result-determining** (`EXECUTED_NON_RESULT_FILES`): `provenance`, `report`, `html_report`, `son_score`. `provenance.py` and `html_report.py` differ from the tag in Phase 5 (they record and render).
`FROZEN_ENGINE_CLOSURE_SHA256` (`56b57ebe...`) and the per-file hashes are computed from git at the frozen tag; tests fail if any closure file differs from the tag, if the closure stops matching the import
closure of `assess.py`, or if `FROZEN_ENGINE_CLOSURE_SHA256` is not the tag's value. (The first Phase 5 fingerprint covered 12 files, omitted `reference.py`, `pipeline.py`, `registry.py`, `scoring.py`, `estimators.py`,
`contracts.py` and `statistics.py`, and included `reference_builders.py`, which is never imported; `scoring.py` had also been modified. Both corrected; the frozen engine itself was never changed.)
The engine-read configuration is fingerprinted separately (canonical numbers; only the raster keys the engine reads). `config.yaml` differs from the frozen notebook config in five fields (stray space in
`gee_project`, `raster_paths`, `output_dir`, `output_format`, `archetype`); none is read by the engine's behaviour, so the engine-config fingerprint is identical (a test pins this). Every audit and report
records both; a non-frozen engine is always refused, and strict mode (default) also refuses a dirty or moved checkout or an engine-config difference.

## Parity with the standalone Tata results (offline) and its limit
Established by: (1) the 19 engine-closure files byte-identical to the tag; (2) the engine is called through the same entry point (`run_smoke_test`) with the same zone, realm, config and order;
(3) the pipeline-owned path (manifest -> engine call -> audit files -> adapter -> aggregation -> headline -> CSV/HTML) replayed with the engine returning exactly the standalone rows:
all 690 rows reproduce (strings, ints, None identical; floats to 1e-12, serialisation only), aggregation re-derived independently, headlines pinned. Mutation-tested: n/a->0,
re-normalising the score, best-zone-instead-of-worst are each caught. **Not established offline:** the engine's own arithmetic on Earth Engine data (the audits do not keep reference
arrays). That is the live integration test.

## Known issues carried forward (frozen engine; not changed here)
Lake_Sharma `sabf` is `applicable_but_no_site_value / site_value_not_computed` (floor evaluated on the 10 m evidence, built on the 20 m grid); `suppressed_for_stability` has never
occurred in real Tata rows (rendering is tested on synthetic rows); forest-loss reference availability on external forest zones (see SCORING_ARCHITECTURE section 13.4).

## Known reproducibility issue found by the first live run (open; see the live-validation notes)
`reference.py` builds the Dynamic World land-cover stratum from `filterDate(today - 730 days, today)` with `today = date.today()`. Every reference whose contract population is
`least_disturbed_stratum` or `regional_stratum_unfiltered` (ghm, chm, ndvi, bii, forest_loss_rate, cpland) therefore depends on the date the code runs, and the audits do not record that date.
The live four-zone run differed from the standalone audits on exactly the indicators with such a population. Whether the date alone explains it is being tested (diagnostics D1/D2 in the live notebook);
no methodology change has been made.
