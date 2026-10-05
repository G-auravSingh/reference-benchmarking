"""Generic multi-source evidence ingestion, including optional eDNA evidence.

The engine does not require eDNA. When supplied, eDNA observations enter the same
metric/reference/scoring pathway as field, acoustic, modelled, or EO indicators.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional
import pandas as pd

REQUIRED = {"metric", "raw_value", "pillar", "direction"}
OPTIONAL = {
    "units", "reference_value", "reference_type", "reference_level",
    "reference_approved_for_scoring", "status", "evidence_source",
    "evidence_type", "domain", "notes", "sample_id", "taxon",
}


def load_evidence_csv(path: str | Path, evidence_type: Optional[str] = None) -> pd.DataFrame:
    """Load generic external evidence in a stable, auditable schema.

    Required: metric, raw_value, pillar, direction.
    A reference is optional; without one the record remains visible but cannot score.
    """
    df = pd.read_csv(path)
    missing = REQUIRED - set(df.columns)
    if missing:
        raise ValueError(f"Evidence CSV missing required columns: {sorted(missing)}")
    out = df.copy()
    if evidence_type is not None:
        out["evidence_type"] = evidence_type
    defaults = {
        "units": "", "reference_type": "external", "reference_level": "none",
        "reference_approved_for_scoring": False, "status": "ok",
        "evidence_source": str(path), "evidence_type": evidence_type or "external",
        "domain": "external", "notes": "",
    }
    for col, value in defaults.items():
        if col not in out.columns:
            out[col] = value
    out["raw_value"] = pd.to_numeric(out["raw_value"], errors="coerce")
    if "reference_value" in out.columns:
        out["reference_value"] = pd.to_numeric(out["reference_value"], errors="coerce")
    return out


def load_edna_csv(path: str | Path) -> pd.DataFrame:
    """Load optional eDNA observations.

    This intentionally accepts a broad schema. The most useful direct eDNA metrics are
    eDNA taxon richness, taxon detections, detection rate, and validated abundance/reads
    metrics. Persistence-potential proxies remain contextual unless a defensible reference
    and validation method are supplied.
    """
    df = load_evidence_csv(path, evidence_type="eDNA")
    if "metric" in df:
        df["metric"] = df["metric"].astype(str).str.strip()
    return df


def edna_template(path: str | Path) -> Path:
    """Create a blank eDNA input template for field/lab teams."""
    path = Path(path)
    cols = [
        "metric", "raw_value", "pillar", "direction", "units",
        "reference_value", "reference_type", "reference_level",
        "reference_approved_for_scoring", "status", "evidence_source",
        "sample_id", "taxon", "notes",
    ]
    pd.DataFrame(columns=cols).to_csv(path, index=False)
    return path
