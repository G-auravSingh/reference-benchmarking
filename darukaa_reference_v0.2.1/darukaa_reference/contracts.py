"""
Indicator Contracts & Dispositions (CS-1 / CS-2 / CS-4 / CS-7)
==============================================================

Declarative table that populates the v0.2.0 indicator contract on every registered
indicator and encodes its disposition from the Phase-2 register (retain / redefine /
context / screening / remove). Applying this table is what makes ``registry.scored()``
return the lean, defensible set instead of the full 44.

Why a table (not 44 inline edits): the disposition of the indicator set is a single
scientific decision surface. Keeping it in one place makes it auditable, testable, and
the direct source of INDICATOR_REGISTER.md. Adding/re-classifying an indicator is a
one-line change here, not surgery across the codebase.

Disposition semantics
---------------------
    retain     -> scored; evidence_tier=baseline; reference + uncertainty set
    redefine   -> scored, but definition/label/threshold changed (see note)
    context    -> registered & active but NOT scored (shown as diagnostic context)
    screening  -> registered & active but NOT scored (screening-only, e.g. range overlap)
    remove     -> de-scoped: registered=False, active=False (code kept, never runs/scored)

Construct axes: C1_landscape, C2_vegetation, C3_fauna (state) feed the CONDITION
profile; C4_pressure feeds the separate PRESSURE axis (condition × pressure matrix).

Every value here traces to PHASE1_Comment_Issue_Matrix / PHASE2 §11. Notes cite the
reviewer comment or fault where relevant.
"""
from __future__ import annotations

from typing import Dict, List
import logging

logger = logging.getLogger(__name__)

# Common input-layer tokens (Gate-A redundancy screening keys)
DW = "dynamic_world"; NDVI = "sentinel2_ndvi"; GHM = "csp_ghm"; VIIRS = "viirs_ntl"
SRTM = "srtm"; GEDI = "gedi_chm"; HANSEN = "hansen_gfc"; MODIS_LST = "modis_lst"
S2 = "sentinel2"; JRC = "jrc_water"; IUCN = "iucn_range_maps"; EII_LAYER = "landbanking_eii"
BII_LAYER = "predicts_bii"; FLII_LAYER = "flii_asset"; PDF_LAYER = "lc_impact_pdf"

