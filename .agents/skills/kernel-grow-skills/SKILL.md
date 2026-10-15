---
name: kernel-grow-skills
description: Extract, assess or revise a reusable Project Kernel agent method from actual task evidence or user feedback, including technical workflows and user-facing document methods. Use when reuse or a demonstrated failure warrants maintained guidance, not for every completed task.
metadata:
  skill-version: "1.1.0"
---

# Kernel Grow Skills

This skill maintains project-local agent guidance. Resolve the repository root three directories above this file. Read [skill growth](../../../docs/architecture/skill-growth.md) and the relevant entry in [the registry](../../../docs/records/skills/registry.json) when using it. Version 1.1.0 is trial and not behaviorally validated; the files do not enable Kernel runtime skill loading, scoring or knowledge promotion.

## Decide Whether A Skill Helps

Extract a method when actual repeated work shows a reusable decision or resource that reduces work, or when the user explicitly requests a reusable method and a concrete use case establishes its intended scope. A successful task alone does not establish that its steps caused success. Keep task facts in their owning records; avoid a skill for one-off findings, generic advice, uncertain personal traits or a method whose maintenance costs outweigh its expected reuse. A draft can remain a candidate until its assumptions are clear.

State the intended task and reader, prerequisites, exclusions, known counterexamples and factors that make the method stale. Put a concise selection condition in the description. Keep essential decisions in `SKILL.md`; add supporting files only when a concrete task needs them. For document methods, organize the result around what the reader wants to understand or do. Evidence tables or handoff sections belong only where they serve that goal.

## Reuse And Observe

Before each reuse, confirm that the task fits the recorded scope, prerequisites and version. Read only the necessary guidance and honor current user instructions. If the task falls outside the scope, use an appropriate method and record the mismatch only when it helps prevent repeated misapplication; do not force the task into this skill.

After actual reuse, create a short [assessment record](../../../docs/records/skills/assessment-template.md) with the request, method version, source evidence, observed result and uncertainties. Rate the method's correctness, applicability, reuse benefit and maintainability separately using the definitions in the growth guide; maintainability includes reading and maintenance costs. Missing evidence is `null`; no invented scores, universal average or user ranking. Record successful observations critically: note plausible alternative causes and what the observation cannot establish.

## Assessment Scope And Failure Analysis

Assess one actual use of one skill version under its recorded request, prerequisites, source versions and observation limits. Do not combine scores across versions or scenarios by default. An environment or provider error does not by itself justify correctness=0; assess the method's handling of the observed failure. This documentation interface belongs to data processing: its output cannot route execution, retry a provider, approve delivery, assign user scores, supply training rewards or trigger knowledge promotion. Knowledge ScoreEngine feedback is separate.

After a failed use or an associated tool failure, distinguish method failure from tool/provider failure and static findings. Record expected/actual results, versions and scope fit, the failed stage and actual timeline, source errors and receipt/operation evidence, candidate causes with supporting and contrary evidence, confirmed causes or missing evidence, impact and external-effect uncertainty, corrections and verification status. Link the owning task record instead of duplicating logs. Summarize the symptom/stage, confirmed and unresolved causes, impact, correction and actual recheck result. Complete analysis covers those questions; it does not invent a definite cause. For unresolved causes, state the next observation that could distinguish them. Check existing authorization and effect state before any retry; an assessment does not authorize replaying an unknown external write.

## Review And Revise

A material counterexample or a low dimension rating opens `review_required` with a concrete question and review reference. Distinguish a method defect, excessive scope, stale assumptions and caller misuse before choosing a correction. If following the version can produce a harmful or materially incorrect result, suspend that version pending review. One successful reuse cannot cancel an unresolved correctness failure.

Make the smallest supported correction: change the method, narrow its scope, update stale references, improve selection guidance or retire it if upkeep is not justified. Record the old version, evidence, reason, changes and remaining uncertainty. Set the new local version to `trial` / `not_validated`, and observe it again in the relevant authorized scenario; editing the instructions is not evidence of improvement. Link later observations and make a scoped review decision before marking it active. Corrections and withdrawals remain possible.

## Authorization

Assessment and ordinary local record maintenance proceed within existing task authorization. A skill never authorizes external writes, publication, pushing, important data deletion or extra behavioral verification. Check the current user's approval and conditions; if the action is already explicitly covered, do not ask again. Otherwise prepare the concrete result for review and request approval at the final execution step. Do not bypass a user's no-test instruction to validate a skill.
