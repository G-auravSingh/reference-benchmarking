# Colab runbook

1. Open `notebooks/Nandoshi_Lake_Aquatic_Assessment_Colab.ipynb` in Google Colab.
2. Run the first setup cell. It clones the repository when absent and otherwise performs a fast-forward-only pull from `main`.
3. The same cell clears cached `darukaa_adaptive` modules and reinstalls the local editable package.
4. Authenticate Earth Engine and set the working GEE project.
5. Upload the master KML/KMZ.
6. Optionally enable a Tier-1 reference KML or reference CSV. Do not treat a randomly chosen nearby area as a pristine reference without review.
7. Run geometry QA and inspect the map.
8. Run the baseline water diagnostics and monthly water series.
9. Run the metric suite.
10. Run reference benchmarking and inspect raw values, selected reference and intactness.
11. Apply the fixed Darukaa five-band concern convention through the scoring cell. Indicator scoring requires an explicitly approved selected reference.
12. Inspect C1 Extent, C2 Vegetation, C3 Fauna and C4 Pressure pillar coverage. Each pillar is the geometric mean of continuous 0–100 intactness values and reports its limiting indicator.
13. The overall State of Nature is the geometric mean of all four pillars when required pillar coverage is met. It reports the limiting pillar and limiting indicator.
14. Download or archive the output directory as the Year-0 evidence package.
15. For later monitoring, use the same seasonal baseline window shifted by year and compare against the stored `metric_scorecard.csv` with `darukaa_adaptive.trajectory.compare()`.

## Field / acoustic / terrestrial data

External observations can use the same scoring engine with:

`metric, pillar, raw_value, direction, reference_value`

plus optional metadata such as units, reference type/level, reference approval, status and notes.

For C3 Fauna, field surveys, acoustics, eDNA or another validated biodiversity module should supply the evidence. EO water proxies do not substitute for local fauna observations.

## Pulling manual GitHub edits later

After someone edits a file inside the repository on GitHub, return to the notebook and re-run the setup/synchronization cell. It uses `git pull --ff-only origin main` and then reinstalls the local package. The notebook does not use `git reset --hard`, so local uncommitted work is not silently destroyed; Git will stop and report the conflict/state for the user to resolve.
