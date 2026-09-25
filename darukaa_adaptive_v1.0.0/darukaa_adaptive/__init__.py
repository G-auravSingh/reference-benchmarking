"""Darukaa Adaptive Biodiversity Assessment Framework."""
from .benchmark import BenchmarkResult, ReferenceEngine
from .config import AssessmentConfig
from .metrics import LakeMetrics, MetricResult
from .periods import annual_periods, month_periods
from .qa import qa_metrics
from .pipeline import LakePipeline
from .registry import PILLARS
from .scoring import geometric_mean, concern_label, score_external_observations
from .water import WaterDetector, WaterPeriodResult

__version__ = "1.2.0"

__all__ = [
    "AssessmentConfig",
    "LakePipeline",
    "WaterDetector",
    "WaterPeriodResult",
    "LakeMetrics",
    "MetricResult",
    "BenchmarkResult",
    "ReferenceEngine",
    "annual_periods",
    "month_periods",
    "qa_metrics",
    "PILLARS",
    "geometric_mean",
    "concern_label",
    "score_external_observations",
]
