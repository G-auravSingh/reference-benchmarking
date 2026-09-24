# TataMotors_Pimpri — status (Aug 2026 rebuild)

Rebuilt against the client's real, corrected ecological zonation
(`Pune-Pimpri-eco_zones_1.kml`), replacing the old v6.0 pipeline's purely
algorithmic SEG01-SEG10 segments (confirmed to have zero relationship to
any real ecological concept).

## What's built and tested this session

- **Preprocessing** (`preprocess_eco_zones.py`): parses the KML's 20 real
  GDAL layers, splits into true exclusion polygons + buffered line
  features (buildings 10m, paths 5m, water/reed beds/wetland-line 15m —
  buffering chosen over closed-loop detection since real closure rates
  ranged 1-61% across layers) and 10 real usable eco-zones, clipped
  correctly so exclusion always takes precedence over usable-zone
  eligibility (a real ~14ha raw overlap found and fixed).
- **Full ingestion + candidate grid + spatial join**: 1,298 real candidate
  cells generated and tagged with their real eco-zone; 103 correctly
  unmatched (the genuine ~4ha digitization gap, not a bug).
- **Zone-aware EMU delineation**: `segmentation_reconciliation.py` now
  respects real zone boundaries as a hard partition (never splits or
  merges across one), verified with a real regression test that this
  doesn't affect Soulforest/GV, which never opt in.
- **Season-reset position rotation**: corrected from an initially wrong
  proposal (reused the wrong prior device-role design) to the validated
  one — same position at the same relative week in every one of 3
  seasons, verified directly against synthetic data.
- **Zone-scoped multi-EMU rotation**: for a zone split into multiple real
  sub-EMUs, the assigned device now rotates between them across weeks
  too, with the same season-reset and real temporal-replication honesty
  applied recursively. New `zone_scoped_continuous` regime, wired through
  camera trap co-location and schedule export, regression-tested against
  every existing project.
- **Historical crosswalk** (`historical/build_crosswalk.py`): every real
  Phase 01 position (13-27 Aug 2026) spatially joined against the
  corrected boundary/exclusion/zone structure. Real findings: 2 of 10
  audiomoths and 1 soil sample now fall inside the corrected exclusion
  buffer or an unmatched gap area — worth noting when interpreting that
  data, not a pipeline bug.

## What's still open

- **Real sub-EMU counts per zone** depend on the live GEE SNIC run — the
  ready-to-run script is generated (`gee_output/TataMotors_Pimpri_ready_to_run.js`)
  but not yet executed.
- Full end-to-end deployment schedule can't be produced until that run
  completes and 03b/04 actually execute against real segmentation data.
- One known client-source data quality note: `_L_Veg_Water margion` (typo
  for "margin") is the layer's real name in the source KML — kept as-is
  rather than silently corrected, since it's the client's own label.
