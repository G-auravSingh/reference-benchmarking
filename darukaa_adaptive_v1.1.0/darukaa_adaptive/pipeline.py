"""Profile-driven adaptive biodiversity assessment pipeline."""
from __future__ import annotations
from pathlib import Path
import copy
import json
import shutil
import pandas as pd
from .benchmark import ReferenceEngine
from .config import AssessmentConfig
from .evidence import load_evidence_csv
from .metrics import LakeMetrics
from .qa import qa_metrics
from .readiness import assess_readiness
from .report import write_assessment, write_project_report
from .scoring import build_scorecard, score_external_observations
from .site import area_ha, make_domains, read_kml
from .inputs import load_project_input
from .aggregation import (aggregate_emu_scorecards, aggregate_project_metric_scores, aggregate_project_pillars, build_emu_comparison_table)
from .terrestrial import TerrestrialMetrics
from .full_metrics import FullMetricEngine
from .registry import FULL_INDICATORS, effective_scoring_role
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

        # Full 0.2.7 calculator inventory.  These calculators are deliberately
        # adapted into v1 MetricResult objects; legacy reference/scoring logic is
        # never called.  Existing v1 profile metrics remain for compatibility.
        full_realm = 'aquatic' if realm == 'aquatic_lake' else realm
        if full_realm in {'terrestrial','aquatic','mixed'}:
            full_engine = FullMetricEngine(self.config)
            metric_results.extend(full_engine.run(
                domains['boundary'], realm=full_realm,
                temporal_window=f"{start}:{end}"
            ))
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
                        pressure_pop=terr_ref_engine.auto.terrestrial_pressure_reference_candidate(domains["boundary"], start=start, end=end)
                        reference_populations["terrestrial_pressure"] = pressure_pop.to_dict()
                    else:
                        pop=None
                        pressure_pop=None
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
        # Benchmark all newly migrated scored indicators against the approved
        # v1 reference population for their realm. Reference values are extracted
        # with the same calculator on the reference geometry, preserving metric
        # semantics and avoiding universal ratio assumptions.
        from .benchmark import benchmark_metric
        legacy_scored = [m for m in metric_results if m.metric in {x.name for x in FULL_INDICATORS}
                         and m.status == "calculated" and effective_scoring_role(next(x for x in FULL_INDICATORS if x.name == m.metric), self.config) in {"SCORED", "PRESSURE"}]
        # Reference metrics are calculated once per reference population, not once
        # per metric. The previous nested execution multiplied expensive GEE calls
        # by the number of scored indicators.
        ref_metric_cache = {}
        for m in legacy_scored:
            is_pressure = m.pillar == "P4_pressure"
            ref_pop = (reference_populations.get("aquatic") if m.domain == "aquatic" else
                       reference_populations.get("terrestrial_pressure" if is_pressure else "terrestrial"))
            pop_obj = None
            if m.domain == "aquatic" and 'lake_ref_engine' in locals():
                pop_obj = getattr(lake_ref_engine, "last_population", None)
            elif m.domain == "terrestrial" and 'terr_ref_engine' in locals():
                if is_pressure:
                    pop_obj = locals().get("pressure_pop")
                else:
                    pop_obj = getattr(terr_ref_engine, "last_population", None)

            if pop_obj is None or getattr(pop_obj, "geometry", None) is None:
                benchmarks.append(benchmark_metric(
                    m.metric, m.value, None, None, allow_tier2=True,
                    reference_level="none", reference_approval_basis="reference_population_unavailable",
                    reference_state="", reference_method=""
                ))
                continue

            cache_key = (m.domain, id(pop_obj))
            if cache_key not in ref_metric_cache:
                try:
                    scored_names = [x.metric for x in legacy_scored if x.domain == m.domain]
                    ref_result = FullMetricEngine(self.config).run(
                        pop_obj.geometry, realm=m.domain, temporal_window=f"{start}:{end}",
                        metric_names=scored_names
                    )
                    ref_metric_cache[cache_key] = {x.metric: x for x in ref_result}
                except Exception as exc:
                    ref_metric_cache[cache_key] = {"__error__": exc}

            ref_rows = ref_metric_cache[cache_key]
            if "__error__" in ref_rows:
                exc = ref_rows["__error__"]
                benchmarks.append(benchmark_metric(
                    m.metric, m.value, None, None, allow_tier2=True,
                    reference_level="none",
                    reference_approval_basis=f"reference_metric_failed:{type(exc).__name__}"
                ))
                continue

            ref_row = ref_rows.get(m.metric)
            rv = ref_row.value if ref_row else None
            ref_diag = {}
            if ref_row:
                ref_diag = {k: getattr(ref_row, k) for k in
                            ("std_dev","p05","p10","p25","p50","p75","p90","p95","valid_pixels")
                            if getattr(ref_row,k,None) is not None}
                # Robust-reference indicators use the median of the reference spatial
                # distribution as the central comparator; ratio-scale log-response
                # indicators retain the spatial mean. In both cases the distribution
                # diagnostics remain attached to the benchmark.
                ref_spec = next((x for x in FULL_INDICATORS if x.name == m.metric), None)
                if ref_spec is not None and ref_spec.reference_estimator == "robust_z" and getattr(ref_row, "p50", None) is not None:
                    rv = ref_row.p50
            benchmarks.append(benchmark_metric(
                m.metric, m.value, None, rv, allow_tier2=True,
                tier2_approved=bool(getattr(pop_obj, "approval", False)),
                reference_level=("auto_terrestrial_pressure" if (m.domain == "terrestrial" and is_pressure) else ("auto_terrestrial" if m.domain == "terrestrial" else "auto_aquatic")),
                reference_n=getattr(pop_obj, "candidate_pixels", None),
                reference_method=getattr(pop_obj, "method", "automatic_reference"),
                reference_state=getattr(pop_obj, "reference_state", ""),
                reference_approval_basis=("automated_reference_QA" if getattr(pop_obj, "approval", False) else "not_approved"),
                reference_diagnostics=ref_diag,
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
        root_output = Path(self.config.output_dir) / project.project_id
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
                scored_rows = result.get("metric_concern")
                if hasattr(scored_rows, "iterrows"):
                    for _, row in scored_rows.iterrows():
                        metric_rows.append({
                            "emu_id": emu.emu_id, "area_ha": result["emu_area_ha"],
                            "metric": row.get("metric"), "value": row.get("raw_value"),
                            "score_0_to_100": row.get("intactness_score_0_100"),
                            "score_eligible": row.get("score_eligible", False),
                            "domain": resolved_domain, "pillar": row.get("pillar"),
                            "subdimension": row.get("subdimension"),
                        })
                for _, row in (result.get("pillars") if hasattr(result.get("pillars"), "iterrows") else pd.DataFrame()).iterrows():
                    pillar_rows.append({"emu_id":emu.emu_id,"area_ha":result["emu_area_ha"],"domain":resolved_domain,**row.to_dict()})
        finally:
            self.config.output_dir = original_output

        raw_metric_agg=aggregate_emu_scorecards([r for r in metric_rows if "score_0_to_100" not in r])
        scored_metric_agg=aggregate_project_metric_scores([r for r in metric_rows if r.get("score_eligible", False)])
        pillar_agg=aggregate_project_pillars(pillar_rows)
        comparison=build_emu_comparison_table(pillar_rows,[r for r in metric_rows if "score_0_to_100" in r])
        condition_pillars=pillar_agg[pillar_agg["pillar"].isin(["P1_extent_configuration","P2_ecosystem_condition","P3_biodiversity_integrity"]) & pillar_agg["project_score_0_to_100"].notna()] if not pillar_agg.empty else pd.DataFrame()
        pressure=pillar_agg[(pillar_agg["pillar"] == "P4_pressure") & (pillar_agg["project_score_0_to_100"].notna())] if not pillar_agg.empty else pd.DataFrame()
        project_overall={"status":"insufficient_condition_coverage","condition_score_0_to_100":None,"condition_concern_label":None,
                         "pressure_intactness_score_0_to_100":None,"pressure_concern_label":None,
                         "pressure_score_0_to_100":None,
                         "condition_pillars":[],"condition_pillar_count":0,"condition_pillar_total":3,
                         "condition_coverage":"none","limiting_pillar":None,"limiting_emu":None}
        if not pressure.empty:
            ps=float(pressure.iloc[0]["project_score_0_to_100"]); project_overall.update({
                "pressure_intactness_score_0_to_100":ps,
                "pressure_score_0_to_100":ps,
                "pressure_concern_label":__import__('darukaa_adaptive.scoring',fromlist=['concern_label']).concern_label(ps)})
        n_cond=len(condition_pillars)
        project_overall["condition_pillars"]=condition_pillars["pillar"].astype(str).tolist() if n_cond else []
        project_overall["condition_pillar_count"]=int(n_cond)
        project_overall["condition_coverage"]=("complete" if n_cond==3 else "partial" if n_cond>0 else "none")
        min_cond=int(getattr(self.config.scoring,"min_condition_pillars",1))
        if n_cond>=min_cond:
            from .scoring import geometric_mean, concern_label
            cs=geometric_mean(condition_pillars["project_score_0_to_100"].astype(float).tolist())
            project_overall.update({"status":"condition_scored" if n_cond==3 else "condition_scored_partial",
                                    "condition_score_0_to_100":cs,"condition_concern_label":concern_label(cs)})
            idx=condition_pillars["project_score_0_to_100"].astype(float).idxmin(); project_overall["limiting_pillar"]=str(condition_pillars.loc[idx,"pillar"]); project_overall["limiting_emu"]=condition_pillars.loc[idx,"limiting_emu"]
        manifest={"project":project.to_dict(),"n_emus":len(project.emus),"emu_results":[{"emu_id":r["emu_id"],"domain":r["emu_domain"],"area_ha":r["emu_area_ha"],"output":r.get("outputs")} for r in emu_results],"aggregation":{"raw_metric_rows":raw_metric_agg.to_dict("records"),"scored_metric_rows":scored_metric_agg.to_dict("records"),"pillar_rows":pillar_agg.to_dict("records"),"emu_comparison":comparison.to_dict("records"),"project_overall":project_overall}}
        manifest_path=root_output/"project_assessment_manifest.json"
        manifest_path.write_text(__import__("json").dumps(manifest,indent=2,default=str),encoding="utf-8")
        raw_metric_agg.to_csv(root_output/"project_metric_raw_aggregation.csv",index=False)
        scored_metric_agg.to_csv(root_output/"project_metric_score_aggregation.csv",index=False)
        pillar_agg.to_csv(root_output/"project_pillar_aggregation.csv",index=False)
        comparison.to_csv(root_output/"emu_ecological_comparison.csv",index=False)
        (root_output/"project_overall_scorecard.json").write_text(__import__("json").dumps(project_overall,indent=2,default=str),encoding="utf-8")
        project_report=write_project_report(root_output, project, project_overall, pillar_agg, scored_metric_agg, comparison, emu_results, self.config)

        # Automated post-run output audit. These are review flags, not silent
        # corrections: extreme scores and incomplete condition coverage can be
        # scientifically legitimate, but must be visible to the analyst.
        qa_flags=[]
        if project_overall.get("status") == "insufficient_condition_coverage":
            qa_flags.append({"severity":"REVIEW","code":"condition_not_scored","message":"Project condition headline is not scoreable because no condition pillar is score-eligible; inspect evidence coverage."})
        elif project_overall.get("status") == "condition_scored_partial":
            qa_flags.append({"severity":"INFO","code":"partial_condition_coverage","message":f"Project condition score uses {project_overall.get('condition_pillar_count')}/3 condition pillars; missing pillars are not treated as zero."})
        ps=project_overall.get("pressure_intactness_score_0_to_100")
        if ps is not None and (float(ps) <= 5.0 or float(ps) >= 95.0):
            qa_flags.append({"severity":"REVIEW","code":"extreme_project_pressure_score","message":f"Project pressure score is {float(ps):.6g}/100; inspect the underlying P4 metric/reference scores before client interpretation."})
        if not comparison.empty and "score_0_to_100" in comparison.columns:
            pass
        score_rows=pd.DataFrame([r for r in metric_rows if r.get("score_eligible",False) and r.get("score_0_to_100") is not None])
        metric_extremes=[]
        if not score_rows.empty:
            for metric,g in score_rows.groupby("metric"):
                vals=pd.to_numeric(g["score_0_to_100"],errors="coerce").dropna()
                if len(vals):
                    zero_frac=float((vals <= 1e-12).mean()); hundred_frac=float((vals >= 100-1e-12).mean())
                    if zero_frac >= 0.75 or hundred_frac >= 0.75:
                        metric_extremes.append({"metric":str(metric),"n":int(len(vals)),"zero_fraction":zero_frac,"hundred_fraction":hundred_frac})
        if metric_extremes:
            qa_flags.append({"severity":"REVIEW","code":"metric_score_boundary_concentration","message":"One or more metrics have >=75% of EMU scores at a 0 or 100 boundary; inspect reference scale, denominator behaviour and metric distribution.","metrics":metric_extremes})
        qa_flags.append({"severity":"INFO","code":"reference_population_coverage","message":f"Reference populations generated: {sorted(reference_populations)}"})
        project_output_qa={"status":"review_required" if any(f["severity"]=="REVIEW" for f in qa_flags) else "pass","n_emus":len(project.emus),"flags":qa_flags}
        (root_output/"project_output_qa.json").write_text(json.dumps(project_output_qa,indent=2,default=str),encoding="utf-8")

        # Always create a self-contained project archive outside the project output
        # directory. This prevents runtime disconnects from destroying the only
        # copy of the generated reports/tables before the user can download them.
        archive_base = root_output.parent / f"{project.project_id}_assessment_outputs"
        archive_path = Path(shutil.make_archive(str(archive_base), "zip", root_dir=root_output.parent, base_dir=root_output.name))
        manifest["project_output_qa"] = project_output_qa
        manifest["output_archive"] = str(archive_path)
        manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
        return {"project":project,"emus":emu_results,"metric_aggregation":scored_metric_agg,"raw_metric_aggregation":raw_metric_agg,"pillar_aggregation":pillar_agg,"emu_comparison":comparison,"project_overall":project_overall,"project_report":str(project_report),"manifest":manifest,"output_dir":root_output,"project_output_qa":project_output_qa,"output_archive":str(archive_path)}

LakePipeline=AdaptivePipeline