# name -> contract dict
# keys: construct, subdimension, measurement_scale, reference_type, reference_estimator,
#       evidence_tier(via disposition), disposition, input_layers, module, realm, note
C: Dict[str, dict] = {
 # ---------------- C1 landscape context & extent ----------------
 "natural_habitat": dict(construct="C1_landscape", subdimension="extent", measurement_scale="ratio",
    reference_type="contemporary_best_on_offer", reference_estimator="log_response_ratio",
    disposition="retain", input_layers=[DW], note="Core extent metric; ratio-scale, true zero."),
 "natural_landcover": dict(construct="C1_landscape", subdimension="extent", measurement_scale="ratio",
    disposition="context", input_layers=[DW], note="Gate A: shares Dynamic World with natural_habitat -> demote (Fault 1/B1)."),
 "cpland": dict(construct="C1_landscape", subdimension="configuration", measurement_scale="ratio",
    reference_type="regional_distribution", reference_estimator="robust_z",
    disposition="redefine", input_layers=["india_pv_binary"], note="Connectivity; state ecological scale (D8). Fragmentation suite to be added."),
 "forest_loss_rate": dict(construct="C1_landscape", subdimension="disturbance_regime", measurement_scale="ratio",
    reference_type="regional_distribution", reference_estimator="log_response_ratio",
    disposition="redefine", input_layers=[HANSEN], note="Change indicator; needs accuracy assessment (D4); low-baseline reliability flag; report with CI."),
 "kba_overlap": dict(construct="C1_landscape", subdimension="extent", measurement_scale="bounded",
    disposition="screening", input_layers=["kba"], note="Proximity/overlap = screening, not site condition (F-style)."),
 "flii": dict(construct="C1_landscape", subdimension="forest_integrity", measurement_scale="bounded",
    reference_type="published_threshold", reference_estimator="robust_z",
    disposition="retain", input_layers=[FLII_LAYER], module="conservation",
    note="Forest realm only (applicability precondition exists). NPI IND3 landscape intactness."),
 "jrc_water_persistence": dict(construct="C1_landscape", subdimension="hydrology", measurement_scale="ratio",
    reference_type="regional_distribution", reference_estimator="log_response_ratio",
    disposition="retain", input_layers=[JRC], note="Hydrology/surface-water permanence."),
 "rci": dict(construct="C1_landscape", subdimension="hydrology", measurement_scale="bounded",
    reference_type="regional_distribution", reference_estimator="robust_z",
    disposition="context", input_layers=[NDVI], module="conservation",
    note="Riparian complexity; riparian strata only. Citation corrected (Naiman & Decamps 1997)."),
 "riparian_ndvi_trend": dict(construct="C1_landscape", subdimension="hydrology", measurement_scale="interval",
    disposition="context", input_layers=[NDVI], note="Trend-based (correct NDVI use); contextual at cycle-1."),

 # ---------------- C2 vegetation condition ----------------
 "eii": dict(construct="C2_vegetation", subdimension="integrity", measurement_scale="bounded",
    reference_type="contemporary_best_on_offer", reference_estimator="robust_z",
    disposition="retain", input_layers=[EII_LAYER], note="SCORED at PARENT (Landbanking fuzzy-min = non-compensatory, Q4). Components shown as context."),
 "eii_structural": dict(construct="C2_vegetation", subdimension="structure", measurement_scale="bounded",
    disposition="context", input_layers=[EII_LAYER], note="Diagnostic context under parent EII (B2 double-count)."),
 "eii_compositional": dict(construct="C2_vegetation", subdimension="composition", measurement_scale="bounded",
    disposition="context", input_layers=[EII_LAYER], note="Diagnostic context under parent EII."),
 "eii_functional": dict(construct="C2_vegetation", subdimension="function", measurement_scale="bounded",
    disposition="context", input_layers=[EII_LAYER], note="Diagnostic context under parent EII."),
 "ndvi": dict(construct="C2_vegetation", subdimension="structure", measurement_scale="interval",
    disposition="context", input_layers=[NDVI], note="Not ratio-scale; remove from intactness. Keep as trend/context (B1)."),
 "habitat_health": dict(construct="C2_vegetation", subdimension="structure", measurement_scale="bounded",
    disposition="context", input_layers=[NDVI], note="z-score construct; overlaps NDVI (Gate A)."),
 "bii": dict(construct="C2_vegetation", subdimension="composition", measurement_scale="bounded",
    disposition="context", input_layers=[BII_LAYER], note="Modelled -> contextual, not baseline (NPI 'modelled, not responsive')."),
 "pdf": dict(construct="C2_vegetation", subdimension="composition", measurement_scale="bounded",
    disposition="context", input_layers=[PDF_LAYER], note="LCA-derived; ratio intactness invalid; not field-verifiable."),
 "lai": dict(construct="C2_vegetation", subdimension="structure", measurement_scale="ratio",
    disposition="context", input_layers=["modis_lai"], note="Shares greenness with NDVI; MODIS grain too coarse for these sites."),
 "chm": dict(construct="C2_vegetation", subdimension="structure", measurement_scale="ratio",
    reference_type="contemporary_best_on_offer", reference_estimator="log_response_ratio",
    disposition="retain", input_layers=[GEDI], note="Genuinely additive: GEDI canopy height, independent of NDVI/DW cluster."),
 # aquatic condition module (only active for aquatic/mixed realm)
 "tspi": dict(construct="C2_vegetation", subdimension="water_quality", measurement_scale="interval",
    disposition="context", input_layers=[S2], module="aquatic", note="Trophic-state proxy; needs external ref or trend-only."),
 "sabf": dict(construct="C2_vegetation", subdimension="water_quality", measurement_scale="bounded",
    disposition="context", input_layers=[S2], module="aquatic", note="Algal-bloom frequency; aquatic module."),
 "wcpi": dict(construct="C2_vegetation", subdimension="water_quality", measurement_scale="bounded",
    disposition="context", input_layers=[S2], module="aquatic", note="Water-clarity proxy; aquatic module."),
 "wsdi": dict(construct="C2_vegetation", subdimension="water_quality", measurement_scale="bounded",
    disposition="context", input_layers=[S2], module="aquatic", note="Surface-dynamics; aquatic module."),
 "hsas": dict(construct="C2_vegetation", subdimension="water_quality", measurement_scale="bounded",
    disposition="context", input_layers=["edna_points"], module="aquatic", note="Suitability model; contextual until eDNA-validated."),
 "edpp": dict(construct="C2_vegetation", subdimension="water_quality", measurement_scale="bounded",
    disposition="context", input_layers=[S2], module="aquatic", note="Persistence model; contextual."),
 "mspl": dict(construct="C2_vegetation", subdimension="water_quality", measurement_scale="bounded",
    disposition="context", input_layers=[S2], module="aquatic", note="Stress model; contextual."),
 "shdi": dict(construct="C2_vegetation", subdimension="water_quality", measurement_scale="ratio",
    disposition="context", input_layers=[S2], module="aquatic", note="Scalar-only morphometry; not cross-site comparable."),

 # ---------------- C3 faunal condition ----------------
 "flagship_habitat": dict(construct="C3_fauna", subdimension="habitat_suitability", measurement_scale="bounded",
    disposition="context", input_layers=[NDVI], note="No named flagship species; weights unjustified (G3). Demote unless redesigned around a named species."),
 "endemic_richness": dict(construct="C3_fauna", subdimension="representation", measurement_scale="ratio",
    disposition="screening", input_layers=[IUCN], note="Range-map derived -> screening, not observation."),
 "endemic_plant_richness": dict(construct="C3_fauna", subdimension="representation", measurement_scale="ratio",
    disposition="screening", input_layers=[IUCN], note="Range-map derived -> screening."),
 "threatened_richness": dict(construct="C3_fauna", subdimension="representation", measurement_scale="ratio",
    disposition="screening", input_layers=[IUCN], note="Identical across co-located sites -> zero discrimination (F1). Screening-only priority list."),
 "threatened_plant_richness": dict(construct="C3_fauna", subdimension="representation", measurement_scale="ratio",
    disposition="screening", input_layers=[IUCN], note="Same construct/defect as threatened_richness."),
 "ceri": dict(construct="C3_fauna", subdimension="representation", measurement_scale="bounded",
    disposition="remove", input_layers=[IUCN], note="Averaging Red List weights is arithmetically perverse: adding common species LOWERS risk (F3). Not repairable -> removed."),
 "star_t": dict(construct="C3_fauna", subdimension="representation", measurement_scale="ratio",
    disposition="context", input_layers=[IUCN], note="Threat-abatement OPPORTUNITY, not site condition. Prioritisation narrative only. NPI IND4 uses STAR forward-looking."),

 # ---------------- C4 pressures & human interface (separate axis) ----------------
 "ghm": dict(construct="C4_pressure", subdimension="land_use_pressure", measurement_scale="bounded",
    reference_type="regional_distribution", reference_estimator="robust_z",
    disposition="retain", input_layers=[GHM], note="THE land-use pressure metric. Pressure axis, NOT condition. Circularity (Fault 2): if gHM selects the reference it must not also be benchmarked against it -> OD."),
 "light_pollution": dict(construct="C4_pressure", subdimension="direct_pressure", measurement_scale="bounded",
    reference_type="regional_distribution", reference_estimator="robust_z",
    disposition="retain", input_layers=[VIIRS], note="Distinct pressure, independent input (VIIRS)."),
 "hdi": dict(construct="C4_pressure", subdimension="land_use_pressure", measurement_scale="bounded",
    reference_type="regional_distribution", reference_estimator="robust_z",
    disposition="redefine", input_layers=["dw_builtup"], note="Rename to built-up/settlement pressure; health-adjusted HDI citation is WRONG (G4). Check overlap with ghm."),
 "lst_day": dict(construct="C4_pressure", subdimension="climate_exposure", measurement_scale="interval",
    disposition="context", input_layers=[MODIS_LST], note="Temperature = exposure, not a manageable pressure. Climate-exposure context."),
 "lst_night": dict(construct="C4_pressure", subdimension="climate_exposure", measurement_scale="interval",
    disposition="context", input_layers=[MODIS_LST], note="Climate-exposure context."),
 "aridity_index": dict(construct="C4_pressure", subdimension="climate_exposure", measurement_scale="interval",
    disposition="context", input_layers=["chirps_terraclimate"], note="Climate context; moved from C2 to C4 climate exposure."),
 "sdi": dict(construct="C4_pressure", subdimension="direct_pressure", measurement_scale="bounded",
    disposition="context", input_layers=[S2], module="aquatic", note="Aquatic shoreline disturbance; aquatic module."),
 "stsi": dict(construct="C4_pressure", subdimension="direct_pressure", measurement_scale="bounded",
    disposition="context", input_layers=[MODIS_LST], note="Site-relative normalisation only; not cross-site comparable."),
 "iri": dict(construct="C4_pressure", subdimension="direct_pressure", measurement_scale="bounded",
    disposition="context", input_layers=[NDVI], note="Invasive RISK model; contextual until field-validated."),
 "ivsi": dict(construct="C4_pressure", subdimension="direct_pressure", measurement_scale="bounded",
    disposition="context", input_layers=[NDVI], note="Detects NDVI expansion, not taxonomic invasion (own docstring). Must NOT be labelled invasion."),
}

