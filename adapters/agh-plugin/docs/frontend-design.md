# AGH 前端插件化接入：设计与执行规格

面向执行者（GPT）。本文自包含：目标、已核实事实、未核实缺口、视图清单、分阶段步骤、验收与红线。先读"状态"和"红线"，再动手。

## 1. 状态（执行结果：2026-10-13）

已完成：
- `adapters/agh-plugin/index.mjs` 提供 11 个只读查询服务和 `defaults.registry`；真实演示宿主 RPC 已校对，服务检查 9 项通过。
- `KernelSession.queryEnvelope` 保留完整查询元数据；旧 `query` 继续只返回 `data`。
- `client/agnes.client.json` 白名单、单文件 ESM 构建、十个双语主题视图、可见时轮询、退避和 CSP 无内联样式检查均完成。
- 独立 Chromium 检查通过；隔离 AGH 实例完成安装、信任、启用并运行。AGH Web shell 未配置模型和活动会话，服务调用限制已如实记录。

仍未完成：
- 阶段 2 的浏览器写入、DSH 审批详情和需求报单交接。
- 视频音画合成；当前交付画面和解说词。

## 2. 目标与边界

把内核的全部可展示能力做成 AGH 里的一个多视图面板，要体现层级设计、动态效果、用户体验和执行逻辑。第一阶段只读，不新增写入通道。

用户点名的 9 个视图：结构树可视化、需求报单交接、权限申请弹出、设计流分发执行、用户知识库建立、错误统计、skill 创建评分、环境检查、版本管理。另加总览。

每个视图的数据必须带来源标签，只能是四种之一：
- `实时`：来自内核 RPC 查询，已注册可调用。
- `文档声明`：来自磁盘上的文档（registry.json 等），不是运行读数。
- `派生`：前端对实时数据做聚合，不是内核读数。
- `设计预览`：内核尚无对应能力，用示例数据演示形态，界面上必须明确标注，不得与实时数据混排。

## 3. 已核实事实（附出处）

### 3.1 AGH 扩展点（来自 AGH 源码调研）
- 包清单 `package.json` 的 `agnes.plugins` 与 `agnes.clientDescriptors` 用同一个 `rowId` 绑定，现有适配器已照此写好。
- 前端描述 `client/agnes.client.json` 的 `client` 段字段：`entry`、`styles`、`slots`、`slotCatalogVersion`、`services`、`projections`、`publicConfig`。
- 入口是原生 ESM，导出 `apply(ctx, config)`。`ctx` 有 `slots`、`agnes.services.call`、`commands`、`session`、`theme`、`locale`、`resources`（`packages/web-client/src/client-module.ts:28-41`）。
- `ctx.agnes.services.call(name, input)` 要求：服务名在 `config.services` 白名单里，且当前有活动会话（`client-module.ts:82-89`）。
- 宿主 import map 只提供 6 个外部模块：`react`、`react/jsx-runtime`、`react-dom`、`react-dom/client`、`@agnes/cordis`、`@agnes/web-client`（`packages/web-client/src/externals.ts:5-12`）。`antd`、`zustand` 不可用，不要依赖。
- 资源只允许 js/mjs/css/map，单文件 4MB，总量 16MB；描述文件不能 import 包外模块，所以多文件必须先打成单文件（`packages/package-manager/src/client-assets.ts:12-14`）。
- 当前可挂载的槽位：`workbench.panel`（list 型，追加到 `#main-content`）；使用 DSH 槽位须在描述里写 `slotCatalogVersion: "dsh-client-slots/v1"`。相关槽位：`conversation.approval.detail`、`conversation.input.permission`、`shell.overlay`、`sidebar.right.pane.tab`、`settings.section`。
- i18n：`ctx.locale.register(namespace, { en: {...}, 'zh-CN': {...} })`，只支持这两种语言，缺失回落英文；`ctx.locale.bind(namespace)` 返回 `t(key, vars)`，变量用 `{name}` 插值（`packages/web-client/src/services.ts:511-598`）。
- 主题：`ctx.theme.theme` 取当前主题，`subscribe`/`getSnapshot` 可接 `useSyncExternalStore`。
- CSP：`script-src 'self'`，`style-src 'self'`，无 unsafe-inline（`packages/web/src/theme-boot.ts`）。

