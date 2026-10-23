from setuptools import find_packages, setup

setup(
    name="darukaa-adaptive",
    version="1.1.0",
    description="Ex-situ biodiversity baseline assessment aligned with the Nature Positive State of Nature indicators",
    packages=find_packages(),
    install_requires=[
        "earthengine-api>=1.6.0", "shapely>=2.0.0", "pyproj>=3.6.0", "fastkml>=1.1.0",
        "lxml>=5.0.0", "pandas>=2.0.0", "numpy>=1.24.0", "pyyaml>=6.0",
    ],
    include_package_data=True,
)
