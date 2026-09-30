# Darukaa Adaptive Biodiversity Baseline Engine v1.0.0

This is the generalized, profile-driven biodiversity baseline engine. The package name and release version are intentionally fixed at **v1.0.0** for repository continuity.

## Architecture

```text
Project boundary
      ↓
Ecological domains
      ↓
EO / acoustic / field / eDNA / modelled evidence
      ↓
Automatic reference population
      ↓
Reference comparison + uncertainty
      ↓
Intactness 0–100
      ↓
C1 Extent / C2 Vegetation / C3 Fauna / C4 Pressure
      ↓
Condition + Pressure outputs
      ↓
Professional Year-0 HTML report
```

The same downstream evidence contract is used for different evidence sources. A project may be terrestrial, aquatic or mixed. `aquatic_lake` is the first production profile; `terrestrial` and `mixed` are supported profile entry points.

## Spatial model

The supplied KML/KMZ is always the **master assessment boundary**. For aquatic projects, water is derived dynamically for each analysis period. The littoral/shoreline interface is kept distinct from the fixed riparian/terrestrial buffer. A broader landscape context is derived using standardized rules and is not a user-drawn Tier-2 reference polygon.

## Reference model

A reference KML/CSV is **optional**, not required. By default the engine constructs a candidate reference population from spatial/ecological rules:

- aquatic: comparable water pixels/water bodies in the standardized external context, filtered by water occurrence and minimum candidate size;
- terrestrial: standardized natural/semi-natural land-cover candidates in the external context;
- mixed: domain-specific reference populations are kept separate.

Candidate diagnostics and approval status are retained. A reference is not described as pristine merely because it is outside the project boundary.

## Scoring

Raw measurements are never silently converted into scores. The explicit chain is:

`raw value → comparable reference → intactness (0–100) → concern band → pillar score`

The five concern bands are a **declared product convention**, not universal ecological thresholds:

| Intactness | Concern |
|---:|---|
| 80–100 | Very Low |
| 60–<80 | Low |
| 40–<60 | Moderate |
| 20–<40 | High |
| 0–<20 | Very High |

Pillar aggregation uses a geometric mean of score-eligible indicators. **C1–C3 are condition components; C4 pressure is reported separately.** The default Year-0 aquatic profile does not force an overall four-pillar composite when fauna evidence is missing.

## Multi-source evidence and eDNA

eDNA is optional. When validated eDNA observations are available, they can be supplied through the generic evidence CSV and scored in C3 using the same reference/intactness pathway as field or acoustic evidence. The package also recognizes an eDNA persistence-potential metric as contextual: an environmental persistence proxy is not treated as direct evidence of species occurrence or population size without appropriate validation/reference evidence.

Input template can be generated with:

```python
from darukaa_adaptive import edna_template
edna_template("edna_input.csv")
```

## Nandoshi Year-0 defaults

The aquatic profile is configured for **1 Aug 2025–31 Aug 2026** as Year-0 and **2018–2026** as historical context. The notebook is designed to run cell-by-cell in Google Colab and always pulls the current `darukaa_adaptive_v1.0.0` folder from the repository before installing it.

## Outputs

The final assessment writes:

- `metric_scorecard.csv`
- `metric_qa_scorecard.csv`
- `benchmark_scorecard.csv`
- `metric_concern_scorecard.csv`
- `pillar_scorecard.csv`
- `water_periods.csv`
- `external_evidence.csv`
- `readiness.json`
- `overall_scorecard.json`
- `assessment_manifest.json`
- `Year0_Biodiversity_Baseline_Report.html`

The HTML report is generated from the same outputs and includes assessment overview, architecture, reference framework, indicator results, pillar results, separate condition/pressure interpretation, spatial/temporal context, evidence/eDNA section, data gaps and technical appendix.

## Legacy reproducibility

`legacy/darukaa_reference_v0.1.0/` is frozen and is not modified by the adaptive engine.
