import test from "node:test";
import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createServices, kernelPlugin, parseModuleFacts, redactSecrets } from "../index.mjs";
import { KernelSession } from "../kernel-session.mjs";

const task = { project_id: "project-1", object_type: "task", object_id: "task-1", revision_id: "revision-1" };
const envelope = (query, data = {}) => ({ query, as_of_seq: "7", projection_version: "v1",
  computed_at: "2026-10-13T00:00:00Z", freshness: { state: "fresh", store_head_seq: "7" },
  completeness: "complete", gaps: [], required_missing: [], next_page_token: "cursor-1", data });
const indexed = (session, paths) => Object.fromEntries(createServices(async () => session, paths)
  .map((service) => [service.name, service]));

test("browser service catalog matches the descriptor and contains only reads", async () => {
  const services = createServices(() => { throw new Error("unexpected session startup"); });
  const descriptor = JSON.parse(await readFile(new URL("../client/agnes.client.json", import.meta.url), "utf8"));
  const manifest = JSON.parse(await readFile(new URL("../package.json", import.meta.url), "utf8"));
  assert.deepEqual(services.map((s) => s.name).sort(), descriptor.client.services.toSorted());
  assert.deepEqual(services.map((s) => s.name).sort(), manifest.agnes.plugins[0].services.toSorted());
  for (const service of services) {
    assert.equal(service.kind, "query");
    assert.equal(service.inputSchema.additionalProperties, false);
    assert.deepEqual(service.outputSchema.required, ["meta", "data"]);
    assert.ok(!/approval\.(decide|revoke)/.test(service.name));
  }
  assert.equal(services.find((s) => s.name === "pk.events").outputSchema.properties.data.type, "array");
});

test("runtime services preserve metadata, apply kernel defaults and forward history and page cursors", async () => {
  const calls = [];
  const session = { state: { task_ref: task }, queryEnvelope: async (...args) => {
    calls.push(args);
    return envelope(args[0], args[0] === "events.read" ? [{ commit_seq: "6", event_index: 0 }] : {});
  } };
  const services = indexed(session);
  const inputs = {
    "pk.compare": {}, "pk.overview": {}, "pk.approvals": { status: "pending", page_token: "page-2" },
    "pk.events": { commit_seq: "2", event_index: 3, limit: 10 },
    "pk.timeline": { object_type: "task", page_token: "page-3" },
    "pk.trace": { root_ref: task, direction: "outgoing", max_depth: 20 },
    "pk.coverage": {}, "pk.environment": {}, "pk.operation": { operation_id: "op-1" },
  };
  for (const [name, input] of Object.entries(inputs)) {
    const result = await services[name].handler({ ...input, as_of_seq: "4" });
    assert.equal(result.meta.as_of_seq, "7");
    assert.equal(result.meta.projection_version, "v1");
    assert.equal(result.meta.next_page_token, "cursor-1");
    assert.deepEqual(result.meta.gaps, []);
    assert.equal(calls.at(-1)[2], "4", name);
  }
  assert.deepEqual(calls.find(([query]) => query === "attempts.compare")[1], { task_ref: task });
  assert.deepEqual(calls.find(([query]) => query === "events.read")[1],
    { after: { commit_seq: "2", event_index: 3 }, limit: 10 });
  assert.equal(calls.find(([query]) => query === "project.timeline")[3], "page-3");
  assert.equal(calls.find(([query]) => query === "approvals.queue")[3], "page-2");
  await services["pk.trace"].handler({});
  assert.deepEqual(calls.at(-1)[1], { root_ref: task, direction: "both", max_depth: 3 });
  assert.ok(Array.isArray((await services["pk.events"].handler()).data));
});

