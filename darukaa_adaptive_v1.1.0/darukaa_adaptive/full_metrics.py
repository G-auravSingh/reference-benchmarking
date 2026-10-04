"""Full 0.2.7 calculator adapter for the generalized v1.1.0 framework.

The legacy calculators are executed unchanged; this module translates their output
into the v1 MetricResult contract.  No legacy scoring/reference-selection logic is
invoked.
"""
from __future__ import annotations
from dataclasses import asdict
from datetime import date
from typing import Any, Optional
import math

from .metrics import MetricResult
from .registry import FULL_INDICATORS
from . import registry as registry_mod


def _legacy_config(config):
    from .legacy_reference.config import Config as LegacyConfig
    c = LegacyConfig()
    c.gee_project = getattr(config.gee, "project_id", "") or ""
    c.gee_service_account = getattr(config.gee, "service_account", None)
    c.gee_key_path = getattr(config.gee, "key_path", None)
    c.raster_paths = dict(getattr(config, "raster_paths", {}) or {})
    c.ndvi_year = getattr(config.temporal, "end_year", 2025)
    c.ndvi_cloud_threshold = getattr(config.temporal, "max_cloud_pct", 60.0)
    c.lst_year = getattr(config.temporal, "end_year", 2025)
    # Preserve the production v1 reference assets/parameters where legacy
    # calculators consult them through config attributes.
    if hasattr(config, "reference"):
        c.hmi_gee_asset = config.reference.hmi_gee_asset
        c.hmi_gee_band = config.reference.hmi_gee_band
        c.ecoregion_gee_asset = config.reference.ecoregion_gee_asset
        c.landcover_gee_asset = config.reference.landcover_asset
    return c


def _as_float(value):
    if value is None:
        return None
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except Exception:
        return None


class FullMetricEngine:
    """Run all 46 legacy calculators applicable to the requested realm."""

    def __init__(self, config):
        self.config = config
        self.legacy_config = _legacy_config(config)
        self._legacy_registry = getattr(registry_mod, "_LEGACY_REGISTRY", None)

    def _fn(self, name):
        if self._legacy_registry is None:
            raise RuntimeError("Legacy indicator registry could not be loaded")
        spec = self._legacy_registry.get(name)
        if spec is None:
            raise KeyError(name)
        return spec.extract_fn, spec

    def run(self, geometry, realm: str = "terrestrial", temporal_window: str = ""):
        results = []
        for spec in FULL_INDICATORS:
            if realm not in tuple(spec.applicable_realms):
                results.append(MetricResult(
                    metric=spec.name, pillar=spec.pillar, construct=spec.construct,
                    subdimension=spec.subdimension, domain=realm, value=None,
                    units=spec.units, status="not_applicable",
                    temporal_window=temporal_window, dataset=spec.source_type,
                    scale_m=int(spec.native_scale_m or 0),
                    direction=spec.direction, evidence_tier=spec.evidence_tier,
                    reference_type=spec.reference_type, reference_allowed=spec.reference_allowed,
                    score_eligible=False, notes="Metric not applicable to requested realm."
                ))
                continue

            try:
                fn, legacy_spec = self._fn(spec.name)
                raw = fn(geometry, self.legacy_config)
                if not isinstance(raw, dict):
                    raw = {"value": raw}
                value = _as_float(raw.get("value"))
                status = raw.get("status")
                notes = str(raw.get("notes") or raw.get("message") or "")
                if value is not None:
                    status = "calculated"
                elif isinstance(status, str) and "not applicable" in status.lower():
                    status = "not_applicable"
                elif raw.get("value") is None:
                    status = "no_valid_observation"
                else:
                    status = status or "calculation_failed"

                pixels = raw.get("pixels")
                n = None
                std = p05 = p10 = p25 = p50 = p75 = p90 = p95 = None
                if pixels is not None:
                    try:
                        import numpy as np
                        a = np.asarray(pixels, dtype=float)
                        a = a[np.isfinite(a)]
                        if len(a):
                            n = int(len(a))
                            std = float(np.std(a, ddof=1)) if len(a) > 1 else 0.0
                            p05,p10,p25,p50,p75,p90,p95 = [float(x) for x in np.percentile(a,[5,10,25,50,75,90,95])]
                    except Exception:
                        pass

                results.append(MetricResult(
                    metric=spec.name, pillar=spec.pillar, construct=spec.construct,
                    subdimension=spec.subdimension, domain=realm, value=value,
                    units=spec.units, status=status,
                    temporal_window=temporal_window, dataset=spec.source_type,
                    scale_m=int(spec.native_scale_m or 0),
                    direction=spec.direction, evidence_tier=spec.evidence_tier,
                    reference_type=spec.reference_type, reference_allowed=spec.reference_allowed,
                    score_eligible=(spec.scoring_role == "SCORED" and status == "calculated"),
                    valid_observations=n, valid_pixels=n, std_dev=std,
                    p05=p05,p10=p10,p25=p25,p50=p50,p75=p75,p90=p90,p95=p95,
                    notes=notes or spec.notes
                ))
            except (ImportError, ModuleNotFoundError) as exc:
                results.append(MetricResult(
                    metric=spec.name, pillar=spec.pillar, construct=spec.construct,
                    subdimension=spec.subdimension, domain=realm, value=None,
                    units=spec.units, status="pending_input",
                    temporal_window=temporal_window, dataset=spec.source_type,
                    scale_m=int(spec.native_scale_m or 0), direction=spec.direction,
                    evidence_tier=spec.evidence_tier, reference_type=spec.reference_type,
                    reference_allowed=spec.reference_allowed, score_eligible=False,
                    notes=f"Required optional dependency/input unavailable: {exc}"
                ))
            except Exception as exc:
                results.append(MetricResult(
                    metric=spec.name, pillar=spec.pillar, construct=spec.construct,
                    subdimension=spec.subdimension, domain=realm, value=None,
                    units=spec.units, status="calculation_failed",
                    temporal_window=temporal_window, dataset=spec.source_type,
                    scale_m=int(spec.native_scale_m or 0), direction=spec.direction,
                    evidence_tier=spec.evidence_tier, reference_type=spec.reference_type,
                    reference_allowed=spec.reference_allowed, score_eligible=False,
                    notes=f"{type(exc).__name__}: {exc}"
                ))
        return results
