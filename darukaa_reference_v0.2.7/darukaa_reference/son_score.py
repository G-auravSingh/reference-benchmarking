"""
SoN Condition Score & Concern Classification (v0.2.4)
======================================================

The client/dashboard/TNFD-module-facing product layer. Everything here is built on TOP
of the existing profile-first engine in scoring.py — it does not change how a site's
profile, condition roll-up, or pressure headline are computed; it exposes them as a
single number and a declared class label for consumers (a dashboard widget, a TNFD
State-of-Nature input) that need exactly that, rather than the full profile.

WHY THIS EXISTS (and why it didn't exist before): earlier revisions of this pipeline
deliberately did NOT produce a universal single score or concern label, because the
composite this methodology replaced applied arbitrary universal thresholds to raw,
incommensurable units (a canopy-cover-% and an NDVI value do not mean the same thing at
the same number) and hid degradation behind compensatory averaging. Neither problem
actually blocks a single score: every SCORED indicator is already normalised onto a
common 0-1 "distance from its own ecoregion reference" scale (0.5 = at reference) BEFORE
this module ever sees it, and the roll-up feeding it is already the non-compensatory
geometric mean with its minimum component always attached. Applying a declared band-set
to that already-comparable scale is not the same mistake as applying one to raw units.

WHAT THIS PRODUCES
------------------
- overall_condition: one 0-1 score (= the condition roll-up), one class label (VL-VH,
  5 equal bands by default), the minimum component that set it, the sensitivity flag,
  and a confidence flag stating how many of the 4 core pillars actually had data.
- overall_pressure: the same, computed on the pressure axis, KEPT COMPLETELY SEPARATE.
  A dashboard should show two badges, or two numbers feeding two different places in a
  risk model — never one blended condition-and-pressure number.
- per-indicator classification: two modes, selectable per indicator —
    "reference_relative" (default): bands the indicator's own normalised 0-1 benchmark
      (same declared 5-band split as the overall score). Always available, since every
      scored indicator already has this value.
    "literature_anchored": bands the indicator's RAW site value using a published
      ecological breakpoint, where one exists that is defensibly scale/ecoregion-
      independent (see LITERATURE_BREAKPOINTS below) — shown ALONGSIDE the reference-
      relative classification as additional context, never replacing it. Most
      indicators do not have a defensible universal breakpoint (this was confirmed
      metric-by-metric during a document review — see CHANGELOG v0.2.3) and fall back
      to reference_relative only.

THIS DOES NOT EXIST YET, ON PURPOSE: a formula for blending overall_condition and
overall_pressure into one number. They are kept structurally separate by design (see
AGGREGATION_WALKTHROUGH.md). If a consumer (e.g. a TNFD risk-aggregation module) wants
to combine them, that combination belongs in that consumer, as an explicit, documented
step of ITS OWN methodology — not silently invented here.
"""
from __future__ import annotations

