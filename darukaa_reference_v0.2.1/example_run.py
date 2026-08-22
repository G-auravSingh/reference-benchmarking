#!/usr/bin/env python3
"""
Example: Full Darukaa Reference Benchmarking Pipeline
=====================================================

Demonstrates the complete workflow:
    1. Load a KML file with project sites
    2. Resolve ecoregions for each site
    3. Compute 7 indicators per site
    4. Derive Tier 1 (ecoregion-wide) and Tier 2 (least-disturbed) references
    5. Run statistical comparisons (Hedges' g, permutation tests, bootstrap CIs)
    6. Output a profile-first scorecard (JSON + CSV) and an evidence-graded HTML report

Prerequisites:
    - Google Earth Engine authenticated: `earthengine authenticate`
    - Config file pointing to local rasters (GLOBIO4, SEED)
    - A KML file with project site boundaries

Usage:
    python example_run.py --kml path/to/sites.kml --config config.yaml
"""

import argparse
import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("darukaa_reference")


def main():
    parser = argparse.ArgumentParser(
        description="Darukaa Reference Benchmarking Pipeline"
    )
    parser.add_argument(
        "--kml", required=True, help="Path to KML/KMZ/GeoJSON with project sites"
    )
    parser.add_argument(
        "--config", default="config.yaml", help="Path to YAML config (default: config.yaml)"
    )
    parser.add_argument(
        "--output", default=None, help="Output path (default: from config)"
    )
    parser.add_argument(
        "--indicators", nargs="*", default=None,
        help="Specific indicators to run (default: all registered)"
    )
    parser.add_argument(
        "--gee-only", action="store_true",
        help="Run only GEE-based indicators (skip local rasters)"
    )
    args = parser.parse_args()

    # --- Import and initialise ---
    from darukaa_reference import Pipeline
    from darukaa_reference.config import Config
    from darukaa_reference.indicators import create_default_registry

    # Load config
    config = Config.from_yaml(args.config)

    # Override indicators if specified
    if args.indicators:
        config.enabled_indicators = args.indicators

    # Create registry
    registry = create_default_registry()

    # If --gee-only, keep only GEE indicators
    if args.gee_only:
        gee_names = [s.name for s in registry.by_source("gee")]
        config.enabled_indicators = gee_names
        logger.info(f"GEE-only mode: running {gee_names}")

    # Initialise GEE
    logger.info("Initialising Google Earth Engine...")
    import ee
    try:
        if config.gee_service_account and config.gee_key_path:
            credentials = ee.ServiceAccountCredentials(
                config.gee_service_account, config.gee_key_path
            )
            ee.Initialize(credentials, project=config.gee_project)
        else:
            ee.Initialize(project=config.gee_project or None)
        logger.info("GEE initialised successfully")
    except Exception as e:
        logger.error(f"GEE initialisation failed: {e}")
        logger.error("Run 'earthengine authenticate' first")
        sys.exit(1)

    # --- Run pipeline ---
    pipeline = Pipeline(config, registry)
    report = pipeline.run(
        site_path=args.kml,
        output_path=args.output,
    )

    # --- Print summary (profile-first, v0.2.0) ---
    print("\n" + "=" * 70)
    print("EVIDENCE-GRADED SUMMARY")
    print("=" * 70)

    st = report.get("indicator_status", {})
    print(f"  Scored: {len(st.get('scored', []))} | Contextual: {len(st.get('contextual', []))} "
          f"| Screening: {len(st.get('screening_only', []))} | Pending: {len(st.get('pending_inputs', []))} "
          f"| Removed: {len(st.get('removed', []))}")
    print(f"  Scored indicators: {', '.join(st.get('scored', [])) or '—'}")

    for site_id, prof in report.get("site_profiles", {}).items():
        cond = prof.get("condition", {})
        sens = cond.get("sensitivity", {})
        stab = "stable" if sens.get("stable") else "UNSTABLE"
        print(f"\n  ── {site_id} ── decision: {prof.get('matrix_cell')}")
        for comp, cs in prof.get("components", {}).items():
            print(f"     {comp:16s} score={cs.get('headline'):.3f}  "
                  f"(limiting: {cs.get('limiting_subdimension')})")
        if cond.get("rollup") is not None:
            print(f"     condition roll-up: {cond['rollup']:.3f} "
                  f"(min {cond['minimum']:.3f} @ {cond['minimum_component']}; sensitivity {stab})")
        if prof.get("pressure", {}).get("headline") is not None:
            print(f"     pressure axis:     {prof['pressure']['headline']:.3f}")

    out_base = args.output or (config.output_dir + "/benchmark_scorecard")
    print(f"\n  Reports written: {out_base}.json / .csv / .html  (open the .html Evidence Record)")
    print("=" * 70)


# --- Alternative: Minimal programmatic usage ---

def minimal_example():
    """
    Absolute minimum code to run the pipeline.

    Useful for integrating into existing Darukaa.Earth codebase.
    """
    from darukaa_reference import Pipeline

    pipeline = Pipeline.from_yaml("config.yaml")
    report = pipeline.run("sites.kml", output_path="output/scorecard")
    return report


# --- Alternative: Adding a custom indicator ---

def custom_indicator_example():
    """
    Shows how to register a new indicator without touching core code.

    Example: Adding CPLAND (connectivity metric from Darukaa's Pillar 1).
    """
    from darukaa_reference import Pipeline, IndicatorRegistry
    from darukaa_reference.config import Config
    from darukaa_reference.indicators import create_default_registry

    # Start with defaults
    registry = create_default_registry()

    # Register your custom indicator
    def extract_cpland(geometry, config):
        """Your CPLAND extraction logic here."""
        # This could query your internal Darukaa API, compute from rasters, etc.
        return {"value": 0.2135, "pixels": None}

    registry.register(
        name="cpland",
        display_name="Landscape Connectivity (CPLAND)",
        source_type="api",  # or "gee", "local_raster", "in_situ"
        extract_fn=extract_cpland,
        unit="%",
        value_range=(0.0, 100.0),
        citation="McGarigal, K. & Marks, B.J. (1995). FRAGSTATS. USDA Forest Service.",
        tier2_eligible=True,
        pillar=1,
    )

    # Run with the extended registry
    config = Config.from_yaml("config.yaml")
    pipeline = Pipeline(config, registry)
    report = pipeline.run("sites.kml")
    return report


if __name__ == "__main__":
    main()
