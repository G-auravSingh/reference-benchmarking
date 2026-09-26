# Darukaa Adaptive Biodiversity Assessment — v1.2.0

A generalized, profile-driven Year-0 biodiversity baseline engine for **terrestrial, aquatic and mixed sites**.

## What changed in v1.2.0

This release replaces the provisional reference-input/context-ring logic with an **automated reference framework**. A project normally supplies only its master KML/KMZ boundary and optional field/acoustic/eDNA data. The engine automatically resolves ecological context and constructs reference populations.

The four fixed pillars are:

- **C1 — Extent**
- **C2 — Vegetation / ecosystem condition**
- **C3 — Fauna**
- **C4 — Pressure**

Every scoreable indicator follows:

`raw value → comparable reference → signed benchmark → normalized intactness (0–100) → concern`

Pillar and overall aggregation are performed on the continuous 0–100 values using the **geometric mean**. Concern labels are applied only after aggregation; labels are never averaged.

### Declared concern convention

| Normalized intactness | Concern |
|---:|---|
| 80–100 | Very Low |
| 60–<80 | Low |
| 40–<60 | Moderate |
| 20–<40 | High |
| 0–<20 | Very High |

These equal-width bands are a declared Darukaa product convention. They are not presented as universal ecological thresholds. The normalized score is centered at **50% at the reference condition**, matching the reference-relative classification architecture.

## Automatic references

No reference KML or reference CSV is required in the standard workflow.

**Terrestrial references** use the site ecoregion, a least-modified Human Modification filter, natural/modified land-cover stratification and a sampled reference distribution.

**Aquatic references** use the site ecoregion plus comparable waterbody candidates from HydroLAKES, approximate lake-area similarity, spatial exclusion from the project and a least-modified Human Modification filter. Candidate reference populations are evaluated under consistent metric definitions.

Each reference records `n`, standard error, percentiles, selection diagnostics and an approval flag. A metric is not scored when the reference population is too small, unstable or otherwise unsuitable.

## Spatial domains

The project KML is the master spatial frame. The engine derives:

- dynamic water domain
- 50 m littoral/nearshore band
- fixed 100 m riparian band
- 5 km terrestrial/context domain

The same site frame is retained, but individual metrics use the domain/mask appropriate to their ecological question.

## Evidence streams

The same downstream scorer accepts:

- Earth observation
- field ecology
- bioacoustics
- shotgun eDNA/metagenomics
- later eDNA/targeted molecular measurements

External field/acoustic/eDNA observations carry their own sampling/reference metadata. The automatic spatial reference engine is used for EO-derived terrestrial and aquatic metrics; external observations enter the same scoring layer once an appropriate matched reference is supplied and approved.

External metrics can be introduced through CSV metadata without writing new metric-extraction code. An evidence-only record can remain visible in the report without becoming a score until a defensible reference is supplied.

## eDNA integration

The eDNA layer is deliberately conservative. The current Nandoshi Phase-1 workflow can be represented through structured metrics such as taxonomic assignment richness, cyanobacterial fraction, human-associated fraction and reducing-microbe fraction. The report distinguishes **measured, indicated, inferred and unresolved** evidence and retains source HTML/PDF/Krona artefacts when supplied.

Taxonomic assignments are treated as database matches rather than automatically as independently confirmed species observations. Hazard/functional interpretations require their stated validation data.

## Final report

The final Colab cell creates a professional, self-contained HTML Year-0 report covering:

- executive summary
- assessment boundary and domains
- methodology and automatic reference framework
- automated QA/QC
- C1–C4 pillar results
- indicator scorecard
- overall condition, pressure and four-pillar SoN where coverage permits
- limiting pillar/indicator chain
- seasonal water dynamics
- eDNA evidence
- interpretation, recommendations and next-cycle data gaps
- technical appendix and provenance

A Nandoshi-specific structured eDNA evidence example is included at `examples/nandoshi_edna_phase1.csv`; it is evidence-only by default and does not carry approved reference values. The report is a projection of pipeline outputs; it does not silently invent scores for missing references or missing evidence.

## Colab workflow

1. Open `notebooks/Nandoshi_Lake_Aquatic_Assessment_Colab.ipynb`.
2. Run cell-by-cell. The notebook pulls the latest `darukaa_adaptive_v1.0.0` folder from GitHub with `git pull --ff-only` before installing it.
3. Upload a site KML/KMZ. Field/acoustic/eDNA files are optional.
4. Authenticate to Earth Engine.
5. Run metric extraction, QA, reference selection, benchmarking and scoring.
6. The **last cell only** generates and displays `year0_biodiversity_baseline.html`.

## Legacy boundary

The frozen `legacy/darukaa_reference_v0.1.0/` directory is retained for auditability and is not modified by this adaptive release.
