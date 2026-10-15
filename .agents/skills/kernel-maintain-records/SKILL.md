---
name: kernel-maintain-records
description: Update Project Kernel module links and current task/project or learning records when project facts change, and select the relevant owning records. Use for record maintenance in this repository, not as a default template for every user-facing document.
metadata:
  skill-version: "2.0.0"
---

# Kernel Maintain Records

Resolve repository paths from this skill's location, three directories up. Use [the module tree](../../../docs/modules/README.md) to select the affected node before loading broad project history. [Relationship rules](../../../docs/modules/relationships.md) define stable IDs, metadata and relation direction.

## When To Use

Use this skill when a task changes project facts, module responsibility or links, or when the user requests task/project or learning-record maintenance. Read the owning facts and the current task authorization before editing. A one-off explanation, isolated copy edit or unrelated repository task does not require a new record or a full maintenance pass. User-facing documents follow the reader's goal; a handoff checklist is useful only when the reader needs to continue work.

Version 2.0.0 is a trial revision. Its scope, the prior user feedback and pending observations are indexed in [the skill registry](../../../docs/records/skills/registry.json). For each actual reuse, apply the evidence and review procedure in [skill growth](../../../docs/architecture/skill-growth.md); assess the method, never the user's ability. Changed source facts, broken links, a different repository or a different audience can invalidate this method's assumptions.

## Select Context

Read the target node, relevant source symbols, original requirements and specific acceptance conditions. Select direct dependencies needed for the task; expand only with a stated reason. Record selected paths/versions and material gaps in the task record using [the context guide](../../../docs/modules/context-selection.md). Conversation associations are empty in the current tree; do not invent IDs or fetch other chats merely because a node could be associated with one.

## Maintain Records

At meaningful checkpoints and task completion, update affected node responsibility/links, document version, date and source revision when those facts change. Keep `registry.json` consistent with node `navigation_parent`, `depends_on` and `related_to`. A new source commit does not grant acceptance to a new feature; historical AC decisions stay linked to their original files.

Record the task's goal, requirement IDs, affected nodes, choices, actual result, errors with causes/fixes, remaining work and checks actually performed in `docs/records/tasks/`. Update [the project summary](../../../docs/records/project-summary.md) with links to owning facts rather than duplicating evidence. Use [the records architecture](../../../docs/architecture/continuous-records.md) for correction, withdrawal and deletion.

For reusable terms or errors, update [terms and errors](../../../docs/records/terms-and-errors.md). Add targeted learning material only when requested or supported by an actual learning need; clearly distinguish a static code finding from a reproduced failure. Use [kernel-grow-skills](../kernel-grow-skills/SKILL.md) when extracting or revising a reusable method; task facts and personal profile content stay in records.

## Learning Profile

Use [the learning profile](../../../docs/records/user-learning-profile.md) only for relevant conversation or technical-route decisions. User statements and model hypotheses remain separate, dated and source-linked. Prefer descriptive states such as familiar concepts, independently used tools, needs examples or currently learning. Unknown topics stay unknown. A question or single error does not establish the user's knowledge level. Do not assign numerical scores, ranks or fixed ability labels.

Correct or remove a record when the user corrects it. Avoid personal information unrelated to the work, keep profile content project-local and do not feed it into corpus exports or training. User-authorized deletion removes current readable records; existing Git history is a separate concern and must not be claimed erased by editing Markdown.

## Rules And Limits

Use [the existing rule workflow](../../../docs/architecture/pluggable-rules.md) for configuration changes. Declarative rules can add restrictions and warnings but cannot override project scope, trusted human authorization, immutable references or evidence requirements. A skill guides an agent; it is not a Kernel enforcement mechanism or permission to push, release or run external operations.

Routine record updates within the user's authorized task do not require repeated confirmation. Before an important action such as publication, pushing or deletion of important data, check whether the user's existing explicit approval covers that action and its conditions. When approval is missing, prepare the reviewable result first and obtain user approval before executing the action. The skill cannot grant that approval or widen existing authorization.

Honor the user's current verification scope. For documentation work, inspect links, metadata, relation consistency and Git diff. Do not describe planned tests or old accepted evidence as checks performed during the present task. No automatic event listener, frontend or new database is implied by maintaining these records.
