"""
test_doc_registry_consistency.py
===================================

Real test for independent audit items 19 (doc reconciliation) and 20
(automated CI-style consistency checks): the INDICATOR_REGISTER.md "Totals"
line must always match the live registry. Before this fix, this line (and
several others across README.md, METHODOLOGY_MASTER.md,
ASSUMPTIONS_AND_LIMITATIONS.md, OPEN_DECISIONS.md) had drifted stale --
confirmed directly (44 indicators/10 scored claimed in docs vs. the live
registry's real 46/20) -- because nothing checked them against the registry
automatically. generate_indicator_register.py already re-derives this line
correctly when run; this test is the guardrail so a future registry/contract
change that isn't followed by re-running the generator fails CI instead of
silently leaving the doc stale again.

Run with: python -m pytest tests/test_doc_registry_consistency.py -v
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from darukaa_reference.indicators import create_default_registry

_REGISTER_PATH = Path(__file__).resolve().parent.parent / "INDICATOR_REGISTER.md"


def test_indicator_register_totals_match_the_live_registry():
    reg = create_default_registry()
    real_total = len(reg.all())
    real_scored = len(reg.scored())

    text = _REGISTER_PATH.read_text()
    m = re.search(r"\*\*Totals:\*\*\s*(\d+)\s*registered.*?(\d+)\s*scored", text)
    assert m, "Could not find the '**Totals:** N registered ... N scored' line in INDICATOR_REGISTER.md"
    doc_total, doc_scored = int(m.group(1)), int(m.group(2))

    assert doc_total == real_total, (
        f"INDICATOR_REGISTER.md claims {doc_total} registered indicators, but the live "
        f"registry has {real_total}. Run: python generate_indicator_register.py")
    assert doc_scored == real_scored, (
        f"INDICATOR_REGISTER.md claims {doc_scored} scored indicators, but the live "
        f"registry currently scores {real_scored}. Run: python generate_indicator_register.py")


def test_every_scored_indicator_appears_in_the_register_as_scored():
    """Cross-check every individual scored indicator's row, not just the
    aggregate count (a count could coincidentally match while individual
    rows are wrong, e.g. after a swap of one indicator for another)."""
    reg = create_default_registry()
    text = _REGISTER_PATH.read_text()
    for spec in reg.scored():
        row_match = re.search(rf"\|\s*`{re.escape(spec.name)}`\s*\|.*\|", text)
        assert row_match, f"{spec.name} (scored) has no row in INDICATOR_REGISTER.md"
        assert "✅" in row_match.group(0), (
            f"{spec.name} is scored in the live registry but its INDICATOR_REGISTER.md "
            f"row doesn't show the scored checkmark")


if __name__ == "__main__":
    test_indicator_register_totals_match_the_live_registry()
    test_every_scored_indicator_appears_in_the_register_as_scored()
    print("All test_doc_registry_consistency tests passed.")
