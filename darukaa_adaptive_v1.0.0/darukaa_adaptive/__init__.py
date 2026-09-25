"""Darukaa Adaptive Biodiversity Assessment Framework."""
from .benchmark import BenchmarkResult, ReferenceEngine
from .config import AssessmentConfig
from .metrics import LakeMetrics, MetricResult
from .periods import annual_periods, month_periods
from .pipeline import LakePipeline
from .water import WaterDetector, WaterPeriodResult

__version__ = "1.1.0"

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
]
