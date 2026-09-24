# Open Decisions & Assumptions Log

Running log of decisions taken and items still open. Each open item blocks nothing
unless marked BLOCKING. Closed items are kept for provenance.

## Closed (decided)
| ID | Decision | Date/By |
|----|----------|---------|
| OD-C1 | Scoring output = **profile-first hybrid** (Option B): mandatory per-component profile + optional non-compensatory roll-up with published minimum + framing block | Aura, Phase 2 |
| OD-C2 | Within-pillar: **limiting-factor rule** across subdimensions, full profile always shown | Aura, Phase 2 |
| OD-C3 | In-situ metrics **exit concern scoring in cycle 1**; enter as change-vs-baseline from cycle 2 | Aura, Phase 2 |
| OD-C4 | **EII scored at parent level** (Landbanking limiting-factor minimum = non-compensatory; confirmed via a v0.2.2 methodology audit — NOT "fuzzy" logic, a hard min of the 3 sub-scores), 3 components shown as diagnostic context | Phase 2; verified v0.2.2 — see OD-1 |
| OD-C5 | Agroforestry uses **BAU counterfactual** reference (additionality), not naturalness | Aura, Phase 2 |
| OD-C6 | Toggle architecture: `registered` / `active` / computed `eligible`; **active ⟹ eligible** | Aura, Phase 2 (implemented Batch 1) |
| OD-C7 | HMI ceiling restored to **0.05** (SEED max) | HMI audit, Batch 1 |
| OD-8 | `pnv_to_dw_crosswalk` biome codes verified against the live PNV asset's actual band/class metadata (20 `biome_type` classes, band `biome_type`) — codes and names confirmed correct; `pnv_to_dw_crosswalk_verified=True` set in config.py | 2026-08-22, live GEE check (config.py's own inline comment has the full note — this entry was verified before this log was updated to say so) |
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
| OD-1 | ~~Obtain Landbanking EII documentation confirming aggregation logic~~ **CLOSED (v0.2.2 audit)**: confirmed hard limiting-factor minimum (lowest of the 3 sub-scores), not fuzzy logic. Citation still needed for the exact sub-score formulas (Landbanking's proprietary algorithm, not published in full). | closed/partially open | Methods |
| OD-2 | Confirm **equal-weight default** across the 4 components as the published Darukaa standard | open, assumed yes | Aura |
| OD-6 | Confirm **foundation-model embedding asset** for site-selection stratification at implementation | open, asset-agnostic default | Methods |
| OD-7 | Raw **carbon workbook** arithmetic (where applicable) handled manually, outside pipeline scope | open, manual/separate | Methods |
| OD-9 | Calibrate `seed_kernel_delta` via `estimators.fit_delta_diagonal` against real (indicator z-score, HMI) pairs from a live GEE run | open, needs real data | Methods, post live run |
| OD-10 | Decide whether to invest in "full" Mahalanobis covariance (co-located multi-band reference sampling) vs keep "diagonal" as the standing default | open, low urgency | Methods |
| OD-11 | Known gap: pasture/grazing land has no distinct Dynamic World class and is not reliably captured by the default artificial-class list (crops, built) | open, documented | Methods |
| OD-12 | Confirm/obtain a usable access mechanism for the Species Habitat Index (SHI) -- the genuinely correct C3 fauna signal, GBF-adopted, not yet integrated (no confirmed simple GEE asset) | open, needs SHI/mol.org data-access research | Methods |
| OD-13 | FLII's Q/LFC focal radius (config.flii_edge_effect_radius_m, default 300m) is a declared placeholder pending project-specific edge-effect literature review | open | Methods |
| OD-14 | Forest-loss gain detection is a one-time Dynamic World snapshot annualised per window, not an annually-resolved signal the way Hansen loss is -- a genuinely time-resolved gain product would be a real improvement if one becomes available | open | Methods |
