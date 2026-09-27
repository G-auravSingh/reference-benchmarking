"""
test_report_status.py
======================

Real tests for independent audit item 8: "Separate 'eligible to score' from
'actually benchmarked this run'". The registry's scored() only reports whether
an indicator is DEFENSIBLE to score (active + a complete contract) -- it says
nothing about whether a given run actually produced a real reference benchmark
for it. Confirmed real gap directly against the real Tata Motors output, where
several scored indicators returned tier2_benchmark=None (0 tiles with data, or
a raw aquatic site value with no reference pool), yet the prior report's
"What is scored" section listed them identically to indicators that DID
produce a real benchmark.

These tests build fake ComparisonResult rows directly (no live GEE needed) and
check ReportGenerator.generate()'s computed indicator_status fields, plus the
project-level override in project_aggregation.run_multi_tile_project (which
previously just copied one tile's local indicator_status verbatim -- the
literal bug this item targets at project scale).

Run with: python -m pytest tests/test_report_status.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from darukaa_reference.config import Config
from darukaa_reference.registry import IndicatorRegistry
from darukaa_reference.report import ReportGenerator
from darukaa_reference.statistics import ComparisonResult


def _dummy_extract(*a, **k):
    return {}


def _make_registry():
    """Three scored indicators with three different real outcomes:
    - 'ndvi'   : real data, real reference, real benchmark this run.
    - 'ghm'    : real site data, but no reference this run (e.g. suppressed
                 circularity, or genuinely no reference pool found) -- benchmark
                 is None.
    - 'chm'    : no site data at all this run (e.g. 0 tiles with data) --
                 site_value and benchmark are both None.
    Plus one indicator that is registered but NOT scored ('screening_metric'),
    which must never appear in either scored_this_run list.
    """
    reg = IndicatorRegistry()
    common = dict(
        source_type="gee", extract_fn=_dummy_extract,
        evidence_tier="baseline", reference_type="regional_distribution",
        uncertainty_method="bootstrap_ci", construct="C1_landscape",
    )
    reg.register(name="ndvi", display_name="NDVI", subdimension="extent", **common)
    reg.register(name="ghm", display_name="gHM", subdimension="pressure", **common)
    reg.register(name="chm", display_name="Canopy Height", subdimension="structure", **common)
    reg.register(
        name="screening_metric", display_name="Screening only",
        source_type="gee", extract_fn=_dummy_extract,
        evidence_tier="screening",  # not baseline/monitoring -> not eligible -> not scored
        reference_type="regional_distribution", uncertainty_method="bootstrap_ci",
    )
    return reg


def test_scored_this_run_separates_benchmarked_from_not():
    reg = _make_registry()
    config = Config()
    gen = ReportGenerator(config, reg)

    comparisons = [
        ComparisonResult(
            indicator_name="ndvi", site_id="zoneA",
            site_value=0.7, tier2_reference=0.6, tier2_benchmark=1.4,
        ),
        ComparisonResult(
            indicator_name="ghm", site_id="zoneA",
            site_value=0.3, tier2_reference=None, tier2_benchmark=None,
            stratification_diagnostics={"suppressed_reason": "ghm_tier2_reference_circularity_pending_decision"},
        ),
        ComparisonResult(
            indicator_name="chm", site_id="zoneA",
            site_value=None, tier2_reference=None, tier2_benchmark=None,
        ),
        ComparisonResult(
            indicator_name="screening_metric", site_id="zoneA",
            site_value=0.5, tier2_reference=None, tier2_benchmark=None,
        ),
    ]

    report = gen.generate(comparisons)
    status = report["indicator_status"]

    # All three real indicators are registry-eligible ("scored" = defensible).
    assert set(status["scored"]) == {"ndvi", "ghm", "chm"}
    assert "screening_metric" not in status["scored"]

    # Only ndvi actually produced a real benchmark THIS run.
    assert status["scored_this_run"] == ["ndvi"]

    unbenched = {item["name"]: item["reason"] for item in status["scored_but_unbenchmarked_this_run"]}
    assert set(unbenched) == {"ghm", "chm"}
    # ghm's real suppression reason is surfaced verbatim, not genericised.
    assert unbenched["ghm"] == "ghm_tier2_reference_circularity_pending_decision"
    # chm had no site data at all -- a different, real, distinguishable reason.
    assert unbenched["chm"] == "no_data"

    assert status["scored_this_run_summary"] == \
        "1 of 3 scored indicators actually produced a real reference benchmark this run"


def test_no_scored_indicators_missing_this_run_gives_clean_summary():
    """When every scored indicator DID get benchmarked, the unbenched list is
    empty and the summary says so plainly -- no false warning."""
    reg = IndicatorRegistry()
    reg.register(
        name="ndvi", display_name="NDVI", source_type="gee", extract_fn=_dummy_extract,
        evidence_tier="baseline", reference_type="regional_distribution",
        uncertainty_method="bootstrap_ci",
    )
    config = Config()
    gen = ReportGenerator(config, reg)
    comparisons = [
        ComparisonResult(indicator_name="ndvi", site_id="zoneA",
                         site_value=0.7, tier2_reference=0.6, tier2_benchmark=1.1),
    ]
    report = gen.generate(comparisons)
    status = report["indicator_status"]
    assert status["scored_this_run"] == ["ndvi"]
    assert status["scored_but_unbenchmarked_this_run"] == []
    assert status["scored_this_run_summary"] == \
        "1 of 1 scored indicators actually produced a real reference benchmark this run"


def test_reason_distinguishes_no_data_from_no_reference():
    """A real third case: site data WAS extracted, but no reference pool was
    found (distinct from both suppression and total data absence)."""
    reg = IndicatorRegistry()
    reg.register(
        name="wsdi", display_name="WSDI", source_type="gee", extract_fn=_dummy_extract,
        evidence_tier="baseline", reference_type="regional_distribution",
        uncertainty_method="bootstrap_ci",
    )
    config = Config()
    gen = ReportGenerator(config, reg)
    comparisons = [
        ComparisonResult(indicator_name="wsdi", site_id="zoneA",
                         site_value=0.42, tier2_reference=None, tier2_benchmark=None),
    ]
    report = gen.generate(comparisons)
    unbenched = {item["name"]: item["reason"]
                for item in report["indicator_status"]["scored_but_unbenchmarked_this_run"]}
    assert unbenched["wsdi"] == "no_reference"


if __name__ == "__main__":
    test_scored_this_run_separates_benchmarked_from_not()
    test_no_scored_indicators_missing_this_run_gives_clean_summary()
    test_reason_distinguishes_no_data_from_no_reference()
    print("All test_report_status tests passed.")
