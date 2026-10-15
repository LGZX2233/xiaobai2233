# Project Kernel Instructions

This is the independent Python kernel repository. Read [current state](docs/architecture/current-state.md) and the owning node in the [module tree](docs/modules/README.md) before changing runtime behavior. The parent DSH package documentation and pnpm commands are not this repository's runtime entry points.

Choose project guidance by the actual task and the current version's applicability in the [skill index](docs/records/skills/registry.json). Use [kernel-maintain-records](.agents/skills/kernel-maintain-records/SKILL.md) when project facts, module links or ongoing records need maintenance; use [kernel-grow-skills](.agents/skills/kernel-grow-skills/SKILL.md) when extracting, assessing or revising a reusable method. Follow current user instructions and existing authorization. New versions are trial guidance; evidence and counterexamples inform later revisions. These files do not enable Kernel runtime skill loading.

Update affected node metadata and owning records at work checkpoints. Organize user-facing prose around the reader's goal and link detailed reference records where useful; the [growth method](docs/architecture/skill-growth.md) can change with actual feedback. No background updater is installed.

Frozen `contracts/v1`, existing acceptance signatures, raw evidence, third-round materials and ZIPs remain historical inputs. New work needs its own requirements and verification records; never rewrite historical evidence to mark it accepted. Follow the user's current verification instructions and report only checks actually run.

Keep domain decisions, application orchestration and data/provider ownership clear. Reuse existing declarative rule revisions rather than adding executable plugin loading for documentation workflows. Descriptive learning records have no user score; unknown knowledge remains unknown.

Runtime implementations belong in `src/project_kernel/` and `bridge/protocol/`; tests, test hosts and test-only vectors belong in `tests/`. Preserve shared frozen fixtures and historical evidence in their existing owners. Do not commit bytecode or generated caches; see [repository layout](docs/development/repository-layout.md).
