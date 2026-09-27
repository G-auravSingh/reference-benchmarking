"""
test_contracts.py
==================

Automated registry validation tests, added in response to an independent audit
finding: ghm and hdi were both scored under the same (construct, subdimension)
pair ("C4_pressure", "land_use_pressure") -- since scoring.py averages every
indicator within one subdimension before the non-compensatory limiting-factor
rule is applied across subdimensions, this silently averaged the two together
rather than letting each contribute its own independent limiting-factor check.
Fixed for ghm/hdi directly; this test is the audit-requested guardrail so the
SAME class of bug (a future indicator promoted into an existing subdimension
without checking) cannot regress silently again.

Run with: python -m pytest tests/test_contracts.py -v
"""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from darukaa_reference.indicators import create_default_registry
from darukaa_reference import contracts


# Real, explicit exceptions to the one-scored-indicator-per-subdimension rule.
# Each entry here is a DELIBERATE decision, not an oversight -- if you are
# adding to this list, you are choosing to average two indicators together;
# do that consciously, not because a promotion collided by accident.
_EXPLICITLY_JUSTIFIED_SHARED_SUBDIMENSIONS = set()
# (currently empty: the one known real case, ghm+hdi, was fixed by giving hdi
#  its own subdimension rather than accepted as a justified exception)


def _scored_subdimension_map():
    registry = create_default_registry()
    contracts.apply_contracts(registry)
    by_subdim = defaultdict(list)
    for spec in registry.scored():
        by_subdim[(spec.construct, spec.subdimension)].append(spec.name)
    return by_subdim


def test_no_unjustified_shared_subdimensions_among_scored_indicators():
    """The real, audit-requested guardrail: no (construct, subdimension) pair
    may contain more than one scored indicator unless it's in the explicit,
    deliberate exceptions list above. A failure here means a new promotion
    silently started averaging with an existing scored indicator -- exactly
    the real bug found with ghm/hdi."""
    by_subdim = _scored_subdimension_map()
    unjustified_collisions = {
        k: v for k, v in by_subdim.items()
        if len(v) > 1 and k not in _EXPLICITLY_JUSTIFIED_SHARED_SUBDIMENSIONS
    }
    assert not unjustified_collisions, (
        f"Found scored indicators silently sharing a subdimension (they will be "
        f"AVERAGED together, not each independently limiting-factor-checked): "
        f"{unjustified_collisions}. Either give the new indicator its own "
        f"subdimension, or add the pair to _EXPLICITLY_JUSTIFIED_SHARED_SUBDIMENSIONS "
        f"with a real, documented reason for wanting them averaged.")


def test_ghm_and_hdi_specifically_no_longer_collide():
    """Direct regression test for the exact real bug the audit found."""
    registry = create_default_registry()
    contracts.apply_contracts(registry)
    ghm = registry.get("ghm")
    hdi = registry.get("hdi")
    assert (ghm.construct, ghm.subdimension) != (hdi.construct, hdi.subdimension), (
        "ghm and hdi must not share a (construct, subdimension) pair -- "
        "this was the exact real averaging bug the audit found and this fixed.")


def test_every_scored_indicator_has_a_reference_estimator():
    """A scored indicator with no reference_estimator cannot produce a real
    benchmark -- this should never happen, but is cheap to check."""
    registry = create_default_registry()
    contracts.apply_contracts(registry)
    missing = [s.name for s in registry.scored() if not s.reference_estimator]
    assert not missing, f"Scored indicators with no reference_estimator: {missing}"


def test_every_scored_indicator_has_at_least_one_applicable_realm():
    registry = create_default_registry()
    contracts.apply_contracts(registry)
    missing = [s.name for s in registry.scored() if not s.applicable_realms]
    assert not missing, f"Scored indicators with no applicable_realms: {missing}"


def test_ghm_tier2_circularity_resolved_not_suppressed():
    """RESOLVED (independent audit item 3, project owner decision, 2026-09-27,
    replacing the earlier 'suppressed pending decision' behavior this test used
    to check): ghm's Tier2 is no longer suppressed. Instead, reference.py's
    _compute_tier2 uses a real, independently-selected reference pool for ghm
    specifically -- the same ecoregion+land-cover stratum every other indicator
    uses, but WITHOUT the low-HMI narrowing step that made the old pool
    circular (self-selected for already having low ghm). Live GEE execution
    of _compute_tier2 needs a real ee.Geometry and live credentials (not
    available in this sandbox -- see test_estimators.py/test_ghm_and_hdi for
    the same constraint elsewhere in this file); this test instead checks the
    two things verifiable without live GEE: (1) the source no longer contains
    the old unconditional suppression path, and (2) it does contain the real
    ghm-specific independent-reference mechanism (the flag and the fixed
    threshold=1.0 no-filter behavior), as a structural regression guard."""
    import inspect
    from darukaa_reference import reference as reference_module

    source = inspect.getsource(reference_module.ReferenceSelector._compute_tier2)
    assert '"suppressed_reason": "ghm_tier2_reference_circularity_pending_decision"' not in source, (
        "ghm's Tier2 should no longer unconditionally suppress -- item 3 was resolved")
    assert "_ghm_independent_reference" in source
    assert "hmi_threshold = 1.0" in source or "t = 1.0" in source

    # contracts.py's ghm note must reflect the real resolution, not still claim
    # this is an open/pending decision.
    ghm_note = contracts.C["ghm"]["note"].lower()
    assert "resolved" in ghm_note
    assert "pending" not in ghm_note


if __name__ == "__main__":
    import traceback
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    passed, failed = 0, 0
    for t in tests:
        try:
            t()
            print(f"PASS: {t.__name__}")
            passed += 1
        except Exception:
            print(f"FAIL: {t.__name__}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