### 3.2 内核查询的真实数据形状（来自 `src/project_kernel/data/queries/service.py`、`watermarks.py`、`links.py`）
所有 `env.finalize` 的查询返回信封：`query`、`as_of_seq`、`projection_version`、`computed_at`、`source_watermarks`、`freshness{as_of_seq, store_head_seq, projection_lag_seq, projection_stale, source_state, state}`、`completeness`（complete/incomplete/unknown）、`gaps[]`、`required_missing[]`、`next_page_token`、`data`。2026-10-13 已通过真实演示宿主 RPC 校对；部分查询还在信封顶层重复业务字段，消费者读取 `data`，完整元数据由服务放在 `meta`。

| 查询 | `data` 字段 |
| --- | --- |
| `project.overview` | `object_counts{类型:数量}`、`phases{阶段:数量}`、`blockers[]`、`source_gaps[]`、`recent_changes`、`last_commit_seq`、`completeness` |
| `attempts.compare` | `attempts[]{attempt_id, packet_id, strategy_id, status, mode, execution_handle_id, exit_code, verification_result, revision_count, cost}`、`comparable_groups`、`comparability{comparable, reason}`、`failures_retained[]`、`cost{reported, unknown, deduplicated, total, completeness}`、`selected{attempt_id, basis, reason, cost}` 或 null |
| `approvals.queue` | `queue[]{approval_id, snapshot_id, snapshot_digest, status, head_version, expires_at, commit_seq}`、`count`、`status_filter`、`pending_count`。分页用 `page_token` |
| `project.timeline` | `events[]`，每项 `kind` 为 `revision`/`head`/`event`，并带 `commit_seq`、`object_type`、`object_id`、`revision_id`、`event_type` 等；`count`。新到旧排序，可分页；Python 方法有 limit，但冻结 RPC payload 不接受 limit，目前 RPC 使用默认页长 |
| `project.trace` | `root{node_id, object_type, object_id, revision_id}`、`direction`、`max_depth`、`truncated`、`nodes[]{node_id, object_type, object_id, revision_id, exists, relation, depth}`、`edges[]{from, to, relation, path}`、`node_count`、`edge_count`。`root_ref` 必须是完整 ObjectRef；`max_depth` 1–20 |
| `requirements.coverage` | `denominator`、`covered`、`uncovered[]`、`not_applicable`、`not_applicable_ids[]`、`requirements[]{object_id, link_count, linked_packets, coverage, not_applicable, reason}` |
| `environment.report` | `data_state`（ok/no_data/source_failed）、`snapshot`、`facts[]{requirement, required_version, installed_version, path, state, detail}`、`satisfied/missing/unknown/too_old/not_checked[]`、`checked_at`、`freshness_state` |
| `operation.status` | `operation_id`、`operation_kind` 加该操作的 payload |
| `events.read` | `data` 是数组 `[{commit_seq, event_index, event_type, event_schema, object_refs, command_id}]`。QueryService 方法返回数组，bootstrap 在 RPC 层包装完整读取信封 |

真实探针已确认 `client.query` 直接返回 RPC 信封。`KernelSession.query` 保持只返回 `.data`，新增 `queryEnvelope` 提供完整信封供浏览器服务使用（见 5.2）。

### 3.3 现有面板的两个已知错误（来自源码对照，需修）
- `approvals.queue` 的列表在 `data.queue`，现有面板读 `data.items` 或把 `data` 当数组，所以审批队列永远显示为空。
- `phaseOf` 用 `a.verification || a.checks || a.passed` 判断验收阶段，真实字段是 `verification_result`。

### 3.4 文档类数据来源
- `docs/modules/registry.json`：`nodes[]{node_id, document, node_kind, navigation_parent, depends_on[], related_to[], conversation_refs[]}`，共 23 个节点；根 `K-ROOT`，下有 `K-CORE`（9 个子节点）、`K-DATA`（6 个）、`K-EXTENSIONS`（4 个）。
- `docs/records/skills/registry.json`：`skills[]{skill_id, path, current_version, versions[]{version, status, validation_status, source_revision, scope{applies_to, prerequisites, exclusions}, review_refs, evidence_refs}}`，目前 2 个 skill。该文件里没有四维分值字段。
- 四维评分定义在 `docs/records/skills/assessment-template.md`：`correctness`、`applicability`、`reuse_benefit`、`maintainability`，取值 0/1/2/null，不计平均总分，不评价用户。评分记录是 Markdown 文档，没有 RPC。
- 用户画像是 Markdown（`docs/records/user-learning-profile.md`），描述式，不评分。

