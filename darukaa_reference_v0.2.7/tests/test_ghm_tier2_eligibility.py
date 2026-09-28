"""ghm Tier 2 must be reachable in a real run (independent audit item 3, Option B).

reference.py already contains a dedicated independent-reference Tier-2 path for ghm, but the
registry had tier2_eligible=False, and compute() skips Tier 2 entirely for such indicators --
so that path was unreachable. Only ghm is changed; the other Tier-1-only indicators are
deliberately left as they are."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from darukaa_reference.config import Config
from darukaa_reference.reference import ReferenceSelector


def _selector(**kw):
    return ReferenceSelector(Config(**kw))

def test_ghm_tier2_is_now_reachable_and_only_ghm_changed():
    import dataclasses
    from darukaa_reference.indicators import create_default_registry
    reg = create_default_registry()
    assert reg.get("ghm").tier2_eligible is True
    for name in ("hdi", "light_pollution", "iri", "cpland", "jrc_water_persistence"):
        assert reg.get(name).tier2_eligible is False, name      # deliberately unchanged

    spec = dataclasses.replace(reg.get("ghm"), extract_fn=lambda g, c: {"value": 0.6})
    sel = _selector()
    reached = {}
    sel._compute_tier1 = lambda sp, g: {}
    def _t2(sp, g, e):
        reached["spec"] = sp.name
        return {}
    sel._compute_tier2 = _t2
    sel.compute(spec, "GEOM", "siteA", 1)
    assert reached == {"spec": "ghm"}                            # Tier 2 really runs for ghm
