"""Generic field, acoustic and eDNA observation ingestion."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from .registry import get_indicator_spec


def _as_bool(value, default=False):
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except Exception:
        pass
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "approved"}


@dataclass
class ObservationRecord:
    metric: str
    pillar: str
    raw_value: Optional[float]
    units: str
    direction: str
    source_type: str
    evidence_class: str
    temporal_window: str
    reference_value: Optional[float] = None
    reference_level: str = "external"
    reference_approved: bool = False
    uncertainty: Optional[float] = None
    sample_n: Optional[int] = None
    status: str = "ok"
    interpretation: str = ""
    notes: str = ""

    def to_dict(self):
        return asdict(self)


def _record_from_row(row: pd.Series, source_type: str) -> ObservationRecord:
    metric = str(row["metric"]).strip()
    try:
        spec = get_indicator_spec(metric)
        pillar = str(row.get("pillar") or spec.pillar)
        direction = str(row.get("direction") or spec.direction)
        units = str(row.get("units") or spec.units)
        evidence_class = str(row.get("evidence_class") or spec.evidence_class)
    except KeyError:
        required = ["pillar", "direction"]
        missing = [x for x in required if not str(row.get(x, "")).strip()]
        if missing:
            raise ValueError(f"Unknown metric {metric!r}: provide pillar and direction in the input CSV")
        pillar = str(row["pillar"]); direction = str(row["direction"]); units = str(row.get("units") or "")
        evidence_class = str(row.get("evidence_class") or "measured")

    raw = row.get("raw_value", row.get("value"))
    raw_value = None if pd.isna(raw) else float(raw)
    ref = row.get("reference_value")
    ref_value = None if ref is None or pd.isna(ref) else float(ref)
    unc = row.get("uncertainty")
    uncertainty = None if unc is None or pd.isna(unc) else float(unc)
    n = row.get("sample_n", row.get("n"))
    sample_n = None if n is None or pd.isna(n) else int(n)
    return ObservationRecord(
        metric=metric, pillar=pillar, raw_value=raw_value, units=units, direction=direction,
        source_type=source_type, evidence_class=evidence_class,
        temporal_window=str(row.get("temporal_window") or ""), reference_value=ref_value,
        reference_level=str(row.get("reference_level") or "external"),
        reference_approved=_as_bool(row.get("reference_approved", False)), uncertainty=uncertainty,
        sample_n=sample_n, status=str(row.get("status") or "ok"),
        interpretation=str(row.get("interpretation") or ""), notes=str(row.get("notes") or ""),
    )


def load_observations(path: str | Path, source_type: Optional[str] = None) -> List[ObservationRecord]:
    df = pd.read_csv(path)
    if "metric" not in df.columns or not ({"value", "raw_value"} & set(df.columns)):
        raise ValueError("Observation CSV must contain metric and either value or raw_value")
    inferred = source_type or str(df.get("source_type", pd.Series(["field"])).iloc[0])
    return [_record_from_row(row, inferred) for _, row in df.iterrows()]


def observation_table(records: List[ObservationRecord]) -> pd.DataFrame:
    return pd.DataFrame([r.to_dict() for r in records])
