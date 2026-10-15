#!/usr/bin/env node
// Records the Project Kernel workflow inside the official AGH web UI with a real model.
//
//   node record_run.mjs run      full workflow: prompt -> model tool calls -> AGH approval dialog ->
//                                 human terminal approval (real pty) -> "已批准" -> panel tour (video + screenshots)
//   node record_run.mjs gallery  screenshots only of the panel views (THEME=light|dark) for an existing session
//
// Preconditions (see README): `agh serve --port 5186` is already running in the same shell call, the
// plugin is installed/trusted/enabled, a model account is configured, and the plugin backend has been
// started once (a throw-away `agh -p "say ok"`) so the PK launcher appears.
// Configuration by environment (no secrets): PW_MODULE, AGH_URL, CLIP_NAME, FOOTAGE_DIR, SHOTS_DIR, TMPVID,
// PROMPT_FILE, APPROVE_TEXT, PK_ROOT, PK_PYTHON, KN_DIR, BUDGET_S, THEME, MODEL_LABEL.
import { mkdirSync, writeFileSync, readFileSync, copyFileSync, unlinkSync, readdirSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { join } from "node:path";

const env = process.env;
const { chromium } = await import(env.PW_MODULE ?? "playwright");
const mode = process.argv[2] ?? "run";
const BASE = env.AGH_URL ?? "http://127.0.0.1:5186/";
const NAME = env.CLIP_NAME ?? "01-deepseek-run";
const FOOTAGE = env.FOOTAGE_DIR ?? "./footage";
const SHOTS = env.SHOTS_DIR ?? "./screens";
const THEME = env.THEME ?? "light";
const BUDGET_S = Number(env.BUDGET_S ?? 140);
const APPROVE_TEXT = env.APPROVE_TEXT ?? "已批准，请执行交付";
const PROMPT = mode === "run" ? readFileSync(env.PROMPT_FILE, "utf8").trim() : "";
mkdirSync(FOOTAGE, { recursive: true });
mkdirSync(SHOTS, { recursive: true });

const VIEWS = [["overview", "20"], ["design", "21"], ["execution", "22"], ["permissions", "23"],
  ["events", "24"], ["structure", "25"], ["versions", "26"]];
const record = mode === "run";
const vdir = join(env.TMPVID ?? "/tmp/agh_vid", NAME);
const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({
  viewport: { width: 1920, height: 1080 }, locale: "zh-CN", colorScheme: THEME,
  ...(record ? { recordVideo: { dir: vdir, size: { width: 1920, height: 1080 } } } : {}),
});
await ctx.addInitScript(() => { try { localStorage.setItem("agnes-locale", "zh-CN"); } catch { /* storage off */ } });
const page = await ctx.newPage();
const t0 = Date.now();
const over = () => (Date.now() - t0) / 1000 > BUDGET_S;
const cues = { file: `${NAME}.webm`, model: env.MODEL_LABEL ?? "", video_start_wall_ms: t0, events: [] };
const flush = () => writeFileSync(join(FOOTAGE, `${NAME}.cues.json`), JSON.stringify(cues, null, 1));
const cue = (label, kind) => {
  const t = +((Date.now() - t0) / 1000).toFixed(1);
  cues.events.push({ t, label, kind, wall_ms: Date.now() });
  console.log(`[${t}s] (${kind}) ${label}`);
  flush();
};
const shot = (file) => page.screenshot({ path: join(SHOTS, file) }).catch((e) => console.log("shot failed", file, String(e).slice(0, 80)));

async function state() {
  return page.evaluate(() => {
    const vis = (e) => !!e && !e.closest("[hidden]") && getComputedStyle(e).visibility !== "hidden"
      && getComputedStyle(e).display !== "none" && e.getBoundingClientRect().width > 0;
    const dialog = document.querySelector("#approval");
    return { busy: vis(document.querySelector("#cancel")),
      approval: vis(dialog) ? dialog.querySelectorAll("button").length : 0 };
  });
}

// Waits for the model turn to end; clicks the first button ("allow once") of AGH's own approval dialog
// after a short, visible pause, like a person who read it.
async function runUntilIdle(maxMs, tag) {
  const start = Date.now();
  let sawBusy = false;
  let idleSince = null;
  let approvals = 0;
  while (Date.now() - start < maxMs && !over()) {
    const st = await state();
    if (st.approval > 0) {
      cue("AGH 弹出工具批准对话框（pk_request_delivery 永远需要批准）", "approval");
      // The open PK drawer covers the dialog's buttons (FOR-FRONTEND finding), so a person would close
      // the drawer first, decide, and open the panel again.
      const close = page.locator(".pk-drawer button.pk-icon-button", { hasText: "×" });
      if (await close.count()) await close.first().click({ timeout: 3000 }).catch(() => {});
      await page.waitForTimeout(2200);
      if (approvals === 0 && tag === "workflow") await shot("10-agh-approval-dialog-light.png");
      const allow = page.locator("#approval button").first();
      try {
        await allow.click({ timeout: 5000 });
        cue("用户点击“允许一次”", "approval");
      } catch (error) {
        cue(`点击“允许一次”失败：${String(error).slice(0, 80)}`, "error");
      }
      if (await page.locator("button.pk-launcher").isVisible().catch(() => false)) {
        await page.locator("button.pk-launcher").click().catch(() => {});
        await page.waitForTimeout(600);
      }
      approvals += 1;
      sawBusy = true;
      idleSince = null;
      await page.waitForTimeout(800);
      continue;
    }
    if (st.busy) sawBusy = true;
    if (sawBusy && !st.busy) {
      idleSince ??= Date.now();
      if (Date.now() - idleSince > 2500) return { ended: true, approvals };
    } else idleSince = null;
    await page.waitForTimeout(400);
  }
  return { ended: false, approvals };
}

async function tour(theme) {
  for (const [view, idx] of VIEWS) {
    if (over()) break;
    await page.click(`#pk-tab-${view}`, { timeout: 4000 }).catch(() => console.log("no tab", view));
    await page.waitForTimeout(2200);
    await shot(`${idx}-panel-${view}-${theme}.png`);
    cue(`面板视图：${view}`, "panel");
  }
}

try {
  await page.goto(BASE, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForSelector("#prompt", { timeout: 20000 });
  // attached, not visible: the restyled panel hides the launcher while the drawer is open
  await page.waitForSelector("button.pk-launcher", { state: "attached", timeout: 25000 });
  if ((await page.getAttribute(".pk-root", "data-open")) === "false") await page.click("button.pk-launcher");
  await page.waitForTimeout(1500);
  cue("AGH 网页界面已打开，右侧 Project Kernel 面板（启动器 PK）已加载", "panel");
  if (mode === "gallery") {
    await tour(THEME);
  } else {
    await shot("09-agh-panel-open-light.png");
    await page.click("#new");
    await page.waitForTimeout(1000);
    await page.locator("#prompt").pressSequentially(PROMPT, { delay: 8 });
    cue("用户在 AGH 对话框输入中文任务", "user");
    await page.waitForTimeout(800);
    await page.click("#send");
    cue("发送任务，模型开始调用 pk_* 工具", "tool");
    const first = await runUntilIdle(110000, "workflow");
    cue(first.ended ? "模型停下，等待人工批准" : "（超时）模型回合未在预算内结束", "answer");
    await page.click("#pk-tab-permissions", { timeout: 4000 }).catch(() => {});
    await page.locator("button.pk-button").first().click().catch(() => {});
    await page.waitForTimeout(2500);
    await shot("11-panel-permissions-pending-light.png");
    cue("面板“审批”页显示待人工审批（机器通道不能批准）", "panel");
    if (!over() && env.PK_ROOT) {
      cue("人工在终端运行 pk_human_approve（单独的终端片段）", "approval");
      const r = spawnSync("python3", [join(env.KN_DIR, "tools", "agh-sandbox", "human_approve_pty.py"),
        "--root", env.PK_ROOT, "--script", join(env.KN_DIR, "tools", "pk_human_approve.py"),
        "--python", env.PK_PYTHON, "--out", join(FOOTAGE, `${NAME}-terminal.json`)], { encoding: "utf8" });
      console.log((r.stdout ?? "").slice(-900));
      cue(`终端审批结束（退出码 ${r.status}）`, "approval");
      await page.locator("button.pk-button").first().click().catch(() => {});
      await page.waitForTimeout(2500);
      await shot("12-panel-permissions-approved-light.png");
      cue("面板刷新：审批状态已变为 approved", "panel");
      await page.locator("#prompt").pressSequentially(APPROVE_TEXT, { delay: 40 });
      await page.waitForTimeout(500);
      await page.click("#send");
      cue(`用户告诉模型：${APPROVE_TEXT}`, "user");
      const second = await runUntilIdle(50000, "apply");
      cue(second.ended ? "模型调用 pk_apply_delivery 并回报结果" : "（超时）交付回合未结束", "answer");
      await shot("13-agh-final-answer-light.png");
    }
    await tour("light");
  }
} catch (error) {
  console.log("ERROR", String(error).slice(0, 400));
  cue(`脚本错误：${String(error).slice(0, 120)}`, "error");
}
const duration = +((Date.now() - t0) / 1000).toFixed(1);
await ctx.close();
if (record) {
  const files = readdirSync(vdir).filter((f) => f.endsWith(".webm"));
  // copy, not rename: the footage folder is usually on another device than the temp dir (EXDEV)
  if (files.length) { copyFileSync(join(vdir, files[0]), join(FOOTAGE, `${NAME}.webm`)); unlinkSync(join(vdir, files[0])); }
  cues.duration_s = duration;
  flush();
}
await browser.close();
console.log(`done in ${duration}s`);
