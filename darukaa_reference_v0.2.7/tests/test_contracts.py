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


def test_ghm_tier2_benchmark_is_suppressed_pending_human_decision():
    """Real regression test for independent audit item 3: ghm's Tier 2
    reference pool is selected using ghm/HMI itself, so benchmarking ghm's own
    value against that pool is circular. Confirmed directly by tracing
    reference.py's _compute_tier2. Per the audit's explicit instruction not to
    invent a fix silently, this is suppressed (not scored via Tier 2) until a
    real decision is made between the two documented options. This test
    confirms the suppression fires before any real GEE call is attempted."""
    from darukaa_reference.config import Config
    from darukaa_reference.reference import ReferenceSelector

    registry = create_default_registry()
    contracts.apply_contracts(registry)
    config = Config.from_yaml(str(Path(__file__).resolve().parent.parent / "config.yaml"))
    ghm_spec = registry.get("ghm")

    engine = ReferenceSelector(config)
    engine._ensure_gee = lambda: None  # bypass live GEE auth; guard fires before any real call

    result = engine._compute_tier2(ghm_spec, site_geometry=None, eco_id=None)
    assert result == {"suppressed_reason": "ghm_tier2_reference_circularity_pending_decision"}


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
