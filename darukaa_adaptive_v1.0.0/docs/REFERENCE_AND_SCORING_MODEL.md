# Reference and scoring model

## Metric contract

Every native aquatic metric is registered with:

- pillar, construct and subdimension;
- spatial domain;
- direction;
- evidence tier;
- allowed reference type;
- scoring disposition;
- ecological question and management use.

This registry is the control layer. The metric implementation does not decide its own ecological legitimacy merely because a numerical value can be produced.

## Benchmark contract

The benchmark table keeps both raw observations and reference values.

| field | meaning |
|---|---|
| `observed_value` | Site-period measurement |
| `tier1_value` | Externally justified reference, when supplied |
| `tier2_value` | Automatically derived candidate/context reference |
| `selected_reference` | Tier-1 first, otherwise Tier-2 |
| `selected_reference_level` | `tier1`, `tier2` or `none` |
| `raw_relative_ratio` | Direction-aware observed/reference relationship |
| `intactness_ratio` | Raw ratio capped to 0–1 for reference-relative scoring |
| `benchmark_status` | Explicit reference availability/status |

No benchmark is treated as a universal reference for every metric. Metrics marked `contextual` have no generic ratio calculation.

## Concern scoring

The output is intentionally layered:

`raw value → reference comparison → metric concern (1–5) → pillar score → overall 0–10`

A metric can therefore be reportable, benchmarkable and still not score because a validated threshold basis has not been supplied.

## Why complete-pillar gating matters

A composite score can appear numerically stable while the underlying evidence base changes from run to run. The adaptive pipeline therefore records all metrics, marks their score status, requires minimum metric coverage within pillars, and by default withholds the overall score unless all four pillars are represented.

For an aquatic lake, this is important because EO can describe water extent, water quality proxies and shoreline pressures, but cannot manufacture local species assemblage or population-status observations.
