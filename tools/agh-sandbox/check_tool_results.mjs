// Runs the plugin's agent tools directly (no AGH, no model) against a real kernel host and checks that
// every structured result is "bounded JSON data" by the same rules AGH applies
// (packages/protocol-validation/src/json-data.ts inspectJsonData): no undefined, no non-finite numbers,
// plain objects only. Usage:
//   PK_ROOT=/tmp/pk-check PK_PYTHON=<python> node check_tool_results.mjs <path-to-kernel_next>
// Exit code 1 when a tool result would be rejected by AGH.
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { tmpdir } from "node:os";

const repo = process.argv[2];
if (!repo) { console.error("usage: node check_tool_results.mjs <kernel_next dir>"); process.exit(2); }
const plugin = join(repo, "adapters", "agh-plugin");
const { createTools, resolveKernelPaths } = await import(pathToFileURL(join(plugin, "index.mjs")).href);
const { KernelSession } = await import(pathToFileURL(join(plugin, "kernel-session.mjs")).href);

const paths = resolveKernelPaths({ env: process.env, cwd: repo, pluginDir: plugin, platform: process.platform,
  exists: existsSync, tmp: tmpdir() });
if (paths.error) { console.error(paths.error); process.exit(2); }

// Same rules as AGH's inspectJsonData; returns the first offending path or null.
function jsonProblem(value, path = "$", depth = 0) {
  if (depth > 32) return `${path}: nesting exceeds 32`;
  if (value === null || ["string", "boolean"].includes(typeof value)) return null;
  if (typeof value === "number") return Number.isFinite(value) ? null : `${path}: non-finite number`;
  if (typeof value !== "object") return `${path}: unsupported ${typeof value}`;
  const proto = Object.getPrototypeOf(value);
  if (Array.isArray(value) ? proto !== Array.prototype : proto !== null && proto !== Object.prototype) return `${path}: non-plain object`;
  for (const [key, child] of Object.entries(value)) {
    const problem = jsonProblem(child, Array.isArray(value) ? `${path}[${key}]` : `${path}.${key}`, depth + 1);
    if (problem) return problem;
  }
  return null;
}

const session = new KernelSession(paths);
await session.start(async (root) => JSON.parse(await readFile(join(root, "demo-state.json"), "utf8")));
const tools = Object.fromEntries(createTools(async () => session).map((t) => [t.name, t]));
const steps = [["pk_state", {}], ["pk_run_strategy", { strategy_id: "s3" }], ["pk_run_strategy", { strategy_id: "s1" }],
  ["pk_run_strategy", { strategy_id: "s2" }], ["pk_verify", { strategy_id: "s1" }], ["pk_verify", { strategy_id: "s2" }],
  ["pk_compare", {}], ["pk_select", { strategy_id: "s2", reason: "check" }], ["pk_request_delivery", {}], ["pk_events", {}]];
let bad = 0;
for (const [name, args] of steps) {
  const result = await tools[name].execute(args);
  const problem = jsonProblem(result.structured);
  if (problem) bad += 1;
  console.log(`${name} ${JSON.stringify(args)} -> ${problem ? "AGH WOULD REJECT: " + problem : "json ok"}${result.isError ? " (tool error)" : ""}`);
}
await session.close();
process.exit(bad ? 1 : 0);
