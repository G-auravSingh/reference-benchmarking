"""
test_wsdi_context_only.py
============================

Real test for independent audit item 15 (resolved 2026-09-27, project owner
decision: option 1 of 3 presented -- keep WSDI as pressure context only, do
not score).

Real, open ecological problem the audit flagged: WSDI's 'higher dynamism =
worse' direction is not universally true -- a seasonal wetland or floodplain
is SUPPOSED to show high surface dynamism as healthy, natural hydrology, and
the indicator cannot currently distinguish that from unnatural dynamism
(dam operations, erratic dewatering). Rather than keep scoring a direction
that is ecologically wrong for a real, common site type, or silently
redefine the ecological question without sign-off, wsdi is demoted to
context: still computed and still visible in the scorecard, but excluded
from registry.scored() and therefore from the headline profile.

Run with: python -m pytest tests/test_wsdi_context_only.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from darukaa_reference.indicators import create_default_registry


def test_wsdi_is_registered_but_not_scored():
    reg = create_default_registry()
    spec = reg.get("wsdi")
    assert spec.registered
    assert spec.active
    assert not spec.scoring_eligible, "wsdi must NOT be scored (independent audit item 15)"
    assert spec.evidence_tier == "contextual"


def test_wsdi_appears_in_registry_contextual_not_scored():
    reg = create_default_registry()
    scored_names = {s.name for s in reg.scored()}
    contextual_names = {s.name for s in reg.contextual()}
    assert "wsdi" not in scored_names
    assert "wsdi" in contextual_names


def test_wsdi_provenance_documents_the_real_resolution():
    """The provenance dict (independent audit item 14) must reflect the item 15
    resolution, not still claim this is an open/unresolved question."""
    reg = create_default_registry()
    status = reg.get("wsdi").metadata["provenance"]["validation_status"].lower()
    assert "resolved" in status
    assert "context-only" in status or "context only" in status


if __name__ == "__main__":
    test_wsdi_is_registered_but_not_scored()
    test_wsdi_appears_in_registry_contextual_not_scored()
    test_wsdi_provenance_documents_the_real_resolution()
    print("All test_wsdi_context_only tests passed.")
