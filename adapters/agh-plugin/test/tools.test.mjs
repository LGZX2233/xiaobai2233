// Drives the plugin's tools against the real Python demo host over stdio: the whole loop with short args.
import test from "node:test";
import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import { KernelSession } from "../kernel-session.mjs";
import { createTools, resolveKernelPaths } from "../index.mjs";

const run = promisify(execFile);
const repo = resolve(fileURLToPath(new URL("../../../", import.meta.url)));
const python = process.env.PK_PYTHON ?? join(repo, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const hostScript = process.env.PK_HOST_SCRIPT ?? join(repo, "tests", "p14_science_demo", "agh_host.py");

// The person's decision, made outside the agent through the Python CLI's non-interactive core.
const humanDecide = (root, approvalId, prefix, decision, reason) => run(python, ["-I", "-B", "-c",
  "import importlib.util,json,sys\n"
  + "s=importlib.util.spec_from_file_location('a',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\n"
  + "print(json.dumps(m.decide(sys.argv[2],sys.argv[3],sys.argv[4],sys.argv[5],sys.argv[6])))",
  join(repo, "tools", "pk_human_approve.py"), root, approvalId, prefix, decision, reason], { timeout: 60000 });

test("full loop with short args: unknown kept, failed check kept, human approval required before apply",
  { timeout: 180000 }, async () => {
    const root = mkdtempSync(join(tmpdir(), "pk-agh-"));
    const session = new KernelSession({ python, hostScript, root, pollTimeoutSec: 1 });
    await session.start(async (dir) => JSON.parse(readFileSync(join(dir, "demo-state.json"), "utf8")));
    const tools = Object.fromEntries(createTools(async () => session).map((tool) => [tool.name, tool]));
    const call = async (name, args = {}) => {
      const result = await tools[name].execute(args);
      assert.equal(result.isError, undefined, `${name}: ${JSON.stringify(result.structured)}`);
      return result.structured;
    };
    try {
      assert.deepEqual(Object.keys(tools).sort(), ["pk_apply_delivery", "pk_compare", "pk_events",
        "pk_request_delivery", "pk_run_strategy", "pk_select", "pk_state", "pk_verify"]);
      assert.ok(!Object.keys(tools).some((name) => /approve|decide/.test(name)), "approval must not be an agent tool");

      const state = await call("pk_state");
      assert.deepEqual(state.strategies.map((s) => s.strategy_id), ["s1", "s2", "s3"]);
      assert.match(state.guide, /pk_apply_delivery/);

      const stalled = await call("pk_run_strategy", { strategy_id: "s3" });
      assert.equal(stalled.attempt_status, "unknown", JSON.stringify(stalled));

      assert.equal((await tools.pk_verify.execute({ strategy_id: "s1" })).isError, true, "s1 not run yet");
      const skipped = await call("pk_verify", { strategy_id: "s3" });
      assert.equal(skipped.skipped, true, JSON.stringify(skipped));
      assert.equal(skipped.passed, false);
      assert.match(skipped.reason, /never relaunched/);
      assert.equal((await call("pk_run_strategy", { strategy_id: "s1" })).attempt_status, "completed");
      const coarse = await call("pk_verify", { strategy_id: "s1" });
      assert.equal(coarse.passed, false);
      assert.ok(Math.abs(coarse.alpha_fit - 0.35) < 1e-9, JSON.stringify(coarse));
      assert.match(coarse.reason, /disagrees/);

      assert.equal((await call("pk_run_strategy", { strategy_id: "s2" })).attempt_status, "completed");
      const golden = await call("pk_verify", { strategy_id: "s2" });
      assert.equal(golden.passed, true, JSON.stringify(golden));
      assert.ok(Math.abs(golden.alpha_fit - 0.37286) < 1e-4, JSON.stringify(golden));

      const compare = await call("pk_compare");
      assert.equal(compare.attempts.length, 3);
      assert.deepEqual(compare.failures_retained, [stalled.attempt_id]);
      assert.deepEqual(Object.fromEntries(compare.attempts.map((a) => [a.strategy_id, a.verification_result])),
        { s1: "failed", s2: "passed", s3: null });

      const selected = await call("pk_select", { strategy_id: "s2", reason: "黄金分割法通过独立校验，粗网格未通过" });
      assert.equal(selected.status, "committed", JSON.stringify(selected));
      assert.equal(selected.compared_attempts, 3);

      const requested = await call("pk_request_delivery");
      assert.equal(requested.approval_status, "pending", JSON.stringify(requested));
      assert.match(requested.next, /pk-human-approve/);

      const early = await call("pk_apply_delivery");
      assert.equal(early.applied, false);
      assert.equal(early.kernel_error.code, "APPROVAL_INVALID");
      assert.match(early.hint, /pk-human-approve/);

      await assert.rejects(humanDecide(root, requested.approval_id, "00000000", "approved", "wrong"), /摘要前缀/);
      const { stdout } = await humanDecide(root, requested.approval_id, requested.snapshot_digest.slice(0, 8),
        "approved", "人工核对摘要后批准");
      assert.equal(JSON.parse(stdout).approval_status, "approved");

      const applied = await call("pk_apply_delivery");
      assert.equal(applied.applied, true, JSON.stringify(applied));
      assert.equal(applied.operation_status, "applied");

      const events = (await call("pk_events")).events.map((e) => e.split(":")[1]);
      for (const kind of ["verification.recorded", "attempt.selected", "delivery_snapshot.frozen",
        "approval.requested", "approval.decided"]) {
        assert.ok(events.includes(kind), `${kind} missing from ${events.join(",")}`);
      }
      assert.ok(events.indexOf("approval.requested") < events.indexOf("approval.decided"));

      const bad = await tools.pk_verify.execute({ attempt_ref: { project_id: "x" } });
      assert.equal(bad.isError, true);
    } finally {
      await session.close();
    }
  });

test("kernel discovery prefers PK_KERNEL_ROOT, then cwd, then the plugin's repo", () => {
  const good = new Set(["/k/tests/p14_science_demo/agh_host.py", "/k/src/project_kernel",
    "/repo/tests/p14_science_demo/agh_host.py", "/repo/src/project_kernel"]);
  const exists = (p) => good.has(p.replaceAll("\\", "/"));
  const base = { platform: "linux", exists, tmp: "/tmp", now: new Date(2026, 9, 15, 9, 8, 7) };
  const fromEnv = resolveKernelPaths({ ...base, env: { PK_KERNEL_ROOT: "/k" }, cwd: "/repo", pluginDir: "/x/a/b" });
  assert.equal(fromEnv.kernelRoot, "/k");
  assert.equal(fromEnv.source, "PK_KERNEL_ROOT");
  assert.equal(fromEnv.root, join("/tmp", "pk-agh-demo-20261015-090807"));
  const fromCwd = resolveKernelPaths({ ...base, env: {}, cwd: "/repo", pluginDir: "/x/a/b" });
  assert.equal(fromCwd.source, "cwd");
  assert.equal(fromCwd.hostScript, join("/repo", "tests", "p14_science_demo", "agh_host.py"));
  const fromPlugin = resolveKernelPaths({ ...base, env: {}, cwd: "/elsewhere", pluginDir: "/repo/adapters/agh-plugin" });
  assert.equal(fromPlugin.source, "plugin-dir");
  const missing = resolveKernelPaths({ ...base, env: {}, cwd: "/elsewhere", pluginDir: "/x/a/b" });
  assert.equal(missing.kernelRoot, null);
  assert.match(missing.error, /PK_KERNEL_ROOT/);
  const wrongEnv = resolveKernelPaths({ ...base, env: { PK_KERNEL_ROOT: "/nope" }, cwd: "/repo" });
  assert.match(wrongEnv.error, /not a Project Kernel checkout/);
});
