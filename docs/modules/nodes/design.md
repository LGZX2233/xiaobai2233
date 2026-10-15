# 需求、方案与派发

| 字段 | 值 |
| --- | --- |
| node_id | `K-DESIGN` |
| node_kind | `module` |
| document_version | `1.1.0` |
| updated_at | `2026-10-12 Asia/Shanghai` |
| source_version | `1.0.0` |
| source_revision | `0a619766162682606ad57a9aa4c1926d54c1b891` |
| implementation_status | 已实现核心用例；本次新增节点记录，未作新验收 |
| navigation_parent | `K-CORE` |
| conversation_refs | `[]` |

`updated_at` 使用 Asia/Shanghai 日期精度；`source_revision` 是本文静态阅读的源码提交，文档版本单独递增。

## 职责与范围

本节点管理 task 建立、requirement 草稿与确认、design 草稿与确认、execution packet 草稿与确认及撤回。确认 packet 固定需求、方案、验收、规则、环境和 scope 的精确版本；确认仅使 task 进入 `dispatch_ready`，执行由 `K-EXECUTION` 单独发起。

需求确认必须存在至少一个必需验收项，每个验收项绑定该 requirement 草稿和已存在的 recipe。方案内 strategy ID 不重复，选择项必须属于方案。跨项目引用、过期 current 引用、错误 baseline digest、未就绪环境和阻断规则均不能成为有效派发依据。

本节点与 `K-RULES` 共享 `DesignService` 文件，但规则的条件语言、发布和影响预览由规则节点单独描述。模块节点按职责划分，不要求一个节点对应一个文件。

## 节点关系

`depends_on = [K-CONTRACTS, K-STORAGE, K-LEDGER, K-QUERIES, K-IDENTITY, K-RULES]`。

`related_to = [K-EXECUTION, K-DELIVERY, K-ENVIRONMENT, K-BOOTSTRAP, K-RPC, K-RECORDS]`。

| 关系 | 目标 | 含义 |
| --- | --- | --- |
| 导航归属 | `K-CORE` | 执行流的业务入口集合 |
| 依赖 | `K-CONTRACTS` | payload schema、ObjectRef、digest、错误码和枚举 |
| 依赖 | `K-STORAGE`、`K-LEDGER` | 项目 Store、原子 UnitOfWork、不可变 revision、draft/current head 和 CAS |
| 依赖 | `K-QUERIES` | 撤回检查使用已保存的 attempt；规则预览读取指定水位 |
| 依赖 | `K-IDENTITY` | `require_scope` 校验项目、store 和所需 capability |
| 依赖 | `K-RULES` | 派发确认评价 packet 中固定的规则版本 |
| 关联 | `K-ENVIRONMENT` | 环境就绪记录供 packet 引用；当前用例校验任务归属 |
| 关联 | `K-EXECUTION` | attempt 必须消费已确认的 packet，撤回前必须结算活动 attempt |
| 关联 | `K-DELIVERY` | 关键需求、方案、规则发布可使既有批准失效 |
| 关联 | `K-BOOTSTRAP`、`K-RPC` | 装配公开命令，并在发布提交后调用审批刷新 |
| 关联 | `K-RECORDS` | 从需求、方案和派发事实维护任务总结，记录不取代原 revision |

## 源码与接口

| 入口 | 符号 | 用途 |
| --- | --- | --- |
| [设计服务](../../../src/project_kernel/application/design/service.py) | `DesignService.create_task` | `task.create`；保存可信 mode 与 task 初始 revision |
| 同上 | `requirement_save`、`requirement_confirm` | `requirement.save`、`requirement.confirm`；分开草稿、已确认需求和验收版本 |
| 同上 | `design_save`、`design_confirm` | `design.save`、`design.confirm`；保存策略选项和确认决定引用 |
| 同上 | `dispatch_draft`、`dispatch_confirm`、`dispatch_revoke` | 固定 execution packet、校验 baseline、发布或撤回 |
| [引用检查](../../../src/project_kernel/application/design/references.py) | `checked_payload`、`exact`、`current`、`validate_refs` | schema、精确版本、current 指针与项目归属检查 |
| [状态规则](../../../src/project_kernel/domain/flow.py) | `task_transition`、`attempt_is_terminal` | 纯状态转换及活动 attempt 判断 |
| [组合根](../../../src/project_kernel/bootstrap.py) | `KernelServices`、`build_server` | handler 装配和发布后审批刷新 |
| [命令定义](../../../contracts/v1/command-payloads.schema.json) | requirement/design/dispatch payload | 冻结 v1 输入字段，不能由节点文档增加字段 |

