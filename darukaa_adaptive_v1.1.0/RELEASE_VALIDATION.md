# Release validation — darukaa_adaptive_v1.1.0

## 2026-10-07 scoring-participation + zero-reference pressure fix

- Package version remains **1.1.0**.
- Valid metric records with status `calculated` are eligible for scoring when value, reference, QA and scoring-role gates pass.
- `built_fraction` now has an explicit zero-reference safeguard: if the approved reference median is exactly 0, the score uses the bounded native response `100 × (1 − built_fraction)` and records `comparison_method=bounded_absolute_zero_reference`.
- No change to reference-population selection, BII calculation, partial-SoN aggregation, or non-zero-reference pressure response functions.
- 69/69 tests passed.
- Python compilation passed.
- Colab notebook JSON/code-cell compilation passed (11 code cells).

## Recommended Git commit

`Fix scoring participation and zero-reference built fraction`
