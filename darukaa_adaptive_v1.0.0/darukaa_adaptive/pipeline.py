"""Top-level adaptive assessment runner."""
from __future__ import annotations

from pathlib import Path

from .config import AssessmentConfig
from .metrics import LakeMetrics
from .readiness import assess_readiness
from .report import write_assessment
from .site import area_ha, make_domains, read_kml
from .water import WaterDetector


class LakePipeline:
    def __init__(self, config: AssessmentConfig):
        self.config=config
        errors=config.validate()
        if errors: raise ValueError("Invalid config: " + "; ".join(errors))

    def run(self, site_file: str | Path):
        geom, parts=read_kml(site_file)
        domains=make_domains(geom,self.config.spatial.riparian_buffer_m,self.config.spatial.context_buffer_km)
        water=WaterDetector(self.config)
        metrics=LakeMetrics(self.config,water)
        metrics_out=metrics.run(domains["boundary"],domains["riparian_fixed"])
        start=f"{self.config.temporal.start_year}-01-01"; end=f"{self.config.temporal.end_year+1}-01-01"
        water_periods=water.period_metrics(domains["boundary"],[{"start":start,"end":end}])
        boundary_area=area_ha(geom)
        readiness=assess_readiness(self.config,boundary_area,metrics_out)
        paths=write_assessment(self.config.output_dir,self.config,site_file,boundary_area,domains,metrics_out,water_periods,readiness)
        return {"geometry":geom,"parts":parts,"domains":domains,"metrics":metrics_out,"water_periods":water_periods,
                "boundary_area_ha":boundary_area,"readiness":readiness,"outputs":paths}
