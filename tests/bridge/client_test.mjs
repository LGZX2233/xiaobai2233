// P10 stdio boundary tests: framing, out-of-order responses, strict decoding,
// timeout/reconnect recovery and payload-forging refusal (AC37/AC38 on the TS
// bridge side). Run with: node --test tests/bridge/client_test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { ProtocolClient, ProtocolError, inputHash } from "../../bridge/protocol/client.mjs";

const vectors = JSON.parse(
  readFileSync(new URL("./vectors.json", import.meta.url), "utf8"),
);

function fakeTimers() {
  let seq = 0;
  const timers = new Map();
  return {
    setTimer(fn) {
      seq += 1;
      timers.set(seq, fn);
      return seq;
    },
    clearTimer(id) {
      timers.delete(id);
    },
    fireAll() {
      const fns = [...timers.values()];
      timers.clear();
      for (const fn of fns) fn();
    },
    size() {
      return timers.size;
    },
  };
}

function makeClient(options = {}) {
  const sent = [];
  const timers = options.timers ?? fakeTimers();
  const client = new ProtocolClient({
    write: (bytes) => sent.push(bytes.toString("utf8")),
    machineContextId: "ctx-machine-0001",
    setTimer: timers.setTimer,
    clearTimer: timers.clearTimer,
    ...options,
  });
  return {
    client,
    sent,
    timers,
    requests: () => sent.map((line) => JSON.parse(line)),
    lastRequest: () => JSON.parse(sent[sent.length - 1]),
  };
}

const responseLine = (id, result) => Buffer.from(`${JSON.stringify({ jsonrpc: "2.0", id, result })}\n`, "utf8");

test("input_hash golden vectors match the Python digests", () => {
  for (const vector of vectors.vectors) {
    assert.equal(
      inputHash(vector.command, vector.selector, vector.expected_heads, vector.payload),
      vector.input_hash,
      `vector ${vector.id}`);
    if (vector.reordered_hash) {
      assert.equal(
        inputHash(vector.command, vector.selector, vector.reordered_expected_heads, vector.payload),
        vector.reordered_hash,
        `vector ${vector.id} reordered heads`);
      assert.notEqual(vector.reordered_hash, vector.input_hash);
    }
    // the minted handle must never influence the idempotency hash
    assert.equal(vector.handle_a === vector.handle_b, false);
    assert.equal(
      inputHash(vector.command, vector.selector, vector.expected_heads, vector.payload),
      vector.input_hash);
  }
});

test("a frame split inside a multi-byte UTF-8 character still resolves", async () => {
  const { client } = makeClient();
  const body = responseLine("rpc-1", { msg: "中文完成" });
  const marker = Buffer.from("中", "utf8");
  const idx = body.indexOf(marker);
  assert.ok(idx > 0);
  const promise = client.request("kernel.initialize", { client_id: "c" });
  client.onData(body.subarray(0, idx + 1)); // partial frame, mid-character
  client.onData(body.subarray(idx + 1));
  assert.deepEqual(await promise, { msg: "中文完成" });
});

test("coalesced and out-of-order responses bind to their own request ids", async () => {
  const { client } = makeClient();
  const first = client.request("kernel.query", { q: 1 });
  const second = client.request("kernel.query", { q: 2 });
  client.onData(Buffer.concat([
    responseLine("rpc-2", { winner: 2 }),
    responseLine("rpc-1", { winner: 1 }),
  ]));
  assert.deepEqual(await second, { winner: 2 });
  assert.deepEqual(await first, { winner: 1 });
});

test("a duplicate response id is an orphan, not a second resolve", async () => {
  const { client } = makeClient();
  const promise = client.request("kernel.query", { q: 1 });
  client.onData(responseLine("rpc-1", { ok: true }));
  client.onData(responseLine("rpc-1", { ok: "second" }));
  assert.deepEqual(await promise, { ok: true });
  assert.equal(client.orphanResponses.length, 1);
});

test("invalid UTF-8 fails every pending request instead of hanging", async () => {
  const { client } = makeClient();
  const promise = client.request("kernel.query", { q: 1 });
  client.onData(Buffer.concat([Buffer.from('{"jsonrpc":"2.0","id":"rpc-1","result":{"a":"'), Buffer.from([0xff, 0xfe]), Buffer.from('"}}\n')]));
  await assert.rejects(promise, (err) => err.code === "PARSE_ERROR");
  assert.ok(client.failed);
});

test("duplicate JSON keys and oversized frames are rejected", async () => {
  const dup = makeClient();
  const dupPromise = dup.client.request("kernel.query", { q: 1 });
  dup.client.onData(Buffer.from('{"jsonrpc":"2.0","id":"rpc-1","id":"rpc-1","result":{}}\n'));
  await assert.rejects(dupPromise, (err) => err.code === "PARSE_ERROR");

  const big = makeClient({ maxFrameBytes: 64 });
  const bigPromise = big.client.request("kernel.query", { q: 1 });
  big.client.onData(Buffer.alloc(128, 0x61)); // no newline, over the limit
  await assert.rejects(bigPromise, (err) => err.code === "FRAME_TOO_LARGE");
});

