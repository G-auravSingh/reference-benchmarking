"""Profile-driven adaptive biodiversity assessment pipeline."""
from __future__ import annotations
from pathlib import Path
import copy
import pandas as pd
from .benchmark import ReferenceEngine
from .config import AssessmentConfig
from .evidence import load_evidence_csv
from .metrics import LakeMetrics
from .qa import qa_metrics
from .readiness import assess_readiness
from .report import write_assessment, write_project_html_report
from .scoring import build_scorecard, score_external_observations
from .site import area_ha, make_domains, read_kml
from .inputs import load_project_input
from .aggregation import aggregate_emu_scorecards
from .terrestrial import TerrestrialMetrics
from .water import WaterDetector

class AdaptivePipeline:
    def __init__(self,config):
        self.config=config
        errors=config.validate()
        if errors: raise ValueError('Invalid config: '+ '; '.join(errors))
    def _run_single(self,site_file,external_evidence_file=None,geometry=None,emu_id=None):
        if geometry is None:
            geom,parts=read_kml(site_file)
        else:
            geom=geometry; parts={emu_id or "EMU_001": geometry}
        domains=make_domains(geom,self.config.spatial.riparian_buffer_m,self.config.spatial.context_buffer_km)
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
            if realm in {"aquatic_lake","mixed"}:
                aquatic_metrics=[m for m in metric_results if m.metric in {"water_extent","water_persistence","ndci_proxy","red_reflectance_turbidity_proxy","surface_algal_bloom_frequency","riparian_ndvi","riparian_ndvi_sen_slope","shoreline_disturbance_fraction","landcover_composition"}]
                if aquatic_metrics:
                    lake_engine=LakeMetrics(self.config,WaterDetector(self.config))
                    lake_ref_engine=ReferenceEngine(self.config,lake_engine)
                    benchmarks.extend(lake_ref_engine.build(aquatic_metrics,domains["boundary"],baseline_start=start,baseline_end=end))
                    if lake_ref_engine.last_population is not None:
                        reference_populations["aquatic"] = lake_ref_engine.last_population.to_dict()

            if realm in {"terrestrial","mixed"}:
                terrestrial_metrics=[m for m in metric_results if m.metric in {"natural_landcover_fraction","terrestrial_ndvi","built_fraction"}]
                if terrestrial_metrics:
                    terr_engine=TerrestrialMetrics(self.config)
                    terr_ref_engine=ReferenceEngine(self.config,terr_engine)
                    if self.config.reference.automatic_enabled:
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
                    'least_disturbed_enabled':self.config.reference.least_disturbed_enabled,
                    'least_disturbed_quantile':self.config.reference.least_disturbed_quantile,
                    'manual_hmi_fallback_enabled':self.config.reference.manual_hmi_fallback_enabled,
                    'manual_hmi_threshold':self.config.reference.manual_hmi_threshold,
                    'manual_hmi_reference_state':self.config.reference.manual_hmi_reference_state,
                    'approval_is_QA_gated':True,
                    'automatic_escalation_is_finite':True,
                },
                'reference_populations': reference_populations,
            }
        )
        return {'geometry':geom,'parts':parts,'domains':domains,'metrics':metric_results,'metric_qa':metric_qa,'benchmarks':benchmarks,
                'reference_populations':reference_populations,'metric_concern':scored,'pillars':pillars,'overall':overall,
                'water_periods':water_periods,'landcover':landcover,'boundary_area_ha':area_ha(geom),'readiness':readiness,
                'evidence':evidence_df,'outputs':paths}

    def run(self, site_file, external_evidence_file=None, *, project_id=None, project_name=None, domain="auto"):
        """Run either a single supported input or a multi-EMU project.

        Every EMU is assessed independently first. Reference populations and scores
        are never pooled across incompatible ecological domains. Project aggregation
        is performed only after EMU-level outputs exist.
        """
        project = load_project_input(site_file, project_id=project_id, project_name=project_name, domain=domain)
        # Human-readable project folder; preserve project_id inside the manifest.
        import re
        project_folder = re.sub(r"[^A-Za-z0-9._-]+", "_", str(project.project_name or project.project_id)).strip("._") or "project"
        root_output = Path(self.config.output_dir) / project_folder
        root_output.mkdir(parents=True, exist_ok=True)
        emu_results = []
        metric_rows=[]; pillar_rows=[]
        project_evidence = None
        if external_evidence_file:
            project_evidence = load_evidence_csv(external_evidence_file)
            if "emu_id" not in project_evidence.columns:
                raise ValueError("Multi-EMU external evidence must include an 'emu_id' column; otherwise project-level evidence would be duplicated across EMUs.")
        original_output = self.config.output_dir
        try:
            for emu in project.emus:
                local_cfg = copy.deepcopy(self.config)
                local_cfg.output_dir = str(root_output / emu.emu_id)
                resolved_domain = emu.resolved_domain(project.project_domain)
                # A mixed project is routed at EMU level; profile selection is therefore
                # explicit per EMU rather than allowing aquatic metrics into terrestrial units.
                if resolved_domain == "aquatic":
                    local_cfg.profile.name = "aquatic_lake"
                elif resolved_domain == "terrestrial":
                    local_cfg.profile.name = "terrestrial"
                runner = AdaptivePipeline(local_cfg)
                emu_evidence_file = None
                if project_evidence is not None:
                    # Preserve the existing CSV contract by writing an EMU-scoped temporary
                    # file; evidence is never duplicated across EMUs.
                    import tempfile
                    evidence_tmp = Path(tempfile.mkdtemp(prefix=f"darukaa_evidence_{emu.emu_id}_")) / "external_evidence.csv"
                    project_evidence[project_evidence["emu_id"].astype(str) == str(emu.emu_id)].to_csv(evidence_tmp, index=False)
                    emu_evidence_file = str(evidence_tmp)
                result = runner._run_single(site_file, emu_evidence_file, geometry=emu.geometry, emu_id=emu.emu_id)
                result["emu_id"] = emu.emu_id
                result["emu_domain"] = resolved_domain
                result["emu_area_ha"] = emu.area_ha or area_ha(emu.geometry)
                result["parent_zone"] = emu.parent_zone
                result["input_attributes"] = emu.attributes
                emu_results.append(result)
                for m in result.get("metrics", []):
                    metric_rows.append({"emu_id":emu.emu_id,"area_ha":result["emu_area_ha"],"metric":m.metric,"value":m.value,"domain":resolved_domain})
                for _, row in (result.get("pillars") if hasattr(result.get("pillars"), "iterrows") else pd.DataFrame()).iterrows():
                    pillar_rows.append({"emu_id":emu.emu_id,"area_ha":result["emu_area_ha"],**row.to_dict()})
        finally:
            self.config.output_dir = original_output

        metric_agg=aggregate_emu_scorecards(metric_rows)
        pillar_agg=__import__("darukaa_adaptive.aggregation",fromlist=["aggregate_pillar_scores"]).aggregate_pillar_scores(pillar_rows)
        manifest={"project":project.to_dict(),"n_emus":len(project.emus),"emu_results":[{"emu_id":r["emu_id"],"domain":r["emu_domain"],"area_ha":r["emu_area_ha"],"output":r.get("outputs")} for r in emu_results],"aggregation":{"metric_rows":metric_agg.to_dict("records"),"pillar_rows":pillar_agg.to_dict("records")}}
        manifest_path=root_output/"project_assessment_manifest.json"
        manifest_path.write_text(__import__("json").dumps(manifest,indent=2,default=str),encoding="utf-8")
        metric_agg.to_csv(root_output/"project_metric_aggregation.csv",index=False)
        pillar_agg.to_csv(root_output/"project_pillar_aggregation.csv",index=False)
        project_report = write_project_html_report(root_output, project, emu_results, metric_agg, pillar_agg, manifest)
        manifest["project_report"] = project_report
        manifest_path.write_text(__import__('json').dumps(manifest, indent=2, default=str), encoding='utf-8')
        return {"project":project,"emus":emu_results,"metric_aggregation":metric_agg,"pillar_aggregation":pillar_agg,"manifest":manifest,"output_dir":root_output,"project_report":project_report}

LakePipeline=AdaptivePipeline