## 4. 未核实缺口（执行者必须先处理或如实标注）

1. 内核响应的真实形状：用探针对 8 个查询抓一次真实响应，对照 3.2 修正。探针思路：用适配器自己的 `KernelSession` 启动演示宿主（`tests/p14_science_demo/agh_host.py`，根目录必须在系统临时目录或 `.validation-tmp` 下），逐个 `session.query`，结果写成 JSON。
2. esbuild 是否可用：AGH 检出里有 `node_modules/.pnpm/esbuild@0.28.2`，是否能直接 `require` 未验证。
3. `workbench.panel` 在页面布局里是否可见、会不会挤占对话区：未在真实浏览器验证。
4. React 通过 CSSOM 设置 `style` 对象是否被 CSP 允许：未验证。本规格要求不用 `style`，改用类名。
5. 后端 effect 服务如何注册（浏览器写入通道）：`registerEffect` 存在，后端注册方式未找到。因此第一阶段不做浏览器写入。
6. DSH 槽位（`conversation.approval.detail`、`shell.overlay`）的渲染语义和入参未读：第二阶段前先读槽位目录。
7. 演示宿主种子状态从 `dispatch_ready` 开始，没有需求/设计阶段的实时过程；"从空项目演示需求报单"需要宿主改造，不在第一阶段。

## 5. 架构决策

### 5.1 形态
单个 `workbench.panel`，内部分页签。理由：已验证的槽位只有这一个，多槽位是否支持没核实。源码放 `client/src/`，用 esbuild 打成单文件 `client/index.js`，把 6 个宿主外部模块标成 external。样式拆成一个或多个 CSS 文件，`styles` 里列出。

打包命令参考（路径需先验证）：
```
esbuild client/src/main.jsx --bundle --format=esm --jsx=automatic ^
  --external:react --external:react/jsx-runtime --external:react-dom ^
  --external:react-dom/client --external:@agnes/cordis --external:@agnes/web-client ^
  --outfile=client/index.js
```

### 5.2 后端改动
- 让 `KernelSession.query` 支持返回完整信封：新增 `queryEnvelope(query, payload, asOf)`，原 `query` 保持返回 `.data`，避免破坏现有工具和测试。`pk.*` 服务返回 `{ meta: { as_of_seq, freshness, completeness, gaps, required_missing }, data }`。注意同步 `outputSchema`（现在是开放对象）。
- 新增 `pk.skills`（读 skills registry，标 `文档声明`）。`defaults` 里加对应路径环境变量。
- 所有服务继续只读。文档类服务读不到文件时返回明确错误，不返回空数据冒充。
- 为版本回看预留：服务可选接收 `as_of_seq`，透传给 `client.query` 的 `asOfSeq`（协议已支持）。

### 5.3 前端分层
```
client/src/
  main.jsx            apply(ctx, config)，注册 workbench.panel、locale
  app/Shell.jsx       标签页、顶栏（连接状态、水位、完整度）、数据来源图例
  data/usePoll.js     轮询与退避，返回 {phase, data, meta, error}
  data/services.js    封装 ctx.agnes.services.call
  i18n/messages.js    en 与 zh-CN 两套文案
  views/              每个视图一个文件（见第 6 节）
  parts/              Badge、SourceTag、EmptyState、Stagger 等
  styles/*.css
```
状态管理用 React 自带 hooks，不引入 zustand。

### 5.4 体验与动效约束
- 动效全部写在 CSS：入场错峰（用 `.pk-i-0` 到 `.pk-i-15` 这类类名设置延迟）、阶段圆点脉冲、结构树展开、依赖边流动（SVG `stroke-dashoffset`）、数字变化过渡、弹层滑入。不使用 `style` 属性。
- 必须尊重 `prefers-reduced-motion`。
- 颜色取宿主主题变量并带默认值；订阅 `ctx.theme` 切换亮/暗。
- 每个视图有四种状态且视觉可区分：加载中、无数据（`no_data`，不等于失败）、不可用（含原因）、数据过期（`freshness.state != fresh` 或 `completeness != complete` 时显示缺口）。
- 轮询只在面板可见时进行，退避到最长约 10 秒；连接失败要明确提示"需要先选择会话并启用 services 能力"。
- 所有文案走 locale，不写死中文。

## 6. 视图清单

每项给出：数据来源与标签、展示内容、动效与交互、不可做的事。

