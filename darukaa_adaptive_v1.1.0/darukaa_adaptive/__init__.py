"""Darukaa Adaptive v1.1.0: ex-situ biodiversity baseline assessment.

Public entry points:
    load_project_input / load_project_inputs / load_boundary  (inputs)
    AssessmentConfig                                          (config)
    run_assessment                                            (assessment)
    write_bundle                                              (outputs)
    catalogue                                                 (metric contracts)
"""
from . import catalogue
from .config import VERSION, AssessmentConfig
from .inputs import load_boundary, load_project_input, load_project_inputs

__version__ = VERSION


def run_assessment(*args, **kwargs):
    from .assessment import run_assessment as _run
    return _run(*args, **kwargs)


def write_bundle(*args, **kwargs):
    from .outputs import write_bundle as _write
    return _write(*args, **kwargs)


__all__ = ["AssessmentConfig", "catalogue", "load_boundary", "load_project_input", "load_project_inputs",
           "run_assessment", "write_bundle", "__version__"]
