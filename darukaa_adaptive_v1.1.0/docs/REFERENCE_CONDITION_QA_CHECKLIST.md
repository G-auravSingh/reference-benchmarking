# Reference-Condition QA Checklist

This checklist is mandatory for any production release that changes reference selection, reference scoring or the datasets used to construct reference populations.

## A. Candidate construction

- [ ] Assessed site boundary is excluded from the automatic candidate search.
- [ ] Reference search radius is documented and profile-controlled.
- [ ] Reference search radius is not confused with the ordinary analytical context.
- [ ] Dominant ecological/biogeographic stratum is resolved.
- [ ] Habitat/ecosystem comparability rule is documented.
- [ ] Temporal window matches the assessment question.
- [ ] Anthropogenic pressure screen is documented.
- [ ] Minimum area/pixel requirements are applied.
- [ ] Candidate geometry is non-empty when approval is claimed.

## B. Earth Engine dataset QA

- [ ] Dynamic World asset resolves as an ImageCollection.
- [ ] TNC HM v3 `TNC/HM/v3/90m_s` resolves as an ImageCollection.
- [ ] TNC `All_threats_combined` band resolves.
- [ ] RESOLVE Ecoregions 2017 resolves as a FeatureCollection.
- [ ] Dataset temporal coverage is appropriate for the assessment.
- [ ] Dataset API/type errors are distinguished from valid candidate rejection.

## C. Reference approval

- [ ] Candidate passes population adequacy.
- [ ] Candidate passes ecological match.
- [ ] Candidate passes pressure screen.
- [ ] Candidate passes temporal compatibility.
- [ ] Candidate passes spatial quality.
- [ ] Automated approval is impossible unless all gates pass.
- [ ] Approval basis is stored in output.
- [ ] Reference state is stored in output.

## D. Reference distribution and benchmark

- [ ] Reference central estimator is documented; default is spatial median (`P50`) where available.
- [ ] Reference sample size/valid pixels are retained.
- [ ] Spatial distribution diagnostics are retained where values are available.
- [ ] Relative departure is signed and direction-aware.
- [ ] Reference attainment is bounded and not described as ecological perfection.
- [ ] Reference uncertainty is not represented as a formal independent-pixel confidence interval.
- [ ] Uncalibrated proxies remain explicitly labelled as proxies.
- [ ] `water_extent` is not benchmarked against a fabricated 100% water target.

## E. Scoring

- [ ] Metric is usable before it can be scored.
- [ ] Reference exists and is approved for scoring.
- [ ] C4 Pressure remains separate from C1–C3 condition.
- [ ] C3 Fauna requirement is applied according to the active profile.
- [ ] Missing/unassessed pillars are represented as missing/not assessed, not 100.
- [ ] Concern bands are identified as Darukaa product conventions rather than universal ecological thresholds.

## F. Reporting and provenance

- [ ] Reference state shown.
- [ ] Reference method shown.
- [ ] Reference approval shown.
- [ ] Reference diagnostics shown in machine-readable output.
- [ ] `reference_governance.csv` generated.
- [ ] Exact Git commit recorded.
- [ ] Site-file SHA-256 recorded.
- [ ] Condition and pressure remain separate.
- [ ] Landscape intactness is not used as a generic synonym for reference attainment.

## G. Dataset/method upgrades

- [ ] Dataset ID/version/date recorded.
- [ ] Native resolution reviewed.
- [ ] Temporal coverage reviewed.
- [ ] Formula/masking changes regression-tested.
- [ ] Reference compatibility re-reviewed.
- [ ] Changelog updated.
- [ ] Live Earth Engine validation repeated before client use.
