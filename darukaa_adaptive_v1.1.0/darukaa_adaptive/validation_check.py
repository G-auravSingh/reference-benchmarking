"""Compare run bundles with pre-registered expected answers (validation rung R2).

Works offline on the CSV bundle the notebook writes, so results can be checked
here without Earth Engine. Each rule reports PASS, MISS or NO_DATA; NO_DATA is
never counted as a pass.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

OPS = {">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b, "==": lambda a, b: a == b}


def _rule(kind: str, name: str, actual: Any, op: str, target: Any) -> Dict[str, Any]:
    if actual is None or (isinstance(actual, float) and pd.isna(actual)):
        return {"check": kind, "item": name, "expected": f"{op} {target}", "actual": None, "result": "NO_DATA"}
    ok = OPS[op](actual, target)
    return {"check": kind, "item": name, "expected": f"{op} {target}", "actual": actual, "result": "PASS" if ok else "MISS"}


def check_bundle(bundle_dir: str | Path, expected: Dict[str, Any]) -> List[Dict[str, Any]]:
    d = Path(bundle_dir)
    metrics = pd.read_csv(d / "metrics.csv")
    pillars = pd.read_csv(d / "pillars.csv")
    heads = pd.read_csv(d / "site_headlines.csv")
    site = metrics[metrics["level"] == "site"]
    out: List[Dict[str, Any]] = []
    for metric, (op, target) in expected.get("values", {}).items():
        row = site[site["metric"] == metric]
        out.append(_rule("value", metric, float(row["value"].iloc[0]) if len(row) and pd.notna(row["value"].iloc[0]) else None, op, target))
    for metric, status in expected.get("statuses", {}).items():
        row = site[site["metric"] == metric]
        actual = row["status"].iloc[0] if len(row) else None
        out.append({"check": "status", "item": metric, "expected": status, "actual": actual,
                    "result": "NO_DATA" if actual is None else ("PASS" if actual == status else "MISS")})
    sp = pillars[pillars["unit_id"].isin(heads["unit_id"])]
    for p, (op, target) in expected.get("pillars", {}).items():
        row = sp[sp["pillar"] == p]
        out.append(_rule("pillar", p, float(row["score_0_100"].iloc[0]) if len(row) and pd.notna(row["score_0_100"].iloc[0]) else None, op, target))
    h = expected.get("headline", {})
    if h and len(heads):
        cs = heads["son_status"].iloc[0]
        if "son_status" in h:
            out.append({"check": "headline", "item": "son_status", "expected": h["son_status"], "actual": cs,
                        "result": "PASS" if cs == h["son_status"] else "MISS"})
        if "son_status_not" in h:
            out.append({"check": "headline", "item": "son_status", "expected": f"not {h['son_status_not']}", "actual": cs,
                        "result": "PASS" if cs != h["son_status_not"] else "MISS"})
    return out


def check_controls(bundles: Dict[str, str | Path], expected_file: str | Path) -> pd.DataFrame:
    exp = json.loads(Path(expected_file).read_text())["controls"]
    rows = []
    for name, rules in exp.items():
        if name not in bundles:
            rows.append({"control": name, "check": "bundle", "item": "-", "expected": "bundle present", "actual": None, "result": "NO_DATA"})
            continue
        for r in check_bundle(bundles[name], rules):
            rows.append({"control": name, **r})
        rel = rules.get("relative_to")
        if rel and rel["control"] in bundles:
            a = pd.read_csv(Path(bundles[name]) / "metrics.csv")
            b = pd.read_csv(Path(bundles[rel["control"]]) / "metrics.csv")
            va = a[(a.level == "site") & (a.metric == rel["metric"])]["value"]
            vb = b[(b.level == "site") & (b.metric == rel["metric"])]["value"]
            if len(va) and len(vb) and pd.notna(va.iloc[0]) and pd.notna(vb.iloc[0]) and vb.iloc[0]:
                diff = abs(va.iloc[0] - vb.iloc[0]) / abs(vb.iloc[0])
                rows.append({"control": name, "check": "relative", "item": rel["metric"], "expected": f"<= {rel['max_relative_difference']}",
                             "actual": diff, "result": "PASS" if diff <= rel["max_relative_difference"] else "MISS"})
    return pd.DataFrame(rows)
