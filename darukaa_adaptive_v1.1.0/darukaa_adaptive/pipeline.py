"""Profile-driven adaptive biodiversity assessment pipeline."""
from __future__ import annotations
from pathlib import Path
import pandas as pd
from .benchmark import ReferenceEngine
from .config import AssessmentConfig
from .evidence import load_evidence_csv
from .metrics import LakeMetrics
from .qa import qa_metrics
from .readiness import assess_readiness
from .report import write_assessment
from .scoring import build_scorecard, score_external_observations
from .site import area_ha, make_domains, read_kml
from .terrestrial import TerrestrialMetrics
from .water import WaterDetector

class AdaptivePipeline:
    def __init__(self,config):
        self.config=config
        errors=config.validate()
        if errors: raise ValueError('Invalid config: '+ '; '.join(errors))
    def run(self,site_file,external_evidence_file=None,tier1_reference_file=None,tier1_reference_csv=None):
        geom,parts=read_kml(site_file); domains=make_domains(geom,self.config.spatial.riparian_buffer_m,self.config.spatial.context_buffer_km)
        if tier1_reference_file: self.config.reference.tier1_reference_kml=str(tier1_reference_file)
        if tier1_reference_csv: self.config.reference.tier1_reference_csv=str(tier1_reference_csv)
        start,end=self.config.temporal.baseline_dates(); realm=self.config.profile.name
        metric_results=[]
        if realm in {'aquatic_lake','mixed'} or self.config.profile.allow_terrestrial_metrics is False:
            if realm!='terrestrial':
                water=WaterDetector(self.config); engine=LakeMetrics(self.config,water); metric_results=engine.run(domains['boundary'],domains['riparian_fixed'],start,end)
        if realm in {'terrestrial','mixed'} or self.config.profile.allow_terrestrial_metrics:
            metric_results.extend(TerrestrialMetrics(self.config).run(domains['boundary'],start,end))
        metric_qa=qa_metrics(metric_results)
        benchmarks=[]
        reference_populations={}
        if metric_results:
            tier1_geometry = None
            if tier1_reference_file and self.config.reference.tier1_enabled:
                tier1_geometry = ReferenceEngine(self.config, LakeMetrics(self.config, WaterDetector(self.config))).build_tier1_geometry(tier1_reference_file)

            if realm in {"aquatic_lake","mixed"}:
                aquatic_metrics=[m for m in metric_results if m.metric in {"water_extent","water_persistence","ndci_proxy","red_reflectance_turbidity_proxy","surface_algal_bloom_frequency","riparian_ndvi","riparian_ndvi_sen_slope","shoreline_disturbance_fraction","landcover_composition"}]
                if aquatic_metrics:
                    lake_engine=LakeMetrics(self.config,WaterDetector(self.config))
                    lake_ref_engine=ReferenceEngine(self.config,lake_engine)
                    benchmarks.extend(lake_ref_engine.build(aquatic_metrics,domains["boundary"],tier1_geometry=tier1_geometry,baseline_start=start,baseline_end=end))
                    if lake_ref_engine.last_population is not None:
                        reference_populations["aquatic"] = lake_ref_engine.last_population.to_dict()

            if realm in {"terrestrial","mixed"}:
                terrestrial_metrics=[m for m in metric_results if m.metric in {"natural_landcover_fraction","terrestrial_ndvi","built_fraction"}]
                if terrestrial_metrics:
                    terr_engine=TerrestrialMetrics(self.config)
                    terr_ref_engine=ReferenceEngine(self.config,terr_engine)
                    if self.config.reference.automatic_enabled and self.config.reference.tier2_enabled:
                        pop=terr_ref_engine.auto.terrestrial_candidate(domains["boundary"], start=start, end=end)
                        terr_ref_engine.last_population=pop
                        reference_populations["terrestrial"] = pop.to_dict()
                    else:
                        pop=None
                    for m in terrestrial_metrics:
                        rv=terr_ref_engine._metric_reference_value(m.metric,pop.geometry,start,end) if pop is not None and pop.geometry is not None else None
                        from .benchmark import benchmark_metric
                        benchmarks.append(benchmark_metric(
                            m.metric,m.value,None,rv,allow_tier2=True,
                            tier2_approved=bool(pop and pop.approval),
                            reference_level="auto_terrestrial",
                            reference_n=(pop.candidate_pixels if pop else None),
                            reference_method=(pop.method if pop else "automatic_reference_disabled"),
                            reference_state=(pop.reference_state if pop else ""),
                            reference_approval_basis=("automated_reference_QA" if pop and pop.approval else "not_approved"),
                            reference_diagnostics=(pop.diagnostics if pop else {}),
                        ))
        scored,pillars,overall=build_scorecard(metric_results,benchmarks,self.config)
        evidence_df=pd.DataFrame()
        if external_evidence_file:
            evidence_df=load_evidence_csv(external_evidence_file)
            edf,epill,eo=score_external_observations(evidence_df,self.config)
            scored=pd.concat([scored,edf],ignore_index=True); pillars=__import__('darukaa_adaptive.scoring',fromlist=['aggregate_pillars']).aggregate_pillars(scored,self.config); overall=__import__('darukaa_adaptive.scoring',fromlist=['aggregate_overall']).aggregate_overall(pillars,self.config)
        readiness=assess_readiness(self.config,area_ha(geom),metric_results,benchmarks,overall,evidence_df)
        water_periods=[]; landcover=None
        if realm!='terrestrial':
            water=WaterDetector(self.config); water_periods=water.period_metrics(domains['boundary'],[{'start':start,'end':end}]); landcover=LakeMetrics(self.config,water).landcover_composition(domains['boundary'],start,end)
        paths=write_assessment(
            self.config.output_dir,self.config,site_file,area_ha(geom),domains,metric_results,water_periods,readiness,
            benchmarks=benchmarks,scored_df=scored,pillar_df=pillars,overall=overall,landcover=landcover,
            metric_qa=metric_qa,evidence_df=evidence_df,
            extra_manifest={
                'reference_policy':{
                    'automatic_enabled':self.config.reference.automatic_enabled,
                    'tier1_enabled':self.config.reference.tier1_enabled,
                    'tier2_enabled':self.config.reference.tier2_enabled,
                    'manual_reference_optional':True,
                    'approval_is_QA_gated':True,
                },
                'reference_populations': reference_populations,
            }
        )
        return {'geometry':geom,'parts':parts,'domains':domains,'metrics':metric_results,'metric_qa':metric_qa,'benchmarks':benchmarks,
                'reference_populations':reference_populations,'metric_concern':scored,'pillars':pillars,'overall':overall,
                'water_periods':water_periods,'landcover':landcover,'boundary_area_ha':area_ha(geom),'readiness':readiness,
                'evidence':evidence_df,'outputs':paths}

LakePipeline=AdaptivePipeline
