"""End-to-end run of the assessment with Earth Engine replaced by synthetic data.

This exercises units -> measurements -> references -> scores -> bundle -> R2 checker
offline. It proves the orchestration and the no-silent-failure rules; it says
nothing about real Earth Engine values (evidence level: mocks).
"""
import json
import sys
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from darukaa_adaptive import assessment as A
from darukaa_adaptive import catalogue as cat
from darukaa_adaptive.config import AssessmentConfig
from darukaa_adaptive.inputs import EMU, ProjectInput
from darukaa_adaptive.measurement import Measurement
from darukaa_adaptive.reference_pool import ConditionPool
from darukaa_adaptive.scorecard import ReferenceSample
from darukaa_adaptive.site import area_ha

VALUES = {  # synthetic "forest-like" site values
    "natural_extent_pct": 92.0, "natural_gross_loss_pct": 0.5, "tree_cover_loss_rate": 0.1, "natural_core_area_pct": 80.0,
    "ndvi_peak_season": 0.78, "canopy_height_m": 22.0, "bii": 0.85, "eii_functional": 0.8, "flii": 9.1,
    "built_fraction": 0.004, "ghm": 0.08, "road_density": 0.3, "fire_frequency": 0.0, "night_lights": 0.3,
    "managed_area_pct": 6.0,
}
FAIL = {"night_lights"}  # simulate a layer error on EMUs


def fake_measure_units(units, metric_ids, ctx_base, min_px=4.0):
    out = []
    rng = np.random.default_rng(len(units))
    for u in units:
        for mid in metric_ids:
            if mid in FAIL and u.level == "emu":
                out.append(Measurement(mid, u.unit_id, u.level, None, "error", ran=False, error="RuntimeError: simulated"))
                continue
            v = VALUES.get(mid)
            if u.level == "reference_block" and v is not None:
                v = abs(v * (1 + rng.normal(0, 0.5))) + (0.05 if cat.get(mid).direction == "lower_is_better" else 0)
            if v is None:
                out.append(Measurement(mid, u.unit_id, u.level, None, "pending_input", notes="synthetic"))
                continue
            extras = {}
            if mid == "natural_extent_pct":
                extras["natural_2020_pct"] = 95.0 if u.level != "reference_block" else float(rng.uniform(80, 100))
            if cat.get(mid).reference_type == "reference_condition" and (cat.get(mid).native_scale_m or 99) <= 30:
                extras["by_stratum"] = {10: {"mean": v, "weight": 100.0}}
            out.append(Measurement(mid, u.unit_id, u.level, float(v), "ok", covered_pixel_equivalent=1e4,
                                   effective_period="2025", extras=extras))
    return out


def fake_pool(footprint, ctx_base, cfg):
    rng = np.random.default_rng(7)
    samples = {}
    for mid, v in VALUES.items():
        c = cat.get(mid)
        if c.reference_type != "reference_condition":
            continue
        vals = rng.normal(v * 1.05, abs(v) * 0.05, 300)
        for key in (10, "natural_all"):
            samples[(mid, key)] = ReferenceSample(mid, "reference_condition", vals, np.arange(300) % 20)
    return ConditionPool({"ECO_NAME": "synthetic"}, {10: {"stage": "strict_hmi", "threshold": 0.05, "total": 9999, "eligible": 999}},
                         samples, 300)


@pytest.fixture
def mocked(monkeypatch):
    monkeypatch.setitem(sys.modules, "ee", mock.MagicMock())
    monkeypatch.setattr(A, "measure_units", fake_measure_units)
    monkeypatch.setattr(A, "build_condition_pool", fake_pool)
    monkeypatch.setattr(A, "same_ecoregion", lambda blocks, fp: blocks)
    monkeypatch.setattr(A, "evaluate", lambda lazy: {k: 0.5 for k in lazy})
    monkeypatch.setattr(A, "monthly_ndvi_means", lambda region, months, crs, cp=50.0: {m[0]: 0.5 for m in months})
    import darukaa_adaptive.natural_mask as nm
    monkeypatch.setattr(nm, "build_mask", lambda *a, **k: (mock.MagicMock(), mock.MagicMock()))


def _project():
    a = box(76.43, 11.10, 76.45, 11.12)
    b = box(76.45, 11.10, 76.46, 11.11)
    return ProjectInput("synthetic", "synthetic", "<test>", [EMU("E1", a, area_ha=area_ha(a)), EMU("E2", b, area_ha=area_ha(b))])


