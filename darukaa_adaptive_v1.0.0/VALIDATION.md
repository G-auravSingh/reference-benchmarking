# Local validation performed in this build

- Nandoshi KML parsed successfully.
- Geometry type: Polygon.
- Geodesic area from the supplied KML: approximately 8.786 ha.
- KML bounds: 74.294524–74.298297 E; 17.525978–17.529033 N.
- Python source files compile successfully with `compileall`.
- Local geometry test passes.

## Not executed in this environment

Google Earth Engine processing was not executed because this build environment cannot authenticate to the user's GEE project. Therefore the remote Sentinel-2 / Dynamic World / JRC computations remain to be run in the supplied Colab notebook using the user's GEE credentials.

This is intentional: no fake GEE outputs have been placed in the package.
