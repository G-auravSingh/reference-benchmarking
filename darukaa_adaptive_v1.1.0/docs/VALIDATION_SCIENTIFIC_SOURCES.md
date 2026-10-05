# Scientific and Dataset Sources Used for Validation

The framework was checked against the following authoritative or primary documentation during the v1.1.0 design/build review.

1. TNFD. *Guidance on the identification and assessment of nature-related issues: The TNFD LEAP approach v1.1* (2023). Reference condition is context-dependent; ecosystem condition is compared to a reference state; no single universal condition metric is prescribed.
2. TNFD. *Metrics*. TNFD explicitly notes that no single metric captures all relevant dimensions of changes to the state of nature.
3. SEEA. *Selection criteria for ecosystem condition indicators* (2024). Indicator selection should be transparent and scientifically grounded, with conceptual relevance and practical validity, while the overall set should be comprehensive and parsimonious.
4. SEEA. *Technical Recommendations / Ecosystem condition accounts*. Reference conditions provide a common measurement basis and condition indicators can be normalized before aggregation; uncertainty and data gaps should remain visible.
5. Google Earth Engine Data Catalog. *Dynamic World V1*. 10 m land-cover probability/label dataset used for land-cover and water-screening operations.
6. Google Earth Engine Data Catalog. *RESOLVE Ecoregions 2017*. 846 terrestrial ecoregions used as a biogeographic context layer, not as a universal aquatic ecosystem typology.
7. Google Earth Engine Data Catalog. *TNC Global Human Modification v3 — 90 m static snapshot*. 2022 terrestrial human-modification layer, 0–1, with `All_threats_combined`; used as a pressure screen rather than an ecological-integrity score.

The package does not claim that any dataset above is a direct measurement of biodiversity. Dataset limitations are retained in the indicator registry and report.
