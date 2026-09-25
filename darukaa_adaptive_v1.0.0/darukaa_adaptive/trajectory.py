"""Baseline-to-monitoring comparison using the same metric definitions and domains."""
from __future__ import annotations

from typing import Optional

import pandas as pd

from .benchmark import baseline_delta, percent_change


def compare(current_csv: str, baseline_csv: str) -> pd.DataFrame:
    cur = pd.read_csv(current_csv)
    base = pd.read_csv(baseline_csv)
    keep = [c for c in ["metric", "value", "units", "direction", "temporal_window", "status"] if c in cur.columns]
    cur = cur[keep].rename(columns={"value": "current_value", "temporal_window": "current_window", "status": "current_status"})
    keepb = [c for c in ["metric", "value", "units", "direction", "temporal_window", "status"] if c in base.columns]
    base = base[keepb].rename(columns={"value": "baseline_value", "units": "baseline_units", "direction": "baseline_direction",
                                        "temporal_window": "baseline_window", "status": "baseline_status"})

    df = cur.merge(base, on="metric", how="outer")
    df["delta"] = df.apply(lambda r: baseline_delta(r.get("current_value"), r.get("baseline_value")), axis=1)
    df["percent_change"] = df.apply(lambda r: percent_change(r.get("current_value"), r.get("baseline_value")), axis=1)

    def flag(row):
        if pd.isna(row.get("delta")):
            return "not_comparable"
        if row.get("current_window") == row.get("baseline_window"):
            return "unchanged" if row["delta"] == 0 else "changed_same_window"
        return "changed_different_window"

    df["change_flag"] = df.apply(flag, axis=1)
    df["interpretation"] = "Descriptive change only; ecological improvement/degradation requires metric-specific evidence."
    return df