from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Declared default classification (product convention, NOT a claim of ecological
# universality — this is the [X] fallback used whenever no literature-anchored
# breakpoint applies). Five equal-width bands on the normalised 0-1 scale, symmetric
# around 0.5 = "at reference". Oriented so higher score = lower concern.
# ---------------------------------------------------------------------------
DEFAULT_BANDS = [
    (0.80, 1.01, "Very Low"),
    (0.60, 0.80, "Low"),
    (0.40, 0.60, "Moderate"),
    (0.20, 0.40, "High"),
    (0.00, 0.20, "Very High"),
]

CONCERN_ORDER = ["Very Low", "Low", "Moderate", "High", "Very High"]

# ---------------------------------------------------------------------------
# Literature-anchored RAW-VALUE breakpoints (v0.2.4). Populated ONLY where a
# document review (v0.2.3, see CHANGELOG) found a breakpoint argued in the literature
# to be structurally/geometrically general rather than climate- or spectrally-driven
# (which do NOT transfer across ecoregions — see natural_habitat's own reviewed
# citations vs NDVI's, which explicitly disclaims universal thresholds). This list is
# intentionally short; most indicators have no defensible universal raw breakpoint and
# correctly fall back to reference_relative only. Bands are on the RAW site value, in
# the indicator's own native units, oriented low-to-high or high-to-low per indicator.
# Each entry: list of (lo, hi, label) ascending by raw value, plus the source note.
# ---------------------------------------------------------------------------
LITERATURE_BREAKPOINTS: Dict[str, Dict] = {
    "natural_habitat": {
        "unit": "fraction natural habitat cover (0-1)",
        "bands": [  # higher cover = lower concern
            (0.70, 1.01, "Very Low"),
            (0.50, 0.70, "Low"),
            (0.30, 0.50, "Moderate"),
            (0.10, 0.30, "High"),
            (0.00, 0.10, "Very High"),
        ],
        "source": ("Andren (1994); Fahrig (2002); Radford et al. (2005) — fragmentation "
                  "effects intensify below ~30% habitat cover; ~60-70% landscapes remain "
                  "relatively intact (Villard & Metzger 2014). Argued as structurally "
                  "general (patch-geometry-driven), not ecoregion-specific — unlike "
                  "spectral/climate indices. 50-70% and 10-30% are project-specific "
                  "interpolations around the two literature-anchored breakpoints (30%, "
                  "60-70%), not independently literature-sourced themselves."),
    },
    "tspi": {
        "unit": "Carlson Trophic State Index (dimensionless, typically 0-100+)",
        "bands": [  # lower TSI (oligotrophic) = lower concern; higher = more eutrophic
            (-999, 30, "Very Low"),
            (30, 40, "Low"),
            (40, 50, "Moderate"),
            (50, 70, "High"),
            (70, 999, "Very High"),
        ],
        "source": ("Carlson (1977) Limnol. Oceanogr. 22:361-369 — the original TSI "
                  "classification (oligotrophic <40, mesotrophic 40-50, eutrophic 50-70, "
                  "hypereutrophic >70), with a <30 'ultra-oligotrophic' sub-band commonly "
                  "used in later limnology literature. Unlike ecoregion-dependent land "
                  "indices, TSI is explicitly designed as a universal lentic-water "
                  "classification — this is one of the few indicators where the "
                  "literature-anchored view is arguably MORE authoritative than the "
                  "reference-relative one, not merely supplementary to it."),
    },
}


def classify(value: Optional[float], bands: List[tuple] = None) -> Optional[str]:
    """Map a value onto a 5-band label using the given (lo, hi, label) band list.
    Defaults to DEFAULT_BANDS (normalised 0-1 scale) if none given. Bands are checked
    in the given order, first match wins (lo <= value < hi) — the caller is responsible
    for giving the outermost band a generously high/low bound so real values are always
    caught (DEFAULT_BANDS uses 1.01; LITERATURE_BREAKPOINTS entries use ±999)."""
    if value is None:
        return None
    bands = bands or DEFAULT_BANDS
    for lo, hi, label in bands:
        if lo <= value < hi:
            return label
    return None


def classify_indicator(name: str, normalized_score: Optional[float],
                       raw_value: Optional[float] = None) -> Dict:
    """Classify one indicator both ways: always reference_relative (if the normalised
    score is available), plus literature_anchored where a defensible breakpoint exists
    for this indicator AND a raw value was supplied. Never silently prefers one over
    the other — both are returned, clearly labelled by basis, so a report can show
    either or both."""
    out = {
        "reference_relative": {
            "class": classify(normalized_score, DEFAULT_BANDS),
            "basis": "normalised distance from this site's own ecoregion reference "
                    "(0.5=at reference); declared 5-band product convention",
        },
        "literature_anchored": None,
    }
    lit = LITERATURE_BREAKPOINTS.get(name)
    if lit and raw_value is not None:
        out["literature_anchored"] = {
            "class": classify(raw_value, lit["bands"]),
            "basis": lit["source"],
            "unit": lit["unit"],
            "raw_value": raw_value,
        }
    return out


def _confidence(n_assessed: int, n_total: int) -> Dict:
    frac = (n_assessed / n_total) if n_total else 0.0
    if frac >= 0.75:
        level = "high"
    elif frac >= 0.5:
        level = "medium"
    elif frac > 0:
        level = "low"
    else:
        level = "insufficient"
    return {"level": level, "n_pillars_assessed": n_assessed, "n_pillars_total": n_total,
           "note": f"{n_assessed} of {n_total} core pillars (C1-C4) had at least one "
                  f"scored indicator with data this run."}


def overall_condition(profile: Dict) -> Dict:
    """The single condition score + class + confidence for this site's profile.

    profile : the dict returned by scoring.build_site_profile() for one site (or one
    project, for the multi-tile case — the input shape is identical either way).
    """
    cond = profile.get("condition", {}) or {}
    score = cond.get("rollup")
    sens = cond.get("sensitivity", {}) or {}

    n_assessed = len([c for c in profile.get("components", {}).values()
                      if c.get("headline") is not None])
    conf = _confidence(n_assessed, 3)  # C1, C2, C3 are the 3 condition components

    return {
        "score": round(score, 4) if score is not None else None,
        "concern_class": classify(score, DEFAULT_BANDS),
        "minimum_component": cond.get("minimum_component"),
        "minimum_component_score": cond.get("minimum"),
        "stable": sens.get("stable"),
        "confidence": conf,
        "framing": cond.get("framing"),
    }


def overall_pressure(profile: Dict) -> Dict:
    """The single pressure score + class — kept structurally separate from condition.
    Never combine this with overall_condition() inside this pipeline; that decision
    belongs to whatever consumes both (see module docstring)."""
    press = profile.get("pressure", {}) or {}
    score = press.get("headline")
    return {
        "score": round(score, 4) if score is not None else None,
        "concern_class": classify(score, DEFAULT_BANDS),
        "limiting_subdimension": press.get("limiting_subdimension"),
        "note": ("Pressure is deliberately NOT blended into overall_condition. Kept "
                "separate so a consumer (dashboard, risk model) can show or use both "
                "independently — see AGGREGATION_WALKTHROUGH.md."),
    }


def son_summary(profile: Dict) -> Dict:
    """The complete client/dashboard-facing summary for one site or project profile:
    both badges, matrix cell, and confidence — the thing a product team binds a
    dashboard to."""
    return {
        "overall_condition": overall_condition(profile),
        "overall_pressure": overall_pressure(profile),
        "matrix_cell": profile.get("matrix_cell"),
    }
