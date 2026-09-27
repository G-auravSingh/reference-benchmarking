"""
test_composite_provenance.py
==============================

Real test for independent audit item 14: reclassify aquatic/pressure
composites (mspl, edpp, rci, sabf, iri, hsas, wsdi) as explicit Darukaa
proxies with documented validation status.

Before this fix, this documentation existed only as free-text prose inside
each indicator's `citation` string -- readable, but not machine-checkable,
and two of the seven (rci, sabf) were missing the "Darukaa composite, not a
validated formula" disclosure entirely (rci was bare-cited to a conceptual
ecology paper that specifies no formula or weights; sabf's real FAI formula
was correctly literature-derived, but its 0.005 bloom threshold and
frequency-averaging were undisclosed Darukaa choices).

Fix: every one of the seven now carries a structured
metadata['provenance'] dict with four required keys (literature_component,
darukaa_transformation, darukaa_weights, validation_status), checked here so
an eighth composite added later can't silently skip this documentation.

Run with: python -m pytest tests/test_composite_provenance.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from darukaa_reference.indicators import create_default_registry

_COMPOSITES = ["mspl", "edpp", "rci", "sabf", "iri", "hsas", "wsdi"]
_REQUIRED_KEYS = {"literature_component", "darukaa_transformation", "darukaa_weights", "validation_status"}


def test_every_aquatic_pressure_composite_has_structured_provenance():
    reg = create_default_registry()
    for name in _COMPOSITES:
        spec = reg.get(name)
        provenance = spec.metadata.get("provenance")
        assert provenance is not None, f"{name} is missing metadata['provenance']"
        missing = _REQUIRED_KEYS - set(provenance.keys())
        assert not missing, f"{name}'s provenance is missing keys: {missing}"
        assert provenance["literature_component"], f"{name}: literature_component must not be empty"
        assert provenance["darukaa_transformation"], f"{name}: darukaa_transformation must not be empty"
        assert provenance["validation_status"], f"{name}: validation_status must not be empty"


def test_rci_and_sabf_no_longer_silently_over_attributed():
    """The two real gaps this item found: rci's weighted composite formula was
    bare-cited with no Darukaa-origin disclosure; sabf's bloom threshold was
    undisclosed. Both citations must now name Darukaa explicitly."""
    reg = create_default_registry()
    rci_citation = reg.get("rci").citation.lower()
    assert "darukaa" in rci_citation
    assert "naiman" in rci_citation  # the real literature motivation stays, just not overstated

    sabf_citation = reg.get("sabf").citation.lower()
    assert "darukaa" in sabf_citation
    assert "hu c (2009)" in sabf_citation or "hu (2009)" in sabf_citation


def test_composites_with_real_weighted_formulas_report_their_weights():
    """rci, mspl, iri, hsas are genuine Darukaa weighted composites -- their
    provenance must carry the real weights, not None."""
    reg = create_default_registry()
    for name in ("rci", "mspl", "iri", "hsas"):
        weights = reg.get(name).metadata["provenance"]["darukaa_weights"]
        assert weights is not None, f"{name} is a weighted composite; darukaa_weights must be populated"
        assert abs(sum(weights.values()) - 1.0) < 1e-6, f"{name}'s weights must sum to 1.0"


if __name__ == "__main__":
    test_every_aquatic_pressure_composite_has_structured_provenance()
    test_rci_and_sabf_no_longer_silently_over_attributed()
    test_composites_with_real_weighted_formulas_report_their_weights()
    print("All test_composite_provenance tests passed.")
