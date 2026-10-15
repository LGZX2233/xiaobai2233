# 真实 AGH 运行记录（agh-run）

## 这是什么，什么是真的
官方 AGH 打包运行时（`agh 0.0.0`，node 24.22.0，协议 `_agnes/v1`）在 **Linux 沙箱** 里运行，由自动化浏览器（Playwright Chromium，1920x1080）驱动网页界面。
**真实的部分**：模型调用（DeepSeek `deepseek-flash`、Agnes AI `agnes-3.0-flash`，API 自报的模型 id）、AGH 的工具调用与批准对话框、内核账本记录、人工审批终端（Linux 伪终端里运行 `tools/pk_human_approve.py`，按快照摘要前 8 位键入）。
**不是**：不在 Windows 上；不是真人手点（浏览器由脚本操作）；演示数据是合成且确定的；证据模式 `test`；隔离是 `directory_only`；stdio JSON-RPC 不是 MCP；插件只在 AGH 上验证。
终端片段 `03/04-terminal-*.webm` 是真实伪终端会话的回放（文字与节奏取自录制的转录），窗口外观是绘制的。

## 两次运行（各约 75 s，独立记录）
| 运行 | 模型（API 自报） | 视频 | 记录目录（仓库内） |
|---|---|---|---|
| DeepSeek | `deepseek-flash`（AGH 目录名 "DeepSeek V4.1 Flash"，API 不使用这个名字） | `footage/01-deepseek-run.webm` 75 s | `evidence/agh-run/20261015-0921-deepseek-flash/` |
| Agnes AI | `agnes-3.0-flash` | `footage/02-agnes-run.webm` 79.7 s | `evidence/agh-run/20261015-0921-agnes-3.0-flash/` |

工具调用链（两次一致）：`pk_state` → `pk_run_strategy` s3/s1/s2 → `pk_verify` s1、s2（Agnes 那次还对 s3 调了 `pk_verify`，返回 `skipped`）→ `pk_compare` → `pk_select s2` → `pk_request_delivery`（AGH 弹出批准对话框，点“允许一次”）→ 模型停下 → 人在终端批准 → 用户输入“已批准，请执行交付” → `pk_apply_delivery` → `operation_status: applied`。s3 为 `unknown` 并被保留、不重跑；s1 `alpha_fit 0.3500` 验证失败；s2 `0.37286` 通过。
每个记录目录含：`tool-chain.md/json`（时间、工具、参数、结果摘要）、`ledger-events.md`（账本事件）、`human-approval-terminal.txt`、`session.agnes.jsonl` 与 `session.html`（`agh export` 的脱敏导出）、`versions.json`。

## 截图
`screens/`：DeepSeek 运行 09、10（AGH 批准对话框）、11/12（面板审批页待批/已批）、13、20–26（七个面板视图，light 与 dark）；`screens/agnes/`：Agnes 运行的同组 light 截图。

## 复现命令（全部在 tools/agh-sandbox/，无密钥）
一个沙箱 bash 调用结束时所有后台进程都会被杀，所以每次调用要自己先起 `agh serve`。
```
export PATH=<node24>/bin:$PATH TMPDIR=/tmp AGH_HOME=/tmp/agh_home AGNES_PROFILE=local-dev
export PK_KERNEL_ROOT=<kernel_next> PK_PYTHON=<python> PK_ROOT=/tmp/agh_pk/run1
bash tools/agh-sandbox/bootstrap_home.sh /tmp/agh_home deepseek deepseek-flash /tmp/deepseek_key <kernel_next>   # 安装插件 + 配账号（密钥只从文件读，输出已遮蔽）
agh serve --port 5186 --profile local-dev --cwd <kernel_next> --data-dir $AGH_HOME/data &                          # 必须先于其他 agh 命令
agh -p "say ok" --cwd <kernel_next> < /dev/null                                                                    # 预热，让 PK 启动器出现
node tools/agh-sandbox/record_run.mjs run          # 需要 PW_MODULE、PROMPT_FILE、FOOTAGE_DIR、SHOTS_DIR、KN_DIR、PK_ROOT、PK_PYTHON
python3 tools/agh-sandbox/build_records.py --help  # 生成本目录里的记录
node tools/agh-sandbox/check_tool_results.mjs <kernel_next>   # 不经 AGH 检查工具结果是否是合法 JSON
```
`install_plugin.py`（伪终端装插件）、`configure_provider.py`（驱动 `agh config` 向导）、`human_approve_pty.py`、`render_terminal.mjs` 同目录。`provider-setup-*.txt`、`provider-probe.txt` 是配置与探测记录。`agh-facts.md` 回答环境变量/工作目录/进程/安装副本位置的问题。

## 限制与未验证项（照实写）
- **沙箱专用的绕过**：仓库里 `adapters/agh-plugin/index.mjs:186` 在 s1/s2 的 `pk_run_strategy` 结果里放了 `note: undefined`，AGH 的 JSON 校验（`inspectJsonData`）拒绝 `undefined`，该调用在 AGH 里被记为 `TOOL_OUTCOME_UNKNOWN`（实际内核已记录尝试；第一次无头运行就是这样，见 `FOR-BACKEND`）。本次录制用的插件副本把 `undefined` 改成 `null`，**仓库本身没有改**。仓库修好之前，Windows 用户会遇到同样的错误。
- 无头 `agh -p` 没有批准提示器，`pk_request_delivery` 会被拒绝（`APPROVAL_REJECTED`）；完整流程要走网页或 TUI。
- 面板抽屉打开时会盖住 AGH 的批准对话框按钮（第一次录制点击超时，批准对话框过期，模型重发了请求）。录制脚本在点击前先关闭抽屉。
- 第一次标成 Agnes 的录制实际用的是 `deepseek-flash`（切换默认账号不改变模型），已丢弃；重录前禁用了 DeepSeek 账号，导出的 `cost/ledger` 里模型只有 `agnes-3.0-flash`。
- Agnes 运行前的预热 `agh -p` 报 `E_PRESET_UNRESOLVED: selected model is absent from contract catalog`，但网页会话用 Agnes 正常完成；原因没有追查。
- `agh doctor provider --probe` 两个账号的联通与最小推理都通过，但 `models[].observed=false`（`E_PROVIDER_MODEL_MISMATCH`），原因未查。
- `01-deepseek-run.webm` 原文件尾部损坏（17 MiB 处被截断），已按 75 s 重新封装（实际录制 74 s），已确认可解码。
- 面板里 `pk.compare` 行没有 `alpha_fit`/原因，只有工具结果里有（前端备注）。
