"""
Indicator Contracts & Dispositions (CS-1 / CS-2 / CS-4 / CS-7)
==============================================================

Declarative table that populates the v0.2.0 indicator contract on every registered
indicator and encodes its disposition from the Phase-2 register (retain / redefine /
context / screening / remove). Applying this table is what makes ``registry.scored()``
return the lean, defensible set instead of the full registered count (45 as of
v0.2.7 -- re-check via len(registry.all()) rather than trusting a hardcoded number
here again; this docstring itself drifted stale once already).

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

from typing import Dict, List, Optional
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
    reference_type="contemporary_best_on_offer", reference_estimator="robust_z",
    disposition="retain", input_layers=[FLII_LAYER], module="conservation",
    note=("Forest realm only. v0.2.1: renamed from 'FLII' — this is a Darukaa-computed "
         "proxy (VIIRS + fragmentation), NOT the published Grantham et al. 2020 product "
         "(prior citation was corrected as a citation-integrity fix). reference_type "
         "changed from published_threshold accordingly; see ASSUMPTIONS §1.")),
 "jrc_water_persistence": dict(construct="C1_landscape", subdimension="hydrology", measurement_scale="ratio",
    reference_type="regional_distribution", reference_estimator="log_response_ratio",
    disposition="retain", input_layers=[JRC], note="Hydrology/surface-water permanence."),
 "rci": dict(construct="C1_landscape", subdimension="riparian_complexity", measurement_scale="bounded",
    reference_type="regional_distribution", reference_estimator="robust_z",
    disposition="retain", input_layers=[NDVI], module="conservation",
    note=("PROMOTED (this audit, default-to-scored strategy): own distinct subdimension -- "
         "originally shared 'hydrology' with jrc_water_persistence (already scored there), "
         "which would have averaged the two together; corrected. Citation corrected "
         "(Naiman & Decamps 1997).")),
 "riparian_ndvi_trend": dict(construct="C1_landscape", subdimension="hydrology", measurement_scale="interval",
    disposition="context", input_layers=[NDVI], note="Trend-based (correct NDVI use); contextual at cycle-1."),

 # ---------------- C2 vegetation condition ----------------
 "eii": dict(construct="C2_vegetation", subdimension="integrity", measurement_scale="bounded",
    disposition="context", input_layers=[EII_LAYER],
    note=("DEMOTED (this audit, was 'retain'): the parent band is itself the dataset "
         "provider's own hard-minimum of the 3 sub-scores (non-compensatory by "
         "construction, confirmed v0.2.2) -- scoring the 3 sub-components separately "
         "(now promoted, see below) gives the SAME worst-case-driven result but with real "
         "visibility into WHICH dimension (structure/composition/function) is actually "
         "limiting, which the single blended parent number hides. Kept as context, not "
         "removed, so the pre-blended number is still shown for reference.")),
 "eii_structural": dict(construct="C2_vegetation", subdimension="eii_structure", measurement_scale="bounded",
    reference_type="contemporary_best_on_offer", reference_estimator="robust_z",
    disposition="retain", input_layers=[EII_LAYER],
    note="PROMOTED (this audit, default-to-scored strategy): own distinct subdimension -- originally shared 'structure' with chm (already scored there), which would have averaged the two together; corrected."),
 "eii_compositional": dict(construct="C2_vegetation", subdimension="composition", measurement_scale="bounded",
    reference_type="contemporary_best_on_offer", reference_estimator="robust_z",
    disposition="retain", input_layers=[EII_LAYER],
    note=("PROMOTED (this audit): own real subdimension. Real, remaining overlap risk with "
         "bii (both proxy species-compositional intactness) is now empirical, not "
         "structural -- bii's data source was already fixed (v0.2.4) to be genuinely "
         "independent of this asset, so this is a correlation question to check once "
         "enough real runs exist, not a known double-count.")),
 "eii_functional": dict(construct="C2_vegetation", subdimension="function", measurement_scale="bounded",
    reference_type="contemporary_best_on_offer", reference_estimator="robust_z",
    disposition="retain", input_layers=[EII_LAYER],
    note="PROMOTED (this audit): own real subdimension, no longer double-counted now that the parent is context-only."),
 "ndvi": dict(construct="C2_vegetation", subdimension="structure", measurement_scale="interval",
    disposition="context", input_layers=[NDVI], note="Not ratio-scale; remove from intactness. Keep as trend/context (B1)."),
 "habitat_health": dict(construct="C2_vegetation", subdimension="structure", measurement_scale="bounded",
    disposition="context", input_layers=[NDVI], note="z-score construct; overlaps NDVI (Gate A)."),
 "bii": dict(construct="C3_fauna", subdimension="abundance_intactness", measurement_scale="bounded",
    reference_type="contemporary_best_on_offer", reference_estimator="robust_z",
    disposition="retain", input_layers=[BII_LAYER],
    note=("v0.2.4: moved C2->C3 and promoted context->scored — this is C3's real signal, "
         "closing the fauna-pillar gap (was empty). Covers abundance/compositional "
         "intactness across many taxa including birds and mammals (not fauna-exclusive — "
         "also plants/fungi/invertebrates; PREDICTS database, ~58,000 species). Fixed a "
         "real bug: was previously derived from EII's own compositional_integrity band, "
         "not independent data (see ASSUMPTIONS §9). Now uses a genuinely separate "
         "source (Impact Observatory/Vizzuality, PREDICTS-based, 100m).")),
 "pdf": dict(construct="C2_vegetation", subdimension="composition", measurement_scale="bounded",
    disposition="context", input_layers=[PDF_LAYER],
    note=("LCA-derived species-area-relationship metric (PDF = 1-(A_new/A_reference)^z; "
         "z~0.25 is the commonly-cited canonical SAR exponent, Preston 1962/MacArthur & "
         "Wilson 1967, not arbitrary despite not being pinned by project docs). "
         "STRUCTURALLY this compares a site to ITS OWN historical baseline (a temporal "
         "change metric, like forest_loss_rate), not to an ecoregion reference pool like "
         "most other C2 indicators — kept context, not run through the SEED Tier-2 "
         "cross-sectional benchmark, since that comparison basis doesn't apply here.")),
 "lai": dict(construct="C2_vegetation", subdimension="structure", measurement_scale="ratio",
    disposition="context", input_layers=["modis_lai"], note="Shares greenness with NDVI; MODIS grain too coarse for these sites."),
 "chm": dict(construct="C2_vegetation", subdimension="structure", measurement_scale="ratio",
    reference_type="contemporary_best_on_offer", reference_estimator="log_response_ratio",
    disposition="retain", input_layers=[GEDI], note="Genuinely additive: GEDI canopy height, independent of NDVI/DW cluster."),
 # aquatic condition module (only active for aquatic/mixed realm)
 "tspi": dict(construct="C2_vegetation", subdimension="water_quality", measurement_scale="interval",
    reference_type="published_threshold", reference_estimator="robust_z",
    disposition="retain", input_layers=[S2], module="aquatic",
    note=("v0.2.5: upgraded from a bare NDCI proxy to the real Carlson (1977) TSI(Chl) "
         "formula via Mishra & Mishra (2012) chlorophyll-a regression — a genuine, "
         "literature-supported trophic-state index, not a proxy. Promoted context->"
         "scored; has a real published_threshold classification (see "
         "son_score.LITERATURE_BREAKPOINTS). Aquatic module only (needs a water body).")),
 "sabf": dict(construct="C2_vegetation", subdimension="algal_bloom_frequency", measurement_scale="bounded",
    reference_type="regional_distribution", reference_estimator="robust_z",
    disposition="retain", input_layers=[S2], module="aquatic",
    note=("PROMOTED (this audit, default-to-scored strategy): given its own distinct "
         "subdimension rather than sharing 'water_quality' with the 5 other aquatic C2 "
         "indicators below -- they were all one shared subdimension before, which would "
         "AVERAGE them together if more than one were promoted at once, undermining this "
         "pipeline's non-compensatory design (one genuinely bad signal diluted by others). "
         "Distinct subdimensions preserve limiting-factor logic across all of them.")),
 "wcpi": dict(construct="C2_vegetation", subdimension="water_clarity", measurement_scale="bounded",
    reference_type="regional_distribution", reference_estimator="robust_z",
    disposition="retain", input_layers=[S2], module="aquatic",
    note="PROMOTED (this audit): own distinct subdimension, see sabf's note above for why."),
 "wsdi": dict(construct="C2_vegetation", subdimension="water_surface_dynamics", measurement_scale="bounded",
    reference_type="regional_distribution", reference_estimator="robust_z",
    disposition="retain", input_layers=[S2], module="aquatic",
    note="PROMOTED (this audit): own distinct subdimension, see sabf's note above for why."),
 "hsas": dict(construct="C2_vegetation", subdimension="habitat_suitability", measurement_scale="bounded",
    reference_type="regional_distribution", reference_estimator="robust_z",
    disposition="retain", input_layers=["edna_points"], module="aquatic",
    note=("PROMOTED (this audit, default-to-scored strategy): own distinct subdimension. "
         "Real, honest caveat retained: this is a Darukaa-constructed composite (see "
         "indicators/__init__.py citation), not yet eDNA-validated -- scored now under the "
         "'score by default, refine with real evidence later' strategy, not because "
         "validation is complete.")),
 "edpp": dict(construct="C2_vegetation", subdimension="edna_persistence", measurement_scale="bounded",
    reference_type="regional_distribution", reference_estimator="robust_z",
    disposition="retain", input_layers=[S2], module="aquatic",
    note="PROMOTED (this audit): own distinct subdimension, see sabf's note above for why. Darukaa composite, environmental drivers literature-supported (see citation), formula itself not externally validated."),
 "mspl": dict(construct="C2_vegetation", subdimension="microbial_stress", measurement_scale="bounded",
    reference_type="regional_distribution", reference_estimator="robust_z",
    disposition="retain", input_layers=[S2], module="aquatic",
    note="PROMOTED (this audit): own distinct subdimension, see sabf's note above for why. Darukaa composite, see citation."),
 "shdi": dict(construct="C2_vegetation", subdimension="water_quality", measurement_scale="ratio",
    disposition="context", input_layers=[S2], module="aquatic", note="Scalar-only morphometry; not cross-site comparable. Real structural reason (not caution) to keep context -- Tier2 needs a spatially benchmarkable value, which this single-number-per-site metric cannot provide."),

 # ---------------- C3 faunal condition ----------------
 "flagship_habitat": dict(construct="C3_fauna", subdimension="habitat_suitability", measurement_scale="bounded",
    disposition="context", input_layers=[NDVI], note="No named flagship species; weights unjustified (G3). Demote unless redesigned around a named species."),
 "shi": dict(construct="C3_fauna", subdimension="habitat_intactness", measurement_scale="bounded",
    disposition="context", input_layers=["mol_api"], reference_type="regional_distribution",
    reference_estimator="robust_z", note=("OD-12 placeholder: real, defensible metric once Map of Life API "
        "access is confirmed (no simple GEE asset exists — checked directly, not assumed). Kept at 'context' "
        "disposition rather than 'retain' deliberately: the indicator's own requires=['mol_api_credentials'] "
        "(see indicators/__init__.py) is what actually gates scoring, so promoting disposition here before "
        "extract_shi is genuinely implemented would be premature.")),
 "endemic_richness": dict(construct="C3_fauna", subdimension="representation", measurement_scale="ratio",
    disposition="screening", input_layers=[IUCN], note=("Range-map derived -> screening, not observation. "
        "Area-normalised to species-per-100km2 (v0.2.7) so the raw count is at least comparable across "
        "differently-sized sites/projects, but this does not change disposition: real, industry-documented "
        "limitation (IBAT/STAR's own guidance: 'Estimated STAR has a 5km2 resolution, not granular enough "
        "to offer much distinction at the level of a farm or asset') confirms this class of range-map metric "
        "cannot discriminate condition within a single project's own EMUs. Genuine site-level fauna "
        "discrimination requires in-situ data (camera trap, eDNA) via change.py, not this pathway.")),
 "endemic_plant_richness": dict(construct="C3_fauna", subdimension="representation", measurement_scale="ratio",
    disposition="screening", input_layers=[IUCN], note="Range-map derived -> screening.",),
 "threatened_richness": dict(construct="C3_fauna", subdimension="representation", measurement_scale="ratio",
    disposition="screening", input_layers=[IUCN], note=("Identical across co-located sites -> zero "
        "discrimination (F1). Screening-only priority list. Area-normalised to species-per-100km2 (v0.2.7) "
        "for cross-project comparability of the priority list itself — does not resolve F1, which is a "
        "structural range-map-resolution limitation, not a units problem. See endemic_richness's note.")),
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
 "sdi": dict(construct="C4_pressure", subdimension="shoreline_disturbance", measurement_scale="bounded",
    reference_type="regional_distribution", reference_estimator="robust_z",
    disposition="retain", input_layers=[S2], module="aquatic",
    note=("PROMOTED (this audit, default-to-scored strategy): given its own distinct "
         "subdimension rather than sharing 'direct_pressure' with light_pollution (already "
         "scored there) -- promoting into the same subdimension would have suddenly "
         "averaged it with an existing, correctly-functioning scored indicator.")),
 "stsi": dict(construct="C4_pressure", subdimension="direct_pressure", measurement_scale="bounded",
    disposition="context", input_layers=[MODIS_LST], note="Site-relative normalisation only; not cross-site comparable."),
 "iri": dict(construct="C4_pressure", subdimension="invasive_risk", measurement_scale="bounded",
    reference_type="regional_distribution", reference_estimator="robust_z",
    disposition="retain", input_layers=[NDVI],
    note=("PROMOTED (this audit, default-to-scored strategy): own distinct subdimension "
         "(same reasoning as sdi -- avoids averaging with light_pollution). Real, honest "
         "caveat retained: Darukaa-constructed composite (see indicators/__init__.py "
         "citation), field-validation still pending -- scored now under 'score by default, "
         "refine with real evidence later', not because validation is complete.")),
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
        # REAL FIX: applicable_realms is the authoritative realm-filtering
        # gate (see registry.py's field docstring for why module alone
        # wasn't safe to use directly). Derived here from the SAME
        # contract-table module tag, as one single source of truth,
        # rather than set separately in indicators/__init__.py for these
        # contract-driven indicators too. An explicit "applicable_realms"
        # key in the contract entry overrides this default derivation,
        # for the rare case a module="aquatic" indicator is still
        # genuinely meaningful on land (or vice versa) -- checked
        # directly, none currently need that override, but the escape
        # hatch is real, not hypothetical busywork.
        if "applicable_realms" in c:
            spec.applicable_realms = tuple(c["applicable_realms"])
        elif spec.module == "aquatic":
            spec.applicable_realms = ("aquatic", "mixed")
        # else: leave whatever indicators/__init__.py's own registration
        # set (defaults to all realms if that file didn't restrict it).
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


# Client-activation safety tiers (v0.2.1). "Does the client asking for an indicator to
# be scored make it defensible to score?" depends entirely on WHY it wasn't scored:
#   context   -> usually a parsimony/redundancy choice, not a construct flaw. Promotable.
#   screening -> the construct itself has a real, documented limitation for scoring
#     (e.g. zero site-discrimination, modelled-not-responsive). Promotable ONLY with an
#     explicit force flag, and the report carries the original caveat permanently so
#     nobody downstream mistakes it for a vetted metric.
#   remove    -> a documented, unrepairable ARITHMETIC/logical flaw (e.g. CERI: averaging
#     Red List weights means adding a common species LOWERS risk). Never promotable this
#     way — scoring it would be presenting a broken construct as a number. If a client
#     genuinely needs this dimension covered, that requires a methodology fix, not a
#     config flip; raise it as a design question, not an activation request.
_PROMOTABLE_FREELY = {"context"}
_PROMOTABLE_WITH_FORCE = {"screening"}
_NEVER_PROMOTABLE = {"remove"}


def request_activation(registry, indicator_names: List[str],
                       force: Optional[List[str]] = None) -> Dict[str, Dict]:
    """Client-facing indicator activation. Promotes named indicators to scored status
    where the science allows it; refuses (with the specific reason) where it doesn't.

    indicator_names : indicators to activate beyond the Darukaa default scored set.
    force           : subset of indicator_names to promote even if disposition is
                      "screening" (never overrides "remove" — see tiers above).

    Returns {name: {"status": "promoted"|"refused_screening"|"refused_removed"|
                    "not_found", "reason": str}}. Every promotion sets
    spec.client_override=True and a note, so it's visible in the final report — an
    activated indicator is never indistinguishable from a Darukaa-default one.
    """
    force = set(force or [])
    results: Dict[str, Dict] = {}

    for name in indicator_names:
        spec = registry.get(name) if name in registry else None
        if spec is None:
            results[name] = {"status": "not_found",
                             "reason": f"'{name}' is not a registered indicator name."}
            continue

        disp = spec.metadata.get("disposition", "?")

        if disp in _NEVER_PROMOTABLE:
            results[name] = {"status": "refused_removed", "reason": (
                f"'{name}' has a documented, unrepairable construct flaw "
                f"({spec.metadata.get('contract_note', 'see contracts.py')}). "
                f"Activating it would present a broken metric as a number — this "
                f"requires a methodology fix, not an activation override.")}
            continue

        if disp in _PROMOTABLE_WITH_FORCE and name not in force:
            results[name] = {"status": "refused_screening", "reason": (
                f"'{name}' is screening-tier: {spec.metadata.get('contract_note', '')} "
                f"To activate anyway, add '{name}' to the `force` list — every appearance "
                f"of it in the report will permanently carry this caveat.")}
            continue

        # Promotable: either "context" (freely), a scored indicator already (no-op,
        # explicit confirmation), or "screening" with force explicitly given.
        spec.active = True
        spec.evidence_tier = "baseline" if spec.evidence_tier not in ("baseline", "monitoring") else spec.evidence_tier
        if not spec.reference_type:
            spec.reference_type = "contemporary_best_on_offer"  # generic, honest default
        if not spec.uncertainty_method or spec.uncertainty_method == "none":
            spec.uncertainty_method = "bootstrap_ci"
        spec.client_override = True
        spec.client_override_note = (
            f"Activated by explicit client request (original disposition: {disp}"
            f"{' — screening caveat: ' + spec.metadata.get('contract_note','') if disp == 'screening' else ''})."
        )
        results[name] = {"status": "promoted", "reason": spec.client_override_note}

    return results


def request_deactivation(registry, indicator_names: List[str]) -> Dict[str, Dict]:
    """Client-facing indicator DEACTIVATION — the other half of the bidirectional
    control. A client may want fewer indicators scored than the Darukaa default (e.g. a
    quick screening pass, or excluding a construct their project archetype doesn't need)
    just as legitimately as they may want more (request_activation above).

    Unlike activation, deactivation carries no scientific safety tiers to enforce —
    turning an indicator OFF can never make a report less defensible, only smaller. Any
    currently-active indicator (default-scored or previously client-activated) can be
    deactivated. The one thing this does NOT allow: deactivating something that was never
    active in the first place (a no-op, reported as such, not an error).

    Every deactivation is recorded with the same client_override / client_override_note
    visibility as an activation, so a report always shows the FULL story of how the
    scored set diverged from the Darukaa default in either direction — never silent.
    """
    results: Dict[str, Dict] = {}
    for name in indicator_names:
        spec = registry.get(name) if name in registry else None
        if spec is None:
            results[name] = {"status": "not_found",
                             "reason": f"'{name}' is not a registered indicator name."}
            continue
        if not spec.active:
            results[name] = {"status": "already_inactive",
                             "reason": f"'{name}' was already inactive; no change made."}
            continue

        default_disposition = spec.metadata.get("disposition", "?")
        spec.active = False
        spec.client_override = True
        spec.client_override_note = (
            f"Deactivated by explicit client request (Darukaa default disposition: "
            f"{default_disposition}). Not scored this run even though eligible.")
        results[name] = {"status": "deactivated", "reason": spec.client_override_note}

    return results


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
