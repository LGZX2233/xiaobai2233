# 内核现状

内核可以保存和查询项目执行事实，管理版本、审批及外部交付效果。它由宿主配置和调用，使用前需要完整源码树、可信调用身份和对应 provider。下表便于按能力查找；[架构](kernel-architecture.md)解释职责与数据流，[模块树](../modules/README.md)提供源码、需求和验收入口。

文档版本：1.5.0；更新日期：2026-10-12（Asia/Shanghai）。RPC 异常处理修复和前期模块、记录及布局维护已提交并推送 `main`。修复仅静态审查、未行为验证；具体要求及结果见[修复要求](../requirements/2026-10-10-rpc-resilience.md)、[任务记录](../records/tasks/2026-10-10-rpc-resilience.md)和[同步记录](../handoffs/2026-10-10-rpc-fix-main-sync.md)。

2026-10-12 补充了[消费者一致性](consumer-consistency.md)、[SCM 效果映射](scm-effect-mapping.md)、[训练职责](training-data-boundary.md)及[评分/失败分析](skill-growth.md#数据处理接口与评分范围)。本次仅文档与 skill 修订，源码基准为 `16410c9fbf4a8507445b4603e371e701614e4499`；[复核记录](../reviews/2026-10-12-boundary-review.md)纠正部分旧评价，不宣称完成全源码审查或新增运行接受。

同日新增[从零复现总指南与四章规格](reproduction-blueprint.md)，将已选路线 A、项目/模块分层、多方案并行、上下文和采用流程写成 R1 参考实现。R1 新字段、接口、schema 与状态仍未实施，不能作为当前 v1 的可调用能力清单。

## 使用范围

独立核心的历史 G2 状态是 `accepted_g2`，`release_approved=false`。实际执行保证为 `directory_only`，不等于操作系统沙盒；验收使用 verified synthetic test proof，不能直接作为真实宿主人审接入的证据。

真实 DSH 适配属于 G3，工作台属于 G4，可选知识和语料属于 G2-K；生产恢复和真实试点仍需后续工作。当前没有 Git 交付 provider，仓库同步不能代替内核的交付效果。各平台也需单独宿主验收，自有 stdio JSON-RPC 不是 MCP。

## 能力与入口

| 能力 | 当前实现 | 限制与入口 |
| --- | --- | --- |
| 项目身份 | 身份 SQLite、项目创建与对账、项目 Store 身份校验、跨库绑定操作和回执 | `build_identity_server` 独立提供 provision/reconcile；配置 `identity_registry` 后项目 RPC 提供 bind |
| 需求、方案、规则 | draft/current 精确版本、验收项、规则预览、冻结派发包 | application 与纯 domain 规则共同约束；确认派发只到 dispatch_ready |
| 执行 | 持久 attempt 意图、provider handle、来源结算、取消请求、真实输出制品 | 注入 executor 与制品存储；实际目录隔离不等于操作系统沙盒；未知结果不自动重跑 |
| 验收与选择 | 绑定候选和验收版本的报告、可信人审补充、方案比较和显式选择 | 零必需项、缺失检查、旧候选和 production 中的 test 证据不能通过 |
| 审批与交付 | 快照摘要、独立人类入口、关键依据失效、claim/apply-start/epoch、效果观察与显式对账 | `DeliveryProvider` 显式注入；文件实现由 `BundleDeliveryProvider` 包装；回执 accepted 不代表效果成功 |
| 制品与归档 | staging/ready、真实字节摘要、不可变 manifest、各 sink 回执与 repair | artifact/archive provider 按配置工作；repair 不重新执行任务或交付；本地来源连续不证明宿主 flush |
| 备份与恢复 | SQLite 一致备份、校验、隔离副本恢复、独立离线 test-store 替换 | business_revision 恢复为新 draft；灾难恢复 RPC 不替换活动库；离线替换只围住协作 Kernel 写者 |
| 来源与查询 | 来源身份、去重/冲突、连续序号与 gap；as_of、分页、总览、追溯和 unknown 用量 | rebuild 是导出的只读 API，`persisted=false`；没有 projection.rebuild RPC 或后台投影 worker |
| 旧数据迁移 | 可信不可变 snapshot、规划、导入、对账和隔离 | `legacy_config` 仅 test 模式；不补造通过、审批或费用，不接受生产导入声明 |
| knowledge | 上下文预算、精确来源、反馈去重、评分与提升 API | `KernelServices` 未装配 `KnowledgeService`；knowledge 命令未提供 RPC；提升缺口见设计审查 |
| corpus | 数据集构建、样本审核、独立导出授权、文件导出与观察、清理计划 | `enable_corpus` 默认 false；需 policy/purpose/sink，G2-K 单独接受；清理计划不删除文件 |
| RPC 与 Node bridge | 版本化 JSON-RPC、分帧、Schema、可信句柄、超时后原 key 补查；RPC 解析和编码异常处理修复已实施 | 自有 stdio 协议不是 MCP；本次修复仅静态审查、未行为验证，见修复记录 |
| 模块导航、记录与技能 | [23节点文档树](../modules/README.md)、关系索引、项目/任务总结、学习资料、描述式用户画像及项目 skill | 由当前 Codex 工作流应用，尚无内核运行服务、自动同步或对话映射；技能可评价，用户画像不评分 |

[持续记录](continuous-records.md)、[规则扩展](pluggable-rules.md)与[技能成长](skill-growth.md)分别说明记录职责、项目附加规则和可复用工作方法。当前文档与布局工作见[任务记录](../records/tasks/2026-10-10-layout-and-skill-growth.md)；它不会给新能力继承历史 G2 接受。

`initialize.supported_commands` 表示配置后注册的入口。核心命令可以已注册而缺少执行 provider，调用时返回 `CAPABILITY_UNAVAILABLE`。未注册入口返回 `UNSUPPORTED_COMMAND`；两者不能混写成“所有已公布能力都可执行”。当前 `provider_capabilities` 未由组合根汇集实际 provider 声明。

## 运行与部署条件

内核是由宿主组合和调用的源码项目，没有独立生产应用启动器、动态 provider registry、自动对账 worker 或通用 async 作业调度器。宿主负责可信身份、调用调度、provider 生命周期、关闭连接和真实会话 flush。同步业务调用会调用 executor/checker/provider；`accepted` 的持久操作身份不等于异步宿主任务已经完成。

application 的部分代码直接使用 Store SQL；纯 domain 规则不执行外部 I/O。冻结 `ports/ports.py` 保留服务声明，当前具体类不全都逐签名实现这些 Protocol；适配器应核对真实消费端，不能仅按冻结端口推断可直接替换。

当前 Schema、catalog 和 digest 读取源码仓库中的 `contracts/v1`。`pyproject.toml` 尚未声明这些仓库外置文件的安装资源；因此完整源码树是当前运行前提，不能声称普通 wheel 安装已可独立运行。

运行实现位于 `src/project_kernel/` 与 `bridge/protocol/`，测试位于 `tests/`；Node 测试已迁至 `tests/bridge/`。目录职责和历史路径映射见[目录分工](../development/repository-layout.md)。前一布局阶段只调整测试引用并清理功能源码缓存；当前 RPC 修复修改了 `framing.py` 与 `protocol.py`，见本次任务记录。

## 待处理问题

[静态设计审查](../reviews/2026-10-10-design-review.md#核心-rpc-问题)保留修复前的 RPC 递归解析和 Unicode 错误响应发现。当前工作树已将解码递归限制和不可编码字符串转换为解析失败，只回显匹配冻结 id 正则的 id，并为响应序列化失败提供错误兜底；这些修复未做行为验证。knowledge 提升仍有授权及持久效果处理问题，需要在开放 G2-K 前处理。处理范围和宿主、生产部署工作见[后续计划](../plans/2026-10-09-kernel-remediation-next.md)。

## 日期、来源与历史验收

更新日期：2026-10-10（Asia/Shanghai，日期精度）。原审查依据为项目1.0.0、`0a619766162682606ad57a9aa4c1926d54c1b891`；当前修复源码为 `c36453981a2151c7652b54301c0cb5a7a1840856`。主分支合并与推送事实见[同步记录](../handoffs/2026-10-10-rpc-fix-main-sync.md)，后续同步文档不再改变 RPC 实现。

[第四轮验收](../acceptance/G2-round4-report.md)记录冻结的25项87条件、620项不重复 Python、19项 Node 和1281项文件校验。它们是历史证据，不是本次文档修订运行的检查。[条件裁决](../acceptance/G2-round4/checks.json)与[限制](../acceptance/G2-round4/limitations.md)保留具体依据。

第四轮 manifest 保存验收时的文档字节。维护文档与历史摘要不同是预期审计差异；不能为消除差异重建旧 manifest 或签字，也不能把新增审查写成已纳入原验收。冻结协议、原始资料和既有 ZIP 继续作为历史输入。

测试搬迁使原 manifest 四个旧路径不再位于当前工作树，Python vectors 消费端及 Node 测试引用也已改变；实际差异由当前任务记录列出。原历史1281项校验结论保留，不等于整理后的工作树与原 manifest 逐项相同。
