# Project Kernel

A project delivery governance kernel alongside an agent runtime. Models propose, independent checkers verify, people approve an exact snapshot, and providers apply and observe external effects.

[中文与19张设计图](README.md) · [Demo · 3m53s](docs/assets/demo.mp4) · [Design](docs/architecture/kernel-design-and-growth.md) · [Current capabilities](docs/architecture/current-state.md)

## Responsibilities

The kernel owns execution flow and project data/statistics. The host owns the model loop, tools, sessions, compaction, skill loading, subagents and sandbox lifecycle. Interfaces are optional consumers.

The eight-stage design is design → split → dispatch → execute → package/verify → review → human confirmation → apply and publish adoption. Project L0 and module L1 records carry exact versions; R1 currently uses logical layers within a project SQLite database. ContextManifest records actual inputs, selection/exclusion and budgets. Questions reference the versions read; transient forms belong to the host until submission.

Multiple implementations and fixed integration candidates coexist. Implementation, knowledge-use and skill scores are separate. Machine checks, model review, human approval and external success are distinct facts. Completion has six levels: receipt, persistence, candidate verification, approval, observed effect and adoption publication. Unknown effects are observed or reconciled, never silently retried.

Raw process records, sourced project memory and explicitly promoted shared memory form three layers. Skills retain versions and applicability; error reviews retain evidence, correction and rollback. Migration freezes a mapping for human review without inventing historical approvals or test results.

## Problems and limits

Versioned facts and read watermarks address forgotten context and opaque execution; durable attempts and idempotent receipts prevent duplicate effects; independent checking rejects self-reported results; snapshot approval binds authorization to exact content. The heat-inversion example retains failed and unknown strategies and rejects a forged result.

Repository hygiene is a continuing task. Staging/ready, manifests and digests already provide a foundation. Output path/type/size budgets, unowned-output quarantine, reference-aware retention, reviewable cleanup and host enforcement are still incomplete. Directory isolation and skill instructions are not an OS sandbox.

## Modularity and growth

Contracts define versioned inputs; domain contains pure rules; application orchestrates authorization and atomic use cases; data owns revisions, queries and receipts; providers own side effects; bridges map protocols without duplicating business state. New modules must declare their fact owner, ports, failure/unknown behavior and acceptance criteria. Known debt includes application SQL, mismatched port signatures and incomplete provider capability aggregation.

The headless integration is a **plan**: standard skills for context, design/dispatch, execution/verification, comparison, delivery review and reconciliation call a host adapter and versioned kernel contract. The existing custom stdio JSON-RPC is not MCP. MCP/HTTP bridges and each new framework require separate acceptance; skills cannot approve delivery. Priorities are a capability matrix, read skills, then controlled write skills.

## Implementation tracks

- v1 in `src/project_kernel/`: immutable ledger, attempts, verification, approval, delivery effects and queries. Historical `accepted_g2`, `release_approved=false`, test evidence, directory-only isolation.
- The separate local R1 development track (not included in this documentation/media release): independent S0–S7 reference slices for project/module layers, contexts, candidates, adoption and SCM rules. Eight real-host acceptance cases remain `not_run`; this is not automatically a v1 feature set.
- AGH is one demonstrated adapter. Frontend development is outside this kernel documentation change.
- KnowledgeService is not wired into core RPC; corpus is disabled by default; document skills do not imply a runtime loader.

This cleanup ran 3 import-boundary tests and in-memory compilation of 278 Python files. Expanded R1 tests encountered sandbox write restrictions; no new full-suite acceptance is claimed. Video: 233.223 seconds, 1080p30, animated reveals/zoom, staggered frames and original AGH footage.

## Source checkout

Python 3.12+ and the complete source tree are required; the wheel does not bundle `contracts/v1` yet.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider tests/p00_contracts/test_import_boundaries.py -q
```

See [design and growth](docs/architecture/kernel-design-and-growth.md), [module map](docs/modules/README.md), [R1 blueprint](docs/architecture/reproduction-blueprint.md), [ongoing plan](docs/plans/kernel-hygiene-and-headless.md), [cleanup record](docs/records/tasks/2026-10-15-kernel-cleanup.md) and [demo build](docs/development/demo-build.md). The Chinese README contains all 19 diagrams and detailed source links.
