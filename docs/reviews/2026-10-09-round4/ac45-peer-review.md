# AC45 Independent Peer Review

Scope: sealed G2 round-four evidence under `docs/acceptance/G2-round4`, checked read-only from the current worktree.

## Checks

- `protected-inputs.json` contains 53 entries. All 53 have `base_bytes_match: true`; every listed file exists and its recomputed SHA-256 matches. The base commit is `aca09b044c8138389039783152d0f1e13e58dba8`, and the acceptance matrix exists with the recorded SHA-256 `cbfd2340e621ad64764921beffd1b64058bdc3c9be56b57d736a40ca44c7d373`.
- The sealed scenario index contains 2,327 source-file entries. It records 410 `archived_path` entries; the sealed tree contains 411 files including `index.json`. Every archived file exists and matches the index size and SHA-256.
- The index records 913 database, WAL, SHM, or staged-WAL/SHM entries. All 913 are marked `database_bytes_not_archived: true`, and none has an `archived_path`. The sealed tree contains no SQLite/WAL/SHM file, ZIP, credential/secret file, cache file, contract file, or fixture file, and no archived evidence text points to a database path under the sealed destination.
- The sealed Python capture exits 0 and its output hash matches; its JUnit has 620 test cases with zero failures, errors, or skips. The sealed Node capture exits 0, its output hash matches, and its output reports 19 passed, zero failed, cancelled, skipped, or todo tests.
- The sealed index and sealed capture files match their `artifact-manifest.json` hashes.
- `artifact-manifest.json` is a source/evidence fingerprint list and consequently includes contract and fixture inputs; the exclusion check above applies to the staged scenario archive under `scenarios-sealed`, whose archived paths contain neither.

## Stability Gap

The sealed captures fingerprint `tools/build_g2_round4.py` as `36c01e53834f14c7e6154fa41980f5fa479e781fa5eb5652f960f5469e59aa30`, while the current file hashes to `7d4ebb48d8e5b0eb10b97b5882dafed1636701040a63b95d1309f2ddc8ae7b58`. The artifact manifest separately records `fcc3cdd99bdb0ce633f14116547eddeb8eab48880beabcf10c21b6674a64ce46` for the same file. `tools/verify_g2_evidence.py` therefore reports two sealed-capture input-hash changes and one manifest hash change.

## Verdict

`pending`: AC45 evidence content and exclusions pass the independent checks, but sealed capture input fingerprints and the final artifact manifest are not stable. Reconcile the build-tool bytes, then regenerate or replace the sealed capture and manifest hashes before accepting AC45. This review does not modify the sealed evidence, protected inputs, source, tests, or existing archives.
