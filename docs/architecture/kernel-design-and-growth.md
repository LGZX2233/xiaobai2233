# 内核设计、问题治理与无界面接入计划

本文是 `kernel_next` 的设计说明和维护基线。它只描述独立内核、宿主适配和无界面 agent 接入；工作台或其它前端属于外部消费者，不是内核运行时的一部分。现有实现与限制以[内核现状](current-state.md)为准，本文中的“计划”不扩大历史 G2 接受范围。

## 1. 定位与边界

内核放在 DSH/AGH 等 agent 运行时旁边，承担两类职责：

1. **执行流**：把需求、方案、派发包、attempt、独立验收、候选比较、人工批准、交付和效果观察连接成可追溯流程。
2. **项目数据与统计**：保存项目身份、版本、来源、审计、制品、回执、查询水位、错误和效果统计。

模型循环、工具调用、会话、上下文压缩、skill 加载、子任务调度、宿主权限和沙盒生命周期由宿主提供。内核通过显式 provider/adapter 使用这些能力，不另起一套 agent loop，也不把界面状态当作业务事实。

核心数据链遵循四条边界：

- 每类事实只有一个拥有者；消费者只能按版本或水位投影。
- 机器检查、代理审查、人类批准和外部效果是四种事实，分别留档。
- 事实按不可变 revision、精确引用和 digest 关联；需要修订就产生新版本。
- 可选能力缺失时返回明确的禁用或能力不可用状态，不静默换路径。

## 2. 一次任务如何闭环

设计模型读取整体约束、需求和历史，形成方案与验收项；拆分阶段将方案切成模块并建立 L0 项目资料和 L1 模块资料；分发阶段冻结 execution packet，执行模型在独立 root 中并行尝试；独立 checker 根据固定输入和验收版本重算结果；收尾模型比较候选、整理依赖并提出采用建议；可信人工入口确认冻结快照；最后由 provider 执行交付并只读观察外部效果。

流程按八个阶段记录：`design → split → dispatch → execute → package/verify → review → human-confirm → apply/reconcile`。需求或约束改变时回到 split，创建新 revision；结果无法确认时保持 `unknown`，等待观察或显式对账。没有采用的候选、失败和未完成证据仍可查，不能为了生成漂亮的成功路径而删除。

上下文由 ContextResolver 按优先级装配：身份与约束 → 需求、验收和设计 → 环境、错误和依赖 → 项目资料 → 共享经验。每次装配生成 ContextManifest，记录来源 revision、选择/排除原因和预算；超过预算时报告缺口，不静默截断。模型交换和表单提交也必须引用当时读取的版本；表单暂态由宿主管理，提交后才成为内核事实。

L0/L1 双层存储把项目整体与模块局部隔开。执行模型只读自己的 L1；回到 L0 前必须通过验收、打包、去耦和人工确认。多实现包可以并存，方案、知识使用和 skill 采用独立评分，避免“尝试过”被误写成“已采用”。

## 3. 要解决的问题与治理机制

| 问题 | 内核机制 | 结果口径 |
| --- | --- | --- |
| 长对话遗忘、跨会话重跑 | 不可变账本、`as_of_seq`、ContextManifest、项目/共享记忆分层 | 模型按需读事实；历史水位可重放，成本收益仍需实测 |
| 卡死或超时任务被重复启动 | 幂等键、持久 attempt、`unknown` 结算、原回执补查 | 未知结果保留并观察，不自动重跑或把未知当失败 |
| 模型自报数字或测试结论 | 独立 checker、固定验收版本、来源和制品摘要 | 自报内容只是候选证据，不能单独通过或批准 |
| 机器检查绕过人审 | 人工命令走独立 trusted entry，批准绑定 snapshot digest | `READY` 只表示可以申请；候选变化会使旧批准失效 |
| 过程黑箱、责任不清 | 事件、审计、outbox、回执和四类事实分开写入同一 UoW | 每次判断可追到输入、版本、操作者和结果 |
| 模型“乱丢垃圾” | 受声明的执行 root、staging/ready 两段制、artifact manifest/digest、类型和路径策略、未归属输出隔离 | 模型输出先是候选制品；只有验收、去耦和批准后才能进入交付目标；临时/失败/未引用文件保留在隔离区并可清理，不进入项目主树 |
| 模块互相调用、改一处全局失效 | 领域规则、application、data、provider ports、协议和宿主 adapter 分层 | 业务逻辑不依赖文件/进程/模型 SDK；provider 可替换，事务所有权集中 |
| 新能力越加越乱 | 冻结 contracts、显式组合根、稳定模块 ID、可选插件边界、持续记录 | 新能力先有端口、事实主人和验收条件，再接入宿主；不靠复制第二套状态机成长 |

### 3.1 模型垃圾治理的最低闭环

“垃圾”包括未声明文件、脱离任务的日志、无来源的总结、重复制品以及把草稿误写成项目结论。目标不是替模型决定内容，而是让任何输出都可归属、可验证、可撤回：

1. 任务派发时声明允许的 output kind、目标相对路径、大小/数量预算和验收项；执行 root 与项目根隔离。
2. 输出先写 staging，由采集器计算真实字节摘要、来源 attempt、调用身份和 packet 版本；没有这些字段的文件进入 quarantine，不进入 ready。
3. 验收、方案收尾和去耦检查只读取 staging manifest；失败或未知的输出保留原字节和原因，禁止覆盖成功候选。
4. 只有冻结交付快照经人工批准后才调用 delivery provider。provider 只允许写批准的目标与摘要；`unknown` 只能 reconcile，不能再次 apply。
5. 任务关闭时生成清单：已采用、未采用、失败、临时、未归属和待清理。清理动作另有保留期、引用检查和审计记录，不能把“看起来没用”当作删除依据。