test("invalid browser inputs fail before starting a host", async () => {
  let starts = 0;
  const services = Object.fromEntries(createServices(async () => { starts += 1; throw new Error("unexpected startup"); })
    .map((s) => [s.name, s]));
  const invalid = [
    ["pk.overview", null], ["pk.overview", JSON.parse('{"__proto__": {}}')],
    ["pk.compare", { as_of_seq: 3 }], ["pk.coverage", { as_of_seq: "-1" }],
    ["pk.environment", { force: true }], ["pk.operation", {}], ["pk.operation", { operation_id: "" }],
    ["pk.events", { event_index: -1 }], ["pk.events", { limit: 1001 }],
    ["pk.timeline", { page_token: "" }], ["pk.approvals", { status: "made-up" }],
    ["pk.trace", { max_depth: 21 }], ["pk.trace", { max_depth: "3" }],
    ["pk.trace", { direction: "sideways" }], ["pk.trace", { root_ref: { object_id: "task-1" } }],
    ["pk.trace", { root_ref: { ...task, force: true } }],
    ["pk.tree", { as_of_seq: "1" }], ["pk.skills", { operation_id: "op-1" }],
  ];
  for (const [name, input] of invalid) {
    await assert.rejects(services[name].handler(input), { code: "INVALID_INPUT" }, `${name}: ${JSON.stringify(input)}`);
  }
  assert.equal(starts, 0);
});

