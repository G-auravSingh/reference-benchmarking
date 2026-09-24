# Legacy compatibility protocol

The legacy terrestrial package is intentionally vendored without source edits.

Before migrating any old project to the adaptive framework:

1. Run the old project using its original notebook/package version.
2. Save the complete scorecard and pillar/SoN outputs as a golden reference.
3. Run the same project through the new `terrestrial` profile once implemented.
4. Compare every unchanged metric with a numerical tolerance.
5. Investigate any difference before release.

The adaptive lake profile should not be used as a replacement for the old terrestrial workflow until this regression suite exists.
