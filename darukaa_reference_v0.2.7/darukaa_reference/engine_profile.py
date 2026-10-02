"""
engine_profile.py -- profile-first aggregation from ENGINE scores (v0.2.9 Phase 5, pipeline layer)
=================================================================================================

`scoring.build_site_profile` normalises a signed benchmark with a logistic. The v0.2.8 engine already produced a 0-1 `score` (by reference percentile for some
indicators, by the same logistic for others), and normalising a percentile again is silently wrong (0.745 would become 0.592). This function takes the engine score
AS IS and never normalises anything; it then uses the unchanged legacy roll-up helpers (`component_score`, `condition_rollup`, `sensitivity_report`,
`matrix_cell`) imported from `scoring.py`, which is part of the frozen engine closure and is byte-identical to the frozen tag.

It lives here, not in `scoring.py`, so that the executable engine closure stays provably unchanged. Equivalence with the legacy function wherever the two are
comparable is a test (tests/test_engine_profile.py).
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

import numpy as np

from darukaa_reference import scoring

logger = logging.getLogger(__name__)

_COND = ("C1_landscape", "C2_vegetation", "C3_fauna")


def build_profile(items: List[Dict], weights: Optional[Dict[str, float]] = None) -> Dict:
    """items: [{name, construct, subdimension, score}] where `score` is the engine's 0-1 score. An item without a score is skipped, never normalised, never 0."""
    by_comp: Dict[str, Dict[str, list]] = {}
    press: Dict[str, list] = {}
    for b in items:
        s = b.get("score")
        if s is None:
            continue
        if b["construct"] == "C4_pressure":
            press.setdefault(b.get("subdimension", "pressure"), []).append(s)
        elif b["construct"] in _COND:
            by_comp.setdefault(b["construct"], {}).setdefault(b.get("subdimension", "_"), []).append(s)
        else:
            logger.warning("Score with unrecognised construct %r (expected one of %s or 'C4_pressure') - skipped, not folded into the condition roll-up.", b["construct"], _COND)
    comp_out, comp_headlines = {}, {}
    for comp, subs in by_comp.items():
        cs = scoring.component_score({k: float(np.mean(v)) for k, v in subs.items()})
        comp_out[comp] = cs
        comp_headlines[comp] = cs["headline"]
    condition = scoring.condition_rollup(comp_headlines, weights)
    condition["sensitivity"] = scoring.sensitivity_report(comp_headlines)
    press_sub = {k: float(np.mean(v)) for k, v in press.items()}
    pressure = scoring.component_score(press_sub) if press_sub else {"headline": None, "profile": {}}
    return {"components": comp_out, "condition": condition, "pressure": pressure, "matrix_cell": scoring.matrix_cell(condition.get("rollup"), pressure.get("headline"))}
