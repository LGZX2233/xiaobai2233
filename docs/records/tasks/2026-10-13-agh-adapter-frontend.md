---
record_id: CCR-TASK-AGH-ADAPTER-FRONTEND
record_version: 2
updated_at: 2026-10-13
timezone: Asia/Shanghai
source_revision: 16410c9fbf4a8507445b4603e371e701614e4499
source_worktree: adapters/ 未跟踪；adapters/agh-plugin/index.mjs 本任务有修改；src/project_kernel/bootstrap.py 工作树有修改，非本任务所改
status: in_progress
requirement_ids: []
module_ids: []
acceptance_status: self_tested
---

# 内核接入 AGH：前端插件化与演示视频进度记录

## 目标与范围

比赛要求成果通过 Agnes Harness（AGH）运行，截止时间 2026-10-15 12:00（见项目记忆）。用户在本任务中依次提出：

- 查找 `D:\bisai` 的修改记录。
- 为比赛做展示视频，讲内核设计思路和创新，不提及详细代码实现；随后明确"不要 ppt，要视频"。
- 先完成内核对 AGH 的适配和前端改造，要求体现结构树可视化、需求报单交接、权限申请弹出、设计流分发执行、用户知识库建立、错误统计、skill 创建评分、环境检查、版本管理，并注意动态效果、层级设计、用户体验和执行逻辑。
- 前端设计写好后交给 GPT 实现；先把进度记录为文档（即本记录）。

排除项：未提交、未推送；未改 AGH 源码；未改日常 AGH 实例。

## 输入与来源

- 内核源码基线 `16410c9fbf4a8507445b4603e371e701614e4499`。
- 内核文档：`docs/architecture/`、`docs/modules/registry.json`、`docs/records/skills/`。
- AGH 源码 `D:\bisai\agnes-harness-main`，本地构建产物 `D:\bisai\agh-build\runtime`（`build.log` 显示 `build:local` 退出码 0）。
- 现有适配器 `adapters/agh-plugin/`（7 个工具、4 个查询服务、单页只读面板）。

## 技术选择与结果

已落盘：

| 产物 | 位置 | 状态 |
| --- | --- | --- |
| 前端设计与执行规格 | `adapters/agh-plugin/docs/frontend-design.md` | 已写成并执行 |
| 11 个只读查询服务（含 `pk.overview`、`pk.compare`、`pk.approvals`、`pk.events` 及原 6 项）和 `defaults.registry` | `adapters/agh-plugin/index.mjs` | 已实现；`node --check` 与后端服务检查通过 |
| 10 页只读面板与构建产物 | `adapters/agh-plugin/client/` | 已实现、构建并通过 SSR、轮询和浏览器检查 |
| 创新点展示测试（账本水位、未知不重放、独立复算、人工专属审批、幂等、审批失效、交付对账、只收紧的规则，加上面板用到的追溯/覆盖/环境/时间线读模型，以及模块树与 skill 索引的结构检查） | `tests/p15_innovation_showcase/test_innovation_showcase.py` | 已写成；见下方"验收与限制"中的运行记录 |
| 10 页画面与逐页解说词（约 1230 字） | `D:\bisai\demo-video\build\slides`、`build\narration`，生成脚本在 `D:\bisai\demo-video\src` | 已生成；第 3 页版式修改后重新生成，未再查看 |

选择与理由：

- 采用单个 `workbench.panel` 内分页签，因为已核实可挂载的槽位只有它。
- 第一阶段只读；写入走智能体工具，浏览器写入通道的后端注册方式未核实。
- 知识库、skill 评分、错误统计、耦合度量等内核尚无 RPC 的能力，一律做"设计预览"或标"派生"，不冒充实时读数。
- 视频画面用"设计流程示意"措辞，因为适配器图表文档写明 AGH 内真实运行结果尚未验证。

## 错误与学习资料

静态发现（读源码得出，后续已用真实服务检查复核）：

- 现有面板读 `approvals.queue` 的 `data.items`，真实字段是 `data.queue`，审批队列会恒为空。
- 现有面板 `phaseOf` 判断验收用 `verification`、`checks`、`passed`，真实字段是 `verification_result`。
- `KernelSession.query` 只返回 `.data`，信封里的 `as_of_seq`、`freshness`、`completeness`、`gaps` 丢失；界面要展示读取水位须改会话类。

