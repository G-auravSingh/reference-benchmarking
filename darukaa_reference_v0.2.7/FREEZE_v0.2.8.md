# v0.2.8 CONTRACT FROZEN (production Tata assessment)

| | |
|---|---|
| Contract version | `0.2.8` (`indicator_contract.CONTRACT_VERSION`) |
| Code frozen at | commit `0f1eef8` on `v0.2.8-contract`; this freeze commit adds documentation only (the `darukaa_reference/` package tree is byte-identical to `0f1eef8`) |
| Package source SHA-256 | `ce2ecb733d20b2710365da9e776ff00d0bc8e015ceaf5aa828a20d732478c26d` (every production audit must record exactly this in `provenance.source_sha256_at_import`) |
| Configuration SHA-256 | `7f64f9f08879e1cb9be73cd3728f2a5285e94e5fff13614ec138eede75fb5057` (identical in the run-3 and run-4 outputs) |
| Package `__version__` | still reads `0.2.7` by design (not bumped, to keep the code byte-identical); the contract version is authoritative |
| `main` | untouched (`be73839`) |

## Evidence
* Run 3 (code `9c2c4d3`): parity 55 MATCH / 0 DISCREPANCY / 38 INFO / 0 HARNESS_ERROR; Deccan 8 scored; Lake_Suman 7 scored; aquatic permanence
  consistent (spread 0.0032). Source fingerprints recorded in those outputs were re-derived independently from git and match.
* Run 4 (code `0f1eef8`): fresh forest-validation audit with real provenance; strict provenance gate ok; the ZIP holds only the four fresh artifacts.
* `9c2c4d3` -> `0f1eef8`: one package file changed (`provenance.py`, +59 lines, 0 deleted, one added function that nothing in the package calls);
  the twelve scoring / reference / parity / contract / config / indicator modules are byte-identical. 321 offline tests pass.

## What is frozen
The indicator contract, the applicability rules and statuses, the coverage-weighted site-support convention, the water-body construction (pixel-count
area, edge rule, `MAX_WATER_BODY_EXTENT_M = 2000`), the canonical aquatic permanence (S1 occurrence over the body, 10 m), the tiled reference builders,
the percentile / robust-z scoring, the parity harness, the provenance mechanism. Headline aggregation is unchanged.

## Known limitations carried into production (none blocks the Tata assessment)
1. Forest-loss reference availability on external forest zones (§13.4). Not reachable by Tata zones.
2. `ndvi` and `chm` least-disturbed references are small (n = 138 on Deccan) but above the minimum of 30.
3. 0.4-0.8 % residuals between Earth Engine and numpy site values (INFO, unexplained, by decision not investigated).
4. `tspi` is `pending_methodology`.
5. Runtime is long under restricted quota (Deccan about 1 h 15 min; each aquatic reference 14-18 min).

## Running production
Pull tag `v0.2.8-contract-frozen`, **restart the runtime**, run the provenance gate cell (it stops on a stale or dirty checkout), write to a **fresh output
folder**, and finish with `provenance.verify_outputs(<folder>)`. Any change to the package invalidates this freeze: it needs a new version.
