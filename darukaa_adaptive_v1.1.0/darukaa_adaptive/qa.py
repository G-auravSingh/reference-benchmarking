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


def qa_metric_record(metric) -> dict:
    """Return structural/measurement QA flags for one MetricResult-like record."""
    flags = []
    status = getattr(metric, "status", None)
    value = getattr(metric, "value", None)
    n_obs = getattr(metric, "valid_observations", None)
    n_pix = getattr(metric, "valid_pixels", None)
    p05 = getattr(metric, "p05", None)
    p95 = getattr(metric, "p95", None)

    if status not in {"ok", "usable"}:
        flags.append(f"status:{status or 'missing'}")
    if value is None:
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

    return {
        "metric": getattr(metric, "metric", None),
        "pillar": getattr(metric, "pillar", None),
        "qa_pass": len(flags) == 0,
        "qa_status": "pass" if not flags else "review",
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
