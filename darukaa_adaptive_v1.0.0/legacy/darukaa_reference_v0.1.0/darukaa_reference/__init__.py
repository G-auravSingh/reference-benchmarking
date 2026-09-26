"""
darukaa_reference — Biodiversity Indicator Reference Benchmarking Pipeline
==========================================================================

A modular, indicator-agnostic framework for comparing project-site biodiversity
metrics against ecoregion-specific reference benchmarks at two tiers:

    Tier 1 — Global Modelled Reference (ex-situ):
        Pre-computed global raster layers (GLOBIO4 MSA, BII, EII, SEED, etc.)
        extracted at site location and ecoregion scale.

    Tier 2 — Contemporary Reference (SEED-style):
        Top 5% least-disturbed pixels within the same ecoregion × land-cover
        combination, identified via Global Human Modification Index.

Methodology References
----------------------
- Dinerstein et al. (2017). BioScience, 67(6), 534–545. DOI:10.1093/biosci/bix014
- Schipper et al. (2020). Global Change Biology, 26(2), 760–771. DOI:10.1111/gcb.14848
- Newbold et al. (2016). Science, 353(6296), 288–291. DOI:10.1126/science.aaf2201
- McElderry et al. (2024). EcoEvoRxiv. DOI:10.32942/X2689N
- McNellie et al. (2020). Global Change Biology, 26(12), 6702–6714. DOI:10.1111/gcb.15383
- Yen et al. (2019). Ecological Applications, 29(7), e01970. DOI:10.1002/eap.1970
- Kennedy et al. (2019). Global Change Biology, 25(3), 811–826. DOI:10.1111/gcb.14549
- Hill et al. (2022). bioRxiv. DOI:10.1101/2022.08.21.504707

Author: Darukaa.Earth
"""

__version__ = "0.1.0"

from darukaa_reference.registry import IndicatorRegistry
from darukaa_reference.site_loader import SiteLoader
from darukaa_reference.ecoregion import EcoregionResolver
from darukaa_reference.reference import ReferenceSelector
from darukaa_reference.statistics import StatisticalComparison
from darukaa_reference.report import ReportGenerator
from darukaa_reference.pipeline import Pipeline