写入口使用 `design.write` 或 `dispatch.confirm` capability；规则入口另要求 `rules.publish`。命令返回 `CommandReceipt` 与精确对象引用，`accepted` 表示该命令已提交，不表示 provider 已执行或验收已通过。

## 数据与版本

| 对象 | 写入与引用 |
| --- | --- |
| `task.v1` | 建立时 phase 为 `draft`；派发确认记录 `packet_ref` 与新 phase |
| `requirement.v1` | `draft` 保存修订，确认后发布 `current`，保留 `confirmed_from_ref`、验收项和 `acceptance_refs` |
| `acceptance.v1` | 独立不可变验收依据，与 exact requirement 草稿绑定 |
| `design.v1` | 多策略选项与选中策略；draft/current 分开 |
| `execution_packet.v1` | task/design/requirement/acceptance/rules/environment/scope 等精确引用；draft 与 current 指向已保存版本 |

packet 确认不修改原 packet payload 或 digest。撤回追加新 revision，保存 `revoked` 和理由。新 rules 发布不会回写已保存 packet；后续执行和交付仍需要各自的 current、模式和证据检查。

## 需求记录

既有冻结要求的正式文字来自 [G2 第四轮条件表](../../acceptance/G2-round4/checks.json)，本表只是模块定位，不改写冻结验收。

| 记录 | 来源与要求 | 当前落点 |
| --- | --- | --- |
| 冻结 `AC12` | packet 及 scope/验收/rules 固定；确认只到 `dispatch_ready` | `dispatch_draft`、`dispatch_confirm` |
| 冻结 `AC13` | 非法规则拒绝，未知事实不能绕过限制 | `dispatch_confirm` 消费 `K-RULES` 的结果 |
| 冻结 `AC18` | 零必需验收项不能 passed | `requirement_confirm` 在需求确认时先拒绝零必需项；验收结果由 `K-DELIVERY` 再检查 |
| 冻结 `AC21` | 关键发布使批准失效，无关名称和审计不误失效 | `K-BOOTSTRAP` 的发布 handler 与 `K-DELIVERY.refresh_approvals` |
| 冻结 `AC30` | 零链接需求进入覆盖分母，N/A 明确，多跳追溯正确 | 此节点提供需求与 packet 事实；覆盖/追溯结果归 `K-QUERIES` |
| 新增 `REQ-CCR-01`、`REQ-CCR-02` | [持续记录需求](../../requirements/2026-10-10-continuous-records.md)：维护可导航节点及需求、验收、版本和更新记录 | 本文与结构化模块索引；不新增业务命令 |
| 新增 `REQ-CCR-03` | [持续记录需求](../../requirements/2026-10-10-continuous-records.md)：明确有向关系，允许空和多对多，不关联本轮对话 | 本文 depends_on/related_to 与 [关系索引](../registry.json)；conversation_refs 为空 |
| 新增 `REQ-CCR-04`、`REQ-CCR-05` | [持续记录需求](../../requirements/2026-10-10-continuous-records.md)：任务与项目总结引用原始事实 | 关联 `K-RECORDS` 与 [维护 skill](../../../.agents/skills/kernel-maintain-records/SKILL.md)；总结不能代替 requirement、acceptance 或确认决定 |
| 新增 `REQ-CCR-11` | 内核结构清晰与冻结证据保护 | 新增文档记录，保持源码、协议与验收档案原状 |

## 历史验收记录

以下为 G2 第四轮已有 `accepted` 条件的映射，实际签字和 exact JUnit 绑定以 [checks.json](../../acceptance/G2-round4/checks.json) 为准。本次没有运行测试，也没有给整个节点新增接受结论；G2 保持 `accepted_g2`，`release_approved=false`。

