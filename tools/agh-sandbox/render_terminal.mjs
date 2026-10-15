#!/usr/bin/env node
// Replays a recorded pty transcript (output of human_approve_pty.py) as a terminal-styled page and
// records it as its own clip. The text and the timing are the real ones; only the window is drawn.
//   node render_terminal.mjs <transcript.json> <out.webm>
import { readFileSync, mkdirSync, readdirSync, copyFileSync, unlinkSync } from "node:fs";
import { join, dirname } from "node:path";

const { chromium } = await import(process.env.PW_MODULE ?? "playwright");
const [src, out] = process.argv.slice(2);
if (!src || !out) { console.error("usage: render_terminal.mjs <transcript.json> <out.webm>"); process.exit(2); }
const data = JSON.parse(readFileSync(src, "utf8"));
const ANSI = /\x1b\[[0-9;?]*[A-Za-z]/g;
const chunks = data.chunks.map(([t, text]) => [t, text.replace(ANSI, "")]);
const last = chunks.length ? chunks[chunks.length - 1][0] : 1;
const html = `<!doctype html><meta charset="utf-8"><style>
html,body{margin:0;height:100%;background:#0d1117;color:#e6edf3}
.win{margin:90px auto 0;width:1500px;border-radius:12px;overflow:hidden;box-shadow:0 20px 60px #000a;border:1px solid #30363d}
.bar{background:#161b22;padding:14px 20px;font:16px "Noto Sans CJK SC",sans-serif;color:#9da7b3;display:flex;gap:10px;align-items:center}
.dot{width:13px;height:13px;border-radius:50%;display:inline-block}
pre{margin:0;padding:26px 30px;min-height:620px;font:25px/1.55 "Noto Sans Mono CJK SC","DejaVu Sans Mono",monospace;white-space:pre-wrap;background:#0d1117}
.cur{display:inline-block;width:14px;height:28px;background:#e6edf3;vertical-align:-5px;animation:b 1s steps(1) infinite}
@keyframes b{50%{opacity:0}}
.note{width:1500px;margin:18px auto;font:17px "Noto Sans CJK SC",sans-serif;color:#8b949e}
</style>
<div class="win"><div class="bar"><span class="dot" style="background:#ff5f56"></span><span class="dot" style="background:#ffbd2e"></span><span class="dot" style="background:#27c93f"></span>
<span style="margin-left:14px">人工审批终端（Linux pty）· ${data.command.replace(/[<>&]/g, "")}</span></div>
<pre id="t"></pre></div>
<div class="note">真实终端会话：由 tools/agh-sandbox/human_approve_pty.py 以人工节奏键入摘要前 8 位；审批由内核 approval.decide 完成。窗口样式为示意。</div>
<script>
const chunks=${JSON.stringify(chunks)};
let lines=[""],col=0;
const put=(c)=>{if(c==="\\n"){lines.push("");col=0}else if(c==="\\r"){col=0}else if(c==="\\b"){col=Math.max(0,col-1)}else{const l=lines[lines.length-1];lines[lines.length-1]=l.slice(0,col)+c+l.slice(col+1);col++}};
const draw=()=>{document.getElementById("t").innerHTML=lines.join("\\n").replace(/&/g,"&amp;").replace(/</g,"&lt;")+'<span class="cur"></span>'};
lines=["$ ${data.command.replace(/[\\"`$]/g, "")}"];lines.push("");col=0;draw();
const start=performance.now()+1200;
chunks.forEach(([t,text])=>setTimeout(()=>{for(const c of text)put(c);draw()},1200+t*1000));
window.__done=1200+${last}*1000+3000;
</script>`;
// one temp dir per output file, so two renders can never pick up each other's video
const vdir = "/tmp/agh_vid/terminal-" + out.replace(/[^A-Za-z0-9]+/g, "_").slice(-60);
mkdirSync(vdir, { recursive: true });
const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 },
  recordVideo: { dir: vdir, size: { width: 1920, height: 1080 } } });
const page = await ctx.newPage();
await page.setContent(html);
const total = await page.evaluate(() => window.__done);
await page.waitForTimeout(total);
await page.screenshot({ path: out.replace(/\.webm$/, ".png") });
await ctx.close();
const f = readdirSync(vdir).filter((x) => x.endsWith(".webm")).sort().pop();
mkdirSync(dirname(out), { recursive: true });
copyFileSync(join(vdir, f), out); // copy, not rename: other device (EXDEV)
unlinkSync(join(vdir, f));
await browser.close();
console.log("terminal clip", out, (total / 1000).toFixed(1) + "s");
