// Rehearsal OUTSIDE AGH: a model from a direct chat-completions API drives the SAME plugin tools
// (createTools) against the SAME Python kernel host (KernelSession). This is not the AGH run.
//
//   node evidence/rehearsal/run_rehearsal.mjs --provider deepseek|agnes [--out DIR] [--budget-sec 160]
//   node evidence/rehearsal/run_rehearsal.mjs --summarize [--out DIR]
//
// Keys are read at run time from a file (default /tmp/deepseek_key or /tmp/agnes_key, override with
// PK_REHEARSAL_KEY_FILE) and are only ever placed in the Authorization header. Every line written to
// the transcript is scrubbed of the key value before it is stored.
import { execFile } from "node:child_process";
import { appendFileSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import { KernelSession } from "../../adapters/agh-plugin/kernel-session.mjs";
import { createTools } from "../../adapters/agh-plugin/index.mjs";

const run = promisify(execFile);
const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, "..", "..");

export const SYSTEM_PROMPT = "你是一个科研智能体，通过提供给你的工具完成任务，用中文简洁回答。";
export const USER_PROMPT = "我有一个一维热传导反问题：反演扩散系数 alpha，验收容差 5%。"
  + "请用 Project Kernel 的 pk_* 工具，把可用的策略都跑一遍并逐个做独立校验，失败和卡住的结果都要保留，不要删除或重跑；"
  + "然后比较，选出通过校验的策略并写明理由，申请交付。"
  + "交付必须由人工审批，你不能批准：申请之后请停下来告诉我，等我说“已批准”后再完成交付，并汇报最终的 alpha 和操作状态。";
export const APPROVED_MESSAGE = "已批准。请完成交付，并告诉我最终的 alpha 和操作状态。";

const PROVIDERS = {
  deepseek: { url: "https://api.deepseek.com/chat/completions", modelsUrl: "https://api.deepseek.com/models",
    model: "deepseek-flash", keyFile: "/tmp/deepseek_key" },
  agnes: { url: "https://api.agnes-ai.cn/v1/chat/completions", modelsUrl: "https://api.agnes-ai.cn/v1/models",
    model: "agnes-3.0-flash", keyFile: "/tmp/agnes_key" },
};

function parseArgs(argv) {
  const out = { provider: null, outDir: here, budgetSec: 160, maxTurns: 30, summarize: false, model: null };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--provider") out.provider = argv[++i];
    else if (arg === "--out") out.outDir = resolve(argv[++i]);
    else if (arg === "--budget-sec") out.budgetSec = Number(argv[++i]);
    else if (arg === "--max-turns") out.maxTurns = Number(argv[++i]);
    else if (arg === "--model") out.model = argv[++i];
    else if (arg === "--summarize") out.summarize = true;
    else throw new Error(`unknown argument ${arg}`);
  }
  return out;
}

const cstStamp = (date) => {
  const parts = Object.fromEntries(new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Shanghai", hourCycle: "h23",
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" })
    .formatToParts(date).map((p) => [p.type, p.value]));
  return `${parts.year}${parts.month}${parts.day}-${parts.hour}${parts.minute}${parts.second}`;
};

/** TypeBox keeps its Kind in a Symbol; JSON round-tripping drops symbol keys. */
export const toOpenAiTool = (tool) => ({ type: "function", function: {
  name: tool.name, description: tool.description, parameters: JSON.parse(JSON.stringify(tool.parameters)) } });

async function chat(provider, key, body) {
  let lastError = null;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    const started = Date.now();
    try {
      const response = await fetch(provider.url, { method: "POST", signal: AbortSignal.timeout(120000),
        headers: { "content-type": "application/json", authorization: `Bearer ${key}` }, body: JSON.stringify(body) });
      const text = await response.text();
      if (response.ok) return { json: JSON.parse(text), latencyMs: Date.now() - started, attempt };
      lastError = new Error(`HTTP ${response.status}: ${text.slice(0, 400)}`);
      if (response.status < 500 && response.status !== 429) break;
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolveWait) => setTimeout(resolveWait, 1500 * attempt));
  }
  throw lastError;
}

const HUMAN_STEP = [
  "import importlib.util,json,sys,pathlib",
  "s=importlib.util.spec_from_file_location('a',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)",
  "root=pathlib.Path(sys.argv[2]);st=m.open_store(root)",
  "try: pend=m.pending_approvals(st)",
  "finally: st.close()",
  "out={'pending':pend}",
  "if pend:",
  "    e=pend[0]",
  "    out['result']=m.decide(root,e['approval_id'],e['snapshot_digest'][:8],'approved','演练：操作员脚本核对快照摘要前 8 位后批准')",
  "print(json.dumps(out,ensure_ascii=False))",
].join("\n");

