# Test ownership

Automated tests and test-only hosts belong in `tests/`. Python suites remain grouped by their existing `p00_contracts` through `p13_integration` owners; `g2_acceptance/` owns the acceptance scenarios and its stdio host.

`bridge/` contains the Node protocol tests and `vectors.json`, shared with `p10_protocol/test_vectors.py`. Node tests import the runtime client and canonicalizer using `../../bridge/protocol/` relative to each test file. The frozen digest examples remain in `contracts/v1/` and the legacy fixture remains in `fixtures/`.

Runtime implementations belong in `src/project_kernel/` and the repository's `bridge/protocol/`; keep test cases, test hosts and test-only vectors out of those directories. Generated Python bytecode is ignored, and local test output belongs in temporary or ignored output directories rather than runtime directories.

Existing acceptance captures, signatures, manifests, third-round records and ZIPs describe their original source layout and remain historical evidence. Moving a test does not refresh its acceptance or its recorded hash; current file locations and migration details belong in the [repository layout](../docs/development/repository-layout.md) and the [present task record](../docs/records/tasks/2026-10-10-layout-and-skill-growth.md).
