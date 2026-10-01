# Release Hardening Notes — 2026-09-30 to 2026-10-01

This document records the hardening work that preceded the complete `darukaa_adaptive_v1.1.0` release.

## Changes carried into v1.1.0

1. Fixed duplicate/ambiguous aquatic seasonal-month handling.
2. Migrated the Nandoshi Colab workflow to the profile-driven `AdaptivePipeline`.
3. Added clean repository checkout and stale-package guards.
4. Added package version/path/Git-SHA checks.
5. Added profile validation before expensive Earth Engine operations.
6. Removed obsolete composite-scoring notebook calls.
7. Corrected reference geometry handling for riparian/shoreline reference metrics.
8. Corrected monthly water diagnostics to follow the configured Year-0 baseline rather than inventing future zero-water months.
9. Added reference-condition QA and approval governance.
10. Corrected TNC HM v3 90 m asset handling as an Earth Engine ImageCollection.
11. Added full reference diagnostics and execution-error handling.
12. Added integrated reference governance outputs and manifest records.
13. Added C3 fauna gating to overall condition scoring.

The authoritative final methodology is `docs/METHODOLOGY.md` and the detailed reference standard is `docs/REFERENCE_CONDITION_METHODOLOGY.md`.
