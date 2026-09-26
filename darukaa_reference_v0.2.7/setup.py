from setuptools import setup, find_packages
import re
from pathlib import Path

# REAL BUG FIXED HERE (found during a full-repo consistency sweep): this was
# hardcoded to "0.2.5" -- confirmed stale, the package's real __version__ is
# "0.2.7" (darukaa_reference/__init__.py). The exact same class of drift
# already caught and fixed in report.py's footer and son_score.py's
# docstring this session. Read from the single real source instead of a
# second hardcoded copy that can go stale again.
_init_content = (Path(__file__).parent / "darukaa_reference" / "__init__.py").read_text()
_version_match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', _init_content, re.MULTILINE)
_version = _version_match.group(1) if _version_match else "0.0.0-unknown"

setup(
    name="darukaa_reference",
    version=_version,
    description="Biodiversity indicator reference benchmarking pipeline",
    author="Darukaa.Earth",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "geopandas>=0.14.0",
        "shapely>=2.0",
        "fiona>=1.9",
        "rasterio>=1.3",
        "numpy>=1.24",
        "pandas>=2.0",
        "pyyaml>=6.0",
        "scipy>=1.11",
        "earthengine-api>=0.1.380",
    ],
    entry_points={
        "console_scripts": [
            "darukaa-ref=example_run:main",
        ],
    },
)
