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
from .registry import FULL_INDICATORS, effective_scoring_role
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

    def run(self, geometry, realm: str = "terrestrial", temporal_window: str = "", metric_names=None):
        """Run the migrated metric calculators for a realm.

        ``metric_names`` is an execution filter used by reference benchmarking.
        Site assessments may still request the full registered inventory, but a
        reference population only needs the metrics that are actually score-eligible.
        This avoids re-running all 46 calculators once for every scored metric.
        """
        requested = set(metric_names) if metric_names is not None else None
        results = []
        for spec in FULL_INDICATORS:
            if requested is not None and spec.name not in requested:
                continue
            if not spec.registered:
                continue
            if realm not in tuple(spec.applicable_realms):
                results.append(MetricResult(
                    metric=spec.name, pillar=spec.pillar, construct=spec.construct,
                    subdimension=spec.subdimension, domain=realm, value=None,
                    units=spec.units, status="not_applicable",
                    temporal_window=temporal_window, dataset=spec.source_type,
                    scale_m=int(spec.native_scale_m or 0),
                    direction=spec.direction, evidence_tier=spec.evidence_tier,
                    reference_type=spec.reference_type, reference_allowed=spec.reference_allowed,
                    score_eligible=False, notes="Metric not applicable to requested realm.",
                    metadata={"applicable": False, "status": "not_applicable"}
                ))
                continue

            try:
                fn, legacy_spec = self._fn(spec.name)
                raw = fn(geometry, self.legacy_config)
                if not isinstance(raw, dict):
                    raw = {"value": raw}
                value = _as_float(raw.get("value"))
                raw_meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
                status = raw.get("status") or raw_meta.get("status")
                notes = str(raw.get("notes") or raw.get("message") or raw_meta.get("note") or raw_meta.get("reason") or "")
                if raw_meta.get("applicable") is False:
                    status = "not_applicable"
                elif spec.name == "hsas" and raw_meta.get("edna_points_used") is False:
                    # Habitat suitability alone is not HSAS; the contract requires
                    # real eDNA evidence before this metric can enter scoring.
                    status = "pending_input"
                    notes = raw_meta.get("note", "eDNA evidence required for HSAS scoring.")
                elif spec.name == "bii" and raw_meta.get("bii_source") == "eii_compositional_fallback":
                    status = "pending_input"
                    notes = "Independent BII asset unavailable; EII compositional fallback retained for diagnostic continuity and excluded from scoring."
                elif value is not None and not status:
                    status = "calculated"
                elif value is not None and status in {"ok", "usable"}:
                    status = "calculated"
                elif value is None and not status:
                    status = "no_valid_observation"
                elif status is None:
                    status = "calculation_failed"

                pixels = raw.get("pixels")
                n = None
                std = p05 = p10 = p25 = p50 = p75 = p90 = p95 = None
                # Prefer server-side spatial distribution diagnostics returned by the
                # legacy reducer. This keeps reference populations descriptive without
                # transferring all raster pixels to Colab.
                if raw_meta:
                    n = raw_meta.get("spatial_valid_pixel_count")
                    std = raw_meta.get("spatial_stddev")
                    p05 = raw_meta.get("spatial_p05")
                    p10 = raw_meta.get("spatial_p10")
                    p25 = raw_meta.get("spatial_p25")
                    p50 = raw_meta.get("spatial_p50")
                    p75 = raw_meta.get("spatial_p75")
                    p90 = raw_meta.get("spatial_p90")
                    p95 = raw_meta.get("spatial_p95")
                if pixels is not None and n is None:
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

                runtime_role = effective_scoring_role(spec, self.config)
                runtime_reference_allowed = bool(spec.reference_allowed) or runtime_role in {"SCORED", "PRESSURE"}
                runtime_reference_type = spec.reference_type if spec.reference_type != "none" else ("adaptive_matched_distribution" if runtime_reference_allowed else "none")
                results.append(MetricResult(
                    metric=spec.name, pillar=spec.pillar, construct=spec.construct,
                    subdimension=spec.subdimension, domain=realm, value=value,
                    units=spec.units, status=status,
                    temporal_window=temporal_window, dataset=spec.source_type,
                    scale_m=int(spec.native_scale_m or 0),
                    direction=spec.direction, evidence_tier=spec.evidence_tier,
                    reference_type=runtime_reference_type, reference_allowed=runtime_reference_allowed,
                    score_eligible=(runtime_role in {"SCORED", "PRESSURE"} and status == "calculated"),
                    valid_observations=n, valid_pixels=n, std_dev=std,
                    p05=p05,p10=p10,p25=p25,p50=p50,p75=p75,p90=p90,p95=p95,
                    notes=notes or spec.notes,
                    metadata=raw_meta
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
                    notes=f"Required optional dependency/input unavailable: {exc}",
                    metadata={"exception_type": type(exc).__name__}
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
                    notes=f"{type(exc).__name__}: {exc}",
                    metadata={"exception_type": type(exc).__name__}
                ))
        return results
