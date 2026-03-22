"""
Pre-registered Indicators
=========================

Seven default indicators covering Darukaa's four pillars, each with its
extraction function, GEE/raster source, and peer-reviewed citation.

To add a new indicator, simply write an extract_fn and call registry.register().
No changes to core pipeline code are needed.

Registered indicators:
    1. ndvi          — Vegetation Structure (Sentinel-2, Pillar 1)
    2. lst           — Land Surface Temperature (MODIS MOD11A2, Pillar 1)
    3. msa_globio4   — Mean Species Abundance (GLOBIO4 raster, Pillar 3)
    4. bii           — Biodiversity Intactness Index (GEE, Pillar 3)
    5. eii           — Ecosystem Integrity Index (GEE, Pillar 1)
    6. seed          — SEED Biocomplexity Index (local raster, Pillar 1)
    7. ghm           — Global Human Modification (GEE, Pillar 4)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Union

import numpy as np

from darukaa_reference.config import Config
from darukaa_reference.registry import IndicatorRegistry

logger = logging.getLogger(__name__)


def create_default_registry() -> IndicatorRegistry:
    """
    Create an IndicatorRegistry pre-loaded with all default indicators.

    Returns
    -------
    IndicatorRegistry
        Registry with 7 indicators ready to use.
    """
    registry = IndicatorRegistry()

    # 1. NDVI — Sentinel-2
    #    Regional vegetation patterns operate at 50–100 km scale
    registry.register(
        name="ndvi",
        display_name="Vegetation Structure (NDVI)",
        source_type="gee",
        extract_fn=extract_ndvi,
        unit="index",
        value_range=(-1.0, 1.0),
        citation=(
            "Sentinel-2 MSI Level-2A Surface Reflectance. "
            "Drusch, M. et al. (2012). Sentinel-2: ESA's Optical High-Resolution "
            "Mission for GMES Operational Services. RSE, 120, 25–36. "
            "DOI:10.1016/j.rse.2011.11.026"
        ),
        tier1_layer="COPERNICUS/S2_SR_HARMONIZED",
        tier2_eligible=True,
        reference_radius_km=50.0,  # Vegetation community scale
        pillar=1,
        metadata={"gee_image_fn": _build_ndvi_image},
    )

    # 2. LST — MODIS (PRESSURE-like: lower LST = more canopy/evapotranspiration = healthier)
    #    Tight radius to reduce elevation confounding in mountainous regions
    registry.register(
        name="lst",
        display_name="Land Surface Temperature",
        source_type="gee",
        extract_fn=extract_lst,
        unit="°C",
        value_range=(-40.0, 70.0),
        citation=(
            "Wan, Z., Hook, S., & Hulley, G. (2021). MOD11A2 v061. "
            "NASA EOSDIS LP DAAC. DOI:10.5067/MODIS/MOD11A2.061"
        ),
        tier1_layer="MODIS/061/MOD11A2",
        tier2_eligible=True,
        higher_is_better=False,  # Lower LST = more canopy = healthier ecosystem
        reference_radius_km=25.0,  # Tight radius — LST varies sharply with elevation
        pillar=1,
        metadata={"gee_image_fn": _build_lst_image},
    )

    # 3. MSA — GLOBIO4 (local raster)
    #    MSA is a macroecological metric — ecoregion scale is ideal
    registry.register(
        name="msa_globio4",
        display_name="Mean Species Abundance (GLOBIO4)",
        source_type="local_raster",
        extract_fn=extract_msa_local,
        unit="index",
        value_range=(0.0, 1.0),
        citation=(
            "Schipper, A.M., Hilbers, J.P., Meijer, J.R., et al. (2020). "
            "Projecting terrestrial biodiversity intactness with GLOBIO 4. "
            "Global Change Biology, 26(2), 760–771. DOI:10.1111/gcb.14848"
        ),
        tier1_layer=None,  # Set via config.raster_paths["globio4_msa"]
        tier2_eligible=True,
        reference_radius_km=100.0,  # Macroecological — broad landscape
        pillar=3,
    )

    # 4. BII — Biodiversity Intactness Index
    #    Community-level intactness — broad landscape scale
    registry.register(
        name="bii",
        display_name="Biodiversity Intactness Index",
        source_type="gee",
        extract_fn=extract_bii,
        unit="index",
        value_range=(0.0, 1.0),
        citation=(
            "Newbold, T. et al. (2016). Has land use pushed terrestrial "
            "biodiversity beyond the planetary boundary? Science, 353(6296), "
            "288–291. DOI:10.1126/science.aaf2201. "
            "Impact Observatory ~100m BII layer."
        ),
        tier1_layer="projects/ebx-data/assets/earthblox/IO/BIOINTACT",
        tier2_eligible=True,
        reference_radius_km=75.0,  # Community intactness — regional landscape
        pillar=3,
        metadata={"gee_image_fn": _build_bii_image},
    )

    # 5. EII — Ecosystem Integrity Index (Landbanking Group open-source)
    #    Composite of structure + function + composition — broad scale
    registry.register(
        name="eii",
        display_name="Ecosystem Integrity Index",
        source_type="gee",
        extract_fn=extract_eii,
        unit="index",
        value_range=(0.0, 1.0),
        citation=(
            "Hill, S.L.L. et al. (2022). The Ecosystem Integrity Index: "
            "a novel measure of terrestrial ecosystem integrity. "
            "bioRxiv. DOI:10.1101/2022.08.21.504707. "
            "Open-source: github.com/landler-io/ecosystem-integrity-index"
        ),
        tier1_layer=None,  # EII is computed from components, not a single asset
        tier2_eligible=True,
        reference_radius_km=75.0,  # Ecosystem-level — matches BII scale
        pillar=1,
        metadata={"gee_image_fn": _build_eii_image},
    )

    # 6. SEED Biocomplexity Index (local raster)
    #    Designed for ecoregion-scale comparison per McElderry et al. (2024)
    registry.register(
        name="seed",
        display_name="SEED Biocomplexity Index",
        source_type="local_raster",
        extract_fn=extract_seed_local,
        unit="index",
        value_range=(0.0, 1.0),
        citation=(
            "McElderry, R.M. et al. (2024). Assessing the multidimensional "
            "complexity of biodiversity using a globally standardized approach. "
            "EcoEvoRxiv. DOI:10.32942/X2689N. "
            "Data: Zenodo DOI:10.5281/zenodo.13799961"
        ),
        tier1_layer=None,  # Set via config.raster_paths["seed_biocomplexity"]
        tier2_eligible=True,
        reference_radius_km=100.0,  # SEED is inherently ecoregion-scale
        pillar=1,
    )

    # 7. gHM — Global Human Modification (PRESSURE indicator: lower = better)
    #    Landscape disturbance — broad scale for context
    registry.register(
        name="ghm",
        display_name="Global Human Modification",
        source_type="gee",
        extract_fn=extract_ghm,
        unit="index",
        value_range=(0.0, 1.0),
        citation=(
            "Kennedy, C.M. et al. (2019). Managing the middle: A shift in "
            "conservation priorities based on the global human modification "
            "gradient. Global Change Biology, 25(3), 811–826. "
            "DOI:10.1111/gcb.14549"
        ),
        tier1_layer="CSP/HM/GlobalHumanModification",
        tier2_eligible=False,  # gHM is the selector, not a benchmarked indicator
        higher_is_better=False,  # PRESSURE: lower human modification = better
        reference_radius_km=50.0,  # Landscape disturbance context
        pillar=4,
        metadata={"gee_image_fn": _build_ghm_image},
    )

    return registry


# ===========================================================================
# Extraction functions
# ===========================================================================
# Each function has the signature: (geometry, config) → dict
# geometry: shapely geometry or ee.Geometry
# config: Config
# Returns: {"value": float, "pixels": np.ndarray (optional)}


def extract_ndvi(geometry, config: Config) -> Dict[str, Any]:
    """
    Extract median annual NDVI from Sentinel-2 SR Harmonized.

    NDVI = (B8 - B4) / (B8 + B4)  at 10 m resolution.
    Cloud-masked using QA60 bitmask; annual median composite.
    """
    import ee

    image = _build_ndvi_image(config)
    return _reduce_image_at_site(image, geometry, scale=10)


def extract_lst(geometry, config: Config) -> Dict[str, Any]:
    """
    Extract mean annual daytime Land Surface Temperature from MODIS MOD11A2.

    Conversion: raw × 0.02 − 273.15 = °C.
    """
    import ee

    image = _build_lst_image(config)
    return _reduce_image_at_site(image, geometry, scale=1000)


def extract_msa_local(geometry, config: Config) -> Dict[str, Any]:
    """
    Extract MSA from a locally-stored GLOBIO4 GeoTIFF.

    Requires config.raster_paths["globio4_msa"] to be set.

    Reference: Schipper et al. (2020). DOI:10.1111/gcb.14848
    """
    raster_path = config.raster_paths.get("globio4_msa")
    if not raster_path:
        raise ValueError("config.raster_paths['globio4_msa'] not set")
    return _extract_from_local_raster(raster_path, geometry, band=1)


def extract_bii(geometry, config: Config) -> Dict[str, Any]:
    """
    Extract BII from available GEE source.

    Reference: Newbold et al. (2016). DOI:10.1126/science.aaf2201
    """
    import ee

    image = _build_bii_image(config)
    if image is None:
        return {"value": None, "pixels": None}
    return _reduce_image_at_site(image, geometry, scale=100)


def extract_eii(geometry, config: Config) -> Dict[str, Any]:
    """
    Extract EII (Ecosystem Integrity Index).

    EII = fuzzy_minimum(Structural, Compositional, Functional integrity).

    Reference: Hill et al. (2022). DOI:10.1101/2022.08.21.504707
    Open-source: github.com/landler-io/ecosystem-integrity-index
    """
    import ee

    image = _build_eii_image(config)
    if image is None:
        return {"value": None, "pixels": None}
    return _reduce_image_at_site(image, geometry, scale=300)


def extract_seed_local(geometry, config: Config) -> Dict[str, Any]:
    """
    Extract SEED Biocomplexity Index from a locally-stored 10-band GeoTIFF.

    Band 1 = headline Biocomplexity Index (weighted average of 9 dimensions).

    Reference: McElderry et al. (2024). DOI:10.32942/X2689N
    Data: Zenodo DOI:10.5281/zenodo.13799961
    """
    raster_path = config.raster_paths.get("seed_biocomplexity")
    if not raster_path:
        raise ValueError("config.raster_paths['seed_biocomplexity'] not set")
    return _extract_from_local_raster(raster_path, geometry, band=1)


def extract_ghm(geometry, config: Config) -> Dict[str, Any]:
    """
    Extract Global Human Modification index (0–1).

    Reference: Kennedy et al. (2019). DOI:10.1111/gcb.14549
    GEE: CSP/HM/GlobalHumanModification
    """
    import ee

    image = _build_ghm_image(config)
    return _reduce_image_at_site(image, geometry, scale=1000)


# ===========================================================================
# GEE image builders (used by both extract_fn and ReferenceSelector)
# ===========================================================================


def _build_ndvi_image(config: Config):
    """Build annual median NDVI from Sentinel-2."""
    import ee

    year = config.ndvi_year

    def mask_clouds(image):
        qa = image.select("QA60")
        mask = qa.bitwiseAnd(1 << 10).eq(0).And(qa.bitwiseAnd(1 << 11).eq(0))
        return image.updateMask(mask).divide(10000)

    s2 = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterDate(f"{year}-01-01", f"{year}-12-31")
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", config.ndvi_cloud_threshold))
        .map(mask_clouds)
    )

    ndvi = s2.map(
        lambda img: img.normalizedDifference(["B8", "B4"]).rename("NDVI")
    ).median()

    return ndvi.select("NDVI")


def _build_lst_image(config: Config):
    """Build mean annual daytime LST from MODIS."""
    import ee

    year = config.lst_year
    lst = (
        ee.ImageCollection("MODIS/061/MOD11A2")
        .filterDate(f"{year}-01-01", f"{year}-12-31")
        .select("LST_Day_1km")
    )
    return lst.mean().multiply(0.02).subtract(273.15).rename("LST")


def _build_bii_image(config: Config):
    """
    Get Biodiversity Intactness Index image.

    Tries multiple sources in order:
    1. GEE Community Catalog BII (public, ~100m)
    2. Impact Observatory asset (may require access)

    Reference: Newbold et al. (2016). Science, 353(6296), 288–291.
    DOI:10.1126/science.aaf2201
    """
    import ee

    # Source 1: GEE Community Catalog (publicly accessible)
    BII_ASSETS = [
        "projects/sat-io/open-datasets/BII/BII_2017",
        "projects/ebx-data/assets/earthblox/IO/BIOINTACT",
    ]

    for asset_id in BII_ASSETS:
        try:
            # Try as Image first
            img = ee.Image(asset_id).select(0).rename("BII")
            # Force evaluation to check if accessible
            img.getInfo()
            logger.info(f"BII loaded from: {asset_id}")
            return img
        except Exception:
            try:
                # Try as ImageCollection
                img = (
                    ee.ImageCollection(asset_id)
                    .sort("system:time_start", False)
                    .first()
                    .select(0)
                    .rename("BII")
                )
                img.getInfo()
                logger.info(f"BII loaded from collection: {asset_id}")
                return img
            except Exception:
                logger.debug(f"BII asset not accessible: {asset_id}")
                continue

    logger.warning(
        "No BII asset accessible. To use BII, download NHM v2.1.1 from "
        "https://data.nhm.ac.uk/dataset/bii-developed-by-nhm-v2-1-1-limited-release "
        "and register as a local_raster indicator."
    )
    return None


def _build_eii_image(config: Config):
    """
    Build a simplified EII from its three components.

    Structural: 1 - gHM
    Compositional: BII
    Functional: actual NPP / potential NPP (simplified as MODIS NPP)

    EII = fuzzy_minimum(S, C, F)
    The minimum component is the score; other low components pull it down further.

    Reference: Hill et al. (2022). DOI:10.1101/2022.08.21.504707
    Landbanking implementation: github.com/landler-io/ecosystem-integrity-index
    """
    import ee

    # Structural: inverse of human modification
    structural = (
        ee.ImageCollection("CSP/HM/GlobalHumanModification")
        .first()
        .select("gHM")
    )
    structural = ee.Image.constant(1).subtract(structural).rename("structural")

    # Compositional: BII (may not be available)
    bii_image = _build_bii_image(config)

    # Functional: Use MODIS NPP as proxy (simplified)
    # Full EII uses actual/potential NPP ratio; here we normalize MODIS NPP
    npp = (
        ee.ImageCollection("MODIS/061/MOD17A3HGF")
        .sort("system:time_start", False)
        .first()
        .select("Npp")
        .multiply(0.0001)  # scale factor
    )
    # Normalize to 0-1 (rough: max global NPP ~2000 gC/m²/yr)
    functional = npp.divide(2.0).min(1.0).max(0.0).rename("functional")

    # Fuzzy minimum: min(S, C, F) — or min(S, F) if BII unavailable
    if bii_image is not None:
        compositional = bii_image.rename("compositional")
        stack = structural.addBands(compositional).addBands(functional)
    else:
        logger.warning("EII: BII unavailable, using structural + functional only")
        stack = structural.addBands(functional)

    eii = stack.reduce(ee.Reducer.min()).rename("EII")

    return eii


def _build_ghm_image(config: Config):
    """Get gHM image. CSP/HM/GlobalHumanModification is an ImageCollection."""
    import ee

    return (
        ee.ImageCollection("CSP/HM/GlobalHumanModification")
        .first()
        .select("gHM")
        .rename("gHM")
    )


# ===========================================================================
# Helpers
# ===========================================================================


def _reduce_image_at_site(image, geometry, scale: int = 100) -> Dict[str, Any]:
    """Extract mean value of a GEE image within a geometry."""
    import ee

    # Convert shapely to ee.Geometry if needed
    if not isinstance(geometry, ee.Geometry):
        from shapely.geometry import mapping
        from shapely.ops import transform as shapely_transform

        # Strip Z coordinates — KML/KMZ files include altitude which GEE rejects
        if hasattr(geometry, "has_z") and geometry.has_z:
            geometry = shapely_transform(lambda x, y, z=None: (x, y), geometry)

        geojson = mapping(geometry)
        geometry = ee.Geometry(geojson)

    stats = image.reduceRegion(
        reducer=ee.Reducer.mean().combine(ee.Reducer.median(), sharedInputs=True),
        geometry=geometry,
        scale=scale,
        maxPixels=1e8,
        bestEffort=True,
    ).getInfo()

    # Parse — get first non-None mean value
    value = None
    for k, v in (stats or {}).items():
        if "mean" in k.lower() and v is not None:
            value = v
            break

    if value is None:
        for v in (stats or {}).values():
            if v is not None:
                value = v
                break

    return {"value": value, "pixels": None}


def _extract_from_local_raster(
    raster_path: str, geometry, band: int = 1
) -> Dict[str, Any]:
    """Extract values from a local GeoTIFF within a geometry."""
    import rasterio
    from rasterio.mask import mask as rio_mask
    from shapely.geometry import mapping, Point

    with rasterio.open(raster_path) as src:
        # If geometry is a point or very small, use a buffer
        if hasattr(geometry, "area") and geometry.area < 1e-6:
            # Point-like; sample the raster directly
            centroid = geometry.centroid if hasattr(geometry, "centroid") else geometry
            if isinstance(centroid, Point):
                row, col = src.index(centroid.x, centroid.y)
                data = src.read(band)
                val = float(data[row, col])
                if src.nodata is not None and val == src.nodata:
                    return {"value": None, "pixels": None}
                return {"value": val, "pixels": np.array([val])}

        geom_json = [mapping(geometry)]
        try:
            out_image, _ = rio_mask(src, geom_json, crop=True, nodata=src.nodata)
            arr = out_image[band - 1]
            if src.nodata is not None:
                arr = arr[arr != src.nodata]
            arr = arr[np.isfinite(arr)]
            if len(arr) == 0:
                return {"value": None, "pixels": None}
            return {"value": float(np.nanmean(arr)), "pixels": arr}
        except Exception as e:
            logger.warning(f"Raster extraction failed: {e}")
            return {"value": None, "pixels": None}
