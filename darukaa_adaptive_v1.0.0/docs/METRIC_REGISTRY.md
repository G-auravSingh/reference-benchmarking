# Lake metric registry — v1.0.0

| Metric | Domain | Automated? | Default SoN? | Notes |
|---|---|---:|---:|---|
| Water extent | Fixed KML + dynamic water | Yes | No | Primary site-status variable; report as extent and fraction. |
| Water persistence | Fixed KML + dynamic water | Yes | No | Current-year high-persistence fraction; distinct from JRC historical persistence. |
| TSPI / NDCI | Dynamic water | Yes | Yes* | Proxy, not field-calibrated chlorophyll-a. |
| SABF / FAI | Dynamic water | Yes | Yes* | Frequency of FAI bloom proxy among valid water observations. |
| WCPI | Dynamic water | Yes | Yes* | Remote-sensing clarity/turbidity proxy. |
| WSDI | Fixed KML + dynamic water | Yes | Yes* | High values mean frequent transition; ecological interpretation needs lake-specific validation. |
| Riparian NDVI trend | Fixed external riparian buffer | Yes | Yes* | Multi-year annual median NDVI slope. |
| RCI | Fixed external riparian buffer | Yes | Yes* | Retains supplied formula family. |
| SHDI | Derived water shoreline | Yes | No | Descriptive morphometric metric by default. |
| Threatened richness | Species range context | Optional | No | Range overlap is not confirmed local occurrence. |
| Endemic richness | Species range context | Optional | No | Species-area/range-overlap caveat. |
| CERI | Species range context | Optional | No | Range-overlap conservation-risk profile. |
| STAR_T | Species range context | Optional | No | Threat-abatement opportunity, not extinction probability. |

`*` Compatibility scoring only; thresholds are inherited from the supplied Nandoshi notebook and require formal aquatic validation before client-grade use.
