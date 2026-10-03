"""Project-level aggregation of EMU assessment outputs.

Aggregation is deliberately transparent: EMU-level values are retained, weights are
explicit, and missing/insufficient EMUs are never silently converted to zero.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List
import math
import pandas as pd


def _weighted_mean(values: pd.Series, weights: pd.Series) -> float | None:
    mask = values.notna() & weights.notna() & (weights > 0)
    if not mask.any(): return None
    return float((values[mask] * weights[mask]).sum() / weights[mask].sum())


def aggregate_emu_scorecards(rows: Iterable[Dict[str, Any]]) -> pd.DataFrame:
    """Aggregate EMU metric/benchmark rows by metric using area weights.

    This function only aggregates already-scored EMU observations. It never creates
    a reference or imputes missing ecological evidence.
    """
    df = pd.DataFrame(list(rows))
    if df.empty: return pd.DataFrame(columns=["metric","project_value","n_emus","coverage_weight"])
    required = {"metric", "value", "area_ha", "emu_id"}
    missing = required - set(df.columns)
    if missing: raise ValueError(f"Aggregation rows missing columns: {sorted(missing)}")
    out=[]
    for metric,g in df.groupby("metric", dropna=False):
        total_area=float(g["area_ha"].fillna(0).sum())
        valid=g[g["value"].notna() & (g["area_ha"]>0)]
        out.append({"metric":metric,"project_value":_weighted_mean(valid["value"],valid["area_ha"]),"n_emus":int(valid["emu_id"].nunique()),"n_emus_total":int(g["emu_id"].nunique()),"coverage_weight":float(valid["area_ha"].sum()/total_area) if total_area else 0.0})
    return pd.DataFrame(out)


def aggregate_pillar_scores(pillar_rows: Iterable[Dict[str, Any]]) -> pd.DataFrame:
    df=pd.DataFrame(list(pillar_rows))
    if df.empty: return df
    if "area_ha" not in df or "score_0_to_100" not in df: raise ValueError("Pillar rows require area_ha and score_0_to_100")
    out=[]
    for pillar,g in df.groupby("pillar",dropna=False):
        valid=g[g["score_0_to_100"].notna() & (g["area_ha"]>0)]
        out.append({"pillar":pillar,"score_0_to_100":_weighted_mean(valid["score_0_to_100"],valid["area_ha"]),"n_emus":int(valid["emu_id"].nunique()),"n_emus_total":int(g["emu_id"].nunique()),"coverage_weight":float(valid["area_ha"].sum()/g["area_ha"].fillna(0).sum()) if g["area_ha"].sum()>0 else 0.0})
    return pd.DataFrame(out)
