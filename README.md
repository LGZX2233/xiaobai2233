# Project Kernel：Agent 项目交付治理内核

把项目事实、执行过程和交付依据从对话中取出来，交给可追溯账本：模型提出方案，独立程序验收，人确认具体版本，provider 执行并观察真实效果。

[English](README.en.md) ｜ [演示视频 · 3分53秒](docs/assets/demo.mp4) ｜ [设计全文](docs/architecture/kernel-design-and-growth.md) ｜ [模块导航](docs/modules/README.md) ｜ [当前实现](docs/architecture/current-state.md)

## 定位与职责

内核独立于前端和具体 agent 框架，只承担两部分：**执行流**与**项目数据及统计**。DSH、AGH 等宿主继续提供模型循环、工具调用、会话、压缩、skill 加载、子任务和沙箱；内核通过显式端口使用它们。可视化是可选消费者，不是核心运行前提。

执行流把需求、方案、派发、尝试、验收、比较、批准和交付连接起来；数据层保存精确版本、来源、制品摘要、审计、回执和读水位。内核不替模型规划，也不因模型说“完成”而宣布外部动作成功。

## 解决什么问题

| 问题 | 设计机制 | 当前边界 |
| --- | --- | --- |
| 长对话遗忘、换会话重来 | 不可变账本、按水位查询、上下文清单与分层记忆 | v1 账本与水位已有实现；R1 上下文有独立参考实现，尚需真实宿主接线；成本收益未量化 |
| 超时被当失败、重复执行 | 幂等回执、持久 attempt、unknown 保留、只观察对账 | 已有 v1 实现与历史测试；真实宿主 flush 和进程生命周期仍需验收 |
| 模型自报结果不可核对 | 独立 checker、固定验收版本、真实字节摘要 | 热传导案例可拒绝伪造结果；其他领域需对应 checker |
| 批准对象含糊、机器越权 | 人审专属入口、冻结快照、候选变化使旧批准失效 | v1 已实现；真实身份安全边界由宿主建立 |
| 过程黑箱、失败被抹掉 | revision、事件、审计、回执、失败与未选方案留存 | v1 已实现；缺失用量保留未知，不冒充零成本 |
| 模型乱写临时文件、重复总结和无主产物 | 独立执行 root、staging/ready、制品归属、路径预算、quarantine、可审查清理 | **持续任务**：已有制品基础，但完整输出策略、隔离扫描、引用检查与保留期尚未闭环 |
| 大项目模块纠缠、扩展越做越重 | 事实单一所有者、纯领域、显式端口、可替换 provider、模块 L1 | 当前仍有 application 直接 SQL、端口签名偏差和能力汇总缺口，按切片整改 |
| 非可视化能力难以接入模型 | 标准 skills + 宿主适配 + 版本化协议 | **计划**：先做无 UI 契约矩阵与读写 skills，再逐框架验收 |

这里的收益来自事实组织与治理边界，不声称改变模型本身。历史测试不能替代真实部署或本次验收。

## 设计与实现路径

设计模型读项目整体、澄清需求、拆出模块与验收；执行模型只读被分配的模块资料，在独立 root 中尝试实现；收尾模型比较实现包、组合候选、整理依赖并提出采用建议。宿主管调度，人通过可信入口确认。多个模块可以共同采用，不要求全项目只剩一个胜者。

八阶段为：**设计 → 拆分 → 分发 → 执行 → 打包验收 → 收尾 → 人工确认 → 执行并发布采用记录**。范围变化产生新基线并返回拆分；同一请求用原幂等键补查；外部效果不明则保持 unknown，只观察或显式对账。

L0 保存项目整体架构、需求与模块关系；L1 保存模块独立范围、接口、方案和验收。R1 参考实现采用单项目 SQLite 的逻辑分层，不把“双层”宣称为已经部署的物理双库。合回主库前需验收、打包、去耦及人审。

上下文按“身份与约束 → 需求、验收与设计 → 环境、错误与依赖 → 项目资料 → 共享经验”装配。ContextManifest 保存实际来源版本、选择与排除原因及预算；超预算明确报告。问答引用读取时的版本；实时表单暂态归宿主，有意提交后才成为事实。