test("escaped and literal spellings of the same JSON key are duplicates", async () => {
  const { client } = makeClient();
  const pending = client.request("kernel.query", { q: 1 });
  client.onData(Buffer.from('{"jsonrpc":"2.0","id":"rpc-1","result":{"a":1,"\\u0061":2}}\n'));
  await assert.rejects(pending, (err) => err.code === "PARSE_ERROR");
});

test("a complete oversized frame is rejected before resolving a pending request", async () => {
  const { client } = makeClient({ maxFrameBytes: 128 });
  const pending = client.request("kernel.query", { q: 1 });
  client.onData(responseLine("rpc-1", { text: "x".repeat(256) }));
  await assert.rejects(pending, (err) => err.code === "FRAME_TOO_LARGE");
});

test("invalid escapes in object keys remain protocol parse errors", async () => {
  const { client } = makeClient();
  const pending = client.request("kernel.query", { q: 1 });
  client.onData(Buffer.from('{"jsonrpc":"2.0","id":"rpc-1","result":{"\\q":1}}\n'));
  await assert.rejects(pending, (err) => err.code === "PARSE_ERROR");
});

test("a finite JSON exponent that overflows the runtime cannot resolve as Infinity", async () => {
  const { client } = makeClient();
  const pending = client.request("kernel.query", { q: 1 });
  client.onData(Buffer.from('{"jsonrpc":"2.0","id":"rpc-1","result":{"values":[1e999]}}\n'));
  await assert.rejects(pending, (err) => err.code === "PARSE_ERROR");
});

test("timeout is not cancellation and recovery reuses the original key", async () => {
  const { client, sent, timers, lastRequest } = makeClient();
  const promise = client.command({
    command: "task.create", selector: { project_id: "project-demo" },
    payload: { title: "t", goal: "g", requirement_refs: [], mode: "test" },
    idempotencyKey: "key-1",
  });
  const written = sent.length;
  timers.fireAll();
  await assert.rejects(promise, (err) => err.code === "COMMIT_OUTCOME_UNKNOWN" && err.retryable === true);
  assert.equal(sent.length, written, "a timeout must not emit a cancel frame");
  assert.equal(lastRequest().params.idempotency_key, "key-1");

  const recovery = client.recoverReceipt({
    idempotencyKey: "key-1", receiptDomain: "project",
    selector: { project_id: "project-demo" },
  });
  const recoveryRequest = JSON.parse(sent[sent.length - 1]);
  assert.equal(recoveryRequest.params.query, "command.receipt");
  assert.equal(recoveryRequest.params.payload.idempotency_key, "key-1");
  assert.equal(recoveryRequest.params.payload.receipt_domain, "project");
  client.onData(responseLine(recoveryRequest.id, { data: { receipt: { status: "committed" } } }));
  assert.deepEqual(await recovery, { status: "committed" });
});

test("an unknown receipt is reported as unknown, never as success", async () => {
  const { client, sent } = makeClient();
  const recovery = client.recoverReceipt({ idempotencyKey: "key-2" });
  const request = JSON.parse(sent[sent.length - 1]);
  client.onData(responseLine(request.id, { data: { receipt: null } }));
  assert.equal(await recovery, null);
});

test("business errors surface their frozen code and retryable flag", async () => {
  const { client } = makeClient();
  const promise = client.command({
    command: "attempt.start", selector: { project_id: "project-demo" }, payload: {},
    idempotencyKey: "key-3",
  });
  client.onData(Buffer.from(`${JSON.stringify({
    jsonrpc: "2.0", id: "rpc-1",
    error: { code: -32602, message: "busy", data: { code: "SQLITE_BUSY", retryable: true } },
  })}\n`, "utf8"));
  await assert.rejects(promise, (err) => err.code === "SQLITE_BUSY" && err.retryable === true);
});

test("the caller cannot forge identity, scope or trust references", () => {
  const { client } = makeClient();
  assert.throws(() => client.command({
    command: "task.create", selector: { project_id: "p" },
    payload: { title: "t", actor_id: "admin" }, idempotencyKey: "k",
  }), (err) => err instanceof ProtocolError && err.code === "INVALID_INPUT");
  assert.throws(() => client.command({
    command: "artifact.register", selector: { project_id: "p" },
    payload: { trusted_staged_locator_ref: {} }, idempotencyKey: "k",
  }), (err) => err.code === "INVALID_INPUT");
  assert.throws(() => client.command({
    command: "task.create", selector: { project_id: "p" }, payload: {},
  }), (err) => err.code === "INVALID_INPUT"); // no idempotency key

  const unbound = makeClient({ machineContextId: null });
  assert.throws(() => unbound.client.command({
    command: "task.create", selector: { project_id: "p" }, payload: {}, idempotencyKey: "k",
  }), (err) => err.code === "PERMISSION_DENIED");
});

test("the handle is attached at the boundary and never sits in the payload", () => {
  const { client, sent } = makeClient();
  client.command({
    command: "task.create", selector: { project_id: "project-demo" },
    payload: { title: "t", goal: "g", requirement_refs: [], mode: "test" },
    idempotencyKey: "key-4",
  });
  const request = JSON.parse(sent[0]);
  assert.equal(request.params.invocation_context_id, "ctx-machine-0001");
  assert.equal(Object.keys(request.params.payload).includes("invocation_context_id"), false);
});
