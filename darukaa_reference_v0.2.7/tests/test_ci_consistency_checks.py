"""
test_ci_consistency_checks.py
================================

Real tests for independent audit item 20: the remaining automated
CI-style consistency checks the audit listed beyond the registry-count-vs-
doc-count check already built in tests/test_doc_registry_consistency.py.

1. Every scored aquatic-module indicator has a real benchmark pathway
   (reference_type + reference_estimator), not just a registered/scored
   status with nothing to actually benchmark against.
2. No extraction function still queries the JRC monthly-water asset that was
   confirmed retired at independent audit item 6 (structurally guaranteed
   empty for any current date) -- a live-execution version of "current date
   vs dataset availability" isn't runnable without GEE credentials, so this
   checks the concrete, confirmed real case (JRC/GSW1_4/MonthlyHistory) is
   genuinely gone from the extraction path, not just from the citation text.
3. Nowhere in the client-facing HTML report does a raw signed benchmark
   appear without a bounded percentage alongside it in the same table (the
   real gap independent audit item 7 found and fixed for the project-level
   scorecard).

Run with: python -m pytest tests/test_ci_consistency_checks.py -v
"""
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from darukaa_reference.indicators import create_default_registry


def test_every_scored_aquatic_indicator_has_a_real_benchmark_pathway():
    """A scored indicator with no reference_type/reference_estimator is
    registered as scorable but has nothing to actually benchmark against --
    a silent dead end the audit's item 20 wanted guarded against."""
    reg = create_default_registry()
    aquatic_scored = [s for s in reg.scored() if s.module == "aquatic"]
    assert aquatic_scored, "expected at least one scored aquatic indicator to check"
    for spec in aquatic_scored:
        assert spec.reference_type, f"{spec.name} (scored, aquatic) has no reference_type"
        assert spec.reference_estimator, f"{spec.name} (scored, aquatic) has no reference_estimator"


def test_jrc_monthly_history_asset_not_queried_by_any_extraction():
    """independent audit item 6: JRC/GSW1_4/MonthlyHistory's real, documented
    coverage ends 2022-01-01 -- querying it for any current/recent year is
    structurally, guaranteedly empty, not a probabilistic gap. Confirmed the
    live jrc_water_persistence extraction switched to Sentinel-1 entirely;
    this guards against a future change silently reintroducing a live query
    against that asset (the string may still appear in citations/comments
    explaining the history, which is fine and expected)."""
    from darukaa_reference import indicators as indicators_module

    for name, fn in vars(indicators_module).items():
        if not (name.startswith("extract_") or name.startswith("_img_")):
            continue
        if not callable(fn) or not hasattr(fn, "__code__"):
            continue
        try:
            source = inspect.getsource(fn)
        except (OSError, TypeError):
            continue
        # A live query looks like ee.Image(...)/ee.ImageCollection(...) with the
        # asset string as an argument -- a bare mention in a comment/citation
        # (e.g. explaining what was replaced) is fine; an active ee.* call is not.
        if "JRC/GSW1_4/MonthlyHistory" in source:
            live_call = ("ee.Image('JRC/GSW1_4/MonthlyHistory'" in source
                        or 'ee.Image("JRC/GSW1_4/MonthlyHistory"' in source
                        or "ee.ImageCollection('JRC/GSW1_4/MonthlyHistory'" in source
                        or 'ee.ImageCollection("JRC/GSW1_4/MonthlyHistory"' in source)
            assert not live_call, (
                f"{name} still contains a LIVE query against the retired "
                f"JRC/GSW1_4/MonthlyHistory asset (coverage ends 2022-01-01)")


def test_no_raw_signed_benchmark_shown_without_a_bounded_percentage_alongside():
    """independent audit item 7: the project-level scorecard table used to
    show ONLY a raw, unbounded signed value (e.g. -93.6023) as the sole
    number for every indicator. Fixed by adding a bounded 'Intactness' %
    column to the same table. This guards against that column being removed
    again while the raw-value column stays, which would silently reintroduce
    the exact problem item 7 found."""
    from darukaa_reference import html_report

    source = inspect.getsource(html_report)
    # Every table-header string that mentions a raw/signed benchmark must be
    # part of a header block that also shows a bounded Intactness column.
    header_blocks = source.split("<table class=\"dk-table\">")[1:]
    found_a_signed_header = False
    for block in header_blocks:
        header_end = block.find("</tr>")
        header = block[:header_end] if header_end != -1 else block[:400]
        if "signed" in header.lower():
            found_a_signed_header = True
            assert "Intactness" in header, (
                "A table header shows a raw/signed benchmark without a bounded "
                "Intactness percentage in the same header — independent audit "
                "item 7's exact fix is regressing.")
    assert found_a_signed_header, (
        "Expected at least one table header mentioning a signed benchmark "
        "(the project-level scorecard) -- if this indicator was intentionally "
        "removed/renamed, update this test's expectation accordingly.")


if __name__ == "__main__":
    test_every_scored_aquatic_indicator_has_a_real_benchmark_pathway()
    test_jrc_monthly_history_asset_not_queried_by_any_extraction()
    test_no_raw_signed_benchmark_shown_without_a_bounded_percentage_alongside()
    print("All test_ci_consistency_checks tests passed.")
