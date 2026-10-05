from setuptools import find_packages, setup

setup(
    name="darukaa-adaptive",
    version="1.1.1",
    description="Profile-driven biodiversity baseline engine for aquatic, terrestrial and mixed assessments",
    packages=find_packages(),
    install_requires=[
        "earthengine-api>=1.6.0", "geemap>=0.35.0", "geopandas>=1.1.0",
        "shapely>=2.0.0", "pyproj>=3.6.0", "fastkml>=1.1.0", "lxml>=5.0.0",
        "pandas>=2.0.0", "numpy>=1.24.0", "scipy>=1.10.0", "pyyaml>=6.0",
        "jupyter>=1.1.0",
    ],
    include_package_data=True,
)
