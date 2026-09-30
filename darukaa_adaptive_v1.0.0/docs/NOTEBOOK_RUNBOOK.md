# Colab runbook

1. Open `notebooks/Nandoshi_Lake_Aquatic_Assessment_Colab.ipynb`.
2. Run cells in order.
3. Cell 1 pulls the current GitHub repository and installs only `darukaa_adaptive_v1.0.0`.
4. Upload one master KML/KMZ.
5. Leave optional external/eDNA evidence disabled when it is unavailable.
6. Authenticate Earth Engine.
7. Inspect the monthly water trajectory before running the full assessment.
8. Run the profile-driven pipeline.
9. Inspect raw metrics, QA, references and scorecards separately.
10. Open the generated `Year0_Biodiversity_Baseline_Report.html`.
11. Freeze the Year-0 scorecard for future comparison.
12. Zip the outputs.

If GitHub changes are made later, rerunning cell 1 on a clean runtime pulls them before installation. The notebook does not modify any other repository folder.
