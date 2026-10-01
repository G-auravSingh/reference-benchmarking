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
Project-realm signal per indicator = the worst scored zone's engine `score` (non-compensatory). `scoring.build_site_profile` now accepts the engine's `score` as is
(a percentile fed through the old z-score logistic would be silently wrong: 0.745 would become 0.592); legacy callers are unchanged. Terrestrial and aquatic zones are never
pooled: one profile and one headline per realm, no blended headline. Area-weighted figures are labelled context.

## Headline and coverage
The existing profile-first headline (condition roll-up, pressure kept separate, pillar confidence) is computed only from `scored` rows; with no scoreable condition evidence
there is no headline. The legacy confidence flag counts **pillars**; because a worst-zone headline built from one zone says little about the rest, every realm headline also carries
**per-pillar zone coverage** and a caveat (e.g. C3 fauna evidenced in 1 of 9 zones, 60 % of the realm's area).

## Engine identity and provenance
`engine_identity.py`: SHA-256 over the 12 engine modules (`4ec83137...`, computed from git at the tag) and over the engine-read configuration only (canonical numbers). Every audit and
report records both; a non-frozen engine is always refused, and strict mode (default) also refuses a dirty or moved checkout or an engine-config difference.
`config.yaml` differs from the frozen notebook config in five fields (stray space in `gee_project`, `raster_paths`, `output_dir`, `output_format`, `archetype`); none is read by the
engine's behaviour, so the engine-config fingerprint is identical (a test pins this).

## Parity with the standalone Tata results (offline) and its limit
Established by: (1) engine files byte-identical to the tag; (2) the engine is called through the same entry point (`run_smoke_test`) with the same zone, realm, config and order;
(3) the pipeline-owned path (manifest -> engine call -> audit files -> adapter -> aggregation -> headline -> CSV/HTML) replayed with the engine returning exactly the standalone rows:
all 690 rows reproduce (strings, ints, None identical; floats to 1e-12, serialisation only), aggregation re-derived independently, headlines pinned. Mutation-tested: n/a->0,
re-normalising the score, best-zone-instead-of-worst are each caught. **Not established offline:** the engine's own arithmetic on Earth Engine data (the audits do not keep reference
arrays). That is the live integration test.

## Known issues carried forward (frozen engine; not changed here)
Lake_Sharma `sabf` is `applicable_but_no_site_value / site_value_not_computed` (floor evaluated on the 10 m evidence, built on the 20 m grid); `suppressed_for_stability` has never
occurred in real Tata rows (rendering is tested on synthetic rows); forest-loss reference availability on external forest zones (see SCORING_ARCHITECTURE section 13.4).
