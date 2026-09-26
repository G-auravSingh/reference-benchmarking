from setuptools import find_packages, setup

setup(
    name="darukaa_adaptive",
    version="1.2.0",
    description="Generalized terrestrial, aquatic and mixed biodiversity baseline engine",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "pandas>=2.0.0", "numpy>=1.24.0", "scipy>=1.10.0", "pyyaml>=6.0",
        "shapely>=2.0.0", "pyproj>=3.6.0", "fastkml>=1.1.0", "lxml>=5.0.0",
    ],
)
