"""Baseline-to-monitoring comparison using the same metric definitions and domains."""
from __future__ import annotations

import pandas as pd


def compare(current_csv: str, baseline_csv: str) -> pd.DataFrame:
    cur=pd.read_csv(current_csv)
    base=pd.read_csv(baseline_csv)
    key="metric"
    keep=[key,"value","units","direction"]
    cur=cur[[c for c in keep if c in cur.columns]].rename(columns={"value":"current_value"})
    base=base[[c for c in keep if c in base.columns]].rename(columns={"value":"baseline_value","units":"baseline_units","direction":"baseline_direction"})
    df=cur.merge(base,on=key,how="outer")
    df["delta"]=df["current_value"]-df["baseline_value"]
    df["percent_change"]=df["delta"]/df["baseline_value"].replace(0,pd.NA)*100
    def change(row):
        if pd.isna(row["delta"]): return "not_comparable"
        if row.get("direction") in ("higher_is_better","lower_is_better"):
            return "higher_than_baseline" if row["delta"]>0 else "lower_than_baseline" if row["delta"]<0 else "unchanged"
        return "changed" if row["delta"]!=0 else "unchanged"
    df["change_flag"]=df.apply(change,axis=1)
    return df
