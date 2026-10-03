# Darukaa Site Selection → Adaptive Biodiversity Assessment Handoff Specification

**Specification:** 1.0.0  
**Applies to:** `darukaa_adaptive_v1.1.0` and compatible Site Selection releases

## 1. Purpose

This specification defines the machine-readable contract between the Darukaa Site Selection pipeline and the Darukaa Adaptive Biodiversity Assessment framework. The purpose is to ensure that ecological units identified during site selection can be transferred into biodiversity assessment without manual reformatting, filename-dependent logic, or loss of provenance.

The fundamental downstream assessment unit is the **Ecological Management Unit (EMU)**. An EMU is a scientifically defined assessment unit and is not required to be spatially contiguous. Scattered agroforestry parcels may legitimately form one EMU when the Site Selection methodology identifies them as one ecological unit.

## 2. Canonical project hierarchy

```text
Project
 ├── EMU 01
 │    ├── ecological domain
 │    ├── geometry (Polygon/MultiPolygon)
 │    ├── ecological characterization
 │    ├── reference population
 │    ├── metric observations
 │    ├── metric QA/QC
 │    ├── benchmarks
 │    └── readiness / reporting
 ├── EMU 02
 │    └── ...
 └── Project aggregation
      ├── metric coverage
      ├── area-weighted summaries
      ├── domain-specific condition
      └── project-level reporting
```

The hierarchy is intentional. A project-level score must not replace EMU-level evidence, and a project must not be treated as a single homogeneous ecological population merely because it is registered as one project.

## 3. Supported input forms

The Adaptive framework accepts:

1. a Site Selection handoff ZIP containing `tile_manifest.json` and referenced GeoJSON tiles;
2. a handoff `tile_manifest.json` and its referenced GeoJSON tiles;
3. a multi-feature GeoJSON / GeoJSON FeatureCollection;
4. a KML or KMZ containing one or more named polygon features;
5. a single Polygon/MultiPolygon supplied through the Python API.

The handoff contract is preferred for production Site Selection projects because it preserves explicit EMU identity and project provenance.

## 4. Required handoff concepts

### Project

| Field | Required | Meaning |
|---|---:|---|
| `schema_version` | Yes | Handoff contract version |
| `project_id` | Yes | Stable project identifier |
| `project_name` | Recommended | Human-readable project name |
| `domain` | Recommended | `terrestrial`, `aquatic`, `mixed`, or `auto` |
| `tiles` | Yes | List of EMU GeoJSON records |

### EMU tile

| Field | Required | Meaning |
|---|---:|---|
| `emu_id` | Yes | Stable EMU identifier |
| `path` | Yes | Relative path to the EMU GeoJSON |
| `domain` | Recommended | Ecological routing domain |
| `parent_zone` | Optional | Parent client/site-selection zone |
| `source_project` | Optional | Upstream project identifier |
| additional attributes | Optional | Site Selection covariates and provenance |

The GeoJSON tile itself must contain a valid Polygon or MultiPolygon geometry. The Adaptive framework calculates area from geometry rather than trusting a filename or a stale area value.

## 5. Domain routing

The domain is routed in this order:

1. explicit EMU domain;
2. project domain;
3. configured assessment profile.

When geometry alone is supplied without ecological metadata, the framework does **not** infer an aquatic ecosystem merely from polygon shape. The conservative fallback is terrestrial unless the user explicitly configures another profile. This prevents an apparently lake-shaped polygon from silently receiving an aquatic ecological interpretation.

For mixed projects, aquatic and terrestrial EMUs are assessed separately. Their reference populations are not pooled.

## 6. Geometry rules

- Polygon and MultiPolygon geometries are valid inputs.
- Multipart/disconnected EMUs are retained as one EMU when the upstream handoff defines them as one unit.
- Geometry is normalized and validity checked before analysis.
- Area is calculated in a local projected CRS and reported in hectares.
- Geometry provenance should be retained through the project manifest.
- The Adaptive framework does not dissolve separate EMUs into one ecological population merely to simplify processing.

## 7. Reference-condition implications

The EMU boundary is the assessment unit; it is not automatically the reference population.

Reference construction occurs after ecological characterization. For terrestrial EMUs, the current production policy uses ecological comparability based on ecoregion and habitat stratum. For aquatic EMUs, the current production policy uses ecoregional/biogeographic context and hydrological regime. HMI is a disturbance-ordering variable after ecological eligibility and is not permitted to compensate for ecological mismatch.

Mixed projects therefore retain separate aquatic and terrestrial reference populations.

## 8. Project-level aggregation

Project aggregation is performed only after EMU-level results exist. The current generalized aggregation contract:

- retains all EMU-level observations;
- calculates area-weighted summaries where a metric is quantitatively aggregable;
- reports `n_emus` and `n_emus_total`;
- reports `coverage_weight` so incomplete spatial coverage remains visible;
- does not convert missing EMU observations to zero;
- does not create a project-level reference population by pooling incompatible EMUs.

An area-weighted mean is not automatically appropriate for every future metric. Metric-specific aggregation rules belong in the indicator registry and must be validated before activation.

## 9. Provenance requirements

A client-grade assessment should retain:

- upstream project identifier;
- EMU identifiers;
- source handoff archive or manifest;
- source geometry files;
- exact Adaptive Git commit;
- assessment profile and configuration;
- data-source versions where available;
- reference selection diagnostics;
- metric QA/QC status;
- project aggregation coverage.

## 10. Compatibility and change control

The handoff contract is versioned independently from the assessment package. A future breaking change must increment the schema major version and provide an explicit migration path. New optional attributes may be added without changing the meaning of existing required fields.

The Adaptive framework should reject malformed handoffs rather than silently guessing missing EMU identity or geometry relationships.