def test_end_to_end_bundle(mocked, tmp_path):
    from darukaa_adaptive.outputs import write_bundle
    from darukaa_adaptive.validation_check import check_bundle
    cfg = AssessmentConfig(output_dir=str(tmp_path))
    cfg.pool.n_regional_blocks = 120
    res = A.run_assessment(_project(), cfg, progress=lambda *_: None)
    assert len(res.units.sites) == 1 and len(res.headlines) == 1
    h = res.headlines[0]
    assert h.condition_score is not None and h.condition_pillars == ["P1", "P2"]
    assert h.condition_interval[0] <= h.condition_score <= h.condition_interval[1]
    assert h.pressure_score is not None
    # the simulated EMU layer errors stay errors: never a value, never a score
    errs = [m for m in res.measurements if m.metric == "night_lights" and m.level == "emu"]
    assert not errs or all(m.value is None and m.status == "error" for m in errs)
    # P3 is not covered and says why
    cov = {r["indicator"]: r["covered"] for r in res.project["nature_positive_coverage"]}
    assert cov["Species extinction risk"] == "no"
    paths = write_bundle(res, tmp_path)
    d = Path(paths["report"]).parent
    for f in ("metrics.csv", "scores.csv", "pillars.csv", "site_headlines.csv", "metric_roles.csv", "report.html", "run_manifest.json"):
        assert (d / f).exists(), f
    m = pd.read_csv(d / "metrics.csv")
    assert {"ran", "measured_valid", "sufficient_to_score", "interpretable"} <= set(m.columns)
    pending = m[m.status == "pending_input"]
    assert pending["value"].isna().all() and not pending["sufficient_to_score"].any()
    html = (d / "report.html").read_text()
    assert "preparatory" in html and "not attributable" in html
    checks = check_bundle(d, {"values": {"natural_extent_pct": [">=", 85]}, "pillars": {"P1": [">=", 80]},
                              "headline": {"condition_status": "scored_without_P3"}})
    assert all(c["result"] == "PASS" for c in checks), checks


def test_missing_condition_reference_withholds_condition_not_zero(mocked, monkeypatch, tmp_path):
    def broken_pool(*a, **k):
        raise RuntimeError("no least-disturbed pixels")
    monkeypatch.setattr(A, "build_condition_pool", broken_pool)
    res = A.run_assessment(_project(), AssessmentConfig(output_dir=str(tmp_path)), progress=lambda *_: None)
    h = res.headlines[0]
    assert h.condition_score is None and "P2" in h.condition_status
    assert any(f["code"] == "condition_reference_failed" for f in res.flags)


def test_low_pressure_search_widens_when_ring_is_converted(mocked, monkeypatch, tmp_path):
    """D-26-1: 25 km ring fully converted -> 50 km ring supplies natural blocks."""
    def measure(units, metric_ids, ctx_base, min_px=4.0):
        out = fake_measure_units(units, metric_ids, ctx_base, min_px)
        for m in out:
            if m.metric == "natural_extent_pct" and m.level == "reference_block":
                m.extras["natural_2020_pct"] = 95.0 if m.unit_id.startswith("W50_") else 2.0
        return out
    monkeypatch.setattr(A, "measure_units", measure)
    cfg = AssessmentConfig(output_dir=str(tmp_path))
    res = A.run_assessment(_project(), cfg, progress=lambda *_: None)
    info = res.references["regional_blocks"]["SITE_01"]
    assert info["low_pressure_radius_km"] == 50.0 and info["low_pressure_stage"].startswith("strict")
    ghm = [s for s in res.scores if s.metric == "ghm" and s.unit_id == "SITE_01"][0]
    assert ghm.score is not None and ghm.reference_status == "ok"


def test_low_pressure_reference_insufficient_everywhere_gives_no_p4_score(mocked, monkeypatch, tmp_path):
    def measure(units, metric_ids, ctx_base, min_px=4.0):
        out = fake_measure_units(units, metric_ids, ctx_base, min_px)
        for m in out:
            if m.metric == "natural_extent_pct" and m.level == "reference_block":
                m.extras["natural_2020_pct"] = 1.0
        return out
    monkeypatch.setattr(A, "measure_units", measure)
    res = A.run_assessment(_project(), AssessmentConfig(output_dir=str(tmp_path)), progress=lambda *_: None)
    info = res.references["regional_blocks"]["SITE_01"]
    assert info["low_pressure_stage"] == "reference_insufficient" and info["low_pressure_radius_km"] == 100.0
    ghm = [s for s in res.scores if s.metric == "ghm" and s.unit_id == "SITE_01"][0]
    assert ghm.score is None and ghm.context_score is not None and ghm.absolute_class is not None
    assert res.headlines[0].pressure_score is None
