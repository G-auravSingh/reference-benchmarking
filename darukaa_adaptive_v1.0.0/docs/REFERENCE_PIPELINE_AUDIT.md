# Reference Pipeline Audit — v1.2.0

The former adaptive v1.1 proof-of-concept used an explicit Tier-1 reference KML/CSV path and a Tier-2 context-ring candidate. That design is no longer used by the standard workflow.

The v1.2 engine uses an automatic, realm-aware reference population derived from spatial/ecological comparability and a least-modified filter. Manual reference inputs remain possible only as future, explicit overrides; they are not required.

The legacy `darukaa_reference_v0.1.0` directory remains frozen for auditability. The v0.2.7 methodology was used as the conceptual source for ecoregion-based reference selection, scale-aware estimators, evidence gating and profile-first reporting, but the aquatic candidate-selection logic is adapted rather than copied unchanged from the terrestrial pathway.