test("document services retain declarations without a session and report unreadable or invalid registries", async (t) => {
  const root = await mkdtemp(join(tmpdir(), "pk-services-docs-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const paths = { registry: join(root, "modules.json"), skillsRegistry: join(root, "skills.json") };
  const services = indexed(null, paths);
  await assert.rejects(services["pk.tree"].handler({}), { code: "DOCUMENT_READ_FAILED" });
  await assert.rejects(services["pk.skills"].handler({}), { code: "DOCUMENT_READ_FAILED" });
  await writeFile(paths.registry, "{ invalid", "utf8");
  await assert.rejects(services["pk.tree"].handler({}), { code: "DOCUMENT_PARSE_FAILED" });
  await writeFile(paths.registry, "{}", "utf8");
  await assert.rejects(services["pk.tree"].handler({}), { code: "DOCUMENT_INVALID_REGISTRY" });
  await writeFile(paths.skillsRegistry, JSON.stringify({ skills: [{ skill_id: "skill-1" }] }), "utf8");
  await assert.rejects(services["pk.skills"].handler({}), { code: "DOCUMENT_INVALID_REGISTRY" });
  await writeFile(paths.registry, JSON.stringify({ document_version: "2", nodes: [{ node_id: "K-ROOT" }] }), "utf8");
  await writeFile(paths.skillsRegistry, JSON.stringify({ skills: [{ skill_id: "skill-1", versions: [] }] }), "utf8");
  const tree = await services["pk.tree"].handler({});
  const skills = await services["pk.skills"].handler({});
  assert.equal(tree.meta.origin_kind, "documentation");
  assert.equal(tree.meta.as_of_seq, null);
  assert.equal(tree.meta.freshness, null);
  assert.equal(tree.meta.document_version, "2");
  assert.equal(tree.data.nodes[0].node_id, "K-ROOT");
  assert.equal(skills.data.skills[0].skill_id, "skill-1");
});

test("module facts come only from what the node document states and drop missing links", async () => {
  const text = [
    "# K-DEMO：演示节点", "", "| 字段 | 值 |", "| --- | --- |", "| document_version | `1.2.0` |",
    "| updated_at | `2026-10-12 Asia/Shanghai` |", "| implementation_status | 已实现；未作新验收 |",
    "| source_revision | `16410c9fbf4a8507445b4603e371e701614e4499` |", "",
    "见 [交接](../../handoffs/P01.md) 与 [缺失](../../handoffs/GONE.md) 和 [外链](https://example.com/x)，REQ-CCR-01、REQ-BOUNDARY-06、REQ-CCR-01。",
  ].join("\n");
  const exists = (path) => path === "docs/handoffs/P01.md";
  const facts = parseModuleFacts(text, "nodes/demo.md", exists);
  assert.deepEqual(facts, {
    title: "演示节点", document_version: "1.2.0", updated_at: "2026-10-12", implementation_status: "已实现；未作新验收",
    source_revision: "16410c9fbf4a", requirement_ids: ["REQ-BOUNDARY-06", "REQ-CCR-01"],
    linked_records: { handoffs: ["docs/handoffs/P01.md"] },
  });
  const bare = parseModuleFacts("没有元数据的文档", "nodes/none.md", () => true);
  assert.equal(bare.document_version, null);
  assert.equal(bare.implementation_status, null);
  assert.deepEqual(bare.linked_records, {});
});

test("document services list and read only docs/ and the root plan, redact credentials and check references", async (t) => {
  const root = await mkdtemp(join(tmpdir(), "pk-services-read-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  await mkdir(join(root, "docs/modules/nodes"), { recursive: true });
  await mkdir(join(root, "docs/handoffs"), { recursive: true });
  await writeFile(join(root, "docs/modules/registry.json"), JSON.stringify({ nodes: [{ node_id: "K-ROOT" }] }), "utf8");
  await writeFile(join(root, "docs/handoffs/h1.md"), "# 交接一\n见 [计划](../../DELIVERY_PLAN.md)", "utf8");
  await writeFile(join(root, "DELIVERY_PLAN.md"), "# 计划\nDEMO_API_KEY=abc123\n`docs/handoffs/h1.md` `docs/gone.md`", "utf8");
  await writeFile(join(root, "README.md"), "# 不可读", "utf8");
  await writeFile(join(root, "secret.md"), "# 不可读", "utf8");
  const services = indexed(null, { registry: join(root, "docs/modules/registry.json"), skillsRegistry: join(root, "none.json") });
  const list = await services["pk.documents"].handler({});
  assert.deepEqual(list.data.documents.map((d) => d.path), ["DELIVERY_PLAN.md", "docs/handoffs/h1.md"]);
  assert.equal(list.data.documents[1].title, "交接一");
  assert.equal(list.data.documents[0].category, "plans");
  const plan = await services["pk.document"].handler({ path: "DELIVERY_PLAN.md" });
  assert.ok(!plan.data.text.includes("abc123"), "credential values never leave the plugin");
  assert.match(plan.data.text, /DEMO_API_KEY=\[已隐藏\]/);
  assert.deepEqual(plan.data.references, [{ path: "docs/gone.md", exists: false }, { path: "docs/handoffs/h1.md", exists: true }]);
  const handoff = await services["pk.document"].handler({ path: "docs/handoffs/h1.md" });
  assert.deepEqual(handoff.data.references, [{ path: "DELIVERY_PLAN.md", exists: true }]);
  for (const path of ["README.md", "secret.md", "docs/../README.md", "docs/handoffs/../../README.md", "src/a.md", "docs/a.txt"]) {
    await assert.rejects(services["pk.document"].handler({ path }), (error) => ["INVALID_INPUT", "DOCUMENT_NOT_ALLOWED"].includes(error.code), path);
  }
  await assert.rejects(services["pk.document"].handler({ path: "docs/handoffs/none.md" }), { code: "DOCUMENT_READ_FAILED" });
  await assert.rejects(services["pk.document"].handler({}), { code: "INVALID_INPUT" });
  assert.equal(redactSecrets("A_TOKEN: x\nB=1"), "A_TOKEN: [已隐藏]\nB=1");
});

test("queryEnvelope retains the RPC result and query retains legacy data while forwarding protocol options", async () => {
  const calls = [];
  const session = new KernelSession({});
  session.state = { project_id: "project-1" };
  const response = envelope("events.read", []);
  session.client = { query: async (args) => { calls.push(args); return response; } };
  assert.strictEqual(await session.queryEnvelope("events.read", {}, "4", "cursor"), response);
  assert.strictEqual(await session.query("events.read", {}, "4"), response.data);
  assert.equal(calls[0].asOfSeq, "4");
  assert.equal(calls[0].pageToken, "cursor");
  assert.deepEqual(calls[0].selector, { project_id: "project-1" });
});

test("concurrent browser queries share startup and disposal closes that session", async (t) => {
  const original = { start: KernelSession.prototype.start, close: KernelSession.prototype.close,
    queryEnvelope: KernelSession.prototype.queryEnvelope };
  t.after(() => Object.assign(KernelSession.prototype, original));
  let starts = 0;
  let closes = 0;
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  KernelSession.prototype.start = async function () { starts += 1; await gate; this.state = { task_ref: task }; };
  KernelSession.prototype.close = async function () { closes += 1; };
  KernelSession.prototype.queryEnvelope = async function (query) { return envelope(query); };
  const services = new Map();
  const disposers = [];
  kernelPlugin.apply({ extension: () => ({ registerTool: () => () => {} }),
    services: { register: (s) => { services.set(s.name, s); return () => services.delete(s.name); } },
    effect: (setup) => disposers.push(setup()) });
  const pending = [services.get("pk.overview").handler({}), services.get("pk.compare").handler({})];
  assert.equal(starts, 1);
  release();
  await Promise.all(pending);
  for (const dispose of disposers.toReversed()) await dispose?.();
  assert.equal(closes, 1);
});

test("disposing while startup is pending closes the child and rejects waiting callers", async (t) => {
  const original = { start: KernelSession.prototype.start, close: KernelSession.prototype.close };
  t.after(() => Object.assign(KernelSession.prototype, original));
  let rejectStartup;
  let closes = 0;
  KernelSession.prototype.start = function () {
    return new Promise((_resolve, reject) => { rejectStartup = reject; });
  };
  KernelSession.prototype.close = async function () {
    closes += 1;
    rejectStartup(new Error("closed during startup"));
  };
  const services = new Map();
  const disposers = [];
  kernelPlugin.apply({ extension: () => ({ registerTool: () => () => {} }),
    services: { register: (s) => { services.set(s.name, s); return () => {}; } },
    effect: (setup) => disposers.push(setup()) });
  const pending = services.get("pk.overview").handler({});
  const rejection = assert.rejects(pending, /closed during startup/);
  await disposers.at(-1)();
  await rejection;
  assert.equal(closes, 1);
  await assert.rejects(services.get("pk.overview").handler({}), /disposed/);
});

test("real RPC services carry freshness and history, document queries bypass the host", {
  timeout: 120000, skip: !process.env.PK_HOST_SCRIPT || !process.env.PK_PYTHON,
}, async (t) => {
  const root = await mkdtemp(join(tmpdir(), "pk-services-real-"));
  const session = new KernelSession({ root, python: process.env.PK_PYTHON,
    hostScript: process.env.PK_HOST_SCRIPT, pollTimeoutSec: 1 });
  t.after(async () => { await session.close(); await rm(root, { recursive: true, force: true }); });
  const firstStart = session.start(async (dir) => JSON.parse(await readFile(join(dir, "demo-state.json"), "utf8")));
  assert.strictEqual(session.start(() => { throw new Error("second startup"); }), firstStart);
  await firstStart;
  const services = indexed(session, { registry: process.env.PK_REGISTRY, skillsRegistry: process.env.PK_SKILLS_REGISTRY });
  for (const name of ["pk.overview", "pk.compare", "pk.approvals", "pk.events", "pk.timeline", "pk.trace", "pk.coverage", "pk.environment"]) {
    const result = await services[name].handler({});
    assert.equal(typeof result.meta.as_of_seq, "string", name);
    assert.equal(typeof result.meta.freshness.state, "string", name);
    assert.ok(Array.isArray(result.meta.gaps), name);
    assert.ok(Array.isArray(result.meta.required_missing), name);
    assert.ok("data" in result, name);
  }
  assert.ok(Array.isArray((await services["pk.approvals"].handler({})).data.queue));
  assert.ok(Array.isArray((await services["pk.events"].handler({})).data));
  assert.equal((await services["pk.overview"].handler({ as_of_seq: "0" })).meta.as_of_seq, "0");
  await assert.rejects(services["pk.operation"].handler({ operation_id: "missing-operation" }), { code: "REFERENCE_NOT_FOUND" });
  const started = await session.command("attempt.start", { packet_ref: session.state.packet_ref,
    strategy_id: "s2", execution_root_ref: session.state.execution_roots.s2 });
  const operation = await services["pk.operation"].handler({ operation_id: started.receipt.operation_id });
  assert.equal(operation.data.operation_id, started.receipt.operation_id);
  if (process.env.PK_REGISTRY && process.env.PK_SKILLS_REGISTRY) {
    const documents = Object.fromEntries(createServices(() => { throw new Error("document started host"); },
      { registry: process.env.PK_REGISTRY, skillsRegistry: process.env.PK_SKILLS_REGISTRY }).map((s) => [s.name, s]));
    assert.ok((await documents["pk.tree"].handler({})).data.nodes.length);
    assert.ok((await documents["pk.skills"].handler({})).data.skills.length);
  }
});
