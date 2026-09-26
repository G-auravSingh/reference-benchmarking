"""eDNA/metagenomic evidence ingestion and conservative integration."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

import pandas as pd

from .observations import ObservationRecord


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
class EDNAEvidence:
    metric: str
    raw_value: Optional[float]
    units: str
    pillar: str
    evidence_class: str
    temporal_window: str
    reference_value: Optional[float] = None
    reference_approved: bool = False
    interpretation: str = ""
    validation_required: str = ""
    notes: str = ""

    def to_dict(self):
        return asdict(self)


def load_edna_csv(path: str | Path) -> List[EDNAEvidence]:
    df = pd.read_csv(path)
    required = {"metric", "value", "units", "pillar", "evidence_class"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"eDNA CSV missing columns: {sorted(missing)}")
    out = []
    for _, r in df.iterrows():
        value = None if pd.isna(r["value"]) else float(r["value"])
        ref = None if "reference_value" not in df.columns or pd.isna(r.get("reference_value")) else float(r.get("reference_value"))
        out.append(EDNAEvidence(
            metric=str(r["metric"]), raw_value=value, units=str(r["units"]), pillar=str(r["pillar"]),
            evidence_class=str(r["evidence_class"]), temporal_window=str(r.get("temporal_window", "")),
            reference_value=ref, reference_approved=_as_bool(r.get("reference_approved", False)),
            interpretation=str(r.get("interpretation", "")), validation_required=str(r.get("validation_required", "")),
            notes=str(r.get("notes", "")),
        ))
    return out


def edna_to_observations(records: List[EDNAEvidence]) -> List[ObservationRecord]:
    """Expose only quantitatively comparable eDNA records to the shared scorer.

    A record without an approved reference remains evidence-only in the report.
    """
    out = []
    direction_map = {
        "edna_taxonomic_richness": "higher_is_better",
        "edna_fauna_taxonomic_richness": "higher_is_better",
        "edna_cyanobacterial_fraction": "lower_is_better",
        "edna_human_associated_fraction": "lower_is_better",
        "edna_reducing_microbe_fraction": "lower_is_better",
    }
    for r in records:
        if r.reference_value is None:
            continue
        out.append(ObservationRecord(
            metric=r.metric, pillar=r.pillar, raw_value=r.raw_value, units=r.units,
            direction=direction_map.get(r.metric, "higher_is_better"), source_type="edna",
            evidence_class=r.evidence_class, temporal_window=r.temporal_window,
            reference_value=r.reference_value, reference_level="external_edna_reference",
            reference_approved=r.reference_approved, status="ok",
            interpretation=r.interpretation, notes=r.notes,
        ))
    return out


def write_template(path: str | Path) -> None:
    df = pd.DataFrame([
        {"metric":"edna_taxonomic_richness","value":"","units":"taxonomic assignments","pillar":"C2_vegetation","evidence_class":"measured","temporal_window":"","reference_value":"","reference_approved":False,"interpretation":"Broad molecular-community complexity signal.","validation_required":"Matched shotgun metagenomic sampling, extraction and classification protocol.","notes":"Do not equate assignments with independently confirmed species records or direct fauna richness."},
        {"metric":"edna_fauna_taxonomic_richness","value":"","units":"taxa","pillar":"C3_fauna","evidence_class":"measured","temporal_window":"","reference_value":"","reference_approved":False,"interpretation":"Targeted faunal eDNA richness; future C3 input.","validation_required":"Fauna-specific assay/filtering and matched reference sampling.","notes":"Not populated from the current broad Nandoshi shotgun metagenomic assignment count."},
        {"metric":"edna_cyanobacterial_fraction","value":"","units":"fraction of assigned reads","pillar":"C2_vegetation","evidence_class":"indicated","temporal_window":"2026-05-28","reference_value":"","reference_approved":False,"interpretation":"Potential cyanobacterial stress signal.","validation_required":"Chlorophyll-a/phycocyanin, microscopy/cell counts, toxin genes and toxin concentration where relevant.","notes":"Species/taxon assignment does not establish toxigenicity."},
        {"metric":"edna_human_associated_fraction","value":"","units":"fraction of assigned reads","pillar":"C4_pressure","evidence_class":"indicated","temporal_window":"2026-05-28","reference_value":"","reference_approved":False,"interpretation":"Human-associated molecular material detected.","validation_required":"Microbial source tracking and conventional water-quality testing.","notes":"Source cannot be attributed from this signal alone."},
        {"metric":"edna_reducing_microbe_fraction","value":"","units":"fraction of genetic material","pillar":"C2_vegetation","evidence_class":"indicated","temporal_window":"2026-05-28","reference_value":"","reference_approved":False,"interpretation":"Reducing/oxygen-limited condition signal.","validation_required":"Direct dissolved oxygen and related chemistry.","notes":"May also reflect sediment microenvironments."},
    ])
    df.to_csv(path, index=False)
