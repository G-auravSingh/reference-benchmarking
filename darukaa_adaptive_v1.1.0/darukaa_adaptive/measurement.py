"""Measurement records and the four-layer status model.

Every metric value carries four separate answers (project rule; audit M6):

1. ``ran``                - did the extractor execute without error?
2. ``measured_valid``     - is there a finite value with enough native-pixel support,
                            inside the metric's valid range?
3. ``sufficient_to_score``- is the metric in a scored role, with an approved reference
                            and a computed score?
4. ``interpretable``      - is it sufficient and not Low confidence?

A failed, missing or invalid measurement never becomes zero or a score.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional, Sequence

from . import catalogue as cat

STATUSES = (
    "ok", "scored_context_scale", "not_run", "error", "source_unavailable", "no_valid_pixels",
    "below_min_support", "out_of_range_review", "pending_input", "year_unavailable",
    "not_applicable_no_forest_baseline", "not_applicable_non_forest", "not_applicable_no_woody_type",
    "not_applicable_no_natural_baseline", "not_applicable_no_natural_pixels",
)
VALID_STATUSES = {"ok", "scored_context_scale"}


@dataclass
class Measurement:
    metric: str
    unit_id: str
    level: str  # "site" | "emu"
    value: Optional[float]
    status: str
    ran: bool = True
    error: Optional[str] = None
    covered_pixel_equivalent: Optional[float] = None
    touched_pixels: Optional[int] = None
    native_scale_m: Optional[float] = None
    analysis_scale_m: Optional[float] = None
    context_buffer_m: float = 0.0
    effective_period: str = ""
    period_gap_years: float = 0.0
    sources: str = ""
    spread: Dict[str, Optional[float]] = field(default_factory=dict)
    extras: Dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    def __post_init__(self):
        if self.status not in STATUSES:
            raise ValueError(f"Unknown measurement status: {self.status}")
        if self.status not in VALID_STATUSES:
            # A failed or inapplicable measurement can never carry a value.
            self.value = None
        if self.value is not None and (not isinstance(self.value, (int, float)) or not math.isfinite(float(self.value))):
            self.value, self.status = None, "no_valid_pixels"
            self.notes = (self.notes + " non-finite value rejected").strip()

    @property
    def site_resolved(self) -> bool:
        return self.context_buffer_m == 0

    @property
    def measured_valid(self) -> bool:
        return self.ran and self.status in VALID_STATUSES and self.value is not None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["measured_valid"] = self.measured_valid
        return d


def not_run(metric: str, unit_id: str, level: str, reason: str) -> Measurement:
    return Measurement(metric, unit_id, level, None, "not_run", ran=False, notes=reason)


def failed(metric: str, unit_id: str, level: str, exc: BaseException) -> Measurement:
    return Measurement(metric, unit_id, level, None, "error", ran=False, error=f"{type(exc).__name__}: {exc}")


def check_measurement(m: Measurement) -> Measurement:
    """Apply the contract's support and range gates. Never alters a valid value."""
    if not m.measured_valid:
        return m
    c = cat.get(m.metric)
    if m.covered_pixel_equivalent is not None and m.covered_pixel_equivalent < c.min_support_px:
        m.status, m.value = "below_min_support", None
        m.notes = (m.notes + f" support {m.covered_pixel_equivalent:.2f} < {c.min_support_px} native pixels").strip()
        return m
    lo, hi = c.value_range
    if (lo is not None and m.value < lo) or (hi is not None and m.value > hi):
        m.notes = (m.notes + f" value {m.value} outside valid range {c.value_range}").strip()
        m.status, m.value = "out_of_range_review", None
    return m


@dataclass
class StatusLayers:
    ran: bool
    measured_valid: bool
    sufficient_to_score: bool
    interpretable: bool
    reason: str = ""


def status_layers(m: Measurement, role: str, score: Optional[float], confidence: Optional[str],
                  reference_ok: bool) -> StatusLayers:
    if not m.ran:
        return StatusLayers(False, False, False, False, m.error or m.notes or m.status)
    if not m.measured_valid:
        return StatusLayers(True, False, False, False, m.status)
    if role != "scored":
        return StatusLayers(True, True, False, False, f"role={role}")
    if not reference_ok:
        return StatusLayers(True, True, False, False, "reference not available or not approved")
    if score is None:
        return StatusLayers(True, True, False, False, "score not computable")
    interp = confidence in {"High", "Medium"}
    return StatusLayers(True, True, True, interp, "" if interp else "low confidence")
