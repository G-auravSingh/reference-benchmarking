"""
Pipeline
========

The top-level orchestrator that ties all components together.

    KML → SiteLoader → EcoregionResolver → ReferenceSelector → StatisticalComparison → ReportGenerator

Usage::

    from darukaa_reference import Pipeline

    pipeline = Pipeline.from_yaml("config.yaml")
    report = pipeline.run("project_sites.kml")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Union

from darukaa_reference.config import Config
from darukaa_reference.ecoregion import EcoregionResolver
from darukaa_reference.reference import ReferenceResult, ReferenceSelector
from darukaa_reference.registry import IndicatorRegistry
from darukaa_reference.report import ReportGenerator
from darukaa_reference.site_loader import SiteLoader
from darukaa_reference.statistics import ComparisonResult, StatisticalComparison

logger = logging.getLogger(__name__)


class Pipeline:
    """
    End-to-end biodiversity reference benchmarking pipeline.

    Orchestrates:
        1. Load site geometries from KML/GeoJSON/Shapefile
        2. Resolve ecoregion for each site
        3. For each (site × indicator): extract site value, compute Tier 1
           and Tier 2 reference benchmarks
        4. Run statistical comparisons
        5. Generate structured scorecard report
    """

    def __init__(self, config: Config, registry: IndicatorRegistry):
        self.config = config
        self.registry = registry
        self.loader = SiteLoader()
        self.resolver = EcoregionResolver(config)
        self.reference = ReferenceSelector(config)
        self.stats = StatisticalComparison(config)
        self.reporter = ReportGenerator(config, registry)

    @classmethod
    def from_yaml(cls, config_path: str, registry: Optional[IndicatorRegistry] = None) -> "Pipeline":
        """
        Create a pipeline from a YAML config file.

        If no registry is provided, creates one with all default indicators.
        """
        config = Config.from_yaml(config_path)

        if registry is None:
            from darukaa_reference.indicators import create_default_registry
            registry = create_default_registry()

        return cls(config, registry)

    def run(
        self,
        site_path: Union[str, List[str]],
        output_path: Optional[str] = None,
    ) -> Dict:
        """
        Execute the full pipeline.

        Parameters
        ----------
        site_path : str or list of str
            Path(s) to KML/GeoJSON/Shapefile with project sites.
        output_path : str, optional
            Where to write the report. If None, uses config.output_dir.

        Returns
        -------
        dict
            The full report dictionary.
        """
        # --- 1. Load sites ---
        logger.info("=" * 60)
        logger.info("DARUKAA REFERENCE BENCHMARKING PIPELINE")
        logger.info("=" * 60)

        if isinstance(site_path, list):
            sites = self.loader.load_multiple(site_path)
        else:
            sites = self.loader.load(site_path)

        logger.info(f"Loaded {len(sites)} sites")

        # --- 2. Resolve ecoregions ---
        logger.info("Resolving ecoregions...")
        sites = self.resolver.resolve(sites)

        # Build site metadata dict
        site_metadata = {}
        for _, row in sites.iterrows():
            site_metadata[row["site_id"]] = {
                "ECO_ID": row.get("ECO_ID"),
                "ECO_NAME": row.get("ECO_NAME"),
                "BIOME_NAME": row.get("BIOME_NAME"),
                "REALM": row.get("REALM"),
            }

        # --- 3. Determine which indicators to run ---
        if self.config.enabled_indicators:
            indicators = [
                self.registry.get(name) for name in self.config.enabled_indicators
                if name in self.registry
            ]
        else:
            indicators = self.registry.all()

        logger.info(f"Running {len(indicators)} indicators: {[i.name for i in indicators]}")

        # --- 4. For each site × indicator: compute references ---
        all_ref_results: List[ReferenceResult] = []
        all_comparisons: List[ComparisonResult] = []

        for _, site_row in sites.iterrows():
            site_id = site_row["site_id"]
            eco_id = site_row.get("ECO_ID")
            site_geom = site_row.geometry

            logger.info(f"\n--- Site: {site_id} (Ecoregion: {eco_id}) ---")

            # Get ecoregion geometry for reference selection
            eco_geom = None
            if eco_id is not None:
                try:
                    eco_geom = self.resolver.get_ecoregion_geometry(int(eco_id))
                except Exception as e:
                    logger.warning(f"Could not get ecoregion geometry: {e}")

            for spec in indicators:
                logger.info(f"  Computing: {spec.display_name}...")

                # Compute references
                ref_result = self.reference.compute(
                    indicator_spec=spec,
                    site_geometry=site_geom,
                    site_id=site_id,
                    eco_id=eco_id,
                    eco_geometry=eco_geom,
                )
                all_ref_results.append(ref_result)

                # Statistical comparison
                comp = self.stats.compare(ref_result)
                all_comparisons.append(comp)

                # Log summary
                if comp.tier2_intactness is not None:
                    logger.info(
                        f"    → site={comp.site_value:.4f}, "
                        f"T2_ref={comp.tier2_reference:.4f}, "
                        f"intactness={comp.tier2_intactness:.1%}"
                    )
                elif comp.tier1_intactness is not None:
                    logger.info(
                        f"    → site={comp.site_value:.4f}, "
                        f"T1_ref={comp.tier1_reference:.4f}, "
                        f"intactness={comp.tier1_intactness:.1%}"
                    )
                elif comp.site_value is not None:
                    logger.info(f"    → site={comp.site_value:.4f} (no reference)")
                else:
                    logger.info("    → extraction failed")

        # --- 5. Generate report ---
        if output_path is None:
            output_path = str(
                Path(self.config.output_dir) / "benchmark_scorecard"
            )

        report = self.reporter.generate(
            comparisons=all_comparisons,
            site_metadata=site_metadata,
            output_path=output_path,
        )

        n_complete = sum(
            1 for c in all_comparisons
            if c.tier2_intactness is not None or c.tier1_intactness is not None
        )
        logger.info(f"\n{'=' * 60}")
        logger.info(
            f"Pipeline complete: {n_complete}/{len(all_comparisons)} "
            f"indicator-site pairs benchmarked"
        )
        logger.info(f"Report: {output_path}")

        return report
