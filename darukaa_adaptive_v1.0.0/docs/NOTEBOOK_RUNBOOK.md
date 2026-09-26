# Colab Runbook

The notebook is designed to be run one cell at a time.

The first code cell pulls `darukaa_adaptive_v1.0.0` with `git pull --ff-only` when the repository already exists, then reinstalls the package and clears cached imports.

Only the master project KML/KMZ is required for the spatial/EO workflow. Field, acoustic and eDNA CSVs are optional. eDNA PDF/HTML/Krona files can be supplied as evidence artefacts for the final report.

The final cell alone builds and displays `year0_biodiversity_baseline.html`.
