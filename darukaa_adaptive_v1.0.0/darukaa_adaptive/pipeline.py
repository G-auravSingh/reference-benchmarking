"""Generalized assessment orchestration for terrestrial, aquatic and mixed sites."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional

import pandas as pd

from .benchmark import ReferenceEngine, benchmark_observation
from .config import AssessmentConfig
from .edna import edna_to_observations, load_edna_csv
from .metrics import LakeMetrics
from .observations import load_observations
from .readiness import assess_readiness
from .report import write_assessment
from .registry import PILLARS
from .scoring import aggregate_overall, aggregate_pillars, score_metric
from .site import area_ha, make_domains, read_kml
from .terrestrial_metrics import TerrestrialMetrics
from .water import WaterDetector


class AssessmentPipeline:
    def __init__(self, config: AssessmentConfig):
        self.config = config
        errors = config.validate()
        if errors:
            raise ValueError("Invalid config: " + "; ".join(errors))

    def run(self, site_file, field_csv=None, acoustic_csv=None, edna_csv=None, edna_pdf=None, edna_html=None, krona_html=None):
        geom, parts = read_kml(site_file)
        domains = make_domains(geom, self.config.spatial.riparian_buffer_m, self.config.spatial.context_buffer_km, self.config.spatial.littoral_band_m)
        baseline_start, baseline_end = self.config.temporal.baseline_dates()
        all_metrics = []
        water_periods = []
        landcover = {}

        water = WaterDetector(self.config)
        if self.config.profile.aquatic_enabled:
            aquatic = LakeMetrics(self.config, water)
            all_metrics.extend(aquatic.run(domains["boundary"], domains["riparian_fixed"], baseline_start, baseline_end))
            water_periods = water.period_metrics(domains["boundary"], __import__("darukaa_adaptive.periods", fromlist=["month_periods"]).month_periods(*self.config.temporal.baseline_inclusive_window()))
            landcover = aquatic.landcover_composition(domains["boundary"], baseline_start, baseline_end)
        else:
            aquatic = None

        if self.config.profile.terrestrial_enabled:
            terr = TerrestrialMetrics(self.config)
            all_metrics.extend(terr.run(domains["terrestrial_context"], baseline_start, baseline_end))

        observations = []
        external_sources = [(field_csv, "field"), (acoustic_csv, "acoustic")]
        for path, source in external_sources:
            if path:
                observations.extend(load_observations(path, source))
        edna_records = []
        if edna_csv:
            edna_records = load_edna_csv(edna_csv)
            observations.extend(edna_to_observations(edna_records))

        ref_metrics = all_metrics
        reference_engine = ReferenceEngine(self.config, aquatic if aquatic is not None else terr)
        reference_engine.characterize_site(domains["boundary"])
        benchmarks = reference_engine.build(ref_metrics, domains["boundary"], baseline_start, baseline_end, observations)

        scored_df, pillar_df, overall = __import__("darukaa_adaptive.scoring", fromlist=["build_scorecard"]).build_scorecard(ref_metrics, benchmarks, self.config)
        ext_only = []
        # External observations that are not already present in EO metrics are scored here.
        existing = {m.metric for m in ref_metrics}
        for rec in observations:
            if rec.metric in existing:
                continue
            ext_only.append(rec)
        if ext_only:
            for rec in ext_only:
                b = benchmark_observation(rec, self.config)
                # use the same metric score shape and append to scorecard
                scored_df = pd.concat([scored_df, pd.DataFrame([{
                    "metric": rec.metric, "pillar": rec.pillar, "construct": "external", "subdimension": "external",
                    "domain": rec.source_type, "raw_value": rec.raw_value, "units": rec.units, "direction": rec.direction,
                    "evidence_class": rec.evidence_class, "source_type": rec.source_type, "reference_value": b.reference_value,
                    "reference_level": b.reference_level, "reference_source": b.reference_source, "reference_n": b.reference_n,
                    "reference_se": b.reference_se, "raw_relative_ratio": b.raw_relative_ratio, "signed_benchmark": b.signed_benchmark,
                    "percentile_in_reference": b.percentile_in_reference, "intactness_score_0_100": b.intactness_score_0_100,
                    "concern_label": None if b.intactness_score_0_100 is None else __import__("darukaa_adaptive.scoring", fromlist=["concern_label"]).concern_label(b.intactness_score_0_100),
                    "score_eligible": b.reference_approved_for_scoring, "score_status": "scored" if b.reference_approved_for_scoring else b.benchmark_status,
                    "reference_approved_for_scoring": b.reference_approved_for_scoring, "notes": rec.notes,
                }])], ignore_index=True)
            pillar_df = aggregate_pillars(scored_df, self.config); overall = aggregate_overall(pillar_df, self.config)

        for m in all_metrics:
            hit = scored_df[scored_df["metric"] == m.metric]
            if not hit.empty:
                m.score_eligible = bool(hit.iloc[0]["score_eligible"])

        qa = self._qa(scored_df)
        readiness = assess_readiness(self.config, area_ha(geom), all_metrics, benchmarks, overall, observations=observations, reference_diagnostics=reference_engine.diagnostics)
        result = {
            "config": self.config.to_dict(),
            "geometry": geom, "parts": parts, "domains": domains, "metrics": all_metrics, "benchmarks": benchmarks,
            "metric_concern": scored_df, "pillars": pillar_df, "overall": overall, "water_periods": water_periods,
            "landcover": landcover, "boundary_area_ha": area_ha(geom), "readiness": readiness, "qa": qa,
            "observations": observations, "edna": edna_records, "reference_diagnostics": reference_engine.diagnostics,
            "inputs": {"site_file": str(site_file), "field_csv": field_csv, "acoustic_csv": acoustic_csv, "edna_csv": edna_csv, "edna_pdf": edna_pdf, "edna_html": edna_html, "krona_html": krona_html},
        }
        outputs = write_assessment(self.config.output_dir, self.config, site_file, result)
        result["outputs"] = outputs
        return result

    @staticmethod
    def _qa(scored_df: pd.DataFrame):
        rows = []
        for _, r in scored_df.iterrows():
            flags = []
            if pd.isna(r.get("raw_value")): flags.append("missing_raw_value")
            if r.get("score_eligible") and pd.isna(r.get("reference_value")): flags.append("missing_reference")
            status = "pass" if not flags else "review"
            rows.append({"metric": r.get("metric"), "pillar": r.get("pillar"), "qa_pass": status == "pass", "qa_status": status, "qa_flags": "; ".join(flags)})
        return pd.DataFrame(rows)


# Backward-compatible alias.
LakePipeline = AssessmentPipeline
