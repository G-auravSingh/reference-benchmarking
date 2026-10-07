"""Transparent EMU and project aggregation for the adaptive assessment framework.

The aggregation layer never invents missing ecological evidence. It preserves the
EMU distribution, applies metric-specific project aggregation rules, and provides
comparison statistics separately from the client-facing project score.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable
import math
import pandas as pd


def _weighted_mean(values: pd.Series, weights: pd.Series) -> float | None:
    mask = values.notna() & weights.notna() & (weights > 0)
    if not mask.any():
        return None
    return float((values[mask] * weights[mask]).sum() / weights[mask].sum())


def _weighted_geometric_mean(values: pd.Series, weights: pd.Series) -> float | None:
    mask = values.notna() & weights.notna() & (weights > 0)
    if not mask.any():
        return None
    vals = values[mask].astype(float).clip(lower=1e-12)
    w = weights[mask].astype(float)
    return float(math.exp((w * vals.map(math.log)).sum() / w.sum()))


def _distribution(values: pd.Series) -> Dict[str, Any]:
    x = pd.to_numeric(values, errors="coerce").dropna()
    if x.empty:
        return {"n": 0, "mean": None, "median": None, "std": None, "mad": None,
                "min": None, "max": None, "p10": None, "p25": None, "p75": None, "p90": None}
    med = float(x.median())
    return {
        "n": int(x.size), "mean": float(x.mean()), "median": med,
        "std": float(x.std(ddof=1)) if x.size > 1 else None,
        "mad": float((x - med).abs().median()),
        "min": float(x.min()), "max": float(x.max()),
        "p10": float(x.quantile(0.10)), "p25": float(x.quantile(0.25)),
        "p75": float(x.quantile(0.75)), "p90": float(x.quantile(0.90)),
    }


def aggregate_emu_metric_values(rows: Iterable[Dict[str, Any]]) -> pd.DataFrame:
    """Aggregate raw metric observations across EMUs using area weighting.

    This is appropriate only for metrics whose registry explicitly declares
    ``area_weighted_mean`` as the project aggregation method. The result is a
    project descriptive value, not a replacement for the EMU distribution.
    """
    df = pd.DataFrame(list(rows))
    if df.empty:
        return pd.DataFrame()
    required = {"metric", "value", "area_ha", "emu_id"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Aggregation rows missing columns: {sorted(missing)}")
    out = []
    for metric, g in df.groupby("metric", dropna=False):
        total_area = float(g["area_ha"].fillna(0).sum())
        valid = g[g["value"].notna() & (g["area_ha"] > 0)]
        d = _distribution(valid["value"])
        out.append({
            "metric": metric,
            "project_value": _weighted_mean(valid["value"], valid["area_ha"]),
            "n_emus": int(valid["emu_id"].nunique()),
            "n_emus_total": int(g["emu_id"].nunique()),
            "coverage_weight": float(valid["area_ha"].sum() / total_area) if total_area else 0.0,
            **{f"emu_{k}": v for k, v in d.items()},
            "aggregation_method": "area_weighted_mean",
        })
    return pd.DataFrame(out)


# Backwards-compatible public name used by earlier v1.1 outputs.
def aggregate_emu_scorecards(rows: Iterable[Dict[str, Any]]) -> pd.DataFrame:
    return aggregate_emu_metric_values(rows)


def aggregate_project_metric_scores(rows: Iterable[Dict[str, Any]]) -> pd.DataFrame:
    """Aggregate already-scored EMU metric observations.

    For a reference-relative condition score, the default project headline is an
    area-weighted arithmetic mean because the score is already on a bounded common
    scale and area represents the amount of project area represented by the EMU.
    The full EMU distribution is retained for ecological comparison. A metric may
    explicitly request ``area_weighted_geometric_mean`` in future registry versions.
    """
    df = pd.DataFrame(list(rows))
    if df.empty:
        return pd.DataFrame()
    required = {"metric", "score_0_to_100", "area_ha", "emu_id"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Project score rows missing columns: {sorted(missing)}")
    out = []
    for metric, g in df.groupby("metric", dropna=False):
        total_area = float(g["area_ha"].fillna(0).sum())
        valid = g[g["score_0_to_100"].notna() & (g["area_ha"] > 0)]
        d = _distribution(valid["score_0_to_100"])
        out.append({
            "metric": metric,
            "project_score_0_to_100": _weighted_mean(valid["score_0_to_100"], valid["area_ha"]),
            "n_emus": int(valid["emu_id"].nunique()),
            "n_emus_total": int(g["emu_id"].nunique()),
            "coverage_weight": float(valid["area_ha"].sum() / total_area) if total_area else 0.0,
            "limiting_emu": None if valid.empty else str(valid.loc[valid["score_0_to_100"].astype(float).idxmin(), "emu_id"]),
            **{f"emu_{k}": v for k, v in d.items()},
            "aggregation_method": "area_weighted_mean_on_common_score_scale",
        })
    return pd.DataFrame(out)


def aggregate_project_pillars(pillar_rows: Iterable[Dict[str, Any]]) -> pd.DataFrame:
    """Area-weight pillar scores while retaining between-EMU comparison statistics."""
    df = pd.DataFrame(list(pillar_rows))
    if df.empty:
        return pd.DataFrame()
    required = {"pillar", "score_0_to_100", "area_ha", "emu_id"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Pillar rows missing columns: {sorted(missing)}")
    out = []
    for pillar, g in df.groupby("pillar", dropna=False):
        total_area = float(g["area_ha"].fillna(0).sum())
        valid = g[g["score_0_to_100"].notna() & (g["area_ha"] > 0)]
        d = _distribution(valid["score_0_to_100"])
        out.append({
            "pillar": pillar,
            "pillar_name": str(valid["pillar_name"].iloc[0]) if "pillar_name" in valid and not valid.empty else pillar,
            "project_score_0_to_100": _weighted_mean(valid["score_0_to_100"], valid["area_ha"]),
            "n_emus": int(valid["emu_id"].nunique()),
            "n_emus_total": int(g["emu_id"].nunique()),
            "coverage_weight": float(valid["area_ha"].sum() / total_area) if total_area else 0.0,
            "limiting_emu": None if valid.empty else str(valid.loc[valid["score_0_to_100"].astype(float).idxmin(), "emu_id"]),
            **{f"emu_{k}": v for k, v in d.items()},
            "aggregation_method": "area_weighted_mean_on_common_score_scale",
        })
    return pd.DataFrame(out)


# Backwards-compatible public name.
def aggregate_pillar_scores(pillar_rows: Iterable[Dict[str, Any]]) -> pd.DataFrame:
    return aggregate_project_pillars(pillar_rows)


def build_emu_comparison_table(pillar_rows: Iterable[Dict[str, Any]], metric_score_rows: Iterable[Dict[str, Any]]) -> pd.DataFrame:
    """Create a client-facing EMU comparison table without ranking by a hidden index."""
    pdf = pd.DataFrame(list(pillar_rows))
    mdf = pd.DataFrame(list(metric_score_rows))
    if pdf.empty:
        return pd.DataFrame()
    rows = []
    for emu_id, g in pdf.groupby("emu_id"):
        row = {"emu_id": emu_id, "area_ha": float(g["area_ha"].iloc[0]) if pd.notna(g["area_ha"].iloc[0]) else None,
               "domain": g["domain"].iloc[0] if "domain" in g else None}
        for _, r in g.iterrows():
            row[f"{r['pillar']}_score_0_to_100"] = r.get("score_0_to_100")
            row[f"{r['pillar']}_concern"] = r.get("concern_label")
            row[f"{r['pillar']}_limiting_metric"] = r.get("limiting_metric")
        if not mdf.empty:
            mg = mdf[mdf["emu_id"] == emu_id]
            valid = mg[mg["score_0_to_100"].notna()] if "score_0_to_100" in mg else pd.DataFrame()
            row["n_scored_metrics"] = int(len(valid))
            row["limiting_metric"] = None if valid.empty else str(valid.loc[valid["score_0_to_100"].astype(float).idxmin(), "metric"])
            row["limiting_metric_score_0_to_100"] = None if valid.empty else float(valid["score_0_to_100"].min())
        rows.append(row)
    return pd.DataFrame(rows).sort_values("emu_id").reset_index(drop=True)
