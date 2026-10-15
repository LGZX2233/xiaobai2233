# K-RECORDS：持续总结与学习记录

| 字段 | 值 |
| --- | --- |
| node_id | K-RECORDS |
| node_kind | workflow |
| document_version | 1.4.0 |
| updated_at | 2026-10-12 Asia/Shanghai |
| source_version | 1.0.0（项目基线；本节点为新增文档工作流） |
| source_revision | `16410c9fbf4a8507445b4603e371e701614e4499` |
| implementation_status | 文档及项目 skill 可用，按任务维护，无 runtime 接线 |
| navigation_parent | K-EXTENSIONS |
| conversation_refs | [] |

## 职责与入口

本节点通过[记录目录](../../records/README.md)和[项目 skill](../../../.agents/skills/kernel-maintain-records/SKILL.md)维护任务总结、项目总体摘要、术语/错误解释、学习资料及描述式用户画像。[持续记录架构](../../architecture/continuous-records.md)拥有元数据、更新、撤回和删除规则；[项目 AGENTS](../../../AGENTS.md)提供发现入口。

[技能成长](../../architecture/skill-growth.md)、[版本索引](../../records/skills/registry.json)和[成长 skill](../../../.agents/skills/kernel-grow-skills/SKILL.md)维护方法适用范围、实际复用评价、反例及修订。当前维护 skill 2.0.0、成长 skill 1.1.0均待实际观察；用户画像不评分。

输入是本次用户要求、工作中的明确决定、真实操作结果及来源版本；输出是可修改、模型可阅读的 Markdown。不建数据库或新的 Python 包，不自动监听对话/文件，也不创建用户知识分数。K-LEDGER 是运行账本，本节点是文档工作流，两者不能混写。

## 关系

`depends_on=[K-ROOT]` 是工作流对项目事实与适用范围的依赖，非运行导入。`related_to=[K-DESIGN, K-RULES, K-EXECUTION, K-DELIVERY, K-QUERIES, K-KNOWLEDGE, K-CORPUS]` 支持从相应资料维护记录，不表示宿主已经自动同步。

## 需求和交付记录

| 要求 | 本轮入口与状态 |
| --- | --- |
| [REQ-CCR-04](../../requirements/2026-10-10-continuous-records.md) | [本轮任务总结](../../records/tasks/2026-10-10-kernel-maintenance.md)与[任务模板](../../records/templates/task-record.md) |
| REQ-CCR-05 | [项目总结](../../records/project-summary.md)，原事实仍链接各自 owner |
| REQ-CCR-06 | [术语/错误](../../records/terms-and-errors.md)与[学习资料](../../records/learning/2026-10-10-modules-and-rules.md)，静态发现不伪造运行故障 |
| REQ-CCR-07 | [用户学习画像](../../records/user-learning-profile.md)，已确认与推断分开，熟悉度未知，无评分，可纠正 |
| REQ-CCR-09/10 | [skill](../../../.agents/skills/kernel-maintain-records/SKILL.md)与[上下文流程](../context-selection.md)，从节点选相关来源，不自动全量加载 |
| REQ-CCR-11 | 文件集中于文档与 skill；不修改核心源码或历史接受资料 |
| [REQ-SG-02/03/04/05/06](../../requirements/2026-10-10-clean-layout-and-skill-growth.md) | 版本适用、评价和复核、操作授权、读者体验；产物与静态核对见[新任务](../../records/tasks/2026-10-10-layout-and-skill-growth.md) |

## 接受范围与更新

本节点是新增文档交付，没有历史 AC 运行接受：`acceptance_refs=[]`（历史 G2 仅作项目摘要来源）。静态核对记录在[本轮任务](../../records/tasks/2026-10-10-kernel-maintenance.md)；用户要求不用测试，本轮不运行 skill 行为测试或内核运行测试。

记录随工作检查点、决定变化、用户纠正和结束时维护；不经过工作流的改动不会自行同步。知识熟悉度需要明确依据，不从单个提问或错误反推长期能力。真正自动触发、宿主对话关联或跨项目存储需新运行设计和接受。

| 日期 | 文档版本 | 变更 |
| --- | --- | --- |
| 2026-10-10 | 1.0.0 | 建立任务/项目/学习记录及 skill 工作流，与运行账本分清职责 |
| 2026-10-10 | 1.1.0 | 增加技能成长、版本索引及当前需求，保留未接线和待观察状态 |

## 2026-10-12 设计补充

[数据处理评分与失败分析](../../architecture/skill-growth.md#数据处理接口与评分范围)对应 [REQ-BOUNDARY-04/05](../../requirements/2026-10-12-kernel-boundaries.md)。静态复核与限制见[本轮复核](../../reviews/2026-10-12-boundary-review.md)，实际交付和核对见[任务记录](../../records/tasks/2026-10-12-kernel-boundaries.md)。本次只改文档与 skill；评分/总结保留在数据处理，不增加执行依赖或运行接口。

文档版本 1.2.0：补充消费者、外部效果或数据处理职责；无新增行为接受。

文档版本 1.3.0：[REQ-BOUNDARY-09/12](../../requirements/2026-10-12-kernel-boundaries.md)确定路线 A 与多代理实施要求；[持续记录](../../architecture/continuous-records.md)沿用已给授权、按文件拆分职责并汇总实际检查。本次只维护同轮记录，不新增运行触发。

## R1 从零复现规格

文档版本 1.4.0：[详细规格](../../architecture/reproduction-blueprint.md)补充R1 规格阅读入口及同轮多代理维护，对应 [REQ-BOUNDARY-13](../../requirements/2026-10-12-kernel-boundaries.md)。R1 参照源码 `16410c9fbf4a8507445b4603e371e701614e4499`，新增字段、接口与流程尚未实现或行为验收；实际本轮交付由[任务记录](../../records/tasks/2026-10-12-kernel-boundaries.md)拥有，不改变本节点的既有运行依赖或历史接受。
