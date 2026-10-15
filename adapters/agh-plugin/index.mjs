// AGH backend plugin: exposes the Project Kernel's machine channel as agent tools.
// Approval is deliberately not a tool: approval.decide is human-only in the kernel.
import { existsSync } from "node:fs";
import { mkdir, readdir, readFile, realpath, stat, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { KernelSession } from "./kernel-session.mjs";

const Kind = Symbol.for("TypeBox.Kind");
const str = (extra = {}) => ({ [Kind]: "String", type: "string", maxLength: 256, ...extra });
const obj = (properties, required = []) => ({
  [Kind]: "Object", type: "object", properties, required, additionalProperties: false,
});
const refSchema = () => ({ [Kind]: "Object", type: "object", additionalProperties: true });

const HOST_SCRIPT = ["tests", "p14_science_demo", "agh_host.py"];
export const ROOT_POINTER = "pk-agh-last-root.txt";

const pad = (n) => String(n).padStart(2, "0");
const stamp = (d) => `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-`
  + `${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;

/**
 * Decide where the kernel checkout, Python and the demo store live. Pure: every input is passed in.
 * AGH copies installed packages into its own package cache, so the plugin directory is only a
 * last resort; the daemon's cwd (the user starts AGH from the repo) or PK_KERNEL_ROOT come first.
 */
export function resolveKernelPaths({ env = {}, cwd = null, pluginDir = null, platform = "linux",
  exists = () => false, tmp, now = new Date() }) {
  const valid = (dir) => Boolean(dir) && exists(join(dir, ...HOST_SCRIPT)) && exists(join(dir, "src", "project_kernel"));
  const pluginRepo = pluginDir ? resolve(pluginDir, "..", "..") : null;
  let kernelRoot = null;
  let source = null;
  let error = null;
  if (env.PK_KERNEL_ROOT) {
    const dir = resolve(env.PK_KERNEL_ROOT);
    if (valid(dir)) [kernelRoot, source] = [dir, "PK_KERNEL_ROOT"];
    else error = `PK_KERNEL_ROOT=${dir} is not a Project Kernel checkout `
      + "(tests/p14_science_demo/agh_host.py or src/project_kernel is missing).";
  } else if (cwd && valid(resolve(cwd))) {
    [kernelRoot, source] = [resolve(cwd), "cwd"];
  } else if (valid(pluginRepo)) {
    [kernelRoot, source] = [pluginRepo, "plugin-dir"];
  } else {
    error = `Cannot find the Project Kernel checkout (checked cwd ${cwd ?? "?"} and ${pluginRepo ?? "?"}). `
      + "Set PK_KERNEL_ROOT to the kernel_next folder before starting AGH, e.g. "
      + "$env:PK_KERNEL_ROOT=\"D:\\deepseekhannes\\kernel_next\".";
  }
  const venvPython = kernelRoot && (platform === "win32"
    ? join(kernelRoot, ".venv", "Scripts", "python.exe") : join(kernelRoot, ".venv", "bin", "python"));
  const python = env.PK_PYTHON || (venvPython && exists(venvPython) ? venvPython : "python");
  const hostScript = env.PK_HOST_SCRIPT || (kernelRoot ? join(kernelRoot, ...HOST_SCRIPT) : null);
  if (env.PK_HOST_SCRIPT) error = null;
  const docsBase = kernelRoot ?? pluginRepo ?? ".";
  return {
    kernelRoot, source, error, python, hostScript,
    registry: env.PK_REGISTRY || join(docsBase, "docs", "modules", "registry.json"),
    skillsRegistry: env.PK_SKILLS_REGISTRY || join(docsBase, "docs", "records", "skills", "registry.json"),
    root: env.PK_ROOT || join(tmp, `pk-agh-demo-${stamp(now)}`),
    pointerFile: join(tmp, ROOT_POINTER),
  };
}

const here = fileURLToPath(new URL(".", import.meta.url));
const defaults = resolveKernelPaths({ env: process.env, cwd: process.cwd(), pluginDir: here,
  platform: process.platform, exists: existsSync, tmp: tmpdir() });

const meta = (overrides) => ({
  isReadOnly: false, isDestructive: false, isConcurrencySafe: false, isOpenWorld: false,
  replay: "never", costHint: undefined, deferLoading: false, requiresApproval: "never",
  ...overrides,
});
const readMeta = meta({ isReadOnly: true, isConcurrencySafe: true, replay: "safe" });

const done = (structured) => ({
  content: [{ type: "text", text: JSON.stringify(structured) }], structured,
});
const failed = (error) => {
  const structured = { error: error?.code ?? error?.name ?? "ERROR", message: String(error?.message ?? error) };
  return { content: [{ type: "text", text: JSON.stringify(structured) }], structured, isError: true };
};

export const WORKFLOW_GUIDE = "Workflow: (1) pk_state to inspect the task, strategies and environment; "
  + "(2) pk_run_strategy for each strategy s1, s2, s3 (s3 stalls and settles as unknown; that is expected and kept); "
  + "(3) pk_verify {strategy_id} for every completed strategy; a failed check is a real result, keep it; "
  + "(4) pk_compare; (5) pk_select {strategy_id, reason} for the strategy whose check passed; "
  + "(6) pk_request_delivery {} which opens a pending approval; (7) STOP and tell the user that a person must "
  + "approve it in a terminal (tools\\pk-human-approve.ps1); you cannot approve; "
  + "(8) after the user says it is approved, pk_apply_delivery {} and report the operation status.";

const HUMAN_HINT = "A person must approve in a terminal: powershell -File tools\\pk-human-approve.ps1 "
  + "(人工审批：在终端运行 tools\\pk-human-approve.ps1，输入快照摘要前 8 位确认). The agent cannot approve.";

const STRATEGY_IDS = ["s1", "s2", "s3"];
const STRATEGY_NOTES = { s1: "coarse grid search", s2: "golden-section search", s3: "stalling solver (failure sample)" };

// Per-session memory so the model can use short ids instead of copying ObjectRef JSON.
const memos = new WeakMap();
const memoOf = (session) => {
  if (!memos.has(session)) memos.set(session, { attempts: {}, candidates: {}, checks: {}, selection: null, approval: null });
  return memos.get(session);
};
const strategyOfAttempt = (memo, attemptId) =>
  Object.keys(memo.attempts).find((sid) => memo.attempts[sid].object_id === attemptId) ?? null;

export function createTools(getSession) {
  const guarded = (fn) => async (args = {}) => {
    try {
      return done(await fn(await getSession(), args));
    } catch (error) {
      return failed(error);
    }
  };
  const receiptOf = ({ receipt, recovered, requestId }) => ({
    status: receipt?.status ?? "unknown", operation_id: receipt?.operation_id ?? null,
    object_refs: receipt?.object_refs ?? [], error: receipt?.error ?? null,
    recovered: Boolean(recovered), request_id: requestId,
  });
  const kernelError = (error) => error ? { code: error.code ?? null, message: error.message ?? String(error) } : null;
  const compareData = (session) => session.query("attempts.compare", { task_ref: session.state.task_ref });
  const currentRef = async (session, attemptId) =>
    (await session.hostCall("host.attempt_ref", { attempt_id: attemptId })).attempt_ref;
  const attemptFor = (memo, { strategy_id, attempt_ref }) => {
    if (attempt_ref) return attempt_ref;
    if (!strategy_id) throw Object.assign(new Error("give strategy_id (s1, s2 or s3)"), { code: "INVALID_INPUT" });
    const ref = memo.attempts[strategy_id];
    if (!ref) throw Object.assign(new Error(`strategy ${strategy_id} has not been run yet; call pk_run_strategy first`),
      { code: "NOT_RUN" });
    return ref;
  };
  const strategyArg = str({ enum: STRATEGY_IDS, description: "s1, s2 or s3" });
  const legacyRef = (what) => ({ ...refSchema(), description: `optional full ObjectRef of the ${what}; normally omit` });

  return [
    {
      name: "pk_state",
      description: "Start here. Shows the task, the strategies s1/s2/s3, the environment check, the workflow guide and what has been done so far.",
      parameters: obj({}),
      meta: readMeta,
      execute: guarded(async (session) => {
        const memo = memoOf(session);
        const overview = await session.query("project.overview");
        let environment = null;
        try {
          const report = await session.query("environment.report", { task_ref: session.state.task_ref });
          const snap = report.snapshot ?? report;
          environment = { status: snap.status ?? report.data_state ?? null,
            facts: (snap.facts ?? []).map((f) => `${f.name} ${f.version ?? "?"} (${f.state})`) };
        } catch (error) { environment = { status: "unavailable", reason: String(error.message ?? error) }; }
        return {
          guide: WORKFLOW_GUIDE,
          pk_root: session.root,
          task_id: session.state.task_ref?.object_id ?? null,
          strategies: Object.keys(session.state.execution_roots).filter((k) => STRATEGY_IDS.includes(k))
            .map((id) => ({ strategy_id: id, method: STRATEGY_NOTES[id] ?? id,
              attempt_id: memo.attempts[id]?.object_id ?? null, check: memo.checks[id] ?? null })),
          environment,
          selected: memo.selection?.strategy_id ?? null,
          approval: memo.approval ? { approval_id: memo.approval.approval_id, status: memo.approval.status } : null,
          overview: { phases: overview.phases, blockers: overview.blockers, last_commit_seq: overview.last_commit_seq },
          task_ref: session.state.task_ref,
        };
      }),
    },
    {
      name: "pk_run_strategy",
      description: "Run one strategy as a new attempt: s1 coarse grid, s2 golden section, s3 stalls (settles as unknown and is never relaunched).",
      parameters: obj({ strategy_id: strategyArg, request_id: str() }, ["strategy_id"]),
      meta: meta({}),
      execute: guarded(async (session, { strategy_id, request_id }) => {
        const roots = session.state.execution_roots;
        if (!roots[strategy_id]) throw Object.assign(new Error(`unknown strategy ${strategy_id}`), { code: "INVALID_INPUT" });
        const started = await session.command("attempt.start", {
          packet_ref: session.state.packet_ref, strategy_id, execution_root_ref: roots[strategy_id],
        }, request_id);
        const attempt = started.receipt?.object_refs?.[0] ?? null;
        const status = attempt
          ? await session.query("operation.status", { operation_id: started.receipt.operation_id }) : null;
        if (attempt) memoOf(session).attempts[strategy_id] = attempt;
        const operation = status ? { status: status.status, attempt_id: status.attempt_id,
          strategy_id: status.strategy_id, exit_code: status.exit_code ?? null } : null;
        return {
          strategy_id, attempt_status: operation?.status ?? null, attempt_id: attempt?.object_id ?? null,
          receipt_status: started.receipt?.status ?? "unknown", error: kernelError(started.receipt?.error),
          note: operation?.status === "unknown" ? "kept as a failure sample; the kernel will not relaunch it" : null,
          operation, attempt_ref: attempt, request_id: started.requestId,
        };
      }),
    },
    {
      name: "pk_verify",
      description: "Run the independent check on one completed strategy's result (pass strategy_id). Returns passed true/false, the reason and alpha_fit. A strategy that settled as unknown (s3) has nothing to check: it returns skipped.",
      parameters: obj({ strategy_id: strategyArg, attempt_ref: legacyRef("attempt"), request_id: str() }),
      meta: meta({}),
      execute: guarded(async (session, { strategy_id, attempt_ref, request_id }) => {
        const memo = memoOf(session);
        const launched = attemptFor(memo, { strategy_id, attempt_ref });
        if (!launched?.object_id) throw Object.assign(new Error("attempt_ref needs object_id"), { code: "INVALID_INPUT" });
        // Verify the settled head revision: delivery binds the verification to the same revision selection uses.
        const attempt = await currentRef(session, launched.object_id);
        const sid = strategy_id ?? strategyOfAttempt(memo, attempt.object_id);
        // A stalled attempt settled as unknown has no result file: say so instead of surfacing a host error.
        const settled = (await compareData(session)).attempts?.find((a) => a.attempt_id === attempt.object_id);
        if (settled && settled.status !== "completed") {
          return { strategy_id: sid ?? settled.strategy_id ?? null, attempt_id: attempt.object_id, passed: false,
            verification_result: null, skipped: true, attempt_status: settled.status,
            reason: `attempt status is ${settled.status}: no result to verify; kept as a failure sample and never relaunched`,
            alpha_fit: null, receipt_status: "not_run", error: null };
        }
        const published = await session.hostCall("host.publish_candidate", { attempt_ref: attempt });
        const candidate = published.candidate_manifest_ref;
        const verified = await session.command("verification.run", {
          attempt_ref: attempt, candidate_manifest_ref: candidate, acceptance_refs: [session.state.acceptance_ref],
        }, request_id);
        const row = (await compareData(session)).attempts?.find((a) => a.attempt_id === attempt.object_id);
        const check = await session.hostCall("host.last_check", {});
        const result = row?.verification_result ?? null;
        const summary = { strategy_id: sid ?? row?.strategy_id ?? null, attempt_id: attempt.object_id,
          passed: verified.receipt?.status !== "rejected" && result === "passed",
          verification_result: result, reason: check.reason || null,
          method: published.summary?.method ?? null, alpha_fit: published.summary?.alpha_fit ?? null,
          elapsed_s: published.summary?.elapsed_s ?? null };
        if (summary.strategy_id) {
          memo.candidates[summary.strategy_id] = candidate;
          memo.checks[summary.strategy_id] = { passed: summary.passed, reason: summary.reason, alpha_fit: summary.alpha_fit };
        }
        return { ...summary, receipt_status: verified.receipt?.status ?? "unknown",
          error: kernelError(verified.receipt?.error), candidate_id: candidate.object_id,
          status: verified.receipt?.status ?? "unknown", candidate_manifest_ref: candidate };
      }),
    },
    {
      name: "pk_compare",
      description: "Compare every attempt of the task: strategy, status, check result; failed and unknown attempts stay listed.",
      parameters: obj({}),
      meta: readMeta,
      execute: guarded(async (session) => {
        const memo = memoOf(session);
        const data = await compareData(session);
        const attempts = (data.attempts ?? []).map((a) => ({ strategy_id: a.strategy_id, attempt_id: a.attempt_id,
          status: a.status, exit_code: a.exit_code ?? null, verification_result: a.verification_result ?? null,
          alpha_fit: memo.checks[a.strategy_id]?.alpha_fit ?? null, reason: memo.checks[a.strategy_id]?.reason ?? null }));
        const failures = (data.failures_retained ?? []).map((id) => ({ attempt_id: id,
          strategy_id: strategyOfAttempt(memo, id), status: "unknown (retained, not relaunched)" }));
        return { attempts, failures_retained: data.failures_retained ?? [], failures, comparability: data.comparability ?? null,
          selected: data.selected ?? null, cost_note: "usage not reported by the solver; cost is unknown, not zero" };
      }),
    },
    {
      name: "pk_select",
      description: "Choose the strategy to deliver (pass strategy_id and a one-sentence reason). All other attempts are kept for comparison automatically.",
      parameters: obj({ strategy_id: strategyArg, reason: str({ description: "why this strategy is chosen" }),
        attempt_ref: legacyRef("chosen attempt"),
        comparison_refs: { [Kind]: "Array", type: "array", items: refSchema(), maxItems: 16,
          description: "optional; defaults to all attempts of the task" },
        request_id: str() }, ["reason"]),
      meta: meta({}),
      execute: guarded(async (session, { strategy_id, attempt_ref, comparison_refs, reason, request_id }) => {
        const memo = memoOf(session);
        const chosen = attemptFor(memo, { strategy_id, attempt_ref });
        let comparisons = comparison_refs;
        if (!comparisons?.length) {
          const data = await compareData(session);
          const ids = [...new Set([...(data.attempts ?? []).map((a) => a.attempt_id), ...(data.failures_retained ?? [])])];
          comparisons = await Promise.all(ids.map((id) => currentRef(session, id)));
        }
        // Selection needs the settled head revision, not the revision returned at launch.
        const head = await currentRef(session, chosen.object_id);
        const selected = await session.command("attempt.select", {
          attempt_ref: head, comparison_refs: comparisons, purpose: "delivery", reason,
        }, request_id);
        const sid = strategy_id ?? strategyOfAttempt(memo, chosen.object_id);
        if (selected.receipt?.status !== "rejected") {
          memo.selection = { strategy_id: sid, attempt_id: chosen.object_id, selection_ref: selected.receipt.object_refs[0] };
        }
        return { strategy_id: sid, attempt_id: chosen.object_id, compared_attempts: comparisons.length, reason,
          selection_id: selected.receipt?.object_refs?.[0]?.object_id ?? null, ...receiptOf(selected) };
      }),
    },
    {
      name: "pk_request_delivery",
      description: "Request delivery of the selected strategy (no arguments needed). Opens a pending approval that only a human can decide; then stop and wait.",
      parameters: obj({ selection_ref: legacyRef("selection"), candidate_ref: legacyRef("candidate"), request_id: str() }),
      meta: meta({ requiresApproval: "always" }),
      execute: guarded(async (session, { selection_ref, candidate_ref, request_id }) => {
        const memo = memoOf(session);
        const selection = selection_ref ?? memo.selection?.selection_ref;
        const sid = memo.selection?.strategy_id ?? null;
        const candidate = candidate_ref ?? (sid ? memo.candidates[sid] : null);
        if (!selection) throw Object.assign(new Error("nothing selected yet; call pk_select first"), { code: "NOT_SELECTED" });
        if (!candidate) throw Object.assign(new Error(`no verified candidate for ${sid}; call pk_verify first`), { code: "NOT_VERIFIED" });
        const requested = await session.command("delivery.request", {
          selection_ref: selection, candidate_ref: candidate, target_ref: session.state.target_ref,
        }, request_id);
        const out = { strategy_id: sid, ...receiptOf(requested) };
        const approvalRef = requested.receipt?.object_refs?.find((r) => r.object_type === "approval");
        if (approvalRef) {
          const queue = await session.query("approvals.queue", {});
          const entry = queue.queue?.find((e) => e.approval_id === approvalRef.object_id);
          memo.approval = { approval_id: approvalRef.object_id, snapshot_digest: entry?.snapshot_digest ?? null,
            status: entry?.status ?? null };
          Object.assign(out, { approval_id: approvalRef.object_id, approval_status: entry?.status ?? null,
            snapshot_digest: entry?.snapshot_digest ?? null, next: `Stop here and wait. ${HUMAN_HINT}` });
        }
        return out;
      }),
    },
    {
      name: "pk_apply_delivery",
      description: "After a person has approved in the terminal, apply the delivery (no arguments needed). If it is not approved yet the kernel refuses and you must wait.",
      parameters: obj({ approval_id: str({ description: "optional; defaults to this session's request" }), request_id: str() }),
      meta: meta({}),
      execute: guarded(async (session, { approval_id, request_id }) => {
        const memo = memoOf(session);
        const id = approval_id ?? memo.approval?.approval_id;
        if (!id) throw Object.assign(new Error("no delivery request in this session; call pk_request_delivery first"),
          { code: "NOT_REQUESTED" });
        const queue = await session.query("approvals.queue", {});
        const entry = queue.queue?.find((e) => e.approval_id === id);
        if (!entry) throw Object.assign(new Error(`approval ${id} not found`), { code: "NOT_FOUND" });
        if (memo.approval?.approval_id === id) memo.approval.status = entry.status;
        let applied;
        try {
          applied = await session.command("delivery.apply", { approval_id: id, snapshot_digest: entry.snapshot_digest }, request_id);
        } catch (error) {
          return { applied: false, approval_id: id, approval_status: entry.status,
            kernel_error: { code: error.code ?? "ERROR", message: String(error.message ?? error) },
            hint: entry.status === "pending" ? HUMAN_HINT : undefined };
        }
        if (applied.receipt?.status === "rejected") {
          return { applied: false, approval_id: id, approval_status: entry.status, receipt_status: "rejected",
            kernel_error: kernelError(applied.receipt.error),
            hint: entry.status === "pending" ? `Not approved yet. ${HUMAN_HINT}` : undefined };
        }
        const op = await session.query("operation.status", { operation_id: applied.receipt.operation_id });
        return { applied: op?.status === "applied", approval_id: id, approval_status: entry.status,
          operation_id: applied.receipt.operation_id, operation_status: op?.status ?? null,
          strategy_id: memo.selection?.strategy_id ?? null, receipt_status: applied.receipt.status };
      }),
    },
    {
      name: "pk_events",
      description: "Read the audit trail: committed kernel events in order (command bookkeeping is counted, not listed).",
      parameters: obj({ commit_seq: str(), event_index: { [Kind]: "Integer", type: "integer", minimum: 0 } }),
      meta: readMeta,
      execute: guarded(async (session, { commit_seq = "0", event_index = 0 }) => {
        const events = await session.query("events.read", { after: { commit_seq, event_index }, limit: 1000 });
        const meaningful = events.filter((e) => e.event_type !== "command.committed");
        const last = events.at(-1);
        return { count: events.length, command_commits: events.length - meaningful.length,
          events: meaningful.map((e) => `${e.commit_seq}:${e.event_type}`),
          next_cursor: last ? { commit_seq: last.commit_seq, event_index: last.event_index } : { commit_seq, event_index } };
      }),
    },
  ];
}

const identifier = { type: "string", minLength: 1, maxLength: 128,
  pattern: "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$" };
const sequence = { type: "string", pattern: "^(0|[1-9][0-9]*)$" };
const objectReference = { type: "object", additionalProperties: false,
  properties: { project_id: identifier, object_type: identifier, object_id: identifier, revision_id: identifier },
  required: ["project_id", "object_type", "object_id", "revision_id"] };
const metadataSchema = { type: "object", additionalProperties: true, properties: {
  as_of_seq: { type: ["string", "null"] }, freshness: { type: ["object", "null"] },
  completeness: { type: "string", enum: ["complete", "incomplete", "unknown"] },
  gaps: { type: "array" }, required_missing: { type: "array" },
  next_page_token: { type: ["string", "null"] },
}, required: ["as_of_seq", "freshness", "completeness", "gaps", "required_missing", "next_page_token"] };

// Handlers are also called outside AGH in adapter tests; validate at this JSON entry point.
function validateInput(value, schema, path = "input") {
  const invalid = () => { throw Object.assign(new Error(`invalid ${path}`), { code: "INVALID_INPUT" }); };
  if (schema.type === "object") {
    if (!value || typeof value !== "object" || Array.isArray(value)) invalid();
    for (const key of schema.required ?? []) if (!Object.hasOwn(value, key)) invalid();
    for (const [key, child] of Object.entries(value)) {
      if (!Object.hasOwn(schema.properties, key)) invalid();
      const definition = schema.properties[key];
      validateInput(child, definition, `${path}.${key}`);
    }
  } else if (schema.type === "string") {
    if (typeof value !== "string" || value.length < (schema.minLength ?? 0)
      || value.length > (schema.maxLength ?? Infinity)
      || (schema.pattern && !new RegExp(schema.pattern).test(value))) invalid();
  } else if (schema.type === "integer") {
    if (!Number.isSafeInteger(value) || value < (schema.minimum ?? -Infinity)
      || value > (schema.maximum ?? Infinity)) invalid();
  }
  if (schema.enum && !schema.enum.includes(value)) invalid();
}

async function readRegistry(path, origin, collection) {
  let text;
  try {
    text = await readFile(path, "utf8");
  } catch (error) {
    throw Object.assign(new Error(`Cannot read ${origin}: ${error.message}`), { code: "DOCUMENT_READ_FAILED" });
  }
  let raw;
  try {
    raw = JSON.parse(text);
  } catch (error) {
    throw Object.assign(new Error(`Invalid JSON in ${origin}: ${error.message}`), { code: "DOCUMENT_PARSE_FAILED" });
  }
  const id = collection === "nodes" ? "node_id" : "skill_id";
  if (!raw || typeof raw !== "object" || !Array.isArray(raw[collection])
    || raw[collection].some((item) => !item || typeof item[id] !== "string"
      || (collection === "skills" && !Array.isArray(item.versions)))) {
    throw Object.assign(new Error(`Invalid ${collection} registry in ${origin}`), { code: "DOCUMENT_INVALID_REGISTRY" });
  }
  return { meta: { origin, origin_kind: "documentation", as_of_seq: null, freshness: null,
    completeness: "unknown", gaps: [], required_missing: [], next_page_token: null,
    document_version: raw.document_version ?? null, updated_at: raw.updated_at ?? null,
    source_revision: raw.source_revision ?? null }, data: raw };
}

const RECORD_KINDS = [["docs/handoffs/", "handoffs"], ["docs/requirements/", "requirements"],
  ["docs/records/tasks/", "tasks"], ["docs/acceptance/", "acceptance"], ["docs/reviews/", "reviews"],
  ["docs/architecture/", "architecture"]];
const FACT_KEYS = new Set(["document_version", "updated_at", "implementation_status", "source_revision"]);

function normalizePosix(parts) {
  const out = [];
  for (const part of parts.join("/").split("/")) {
    if (part === "..") out.pop();
    else if (part && part !== ".") out.push(part);
  }
  return out.join("/");
}

/** Facts a module document states about itself; nothing here is inferred. */
export function parseModuleFacts(text, document, exists) {
  const meta = {};
  for (const line of text.split(/\r?\n/)) {
    const row = /^\|\s*`?([a-z_]+)`?\s*\|\s*(.+?)\s*\|\s*$/.exec(line);
    if (row && FACT_KEYS.has(row[1]) && !(row[1] in meta)) meta[row[1]] = row[2].replace(/^[`\s]+|[`\s]+$/g, "");
  }
  const linked = {};
  for (const [, target] of text.matchAll(/\[[^\]]+\]\(([^)#\s]+)(?:#[^)]*)?\)/g)) {
    if (/^[a-z]+:/i.test(target)) continue;
    const path = normalizePosix(["docs/modules", document.split("/").slice(0, -1).join("/"), target]);
    const kind = RECORD_KINDS.find(([prefix]) => path.startsWith(prefix));
    if (kind && exists(path) && !(linked[kind[1]] ??= []).includes(path)) linked[kind[1]].push(path);
  }
  for (const list of Object.values(linked)) list.sort();
  const heading = /^#\s+(.+)$/m.exec(text)?.[1]?.replace(/^K-[A-Z]+\s*[:：]\s*/, "").trim();
  return {
    title: heading || null,
    document_version: meta.document_version ?? null,
    updated_at: /\d{4}-\d{2}-\d{2}/.exec(meta.updated_at ?? "")?.[0] ?? null,
    implementation_status: meta.implementation_status ?? null,
    source_revision: meta.source_revision ? meta.source_revision.slice(0, 12) : null,
    requirement_ids: [...new Set(text.match(/REQ-[A-Z]+-\d+/g) ?? [])].sort(),
    linked_records: linked,
  };
}

async function attachModuleFacts(registry, registryPath) {
  const modulesDir = dirname(registryPath);
  const repoRoot = resolve(modulesDir, "../..");
  const present = new Set();
  await Promise.all(registry.data.nodes.map(async (node) => {
    if (typeof node.document !== "string") return;
    let text;
    try { text = await readFile(join(modulesDir, node.document), "utf8"); } catch { node.facts = null; return; }
    const links = [...text.matchAll(/\[[^\]]+\]\(([^)#\s]+)(?:#[^)]*)?\)/g)].map((m) => m[1]);
    await Promise.all(links.filter((target) => !/^[a-z]+:/i.test(target)).map(async (target) => {
      const path = normalizePosix(["docs/modules", node.document.split("/").slice(0, -1).join("/"), target]);
      try { if ((await stat(join(repoRoot, path))).isFile()) present.add(path); } catch { /* absent links are dropped */ }
    }));
    node.facts = parseModuleFacts(text, node.document, (path) => present.has(path));
  }));
  registry.meta.facts_origin = "node documents";
  return registry;
}

const DOCUMENT_PATH = "^(docs/[A-Za-z0-9._/-]{1,240}\\.md|DELIVERY_PLAN\\.md)$";
const DOCUMENT_ROOTS = ["docs/handoffs/", "docs/requirements/", "docs/records/", "docs/architecture/",
  "docs/acceptance/", "docs/reviews/", "docs/plans/", "docs/modules/", "docs/frontend/"];
// Root-level planning files the panel may show; everything else at the root stays unreadable.
const ROOT_DOCUMENTS = new Set(["DELIVERY_PLAN.md"]);
const DOCUMENT_LIMIT = 96 * 1024;
const SECRET_ASSIGNMENT = /\b([A-Z0-9_]*(?:API_KEY|SECRET|TOKEN|PASSWORD)[A-Z0-9_]*)(\s*[=:]\s*)\S+/g;

/** Mask credential-shaped assignments; documents must never carry key material into the browser. */
export function redactSecrets(text) {
  return text.replace(SECRET_ASSIGNMENT, (_match, key, sepr) => `${key}${sepr}[已隐藏]`);
}

/** Repo paths a document mentions in backticks or links; existence is checked, not assumed. */
export function documentReferences(text, documentPath) {
  const found = new Set();
  const base = documentPath.split("/").slice(0, -1).join("/");
  for (const [, target] of text.matchAll(/\[[^\]]*\]\(([^)#\s]+)(?:#[^)]*)?\)/g)) {
    if (!/^[a-z]+:/i.test(target)) found.add(normalizePosix([base, target]));
  }
  for (const [, raw] of text.matchAll(/`([A-Za-z0-9_.\-/]+\/[A-Za-z0-9_.\-/]*[A-Za-z0-9_\-]\.[a-z]{1,5})`/g)) {
    if (!raw.startsWith("/") && !raw.includes("..")) found.add(normalizePosix([raw]));
  }
  return [...found].filter((path) => path && !path.startsWith("..")).sort();
}

const DOCUMENT_INDEX_LIMIT = 2000;

/** List readable documents with their first heading; the list is what exists on disk now. */
async function listDocuments(registryPath) {
  const repoRoot = resolve(dirname(registryPath), "../..");
  const found = [];
  const walk = async (relative) => {
    let entries;
    try { entries = await readdir(join(repoRoot, relative), { withFileTypes: true }); } catch { return; }
    for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
      const path = `${relative}/${entry.name}`;
      if (entry.isDirectory()) await walk(path);
      else if (entry.isFile() && entry.name.endsWith(".md") && DOCUMENT_ROOTS.some((prefix) => path.startsWith(prefix))
        && new RegExp(DOCUMENT_PATH).test(path)) found.push(path);
      if (found.length >= DOCUMENT_INDEX_LIMIT) return;
    }
  };
  await walk("docs");
  for (const name of ROOT_DOCUMENTS) {
    try { if ((await stat(join(repoRoot, name))).isFile()) found.unshift(name); } catch { /* absent root files are skipped */ }
  }
  const documents = await Promise.all(found.map(async (path) => {
    let title = null;
    try { title = /^#\s+(.+)$/m.exec((await readFile(join(repoRoot, path), "utf8")).slice(0, 4096))?.[1]?.trim() ?? null; } catch { /* unreadable */ }
    const category = ROOT_DOCUMENTS.has(path) ? "plans" : path.split("/")[1];
    return { path, title, category };
  }));
  return { meta: { origin: "docs/", origin_kind: "documentation", as_of_seq: null, freshness: null,
    completeness: found.length >= DOCUMENT_INDEX_LIMIT ? "incomplete" : "unknown",
    gaps: found.length >= DOCUMENT_INDEX_LIMIT ? ["document_index_truncated"] : [], required_missing: [],
    next_page_token: null }, data: { documents, count: documents.length } };
}

/** Read one project document under docs/ (or an allowed root plan file); never anything else. */
async function readDocument(registryPath, path) {
  const denied = (message, code = "DOCUMENT_NOT_ALLOWED") => Object.assign(new Error(message), { code });
  const rootFile = ROOT_DOCUMENTS.has(path);
  if (path.split("/").some((part) => part === "" || part === "." || part === "..")
    || (!rootFile && !DOCUMENT_ROOTS.some((prefix) => path.startsWith(prefix)))) {
    throw denied(`Document path is not readable: ${path}`);
  }
  const repoRoot = resolve(dirname(registryPath), "../..");
  let real;
  let allowedRoot;
  try {
    [real, allowedRoot] = await Promise.all([realpath(resolve(repoRoot, path)),
      realpath(rootFile ? repoRoot : join(repoRoot, "docs"))]);
  } catch (error) {
    throw denied(`Cannot read ${path}: ${error.message}`, "DOCUMENT_READ_FAILED");
  }
  if (rootFile ? dirname(real) !== allowedRoot : !real.startsWith(allowedRoot + sep)) {
    throw denied(`Document resolves outside its allowed root: ${path}`);
  }
  const bytes = await readFile(real);
  const truncated = bytes.length > DOCUMENT_LIMIT;
  const text = redactSecrets(bytes.subarray(0, DOCUMENT_LIMIT).toString("utf8").replace(/�$/, ""));
  const references = await Promise.all(documentReferences(text, path).map(async (ref) => {
    try { return { path: ref, exists: (await stat(join(repoRoot, ref))).isFile() }; } catch { return { path: ref, exists: false }; }
  }));
  return { meta: { origin: path, origin_kind: "documentation", as_of_seq: null, freshness: null,
    completeness: truncated ? "incomplete" : "unknown", gaps: truncated ? ["document_truncated"] : [],
    required_missing: [], next_page_token: null, bytes: bytes.length, truncated },
  data: { path, title: /^#\s+(.+)$/m.exec(text)?.[1]?.trim() ?? null, text, references } };
}

/** Build the browser's read-only services; document reads do not start a Python host. */
export function createServices(getSession, paths = defaults) {
  const output = (data) => ({ type: "object", additionalProperties: false,
    properties: { meta: metadataSchema, data }, required: ["meta", "data"] });
  const objectData = { type: "object", additionalProperties: true };
  const definition = (name, run, properties = {}, required = [], data = objectData) => {
    const inputSchema = { type: "object", properties, required, additionalProperties: false };
    return { name, kind: "query", timeoutMs: 10000, maxResultBytes: 262144,
      inputSchema, outputSchema: output(data), handler: async (input = {}) => {
        validateInput(input, inputSchema);
        return run(input);
      } };
  };
  const query = (name, kernelQuery, payload, properties = {}, required = [], data = objectData) =>
    definition(name, async (input) => {
      const session = await getSession();
      const envelope = await session.queryEnvelope(kernelQuery, payload(session, input),
        input.as_of_seq, input.page_token);
      if (!envelope || typeof envelope !== "object" || !("data" in envelope)
        || (kernelQuery === "events.read" && !Array.isArray(envelope.data))) {
        throw Object.assign(new Error(`Invalid envelope for ${kernelQuery}`), { code: "INVALID_RESPONSE" });
      }
      const { data, ...meta } = envelope;
      return { meta, data };
    }, { as_of_seq: sequence, ...properties }, required, data);
  const page = { page_token: { type: "string", minLength: 1, maxLength: 8192 } };
  return [
    query("pk.compare", "attempts.compare", (s) => ({ task_ref: s.state.task_ref })),
    query("pk.overview", "project.overview", () => ({})),
    query("pk.approvals", "approvals.queue", (_s, i) => i.status ? { status: i.status } : {},
      { ...page, status: { type: "string", enum: ["pending", "approved", "rejected", "expired", "superseded", "revoked"] } }),
    query("pk.events", "events.read", (_s, i) => ({
      after: { commit_seq: i.commit_seq ?? "0", event_index: i.event_index ?? 0 }, limit: i.limit ?? 100,
    }), { commit_seq: sequence, event_index: { type: "integer", minimum: 0 },
      limit: { type: "integer", minimum: 1, maximum: 1000 } }, [], { type: "array", items: objectData }),
    query("pk.timeline", "project.timeline", (_s, i) => i.object_type ? { object_type: i.object_type } : {},
      { ...page, object_type: identifier }),
    query("pk.trace", "project.trace", (s, i) => ({ root_ref: i.root_ref ?? s.state.task_ref,
      direction: i.direction ?? "both", max_depth: i.max_depth ?? 3 }), {
      root_ref: objectReference, direction: { type: "string", enum: ["incoming", "outgoing", "both"] },
      max_depth: { type: "integer", minimum: 1, maximum: 20 },
    }),
    query("pk.coverage", "requirements.coverage", () => ({})),
    query("pk.environment", "environment.report", (s) => ({ task_ref: s.state.task_ref })),
    query("pk.operation", "operation.status", (_s, i) => ({ operation_id: i.operation_id }),
      { operation_id: identifier }, ["operation_id"]),
    definition("pk.tree", async () => attachModuleFacts(
      await readRegistry(paths.registry, "docs/modules/registry.json", "nodes"), paths.registry)),
    definition("pk.skills", () => readRegistry(paths.skillsRegistry, "docs/records/skills/registry.json", "skills")),
    definition("pk.documents", () => listDocuments(paths.registry)),
    definition("pk.document", (input) => readDocument(paths.registry, input.path),
      { path: { type: "string", minLength: 1, pattern: DOCUMENT_PATH } }, ["path"],
      { type: "object", additionalProperties: false, properties: { path: { type: "string" },
        title: { type: ["string", "null"] }, text: { type: "string" }, references: { type: "array" } } }),
  ];
}

export const kernelPlugin = {
  inject: ["extension"],
  apply(ctx) {
    const agnes = ctx.extension();
    let session = null;
    let pendingSession = null;
    let starting = null;
    let disposed = false;
    const getSession = async () => {
      if (disposed) throw new Error("kernel plugin is disposed");
      if (session) return session;
      if (!starting) starting = (async () => {
        if (!defaults.hostScript) {
          throw Object.assign(new Error(defaults.error), { code: "KERNEL_NOT_FOUND" });
        }
        // Start the host first (it creates its own root); concurrent callers share this one startup.
        const next = new KernelSession(defaults);
        pendingSession = next;
        const started = next.start(async (root) => JSON.parse(await readFile(join(root, "demo-state.json"), "utf8")));
        try {
          await started;
          // Lets the human approval CLI find this run's store without copying paths around.
          try {
            await mkdir(dirname(defaults.pointerFile), { recursive: true });
            await writeFile(defaults.pointerFile, defaults.root, "utf8");
          } catch { /* pointer is a convenience */ }
          if (disposed) {
            await next.close();
            throw new Error("kernel plugin disposed during startup");
          }
          session = next;
          return session;
        } finally {
          if (pendingSession === next) pendingSession = null;
          starting = null;
        }
      })();
      return starting;
    };
    for (const tool of createTools(getSession)) ctx.effect(() => agnes.registerTool(tool));
    // Read-only query services for the browser panel; needs `services` in the capability ceiling.
    if (ctx.services?.register) {
      for (const service of createServices(getSession)) ctx.effect(() => ctx.services.register(service));
    }
    ctx.effect(() => async () => {
      disposed = true;
      await (session ?? pendingSession)?.close();
      if (starting) {
        try { await starting; } catch (error) { /* Startup failure already closes its child. */ }
      }
    });
  },
};
