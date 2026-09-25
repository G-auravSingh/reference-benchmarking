# Release checklist

Before using a build for a client run:

- confirm the repository commit shown by the Colab notebook;
- confirm the master KML hash is recorded in `assessment_manifest.json`;
- inspect master boundary area and map domains;
- confirm Year-0 dates are the intended seasonal window;
- confirm Dynamic World/Sentinel-2/Sentinel-1 assets are accessible;
- inspect monthly water extent diagnostics;
- inspect all metric statuses and valid-pixel counts;
- inspect Tier-1/Tier-2 benchmark availability and provenance;
- confirm score eligibility and pillar coverage;
- confirm that the selected reference tiers are explicitly approved for scoring; apply the fixed Darukaa 0–100 intactness concern bands;
- retain the complete output directory and Year-0 `baseline_metric_scorecard.csv`.
