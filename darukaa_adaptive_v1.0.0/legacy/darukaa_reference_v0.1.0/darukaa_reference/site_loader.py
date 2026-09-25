"""
Site Loader
===========

Reads project site geometries from KML, KMZ, GeoJSON, or Shapefile formats
into a standardised GeoDataFrame in EPSG:4326 (WGS 84).

Handles both single-site and multi-site files. Each site gets a unique
``site_id`` derived from the filename and feature index.
"""

from __future__ import annotations

import logging
import tempfile
import zipfile
from pathlib import Path
from typing import List, Union

import geopandas as gpd
import fiona
from shapely import wkb, wkt
from shapely.geometry import shape, mapping
from shapely.ops import transform as shapely_transform

logger = logging.getLogger(__name__)

# Enable KML driver in fiona
fiona.drvsupport.supported_drivers["KML"] = "rw"
fiona.drvsupport.supported_drivers["LIBKML"] = "rw"


def _force_2d(geom):
    """
    Strip Z coordinates from a shapely geometry.

    KML/KMZ files from Google Earth almost always include altitude as a
    third coordinate. Google Earth Engine and many GeoJSON consumers
    reject 3D geometries ('Invalid GeoJSON geometry'). This function
    projects any geometry down to 2D by discarding the Z component.
    """
    if geom is None or geom.is_empty:
        return geom
    if geom.has_z:
        return shapely_transform(lambda x, y, z=None: (x, y), geom)
    return geom


class SiteLoader:
    """
    Load project site geometries from various geospatial file formats.

    Supported formats: .kml, .kmz, .geojson, .json, .shp, .gpkg

    Usage::

        loader = SiteLoader()
        sites = loader.load("project_sites.kml")
        # Returns GeoDataFrame with columns: site_id, name, geometry
    """

    SUPPORTED_EXTENSIONS = {".kml", ".kmz", ".geojson", ".json", ".shp", ".gpkg"}

    def load(self, path: Union[str, Path]) -> gpd.GeoDataFrame:
        """
        Load sites from a single file.

        Parameters
        ----------
        path : str or Path
            Path to the geospatial file.

        Returns
        -------
        GeoDataFrame
            Columns: site_id, name, geometry (EPSG:4326).
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Site file not found: {path}")

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported format '{ext}'. "
                f"Supported: {self.SUPPORTED_EXTENSIONS}"
            )

        if ext == ".kmz":
            gdf = self._load_kmz(path)
        elif ext in (".kml",):
            gdf = self._load_kml(path)
        elif ext in (".geojson", ".json"):
            gdf = gpd.read_file(path)
        elif ext == ".shp":
            gdf = gpd.read_file(path)
        elif ext == ".gpkg":
            gdf = gpd.read_file(path)
        else:
            gdf = gpd.read_file(path)

        # Standardise CRS to WGS 84
        if gdf.crs is None:
            logger.warning("No CRS detected, assuming EPSG:4326")
            gdf = gdf.set_crs("EPSG:4326")
        elif gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs("EPSG:4326")

        # Strip Z coordinates (KML/KMZ files include altitude which
        # causes 'Invalid GeoJSON geometry' errors in GEE and others)
        gdf["geometry"] = gdf["geometry"].apply(_force_2d)
        if any(gdf.geometry.has_z):
            logger.warning("Some geometries still have Z after force_2d")

        # Standardise columns
        gdf = self._standardise_columns(gdf, path.stem)

        logger.info(f"Loaded {len(gdf)} sites from {path.name}")
        return gdf

    def load_multiple(self, paths: List[Union[str, Path]]) -> gpd.GeoDataFrame:
        """Load and concatenate sites from multiple files."""
        gdfs = [self.load(p) for p in paths]
        combined = gpd.GeoDataFrame(
            __import__("pandas").concat(gdfs, ignore_index=True),
            crs="EPSG:4326",
        )
        # Ensure unique site_ids
        if combined["site_id"].duplicated().any():
            combined["site_id"] = [
                f"site_{i:04d}" for i in range(len(combined))
            ]
        return combined

    def _load_kml(self, path: Path) -> gpd.GeoDataFrame:
        """Load a KML file, trying multiple drivers."""
        try:
            return gpd.read_file(path, driver="KML")
        except Exception:
            try:
                return gpd.read_file(path, driver="LIBKML")
            except Exception as e:
                raise IOError(f"Failed to read KML file {path}: {e}")

    def _load_kmz(self, path: Path) -> gpd.GeoDataFrame:
        """Extract KML from KMZ archive and load."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with zipfile.ZipFile(path, "r") as z:
                kml_files = [f for f in z.namelist() if f.endswith(".kml")]
                if not kml_files:
                    raise ValueError(f"No KML file found inside KMZ: {path}")
                z.extract(kml_files[0], tmpdir)
                kml_path = Path(tmpdir) / kml_files[0]
                return self._load_kml(kml_path)

    def _standardise_columns(
        self, gdf: gpd.GeoDataFrame, file_stem: str
    ) -> gpd.GeoDataFrame:
        """Ensure consistent site_id and name columns."""
        # Try to find a name column
        name_col = None
        for candidate in ["Name", "name", "NAME", "site_name", "SITE_NAME"]:
            if candidate in gdf.columns:
                name_col = candidate
                break

        if name_col and name_col != "name":
            gdf = gdf.rename(columns={name_col: "name"})
        elif name_col is None:
            gdf["name"] = [f"{file_stem}_{i}" for i in range(len(gdf))]

        # Generate site_id
        if "site_id" not in gdf.columns:
            gdf["site_id"] = [
                f"{file_stem}_{i:04d}" for i in range(len(gdf))
            ]

        # Keep only essential columns + geometry
        keep = ["site_id", "name", "geometry"]
        extra = [c for c in gdf.columns if c not in keep and c != "geometry"]
        return gdf[keep + [c for c in extra if c in gdf.columns]]