1. 总览（实时）
   - `pk.overview` + `pk.compare` + `pk.approvals`。执行流程 6 步条（派发、尝试、验收、选择、审批、交付），当前阶段按真实字段推断（修 3.3 两处错误）；`object_counts` 与 `phases` 做计数卡片；`blockers` 列表；顶栏显示 `as_of_seq`、`freshness.state`、`completeness`。
   - 动效：当前步骤脉冲；计数变化数字过渡。
2. 结构树可视化（文档声明 + 实时）
   - 模块树：`pk.tree`，标 `文档声明`，按 `navigation_parent` 画层级树，节点显示 `node_kind`；可展开/折叠；选中节点高亮其 `depends_on` 与 `related_to`（两种线型区分）；前端据 `depends_on` 计算入度/出度，标 `派生`，旁注"文档声明依赖，非运行读数"。
   - 业务对象图：`pk.trace`，以任务为根，标 `实时`；`truncated` 为真时显示"图不完整"。节点按 `object_type` 分色，边按 `relation` 标注。
   - 不要把两张图混成一张。
3. 需求报单交接（实时，有限）
   - `pk.coverage` + `pk.trace`。展示需求 → 方案 → 派发包 → 尝试的链路和覆盖率（`covered/denominator`，`not_applicable` 单列，零链接需求保留在分母内）。
   - 种子状态已在 `dispatch_ready`，所以本视图展示"已交接的结果与追溯"，不演示从空开始的过程；如要演示过程，需要宿主改造（见 4.7）。界面不得暗示实时的需求录入。
4. 权限申请弹出（实时，仅展示）
   - `pk.approvals` 的 `pending_count > 0` 时，从面板顶部滑入一个弹层，显示 `approval_id`、`snapshot_id`、摘要前缀、`expires_at` 倒计时、`head_version`。
   - 没有批准/拒绝按钮。弹层文案说明批准只能在独立人工入口完成。不得调用 `approval.decide` 或任何人工专属命令。
   - 两层权限不要混淆：AGH 工具层 `requiresApproval`（`pk_request_delivery` 已设置）由宿主弹窗处理；内核层 `approval.decide` 绑定快照摘要、只走人工入口。DSH 槽位里的审批详情放第二阶段。
5. 设计流分发执行（实时）
   - `pk.compare`：按策略列出 attempt，状态用颜色与文字双编码（completed/failed/unknown/running 等）；`unknown` 显示"提供方结果未证实，不自动重跑，不当作成功"；`selected` 显示选择理由；`comparability` 不可比时说明原因；成本 `unknown` 时显示"未上报不等于零"。
   - 交付状态：对已有 `operation_id` 用 `pk.operation` 查，显示 prepared、claimed、applying、applied、failed、unknown 的状态机位置。
   - 不提供"运行"按钮（第一阶段无写入）；提示"在会话中让助手执行 `pk_run_strategy`"。
6. 用户知识库建立（设计预览）
   - 内核 knowledge 模块未接核心 RPC，corpus 默认关闭，用户画像是 Markdown。整页标 `设计预览`，用示例数据展示：知识树形态、上下文预算与 mandatory/optional 取舍、精确来源与摘要。不得出现任何看起来像实时统计的数字，示例数据要明显标记。
7. 错误统计（派生）
   - 用 `pk.compare` 的 `failures_retained` 与状态分布、`pk.overview` 的 `blockers`、`pk.timeline` 的事件类型分布聚合出图表。每张图下标 `派生，非内核读数`。内核没有专用统计查询。
   - 可作图的类型：状态分布条形图、失败/未知时间序列。图表用纯 SVG，遵守无内联样式。
8. Skill 创建与评分（文档声明 + 设计预览）
   - 列表：`pk.skills`，标 `文档声明`，显示 skill_id、当前版本、各版本 `status` 与 `validation_status`、适用范围与排除项。
   - 评分：registry 里没有分值，默认显示四维都是"未评估(null)"。另放一个"评估表单形态预览"，标 `设计预览`，演示 0/1/2/null 四维填写，不计算总分，不评价用户。
9. 环境检查（实时）
   - `pk.environment`：五类分桶（satisfied、missing、unknown、too_old、not_checked）做分组展示，显示 requirement、required/installed 版本、path、`checked_at`、`freshness_state`。`data_state` 为 `no_data` 时说明"尚无探测记录"，与 `source_failed` 分开显示。
