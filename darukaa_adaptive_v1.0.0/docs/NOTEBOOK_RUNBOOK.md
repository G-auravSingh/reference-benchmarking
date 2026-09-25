# Colab runbook

1. Open `notebooks/Nandoshi_Lake_Aquatic_Assessment_Colab.ipynb` in Google Colab.
2. Run the first setup cell. It clones the repository when absent and otherwise performs a fast-forward-only pull from `main`.
3. The same cell clears cached `darukaa_adaptive` modules and reinstalls the local editable package.
4. Authenticate Earth Engine and set the working GEE project.
5. Upload the master KML/KMZ.
6. Optionally enable a Tier-1 reference KML or reference CSV. Do not treat a randomly chosen nearby area as a Tier-1 reference.
7. Run geometry QA and inspect the map.
8. Run the baseline water diagnostics and monthly water series.
9. Run the metric suite.
10. Run benchmarking and score gating. The default aquatic configuration will show raw/reference readiness but will not invent a composite score.
11. Download or archive the output directory as the Year-0 evidence package.
12. For later monitoring, use the same seasonal baseline window shifted by year and compare against the stored `metric_scorecard.csv` with `darukaa_adaptive.trajectory.compare()`.

## Pulling manual GitHub edits later

After someone edits a file inside the repository on GitHub, return to the notebook and re-run the setup/synchronization cell. It uses `git pull --ff-only origin main` and then reinstalls the local package. The notebook does not use `git reset --hard`, so local uncommitted work is not silently destroyed; instead, Git will stop and report the conflict/state for the user to resolve.
