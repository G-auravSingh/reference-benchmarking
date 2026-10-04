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

        # Runtime toggle (Q7): never compute REMOVED (registered=False) or deactivated
        # indicators. Contextual/screening indicators still run (they are shown, not scored).
        indicators = [s for s in indicators if getattr(s, "registered", True)
                      and getattr(s, "active", True)]

        # REAL FIX (round 2): config.realm ("terrestrial" | "aquatic" |
        # "mixed") was already loaded and logged every run, but never
        # actually used to filter anything — confirmed directly, not
        # assumed, before completing it. The FIRST version of this fix
        # filtered by `module` (core/aquatic/...), which was too coarse:
        # checked directly against real extraction logic and found 5 of
        # the 12 currently-scored "core" indicators give a degenerate,
        # misleading value on open water (chm: canopy height ~0m on a
        # lake; forest_loss_rate: trivially ~0% on a lake;
        # natural_habitat: DW_NATURAL_CLASSES excludes water entirely, so
        # a pristine lake would wrongly show ~0% "natural"; cpland: a
        # land-vegetation classification layer; bii: PREDICTS is an
        # explicitly terrestrial model). `applicable_realms` (registry.py)
        # is the real, per-indicator-verified gate now — every one of the
        # 12 core-scored indicators and all 9 aquatic-module indicators
        # were checked individually before being set, not assumed from
        # their module tag. "mixed" (or an unrecognised realm) keeps
        # every indicator, preserving the exact prior behaviour for every
        # existing project/config unless realm is explicitly changed.
        realm = getattr(self.config, "realm", "terrestrial")
        if realm in ("terrestrial", "aquatic"):
            indicators = [s for s in indicators if realm in getattr(s, "applicable_realms", ("terrestrial", "aquatic", "mixed"))]
        # realm == "mixed" (or anything else): no realm filtering, same as before this fix.

        mode = getattr(self.config, "assessment_mode", "baseline")
        logger.info(f"Assessment mode: {mode} | realm={realm} "
                    f"| archetype={getattr(self.config,'archetype','conservation')}")
        logger.info(f"Realm filter kept {len(indicators)} indicator(s) for realm='{realm}'")
        if mode == "monitoring":
            logger.warning(
                "Monitoring mode: change-vs-baseline scoring requires a stored Year-0 "
                "baseline artifact and in-situ change metrics (OPEN_DECISIONS OD; not yet "
                "wired). Running baseline-style computation for this cycle.")

        n_scored = len([s for s in indicators if getattr(s, "scoring_eligible", False)])
        logger.info(f"Running {len(indicators)} indicators "
                    f"({n_scored} scored, rest contextual/screening): {[i.name for i in indicators]}")

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
        n_profiles = len(report.get("site_profiles", {}))
        logger.info(f"\n{'=' * 60}")
        logger.info(
            f"Pipeline complete: {n_complete}/{len(all_comparisons)} "
            f"indicator-site pairs benchmarked; {n_profiles} site profile(s) scored"
        )
        logger.info(f"Reports: {output_path}.json/.csv/.html")

        return report
