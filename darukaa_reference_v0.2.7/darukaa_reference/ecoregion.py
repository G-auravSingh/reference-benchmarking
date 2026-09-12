"""
Ecoregion Resolver
==================

Tags each project site with its WWF RESOLVE Ecoregion (2017) via spatial join.

Adds columns: ECO_ID, ECO_NAME, BIOME_NUM, BIOME_NAME, REALM.

Reference
---------
Dinerstein, E., Olson, D., Joshi, A., et al. (2017). An Ecoregion-Based
Approach to Protecting Half the Terrestrial Realm. BioScience, 67(6), 534–545.
DOI: 10.1093/biosci/bix014

Olson, D.M., Dinerstein, E., et al. (2001). Terrestrial Ecoregions of the World:
A New Map of Life on Earth. BioScience, 51(11), 933–938.
DOI: 10.1641/0006-3568(2001)051[0933:TEOTWA]2.0.CO;2

Data Source
-----------
- GEE: ee.FeatureCollection("RESOLVE/ECOREGIONS/2017")
- Shapefile: https://storage.googleapis.com/teow2016/Ecoregions2017.zip
"""

from __future__ import annotations

import logging
from typing import Optional

import geopandas as gpd

from darukaa_reference.config import Config

logger = logging.getLogger(__name__)

# Columns we want from the ecoregion layer
ECO_COLUMNS = ["ECO_ID", "ECO_NAME", "BIOME_NUM", "BIOME_NAME", "REALM"]


class EcoregionResolver:
    """
    Resolve ecoregion membership for project sites.

    Supports two backends:
        - "gee": Uses Google Earth Engine FeatureCollection (requires ee.Initialize)
        - "local": Uses a local shapefile/geopackage

    Usage::

        resolver = EcoregionResolver(config)
        sites_with_eco = resolver.resolve(sites_gdf)
        # sites_gdf now has ECO_ID, ECO_NAME, BIOME_NUM, BIOME_NAME, REALM
    """

    def __init__(self, config: Config):
        self.config = config
        self._ecoregions_gdf: Optional[gpd.GeoDataFrame] = None

    def resolve(self, sites: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """
        Perform spatial join to tag each site with its ecoregion.

        Parameters
        ----------
        sites : GeoDataFrame
            Must have geometry in EPSG:4326.

        Returns
        -------
        GeoDataFrame
            Input sites with added ecoregion columns.
        """
        if self.config.ecoregion_source == "gee":
            return self._resolve_via_gee(sites)
        else:
            return self._resolve_via_local(sites)

    def _resolve_via_gee(self, sites: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Use GEE to resolve ecoregions (works for any number of sites)."""
        import ee

        eco_fc = ee.FeatureCollection(self.config.ecoregion_gee_asset)

        results = []
        for idx, row in sites.iterrows():
            centroid = row.geometry.centroid
            point = ee.Geometry.Point([centroid.x, centroid.y])

            # Filter ecoregions containing this point
            matched = eco_fc.filterBounds(point).first()
            try:
                info = matched.getInfo()
                if info and "properties" in info:
                    props = info["properties"]
                    results.append({
                        col: props.get(col) for col in ECO_COLUMNS
                    })
                else:
                    logger.warning(
                        f"No ecoregion found for site {row.get('site_id', idx)}"
                    )
                    results.append({col: None for col in ECO_COLUMNS})
            except Exception as e:
                logger.error(f"GEE error for site {row.get('site_id', idx)}: {e}")
                results.append({col: None for col in ECO_COLUMNS})

        import pandas as pd

        eco_df = pd.DataFrame(results)
        for col in ECO_COLUMNS:
            sites[col] = eco_df[col].values

        n_resolved = sites["ECO_ID"].notna().sum()
        logger.info(f"Resolved ecoregions for {n_resolved}/{len(sites)} sites")
        return sites

    def _resolve_via_local(self, sites: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Use local shapefile for spatial join."""
        if self._ecoregions_gdf is None:
            path = self.config.ecoregion_source
            logger.info(f"Loading ecoregion shapefile from {path}")
            self._ecoregions_gdf = gpd.read_file(path)
            if self._ecoregions_gdf.crs.to_epsg() != 4326:
                self._ecoregions_gdf = self._ecoregions_gdf.to_crs("EPSG:4326")

        # Spatial join
        joined = gpd.sjoin(
            sites,
            self._ecoregions_gdf[ECO_COLUMNS + ["geometry"]],
            how="left",
            predicate="intersects",
        )

        # Drop the index_right column from sjoin
        if "index_right" in joined.columns:
            joined = joined.drop(columns=["index_right"])

        # Handle duplicates (site spanning multiple ecoregions → keep first)
        if joined.index.duplicated().any():
            joined = joined[~joined.index.duplicated(keep="first")]

        n_resolved = joined["ECO_ID"].notna().sum()
        logger.info(f"Resolved ecoregions for {n_resolved}/{len(sites)} sites (local)")
        return joined

    def get_ecoregion_geometry(self, eco_id: int) -> Optional[object]:
        """
        Get the geometry of a specific ecoregion (for Tier 2 reference selection).

        Returns ee.Geometry if using GEE, or shapely geometry if local.
        """
        if self.config.ecoregion_source == "gee":
            import ee

            eco_fc = ee.FeatureCollection(self.config.ecoregion_gee_asset)
            return eco_fc.filter(ee.Filter.eq("ECO_ID", eco_id)).geometry()
        else:
            if self._ecoregions_gdf is None:
                self._ecoregions_gdf = gpd.read_file(self.config.ecoregion_source)
            match = self._ecoregions_gdf[
                self._ecoregions_gdf["ECO_ID"] == eco_id
            ]
            if len(match) > 0:
                return match.iloc[0].geometry
            return None