方案评分、知识使用评分、skill 四维评价分别记录。已选路线 A 是“模型审阅证据并提出采用建议，人确认固定版本”；高分不能替代验收、授权或真实执行成功。机器检查、代理审查、人类批准、外部效果四类事实不混用；“完成”分命令回执、持久化、候选验收、人审、外部效果、采用记录发布六层。

三层记忆为原始过程、带来源与适用条件的项目记忆、显式晋升的共享记忆。有效方法沉淀为版本化 skill，以正确性、适用性、复用收益、可维护性评价；错误与复盘保留根因、证据、修正和回滚，未知根因保持未知。评价方法，不给用户能力打分。

进行中的项目可以先扫描、冻结匹配结果、形成模块/需求映射、由人确认后建立版本初始与备份；迁移不补造旧验收、旧批准或成本记录。完整对象与事务规格见 [R1 复现蓝图](docs/architecture/reproduction-blueprint.md)。

## 模块化、低耦合、可成长

| 边界 | 所有权与约束 |
| --- | --- |
| contracts / domain | 契约、版本、状态和纯规则；领域不访问 SQLite、文件、进程或模型 SDK |
| application | 用例、授权与事务编排；一项原子业务语义保持一个 UnitOfWork |
| data | revision/head、查询水位、来源、事件与回执；事实只有一个主人 |
| provider / adapter | 执行、环境、制品、备份、交付等副作用，通过组合根显式注入 |
| bridge / host | 协议映射、调用身份、工具生命周期；复用宿主，不复制业务状态机 |
| records / skills | 文档维护与模型使用方法；不因此获得内核运行能力或人审权限 |

成长采用稳定核心加可选能力。新模块先明确事实主人、输入输出、失败/未知语义及验收条件，再声明依赖和 capability；能力缺失要明确拒绝。Context、知识、实验、SCM、整理和展示按边界扩展。低耦合必须由依赖检查与行为验收证明，不能只靠目录命名。

当前优先修正调用方端口与实现签名、集中 capability 汇总，再逐步抽取 application 中的 SQL；不以一次大搬迁破坏冻结协议、事务或历史证据。[设计与成长全文](docs/architecture/kernel-design-and-growth.md)记录边界与缺口。

## 项目整洁治理是持续任务

派发时声明输出类型、相对路径、数量/大小预算与保留策略；输出先进入 staging，由真实摘要、attempt 和来源版本建立归属；无主输出进入 quarantine；验收与去耦后生成固定交付清单，经人确认才写目标。任务关闭时列出已采用、未采用、失败、临时及待清理文件，清理前检查引用与保留期，留下可恢复清单和审计。

现有 staging/ready、manifest、digest 和 unknown 是基础，**当前实现还不足以阻止模型任意乱写**。目录隔离不是 OS 沙箱，skill 约定也不是强制访问控制。路径与输出预算、quarantine、引用扫描、保留期、清理 dry-run 和宿主限制统一列入[持续维护任务](docs/plans/kernel-hygiene-and-headless.md)，每个实现切片单独验收。

## 无可视化插件接入 Agent 框架（计划）

模型通过 `project_context`、`design_dispatch`、`execute_verify`、`compare_select`、`delivery_review`、`records_reconcile` 等标准 skills 使用内核。每个 skill 声明触发条件、最小参数、可调用命令、scope、版本引用、失败和 unknown 处理；授权与审计仍归内核，人审仍经独立可信入口。

调用链为 **skill → 宿主 adapter → 版本化 Kernel contract → 内核**。保留自有 stdio JSON-RPC 基线，再为 MCP、tool calling、HTTP 编写薄桥；每种框架分别验收重连、取消、超时、幂等、来源 flush 与可信身份。当前协议不是 MCP，不宣称已经通用兼容。

