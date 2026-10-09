# Project report output specification — v1.1.0

## Purpose and audience

`Project_Biodiversity_Baseline_Report.html` is the client-facing project-level summary generated after the multi-EMU Colab run. It is designed to be read alongside, not instead of, the machine-readable EMU outputs and project manifest. It is a Year-0 baseline interpretation, not a biodiversity certification, regulatory opinion, or verified biodiversity-risk rating.

## Required report sections

1. **Project headline:** project name, framework version, run timestamp, summed EMU area, EMU count, project condition and condition coverage, pressure intactness, limiting pillar/EMU.
2. **Executive summary:** EMU-based workflow and distinction between condition and anthropogenic pressure.
3. **Assessment overview:** profile, configured baseline window, historical context and domain coverage by EMU count/area.
4. **Project pillar summary:** project-level scores, scored-EMU counts, total EMUs, area coverage, distribution statistics and limiting EMU where available.
5. **Project metric summary:** area-weighted common-scale score, metric coverage, distribution and limiting EMU where available.
6. **EMU condition concern distribution:** counts and area shares by existing concern band for EMUs with all three condition pillars scored; partial and insufficient evidence are separate categories.
7. **EMU ecological comparison:** pillar scores/concerns, limiting metrics, condition score/band only when all three condition pillars are scored, and coverage status.
8. **Interpretation and management priorities:** use limiting indicators and spatial variation; do not infer a single hidden rank or conflate pressure with condition.
9. **Evidence gaps:** partial/insufficient condition and unavailable pressure headlines.
10. **Automated output QA:** surfaced review flags and a clear note that a PASS is not ecological validation.
11. **EMU/reference index:** per-EMU domain, area, condition coverage, limiting metric, reference populations and output path.
12. **Traceability/deliverables:** list of CSV/JSON/report outputs and the manifest relationship.

## Interpretation rules

- The 0–100 score is reference attainment under the configured metric response function; it is not automatically an absolute ecological-integrity percentage.
- P1/P2/P3 condition and P4 anthropogenic pressure are separate. Do not invert one to infer the other.
- Project headline scores do not replace EMU-level results. Review the distribution and limiting indicators before selecting management actions.
- Overall EMU concern bands are only assigned when all three condition pillars are score-eligible. Partial/insufficient EMUs are not assigned zero and are not forced into a concern band.
- The existing score concern bands are reused; the report does not introduce new cut-offs.
- Area shares use summed EMU area and assume non-overlapping EMUs. If overlaps exist, a validated non-overlapping area basis is required before interpreting area shares.
- Automated QA flags are review aids, not ecological certification. Live Earth Engine source access, native-resolution support, reference comparability, uncertainty and field validation still require review as applicable.

## Output bundle acceptance checklist

- `Project_Biodiversity_Baseline_Report.html` exists and includes the required sections above.
- `emu_condition_concern_distribution.csv` exists; counts and areas reconcile to the EMU comparison table and summed EMU area, allowing for rounding.
- `emu_ecological_comparison.csv` retains EMU-level pillar scores, condition coverage, limiting metric and concern where defensible.
- `project_output_qa.json` is present and all REVIEW flags are inspected before client release.
- `project_assessment_manifest.json` includes EMU outputs, aggregation, condition distribution, final output-QA state and the archive path.
- Each EMU output folder is reviewed for metric QA/QC, reference governance, benchmark records, scorecards, readiness and its Year-0 report.
- The downloaded archive contains the final manifest and all report/table outputs.
