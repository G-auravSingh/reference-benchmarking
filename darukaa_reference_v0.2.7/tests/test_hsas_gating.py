"""
test_hsas_gating.py
=====================

Real tests for independent audit item 13: gate HSAS when eDNA is absent.

extract_hsas (indicators/__init__.py) already honestly labels its own output
via metadata['edna_points_used'] -- True only when real eDNA point data was
supplied for a project, False when it degrades to habitat-suitability-only
(real data, but not a true HSAS). Before this fix, that flag was computed but
never actually ACTED on: hsas stayed registry-scored regardless, so an
unvalidated habitat-suitability value could silently drive the headline
biodiversity score exactly as if it were a real, eDNA-validated HSAS.

Fix: report.py now computes a per-run, machine-readable hsas_validated field
on the hsas row, and _component_profiles excludes hsas from the headline
profile whenever hsas_validated is not True -- while the row itself (with its
real value and classification) still appears in the scorecard as honest
context, never deleted.

Run with: python -m pytest tests/test_hsas_gating.py -v
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from darukaa_reference.config import Config
from darukaa_reference.registry import IndicatorRegistry
from darukaa_reference.report import ReportGenerator
from darukaa_reference.statistics import ComparisonResult


def _dummy_extract(*a, **k):
    return {}


def _make_registry():
    reg = IndicatorRegistry()
    common = dict(
        source_type="gee", extract_fn=_dummy_extract,
        evidence_tier="baseline", reference_type="regional_distribution",
        uncertainty_method="bootstrap_ci", construct="C2_vegetation",
    )
    reg.register(name="hsas", display_name="HSAS", subdimension="habitat_suitability", **common)
    reg.register(name="tspi", display_name="TSPI", subdimension="water_quality", **common)
    return reg


def _generate_and_capture_profile_inputs(comparisons):
    """Runs ReportGenerator.generate() with scoring.build_site_profile patched
    to record exactly which indicator names were actually passed into the
    headline profile builder, so the test can assert hsas's inclusion/
    exclusion directly rather than reverse-engineering it from the profile
    output's internal scoring math."""
    reg = _make_registry()
    config = Config()
    gen = ReportGenerator(config, reg)
    captured = {}

    def _fake_build_site_profile(benches, **kwargs):
        captured["names"] = sorted(b["name"] for b in benches)
        return {"matrix_cell": "TEST"}

    with patch("darukaa_reference.scoring.build_site_profile", side_effect=_fake_build_site_profile):
        report = gen.generate(comparisons)
    return report, captured


def test_hsas_validated_true_when_edna_points_used():
    comparisons = [
        ComparisonResult(indicator_name="hsas", site_id="zoneA",
                         site_value=0.6, tier2_reference=0.5, tier2_benchmark=1.2,
                         metadata={"edna_points_used": True, "edna_asset": "projects/x/edna"}),
        ComparisonResult(indicator_name="tspi", site_id="zoneA",
                         site_value=0.4, tier2_reference=0.3, tier2_benchmark=0.9,
                         metadata={}),
    ]
    report, captured = _generate_and_capture_profile_inputs(comparisons)
    hsas_row = next(r for r in report["scorecard"] if r["indicator"] == "hsas")
    assert hsas_row["hsas_validated"] is True
    # validated hsas DOES enter the headline profile
    assert "hsas" in captured["names"]


def test_hsas_validated_false_and_excluded_when_no_edna_points():
    comparisons = [
        ComparisonResult(indicator_name="hsas", site_id="zoneA",
                         site_value=0.6, tier2_reference=0.5, tier2_benchmark=1.2,
                         metadata={"edna_points_used": False,
                                  "note": "No eDNA asset provided. Value = habitat suitability only, NOT true HSAS."}),
        ComparisonResult(indicator_name="tspi", site_id="zoneA",
                         site_value=0.4, tier2_reference=0.3, tier2_benchmark=0.9,
                         metadata={}),
    ]
    report, captured = _generate_and_capture_profile_inputs(comparisons)
    hsas_row = next(r for r in report["scorecard"] if r["indicator"] == "hsas")
    assert hsas_row["hsas_validated"] is False
    # unvalidated hsas is EXCLUDED from the headline profile...
    assert "hsas" not in captured["names"]
    # ...but tspi (a real, unaffected scored indicator) still enters normally
    assert "tspi" in captured["names"]
    # and hsas's real row/value is still present in the scorecard as context,
    # not deleted just because it's excluded from the headline
    assert hsas_row["tier2_benchmark"] == 1.2


def test_hsas_validated_is_none_for_non_hsas_indicators():
    """The flag is meaningful only for hsas specifically -- must not leak a
    spurious True/False onto unrelated indicators."""
    comparisons = [
        ComparisonResult(indicator_name="tspi", site_id="zoneA",
                         site_value=0.4, tier2_reference=0.3, tier2_benchmark=0.9,
                         metadata={"edna_points_used": True}),  # even if present, irrelevant here
    ]
    report, _ = _generate_and_capture_profile_inputs(comparisons)
    tspi_row = next(r for r in report["scorecard"] if r["indicator"] == "tspi")
    assert tspi_row["hsas_validated"] is None


def test_hsas_validated_defaults_false_when_metadata_missing_the_key():
    """A real hsas row whose metadata never set edna_points_used at all (e.g.
    an older cached run, or an extraction failure path) must fail SAFE --
    excluded from the headline, not silently assumed validated. Here hsas is
    the ONLY row, so once excluded there is nothing left to build a profile
    from at all -- build_site_profile correctly never gets called, and the
    site gets no profile, rather than a profile built from zero indicators."""
    comparisons = [
        ComparisonResult(indicator_name="hsas", site_id="zoneA",
                         site_value=0.6, tier2_reference=0.5, tier2_benchmark=1.2,
                         metadata={}),
    ]
    report, captured = _generate_and_capture_profile_inputs(comparisons)
    hsas_row = next(r for r in report["scorecard"] if r["indicator"] == "hsas")
    assert hsas_row["hsas_validated"] is False
    # excluded before ever reaching build_site_profile -- nothing captured
    assert captured == {}
    # and correctly no profile at all for zoneA (would be misleading to build
    # one from zero real headline indicators)
    assert "zoneA" not in report["site_profiles"]


if __name__ == "__main__":
    test_hsas_validated_true_when_edna_points_used()
    test_hsas_validated_false_and_excluded_when_no_edna_points()
    test_hsas_validated_is_none_for_non_hsas_indicators()
    test_hsas_validated_defaults_false_when_metadata_missing_the_key()
    print("All test_hsas_gating tests passed.")
