"""engine_profile.build_profile: takes the engine score AS IS, never normalises, and agrees exactly with the legacy scoring.build_site_profile wherever the two are comparable."""
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from darukaa_reference import engine_profile as EPR
from darukaa_reference import scoring

POOL = [("ghm", "C4_pressure", "land_use_pressure"), ("light_pollution", "C4_pressure", "direct_pressure"), ("hdi", "C4_pressure", "land_use_pressure"),
        ("natural_habitat", "C1_landscape", "extent"), ("net_tree", "C1_landscape", "change"), ("ndvi", "C2_vegetation", "greenness"), ("chm", "C2_vegetation", "structure"),
        ("bii", "C3_fauna", "intactness")]


def test_agrees_exactly_with_the_legacy_function_when_the_score_is_the_legacy_normalisation():
    rng = random.Random(7)
    for _ in range(200):
        picks = rng.sample(POOL, rng.randint(1, len(POOL)))
        legacy_items, engine_items = [], []
        for name, c, s in picks:
            z = rng.uniform(-4, 4)
            legacy_items.append({"name": name, "construct": c, "subdimension": s, "value": z, "estimator": "robust_z"})
            engine_items.append({"name": name, "construct": c, "subdimension": s, "score": scoring.normalize(z, "robust_z")})
        a, b = scoring.build_site_profile(legacy_items), EPR.build_profile(engine_items)
        assert a == b, picks


def test_the_engine_score_is_used_as_is_and_never_renormalised():
    p = EPR.build_profile([{"name": "n", "construct": "C1_landscape", "subdimension": "extent", "score": 0.745}])
    assert p["components"]["C1_landscape"]["headline"] == pytest.approx(0.745)
    assert abs(scoring.normalize(0.745, "percentile") - 0.745) > 0.1          # what the legacy path would have done to it


def test_an_item_without_a_score_is_skipped_never_normalised_never_zero():
    p = EPR.build_profile([{"name": "n", "construct": "C1_landscape", "subdimension": "extent", "score": None, "value": -9.0, "estimator": "robust_z"}])
    assert p["components"] == {} and p["pressure"]["headline"] is None and p["condition"].get("rollup") is None


def test_an_unrecognised_construct_is_skipped_with_a_warning(caplog):
    with caplog.at_level("WARNING"):
        p = EPR.build_profile([{"name": "n", "construct": "C9_typo", "subdimension": "x", "score": 0.1}])
    assert p["components"] == {} and any("unrecognised construct" in r.message for r in caplog.records)
