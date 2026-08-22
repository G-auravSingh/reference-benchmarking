# Open Decisions & Assumptions Log

Running log of decisions taken and items still open. Each open item blocks nothing
unless marked BLOCKING. Closed items are kept for provenance.

## Closed (decided)
| ID | Decision | Date/By |
|----|----------|---------|
| OD-C1 | Scoring output = **profile-first hybrid** (Option B): mandatory per-component profile + optional non-compensatory roll-up with published minimum + framing block | Aura, Phase 2 |
| OD-C2 | Within-pillar: **limiting-factor rule** across subdimensions, full profile always shown | Aura, Phase 2 |
| OD-C3 | In-situ metrics **exit concern scoring in cycle 1**; enter as change-vs-baseline from cycle 2 | Aura, Phase 2 |
| OD-C4 | **EII scored at parent level** (Landbanking fuzzy-minimum = non-compensatory), 3 components shown as diagnostic context | Aura, Phase 2 (verify fuzzy-min in Landbanking docs — see OD-1) |
| OD-C5 | Agroforestry uses **BAU counterfactual** reference (additionality), not naturalness | Aura, Phase 2 |
| OD-C6 | Toggle architecture: `registered` / `active` / computed `eligible`; **active ⟹ eligible** | Aura, Phase 2 (implemented Batch 1) |
| OD-C7 | HMI ceiling restored to **0.05** (SEED max) | HMI audit, Batch 1 |
| OD-C8 | Scoring logic lives **in the pipeline** (no separate SoN Module doc); PRD is generated if needed | Aura, Phase 4 |
| OD-C9 | Site-selection Phase 3b = **spatial tiling** (DBSCAN) for large multi-site AOIs, NOT the SEED reference; rename `reference_cluster_*` → `assessment_cluster_*` | Aura, Phase 4 |
| OD-C10 | Corporate/solar/mining/materials modules **registered-inactive** by default | Aura, Phase 4 |

| OD-C11 | Variance-stability reference floor (OD-3): accept reference only if bootstrap median SE within tolerance, else suppress score | Batch 5 |
| OD-C12 | Multivariate SEED kernel (OD-4) implemented as optional per-construct similarity view | Batch 5 |
| OD-C13 | Ecoregion-primary + PNV reference stratification (OD-5) added (config-gated; GEE path) | Batch 5 |
| OD-C14 | Cycle-2 in-situ change scoring (change.py: delta vs Year-0 + detection test + BACI contrast) | Batch 5 |

| OD-C15 | SEED structural audit: corrected PNV role (artificial-pixel relabelling only, not primary classifier), joint ecoregion x land-cover stratification (was ecoregion-only + PNV), removed elevation from the SEED-faithful path, applied the previously-unused eco_id ecoregion constraint, replaced the L1 kernel approximation with a genuine Mahalanobis kernel (Eq. 1), upgraded HMI (CSP gHM 1km/2016 -> TNC HM v3 90m/2022) and land-cover (Copernicus 100m/2019 -> Dynamic World 10m/current) | v0.2.0.1 (post-review audit) |

## Open
| ID | Item | Status | Owner |
|----|------|--------|-------|
| OD-1 | Obtain Landbanking EII documentation confirming **fuzzy-minimum** aggregation + citation for METHODOLOGY_MASTER | open, non-blocking | Aura |
| OD-2 | Confirm **equal-weight default** across the 4 components as the published Darukaa standard | open, assumed yes | Aura |
| OD-6 | Confirm **foundation-model embedding asset** for site-selection stratification at implementation | open, asset-agnostic default | Methods |
| OD-7 | Raw **carbon workbook** arithmetic fix (p.29) handled manually in the separate Corbett report track (out of pipeline scope) | open, manual/separate | Aura |
| OD-8 | Verify `pnv_to_dw_crosswalk` biome codes against the live PNV asset legend in the GEE Code Editor; correct if wrong; set `pnv_to_dw_crosswalk_verified=True` | BLOCKING for the PNV correction to be trustworthy | Aura, first live run |
| OD-9 | Calibrate `seed_kernel_delta` via `estimators.fit_delta_diagonal` against real (indicator z-score, HMI) pairs from a live GEE run | open, needs real data | Methods, post live run |
| OD-10 | Decide whether to invest in "full" Mahalanobis covariance (co-located multi-band reference sampling) vs keep "diagonal" as the standing default | open, low urgency | Methods |
| OD-11 | Known gap: pasture/grazing land has no distinct Dynamic World class and is not reliably captured by the default artificial-class list (crops, built) | open, documented | Methods |