# Which dispositions produce a scored (baseline, eligible) indicator
_SCORED = {"retain", "redefine"}
_TIER = {"retain": "baseline", "redefine": "baseline",
         "context": "contextual", "screening": "screening", "remove": "screening"}


def apply_contracts(registry) -> Dict[str, int]:
    """Populate the CS-1 contract + disposition on every registered indicator.

    Returns a summary count by disposition. Indicators absent from the table are
    left registered but flagged contextual (fail-safe: never silently scored).
    """
    counts = {k: 0 for k in ("retain", "redefine", "context", "screening", "remove", "unmapped")}
    for spec in registry.all():
        c = C.get(spec.name)
        if c is None:
            spec.evidence_tier = "contextual"
            spec.metadata["contract_note"] = "UNMAPPED — defaults to contextual (not scored)."
            counts["unmapped"] += 1
            logger.warning("Indicator %s has no contract entry; defaulting to contextual.", spec.name)
            continue
        disp = c["disposition"]
        spec.construct = c.get("construct")
        spec.subdimension = c.get("subdimension")
        spec.measurement_scale = c.get("measurement_scale")
        spec.input_layers = list(c.get("input_layers", []))
        spec.module = c.get("module", "core")
        spec.evidence_tier = _TIER[disp]
        spec.metadata["disposition"] = disp
        spec.metadata["contract_note"] = c.get("note", "")
        if disp in _SCORED:
            spec.reference_type = c.get("reference_type")
            spec.reference_estimator = c.get("reference_estimator")
            spec.uncertainty_method = "bootstrap_ci"  # pipeline computes CIs (statistics.py)
        if disp == "remove":
            spec.registered = False
            spec.active = False
        counts[disp] += 1
    return counts


def redundancy_guard(registry) -> List[str]:
    """Gate-A check: no two SCORED indicators in the same (construct, subdimension)
    may share a primary input layer. Returns a list of violation messages (empty = ok).
    """
    violations: List[str] = []
    scored = registry.scored()
    seen: Dict[tuple, Dict[str, str]] = {}
    for s in scored:
        key = (s.construct, s.subdimension)
        seen.setdefault(key, {})
        for layer in s.input_layers:
            if layer in seen[key]:
                violations.append(
                    f"Redundancy: '{s.name}' and '{seen[key][layer]}' both scored in "
                    f"{key} sharing input '{layer}' (Gate A).")
            else:
                seen[key][layer] = s.name
    return violations