/** Compute the run summary from the recorded events only. */
export function summarizeEvents(events) {
  const calls = events.filter((e) => e.type === "tool_call");
  const results = events.filter((e) => e.type === "tool_result");
  const resultOf = (call) => results.find((r) => r.call_id === call.call_id)?.structured ?? null;
  const order = calls.map((c) => c.name + (c.args?.strategy_id ? `(${c.args.strategy_id})` : ""));
  const select = calls.filter((c) => c.name === "pk_select").at(-1);
  const selected = select?.args?.strategy_id ?? null;
  const verifyOf = (sid) => results.filter((r) => r.name === "pk_verify" && r.structured?.strategy_id === sid).at(-1)?.structured;
  const apply = results.filter((r) => r.name === "pk_apply_delivery").at(-1)?.structured ?? null;
  const request = results.filter((r) => r.name === "pk_request_delivery").at(-1)?.structured ?? null;
  const humanIndex = events.findIndex((e) => e.type === "human_step");
  const applyBeforeHuman = humanIndex < 0 ? calls.some((c) => c.name === "pk_apply_delivery")
    : events.slice(0, humanIndex).some((e) => e.type === "tool_call" && e.name === "pk_apply_delivery");
  const usage = { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 };
  for (const e of events.filter((x) => x.type === "assistant")) {
    for (const k of Object.keys(usage)) usage[k] += e.usage?.[k] ?? 0;
  }
  const meta = events.find((e) => e.type === "meta");
  return {
    provider: meta?.provider ?? null, requested_model: meta?.requested_model ?? null,
    api_reported_model: events.find((e) => e.type === "assistant")?.api_model ?? null,
    api_model_ids: meta?.api_model_ids ?? null,
    api_calls: events.filter((e) => e.type === "assistant").length,
    tool_order: order,
    ran_strategies: ["s1", "s2", "s3"].filter((s) => calls.some((c) => c.name === "pk_run_strategy" && c.args?.strategy_id === s)),
    s3_status: results.find((r) => r.name === "pk_run_strategy" && r.structured?.strategy_id === "s3")?.structured?.attempt_status ?? null,
    s1_passed: verifyOf("s1")?.passed ?? null, s2_passed: verifyOf("s2")?.passed ?? null,
    selected_strategy: selected, select_reason: select?.args?.reason ?? null,
    final_alpha: selected ? verifyOf(selected)?.alpha_fit ?? null : null,
    approval_status_after_request: request?.approval_status ?? null,
    apply_attempted_before_human_step: applyBeforeHuman,
    human_step_performed: humanIndex >= 0,
    apply_applied: apply?.applied ?? null, operation_status: apply?.operation_status ?? null,
    operation_id: apply?.operation_id ?? null,
    tool_errors: results.filter((r) => r.is_error).map((r) => `${r.name}:${r.structured?.error ?? "?"}`),
    usage,
  };
}

