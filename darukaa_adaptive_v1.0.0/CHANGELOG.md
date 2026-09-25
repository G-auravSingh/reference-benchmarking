# Changelog

## 1.1.0 — adaptive lake production pass

- Added explicit date-driven Year-0 baseline support (default: 2025-08-01 through 2026-08-31).
- Kept separate historical 2018–2026 trend/context window.
- Added canonical configuration validation with backward support for the earlier `gEE` key.
- Added native aquatic indicator contracts and retained the frozen 44-indicator legacy crosswalk.
- Added metric-level Tier-1/Tier-2 benchmark model with explicit reference provenance.
- Added optional reference KML and reference CSV pathways for Tier-1 benchmarks.
- Added uncertainty-ready metric statistics and richer metric provenance fields.
- Added gated 1–5 metric concern scoring, pillar aggregation and legacy-compatible 0–10 overall scoring.
- Added formal pillar coverage and score-eligibility rules so missing evidence cannot silently alter the composite.
- Added readiness reporting for temporal, reference, threshold and field-validation status.
- Added reusable monthly/annual period helpers.
- Updated the Nandoshi Colab notebook for clean cell-by-cell execution and repeatable GitHub pull/install behavior.
- Added output registry/crosswalk tables and expanded assessment manifest provenance.
- Added documentation describing the reference and scoring model.
- Legacy package content remains unchanged.
