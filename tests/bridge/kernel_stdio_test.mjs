// Real test-only Python composition root over pipes, with a lost reply and restart.
import test from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { ProtocolClient } from "../../bridge/protocol/client.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const python = join(root, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");

function host(temp, drop = false) {
  const child = spawn(python, ["-X", "utf8", "-B", "tests/g2_acceptance/stdio_test_host.py",
    "--root", temp, ...(drop ? ["--drop-first-command"] : [])], { cwd: root, windowsHide: true });
  const requests = [], responses = [], logs = [], timers = new Map();
  let seq = 0, stderr = "", droppedResolve;
  const dropped = new Promise((resolve) => { droppedResolve = resolve; });
  const done = new Promise((resolve, reject) => {
    child.once("error", reject);
    child.once("close", (code) => code === 0 ? resolve() : reject(new Error(`host exited ${code}: ${stderr}`)));
  });
  const client = new ProtocolClient({
    machineContextId: "test-protocol-handle",
    write(bytes) {
      requests.push(JSON.parse(bytes.toString("utf8")));
      const split = Math.min(47, bytes.length);
      child.stdin.write(bytes.subarray(0, split));
      child.stdin.write(bytes.subarray(split));
    },
    setTimer(fn) { timers.set(++seq, fn); return seq; },
    clearTimer(id) { timers.delete(id); },
  });
  child.stdout.on("data", (bytes) => {
    responses.push(bytes.toString("utf8"));
    client.onData(bytes);
  });
  child.stderr.on("data", (bytes) => {
    stderr += bytes.toString("utf8");
    logs.push(bytes.toString("utf8"));
    if (stderr.includes("committed response deliberately dropped")) droppedResolve();
  });
  return { client, requests, responses, logs, dropped, done,
    fireTimeouts() { const callbacks = [...timers.values()]; timers.clear(); callbacks.forEach((fn) => fn()); },
    async close() { child.stdin.end(); await done; client.close(); },
  };
}

test("real stdio timeout preserves a committed task and reconnect reads the original key", { timeout: 30000 }, async () => {
  const tempRoot = join(root, ".validation-tmp", "g2-round4-node-final");
  mkdirSync(tempRoot, { recursive: true });
  const temp = mkdtempSync(join(tempRoot, "stdio-"));
  const first = host(temp, true);
  const selector = { project_id: "protocol-project" };
  const input = { command: "task.create", selector, payload: {
    title: "stdio task", goal: "lost response", requirement_refs: [], mode: "test" }, idempotencyKey: "original-key" };
  let second;
  try {
    assert.equal((await first.client.initialize("test-node-client")).mode, "test");
    const pending = first.client.command(input);
    const rejected = assert.rejects(pending, (err) => err.code === "COMMIT_OUTCOME_UNKNOWN");
    await first.dropped;
    const sentBeforeTimeout = first.requests.length;
    first.fireTimeouts();
    await rejected;
    assert.equal(first.requests.length, sentBeforeTimeout);
    await first.close();

    second = host(temp);
    const receipt = await second.client.recoverReceipt({ selector, idempotencyKey: "original-key" });
    assert.equal(receipt.status, "committed");
    const replay = await second.client.command(input);
    assert.deepEqual(replay.receipt, receipt);
    assert.equal(await second.client.recoverReceipt({ selector, idempotencyKey: "never-issued" }), null);
    const overview = await second.client.query({ query: "project.overview", selector });
    assert.equal(overview.data.object_counts.task, 1);
    await second.close();
    for (const connection of [first, second]) {
      for (const line of connection.responses.join("").trim().split("\n")) assert.equal(JSON.parse(line).jsonrpc, "2.0");
      assert.ok(connection.logs.join("").includes("kernel."));
      assert.ok(!connection.logs.join("").includes("test-protocol-handle"));
    }
    const files = readdirSync(temp).map((name) => ({ path: name,
      sha256: createHash("sha256").update(readFileSync(join(temp, name))).digest("hex") }));
    writeFileSync(join(temp, "node-stdio-evidence.json"), JSON.stringify({ mode: "test", root: temp,
      input, receipt, overview, connections: [first, second].map(({ requests, responses, logs }) => ({ requests, responses, logs })), files }, null, 2) + "\n");
  } finally {
    await first.close();
    if (second) await second.close();
  }
});
