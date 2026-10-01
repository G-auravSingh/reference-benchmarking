# Reference-Condition QA Checklist

This checklist is mandatory for any production release that changes reference selection or scoring.

## Candidate construction

- [ ] Site boundary excluded from candidate population.
- [ ] Search radius documented and profile-controlled.
- [ ] Ecological region/classification resolved.
- [ ] Habitat/ecosystem comparability rule documented.
- [ ] Temporal window matches the assessment question.
- [ ] Anthropogenic pressure screen documented.
- [ ] Minimum area/pixel requirements applied.

## Reference approval

- [ ] Candidate passes population adequacy.
- [ ] Candidate passes ecological match.
- [ ] Candidate passes pressure screen.
- [ ] Candidate passes temporal compatibility.
- [ ] Candidate passes spatial quality.
- [ ] Automated approval is impossible unless all gates pass.
- [ ] Approval basis is stored in output.

## Metric benchmark

- [ ] Metric direction/target is explicitly declared.
- [ ] Reference median and sample size are retained.
- [ ] Distribution diagnostics are retained where values are available.
- [ ] Reference uncertainty is not represented as independent-pixel confidence.
- [ ] Relative departure is signed and interpretable.
- [ ] Reference attainment is not called ecological perfection.
- [ ] Uncalibrated proxies remain contextual/screening unless separately validated.

## Reporting

- [ ] Reference state shown.
- [ ] Reference method shown.
- [ ] Reference approval shown.
- [ ] No missing-fauna pillar is displayed as 100.
- [ ] Condition and pressure remain separate.
- [ ] Landscape intactness is not used as a generic synonym for reference attainment.

## Dataset upgrades

- [ ] Dataset ID/version/date recorded.
- [ ] Native resolution reviewed.
- [ ] Temporal coverage reviewed.
- [ ] Formula/masking changes regression-tested.
- [ ] Reference compatibility re-reviewed.
- [ ] Changelog updated.
