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
from darukaa_reference import scoring

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
                # v0.2.0 contract fields (CS-1/CS-4) — construct placement + scoring status
                "construct": getattr(spec, "construct", None) if spec else None,
                "subdimension": getattr(spec, "subdimension", None) if spec else None,
                "evidence_tier": getattr(spec, "evidence_tier", None) if spec else None,
                "scoring_eligible": bool(getattr(spec, "scoring_eligible", False)) if spec else False,
                # v0.2.1: never let a client-activated indicator look indistinguishable
                # from a Darukaa-default scored one — always visible downstream.
                "client_override": bool(getattr(spec, "client_override", False)) if spec else False,
                "client_override_note": getattr(spec, "client_override_note", "") if spec else "",
                # Responsive benchmark (CS-3) — signed, uncapped; the value scoring uses.
                # Falls back to None (NOT the capped ratio) if not yet propagated upstream.
                "tier2_benchmark": _safe_round(getattr(comp, "tier2_benchmark", None)),
                "tier2_benchmark_estimator": getattr(comp, "tier2_benchmark_estimator", None),
                "reference_type": getattr(comp, "reference_type", None),
                # v0.2.0 (post-audit): full stratification diagnostics — mode, masks
                # applied, land-cover class (+ PNV correction status), realised HMI
                # threshold, fallback level used. This is what makes this JSON file
                # self-sufficient for validating a live run (no separate export needed).
                "stratification_diagnostics": getattr(comp, "stratification_diagnostics", {}) or {},
                # v0.2.4: dual-mode concern classification, computed from the SAME
                # reference-relative benchmark used for scoring (never a separate,
                # unrelated comparison) — see son_score.classify_indicator().
                "classification": self._classify_row(spec, comp),
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
                "metadata": comp.metadata or {},   #added now
                "eco_id": meta.get("ECO_ID"),
                "eco_name": meta.get("ECO_NAME"),
                "biome": meta.get("BIOME_NAME"),
                "realm": meta.get("REALM"),
            }
            rows.append(row)

        report = {
            "meta": {
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "pipeline_version": "0.2.5",
                "n_sites": len(set(r["site_id"] for r in rows)),
                "n_indicators": len(set(r["indicator"] for r in rows)),
                "tier2_hmi_percentile": self.config.hmi_percentile_threshold,
                "tier2_hmi_ceiling": self.config.hmi_hard_ceiling,
                "tier2_buffer_km": self.config.reference_buffer_km,
                "assessment_mode": getattr(self.config, "assessment_mode", "baseline"),
                "realm": getattr(self.config, "realm", "terrestrial"),
                "archetype": getattr(self.config, "archetype", "conservation"),
                "scoring": "profile-first hybrid; non-compensatory (limiting-factor + "
                           "geometric mean); state and pressure separated; responsive "
                           "benchmark (uncapped). See METHODOLOGY_MASTER.md.",
                "methodology_references": [
                    "McElderry et al. (2024). DOI:10.32942/X2689N",
                    "McNellie et al. (2020). DOI:10.1111/gcb.15383",
                    "Yen et al. (2019). DOI:10.1002/eap.1970",
                    "Schipper et al. (2020). DOI:10.1111/gcb.14848",
                    "Kennedy et al. (2019). DOI:10.1111/gcb.14549",
                    "Hedges, Gurevitch & Curtis (1999). Ecology 80(4):1150-1156.",
                ],
            },
            # Scoring transparency (CS-1/CS-2/CS-7): which indicators are scored vs
            # shown-as-context vs screening-only vs removed — the honest register.
            "indicator_status": {
                "scored": [s.name for s in self.registry.scored()],
                "contextual": [s.name for s in self.registry.contextual()],
                "screening_only": [s.name for s in self.registry.all()
                                   if getattr(s, "evidence_tier", None) == "screening"],
                "pending_inputs": [s.name for s in self.registry.pending()],
                "removed": [s.name for s in self.registry.all() if not s.registered],
            },
            "scorecard": rows,
        }

        # Profile-first hybrid scoring (CS-4/CS-5) — the primary output.
        report["site_profiles"] = self._component_profiles(rows)

        # v0.2.4: product/dashboard-facing layer on top of each profile — one condition
        # score+class, one SEPARATE pressure score+class, and a confidence flag. Never
        # replaces the profile above; every consumer that needs it is still fed by it.
        from darukaa_reference import son_score
        report["son_summary"] = {
            site_id: son_score.son_summary(profile)
            for site_id, profile in report["site_profiles"].items()
        }

        # Legacy pillar summary retained (DEPRECATED) for back-compat/comparison only.
        report["pillar_summary_deprecated"] = self._pillar_summary(rows)

        # Write outputs
        if output_path:
            self._write(report, rows, output_path)

        return report

    def _classify_row(self, spec, comp) -> Dict:
        """Per-indicator dual-mode classification — always computed from the reference-
        relative benchmark this indicator was ALREADY scored against (never a fresh,
        separate comparison), plus a literature-anchored view where one exists."""
        from darukaa_reference import son_score, scoring
        if spec is None or not getattr(spec, "scoring_eligible", False):
            return {"reference_relative": None, "literature_anchored": None}
        benchmark = getattr(comp, "tier2_benchmark", None)
        estimator = getattr(comp, "tier2_benchmark_estimator", None) or "robust_z"
        normalized = scoring.normalize(benchmark, estimator) if benchmark is not None else None
        return son_score.classify_indicator(
            spec.name, normalized_score=normalized, raw_value=getattr(comp, "site_value", None))

    def _component_profiles(self, rows: List[Dict]) -> Dict[str, Dict]:
        """Profile-first hybrid scoring per site (CS-4/CS-5).

        Only SCORED indicators (registry.scored(): active AND computed-eligible) enter.
        This is what excludes CERI, range-overlap richness, and DW-redundant indicators
        from the score automatically. State (C1-C3) and pressure (C4) are aggregated on
        separate axes via the limiting-factor + non-compensatory geometric mean, and
        combined only into the condition x pressure matrix cell.

        Uses the SIGNED, uncapped benchmark (tier2_benchmark). Indicators whose benchmark
        has not yet been propagated upstream are skipped — the legacy capped ratio is
        never used here.
        """
        scored_names = {s.name for s in self.registry.scored()}
        by_site: Dict[str, List[Dict]] = {}
        for r in rows:
            if r["indicator"] not in scored_names:
                continue
            if r.get("tier2_benchmark") is None or not r.get("construct"):
                continue
            by_site.setdefault(r["site_id"], []).append({
                "name": r["indicator"],
                "construct": r["construct"],
                "subdimension": r.get("subdimension") or "_",
                "value": r["tier2_benchmark"],
                "estimator": r.get("tier2_benchmark_estimator") or "robust_z",
            })

        profiles = {}
        for site_id, benches in by_site.items():
            profiles[site_id] = scoring.build_site_profile(
                benches,
                seed_kernel=getattr(self.config, "use_seed_kernel", False),
                seed_delta=getattr(self.config, "seed_kernel_delta", 0.5))
        return profiles

    def _pillar_summary(self, rows: List[Dict]) -> List[Dict]:
        """DEPRECATED (v0.2.0). Legacy pillar means over the capped intactness ratio,
        retained only for back-compat/comparison. Superseded by _component_profiles
        (profile-first, non-compensatory). Do not use for client output."""
        from collections import defaultdict

        pillar_vals = defaultdict(list)
        for r in rows:
            if r["pillar"] and r["tier2_intactness"] is not None:
                pillar_vals[r["pillar"]].append(r["tier2_intactness"])

        # v0.2.0: corrected labels. Pillar 3 was mislabelled "Population Size" though no
        # population size is measured (B8); extinction-risk pillar is no longer scored (F1-F3).
        pillar_names = {
            1: "Ecosystem Extent (legacy)",
            2: "Ecosystem Condition (legacy)",
            3: "Faunal abundance/activity indices (legacy; NOT population size)",
            4: "Species representation (legacy; extinction-risk retired from scoring)",
            5: "Threats & Pressures (contextual; scored on separate axis)",
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

        # Evidence-graded HTML report is ALWAYS emitted (standard pipeline output, CS-10).
        try:
            from darukaa_reference import html_report
            project_name = getattr(self.config, "archetype", "Darukaa").title() + " Assessment"
            html_path = html_report.write_html(report, str(out.with_suffix(".html")), project_name)
            logger.info(f"Evidence-graded HTML report written to {html_path}")
        except Exception as e:
            logger.warning(f"HTML report generation failed (non-fatal): {e}")


def _safe_round(val, digits=4):
    """Round a value safely, handling None."""
    if val is None:
        return None
    return round(float(val), digits)
