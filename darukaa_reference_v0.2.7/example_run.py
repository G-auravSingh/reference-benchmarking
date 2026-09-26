#!/usr/bin/env python3
"""
Example: Full Darukaa Reference Benchmarking Pipeline
=====================================================

Demonstrates the complete workflow:
    1. Load a KML file with project sites
    2. Resolve ecoregions for each site
    3. Benchmark every registered, eligible indicator per site (real count is
       live -- run create_default_registry() + contracts.apply_contracts() and
       check len(registry.all())/len(registry.scored()) rather than trusting a
       hardcoded number here; this docstring already drifted stale once,
       claiming "7 indicators" against a live registry that's actually 45
       registered / 12 scored)
    4. Derive Tier 1 (ecoregion-wide) and Tier 2 (least-disturbed) references
    5. Run statistical comparisons (Hedges' g, permutation tests, bootstrap CIs)
    6. Output a profile-first scorecard (JSON + CSV) and an evidence-graded HTML report

Prerequisites:
    - Google Earth Engine authenticated: `earthengine authenticate`
    - A real GEE project ID in config.yaml (every currently-registered indicator
      is source_type="gee" -- checked directly; the local-raster path this
      docstring used to mention is real, dead code today, never actually
      invoked by any registered indicator)
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

    # REAL FIX (found during a full-repo consistency sweep, the exact same
    # class of bug already caught and fixed in the notebook): this used to
    # print raw, unbounded profile scores (e.g. "score=0.297") straight
    # from the profile dict. Uses the same real son_score functions the
    # HTML report itself uses, so this summary is consistent with the
    # report, not a stale, separate view of the same data.
    from darukaa_reference import son_score
    for site_id, prof in report.get("site_profiles", {}).items():
        site_rows = [r for r in report["scorecard"] if r.get("site_id") == site_id]
        summary = son_score.son_summary(prof, site_rows, son_score.PILLAR_NAMES)
        oc, op = summary["overall_condition"], summary["overall_pressure"]
        chain = summary["limiting_chain"]
        chain_str = chain["display"] if chain["available"] else "no pillar had scored data this run"
        chain_display = chain_str[0].upper() + chain_str[1:]  # not .capitalize() -- lowercases "C1" etc.
        print(f"\n  ── {site_id} ── decision: {summary['matrix_cell']}")
        print(f"     Overall SoN: {oc['score_pct']} {oc['concern_class']}  ({chain_display})")
        for p in summary["pillars"]:
            limiting = " & ".join(p["limiting_indicators"]) if p["limiting_indicators"] else p["limiting_subdimension"]
            print(f"     {p['pillar_label']:32s} {p['score_pct']:>5s}  {p['concern_class']:10s} (limited by: {limiting})")
        print(f"     Pressure axis: {op['score_pct']} {op['concern_class']}  (kept structurally separate)")

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

    Example: Adding CPLAND (connectivity metric, Darukaa's C1 landscape-extent pillar).
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

    # REAL BUG FIXED HERE (found during a full-repo consistency sweep): this
    # example used to pass pillar=1 -- confirmed directly, that field is
    # accepted silently but does NOTHING for pillar-based scoring/reporting;
    # the real field every pillar card, limiting-chain, and aggregation
    # function actually groups by is `construct` (a string like
    # "C1_landscape"), which stayed None the whole time. A developer
    # following the old example would have gotten an indicator invisible
    # to every pillar-level view in the report. subdimension is also real
    # and required for the limiting-chain naming to resolve to this
    # indicator specifically, not just its parent pillar.
    registry.register(
        name="cpland",
        display_name="Landscape Connectivity (CPLAND)",
        source_type="api",  # or "gee", "local_raster", "in_situ"
        extract_fn=extract_cpland,
        construct="C1_landscape",   # real pillar this indicator belongs to
        subdimension="configuration",  # real subdimension within that pillar
        unit="%",
        value_range=(0.0, 100.0),
        citation="McGarigal, K. & Marks, B.J. (1995). FRAGSTATS. USDA Forest Service.",
        tier2_eligible=True,
        evidence_tier="baseline",  # required alongside tier2_eligible for real scoring eligibility
        reference_type="regional_distribution",
        reference_estimator="robust_z",
        uncertainty_method="bootstrap_ci",
    )

    # Run with the extended registry
    config = Config.from_yaml("config.yaml")
    pipeline = Pipeline(config, registry)
    report = pipeline.run("sites.kml")
    return report


if __name__ == "__main__":
    main()