| AC 与条件 | 历史观察 | 原始证据或审查 |
| --- | --- | --- |
| `AC12` packet 冻结 | 合法确认前后 exact revision、payload、digest 相同；错误 baseline 返回 `SNAPSHOT_CHANGED` | [packet 场景][ac12] |
| `AC12` scope/验收/rules 固定 | scope、acceptance_refs、rule_refs 与原输入一致；新规则发布后原 packet 保持旧规则 revision | [packet 场景][ac12] |
| `AC12` 确认只 dispatch_ready | 没有 attempt revision 或 provider 执行 | [packet 场景][ac12]、[执行审查][execution-review] |
| `AC18` 需求确认的零必需项拒绝 | 常规 `requirement.confirm` 拒绝零必需项；故障注入的 optional-only 验收仍不能 passed | [零必需项场景][ac18]；完整验收归属见 [K-DELIVERY](delivery.md) |
| `AC21` 关键发布后失效 | 需求确认已提交，旧 pending/approved 追加 superseded；重放原回执和查询不恢复批准 | [pending 场景][ac21-pending]、[approved 场景][ac21-approved]、[独立审批复核][approval-review] |
| `AC21` 无关变更不误失效 | task display_name 和普通审计变化保持快照 digest，不阻止批准 | [无关变更场景][ac21-unrelated] |

`AC30` 的完整条件证据保存在 [checks.json](../../acceptance/G2-round4/checks.json)，此节点仅提供上游需求事实，查询节点负责其验收映射。`AC43` 的公开闭环包含这些入口，但不扩展本节点接受范围到真实宿主或工作台。

## 当前限制与维护要求

`design.confirm` 保存存在的 decision 引用，不应据此声称它实现了交付批准；交付批准必须走可信 human entry。provider 配置、execution root、recipe 等版本由显式宿主提供，G2 样本属于 test 模式。

公开发布 handler 提交后会刷新批准；直接调用 `DesignService` 不附带该 hook。若宿主绕过 RPC，必须核对自己调用路径的审批刷新和后续 current 检查，不能仅依赖一条历史 approved 记录。

任务、需求、方案、packet 和审批各有独立状态，本文导航不创造统一大状态机。新增总结与学习记录在 `K-RECORDS` 文档工作流中维护，不能混入冻结 packet 或覆盖 immutable revision。

待办关联：`REQ-CCR-01/02/03/04/05` 的内容变更需同步节点记录、需求引用和项目总结；任何新增 runtime 入口需要独立接口与验收记录。真实 DSH 的任务、Session、Jobs 与取消映射属于 G3，未在本次执行。

## 变更记录

| 日期 | 文档版本 | 源码依据 | 变更与验证 |
| --- | --- | --- | --- |
| 2026-10-10 | `1.0.0` | `0a619766162682606ad57a9aa4c1926d54c1b891` | 建立需求/方案/派发节点，记录冻结 AC、源码、依赖、限制和新增需求；静态阅读，未运行测试 |

[ac12]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac12_rpc_packet_freezes_b0/execution-evidence.json
[ac18]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac18_public_verification_0/delivery-evidence.json
[ac21-pending]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac21_public_requirement_c0/delivery-evidence.json
[ac21-approved]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac21_public_requirement_c1/delivery-evidence.json
[ac21-unrelated]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac21_unrelated_task_name_0/delivery-evidence.json
[execution-review]: ../../reviews/2026-10-09-round4/execution-review.md
[approval-review]: ../../reviews/2026-10-09-round4/approval-peer-review.md

## R1 从零复现规格

文档版本 1.1.0：[详细规格](../../architecture/reproduction/02-orchestration.md)补充初始澄清基线、模块需求/范围/验收与分发规则，对应 [REQ-BOUNDARY-13](../../requirements/2026-10-12-kernel-boundaries.md)。R1 参照源码 `16410c9fbf4a8507445b4603e371e701614e4499`，新增字段、接口与流程尚未实现或行为验收；实际本轮交付由[任务记录](../../records/tasks/2026-10-12-kernel-boundaries.md)拥有，不改变本节点的既有运行依赖或历史接受。