当前 v1 已有 staging/ready、manifest、provider、digest 和 unknown 语义，但“输出 kind/路径预算、quarantine 扫描、自动引用检查、宿主级沙盒”尚未形成完整运行闭环；这部分是后续实现项。

## 4. 模块化、低耦合与可成长性

模块边界按事实和副作用划分，而不是按页面划分：

- **contracts** 只负责 DTO、Schema、版本和摘要；不调用数据库。
- **domain** 只负责状态和规则；不访问文件、进程、SQLite 或模型 SDK。
- **application** 编排用例、授权和事务边界；不隐藏 provider。
- **data** 拥有 Store、UnitOfWork、revision/head、查询和水位。
- **provider/adapter** 承担执行、环境探测、证据、交付等外部副作用，由组合根显式注入。
- **bridge** 只负责协议分帧、句柄和调用匹配；不复制业务状态。
- **records** 维护任务、项目、术语和学习记录；它是文档工作流，不是运行服务。

维护任何新模块前先回答四个问题：事实由谁拥有？输入输出契约是什么？副作用在哪个 provider？失败和未知如何结算？跨模块调用必须通过已声明的端口或查询接口；禁止通过 UI、共享全局变量或私有 SQL 形成隐式耦合。一个 UnitOfWork 的原子边界不能因文档节点拆分而被拆成多次提交。

可成长性采用“稳定核心 + 可选能力”：核心保留身份、版本、授权、执行状态、证据、回执和查询；ContextResolver、knowledge、方案实验、脚本整理、语料、SCM 和展示都是可按能力启用的插件/消费者。每个插件必须提供 manifest（版本、输入、输出、依赖、禁用状态、迁移和验收），并能在缺失时给出 `CAPABILITY_UNAVAILABLE`。禁止为每个宿主再造一套账本、权限和审批。

已知的结构性风险是部分 application 仍直接使用 Store SQL，`ports/ports.py` 与实际消费端并非逐签名一致，组合根也尚未汇总 provider capabilities。重构时先补调用方契约和行为测试，再移动 SQL；不以一次大拆包换取不可追溯的事务变化。

## 5. 无可视化插件的标准 agent 接入（计划）

部分能力只需要被模型调用，不应依赖面板。计划把内核作为 headless agent service 和 skill 包接入任意宿主；当前自有 stdio JSON-RPC 不是 MCP，以下是兼容路线而非已完成能力。

### 5.1 标准化分层

1. **Kernel contract**：继续使用版本化 JSON Schema 定义命令、查询、错误、ObjectRef、能力声明和回执；增加 `context.manifest.read`、`model_exchange.append/read`、`artifact.inspect` 等 R1 计划接口时保持向后兼容。
2. **Agent skill manifest**：为模型提供 `project_context`、`design_dispatch`、`execute_verify`、`compare_select`、`delivery_review`、`records_reconcile` 等 skills。每个 skill 声明触发条件、最小参数、可调用命令、必需 scope、失败/未知语义、引用格式和示例；skill 只引导调用，不获得审批权限。
3. **Host adapter**：把不同 agent 框架的 session、tool call、取消、重连、来源 append/flush、模型可见日志和可信人审入口映射到 kernel contract。宿主负责模型循环和工具权限，内核负责事实、授权和效果。
4. **Transport bridges**：保留 stdio JSON-RPC 作为基线；再提供 MCP/tool-calling/HTTP 等薄桥接，桥接层只做字段映射和 framing，不复制状态。每种 transport 单独做协议、重连、超时和能力矩阵验收。
5. **No-UI operation**：没有面板时，agent 通过 skills 读取状态、提交设计/派发、启动或查询 attempt、请求验收、比较候选和形成 delivery request；人审仍走独立可信通道。所有响应携带 source revision、watermark、receipt 和下一合法动作。

### 5.2 计划阶段与验收

| 阶段 | 产物 | 必须证明 |
| --- | --- | --- |
| H0 契约盘点 | skill/command/capability 矩阵 | 无 UI 也能覆盖核心读写，禁用能力有明确错误 |
| H1 headless read | `state/context/events/trace` skills | 重启、历史水位、权限和引用可重放 |
| H2 controlled write | design/dispatch/attempt/verify skills | 幂等、取消、unknown、失败和来源 flush 均可对账 |
| H3 review and delivery | compare/select/request/reconcile skills | 机器不能批准；快照变化使批准失效；provider 效果可观察 |
| H4 framework bridges | MCP/HTTP/其它 agent 适配器 | 每个宿主单独验收，不把一个框架的通过外推到全部框架 |
| H5 growth loop | skill 版本、失败复盘、效果反馈 | skill 只在实际采用和重验后提升；共享记忆需显式批准 |

当前优先级是 H0–H2。`KnowledgeService` 尚未接入核心 RPC，`model_exchange`、实时表单、会话到版本映射、OS 级沙盒和真实宿主 lifecycle 仍需实现与行为验收；因此本节不能作为已提供的无界面插件能力清单。

## 6. 维护规则

每个实现或文档检查点更新受影响的模块节点、项目/任务记录和链接；只记录实际运行的检查。历史 G2 证据、冻结 contracts 和原始失败材料保持原位，不用新文档覆盖。脚本或产物删除前先做引用清单、替代入口和可恢复归档；本次文档工作不替代删除审批，也不把未验证的实现写成完成。

相关入口：[架构总览](kernel-architecture.md)、[内核现状](current-state.md)、[模块树](../modules/README.md)、[持续记录](continuous-records.md)、[R1 复现规格](reproduction-blueprint.md)。本文件由[2026-10-15 内核目录整理任务](../records/tasks/2026-10-15-kernel-cleanup.md)维护。
