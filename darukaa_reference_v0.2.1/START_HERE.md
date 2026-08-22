# darukaa_reference v0.2.0 — Start Here

Profile-first, non-compensatory, evidence-graded biodiversity benchmarking pipeline.

## Read in this order
1. `METHODOLOGY_MASTER.md` — the methodology (start here)
2. `ASSUMPTIONS_AND_LIMITATIONS.md` — **read before quoting any result** (SEED caveats, un-run GEE paths)
3. `INDICATOR_REGISTER.md` — every indicator, its contract, and whether it is scored
4. `SCORING_LOGIC_NOTE.md` — how a site becomes a profile + score
5. `CHANGELOG.md` / `OPEN_DECISIONS.md` — what changed and what is still open
6. `NPI_CROSSWALK.md`, `TNFD_LEAP_CROSSWALK.md`, `SOCIAL_BASELINE_FRAMEWORK.md`, `NEXT_CYCLE_IMPLEMENTATION.md`

## Run it
- **Colab (easiest):** open `notebooks/run_pipeline.ipynb`, run top to bottom.
- **Local/CLI:** `pip install -e .` then `python example_run.py --site your.kml`
  (needs an authenticated Earth Engine project, e.g. `gaurav-singh-007`).

Every run writes `outputs/benchmark_scorecard.json/.csv/.html`. Open the **.html** —
that is the evidence-graded report (the client deliverable).

## Before a real run
- Authenticate GEE to your project.
- Leave `reference_stratification='landcover_elevation'` unless you have read the PNV/SEED
  caveats (ASSUMPTIONS §1) — the `pnv_ecoregion` path is wired but not yet validated live.
