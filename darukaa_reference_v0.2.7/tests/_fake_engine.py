"""
A deterministic stand-in for Earth Engine, used ONLY by offline tests. It subclasses the real EEProvider (so `implemented`, unit and temporal helpers are the real
ones) and overrides the three methods that would call Earth Engine. The specs it builds follow EEProvider._site / _cell_references / _water_body, so the REAL
`assess_zone` -> `evaluate_indicator` produces genuine statuses, benchmarks and scores from them.
"""
import hashlib
from pathlib import Path

import numpy as np

from darukaa_reference import assess as A
from darukaa_reference import benchmarking as B
from darukaa_reference import indicator_contract as IC
from darukaa_reference import support as S


def _rng(*key):
    return np.random.default_rng(int(hashlib.sha256("|".join(map(str, key)).encode()).hexdigest()[:12], 16))


def polygon_area_m2(geometry):
    import geopandas as gpd
    return float(gpd.GeoSeries([geometry], crs=4326).to_crs(6933).area.iloc[0])


class FakeEngineProvider(A.EEProvider):
    def __init__(self, config, registry, **kw):
        super().__init__(config, registry, ee=object(), selector=None, log=lambda *a, **k: None)
        self.calls = []

    def evidence(self, zone):
        self.calls.append(("evidence", zone.label, zone.realm))
        aquatic = zone.realm == "aquatic"
        return B.SiteEvidence(domain=zone.realm, site_area_m2=polygon_area_m2(zone.geometry), ecosystem_tags=frozenset({"woody", "open_water"} if aquatic else {"woody"}),
                              forest_baseline_m2=0.0, water_body_valid=aquatic, n_pure_water_px=100 if aquatic else None,
                              water_probe="ok" if aquatic else "no_water_body", diagnostics={"fake": True})

    def site(self, name, zone, ev):
        self.calls.append(("site", zone.label, name))
        c = IC.CONTRACTS[name]
        native = float(c.native_resolution_m or 10.0)
        value = float(_rng("site", zone.label, name).uniform(0.2, 0.8))
        spec = B.MetricSpec(name, self._unit(name), self._temporal(c), c.site_support, "site", native_scale_m=native)
        return A.SiteResult(value, self._unit(name), spec, {"fake": True})

    def references(self, name, zone, ev, site):
        self.calls.append(("references", zone.label, name))
        c = IC.CONTRACTS[name]
        native = float(c.native_resolution_m or 10.0)
        vals = _rng("ref", zone.label, name).uniform(0.1, 0.9, 200)
        win = None
        if c.reference_support == "site_window_mean" or c.reference_support == "site_window_rate":
            k = S.cell_size_px(ev.site_area_m2, native)
            win = float(k * native) ** 2
        spec = B.MetricSpec(name, self._unit(name), self._temporal(c), c.reference_support, c.reference_population, window_area_m2=win, native_scale_m=native)
        return {c.reference_tier: B.ReferenceData(vals, spec, c.reference_tier, "fake reference", {"fake": True})}


def stub_zone_loader(config, registry, path, label, realm):
    """Real tile geometry from the real file; no Earth Engine ecoregion lookup."""
    from darukaa_reference.site_loader import SiteLoader
    g = SiteLoader().load(path)
    geoms = g.geometry
    return A.Zone(label=label, geometry=(geoms.union_all() if hasattr(geoms, "union_all") else geoms.unary_union), realm=realm, eco_id=None)


def fake_factory(config, registry):
    return FakeEngineProvider(config, registry)
