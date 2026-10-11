# Validation Protocol — v1.1.0

## Automated validation

The release gate requires:

```bash
pytest -q
python -m compileall -q darukaa_adaptive
```

The tests cover the generalized input contract, Site Selection handoff parsing, reference policy, metric scoring, hierarchical aggregation, project aggregation and report-related data structures.

## Live acceptance

A client-ready run additionally requires a fresh Colab execution against the exact release commit with Earth Engine initialized.

The live run must verify:

1. package version and Git SHA;
2. input/EMU count and geometry validity;
3. domain routing;
4. reference engine execution without API/runtime errors;
5. reference candidate rejection vs approval status;
6. metric QA/QC;
7. benchmark and score eligibility;
8. P1/P2/P3/P4 separation;
9. project aggregation coverage;
10. EMU ecological comparison;
11. HTML report and CSV/JSON consistency.

A candidate being rejected by reference QA is a valid scientific outcome. An Earth Engine exception, missing dataset, parser failure or calculation exception is not a scientific outcome and blocks release of that run.

## Scientific verification

The framework has been checked against TNFD LEAP/State of Nature guidance and SEEA ecosystem-condition guidance. These sources support reference-relative measurement, explicit metric selection, normalization before aggregation, transparent aggregation and visible uncertainty/data gaps. They do not prescribe the Darukaa 0–100 bands or limiting-factor hierarchy as universal ecological laws; those are explicit product/method conventions documented in `docs/METHODOLOGY.md`.


## Runtime QA/readiness follow-up (2026-10-10)

- Automated suite: **92 tests passed** after adding QA/readiness regression tests.
- `calculated` is treated as a normal successful status; explicit zero observation/pixel support remains a review condition.
- `not_applicable` and contextual/pending provenance states are preserved as non-scored statuses rather than treated as missing-measurement failures.
- Project report now surfaces metric-level QA gaps and documents the project/EMU aggregation basis.
- These are local tests. A live Earth Engine run and client-specific output review are still required; the prior attached run has not been retroactively recalculated by this code change.


## 2026-10-11 pre-Colab gate update

- Offline regression suite: 101 tests pass after the metric-disposition, NDVI response, support-gate, area-contract and headline-coverage changes.
- Default headline guard: at least 3 valid scored metrics across 3 subdimensions per pillar; all three condition pillars required for a condition headline.
- NDVI is scored only with a valid reference p05/median response; raw NDVI ratio scoring is prohibited.
- EII remains contextual until source/path QA resolves the documented anomaly; BII remains the alternative scoreable biodiversity-intactness signal.
- A project handoff without an independent project-boundary geometry is flagged for review; EMU sum/union is not labelled project area.
- These are offline tests only. A fresh Earth Engine/Colab run is still required to validate current raster values, asset access, per-metric support, and reference distributions.
