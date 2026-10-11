"""Automated metric QA/QC for the adaptive assessment layer.

The QA layer checks computational evidence quality and flags records for scientific review.
It does not decide whether a proxy is ecologically valid; that decision remains in the registry
and assessment methodology.
"""
from __future__ import annotations

import math
from dataclasses import asdict
from typing import Iterable

import pandas as pd


def normalize_measurement_status(metric):
    """Normalize a nominally successful metric with zero support to no observation.

    Some legacy calculators returned ``value=0`` and ``status=calculated`` when
    Earth Engine returned no valid pixels. A zero is a valid ecological value
    only when measurement support exists; explicit zero support must not be
    passed into reference benchmarking or scoring as an observed zero.
    """
    status = getattr(metric, "status", None)
    if status not in {"ok", "usable", "calculated"}:
        return metric
    n_obs = getattr(metric, "valid_observations", None)
    n_pix = getattr(metric, "valid_pixels", None)
    metric_name = str(getattr(metric, "metric", ""))
    # Coarse raster indicators cannot support site-level scoring from only a few
    # valid cells. Four cells is a minimum computational support gate, not a claim
    # of statistical independence or ecological representativeness.
    min_pixels = {"ghm": 4, "lai": 4, "flii": 4, "bii": 4, "light_pollution": 4}.get(metric_name, 1)
    no_support = ((n_obs is not None and n_obs < 1) or (n_pix is not None and n_pix < 1) or
                  (n_pix is not None and 0 < n_pix < min_pixels))
    if no_support:
        metric.status = "no_valid_observation"
        metric.value = None
        existing = str(getattr(metric, "notes", "") or "")
        reason = (f"Only {n_pix} valid native raster pixels; minimum support for {metric_name} is {min_pixels}." if n_pix is not None and 0 < n_pix < min_pixels else "No valid measurement support; zero is not interpreted as an observed ecological value.")
        metric.notes = (existing + " " + reason).strip()
    return metric


def qa_metric_record(metric) -> dict:
    """Return structural/measurement QA flags for one MetricResult-like record."""
    flags = []
    status = getattr(metric, "status", None)
    value = getattr(metric, "value", None)
    n_obs = getattr(metric, "valid_observations", None)
    n_pix = getattr(metric, "valid_pixels", None)
    p05 = getattr(metric, "p05", None)
    p95 = getattr(metric, "p95", None)

    # ``calculated`` is the normal successful status emitted by the v1.1.0
    # terrestrial/full-metric engines. Treating it as a failure made every
    # calculated record fail QA and forced readiness.usable_metrics to zero.
    # Non-scored workflow states are explicit and should not be mislabeled as
    # calculation failures; zero-observation/pixel checks below still catch
    # a nominally calculated record with no measurement support.
    successful_statuses = {"ok", "usable", "calculated"}
    informational_statuses = {
        "not_applicable", "pending_input", "context_only_pending_provenance",
        "contextual", "diagnostic_only",
    }
    if status not in successful_statuses | informational_statuses:
        flags.append(f"status:{status or 'missing'}")
    if value is None and status not in informational_statuses:
        flags.append("missing_value")
    elif isinstance(value, (int, float)) and not math.isfinite(float(value)):
        flags.append("non_finite_value")

    if n_obs is not None and n_obs < 1:
        flags.append("no_valid_observations")
    if n_pix is not None and n_pix < 1:
        flags.append("no_valid_pixels")

    if p05 is not None and p95 is not None and p05 > p95:
        flags.append("percentile_order_error")
    if value is not None and p05 is not None and value < p05:
        flags.append("value_below_p05")
    if value is not None and p95 is not None and value > p95:
        flags.append("value_above_p95")

    if flags:
        qa_status = "review"
        qa_pass = False
    elif status in informational_statuses:
        qa_status = str(status)
        qa_pass = None
    else:
        qa_status = "pass"
        qa_pass = True

    return {
        "metric": getattr(metric, "metric", None),
        "pillar": getattr(metric, "pillar", None),
        "status": status,
        "score_eligible": getattr(metric, "score_eligible", False),
        "valid_observations": n_obs,
        "valid_pixels": n_pix,
        "qa_pass": qa_pass,
        "qa_status": qa_status,
        "qa_flags": ";".join(flags),
    }


def qa_metrics(metrics: Iterable) -> pd.DataFrame:
    """Run automated QA over metric records."""
    return pd.DataFrame([qa_metric_record(m) for m in metrics])


def merge_metric_qa(metric_df: pd.DataFrame, qa_df: pd.DataFrame) -> pd.DataFrame:
    """Attach QA columns to the metric scorecard by metric name."""
    if metric_df.empty or qa_df.empty:
        return metric_df.copy()
    return metric_df.merge(
        qa_df[["metric", "qa_pass", "qa_status", "qa_flags"]],
        on="metric",
        how="left",
        suffixes=("", "_qa"),
    )
