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