被拒绝的操作（自动模式分类器拒绝，原因均为"瞬时错误"，未换途径重试）：

- 用 pip 安装 `imageio-ffmpeg==0.6.0` 到 `D:\bisai\demo-video\_ffmpeg_pkg`。
- 用 PowerShell 调 Windows 中文语音合成 10 个 WAV。
- 探针脚本写入（后来用户授权后仍有一次被拒）。
- 检查 AGH 检出里的 esbuild 能否运行。

因此：没有 ffmpeg，没有配音，没有 mp4；视频仍只交付画面和解说词。

## 验收与限制

实际运行过的检查：

- `node --check adapters/agh-plugin/index.mjs`：通过。
- 适配器后端与原工具集成检查：9 项通过。
- `npm test`：37 项通过、1 项真实 RPC 场景按测试标记跳过；无失败。
- 前端 SSR 与轮询测试：29/29 通过。
- 独立 Chromium 浏览器检查：10 个视图、真实待审批弹层、历史水位、主题、语言、隐藏暂停轮询、移动端布局均通过；`style` 属性为 0，控制台无错误。证据：`D:\bisai\kernel-agh-work\evidence\browser-results.json`。
- AGH 隔离实例：安装、精确 integrity/capability hash 信任、enable、status 均成功；`desired=enabled actual=running trusted=true`。未改日常 `D:\agnes`，未改 AGH 源码。
- `make_slides.py` 生成 10 张画面和解说词。

创新点展示测试的运行记录：

- 写好后在项目虚拟环境里跑了两次，均在我按源码推断的断言处失败，不是内核缺陷。第一次：`project.timeline` 实际按种类（revision、head、event）分段排序，而不是按提交序交错，且第一页只含 revision 和 head。第二次：冻结水位后回看总览，`completeness` 在回看时是 `incomplete`、冻结时是 `complete`，其余事实相同。
- 据此已修改两处断言（改为分页遍历时间线；比较时排除 `completeness` 并单独断言它）。
- 修改后使用项目虚拟环境运行：`D:\deepseekhannes\kernel_next\.venv\Scripts\python.exe -B -m pytest D:\deepseekhannes\kernel_next\tests\p15_innovation_showcase D:\deepseekhannes\kernel_next\tests\p14_science_demo -p no:cacheprovider -q`。结果 `..... [100%]`，p15 三项和 p14 两项全部通过；JUnit 证据：`D:\bisai\kernel-agh-work\evidence\p15-p14-final-results.xml`。
- 同一次运行还核实了：现有 `p14_science_demo` 的 2 个测试在项目虚拟环境里通过。

未验证：

- AGH Web shell 中没有配置模型和活动会话，因此隔离页面实际显示“需要先选择会话并启用 services”；独立浏览器 harness 已用真实内核服务完成面板调用验证。
- 视频的音画合成。

状态口径不变：内核为"自测通过"，`accepted_g2`，`release_approved=false`；证据模式 test，隔离级别 `directory_only`，不是操作系统沙盒；平台只称"可适配"，自有 stdio JSON-RPC 不是 MCP。本任务没有新增验收，也不继承历史 G2 接受。

附带事实：`D:\bisai` 不是版本库；`agnes-harness-main` 中除 `node_modules` 外的文件修改时间均为解压时间 17:27，没有此后被改动的源码。

## 交接与修订

下一步（不属于本次只读阶段）：

1. 阶段 2：DSH 槽位里的审批详情、写入工具、从空项目演示需求报单；需另行核实宿主写入通道。
2. 视频：当前保留画面和解说词，音画合成需用户选择配音工具。

需要用户决定：

- 是否为 Edit/Write/Bash 相关命令加权限规则，以便装 ffmpeg 和合成配音。
- 或改为用户自己录音、使用自有剪辑工具，由本任务只交付画面与解说词。
- 视频是否等真实 AGH 运行结果后再录，还是先用设计流程示意版本。

| 版本 | 日期 | 内容 |
| --- | --- | --- |
| 1 | 2026-10-13 | 首次记录：设计规格、后端查询服务、视频素材与被拒操作 |
| 2 | 2026-10-13 | 完成只读多视图、查询信封、浏览器与隔离 AGH 自测；p15/p14 共 5 项通过；保留活动会话限制与 `release_approved=false` |
