from setuptools import setup, find_packages

setup(
    name="darukaa_reference",
    version="0.1.0",
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
