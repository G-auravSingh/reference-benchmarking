"""Scores, intervals, confidence and aggregation (offline; no Earth Engine).

Response functions (catalogue reference types)
---------------------------------------------
* ``reference_condition`` (condition metrics, higher is better):
  score = 100 x min(observed / reference median, 1). Reference median <= 0 is invalid.
* ``regional_context`` (pressure and loss rates, lower is better; decision 4, D-23-9):
  score = 100 x (1 - clamp((obs - ref) / (worst - ref), 0, 1)), ref = regional median,
  worst = regional p95; if the regional distribution is degenerate (worst <= ref) the
  contract's upper value bound is used; if that is also unavailable the metric is not
  scored. For higher-is-better regional metrics the mirror form is used.
* ``low_pressure`` (P4 pressure, lower is better; option B, D-25-1): the same bounded
  function, but ref = median of *low-pressure* blocks in the same ring and ecoregion,
  selected by their 2020 natural-ecosystem share (ForTy/SBTN), never by a pressure
  metric, so the reference is not circular with what is scored; worst = p95 of all
  ring blocks. The all-land regional score (option A) is kept as a context figure.
* ``natural_scale``: the value on its 0-100 scale, no reference ratio.

Intervals come from a spatial-block bootstrap of the reference sample: blocks are
resampled with replacement, the reference statistics are recomputed, and the score
is recomputed for every draw. Draws are carried through aggregation draw-by-draw, so
pillar, headline and project scores get intervals from the same draws.

Aggregation (unchanged rules unless a decision says otherwise)
--------------------------------------------------------------
metric -> component: geometric mean; component -> pillar: minimum (limiting factor),
gated by ``min_metrics_per_pillar`` and ``min_components_per_pillar``; condition
headline: geometric mean of P1 and P2, plus P3 when P3 is scored (D-23-10); pressure
(P4) is reported separately and never enters the condition headline. A component
scoring exactly 0 is flagged (decision 4). Sites roll up to the project by
area-weighted arithmetic mean, labelled with contributing count and area share (D-23-6).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from . import catalogue as cat
from .measurement import Measurement

CONCERN_BANDS = (20.0, 40.0, 60.0, 80.0)
CONCERN_LABELS = ("Very High", "High", "Moderate", "Low", "Very Low")  # concern for a 0-100 score


def concern_label(score: Optional[float]) -> Optional[str]:
    if score is None or not math.isfinite(score):
        return None
    for upper, label in zip(CONCERN_BANDS, CONCERN_LABELS):
        if score < upper:
            return label
    return CONCERN_LABELS[-1]


def concern_0_10(score: Optional[float]) -> Optional[float]:
    """Documented mapping to the 0-10 client concern convention (higher = worse; D-22-1)."""
    if score is None:
        return None
    return round(10.0 * (1.0 - max(0.0, min(100.0, score)) / 100.0), 2)


# ----------------------------------------------------------------- reference sample
@dataclass
class ReferenceSample:
    metric: str
    reference_type: str
    values: np.ndarray
    blocks: np.ndarray
    stratum: str = ""
    method: str = ""
    approved: bool = True
    min_n: int = 30
    min_blocks: int = 5
    notes: str = ""

    def __post_init__(self):
        v = np.asarray(self.values, dtype=float)
        b = np.asarray(self.blocks)
        if v.shape != b.shape:
            raise ValueError("values and blocks must have the same length")
        keep = np.isfinite(v)
        self.values, self.blocks = v[keep], b[keep]

    @property
    def n(self) -> int:
        return int(self.values.size)

    @property
    def n_blocks(self) -> int:
        return int(np.unique(self.blocks).size)

    @property
    def usable(self) -> bool:
        return self.approved and self.n >= self.min_n and self.n_blocks >= self.min_blocks

    def status(self) -> str:
        if not self.approved:
            return "reference_not_approved"
        if self.n < self.min_n or self.n_blocks < self.min_blocks:
            return "reference_insufficient"
        return "ok"


def block_bootstrap(sample: ReferenceSample, n_boot: int = 200, seed: int = 20261023) -> Dict[str, np.ndarray]:
    """Spatial-block bootstrap of the reference median, p05 and p95."""
    rng = np.random.default_rng(seed)
    ids = np.unique(sample.blocks)
    groups = [sample.values[sample.blocks == i] for i in ids]
    med, p05, p95 = np.empty(n_boot), np.empty(n_boot), np.empty(n_boot)
    for k in range(n_boot):
        pick = rng.integers(0, len(groups), len(groups))
        vals = np.concatenate([groups[i] for i in pick])
        med[k] = np.median(vals)
        p05[k], p95[k] = np.percentile(vals, [5, 95])
    return {"median": med, "p05": p05, "p95": p95}


# ----------------------------------------------------------------- response functions
def reference_attainment(obs: float, ref_median: float, direction: str) -> Optional[float]:
    if direction != "higher_is_better":
        raise ValueError("reference_condition scoring is defined for higher-is-better metrics")
    if ref_median is None or not math.isfinite(ref_median) or ref_median <= 0:
        return None
    return float(100.0 * min(max(obs / ref_median, 0.0), 1.0))


def bounded_regional(obs: float, ref: float, worst: Optional[float], direction: str,
                     fallback_worst: Optional[float] = None) -> Tuple[Optional[float], str]:
    """Decision 4 bounded response. Returns (score, basis)."""
    basis = "regional_p95"
    if direction == "lower_is_better":
        if worst is None or not math.isfinite(worst) or worst <= ref:
            worst, basis = fallback_worst, "contract_value_range_max"
        if worst is None or not math.isfinite(worst) or worst <= ref:
            return None, "degenerate_reference"
        x = (obs - ref) / (worst - ref)
    elif direction == "higher_is_better":
        if worst is None or not math.isfinite(worst) or worst >= ref:
            worst, basis = fallback_worst, "contract_value_range_min"
        if worst is None or not math.isfinite(worst) or worst >= ref:
            return None, "degenerate_reference"
        x = (ref - obs) / (ref - worst)
    else:
        raise ValueError("regional_context needs a direction")
    return float(100.0 * (1.0 - min(max(x, 0.0), 1.0))), basis


def natural_scale(obs: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return float(100.0 * min(max((obs - lo) / (hi - lo), 0.0), 1.0))


# ----------------------------------------------------------------- metric scores
@dataclass
class MetricScore:
    metric: str
    unit_id: str
    pillar: str
    component: str
    role: str
    value: Optional[float]
    score: Optional[float]
    interval: Tuple[Optional[float], Optional[float]]
    draws: Optional[np.ndarray]
    reference_status: str
    reference_value: Optional[float]
    reference_worst: Optional[float]
    reference_n: Optional[int]
    reference_blocks: Optional[int]
    basis: str
    confidence: Optional[str]
    confidence_reasons: List[str] = field(default_factory=list)
    context_score: Optional[float] = None     # all-land regional comparison (option A), context only
    absolute_class: Optional[str] = None      # published class where one exists (option C), context only

    def row(self) -> Dict[str, object]:
        return {
            "metric": self.metric, "unit_id": self.unit_id, "pillar": self.pillar, "component": self.component,
            "role": self.role, "value": self.value, "score_0_100": self.score,
            "score_low": self.interval[0], "score_high": self.interval[1],
            "concern": concern_label(self.score), "concern_0_10": concern_0_10(self.score),
            "reference_status": self.reference_status, "reference_value": self.reference_value,
            "reference_worst": self.reference_worst, "reference_n": self.reference_n,
            "reference_blocks": self.reference_blocks, "basis": self.basis,
            "confidence": self.confidence, "confidence_reasons": "; ".join(self.confidence_reasons),
            "score_vs_surroundings": self.context_score, "absolute_class": self.absolute_class,
        }


def _interval(draws: Optional[np.ndarray]) -> Tuple[Optional[float], Optional[float]]:
    if draws is None or draws.size == 0 or not np.all(np.isfinite(draws)):
        return (None, None)
    return (float(np.percentile(draws, 5)), float(np.percentile(draws, 95)))


def confidence_rating(m: Measurement, contract: cat.MetricContract, interval, ref: Optional[ReferenceSample],
                      max_interval_width: float = 20.0, min_ref_blocks_high: int = 10) -> Tuple[str, List[str]]:
    """High / Medium / Low, reported beside the score and never blended into it.

    Darukaa rule [DARUKAA]; the idea of pairing every score with an evidence-strength
    rating follows Earthly's public description of indicator confidence [VENDOR].
    One downgrade per weakness: context-scale support, small reference, wide interval,
    period gap over one year, pressure-modelled source.
    """
    reasons = []
    if not m.site_resolved:
        reasons.append(f"context-scale value (buffer {m.context_buffer_m:.0f} m)")
    if ref is not None and ref.n_blocks < min_ref_blocks_high:
        reasons.append(f"reference has {ref.n_blocks} spatial blocks")
    lo, hi = interval
    if lo is not None and hi is not None and hi - lo > max_interval_width:
        reasons.append(f"interval width {hi - lo:.1f} points")
    if m.period_gap_years > 1:
        reasons.append(f"data {m.period_gap_years:.0f} years from assessment window")
    if contract.pressure_modelled:
        reasons.append("pressure-modelled source")
    level = "High" if not reasons else ("Medium" if len(reasons) == 1 else "Low")
    return level, reasons


GHM_CLASSES = ((0.1, "low"), (0.4, "moderate"), (0.7, "high"), (float("inf"), "very high"))


def ghm_class(value: Optional[float]) -> Optional[str]:
    """Human-modification class (Kennedy et al. 2019, Glob Change Biol 25:811) [ACAD]."""
    if value is None:
        return None
    for upper, label in GHM_CLASSES:
        if value <= upper:
            return f"{label} (gHM; Kennedy et al. 2019)"
    return None


def score_metric(m: Measurement, role: str, ref: Optional[ReferenceSample], n_boot: int = 200,
                 seed: int = 20261023, worst_ref: Optional[ReferenceSample] = None) -> MetricScore:
    c = cat.get(m.metric)
    base = dict(metric=m.metric, unit_id=m.unit_id, pillar=c.pillar, component=c.component, role=role, value=m.value)
    empty = dict(score=None, interval=(None, None), draws=None, reference_value=None, reference_worst=None,
                 reference_n=ref.n if ref is not None else None, reference_blocks=ref.n_blocks if ref is not None else None,
                 confidence=None)
    if role != "scored":
        return MetricScore(**base, **empty, reference_status="not_scored_role", basis="")
    if not m.measured_valid:
        return MetricScore(**base, **empty, reference_status="no_valid_measurement", basis=m.status)
    if not c.can_score:
        return MetricScore(**base, **empty, reference_status="metric_not_scoreable", basis="")
    obs = float(m.value)
    if c.reference_type == "natural_scale":
        lo, hi = c.value_range
        s = natural_scale(obs, lo if lo is not None else 0.0, hi if hi is not None else 100.0)
        draws = np.full(n_boot, s)
        conf, reasons = confidence_rating(m, c, (s, s), None)
        return MetricScore(**base, score=s, interval=(s, s), draws=draws, reference_status="natural_scale",
                           reference_value=None, reference_worst=None, reference_n=None, reference_blocks=None,
                           basis=f"natural scale {c.value_range}", confidence=conf, confidence_reasons=reasons)
    if ref is None:
        return MetricScore(**base, **empty, reference_status="reference_missing", basis="")
    if not ref.usable:
        return MetricScore(**base, **empty, reference_status=ref.status(), basis="")
    boot = block_bootstrap(ref, n_boot, seed)
    point_ref = float(np.median(ref.values))
    point_worst = float(np.percentile(ref.values, 95))
    if c.reference_type == "reference_condition":
        point = reference_attainment(obs, point_ref, c.direction)
        draws = np.array([reference_attainment(obs, r, c.direction) if r > 0 else np.nan for r in boot["median"]], dtype=float)
        basis, worst = "attainment of reference median", None
    elif c.reference_type == "regional_context":
        fallback = c.value_range[1] if c.direction == "lower_is_better" else c.value_range[0]
        if c.direction == "higher_is_better":
            point_worst = float(np.percentile(ref.values, 5))
            boot_worst = boot["p05"]
        else:
            boot_worst = boot["p95"]
        point, basis = bounded_regional(obs, point_ref, point_worst, c.direction, fallback)
        draws = np.array([bounded_regional(obs, r, w, c.direction, fallback)[0] for r, w in zip(boot["median"], boot_worst)], dtype=float)
        worst = point_worst
    elif c.reference_type == "low_pressure":
        if c.direction != "lower_is_better":
            raise ValueError("low_pressure scoring is defined for lower-is-better metrics")
        if worst_ref is None or not worst_ref.usable:
            return MetricScore(**base, **empty, reference_status="regional_distribution_missing", basis="")
        wboot = block_bootstrap(worst_ref, n_boot, seed + 1)
        point_worst = float(np.percentile(worst_ref.values, 95))
        fallback = c.value_range[1]
        point, basis = bounded_regional(obs, point_ref, point_worst, c.direction, fallback)
        basis = f"low-pressure reference median; worst = {basis.replace('regional_p95', 'all-ring p95')}"
        draws = np.array([bounded_regional(obs, r, w, c.direction, fallback)[0] for r, w in zip(boot["median"], wboot["p95"])], dtype=float)
        worst = point_worst
    else:
        return MetricScore(**base, **empty, reference_status="no_reference_type", basis="")
    if point is None:
        return MetricScore(**base, **empty, reference_status="reference_invalid", basis=basis)
    interval = _interval(draws)
    conf, reasons = confidence_rating(m, c, interval, ref)
    return MetricScore(**base, score=point, interval=interval, draws=draws, reference_status="ok",
                       reference_value=point_ref, reference_worst=worst, reference_n=ref.n,
                       reference_blocks=ref.n_blocks, basis=basis, confidence=conf, confidence_reasons=reasons)


# ----------------------------------------------------------------- aggregation
def _geomean_draws(arrs: Sequence[np.ndarray]) -> np.ndarray:
    stack = np.vstack(arrs)
    if np.any(stack <= 0):
        out = np.where(np.any(stack <= 0, axis=0), 0.0, np.exp(np.mean(np.log(np.clip(stack, 1e-12, None)), axis=0)))
        return out
    return np.exp(np.mean(np.log(stack), axis=0))


def _geomean_point(values: Sequence[float]) -> float:
    vals = [float(v) for v in values]
    if any(v <= 0 for v in vals):
        return 0.0
    return float(math.prod(vals) ** (1.0 / len(vals)))


@dataclass
class PillarResult:
    unit_id: str
    pillar: str
    score: Optional[float]
    interval: Tuple[Optional[float], Optional[float]]
    draws: Optional[np.ndarray]
    status: str
    n_metrics: int
    n_components: int
    components: Dict[str, float]
    limiting_component: Optional[str]
    metrics: List[str]
    flags: List[str] = field(default_factory=list)
    limiting_metric: Optional[str] = None
    limiting_confidence: Optional[str] = None

    def row(self) -> Dict[str, object]:
        return {"unit_id": self.unit_id, "pillar": self.pillar, "pillar_name": cat.PILLARS[self.pillar],
                "score_0_100": self.score, "score_low": self.interval[0], "score_high": self.interval[1],
                "concern": concern_label(self.score), "concern_0_10": concern_0_10(self.score), "status": self.status,
                "n_metrics": self.n_metrics, "n_components": self.n_components,
                "limiting_component": self.limiting_component, "limiting_metric": self.limiting_metric,
                "limiting_metric_confidence": self.limiting_confidence, "metrics": ", ".join(self.metrics),
                "component_scores": "; ".join(f"{k}={v:.1f}" for k, v in self.components.items()),
                "flags": "; ".join(self.flags)}


def aggregate_pillar(scores: Iterable[MetricScore], unit_id: str, pillar: str, min_metrics: int = 3,
                     min_components: int = 3) -> PillarResult:
    usable = [s for s in scores if s.pillar == pillar and s.role == "scored" and s.score is not None and s.draws is not None]
    comps: Dict[str, List[MetricScore]] = {}
    for s in usable:
        comps.setdefault(s.component, []).append(s)
    names = [s.metric for s in usable]
    if len(usable) < min_metrics or len(comps) < min_components:
        return PillarResult(unit_id, pillar, None, (None, None), None, "insufficient_evidence", len(usable), len(comps),
                            {}, None, names, [f"needs >= {min_metrics} scored metrics across >= {min_components} components"])
    comp_draws = {k: _geomean_draws([s.draws for s in v]) for k, v in comps.items()}
    comp_point = {k: _geomean_point([s.score for s in v]) for k, v in comps.items()}
    pillar_draws = np.min(np.vstack(list(comp_draws.values())), axis=0)
    point = min(comp_point.values())
    limiting = min(comp_point, key=comp_point.get)
    flags = [f"component {k} scored 0" for k, v in comp_point.items() if v == 0]
    lim = min(comps[limiting], key=lambda s: s.score)
    if lim.confidence in ("Medium", "Low"):
        # Non-compensatory pillars inherit the weakness of their weakest metric; say so.
        flags.append(f"pillar set by {lim.metric} ({lim.confidence} confidence: {'; '.join(lim.confidence_reasons)})")
    return PillarResult(unit_id, pillar, float(point), _interval(pillar_draws), pillar_draws, "scored", len(usable),
                        len(comps), comp_point, limiting, names, flags, lim.metric, lim.confidence)


SON_LABEL = "SoN score: Darukaa composite, preparatory; not a Nature Positive standard metric"
CONFIDENCE_ORDER = {"High": 2, "Medium": 1, "Low": 0}
SON_DIVERGENCE_POINTS = 20.0     # P-27-2: flag when the composite exceeds the weakest pillar by more than this


def lowest_confidence(levels: Sequence[Optional[str]]) -> Optional[str]:
    """Lowest of the given ratings; unknown (None) if any rating is missing, never assumed High."""
    if not levels or any(c not in CONFIDENCE_ORDER for c in levels):
        return None
    return min(levels, key=CONFIDENCE_ORDER.get)


def coverage_label(pillars: Sequence[str]) -> str:
    names = {"P1": "extent", "P2": "condition", "P3": "species"}
    have = [names[p] for p in pillars if p in names]
    missing = [names[p] for p in ("P1", "P2", "P3") if p not in pillars]
    lab = " and ".join(have) + " only" if missing else "extent, condition and species"
    if missing:
        lab += "; " + ", ".join(missing) + " not covered"
    return lab


@dataclass
class Headline:
    """Site headline (D-27-2, P-27-2 approved 27 Oct).

    Primary view is the pillar profile. The SoN score is a secondary Darukaa composite:
    equal-weight geometric mean of the scored state pillars (P1, P2, plus P3 when scored),
    withheld unless P1 and P2 are scored, never including pressure, and always carried
    with the weakest pillar, coverage, lowest pillar confidence, interval and its label.
    """
    unit_id: str
    son_score: Optional[float]
    son_interval: Tuple[Optional[float], Optional[float]]
    son_draws: Optional[np.ndarray]
    son_pillars: List[str]
    son_status: str
    pressure_score: Optional[float]
    pressure_interval: Tuple[Optional[float], Optional[float]]
    pressure_draws: Optional[np.ndarray]
    label: str
    weakest_pillar: Optional[str] = None
    weakest_pillar_score: Optional[float] = None
    weakest_pillar_metric: Optional[str] = None
    son_confidence: Optional[str] = None
    coverage_label: str = ""
    son_divergence_flag: Optional[str] = None
    pressure_confidence: Optional[str] = None

    def row(self) -> Dict[str, object]:
        return {"unit_id": self.unit_id, "son_score_0_100": self.son_score,
                "son_low": self.son_interval[0], "son_high": self.son_interval[1],
                "son_concern": concern_label(self.son_score), "son_concern_0_10": concern_0_10(self.son_score),
                "son_confidence": self.son_confidence, "son_pillars": "+".join(self.son_pillars), "son_status": self.son_status,
                "coverage_label": self.coverage_label, "weakest_pillar": self.weakest_pillar,
                "weakest_pillar_score": self.weakest_pillar_score, "weakest_pillar_metric": self.weakest_pillar_metric,
                "son_divergence_flag": self.son_divergence_flag,
                "pressure_score_0_100": self.pressure_score, "pressure_low": self.pressure_interval[0],
                "pressure_high": self.pressure_interval[1], "pressure_concern": concern_label(self.pressure_score),
                "pressure_confidence": self.pressure_confidence, "label": self.label}


def headline(pillars: Mapping[str, PillarResult], unit_id: str) -> Headline:
    """SoN score = equal-weight geometric mean of P1 and P2, plus P3 when scored (P-27-2). P4 separate."""
    p1, p2, p3, p4 = (pillars.get(p) for p in ("P1", "P2", "P3", "P4"))
    used = [p for p in (p1, p2, p3) if p is not None and p.score is not None]
    have_core = p1 is not None and p1.score is not None and p2 is not None and p2.score is not None
    pres = (p4.score, p4.interval, p4.draws) if p4 is not None and p4.score is not None else (None, (None, None), None)
    pres_conf = p4.limiting_confidence if p4 is not None and p4.score is not None else None
    if not have_core:
        missing = [n for n, p in (("P1", p1), ("P2", p2)) if p is None or p.score is None]
        status = f"withheld: {'+'.join(missing)} not scored"
        return Headline(unit_id, None, (None, None), None, [], status, pres[0], pres[1], pres[2],
                        f"{status}; pressure reported separately", coverage_label=coverage_label([p.pillar for p in used]),
                        pressure_confidence=pres_conf)
    draws = _geomean_draws([p.draws for p in used])
    point = _geomean_point([p.score for p in used])
    names = [p.pillar for p in used]
    weakest = min(used, key=lambda p: p.score)
    div = None
    if point - weakest.score > SON_DIVERGENCE_POINTS:
        div = (f"SoN score {point:.1f} exceeds the weakest pillar {weakest.pillar} ({weakest.score:.1f}) by more than "
               f"{SON_DIVERGENCE_POINTS:.0f} points: the composite hides a weak pillar")
    status = "scored" if len(names) == 3 else "scored_without_P3"
    return Headline(unit_id, point, _interval(draws), draws, names, status, pres[0], pres[1], pres[2],
                    f"{SON_LABEL}; from {'+'.join(names)}; pressure reported separately",
                    weakest.pillar, weakest.score, weakest.limiting_metric,
                    lowest_confidence([p.limiting_confidence for p in used]), coverage_label(names), div, pres_conf)


@dataclass
class RollUp:
    value: Optional[float]
    interval: Tuple[Optional[float], Optional[float]]
    n_contributing: int
    n_total: int
    area_share_pct: float
    label: str


def area_weighted(units: Sequence[Tuple[str, float, Optional[float], Optional[np.ndarray]]]) -> RollUp:
    """Area-weighted arithmetic mean of unit scores with an explicit contribution label (D-6/D-23-6).

    ``units`` = (unit_id, area_ha, score, draws). Units without a score are excluded
    and the label says so; nothing is imputed.
    """
    total_area = sum(a for _, a, _, _ in units)
    contrib = [(u, a, s, d) for u, a, s, d in units if s is not None]
    if not contrib:
        return RollUp(None, (None, None), 0, len(units), 0.0, f"no unit scored (0 of {len(units)})")
    w = np.array([a for _, a, _, _ in contrib], dtype=float)
    share = 100.0 * w.sum() / total_area if total_area else 0.0
    value = float(np.sum(w * np.array([s for _, _, s, _ in contrib])) / w.sum())
    if all(d is not None for _, _, _, d in contrib):
        draws = np.sum(w[:, None] * np.vstack([d for _, _, _, d in contrib]), axis=0) / w.sum()
        interval = _interval(draws)
    else:
        interval = (None, None)
    label = f"based on {len(contrib)} of {len(units)} units, {share:.1f}% of area"
    return RollUp(value, interval, len(contrib), len(units), share, label)