H0 盘点 skill/command/capability；H1 打通只读状态、上下文、事件与追溯；H2 打通受控设计、派发、执行和验收；H3 接通审阅与交付；H4 逐宿主桥接；H5 根据真实使用改进 skill。优先 H0–H2，详细验收见[接入计划](docs/architecture/kernel-design-and-growth.md#52-计划阶段与验收)。

## 设计与创新一图看懂


下面展示完整设计，按定位、执行结构、数据边界、记忆复用和宿主接入展开。实现范围另见本文现状表与内核现状文档。

### 01 · 项目交付治理内核

定位：Agent 运行时旁边的项目交付治理内核。宿主负责循环、工具、会话和沙箱，内核聚焦执行流以及项目数据与统计。

![项目交付治理内核](docs/assets/design/vision.png)

### 02 · 问题与机制对应

把长流程中的遗忘、重跑、黑箱和耦合逐项对应到可追溯账本、按需装配、未知保留和模块边界。

![问题与机制对应](docs/assets/design/map.png)

### 03 · 三类模型的分工

设计模型读整体并拆模块，执行模型在沙盒中并行实现，收尾模型比较候选并整理依赖，宿主管编排和交互。

![三类模型的分工](docs/assets/design/roles.png)

### 04 · 八阶段执行流

从设计、拆分、分发、执行到打包验收、收尾、人工确认和发布采用记录，范围变化回到拆分并建立新版本。

![八阶段执行流](docs/assets/design/stages.png)

### 05 · 项目与模块双层资料

L0 保存项目整体，L1 保存模块独立资料；执行模型只读自己的模块，回到主库需经过验收、打包、去耦和人工确认。

![项目与模块双层资料](docs/assets/design/duallayer.png)

### 06 · 可重放的上下文装配

上下文工厂按身份约束、需求验收、环境依赖、项目资料和共享经验的优先级装配，每次留下可重放的 ContextManifest。

![可重放的上下文装配](docs/assets/design/context.png)

### 07 · 有版本的问答与表单

模型之间交换问题和回答时引用当时读取的库版本；表单暂态由宿主管理，有意提交后才成为有版本的事实。

![有版本的问答与表单](docs/assets/design/exchange.png)

### 08 · 多方案与组合候选

多个实现包可以并存，收尾阶段组合候选做集成验收；未采用的方案仍保留，便于比较和回看。

![多方案与组合候选](docs/assets/design/combo.png)

### 09 · 三套评分与收尾路线 A

方案、知识使用和 skill 分开评分，收尾走路线 A：先审阅证据，再提交入库方案，最后由人确认采用。

![三套评分与收尾路线 A](docs/assets/design/scoring.png)

### 10 · 四类事实分别留档

机器检查、代理审查、人类批准和真实执行成功四类事实分别记录，批注绑定冻结快照，内容变化后重新申请。

![四类事实分别留档](docs/assets/design/facts.png)

### 11 · 完成的六个层次

“完成”分为命令回执、对象持久化、固定候选验收、人类批准、外部效果证实和采用记录发布六层。

![完成的六个层次](docs/assets/design/done.png)

### 12 · 十二条不变式

十二条不变式约束历史不可覆盖、权限入口、幂等语义、未知结果和并行隔离，让每次判断都能追溯依据。

![十二条不变式](docs/assets/design/invariants.png)

### 13 · 三层记忆与效果评估

记忆分为原始过程记录、带来源和条件的项目记忆、显式晋升的共享记忆，并以验证、复发和回滚来评估效果。

![三层记忆与效果评估](docs/assets/design/memory.png)

### 14 · Skill 复用与错误复盘

有效方法沉淀为带版本的 skill，按正确性、适用性、复用收益和可维护性评分；错误目录保留复盘，帮助避开同类问题。

![Skill 复用与错误复盘](docs/assets/design/reuse.png)

### 15 · 事实所有权与数据流

每类事实只有一个主人：宿主管对话，治理库管任务与交付，知识库管提炼结论，工作台负责投影。

![事实所有权与数据流](docs/assets/design/dataflow.png)

### 16 · 按能力拆分插件

能力按插件拆分：治理、宿主桥接、上下文、记忆、环境、方案实验、产物整理和工作台按需启用，缺失时明确禁用。

![按能力拆分插件](docs/assets/design/plugins.png)

### 17 · 进行中项目的迁移

进行中的项目可以先扫描、冻结匹配结果、由模型与人归纳映射，再以版本初始与备份接入执行流，过程不覆盖原记录。

![进行中项目的迁移](docs/assets/design/migration.png)

### 18 · AGH 宿主适配案例

当前落点是 AGH 插件：AGH 与模型规划工具，插件提供 pk_* 工具和面板，Project Kernel 记录、校验、拦截并写入账本。

![AGH 宿主适配案例](docs/assets/design/arch.png)

### 19 · 热传导反演的治理闭环

热传导反演示例沿着派发策略、独立校验、并列比较、选定理由、申请交付、人工批准、执行交付和只观察对账推进。

![热传导反演的治理闭环](docs/assets/design/flow.png)

## 当前代码与证据

| 轨道 | 范围 | 限制 |
| --- | --- | --- |
| v1 `src/project_kernel/` | 版本账本、派发/attempt、独立验收、人工审批、交付效果、查询与 stdio JSON-RPC | 历史 accepted_g2；release_approved=false；证据模式 test；directory_only；需要完整源码树与显式 provider |
| 本地独立 R1 参考轨道 | S0–S7 独立参考实现：项目/模块分层、多方案、ContextManifest、采用与 SCM 规则 | 本次文档/媒体发布不包含该参考代码；已有独立切片及 synthetic 测试，真实宿主 8 项仍 not_run，未自动合入 v1 |
| AGH adapter | 已有宿主工具与实机运行证据 | 仅作为一个接入案例；不把 AGH 通过外推到其他框架 |
| 可选能力 | KnowledgeService、corpus、文档与 skill 工作流 | KnowledgeService 未接核心 RPC；corpus 默认关闭；文档 skill 不等于运行时自动加载 |
| 后续计划 | 完整垃圾治理、低耦合整改、无 UI 标准 skills、OS 沙箱、真实效果与成本验证 | 不继承历史接受，不记为已完成 |

热传导反演案例使用固定种子的合成数据：粗网格 s1 未达容差；黄金分割 s2 的 α≈0.37286 通过独立重算；卡住的 s3 保留 unknown；篡改 α=0.9 被拒。模型比较并写选择理由，交付先 pending，经人确认固定摘要后才执行；对账只观察、不重复写入。[样例与历史输出](docs/submission/测试样例.md)、[实机证据](docs/submission/运行证据.md)分别保留来源。

本轮整理检查：导入边界 **3 passed**、278 个 Python 文件内存编译通过；README 图片/文档链接、模块 registry 和视频摘要另有整理记录。扩展 R1 测试受沙箱写权限限制，不能据此声称本轮全套通过。详见[本次任务](docs/records/tasks/2026-10-15-kernel-cleanup.md)。

## 从源码验证

需要 Python 3.12+，在完整源码树内执行；`contracts/v1` 尚未作为 wheel 资源打包。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider tests/p00_contracts/test_import_boundaries.py -q
.\.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider tests/p14_science_demo tests/p15_innovation_showcase -q
```

最后一条是供复验的命令，不是本轮新增运行结论。AGH 案例配置与可信人工入口见[适配器说明](adapters/agh-plugin/README.md)；内核测试不需要模型 API 密钥。

## 文档入口

| 需要了解 | 入口 |
| --- | --- |
| 完整设计、问题映射、模块边界与无 UI 计划 | [设计与成长](docs/architecture/kernel-design-and-growth.md) |
| 当前可调用能力、部署前提与缺口 | [内核现状](docs/architecture/current-state.md) |
| 对象、事务、不变式、编排、上下文与迁移规格 | [R1 复现蓝图](docs/architecture/reproduction-blueprint.md) |
| 源码所有者与依赖关系 | [模块树](docs/modules/README.md)、[目录分工](docs/development/repository-layout.md) |
| 持续治理和接入待办 | [整洁治理与 headless 计划](docs/plans/kernel-hygiene-and-headless.md) |
| 项目进展与本次清理 | [项目总结](docs/records/project-summary.md)、[整理记录](docs/records/tasks/2026-10-15-kernel-cleanup.md) |
| 设计图与演示 | [3分53秒视频](docs/assets/demo.mp4)、[素材与构建说明](docs/development/demo-build.md) |
| 历史证据 | [验收报告](docs/acceptance/G2-round4-report.md)、[运行证据](docs/submission/运行证据.md) |