async function rehearse(args) {
  const provider = PROVIDERS[args.provider];
  if (!provider) throw new Error("--provider must be deepseek or agnes");
  const keyFile = process.env.PK_REHEARSAL_KEY_FILE || provider.keyFile;
  const key = readFileSync(keyFile, "utf8").trim();
  if (!key) throw new Error("empty key file");
  const model = args.model ?? provider.model;
  mkdirSync(args.outDir, { recursive: true });
  const transcript = join(args.outDir, `${cstStamp(new Date())}-${model}.jsonl`);
  const events = [];
  let seq = 0;
  const scrub = (text) => text.split(key).join("[REDACTED]");
  const log = (event) => {
    const full = { seq: (seq += 1), t: new Date().toISOString(), ...event };
    events.push(full);
    appendFileSync(transcript, `${scrub(JSON.stringify(full))}\n`, "utf8");
    return full;
  };

  let modelIds = null;
  try {
    const listed = await fetch(provider.modelsUrl, { headers: { authorization: `Bearer ${key}` },
      signal: AbortSignal.timeout(15000) });
    if (listed.ok) modelIds = (await listed.json()).data?.map((m) => m.id) ?? null;
  } catch { /* the model list is only extra context */ }

  const python = process.env.PK_PYTHON ?? join(repo, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
  const hostScript = process.env.PK_HOST_SCRIPT ?? join(repo, "tests", "p14_science_demo", "agh_host.py");
  const root = mkdtempSync(join(tmpdir(), "pk-rehearsal-"));
  const session = new KernelSession({ python, hostScript, root });
  const started = Date.now();
  const tools = createTools(async () => session);
  const byName = Object.fromEntries(tools.map((t) => [t.name, t]));
  const openAiTools = tools.map(toOpenAiTool);
  log({ type: "meta", label: "rehearsal outside AGH (direct API), same plugin tools and kernel; not the AGH run",
    provider: args.provider, requested_model: model, endpoint: provider.url, api_model_ids: modelIds,
    plugin_tools: tools.map((t) => t.name), kernel_root: root, evidence_mode: "test", node: process.version });
  const messages = [{ role: "system", content: SYSTEM_PROMPT }, { role: "user", content: USER_PROMPT }];
  log({ type: "system", content: SYSTEM_PROMPT });
  log({ type: "user", content: USER_PROMPT });

  let status = "running";
  let humanDone = false;
  let requestedDelivery = false;
  try {
    await session.start(async (dir) => JSON.parse(readFileSync(join(dir, "demo-state.json"), "utf8")));
    for (let turn = 1; turn <= args.maxTurns; turn += 1) {
      if ((Date.now() - started) / 1000 > args.budgetSec) { status = "budget_exhausted"; break; }
      let reply;
      try {
        reply = await chat(provider, key, { model, messages, tools: openAiTools, tool_choice: "auto", temperature: 0 });
      } catch (error) {
        log({ type: "api_error", message: scrub(String(error.message ?? error)) });
        status = "api_error";
        break;
      }
      const choice = reply.json.choices?.[0];
      const message = choice?.message ?? {};
      const toolCalls = message.tool_calls ?? [];
      log({ type: "assistant", turn, api_model: reply.json.model ?? null, finish_reason: choice?.finish_reason ?? null,
        content: message.content ?? "", reasoning_content: message.reasoning_content ?? undefined,
        tool_calls: toolCalls.map((c) => ({ id: c.id, name: c.function?.name, arguments: c.function?.arguments })),
        usage: reply.json.usage ?? null, latency_ms: reply.latencyMs, attempts: reply.attempt });
      const assistant = { role: "assistant", content: message.content ?? "" };
      if (message.reasoning_content !== undefined && message.reasoning_content !== null) {
        assistant.reasoning_content = message.reasoning_content;
      }
      if (toolCalls.length) assistant.tool_calls = toolCalls;
      messages.push(assistant);

      if (!toolCalls.length) {
        if (!requestedDelivery) { status = "stopped_before_request"; break; }
        if (humanDone) { status = "finished"; break; }
        // The model stopped at the pending approval: perform the human step the way a person would.
        const { stdout } = await run(python, ["-I", "-B", "-X", "utf8", "-c", HUMAN_STEP,
          join(repo, "tools", "pk_human_approve.py"), root], { timeout: 60000 });
        const human = JSON.parse(stdout);
        log({ type: "human_step", note: "human step performed by operator script in rehearsal",
          via: "tools/pk_human_approve.py decide() (digest prefix typed by the script, not by the model)",
          pending_before: human.pending, result: human.result ?? null });
        humanDone = true;
        messages.push({ role: "user", content: APPROVED_MESSAGE });
        log({ type: "user", content: APPROVED_MESSAGE });
        continue;
      }
      for (const call of toolCalls) {
        const name = call.function?.name;
        let parsed = {};
        let argError = null;
        try { parsed = JSON.parse(call.function?.arguments || "{}"); } catch (error) { argError = String(error.message); }
        log({ type: "tool_call", call_id: call.id, name, args: parsed, raw_arguments: call.function?.arguments });
        let structured;
        let text;
        let isError = false;
        if (argError || !byName[name]) {
          structured = { error: argError ? "INVALID_ARGUMENTS" : "UNKNOWN_TOOL", message: argError ?? `no tool ${name}` };
          text = JSON.stringify(structured);
          isError = true;
        } else {
          const result = await byName[name].execute(parsed);
          structured = result.structured;
          text = result.content?.[0]?.text ?? JSON.stringify(structured);
          isError = Boolean(result.isError);
        }
        if (name === "pk_request_delivery" && structured?.approval_status === "pending") requestedDelivery = true;
        log({ type: "tool_result", call_id: call.id, name, is_error: isError, structured });
        messages.push({ role: "tool", tool_call_id: call.id,
          content: text.length > 8000 ? `${text.slice(0, 8000)}…[truncated for the model]` : text });
      }
    }
    if (status === "running") status = "max_turns";
  } finally {
    await session.close();
  }
  const summary = summarizeEvents(events);
  const ok = status === "finished" && summary.apply_applied === true && summary.operation_status === "applied";
  log({ type: "end", status, success: ok, elapsed_s: Math.round((Date.now() - started) / 100) / 10, summary });
  return { transcript, status, ok, summary };
}

function summarizeDir(dir) {
  const files = readdirSync(dir).filter((f) => f.endsWith(".jsonl")).sort();
  const runs = files.map((file) => {
    const events = readFileSync(join(dir, file), "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l));
    const end = events.find((e) => e.type === "end");
    return { file, end, summary: end?.summary ?? summarizeEvents(events), meta: events.find((e) => e.type === "meta") };
  });
  const lines = [
    "# 演练摘要（rehearsal outside AGH）", "",
    "**rehearsal outside AGH (direct API), same plugin tools and kernel; not the AGH run.**", "",
    "- 模型通过各自厂商的 chat-completions 接口直接调用 `adapters/agh-plugin` 的同一组 `createTools` 工具，连接同一个 Python 内核（`tests/p14_science_demo/agh_host.py`，stdio JSON-RPC）。",
    "- 这不是 AGH 里的运行；AGH 里的运行见 `evidence/agh-run`（如果存在）。",
    "- 证据模式 test；数据为合成、确定性数据；批准一步由操作员脚本调用 `tools/pk_human_approve.py` 的 `decide()` 完成，记录为 `human step performed by operator script in rehearsal`，模型本身没有批准能力。",
    "- 提示词全文见 `prompt.md`；逐条消息、工具调用、结果、时间戳、用量见各 `*.jsonl`。", "",
    "| 记录文件 | 模型（接口返回） | 状态 | 工具顺序 | 选中 | 最终 alpha | 操作状态 | 提前 apply | 总 token |",
    "|---|---|---|---|---|---|---|---|---|",
  ];
  for (const r of runs) {
    const s = r.summary;
    lines.push(`| ${r.file} | ${s.api_reported_model ?? s.requested_model} | ${r.end?.status ?? "未结束"}${r.end?.success ? "（成功）" : ""} | `
      + `${s.tool_order.join(" → ")} | ${s.selected_strategy ?? "-"} | ${s.final_alpha ?? "-"} | ${s.operation_status ?? "-"} | `
      + `${s.apply_attempted_before_human_step ? "是" : "否"} | ${s.usage.total_tokens} |`);
  }
  lines.push("");
  for (const r of runs) {
    const s = r.summary;
    lines.push(`## ${r.file}`, "",
      `- 请求的模型 id：${s.requested_model}；接口返回的模型 id：${s.api_reported_model}；接口 /models 列出：${(s.api_model_ids ?? []).join(", ") || "未取得"}`,
      `- 接口调用次数：${s.api_calls}；用量：prompt ${s.usage.prompt_tokens} / completion ${s.usage.completion_tokens} / total ${s.usage.total_tokens}`,
      `- s3 状态：${s.s3_status}；s1 通过：${s.s1_passed}；s2 通过：${s.s2_passed}`,
      `- 选择理由（模型写的）：${s.select_reason ?? "-"}`,
      `- 申请交付后的审批状态：${s.approval_status_after_request}；人工步骤已执行：${s.human_step_performed}；apply.applied：${s.apply_applied}；operation_id：${s.operation_id}`,
      `- 工具报错：${s.tool_errors.join(", ") || "无"}`,
      `- 耗时：${r.end?.elapsed_s ?? "?"} s`, "");
  }
  const notes = join(dir, "notes.md");
  if (existsSync(notes)) lines.push("## 备注（人工整理：运行次数与改动）", "", readFileSync(notes, "utf8").trim(), "");
  writeFileSync(join(dir, "summary.md"), `${lines.join("\n")}\n`, "utf8");
  return runs.length;
}

function writePrompt(dir) {
  const text = [
    "# 演练使用的提示词", "",
    "rehearsal outside AGH (direct API), same plugin tools and kernel; not the AGH run.", "",
    "## system", "", SYSTEM_PROMPT, "",
    "## user（一个人在 AGH 里会输入的话）", "", USER_PROMPT, "",
    "## 人工批准之后追加的 user 消息", "",
    `${APPROVED_MESSAGE}`, "",
    "## 工具", "",
    "与 `adapters/agh-plugin/index.mjs` 的 `createTools` 完全相同（pk_state、pk_run_strategy、pk_verify、pk_compare、pk_select、pk_request_delivery、pk_apply_delivery、pk_events）；",
    "参数 schema 去掉 TypeBox 的 Kind 符号后作为 OpenAI function tools 传给接口，`tool_choice=auto`，`temperature=0`。", "",
  ].join("\n");
  writeFileSync(join(dir, "prompt.md"), text, "utf8");
}

const args = parseArgs(process.argv.slice(2));
if (args.summarize) {
  mkdirSync(args.outDir, { recursive: true });
  writePrompt(args.outDir);
  console.log(`summary.md written from ${summarizeDir(args.outDir)} transcript(s)`);
} else {
  writePrompt(args.outDir);
  const outcome = await rehearse(args);
  summarizeDir(args.outDir);
  console.log(JSON.stringify({ transcript: outcome.transcript, status: outcome.status, success: outcome.ok,
    tool_order: outcome.summary.tool_order, selected: outcome.summary.selected_strategy,
    final_alpha: outcome.summary.final_alpha, operation_status: outcome.summary.operation_status,
    usage: outcome.summary.usage }, null, 1));
  process.exit(0);
}
