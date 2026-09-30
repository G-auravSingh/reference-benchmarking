# Changelog — darukaa_adaptive_v1.0.0

## v1.0.0

Rebuilt from the supplied previous v1.0.0 base as the production adaptive baseline engine.

- Profile-driven aquatic / terrestrial / mixed architecture.
- Master KML boundary retained as the only required spatial input.
- Automatic reference-population construction; manual reference files are optional overrides.
- Explicit aquatic, littoral/shoreline, riparian and landscape-domain concepts.
- Shared multi-source evidence contract for EO, field, acoustic, eDNA and modelled evidence.
- Optional eDNA ingestion and C3 scoring pathway; eDNA persistence-potential proxy remains contextual unless validated for scoring.
- Condition (C1–C3) and pressure (C4) are separated.
- Reference-relative intactness and five-band concern convention retained as a product convention.
- Reference diagnostics/provenance are exported.
- Complete self-contained Year-0 HTML report generated automatically.
- Colab notebook rebuilt as a clean cell-by-cell production workflow with repository sync, package reinstall and optional external/eDNA input.
- Fixed Earth Engine callback casting and null-result handling retained in the aquatic implementation.
- Package installation now declares runtime dependencies through `setup.py` as well as `requirements.txt`.
- Legacy v0.1.0 package remains frozen.
