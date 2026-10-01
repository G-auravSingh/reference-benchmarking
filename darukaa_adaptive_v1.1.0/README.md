# Darukaa Adaptive Biodiversity Assessment Framework

**Production release line:** `darukaa_adaptive_v1.1.0`  
**Reference-condition architecture:** R4 / 2026-10-01

Darukaa Adaptive is a profile-driven biodiversity assessment framework for terrestrial, aquatic and mixed sites. It is designed for reproducible Earth Observation assessments while keeping ecological interpretation, reference benchmarking, pressure/state separation and evidence provenance explicit.

## Start here

If you are maintaining or reviewing the methodology, read these in order:

1. **`docs/REFERENCE_CONDITION_METHODOLOGY.md`** — the core company methodology for reference conditions.
2. **`docs/REFERENCE_CONDITION_QA_CHECKLIST.md`** — production QA gate.
3. `docs/REFERENCE_AND_SCORING_MODEL.md` — downstream scoring contract.
4. `docs/METHOD_NOTES.md` — implementation caveats and metric notes.
5. `VALIDATION.md` — what has been tested and what requires live Earth Engine execution.
6. `CHANGELOG.md` — release history and scientific changes.

## Core architecture

```text
Site boundary
    ↓
Ecological domains
    ↓
Metric extraction
    ↓
Reference-condition engine
    ├─ ecological matching
    ├─ low-pressure screening
    ├─ temporal matching
    └─ population adequacy
    ↓
Reference QA / approval gate
    ↓
Reference distribution
    ↓
Metric-specific reference comparison
    ├─ relative departure
    ├─ reference attainment (where scoreable)
    └─ uncertainty / interpretation
    ↓
C1/C2/C3 condition
    +
C4 pressure (separate)
    ↓
Auditable report + manifest
```

## What changed in the R4 reference architecture

The production system no longer treats an automatically generated spatial candidate as a reference merely because it is nearby or has low disturbance.

The default automated reference is a **least-disturbed contemporary reference population** that must satisfy explicit gates for:

- ecological comparability;
- anthropogenic-pressure screening;
- temporal compatibility;
- spatial quality;
- minimum population size.

The `auto_approve` setting is only permission to approve a candidate **after** these gates pass. It is not an unconditional bypass.

### Reference state ≠ pristine by definition

The reference state can be:

- minimally disturbed/undisturbed;
- least-disturbed contemporary;
- historical;
- best attainable;
- paired control;
- published target.

The default is `least_disturbed_contemporary` because a true pristine state is often unavailable or scientifically undefinable from contemporary EO alone.

### Reference attainment ≠ landscape intactness

The legacy `intactness_score_0_100` field remains for backwards compatibility, but the production interpretation is **reference attainment**.

Landscape intactness is reserved for spatial ecosystem configuration, fragmentation, connectivity and related State-of-Nature constructs.

## Production reference engines

### Aquatic

The automatic aquatic reference searches a broader configurable region than the ordinary site context and uses:

- water occurrence/hydroperiod similarity;
- RESOLVE ecoregion compatibility;
- low human-modification screening in the surrounding land context;
- minimum candidate area/pixel thresholds;
- temporal adequacy.

Water extent itself is not benchmarked against a false 100% water reference. Hydrological dynamics are treated as a reference-target problem.

### Terrestrial

The automatic terrestrial reference uses:

- RESOLVE ecoregion compatibility;
- Dynamic World habitat/land-cover class as a comparability stratum;
- TNC Global Human Modification v3 90 m as the default pressure screen;
- minimum candidate population requirements;
- automated QA before approval.

Dynamic World class is not interpreted as proof of naturalness.

## Metric evolution

Metrics are deliberately modular. A dataset or formula can be replaced without changing the reference-condition API.

Every metric should retain:

- source/dataset identity;
- temporal window;
- native resolution;
- formula/processing version;
- direction or target type;
- reference method;
- evidence tier;
- uncertainty method.

A metric upgrade must be regression-tested and documented in the changelog before release.

## Running the package

### Colab

Open:

`notebooks/Nandoshi_Lake_Aquatic_Assessment_Colab.ipynb`

The notebook clones the requested repository ref, installs the package, records release identity and runs the full aquatic pipeline.

### Local

```bash
pip install -r requirements.txt
pip install -e .
pytest -q
```

For a live Earth Engine run, authenticate Earth Engine and supply the project ID through the profile/notebook configuration.

## Output contract

A production run writes:

- `metric_scorecard.csv` — raw metric extraction;
- `metric_qa_scorecard.csv` — measurement QA;
- `benchmark_scorecard.csv` — reference comparison and reference governance;
- `metric_concern_scorecard.csv` — final scoring disposition;
- `pillar_scorecard.csv` — pillar aggregation;
- `overall_scorecard.json` — condition/pressure summary;
- `readiness.json` — readiness and coverage;
- `assessment_manifest.json` — reproducibility/provenance;
- `Year0_Biodiversity_Baseline_Report.html` — self-contained report;
- water-period and land-cover diagnostics where applicable.

## Scientific guardrails

The framework does not claim that:

- low human modification alone proves ecological integrity;
- a reference ratio is biodiversity itself;
- NDVI is biodiversity;
- exceeding a reference means ecological perfection;
- a protected area is automatically pristine;
- one reference-search radius is valid for every ecosystem;
- remote sensing eliminates the need for field validation where validation is required.

## External methodological basis

The methodology is informed by TNFD LEAP/reference-condition guidance, UN SEEA ecosystem accounting, Nature Positive Initiative State of Nature Metrics, SBTN guidance, reference-condition ecology literature, ecological restoration reference-ecosystem principles, and habitat-condition approaches such as Natural England's Biodiversity Metric.

These frameworks are evolving. Darukaa therefore maintains its own explicit methodology contract and re-audits external standards and datasets at major releases.
