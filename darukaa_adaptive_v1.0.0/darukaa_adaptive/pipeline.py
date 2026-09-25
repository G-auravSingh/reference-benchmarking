"""Top-level adaptive assessment runner."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .benchmark import ReferenceEngine
from .config import AssessmentConfig
from .metrics import LakeMetrics
from .readiness import assess_readiness
from .report import write_assessment
from .qa import qa_metrics
from .scoring import build_scorecard
from .site import area_ha, make_domains, read_kml
from .water import WaterDetector


class LakePipeline:
    def __init__(self, config: AssessmentConfig):
        self.config = config
        errors = config.validate()
        if errors:
            raise ValueError("Invalid config: " + "; ".join(errors))

    def _periods(self):
        start, end = self.config.temporal.baseline_dates()
        return [{"label": self.config.temporal.baseline_label, "start": start, "end": end}]

    def run(
        self,
        site_file: str | Path,
        tier1_reference_file: Optional[str | Path] = None,
        tier1_reference_csv: Optional[str | Path] = None,
    ):
        geom, parts = read_kml(site_file)
        domains = make_domains(
            geom,
            self.config.spatial.riparian_buffer_m,
            self.config.spatial.context_buffer_km,
        )

        if tier1_reference_file:
            self.config.reference.tier1_reference_kml = str(tier1_reference_file)
        if tier1_reference_csv:
            self.config.reference.tier1_reference_csv = str(tier1_reference_csv)

        water = WaterDetector(self.config)
        metrics = LakeMetrics(self.config, water)
        baseline_start, baseline_end = self.config.temporal.baseline_dates()
        metric_results = metrics.run(domains["boundary"], domains["riparian_fixed"], baseline_start, baseline_end)
        metric_qa = qa_metrics(metric_results)

        reference_engine = ReferenceEngine(self.config, metrics)
        tier1_geometry = reference_engine.build_tier1_geometry(self.config.reference.tier1_reference_kml)
        tier2_geometry, tier2_status = reference_engine.build_tier2_candidate_geometry(
            domains["context"], baseline_start, baseline_end
        )
        benchmarks = reference_engine.build(
            metric_results,
            domains["boundary"],
            tier1_geometry=tier1_geometry,
            tier2_geometry=tier2_geometry,
            baseline_start=baseline_start,
            baseline_end=baseline_end,
        )

        scored_df, pillar_df, overall = build_scorecard(metric_results, benchmarks, self.config)
        eligibility = {row["metric"]: bool(row["score_eligible"]) for _, row in scored_df.iterrows()} if not scored_df.empty else {}
        for metric_result in metric_results:
            metric_result.score_eligible = eligibility.get(metric_result.metric, False)
        readiness = assess_readiness(self.config, area_ha(geom), metric_results, benchmarks, overall)

        water_periods = water.period_metrics(domains["boundary"], [{"start": baseline_start, "end": baseline_end}])
        landcover = metrics.landcover_composition(domains["boundary"], baseline_start, baseline_end)

        paths = write_assessment(
            self.config.output_dir,
            self.config,
            site_file,
            area_ha(geom),
            domains,
            metric_results,
            water_periods,
            readiness,
            benchmarks=benchmarks,
            scored_df=scored_df,
            pillar_df=pillar_df,
            overall=overall,
            landcover=landcover,
            metric_qa=metric_qa,
            extra_manifest={
                "baseline_window_inclusive": {
                    "start": self.config.temporal.baseline_start_date,
                    "end": self.config.temporal.baseline_end_date,
                    "label": self.config.temporal.baseline_label,
                },
                "reference_policy": {
                    "tier1_preferred": True,
                    "tier1_approved_for_scoring": self.config.reference.tier1_approved_for_scoring,
                    "tier2_is_candidate_reference": True,
                    "tier2_candidate_status": tier2_status,
                    "tier2_approved_for_scoring": self.config.reference.tier2_approved_for_scoring,
                },
            },
        )
        return {
            "geometry": geom,
            "parts": parts,
            "domains": domains,
            "metrics": metric_results,
            "metric_qa": metric_qa,
            "benchmarks": benchmarks,
            "metric_concern": scored_df,
            "pillars": pillar_df,
            "overall": overall,
            "water_periods": water_periods,
            "landcover": landcover,
            "boundary_area_ha": area_ha(geom),
            "readiness": readiness,
            "outputs": paths,
        }