10. 版本管理（实时）
   - `pk.timeline`：按 `commit_seq` 倒序的时间线，三类条目（revision、head、event）用不同图标；按 `object_type` 过滤。
   - 水位回看：一个滑块选 `as_of_seq`，面板其余视图随之回看（依赖 5.2 的 `as_of_seq` 透传）；回看时顶栏明确标"历史视图，非当前"。
   - 规则版本（`rules.save/preview/publish`）第一阶段不做，写入通道未就绪。
11. 审计与归档（可选，实时）
   - `events.read` 事件流（沿用现有，注意返回是数组）。`archive.status` 需要 `manifest_ref`，演示数据里没有，先不做。

设计预览项统一用一个 `SourceTag` 组件渲染，样式与实时项明显不同（虚线边框、水印"设计预览"）。

## 7. 分阶段步骤

阶段 0，摸清事实（必须先做）：
1. 运行探针，保存 8 个查询的真实响应，把差异回写到本文 3.2 和 6。
2. 验证 esbuild 能在本机运行；验证 `client.query` 返回形状。

阶段 1，只读多视图（本规格的主体）：
1. 后端：`queryEnvelope`、`as_of_seq` 透传、`pk.skills`，并更新 `agnes.client.json` 的 `services` 白名单（补全 `pk.timeline`、`pk.trace`、`pk.coverage`、`pk.environment`、`pk.operation`、`pk.tree`、`pk.skills`）。
2. 前端：按 5.3 搭骨架，先做 Shell 与总览，再逐个视图；修 3.3 两处错误。
3. 打包为单文件，核对体积远小于 4MB。
4. 更新测试（见第 8 节）。
5. 在隔离的 AGH 实例里安装验证（见第 8 节）。

阶段 2，增强（单独评估后再做，不要混入阶段 1）：
- DSH 槽位里的审批详情与全局弹层（先读槽位目录与语义）。
- 写入工具：需求、设计、派发、环境探测、规则，走工具通道而非浏览器；浏览器 effect 通道待后端注册方式核实。
- 宿主改造以支持从空项目演示需求报单。
- 若内核将来暴露知识库/统计/耦合度量，再把对应预览切换为实时。

## 8. 验收与测试

- 单元：保留 `test/tools.test.mjs`；新增各 `pk.*` 服务的输入校验与错误路径测试（文档类服务文件缺失时返回错误）。
- 渲染：更新 `test/panel.test.mjs`。该测试现在靠字符串替换 `import ... from 'react'`，打包后失效，改为打包时把 `react` 别名到 AGH 检出里的 React 路径，或改用 esbuild 产出的测试版本。保留的断言：不渲染任何批准按钮；SSR 输出不含 `style=`；各视图标题与来源标签存在。
- 内容红线断言：整页不得出现"已通过验收"字样；设计预览项必须带"设计预览"标签。
- 安装验证：只在隔离实例里做，流程为 `package inspect file:<dir>` → `install` → `package trust <id> <integrity> <capHash>` → `package enable <id>` → `package status`；`docs/local-dev.profile.yaml` 要放进隔离实例 `profiles/local-dev/profile.yaml`，能力上限必须含 `services`。迭代时改版本号后走 Web 的"从新来源更新"。不要改用户的日常实例（`D:\agnes`）。
- 如实报告：没在真实浏览器里看过的，写"未在浏览器验证"。

## 9. 红线

1. 内核状态只能写"自测通过"，`accepted_g2`，`release_approved=false`；不得写"已通过验收"或"已发布"。
2. 界面不提供、也不调用任何批准/拒绝/撤销命令；不得让弹层或按钮绕过人工入口。
3. 设计预览与实时数据必须视觉分离并明确标注；示例数据不得伪装成读数。
4. 证据模式是 test，隔离级别 `directory_only`，不是操作系统沙盒；平台只能说"可适配"，自有 stdio JSON-RPC 不是 MCP。
5. 不改 AGH 源码，不改日常 AGH 实例，不提交、不推送（除非用户另行要求）。
6. 不在 `publicConfig` 里放凭据形状的键。
7. 不用内联样式；动效写在 CSS。
8. 无法验证的行为不得声称已验证。

## 10. 需要的默认决策（已替用户选定，可被推翻）
- 采用单面板分页签，不做多槽位。
- 第一阶段只读，写入走智能体工具。
- 设计项一律做"设计预览"，不扩内核去补能力。
- 中英文文案都提供，默认 zh-CN。
