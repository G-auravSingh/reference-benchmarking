"""
Report Generator
================

Produces structured scorecards from pipeline results in JSON and/or CSV format.

Output schema per row:
    site_id, indicator, pillar, site_value, unit,
    tier1_median, tier1_intactness,
    tier2_median, tier2_intactness,
    hedges_g, hedges_g_ci_lo, hedges_g_ci_hi,
    bootstrap_ci_lo, bootstrap_ci_hi,
    permutation_p, interpretation,
    eco_id, eco_name, biome, realm
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from darukaa_reference.config import Config
from darukaa_reference.registry import IndicatorRegistry
from darukaa_reference.statistics import ComparisonResult

logger = logging.getLogger(__name__)


class ReportGenerator:
    """
    Generate benchmark scorecards from pipeline results.

    Usage::

        reporter = ReportGenerator(config, registry)
        reporter.generate(comparisons, site_metadata, output_path)
    """

    def __init__(self, config: Config, registry: IndicatorRegistry):
        self.config = config
        self.registry = registry

    def generate(
        self,
        comparisons: List[ComparisonResult],
        site_metadata: Optional[Dict[str, Dict]] = None,
        output_path: Optional[str] = None,
    ) -> Dict:
        """
        Generate the full report.

        Parameters
        ----------
        comparisons : list of ComparisonResult
        site_metadata : dict mapping site_id → {eco_id, eco_name, biome, realm}
        output_path : str, optional
            If provided, writes files. Otherwise returns dict only.

        Returns
        -------
        dict
            The full report as a nested dictionary.
        """
        site_metadata = site_metadata or {}

        rows = []
        for comp in comparisons:
            spec = self.registry.get(comp.indicator_name) if comp.indicator_name in self.registry else None
            meta = site_metadata.get(comp.site_id, {})

            row = {
                "site_id": comp.site_id,
                "indicator": comp.indicator_name,
                "display_name": spec.display_name if spec else comp.indicator_name,
                "pillar": spec.pillar if spec else None,
                "unit": spec.unit if spec else "",
                "ref_radius_km": spec.reference_radius_km if spec else None,
                "higher_is_better": spec.higher_is_better if spec else True,
                "site_value": _safe_round(comp.site_value),
                "tier1_reference": _safe_round(comp.tier1_reference),
                "tier1_intactness": _safe_round(comp.tier1_intactness),
                "tier2_reference": _safe_round(comp.tier2_reference),
                "tier2_intactness": _safe_round(comp.tier2_intactness),
                "hedges_g": _safe_round(comp.hedges_g),
                "hedges_g_ci_lo": _safe_round(comp.hedges_g_ci[0]) if comp.hedges_g_ci else None,
                "hedges_g_ci_hi": _safe_round(comp.hedges_g_ci[1]) if comp.hedges_g_ci else None,
                "bootstrap_ci_lo": (
                    _safe_round(comp.intactness_bootstrap_ci[0])
                    if comp.intactness_bootstrap_ci else None
                ),
                "bootstrap_ci_hi": (
                    _safe_round(comp.intactness_bootstrap_ci[1])
                    if comp.intactness_bootstrap_ci else None
                ),
                "permutation_p": _safe_round(comp.permutation_p_value, 6),
                "interpretation": comp.interpretation,
                "eco_id": meta.get("ECO_ID"),
                "eco_name": meta.get("ECO_NAME"),
                "biome": meta.get("BIOME_NAME"),
                "realm": meta.get("REALM"),
            }
            rows.append(row)

        report = {
            "meta": {
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "pipeline_version": "0.1.0",
                "n_sites": len(set(r["site_id"] for r in rows)),
                "n_indicators": len(set(r["indicator"] for r in rows)),
                "tier2_hmi_percentile": self.config.hmi_percentile_threshold,
                "tier2_buffer_km": self.config.reference_buffer_km,
                "methodology_references": [
                    "McElderry et al. (2024). DOI:10.32942/X2689N",
                    "McNellie et al. (2020). DOI:10.1111/gcb.15383",
                    "Yen et al. (2019). DOI:10.1002/eap.1970",
                    "Schipper et al. (2020). DOI:10.1111/gcb.14848",
                    "Kennedy et al. (2019). DOI:10.1111/gcb.14549",
                ],
            },
            "scorecard": rows,
        }

        # Pillar summaries
        report["pillar_summary"] = self._pillar_summary(rows)

        # Write outputs
        if output_path:
            self._write(report, rows, output_path)

        return report

    def _pillar_summary(self, rows: List[Dict]) -> List[Dict]:
        """Aggregate intactness by pillar."""
        from collections import defaultdict

        pillar_vals = defaultdict(list)
        for r in rows:
            if r["pillar"] and r["tier2_intactness"] is not None:
                pillar_vals[r["pillar"]].append(r["tier2_intactness"])

        pillar_names = {
            1: "Ecosystem Condition",
            2: "Species Assemblage",
            3: "Species/Population Status",
            4: "Threats & Pressures",
        }

        summaries = []
        for pillar in sorted(pillar_vals.keys()):
            vals = pillar_vals[pillar]
            import numpy as np
            summaries.append({
                "pillar": pillar,
                "pillar_name": pillar_names.get(pillar, f"Pillar {pillar}"),
                "mean_intactness": _safe_round(float(np.mean(vals))),
                "min_intactness": _safe_round(float(np.min(vals))),
                "max_intactness": _safe_round(float(np.max(vals))),
                "n_indicators": len(vals),
            })

        return summaries

    def _write(self, report: Dict, rows: List[Dict], output_path: str):
        """Write report to file(s)."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        fmt = self.config.output_format

        if fmt in ("json", "both"):
            json_path = out.with_suffix(".json")
            with open(json_path, "w") as f:
                json.dump(report, f, indent=2, default=str)
            logger.info(f"JSON report written to {json_path}")

        if fmt in ("csv", "both"):
            import csv

            csv_path = out.with_suffix(".csv")
            if rows:
                with open(csv_path, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                    writer.writeheader()
                    writer.writerows(rows)
                logger.info(f"CSV report written to {csv_path}")


def _safe_round(val, digits=4):
    """Round a value safely, handling None."""
    if val is None:
        return None
    return round(float(val), digits)
