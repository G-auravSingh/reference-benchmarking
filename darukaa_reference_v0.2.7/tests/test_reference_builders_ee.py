"""
Structure tests for the Earth Engine reference builders (v0.2.8 Phase 3).

These use fakes: they prove the CONTROL FLOW (radius ladder, refusal to fabricate a reference, validity
reasons, population/reference_n exposure, shared selection rule) and that the call chains execute. They do NOT
prove Earth Engine behaviour: that is the Phase 5 / Phase 6 live acceptance run.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from darukaa_reference import constructs as K
from darukaa_reference import reference_builders_ee as RE
from darukaa_reference import indicator_contract as IC


def rec(uid, area, pure=100, value=0.1, perm=0.9):
    return {"uid": uid, "area_m2": area, "pure_px": pure, "value": value, "permanence": perm}


def target():
    return rec("T", 40000.0, value=0.5)


def matching(n, start=0):
    return [rec(f"M{start + i}", 40000.0 * (0.5 + 0.1 * i)) for i in range(n)]


def run(monkeypatch, per_radius, min_n=10, **kw):
    """per_radius: list of record lists, one per radius step in order."""
    calls = iter(per_radius)
    monkeypatch.setattr(RE, "unit_records_ee", lambda ee, **k: next(calls))
    monkeypatch.setattr(RE, "_bodies_touching_site", lambda *a, **k: {"T"})
    site = MagicMock()
    return RE.water_body_reference_ee(
        MagicMock(), site_geometry=site, water_mask=MagicMock(), metric_image=MagicMock(), kind="water",
        native_scale_m=10.0, construct="sabf", unit="f", temporal="t", population="comparable_water_bodies",
        radii_km=(10.0, 25.0, 50.0), min_reference_n=min_n, **kw)


def test_radius_ladder_stops_as_soon_as_the_documented_minimum_is_reached(monkeypatch):
    out = run(monkeypatch, [[target()] + matching(4), [target()] + matching(12), [target()] + matching(30)])
    assert out["valid"] and out["radius_used_km"] == 25.0
    ref = out["reference"]
    assert ref.reference_n == 12 and ref.tier == "tier2"
    assert "within 25 km" in ref.population_definition and "area within [1/3, 3]" in ref.population_definition
    assert ref.diagnostics["radius_used_km"] == 25.0 and ref.diagnostics["funnel"]["n_reference_bodies"] == 12
    assert ref.spec.support == "water_body_unit" and ref.spec.population == "comparable_water_bodies"


def test_a_reference_below_the_minimum_is_returned_honestly_never_padded(monkeypatch):
    out = run(monkeypatch, [[target()] + matching(3), [target()] + matching(5), [target()] + matching(7)])
    assert out["valid"] and out["radius_used_km"] == 50.0
    assert out["reference"].reference_n == 7 < IC.MIN_COMPARABLE_WATER_BODIES       # engine will refuse to score it


def test_target_with_too_few_pure_water_pixels_is_invalid_with_a_reason(monkeypatch):
    t = rec("T", 40000.0, pure=9, value=0.5)
    out = run(monkeypatch, [[t] + matching(20)])
    assert not out["valid"] and out["invalid_reason"] == "insufficient_pure_water" and out["n_pure_water_px"] == 9


def test_no_water_body_in_site_and_no_valid_metric_pixels_have_explicit_reasons(monkeypatch):
    monkeypatch.setattr(RE, "unit_records_ee", lambda ee, **k: matching(15))
    monkeypatch.setattr(RE, "_bodies_touching_site", lambda *a, **k: set())
    kw = dict(site_geometry=MagicMock(), water_mask=MagicMock(), metric_image=MagicMock(), kind="water",
              native_scale_m=10.0, construct="c", unit="u", temporal="t", population="comparable_water_bodies",
              radii_km=(10.0,))
    out = RE.water_body_reference_ee(MagicMock(), **kw)
    assert not out["valid"] and out["invalid_reason"] == "no_water_body_in_site"
    out = run(monkeypatch, [[rec("T", 4e4, value=None)] + matching(15)])
    assert out["invalid_reason"] == "no_valid_metric_pixels"


def test_target_only_mode_does_not_build_a_reference(monkeypatch):
    out = run(monkeypatch, [[target()] + matching(20)], want_reference=False)
    assert out["valid"] and out["reference"] is None and out["target"]["value"] == 0.5


def test_selection_rule_applies_size_permanence_and_pixel_criteria():
    recs = [target(), rec("a", 40000 * 3.0), rec("b", 40000 * 3.01), rec("c", 40000 / 3.0), rec("d", 40000 / 3.1),
            rec("e", 40000.0, perm=0.65), rec("f", 40000.0, perm=0.64), rec("g", 40000.0, pure=9), rec("h", 40000.0, value=None)]
    final, f = RE.select_reference_records(recs, "T")
    assert sorted(r["uid"] for r in final) == ["a", "c", "e"]        # ratio bounds and |dperm| <= 0.25 are inclusive
    assert f["n_rejected_size"] == 2 and f["n_rejected_permanence"] == 1
    final2, _ = RE.select_reference_records(recs, "T", use_permanence=False)
    assert sorted(r["uid"] for r in final2) == ["a", "c", "e", "f"]


def test_unit_records_builds_the_call_chain_and_reads_features():
    ee = MagicMock()
    vals = MagicMock(); vals.getInfo.return_value = {"features": [{"properties": {"uid": "u1", "v": 0.2, "perm": 0.8}}]}
    pure = MagicMock(); pure.getInfo.return_value = {"features": [{"properties": {"uid": "u1", "area_m2": 900.0, "sum": 50}}]}
    img = MagicMock()
    img.select.return_value.rename.return_value.updateMask.return_value.addBands.return_value.reduceRegions.return_value = vals
    water = MagicMock()
    water.focal_min.return_value.rename.return_value.reduceRegions.return_value = pure
    out = RE.unit_records_ee(ee, region=MagicMock(), water_mask=water, metric_image=img, kind="water",
                             native_scale_m=10.0, permanence_image=MagicMock())
    assert out == [{"uid": "u1", "area_m2": 900.0, "pure_px": 50, "value": 0.2, "permanence": 0.8}]
    water.focal_min.assert_called_with(radius=K.PURE_WATER_ERODE_PX, kernelType="square", units="pixels")


def test_cell_reference_exposes_population_cell_size_and_reference_n():
    ee = MagicMock()
    fake = MagicMock(); fake.getInfo.return_value = [0.1, 0.2, None, 0.3]
    fc = MagicMock(); fc.aggregate_array.return_value = fake
    import darukaa_reference.support as S
    orig = S.ee_sample_cells
    S.ee_sample_cells = lambda *a, **k: fc
    try:
        ref = RE.cell_reference_ee(ee, cell_image="IMG", region="Z", native_scale_m=10.0, site_area_m2=4.01e5,
                                   crs="EPSG:32643", n=5000, seed=12345, support="site_window_mean", construct="c",
                                   unit="u", temporal="t", population="regional_ecoregion", tier="tier1",
                                   population_definition="ecoregion cells")
    finally:
        S.ee_sample_cells = orig
    assert ref.reference_n == 3 and ref.population_definition == "ecoregion cells"           # the None is dropped
    assert ref.spec.window_area_m2 == 630.0 ** 2 and ref.diagnostics["cell_px"] == 63 and ref.diagnostics["crs"] == "EPSG:32643"
    assert ref.diagnostics["seed"] == 12345 and ref.diagnostics["sample_requested"] == 5000


def test_shared_water_definition_is_mndwi_and_pure_water_is_eroded():
    comp = MagicMock()
    RE.water_mask_s2(comp)
    comp.normalizedDifference.assert_called_with(["B3", "B11"])
    wm = MagicMock()
    RE.pure_water_mask(wm)
    wm.focal_min.assert_called_with(radius=1, kernelType="square", units="pixels")
